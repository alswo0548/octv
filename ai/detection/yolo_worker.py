"""분석 Frame Queue를 소비하고 detector를 실행하는 YOLO Worker."""

import time
from dataclasses import dataclass
from threading import Event
from typing import Callable

from ..contracts import Detection, Frame
from .frame_queue import AnalysisFrameQueue


@dataclass(frozen=True)
class YoloPerformance:
    """
    Frame 한 장의 YOLO 처리 성능 정보.
    """

    queue_wait_sec: float
    inference_sec: float
    total_latency_sec: float


class YoloWorker:
    """
    분석용 RAM Queue에서 Frame을 하나씩 꺼내
    detector 함수에 전달한다.

    하나의 Worker가 여러 CCTV Frame을 처리할 수 있으므로
    분석 상태는 CCTV별로 관리한다.
    """

    def __init__(
        self,
        frame_queue: AnalysisFrameQueue,
        detect_fn: Callable[
            [Frame],
            list[Detection],
        ],
        poll_interval_sec: float = 0.1,
    ):
        if poll_interval_sec <= 0:
            raise ValueError(
                "poll_interval_sec은 0보다 커야 합니다."
            )

        self.frame_queue = frame_queue
        self.detect_fn = detect_fn
        self.poll_interval_sec = poll_interval_sec

        self._stop_event = Event()

        # CCTV별 마지막으로 알린 분석 상태
        # 같은 상태를 매 Frame마다 반복 저장하지 않기 위해 사용
        self._status_by_cctv: dict[int, str] = {}

        # Worker가 실제로 처리한 CCTV 목록
        self._seen_cctv_ids: set[int] = set()

    def stop(self) -> None:
        """YOLO Worker 종료 요청."""

        self._stop_event.set()

    def run(
        self,
        on_result: Callable[
            [
                Frame,
                list[Detection],
                YoloPerformance,
            ],
            None,
        ]
        | None = None,
        on_status: Callable[
            [int, str],
            None,
        ]
        | None = None,
    ) -> None:
        """
        Queue에서 Frame을 계속 꺼내
        detector를 실행한다.

        on_status:
        - CCTV별 분석 상태가 변경될 때 호출
        - RUNNING
        - ERROR
        - STOPPED
        """

        print("[YOLO WORKER] 시작")

        self._status_by_cctv.clear()
        self._seen_cctv_ids.clear()

        worker_failed = False

        try:
            while not self._stop_event.is_set():

                queued_frame = (
                    self.frame_queue.get(
                        timeout_sec=(
                            self.poll_interval_sec
                        )
                    )
                )

                if queued_frame is None:
                    continue

                frame = queued_frame.frame

                self._seen_cctv_ids.add(
                    frame.cctv_id
                )

                # -----------------------------------------
                # Queue 대기시간
                # -----------------------------------------

                inference_started_at = (
                    time.monotonic()
                )

                queue_wait_sec = (
                    inference_started_at
                    - queued_frame.enqueued_at_monotonic
                )

                print(
                    f"[YOLO WORKER] 분석 시작 "
                    f"/ cctv={frame.cctv_id} "
                    f"/ captured_at={frame.captured_at}"
                )

                # -----------------------------------------
                # 실제 YOLO 추론
                # -----------------------------------------

                try:
                    detections = (
                        self.detect_fn(
                            frame
                        )
                    )

                except Exception as exc:
                    print(
                        f"[YOLO WORKER] 분석 실패 "
                        f"/ cctv={frame.cctv_id} "
                        f"/ error={exc}"
                    )

                    self._notify_status(
                        on_status=on_status,
                        cctv_id=frame.cctv_id,
                        status="ERROR",
                    )

                    continue

                # -----------------------------------------
                # 추론 성공
                #
                # 첫 성공 또는 ERROR에서 복구된 경우에만
                # RUNNING 상태 callback이 실제 호출된다.
                # -----------------------------------------

                self._notify_status(
                    on_status=on_status,
                    cctv_id=frame.cctv_id,
                    status="RUNNING",
                )

                inference_finished_at = (
                    time.monotonic()
                )

                inference_sec = (
                    inference_finished_at
                    - inference_started_at
                )

                # Queue에 들어간 순간부터
                # Detection 결과 생성까지 걸린 전체 시간
                total_latency_sec = (
                    inference_finished_at
                    - queued_frame.enqueued_at_monotonic
                )

                performance = YoloPerformance(
                    queue_wait_sec=queue_wait_sec,
                    inference_sec=inference_sec,
                    total_latency_sec=(
                        total_latency_sec
                    ),
                )

                print(
                    f"[YOLO WORKER] 분석 완료 "
                    f"/ cctv={frame.cctv_id} "
                    f"/ detections={len(detections)}"
                )

                print(
                    f"[YOLO PERF] "
                    f"cctv={frame.cctv_id} "
                    f"/ queue_wait="
                    f"{queue_wait_sec:.4f}s "
                    f"/ inference="
                    f"{inference_sec:.4f}s "
                    f"/ total="
                    f"{total_latency_sec:.4f}s"
                )

                if on_result is not None:
                    on_result(
                        frame,
                        detections,
                        performance,
                    )

        except Exception as exc:
            worker_failed = True

            print(
                f"[YOLO WORKER] 치명적 오류: {exc}"
            )

            # Worker 자체가 예상치 못하게 죽는 경우
            # 지금까지 처리하던 CCTV는 ERROR로 표시
            for cctv_id in self._seen_cctv_ids:
                self._notify_status(
                    on_status=on_status,
                    cctv_id=cctv_id,
                    status="ERROR",
                )

            raise

        finally:
            # 정상적인 stop 요청에 의한 종료라면
            # 지금까지 분석했던 CCTV를 STOPPED 처리
            if not worker_failed:
                for cctv_id in self._seen_cctv_ids:
                    self._notify_status(
                        on_status=on_status,
                        cctv_id=cctv_id,
                        status="STOPPED",
                    )

            print(
                "[YOLO WORKER] 종료"
            )

    def _notify_status(
        self,
        on_status: Callable[
            [int, str],
            None,
        ]
        | None,
        cctv_id: int,
        status: str,
    ) -> None:
        """
        CCTV별 분석 상태 변경을 외부에 알린다.

        같은 상태는 반복해서 알리지 않는다.
        DB 저장 등은 외부 callback에서 담당한다.
        """

        previous_status = (
            self._status_by_cctv.get(
                cctv_id
            )
        )

        if previous_status == status:
            return

        if on_status is None:
            self._status_by_cctv[
                cctv_id
            ] = status

            return

        try:
            on_status(
                cctv_id,
                status,
            )

        except Exception as exc:
            print(
                f"[YOLO WORKER] "
                f"상태 callback 실패 "
                f"/ cctv={cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

            return

        self._status_by_cctv[
            cctv_id
        ] = status