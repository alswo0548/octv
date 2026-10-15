"""실제 DB 상태를 SamplingPolicyMonitor에 연결하는 테스트."""

import time
from threading import Thread

from ai.detection.frame_sampler import FrameSampler
from ai.detection.sampling_monitor import SamplingPolicyMonitor

from backend.app.cctvs.repository import (
    get_cctv_runtime_state,
)
from backend.app.db.session import (
    get_connection,
)
from backend.app.settings.repository import (
    get_monitoring_settings,
)


CCTV_ID = 1


def main() -> None:

    print("=" * 70)
    print("SAMPLING POLICY MONITOR DB TEST")
    print("=" * 70)

    # =====================================================
    # DB Provider
    # =====================================================

    def state_provider() -> list[dict]:
        """
        실제 cctvs 테이블에서 현재 CCTV 상태를 읽는다.
        """

        with get_connection() as connection:

            state = get_cctv_runtime_state(
                connection=connection,
                cctv_id=CCTV_ID,
            )

        if state is None:
            raise RuntimeError(
                f"CCTV {CCTV_ID}를 찾을 수 없습니다."
            )

        return [state]

    def settings_provider() -> dict:
        """
        실제 monitoring_settings 최신값을 읽는다.
        """

        with get_connection() as connection:

            settings = get_monitoring_settings(
                connection=connection,
            )

        if settings is None:
            raise RuntimeError(
                "monitoring_settings가 없습니다."
            )

        return settings

    # =====================================================
    # FrameSampler
    # =====================================================

    sampler = FrameSampler(
        default_interval_sec=5.0,
    )

    # =====================================================
    # SamplingPolicyMonitor
    # =====================================================

    monitor = SamplingPolicyMonitor(
        sampler=sampler,
        check_interval_sec=1.0,
    )

    monitor_thread = Thread(
        target=monitor.run,
        kwargs={
            "state_provider": state_provider,
            "settings_provider": settings_provider,
        },
        name="sampling-policy-monitor-db-test",
    )

    print()

    print(
        f"[TEST] CCTV {CCTV_ID}의 "
        "실제 monitored_mode를 DB에서 읽습니다."
    )

    try:

        monitor_thread.start()

        # 최초 DB 조회 대기
        time.sleep(2.0)

        # -------------------------------------------------
        # 현재 실제 DB 상태 확인
        # -------------------------------------------------

        states = state_provider()

        state = states[0]

        mode = state[
            "monitored_mode"
        ]

        interval = sampler.get_interval(
            CCTV_ID
        )

        print()

        print(
            f"DB monitored_mode : {mode}"
        )

        print(
            f"Sampler interval  : {interval}"
        )

        # -------------------------------------------------
        # 기대 주기 계산
        # -------------------------------------------------

        settings = settings_provider()

        expected_by_mode = {
            "BASE": float(
                settings[
                    "base_analysis_interval_sec"
                ]
            ),

            "ALERT": float(
                settings[
                    "alert_analysis_interval_sec"
                ]
            ),

            "VERIFY": float(
                settings[
                    "verify_analysis_interval_sec"
                ]
            ),

            "POST_ALERT": float(
                settings[
                    "base_analysis_interval_sec"
                ]
            ),

            "OFF": None,
        }

        mode_text = str(
            mode
        ).upper()

        expected_interval = (
            expected_by_mode[
                mode_text
            ]
        )

        if expected_interval is None:

            print(
                "[PASS] DB mode OFF "
                "→ 분석 비활성화 상태 적용"
            )

        else:

            if interval != expected_interval:

                raise AssertionError(
                    f"{mode_text}의 예상 interval은 "
                    f"{expected_interval}초인데 "
                    f"실제는 {interval}초입니다."
                )

            print(
                f"[PASS] DB mode {mode_text} "
                f"→ {interval}초 적용"
            )

    finally:

        print()

        print(
            "[TEST] Sampling Monitor 종료"
        )

        monitor.stop()

        monitor_thread.join(
            timeout=3
        )

        if monitor_thread.is_alive():

            raise AssertionError(
                "SamplingPolicyMonitor Thread가 "
                "종료되지 않았습니다."
            )

    print()

    print("=" * 70)

    print(
        "[SUCCESS] 실제 DB monitored_mode / "
        "monitoring_settings 연동 정상"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()