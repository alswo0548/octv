"""YOLO 분석에 사용할 Frame의 샘플링 주기를 관리한다."""

import time
from threading import Lock

from ..contracts import Frame


class FrameSampler:
    """
    CCTV별로 지정된 시간 간격마다 분석용 Frame을 선택한다.

    예:
    - 기본 감시: 5초
    - 특보 감시: 3초
    - 집중 검증: 2초

    각 CCTV는 서로 다른 분석 주기를 가질 수 있다.
    """

    def __init__(
        self,
        default_interval_sec: float,
    ):
        if default_interval_sec <= 0:
            raise ValueError(
                "default_interval_sec은 0보다 커야 합니다."
            )

        # 기본 분석 주기
        self._default_interval_sec = (
            default_interval_sec
        )

        # CCTV별 분석 주기
        self._interval_by_cctv: dict[
            int,
            float,
        ] = {}

        # CCTV별 마지막 샘플링 시각
        self._last_sampled_at: dict[
            int,
            float,
        ] = {}

        # OFF 상태 등으로 분석이 비활성화된 CCTV
        self._disabled_cctv_ids: set[int] = set()

        self._lock = Lock()

    def should_sample(
        self,
        frame: Frame,
    ) -> bool:
        """
        현재 Frame을 분석 대상으로 선택할지 판단한다.

        CCTV별 첫 Frame은 즉시 선택한다.

        이후에는 해당 CCTV에 설정된 interval_sec이
        지난 경우에만 선택한다.

        비활성화된 CCTV는 항상 False를 반환한다.
        """

        now = time.monotonic()

        with self._lock:

            # 분석 OFF 상태라면 샘플링하지 않음
            if (
                frame.cctv_id
                in self._disabled_cctv_ids
            ):
                return False

            interval_sec = (
                self._interval_by_cctv.get(
                    frame.cctv_id,
                    self._default_interval_sec,
                )
            )

            last_sampled_at = (
                self._last_sampled_at.get(
                    frame.cctv_id
                )
            )

            # 첫 Frame은 즉시 분석
            if last_sampled_at is None:
                self._last_sampled_at[
                    frame.cctv_id
                ] = now

                return True

            elapsed = (
                now
                - last_sampled_at
            )

            if elapsed >= interval_sec:
                self._last_sampled_at[
                    frame.cctv_id
                ] = now

                return True

            return False

    def set_interval(
        self,
        cctv_id: int,
        interval_sec: float,
    ) -> None:
        """
        특정 CCTV의 분석 주기를 변경한다.

        예:
        CCTV 1 → 5초
        CCTV 2 → 3초
        CCTV 3 → 2초
        """

        if interval_sec <= 0:
            raise ValueError(
                "interval_sec은 0보다 커야 합니다."
            )

        with self._lock:
            self._interval_by_cctv[
                cctv_id
            ] = interval_sec

    def set_enabled(
        self,
        cctv_id: int,
        enabled: bool,
    ) -> None:
        """
        특정 CCTV의 분석 활성/비활성 상태를 설정한다.

        OFF -> ON으로 실제 상태가 변경된 경우에만
        마지막 샘플링 시각을 초기화한다.
        """

        with self._lock:

            if enabled:
                was_disabled = (
                    cctv_id
                    in self._disabled_cctv_ids
                )

                self._disabled_cctv_ids.discard(
                    cctv_id
                )

                # 실제로 OFF -> ON이 된 경우만
                # 다음 Frame을 즉시 분석
                if was_disabled:
                    self._last_sampled_at.pop(
                        cctv_id,
                        None,
                    )

            else:
                was_enabled = (
                    cctv_id
                    not in self._disabled_cctv_ids
                )

                self._disabled_cctv_ids.add(
                    cctv_id
                )

                # 실제로 ON -> OFF가 된 경우만 초기화
                if was_enabled:
                    self._last_sampled_at.pop(
                        cctv_id,
                        None,
                    )

    def reset(
        self,
        cctv_id: int,
    ) -> None:
        """
        특정 CCTV의 마지막 샘플링 시각을 초기화한다.

        다음 Frame은 즉시 분석 대상으로 선택된다.
        """

        with self._lock:
            self._last_sampled_at.pop(
                cctv_id,
                None,
            )

    def get_interval(
        self,
        cctv_id: int,
    ) -> float:
        """
        특정 CCTV에 현재 적용된 분석 주기를 반환한다.
        """

        with self._lock:
            return self._interval_by_cctv.get(
                cctv_id,
                self._default_interval_sec,
            )

    def is_enabled(
        self,
        cctv_id: int,
    ) -> bool:
        """
        해당 CCTV의 Frame sampling 활성화 여부를 반환한다.
        """

        with self._lock:
            return (
                cctv_id
                not in self._disabled_cctv_ids
            )