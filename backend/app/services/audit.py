"""Audit log helper (sensitive values must never be written here)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent

_SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "authorization", "config_json"}


def _sanitize(detail: dict) -> dict:
    return {k: ("***" if k.lower() in _SENSITIVE_KEYS else v) for k, v in detail.items()}


def audit(db: Session, org_id: int, user_id: int | None, action: str,
          entity_type: str = "", entity_id: str = "", detail: dict | None = None) -> None:
    db.add(AuditEvent(
        org_id=org_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=str(entity_id),
        detail_json=json.dumps(_sanitize(detail or {}), ensure_ascii=False, default=str),
    ))
