"""Regressions for locked requirements and quote approval provenance."""
from copy import deepcopy

import pytest

from app.models import Quote
from app.services.requirement_engine import apply_updates, manual_override
from app.services.slot_extractor import SlotUpdate
from tests.conftest import auth_headers


@pytest.mark.parametrize("updates", [
    [SlotUpdate(field="color", raw="any color", value="any", normalized="", unconstrained=True)],
    [SlotUpdate(field="color", raw="black or red", value="black", normalized="black", conflict=True)],
    [SlotUpdate(field="color", raw=c, value=c, normalized=c) for c in ("black", "red")],
])
def test_locked_slot_preserves_entire_state_for_every_update_branch(updates):
    slots = {}
    manual_override(slots, "color", "Pantone blue", "blue", "blue", lock=True)
    slots["color"].source_message_id = 1
    before = deepcopy(slots["color"])
    changes = apply_updates(slots, updates, message_id=2)
    assert slots["color"] == before
    assert changes and all(c.change_type == "locked_ignored" for c in changes)
    assert all(u.raw in " ".join(c.note for c in changes) for u in updates)


@pytest.fixture()
def quote_case(client):
    h = auth_headers(client)
    p = client.post("/api/products", headers=h, json={
        "sku": "APPROVAL-REGRESSION", "name_en": "Insulated Bottle", "moq": 500,
        "price_tiers": [{"min_qty": 500, "unit_price": 3.0}],
        "unit_weight_kg": 0.35,
    }).json()
    inq = client.post("/api/inquiries", headers=h, json={
        "text": "Need 1000 insulated bottles, FOB, to Hamburg",
    }).json()
    body = {"inquiry_id": inq["id"], "product_id": p["id"], "quantity": 1000}
    r = client.post("/api/quotes", headers=h, json=body)
    assert r.status_code == 201, r.text
    return h, body, r.json()


@pytest.mark.parametrize("below_cost", [False, True])
def test_changing_approved_price_revokes_approval(client, quote_case, below_cost):
    h, _, quote = quote_case
    qid = quote["id"]
    assert client.post(f"/api/quotes/{qid}/approve", headers=h).status_code == 200
    price = quote["unit_cost"] * (0.5 if below_cost else 2)
    r = client.post(f"/api/quotes/{qid}/price", headers=h, json={"customer_price": price})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_approval"
    assert r.json()["is_formal"] is False
    row = client.app.state.test_db.get(Quote, qid)
    assert row.approved_by_user_id is None and row.approved_at is None
    assert row.total_amount == round(price * row.quantity, 2)
    if not below_cost:
        assert client.post(f"/api/quotes/{qid}/approve", headers=h).json()["is_formal"] is True


def test_unchanged_price_preserves_approval(client, quote_case):
    h, _, quote = quote_case
    url = f"/api/quotes/{quote['id']}"
    assert client.post(url + "/approve", headers=h).status_code == 200
    row = client.app.state.test_db.get(Quote, quote["id"])
    approved_at = row.approved_at
    r = client.post(url + "/price", headers=h, json={"customer_price": quote["customer_price"]})
    assert r.json()["is_formal"] is True
    assert row.approved_at == approved_at


@pytest.mark.parametrize("terminal", ["rejected", "superseded"])
def test_closed_quote_cannot_be_edited_or_reapproved(client, quote_case, terminal):
    h, body, quote = quote_case
    url = f"/api/quotes/{quote['id']}"
    if terminal == "rejected":
        client.post(url + "/reject", headers=h)
    else:
        client.post("/api/quotes", headers=h, json=body)
    for action, payload in (("price", {"customer_price": 10}), ("approve", None)):
        r = client.post(url + "/" + action, headers=h, json=payload)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "quote_closed"


def test_superseded_quote_is_no_longer_formal(client, quote_case):
    h, body, quote = quote_case
    url = f"/api/quotes/{quote['id']}"
    client.post(url + "/approve", headers=h)
    client.post("/api/quotes", headers=h, json=body)
    old = client.get(url, headers=h).json()
    assert old["status"] == "superseded" and old["is_formal"] is False
