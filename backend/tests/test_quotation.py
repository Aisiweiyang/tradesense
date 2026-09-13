"""Quotation calculator tests: deterministic build-up, sources, risks."""
import json

from app.services.quotation import DEFAULT_RULES, QuoteInput, compute_quote


def _product(**kw):
    from app.models import Product

    defaults = dict(org_id=1, id=1, sku="T-1", name_en="Vacuum Insulated Bottle",
                    name_zh="保温杯", category="insulated_bottle", material="stainless steel 304",
                    spec="500ml", moq=500,
                    price_tiers_json=json.dumps([{"min_qty": 500, "unit_price": 3.0},
                                                 {"min_qty": 1000, "unit_price": 2.8}]),
                    lead_time_days=25, unit_weight_kg=0.35, is_active=True)
    defaults.update(kw)
    return Product(**defaults)


def test_fob_buildup_deterministic():
    rules = dict(DEFAULT_RULES)
    out = compute_quote(QuoteInput(product=_product(), quantity=1000, incoterm="FOB",
                                   margin_rate=0.15), rules)
    # EXW = 2.8 + 0.25 = 3.05; FOB adds (280+180)/1000 = 0.46 → 3.51
    assert abs(out.unit_cost - 3.51) < 0.01
    assert abs(out.unit_price - 3.51 / 0.85) < 0.01
    items = [b["item"] for b in out.breakdown]
    assert "产品成本 (阶梯价)" in items and "国内物流（工厂→港口）" in items
    # every line has a source
    assert all(b.get("source") for b in out.breakdown)


def test_incoterm_ladder_exw_fob_cif():
    rules = dict(DEFAULT_RULES)
    exw = compute_quote(QuoteInput(product=_product(), quantity=1000, incoterm="EXW",
                                   margin_rate=0.15), rules)
    fob = compute_quote(QuoteInput(product=_product(), quantity=1000, incoterm="FOB",
                                   margin_rate=0.15), rules)
    cif = compute_quote(QuoteInput(product=_product(), quantity=1000, incoterm="CIF",
                                   margin_rate=0.15, destination_iso="DE"), rules)
    assert exw.unit_cost < fob.unit_cost < cif.unit_cost
    assert any("海运" in b["item"] for b in cif.breakdown)
    assert any("保险" in b["item"] for b in cif.breakdown)


def test_ladder_tier_selection_by_quantity():
    rules = dict(DEFAULT_RULES)
    small = compute_quote(QuoteInput(product=_product(), quantity=500, incoterm="EXW",
                                     margin_rate=0.15), rules)
    big = compute_quote(QuoteInput(product=_product(), quantity=5000, incoterm="EXW",
                                   margin_rate=0.15), rules)
    assert small.unit_cost > big.unit_cost  # quantity discount reflected


def test_target_price_below_cost_flags_loss_risk():
    rules = dict(DEFAULT_RULES)
    out = compute_quote(QuoteInput(product=_product(), quantity=1000, incoterm="FOB",
                                   margin_rate=0.15, target_price=2.0), rules)
    assert any("低于成本" in r or "低于内部成本" in r for r in out.risks)


def test_printing_amortized_with_cap():
    rules = dict(DEFAULT_RULES)
    out = compute_quote(QuoteInput(product=_product(), quantity=100, incoterm="EXW",
                                   margin_rate=0.15, printing=True), rules)
    printing_line = next(b for b in out.breakdown if "印刷" in b["item"])
    assert abs(printing_line["per_unit"] - 0.15) < 1e-9  # capped at 0.15


def test_ddp_includes_duty_with_warning():
    rules = dict(DEFAULT_RULES)
    out = compute_quote(QuoteInput(product=_product(), quantity=1000, incoterm="DDP",
                                   margin_rate=0.15, destination_iso="SA"), rules)
    assert any("关税" in b["item"] for b in out.breakdown)
    assert any("DDP" in r for r in out.risks)


def test_missing_weight_reported():
    rules = dict(DEFAULT_RULES)
    out = compute_quote(QuoteInput(product=_product(unit_weight_kg=None), quantity=1000,
                                   incoterm="CIF", margin_rate=0.15, destination_iso="DE"), rules)
    assert any("重量" in m for m in out.missing)
    assert any("0.35" in a for a in out.assumptions)
