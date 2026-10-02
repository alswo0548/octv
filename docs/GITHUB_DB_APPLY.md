# GitHub 병합 후 적용 순서

민재님과 수연님 모두 자신의 PC에서 진행합니다. 아래는 Windows VSCode의 CMD 기준이며 명령은 프로젝트 루트에서 실행합니다.
작업 브랜치 fix/final-erd-uniques-1002의 PR을 main에 병합한 뒤 진행하세요.

## 1 개인 작업 확인과 최신 코드 받기

```cmd
cd /d "C:\KDT2604\최종 프로젝트\octv"
git status
```

본인 경로로 바꿉니다. 수정 파일이 있으면 해당 작업을 커밋하거나 별도 보관한 뒤 다음 명령을 실행합니다.
직전 ZIP을 덮어쓴 미커밋 변경이 있다면 변경분을 보존한 후 병합합니다. 강제 초기화 명령은 사용하지 않습니다.

```cmd
git switch main
git pull --ff-only origin main
```

pull이 충돌하거나 fast-forward 불가로 중단되면 해당 메시지를 확인하고 해결한 뒤 진행합니다.
개인 .env, .venv, node_modules와 학습 데이터는 그대로 사용합니다. 이번 수정은 의존성 버전을 바꾸지 않습니다.

## 2 DB 개인 설정과 시작

Docker Desktop을 먼저 실행합니다. .env가 없을 때만 예제를 복사합니다.

```cmd
if not exist .env copy .env.example .env
notepad .env
docker compose config --quiet
docker compose up -d db
docker compose ps
docker compose logs --tail 50 db
```

POSTGRES_DB/USER/PASSWORD/PORT를 확인합니다. 기존 DB에서는 원래 계정·비밀번호를 유지합니다.
루트 설정과 다른 DATABASE_URL이 환경변수나 backend/.env에 있으면 실제 사용 DB에 맞춥니다.
컨테이너가 healthy이고 초기화 오류가 없어야 다음 단계로 진행합니다.

## 3 기존 DB 갱신과 연결 확인

아래 순서는 빈 볼륨으로 새로 만든 DB와 기존 DB 모두 사용할 수 있습니다.

```cmd
.venv\Scripts\python scripts\db.py migrate
.venv\Scripts\python scripts\db.py verify
.venv\Scripts\python scripts\check-db.py
```

새로 초기화됐거나 이미 최신이면 ALREADY CURRENT로 끝납니다. 기존 DB는 백업 후 003을 적용해 MIGRATION OK를 출력합니다.
verify의 SCHEMA OK와 UNIQUE OK, check-db.py의 DB OK와 SCHEMA OK를 확인하세요.
드라이버가 없을 때만 `.venv\Scripts\python -X utf8 -m pip install -r backend\requirements.txt`를 실행합니다.
가상환경이 아직 없다면 README의 Python 3.12 최초 설치 절차를 먼저 진행합니다.

중복 ID나 captured_at NULL 오류가 나면 해당 데이터를 확인해야 합니다. 볼륨을 삭제하거나 오류를 무시하고 후속 작업을 진행하지 않습니다.
백업은 database/backups/before_003_날짜_시각.dump에 저장됩니다. 백업 목록 검사는 실제 복구 리허설과 다르므로 중요한 데이터는 별도 DB에서 복구도 확인합니다.
두 PC의 DB 데이터는 독립적이며 Git pull만으로 데이터가 서로 공유되지는 않습니다.

## 4 다음 작업 시작

각자 담당 기능용 새 브랜치를 생성합니다. 기존 진행 중인 기능 브랜치가 있다면 새 브랜치를 만들지 않고 main 변경을 병합해 이어갑니다.
다음 요청에서는 이 PR 반영본을 기준으로 진행하면 됩니다.
