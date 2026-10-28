"""CCTV 조회·감시 상태 HTTP API."""

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)

from ..dependencies import (
    require_control_admin,
)
from . import (
    schemas,
    service,
)


router = APIRouter(
    prefix="/cctvs",
    tags=[
        "CCTV 조회·감시 상태"
    ],
)


@router.get(
    "",
    response_model=list[
        schemas.CctvResponse
    ],
    summary="CCTV 목록 조회",
)
def list_cctvs(
    region_code: str | None = Query(
        default=None,
        description=(
            "지역 코드 필터"
        ),
    ),
    _admin=Depends(
        require_control_admin
    ),
):
    """
    관제 관리자만 CCTV 목록을 조회할 수 있다.
    """

    return service.list_cctvs(
        region_code=region_code,
    )


@router.get(
    "/summary",
    response_model=(
        schemas.CctvSummaryResponse
    ),
    summary="CCTV 상태 요약 조회",
)
def get_cctv_summary(
    region_code: str | None = Query(
        default=None,
        description=(
            "지역 코드 필터"
        ),
    ),
    _admin=Depends(
        require_control_admin
    ),
):
    """
    관제 관리자만 CCTV 상태 요약을 조회할 수 있다.
    """

    return service.get_cctv_summary(
        region_code=region_code,
    )


@router.get(
    "/stream-access",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="관리자 실시간 CCTV WHEP 접근 확인",
)
def verify_stream_access(
    _admin=Depends(require_control_admin),
):
    """Caddy forward_auth 전용: 관리자 JWT·활성 계정을 확인한 뒤 본문 없이 허용."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{cctv_id}/stream",
    response_model=(
        schemas.CctvStreamResponse
    ),
    summary="CCTV 실시간 영상 준비",
)
def prepare_stream(
    cctv_id: int,
    _admin=Depends(
        require_control_admin
    ),
):
    """
    관제 관리자만 현재 감시 중인 CCTV의
    MediaMTX WebRTC 스트림을 준비할 수 있다.

    실제 UTIC 원본 Stream URL은
    클라이언트에 노출하지 않는다.
    """

    return service.prepare_stream(
        cctv_id
    )



@router.post(
    "/{cctv_id}/reconnect",
    response_model=(
        schemas.CctvReconnectResponse
    ),
    status_code=(
        status.HTTP_202_ACCEPTED
    ),
    summary="CCTV 수동 재연결 요청",
)
def request_reconnect(
    cctv_id: int,
    _admin=Depends(
        require_control_admin
    ),
):
    """
    관제 관리자가 특정 CCTV의
    수동 재연결을 요청한다.

    실제 재연결은 독립 실행 중인
    CCTV Runtime에서 수행한다.
    """

    return service.request_reconnect(
        cctv_id
    )



@router.get(
    "/{cctv_id}",
    response_model=(
        schemas.CctvResponse
    ),
    summary="CCTV 상세 조회",
)
def get_cctv(
    cctv_id: int,
    _admin=Depends(
        require_control_admin
    ),
):
    """
    관제 관리자만 CCTV 상세 정보를 조회할 수 있다.
    """

    return service.get_cctv(
        cctv_id
    )


@router.patch(
    "/{cctv_id}/monitoring",
    response_model=(
        schemas.CctvResponse
    ),
    summary="CCTV 감시 ON/OFF",
)
def change_monitoring(
    cctv_id: int,
    body: schemas.MonitoringRequest,
    _admin=Depends(
        require_control_admin
    ),
):
    """
    관제 관리자만 CCTV 감시 상태를 변경할 수 있다.
    """

    return service.change_monitoring(
        cctv_id,
        body,
    )