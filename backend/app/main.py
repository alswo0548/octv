"""실행: python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .errors import FeatureNotImplemented
from .auth.router import router as auth_router
from .cctvs.router import router as cctvs_router
from .incidents.router import router as incidents_router
from .agencies.router import router as agencies_router
from .routes.router import router as routes_router
from .notifications.router import router as notifications_router
from .support_requests.router import router as support_requests_router
from .settings.router import router as settings_router
from .stats.router import router as stats_router
from .dashboard.router import router as dashboard_router

app = FastAPI(title="OCTV 개발용 API 골격", version="0.1.0")


@app.exception_handler(FeatureNotImplemented)
async def feature_not_implemented(request: Request, exc: FeatureNotImplemented):
    return JSONResponse(status_code=501, content={"detail": str(exc)})


@app.get("/health", tags=["개발 환경"])
def health():
    # 서버 기동 확인만 합니다. DB/AI 연결 성공을 뜻하지 않습니다.
    return {
        "status": "ok",
        "database": "not_checked",
        "business_api": "not_implemented",
    }


app.include_router(auth_router, prefix="/api")
app.include_router(cctvs_router, prefix="/api")
app.include_router(incidents_router, prefix="/api")
app.include_router(agencies_router, prefix="/api")
app.include_router(routes_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(support_requests_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
