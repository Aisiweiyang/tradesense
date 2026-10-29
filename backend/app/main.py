"""TradeSense FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8001
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api import api_router
from .config import settings
from .database import engine
from .models import Base

logger = logging.getLogger("tradesense")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # lightweight startup: ensure schema exists (Alembic is the source of truth
    # for upgrades; create_all keeps first-run one-click start working)
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        try:
            from .seed.run import ensure_seeded
            ensure_seeded()
        except Exception:  # noqa: BLE001 — demo data must never block startup
            logger.exception("demo seed failed (continuing anyway)")
    yield


app = FastAPI(
    title="TradeSense API",
    version="1.2.0",
    description="AI 外贸询盘、客户跟进、产品匹配与报价辅助平台 — 后端 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# unified error envelope: {error: {code, message, details}}
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "validation_error", "message": "请求参数校验失败",
                           "details": jsonable_errors(exc.errors())}})


def jsonable_errors(errors):
    out = []
    for e in errors:
        out.append({"loc": [str(x) for x in e.get("loc", [])],
                    "msg": e.get("msg", ""), "type": e.get("type", "")})
    return out


from fastapi import HTTPException  # noqa: E402


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        body = {"error": {**detail}}
    else:
        body = {"error": {"code": "http_error", "message": str(detail)}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={
        "error": {"code": "internal_error", "message": "服务器内部错误，请查看后端日志"}})


app.include_router(api_router)


@app.get("/api/health")
def health():
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    from .services.ai import get_ai
    ai = get_ai()
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "database": "ok" if db_ok else "error",
        "ai_provider": ai.name,
        "ai_available": ai.available(),
        "note": "AI 不可用时核心流程全部可用（确定性降级）",
    }
