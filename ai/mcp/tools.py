
"""
MCP에서 사건의 외부 상황 정보를 조회하기 위한 함수

주요 기능
1. AI 실행 환경 설정 가져오기
2. 사건 ID를 이용해 Context 수집하여 기상·수위·교통 데이터를 통합하여 반환하여 AI 위험도 판단에 필요한 ContextSnapshot 전달

※ 외부 API 호출과 데이터 통합은
   backend/app/integrations/context.py 의 collect_context() 함수에서 수행
"""

from ai.contracts import ContextSnapshot
from ai.config import get_runtime_config
from backend.app.integrations.context import collect_context

# 사건 ID를 전달받아 외부 상황 정보를 조회하는 함수
def query_context(incident_id: int) -> ContextSnapshot:
    config = get_runtime_config()

    # collect_context()가 DB 사건 조회,
    # 기상·수위·교통 데이터 수집 및 통합 수행
    return collect_context(
        incident_id,
        config['query_factory']
    )
