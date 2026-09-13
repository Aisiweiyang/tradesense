"""Quote routes: deterministic calculation, versioning, human approval gate."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope, order_by, paginate
from ...rbac import require_role
from ...models import Inquiry, Product, Quote, QuoteItem
from ...schemas import QuoteCreateIn, QuoteOut, QuotePriceIn
from ...services.audit import audit
from ...services.quotation import QuoteInput, compute_quote, load_rules
from ...services.requirement_service import RequirementService

router = APIRouter(prefix="/quotes", tags=["quotes"])


def _dump(q: Quote) -> dict:
    return QuoteOut.model_validate(q).model_dump(mode="json")


def _next_version(db: Session, org_id: int, inquiry_id: int, product_id: int) -> int:
    last = db.scalar(select(func.max(Quote.version)).where(
        Quote.org_id == org_id, Quote.inquiry_id == inquiry_id, Quote.product_id == product_id))
    return (last or 0) + 1


@router.post("", status_code=201)
def create_quote(body: QuoteCreateIn, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    inq = db.scalar(select(Inquiry).where(Inquiry.org_id == scope.org_id, Inquiry.id == body.inquiry_id))
    if inq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "询盘不存在"})
    p = db.scalar(select(Product).where(Product.org_id == scope.org_id, Product.id == body.product_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "产品不存在"})

    rules = load_rules(db, scope.org_id)
    base_override = None
    base_source = ""
    if body.supplier_product_id:
        from ...models import SupplierProduct, Supplier
        sp = db.scalar(select(SupplierProduct).where(
            SupplierProduct.org_id == scope.org_id, SupplierProduct.id == body.supplier_product_id))
        if sp is None or sp.product_id != p.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                detail={"code": "not_found", "message": "供应商报价不存在或不属于该产品"})
        sup = db.get(Supplier, sp.supplier_id)
        base_override = float(sp.cost_price)
        base_source = f"供应商比价：{sup.name if sup else ''} 报价 {sp.cost_price:g} {sp.currency}"
        if sp.currency != body.currency:
            out_hint = (f"供应商报价币种 {sp.currency} 与报价币种 {body.currency} 不同，"
                        "请在汇率中填入折算汇率")
            # surfaced via assumptions below
    out = compute_quote(QuoteInput(
        product=p, quantity=body.quantity, incoterm=body.incoterm, currency=body.currency,
        margin_rate=body.margin_rate, destination_iso=body.destination_iso,
        printing=body.printing, mold_lump=body.mold_lump,
        packaging_unit=body.packaging_unit, exchange_rate=body.exchange_rate,
        valid_days=body.valid_days,
        base_cost_override=base_override, base_cost_source=base_source), rules)
    if body.supplier_product_id and sp.currency != body.currency:
        out.assumptions = list(out.assumptions) + [
            f"供应商报价币种 {sp.currency} 与报价币种 {body.currency} 不同；"
            "如需折算请填写汇率（当前按 1:1 计）"]

    # target-price risk from requirement state
    values = RequirementService(db, scope.org_id).active_values(inq.id)
    target_raw = (values.get("target_price") or {}).get("normalized") or ""
    if target_raw:
        try:
            out.risks = list(out.risks)
            target = float(target_raw.split("|")[0])
            if target < out.unit_price:
                out.risks.append(f"客户目标价 {target} 低于本次建议报价 {out.unit_price}")
        except (ValueError, IndexError):
            pass

    version = _next_version(db, scope.org_id, inq.id, p.id)
    # supersede previous versions of the same inquiry+product
    for old in db.scalars(select(Quote).where(
            Quote.org_id == scope.org_id, Quote.inquiry_id == inq.id,
            Quote.product_id == p.id, Quote.status.notin_(("superseded", "rejected")))).all():
        old.status = "superseded"

    quote = Quote(
        org_id=scope.org_id, inquiry_id=inq.id, product_id=p.id, version=version,
        status="draft", incoterm=body.incoterm, currency=body.currency,
        quantity=body.quantity, unit_cost=out.unit_cost, unit_price=out.unit_price,
        customer_price=body.customer_price or out.unit_price,
        total_amount=round((body.customer_price or out.unit_price) * body.quantity, 2),
        margin_rate=body.margin_rate,
        breakdown_json=json.dumps(out.breakdown, ensure_ascii=False),
        assumptions_json=json.dumps(out.assumptions, ensure_ascii=False),
        missing_json=json.dumps(out.missing, ensure_ascii=False),
        risks_json=json.dumps(out.risks, ensure_ascii=False),
        exchange_rate_json=json.dumps(out.exchange, ensure_ascii=False),
        valid_until=out.valid_until, created_by_user_id=scope.user.id,
        notes=f"SKU {p.sku} {p.name_en}",
    )
    db.add(quote)
    db.flush()
    db.add(QuoteItem(org_id=scope.org_id, quote_id=quote.id, product_id=p.id,
                     description=f"{p.sku} {p.name_en}", qty=body.quantity,
                     unit_cost=out.unit_cost, unit_price=out.unit_price,
                     subtotal=out.total_amount, margin_rate=body.margin_rate))
    audit(db, scope.org_id, scope.user.id, "quote.create", "quote", quote.id,
          {"version": version, "unit_price": out.unit_price})
    db.commit()
    return _dump(quote)


@router.get("")
def list_quotes(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                pg: dict = Depends(paginate), inquiry_id: int = Query(0),
                status_filter: str = Query("", alias="status")):
    stmt = select(Quote).where(Quote.org_id == scope.org_id)
    if inquiry_id:
        stmt = stmt.where(Quote.inquiry_id == inquiry_id)
    if status_filter:
        stmt = stmt.where(Quote.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(Quote, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    return {"items": [_dump(q) for q in rows], "total": total,
            "page": pg["page"], "page_size": pg["page_size"]}


@router.get("/by-inquiry/{inquiry_id}")
def quotes_by_inquiry(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                      db: Session = Depends(get_db)):
    rows = db.scalars(select(Quote).where(
        Quote.org_id == scope.org_id, Quote.inquiry_id == inquiry_id
    ).order_by(Quote.product_id, Quote.version.desc())).all()
    product_ids = {q.product_id for q in rows if q.product_id}
    products = {p.id: p for p in db.scalars(select(Product).where(
        Product.org_id == scope.org_id, Product.id.in_(product_ids or [0]))).all()}
    return {"items": [{**_dump(q), "product_name": products[q.product_id].name_en if q.product_id in products else ""}
                      for q in rows]}


@router.get("/{quote_id}")
def get_quote(quote_id: int, scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    q = db.scalar(select(Quote).where(Quote.org_id == scope.org_id, Quote.id == quote_id))
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "报价不存在"})
    data = _dump(q)
    data["breakdown"] = json.loads(q.breakdown_json or "[]")
    data["assumptions"] = json.loads(q.assumptions_json or "[]")
    data["missing"] = json.loads(q.missing_json or "[]")
    data["risks"] = json.loads(q.risks_json or "[]")
    data["exchange"] = json.loads(q.exchange_rate_json or "{}")
    if q.inquiry_id:
        blocking = _quote_blocking(db, scope, q.inquiry_id)
        data["requirement_blockers"] = blocking
    return data


def _quote_blocking(db: Session, scope: OrgScope, inquiry_id: int) -> list[str]:
    """Hard-stop warnings that must be visible before a formal quote."""
    from ...services.fields import BASE_REQUIRED_FOR_QUOTE, FIELD_DEFS  # local to avoid cycles
    values = RequirementService(db, scope.org_id).active_values(inquiry_id)
    blockers = []
    for f in BASE_REQUIRED_FOR_QUOTE:
        if not values.get(f, {}).get("normalized"):
            blockers.append(f"询盘缺少必填字段：{FIELD_DEFS[f].label_zh}（不允许生成无警告的正式报价）")
    for f, v in values.items():
        if v.get("status") == "conflicting":
            label = FIELD_DEFS[f].label_zh if f in FIELD_DEFS else f
            blockers.append(f"字段存在矛盾需确认：{label}")
    return blockers


@router.post("/{quote_id}/price")
def set_customer_price(quote_id: int, body: QuotePriceIn,
                       scope: OrgScope = Depends(require_role("quote.set_price")),
                       db: Session = Depends(get_db)):
    """Salesperson sets the actually-quoted customer price (cost stays internal)."""
    q = db.scalar(select(Quote).where(Quote.org_id == scope.org_id, Quote.id == quote_id))
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "报价不存在"})
    if q.customer_price and body.customer_price < q.unit_cost:
        q.status = "pending_approval"
        note = "客户价低于内部成本，已自动转入待审批状态"
    else:
        note = ""
    q.customer_price = body.customer_price
    q.total_amount = round(body.customer_price * q.quantity, 2)
    if body.notes:
        q.notes = (q.notes + " | " if q.notes else "") + body.notes
    audit(db, scope.org_id, scope.user.id, "quote.set_price", "quote", q.id,
          {"customer_price": body.customer_price})
    db.commit()
    return {**_dump(q), "note": note}


@router.post("/{quote_id}/approve")
def approve_quote(quote_id: int, scope: OrgScope = Depends(require_role("quote.approve")),
                  db: Session = Depends(get_db)):
    """Human approval is the ONLY way a quote becomes formal."""
    q = db.scalar(select(Quote).where(Quote.org_id == scope.org_id, Quote.id == quote_id))
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "报价不存在"})
    blockers = _quote_blocking(db, scope, q.inquiry_id)
    if blockers:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "blocked_by_requirements",
                                    "message": "存在未解决的报价阻塞项，不能批准为正式报价",
                                    "details": blockers})
    if q.customer_price and q.customer_price < q.unit_cost:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "below_cost",
                                    "message": "客户价低于内部成本，需先调整价格"})
    q.status = "approved"
    q.is_formal = True
    q.approved_by_user_id = scope.user.id
    q.approved_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    inq = db.get(Inquiry, q.inquiry_id)
    if inq:
        inq.status = "quoted"
    audit(db, scope.org_id, scope.user.id, "quote.approve", "quote", q.id,
          {"version": q.version, "customer_price": q.customer_price})
    db.commit()
    return _dump(q)


@router.post("/{quote_id}/reject")
def reject_quote(quote_id: int, scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    q = db.scalar(select(Quote).where(Quote.org_id == scope.org_id, Quote.id == quote_id))
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "报价不存在"})
    q.status = "rejected"
    q.is_formal = False
    audit(db, scope.org_id, scope.user.id, "quote.reject", "quote", q.id, {})
    db.commit()
    return _dump(q)
