"""Intake runner: gather text (inquiry + attachments), propose, adjudicate.

Caller decides *when* (new inquiry / manual button / connector sync); this
module owns the how, and never lets an AI failure break the main flow.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Inquiry, InquiryAttachment, Organization
from ..audit import audit
from ..requirement_service import RequirementService
from . import get_ai
from .intake import propose_slots
from .org_gate import intake_enabled


def run_intake(db: Session, org_id: int, inquiry: Inquiry,
               user_id: int | None) -> dict | None:
    """AI propose + state-machine adjudication. Returns summary or None."""
    ai = get_ai()
    if not ai.available():
        return None
    org = db.get(Organization, org_id)
    if org is None or not intake_enabled(db, org):
        return None

    parts = [inquiry.raw_text or ""]
    for att in db.scalars(select(InquiryAttachment).where(
            InquiryAttachment.org_id == org_id,
            InquiryAttachment.inquiry_id == inquiry.id,
            InquiryAttachment.status == "extracted")).all():
        if att.extracted_text:
            parts.append(att.extracted_text)
    text = "\n\n".join(p for p in parts if p).strip()
    if not text:
        return None

    proposals = propose_slots(text)
    if not proposals:
        return None
    provider = ai.name
    summary = RequirementService(db, org_id).apply_ai_proposals(inquiry, proposals, provider)
    audit(db, org_id, user_id, "ai.intake", "inquiry", inquiry.id,
          {"provider": provider, **summary})
    return summary
