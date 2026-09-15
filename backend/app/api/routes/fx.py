"""汇率配置路由：手工维护，manager+。存储方向按币种字母序规范化。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope
from ...models import ExchangeRate, User
from ...rbac import require_role
from ...services.audit import audit
from ...services.fx import MISSING, normalize, resolve

router = APIRouter(prefix="/fx", tags=["fx"])

CCY = r"^[A-Za-z]{3}$"


class FxSetIn(BaseModel):
    base_currency: str = Field(pattern=CCY)
    quote_currency: str = Field(pattern=CCY)
    rate: float = Field(gt=0)


@router.get("/resolve")
def resolve_rate(from_ccy: str = Query(..., min_length=3, max_length=3),
                 to_ccy: str = Query(..., min_length=3, max_length=3),
                 scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    """报价面板预览当前生效汇率：登录即可（member 也要能看），不含任何敏感配置。"""
    rate, note = resolve(db, scope.org_id, from_ccy, to_ccy)
    return {"from_currency": from_ccy.upper(), "to_currency": to_ccy.upper(),
            "rate": rate, "configured": not note.startswith(MISSING)}


@router.get("")
def list_rates(scope: OrgScope = Depends(require_role("fx.manage")), db: Session = Depends(get_db)):
    rows = db.scalars(select(ExchangeRate).where(
        ExchangeRate.org_id == scope.org_id).order_by(ExchangeRate.base_currency)).all()
    users = {u.id: u.name for u in db.scalars(select(User).where(
        User.org_id == scope.org_id)).all()}
    return {"items": [{
        "id": r.id,
        "base_currency": r.base_currency,
        "quote_currency": r.quote_currency,
        "rate": r.rate,
        "pair": f"{r.base_currency}/{r.quote_currency}",
        "updated_by_name": users.get(r.updated_by_user_id, ""),
        "updated_at": r.updated_at,
    } for r in rows]}


@router.put("")
def set_rate(body: FxSetIn, scope: OrgScope = Depends(require_role("fx.manage")),
             db: Session = Depends(get_db)):
    if body.base_currency.upper() == body.quote_currency.upper():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "same_currency", "message": "两种币种不能相同"})
    base, quote = normalize(body.base_currency, body.quote_currency)
    rate = body.rate
    if base != body.base_currency.upper():
        # 输入方向与存储方向相反：USD/CNY=7.2 规范化为 CNY/USD 后存 1/7.2
        rate = 1.0 / body.rate
    row = db.scalar(select(ExchangeRate).where(
        ExchangeRate.org_id == scope.org_id,
        ExchangeRate.base_currency == base, ExchangeRate.quote_currency == quote))
    if row is None:
        row = ExchangeRate(org_id=scope.org_id, base_currency=base, quote_currency=quote)
        db.add(row)
    row.rate = rate
    row.updated_by_user_id = scope.user.id
    db.flush()
    audit(db, scope.org_id, scope.user.id, "fx.set", "exchange_rate", row.id,
          {"pair": f"{base}/{quote}", "rate": body.rate})
    db.commit()
    return {"id": row.id, "pair": f"{base}/{quote}", "rate": row.rate,
            "note": f"存储方向 {base}/{quote}=1 base 兑 rate quote；反向查询按 1/rate 折算"}


@router.delete("/{rate_id}", status_code=204)
def delete_rate(rate_id: int, scope: OrgScope = Depends(require_role("fx.manage")),
                db: Session = Depends(get_db)):
    row = db.scalar(select(ExchangeRate).where(
        ExchangeRate.org_id == scope.org_id, ExchangeRate.id == rate_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "汇率记录不存在"})
    db.delete(row)
    audit(db, scope.org_id, scope.user.id, "fx.delete", "exchange_rate", rate_id,
          {"pair": f"{row.base_currency}/{row.quote_currency}"})
    db.commit()
    return None
