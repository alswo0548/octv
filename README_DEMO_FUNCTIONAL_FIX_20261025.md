# OCTV 2026-10-25 기능 보완 — PR #69 후속

## 범위
- 관리자 웹: 상단 헤더 알림 고정, 사건 숨김 버튼을 오탐 옆으로 이동, 계산 근거 JSON 접기 두 개 제거, LLM 설명 요청 버튼
- 승인 DEMO v5 3대: 기존 위험도 Rule을 **가상 Context에 다시 적용**해 시연용 점수 85(P1) / 55(P2) / 40(P2) 구성
- 실측 Context 조회와 저장은 그대로 진행. `risk_breakdown_json.context_snapshot`에는 **실제 API 관측 상태**를 보존하며, `demo_simulation.inputs`는 **가상 입력**으로 별도 저장
- UTIC/팀원 탐지·사건화 원본/FCM/DB 스키마/기존 사건 미변경

## 주의
- 가상 위험도는 실제 점수가 아닙니다. 사건 상세의 위험도 카드 하단에 시연 전용으로 명시합니다. 운영 판단이나 기관 전달에 쓰지 마세요.
- N003 40점은 기존 Rule에 따라 P2입니다. 40점 P3 변경은 하지 않습니다.
- 분석 완료 후에는 기존 incident_assessments를 자동 덮어쓰지 않습니다. **새로 시작한 시연에서 신규 사건만** 점수가 달라집니다.
- 기존 숨김은 세션 단위이며 재로그인 시 복원됩니다. 영구 삭제나 FK 변경 없음.
- LLM은 사용자 클릭 시에만 실제 OpenAI 채팅 API 호출. 점수/위험도/우선순위 결정을 절대 맡기지 않습니다.

## 수동 설정 (backend/.env — 절대 Git에 커밋 금지)
```ini
OCTV_DEMO_SCENARIO_RISK_ENABLED=1
OCTV_LLM_API_KEY=발급받은_API키
OCTV_LLM_MODEL=gpt-4o-mini
```
- `OCTV_LLM_API_KEY`와 `OCTV_LLM_MODEL` 중 하나라도 비어 있으면 `NOT_CONFIGURED` 안내 표시. 실제 LLM 성공 판정 금지.
- FastAPI v5 및 Celery **모두 재시작**, 웹은 Vite 자동 갱신. CCTV Runtime은 모델 코드 불변이나 시연 시작 전 재시작 권장.
- 이미 열린 Demo가 있다면 정상 종료 후 재시작; Redis 작업 잔여/UTIC 감시 상태 확인.
- 시연 `start` 시 자동 매핑 준비는 기존 사전 패치 유지. 수위/교통이 근거 없이 수집됨으로 바뀌지 않습니다.

## 검증
- 다음 테스트는 기능 구현 검증용. 실제 DB+외부 API+LLM 인증 호출은 사용자 PC에서 확인해야 합니다.
- Python 컴파일 / TypeScript 타입 검사 / patch apply 검사를 통과한 경우에만 적용합니다.
