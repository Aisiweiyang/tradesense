"""Document extractor tests using reportlab-generated sample PDFs."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.seed import docgen
from app.services.doc_extractor import as_number, extract_pdf_fields, normalize_value


def _docs_dir() -> Path:
    """Windows sandboxes may block the system temp dir; use the gitignored
    backend/data/test_docs instead."""
    d = Path("data") / "test_docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _new(name: str) -> Path:
    return _docs_dir() / f"{uuid.uuid4().hex[:8]}-{name}"


@pytest.fixture(scope="module")
def invoice_pdf() -> Path:
    return docgen.make_invoice(_new("inv.pdf"), invoice_no="TS-INV-2609-0842",
                               total_amount="48,620.00", hs_code="8467.29",
                               description="Cordless Drill Set", consignee="HausKonzept GmbH")


def _fields(path):
    out = extract_pdf_fields(str(path))
    assert out.has_text_layer
    return {f.field_name: f for f in out.fields}


def test_invoice_core_fields(invoice_pdf):
    f = _fields(invoice_pdf)
    assert f["invoice_no"].value == "TS-INV-2609-0842"
    assert f["total_amount"].value == "48,620.00"
    assert f["hs_code"].value == "8467.29"
    assert "Cordless Drill Set" in f["description"].value


def test_evidence_page_and_text(invoice_pdf):
    f = _fields(invoice_pdf)
    assert f["invoice_no"].evidence_page == 1
    assert "Invoice No.:" in f["invoice_no"].evidence_text


def test_lc_fields():
    out = _fields(docgen.make_letter_of_credit(
        _new("lc.pdf"), lc_amount="46,820.00", consignee="TO ORDER OF ABC BANK",
        description="Electric Hand Drill", latest_shipment_date="2026-10-15"))
    assert out["lc_amount"].value == "46,820.00"
    assert out["consignee"].value == "TO ORDER OF ABC BANK"
    assert out["latest_shipment_date"].value == "2026-10-15"


def test_bl_fields():
    out = _fields(docgen.make_bill_of_lading(_new("bl.pdf"), consignee="TO ORDER",
                                      gross_weight="12,480.00"))
    assert out["consignee"].value == "TO ORDER"
    assert out["gross_weight"].value == "12,480.00"
    assert out["container_no"].value == "TCLU1234567"


def test_scan_like_pdf_has_no_text_layer():
    out = extract_pdf_fields(str(docgen.make_scan_like_pdf(_new("scan.pdf"))))
    assert out.has_text_layer is False
    assert out.fields == []


def test_weight_variants():
    out = _fields(docgen.make_packing_list(_new("pl.pdf"), gross_weight="12,480.00",
                                    net_weight="9,800.00"))
    assert out["gross_weight"].value == "12,480.00"
    assert out["net_weight"].value == "9,800.00"
    assert out["packages"].value == "500"


def test_customs_hs_code():
    out = _fields(docgen.make_customs_declaration(_new("cus.pdf"), hs_code="8467.21"))
    assert out["hs_code"].value == "8467.21"


def test_normalize_value():
    assert normalize_value("TO ORDER") == "TOORDER"
    assert normalize_value(" to  order ") == "TOORDER"
    assert normalize_value(None) == ""


def test_as_number():
    assert as_number("USD 48,620.00") == 48620.0
    assert as_number("12,840.00 KGS") == 12840.0
    assert as_number("") is None


def test_unknown_pdf():
    p = docgen._lines(_new("empty.pdf"), "HELLO WORLD", ["nothing to see here"])
    out = extract_pdf_fields(str(p))
    assert out.has_text_layer
    assert "currency" not in {f.field_name for f in out.fields}
