"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented
from datetime import datetime

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def list_cctvs(connection, region_code: str | None = None):
    # TODO: cctvs와 region 조회. 감시 상태와 연결 상태를 각각 반환.
    raise FeatureNotImplemented("cctvs.list_cctvs DB 쿼리 구현 예정")


def update_monitoring(connection, cctv_id: int, enabled: bool, mode: str | None):
    # TODO: 특보/권한을 서비스에서 확인한 후 기본 감시 대상 여부와 현재 모드의 의미를 구분해 저장. 동시 변경 충돌 고려.
    raise FeatureNotImplemented("cctvs.update_monitoring DB 쿼리 구현 예정")


def list_monitored_utic_cctvs(connection):
    """
    현재 감시 대상인 UTIC CCTV를 조회한다.

    조건:
    - provider = UTIC
    - is_monitored = TRUE
    - monitored_mode != OFF
    """

    query = """
        SELECT
            id,
            external_cctv_id,
            name,
            provider,
            address,
            latitude,
            longitude,
            stream_url,
            is_monitored,
            connection_status,
            video_quality_status,
            analysis_status,
            last_frame_at,
            region_code,
            monitored_mode
        FROM cctvs
        WHERE provider = 'UTIC'
          AND is_monitored = TRUE
          AND monitored_mode <> 'OFF'
        ORDER BY id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


CONNECTION_STATUSES = {
    "CONNECTED",
    "DISCONNECTED",
    "RECONNECTING",
}


def update_connection_status(
    connection,
    cctv_id: int,
    status: str,
):
    """
    CCTV의 현재 영상 연결 상태를 변경한다.

    status:
    - CONNECTED
    - DISCONNECTED
    - RECONNECTING
    """

    if status not in CONNECTION_STATUSES:
        raise ValueError(
            f"지원하지 않는 CCTV 연결 상태입니다: {status}"
        )

    query = """
        UPDATE cctvs
        SET connection_status = %s::connection_status_enum
        WHERE id = %s
        RETURNING
            id,
            external_cctv_id,
            connection_status;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                status,
                cctv_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"CCTV를 찾을 수 없습니다. cctv_id={cctv_id}"
        )

    return row


ANALYSIS_STATUSES = {
    "RUNNING",
    "STOPPED",
    "ERROR",
}


def update_analysis_status(
    connection,
    cctv_id: int,
    status: str,
):
    """
    CCTV의 현재 AI 분석 상태를 변경한다.

    status:
    - RUNNING
    - STOPPED
    - ERROR
    """

    if status not in ANALYSIS_STATUSES:
        raise ValueError(
            f"지원하지 않는 CCTV 분석 상태입니다: {status}"
        )

    query = """
        UPDATE cctvs
        SET analysis_status = %s::analysis_status_enum
        WHERE id = %s
        RETURNING
            id,
            external_cctv_id,
            analysis_status;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                status,
                cctv_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"CCTV를 찾을 수 없습니다. cctv_id={cctv_id}"
        )

    return row


def update_last_frame_at(
    connection,
    cctv_id: int,
    captured_at: datetime,
):
    """
    CCTV의 마지막 프레임 수신 시각을 갱신한다.

    DB 컬럼이 TIMESTAMP WITHOUT TIME ZONE이므로
    timezone-aware datetime은 현재 지역 시각을 유지한 채
    tzinfo를 제거하여 저장한다.
    """

    db_timestamp = (
        captured_at.replace(tzinfo=None)
        if captured_at.tzinfo is not None
        else captured_at
    )

    query = """
        UPDATE cctvs
        SET last_frame_at = %s
        WHERE id = %s
        RETURNING
            id,
            external_cctv_id,
            last_frame_at;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                db_timestamp,
                cctv_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"CCTV를 찾을 수 없습니다. cctv_id={cctv_id}"
        )

    return row


VIDEO_QUALITY_STATUSES = {
    "GOOD",
    "LOW",
    "UNAVAILABLE",
}


def update_video_quality_status(
    connection,
    cctv_id: int,
    status: str,
):
    """
    CCTV의 현재 영상 품질 상태를 변경한다.

    status:
    - GOOD
    - LOW
    - UNAVAILABLE
    """

    if status not in VIDEO_QUALITY_STATUSES:
        raise ValueError(
            f"지원하지 않는 영상 품질 상태입니다: {status}"
        )

    query = """
        UPDATE cctvs
        SET video_quality_status = %s::video_quality_enum
        WHERE id = %s
        RETURNING
            id,
            external_cctv_id,
            video_quality_status;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                status,
                cctv_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"CCTV를 찾을 수 없습니다. cctv_id={cctv_id}"
        )

    return row

def get_cctv_runtime_state(
    connection,
    cctv_id: int,
):
    """
    CCTV Health Check에 필요한
    현재 실행 상태를 조회한다.
    """

    query = """
        SELECT
            id,
            external_cctv_id,
            connection_status,
            video_quality_status,
            analysis_status,
            last_frame_at,
            monitored_mode
        FROM cctvs
        WHERE id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (cctv_id,),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"CCTV를 찾을 수 없습니다. cctv_id={cctv_id}"
        )

    return row