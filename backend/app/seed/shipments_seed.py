"""Demo shipments with sample PDFs and realistic verification issues.

Scenarios (mirrors the product spec examples):
  S1 Hamburg tools  — 金额不一致(高) + TO ORDER(高) + HS Code(中) + 缺原产地证倒计时(高)
  S2 LA electronics — 毛重超允差(中)
  S3 Rotterdam food — 品名表述差异(低) + 缺装箱单
  S4 clean shipment — 全部核验通过，无异常
  S5 fresh shipment — 空单证（空状态）
  S6 scanned docs   — 无文本层 → 待人工录入
"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Customer, Document, DocumentField, Shipment, ShipmentIssue
from ..services.doc_rules import refresh_issues
from .docgen import (make_bill_of_lading, make_customs_declaration, make_invoice,
                     make_letter_of_credit, make_packing_list, make_scan_like_pdf)


def _mk_shipment(db: Session, org_id: int, user_id: int, customer: Customer | None,
                 no_suffix: str, **kw) -> Shipment:
    s = Shipment(
        org_id=org_id, shipment_no=f"SH-20260912-{no_suffix}",
        customer_id=customer.id if customer else None,
        owner_user_id=user_id, **kw)
    db.add(s)
    db.flush()
    return s


def _attach(db: Session, org_id: int, user_id: int, shipment: Shipment,
            doc_type: str, filename: str, pdf_path, status_: str = "extracted",
            pages: int = 1, has_text: bool = True, fields: list[tuple] | None = None) -> Document:
    doc = Document(org_id=org_id, shipment_id=shipment.id, doc_type=doc_type,
                   version=1, file_path=str(pdf_path), original_filename=filename,
                   status=status_, pages=pages, has_text_layer=has_text,
                   uploaded_by_user_id=user_id)
    db.add(doc)
    db.flush()
    for (name, value, page, text, conf) in (fields or []):
        db.add(DocumentField(org_id=org_id, document_id=doc.id, field_name=name,
                             value=value, confidence=conf, evidence_page=page,
                             evidence_text=text, source="extracted"))
    db.flush()
    return doc


def seed_shipments(db: Session, org_id: int, user_id: int) -> None:
    from pathlib import Path

    docs_dir = Path("data") / "demo_docs"
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    soon_cutoff = now + timedelta(hours=6)          # <24h → 缺件为高风险
    far_cutoff = now + timedelta(days=10)

    customers = db.scalars(select(Customer).where(Customer.org_id == org_id)).all()
    by_name = {c.company_name: c for c in customers}
    c_tools = by_name.get("HausKonzept GmbH")
    c_us = by_name.get("KitchenDoor LLC")
    c_food = by_name.get("BudgetLine Wholesale") or (customers[0] if customers else None)

    # ---- S1 宁波→汉堡：金额 + TO ORDER + HS Code + 缺证倒计时 -----------------
    s1 = _mk_shipment(db, org_id, user_id, c_tools, "0842",
                      order_no="PO-2026-4417", transport_mode="sea",
                      port_of_loading="Ningbo", port_of_discharge="Hamburg",
                      incoterm="FOB", etd=now + timedelta(days=4),
                      cutoff_at=soon_cutoff, status="docs_making",
                      required_docs_json=json.dumps(
                          ["invoice", "packing_list", "bill_of_lading", "origin_certificate"]))
    _attach(db, org_id, user_id, s1, "invoice", "INV-0842.pdf",
            make_invoice(docs_dir / "s1_invoice.pdf", invoice_no="TS-INV-2609-0842",
                         total_amount="48,620.00", hs_code="8467.29",
                         description="Cordless Drill Set",
                         consignee="HausKonzept GmbH"),
            fields=[("invoice_no", "TS-INV-2609-0842", 1, "Invoice No.: TS-INV-2609-0842", 0.9),
                    ("total_amount", "48,620.00", 1, "Total Amount: USD 48,620.00", 0.9),
                    ("hs_code", "8467.29", 1, "HS Code: 8467.29", 0.9),
                    ("description", "Cordless Drill Set", 1, "Description of Goods: Cordless Drill Set", 0.85),
                    ("consignee", "HausKonzept GmbH", 1, "Consignee: HausKonzept GmbH", 0.9)])
    _attach(db, org_id, user_id, s1, "packing_list", "PL-0842.pdf",
            make_packing_list(docs_dir / "s1_pl.pdf", gross_weight="12,480.00"),
            fields=[("gross_weight", "12,480.00", 1, "Gross Weight: 12,480.00 KGS", 0.9),
                    ("container_no", "TCLU1234567", 1, "Container No.: TCLU1234567", 0.9)])
    _attach(db, org_id, user_id, s1, "bill_of_lading", "BL-0842.pdf",
            make_bill_of_lading(docs_dir / "s1_bl.pdf", consignee="TO ORDER",
                                gross_weight="12,480.00"),
            fields=[("consignee", "TO ORDER", 1, "Consignee: TO ORDER", 0.9),
                    ("gross_weight", "12,480.00", 1, "Gross Weight: 12,480.00 KGS", 0.9)])
    _attach(db, org_id, user_id, s1, "letter_of_credit", "LC-0842.pdf",
            make_letter_of_credit(docs_dir / "s1_lc.pdf", lc_amount="46,820.00",
                                  consignee="TO ORDER OF ABC BANK",
                                  description="Electric Hand Drill Set"),
            fields=[("lc_amount", "46,820.00", 1, "LC Amount: USD 46,820.00", 0.9),
                    ("consignee", "TO ORDER OF ABC BANK", 1, "Consignee: TO ORDER OF ABC BANK", 0.9),
                    ("description", "Electric Hand Drill Set", 1, "Description of Goods: Electric Hand Drill Set", 0.85)])
    _attach(db, org_id, user_id, s1, "customs_declaration", "CUS-0842.pdf",
            make_customs_declaration(docs_dir / "s1_cus.pdf", hs_code="8467.21"),
            fields=[("hs_code", "8467.21", 1, "HS Code: 8467.21", 0.9)])
    refresh_issues(db, org_id, s1, user_id)

    # ---- S2 深圳→洛杉矶：毛重不一致 ------------------------------------------
    s2 = _mk_shipment(db, org_id, user_id, c_us, "0317",
                      order_no="PO-2026-9921", transport_mode="sea",
                      port_of_loading="Yantian", port_of_discharge="Los Angeles",
                      incoterm="FOB", etd=now + timedelta(days=6),
                      cutoff_at=far_cutoff, status="docs_making")
    _attach(db, org_id, user_id, s2, "packing_list", "PL-0317.pdf",
            make_packing_list(docs_dir / "s2_pl.pdf", gross_weight="12,480.00"),
            fields=[("gross_weight", "12,480.00", 1, "Gross Weight: 12,480.00 KGS", 0.9)])
    _attach(db, org_id, user_id, s2, "bill_of_lading", "BL-0317.pdf",
            make_bill_of_lading(docs_dir / "s2_bl.pdf", consignee="KitchenDoor LLC",
                                gross_weight="12,840.00", port_discharge="Los Angeles"),
            fields=[("gross_weight", "12,840.00", 1, "Gross Weight: 12,840.00 KGS", 0.9),
                    ("consignee", "KitchenDoor LLC", 1, "Consignee: KitchenDoor LLC", 0.9)])
    refresh_issues(db, org_id, s2, user_id)

    # ---- S3 青岛→鹿特丹：品名差异 + 缺装箱单 ----------------------------------
    s3 = _mk_shipment(db, org_id, user_id, c_food, "0196",
                      order_no="PO-2026-3308", transport_mode="sea",
                      port_of_loading="Qingdao", port_of_discharge="Rotterdam",
                      incoterm="CIF", etd=now + timedelta(days=3),
                      cutoff_at=far_cutoff, status="docs_making")
    _attach(db, org_id, user_id, s3, "invoice", "INV-0196.pdf",
            make_invoice(docs_dir / "s3_invoice.pdf", invoice_no="TS-INV-2609-0196",
                         total_amount="18,900.00", hs_code="8467.29",
                         description="Cordless Drill", consignee="BudgetLine BV",
                         port_discharge="Rotterdam"),
            fields=[("description", "Cordless Drill", 1, "Description of Goods: Cordless Drill", 0.85),
                    ("total_amount", "18,900.00", 1, "Total Amount: USD 18,900.00", 0.9)])
    _attach(db, org_id, user_id, s3, "letter_of_credit", "LC-0196.pdf",
            make_letter_of_credit(docs_dir / "s3_lc.pdf", lc_amount="18,900.00",
                                  consignee="BudgetLine BV",
                                  description="Electric Hand Drill"),
            fields=[("description", "Electric Hand Drill", 1, "Description of Goods: Electric Hand Drill", 0.85),
                    ("consignee", "BudgetLine BV", 1, "Consignee: BudgetLine BV", 0.9)])
    refresh_issues(db, org_id, s3, user_id)

    # ---- S4 干净货件：全部核验通过 --------------------------------------------
    s4 = _mk_shipment(db, org_id, user_id, c_tools, "0501",
                      order_no="PO-2026-7710", transport_mode="air",
                      port_of_loading="Shanghai", port_of_discharge="Frankfurt",
                      incoterm="CIF", etd=now + timedelta(days=8),
                      cutoff_at=far_cutoff, status="ready_to_ship")
    _attach(db, org_id, user_id, s4, "invoice", "INV-0501.pdf",
            make_invoice(docs_dir / "s4_invoice.pdf", invoice_no="TS-INV-2609-0501",
                         total_amount="26,000.00", hs_code="8467.29",
                         description="Cordless Drill Set", consignee="HausKonzept GmbH",
                         port_discharge="Frankfurt"),
            fields=[("total_amount", "26,000.00", 1, "Total Amount: USD 26,000.00", 0.9)])
    _attach(db, org_id, user_id, s4, "packing_list", "PL-0501.pdf",
            make_packing_list(docs_dir / "s4_pl.pdf", gross_weight="6,500.00"),
            fields=[("gross_weight", "6,500.00", 1, "Gross Weight: 6,500.00 KGS", 0.9)])
    _attach(db, org_id, user_id, s4, "bill_of_lading", "BL-0501.pdf",
            make_bill_of_lading(docs_dir / "s4_bl.pdf", consignee="HausKonzept GmbH",
                                gross_weight="6,500.00", port_discharge="Frankfurt"),
            fields=[("consignee", "HausKonzept GmbH", 1, "Consignee: HausKonzept GmbH", 0.9),
                    ("gross_weight", "6,500.00", 1, "Gross Weight: 6,500.00 KGS", 0.9)])
    refresh_issues(db, org_id, s4, user_id)

    # ---- S5 空白新货件（空状态） ----------------------------------------------
    _mk_shipment(db, org_id, user_id, c_us, "0666",
                 order_no="PO-2026-0001", transport_mode="express",
                 port_of_loading="Shenzhen", port_of_discharge="New York",
                 incoterm="FOB", status="preparing")

    # ---- S6 扫描件（无文本层 → 待人工录入） ------------------------------------
    s6 = _mk_shipment(db, org_id, user_id, c_tools, "0777",
                      order_no="PO-2026-5555", transport_mode="rail",
                      port_of_loading="Xi'an", port_of_discharge="Duisburg",
                      incoterm="FCA", etd=now + timedelta(days=12),
                      cutoff_at=far_cutoff, status="docs_making")
    _attach(db, org_id, user_id, s6, "invoice", "scan-inv-0777.pdf",
            make_scan_like_pdf(docs_dir / "s6_scan.pdf"), status_="needs_manual",
            has_text=False)

    db.flush()
