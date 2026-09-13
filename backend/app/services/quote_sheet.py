"""Merged quotation sheet (QuoteSheet) builder + bilingual PDF export.

Deterministic aggregation of approved-quote candidates into one sheet.
Security invariants (enforced here and tested):
  - internal cost (unit_cost) NEVER appears in the PDF or any export payload
  - a sheet that is not approved carries a diagonal "NOT FORMAL / 非正式报价"
    watermark on every page
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Inquiry, Quote, QuoteSheet

RATE = __import__("decimal").Decimal


def _money(v) -> str:
    return f"{float(v):,.2f}"


def build_sheet_lines(db: Session, org_id: int, quote_ids: list[int]) -> list[dict]:
    quotes = db.scalars(select(Quote).where(
        Quote.org_id == org_id, Quote.id.in_(quote_ids or [0]))).all()
    by_id = {q.id: q for q in quotes}
    lines = []
    for qid in quote_ids:  # preserve caller order
        q = by_id.get(qid)
        if q is None:
            continue
        p = None
        if q.product_id:
            from ..models import Product
            p = db.get(Product, q.product_id)
        qty = q.quantity or 0
        price = q.customer_price or q.unit_price
        lines.append({
            "quote_id": q.id, "product_id": q.product_id,
            "sku": p.sku if p else "", "name_en": p.name_en if p else "",
            "name_zh": p.name_zh if p else "",
            "spec": p.spec if p else "",
            "qty": qty, "unit_price": round(float(price), 4),
            "subtotal": round(float(price) * qty, 2),
        })
    return lines


def _target_price(inquiry: Inquiry) -> float | None:
    try:
        raw = (json.loads(inquiry.summary_json or "{}").get("target_price") or "")
    except json.JSONDecodeError:
        return None
    # summary target_price like "USD 4.5 / pcs" — pull the number
    for token in raw.replace(",", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


def create_sheet(db: Session, org_id: int, inquiry_id: int, quote_ids: list[int],
                 user_id: int | None, notes: str = "") -> QuoteSheet:
    inquiry = db.get(Inquiry, inquiry_id)
    lines = build_sheet_lines(db, org_id, quote_ids)
    if not lines:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "no_lines", "message": "没有有效的报价行，请先为询盘创建报价"})

    version = (db.scalar(select(__import__("sqlalchemy").func.max(QuoteSheet.version)).where(
        QuoteSheet.org_id == org_id, QuoteSheet.inquiry_id == inquiry_id)) or 0) + 1
    seq = (db.scalar(select(__import__("sqlalchemy").func.count(QuoteSheet.id)).where(
        QuoteSheet.org_id == org_id)) or 0) + 1
    subtotal = round(sum(l["subtotal"] for l in lines), 2)
    first_quote = db.get(Quote, lines[0]["quote_id"])
    target = _target_price(inquiry) if inquiry else None
    target_json = {}
    if target:
        total_qty = sum(l["qty"] for l in lines) or 1
        avg_price = subtotal / total_qty
        target_json = {
            "target_unit": target, "avg_unit": round(avg_price, 4),
            "gap_pct": round((avg_price - target) / target * 100, 2),
            "note": ("建议报价高于客户目标价" if avg_price > target
                     else "平均单价满足客户目标价"),
        }
    # supersede previous versions
    for old in db.scalars(select(QuoteSheet).where(
            QuoteSheet.org_id == org_id, QuoteSheet.inquiry_id == inquiry_id,
            QuoteSheet.status.notin_(("superseded", "rejected")))).all():
        old.status = "superseded"

    sheet = QuoteSheet(
        org_id=org_id, inquiry_id=inquiry_id,
        sheet_no=f"QS-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{seq:04d}",
        version=version, status="draft",
        currency=first_quote.currency if first_quote else "USD",
        incoterm=first_quote.incoterm if first_quote else "FOB",
        lines_json=json.dumps(lines, ensure_ascii=False),
        subtotal=subtotal,
        margin_rate=(first_quote.margin_rate if first_quote else 0),
        target_price_json=json.dumps(target_json, ensure_ascii=False),
        notes=notes, created_by_user_id=user_id,
    )
    db.add(sheet)
    db.flush()
    return sheet


def render_sheet_pdf(db: Session, org_id: int, sheet: QuoteSheet) -> bytes:
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    # machine-readable formal/informal marker (visual diagonal watermark below)
    c.setSubject("NOT FORMAL - unapproved draft" if not sheet.is_formal
                 else "approved quotation")
    width, height = A4
    lines = json.loads(sheet.lines_json or "[]")
    inquiry = db.get(Inquiry, sheet.inquiry_id) if db is not None else None
    customer_name = ""
    if inquiry and inquiry.customer_id:
        from ..models import Customer
        cust = db.get(Customer, inquiry.customer_id)
        customer_name = cust.company_name if cust else ""

    def header_footer(page_no: int):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(60, height - 60, "QUOTATION")
        c.setFont("STSong-Light", 14)
        c.drawString(200, height - 60, "报 价 单")
        c.setFont("STSong-Light", 10)
        c.drawString(60, height - 80, f"No. {sheet.sheet_no}  v{sheet.version}")
        c.drawRightString(width - 60, height - 80,
                          f"Date: {datetime.now(timezone.utc).date()}")
        c.drawString(60, height - 100, f"Customer: {customer_name}")
        c.drawRightString(width - 60, height - 100,
                          f"Trade term: {sheet.incoterm}   Currency: {sheet.currency}")
        c.line(60, height - 110, width - 60, height - 110)
        c.setFont("STSong-Light", 8)
        c.drawString(60, 40, "Prices are program-calculated from tier pricing and fee "
                             "rules; valid until noted above.")
        c.drawRightString(width - 60, 40, f"Page {page_no}")
        if not sheet.is_formal:
            c.saveState()
            c.setFillAlpha(0.12)
            c.translate(width / 2, height / 2)
            c.rotate(35)
            c.setFont("Helvetica-Bold", 42)
            c.drawCentredString(0, 30, "NOT FORMAL")
            c.setFont("STSong-Light", 36)
            c.drawCentredString(0, -30, "非正式报价")
            c.restoreState()

    # ---- page 1: lines table ---------------------------------------------
    header_footer(1)
    y = height - 150
    c.setFont("STSong-Light", 10)
    headers = ["#", "SKU", "Description", "Qty", "Unit Price", "Amount"]
    xs = [60, 90, 200, 400, 460, 540]
    for x, h in zip(xs, headers):
        c.drawString(x, y, h)
    c.line(60, y - 4, width - 60, y - 4)
    y -= 20
    for idx, l in enumerate(lines, start=1):
        desc = l["name_en"] or l["name_zh"]
        c.setFont("Helvetica", 9)
        c.drawString(xs[0], y, str(idx))
        c.drawString(xs[1], y, l["sku"][:14])
        c.drawString(xs[2], y, desc[:34])
        c.drawRightString(xs[3] + 30, y, str(l["qty"]))
        c.drawRightString(xs[4] + 40, y, _money(l["unit_price"]))
        c.drawRightString(xs[5] + 20, y, _money(l["subtotal"]))
        y -= 18
        if y < 90:
            c.showPage()
            header_footer(2)
            y = height - 150
    c.line(60, y - 2, width - 60, y - 2)
    y -= 20
    c.setFont("STSong-Light", 12)
    c.drawRightString(xs[5] + 20, y, f"Total: {sheet.currency} {_money(sheet.subtotal)}")
    y -= 18
    try:
        target = json.loads(sheet.target_price_json or "{}")
        if target.get("note"):
            c.setFont("STSong-Light", 9)
            c.drawString(60, y, f"Note: {target['note']}")
            y -= 14
    except json.JSONDecodeError:
        pass
    c.setFont("STSong-Light", 9)
    c.drawString(60, y - 6, "Payment: T/T (30% deposit, 70% against B/L copy)")
    c.save()
    return buf.getvalue()
