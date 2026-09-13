"""Product CRUD, bulk enable/disable, CSV export."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope, order_by, paginate
from ...rbac import require_role
from ...models import Product, Supplier
from ...schemas import BulkIds, ProductIn, ProductOut, ProductUpdate
from ...services.audit import audit

router = APIRouter(prefix="/products", tags=["products"])


def _dump(p: Product) -> dict:
    return ProductOut.model_validate(p).model_dump(mode="json")


@router.get("")
def list_products(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                  pg: dict = Depends(paginate), q: str = Query("", max_length=200),
                  category: str = Query("", max_length=80),
                  active: str = Query("", pattern="^(true|false|)$")):
    stmt = select(Product).where(Product.org_id == scope.org_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Product.sku.ilike(like), Product.name_zh.ilike(like),
                              Product.name_en.ilike(like), Product.keywords.ilike(like),
                              Product.material.ilike(like)))
    if category:
        stmt = stmt.where(Product.category == category)
    if active == "true":
        stmt = stmt.where(Product.is_active == True)  # noqa: E712
    if active == "false":
        stmt = stmt.where(Product.is_active == False)  # noqa: E712
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(Product, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    return {"items": [_dump(p) for p in rows], "total": total,
            "page": pg["page"], "page_size": pg["page_size"],
            "categories": [r[0] for r in db.execute(
                select(Product.category).where(Product.org_id == scope.org_id)
                .distinct().order_by(Product.category)).all() if r[0]]}


@router.post("", status_code=201)
def create_product(body: ProductIn, scope: OrgScope = Depends(require_role("product.write")),
                   db: Session = Depends(get_db)):
    dup = db.scalar(select(Product).where(Product.org_id == scope.org_id,
                                          Product.sku == body.sku))
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "sku_exists", "message": f"SKU {body.sku} 已存在"})
    p = Product(org_id=scope.org_id, **_to_model(body), data_source="manual")
    db.add(p)
    audit(db, scope.org_id, scope.user.id, "product.create", "product", p.id, {"sku": p.sku})
    db.commit()
    return _dump(p)


def _to_model(body: ProductIn | ProductUpdate) -> dict:
    data = body.model_dump(exclude_unset=True, exclude={"price_tiers", "certifications"})
    if "price_tiers" in body.model_fields_set:
        data["price_tiers_json"] = json.dumps(
            [t if isinstance(t, dict) else t.model_dump() for t in body.price_tiers or []])
    if "certifications" in body.model_fields_set:
        data["certifications_json"] = json.dumps(body.certifications or [])
    return data


@router.get("/export")
def export_products(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                    fmt: str = Query("csv", pattern="^(csv|xlsx)$")):
    rows = db.scalars(select(Product).where(Product.org_id == scope.org_id)
                      .order_by(Product.id)).all()
    headers = ["sku", "name_zh", "name_en", "category", "material", "spec", "color",
               "packaging", "moq", "price_tiers", "currency", "lead_time_days",
               "certifications", "customization", "stock_status", "markets", "is_active"]
    if fmt == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "products"
        ws.append(headers)
        for p in rows:
            ws.append(_row(p))
        buf = io.BytesIO()
        wb.save(buf)
        return Response(content=buf.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=products.xlsx"})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for p in rows:
        writer.writerow(_row(p))
    return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=products.csv"})


def _row(p: Product) -> list:
    return [p.sku, p.name_zh, p.name_en, p.category, p.material, p.spec, p.color,
            p.packaging, p.moq,
            "; ".join(f"{t.get('min_qty')}:{t.get('unit_price')}" for t in json.loads(p.price_tiers_json or "[]")),
            p.currency, p.lead_time_days,
            ", ".join(json.loads(p.certifications_json or "[]")),
            p.customization, p.stock_status, p.markets, "是" if p.is_active else "否"]


@router.get("/{product_id}")
def get_product(product_id: int, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.org_id == scope.org_id, Product.id == product_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "产品不存在"})
    data = _dump(p)
    if p.supplier_id:
        sup = db.get(Supplier, p.supplier_id)
        if sup:
            data["supplier_name"] = sup.name
    return data


@router.patch("/{product_id}")
def update_product(product_id: int, body: ProductUpdate,
                   scope: OrgScope = Depends(require_role("product.write")),
                   db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.org_id == scope.org_id, Product.id == product_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "产品不存在"})
    for k, v in _to_model(body).items():
        setattr(p, k, v)
    audit(db, scope.org_id, scope.user.id, "product.update", "product", p.id,
          {"fields": list(_to_model(body).keys())})
    db.commit()
    return _dump(p)


@router.post("/bulk-active")
def bulk_active(body: BulkIds, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    rows = db.scalars(select(Product).where(Product.org_id == scope.org_id,
                                            Product.id.in_(body.ids))).all()
    for p in rows:
        p.is_active = body.is_active
    audit(db, scope.org_id, scope.user.id, "product.bulk_active", "product", "",
          {"count": len(rows), "is_active": body.is_active})
    db.commit()
    return {"updated": len(rows)}


# ------------------------------------------------------------------ supplier quotes
from fastapi import Request  # noqa: E402
from ...models import SupplierProduct  # noqa: E402
from ...services.compare import compare_suppliers, recommend_reason  # noqa: E402


@router.get("/{product_id}/supplier-quotes")
def supplier_quotes(product_id: int, scope: OrgScope = Depends(get_scope),
                    db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.org_id == scope.org_id,
                                              Product.id == product_id))
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "产品不存在"})
    rows = compare_suppliers(db, scope.org_id, product)
    items = [{
        "id": q.supplier_product.id,
        "supplier_id": q.supplier_product.supplier_id,
        "supplier_name": q.supplier.name if q.supplier else "",
        "cost_price": q.supplier_product.cost_price,
        "currency": q.supplier_product.currency,
        "moq": q.supplier_product.moq,
        "lead_time_days": q.supplier_product.lead_time_days,
        "total": q.total,
        "scores": q.scores,
    } for q in rows]
    return {"items": items, "recommend_reason": recommend_reason(rows)}


from ...schemas import ORMModel as _ORM  # noqa: E402


class SupplierQuoteIn(_ORM):
    supplier_id: int
    cost_price: float
    currency: str = "CNY"
    moq: int = 0
    lead_time_days: int = 0
    supplier_sku: str = ""


@router.post("/{product_id}/supplier-quotes", status_code=201)
def add_supplier_quote(product_id: int, body: SupplierQuoteIn,
                       scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.org_id == scope.org_id,
                                              Product.id == product_id))
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "产品不存在"})
    sup = db.scalar(select(Supplier).where(Supplier.org_id == scope.org_id,
                                           Supplier.id == body.supplier_id))
    if sup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "供应商不存在"})
    row = SupplierProduct(org_id=scope.org_id, product_id=product.id,
                          supplier_id=sup.id, supplier_sku=body.supplier_sku,
                          cost_price=body.cost_price, currency=body.currency,
                          moq=body.moq, lead_time_days=body.lead_time_days)
    db.add(row)
    audit(db, scope.org_id, scope.user.id, "product.supplier_quote.add", "product", product.id,
          {"supplier": sup.name, "cost": body.cost_price})
    db.commit()
    return {"id": row.id}


@router.delete("/{product_id}/supplier-quotes/{row_id}")
def delete_supplier_quote(product_id: int, row_id: int,
                          scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    row = db.scalar(select(SupplierProduct).where(
        SupplierProduct.org_id == scope.org_id,
        SupplierProduct.id == row_id, SupplierProduct.product_id == product_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "比价记录不存在"})
    db.delete(row)
    audit(db, scope.org_id, scope.user.id, "product.supplier_quote.delete", "product", product_id,
          {"row": row_id})
    db.commit()
    return {"ok": True}
