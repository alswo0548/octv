"""CCTV별 최신 Frame을 RAM에 보관하는 버퍼."""

from threading import Lock

from ..contracts import Frame


class LatestFrameStore:
    """
    CCTV별 가장 최신 Frame 한 장만 보관한다.

    새 Frame이 들어오면 이전 Frame을 교체한다.
    여러 Capture Thread에서 동시에 접근할 수 있도록 Lock을 사용한다.
    """
    # Lock은 여러 Thread가 같은 데이터를 동시에 읽거나 수정하려고 할 때, 한 번에 하나의 Thread만 접근하게 해서 데이터 충돌을 막아주는 장치
    # 한 Thread의 작업이 끝난 뒤 다음 Thread가 접근하도록 순서를 보장해줌
    # CCTV 수신 Thread, YOLO Thread, 스트리밍 Thread 등이 같은 최신 Frame 저장소를 동시에 사용할 수 있으므로,
    # Frame을 읽고 쓰는 순간 서로 충돌하지 않도록 보호하기 위해 사용한다.

    def __init__(self):
        self._frames: dict[int, Frame] = {}
        # dict[int, Frame]은 CCTV ID → 그 CCTV의 최신 Frame 형태로 관리하기 위해 사용하는 구조
        self._lock = Lock()

    def update(self, frame: Frame) -> None:
        """해당 CCTV의 최신 Frame을 갱신한다."""

        with self._lock:
            self._frames[frame.cctv_id] = frame

    def get(self, cctv_id: int) -> Frame | None:
        """해당 CCTV의 최신 Frame을 반환한다."""

        with self._lock:
            return self._frames.get(cctv_id)

    def remove(self, cctv_id: int) -> None:
        """해당 CCTV의 최신 Frame을 제거한다."""

        with self._lock:
            self._frames.pop(cctv_id, None)

    def cctv_ids(self) -> list[int]:
        """현재 Frame이 저장된 CCTV ID 목록을 반환한다."""

        with self._lock:
            return list(self._frames.keys())