"""SamplingPolicyMonitor 실시간 mode·sampling 설정 변경 테스트."""

import time

from datetime import datetime
from threading import Lock, Thread
from zoneinfo import ZoneInfo

import numpy as np

from ai.contracts import Frame
from ai.detection.frame_sampler import FrameSampler
from ai.detection.sampling_monitor import (
    SamplingPolicyMonitor,
)


KST = ZoneInfo("Asia/Seoul")


def main() -> None:

    print("=" * 70)
    print("SAMPLING POLICY MONITOR TEST")
    print("=" * 70)

    # =====================================================
    # 가짜 monitoring_settings
    # =====================================================

    settings_lock = Lock()

    settings = {
        "base_analysis_interval_sec": 5,
        "alert_analysis_interval_sec": 3,
        "verify_analysis_interval_sec": 2,
    }

    # =====================================================
    # 가짜 CCTV 상태
    # =====================================================

    state_lock = Lock()

    current_state = {
        "id": 1,
        "monitored_mode": "BASE",
    }

    # =====================================================
    # Provider
    # =====================================================

    def state_provider() -> list[dict]:
        """
        실제 서비스에서는 DB의 CCTV 상태를 조회하지만,
        테스트에서는 메모리의 current_state를 반환한다.
        """

        with state_lock:

            return [
                current_state.copy()
            ]

    def settings_provider() -> dict:
        """
        실제 서비스에서는 monitoring_settings를 조회한다.
        """

        with settings_lock:

            return settings.copy()

    # =====================================================
    # FrameSampler
    # =====================================================

    sampler = FrameSampler(
        default_interval_sec=5.0,
    )

    # =====================================================
    # Sampling Monitor
    # =====================================================

    monitor = SamplingPolicyMonitor(
        sampler=sampler,

        # 테스트니까 빠르게 확인
        check_interval_sec=0.1,
    )

    monitor_thread = Thread(
        target=monitor.run,
        kwargs={
            "state_provider":
                state_provider,

            "settings_provider":
                settings_provider,
        },
        name="sampling-policy-monitor-test",
    )

    # =====================================================
    # 변경 Helper
    # =====================================================

    def change_mode(
        mode: str,
    ) -> None:

        with state_lock:

            current_state[
                "monitored_mode"
            ] = mode

        print()

        print(
            f"[TEST MODE CHANGE] "
            f"→ {mode}"
        )

        # Monitor가 상태를 읽을 시간
        time.sleep(0.3)

    def change_setting(
        key: str,
        value: float,
    ) -> None:

        with settings_lock:

            settings[
                key
            ] = value

        print()

        print(
            f"[TEST SETTING CHANGE] "
            f"{key} → {value}"
        )

        # Monitor가 설정을 읽을 시간
        time.sleep(0.3)

    # =====================================================
    # Frame 생성 Helper
    # =====================================================

    def create_test_frame() -> Frame:

        image = np.zeros(
            (100, 100, 3),
            dtype=np.uint8,
        )

        return Frame(
            cctv_id=1,
            captured_at=datetime.now(
                KST
            ),
            image=image,
        )

    # =====================================================
    # 테스트 시작
    # =====================================================

    print()

    print(
        "[1] Sampling Monitor 시작"
    )

    monitor_thread.start()

    # 최초 BASE 적용 대기
    time.sleep(0.3)

    # =====================================================
    # BASE
    # =====================================================

    print()

    print(
        "[2] BASE 확인"
    )

    interval = sampler.get_interval(
        1
    )

    print(
        f"현재 interval : "
        f"{interval}"
    )

    if interval != 5.0:
        raise AssertionError(
            f"BASE는 5초여야 합니다. "
            f"actual={interval}"
        )

    print(
        "[PASS] BASE → 5초"
    )

    # =====================================================
    # BASE mode 유지 + settings 변경
    #
    # 기존 버그:
    # monitored_mode가 BASE 그대로이면
    # base_analysis_interval_sec 변경이 반영되지 않았다.
    # =====================================================

    change_setting(
        "base_analysis_interval_sec",
        4,
    )

    interval = sampler.get_interval(
        1
    )

    if interval != 4.0:
        raise AssertionError(
            "BASE mode 유지 상태에서 "
            "base_analysis_interval_sec 변경이 "
            "반영되지 않았습니다. "
            f"actual={interval}"
        )

    print(
        "[PASS] BASE 유지 + 설정 변경 "
        "→ 4초"
    )

    # 이후 기존 mode 전환 테스트가
    # 원래 설정값 5초를 계속 사용하도록 복구
    change_setting(
        "base_analysis_interval_sec",
        5,
    )

    interval = sampler.get_interval(
        1
    )

    if interval != 5.0:
        raise AssertionError(
            "BASE mode 유지 상태에서 "
            "base_analysis_interval_sec 복구가 "
            "반영되지 않았습니다. "
            f"actual={interval}"
        )

    print(
        "[PASS] BASE 유지 + 설정 복구 "
        "→ 5초"
    )

    # =====================================================
    # ALERT
    # =====================================================

    change_mode(
        "ALERT"
    )

    interval = sampler.get_interval(
        1
    )

    print(
        f"현재 interval : "
        f"{interval}"
    )

    if interval != 3.0:
        raise AssertionError(
            f"ALERT는 3초여야 합니다. "
            f"actual={interval}"
        )

    print(
        "[PASS] ALERT → 3초"
    )

    # =====================================================
    # VERIFY
    # =====================================================

    change_mode(
        "VERIFY"
    )

    interval = sampler.get_interval(
        1
    )

    print(
        f"현재 interval : "
        f"{interval}"
    )

    if interval != 2.0:
        raise AssertionError(
            f"VERIFY는 2초여야 합니다. "
            f"actual={interval}"
        )

    print(
        "[PASS] VERIFY → 2초"
    )

    # =====================================================
    # POST_ALERT
    # =====================================================

    change_mode(
        "POST_ALERT"
    )

    interval = sampler.get_interval(
        1
    )

    print(
        f"현재 interval : "
        f"{interval}"
    )

    if interval != 5.0:
        raise AssertionError(
            f"POST_ALERT는 BASE와 동일하게 "
            f"5초여야 합니다. "
            f"actual={interval}"
        )

    print(
        "[PASS] POST_ALERT → 5초"
    )

    # =====================================================
    # OFF
    # =====================================================

    change_mode(
        "OFF"
    )

    test_frame = (
        create_test_frame()
    )

    should_sample = (
        sampler.should_sample(
            test_frame
        )
    )

    print(
        f"OFF should_sample : "
        f"{should_sample}"
    )

    if should_sample:
        raise AssertionError(
            "OFF 상태에서는 "
            "Frame을 샘플링하면 안 됩니다."
        )

    print(
        "[PASS] OFF → 분석 비활성화"
    )

    # =====================================================
    # OFF → BASE 복구도 확인
    # =====================================================

    change_mode(
        "BASE"
    )

    interval = sampler.get_interval(
        1
    )

    test_frame = (
        create_test_frame()
    )

    should_sample = (
        sampler.should_sample(
            test_frame
        )
    )

    print(
        f"복구 interval      : "
        f"{interval}"
    )

    print(
        f"복구 should_sample : "
        f"{should_sample}"
    )

    if interval != 5.0:
        raise AssertionError(
            "OFF → BASE 복구 후 "
            "interval이 5초가 아닙니다."
        )

    if not should_sample:
        raise AssertionError(
            "OFF → BASE 복구 후 "
            "첫 Frame은 즉시 샘플링되어야 합니다."
        )

    print(
        "[PASS] OFF → BASE 복구 정상"
    )

    # =====================================================
    # Monitor 종료
    # =====================================================

    print()

    print(
        "[3] Sampling Monitor 종료"
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

    # =====================================================
    # 결과
    # =====================================================

    print()

    print("=" * 70)

    print("RESULT")

    print("=" * 70)

    print(
        "BASE       → 5초"
    )

    print(
        "BASE 유지 + 설정 변경 "
        "→ 4초 → 5초"
    )

    print(
        "ALERT      → 3초"
    )

    print(
        "VERIFY     → 2초"
    )

    print(
        "POST_ALERT → 5초"
    )

    print(
        "OFF        → 분석 비활성화"
    )

    print(
        "OFF → BASE → 분석 재개"
    )

    print()

    print(
        "[SUCCESS] "
        "SamplingPolicyMonitor "
        "실시간 mode·sampling 설정 변경 반영 정상"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
