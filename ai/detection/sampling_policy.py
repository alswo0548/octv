"""CCTV 감시 모드에 따라 YOLO 분석 주기를 적용한다."""

from typing import Mapping, Any

from .frame_sampler import FrameSampler


VALID_MONITORED_MODES = {
    "BASE",
    "ALERT",
    "VERIFY",
    "POST_ALERT",
    "OFF",
}


def apply_sampling_mode(
    sampler: FrameSampler,
    cctv_id: int,
    monitored_mode: str,
    settings: Mapping[str, Any],
) -> float | None:
    """
    CCTV의 monitored_mode와 monitoring_settings를 이용해
    FrameSampler의 분석 주기를 설정한다.

    반환값:
    - BASE / ALERT / VERIFY / POST_ALERT -> 적용된 초 단위 주기
    - OFF -> None
    """

    if not monitored_mode:
        raise ValueError(
            "monitored_mode가 필요합니다."
        )

    mode = str(
        monitored_mode
    ).upper()

    if mode not in VALID_MONITORED_MODES:
        raise ValueError(
            f"지원하지 않는 monitored_mode입니다: "
            f"{monitored_mode}"
        )

    # =====================================================
    # OFF
    # =====================================================

    if mode == "OFF":
        sampler.set_enabled(
            cctv_id=cctv_id,
            enabled=False,
        )

        return None

    # OFF가 아닌 경우 분석 가능 상태
    sampler.set_enabled(
        cctv_id=cctv_id,
        enabled=True,
    )

    # =====================================================
    # 분석 주기 결정
    # =====================================================

    if mode == "BASE":
        interval_sec = float(
            settings[
                "base_analysis_interval_sec"
            ]
        )

    elif mode == "ALERT":
        interval_sec = float(
            settings[
                "alert_analysis_interval_sec"
            ]
        )

    elif mode == "VERIFY":
        interval_sec = float(
            settings[
                "verify_analysis_interval_sec"
            ]
        )

    elif mode == "POST_ALERT":
        # 특보 종료 후에도 CCTV는 계속 감시하지만
        # 분석 주기는 일반 BASE 모드와 동일하게 사용
        interval_sec = float(
            settings[
                "base_analysis_interval_sec"
            ]
        )

    else:
        raise ValueError(
            f"처리할 수 없는 monitored_mode입니다: "
            f"{mode}"
        )

    if interval_sec <= 0:
        raise ValueError(
            "분석 주기는 0보다 커야 합니다."
        )

    sampler.set_interval(
        cctv_id=cctv_id,
        interval_sec=interval_sec,
    )

    return interval_sec