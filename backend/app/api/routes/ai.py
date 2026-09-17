"""AI Intake routes: status, org toggle, manual re-parse."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope
from ...models import Inquiry, Organization
from ...rbac import require_role
from ...services.ai import get_ai
from ...services.ai.org_gate import intake_enabled, set_intake_enabled
from ...services.ai.runner import run_intake
from ...services.audit import audit

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    ai = get_ai()
    org = db.get(Organization, scope.org_id)
    return {"provider": ai.name, "available": ai.available(),
            "intake_enabled": intake_enabled(db, org) if org else False}


class IntakeToggleIn(BaseModel):
    intake_enabled: bool


@router.put("/settings")
def ai_settings(body: IntakeToggleIn, scope: OrgScope = Depends(require_role("settings.manage")),
                db: Session = Depends(get_db)):
    org = db.get(Organization, scope.org_id)
    set_intake_enabled(db, org, body.intake_enabled)
    audit(db, scope.org_id, scope.user.id, "ai.settings", "organization", scope.org_id,
          {"intake_enabled": body.intake_enabled})
    db.commit()
    return {"intake_enabled": body.intake_enabled}


@router.post("/parse/{inquiry_id}")
def ai_parse(inquiry_id: int, scope: OrgScope = Depends(require_role("inquiry.write")),
             db: Session = Depends(get_db)):
    """手动触发 AI 解析（新建询盘与渠道同步之外的人工入口）。"""
    inq = db.scalar(select(Inquiry).where(
        Inquiry.org_id == scope.org_id, Inquiry.id == inquiry_id))
    if inq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "询盘不存在"})
    summary = run_intake(db, scope.org_id, inq, scope.user.id)
    if summary is None:
        return {"ok": False, "reason": "AI 不可用、已关闭或没有可解析文本"}
    db.commit()
    return {"ok": True, **summary}
