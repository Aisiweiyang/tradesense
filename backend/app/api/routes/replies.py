"""Reply draft routes: generate (10 kinds x 3 tones), edit, approve."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope
from ...models import Customer, Inquiry, KnowledgeDocument, ReplyDraft
from ...schemas import ReplyGenerateIn, ReplyOut, ReplyUpdateIn
from ...services.ai import ai_polish_reply
from ...services.audit import audit
from ...services.reply_drafts import build_variables, generate_draft
from ...services.requirement_service import RequirementService

router = APIRouter(prefix="/replies", tags=["replies"])


def _dump(r: ReplyDraft) -> dict:
    data = ReplyOut.model_validate(r).model_dump(mode="json")
    data["variables"] = json.loads(r.variables_json or "{}")
    data["facts_used"] = json.loads(r.facts_used_json or "[]")
    data["needs_confirmation"] = json.loads(r.needs_confirmation_json or "[]")
    return data


def _inquiry(db: Session, scope: OrgScope, inquiry_id: int) -> Inquiry:
    inq = db.scalar(select(Inquiry).where(Inquiry.org_id == scope.org_id, Inquiry.id == inquiry_id))
    if inq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "询盘不存在"})
    return inq


@router.post("/generate", status_code=201)
def generate(body: ReplyGenerateIn, scope: OrgScope = Depends(get_scope),
             db: Session = Depends(get_db)):
    if "inquiry_id" not in body.extra:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "missing_inquiry", "message": "extra 需包含 inquiry_id"})
    inq = _inquiry(db, scope, int(body.extra["inquiry_id"]))
    svc = RequirementService(db, scope.org_id)
    values = svc.active_values(inq.id)
    customer = db.get(Customer, inq.customer_id) if inq.customer_id else None
    extra = dict(body.extra)
    if customer:
        contact = customer.contacts[0] if customer.contacts else None
        extra["customer_name"] = (contact.name.split(" ")[0] if contact and contact.name
                                  else customer.company_name)
    variables = build_variables(inq, values, extra)

    # auto-fill the clarification questions when generating ask-for-info drafts
    if body.kind in ("first_reply", "ask_missing_info") and not extra.get("questions_en"):
        from ...services.clarification import build_candidates
        candidates = build_candidates(db, scope.org_id, values)[:3]
        extra_q_en = "\n".join(f"- {c['question_en']}" for c in candidates)
        extra_q_zh = "\n".join(f"- {c['question_zh']}" for c in candidates)
        variables["questions_en"] = extra_q_en or "- Any other requirements we should know?"
        variables["questions_zh"] = extra_q_zh or "- 其他需要我们了解的需求？"

    draft_data = generate_draft(body.kind, body.tone, variables, values)

    # optional AI polish — template stays the deterministic fallback
    polished = ai_polish_reply(body.kind, draft_data["body_en"])
    if polished:
        draft_data["variables"]["ai_polished"] = True
        draft_data["body_en"] = polished
        draft_data["needs_confirmation"].append("正文经过 AI 润色，请人工核对事实未被改动")

    # 知识库引用（可选）：extra.knowledge_ids 指定条目，按 org 取，摘录以引用块进正文；
    # 未指定时行为与原来完全一致。放在 AI 润色之后追加，引用内容不会被润色改写。
    raw_ids = body.extra.get("knowledge_ids") or []
    kb_entries = []
    if isinstance(raw_ids, list) and raw_ids:
        wanted = []
        for rid in raw_ids:
            try:
                wanted.append(int(rid))
            except (TypeError, ValueError):
                continue
        if wanted:
            rows = db.scalars(select(KnowledgeDocument).where(
                KnowledgeDocument.org_id == scope.org_id,
                KnowledgeDocument.id.in_(wanted))).all()
            by_id = {k.id: k for k in rows}
            kb_entries = [by_id[i] for i in dict.fromkeys(wanted) if i in by_id]
    if kb_entries:
        quotes = []
        for k in kb_entries:
            excerpt = " ".join(k.content.split())
            if len(excerpt) > 220:
                excerpt = excerpt[:220].rstrip() + "…"
            quotes.append(f"> {k.title}: {excerpt}")
        draft_data["body_en"] += ("\n\nUseful notes from our team knowledge base, please double-check "
                                  "before sending:\n\n" + "\n>\n".join(quotes))
        draft_data["facts_used"].extend(
            {"field": f"知识库#{k.id}", "value": k.title, "source_message_id": None}
            for k in kb_entries)
        draft_data["needs_confirmation"].append("知识库内容已引用，请人工核对")

    draft = ReplyDraft(
        org_id=scope.org_id, inquiry_id=inq.id, kind=body.kind, tone=body.tone,
        subject_en=draft_data["subject_en"], body_en=draft_data["body_en"],
        body_zh=draft_data["body_zh"],
        variables_json=json.dumps(draft_data["variables"], ensure_ascii=False),
        facts_used_json=json.dumps(draft_data["facts_used"], ensure_ascii=False),
        needs_confirmation_json=json.dumps(draft_data["needs_confirmation"], ensure_ascii=False),
        created_by_user_id=scope.user.id,
    )
    db.add(draft)
    db.flush()
    audit(db, scope.org_id, scope.user.id, "reply.generate", "reply", draft.id,
          {"kind": body.kind, "tone": body.tone, "inquiry": inq.id})
    db.commit()
    return _dump(draft)


@router.get("")
def list_replies(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                 inquiry_id: int = 0, status_filter: str = ""):
    stmt = select(ReplyDraft).where(ReplyDraft.org_id == scope.org_id)
    if inquiry_id:
        stmt = stmt.where(ReplyDraft.inquiry_id == inquiry_id)
    if status_filter:
        stmt = stmt.where(ReplyDraft.status == status_filter)
    rows = db.scalars(stmt.order_by(ReplyDraft.id.desc()).limit(100)).all()
    return {"items": [_dump(r) for r in rows]}


@router.get("/{reply_id}")
def get_reply(reply_id: int, scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    r = db.scalar(select(ReplyDraft).where(ReplyDraft.org_id == scope.org_id, ReplyDraft.id == reply_id))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "草稿不存在"})
    return _dump(r)


@router.patch("/{reply_id}")
def update_reply(reply_id: int, body: ReplyUpdateIn, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    r = db.scalar(select(ReplyDraft).where(ReplyDraft.org_id == scope.org_id, ReplyDraft.id == reply_id))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "草稿不存在"})
    changed = False
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "status":
            if v not in ("draft", "edited", "approved", "sent_manually", "discarded"):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail={"code": "bad_status", "message": f"非法状态 {v}"})
            if v == "sent_manually" and r.status != "approved":
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    detail={"code": "must_approve_first",
                                            "message": "只有人工批准后的草稿才能标记为已人工发送"})
        setattr(r, k, v)
        changed = True
    if changed and r.status == "draft":
        r.status = "edited"
    audit(db, scope.org_id, scope.user.id, "reply.update", "reply", r.id,
          {"fields": list(body.model_dump(exclude_none=True).keys())})
    db.commit()
    return _dump(r)


@router.post("/{reply_id}/approve")
def approve_reply(reply_id: int, scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    r = db.scalar(select(ReplyDraft).where(ReplyDraft.org_id == scope.org_id, ReplyDraft.id == reply_id))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "草稿不存在"})
    needs = json.loads(r.needs_confirmation_json or "[]")
    r.status = "approved"
    audit(db, scope.org_id, scope.user.id, "reply.approve", "reply", r.id,
          {"kind": r.kind, "pending_confirmations": needs})
    db.commit()
    return {**_dump(r), "note": "已批准。系统不会自动发送，请业务员在邮件/WhatsApp 中人工发送。"}
