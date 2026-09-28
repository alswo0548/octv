"""YOLO 모델 로딩·추론 작업 위치."""

from ..contracts import Frame, Detection


def detect(frame: Frame) -> list[Detection]:
    # TODO: 가중치 로딩·전처리·추론·후처리와 모델 버전을 구현하세요. 실패를 탐지 없음으로 바꾸지 마세요.
    raise NotImplementedError("YOLO 모델 로딩·추론 구현 예정")
