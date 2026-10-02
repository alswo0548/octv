# Docker와 DB 세팅 안내

Windows + VSCode + CMD 기준입니다. 모든 명령은 compose.yaml이 있는 프로젝트 루트에서 실행합니다.
PostgreSQL만 Docker로 실행하고 프론트엔드·백엔드는 기존 로컬 환경을 씁니다.
Docker 이미지 postgres:17.11-bookworm과 프로젝트명 octv, postgres_data 볼륨 이름을 유지했습니다.

## 설치 확인

Docker Desktop 공식 Windows 설치 안내: https://docs.docker.com/desktop/setup/install/windows-install/
WSL 안내: https://docs.docker.com/desktop/features/wsl/
Microsoft WSL 설치: https://learn.microsoft.com/ko-kr/windows/wsl/install
2026-10-02 확인. 지원 Windows 버전·가상화·RAM 요구사항은 공식 설치 페이지에서 확인합니다.

이미 설치했다면 일반 CMD에서 wsl --version, docker version, docker compose version을 확인합니다.
WSL은 2.1.5 이상이며 최신 버전 사용을 권장합니다. WSL이 없다면 관리자 CMD에서 wsl --install 후 재부팅합니다.
wsl --update로 갱신할 때 권한 요청이 나오면 관리자 CMD에서 실행합니다.
Docker Desktop 설치 시 WSL 2 방식을 선택하고 실행합니다. Linux containers 모드를 사용합니다.
Settings > General의 Use the WSL 2 based engine을 확인합니다. Windows CMD 사용에는 별도 배포판 연동 설정이 필수는 아닙니다.
일반 CMD에서 docker info --format "{{.OSType}}" 결과가 linux인지 확인합니다.
설치기 전체 사용자 설치는 관리자 권한이 필요하며 기본 사용자별 설치는 보통 필요하지 않습니다.

## 개인 설정

```cmd
cd /d "C:\KDT2604\최종 프로젝트\octv"
if not exist .env copy .env.example .env
notepad .env
```

경로는 본인의 실제 프로젝트 위치로 바꿉니다. 기존 .env를 덮어쓰지 않습니다.
POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_PORT가 모두 있는지 확인합니다.
기본 DB·사용자는 octv_dev, 호스트 포트는 5432입니다. 비밀번호는 개인 값으로 넣습니다.
$ 또는 #이 포함된 값은 작은따옴표로 감쌉니다. 실제 .env와 비밀번호는 Git·공유 ZIP에서 제외합니다.

Python 연결은 환경변수 DATABASE_URL → backend/.env의 DATABASE_URL → 루트 .env의 POSTGRES_* 순서입니다.
권장 방법은 DATABASE_URL을 비워 루트 설정을 함께 쓰는 것입니다. 기존 backend/.env는 보존하면서 DB 항목만 대조합니다.
DATABASE_URL을 사용하면 비밀번호 특수문자를 URL 인코딩하고 127.0.0.1 및 호스트 포트를 맞춥니다.
포트 충돌 시 루트 POSTGRES_PORT=5433으로 변경합니다. DATABASE_URL이 있다면 그 포트도 5433으로 변경합니다.
컨테이너 내부 포트 5432는 바꾸지 않습니다. DB명·계정·비밀번호 환경변수 변경은 기존 볼륨의 계정을 바꾸지 않습니다.

## 빈 DB 처음 만들기

```cmd
docker compose config --quiet
docker compose up -d db
docker compose ps
docker compose logs --tail 50 db
.venv\Scripts\python scripts\db.py tables
.venv\Scripts\python scripts\db.py verify
.venv\Scripts\python scripts\check-db.py
```

config --quiet는 오류 없이 끝나면 설정 해석 성공입니다. 설정값이 출력되는 config 대신 이 명령을 사용합니다.
ps는 db가 Up (healthy), 로그는 초기화 오류 없이 ready to accept connections가 보여야 합니다.
단, healthy는 서버 상태만 뜻하므로 반드시 tables와 verify까지 확인합니다.
tables는 테이블 13개, verify는 SCHEMA OK가 나와야 합니다.
check-db.py는 Python에서 실제 TCP 접속 후 SELECT와 읽기 전용 구조 검사를 실행합니다. DB OK와 SCHEMA OK가 모두 필요합니다.
드라이버가 없다면 기존 .venv에 필요한 백엔드 패키지만 설치합니다. 기존 환경을 재생성하지 않습니다.

```cmd
.venv\Scripts\python -m pip install -r backend\requirements.txt
```

최신 정의는 13개 테이블, 123개 컬럼, 19개 외래키, ENUM 10종과 추가 UNIQUE 규칙 7개입니다. 상세 기준은 ERD_UNIQUES.md에 있습니다.
Docker의 database/init/00_schema.sql → /opt/octv/database/schema.sql → 기능별 sql/ 순서로 실행합니다.
초기화 파일은 빈 데이터 볼륨의 첫 시작에만 실행됩니다. SQL 수정·컨테이너 재시작만으로 기존 DB는 바뀌지 않습니다.
Python 공통 연결은 with 블록 정상 종료 시 commit, 예외 시 rollback 후 연결을 닫습니다.
백엔드 /health는 DB를 검사하지 않으며 database=not_checked를 반환합니다.

## 기존 DB가 있을 때

작업을 멈추고 먼저 db.py verify를 실행합니다. 통과하면 변경 SQL을 실행하지 않습니다.
이전 14개 또는 직전 13개 테이블 구조라면 다음을 진행합니다. 임의 수정한 DB는 먼저 차이를 검토합니다.

```cmd
.venv\Scripts\python scripts\db.py backup
.venv\Scripts\python scripts\db.py migrate
.venv\Scripts\python scripts\db.py verify
.venv\Scripts\python scripts\check-db.py
```

backup은 database/backups/before_003_날짜_시각.dump에 pg_dump 전체 논리 백업을 만들고 pg_restore --list로 읽을 수 있는지 검사합니다.
migrate도 자체 백업을 다시 만든 뒤 003_final_erd_uniques.sql을 적용하므로 앞의 수동 백업은 선택 사항입니다.
변경 후 사라지는 컬럼·원본 JSON·이전 경로평가 정보는 백업에서 복구할 수 있습니다. 백업 파일은 보관하세요.
변경은 한 트랜잭션에서 처리하고 마지막 구조 검사 실패 시 전체 rollback합니다. 001·002를 먼저 실행할 필요는 없습니다.
FALSE_POSITIVE 사건은 그대로 보존됩니다. 중복값, captured_at NULL, 알림/기관추천 연결 불일치, 지원하지 않는 구조가 있으면 중단하고 전체 rollback합니다.
중복 오류에 표시되는 행 ID를 확인해 실제 데이터에 맞게 정리한 뒤 재실행합니다. 임의 삭제·병합·시각 추정은 하지 않습니다.
이미 최신 구조라면 ALREADY CURRENT를 출력하고 변경 없이 끝냅니다. schema.sql 전체 재실행이나 볼륨 삭제로 해결하지 않습니다.
백업 복구는 우선 별도 검증 DB에 pg_restore로 확인합니다. 기존 DB를 덮어쓰는 복구 명령은 기본 절차에 포함하지 않습니다.

## 평소 명령과 주의

| 목적 | CMD 명령 |
|---|---|
| 시작 또는 설정 반영 | docker compose up -d db |
| 잠시 중지 | docker compose stop db |
| 상태 | docker compose ps |
| 최근 로그 | docker compose logs --tail 50 db |

두 사람의 DB는 각 PC에서 독립적입니다. Git으로 SQL을 공유해도 데이터는 공유되지 않습니다.
볼륨 삭제 옵션은 데이터 삭제이므로 사용하지 않습니다. 기존 compose 프로젝트명·볼륨을 임의 변경하지 마세요.
초기화 실패 뒤 서버가 켜져도 테이블은 없을 수 있습니다. 로그와 verify를 보고 원인을 해결한 뒤 빈 DB 여부를 확인합니다.
검증 범위·현재 미구현 항목은 VALIDATION.md와 CHANGES.md를 봅니다.
