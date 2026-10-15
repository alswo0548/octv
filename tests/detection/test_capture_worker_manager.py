from __future__ import annotations

import time
from datetime import datetime
from threading import Event, Lock
from zoneinfo import ZoneInfo

import numpy as np

from ai.contracts import Frame
from ai.detection.capture_manager import (
    CaptureWorkerManager,
)


KST = ZoneInfo(
    "Asia/Seoul"
)


# =========================================================
# Fake CaptureWorker
# =========================================================


class FakeCaptureWorker:
    """
    실제 CCTV 대신 사용하는 테스트 Worker.

    run()이 시작되면:
        CONNECTED
        → 일정 간격으로 Frame 생성
        → stop() 호출될 때까지 반복
        → DISCONNECTED

    실제 네트워크/OpenCV는 사용하지 않는다.
    """

    def __init__(
        self,
        cctv_id: int,
        frame_interval_sec: float = 0.05,
    ) -> None:

        self.cctv_id = (
            cctv_id
        )

        self.frame_interval_sec = (
            frame_interval_sec
        )

        self._stop_event = (
            Event()
        )

    def run(
        self,
        on_frame,
        on_status,
    ) -> None:

        on_status(
            "CONNECTED"
        )

        frame_number = 0

        try:

            while (
                not self._stop_event.is_set()
            ):

                frame_number += 1

                # CCTV별로 다른 값으로 채워서
                # Frame이 서로 구분되게 한다.
                image = np.full(
                    (
                        120,
                        160,
                        3,
                    ),
                    fill_value=(
                        self.cctv_id
                        % 255
                    ),
                    dtype=np.uint8,
                )

                frame = Frame(
                    cctv_id=(
                        self.cctv_id
                    ),
                    captured_at=(
                        datetime.now(
                            KST
                        )
                    ),
                    image=image,
                )

                on_frame(
                    frame
                )

                time.sleep(
                    self.frame_interval_sec
                )

        finally:

            on_status(
                "DISCONNECTED"
            )

    def stop(
        self,
    ) -> None:

        self._stop_event.set()


# =========================================================
# 대기 Helper
# =========================================================


def wait_until(
    condition,
    timeout_sec: float,
    description: str,
) -> None:
    """
    condition()이 True가 될 때까지 기다린다.
    """

    deadline = (
        time.monotonic()
        + timeout_sec
    )

    while (
        time.monotonic()
        < deadline
    ):

        if condition():

            return

        time.sleep(
            0.05
        )

    raise AssertionError(
        f"Timeout: {description}"
    )


# =========================================================
# Main
# =========================================================


def main() -> None:

    print(
        "=" * 70
    )

    print(
        "OCTV CaptureWorkerManager "
        "Multi-CCTV Test"
    )

    print(
        "=" * 70
    )

    # -----------------------------------------------------
    # 테스트 CCTV
    # -----------------------------------------------------

    cctv_1 = {
        "id": 1,
        "name": "FAKE CCTV 1",
        "provider": "TEST",
    }

    cctv_2 = {
        "id": 2,
        "name": "FAKE CCTV 2",
        "provider": "TEST",
    }

    cctv_3 = {
        "id": 3,
        "name": "FAKE CCTV 3",
        "provider": "TEST",
    }

    # -----------------------------------------------------
    # 통계
    # -----------------------------------------------------

    frame_lock = Lock()

    status_lock = Lock()

    frame_counts: dict[
        int,
        int,
    ] = {}

    status_history: dict[
        int,
        list[str],
    ] = {}

    # =====================================================
    # Worker Factory
    # =====================================================

    def worker_factory(
        cctv,
    ) -> FakeCaptureWorker:

        cctv_id = int(
            cctv["id"]
        )

        print(
            f"[FACTORY] "
            f"CCTV {cctv_id} "
            "Fake Worker 생성"
        )

        return FakeCaptureWorker(
            cctv_id=cctv_id,
            frame_interval_sec=0.05,
        )

    # =====================================================
    # Frame Callback
    # =====================================================

    def handle_frame(
        frame: Frame,
    ) -> None:

        with frame_lock:

            current_count = (
                frame_counts.get(
                    frame.cctv_id,
                    0,
                )
                + 1
            )

            frame_counts[
                frame.cctv_id
            ] = current_count

        # 너무 많은 로그를 막기 위해
        # 첫 Frame과 10번째 단위만 출력
        if (
            current_count == 1
            or current_count % 10 == 0
        ):

            print(
                f"[FRAME] "
                f"CCTV {frame.cctv_id} "
                f"/ count="
                f"{current_count} "
                f"/ captured_at="
                f"{frame.captured_at}"
            )

    # =====================================================
    # Status Callback
    # =====================================================

    def handle_status(
        cctv_id: int,
        status: str,
    ) -> None:

        with status_lock:

            history = (
                status_history.setdefault(
                    cctv_id,
                    [],
                )
            )

            history.append(
                status
            )

        print(
            f"[STATUS] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

    # =====================================================
    # Manager 생성
    # =====================================================

    manager = (
        CaptureWorkerManager(
            worker_factory=(
                worker_factory
            ),
            on_frame=(
                handle_frame
            ),
            on_status=(
                handle_status
            ),
        )
    )

    try:

        # =================================================
        # TEST 1
        # CCTV 1만 시작
        # =================================================

        print()

        print(
            "[TEST 1] CCTV 1 시작"
        )

        result = (
            manager.sync(
                [
                    cctv_1,
                ]
            )
        )

        print(
            f"sync result = "
            f"{result}"
        )

        if (
            result["started"]
            != [1]
        ):

            raise AssertionError(
                "CCTV 1 시작 결과가 "
                "올바르지 않습니다."
            )

        if (
            result["stopped"]
            != []
        ):

            raise AssertionError(
                "예상하지 않은 CCTV가 "
                "종료되었습니다."
            )

        wait_until(
            condition=lambda: (
                manager.running_cctv_ids()
                == [1]
            ),
            timeout_sec=2.0,
            description=(
                "CCTV 1 Worker 시작"
            ),
        )

        wait_until(
            condition=lambda: (
                frame_counts.get(
                    1,
                    0,
                )
                >= 3
            ),
            timeout_sec=2.0,
            description=(
                "CCTV 1 Frame 수신"
            ),
        )

        print(
            "[PASS] CCTV 1 단독 실행"
        )

        # =================================================
        # TEST 2
        # CCTV 2 / 3 추가
        # =================================================

        print()

        print(
            "[TEST 2] CCTV 2, 3 추가"
        )

        result = (
            manager.sync(
                [
                    cctv_1,
                    cctv_2,
                    cctv_3,
                ]
            )
        )

        print(
            f"sync result = "
            f"{result}"
        )

        if (
            result["started"]
            != [2, 3]
        ):

            raise AssertionError(
                "CCTV 2, 3 시작 결과가 "
                "올바르지 않습니다. "
                f"actual="
                f"{result['started']}"
            )

        if (
            result["stopped"]
            != []
        ):

            raise AssertionError(
                "CCTV 추가 과정에서 "
                "기존 CCTV가 종료되었습니다."
            )

        wait_until(
            condition=lambda: (
                manager.running_cctv_ids()
                == [
                    1,
                    2,
                    3,
                ]
            ),
            timeout_sec=2.0,
            description=(
                "CCTV 1,2,3 동시 실행"
            ),
        )

        wait_until(
            condition=lambda: (
                frame_counts.get(
                    1,
                    0,
                )
                >= 5
                and frame_counts.get(
                    2,
                    0,
                )
                >= 3
                and frame_counts.get(
                    3,
                    0,
                )
                >= 3
            ),
            timeout_sec=3.0,
            description=(
                "CCTV 1,2,3 Frame 동시 수신"
            ),
        )

        print(
            "[PASS] CCTV 3대 Worker 동시 실행"
        )

        print(
            f"running="
            f"{manager.running_cctv_ids()}"
        )

        with frame_lock:

            print(
                f"frame_counts="
                f"{dict(frame_counts)}"
            )

        # =================================================
        # TEST 3
        # 같은 목록 재동기화
        # =================================================

        print()

        print(
            "[TEST 3] 동일 목록 재동기화"
        )

        result = (
            manager.sync(
                [
                    cctv_1,
                    cctv_2,
                    cctv_3,
                ]
            )
        )

        print(
            f"sync result = "
            f"{result}"
        )

        if (
            result["started"]
            != []
            or result["stopped"]
            != []
        ):

            raise AssertionError(
                "동일 CCTV 목록인데 "
                "Worker를 다시 시작하거나 "
                "종료했습니다."
            )

        if (
            result["running"]
            != [
                1,
                2,
                3,
            ]
        ):

            raise AssertionError(
                "동일 목록 재동기화 후 "
                "실행 Worker가 "
                "올바르지 않습니다."
            )

        print(
            "[PASS] 중복 Worker 생성 없음"
        )

        # =================================================
        # TEST 4
        # CCTV 1 제거
        # =================================================

        print()

        print(
            "[TEST 4] CCTV 1 감시 대상 제거"
        )

        with frame_lock:

            cctv_1_before_stop = (
                frame_counts.get(
                    1,
                    0,
                )
            )

        result = (
            manager.sync(
                [
                    cctv_2,
                    cctv_3,
                ]
            )
        )

        print(
            f"sync result = "
            f"{result}"
        )

        if (
            result["stopped"]
            != [1]
        ):

            raise AssertionError(
                "CCTV 1이 정상적으로 "
                "종료되지 않았습니다."
            )

        wait_until(
            condition=lambda: (
                manager.running_cctv_ids()
                == [
                    2,
                    3,
                ]
            ),
            timeout_sec=2.0,
            description=(
                "CCTV 1 종료 후 "
                "CCTV 2,3 유지"
            ),
        )

        # CCTV 1 Frame이 더 이상
        # 증가하지 않는지 확인
        time.sleep(
            0.3
        )

        with frame_lock:

            cctv_1_after_stop = (
                frame_counts.get(
                    1,
                    0,
                )
            )

            cctv_2_after = (
                frame_counts.get(
                    2,
                    0,
                )
            )

            cctv_3_after = (
                frame_counts.get(
                    3,
                    0,
                )
            )

        if (
            cctv_1_after_stop
            != cctv_1_before_stop
        ):

            raise AssertionError(
                "CCTV 1 Worker 종료 후에도 "
                "Frame이 계속 생성되었습니다. "
                f"before="
                f"{cctv_1_before_stop}, "
                f"after="
                f"{cctv_1_after_stop}"
            )

        if (
            cctv_2_after
            <= 0
            or cctv_3_after
            <= 0
        ):

            raise AssertionError(
                "CCTV 1 종료 과정에서 "
                "CCTV 2 또는 3까지 "
                "영향을 받았습니다."
            )

        print(
            "[PASS] CCTV 1만 종료 / "
            "CCTV 2,3 계속 실행"
        )

        # =================================================
        # TEST 5
        # CCTV 1 다시 추가
        # =================================================

        print()

        print(
            "[TEST 5] CCTV 1 다시 추가"
        )

        result = (
            manager.sync(
                [
                    cctv_1,
                    cctv_2,
                    cctv_3,
                ]
            )
        )

        print(
            f"sync result = "
            f"{result}"
        )

        if (
            result["started"]
            != [1]
        ):

            raise AssertionError(
                "CCTV 1 재시작 결과가 "
                "올바르지 않습니다."
            )

        wait_until(
            condition=lambda: (
                manager.running_cctv_ids()
                == [
                    1,
                    2,
                    3,
                ]
            ),
            timeout_sec=2.0,
            description=(
                "CCTV 1 재시작"
            ),
        )

        wait_until(
            condition=lambda: (
                frame_counts.get(
                    1,
                    0,
                )
                > cctv_1_after_stop
            ),
            timeout_sec=2.0,
            description=(
                "CCTV 1 재시작 후 "
                "Frame 수신"
            ),
        )

        print(
            "[PASS] CCTV 1 재시작"
        )

        # =================================================
        # TEST 6
        # stop_all
        # =================================================

        print()

        print(
            "[TEST 6] 전체 Worker 종료"
        )

        manager.stop_all()

        if (
            manager.worker_count()
            != 0
        ):

            raise AssertionError(
                "stop_all() 이후에도 "
                "실행 중인 Worker가 있습니다."
            )

        if (
            manager.running_cctv_ids()
            != []
        ):

            raise AssertionError(
                "stop_all() 이후 "
                "running_cctv_ids가 "
                "비어 있지 않습니다."
            )

        print(
            "[PASS] 모든 Worker 종료"
        )

        # =================================================
        # Status History 검증
        # =================================================

        print()

        print(
            "[STATUS HISTORY]"
        )

        with status_lock:

            final_status_history = {
                cctv_id:
                    history.copy()
                for (
                    cctv_id,
                    history,
                ) in (
                    status_history.items()
                )
            }

        for cctv_id in [
            1,
            2,
            3,
        ]:

            history = (
                final_status_history.get(
                    cctv_id,
                    []
                )
            )

            print(
                f"CCTV {cctv_id} : "
                + " → ".join(
                    history
                )
            )

            if (
                "CONNECTED"
                not in history
            ):

                raise AssertionError(
                    f"CCTV {cctv_id}의 "
                    "CONNECTED 상태가 "
                    "없습니다."
                )

            if (
                "DISCONNECTED"
                not in history
            ):

                raise AssertionError(
                    f"CCTV {cctv_id}의 "
                    "DISCONNECTED 상태가 "
                    "없습니다."
                )

        # CCTV 1은
        # 종료 후 다시 시작했기 때문에
        # CONNECTED가 최소 2번이어야 한다.
        if (
            final_status_history[
                1
            ].count(
                "CONNECTED"
            )
            < 2
        ):

            raise AssertionError(
                "CCTV 1 재시작이 "
                "Status History에서 "
                "확인되지 않습니다."
            )

        # =================================================
        # 최종 Frame 통계
        # =================================================

        print()

        print(
            "[FRAME COUNTS]"
        )

        with frame_lock:

            final_frame_counts = (
                dict(
                    frame_counts
                )
            )

        for cctv_id in [
            1,
            2,
            3,
        ]:

            count = (
                final_frame_counts.get(
                    cctv_id,
                    0,
                )
            )

            print(
                f"CCTV {cctv_id} : "
                f"{count}"
            )

            if count <= 0:

                raise AssertionError(
                    f"CCTV {cctv_id}에서 "
                    "Frame이 생성되지 않았습니다."
                )

        print()

        print(
            "=" * 70
        )

        print(
            "[SUCCESS] "
            "CaptureWorkerManager "
            "Multi-CCTV "
            "start / sync / stop / restart "
            "테스트 정상"
        )

        print(
            "=" * 70
        )

    finally:

        # 테스트 중간에 Assertion이 나더라도
        # Thread가 남지 않도록 보장한다.
        try:

            manager.stop_all()

        except Exception as exc:

            print(
                "[CLEANUP WARNING] "
                f"{exc}"
            )


if __name__ == "__main__":
    main()