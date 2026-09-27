# 2인 GitHub 협업 (Windows CMD)

기본안: **main + feature 브랜치 → PR → 상대방 검토 → 병합**. 실제 저장소는 아직 만들지 않았다.
역할 제안: 박수연은 탐지·사건화, 이민재는 판단·대응. UI·공통 파일 담당은 작업 시작 전에 정한다.

아래 명령은 CMD 기준이며 한 줄씩 실행한다. 설명 문장은 터미널에 붙여 넣지 않는다.

## 1. 로컬 설치와 UI 확인

먼저 [UI_RUN.md](UI_RUN.md)에 따라 octv 루트에서 `npm ci`, `npm run typecheck`, WEB 실행을 확인한다. GitHub 초기 업로드도 **frontend 하위 폴더가 아닌 octv 루트**에서 진행한다.

## 2. GitHub에 빈 저장소 만들기

팀에서 한 명만 GitHub에 새 비공개 저장소를 만든다. 예시 이름은 `octv`이며 README·.gitignore·라이선스 자동 생성은 선택하지 않는다. ZIP에 이미 준비된 파일을 최초 커밋으로 올린다.
생성한 저장소의 **HTTPS 주소**를 복사한다. 아래 `https://github.com/YOUR_ACCOUNT/octv.git`는 예시이므로 본인의 실제 저장소 주소로 바꾼다.
기존 커밋이 있는 저장소에는 아래 초기 업로드를 그대로 실행하지 않는다.

## 3. 최초 업로드

octv 루트의 CMD에서 실행한다.

```cmd
git init -b main
git add .
git status
```

추가 목록에서 `.env`·`node_modules`·빌드 결과가 제외되고 `.env.example`·소스·루트 `package-lock.json`은 포함되는지 확인한다. 이 패키지는 제외 규칙을 제공한다.

Git에서 작성자 이름·이메일을 설정한 적이 없다면 다음 두 줄의 값을 자신의 정보로 바꿔 실행한다. 이 설정은 현재 저장소에만 적용된다. GitHub 이메일 공개가 싫으면 GitHub에서 제공하는 비공개 커밋 이메일을 사용한다.

```cmd
git config user.name "본인 이름"
git config user.email "본인의 Git 커밋 이메일"
```

업로드를 진행한다. 주소는 반드시 앞 단계에서 복사한 실제 주소로 바꾼다.

```cmd
git commit -m "chore: OCTV 개발 준비 패키지"
git remote add origin "https://github.com/YOUR_ACCOUNT/octv.git"
git push -u origin main
```

로그인을 요청하면 저장소를 만든 GitHub 계정으로 인증한다. 업로드가 끝나면 GitHub에서 파일이 보이는지 확인한다.
`origin already exists`가 나오면 `git remote -v`로 주소부터 확인한다. 다른 저장소를 가리킬 수 있으므로 무조건 삭제하거나 덮어쓰지 않는다.

## 4. 팀원 초대와 최초 설치

저장소의 설정에서 협업자로 팀원의 GitHub 계정을 초대하고, 팀원은 초대를 수락한다. **비공개 저장소는 주소만 전달해서는 접근할 수 없다.**

팀원은 Node 24 LTS·npm 11·Git을 준비한 뒤 프로젝트를 둘 상위 폴더의 CMD에서 실행한다. 경로와 저장소 주소는 실제 값으로 바꾼다. `git clone`의 마지막 `octv`는 새로 만들 로컬 폴더 이름이므로 같은 이름의 기존 폴더가 없는 위치를 사용한다.

```cmd
cd /d "D:\프로젝트경로"
git clone "https://github.com/YOUR_ACCOUNT/octv.git" octv
cd octv
npm ci
npm run typecheck
npm run dev:web
```

팀원도 VS Code에서 clone한 **octv 폴더 전체**를 연다. `node_modules`를 따로 보내지 않고 각자 `npm ci`로 설치한다. 현재 UI는 `.env`·Backend·DB·API 키 없이 실행할 수 있다.

## 5. 매 작업

각자 현재 변경 사항을 커밋하거나 별도로 보관한 뒤 최신 main에서 새 작업 브랜치를 만든다. 브랜치 이름은 실제 작업에 맞게 바꾼다.

```cmd
git switch main
git pull --ff-only
git switch -c feature/incident-ui
```

코드를 수정하고 화면을 확인한 다음 실행한다. `수정한 파일 경로`는 실제 파일 경로로 바꾸고, 파일이 여러 개면 필요한 경로마다 `git add`를 실행한다.

```cmd
npm run typecheck
git add "수정한 파일 경로"
git status
git commit -m "ui: 사건 상세 패널 정리"
git push -u origin feature/incident-ui
```

GitHub에서 main을 대상으로 PR을 열고 상대 팀원을 리뷰어로 지정한다. 리뷰 후 병합한다.
커밋 접두어 예: `ui:`, `feat:`, `fix:`, `docs:`, `chore:`.

## 충돌 해결

작업 브랜치에서 커밋하지 않은 변경을 먼저 정리한 뒤 main의 변경을 반영한다.

```cmd
git fetch origin
git merge origin/main
```

충돌이 발생하면 파일의 `<<<<<<<` / `=======` / `>>>>>>>` 부분을 상대방과 확인해 편집한다. 아래 `해결한 파일 경로`를 실제 파일 경로로 바꾸고 해결한 각 파일을 추가한다.

```cmd
npm run typecheck
git add "해결한 파일 경로"
git commit
git push
```

충돌 없이 병합이 완료되면 충돌 해결용 `git add`·`git commit`은 필요 없다. 해결이 불확실하면 진행 중인 병합을 `git merge --abort`로 취소한 후 상의한다. 강제 push는 기본 흐름에 사용하지 않는다.

## 병합 후

```cmd
git switch main
git pull --ff-only
git branch -d feature/incident-ui
```

GitHub의 브랜치 삭제 버튼은 병합 확인 후 사용한다.
`shared/`, `database/`, 루트 package.json·package-lock.json을 바꾸기 전에 상대방에게 알린다.
비밀정보와 대형 영상·모델은 올리지 않는다. CI는 UI 검사만 한다.
main 직접 push 금지·PR 리뷰 1명 요구는 저장소 설정에서 팀이 수동으로 정한다.
