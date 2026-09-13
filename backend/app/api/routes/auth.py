"""Auth routes: bootstrap wizard, login, me, status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import get_current_user
from ...models import Organization, User
from ...schemas import BootstrapIn, AuthStatus, LoginIn, TokenOut, UserOut
from ...security import create_access_token, hash_password, verify_password
from ...services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatus)
def status_(db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(User.id)))
    return {"needs_bootstrap": (count or 0) == 0}


@router.post("/bootstrap", response_model=TokenOut)
def bootstrap(body: BootstrapIn, db: Session = Depends(get_db)):
    """First-run initialization wizard: create organization + admin."""
    count = db.scalar(select(func.count(User.id))) or 0
    if count > 0:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "already_initialized",
                                    "message": "系统已初始化，请直接登录"})
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "email_taken", "message": "该邮箱已注册"})
    org = Organization(name=body.org_name)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=body.email.lower(), name=body.name,
                password_hash=hash_password(body.password), role="owner")
    db.add(user)
    db.commit()
    audit(db, org.id, user.id, "auth.bootstrap", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, org.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "bad_credentials", "message": "邮箱或密码错误"})
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail={"code": "inactive", "message": "账号已停用"})
    audit(db, user.org_id, user.id, "auth.login", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.org_id),
                    user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
