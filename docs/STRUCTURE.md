# 폴더 구조 핵심 안내

DB는 PostgreSQL 하나입니다. 기능별로 나누는 것은 SQL과 조회·저장 코드이며 실제 데이터는 Docker 볼륨에 보관합니다.

| 위치 | 역할 |
|---|---|
| frontend/web | 기존 React 관제 웹과 이미지·영상 |
| frontend/mobile | 기존 Expo 모바일 목업과 자산 |
| shared/src | 공통 타입·화면용 목업 데이터 |
| backend/app | 기능별 API·업무 처리·DB 접근 |
| backend/app/db | 공통 연결 session.py와 공유 sql/region.sql |
| ai | 기존 탐지·사건화·판단·학습 골격 |
| database | 초기화 순서 schema.sql, init/ 진입 파일, migrations/, ERD.png |
| scripts | CMD 실행 도우미, DB 확인·백업·변경 도우미 |
| tests | 백엔드 기동 검사와 database_contract.sql 구조 검사 |
| docs | 안내서·변경 사항·검증 결과 |

## 기능 안에서 수정할 파일

기준 경로: backend/app/기능명/

| 파일 | 수정 대상 |
|---|---|
| router.py | API 주소와 HTTP 요청 연결 |
| schemas.py | API 요청·응답 데이터 형식. DB 테이블을 만들지 않음 |
| service.py | 기능 규칙, 처리 순서와 트랜잭션 범위 |
| repository.py | psycopg 연결로 실행할 조회·저장 SQL |
| sql/*.sql | 해당 기능 테이블 생성 정의와 전용 ENUM |

SQL 정의 원본은 한 곳에서만 관리합니다. ORM은 도입하지 않았습니다.
repository와 업무 service는 아직 대부분 501 미구현 골격입니다.

## 기능별 SQL 소유 위치

| 기능 | 테이블 정의 |
|---|---|
| db/sql | region |
| auth/sql | users 및 역할 ENUM |
| agencies/sql | agencies, incident_agency_recommendations 및 ENUM |
| cctvs/sql | cctvs, weather_alerts 및 ENUM |
| settings/sql | monitoring_settings |
| incidents/sql | incidents, incident_contexts, incident_assessments 및 사건 ENUM |
| routes/sql | route_candidates |
| notifications/sql | notifications |
| support_requests/sql | incident_support_requests 및 요청 유형 ENUM |

stats는 기존 테이블을 조회하므로 별도 테이블 SQL을 만들지 않습니다.
공통 초기화는 database/schema.sql이 ENUM → 참조 대상 → 참조하는 테이블 순으로 불러옵니다.
기존 DB 변경은 database/migrations/에서 관리합니다.

## 사건 기능 작업 예시

backend/app/incidents/router.py에서 요청을 확인하고 schemas.py의 입력·출력을 맞춥니다.
service.py에서 처리 규칙을 작성하고 repository.py에서 파라미터 바인딩 SQL을 작성합니다.
DB 컬럼을 확인할 때 sql/incidents.sql을 봅니다. 외부 상황·평가는 같은 sql/의 별도 파일입니다.
실제 테이블 변경이 필요하면 기능 SQL과 기존 DB용 변경 SQL을 함께 관리합니다.
이번에 공통 연결은 실행 가능하게 만들었지만 사건 CRUD는 구현하지 않았습니다.

## 기존 프로젝트에 반영

개인 .env, 미커밋 코드, .venv, node_modules, 데이터·가중치는 보존합니다.
ZIP을 별도 폴더에 풀어 비교한 뒤 필요한 파일을 반영하세요.
기존 database/schema/는 이동이 끝난 옛 경로입니다. 개인 수정분을 먼저 대조·반영한 뒤 그 폴더만 제거합니다.
database/schema.sql은 새 초기화 진입점으로 교체하며 migrations/001_post_alert.sql은 이력으로 유지합니다.
자세한 변경과 확인 사항은 CHANGES.md를 봅니다.
