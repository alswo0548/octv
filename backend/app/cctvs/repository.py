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


class MonitoringChangeBlockedError(
    RuntimeError
):
    """
    현재 CCTV 감시 상태 때문에
    관리자 수동 ON/OFF 변경을 허용할 수 없는 경우.
    """

    def __init__(
        self,
        monitored_mode: str,
    ) -> None:

        self.monitored_mode = (
            str(
                monitored_mode
            ).upper()
        )

        super().__init__(
            "현재 감시 상태에서는 "
            "관리자 수동 감시 변경을 "
            "허용할 수 없습니다. "
            f"mode={self.monitored_mode}"
        )


def update_monitoring(
    connection,
    cctv_id: int,
    enabled: bool,
):
    """
    관리자 CCTV 감시 ON/OFF 변경.

    ON:
        OFF
        -> BASE

        이미 감시 중인
        BASE / ALERT / VERIFY / POST_ALERT
        -> 현재 mode 유지

    OFF:
        BASE / POST_ALERT
        -> OFF

        ALERT / VERIFY
        -> 관리자 수동 종료 차단

        OFF
        -> OFF 유지

    SELECT ... FOR UPDATE로 현재 CCTV 행을 잠근 뒤
    상태를 판단하므로 상태 확인과 UPDATE 사이의
    경쟁 조건을 방지한다.
    """

    # ========================================================
    # 현재 감시 상태 Lock
    # ========================================================

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                id,
                is_monitored,
                monitored_mode::text
                    AS monitored_mode
            FROM cctvs
            WHERE id = %s
            FOR UPDATE;
            """,
            (
                cctv_id,
            ),
        )

        current = (
            cursor.fetchone()
        )

    if current is None:
        return None

    current_mode = str(
        current[
            "monitored_mode"
        ]
    ).upper()

    is_monitored = bool(
        current[
            "is_monitored"
        ]
    )

    # ========================================================
    # 관리자 ON
    # ========================================================

    if enabled:

        # 이미 정상적으로 감시 중이라면
        # ALERT / VERIFY / POST_ALERT 같은
        # 시스템 상태를 BASE로 덮어쓰지 않는다.
        if (
            is_monitored
            and current_mode != "OFF"
        ):

            return get_cctv(
                connection,
                cctv_id,
            )

        target_enabled = True
        target_mode = "BASE"

    # ========================================================
    # 관리자 OFF
    # ========================================================

    else:

        # 기상특보 감시 중이거나
        # 위험 후보 집중 검증 중에는
        # 관리자가 감시를 끌 수 없다.
        if current_mode in {
            "ALERT",
            "VERIFY",
        }:

            raise (
                MonitoringChangeBlockedError(
                    current_mode
                )
            )

        # 이미 OFF이면 idempotent.
        if (
            not is_monitored
            and current_mode == "OFF"
        ):

            return get_cctv(
                connection,
                cctv_id,
            )

        # BASE / POST_ALERT
        # -> OFF
        target_enabled = False
        target_mode = "OFF"

    # ========================================================
    # 상태 변경
    # ========================================================

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
                target_enabled,
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
# Incident VERIFY Runtime 상태 전환
# ============================================================


VERIFY_RESTORE_MODES = {
    "BASE",
    "ALERT",
    "POST_ALERT",
}


def enter_verify_mode(
    connection,
    cctv_id: int,
):
    """
    위험 후보가 발견된 CCTV를
    일시적인 VERIFY 모드로 전환한다.

    DB 구조를 변경하지 않는다.
    기존 cctvs.monitored_mode만 사용한다.

    정상 전환:

        BASE       -> VERIFY
        ALERT      -> VERIFY
        POST_ALERT -> VERIFY

    OFF CCTV는 VERIFY로 전환하지 않는다.

    반환:
        {
            "id": int,
            "changed": bool,
            "previous_mode": str | None,
            "monitored_mode": str,
        }
    """

    select_query = """
        SELECT
            id,
            is_monitored,
            monitored_mode::text
                AS monitored_mode
        FROM cctvs
        WHERE id = %s
        FOR UPDATE;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            select_query,
            (
                cctv_id,
            ),
        )

        current = (
            cursor.fetchone()
        )

        if current is None:

            raise LookupError(
                "CCTV를 찾을 수 없습니다. "
                f"cctv_id={cctv_id}"
            )

        current_mode = str(
            current[
                "monitored_mode"
            ]
        )

        is_monitored = bool(
            current[
                "is_monitored"
            ]
        )

        if (
            not is_monitored
            or current_mode == "OFF"
        ):

            return {
                "id":
                    cctv_id,

                "changed":
                    False,

                "previous_mode":
                    current_mode,

                "monitored_mode":
                    current_mode,
            }

        if current_mode == "VERIFY":

            return {
                "id":
                    cctv_id,

                "changed":
                    False,

                "previous_mode":
                    None,

                "monitored_mode":
                    "VERIFY",
            }

        if (
            current_mode
            not in VERIFY_RESTORE_MODES
        ):

            raise ValueError(
                "VERIFY로 전환할 수 없는 "
                "CCTV 감시 모드입니다. "
                f"mode={current_mode}"
            )

        cursor.execute(
            """
            UPDATE cctvs
            SET monitored_mode =
                'VERIFY'
                ::monitored_mode_enum
            WHERE id = %s
            RETURNING id;
            """,
            (
                cctv_id,
            ),
        )

    return {
        "id":
            cctv_id,

        "changed":
            True,

        "previous_mode":
            current_mode,

        "monitored_mode":
            "VERIFY",
    }


def restore_from_verify_mode(
    connection,
    cctv_id: int,
    restore_mode: str,
):
    """
    VERIFY가 끝난 CCTV를
    검증 전 감시 모드로 복귀한다.

    허용 복귀 모드:

        BASE
        ALERT
        POST_ALERT

    현재 DB 상태가 VERIFY일 때만 변경한다.

    따라서 VERIFY 동안 다른 로직이
    CCTV 상태를 이미 변경했다면
    그 상태를 덮어쓰지 않는다.
    """

    target_mode = str(
        restore_mode
    ).upper()

    if (
        target_mode
        not in VERIFY_RESTORE_MODES
    ):

        raise ValueError(
            "VERIFY 복귀 모드가 "
            "올바르지 않습니다. "
            f"mode={restore_mode}"
        )

    query = """
        UPDATE cctvs
        SET monitored_mode =
            %s::monitored_mode_enum
        WHERE id = %s
          AND is_monitored = TRUE
          AND monitored_mode =
              'VERIFY'
              ::monitored_mode_enum
        RETURNING
            id,
            monitored_mode::text
                AS monitored_mode;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (
                target_mode,
                cctv_id,
            ),
        )

        return cursor.fetchone()


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



def list_monitored_runtime_cctvs(
    connection,
    *,
    include_demo: bool = False,
):
    """
    CCTV Runtime에서 현재 Capture 대상 CCTV를 조회한다.

    기본:
    - UTIC

    Demo 활성화 시:
    - UTIC
    - DEMO

    조건:
    - is_monitored = TRUE
    """

    providers = [
        "UTIC",
    ]

    if include_demo:
        providers.append(
            "DEMO"
        )

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
        WHERE provider =
              ANY(
                  %s::varchar[]
              )
          AND is_monitored = TRUE
        ORDER BY id;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                providers,
            ),
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