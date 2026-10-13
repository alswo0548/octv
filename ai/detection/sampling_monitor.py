"""실행 중 CCTV 감시 모드 변경을 Sampling Policy에 반영한다."""

from threading import Event
from typing import Callable, Mapping, Any

from .frame_sampler import FrameSampler
from .sampling_policy import apply_sampling_mode


class SamplingPolicyMonitor:
    """
    CCTV의 monitored_mode 변경을 주기적으로 확인하고
    FrameSampler에 반영한다.

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
        monitored_mode를 주기적으로 확인한다.

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
    # 상태 적용
    # =====================================================

    def _apply_states(
        self,
        states: list[Mapping[str, Any]],
        settings: Mapping[str, Any],
    ) -> None:
        """
        이전 monitored_mode와 달라진 CCTV만
        Sampling Policy를 다시 적용한다.
        """

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

            # mode가 그대로면 아무것도 하지 않음
            if previous_mode == monitored_mode:
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

            if applied_interval is None:

                print(
                    f"[SAMPLING MONITOR] "
                    f"CCTV {cctv_id} "
                    f"{previous_mode} "
                    f"→ {monitored_mode} "
                    f"/ 분석 비활성화"
                )

            else:

                print(
                    f"[SAMPLING MONITOR] "
                    f"CCTV {cctv_id} "
                    f"{previous_mode} "
                    f"→ {monitored_mode} "
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