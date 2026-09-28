"""영상 입력·재연결·프레임 수집 작업 위치."""

from ..contracts import Frame


def read_frame(cctv_id: int, stream_url: str) -> Frame:
    # TODO: OpenCV 연결, timeout/재연결, 수집 간격, 캡처 시각을 구현하세요. 연결 실패와 정상 프레임을 구분하세요.
    raise NotImplementedError("영상 입력·재연결·프레임 수집 구현 예정")
