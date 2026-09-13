"""Generate sample trade documents (text-layer PDFs) for demo/tests.

The layout is deliberately simple and label-driven so the extractor regexes
can find fields — this mirrors real digital PDFs exported from ERP systems.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def _lines(path: Path, title: str, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, 800, title)
    c.setFont("Helvetica", 11)
    y = 760
    for line in lines:
        c.drawString(60, y, line)
        y -= 22
    c.save()
    return path


def make_invoice(path: Path, *, invoice_no: str, total_amount: str, hs_code: str,
                 description: str, consignee: str, incoterm: str = "FOB",
                 port_loading: str = "Ningbo", port_discharge: str = "Hamburg") -> Path:
    return _lines(path, "COMMERCIAL INVOICE", [
        f"Invoice No.: {invoice_no}",
        "Shipper: Ningbo Haichen Tools Co., Ltd",
        f"Consignee: {consignee}",
        f"Description of Goods: {description}",
        f"HS Code: {hs_code}",
        "Quantity: 2,000",
        "Unit Price: USD 24.31",
        f"Total Amount: USD {total_amount}",
        f"Incoterms: {incoterm} {port_loading}",
        f"Port of Loading: {port_loading}",
        f"Port of Discharge: {port_discharge}",
    ])


def make_packing_list(path: Path, *, gross_weight: str, net_weight: str = "9,800.00",
                      packages: str = "500", container_no: str = "TCLU1234567") -> Path:
    return _lines(path, "PACKING LIST", [
        "Invoice No.: REF-PACK",
        f"Packages: {packages}",
        f"Net Weight: {net_weight} KGS",
        f"Gross Weight: {gross_weight} KGS",
        f"Container No.: {container_no}",
        "Seal No.: SL998877",
    ])


def make_bill_of_lading(path: Path, *, consignee: str, gross_weight: str,
                        vessel: str = "MSC ANNA", voyage: str = "V.126W",
                        port_discharge: str = "Hamburg") -> Path:
    return _lines(path, "BILL OF LADING", [
        "B/L No.: MSCU-778812",
        "Shipper: Ningbo Haichen Tools Co., Ltd",
        f"Consignee: {consignee}",
        f"Vessel: {vessel}",
        f"Voyage: {voyage}",
        f"Port of Discharge: {port_discharge}",
        f"Gross Weight: {gross_weight} KGS",
        "Container No.: TCLU1234567",
    ])


def make_letter_of_credit(path: Path, *, lc_amount: str, consignee: str,
                          description: str,
                          latest_shipment_date: str = "2026-10-15") -> Path:
    return _lines(path, "LETTER OF CREDIT", [
        "LC No.: LC-DE-889900",
        f"LC Amount: USD {lc_amount}",
        f"Consignee: {consignee}",
        f"Description of Goods: {description}",
        f"Latest Shipment Date: {latest_shipment_date}",
    ])


def make_customs_declaration(path: Path, *, hs_code: str) -> Path:
    return _lines(path, "CUSTOMS DECLARATION DRAFT", [
        "Invoice No.: REF-CUS",
        f"HS Code: {hs_code}",
        "Quantity: 2,000",
        "Gross Weight: 12,480.00 KGS",
    ])


def make_scan_like_pdf(path: Path) -> Path:
    """A PDF WITHOUT a text layer (drawn graphics only) → simulates a scan."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.rect(60, 400, 470, 300)
    c.line(60, 500, 530, 500)
    c.line(60, 600, 530, 600)
    c.save()
    return path
