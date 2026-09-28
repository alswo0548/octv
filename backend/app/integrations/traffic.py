"""교통 혼잡·도로 통제의 출처와 수집 시각을 보존하여 상황/경로 평가에 전달하세요."""

from ..errors import FeatureNotImplemented


def fetch_data(query: dict) -> dict:
    # TODO: 제공자 확정 → 응답 계약 → timeout/재시도/오류 처리 → 값 정규화.
    # 자격증명은 config에서 주입하며 실패를 정상 데이터로 바꾸지 마세요.
    raise FeatureNotImplemented("traffic 외부 연동 구현 예정")
