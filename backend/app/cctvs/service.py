"""
CCTV 조회·감시 상태 Service.

관리자 수동 감시 정책:

enabled = True
    -> is_monitored = TRUE
    -> monitored_mode = BASE

enabled = False
    -> is_monitored = FALSE
    -> monitored_mode = OFF

Weather Alert Scheduler의
ALERT / POST_ALERT 상태 전환과
관리자 수동 감시 ON/OFF를 구분한다.
"""

from fastapi import HTTPException

from ..db.session import get_connection
from . import repository, schemas


def _to_cctv_response(
    row,
) -> schemas.CctvResponse:
    """
    DB row를 CCTV API 응답으로 변환한다.
    """

    return schemas.CctvResponse(
        id=row["id"],
        external_cctv_id=(
            row["external_cctv_id"]
        ),
        name=row["name"],
        provider=row["provider"],
        address=row["address"],
        latitude=float(
            row["latitude"]
        ),
        longitude=float(
            row["longitude"]
        ),
        is_monitored=bool(
            row["is_monitored"]
        ),
        connection_status=(
            row["connection_status"]
        ),
        video_quality_status=(
            row[
                "video_quality_status"
            ]
        ),
        analysis_status=(
            row["analysis_status"]
        ),
        last_frame_at=(
            row["last_frame_at"]
        ),
        region_code=(
            row["region_code"]
        ),
        sido_name=(
            row["sido_name"]
        ),
        sigungu_name=(
            row["sigungu_name"]
        ),
        monitored_mode=(
            row["monitored_mode"]
        ),
    )


def list_cctvs(
    region_code: str | None = None,
) -> list[
    schemas.CctvResponse
]:
    """
    CCTV 목록 조회.
    """

    with get_connection() as connection:
        rows = repository.list_cctvs(
            connection,
            region_code=region_code,
        )

    return [
        _to_cctv_response(
            row
        )
        for row in rows
    ]


def get_cctv(
    cctv_id: int,
) -> schemas.CctvResponse:
    """
    CCTV 상세 조회.
    """

    with get_connection() as connection:
        row = repository.get_cctv(
            connection,
            cctv_id,
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "CCTV를 찾을 수 없습니다."
            ),
        )

    return _to_cctv_response(
        row
    )


def get_cctv_summary(
    region_code: str | None = None,
) -> schemas.CctvSummaryResponse:
    """
    CCTV 상태 요약 조회.
    """

    with get_connection() as connection:
        row = (
            repository.get_cctv_summary(
                connection,
                region_code=(
                    region_code
                ),
            )
        )

    return schemas.CctvSummaryResponse(
        total_count=(
            row["total_count"]
        ),
        monitored_count=(
            row["monitored_count"]
        ),
        connected_count=(
            row["connected_count"]
        ),
        disconnected_count=(
            row[
                "disconnected_count"
            ]
        ),
        reconnecting_count=(
            row[
                "reconnecting_count"
            ]
        ),
    )


def change_monitoring(
    cctv_id: int,
    body: schemas.MonitoringRequest,
) -> schemas.CctvResponse:
    """
    관리자 CCTV 감시 ON/OFF.

    ON:
        false + OFF
        -> true + BASE

    OFF:
        BASE / ALERT / VERIFY / POST_ALERT
        -> false + OFF

    POST_ALERT 상태에서 관리자가
    감시 종료 버튼을 누르는 경우도
    enabled=False로 처리한다.
    """

    with get_connection() as connection:
        row = repository.update_monitoring(
            connection,
            cctv_id=cctv_id,
            enabled=body.enabled,
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "CCTV를 찾을 수 없습니다."
                ),
            )

    return _to_cctv_response(
        row
    )