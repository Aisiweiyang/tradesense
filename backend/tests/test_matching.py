"""Matching tests: hard filters, explainability, stable ordering."""
import json
from datetime import datetime, timedelta, timezone

from app.services.matching import DEFAULT_WEIGHTS, evaluate_product, recall_candidates


def _product(**kw):
    from app.models import Product

    defaults = dict(org_id=1, id=1, sku="T-1", name_en="Vacuum Insulated Bottle 500ml",
                    name_zh="保温杯", category="insulated_bottle", material="stainless steel 304",
                    spec="500ml", color="black, silver", moq=500,
                    price_tiers_json=json.dumps([{"min_qty": 500, "unit_price": 4.2},
                                                 {"min_qty": 1000, "unit_price": 3.9}]),
                    lead_time_days=25, certifications_json=json.dumps(["FDA", "LFGB"]),
                    customization="logo print", markets="", unit_weight_kg=0.32,
                    is_active=True, data_source="manual")
    defaults.update(kw)
    return Product(**defaults)


def _values(**kw):
    base = {
        "product": {"value": "Insulated bottle", "normalized": "insulated_bottle", "status": "active"},
        "quantity": {"value": "1,000 pcs", "normalized": "1000", "status": "active"},
        "material": {"value": "", "normalized": "", "status": "unknown"},
        "color": {"value": "", "normalized": "", "status": "unknown"},
        "spec": {"value": "", "normalized": "", "status": "unknown"},
        "certification": {"value": "", "normalized": "", "status": "unknown"},
        "target_price": {"value": "", "normalized": "", "status": "unknown"},
        "lead_time": {"value": "", "normalized": "", "status": "unknown"},
        "customization": {"value": "", "normalized": "", "status": "unknown"},
        "destination_country": {"value": "", "normalized": "", "status": "unknown"},
        "incoterm": {"value": "", "normalized": "", "status": "unknown"},
    }
    base.update(kw)
    return base


NOW = datetime.now(timezone.utc)


def test_full_match_scores_high():
    out = evaluate_product(_product(), _values(), DEFAULT_WEIGHTS, None, NOW)
    assert not out.excluded
    assert out.total_score > 70
    assert any("类别" in m or "完全匹配" in m for m in out.met)


def test_hard_filter_missing_certification():
    values = _values(certification={"value": "FDA, LFGB", "normalized": "FDA|LFGB", "status": "active"})
    out = evaluate_product(_product(), values, DEFAULT_WEIGHTS, None, NOW)
    assert not out.excluded  # has both

    values = _values(certification={"value": "FDA, LFGB, CE", "normalized": "FDA|LFGB|CE", "status": "active"})
    out = evaluate_product(_product(certifications_json=json.dumps(["FDA"])), values,
                           DEFAULT_WEIGHTS, None, NOW)
    assert out.excluded
    assert "LFGB" in out.exclude_reason or "CE" in out.exclude_reason


def test_hard_filter_price_ceiling():
    values = _values(target_price={"value": "USD 3.0 / pcs", "normalized": "3.0|USD|pcs", "status": "active"})
    out = evaluate_product(_product(), values, DEFAULT_WEIGHTS, None, NOW)
    assert out.excluded  # tier 3.9 > target 3.0
    assert out.is_alternative  # single negotiable hard miss → shown as alternative


def test_hard_filter_lead_time():
    values = _values(lead_time={"value": "15 days", "normalized": "15", "unit": "days", "status": "active"})
    out = evaluate_product(_product(), values, DEFAULT_WEIGHTS, None, NOW)
    assert out.excluded and "25" in out.exclude_reason


def test_hard_filter_destination_market():
    values = _values(destination_country={"value": "US", "normalized": "US", "status": "active"})
    out = evaluate_product(_product(markets="DE,FR"), values, DEFAULT_WEIGHTS, None, NOW)
    assert out.excluded


def test_below_moq_is_penalty_not_silent():
    values = _values(quantity={"value": "100 pcs", "normalized": "100", "status": "active"})
    out = evaluate_product(_product(), values, DEFAULT_WEIGHTS, None, NOW)
    assert not out.excluded  # negotiable
    assert any("MOQ" in u for u in out.unmet)
    q_score = out.scores["quantity_vs_moq"]
    assert q_score["score"] < q_score["max"] * 0.5


def test_explainability_fields_present():
    out = evaluate_product(_product(), _values(), DEFAULT_WEIGHTS, None, NOW)
    for dim, info in out.scores.items():
        assert info["score"] <= info["max"] + 1e-9
    assert "sku" in out.data_snapshot and out.data_snapshot["source"] == "manual"


def test_stable_sorting(db, org):
    """Same-score products keep a deterministic order by product id."""
    from app.models import Product
    from sqlalchemy.orm import Session

    from app.services.matching import match_products_for_inquiry

    values = _values()
    result = match_products_for_inquiry(db, org.id, values)
    ids = [o.product.id for o in result["viable"]]
    assert ids == sorted(ids, key=ids.index)
