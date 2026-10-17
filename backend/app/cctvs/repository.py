"""CCTV 조회/저장 Repository."""

from datetime import datetime


# ============================================================
# WEB / API 조회
# ============================================================


def list_cctvs(
    connection,
    region_code: str | None = None,
):
    """
    CCTV 목록을 조회한다.

    region_code가 있으면
    해당 지역 CCTV만 조회한다.
    """

    query = """
        SELECT
            c.id,
            c.external_cctv_id,
            c.name,
            c.provider,
            c.address,
            c.latitude,
            c.longitude,
            c.is_monitored,
            c.connection_status,
            c.video_quality_status,
            c.analysis_status,
            c.last_frame_at,
            c.region_code,
            c.monitored_mode,
            r.sido_name,
            r.sigungu_name
        FROM cctvs AS c
        LEFT JOIN region AS r
          ON r.region_code = c.region_code
    """

    params = []

    if region_code is not None:
        query += """
        WHERE c.region_code = %s
        """

        params.append(
            region_code
        )

    query += """
        ORDER BY
            c.is_monitored DESC,
            r.sido_name,
            r.sigungu_name,
            c.name,
            c.id;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            params,
        )

        return cursor.fetchall()


def get_cctv(
    connection,
    cctv_id: int,
):
    """
    CCTV 한 건을 상세 조회한다.
    """

    query = """
        SELECT
            c.id,
            c.external_cctv_id,
            c.name,
            c.provider,
            c.address,
            c.latitude,
            c.longitude,
            c.is_monitored,
            c.connection_status,
            c.video_quality_status,
            c.analysis_status,
            c.last_frame_at,
            c.region_code,
            c.monitored_mode,
            r.sido_name,
            r.sigungu_name
        FROM cctvs AS c
        LEFT JOIN region AS r
          ON r.region_code = c.region_code
        WHERE c.id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                cctv_id,
            ),
        )

        return cursor.fetchone()


def get_cctv_summary(
    connection,
    region_code: str | None = None,
):
    """
    W04 CCTV 모니터링 화면에 필요한
    CCTV 상태 요약 개수를 조회한다.

    region_code가 있으면
    해당 지역 기준으로 집계한다.
    """

    query = """
        SELECT
            COUNT(*)::int
                AS total_count,

            COUNT(*) FILTER (
                WHERE is_monitored = TRUE
            )::int
                AS monitored_count,

            COUNT(*) FILTER (
                WHERE connection_status =
                    'CONNECTED'
                    ::connection_status_enum
            )::int
                AS connected_count,

            COUNT(*) FILTER (
                WHERE connection_status =
                    'DISCONNECTED'
                    ::connection_status_enum
            )::int
                AS disconnected_count,

            COUNT(*) FILTER (
                WHERE connection_status =
                    'RECONNECTING'
                    ::connection_status_enum
            )::int
                AS reconnecting_count

        FROM cctvs
    """

    params = []

    if region_code is not None:
        query += """
        WHERE region_code = %s
        """

        params.append(
            region_code
        )

    query += ";"

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            params,
        )

        return cursor.fetchone()


def update_monitoring(
    connection,
    cctv_id: int,
    enabled: bool,
):
    """
    관리자가 CCTV 감시 ON/OFF를 변경한다.

    enabled = True
        -> is_monitored = TRUE
        -> monitored_mode = BASE

    enabled = False
        -> is_monitored = FALSE
        -> monitored_mode = OFF

    true + OFF 조합은 생성하지 않는다.

    Weather Alert Scheduler가 만드는
    ALERT / POST_ALERT 상태와 별개로,
    이 함수는 관리자 수동 감시 ON/OFF에 사용한다.
    """

    target_mode = (
        "BASE"
        if enabled
        else "OFF"
    )

    query = """
        UPDATE cctvs
        SET
            is_monitored = %s,
            monitored_mode =
                %s::monitored_mode_enum
        WHERE id = %s
        RETURNING id;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                enabled,
                target_mode,
                cctv_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        return None

    return get_cctv(
        connection,
        cctv_id,
    )


# ============================================================
# CCTV Runtime 조회
# ============================================================


def list_monitored_utic_cctvs(
    connection,
):
    """
    현재 Capture 대상인 UTIC CCTV를 조회한다.

    조건:
    - provider = UTIC
    - is_monitored = TRUE

    현재 정상 상태 조합:

    false + OFF
        -> CaptureWorker 대상 아님

    true + BASE
    true + ALERT
    true + VERIFY
    true + POST_ALERT
        -> CaptureWorker 대상

    true + OFF 조합은 정상 서비스 흐름에서
    생성하지 않는다.

    CaptureWorker 자체를 운영할지는
    is_monitored 값으로 판단한다.
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
        ORDER BY id;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query
        )

        return cursor.fetchall()


# ============================================================
# Runtime connection status
# ============================================================


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
            "지원하지 않는 CCTV 연결 상태입니다: "
            f"{status}"
        )

    query = """
        UPDATE cctvs
        SET connection_status =
            %s::connection_status_enum
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
            "CCTV를 찾을 수 없습니다. "
            f"cctv_id={cctv_id}"
        )

    return row


# ============================================================
# Runtime analysis status
# ============================================================


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
            "지원하지 않는 CCTV 분석 상태입니다: "
            f"{status}"
        )

    query = """
        UPDATE cctvs
        SET analysis_status =
            %s::analysis_status_enum
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
            "CCTV를 찾을 수 없습니다. "
            f"cctv_id={cctv_id}"
        )

    return row


# ============================================================
# Runtime last frame
# ============================================================


def update_last_frame_at(
    connection,
    cctv_id: int,
    captured_at: datetime,
):
    """
    CCTV의 마지막 프레임 수신 시각을 갱신한다.

    DB 컬럼이
    TIMESTAMP WITHOUT TIME ZONE이므로
    timezone-aware datetime은
    현재 지역 시각을 유지한 채
    tzinfo를 제거하여 저장한다.
    """

    db_timestamp = (
        captured_at.replace(
            tzinfo=None
        )
        if captured_at.tzinfo
        is not None
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
            "CCTV를 찾을 수 없습니다. "
            f"cctv_id={cctv_id}"
        )

    return row


# ============================================================
# Runtime video quality
# ============================================================


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

    if (
        status
        not in VIDEO_QUALITY_STATUSES
    ):
        raise ValueError(
            "지원하지 않는 영상 품질 상태입니다: "
            f"{status}"
        )

    query = """
        UPDATE cctvs
        SET video_quality_status =
            %s::video_quality_enum
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
            "CCTV를 찾을 수 없습니다. "
            f"cctv_id={cctv_id}"
        )

    return row


# ============================================================
# Runtime state 조회
# ============================================================


def get_cctv_runtime_state(
    connection,
    cctv_id: int,
):
    """
    CCTV Runtime/Health Check에 필요한
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
            (
                cctv_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            "CCTV를 찾을 수 없습니다. "
            f"cctv_id={cctv_id}"
        )

    return row