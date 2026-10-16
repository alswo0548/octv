"""
기관 목록 API와 기관 추천 조회·선택 전달 API를 기존 FastAPI 앱에 연결합니다.
Router는 WEB에서 들어오는 API 요청을 받아 적절한 Service 함수롤 전달하는 역할

파일 흐름
1. 회원가입용 GET /api/agencies는 인증 없이 기관 목록을 조회합니다.
2. 추천 조회·전달 API는 기존 JWT/require_control_admin으로 관제 관리자를 인증합니다.
3. URL·요청 데이터를 검증한 뒤 Service를 호출해 DB 작업 결과를 돌려줍니다.

주요 기능
- GET 추천·경로 후보 조회 / POST 기관 전달 및 DB 알림 생성
- 알림 조회·읽음 및 FCM 발송은 후속 범위.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ..dependencies import require_control_admin
from . import schemas, service

router = APIRouter(prefix="/agencies", tags=["기관 조회·추천·선택 전달"])


# URL에 포함된 사건 ID를 PostgreSQL BIGINT의 양의 정수 범위로 검사.
IncidentId = Annotated[int, Path(gt=0, le=9223372036854775807)]
# 기존 JWT 인증과 관제 관리자 권한 검사를 별도 로그인 코드를 만들지 않고 재사용.
AdminUser = Annotated[dict, Depends(require_control_admin)]


# 회원가입할 때 선택할 기관 목록을 반환
@router.get(
    "",
    response_model=list[schemas.AgencyResponse],
    summary="회원가입용 기관 목록 조회",
)
def list_agencies():
    return service.list_agencies()


# 인증된 관제 관리자에게 이미 저장된 기관 추천과 경로 후보를 WEB에 반환
@router.get(
    "/incidents/{incident_id}/recommendations",
    response_model=schemas.DeliveryCandidatesResponse,
    summary="기관 전달용 추천·경로 후보 조회",
)
def list_recommendations(incident_id: IncidentId, user: AdminUser):
    return service.list_recommendations(incident_id, user)


# 선택한 기관에 전달하고 DB 알림을 저장하며, 휴대폰 Push는 아직 발송하지 않습니다.
@router.post(
    "/incidents/{incident_id}/deliveries",
    response_model=schemas.DeliveryResponse,
    summary="선택 기관에 사건 전달 및 DB 알림 생성",
)
def deliver(incident_id: IncidentId, body: schemas.DeliveryRequest, user: AdminUser):
    return service.deliver(incident_id, body, user)
