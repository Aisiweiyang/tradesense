"""Document text/field extraction with evidence (page number + original line).

Digital PDFs (text layer) are parsed with pdfplumber. Scanned/image PDFs have
no text layer → the document is marked needs_manual (no OCR in this phase).
Every extracted field records WHERE it came from: 1-based page number and the
original text line, so the UI can show evidence and rules can cite it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber

# field_name -> list of regex patterns (first match across pages wins)
FIELD_PATTERNS: dict[str, list[str]] = {
    "invoice_no": [r"Invoice\s*No\.?\s*[:：]?\s*([A-Z0-9][A-Z0-9/-]*)"],
    "po_no": [r"P\.?O\.?\s*No\.?\s*[:：]?\s*([A-Z0-9][A-Z0-9/-]*)"],
    "bl_no": [r"B/?L\s*No\.?\s*[:：]?\s*([A-Z0-9][A-Z0-9/-]*)"],
    "shipper": [r"Shipper\s*[:：]\s*(.+)"],
    "consignee": [r"Consignee\s*[:：]\s*(.+)"],
    "notify_party": [r"Notify\s*Party\s*[:：]\s*(.+)"],
    "hs_code": [r"HS\s*Code\s*[:：]?\s*(\d{4}(?:\.\d{2})?)"],
    "quantity": [r"Quantity\s*[:：]?\s*([\d,]+)"],
    "packages": [r"Packages\s*[:：]?\s*([\d,]+)"],
    "net_weight": [r"Net\s*Weight\s*[:：]?\s*([\d,.]+)\s*(?:KGS?|kg)"],
    "gross_weight": [r"Gross\s*Weight\s*[:：]?\s*([\d,.]+)\s*(?:KGS?|kg)"],
    "cbm": [r"CBM\s*[:：]?\s*([\d,.]+)"],
    "unit_price": [r"Unit\s*Price\s*[:：]?\s*(?:USD|EUR|CNY)?\s*([\d,.]+)"],
    "total_amount": [r"Total\s*Amount\s*[:：]?\s*(?:USD|EUR|CNY)?\s*([\d,.]+)"],
    "lc_amount": [r"(?:LC|L/C)\s*Amount\s*[:：]?\s*(?:USD|EUR|CNY)?\s*([\d,.]+)"],
    "currency": [r"\b(USD|EUR|CNY|GBP)\b"],
    "incoterm": [r"\b(EXW|FOB|CIF|DDP|CFR|DAP)\b"],
    "port_of_loading": [r"Port\s*of\s*Loading\s*[:：]\s*(.+)"],
    "port_of_discharge": [r"Port\s*of\s*Discharge\s*[:：]\s*(.+)"],
    "vessel": [r"Vessel\s*[:：]\s*(.+)"],
    "voyage": [r"Voyage\s*[:：]\s*([A-Z0-9/-]+)"],
    "container_no": [r"Container\s*No\.?\s*[:：]?\s*([A-Z]{4}\d{7})"],
    "seal_no": [r"Seal\s*No\.?\s*[:：]?\s*([A-Z0-9]+)"],
    "etd": [r"ETD\s*[:：]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"],
    "eta": [r"ETA\s*[:：]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"],
    "latest_shipment_date": [r"Latest\s*Shipment\s*Date\s*[:：]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"],
}

# multi-line description: capture up to 3 lines after the label
_DESC_RE = re.compile(r"Description\s*of\s*Goods\s*[:：]?\s*\n?(.+(?:\n.+){0,2})", re.IGNORECASE)


@dataclass
class ExtractedField:
    field_name: str
    value: str
    confidence: float
    evidence_page: int | None
    evidence_text: str


@dataclass
class ExtractionOutcome:
    has_text_layer: bool
    pages: int
    fields: list[ExtractedField]
    text_head: str = ""  # 前 800 字符原文，供单证类型内容识别


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().strip("，,；;")


def extract_pdf_fields(file_path: str) -> ExtractionOutcome:
    """Extract known fields from a (text-layer) PDF. Never raises for content —
    parse problems on a page degrade that page to empty text."""
    fields: list[ExtractedField] = []
    pages_text: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — damaged page must not kill extraction
                text = ""
            pages_text.append(text)

    has_text_layer = any(t.strip() for t in pages_text)
    if not has_text_layer:
        return ExtractionOutcome(has_text_layer=False, pages=page_count, fields=[])

    full = "\n".join(pages_text)
    for field_name, patterns in FIELD_PATTERNS.items():
        found = None
        for pattern in patterns:
            for idx, text in enumerate(pages_text, start=1):
                m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if m:
                    line = _clean(m.group(0))
                    found = ExtractedField(field_name, _clean(m.group(1)), 0.9, idx, line)
                    break
            if found:
                break
        if found is None and field_name == "currency":
            continue  # currency often implicit; not an error
        if found:
            fields.append(found)

    # multi-line goods description (search per page for correct evidence page)
    for idx, text in enumerate(pages_text, start=1):
        m = _DESC_RE.search(text)
        if m:
            fields.append(ExtractedField(
                "description", _clean(m.group(1)), 0.85, idx, _clean(m.group(0).splitlines()[0])))
            break

    text_head = " ".join(" ".join(pages_text).split())[:800]
    return ExtractionOutcome(has_text_layer=True, pages=page_count, fields=fields,
                             text_head=text_head)


def normalize_value(value: str) -> str:
    """Normalization for cross-document comparison (rules engine)."""
    v = (value or "").upper().strip()
    v = re.sub(r"[\s,]+", "", v)
    v = v.replace("。", "")
    return v


def as_number(value: str) -> float | None:
    m = re.search(r"[\d][\d,]*(?:\.\d+)?", value or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None
