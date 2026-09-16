"""Auth routes: bootstrap wizard, login, me, status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import get_current_user
from ...models import Organization, User
from ...schemas import BootstrapIn, AuthStatus, LoginIn, PasswordChangeIn, TokenOut, UserOut
from ...security import create_access_token, hash_password, verify_password
from ...services.audit import audit
from ...services.ratelimit import allow, reset

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


@router.post("/change-password")
def change_password(body: PasswordChangeIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """自助改密：验证旧密码；改完旧密码立即失效，已签发令牌按自然过期处理。"""
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail={"code": "bad_old_password", "message": "旧密码不正确"})
    if body.old_password == body.new_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "same_password", "message": "新密码不能与旧密码相同"})
    user.password_hash = hash_password(body.new_password)
    audit(db, user.org_id, user.id, "auth.change_password", "user", user.id)
    db.commit()
    return {"ok": True, "note": "密码已更新，下次登录使用新密码"}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    # 失败限速：同一邮箱 60 秒内错 5 次锁 1 分钟，成功登录即清零
    if not allow(f"login-fail:{email}", limit=5, window_seconds=60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={"code": "rate_limited",
                                    "message": "登录失败次数过多，请 1 分钟后再试"})
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "bad_credentials", "message": "邮箱或密码错误"})
    reset(f"login-fail:{email}")
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
