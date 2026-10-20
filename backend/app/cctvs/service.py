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

import requests
from fastapi import HTTPException

from ..db.session import get_connection
from . import (
    reconnect_signal,
    repository,
    schemas,
    streaming,
)


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


def prepare_stream(
    cctv_id: int,
) -> schemas.CctvStreamResponse:
    """
    W04 실시간 CCTV 영상을 준비한다.

    조건:
    - CCTV가 존재해야 한다.
    - provider가 UTIC이어야 한다.
    - is_monitored = TRUE이어야 한다.

    동작:
    - 최신 UTIC Stream URL 조회
    - MediaMTX source 형식 변환
    - MediaMTX path 생성 / 갱신
    - WebRTC 주소 반환
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

    if not bool(
        row["is_monitored"]
    ):

        raise HTTPException(
            status_code=409,
            detail=(
                "현재 감시 중인 CCTV가 "
                "아닙니다."
            ),
        )

    if str(
        row["provider"]
    ).upper() != "UTIC":

        raise HTTPException(
            status_code=409,
            detail=(
                "현재 실시간 스트리밍을 "
                "지원하지 않는 CCTV입니다."
            ),
        )

    try:

        result = (
            streaming.prepare_cctv_stream(
                cctv_id=cctv_id,
                external_cctv_id=str(
                    row[
                        "external_cctv_id"
                    ]
                ),
            )
        )

    except (
        requests.RequestException,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:

        print(
            "[CCTV STREAM ERROR] "
            f"cctv_id={cctv_id} "
            f"/ error={exc}"
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "CCTV 실시간 영상을 "
                "준비하지 못했습니다."
            ),
        ) from exc

    return schemas.CctvStreamResponse(
        **result
    )


def request_reconnect(
    cctv_id: int,
) -> schemas.CctvReconnectResponse:
    """
    관리자가 특정 CCTV의 수동 재연결을 요청한다.

    실제 영상 연결을 FastAPI 프로세스에서
    직접 다시 여는 것이 아니다.

    PostgreSQL NOTIFY를 통해
    24시간 실행 중인 CCTV Runtime에
    재연결 요청만 전달한다.

    실제 connection_status 변경은
    CaptureWorker가 수행한다.
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

        if not bool(
            row["is_monitored"]
        ):

            raise HTTPException(
                status_code=409,
                detail=(
                    "현재 감시 중인 CCTV가 "
                    "아니므로 재연결할 수 없습니다."
                ),
            )

        if str(
            row["provider"]
        ).upper() != "UTIC":

            raise HTTPException(
                status_code=409,
                detail=(
                    "현재 수동 재연결을 지원하지 "
                    "않는 CCTV입니다."
                ),
            )

        reconnect_signal.publish_reconnect_request(
            connection,
            cctv_id,
        )

    return schemas.CctvReconnectResponse(
        cctv_id=cctv_id,
        status="ACCEPTED",
    )


def change_monitoring(
    cctv_id: int,
    body: schemas.MonitoringRequest,
) -> schemas.CctvResponse:
    """
    관리자 CCTV 감시 ON/OFF.

    OFF:
        BASE / POST_ALERT
        -> false + OFF

        ALERT / VERIFY
        -> 409 Conflict

    ON:
        OFF
        -> true + BASE

        이미 감시 중인 CCTV
        -> 현재 monitored_mode 유지

    POST_ALERT 상태에서 관리자가
    감시 종료 버튼을 누르는 경우도
    enabled=False로 처리한다.

    감시 OFF가 되면 해당 CCTV의
    MediaMTX path도 정리한다.
    """

    with get_connection() as connection:

        try:
            row = (
                repository.update_monitoring(
                    connection,
                    cctv_id=cctv_id,
                    enabled=body.enabled,
                )
            )

        except (
            repository
            .MonitoringChangeBlockedError
        ) as exc:

            if (
                exc.monitored_mode
                == "ALERT"
            ):

                detail = (
                    "기상특보 감시 중인 CCTV는 "
                    "수동으로 감시를 종료할 수 없습니다."
                )

            else:

                detail = (
                    "위험상황 검증 중인 CCTV는 "
                    "수동으로 감시를 종료할 수 없습니다."
                )

            raise HTTPException(
                status_code=409,
                detail=detail,
            ) from exc

        if row is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    "CCTV를 찾을 수 없습니다."
                ),
            )

        response = (
            _to_cctv_response(
                row
            )
        )

    # DB 상태 변경은 이미 완료된 뒤다.
    #
    # MediaMTX 장애 때문에
    # CCTV 감시 OFF 자체가 실패하면 안 되므로
    # remove_cctv_stream() 내부에서
    # 삭제 실패는 warning만 남긴다.
    if not body.enabled:

        streaming.remove_cctv_stream(
            cctv_id
        )

    return response