"""CCTV Frame 수신 상태를 주기적으로 감시한다."""

import time
from dataclasses import dataclass
from datetime import datetime
from threading import Event
from typing import Callable


@dataclass
class _ObservedCctv:
    """
    Health Monitor가 CCTV별로 기억하는 상태.

    last_frame_at:
        마지막으로 확인한 DB의 last_frame_at 값

    last_progress_at:
        last_frame_at 값이 마지막으로 변경된 monotonic 시각

    reconnect_requested:
        현재 stale 상태에 대해 이미 재연결 요청을 보냈는지 여부
    """

    last_frame_at: datetime | None

    last_progress_at: float

    reconnect_requested: bool = False


class CctvHealthMonitor:
    """
    감시 중인 CCTV들의 Frame 수신 상태를 주기적으로 확인한다.

    판단 기준:
    - connection_status == CONNECTED
    - last_frame_at 값이 일정 시간 동안 변경되지 않음

    위 조건을 만족하면
    해당 CCTV의 CaptureWorker에 재연결을 요청한다.

    실제 DB 조회와 CaptureWorker 제어는
    callback을 통해 외부에서 처리한다.
    """

    def __init__(
        self,
        check_interval_sec: float = 5.0,
        stale_after_sec: float = 20.0,
    ):
        if check_interval_sec <= 0:
            raise ValueError(
                "check_interval_sec은 "
                "0보다 커야 합니다."
            )

        if stale_after_sec <= 0:
            raise ValueError(
                "stale_after_sec은 "
                "0보다 커야 합니다."
            )

        self.check_interval_sec = (
            check_interval_sec
        )

        self.stale_after_sec = (
            stale_after_sec
        )

        self._stop_event = Event()

        # CCTV별 최근 관찰 상태
        self._observed: dict[
            int,
            _ObservedCctv,
        ] = {}

    # =====================================================
    # 외부 제어
    # =====================================================

    def stop(self) -> None:
        """
        Health Monitor 종료를 요청한다.
        """

        self._stop_event.set()

    # =====================================================
    # Main Loop
    # =====================================================

    def run(
        self,
        state_provider: Callable[
            [],
            list[dict],
        ],
        reconnect_requester: Callable[
            [int],
            None,
        ],
    ) -> None:
        """
        CCTV 상태를 주기적으로 확인한다.

        state_provider:
            현재 감시 대상 CCTV 상태 목록 반환

            각 dict에는 최소한 아래 값이 필요하다.

            - id
            - connection_status
            - last_frame_at

        reconnect_requester:
            stale CCTV에 대해
            실제 CaptureWorker 재연결을 요청한다.

            입력:
            - cctv_id
        """

        print(
            "[HEALTH] CCTV Health Monitor 시작"
        )

        try:

            while not self._stop_event.is_set():

                try:

                    states = (
                        state_provider()
                    )

                    self._check_states(
                        states=states,
                        reconnect_requester=(
                            reconnect_requester
                        ),
                    )

                except Exception as exc:

                    # DB 조회 등의 문제가 생겨도
                    # Health Monitor 자체는 종료하지 않는다.
                    print(
                        "[HEALTH ERROR] "
                        f"{exc}"
                    )

                # stop() 요청을 받을 수 있도록
                # Event.wait() 사용
                self._stop_event.wait(
                    self.check_interval_sec
                )

        finally:

            print(
                "[HEALTH] CCTV Health Monitor 종료"
            )

    # =====================================================
    # CCTV 상태 검사
    # =====================================================

    def _check_states(
        self,
        states: list[dict],
        reconnect_requester: Callable[
            [int],
            None,
        ],
    ) -> None:

        now_monotonic = (
            time.monotonic()
        )

        current_cctv_ids: set[int] = set()

        for state in states:

            cctv_id = state["id"]

            current_cctv_ids.add(
                cctv_id
            )

            connection_status = (
                state[
                    "connection_status"
                ]
            )

            last_frame_at = (
                state[
                    "last_frame_at"
                ]
            )

            # =============================================
            # CONNECTED가 아니면 stale 검사하지 않는다.
            # =============================================

            if (
                connection_status
                != "CONNECTED"
            ):

                # 다음에 다시 CONNECTED가 되면
                # 새로운 관찰 주기로 시작하도록 제거
                self._observed.pop(
                    cctv_id,
                    None,
                )

                continue

            # =============================================
            # 처음 관찰한 CONNECTED CCTV
            # =============================================

            observed = (
                self._observed.get(
                    cctv_id
                )
            )

            if observed is None:

                self._observed[
                    cctv_id
                ] = _ObservedCctv(
                    last_frame_at=(
                        last_frame_at
                    ),
                    last_progress_at=(
                        now_monotonic
                    ),
                )

                print(
                    f"[HEALTH] "
                    f"CCTV {cctv_id} "
                    "CONNECTED 감시 시작"
                )

                continue

            # =============================================
            # last_frame_at이 변경됨
            #
            # 즉 실제 Frame이 계속 들어오고 있음.
            # =============================================

            if (
                last_frame_at
                != observed.last_frame_at
            ):

                observed.last_frame_at = (
                    last_frame_at
                )

                observed.last_progress_at = (
                    now_monotonic
                )

                # 이전 stale 문제에서 복구된 경우
                # 다시 새로운 장애를 감지할 수 있도록 초기화
                observed.reconnect_requested = (
                    False
                )

                continue

            # =============================================
            # last_frame_at 값이 그대로인 시간 계산
            # =============================================

            stale_for_sec = (
                now_monotonic
                - observed.last_progress_at
            )

            # 아직 기준시간 이내
            if (
                stale_for_sec
                <= self.stale_after_sec
            ):
                continue

            # 이미 이번 stale 상태에 대해
            # 재연결 요청을 보냈으면 중복 요청 안 함.
            if observed.reconnect_requested:
                continue

            # =============================================
            # STALE 감지
            # =============================================

            print(
                f"[HEALTH WARNING] "
                f"CCTV {cctv_id} "
                f"Frame 갱신 없음 "
                f"{stale_for_sec:.1f}초 "
                f"→ 재연결 요청"
            )

            try:

                reconnect_requester(
                    cctv_id
                )

            except Exception as exc:

                print(
                    f"[HEALTH RECONNECT ERROR] "
                    f"CCTV {cctv_id}: "
                    f"{exc}"
                )

                # 재연결 요청 자체가 실패했다면
                # 다음 Health Check에서 다시 시도할 수 있게
                # reconnect_requested는 False 유지
                continue

            observed.reconnect_requested = (
                True
            )

        # =================================================
        # 더 이상 감시 대상이 아닌 CCTV는
        # 내부 상태에서 제거
        # =================================================

        stale_ids = (
            set(
                self._observed.keys()
            )
            - current_cctv_ids
        )

        for cctv_id in stale_ids:

            self._observed.pop(
                cctv_id,
                None,
            )