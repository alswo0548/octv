"""
state.py / config.py / nodes.py / analysis_storage.py 를 하나의 LangGraph 로 연결하는 파일
nodes.py 에서의 7개의 실행 노드를 어느 노드부터 시작하고, 어떤 순서로 실행하며, 언제 종료할지 지정.

정리
- state.py      : 노드끼리 주고받을 데이터 보관
- nodes.py      : 각 단계에서 실행할 실제 작업 정의
- pipeline.py   : 노드들의 실행 순서와 종료 조건 결정
"""

from .nodes import create_nodes
from .state import PipelineState, create_state


# 실행 설정은 노드의 클로저에 보관하며, 그래프 상태에는 인증정보를 넣지 않습니다.
def build_graph(config: dict):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(PipelineState) # LangGraph의 기본 틀 생성
    nodes = create_nodes(config) # 7개의 노드를 딕셔너리로 가지고옴
    for name, node in nodes.items():
        graph.add_node(name, node)
    graph.add_edge(START, 'load_incident')
    graph.add_conditional_edges(
        'load_incident',
        lambda state: 'stop' if state['result'] else 'continue',
        {'stop': END, 'continue': 'collect_context'},
    )
    sequence = (
        'collect_context', 'assess_risk', 'select_agencies',
        'evaluate_routes', 'finalize_agencies', 'save_results',
    )
    for current, following in zip(sequence, sequence[1:]):
        graph.add_edge(current, following)
    graph.add_edge('save_results', END)
    return graph.compile()


# 실제로 LangGraph를 실행하는 함수.
def run_pipeline(incident_id: int, config: dict | None = None) -> dict:
    # 초기 State 생성
    state = create_state(incident_id)
    # 실행 설정 준비
    if config is None:
        from ..config import get_runtime_config
        config = get_runtime_config()
    # LangGraph 실제 실행
    output = build_graph(config).invoke(state)
    # Celery에는 datetime·ContextSnapshot 대신 JSON으로 직렬화 가능한 요약만 반환합니다.
    return output['result']
