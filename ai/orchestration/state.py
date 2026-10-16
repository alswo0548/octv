"""
LangGraph가 실행되는 동안 사건 정보와 각 단계의 계산 결과를 공유할 데이터 구조를 정의

state가 채워지는 과정
- 사건 ID = 31 
- 판단 진행 (사건 정보 + Context + 위험도 + 기관 + 경로)
- 판단 완료 (기관 최종 추천 결과 + DB 저장 결과)

전체 코드의 실행 흐름
workers.py의 analyze_incident() → pipeline.py의 run_pipeline() → state.py의 create_state() → LangGraph 노드 실행
"""

from typing import TypedDict

from ..contracts import ContextSnapshot


# 인증키·API 요청 URL은 상태에 넣지 않습니다. 판단 자료와 결과만 전달.
class PipelineState(TypedDict, total=False):
    incident_id: int                                # 분석 대상 사건이 DB ID
    incident: dict                                  # DB에서 조회한 사건 상세 정보
    context: ContextSnapshot                        # 수집한 날씨, 수위, 교통 등의 외부 상황
    assessment: dict                                # 위험도와 우선순위 계산 결과
    agencies: list[dict]                            # 조회한 기관 정보
    preliminary: list[dict]                         # 경로 평가 전 기관 사전 추천
    routes_by_agency: dict[int, list[dict]]         # 기관 ID별 경로 평가 결과
    route_fetches: dict[int, dict]                  # 기관별 경로 API 조회 상태
    recommendations: list[dict]                     # 경로 접근성을 반영한 최종 기관 추천
    result: dict                                    # 저장 결과 또는 분석 건너뛰기 결과


# pipeline.py에서 사용, LangGraph는 노드가 반환하는 변경 항목을 기존 State에 반영
def create_state(incident_id: int) -> PipelineState:
    if type(incident_id) is not int or incident_id <= 0:
        raise ValueError('incident_id는 양의 정수여야 합니다.')
    return {
        'incident_id': incident_id,
        'preliminary': [],
        'routes_by_agency': {},
        'route_fetches': {},
        'recommendations': [],
        'result': {},
    }
