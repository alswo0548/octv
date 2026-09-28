"""
기상특보를 수집하여 weather_alerts에 대응시키고 지역별 CCTV에 연결하세요. 해제 후 POST_ALERT 유지 정책을 cctvs 서비스에 전달하세요.
"""

from ..errors import FeatureNotImplemented


def fetch_data(query: dict) -> dict:
    # TODO: 제공자 확정 → 응답 계약 → timeout/재시도/오류 처리 → 값 정규화.
    # 자격증명은 config에서 주입하며 실패를 정상 데이터로 바꾸지 마세요.
    raise FeatureNotImplemented("weather 외부 연동 구현 예정")
