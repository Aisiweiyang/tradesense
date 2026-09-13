"""Customer CRM routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from ...database import get_db
from ...deps import OrgScope, get_scope, order_by, paginate
from ...models import Customer, FollowUpTask, Inquiry, Quote
from ...schemas import ContactIn, CustomerIn, CustomerOut, CustomerUpdate
from ...services.audit import audit
from ...services.followup import score_customer

router = APIRouter(prefix="/customers", tags=["customers"])


def _with_score(db: Session, scope: OrgScope, c: Customer) -> Customer:
    inquiries = list(db.scalars(select(Inquiry).where(
        Inquiry.org_id == scope.org_id, Inquiry.customer_id == c.id)))
    quotes = list(db.scalars(select(Quote).where(
        Quote.org_id == scope.org_id,
        Quote.inquiry_id.in_([i.id for i in inquiries] or [0]))))
    score, factors = score_customer(c, inquiries, quotes)
    if score != c.lead_score:
        c.lead_score = score
        c.lead_score_factors = __import__("json").dumps(factors, ensure_ascii=False)
    return c


@router.get("")
def list_customers(
    scope: OrgScope = Depends(get_scope),
    db: Session = Depends(get_db),
    pg: dict = Depends(paginate),
    q: str = Query("", max_length=200),
    stage: str = Query("", max_length=30),
):
    stmt = select(Customer).options(joinedload(Customer.contacts)).where(
        Customer.org_id == scope.org_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Customer.company_name.ilike(like), Customer.country.ilike(like),
                              Customer.tags.ilike(like)))
    if stage:
        stmt = stmt.where(Customer.stage == stage)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(Customer, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    items = []
    for c in rows:
        _with_score(db, scope, c)
        items.append(CustomerOut.model_validate(c).model_dump(mode="json"))
    db.commit()
    return {"items": items, "total": total, "page": pg["page"], "page_size": pg["page_size"]}


@router.post("", status_code=201)
def create_customer(body: CustomerIn, scope: OrgScope = Depends(get_scope),
                    db: Session = Depends(get_db)):
    c = Customer(org_id=scope.org_id, company_name=body.company_name, country=body.country,
                 source_channel=body.source_channel, tags=body.tags, priority=body.priority,
                 stage=body.stage, notes=body.notes, next_follow_up_at=body.next_follow_up_at)
    db.add(c)
    db.flush()
    from ...models import Contact
    for contact in body.contacts:
        db.add(Contact(org_id=scope.org_id, customer_id=c.id, **contact.model_dump()))
    audit(db, scope.org_id, scope.user.id, "customer.create", "customer", c.id,
          {"company_name": c.company_name})
    db.commit()
    return CustomerOut.model_validate(
        db.scalar(select(Customer).options(joinedload(Customer.contacts))
                  .where(Customer.id == c.id))).model_dump(mode="json")


@router.get("/{customer_id}")
def get_customer(customer_id: int, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    c = db.scalar(select(Customer).options(joinedload(Customer.contacts)).where(
        Customer.org_id == scope.org_id, Customer.id == customer_id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "客户不存在"})
    _with_score(db, scope, c)
    db.commit()
    data = CustomerOut.model_validate(c).model_dump(mode="json")
    inquiries = db.scalars(select(Inquiry).where(
        Inquiry.org_id == scope.org_id, Inquiry.customer_id == customer_id)
        .order_by(Inquiry.id.desc())).all()
    data["inquiries"] = [{"id": i.id, "title": i.title, "status": i.status,
                          "completeness": i.completeness, "updated_at": i.updated_at.isoformat()}
                         for i in inquiries]
    tasks = db.scalars(select(FollowUpTask).where(
        FollowUpTask.org_id == scope.org_id, FollowUpTask.customer_id == customer_id,
        FollowUpTask.status == "pending").order_by(FollowUpTask.due_at)).all()
    data["pending_tasks"] = [{"id": t.id, "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None}
                             for t in tasks]
    return data


@router.patch("/{customer_id}")
def update_customer(customer_id: int, body: CustomerUpdate,
                    scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    c = db.scalar(select(Customer).where(Customer.org_id == scope.org_id, Customer.id == customer_id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "客户不存在"})
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    audit(db, scope.org_id, scope.user.id, "customer.update", "customer", c.id,
          {"fields": list(body.model_dump(exclude_none=True).keys())})
    db.commit()
    return CustomerOut.model_validate(c).model_dump(mode="json")


@router.post("/{customer_id}/contacts", status_code=201)
def add_contact(customer_id: int, body: ContactIn, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    c = db.scalar(select(Customer).where(Customer.org_id == scope.org_id, Customer.id == customer_id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "客户不存在"})
    from ...models import Contact
    contact = Contact(org_id=scope.org_id, customer_id=customer_id, **body.model_dump())
    db.add(contact)
    db.commit()
    from ...schemas import ContactOut
    return ContactOut.model_validate(contact).model_dump(mode="json")
