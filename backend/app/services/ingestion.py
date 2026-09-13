"""Inquiry ingestion pipeline.

Single entry point used by manual paste, connectors, webhooks and forms:
    message -> normalize -> dedupe(hash) -> parse slots -> requirement state
    -> summary -> completeness -> customer/company auto-link -> audit
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (AuditEvent, Contact, ConversationMessage, ConversationThread,
                      Customer, ExternalMessage, Inquiry)
from ..config import settings
from . import followup as followup_svc
from .normalization import content_hash, resolve_place
from .requirement_service import RequirementService
from .slot_extractor import detect_language

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# greetings/copy-paste hallmarks of spam blasts
_SPAM_MARKS = re.compile(
    r"\bdear\s+(sir|madam|friend)\b.{0,40}\b(we\s+are|buyers?|importers?)\b.{0,80}\b(buy|purchase|order)\b",
    re.I | re.S)


def _utcnow():
    return datetime.now(timezone.utc)


def find_or_create_customer(db: Session, org_id: int, message_text: str,
                            sender: str = "", channel: str = "manual") -> tuple[Customer | None, Contact | None]:
    """Link inquiry to a customer by sender email; create shell customer when new."""
    email = None
    if sender and "@" in sender:
        email = sender.strip().lower().split()[-1].strip("<>")
    if email is None:
        m = _EMAIL_RE.search(message_text or "")
        email = m.group(0).lower() if m else None

    contact = None
    customer = None
    if email:
        contact = db.scalar(select(Contact).where(Contact.org_id == org_id,
                                                  Contact.email == email))
        if contact:
            customer = db.get(Customer, contact.customer_id)
    if customer is None:
        name_guess = (sender.split("@")[0].replace(".", " ").title() if email else
                      (sender or "New Customer")[:80])
        place = resolve_place(message_text or "")
        customer = Customer(
            org_id=org_id,
            company_name=name_guess,
            country=(place or {}).get("country", ""),
            source_channel=channel,
            stage="new",
        )
        db.add(customer)
        db.flush()
        contact = Contact(org_id=org_id, customer_id=customer.id,
                          name=name_guess, email=email or "", is_primary=True)
        db.add(contact)
        db.flush()
    return customer, contact


def ingest_external_message(db: Session, org_id: int, account, payload: dict) -> dict:
    """Idempotent ingestion of one external message.

    payload keys: external_message_id, thread_external_id, sender, received_at,
    text, attachments, raw_json.
    Returns {external_message, inquiry, message, duplicate, changes}.
    """
    text = (payload.get("text") or "").strip()
    ext_id = str(payload.get("external_message_id") or "")
    chash = content_hash(text) if text else content_hash(json.dumps(payload.get("raw_json") or {}, default=str))

    # ---- idempotency: same external message id -> skip ----------------------
    if ext_id:
        dup = db.scalar(select(ExternalMessage).where(
            ExternalMessage.org_id == org_id,
            ExternalMessage.connector_account_id == account.id,
            ExternalMessage.external_message_id == ext_id))
        if dup:
            return {"duplicate": True, "external_message_id": dup.id,
                    "reason": f"external_message_id {ext_id} already ingested"}

    # ---- content hash dedupe within same external thread --------------------
    thread_ext = str(payload.get("thread_external_id") or payload.get("sender") or "")
    if chash:
        dup2 = db.scalar(select(ExternalMessage).where(
            ExternalMessage.org_id == org_id,
            ExternalMessage.connector_account_id == account.id,
            ExternalMessage.thread_external_id == thread_ext,
            ExternalMessage.content_hash == chash))
        if dup2:
            return {"duplicate": True, "external_message_id": dup2.id,
                    "reason": "identical content already ingested from same thread"}

    received_at = payload.get("received_at") or _utcnow()
    if isinstance(received_at, str):
        try:
            received_at = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        except ValueError:
            received_at = _utcnow()

    em = ExternalMessage(
        org_id=org_id, connector_account_id=account.id, channel=account.connector_type,
        external_account=str(payload.get("external_account") or account.name or account.connector_type),
        thread_external_id=thread_ext, external_message_id=ext_id,
        sender=str(payload.get("sender") or ""), received_at=received_at,
        raw_content=json.dumps(payload.get("raw_json") or {"text": text}, ensure_ascii=False, default=str),
        normalized_content=text, attachments_json=json.dumps(payload.get("attachments") or []),
        content_hash=chash, process_status="pending",
    )
    db.add(em)
    db.flush()

    customer, contact = find_or_create_customer(db, org_id, text, em.sender, account.connector_type)

    inquiry = Inquiry(
        org_id=org_id, customer_id=customer.id if customer else None,
        contact_id=contact.id if contact else None,
        title=_make_title(text), raw_text=text,
        language=detect_language(text), source_channel=account.connector_type,
        external_message_id=em.id,
        quality_flag="low_quality" if _is_low_quality(text) else "normal",
    )
    db.add(inquiry)
    db.flush()

    thread = db.scalar(select(ConversationThread).where(
        ConversationThread.org_id == org_id,
        ConversationThread.inquiry_id == inquiry.id))
    if thread is None:
        thread = ConversationThread(org_id=org_id, inquiry_id=inquiry.id,
                                    channel=account.connector_type,
                                    external_account=em.external_account,
                                    external_session_id=thread_ext)
        db.add(thread)
        db.flush()

    msg = add_message(db, org_id, inquiry, thread.id, direction="in",
                      sender=em.sender, text=text, sent_at=received_at,
                      external_message_id=ext_id, content_hash_=chash,
                      attachments=payload.get("attachments") or [])

    em.process_status = "processed"
    em.inquiry_id = inquiry.id
    if customer:
        customer.last_contact_at = received_at
        if not customer.next_follow_up_at:
            customer.next_follow_up_at = received_at + timedelta(days=3)
    db.add(AuditEvent(org_id=org_id, action="inquiry.created", entity_type="inquiry",
                      entity_id=str(inquiry.id),
                      detail_json=json.dumps({"channel": account.connector_type,
                                              "external_message": em.id}, ensure_ascii=False)))
    return {"duplicate": False, "external_message": em, "inquiry": inquiry,
            "message": msg, "customer": customer}


def _make_title(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return "(empty inquiry)"


def _is_low_quality(text: str) -> bool:
    if len((text or "").strip()) < 25:
        return True
    return False


def add_message(db: Session, org_id: int, inquiry: Inquiry, thread_id: int | None,
                direction: str, sender: str, text: str, sent_at=None,
                external_message_id: str = "", content_hash_: str = "",
                attachments: list | None = None) -> ConversationMessage:
    chash = content_hash_ or content_hash(text)
    msg = ConversationMessage(
        org_id=org_id, inquiry_id=inquiry.id, thread_id=thread_id,
        direction=direction, sender=sender,
        sent_at=sent_at or _utcnow(), raw_content=text, normalized_content=text,
        attachments_json=json.dumps(attachments or []),
        external_message_id=external_message_id, content_hash=chash,
    )
    db.add(msg)
    db.flush()

    if direction == "in":
        svc = RequirementService(db, org_id)
        changes = svc.ingest_message(inquiry, msg)
        svc.recompute(inquiry)
        msg.parse_json = msg.parse_json or "{}"
        # persist a compact change summary on the message for the timeline UI
        try:
            msg.parse_json = json.dumps({**json.loads(msg.parse_json or "{}"),
                                         "changes": [
                                             {"field": c.field, "type": c.change_type,
                                              "old": c.old_value, "new": c.new_value,
                                              "note": c.note} for c in changes]},
                                        ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    inquiry.updated_at = _utcnow()
    db.flush()
    return msg
