# 기능 인수인계

로그인·회원가입을 포함한 실제 기능은 모두 팀 구현 영역이다.

| 영역 | 완성 UI | 미구현 / 작성 위치 |
|---|---|---|
| 인증 | 입력·가입 단계·고정 완료 예시 | 검증·계정·해시·JWT·권한: backend/app/auth |
| 사건 | 목록·목업 상세·영상 탭 | 조회·검색·필터·상태 변경: backend/app/incidents |
| 탐지·사건화 | 탐지 박스 시각 연출 | AI 영상·후보·중복·확정: ai/detection, ai/incidentization |
| 위험도·우선순위 | 고정 점수·근거 | 산정·저장: ai/risk_priority |
| 기관 | 체크와 경로 조회 독립 | 추천·전달 처리: ai/agency_recommendation, backend/app/agencies |
| 경로 | 기관별 A/B/C·강조·평가값 | 후보 생성·평가·지도: backend/app/routes, ai/route_evaluation |
| CCTV | 선택·연결/활성 상태 구분 | 스트림·재연결: backend/app/cctvs |
| 통계 | 탐지 신뢰도 목업 차트 | 기간/지역 집계: backend/app/incidents |
| 알림 | 사건 전달 목록·상세 이동 | 발송·수신·읽음: backend/app/notifications |
| 설정 | 입력·토글·확인창 | 설정 저장·적용: backend/app/settings |
| 추가 요청 | 유형·내용 입력·확인창 | 요청 제출·조회: backend/app/support_requests |
| 외부/AI | 없음 | backend/app/integrations, ai/orchestration, ai/mcp |
| DB | 구조 생성 SQL | 연결·ORM·CRUD: backend/app/db |

## 연결 지점
- 화면 파일은 `SCREENS.md`에서 찾는다. 실제 연동 시작 전 해당 화면의 shared 목업 사용을 교체한다.
- 사건: incident_no, cctv_id, hazard_type, confidence, status + 별도 평가/외부 상황 데이터.
- 기관: 사건별 recommendation ID, agency ID, 추천 순위. 조회 기관과 전달 대상 배열을 구분한다.
- 경로: agency_recommendation_id → route_evaluations.id → route_candidates.route_evaluation_id.
- 알림: notifications.incidents_id / route_evaluation_id / agency_id / user_id.
- 모바일의 화면 상태는 `App.tsx`, 라우트 타입은 `src/navigation/types.ts`. 외부 인증 가드는 아직 없다.

목업 가공 필드: riskLabel, reasons, camera 표시명, minutes, distance, verdict, mapPaths 등.
이 값은 SQL 컬럼/단위와 직접 일치하지 않는다. API 계약을 합의한 뒤 변환 책임을 정한다.
