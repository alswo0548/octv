"""실제 DB monitored_mode 변경을 SamplingPolicyMonitor가 실시간 감지하는 테스트."""

import time
from datetime import datetime
from threading import Thread
from zoneinfo import ZoneInfo

import numpy as np

from ai.contracts import Frame
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

KST = ZoneInfo("Asia/Seoul")


def main() -> None:

    print("=" * 70)
    print("SAMPLING POLICY MONITOR DB RUNTIME TEST")
    print("=" * 70)

    # =====================================================
    # DB Provider
    # =====================================================

    def state_provider() -> list[dict]:

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
    # DB mode 변경 Helper
    # =====================================================

    def set_db_mode(
        mode: str,
    ) -> None:

        query = """
        UPDATE cctvs
        SET monitored_mode =
            CAST(%s AS monitored_mode_enum)
        WHERE id = %s;
        """

        with get_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    query,
                    (
                        mode,
                        CCTV_ID,
                    ),
                )

        print()

        print(
            f"[DB MODE CHANGE] "
            f"CCTV {CCTV_ID} → {mode}"
        )

    # =====================================================
    # mode 확인 Helper
    # =====================================================

    def wait_for_mode(
        expected_mode: str,
        expected_interval: float | None,
        timeout_sec: float = 5.0,
    ) -> None:

        deadline = (
            time.monotonic()
            + timeout_sec
        )

        while time.monotonic() < deadline:

            state = state_provider()

            actual_mode = str(
                state[0][
                    "monitored_mode"
                ]
            ).upper()

            actual_interval = (
                sampler.get_interval(
                    CCTV_ID
                )
            )

            if actual_mode == expected_mode:

                sampling_enabled = (
                    sampler.is_enabled(
                        CCTV_ID
                    )
                )

                # OFF
                if expected_interval is None:

                    if not sampling_enabled:

                        print(
                            f"[PASS] "
                            f"{expected_mode} "
                            f"→ 분석 비활성화"
                        )

                        return

                # BASE / ALERT / VERIFY / POST_ALERT
                else:

                    if (
                        sampling_enabled
                        and actual_interval
                        == expected_interval
                    ):

                        print(
                            f"[PASS] "
                            f"{expected_mode} "
                            f"→ "
                            f"{actual_interval:.1f}초"
                        )

                        return

            time.sleep(
                0.1
            )

        raise AssertionError(
            f"{expected_mode} 적용을 "
            f"{timeout_sec}초 안에 "
            "확인하지 못했습니다."
        )

    # =====================================================
    # Frame Helper
    # =====================================================

    def create_test_frame() -> Frame:

        image = np.zeros(
            (
                100,
                100,
                3,
            ),
            dtype=np.uint8,
        )

        return Frame(
            cctv_id=CCTV_ID,
            captured_at=datetime.now(
                KST
            ),
            image=image,
        )

    # =====================================================
    # 원래 mode 보관
    # =====================================================

    original_state = (
        state_provider()[0]
    )

    original_mode = str(
        original_state[
            "monitored_mode"
        ]
    ).upper()

    print()

    print(
        f"[ORIGINAL MODE] "
        f"{original_mode}"
    )

    # =====================================================
    # monitoring_settings 확인
    # =====================================================

    settings = settings_provider()

    base_interval = float(
        settings[
            "base_analysis_interval_sec"
        ]
    )

    alert_interval = float(
        settings[
            "alert_analysis_interval_sec"
        ]
    )

    verify_interval = float(
        settings[
            "verify_analysis_interval_sec"
        ]
    )

    print()

    print(
        "[SETTINGS]"
    )

    print(
        f"BASE       : "
        f"{base_interval:.1f}초"
    )

    print(
        f"ALERT      : "
        f"{alert_interval:.1f}초"
    )

    print(
        f"VERIFY     : "
        f"{verify_interval:.1f}초"
    )

    print(
        f"POST_ALERT : "
        f"{base_interval:.1f}초"
    )

    # =====================================================
    # FrameSampler
    # =====================================================

    sampler = FrameSampler(
        default_interval_sec=(
            base_interval
        ),
    )

    # =====================================================
    # Monitor
    # =====================================================

    monitor = SamplingPolicyMonitor(
        sampler=sampler,

        # 테스트니까 빠르게 polling
        check_interval_sec=0.2,
    )

    monitor_thread = Thread(
        target=monitor.run,
        kwargs={
            "state_provider":
                state_provider,

            "settings_provider":
                settings_provider,
        },
        name=(
            "sampling-policy-"
            "monitor-db-runtime-test"
        ),
    )

    # =====================================================
    # 실제 테스트
    # =====================================================

    try:

        print()

        print(
            "[1] Sampling Monitor 시작"
        )

        monitor_thread.start()

        # 최초 상태 읽을 시간
        time.sleep(
            0.5
        )

        # -------------------------------------------------
        # BASE
        # -------------------------------------------------

        set_db_mode(
            "BASE"
        )

        wait_for_mode(
            expected_mode="BASE",
            expected_interval=(
                base_interval
            ),
        )

        # -------------------------------------------------
        # ALERT
        # -------------------------------------------------

        set_db_mode(
            "ALERT"
        )

        wait_for_mode(
            expected_mode="ALERT",
            expected_interval=(
                alert_interval
            ),
        )

        # -------------------------------------------------
        # VERIFY
        # -------------------------------------------------

        set_db_mode(
            "VERIFY"
        )

        wait_for_mode(
            expected_mode="VERIFY",
            expected_interval=(
                verify_interval
            ),
        )

        # -------------------------------------------------
        # POST_ALERT
        # -------------------------------------------------

        set_db_mode(
            "POST_ALERT"
        )

        wait_for_mode(
            expected_mode=(
                "POST_ALERT"
            ),
            expected_interval=(
                base_interval
            ),
        )

        # -------------------------------------------------
        # OFF
        # -------------------------------------------------

        set_db_mode(
            "OFF"
        )

        wait_for_mode(
            expected_mode="OFF",
            expected_interval=None,
        )

        # -------------------------------------------------
        # OFF → BASE
        # -------------------------------------------------

        set_db_mode(
            "BASE"
        )

        wait_for_mode(
            expected_mode="BASE",
            expected_interval=(
                base_interval
            ),
        )

        frame = create_test_frame()

        should_sample = (
            sampler.should_sample(
                frame
            )
        )

        print(
            f"OFF → BASE "
            f"should_sample : "
            f"{should_sample}"
        )

        if not should_sample:

            raise AssertionError(
                "OFF → BASE 이후 "
                "첫 Frame이 즉시 "
                "샘플링되지 않았습니다."
            )

        print(
            "[PASS] OFF → BASE "
            "분석 재개"
        )

    finally:

        # =================================================
        # 원래 DB mode 복원
        # =================================================

        print()

        print(
            f"[RESTORE] "
            f"원래 mode "
            f"{original_mode}로 복구"
        )

        set_db_mode(
            original_mode
        )

        # Monitor가 복구 상태까지 읽을 시간
        time.sleep(
            0.5
        )

        # =================================================
        # Monitor 종료
        # =================================================

        monitor.stop()

        monitor_thread.join(
            timeout=3
        )

        if monitor_thread.is_alive():

            raise AssertionError(
                "SamplingPolicyMonitor "
                "Thread가 종료되지 않았습니다."
            )

    # =====================================================
    # 최종 DB 확인
    # =====================================================

    restored_state = (
        state_provider()[0]
    )

    restored_mode = str(
        restored_state[
            "monitored_mode"
        ]
    ).upper()

    if (
        restored_mode
        != original_mode
    ):

        raise AssertionError(
            "테스트 종료 후 "
            "원래 monitored_mode로 "
            "복구되지 않았습니다."
        )

    print()

    print(
        f"[PASS] DB mode 복구 확인 "
        f"→ {restored_mode}"
    )

    # =====================================================
    # 결과
    # =====================================================

    print()

    print("=" * 70)

    print("RESULT")

    print("=" * 70)

    print(
        f"BASE       → "
        f"{base_interval:.1f}초"
    )

    print(
        f"ALERT      → "
        f"{alert_interval:.1f}초"
    )

    print(
        f"VERIFY     → "
        f"{verify_interval:.1f}초"
    )

    print(
        f"POST_ALERT → "
        f"{base_interval:.1f}초"
    )

    print(
        "OFF        → 분석 비활성화"
    )

    print(
        "OFF → BASE → 분석 재개"
    )

    print(
        f"DB 복구     → "
        f"{original_mode}"
    )

    print()

    print(
        "[SUCCESS] "
        "실제 DB monitored_mode "
        "실시간 변경 감지 정상"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()