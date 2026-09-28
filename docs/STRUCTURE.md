# 폴더·파일 설명

## 먼저 볼 위치

| 폴더/파일 | 무엇인가 | 언제 수정하나 |
|---|---|---|
| frontend/web | React·Vite 관제 화면 | 웹 UI/API 연결 |
| frontend/mobile | React Native·Expo 현장 화면 | 모바일 UI/API 연결 |
| shared/src/fixtures.json | 두 화면이 함께 쓰는 목업 | 샘플 화면 데이터 변경 |
| shared/src/index.ts / attribution.ts | 공통 타입·화면 목록·CCTV 출처 | 공통 계약/문구 변경 |
| backend/app | FastAPI API·업무 처리 골격 | 서버 기능 개발 |
| ai | 탐지·판단·추천·학습 골격 | AI 기능 개발 |
| database | PostgreSQL 테이블·변경 SQL·ERD 참고 | DB 구조 변경 |
| tests | 서버 기동/미구현 응답, DB 구조 검사 | 기능 구현과 함께 갱신 |
| docs | 개발 기준·구조·DB·출처 4개 안내 | 확정 내용이 바뀔 때만 |
| scripts/start-*.cmd | Windows에서 UI 실행 | 보통 수정 불필요 |
| compose.yaml / .env.example | PostgreSQL 실행/개인 설정 예시 | DB 실행 설정 |
| package.json / package-lock.json | npm 명령/정확한 JS 의존성 | 패키지 변경 시 함께 |
| .nvmrc / .node-version / .python-version | 팀의 Node/Python 버전 | 버전 합의 시 |
| .github | CI 검사·PR/이슈 양식 | 협업 규칙 변경 |
| .gitignore / .gitattributes / .editorconfig / .prettier* | 제외 파일·줄바꿈·코드 형식 | 보통 수정 불필요 |

`__init__.py`는 Python 폴더를 패키지로 만드는 파일입니다. 빈 폴더 유지용 파일이 아닙니다.

## 프론트엔드

- WEB `src/pages/`: Auth(로그인/가입), Overview(관제), Incidents(사건), Routes(경로), Monitor(CCTV), Stats(통계), Settings(설정), Targets(대상 CCTV).
- WEB `components/`: 재사용 UI·기관 선택·영상·지도. `layouts/`: 공통 틀, `routing/`: 이동, `styles/`: 화면 스타일.
- MOBILE `src/screens/`: Auth, Incident, Detail, Notification, Routes, Request, Settings 화면.
- MOBILE `src/navigation/types.ts`: 화면 키. `components/`와 `styles/`: 공통 UI와 테마.
- 각 `App.tsx`: 화면 조립/전환. 각 `assets/`: 현재 UI가 사용하는 영상·이미지·로고.

## 백엔드

`main.py`에서 서버와 기능 라우터를 등록합니다. `config.py`는 환경설정, `dependencies.py`는 인증/권한,
`errors.py`는 미구현 응답, `db/session.py`는 DB 접속 작업 위치입니다.

| 기능 폴더 | 담당 기능 | 주요 DB 테이블 |
|---|---|---|
| auth | 가입·로그인·이메일 확인 | users |
| cctvs | CCTV 조회·감시 상태 | cctvs, weather_alerts |
| incidents | 사건 목록·상세·AI 사건 저장 | incidents, incident_contexts, incident_assessments |
| agencies | 기관·추천 조회·선택 전달 | agencies, incident_agency_recommendations |
| routes | 기관별 후보 경로 조회·저장 | route_evaluations, route_candidates |
| notifications | 사건 전달 알림·읽음 | notifications |
| support_requests | 추가 지원요청 등록·조회 | incident_support_requests |
| settings | 감시 기준·개인 알림 설정 | monitoring_settings, users |
| stats | 기간·유형별 집계 | incidents, cctvs, incident_assessments |
| integrations | 기상·수위·교통·지도/경로·LLM 어댑터 | 상황 스냅샷 등에 변환 |

각 업무 폴더의 `router.py` → `service.py` → `repository.py` 순서로 연결합니다.
`schemas.py`에는 요청/응답 형식을 씁니다. DB 테이블 정의는 SQL 한 곳에서 관리하며 ORM 모델은 아직 도입하지 않았습니다.
`integrations/`의 `weather.py`, `water_level.py`, `traffic.py`, `maps.py`, `llm.py`는 해당 제공자 연동 작업 파일입니다.

## AI

| 위치 | 파일별 작업 |
|---|---|
| contracts.py / config.py | 단계 간 데이터 형식 / 모델·장비·임계값 설정 |
| detection | video.py 프레임 수집, quality.py 품질 검사, detector.py YOLO 추론 |
| incidentization | temporal.py 시간 연속성, deduplication.py 중복 판별 |
| risk_priority/rules.py | 위험도·우선순위 규칙과 근거 |
| agency_recommendation/recommender.py | 후보 기관 순위·추천 근거 |
| route_evaluation/evaluator.py | 기관별 경로 점수·제외 사유 |
| mcp | server.py 도구 등록, tools.py 외부 조회 어댑터 연결 |
| orchestration | state.py 처리 상태, pipeline.py 단계 연결·실패 처리 |
| training | dataset.py 자료/라벨/분할, train.py 학습, evaluate.py 비교·최종 평가 |
| requirements.txt | 현재 추가 패키지 없음. 장비 확인 후 버전 고정 |

함수 본문의 `NotImplementedError`는 작업 위치 표시입니다. 실제 결과를 반환하는 코드로 구현해야 합니다.

## 데이터베이스

`schema.sql`은 실행 순서만 정합니다. `schema/00_types.sql`은 공통 상태 값,
나머지 번호 파일은 지역 → 기관 → 사용자 → CCTV → 설정 → 사건 → 특보 → 상황 → 평가 → 기관추천 → 경로평가 → 후보경로 → 알림 → 지원요청입니다.
각 SQL의 한국어 `COMMENT`가 컬럼 설명입니다. `migrations/`는 기존 DB를 갱신할 SQL입니다.
`ERD.png`는 초기 관계 참고용이며 최신 정의는 SQL과 [DB 안내](DATABASE.md)를 우선합니다.
