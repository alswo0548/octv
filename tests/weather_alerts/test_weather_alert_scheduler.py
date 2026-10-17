"""기상특보 Parser / 정규화 / 감시 트리거 / 지역 매칭 / Scheduler 단위 테스트."""

from backend.app.weather_alerts.client import (
    parse_current_warnings,
)
from backend.app.weather_alerts.repository import (
    build_alert_records,
    build_monitoring_trigger_records,
    is_monitoring_trigger,
)
from backend.app.weather_alerts.scheduler import (
    WeatherAlertScheduler,
)


def main() -> None:
    print("=" * 70)
    print(
        "WEATHER ALERT SCHEDULER UNIT TEST"
    )
    print("=" * 70)

    # =====================================================
    # 1. 코드형 KMA 응답 Parser
    # =====================================================

    code_sample = """
#START7777
L1000000,서울특별시,L1010500,서울동남권,202610151000,202610151100,R,2,1
L1000000,서울특별시,L1010500,서울동남권,202610151010,202610151110,W,3,1
L2000000,경기도,L1020100,수원시,202610151020,202610151120,T,3,1
L1000000,서울특별시,L1010500,서울동남권,202610151030,202610151130,O,2,1
L1000000,서울특별시,L1010500,서울동남권,202610151040,202610151140,S,2,1
L1000000,서울특별시,L1010500,서울동남권,202610151050,202610151150,H,3,1
L1000000,서울특별시,L1010500,서울동남권,202610151100,202610151200,S,1,1
L1000000,서울특별시,L1010500,서울동남권,202610151110,202610151210,W,3,3
#7777END
"""

    warnings = (
        parse_current_warnings(
            code_sample
        )
    )

    if len(warnings) != 8:
        raise AssertionError(
            "KMA 특보 8행을 "
            "파싱해야 합니다."
        )

    if (
        warnings[0].warning_code
        != "R"
    ):
        raise AssertionError(
            "호우 코드 정규화 실패"
        )

    if (
        warnings[0].level_code
        != "2"
    ):
        raise AssertionError(
            "주의보 코드 정규화 실패"
        )

    if (
        warnings[-1].active
    ):
        raise AssertionError(
            "CMD=3 특보는 "
            "해제 상태여야 합니다."
        )

    print(
        "[PASS] 코드형 KMA Parser"
    )

    # =====================================================
    # 2. 실제 API와 같은 한글형 응답 정규화
    # =====================================================

    korean_sample = """
#START7777
S1000000,서해중부,S1252010,서해중부안쪽먼바다,202610151000,202610151100,풍랑,예비,발표
L1000000,수도권,L1010500,서울동남권,202610151010,202610151110,강풍,주의,발표
L1000000,수도권,L1010500,서울동남권,202610151020,202610151120,대설,경보,해제
#7777END
"""

    korean_warnings = (
        parse_current_warnings(
            korean_sample
        )
    )

    if (
        korean_warnings[0].warning_code
        != "V"
    ):
        raise AssertionError(
            "풍랑 -> V 정규화 실패"
        )

    if (
        korean_warnings[0].level_code
        != "1"
    ):
        raise AssertionError(
            "예비 -> 1 정규화 실패"
        )

    if (
        korean_warnings[1].warning_code
        != "W"
    ):
        raise AssertionError(
            "강풍 -> W 정규화 실패"
        )

    if (
        korean_warnings[1].level_code
        != "2"
    ):
        raise AssertionError(
            "주의 -> 2 정규화 실패"
        )

    if not is_monitoring_trigger(
        korean_warnings[1]
    ):
        raise AssertionError(
            "한글형 강풍주의보가 "
            "CCTV ALERT 대상으로 "
            "판정되어야 합니다."
        )

    if (
        korean_warnings[2].command_code
        != "3"
    ):
        raise AssertionError(
            "해제 -> 3 정규화 실패"
        )

    if (
        korean_warnings[2].active
    ):
        raise AssertionError(
            "한글형 해제 특보는 "
            "ACTIVE가 아니어야 합니다."
        )

    print(
        "[PASS] "
        "한글형 WRN/LVL/CMD "
        "내부 코드 정규화"
    )

    # =====================================================
    # 3. 빈 Snapshot
    # =====================================================

    empty = (
        parse_current_warnings(
            "#START7777\n"
            "#7777END\n"
        )
    )

    if empty != []:
        raise AssertionError(
            "유효한 빈 Snapshot은 "
            "[]여야 합니다."
        )

    print(
        "[PASS] 빈 특보 Snapshot"
    )

    # =====================================================
    # 4. CCTV 감시 강화 정책
    # =====================================================

    trigger_expectations = [
        (
            warnings[0],
            True,
            "호우 주의보",
        ),
        (
            warnings[1],
            True,
            "강풍 경보",
        ),
        (
            warnings[2],
            True,
            "태풍 경보",
        ),
        (
            warnings[3],
            True,
            "폭풍해일 주의보",
        ),
        (
            warnings[4],
            True,
            "대설 주의보",
        ),
        (
            warnings[5],
            False,
            "폭염 경보",
        ),
        (
            warnings[6],
            False,
            "대설 예비특보",
        ),
        (
            warnings[7],
            False,
            "해제된 강풍 경보",
        ),
    ]

    for (
        warning,
        expected,
        label,
    ) in trigger_expectations:
        actual = (
            is_monitoring_trigger(
                warning
            )
        )

        if actual != expected:
            raise AssertionError(
                "감시 트리거 판정 오류: "
                f"{label} "
                f"expected={expected}, "
                f"actual={actual}"
            )

    print(
        "[PASS] "
        "호우·강풍·태풍·폭풍해일·대설 "
        "감시 트리거 정책"
    )

    print(
        "[PASS] "
        "폭염 제외 / "
        "예비특보 제외 / "
        "해제특보 제외"
    )

    # =====================================================
    # 5. 기상특보 지역코드
    #    -> OCTV region_code
    # =====================================================

    region_rows = [
        {
            "region_code":
                "11680",

            "weather_region_code":
                [
                    "L1010100",
                    "L1010500",
                ],
        },

        {
            "region_code":
                "41110",

            "weather_region_code":
                [
                    "L1020100",
                ],
        },
    ]

    all_records = (
        build_alert_records(
            warnings=warnings,
            region_rows=(
                region_rows
            ),
        )
    )

    if len(all_records) != 7:
        raise AssertionError(
            "모든 ACTIVE 특보 "
            "7건이 DB 기록 대상이어야 합니다. "
            f"actual={len(all_records)}"
        )

    print(
        "[PASS] "
        "모든 ACTIVE 특보 "
        "DB 기록 대상 유지"
    )

    trigger_records = (
        build_monitoring_trigger_records(
            warnings=warnings,
            region_rows=(
                region_rows
            ),
        )
    )

    if len(trigger_records) != 5:
        raise AssertionError(
            "CCTV 집중감시 대상은 "
            "5건이어야 합니다. "
            f"actual={len(trigger_records)}"
        )

    trigger_titles = {
        record[
            "title"
        ]
        for record
        in trigger_records
    }

    expected_titles = {
        "호우 주의보",
        "강풍 경보",
        "태풍 경보",
        "폭풍해일 주의보",
        "대설 주의보",
    }

    if (
        trigger_titles
        != expected_titles
    ):
        raise AssertionError(
            "CCTV 집중감시 대상 특보가 "
            "예상과 다릅니다: "
            f"{trigger_titles}"
        )

    print(
        "[PASS] "
        "weather_region_code "
        "-> region_code 매칭"
    )

    print(
        "[PASS] "
        "대설 주의보 "
        "CCTV ALERT 대상 포함"
    )

    # =====================================================
    # 6. Scheduler run_once
    # =====================================================

    calls = {
        "fetch": 0,
        "sync": 0,
    }

    def fake_fetch():
        calls[
            "fetch"
        ] += 1

        return warnings

    def fake_sync(
        items,
    ):
        calls[
            "sync"
        ] += 1

        if (
            list(items)
            != warnings
        ):
            raise AssertionError(
                "Scheduler가 조회 결과를 "
                "그대로 sync에 "
                "전달해야 합니다."
            )

        return {
            "api_warning_count":
                len(
                    items
                ),
        }

    scheduler = (
        WeatherAlertScheduler(
            fetch_current=(
                fake_fetch
            ),
            sync_snapshot=(
                fake_sync
            ),
            poll_interval_sec=1.0,
        )
    )

    result = (
        scheduler.run_once()
    )

    if calls != {
        "fetch": 1,
        "sync": 1,
    }:
        raise AssertionError(
            "run_once는 fetch/sync를 "
            "각각 1회 실행해야 합니다."
        )

    if (
        result[
            "api_warning_count"
        ]
        != 8
    ):
        raise AssertionError(
            "Scheduler 결과가 "
            "올바르지 않습니다."
        )

    print(
        "[PASS] Scheduler run_once"
    )

    print()

    print(
        "[SUCCESS] "
        "Weather Alert Scheduler "
        "단위 테스트 정상"
    )


if __name__ == "__main__":
    main()