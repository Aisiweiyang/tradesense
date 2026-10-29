"""QuoteSheet routes: build, list, approve/reject, PDF export (no internal cost)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope
from ...rbac import require_role
from ...models import QuoteSheet, User
from ...security import decode_token
from ...services.audit import audit
from ...services.quote_sheet import create_sheet, render_sheet_pdf

router = APIRouter(prefix="/quote-sheets", tags=["quote-sheets"])


def _get(db: Session, org_id: int, sheet_id: int) -> QuoteSheet:
    sheet = db.scalar(select(QuoteSheet).where(
        QuoteSheet.org_id == org_id, QuoteSheet.id == sheet_id))
    if sheet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "报价单不存在"})
    return sheet


def _dump(s: QuoteSheet) -> dict:
    return {
        "id": s.id, "sheet_no": s.sheet_no, "version": s.version,
        "inquiry_id": s.inquiry_id, "status": s.status,
        "currency": s.currency, "incoterm": s.incoterm,
        "lines": json.loads(s.lines_json or "[]"),
        "subtotal": s.subtotal, "margin_rate": s.margin_rate,
        "target": json.loads(s.target_price_json or "{}"),
        "notes": s.notes, "is_formal": s.is_formal,
        "created_at": s.created_at.isoformat(),
    }


@router.post("", status_code=201)
def build(body: dict, scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    inquiry_id = body.get("inquiry_id")
    quote_ids = body.get("quote_ids") or []
    if not inquiry_id or not quote_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "missing_fields", "message": "需要 inquiry_id 与 quote_ids"})
    sheet = create_sheet(db, scope.org_id, int(inquiry_id),
                         [int(q) for q in quote_ids], scope.user.id,
                         body.get("notes", ""))
    audit(db, scope.org_id, scope.user.id, "quote_sheet.create", "quote_sheet", sheet.id,
          {"sheet_no": sheet.sheet_no, "lines": len(sheet.lines_json)})
    db.commit()
    return _dump(sheet)


@router.get("")
def list_sheets(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                inquiry_id: int = Query(0)):
    stmt = select(QuoteSheet).where(QuoteSheet.org_id == scope.org_id)
    if inquiry_id:
        stmt = stmt.where(QuoteSheet.inquiry_id == inquiry_id)
    rows = db.scalars(stmt.order_by(QuoteSheet.id.desc()).limit(100)).all()
    return {"items": [_dump(s) for s in rows]}


@router.get("/{sheet_id}")
def get_sheet(sheet_id: int, scope: OrgScope = Depends(get_scope),
              db: Session = Depends(get_db)):
    return _dump(_get(db, scope.org_id, sheet_id))


@router.post("/{sheet_id}/approve")
def approve(sheet_id: int, scope: OrgScope = Depends(require_role("quote.approve")),
            db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    sheet = _get(db, scope.org_id, sheet_id)
    if not json.loads(sheet.lines_json or "[]"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail={
            "code": "empty_sheet", "message": "报价单没有有效行"})
    if sheet.status in ("superseded", "rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail={
            "code": "quote_closed", "message": "该报价单已被替代或拒绝，请创建新版本后审批"})
    if sheet.status == "approved" and sheet.is_formal:
        return _dump(sheet)
    sheet.status = "approved"
    sheet.is_formal = True
    sheet.approved_by_user_id = scope.user.id
    sheet.approved_at = datetime.now(timezone.utc)
    audit(db, scope.org_id, scope.user.id, "quote_sheet.approve", "quote_sheet", sheet.id,
          {"version": sheet.version, "subtotal": sheet.subtotal})
    db.commit()
    return _dump(sheet)


@router.post("/{sheet_id}/reject")
def reject(sheet_id: int, scope: OrgScope = Depends(get_scope),
           db: Session = Depends(get_db)):
    sheet = _get(db, scope.org_id, sheet_id)
    sheet.status = "rejected"
    sheet.is_formal = False
    sheet.approved_by_user_id = None
    sheet.approved_at = None
    audit(db, scope.org_id, scope.user.id, "quote_sheet.reject", "quote_sheet", sheet.id, {})
    db.commit()
    return _dump(sheet)


@router.get("/{sheet_id}/pdf")
def export_pdf(sheet_id: int, request: Request,
               access_token: str = Query("", alias="access_token"),
               db: Session = Depends(get_db)):
    """对客报价单 PDF。JWT 走 Authorization 头或 `?access_token=`（浏览器下载
    无法带自定义头）。org 隔离不受影响：org_id 仍取自令牌。"""
    from fastapi.responses import Response

    from ...security import decode_token

    token = access_token or request.headers.get("authorization", "").removeprefix("Bearer ")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "unauthorized", "message": "缺少访问令牌"})
    try:
        payload = decode_token(token)
        user = db.get(User, int(payload["sub"]))
        if user is None or not user.is_active:
            raise ValueError
        scope = OrgScope(user)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "invalid_token", "message": "令牌无效或已过期"})
    sheet = _get(db, scope.org_id, sheet_id)
    data = render_sheet_pdf(db, scope.org_id, sheet)
    audit(db, scope.org_id, scope.user.id, "quote_sheet.export_pdf", "quote_sheet",
          sheet.id, {"formal": sheet.is_formal})
    db.commit()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{sheet.sheet_no}.pdf"'})
