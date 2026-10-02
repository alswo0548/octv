# 최종 ERD와 UNIQUE 기준

새 첨부 ERD를 기준으로 테이블 13개·컬럼 123개·FK 19개를 유지합니다.
직전 전달본에서 사건 FALSE_POSITIVE, 기관추천 COMPLETED, incident_contexts.captured_at NOT NULL을 수정했습니다.
ERD.png와 확대 가능한 ERD.svg는 같은 정의를 표시하며, 파란 U 표시는 아래 규칙입니다.

| 표시 | 테이블 | UNIQUE 대상 | 저장 기준 |
|---|---|---|---|
| U1 | users | lower(btrim(email)) | 이메일 앞뒤 공백·대소문자를 무시한 동일 계정 중복 방지 |
| U2 | cctvs | provider + external_cctv_id | 제공기관별 외부 CCTV 중복 수집 방지 |
| U3 | incidents | incident_no | 사건 번호 중복 방지 |
| U4 | incidents | cctv_id + hazard_type + dedup_key | DETECTED/CONFIRMED/SENT인 진행 사건에만 적용 |
| U5 | weather_alerts | external_alert_id + region_code | 같은 외부 특보의 같은 지역 중복 수집 방지 |
| U6 | incident_agency_recommendations | incident_id + agency_id | 사건·기관별 현재 추천 1행, 재평가는 기존 행 갱신 |
| U7 | notifications | agency_recommendation_id + user_id | 동일 기관추천 전달을 사용자별로 1회 기록 |

U1과 U4는 PostgreSQL UNIQUE 인덱스입니다. 나머지 5개는 일반 UNIQUE 제약입니다.
PK 13개는 원래부터 고유하므로 중복 UNIQUE를 추가하지 않았습니다.

## 업무 코드가 지킬 저장 계약

- 회원가입·로그인·중복 확인은 동일하게 lower(btrim(email)) 기준을 사용합니다. 이번 작업은 저장 제약까지이며 인증은 후속 구현입니다.
- provider는 일관된 제공기관 코드를 씁니다. 같은 외부 CCTV ID라도 제공기관이 다르면 저장 가능합니다.
- dedup_key에는 위치·시간창을 반영합니다. 동일 CCTV·유형·키의 진행 사건은 기존 사건 갱신 대상으로 처리합니다. RESOLVED/FALSE_POSITIVE 행은 키를 점유하지 않으므로 이후 재발을 저장할 수 있습니다. 종결 건을 재개할 때도 충돌 처리가 필요합니다.
- external_alert_id는 단일 특보 원천의 안정적인 식별자로 사용합니다. 같은 발표를 여러 지역에 저장할 수 있습니다. 향후 원천이 여러 개가 되면 source 구분을 포함하는 별도 설계가 필요합니다.
- 기관추천 재계산은 현재 행을 갱신합니다. 변경 이력이 필요하면 이력 모델을 별도로 설계합니다.
- 알림 재시도는 동일 추천·사용자 행을 중복 생성하지 않습니다. 재전달 이벤트별 이력이 필요하면 이벤트 식별자를 추가하는 후속 설계가 필요합니다.

## UNIQUE를 넣지 않은 항목

기관명·전화번호·사용자 이름·좌표는 공유될 수 있습니다.
추천 순위는 동점이 가능하므로 유일하게 제한하지 않습니다.
상황 스냅샷·위험도 평가·경로 후보·지원요청은 재수집·재평가·반복 요청을 막지 않도록 사건 ID 단독 UNIQUE를 넣지 않았습니다.
region.weather_region_code는 여러 지역이 공유할 수 있어 고유값으로 제한하지 않았습니다.

## 기존 데이터 적용

`python scripts/db.py migrate`는 현재 구조 확인 → 전체 백업 → 백업 읽기 확인 → 003 변경 → 구조·UNIQUE 검사 순서입니다.
NULL 수집시각·중복값·알림 관계 오류는 자동 수정하지 않고 중단합니다. 모든 DDL 변경은 한 트랜잭션으로 rollback됩니다.
검증된 백업이 있어야 변경이 시작되며, 현재 구조에서는 재실행해도 ALREADY CURRENT로 종료합니다.

PostgreSQL 17 기준: [표현식 인덱스](https://www.postgresql.org/docs/17/indexes-expressional.html), [부분 UNIQUE 인덱스](https://www.postgresql.org/docs/17/indexes-partial.html).
