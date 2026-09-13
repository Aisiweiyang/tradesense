"""Multi-round requirement state engine tests (pure logic, spec scenario)."""
from app.services.requirement_engine import (SlotData, apply_updates, manual_override,
                                             summarize_changes)
from app.services.slot_extractor import SlotUpdate, extract_slots


def _slots():
    return {}


def _u(field, normalized, value=None, confidence=0.95, **kw):
    return SlotUpdate(field=field, raw=value or normalized, value=value or normalized,
                      normalized=normalized, confidence=confidence, **kw)


def test_spec_scenario_multi_round():
    """Spec section 10: blue→black, 500→1000 with history retained."""
    slots = _slots()
    m1 = extract_slots("I need 500 blue stainless-steel bottles.")
    changes1 = apply_updates(slots, m1.updates, message_id=1)
    assert slots["color"].normalized_value == "blue"
    assert slots["quantity"].normalized_value == "500"

    m2 = extract_slots("Actually, make them black, increase the quantity to 1,000, and ship to Hamburg.")
    changes2 = apply_updates(slots, m2.updates, message_id=2)
    assert slots["color"].normalized_value == "black"
    assert slots["color"].status == "active"
    assert slots["quantity"].normalized_value == "1000"
    assert slots["destination_port"].normalized_value == "Hamburg"

    # history kept: old values recorded
    assert {"value": "blue", "message_id": 1} in [{"value": h["value"], "message_id": h["message_id"]}
                                                  for h in slots["color"].history_values]
    assert {"value": "500 pcs", "message_id": 1} in [{"value": h["value"], "message_id": h["message_id"]}
                                                     for h in slots["quantity"].history_values]
    types = {c.field: c.change_type for c in changes2}
    assert types["color"] == "update"
    assert types["quantity"] == "update"


def test_conflict_then_resolution():
    slots = _slots()
    conflict = extract_slots("quote 5000 lunch boxes, green and navy blue")
    apply_updates(slots, conflict.updates, message_id=1)
    assert slots["color"].status == "conflicting"
    resolve = extract_slots("please make them all green")
    apply_updates(slots, resolve.updates, message_id=2)
    assert slots["color"].status in ("active", "needs_confirmation")
    assert slots["color"].normalized_value == "green"


def test_unconstrained_status():
    slots = _slots()
    r = extract_slots("1,000 travel mugs, any color is fine")
    apply_updates(slots, r.updates, message_id=1)
    assert slots["color"].status == "unconstrained"


def test_locked_field_never_overwritten():
    slots = _slots()
    first = extract_slots("I need 500 blue bottles")
    apply_updates(slots, first.updates, message_id=1)
    manual_override(slots, "color", "blue (pantone 293C)", "blue (pantone 293C)", "blue", lock=True)
    assert slots["color"].locked is True

    later = extract_slots("change color to black please")
    changes = apply_updates(slots, later.updates, message_id=2)
    assert slots["color"].normalized_value == "blue"  # unchanged
    assert slots["color"].status == "active"
    assert any(c.change_type == "locked_ignored" and c.field == "color" for c in changes)


def test_manual_set_confirms_and_low_confidence_needs_confirmation():
    slots = _slots()
    change = manual_override(slots, "quantity", "800", "800", "800")
    assert slots["quantity"].confirmed is True
    assert slots["quantity"].confidence == 1.0
    assert change.change_type == "manual_set"

    low = _u("material", "glass", value="glass", confidence=0.6)
    apply_updates(slots, [low], message_id=3)
    assert slots["material"].status == "needs_confirmation"


def test_reaffirm_keeps_value():
    slots = _slots()
    r1 = extract_slots("500 blue bottles")
    apply_updates(slots, r1.updates, message_id=1)
    r2 = extract_slots("as said, 500 blue bottles")
    apply_updates(slots, r2.updates, message_id=2)
    assert slots["color"].normalized_value == "blue"
    assert slots["quantity"].normalized_value == "500"
    assert slots["color"].source_message_id == 2  # refreshed source


def test_summarize_changes_shape():
    slots = _slots()
    r1 = extract_slots("500 blue bottles")
    apply_updates(slots, r1.updates, message_id=1)
    r2 = extract_slots("make it 1000")
    changes = apply_updates(slots, r2.updates, message_id=2)
    summary = summarize_changes(changes)
    assert summary["quantity"]["old"] == "500 pcs"
    assert summary["quantity"]["new"] == "1,000 pcs"
