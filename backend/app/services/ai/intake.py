"""AI Intake: LLM proposes requirement fields, the state machine adjudicates.

The AI never writes to the DB directly. propose_slots() returns SlotUpdate
candidates (or None on any failure) and requirement_service.apply_ai_proposals
feeds them through the same engine path as message parsing — locked fields,
conflicts and low-confidence handling behave exactly like manual/message input.
"""
from __future__ import annotations

from ..fields import FIELD_DEFS
from ..requirement_engine import SlotUpdate
from . import get_ai

MAX_PROPOSALS = 12
MIN_CONFIDENCE_ACTIVE = 0.75

INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "raw": {"type": "string"},
                    "value": {"type": "string"},
                    "normalized": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                    "unconstrained": {"type": "boolean"},
                },
                "required": ["field", "value"],
            },
        },
    },
    "required": ["fields"],
}

FIELD_HINTS = "; ".join(f"{name}({d.label_zh})" for name, d in FIELD_DEFS.items())


def _valid_evidence(evidence: str, text: str) -> bool:
    return (not evidence) or evidence.strip() in text


def propose_slots(text: str) -> list[SlotUpdate] | None:
    """LLM proposes SlotUpdates. None = AI unavailable/failed → caller falls
    back to rule extraction only. Whitelist + evidence-substring enforced."""
    ai = get_ai()
    if not ai.available():
        return None
    try:
        out = ai.chat_json(
            system="You extract purchasing-requirement fields from trade inquiries "
                   "(email text, attachments, messy multi-language input). "
                   f"Allowed fields: {FIELD_HINTS}. "
                   "For each field give: raw (as written), value (human display), "
                   "normalized (canonical: quantity as plain digits, prices as plain numbers), "
                   "confidence (0-1), evidence (short verbatim quote from the input). "
                   "Only extract what the text actually states; do not guess.",
            user=text[:8000], schema_hint=INTAKE_SCHEMA, max_tokens=1500)
    except Exception:  # noqa: BLE001 — any provider failure falls back to rules
        return None

    updates: list[SlotUpdate] = []
    for item in (out.get("fields") or [])[:MAX_PROPOSALS]:
        fld = str(item.get("field", "")).strip()
        if fld not in FIELD_DEFS:
            continue
        value = str(item.get("value", "")).strip()
        if not value or len(value) > 300:
            continue
        evidence = str(item.get("evidence", "")).strip()
        if not _valid_evidence(evidence, text):
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.6))))
        except (TypeError, ValueError):
            confidence = 0.6
        raw = str(item.get("raw", "")).strip() or value
        normalized = str(item.get("normalized", "")).strip() or value
        updates.append(SlotUpdate(
            field=fld, raw=raw[:300], value=value[:300], normalized=normalized[:300],
            confidence=round(confidence, 2),
            unconstrained=bool(item.get("unconstrained")),
            status_hint="needs_confirmation" if confidence < MIN_CONFIDENCE_ACTIVE else "active",
            note=f"AI 提议；依据：{evidence[:120]}",
        ))
    return updates
