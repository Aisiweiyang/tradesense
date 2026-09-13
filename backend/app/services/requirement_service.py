"""DB-facing requirement state service: ingest messages, manual edits, history."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (ClarificationLog, ConversationMessage, Inquiry,
                      RequirementHistory, RequirementSlot, RequirementState)
from . import normalization as norm
from .fields import FIELD_DEFS, completeness_breakdown
from .requirement_engine import ChangeRecord, SlotData, apply_updates, manual_override, unlock
from .slot_extractor import SlotUpdate, extract_slots


def _slot_data(slot: RequirementSlot) -> SlotData:
    return SlotData(
        field=slot.field, raw_value=slot.raw_value, value=slot.value,
        normalized_value=slot.normalized_value, unit=slot.unit, status=slot.status,
        confidence=slot.confidence, source_message_id=slot.source_message_id,
        history_values=json.loads(slot.history_values or "[]"),
        locked=slot.locked, confirmed=slot.confirmed,
    )


class RequirementService:
    def __init__(self, db: Session, org_id: int):
        self.db = db
        self.org_id = org_id

    # ------------------------------------------------------------------ state
    def ensure_state(self, inquiry_id: int) -> RequirementState:
        state = self.db.scalar(
            select(RequirementState).where(
                RequirementState.org_id == self.org_id,
                RequirementState.inquiry_id == inquiry_id,
            )
        )
        if state is None:
            state = RequirementState(org_id=self.org_id, inquiry_id=inquiry_id)
            self.db.add(state)
            self.db.flush()
            for name in FIELD_DEFS:
                self.db.add(RequirementSlot(
                    org_id=self.org_id, state_id=state.id, inquiry_id=inquiry_id,
                    field=name, status="unknown",
                ))
            self.db.flush()
        return state

    def slots_map(self, inquiry_id: int) -> dict[str, RequirementSlot]:
        self.ensure_state(inquiry_id)
        rows = self.db.scalars(
            select(RequirementSlot).where(
                RequirementSlot.org_id == self.org_id,
                RequirementSlot.inquiry_id == inquiry_id,
            )
        ).all()
        return {r.field: r for r in rows}

    def slots_data(self, inquiry_id: int) -> dict[str, SlotData]:
        return {f: _slot_data(r) for f, r in self.slots_map(inquiry_id).items()}

    def active_values(self, inquiry_id: int) -> dict[str, dict]:
        """Plain view of active/meaningful slot values for downstream services."""
        out = {}
        for f, r in self.slots_map(inquiry_id).items():
            meaningful = r.status in ("active", "conflicting", "needs_confirmation", "unconstrained")
            out[f] = {
                "value": r.value, "normalized": r.normalized_value, "unit": r.unit,
                "status": r.status, "confidence": r.confidence, "locked": r.locked,
                "confirmed": r.confirmed, "source_message_id": r.source_message_id,
                "raw": r.raw_value,
            } if meaningful else {"value": "", "normalized": "", "unit": "", "status": r.status,
                                  "confidence": 0.0, "locked": r.locked, "confirmed": r.confirmed,
                                  "source_message_id": None, "raw": ""}
        return out

    # ------------------------------------------------------------------ ingest
    def ingest_message(self, inquiry: Inquiry, message: ConversationMessage) -> list[ChangeRecord]:
        """Parse a message and merge it into the multi-round requirement state."""
        extraction = extract_slots(message.normalized_content or message.raw_content)
        message.parse_json = json.dumps(
            {"language": extraction.language,
             "updates": [u.to_dict() for u in extraction.updates]},
            ensure_ascii=False)
        slots = self.slots_data(inquiry.id)
        changes = apply_updates(slots, extraction.updates, message.id)
        self._persist_changes(inquiry, slots, changes, source_message_id=message.id)
        inquiry.language = inquiry.language or extraction.language
        return changes

    def _persist_changes(self, inquiry: Inquiry, slots: dict[str, SlotData],
                         changes: list[ChangeRecord], source_message_id: int | None = None,
                         actor: str = "system") -> None:
        rows = self.slots_map(inquiry.id)
        for c in changes:
            row = rows.get(c.field)
            if row is None:
                continue
            data = slots[c.field]
            row.raw_value = data.raw_value
            row.value = data.value
            row.normalized_value = data.normalized_value
            row.unit = data.unit
            row.status = data.status
            row.confidence = data.confidence
            row.source_message_id = data.source_message_id
            row.locked = data.locked
            row.confirmed = data.confirmed
            row.history_values = json.dumps(data.history_values, ensure_ascii=False)
            self.db.add(RequirementHistory(
                org_id=self.org_id, inquiry_id=inquiry.id, slot_id=row.id, field=c.field,
                change_type=c.change_type, old_value=c.old_value, new_value=c.new_value,
                old_status=c.old_status, new_status=c.new_status,
                source_message_id=source_message_id, actor=actor, note=c.note,
            ))
        self.recompute(inquiry)

    # ------------------------------------------------------------------ manual edit
    def manual_set(self, inquiry: Inquiry, fld: str, raw: str, lock: bool = False) -> ChangeRecord:
        if fld not in FIELD_DEFS:
            raise ValueError(f"unknown field: {fld}")
        value, normalized, unit = _normalize_manual(fld, raw)
        slots = self.slots_data(inquiry.id)
        change = manual_override(slots, fld, raw, value, normalized, unit=unit, lock=lock)
        self._persist_changes(inquiry, slots, [change], actor="human")
        # resolving a conflicting field also closes its open clarification
        if change.new_status == "active":
            for log in self.db.scalars(select(ClarificationLog).where(
                    ClarificationLog.org_id == self.org_id,
                    ClarificationLog.inquiry_id == inquiry.id,
                    ClarificationLog.field == fld,
                    ClarificationLog.status == "open")):
                log.status = "answered"
        return change

    def manual_unlock(self, inquiry: Inquiry, fld: str) -> ChangeRecord:
        slots = self.slots_data(inquiry.id)
        change = unlock(slots, fld)
        self._persist_changes(inquiry, slots, [change], actor="human")
        return change

    # ------------------------------------------------------------------ views
    def recompute(self, inquiry: Inquiry) -> dict:
        from .summary import build_summary
        breakdown = completeness_breakdown(self.active_values(inquiry.id))
        inquiry.completeness = breakdown["score"]
        inquiry.summary_json = json.dumps(
            build_summary(self.active_values(inquiry.id), breakdown), ensure_ascii=False)
        return breakdown

    def history(self, inquiry_id: int, limit: int = 200) -> list[RequirementHistory]:
        return list(self.db.scalars(
            select(RequirementHistory).where(
                RequirementHistory.org_id == self.org_id,
                RequirementHistory.inquiry_id == inquiry_id,
            ).order_by(RequirementHistory.id.desc()).limit(limit)))


def _normalize_manual(fld: str, raw: str) -> tuple[str, str, str]:
    """Normalize a human-entered raw string for a field (keeps raw as display)."""
    raw = (raw or "").strip()
    if fld == "product":
        info = norm.canonical_product(raw)
        if info:
            return info["label_en"], info["concept"], ""
        return raw, raw.lower().replace(" ", "_"), ""
    if fld == "color":
        c = norm.normalize_color(raw)
        return (c or raw), (c or raw.lower()), ""
    if fld == "material":
        m = norm.normalize_material(raw)
        return (m or raw), (m or raw.lower()), ""
    if fld == "quantity":
        q = norm.parse_quantity(raw) or ({"value": norm.parse_number(raw), "unit": "pcs"} if norm.parse_number(raw) else None)
        if q and q.get("value"):
            return f'{q["value"]:,} {q.get("unit", "pcs")}', str(int(q["value"])), q.get("unit", "pcs")
        return raw, raw, ""
    if fld == "target_price":
        p = norm.parse_target_price(raw)
        if not p and norm.parse_number(raw):
            p = {"value": norm.parse_number(raw), "currency": "USD", "per": "pcs"}
        if p:
            return f'{p["currency"]} {p["value"]:g} / {p["per"]}', f'{p["value"]}|{p["currency"]}|{p["per"]}', p["currency"]
        return raw, raw, ""
    if fld == "destination_country":
        c = norm.normalize_country(raw)
        if c:
            return c[0], c[1], ""
        return raw, raw, ""
    if fld == "destination_port":
        p = norm.normalize_port(raw)
        if p:
            return p[0], p[0], ""
        return raw, raw, ""
    if fld == "incoterm":
        i = norm.normalize_incoterm(raw)
        if i:
            return i, i, ""
        return raw.upper(), raw.upper(), ""
    if fld == "certification":
        certs = norm.normalize_certifications(raw)
        val = ", ".join(certs) if certs else raw
        return val, "|".join(certs) if certs else raw.lower(), ""
    if fld == "lead_time":
        lead = norm.parse_lead_time(raw) or ({"days": int(norm.parse_number(raw))} if norm.parse_number(raw) else None)
        if lead and lead.get("days") is not None:
            return f'{lead["days"]} days', str(lead["days"]), "days"
        return raw, raw, ""
    return raw, raw, ""


def slot_update_from_manual(fld: str, raw: str) -> SlotUpdate:
    value, normalized, unit = _normalize_manual(fld, raw)
    return SlotUpdate(field=fld, raw=raw, value=value, normalized=normalized, unit=unit, confidence=1.0)
