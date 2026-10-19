"""
추가 지원요청 조회·등록 API의 HTTP 진입점.

주요 기능
1. 기존 JWT로 로그인 사용자 확인
2. 사건 ID 및 지원요청 입력값 검증
3. Service에 사용자 정보 전달
4. 조회·저장 결과 반환
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from ..dependencies import get_current_user
from . import schemas, service

router = APIRouter(prefix="/support-requests", tags=["추가 지원요청"])

IncidentId = Annotated[int, Path(gt=0, le=9223372036854775807)]
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get(
    "/incidents/{incident_id}",
    response_model=list[schemas.SupportRequestResponse],
    summary="사건별 추가 지원 요청 조회",
)
def list_support_requests(incident_id: IncidentId, user: CurrentUser):
    return service.list_support_requests(incident_id, user)


@router.post(
    "/incidents/{incident_id}",
    response_model=schemas.SupportRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="전달받은 사건에 추가 지원 요청 등록",
)
def create_support_request(
    incident_id: IncidentId, body: schemas.SupportRequestCreate, user: CurrentUser
):
    return service.create_support_request(incident_id, body, user)
