"""실행: python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000"""

import os
from threading import Thread

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import (
    cors_allowed_origins,
    load_environment,
)


# ============================================================
# Environment
# ============================================================

# 다른 API 모듈을 가져오기 전에
# backend/.env를 먼저 읽습니다.
load_environment()


# ============================================================
# Routers / modules
# ============================================================

from .errors import FeatureNotImplemented

from .auth.router import (
    router as auth_router,
)

from .cctvs.router import (
    router as cctvs_router,
)

from .cctvs import (
    streaming as cctv_streaming,
)

from .incidents.router import (
    router as incidents_router,
)

from .agencies.router import (
    router as agencies_router,
)

from .routes.router import (
    router as routes_router,
)

from .notifications.router import (
    router as notifications_router,
)

from .support_requests.router import (
    router as support_requests_router,
)

from .settings.router import (
    router as settings_router,
)

from .stats.router import (
    router as stats_router,
)

from .dashboard.router import (
    router as dashboard_router,
)


# ============================================================
# FastAPI
# ============================================================

app = FastAPI(
    title="OCTV 개발용 API 골격",
    version="0.1.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=False,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
    ],
)


# ============================================================
# CCTV Stream Prewarm
# ============================================================


def _stream_prewarm_enabled() -> bool:
    """
    감시 중 CCTV의 MediaMTX stream prewarm 사용 여부.
    """

    return (
        os.getenv(
            "OCTV_STREAM_PREWARM_ENABLED",
            "0",
        ).strip()
        == "1"
    )


def _run_stream_prewarm() -> None:
    """
    현재 감시 중 CCTV를 MediaMTX에 미리 연결한다.

    FastAPI startup 자체를 막지 않도록
    별도 daemon thread에서 실행한다.
    """

    try:
        result = cctv_streaming.prewarm_monitored_cctv_streams()

        print(
            "[CCTV STREAM PREWARM] "
            "startup 완료 "
            f"/ total={result['total']} "
            f"/ success={result['success']} "
            f"/ failed={result['failed']}"
        )

    except Exception as exc:
        print(
            f"[CCTV STREAM PREWARM WARNING] startup 실패 / type={type(exc).__name__} / error={exc}"
        )


@app.on_event("startup")
def start_stream_prewarm() -> None:
    """
    FastAPI 시작 시 현재 is_monitored=TRUE인
    CCTV Stream을 미리 준비한다.
    """

    if not _stream_prewarm_enabled():
        print("[CCTV STREAM PREWARM] 비활성화")
        return

    print("[CCTV STREAM PREWARM] 백그라운드 시작")

    thread = Thread(
        target=_run_stream_prewarm,
        name="cctv-stream-prewarm",
        daemon=True,
    )

    thread.start()


# ============================================================
# Exception Handler
# ============================================================


@app.exception_handler(FeatureNotImplemented)
async def feature_not_implemented(
    request: Request,
    exc: FeatureNotImplemented,
):
    return JSONResponse(
        status_code=501,
        content={
            "detail": str(exc),
        },
    )


# ============================================================
# Health
# ============================================================


@app.get(
    "/health",
    tags=[
        "개발 환경",
    ],
)
def health():
    return {
        "status": "ok",
        "database": "not_checked",
        "business_api": "not_implemented",
    }


# ============================================================
# Routers
# ============================================================

app.include_router(
    auth_router,
    prefix="/api",
)

app.include_router(
    cctvs_router,
    prefix="/api",
)

app.include_router(
    incidents_router,
    prefix="/api",
)

app.include_router(
    agencies_router,
    prefix="/api",
)

app.include_router(
    routes_router,
    prefix="/api",
)

app.include_router(
    notifications_router,
    prefix="/api",
)

app.include_router(
    support_requests_router,
    prefix="/api",
)

app.include_router(
    settings_router,
    prefix="/api",
)

app.include_router(
    stats_router,
    prefix="/api",
)

app.include_router(
    dashboard_router,
    prefix="/api",
)
