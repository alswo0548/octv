"""영상 입력·재연결·프레임 수집 작업 위치."""

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

import cv2

from ..contracts import Frame


class VideoSource:
    """
    하나의 CCTV 영상 source 연결을 관리한다.

    VideoCapture 연결을 한 번 열고 유지하면서
    프레임을 연속으로 읽는다.
    """

    def __init__(self, cctv_id: int, stream_url: str):
        self.cctv_id = cctv_id
        self.stream_url = stream_url
        self.cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        """영상 source에 연결한다."""

        if self.cap is not None:
            self.close()

        self.cap = cv2.VideoCapture(self.stream_url)

        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None

            raise ConnectionError(
                f"영상 source에 연결할 수 없습니다: {self.stream_url}"
            )

    def read(self) -> Frame | None:
        """
        현재 연결에서 프레임 1장을 읽는다.

        정상 프레임이면 Frame을 반환하고,
        영상 종료 또는 프레임 수신 실패 시 None을 반환한다.
        """

        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError(
                "영상 source가 연결되어 있지 않습니다. "
                "open()을 먼저 호출하세요."
            )

        success, image = self.cap.read()

        if not success or image is None:
            return None

        return Frame(
            cctv_id=self.cctv_id,
            captured_at=datetime.now(KST),
            image=image,
        )


    def get_fps(self) -> float:
        """현재 영상 source의 FPS를 반환한다."""

        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError(
                "영상 source가 연결되어 있지 않습니다. "
                "open()을 먼저 호출하세요."
            )

        fps = self.cap.get(cv2.CAP_PROP_FPS)

        if fps <= 0:
            return 30.0

        return fps


    def close(self) -> None:
        """영상 source 연결을 종료한다."""

        if self.cap is not None:
            self.cap.release()
            self.cap = None