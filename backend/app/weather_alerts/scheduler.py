"""기상특보 Snapshot을 주기적으로 동기화하는 독립 Scheduler."""

from __future__ import annotations

from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from threading import Event

from .client import (
    KmaWarningStatus,
)


class WeatherAlertScheduler:
    """
    FastAPI와 독립적으로 실행되는
    기상특보 Scheduler.
    """

    def __init__(
        self,
        fetch_current: Callable[
            [],
            Sequence[
                KmaWarningStatus
            ],
        ],
        sync_snapshot: Callable[
            [
                Sequence[
                    KmaWarningStatus
                ]
            ],
            Mapping[
                str,
                int,
            ],
        ],
        poll_interval_sec: float = 60.0,
    ) -> None:
        if poll_interval_sec <= 0:
            raise ValueError(
                "poll_interval_sec은 "
                "0보다 커야 합니다."
            )

        self._fetch_current = (
            fetch_current
        )

        self._sync_snapshot = (
            sync_snapshot
        )

        self._poll_interval_sec = (
            poll_interval_sec
        )

        self._stop_event = Event()

    def stop(
        self,
    ) -> None:
        """
        Scheduler 종료 요청.
        """

        self._stop_event.set()

    def run_once(
        self,
    ) -> Mapping[
        str,
        int,
    ]:
        """
        기상특보 조회와 DB 동기화를
        한 번 수행한다.
        """

        warnings = list(
            self._fetch_current()
        )

        return (
            self._sync_snapshot(
                warnings
            )
        )

    def run(
        self,
    ) -> None:
        """
        stop()이 호출될 때까지
        일정 주기로 계속 실행한다.
        """

        print(
            "[WEATHER ALERT SCHEDULER] "
            "시작 "
            f"/ poll="
            f"{self._poll_interval_sec:.1f}초"
        )

        try:
            while (
                not
                self._stop_event.is_set()
            ):
                try:
                    result = (
                        self.run_once()
                    )

                    print(
                        "[WEATHER ALERT SCHEDULER] "
                        "동기화 완료 "
                        f"/ api="
                        f"{result.get('api_warning_count', 0)} "
                        f"/ active_rows="
                        f"{result.get('active_alert_row_count', 0)} "
                        f"/ trigger_rows="
                        f"{result.get('monitoring_trigger_alert_row_count', 0)} "
                        f"/ ended_rows="
                        f"{result.get('ended_alert_row_count', 0)} "
                        f"/ to_alert="
                        f"{result.get('cctv_to_alert_count', 0)} "
                        f"/ to_post_alert="
                        f"{result.get('cctv_to_post_alert_count', 0)}"
                    )

                except Exception as exc:
                    # API 키 등이
                    # URL / 예외 문자열에 포함될 수 있으므로
                    # 원문 예외는 그대로 출력하지 않는다.
                    print(
                        "[WEATHER ALERT SCHEDULER ERROR] "
                        f"{type(exc).__name__}"
                    )

                self._stop_event.wait(
                    self._poll_interval_sec
                )

        finally:
            print(
                "[WEATHER ALERT SCHEDULER] "
                "종료"
            )