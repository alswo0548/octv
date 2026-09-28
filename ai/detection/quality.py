"""영상 품질 검사 작업 위치."""

from ..contracts import Frame


def check_quality(frame: Frame) -> dict:
    # TODO: 흐림·암전·안개·역광 기준을 정하고 저품질이면 분석 보류 결과를 반환하세요.
    raise NotImplementedError("영상 품질 검사 구현 예정")
