# DB 사용법 — Windows CMD

Docker Desktop을 실행하고 **프로젝트 루트**에서 진행합니다.
PostgreSQL 17.11, 본인 PC의 `127.0.0.1:5432`, named volume `postgres_data`를 사용합니다.

## 첫 설치

```cmd
if not exist .env copy .env.example .env
notepad .env
```

`POSTGRES_PASSWORD=`에 본인 개발용 비밀번호를 넣고 저장합니다. 기존 `.env`는 덮어쓰지 않습니다.
기본 DB/사용자는 `octv_dev`. 포트 충돌 시 `POSTGRES_PORT=5433`처럼 바꿉니다.

```cmd
docker compose config --quiet
docker compose up -d db
docker compose ps
docker compose logs --tail 50 db
docker compose exec db psql -U octv_dev -d octv_dev -c "\dt"
```

**healthy + 테이블 14개**인지 확인합니다. DB/사용자 이름을 변경했다면 위 `-U`, `-d`도 맞춥니다.
처음 생성한 빈 볼륨에서 `schema.sql`이 `schema/` 파일을 순서대로 한 트랜잭션으로 실행합니다.
실패 시 즉시 중단합니다. 하위 `migrations/`는 자동 실행되지 않습니다.

## 기존 DB를 쓰고 있다면

기존 테이블/데이터는 유지됩니다. SQL 파일 변경이나 컨테이너 재시작만으로 기존 DB가 바뀌지 않습니다.
확정된 감시 정책의 `POST_ALERT`가 없는 DB에는 다음 변경 SQL만 실행합니다.

```cmd
docker compose up -d db
docker compose exec db psql -U octv_dev -d octv_dev -f /docker-entrypoint-initdb.d/migrations/001_post_alert.sql
docker compose exec db psql -U octv_dev -d octv_dev -c "SELECT enum_range(NULL::monitored_mode_enum);"
```

기대값: `{BASE,ALERT,POST_ALERT,VERIFY}`. 반복 실행해도 값이 중복 추가되지 않습니다.
이 SQL은 상태 종류만 추가합니다. 실제 CCTV 상태를 자동 변경하지 않습니다.
기존 DB에 `schema.sql` 전체를 다시 실행하지 마세요.

## 일상 사용

- 종료 `docker compose stop db` / 재시작 `docker compose start db`.
- `docker compose down`은 컨테이너만 정리합니다. **`down -v`는 DB 데이터 삭제**이므로 평소 쓰지 않습니다.
- 초기화 오류가 나면 로그를 먼저 확인합니다. 자동으로 볼륨을 지우지 않습니다.
- `.env`의 비밀번호/사용자 변경은 기존 DB 계정을 자동 변경하지 않습니다.
- 팀원 PC별 독립 DB입니다. seed/업무 데이터 공유는 별도 합의가 필요합니다.
- DB 변경은 `schema/`(신규 설치)와 새 `migrations/` SQL(기존 설치)을 함께 작성합니다. 운영 전 백업/검증합니다.

## 테이블·값 기준

14개 테이블, 134개 컬럼, 20개 FK. 기존 ERD 정의를 분리했고 `POST_ALERT` 상태만 추가했습니다.
컬럼 설명은 SQL의 `COMMENT`를 읽습니다. `ERD.png`에는 이 추가 상태가 반영되어 있지 않습니다.

ENUM 10종은 `schema/00_enums.sql`에서 별도로 관리합니다. `schema.sql`이 ENUM → 테이블 순서로 불러옵니다.
ENUM 파일을 직접 따로 실행하지 않아도 됩니다. 기존 DB의 값 변경은 `migrations/` SQL을 사용합니다.

- OFF는 `cctvs.is_monitored=false`; ON 모드는 BASE/ALERT/POST_ALERT/VERIFY.
- `users.email`, `incidents.dedup_key` 등에 UNIQUE 제약이 아직 없습니다. 인증/중복 방지 구현 전에 정책과 변경 SQL을 합의합니다.
- 시간은 `TIMESTAMP WITHOUT TIME ZONE`. 저장 시간대는 연동 전에 합의합니다.
- `updated_at` 갱신 트리거는 없습니다. repository에서 갱신합니다.
- `notifications.incidents_id`는 기존 DB 컬럼명 그대로입니다.
- UI 문자열 ID/백분율과 DB BIGINT/DECIMAL을 구분합니다. 서버 DB 연결은 아직 없습니다.

검사용 SQL은 `tests/database_contract.sql`입니다. CI가 새 PostgreSQL에서 초기화와 구조를 검사합니다.
Docker의 Windows 실행 여부는 각 PC에서 위 명령으로 확인합니다.

공식 참고: [초기화 규칙](https://hub.docker.com/_/postgres), [psql 상대 파일 실행](https://www.postgresql.org/docs/17/app-psql.html), [상태 값 추가](https://www.postgresql.org/docs/17/sql-altertype.html).
