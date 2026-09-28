# 기존 GitHub 저장소 협업 (Windows CMD)

저장소: https://github.com/alswo0548/octv.git · 기준 브랜치: `main`.
저장소 생성·최초 업로드·팀원 초대는 진행된 상태입니다. 초대 수락·설치 완료는 별도 확인합니다.

## 처음 받는 팀원

```cmd
git clone https://github.com/alswo0548/octv.git
cd octv
npm ci
```
접근 거부가 나오면 초대받은 GitHub 계정과 초대 수락을 확인합니다. 저장소를 다시 만들거나 git init을 실행하지 않습니다.

## 매 작업 시작

```cmd
git status
git branch --show-current
git remote -v
```
수정 파일이 있으면 먼저 자기 작업을 별도 브랜치에 커밋하거나 백업합니다. 작업 파일을 지우고 시작하지 않습니다. 작업 트리가 깨끗해진 뒤:

```cmd
git switch main
git pull --ff-only origin main
git switch -c chore/ui-docker-0928
```
브랜치가 이미 있으면 새 이름을 사용하거나 기존 브랜치의 용도를 확인합니다. pull이 실패하면 강제 초기화하지 않고 원인을 확인합니다.

## 이번 ZIP 적용
1. ZIP을 저장소 밖의 별도 폴더에 압축 해제합니다. 기존 `.git`·개인 `.env`는 보존합니다.
2. `docs/CHANGED_FILES.md`의 변경 파일만 비교합니다. 원격 최신 변경이 있으면 VS Code 비교로 두 변경을 합칩니다. 폴더 전체 덮어쓰기는 피합니다.
3. 추가 파일을 복사하고, 수정 파일은 검토 후 적용합니다. 원본에 없던 다른 파일은 삭제하지 않습니다.
4. `.env.example`의 신규 키만 개인 `.env`에 수동 추가합니다. 개인 `.env`는 커밋하지 않습니다.
5. `package.json`과 `package-lock.json`은 함께 반영하고 `npm ci`를 실행합니다.

## 검사·커밋·푸시·PR

```cmd
npm run format
npm run format:check
npm run typecheck
npm run check:scope
npm run build:web
npm run build:mobile:web
git diff --check
git status
git diff
```
파일 단위로 확인하고 `git add -p`로 형식 정리와 UI·설정 변경을 나눠 스테이징하면 검토하기 쉽습니다. 새 파일은 `git add 파일경로`로 추가합니다. 비밀정보·DB 덤프·빌드 산출물이 포함되지 않았는지 확인합니다.

```cmd
git diff --cached --stat
git diff --cached
git commit -m "feat: refine OCTV UI and Docker development setup"
git push -u origin chore/ui-docker-0928
```
GitHub에서 Compare & pull request → base `main` 확인 → 상대 팀원 검토 → 승인 후 병합합니다. main 직접 덮어쓰기·force push·자동 병합은 하지 않습니다.

## 병합 후 / 충돌

```cmd
git switch main
git pull --ff-only origin main
```
작업 브랜치에서 충돌이 생기면 `git status`로 충돌 파일을 확인하고 양쪽 작업을 비교해 함께 보존합니다. 해결 후 add·검사·커밋합니다. 진행 중인 merge를 취소하려면 `git merge --abort`로 merge 직전 상태로 돌아갑니다. `reset --hard`, `clean -fd`로 팀원·미커밋 작업을 지우지 않습니다.

## 현재 2차 수정 브랜치

[PR #3](https://github.com/alswo0548/octv/pull/3), `fix/octv-ui-round2-0928`에 2차 수정본이 저장되어 있습니다. 기준 main은 `9fd2e6f4102e43936aed1fceddd17cccea68fe14`, 복구 기준 UI 커밋은 `835b7b0511d87de64fb51f7711fceb168d288910`입니다. 이번 재개 문서·캡처도 같은 PR에 추가합니다. main 직접 변경·강제 푸시·자동 병합은 하지 않습니다.

## 병합 전에 확인

기존 미커밋 작업을 건드리지 않고 새 폴더에서 확인합니다.

```cmd
git clone --branch fix/octv-ui-round2-0928 --single-branch https://github.com/alswo0548/octv.git octv-round2-review
cd octv-round2-review
npm ci
npm run dev:web
```

새 CMD에서 같은 폴더로 이동한 뒤 `npm run dev:mobile:web`을 실행합니다. WEB은 http://localhost:4173, MOBILE은 http://localhost:8081입니다. 검토 후 PR을 병합하면 각 PC에서 main을 pull하여 반영합니다.

이번 실행·미검증 범위는 `ROUND2_RESUME_VERIFICATION.md`를 확인하세요.
