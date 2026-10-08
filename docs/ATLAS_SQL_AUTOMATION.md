# OCTV SQL Migration 자동화 — 민재/수연 협업 가이드

> **현재 상황**: 민재는 `main` 기준 003 DB, 수연은 기존 브랜치에서 백엔드 개발 중이고 `agencies.service_region_codes TEXT[]`를 본인 Docker DB에 직접 추가함. 수연 변경사항은 PR 전이다.
>
> **중요**: 이전에 전달된 `OCTV_SQL_Migration_자동화_패치.zip`은 사용하지 마세요. **Atlas 패치 하나만** 적용합니다. 신규 테이블 생성 SQL과 기존 데이터는 보존됩니다.

## 이해해야 할 말은 3개

- **기능별 SQL (`backend/app/*/sql/`)**: 새 DB를 만들 때의 최신 테이블 구조를 적은 설계도.
- **Migration 파일 (`database/atlas_migrations/`)**: *기존* DB를 설계도처럼 바꿀 명령. `diff`를 실행하면 Atlas가 자동 생성. 수동 작성이 원칙이 아님.
- **실제 Docker DB**: 각자 컴퓨터에 따로 있음. SQL 코드나 GitHub가 바뀌어도 자동으로 바뀌지 않음. `apply`로 변경.

기능 개발 중 SELECT/INSERT나 Python 코드만 바뀌면 Migration은 필요 없음. 컬럼·테이블·제약조건 등 **DB 구조**가 바뀌면 `diff`가 필요함.

---

## 0. 두 사람 PC 공통 준비 — 최초 한 번

**Windows + VSCode CMD, `compose.yaml` 파일이 있는 `octv` 루트에서 실행**합니다.

1. Docker Desktop을 먼저 켭니다. `.env`는 기존 것을 유지합니다(없을 경우에만 `.env.example` 복사하고 POSTGRES_PASSWORD 입력).
2. **Atlas CLI** 공식 Windows 설치: https://atlasgo.io/faq/atlas-on-windows — GitHub 공식 배포 `.exe` 다운로드 → `atlas.exe`로 이름 변경 → 예: `C:\atlas\atlas.exe` 저장 → Windows 환경변수 `Path`에 `C:\atlas` 추가 → VSCode CMD 재시작. **Atlas는 pip로 설치하는 Python 패키지가 아니라 독립 프로그램**입니다.
3. CMD에서 아래 확인·설치. 기존 `.venv`가 있으면 첫 줄(생성)은 생략하세요.

```cmd
py -3.12 -m venv .venv
.venv\Scripts\python -X utf8 -m pip install -r backend\requirements.txt
atlas version
docker compose up -d db
docker compose ps
```

`.env`, `backend/.env`, `DATABASE_URL`을 서로 다른 DB로 가리키게 설정하지 마세요. Atlas는 실제 Docker DB 및 백업 DB가 같은지 검사합니다.

---

## 1. 민재 — 자동화 틀을 먼저 GitHub에 올리기 (최초 한 번)

수연의 진행 중인 PR이 `main`에 병합되기 **전에** 수행합니다.

**① 작업 보관 후 `main`에서 브랜치 생성**

```cmd
git status
git switch main
git pull --ff-only origin main
git switch -c chore/atlas-sql-migrations
```

작업 중인 미커밋 내용은 먼저 커밋하거나 별도로 보관하세요.

**② Atlas 패치 ZIP 적용**: ZIP 안의 `octv/`가 현재 프로젝트 `octv/`에 대응하도록 **프로젝트 상위 폴더에서 압축 해제**합니다. 덮어쓰는 대상은 자동화 설정 파일과 안내서뿐입니다. `backend/app/.../sql/`은 변경하지 않습니다.

**③ 현재 Docker DB가 기존 003 구조인지 확인**

```cmd
.venv\Scripts\python scripts\db.py verify
```

`SCHEMA OK`가 나오면 진행. 나오지 않으면 멈춰서 DB 상태부터 확인합니다. **Docker 볼륨 삭제 금지**.

**④ 최초 기준 Migration 자동 생성 → 내 기존 DB에 기준 버전 등록**

```cmd
.venv\Scripts\python scripts\atlas_db.py init-create
.venv\Scripts\python scripts\atlas_db.py init-mark
.venv\Scripts\python scripts\atlas_db.py status
```

- `init-create`: 원래 OCTV 13개 테이블 구조의 최초 Migration 파일을 **자동 생성**. 내 DB는 변경하지 않음.
- `init-mark`: 내 DB에는 그 테이블들이 이미 있으니 **재생성하지 않고, 이미 적용된 기준임을 기록**.
- `status`: 적용 상태 확인.

**⑤ 자동화 파일 + 최초 Migration 함께 PR**

```cmd
git status
git add .gitignore atlas.hcl database/init/00_schema.sql database/atlas_migrations scripts/atlas_db.py docs/ATLAS_SQL_AUTOMATION.md docs/DATABASE.md
git commit -m "chore: initialize Atlas migrations"
git push -u origin HEAD
```

GitHub에서 PR을 만들고 `main`에 병합. `database/atlas_migrations/` 안의 `<시간>_baseline.sql`과 `atlas.sum`을 **반드시 함께 커밋**하세요.

---

## 2. 수연 — 기존 백엔드 작업을 이어서 자동화 연결

**① 작업은 그대로 보존하고, 현재 작업 브랜치에 민재의 자동화 코드만 가져오기**

```cmd
git status
```

미커밋된 백엔드 작업이 있다면 먼저 저장용 커밋을 남깁니다(변경이 없으면 아래 두 줄은 생략).

```cmd
git add backend/app
git status
git commit -m "wip: save backend work before Atlas sync"
```

`git status`에서 `.env`나 불필요한 파일이 스테이징되지 않았는지 확인하세요. `backend/app` 밖의 작업 변경도 있다면 해당 파일을 따로 안전하게 보관합니다.

```cmd
git fetch origin
git merge origin/main
```

**절대 `git switch main`으로 진행 중인 수연 브랜치를 버리지 않습니다.** 충돌하면 해결 후 진행.

**② 기능별 SQL에 최종 구조가 적혀 있는지 확인**

`backend/app/agencies/sql/agencies.sql`의 `CREATE TABLE agencies` 안에 다음 컬럼과 설명이 포함됐는지 확인합니다.

```sql
service_region_codes TEXT[]
-- CREATE TABLE 뒤에 별도로
COMMENT ON COLUMN agencies.service_region_codes IS 'ROAD_MANAGEMENT 기관의 담당 지역코드 목록';
```

예시는 SQL 일부만 발췌한 것으로, 실제 파일 안에서는 다른 컬럼 사이의 쉼표 등 구문을 정확히 유지해야 합니다.

**③ Migration 파일 자동 생성** (**로컬 DB를 직접 바꾸는 단계가 아님**)

```cmd
.venv\Scripts\python scripts\atlas_db.py diff add_agency_service_region_codes
```

이 명령이 `database/atlas_migrations/<시간>_add_agency_service_region_codes.sql`을 자동 생성합니다. 직접 `ALTER TABLE` 파일을 새로 작성할 필요가 없어요. **생성된 내용**이 `service_region_codes` 추가와 설명 등 실제 변경 내용과 일치하는지만 검토합니다. 불필요한 `DROP TABLE`·`DROP COLUMN`이 있으면 중단.

**④ 수연님 PC는 이미 `ALTER TABLE`을 직접 실행했으므로 `apply`를 곧바로 하면 안 됨**

이미 수정된 본인 DB가 **수정된 기능별 SQL과 정확히 일치하는지 검사한 뒤**, 실행 이력만 기록합니다.

```cmd
.venv\Scripts\python scripts\atlas_db.py adopt-manual
```

- 이 명령은 실제 DB와 SQL의 차이를 Atlas `--dry-run`으로 먼저 확인합니다.
- `Schemas are synced, no changes to be made` 수준으로 **차이가 없을 때만** `MARK_ALREADY_APPLIED` 입력을 요청합니다.
- 해당 문구가 나오지 않거나 오류가 있으면 **중단**합니다. 수연님 DB를 되돌리거나 초기화하지 마세요.
- 입력 후 **DB 전체 백업** → 이미 실행한 변경의 Migration 버전만 기록. 같은 `ALTER TABLE`을 다시 실행하지 않습니다.
- 이 단발 명령은 **처음 등록할 때만**, **baseline + 이번 변경 1개** 구성일 때만 사용합니다.

**⑤ 상태 확인, 기능 테스트, GitHub PR**

```cmd
.venv\Scripts\python scripts\atlas_db.py status
git status
git add database/atlas_migrations
```

수정한 백엔드 코드·기능별 SQL 파일도 함께 커밋하고, 기존 브랜치 Push → PR 생성 → `main` 병합.

> **만약 수연님이 SQL 파일만 수정하고 DB에는 아직 적용하지 않은 변경도 섞여 있다면** `adopt-manual`은 스키마 불일치를 감지해 멈춥니다. 이 경우 현재 DB와 코드 차이를 먼저 검토해야 하며, 무조건 버전 표시를 해서는 안 됩니다.

---

## 3. 민재 — 수연님 PR을 받은 뒤

```cmd
git status
git switch main
git pull --ff-only origin main
docker compose up -d db
.venv\Scripts\python scripts\atlas_db.py apply
.venv\Scripts\python scripts\atlas_db.py status
```

- `git pull`: 수연님이 만든 **자동 생성 Migration SQL + 코드** 받기.
- `apply`: 적용 예정 SQL 보여주고 `APPLY` 입력 요청 → 자동 백업 → 내 DB에 **아직 적용되지 않은 변경만** 실행.
- `status`: 적용 여부 확인.

기존 소스 SQL만 Pull하는 것은 **내 Docker DB를 바꾸지 않습니다**.

---

## 4. 두 사람 모두 앞으로 DB 구조를 바꿀 때

**DB를 수정한 사람**

```cmd
git fetch origin
git merge origin/main
REM 기능별 SQL의 CREATE TABLE / COMMENT 등의 정의 수정 후
.venv\Scripts\python scripts\atlas_db.py diff change_description
.venv\Scripts\python scripts\atlas_db.py apply
.venv\Scripts\python scripts\atlas_db.py status
```

수정된 기능별 SQL + 백엔드 코드 + 자동 생성된 Migration + `atlas.sum`을 함께 PR.

**변경을 받는 사람**

```cmd
git pull --ff-only origin main
.venv\Scripts\python scripts\atlas_db.py apply
.venv\Scripts\python scripts\atlas_db.py status
```

- 나중에는 DB 직접 수정용 `ALTER TABLE`을 별도로 실행하지 않는 것을 원칙으로 합니다. **기능별 SQL 수정 → diff 자동 생성 → apply**.
- 신규 `backend/app/*/sql/*.sql` 파일을 추가한다면 `database/schema.sql`에 `\ir` 포함 경로도 추가합니다.
- 새 Migration은 과거 `database/migrations/`가 아니라 **`database/atlas_migrations/`**에 생깁니다.
- 기존 `scripts/db.py migrate`는 과거 003 갱신 전용이므로 Atlas 전환 후에는 사용하지 않습니다.
- 과거 기준 `scripts/db.py verify`와 `scripts/check-db.py`는 최신 컬럼 변경을 반영하지 않을 수 있으니 기능 변경 후 검사 기준도 맞춰야 합니다.
- `docker compose down -v`, 데이터볼륨 삭제, DB 초기화를 마이그레이션 오류 해결책으로 사용하지 마세요.

**검증 상태**: 패치는 정적 검사/모의 테스트 범위에서 점검. Windows에서 Atlas CLI와 PostgreSQL Docker로 *실제 생성·적용*한 결과는 아직 확인되지 않았으므로, 첫 PR 병합 전 사용자 PC에서 실행 결과를 확인해야 합니다.

공식 근거:
- https://atlasgo.io/versioned/diff
- https://atlasgo.io/versioned/apply
- https://atlasgo.io/versioned/import
- https://atlasgo.io/faq/atlas-on-windows
