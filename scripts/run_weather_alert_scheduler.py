"""OCTV 기상특보 Scheduler 실행 진입점."""

from __future__ import annotations

import argparse

from backend.app.db.session import (
    get_connection,
)
from backend.app.weather_alerts.client import (
    fetch_current_warnings,
)
from backend.app.weather_alerts.repository import (
    synchronize_weather_alerts,
)
from backend.app.weather_alerts.scheduler import (
    WeatherAlertScheduler,
)


DEFAULT_POLL_INTERVAL_SEC = 60.0


def sync_snapshot(
    warnings,
):
    """
    한 번의 기상특보 Snapshot을
    하나의 DB transaction으로 반영한다.
    """

    with get_connection() as connection:
        result = synchronize_weather_alerts(
            connection=connection,
            warnings=warnings,
        )
    # commit 이후에만 큐 발행 (Scheduler 자동 활성화 CCTV 포함).
    # 매핑 큐 장애는 특보 저장·감시 정책을 중단시키지 않는다.
    if result.get("cctv_to_alert_count", 0):
        from backend.app.integrations.cctv_mapping import auto_mapping_enabled
        if auto_mapping_enabled():
            try:
                from backend.app.workers import prewarm_all_context_mappings
                prewarm_all_context_mappings.apply_async()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "특보 CCTV 매핑 등록 실패: type=%s", type(exc).__name__
                )
    return result


def build_scheduler(
    poll_interval_sec: float,
) -> WeatherAlertScheduler:
    return WeatherAlertScheduler(
        fetch_current=(
            fetch_current_warnings
        ),
        sync_snapshot=(
            sync_snapshot
        ),
        poll_interval_sec=(
            poll_interval_sec
        ),
    )


def main() -> int:
    parser = (
        argparse.ArgumentParser(
            description=__doc__
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "기상특보를 한 번만 "
            "조회·동기화하고 종료"
        ),
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=(
            DEFAULT_POLL_INTERVAL_SEC
        ),
        help=(
            "연속 실행 시 조회 주기(초). "
            "기본값: 60"
        ),
    )

    args = parser.parse_args()

    scheduler = (
        build_scheduler(
            poll_interval_sec=(
                args.poll_interval
            )
        )
    )

    if args.once:
        result = (
            scheduler.run_once()
        )

        print(
            "[WEATHER ALERT SCHEDULER] "
            "1회 동기화 완료"
        )

        for (
            key,
            value,
        ) in result.items():
            print(
                f"  {key}: {value}"
            )

        return 0

    try:
        scheduler.run()

    except KeyboardInterrupt:
        print()

        print(
            "[WEATHER ALERT SCHEDULER] "
            "Ctrl+C 수신"
        )

        scheduler.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )