"""知识库路由：团队共享的外贸常识、合规与流程要点，可被回复草稿引用。

读写都带组织隔离；搜索 q 同时匹配标题/内容/标签。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope
from ...models import KnowledgeDocument
from ...rbac import require_role
from ...schemas import KnowledgeIn, KnowledgeOut
from ...services.audit import audit

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _dump(k: KnowledgeDocument) -> dict:
    return KnowledgeOut.model_validate(k).model_dump(mode="json")


def _get(db: Session, scope: OrgScope, kid: int) -> KnowledgeDocument:
    k = db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.org_id == scope.org_id, KnowledgeDocument.id == kid))
    if k is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "条目不存在"})
    return k


@router.get("")
def list_knowledge(q: str = "", scope: OrgScope = Depends(require_role("knowledge.read")),
                   db: Session = Depends(get_db)):
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.org_id == scope.org_id)
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(KnowledgeDocument.title.like(like),
                              KnowledgeDocument.content.like(like),
                              KnowledgeDocument.tags.like(like)))
    rows = db.scalars(stmt.order_by(KnowledgeDocument.updated_at.desc())).all()
    return {"items": [_dump(k) for k in rows]}


@router.post("", status_code=201)
def create_knowledge(body: KnowledgeIn,
                     scope: OrgScope = Depends(require_role("knowledge.write")),
                     db: Session = Depends(get_db)):
    k = KnowledgeDocument(org_id=scope.org_id, title=body.title.strip(),
                          content=body.content, tags=body.tags.strip())
    db.add(k)
    db.flush()
    audit(db, scope.org_id, scope.user.id, "knowledge.create", "knowledge", k.id,
          {"title": k.title})
    db.commit()
    return _dump(k)


@router.get("/{kid}")
def get_knowledge(kid: int, scope: OrgScope = Depends(require_role("knowledge.read")),
                  db: Session = Depends(get_db)):
    return _dump(_get(db, scope, kid))


@router.patch("/{kid}")
def update_knowledge(kid: int, body: KnowledgeIn,
                     scope: OrgScope = Depends(require_role("knowledge.write")),
                     db: Session = Depends(get_db)):
    k = _get(db, scope, kid)
    k.title = body.title.strip()
    k.content = body.content
    k.tags = body.tags.strip()
    audit(db, scope.org_id, scope.user.id, "knowledge.update", "knowledge", k.id,
          {"title": k.title})
    db.commit()
    return _dump(k)


@router.delete("/{kid}", status_code=204)
def delete_knowledge(kid: int, scope: OrgScope = Depends(require_role("knowledge.write")),
                     db: Session = Depends(get_db)):
    k = _get(db, scope, kid)
    db.delete(k)
    audit(db, scope.org_id, scope.user.id, "knowledge.delete", "knowledge", kid,
          {"title": k.title})
    db.commit()
    return None
