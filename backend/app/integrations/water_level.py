"""수위 관측소·단위·수집 시각을 정규화하여 incident_contexts.water_level_m에 전달하세요."""

from ..errors import FeatureNotImplemented


def fetch_data(query: dict) -> dict:
    # TODO: 제공자 확정 → 응답 계약 → timeout/재시도/오류 처리 → 값 정규화.
    # 자격증명은 config에서 주입하며 실패를 정상 데이터로 바꾸지 마세요.
    raise FeatureNotImplemented("water_level 외부 연동 구현 예정")
