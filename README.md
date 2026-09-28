# OCTV 개발용 UI · 2026-09-28 2차 최종 수정본

React WEB / React Native·Expo MOBILE의 UI와 개발 준비 파일입니다. 로그인·회원가입·검증·저장·기관 전달·AI·외부 API·DB 연결은 팀 구현 영역입니다. 화면 이동·선택·팝업과 목업 페이지 전환만 동작합니다.

```cmd
npm ci
npm run dev:web
```
WEB: http://localhost:4173
새 CMD에서 `npm run dev:mobile:web` → MOBILE: http://localhost:8081
UI 실행에는 DB·API 키가 필요 없습니다.

- [실행·포맷](docs/UI_RUN.md) · [Docker DB](docs/DATABASE.md)
- [기존 GitHub 협업](docs/GITHUB.md) · [화면 흐름](docs/SCREENS.md)
- [수정·검증 결과](docs/VERIFICATION.md) · [변경 파일](docs/CHANGED_FILES.md)
- [구조](docs/STRUCTURE.md) · [후속 개발](docs/TODO.md)

## 재개 확인

최신 저장본은 [PR #3](https://github.com/alswo0548/octv/pull/3)의 `fix/octv-ui-round2-0928`입니다. 176개 파일을 대조해 복구하고 타입·포맷·범위 검사와 WEB/MOBILE 빌드를 다시 통과했습니다. 이번 브라우저 화면 재검증은 로컬 서버 접근 제한으로 완료하지 못했습니다. 이전 화면 기록과 이번 결과를 [재개 검증표](docs/ROUND2_RESUME_VERIFICATION.md)에서 구분합니다.

## 2차 수정 결과

PPT 7페이지와 CCTV 출처, 감시 상태·특보 제한 목업, WEB·MOBILE 회원가입 버튼 및 역할 명칭을 반영했습니다. 실행 방식과 Docker/DDL은 유지합니다.

- [PPT별 반영표·실제 검증·미검증 항목](docs/ROUND2_VERIFICATION.md)
- [이번 변경 파일](docs/ROUND2_CHANGED_FILES.md) · [진행 상태](docs/ROUND2_STATUS.md)

## 이전 배포본 링크 (최신 ZIP과 구분)

- WEB: https://octv-ui-revision-0928.alswo0548.chatgpt.site
- MOBILE 웹: https://octv-ui-revision-0928.alswo0548.chatgpt.site/mobile.html
- [Penpot 수정 사본과 캡처](docs/PENPOT.md)

이 링크는 이전 작업에서 배포한 본인 전용 사이트입니다. 이번 재개에서는 재배포하지 않았습니다. 최신 소스는 이 패키지와 PR #3을 기준으로 합니다. 이전 2차 화면 검증 기록과 이번 재개 빌드 결과는 구분해서 읽어주세요.

## 이전 1차 변경 (이력)
PPT 1~14쪽 UI 수정, 기관 조회·전달 선택 분리, 최신 지원요청 목록, 영상 배경 비율 유지, 소스 포맷 설정, PostgreSQL만 실행하는 Compose를 반영했습니다.
개인 `.env`는 덮어쓰지 않습니다. DB를 처음 사용할 때 루트 `.env.example`의 키를 본인의 `.env`에 준비하세요.

기존 저장소: https://github.com/alswo0548/octv.git · 기준 브랜치 `main`.
이전 PR #1·#2 반영 후의 main을 기준으로, 이번 2차 변경은 `fix/octv-ui-round2-0928` 브랜치에서 PR로 제출합니다. `main` 반영은 PR 검토·병합 후 이루어지며, PC 파일은 이후 `git pull`로 갱신합니다. 브랜치 확인 방법과 상태는 [협업 가이드](docs/GITHUB.md)와 [인수인계 보고](docs/HANDOVER_RECHECK.md)를 확인하세요. 원본 ZIP·참고 문서는 보존했습니다.

## 빌드 결과로 확인

```cmd
npm ci
npm run build:web
npm run build:mobile:web
npm run preview:web
```
WEB: http://localhost:4173. 새 CMD에서 `npm run preview:mobile:web` → MOBILE: http://localhost:8081. 종료는 각 창에서 Ctrl+C. DB 없이 동작합니다. Windows 자체 실행은 미검증이며 Linux 빌드·브라우저 검증과 구분합니다.
