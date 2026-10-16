"""FrameSampler monitored_mode 정책 테스트."""

from ai.detection.frame_sampler import FrameSampler
from ai.detection.sampling_policy import (
    apply_sampling_mode,
)


def main() -> None:

    settings = {
        "base_analysis_interval_sec": 5,
        "alert_analysis_interval_sec": 3,
        "verify_analysis_interval_sec": 2,
    }

    sampler = FrameSampler(
        default_interval_sec=5,
    )

    print("=" * 60)
    print("SAMPLING POLICY TEST")
    print("=" * 60)

    test_cases = [
        ("BASE", 5.0),
        ("ALERT", 3.0),
        ("VERIFY", 2.0),
        ("POST_ALERT", 5.0),
        ("OFF", None),
    ]

    for mode, expected in test_cases:

        applied = apply_sampling_mode(
            sampler=sampler,
            cctv_id=1,
            monitored_mode=mode,
            settings=settings,
        )

        print()
        print(
            f"mode={mode:<10} "
            f"applied={applied} "
            f"expected={expected}"
        )

        if applied != expected:
            raise AssertionError(
                f"{mode} 분석 주기 오류: "
                f"expected={expected}, "
                f"actual={applied}"
            )

    print()
    print("[SUCCESS] 모든 monitored_mode 정책 정상")
    print("=" * 60)


if __name__ == "__main__":
    main()