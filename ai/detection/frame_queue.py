"""YOLO 분석 대기 Frame을 보관하는 작은 RAM Queue."""

import time
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Lock

from ..contracts import Frame


@dataclass(frozen=True)
class QueuedFrame:
    """
    분석 Queue에 들어간 Frame과
    Queue 진입 시각을 함께 보관한다.
    """

    frame: Frame
    enqueued_at_monotonic: float


class AnalysisFrameQueue:
    """
    YOLO 분석을 기다리는 Frame을 RAM에 제한된 개수만 보관한다.

    Queue가 가득 찬 경우:
    - 가장 오래된 Frame 제거
    - 가장 최신 Frame 추가

    오래된 CCTV 영상 분석이 계속 밀리는 것을 방지한다.
    """

    def __init__(
        self,
        maxsize: int = 4,
    ):
        if maxsize <= 0:
            raise ValueError(
                "maxsize는 0보다 커야 합니다."
            )

        self._queue: Queue[QueuedFrame] = Queue(
            maxsize=maxsize
        )

        # 여러 Capture Thread가 동시에
        # "확인 → 제거 → 추가" 작업을 하지 않도록 보호
        self._put_lock = Lock()

    def put_latest(
        self,
        frame: Frame,
    ) -> Frame | None:
        """
        분석용 Frame을 Queue에 넣는다.

        Queue가 가득 차 있으면 가장 오래된 Frame을 제거한 뒤
        최신 Frame을 넣는다.

        제거된 Frame이 있으면 반환하고,
        없으면 None을 반환한다.
        """

        queued_frame = QueuedFrame(
            frame=frame,
            enqueued_at_monotonic=time.monotonic(),
        )

        dropped_frame = None

        with self._put_lock:
            try:
                self._queue.put_nowait(
                    queued_frame
                )

            except Full:
                try:
                    dropped_item = (
                        self._queue.get_nowait()
                    )

                    dropped_frame = (
                        dropped_item.frame
                    )

                except Empty:
                    dropped_frame = None

                self._queue.put_nowait(
                    queued_frame
                )

        return dropped_frame

    def get(
        self,
        timeout_sec: float = 0.1,
    ) -> QueuedFrame | None:
        """
        가장 오래 기다린 분석용 Frame을 하나 꺼낸다.

        timeout_sec 동안 Frame이 들어오지 않으면
        None을 반환한다.
        """

        try:
            return self._queue.get(
                timeout=timeout_sec
            )

        except Empty:
            return None

    def size(self) -> int:
        """현재 Queue 대기 Frame 수."""

        return self._queue.qsize()

    def empty(self) -> bool:
        """Queue가 비어 있는지 반환."""

        return self._queue.empty()