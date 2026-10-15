"""실행 중 CCTV 감시 모드·분석 주기 변경을 Sampling Policy에 반영한다."""

from threading import Event
from typing import Any, Callable, Mapping

from .frame_sampler import FrameSampler
from .sampling_policy import apply_sampling_mode


class SamplingPolicyMonitor:
    """
    CCTV의 monitored_mode와 sampling 관련 monitoring_settings 변경을
    주기적으로 확인하고 FrameSampler에 반영한다.

    DB 자체에는 직접 의존하지 않는다.

    외부에서:
    - CCTV 상태 조회 함수
    - monitoring_settings 조회 함수

    를 전달받아 사용한다.
    """

    def __init__(
        self,
        sampler: FrameSampler,
        check_interval_sec: float = 2.0,
    ):
        if check_interval_sec <= 0:
            raise ValueError(
                "check_interval_sec은 "
                "0보다 커야 합니다."
            )

        self._sampler = sampler

        self._check_interval_sec = (
            check_interval_sec
        )

        self._stop_event = Event()

        # CCTV별 마지막으로 적용한 mode
        self._last_mode_by_cctv: dict[
            int,
            str,
        ] = {}

        # Sampling 주기에 영향을 주는
        # monitoring_settings의 마지막 적용값
        self._last_sampling_settings_signature: (
            tuple[float, float, float] | None
        ) = None

    # =====================================================
    # 외부 제어
    # =====================================================

    def stop(self) -> None:
        """
        Monitor 종료를 요청한다.
        """

        self._stop_event.set()

    # =====================================================
    # Main Loop
    # =====================================================

    def run(
        self,
        state_provider: Callable[
            [],
            list[Mapping[str, Any]],
        ],
        settings_provider: Callable[
            [],
            Mapping[str, Any],
        ],
    ) -> None:
        """
        monitored_mode와 sampling 설정을 주기적으로 확인한다.

        state_provider:
        [
            {
                "id": 1,
                "monitored_mode": "BASE",
            },
            ...
        ]

        settings_provider:
        monitoring_settings 1행
        """

        print(
            "[SAMPLING MONITOR] "
            "Sampling Policy Monitor 시작"
        )

        try:

            while not self._stop_event.is_set():

                try:

                    states = (
                        state_provider()
                    )

                    settings = (
                        settings_provider()
                    )

                    self._apply_states(
                        states=states,
                        settings=settings,
                    )

                except Exception as exc:

                    # DB 조회 실패 등으로
                    # Monitor 전체를 죽이지 않는다.
                    print(
                        "[SAMPLING MONITOR ERROR] "
                        f"{exc}"
                    )

                self._stop_event.wait(
                    self._check_interval_sec
                )

        finally:

            print(
                "[SAMPLING MONITOR] "
                "Sampling Policy Monitor 종료"
            )

    # =====================================================
    # Sampling 설정 Signature
    # =====================================================

    @staticmethod
    def _sampling_settings_signature(
        settings: Mapping[str, Any],
    ) -> tuple[float, float, float]:
        """
        FrameSampler 주기에 영향을 주는 설정만 추출한다.

        quality_threshold 등 Sampling 주기와 무관한 설정 변경은
        불필요한 Policy 재적용을 발생시키지 않는다.
        """

        return (
            float(
                settings[
                    "base_analysis_interval_sec"
                ]
            ),
            float(
                settings[
                    "alert_analysis_interval_sec"
                ]
            ),
            float(
                settings[
                    "verify_analysis_interval_sec"
                ]
            ),
        )

    # =====================================================
    # 상태 적용
    # =====================================================

    def _apply_states(
        self,
        states: list[Mapping[str, Any]],
        settings: Mapping[str, Any],
    ) -> None:
        """
        아래 조건 중 하나라도 만족하면 Sampling Policy를 적용한다.

        - CCTV의 monitored_mode가 변경됨
        - Sampling 주기에 영향을 주는 monitoring_settings가 변경됨
        - 새 CCTV가 조회 대상에 추가됨
        """

        settings_signature = (
            self._sampling_settings_signature(
                settings
            )
        )

        settings_changed = (
            self._last_sampling_settings_signature
            != settings_signature
        )

        active_cctv_ids: set[int] = set()

        for state in states:

            cctv_id = int(
                state["id"]
            )

            monitored_mode = str(
                state["monitored_mode"]
            ).upper()

            active_cctv_ids.add(
                cctv_id
            )

            previous_mode = (
                self._last_mode_by_cctv.get(
                    cctv_id
                )
            )

            mode_changed = (
                previous_mode
                != monitored_mode
            )

            # mode와 sampling 설정이 모두 그대로면
            # 기존 FrameSampler 설정을 유지한다.
            if (
                not mode_changed
                and not settings_changed
            ):
                continue

            applied_interval = (
                apply_sampling_mode(
                    sampler=self._sampler,
                    cctv_id=cctv_id,
                    monitored_mode=(
                        monitored_mode
                    ),
                    settings=settings,
                )
            )

            self._last_mode_by_cctv[
                cctv_id
            ] = monitored_mode

            if mode_changed:

                change_text = (
                    f"{previous_mode} "
                    f"→ {monitored_mode}"
                )

            else:

                change_text = (
                    f"{monitored_mode} 유지 "
                    "/ 설정 변경 반영"
                )

            if applied_interval is None:

                print(
                    f"[SAMPLING MONITOR] "
                    f"CCTV {cctv_id} "
                    f"{change_text} "
                    f"/ 분석 비활성화"
                )

            else:

                print(
                    f"[SAMPLING MONITOR] "
                    f"CCTV {cctv_id} "
                    f"{change_text} "
                    f"/ 분석 주기 "
                    f"{applied_interval:.1f}초"
                )

        # -------------------------------------------------
        # 조회 대상에서 사라진 CCTV는
        # 내부 mode cache에서 제거
        # -------------------------------------------------

        removed_cctv_ids = (
            set(
                self._last_mode_by_cctv
            )
            - active_cctv_ids
        )

        for cctv_id in removed_cctv_ids:

            self._last_mode_by_cctv.pop(
                cctv_id,
                None,
            )

        # 모든 현재 CCTV에 정상 적용된 뒤에만
        # settings signature를 갱신한다.
        #
        # apply_sampling_mode 중 예외가 발생하면
        # 이 줄까지 도달하지 않으므로 다음 polling에서
        # 동일한 settings 변경을 다시 시도한다.
        self._last_sampling_settings_signature = (
            settings_signature
        )