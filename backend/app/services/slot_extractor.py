"""Rule-based slot extraction from inquiry messages (EN + ZH).

Output is a list of slot updates; the requirement engine decides how each
update mutates the multi-round requirement state. Rule-based extraction is the
deterministic baseline — the optional AI layer can only *suggest* additional
extractions (flagged needs_confirmation), never silently overwrite.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import normalization as norm
from .fields import FIELD_DEFS

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def detect_language(text: str) -> str:
    if not text:
        return "en"
    cjk = len(_CJK_RE.findall(text))
    return "zh" if cjk > max(3, len(text) * 0.15) else "en"


@dataclass
class SlotUpdate:
    field: str
    raw: str
    value: str            # human-readable value for display
    normalized: str       # canonical normalized value
    unit: str = ""
    confidence: float = 0.9
    conflict: bool = False          # contradictory values inside one message
    unconstrained: bool = False     # buyer said "no preference"
    status_hint: str = "active"     # active | needs_confirmation (when uncertain)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field, "raw": self.raw, "value": self.value,
            "normalized": self.normalized, "unit": self.unit,
            "confidence": self.confidence, "conflict": self.conflict,
            "unconstrained": self.unconstrained, "status_hint": self.status_hint,
            "note": self.note,
        }


_PLACE_PREFIX = re.compile(
    r"(?:ship(?:ping)?\s+to|deliver(?:y)?\s+to|destination|dest\.?|discharge|to port|destination port|"
    r"目的港|目的港口|发货至|运至|目的地|目的国家|目的国)[:\s]*([^\n,.;。，；]{2,60})", re.IGNORECASE)


@dataclass
class ExtractionResult:
    language: str
    updates: list[SlotUpdate] = field(default_factory=list)
    product_concept: str | None = None

    def by_field(self) -> dict[str, list[SlotUpdate]]:
        out: dict[str, list[SlotUpdate]] = {}
        for u in self.updates:
            out.setdefault(u.field, []).append(u)
        return out


def extract_slots(text: str) -> ExtractionResult:
    """Extract structured requirement updates from one message."""
    result = ExtractionResult(language=detect_language(text))
    if not text or not text.strip():
        return result

    def add(field: str, raw: str, value: str, normalized: str, **kw):
        result.updates.append(SlotUpdate(field=field, raw=raw, value=value,
                                         normalized=normalized, **kw))

    # ---- product concept ---------------------------------------------------
    concept_info = norm.canonical_product(text)
    if concept_info:
        result.product_concept = concept_info["concept"]
        add("product", concept_info["raw"], concept_info["label_en"],
            concept_info["concept"], confidence=0.95)

    # ---- material ----------------------------------------------------------
    mat = norm.normalize_material(text)
    if mat:
        add("material", mat.replace("_", " "), mat, mat, confidence=0.9)

    # ---- color (with in-message conflict detection) -------------------------
    colors = norm.find_colors(text)
    if len(colors) == 1:
        add("color", colors[0], colors[0], colors[0], confidence=0.95)
    elif len(colors) > 1:
        add("color", "/".join(colors), " or ".join(colors), "|".join(colors),
            confidence=0.9, conflict=True, status_hint="conflicting",
            note="Multiple colors in one message need confirmation")

    # ---- quantity ----------------------------------------------------------
    qty = norm.parse_quantity(text)
    if qty:
        add("quantity", qty["raw"], f'{qty["value"]:,} {qty["unit"]}',
            str(qty["value"]), unit=qty["unit"], confidence=0.95)

    # ---- target price ------------------------------------------------------
    price = norm.parse_target_price(text)
    if price:
        add("target_price", price["raw"], f'{price["currency"]} {price["value"]:g} / {price["per"]}',
            f'{price["value"]}|{price["currency"]}|{price["per"]}',
            unit=price["currency"], confidence=0.9)

    # ---- destination -------------------------------------------------------
    for m in _PLACE_PREFIX.finditer(text):
        place = norm.resolve_place(m.group(1))
        if not place:
            continue
        if place["kind"] == "port":
            add("destination_port", place["raw"], place["value"], place["value"],
                confidence=0.95, note=f'Country inferred from port: {place["country"]}')
            add("destination_country", place["raw"], place["country"], place["iso2"],
                confidence=0.9, note="Inferred from destination port")
        else:
            add("destination_country", place["raw"], place["value"], place["iso2"], confidence=0.9)
        break
    else:
        place = norm.resolve_place(text)
        if place and place["kind"] == "port":
            add("destination_port", place["raw"], place["value"], place["value"],
                confidence=0.8, note="Port detected without explicit destination wording")
            add("destination_country", place["raw"], place["country"], place["iso2"], confidence=0.75)

    # ---- incoterm ----------------------------------------------------------
    incoterm = norm.normalize_incoterm(text)
    if incoterm:
        add("incoterm", incoterm, incoterm, incoterm, confidence=0.95)

    # ---- packaging ---------------------------------------------------------
    pkg = norm.normalize_packaging(text)
    if pkg:
        add("packaging", pkg, pkg, pkg, confidence=0.9)

    # ---- certifications ----------------------------------------------------
    certs = norm.normalize_certifications(text)
    if certs:
        add("certification", ", ".join(certs), ", ".join(certs), "|".join(certs), confidence=0.95)

    # ---- customization -----------------------------------------------------
    customs = norm.detect_customization(text)
    if customs:
        add("customization", "/".join(customs), "/".join(customs), "|".join(customs), confidence=0.9)

    # ---- lead time ---------------------------------------------------------
    lead = norm.parse_lead_time(text)
    if lead:
        add("lead_time", lead["raw"], f'{lead["days"]} days', str(lead["days"]),
            unit="days", confidence=0.85)

    # ---- sample requirement ------------------------------------------------
    if re.search(r"\b(sample|samples)\b|\bneed a sample|样品", text, re.IGNORECASE):
        val = "requested"
        add("sample", val, val, val, confidence=0.85)

    # ---- payment terms -----------------------------------------------------
    pm = re.search(r"\b(t/t|telegraphic transfer|l/c|letter of credit|paypal|western union|"
                   r"(\d{1,2})%\s*(deposit|prepaid).{0,30}?(\d{1,2})%\s*(balance|against))\b", text, re.IGNORECASE)
    if pm:
        add("payment_terms", pm.group(0), pm.group(0).upper(), pm.group(0).lower(), confidence=0.9)

    # ---- spec (capacity / size) --------------------------------------------
    spec = _extract_spec(text)
    if spec:
        add("spec", spec["raw"], spec["value"], spec["normalized"], unit=spec.get("unit", ""),
            confidence=0.85)

    # ---- shipping method ---------------------------------------------------
    sm = re.search(r"\b(by\s+)?(air|sea|express|courier)\s*(freight|shipping|shipment)?\b|空运|海运|快递", text, re.IGNORECASE)
    if sm:
        val = sm.group(2) or (sm.group(0) if not sm.group(0).isascii() else sm.group(0))
        add("shipping_method", sm.group(0).strip(), val.strip().lower(), val.strip().lower(), confidence=0.85)

    # ---- explicit "no preference" ------------------------------------------
    for fld in norm.detect_unconstrained(text):
        add(fld, "no preference", "无特殊要求 (buyer: no preference)", "__unconstrained__",
            unconstrained=True, confidence=0.95)

    # keep only fields we define
    result.updates = [u for u in result.updates if u.field in FIELD_DEFS]
    return result


_VOLUME_RE = re.compile(r"(\d{2,4}(?:[.,]\d+)?)\s*(ml|milliliter|liter|l\b|oz|ounce|cl)\b", re.IGNORECASE)
_DIMENSION_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:x|×|\*)\s*(\d+(?:[.,]\d+)?)\s*(?:x|×|\*)\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|inch|inches|in)\b", re.IGNORECASE)


def _extract_spec(text: str) -> dict | None:
    m = _VOLUME_RE.search(text)
    if m:
        v = float(m.group(1).replace(",", ""))
        unit_raw = m.group(2).lower()
        if unit_raw in ("l", "liter", "litre"):
            v, unit_raw = v * 1000, "ml"
        elif unit_raw == "cl":
            v, unit_raw = v * 10, "ml"
        elif unit_raw in ("oz", "ounce"):
            v, unit_raw = round(v * 29.5735), "ml"
        return {"raw": m.group(0), "value": f"{int(v)} ml", "normalized": f"{int(v)}ml", "unit": "ml"}
    m = _DIMENSION_RE.search(text)
    if m:
        raw = m.group(0)
        unit_raw = m.group(4).lower()
        unit = "mm" if unit_raw == "mm" else ("cm" if unit_raw == "cm" else "inch")
        return {"raw": raw, "value": raw, "normalized": re.sub(r"\s+", "", raw).lower(), "unit": unit}
    return None
