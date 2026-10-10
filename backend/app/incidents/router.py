"""사건 목록·상세 HTTP 진입점."""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Literal
from . import schemas, service
router = APIRouter(prefix="/incidents", tags=["사건 조회·상세"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.

@router.get("", response_model=schemas.IncidentPage, summary="사건 목록 조회")
def list_incidents(
    page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=100),
    status: Literal["DETECTED","CONFIRMED","SENT","RESOLVED","FALSE_POSITIVE"] | None = None,
    hazard_type: str | None = None, priority: Literal["P1","P2","P3"] | None = None,
    region_code: str | None = None, cctv_id: int | None = None,
    start: datetime | None = None, end: datetime | None = None,
    q: str | None = None, confirmed_only: bool = False, active_only: bool = False,
):
    filters = dict(status=status, hazard_type=hazard_type, priority=priority,
        region_code=region_code, cctv_id=cctv_id, q=q,
        confirmed_only=confirmed_only, active_only=active_only)
    for key, value in (("start", start), ("end", end)):
        if value is not None:
            try:
                filters[key] = service.utc_naive(value)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    return service.list_incidents(page, page_size, filters)

@router.get("/{incident_id}", response_model=schemas.IncidentResponse, summary="사건 상세 조회")
def get_incident(incident_id: int):
    return service.get_incident(incident_id)
