"""Deterministic quotation calculator.

Price is ALWAYS computed by this program — never invented by an AI.
Every line shows its source (product tier / rule default / user input),
assumptions, missing items and risks. Internal cost vs suggested quote vs
customer price vs approved price are explicitly separated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta, timezone

from ..models import PriceRule, Product
from .matching import _price_tiers, tier_price

# Default cost/fee assumptions. Organizations can override via PriceRule rows.
DEFAULT_RULES = {
    "packaging_unit": 0.25,          # USD / unit
    "printing_lump": 60.0,           # USD one-time logo setup, amortized
    "printing_unit_cap": 0.15,       # USD / unit cap for amortized printing
    "mold_lump": 0.0,                # USD one-time mold (custom shape)
    "domestic_freight_lump": 280.0,  # USD factory -> port
    "export_customs_lump": 180.0,    # USD export declaration & docs
    "insurance_rate": 0.003,         # of 110% CIF value
    "duty_rate_default": 0.06,       # DDP estimate only
    "exchange_buffer": 0.02,         # FX buffer
    "freight_usd_per_kg": {          # sea LCL estimate by destination zone
        "default": 1.6, "EU": 1.25, "NA": 1.15, "ME": 1.05, "OCE": 1.35, "ASIA": 0.8, "SA": 1.5, "AF": 1.7,
    },
    "freight_min_lump": 260.0,
}

ISO_ZONE = {
    "DE": "EU", "FR": "EU", "NL": "EU", "IT": "EU", "ES": "EU", "PL": "EU", "SE": "EU",
    "NO": "EU", "DK": "EU", "FI": "EU", "CH": "EU", "AT": "EU", "BE": "EU", "IE": "EU",
    "PT": "EU", "GR": "EU", "CZ": "EU", "HU": "EU", "RO": "EU", "GB": "EU",
    "US": "NA", "CA": "NA", "MX": "NA",
    "AE": "ME", "SA": "ME", "QA": "ME", "KW": "ME", "OM": "ME", "BH": "ME", "IL": "ME", "TR": "ME",
    "AU": "OCE", "NZ": "OCE",
    "JP": "ASIA", "KR": "ASIA", "SG": "ASIA", "MY": "ASIA", "TH": "ASIA", "VN": "ASIA",
    "ID": "ASIA", "PH": "ASIA", "IN": "ASIA", "PK": "ASIA", "BD": "ASIA", "LK": "ASIA",
    "BR": "SA", "AR": "SA", "CL": "SA", "CO": "SA", "PE": "SA",
    "ZA": "AF", "NG": "AF", "KE": "AF", "EG": "AF", "MA": "AF",
}

INCOTERM_APPLIES = {
    "EXW": [], "FOB": ["domestic_freight", "export_customs"],
    "CIF": ["domestic_freight", "export_customs", "freight", "insurance"],
    "CFR": ["domestic_freight", "export_customs", "freight"],
    "DAP": ["domestic_freight", "export_customs", "freight", "insurance"],
    "DDP": ["domestic_freight", "export_customs", "freight", "insurance", "duty"],
}


@dataclass
class QuoteInput:
    product: Product
    quantity: int
    incoterm: str = "FOB"
    currency: str = "USD"
    margin_rate: float = 0.15
    destination_iso: str = ""
    unit_weight_kg: float | None = None
    packaging_unit: float | None = None       # override
    printing: bool = False
    mold_lump: float = 0.0
    target_price: float | None = None
    exchange_rate: float = 1.0                # cost currency -> quote currency
    valid_days: int = 30
    base_cost_override: float | None = None   # 供应商比价成本（覆盖阶梯价）
    base_cost_source: str = ""                # 覆盖来源说明（写入 breakdown）


@dataclass
class QuoteOutput:
    unit_cost: float
    unit_price: float
    total_amount: float
    breakdown: list = dc_field(default_factory=list)   # [{item, amount, per_unit, source}]
    assumptions: list = dc_field(default_factory=list)
    missing: list = dc_field(default_factory=list)
    risks: list = dc_field(default_factory=list)
    exchange: dict = dc_field(default_factory=dict)
    valid_until: datetime | None = None


def load_rules(db, org_id: int) -> dict:
    rules = dict(DEFAULT_RULES)
    for r in db.scalars(__import__("sqlalchemy").select(PriceRule).where(
            PriceRule.org_id == org_id, PriceRule.is_active == True)).all():  # noqa: E712
        try:
            cfg = json.loads(r.config_json or "{}")
        except json.JSONDecodeError:
            continue
        if r.rule_type == "margin_default":
            rules.setdefault("margin_default", 0.15)
            rules["margin_default"] = float(cfg.get("rate", rules["margin_default"]))
        else:
            rules.update(cfg)
    return rules


def compute_quote(inp: QuoteInput, rules: dict | None = None) -> QuoteOutput:
    rules = {**DEFAULT_RULES, **(rules or {})}
    p = inp.product
    out = QuoteOutput(unit_cost=0, unit_price=0, total_amount=0)
    qty = max(int(inp.quantity or 0), 1)
    out.valid_until = datetime.now(timezone.utc) + timedelta(days=inp.valid_days)

    # ---- 1. product base cost: supplier quote override > ladder tier -------
    if inp.base_cost_override is not None:
        base_cost = float(inp.base_cost_override)
        breakdown = [{"item": "产品成本 (供应商报价)", "per_unit": round(base_cost, 4),
                      "amount": round(base_cost * qty, 2),
                      "source": inp.base_cost_source or "供应商比价选定报价"}]
    else:
        base_cost = tier_price(p, qty)
        if base_cost is None:
            out.missing.append("产品缺少阶梯价格，无法计算基础成本")
            base_cost = 0.0
        breakdown = [{"item": "产品成本 (阶梯价)", "per_unit": round(base_cost, 4),
                      "amount": round(base_cost * qty, 2),
                      "source": f"SKU {p.sku} 阶梯价格表 qty≥{qty}"}]

    # ---- 2. packaging -------------------------------------------------------
    packaging = inp.packaging_unit if inp.packaging_unit is not None else float(rules["packaging_unit"])
    breakdown.append({"item": "包装", "per_unit": round(packaging, 4),
                      "amount": round(packaging * qty, 2),
                      "source": "价格规则默认值" if inp.packaging_unit is None else "用户输入"})

    # ---- 3. printing (logo) --------------------------------------------------
    printing_unit = 0.0
    if inp.printing:
        lump = float(rules["printing_lump"])
        printing_unit = min(lump / qty, float(rules["printing_unit_cap"]))
        breakdown.append({"item": "Logo 印刷（摊销）", "per_unit": round(printing_unit, 4),
                          "amount": round(min(lump, printing_unit * qty), 2),
                          "source": f"版费 {rules['printing_lump']} USD 按 {qty} 数量摊销，封顶 {rules['printing_unit_cap']} USD/件"})

    # ---- 4. mold -------------------------------------------------------------
    mold_unit = 0.0
    if inp.mold_lump:
        mold_unit = inp.mold_lump / qty
        breakdown.append({"item": "模具（摊销）", "per_unit": round(mold_unit, 4),
                          "amount": round(inp.mold_lump, 2), "source": "用户输入模具费"})

    exw_cost = base_cost + packaging + printing_unit + mold_unit

    # ---- 5. incoterm build-up -------------------------------------------------
    applies = INCOTERM_APPLIES.get(inp.incoterm, ["domestic_freight", "export_customs"])
    if inp.incoterm not in INCOTERM_APPLIES:
        out.assumptions.append(f"贸易术语 {inp.incoterm} 按 FOB+运保口径估算，仅作参考")

    per_unit_add = 0.0
    if "domestic_freight" in applies:
        v = float(rules["domestic_freight_lump"]) / qty
        per_unit_add += v
        breakdown.append({"item": "国内物流（工厂→港口）", "per_unit": round(v, 4),
                          "amount": round(float(rules["domestic_freight_lump"]), 2), "source": "价格规则默认值"})
    if "export_customs" in applies:
        v = float(rules["export_customs_lump"]) / qty
        per_unit_add += v
        breakdown.append({"item": "出口报关及单证", "per_unit": round(v, 4),
                          "amount": round(float(rules["export_customs_lump"]), 2), "source": "价格规则默认值"})

    fob_cost = exw_cost + per_unit_add

    freight_unit = 0.0
    insurance_unit = 0.0
    duty_unit = 0.0
    weight = inp.unit_weight_kg if inp.unit_weight_kg is not None else p.unit_weight_kg
    if weight is None:
        weight = 0.35
        out.assumptions.append("产品未录入单件重量，按 0.35 kg/件估算运费；请核对后重算")
        out.missing.append("产品单件重量未录入（当前按 0.35kg 估算）")
    if "freight" in applies:
        if not inp.destination_iso:
            out.missing.append("缺少目的国，海运费按默认区域费率估算")
            zone = "default"
        else:
            zone = ISO_ZONE.get(inp.destination_iso.upper(), "default")
        rate = float(rules["freight_usd_per_kg"].get(zone, rules["freight_usd_per_kg"]["default"]))
        lump = weight * qty * rate
        lump = max(lump, float(rules["freight_min_lump"]))
        freight_unit = lump / qty
        breakdown.append({"item": f"国际海运（{zone} 区，LCL 估算）", "per_unit": round(freight_unit, 4),
                          "amount": round(lump, 2), "source": f"费率 {rate} USD/kg × {weight} kg × {qty}"})
    if "insurance" in applies:
        value = (fob_cost + freight_unit) * qty
        insurance_lump = value * 1.1 * float(rules["insurance_rate"])
        insurance_unit = insurance_lump / qty
        breakdown.append({"item": "海运保险", "per_unit": round(insurance_unit, 4),
                          "amount": round(insurance_lump, 2),
                          "source": f"110% 发票金额 × {rules['insurance_rate']}"})
    if "duty" in applies:
        duty_unit = (fob_cost + freight_unit + insurance_unit) * float(rules["duty_rate_default"])
        breakdown.append({"item": "目的国关税（估算）", "per_unit": round(duty_unit, 4),
                          "amount": round(duty_unit * qty, 2),
                          "source": f"默认税率 {rules['duty_rate_default']}（DDP 需人工核实目的国税率）"})
        out.risks.append("DDP 报价含目的国关税估算，正式报出前必须由人工核实税率与清关代理")

    cost_unit = fob_cost + freight_unit + insurance_unit + duty_unit

    # ---- 6. FX buffer + margin -----------------------------------------------
    # buffer applies only on a real currency conversion, never for USD→USD
    fx = inp.exchange_rate * (1 + float(rules["exchange_buffer"])) if abs(inp.exchange_rate - 1.0) > 1e-9 else 1.0
    cost_unit_quote_ccy = cost_unit * fx
    if abs(fx - 1.0) > 1e-9:
        out.exchange = {"rate": inp.exchange_rate, "buffer": rules["exchange_buffer"], "applied": round(fx, 6),
                        "note": "报价币种与成本币种不同，已应用汇率与缓冲"}
        breakdown.append({"item": "汇率换算（含缓冲）", "per_unit": round(cost_unit_quote_ccy - cost_unit, 4),
                          "amount": round((cost_unit_quote_ccy - cost_unit) * qty, 2),
                          "source": f"汇率 {inp.exchange_rate} + 缓冲 {rules['exchange_buffer']}"})

    unit_price = cost_unit_quote_ccy / (1 - inp.margin_rate) if inp.margin_rate < 1 else cost_unit_quote_ccy
    margin_line = unit_price - cost_unit_quote_ccy
    breakdown.append({"item": f"利润（{inp.margin_rate:.0%}）", "per_unit": round(margin_line, 4),
                      "amount": round(margin_line * qty, 2), "source": "默认利润率，可在报价中调整"})

    total_cost = cost_unit_quote_ccy * qty
    total_quote = unit_price * qty

    # ---- 7. risks --------------------------------------------------------------
    if inp.target_price is not None and unit_price > inp.target_price:
        out.risks.append(
            f"建议报价 {unit_price:.2f} 高于客户目标价 {inp.target_price:.2f}；成本底线 {cost_unit_quote_ccy:.2f}，"
            "不建议低于成本报出，请先调整配置或与客户沟通")
    if inp.target_price is not None and inp.target_price < cost_unit_quote_ccy:
        out.risks.append("客户目标价低于内部成本，属于亏损订单风险")
    if qty < (p.moq or 0):
        out.risks.append(f"数量 {qty} 低于产品 MOQ {p.moq}，供应商可能不接受或需加价")
    if inp.incoterm == "DDP":
        out.risks.append("DDP 需要目的国清关能力，新手建议优先使用 CIF 或 FOB")
    out.risks.append("运费与税率为程序内置估算值，正式报价前请以货代实时运价核对")

    out.unit_cost = round(cost_unit_quote_ccy, 4)
    out.unit_price = round(unit_price, 4)
    out.total_amount = round(total_quote, 2)
    out.breakdown = breakdown
    out.assumptions = out.assumptions + [
        f"报价有效期 {inp.valid_days} 天（至 {out.valid_until.date()}）",
        f"贸易术语 {inp.incoterm}，报价币种 {inp.currency}",
    ]
    return out
