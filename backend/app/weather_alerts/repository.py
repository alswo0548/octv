"""기상특보 Snapshot 저장과 CCTV 감시 모드 전환 Repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from .client import KmaWarningStatus


KST = ZoneInfo("Asia/Seoul")


# ============================================================
# CCTV 집중감시 트리거 정책
# ============================================================
#
# R = 호우
# W = 강풍
# T = 태풍
# O = 폭풍해일
# S = 대설
#
# 1 = 예비특보
# 2 = 주의보
# 3 = 경보
# ============================================================

MONITORING_TRIGGER_WARNING_CODES = {
    "R",
    "W",
    "T",
    "O",
    "S",
}

MONITORING_TRIGGER_LEVEL_CODES = {
    "2",
    "3",
}


# 기존 DB ACTIVE 행이 감시 트리거였는지 확인할 때 사용한다.
# 기상청 공식 표기에서는 O가 "해일"로 나타날 수도 있으므로
# "해일"과 "폭풍해일"을 모두 허용한다.
MONITORING_TRIGGER_ALERT_TYPES = {
    "호우",
    "강풍",
    "태풍",
    "해일",
    "폭풍해일",
    "대설",
}

MONITORING_TRIGGER_ALERT_LEVELS = {
    "주의보",
    "경보",
}


def _now_kst_naive() -> datetime:
    """
    TIMESTAMP WITHOUT TIME ZONE에 저장할 현재 KST 시각.
    """
    return datetime.now(KST).replace(
        tzinfo=None
    )


def is_monitoring_trigger(
    warning: KmaWarningStatus,
) -> bool:
    """
    해당 특보가 CCTV 집중감시 ALERT 전환 대상인지 판단한다.

    조건:
    ACTIVE
    + 호우 / 강풍 / 태풍 / 폭풍해일 / 대설
    + 주의보 / 경보
    """
    return (
        warning.active
        and warning.warning_code
        in MONITORING_TRIGGER_WARNING_CODES
        and warning.level_code
        in MONITORING_TRIGGER_LEVEL_CODES
    )


def _stored_alert_is_monitoring_trigger(
    row: Mapping,
) -> bool:
    """
    이미 DB에 저장된 기존 ACTIVE 특보가
    CCTV 감시 트리거였는지 판단한다.
    """
    return (
        str(row["alert_type"])
        in MONITORING_TRIGGER_ALERT_TYPES
        and str(row["alert_level"])
        in MONITORING_TRIGGER_ALERT_LEVELS
    )


def list_region_weather_mappings(
    connection,
) -> list[Mapping]:
    """
    OCTV 내부 region_code와
    기상청 특보구역 코드 배열을 조회한다.
    """
    query = """
        SELECT
            region_code,
            weather_region_code
        FROM region
        WHERE weather_region_code IS NOT NULL
          AND cardinality(
              weather_region_code
          ) > 0
        ORDER BY region_code;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def _build_weather_to_regions(
    region_rows: Sequence[Mapping],
) -> dict[str, set[str]]:
    """
    기상청 특보구역 코드
    -> OCTV 내부 region_code 역매핑.
    """
    result: dict[
        str,
        set[str],
    ] = {}

    for row in region_rows:
        region_code = str(
            row["region_code"]
        )

        weather_codes = (
            row.get(
                "weather_region_code"
            )
            or []
        )

        for weather_code in weather_codes:
            normalized_code = (
                str(weather_code)
                .strip()
            )

            if not normalized_code:
                continue

            result.setdefault(
                normalized_code,
                set(),
            ).add(
                region_code
            )

    return result


def _build_records(
    warnings: Sequence[
        KmaWarningStatus
    ],
    region_rows: Sequence[
        Mapping
    ],
    *,
    monitoring_triggers_only: bool,
) -> list[dict]:
    """
    기상청 특보를
    OCTV 내부 region_code 단위
    weather_alert record로 확장한다.
    """
    weather_to_regions = (
        _build_weather_to_regions(
            region_rows
        )
    )

    records_by_key: dict[
        tuple[str, str],
        dict,
    ] = {}

    for warning in warnings:
        # 해제된 특보는 현재 ACTIVE Snapshot에 포함하지 않는다.
        if not warning.active:
            continue

        if (
            monitoring_triggers_only
            and not is_monitoring_trigger(
                warning
            )
        ):
            continue

        matched_regions = (
            weather_to_regions.get(
                warning.weather_region_code,
                set(),
            )
        )

        for region_code in matched_regions:
            key = (
                warning.external_alert_id,
                region_code,
            )

            records_by_key[key] = {
                "external_alert_id":
                    warning.external_alert_id,
                "alert_type":
                    warning.warning_name,
                "alert_level":
                    warning.level_name,
                "title":
                    warning.title,
                "issued_at":
                    warning.issued_at,
                "region_code":
                    region_code,
            }

    return list(
        records_by_key.values()
    )


def build_alert_records(
    warnings: Sequence[
        KmaWarningStatus
    ],
    region_rows: Sequence[
        Mapping
    ],
) -> list[dict]:
    """
    weather_alerts 테이블에 기록할
    모든 현재 ACTIVE 특보를 만든다.

    CCTV 감시 강화 대상이 아닌
    폭염 등의 특보도 DB 기록 자체는 유지한다.
    """
    return _build_records(
        warnings=warnings,
        region_rows=region_rows,
        monitoring_triggers_only=False,
    )


def build_monitoring_trigger_records(
    warnings: Sequence[
        KmaWarningStatus
    ],
    region_rows: Sequence[
        Mapping
    ],
) -> list[dict]:
    """
    CCTV ALERT 전환에 사용할
    현재 ACTIVE 특보만 만든다.

    종류:
    - 호우
    - 강풍
    - 태풍
    - 폭풍해일
    - 대설

    단계:
    - 주의보
    - 경보
    """
    return _build_records(
        warnings=warnings,
        region_rows=region_rows,
        monitoring_triggers_only=True,
    )


def _upsert_active_alerts(
    connection,
    records: Sequence[
        Mapping
    ],
) -> None:
    """
    현재 ACTIVE 특보를
    weather_alerts에 저장/갱신한다.
    """
    if not records:
        return

    query = """
        INSERT INTO weather_alerts (
            external_alert_id,
            alert_type,
            alert_level,
            title,
            issued_at,
            ended_at,
            status,
            region_code
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            NULL,
            'ACTIVE'::weather_status_enum,
            %s
        )
        ON CONFLICT (
            external_alert_id,
            region_code
        )
        DO UPDATE SET
            alert_type =
                EXCLUDED.alert_type,
            alert_level =
                EXCLUDED.alert_level,
            title =
                EXCLUDED.title,
            issued_at =
                EXCLUDED.issued_at,
            ended_at = NULL,
            status =
                'ACTIVE'
                ::weather_status_enum;
    """

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            [
                (
                    record[
                        "external_alert_id"
                    ],
                    record[
                        "alert_type"
                    ],
                    record[
                        "alert_level"
                    ],
                    record[
                        "title"
                    ],
                    record[
                        "issued_at"
                    ],
                    record[
                        "region_code"
                    ],
                )
                for record
                in records
            ],
        )


def _list_active_alert_rows(
    connection,
) -> list[Mapping]:
    """
    DB에서 현재 ACTIVE인
    기상특보를 조회한다.
    """
    query = """
        SELECT
            external_alert_id,
            region_code,
            alert_type,
            alert_level
        FROM weather_alerts
        WHERE status =
            'ACTIVE'
            ::weather_status_enum;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def _end_stale_alerts(
    connection,
    stale_keys: Sequence[
        tuple[str, str]
    ],
    ended_at: datetime,
) -> None:
    """
    이전에는 ACTIVE였지만
    현재 Snapshot에서 사라진 특보를
    ENDED로 변경한다.
    """
    if not stale_keys:
        return

    query = """
        UPDATE weather_alerts
        SET
            status =
                'ENDED'
                ::weather_status_enum,
            ended_at = %s
        WHERE external_alert_id = %s
          AND region_code = %s
          AND status =
              'ACTIVE'
              ::weather_status_enum;
    """

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            [
                (
                    ended_at,
                    external_alert_id,
                    region_code,
                )
                for (
                    external_alert_id,
                    region_code,
                )
                in stale_keys
            ],
        )


def _set_alert_mode(
    connection,
    region_codes: set[str],
) -> int:
    """
    MVP에서는 감시 강화 대상 특보 지역 전체에서
    집중감시 슬롯을 1대만 사용한다.

    이미 해당 특보 지역에서 ALERT 또는 VERIFY 중인
    CCTV가 있으면 새 ALERT CCTV를 추가하지 않는다.

    VERIFY는 Incident Runtime이 ALERT에서
    일시적으로 전환할 수 있는 상태이므로,
    Scheduler 입장에서는 기존 집중감시 슬롯이
    계속 사용 중인 것으로 취급한다.

    ALERT / VERIFY CCTV가 없으면:
    1. OFF CCTV 우선
    2. 없으면 BASE / POST_ALERT CCTV
    순서로 1대를 선택한다.

    Scheduler는 VERIFY 자체를 변경하지 않는다.
    """

    if not region_codes:
        return 0

    query = """
        WITH existing_focus_slot AS (
            SELECT id
            FROM cctvs
            WHERE region_code =
                  ANY(
                      %s::varchar[]
                  )
              AND provider = 'UTIC'
              AND is_monitored = TRUE
              AND monitored_mode IN (
                  'ALERT'
                  ::monitored_mode_enum,
                  'VERIFY'
                  ::monitored_mode_enum
              )
            ORDER BY
                CASE
                    WHEN monitored_mode =
                        'ALERT'
                        ::monitored_mode_enum
                    THEN 0
                    ELSE 1
                END,
                id
            LIMIT 1
        ),

        candidate AS (
            SELECT id
            FROM cctvs
            WHERE region_code =
                  ANY(
                      %s::varchar[]
                  )
              AND provider = 'UTIC'
              AND external_cctv_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM existing_focus_slot
              )
              AND (
                  (
                      is_monitored = FALSE
                      AND monitored_mode =
                          'OFF'
                          ::monitored_mode_enum
                  )
                  OR
                  (
                      is_monitored = TRUE
                      AND monitored_mode IN (
                          'BASE'
                          ::monitored_mode_enum,
                          'POST_ALERT'
                          ::monitored_mode_enum
                      )
                  )
              )
            ORDER BY
                CASE
                    WHEN (
                        is_monitored = FALSE
                        AND monitored_mode =
                            'OFF'
                            ::monitored_mode_enum
                    )
                    THEN 0
                    ELSE 1
                END,
                id
            LIMIT 1
        )

        UPDATE cctvs
        SET
            is_monitored = TRUE,
            monitored_mode =
                'ALERT'
                ::monitored_mode_enum
        WHERE id = (
            SELECT id
            FROM candidate
        );
    """

    sorted_region_codes = sorted(
        region_codes
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                sorted_region_codes,
                sorted_region_codes,
            ),
        )

        return cursor.rowcount


def _set_post_alert_mode(
    connection,
    region_codes: set[str],
) -> int:
    """
    감시 강화 대상 특보가 모두 끝난
    지역의 CCTV를:

    true + ALERT
        -> true + POST_ALERT

    로 변경한다.

    POST_ALERT 이후 감시 종료는
    관리자가 수동으로 수행한다.
    """
    if not region_codes:
        return 0

    query = """
        UPDATE cctvs
        SET monitored_mode =
            'POST_ALERT'
            ::monitored_mode_enum
        WHERE is_monitored = TRUE
          AND region_code =
              ANY(
                  %s::varchar[]
              )
          AND monitored_mode =
              'ALERT'
              ::monitored_mode_enum;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                sorted(
                    region_codes
                ),
            ),
        )

        return cursor.rowcount


def synchronize_weather_alerts(
    connection,
    warnings: Sequence[
        KmaWarningStatus
    ],
) -> dict[
    str,
    int,
]:
    """
    현재 기상특보 Snapshot을
    DB와 CCTV 감시 상태에 반영한다.

    weather_alerts:
        모든 현재 ACTIVE 특보 기록.

    CCTV 집중감시 대상:
        호우 / 강풍 / 태풍 / 폭풍해일 / 대설
        +
        주의보 / 경보

    상태 전환:

        false + OFF
            -> 대상 특보 발생
            -> true + ALERT

        true + BASE
            -> 대상 특보 발생
            -> true + ALERT

        true + POST_ALERT
            -> 대상 특보 재발생
            -> true + ALERT

        true + ALERT
            -> Incident 후보 검증
            -> true + VERIFY
            -> 집중감시 슬롯 유지

        true + ALERT
            -> 해당 지역 대상 특보 모두 종료
            -> true + POST_ALERT

    POST_ALERT 이후 감시 종료:
        관리자 수동
        -> false + OFF

    VERIFY는 Scheduler가 변경하지 않는다.
    """
    region_rows = (
        list_region_weather_mappings(
            connection
        )
    )

    if not region_rows:
        raise RuntimeError(
            "region.weather_region_code "
            "매핑이 없습니다. "
            "기상특보 Scheduler를 "
            "실행할 수 없습니다."
        )

    # ========================================================
    # 모든 ACTIVE 특보
    # ========================================================

    all_active_records = (
        build_alert_records(
            warnings=warnings,
            region_rows=region_rows,
        )
    )

    # ========================================================
    # CCTV 감시 강화용 ACTIVE 특보
    # ========================================================

    trigger_records = (
        build_monitoring_trigger_records(
            warnings=warnings,
            region_rows=region_rows,
        )
    )

    current_keys = {
        (
            str(
                record[
                    "external_alert_id"
                ]
            ),
            str(
                record[
                    "region_code"
                ]
            ),
        )
        for record
        in all_active_records
    }

    active_trigger_region_codes = {
        str(
            record[
                "region_code"
            ]
        )
        for record
        in trigger_records
    }

    # ========================================================
    # DB의 직전 ACTIVE Snapshot
    # ========================================================

    previous_active_rows = (
        _list_active_alert_rows(
            connection
        )
    )

    previous_keys = {
        (
            str(
                row[
                    "external_alert_id"
                ]
            ),
            str(
                row[
                    "region_code"
                ]
            ),
        )
        for row
        in previous_active_rows
    }

    stale_keys = (
        previous_keys
        - current_keys
    )

    # ========================================================
    # 종료되는 특보 중
    # CCTV 감시 강화 트리거였던 지역
    # ========================================================

    stale_trigger_region_codes = {
        str(
            row[
                "region_code"
            ]
        )
        for row
        in previous_active_rows
        if (
            (
                str(
                    row[
                        "external_alert_id"
                    ]
                ),
                str(
                    row[
                        "region_code"
                    ]
                ),
            )
            in stale_keys
            and
            _stored_alert_is_monitoring_trigger(
                row
            )
        )
    }

    # 같은 지역에서:
    #
    # 호우는 종료
    # 태풍은 아직 ACTIVE
    #
    # 같은 상황이면 POST_ALERT로 내려가면 안 된다.
    post_alert_region_codes = (
        stale_trigger_region_codes
        - active_trigger_region_codes
    )

    # ========================================================
    # 1. 현재 ACTIVE 특보 DB 저장
    # ========================================================

    _upsert_active_alerts(
        connection,
        all_active_records,
    )

    # ========================================================
    # 2. 사라진 기존 ACTIVE 특보 종료
    # ========================================================

    _end_stale_alerts(
        connection,
        stale_keys=sorted(
            stale_keys
        ),
        ended_at=(
            _now_kst_naive()
        ),
    )

    # ========================================================
    # 3. CCTV 감시 상태 반영
    # ========================================================

    alert_mode_updates = (
        _set_alert_mode(
            connection,
            active_trigger_region_codes,
        )
    )

    post_alert_mode_updates = (
        _set_post_alert_mode(
            connection,
            post_alert_region_codes,
        )
    )

    return {
        "api_warning_count":
            len(
                warnings
            ),

        "active_alert_row_count":
            len(
                all_active_records
            ),

        "monitoring_trigger_alert_row_count":
            len(
                trigger_records
            ),

        "ended_alert_row_count":
            len(
                stale_keys
            ),

        "alert_region_count":
            len(
                active_trigger_region_codes
            ),

        "post_alert_region_count":
            len(
                post_alert_region_codes
            ),

        "cctv_to_alert_count":
            alert_mode_updates,

        "cctv_to_post_alert_count":
            post_alert_mode_updates,
    }