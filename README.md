# OCTV

CCTV 기반 재난 대응 의사결정 지원 프로젝트. WEB은 통합관제, MOBILE은 현장 담당자 화면입니다.

**현재:** 프론트엔드는 목업 UI입니다. 백엔드는 서버·API 골격만, AI는 작업 함수만 준비되어 있습니다.
실제 인증·DB 연결·추천·기관 전달은 앞으로 구현합니다. 업무 API의 `501`은 **아직 미구현**이라는 응답입니다.

## 읽는 순서

1. 이 README: 설치·실행·협업
2. [개발 기준](docs/DEVELOPMENT.md): 확정 정책과 다음 구현 순서
3. [폴더·파일 설명](docs/STRUCTURE.md): 어느 파일에서 작업하는지
4. [DB 안내](docs/DATABASE.md): Docker·SQL 적용

[자산 출처](docs/ASSET_SOURCES.md)는 영상·이미지 출처 확인용입니다. 수정 과정과 검증 이력은 Git/PR에서 확인합니다.

## 처음 실행 — Windows CMD, 프로젝트 루트

Git, Node.js **24.19.0**(npm 11), Python **3.12**, Docker Desktop(Linux 컨테이너)을 준비합니다.
UI만 실행할 때 Python·Docker·API 키는 필요 없습니다.

```cmd
npm ci
npm run dev:web
```

WEB: http://localhost:4173. 새 터미널에서 `npm run dev:mobile:web` → MOBILE: http://localhost:8081.
휴대폰 Expo 실행은 `npm run dev:mobile`이며 실제 기기·네트워크 설정은 별도로 확인합니다.

백엔드 골격은 새 CMD에서:

```cmd
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
.venv\Scripts\python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

http://127.0.0.1:8000/docs 에서 API 작업 목록, `/health`에서 서버 기동을 확인합니다.
DB와 AI 연결 성공을 뜻하지 않습니다. 프론트는 아직 이 서버를 호출하지 않습니다.
macOS/Linux는 `python3 -m venv .venv`, 이후 `.venv/bin/python`을 사용합니다.

## Python 패키지 설치

| 파일 | 설치 범위 |
|---|---|
| `backend/requirements.txt` | 서버·스키마·환경설정·PostgreSQL 드라이버·인증·HTTP 호출 |
| `ai/requirements.txt` | CPU PyTorch·YOLO·OpenCV·LangGraph·MCP·LLM 어댑터 |
| `requirements.txt` (루트) | 위 두 목록을 함께 설치 |

AI까지 개발할 때는 **Python 3.12, Windows/Linux 64비트 x86_64** 환경에서 다음을 실행합니다.
앞에서 `.venv`를 이미 만들었다면 그대로 사용합니다. UI만 볼 때는 이 설치가 필요 없습니다.

```cmd
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip check
.venv\Scripts\python scripts\check-python-env.py
```

직접 사용하는 패키지 버전을 고정했고 함께 설치되는지는 CI에서 확인합니다. 전체 간접 의존성 lock 파일은 아닙니다.
CPU 설치로 시작하며 모델 가중치는 포함하지 않습니다. GPU 학습은 장비를 확인한 뒤 별도 가상환경을 만듭니다.
그때 [PyTorch 공식 설치 안내](https://pytorch.org/get-started/locally/)에 맞춰 PyTorch/torchvision 조합을 정합니다.
패키지 설치만으로 DB 접속·로그인·AI 판단 기능이 구현되지는 않습니다.

DB는 [DB 안내](docs/DATABASE.md)의 `.env` 준비 → Compose 실행 순서로 진행합니다.
루트 `.env`는 Docker용입니다. `backend/.env.example`은 향후 연동용이며 현재 서버는 읽지 않습니다.

## 작업 전후

기존 작업이 있으면 먼저 커밋합니다. 작업이 없는 상태에서:

```cmd
git switch main
git pull --ff-only origin main
git switch -c feature/작업이름
```

기능별로 작은 커밋 → 작업 브랜치 push → GitHub PR → 상대방 확인 후 merge.
`main` 강제 푸시·기존 변경 삭제는 하지 않습니다. 두 사람의 로컬 DB 데이터는 서로 공유되지 않습니다.

```cmd
npm run typecheck
npm run format:check
npm run build:web
npm run build:mobile:web
.venv\Scripts\python -m unittest discover -s tests -p "test_*.py"
```

종료는 각 서버 창에서 Ctrl+C, DB는 `docker compose stop db`.
개인 `.env`, `.venv`, `node_modules`, 모델·데이터·빌드 결과는 Git에 올리지 않습니다.
