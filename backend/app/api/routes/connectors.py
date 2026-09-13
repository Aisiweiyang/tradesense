"""Connector management routes + webhook endpoints + public form/widget."""
from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from ...deps import OrgScope, get_scope
from ...models import ConnectorAccount, SyncLog
from ...schemas import ConnectorAccountIn, ConnectorAccountOut
from ...services.audit import audit
from ...services.connectors import (CONNECTOR_REGISTRY, get_connector, registry_meta,
                                    normalize_generic_payload, run_sync)
from ...services.connectors.whatsapp_sim import normalize_whatsapp_payload
from ...services.ingestion import ingest_external_message

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("/types")
def list_types():
    """All supported connector types with their real/simulated capabilities."""
    return {"items": registry_meta()}


@router.get("")
def list_accounts(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    rows = db.scalars(select(ConnectorAccount).where(
        ConnectorAccount.org_id == scope.org_id).order_by(ConnectorAccount.id)).all()
    items = []
    for a in rows:
        item = ConnectorAccountOut.model_validate(a).model_dump(mode="json")
        meta = CONNECTOR_REGISTRY.get(a.connector_type)
        item["label"] = meta["label"] if meta else a.connector_type
        item["live_supported"] = meta["live_supported"] if meta else False
        item["env_keys"] = meta["env_keys"] if meta else []
        try:
            cfg = json.loads(a.config_json or "{}")
        except json.JSONDecodeError:
            cfg = {}
        item["config_nonsecret"] = {k: v for k, v in cfg.items()
                                    if not any(s in k.lower() for s in ("password", "token", "secret", "key"))}
        items.append(item)
    return {"items": items}


@router.post("", status_code=201)
def create_account(body: ConnectorAccountIn, scope: OrgScope = Depends(get_scope),
                   db: Session = Depends(get_db)):
    meta = CONNECTOR_REGISTRY.get(body.connector_type)
    if meta is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "unknown_connector",
                                    "message": f"不支持的连接器类型 {body.connector_type}"})
    missing = [k for k in meta["required_config"] if k not in body.config]
    mode = "live" if (meta["live_supported"] and not missing and _has_env_keys(meta)) else "simulated"
    account = ConnectorAccount(
        org_id=scope.org_id, connector_type=body.connector_type, name=body.name,
        mode=mode, status="disconnected",
        auth_state="authorized" if mode == "live" else "not_authorized_simulated",
        config_json=json.dumps(body.config, ensure_ascii=False),
    )
    db.add(account)
    db.flush()
    conn = get_connector(db, account)
    conn.log("account_created", "info", {"mode": mode})
    audit(db, scope.org_id, scope.user.id, "connector.create", "connector", account.id,
          {"type": body.connector_type, "mode": mode})
    db.commit()
    return ConnectorAccountOut.model_validate(account).model_dump(mode="json")


def _has_env_keys(meta: dict) -> bool:
    import os
    return all(os.environ.get(k) for k in meta.get("env_keys", []))


@router.post("/{account_id}/test")
def test_account(account_id: int, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    account = _account(db, scope, account_id)
    conn = get_connector(db, account)
    result = conn.health_check()
    account.status = "connected" if result.get("ok") else "error"
    conn.log("health_check", "info", result)
    db.commit()
    return result


@router.post("/{account_id}/sync")
def sync_account(account_id: int, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    account = _account(db, scope, account_id)

    def ingest(payload: dict) -> dict:
        result = ingest_external_message(db, scope.org_id, account, payload)
        db.flush()
        return result

    result = run_sync(db, account, ingest)
    audit(db, scope.org_id, scope.user.id, "connector.sync", "connector", account.id, result)
    db.commit()
    return result


@router.get("/{account_id}/status")
def account_status(account_id: int, scope: OrgScope = Depends(get_scope),
                   db: Session = Depends(get_db)):
    account = _account(db, scope, account_id)
    return get_connector(db, account).sync_status()


@router.get("/{account_id}/logs")
def account_logs(account_id: int, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    _account(db, scope, account_id)
    rows = db.scalars(select(SyncLog).where(
        SyncLog.org_id == scope.org_id, SyncLog.connector_account_id == account_id
    ).order_by(SyncLog.id.desc()).limit(limit)).all()
    return {"items": [{"id": r.id, "level": r.level, "event": r.event,
                       "detail": json.loads(r.detail_json or "{}"),
                       "created_at": r.created_at.isoformat()} for r in rows]}


@router.delete("/{account_id}")
def delete_account(account_id: int, scope: OrgScope = Depends(get_scope),
                   db: Session = Depends(get_db)):
    account = _account(db, scope, account_id)
    audit(db, scope.org_id, scope.user.id, "connector.delete", "connector", account.id,
          {"type": account.connector_type})
    db.delete(account)
    db.commit()
    return {"ok": True}


def _account(db: Session, scope: OrgScope, account_id: int) -> ConnectorAccount:
    account = db.scalar(select(ConnectorAccount).where(
        ConnectorAccount.org_id == scope.org_id, ConnectorAccount.id == account_id))
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "连接器账号不存在"})
    return account


# ------------------------------------------------------------------ webhooks
webhooks_router = APIRouter(tags=["webhooks"])


@webhooks_router.get("/webhooks/whatsapp/{account_id}")
def whatsapp_verify(account_id: int, request: Request, db: Session = Depends(get_db),
                    org_scope: OrgScope = Depends(get_scope)):
    """Meta webhook verification handshake (hub.challenge echo)."""
    account = _account(db, org_scope, account_id)
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge", "")
    verify_token = (json.loads(account.config_json or "{}").get("verify_token")
                    or settings.secret_key[:20])
    supplied = request.query_params.get("hub.verify_token", "")
    if hub_mode == "subscribe" and supplied == verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        detail={"code": "verify_failed", "message": "Webhook 校验失败"})


@webhooks_router.post("/webhooks/whatsapp/{account_id}")
async def whatsapp_webhook(account_id: int, request: Request,
                           db: Session = Depends(get_db),
                           org_scope: OrgScope = Depends(get_scope)):
    account = _account(db, org_scope, account_id)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "bad_json", "message": "请求体不是合法 JSON"})
    conn = get_connector(db, account)
    msgs = conn.handle_webhook(payload)
    results = []
    for m in msgs:
        res = ingest_external_message(db, org_scope.org_id, account, m)
        results.append({"ingested": not res.get("duplicate"),
                        "external_message": res.get("external_message_id")})
    conn.log("webhook_received", "info", {"messages": len(msgs)})
    db.commit()
    return {"received": len(msgs), "results": results}


@webhooks_router.post("/webhooks/generic/{account_id}")
async def generic_webhook(account_id: int, request: Request, db: Session = Depends(get_db),
                          org_scope: OrgScope = Depends(get_scope)):
    """Generic inbound webhook for n8n / Zapier / Make / internal CRM."""
    account = _account(db, org_scope, account_id)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "bad_json", "message": "请求体不是合法 JSON"})
    normalized = normalize_generic_payload(payload)
    if not normalized["text"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "empty_text",
                                    "message": "payload 缺少 text/message/body 内容字段"})
    res = ingest_external_message(db, org_scope.org_id, account, normalized)
    conn = get_connector(db, account)
    conn.log("webhook_received", "info", {"duplicate": res.get("duplicate", False)})
    db.commit()
    return {"ingested": not res.get("duplicate"),
            "duplicate": bool(res.get("duplicate")),
            "reason": res.get("reason", ""),
            "inquiry_id": res["inquiry"].id if res.get("inquiry") else None}


# ------------------------------------------------------------------ public
public_router = APIRouter(prefix="/public", tags=["public"])


@public_router.post("/webform/{account_id}")
async def webform_submit(account_id: int, request: Request, db: Session = Depends(get_db)):
    """Public inquiry form endpoint for a standalone website (no auth; scoped account)."""
    account = db.scalar(select(ConnectorAccount).where(
        ConnectorAccount.id == account_id, ConnectorAccount.connector_type == "webform"))
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "表单不存在"})
    try:
        form = await request.json()
    except Exception:
        form = dict(await request.form())
    # simple honeypot: bots often fill every field
    if form.get("website_url") or form.get("_hp"):
        return {"ok": True, "ignored": "honeypot"}
    text = " ".join(str(v) for k, v in form.items()
                    if k not in ("website_url", "_hp") and v).strip()
    if len(text) < 5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "empty_form", "message": "表单内容为空"})
    res = ingest_external_message(db, account.org_id, account, {
        "external_message_id": f"form-{secrets.token_hex(8)}",
        "thread_external_id": f"form:{(form.get('email') or 'anonymous')}",
        "sender": str(form.get("email") or form.get("name") or ""),
        "text": text, "attachments": [], "raw_json": form,
    })
    conn = get_connector(db, account)
    conn.log("form_submit", "info", {"duplicate": res.get("duplicate", False)})
    db.commit()
    return {"ok": True, "duplicate": bool(res.get("duplicate"))}


@public_router.get("/widget/{account_id}.js")
def widget_js(account_id: int, db: Session = Depends(get_db)):
    """Embeddable chat widget loader (基础聊天组件)."""
    account = db.scalar(select(ConnectorAccount).where(
        ConnectorAccount.id == account_id, ConnectorAccount.connector_type == "webform"))
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "组件不存在"})
    js = f"""(function() {{
  var api = window.__TRADESENSE_API__ || "{settings.cors_origins[0] if settings.cors_origins else ''}";
  var accountId = {account_id};
  var btn = document.createElement('button');
  btn.textContent = 'Inquire / 询盘';
  btn.style.cssText = 'position:fixed;right:20px;bottom:20px;z-index:99999;padding:12px 18px;' +
    'background:#2563eb;color:#fff;border:none;border-radius:24px;cursor:pointer;font-size:14px;';
  btn.onclick = function() {{
    var name = prompt('Your name / 您的姓名：') || '';
    var email = prompt('Your email / 您的邮箱：') || '';
    var msg = prompt('Your inquiry / 询盘内容：') || '';
    if (!msg) return;
    fetch(api + '/api/public/webform/' + accountId, {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{name: name, email: email, message: msg}})
    }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
      alert(d && d.ok ? 'Thank you! We received your inquiry.' : 'Something went wrong.');
    }}).catch(function() {{ alert('Network error.'); }});
  }};
  document.body.appendChild(btn);
}})();"""
    return Response(content=js, media_type="application/javascript")
