"""Shared FastAPI dependencies: auth, org scoping, pagination, error envelope."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "unauthorized", "message": "缺少访问令牌"})
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "invalid_token", "message": "令牌无效或已过期"})
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "invalid_user", "message": "用户不存在或已停用"})
    return user


class OrgScope:
    """org_id enforced from the token — request can never choose another org."""

    def __init__(self, user: User):
        self.user = user
        self.org_id = user.org_id


def get_scope(user: User = Depends(get_current_user)) -> OrgScope:
    return OrgScope(user)


def paginate(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("-id"),
):
    return {"page": page, "page_size": page_size, "sort": sort}


def order_by(model, sort: str):
    desc = sort.startswith("-")
    field = sort.lstrip("-")
    col = getattr(model, field, None)
    if col is None:
        col = model.id
    return col.desc() if desc else col.asc()
