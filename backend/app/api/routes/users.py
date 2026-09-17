"""User management routes (owner only): list, create, role/active/password."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope
from ...models import User
from ...rbac import require_role, ROLE_LEVELS
from ...security import hash_password
from ...services.audit import audit

router = APIRouter(prefix="/users", tags=["users"])

VALID_ROLES = ("owner", "manager", "member", "viewer")


def _dump(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "locale": u.locale}


class UserCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="member")


class UserPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


def _validate_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "invalid_role",
            "message": f"非法角色 {role}，可选值：{'/'.join(VALID_ROLES)}"})


@router.get("")
def list_users(scope: OrgScope = Depends(require_role("user.manage")),
               db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(
        User.org_id == scope.org_id).order_by(User.id)).all()
    return {"items": [_dump(u) for u in rows],
            "owner_count": db.scalar(select(func.count(User.id)).where(
                User.org_id == scope.org_id, User.role == "owner")) or 0}


@router.post("", status_code=201)
def create_user(body: UserCreateIn, scope: OrgScope = Depends(require_role("user.manage")),
                db: Session = Depends(get_db)):
    _validate_role(body.role)
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail={
            "code": "email_taken", "message": "该邮箱已被注册"})
    user = User(org_id=scope.org_id, email=email, name=body.name.strip(),
                password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    audit(db, scope.org_id, scope.user.id, "user.create", "user", user.id,
          {"email": email, "role": body.role})
    db.commit()
    return _dump(user)


@router.patch("/{user_id}")
def patch_user(user_id: int, body: UserPatchIn,
               scope: OrgScope = Depends(require_role("user.manage")),
               db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(
        User.org_id == scope.org_id, User.id == user_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "用户不存在"})
    changes = {}
    if body.role is not None and body.role != user.role:
        _validate_role(body.role)
        if user.id == scope.user.id:
            raise HTTPException(status.HTTP_409_CONFLICT, detail={
                "code": "self_demote", "message": "不能修改自己的角色（避免失去管理权限）"})
        if user.role == "owner":
            owners = db.scalar(select(func.count(User.id)).where(
                User.org_id == scope.org_id, User.role == "owner")) or 0
            if owners <= 1:
                raise HTTPException(status.HTTP_409_CONFLICT, detail={
                    "code": "last_owner", "message": "组织至少保留一名 owner"})
        user.role = body.role
        changes["role"] = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        if user.id == scope.user.id and not body.is_active:
            raise HTTPException(status.HTTP_409_CONFLICT, detail={
                "code": "self_deactivate", "message": "不能停用自己（避免失去管理权限）"})
        if not body.is_active and user.role == "owner":
            owners_active = db.scalar(select(func.count(User.id)).where(
                User.org_id == scope.org_id, User.role == "owner", User.is_active == True)) or 0  # noqa: E712
            if owners_active <= 1:
                raise HTTPException(status.HTTP_409_CONFLICT, detail={
                    "code": "last_owner", "message": "组织至少保留一名可登录的 owner"})
        user.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.name is not None:
        user.name = body.name.strip()
        changes["name"] = user.name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        changes["password_reset"] = True
    if not changes:
        return _dump(user)
    audit(db, scope.org_id, scope.user.id, "user.update", "user", user.id, changes)
    db.commit()
    return _dump(user)
