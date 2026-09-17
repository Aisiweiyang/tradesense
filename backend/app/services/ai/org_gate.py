"""org 级 AI Intake 开关：organizations.settings_json 里的 {"ai_intake": bool}。

默认开启（AI 可用的前提下）；owner 可在设置页关闭，关了全走规则提取。
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ...models import Organization


def intake_enabled(db: Session, org: Organization) -> bool:
    try:
        cfg = json.loads(org.settings_json or "{}")
    except json.JSONDecodeError:
        cfg = {}
    return bool(cfg.get("ai_intake", True))


def set_intake_enabled(db: Session, org: Organization, enabled: bool) -> None:
    try:
        cfg = json.loads(org.settings_json or "{}")
    except json.JSONDecodeError:
        cfg = {}
    cfg["ai_intake"] = enabled
    org.settings_json = json.dumps(cfg, ensure_ascii=False)
