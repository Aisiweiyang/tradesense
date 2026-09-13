"""Multi-round requirement state engine (pure logic, no DB).

Handles: new conditions, modified conditions, negations, "no preference",
multi-field updates, partial overrides, contradictions, fuzzy input,
human corrections and locked fields.

A locked field can never be silently overwritten by extraction output;
the attempted override is recorded in history and flagged for review.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

from .slot_extractor import SlotUpdate


@dataclass
class SlotData:
    """In-memory representation of one requirement slot."""
    field: str
    raw_value: str = ""
    value: str = ""
    normalized_value: str = ""
    unit: str = ""
    status: str = "unknown"
    confidence: float = 0.0
    source_message_id: Optional[int] = None
    history_values: list = dc_field(default_factory=list)  # [{value, message_id, at}]
    locked: bool = False
    confirmed: bool = False


@dataclass
class ChangeRecord:
    field: str
    change_type: str
    old_value: str = ""
    new_value: str = ""
    old_status: str = ""
    new_status: str = ""
    note: str = ""


def _append_history(slot: SlotData, value: str, message_id: Optional[int]) -> None:
    if value:
        slot.history_values.append({"value": value, "message_id": message_id, "status": slot.status})
        slot.history_values = slot.history_values[-20:]  # cap


def apply_updates(
    slots: dict[str, SlotData],
    updates: list[SlotUpdate],
    message_id: Optional[int],
    actor: str = "system",
    low_confidence_threshold: float = 0.75,
) -> list[ChangeRecord]:
    """Apply one message's extraction result to the state. Returns change records.

    `slots` maps field -> SlotData and is mutated in place.
    """
    changes: list[ChangeRecord] = []
    by_field: dict[str, list[SlotUpdate]] = {}
    for u in updates:
        by_field.setdefault(u.field, []).append(u)

    for fld, ups in by_field.items():
        slot = slots.get(fld)
        if slot is None:
            slot = slots[fld] = SlotData(field=fld)
        if fld == "notes":
            continue

        # ---- contradiction inside a single message -------------------------
        distinct = {u.normalized for u in ups if not u.unconstrained}
        if len(distinct) > 1 or any(u.conflict for u in ups):
            merged_raw = " / ".join(u.raw for u in ups)
            old_status, old_value = slot.status, slot.value
            slot.raw_value = merged_raw
            slot.value = " or ".join(u.value for u in ups)
            slot.normalized_value = "|".join(sorted(distinct))
            slot.status = "conflicting"
            slot.confidence = max(u.confidence for u in ups)
            slot.source_message_id = message_id
            slot.confirmed = False
            _append_history(slot, slot.value, message_id)
            changes.append(ChangeRecord(
                fld, "conflict", old_value, slot.value, old_status, "conflicting",
                note="Contradictory values in the same message; human confirmation required",
            ))
            continue

        u = ups[0]

        # ---- buyer explicitly said "no preference" --------------------------
        if u.unconstrained:
            old_status, old_value = slot.status, slot.value
            slot.raw_value = u.raw
            slot.value = u.value
            slot.normalized_value = "__unconstrained__"
            slot.status = "unconstrained"
            slot.confidence = u.confidence
            slot.source_message_id = message_id
            _append_history(slot, u.value, message_id)
            changes.append(ChangeRecord(
                fld, "unconstrained", old_value, u.value, old_status, "unconstrained",
                note="Buyer stated no preference",
            ))
            continue

        # ---- locked fields are never silently overwritten -------------------
        if slot.locked:
            changes.append(ChangeRecord(
                fld, "locked_ignored", slot.value, u.value, slot.status, slot.status,
                note=f'Locked field kept; incoming "{u.raw}" ignored and flagged for review',
            ))
            continue

        # ---- same value: reaffirm -------------------------------------------
        if slot.normalized_value == u.normalized and slot.status in ("active", "needs_confirmation"):
            slot.confidence = max(slot.confidence, u.confidence)
            slot.source_message_id = message_id
            slot.raw_value = u.raw
            if slot.status == "needs_confirmation" and u.confidence >= low_confidence_threshold:
                slot.status = "active"
            changes.append(ChangeRecord(
                fld, "reaffirmed", u.value, u.value, slot.status, slot.status,
                note="Same value re-confirmed by a newer message",
            ))
            continue

        # ---- conflict resolution: a later explicit value wins ---------------
        resolving_conflict = slot.status == "conflicting"

        old_value, old_status = slot.value, slot.status
        if old_value and old_status in ("active", "conflicting", "needs_confirmation"):
            _append_history(slot, old_value, slot.source_message_id)
        slot.raw_value = u.raw
        slot.value = u.value
        slot.normalized_value = u.normalized
        slot.unit = u.unit or slot.unit
        slot.confidence = u.confidence
        slot.source_message_id = message_id
        slot.confirmed = False
        if u.confidence < low_confidence_threshold and not resolving_conflict:
            slot.status = "needs_confirmation"
        else:
            slot.status = "active"
        if resolving_conflict:
            slot.status = "needs_confirmation" if u.confidence < low_confidence_threshold else "active"
        change_type = "set" if old_status == "unknown" else ("conflict_resolved" if resolving_conflict else "update")
        changes.append(ChangeRecord(
            fld, change_type, old_value, u.value, old_status, slot.status,
            note=f'Source message #{message_id}' if message_id else "",
        ))
    return changes


def manual_override(
    slots: dict[str, SlotData],
    fld: str,
    raw: str,
    value: str,
    normalized: str,
    unit: str = "",
    lock: bool = False,
    actor: str = "human",
) -> ChangeRecord:
    """Human sets/corrects a field (always trusted, marks confirmed; lock pins it)."""
    slot = slots.get(fld)
    if slot is None:
        slot = slots[fld] = SlotData(field=fld)
    old_value, old_status = slot.value, slot.status
    if old_value:
        _append_history(slot, old_value, slot.source_message_id)
    slot.raw_value = raw
    slot.value = value
    slot.normalized_value = normalized
    slot.unit = unit or slot.unit
    slot.confidence = 1.0
    slot.confirmed = True
    slot.status = "active"
    if lock:
        slot.locked = True
    return ChangeRecord(fld, "manual_set", old_value, value, old_status, "active",
                        note="Manually set/confirmed by salesperson" + (" and locked" if lock else ""))


def unlock(slots: dict[str, SlotData], fld: str) -> ChangeRecord:
    slot = slots[fld]
    slot.locked = False
    return ChangeRecord(fld, "unlock", slot.value, slot.value, slot.status, slot.status,
                        note="Field unlocked by human")


def summarize_changes(changes: list[ChangeRecord]) -> dict:
    """Compact view for UI: current vs previous per changed field."""
    return {
        c.field: {"old": c.old_value, "new": c.new_value, "type": c.change_type, "note": c.note}
        for c in changes
        if c.change_type in ("update", "conflict", "conflict_resolved", "unconstrained", "manual_set")
    }
