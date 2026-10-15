import time
from datetime import datetime
from threading import Condition, Thread
from zoneinfo import ZoneInfo

import numpy as np

from ai.contracts import Frame
from ai.detection.frame_queue import AnalysisFrameQueue
from ai.detection.yolo_worker import YoloWorker

from backend.app.cctvs.repository import (
    list_monitored_utic_cctvs,
    update_analysis_status,
)
from backend.app.db.session import get_connection


KST = ZoneInfo("Asia/Seoul")


def main() -> None:
    print("=" * 70)
    print("OCTV YOLO ANALYSIS STATUS TEST")
    print("=" * 70)

    # =====================================================
    # 1. DB에서 테스트할 CCTV 조회
    # =====================================================

    with get_connection() as connection:
        cctvs = list_monitored_utic_cctvs(
            connection
        )

    if not cctvs:
        raise RuntimeError(
            "감시 대상 UTIC CCTV가 없습니다."
        )

    cctv = cctvs[0]
    cctv_id = cctv["id"]

    print()
    print(
        f"CCTV ID          : {cctv_id}"
    )
    print(
        f"External CCTV ID : "
        f"{cctv['external_cctv_id']}"
    )
    print(
        f"현재 분석 상태   : "
        f"{cctv['analysis_status']}"
    )

    # =====================================================
    # 2. Queue
    # =====================================================

    frame_queue = AnalysisFrameQueue(
        maxsize=4
    )

    # =====================================================
    # 3. 가짜 detector
    #
    # 1번째 호출 → 성공
    # 2번째 호출 → 강제 실패
    # 3번째 호출 → 다시 성공
    # =====================================================

    detect_call_count = 0

    def fake_detect(frame: Frame):
        nonlocal detect_call_count

        detect_call_count += 1

        print(
            f"[FAKE DETECTOR] "
            f"호출 #{detect_call_count}"
        )

        if detect_call_count == 2:
            raise RuntimeError(
                "테스트용 강제 YOLO 실패"
            )

        return []

    # =====================================================
    # 4. 상태 callback
    # =====================================================

    status_history: list[str] = []

    condition = Condition()

    def handle_status(
        status_cctv_id: int,
        status: str,
    ) -> None:
        print(
            f"[DB ANALYSIS STATUS] "
            f"CCTV {status_cctv_id} "
            f"→ {status}"
        )

        with get_connection() as connection:
            update_analysis_status(
                connection,
                status_cctv_id,
                status,
            )

        with condition:
            status_history.append(
                status
            )

            condition.notify_all()

    # =====================================================
    # 상태가 실제 callback될 때까지 대기
    # =====================================================

    def wait_for_history(
        expected: list[str],
        timeout_sec: float = 5.0,
    ) -> None:
        deadline = (
            time.monotonic()
            + timeout_sec
        )

        with condition:
            while len(status_history) < len(expected):

                remaining = (
                    deadline
                    - time.monotonic()
                )

                if remaining <= 0:
                    raise TimeoutError(
                        "상태 변경 대기시간을 초과했습니다. "
                        f"expected={expected}, "
                        f"actual={status_history}"
                    )

                condition.wait(
                    timeout=remaining
                )

        actual = (
            status_history[
                :len(expected)
            ]
        )

        if actual != expected:
            raise AssertionError(
                f"상태 순서가 다릅니다. "
                f"expected={expected}, "
                f"actual={actual}"
            )

    # =====================================================
    # Frame 생성
    # =====================================================

    def make_frame() -> Frame:
        return Frame(
            cctv_id=cctv_id,
            captured_at=datetime.now(
                KST
            ),
            image=np.zeros(
                (
                    64,
                    64,
                    3,
                ),
                dtype=np.uint8,
            ),
        )

    # =====================================================
    # 5. YOLO Worker
    # =====================================================

    worker = YoloWorker(
        frame_queue=frame_queue,
        detect_fn=fake_detect,
        poll_interval_sec=0.05,
    )

    worker_thread = Thread(
        target=worker.run,
        kwargs={
            "on_status":
                handle_status,
        },
        name="yolo-status-test",
    )

    print()
    print("[1] YOLO Worker 시작")

    worker_thread.start()

    try:
        # -------------------------------------------------
        # 첫 번째 Frame
        # 성공 → RUNNING
        # -------------------------------------------------

        print()
        print(
            "[2] 성공 Frame 입력"
        )

        frame_queue.put_latest(
            make_frame()
        )

        wait_for_history(
            [
                "RUNNING",
            ]
        )

        # -------------------------------------------------
        # 두 번째 Frame
        # 강제 실패 → ERROR
        # -------------------------------------------------

        print()
        print(
            "[3] 실패 Frame 입력"
        )

        frame_queue.put_latest(
            make_frame()
        )

        wait_for_history(
            [
                "RUNNING",
                "ERROR",
            ]
        )

        # -------------------------------------------------
        # 세 번째 Frame
        # 다시 성공 → RUNNING
        # -------------------------------------------------

        print()
        print(
            "[4] 복구 Frame 입력"
        )

        frame_queue.put_latest(
            make_frame()
        )

        wait_for_history(
            [
                "RUNNING",
                "ERROR",
                "RUNNING",
            ]
        )

    finally:
        # -------------------------------------------------
        # Worker 종료 → STOPPED
        # -------------------------------------------------

        print()
        print(
            "[5] YOLO Worker 종료 요청"
        )

        worker.stop()

        worker_thread.join(
            timeout=5
        )

    if worker_thread.is_alive():
        raise RuntimeError(
            "YOLO Worker가 정상 종료되지 않았습니다."
        )

    wait_for_history(
        [
            "RUNNING",
            "ERROR",
            "RUNNING",
            "STOPPED",
        ]
    )

    # =====================================================
    # 6. 최종 DB 상태 확인
    # =====================================================

    with get_connection() as connection:
        cctvs = list_monitored_utic_cctvs(
            connection
        )

    final_cctv = next(
        row
        for row in cctvs
        if row["id"] == cctv_id
    )

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)

    print(
        f"Detector 호출 수 : "
        f"{detect_call_count}"
    )

    print(
        f"상태 변경 이력   : "
        f"{' → '.join(status_history)}"
    )

    print(
        f"최종 DB 상태     : "
        f"{final_cctv['analysis_status']}"
    )

    expected_history = [
        "RUNNING",
        "ERROR",
        "RUNNING",
        "STOPPED",
    ]

    if status_history != expected_history:
        raise AssertionError(
            f"예상 상태 이력과 다릅니다. "
            f"expected={expected_history}, "
            f"actual={status_history}"
        )

    if (
        final_cctv["analysis_status"]
        != "STOPPED"
    ):
        raise AssertionError(
            "최종 analysis_status가 "
            "STOPPED가 아닙니다."
        )

    print()
    print(
        "[SUCCESS] "
        "RUNNING → ERROR → "
        "RUNNING → STOPPED "
        "DB 연동 정상"
    )


if __name__ == "__main__":
    main()