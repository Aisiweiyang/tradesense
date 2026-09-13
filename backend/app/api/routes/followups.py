"""Follow-up task routes + workload lists + supplier routes."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope, order_by, paginate
from ...models import Customer, FollowUpTask, Inquiry, Supplier
from ...schemas import FollowUpIn, FollowUpOut, FollowUpStatusIn, SupplierIn, SupplierOut
from ...services.audit import audit
from ...services.followup import create_task, workload_enriched

router = APIRouter(prefix="/followups", tags=["followups"])


@router.get("/workload")
def workload(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    return workload_enriched(db, scope.org_id)


@router.get("")
def list_followups(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                   pg: dict = Depends(paginate), status_filter: str = Query("", alias="status"),
                   scope_filter: str = Query("", alias="scope")):
    stmt = select(FollowUpTask).where(FollowUpTask.org_id == scope.org_id)
    now = datetime.now(timezone.utc)
    if status_filter:
        stmt = stmt.where(FollowUpTask.status == status_filter)
    if scope_filter == "due":
        stmt = stmt.where(FollowUpTask.status.in_(["pending"]),
                          FollowUpTask.due_at != None, FollowUpTask.due_at <= now)  # noqa: E711
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(FollowUpTask, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    return {"items": [FollowUpOut.model_validate(t).model_dump(mode="json") for t in rows],
            "total": total, "page": pg["page"], "page_size": pg["page_size"]}


@router.post("", status_code=201)
def create(body: FollowUpIn, scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    if not body.due_at:
        body.due_at = datetime.now(timezone.utc) + timedelta(days=1)
    task = create_task(db, scope.org_id, title=body.title, description=body.description,
                       inquiry_id=body.inquiry_id, customer_id=body.customer_id,
                       task_type=body.task_type, due_at=body.due_at,
                       priority=body.priority,
                       reason_json=json.dumps(body.reason, ensure_ascii=False),
                       created_by_user_id=scope.user.id)
    audit(db, scope.org_id, scope.user.id, "followup.create", "followup", task.id,
          {"title": task.title})
    db.commit()
    return FollowUpOut.model_validate(task).model_dump(mode="json")


@router.post("/{task_id}/status")
def set_status(task_id: int, body: FollowUpStatusIn, scope: OrgScope = Depends(get_scope),
               db: Session = Depends(get_db)):
    task = db.scalar(select(FollowUpTask).where(FollowUpTask.org_id == scope.org_id,
                                                FollowUpTask.id == task_id))
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "任务不存在"})
    if body.status not in ("pending", "done", "snoozed", "cancelled"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "bad_status", "message": f"非法状态 {body.status}"})
    task.status = body.status
    if body.status == "done":
        task.completed_at = datetime.now(timezone.utc)
    if body.due_at:
        task.due_at = body.due_at
    db.commit()
    return FollowUpOut.model_validate(task).model_dump(mode="json")


# ------------------------------------------------------------------ suppliers
suppliers_router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@suppliers_router.get("")
def list_suppliers(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                   q: str = Query("", max_length=100)):
    stmt = select(Supplier).where(Supplier.org_id == scope.org_id)
    if q:
        stmt = stmt.where(Supplier.name.ilike(f"%{q}%"))
    rows = db.scalars(stmt.order_by(Supplier.id)).all()
    return {"items": [SupplierOut.model_validate(s).model_dump(mode="json") for s in rows]}


@suppliers_router.post("", status_code=201)
def create_supplier(body: SupplierIn, scope: OrgScope = Depends(get_scope),
                    db: Session = Depends(get_db)):
    s = Supplier(org_id=scope.org_id, **body.model_dump())
    db.add(s)
    db.commit()
    return SupplierOut.model_validate(s).model_dump(mode="json")


@suppliers_router.patch("/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierIn, scope: OrgScope = Depends(get_scope),
                    db: Session = Depends(get_db)):
    s = db.scalar(select(Supplier).where(Supplier.org_id == scope.org_id, Supplier.id == supplier_id))
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "供应商不存在"})
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return SupplierOut.model_validate(s).model_dump(mode="json")
