# OCTV

**슬기로운 출동생활 · 이민재, 박수연**

샘플 디자인을 옮긴 WEB·MOBILE UI와 개발 준비 패키지다.
화면 이동·탭·모달·선택 표시만 동작한다. 실제 인증·저장·추천·전달은 팀 구현 영역이다.

## 빠른 실행 (Windows CMD)

Node 24 LTS / npm 11 설치 후, 압축을 풀어 `octv` 폴더에서 실행한다.

```cmd
npm ci
npm run typecheck
npm run dev:web
```

WEB: `http://localhost:4173` → 빈 입력으로 로그인 버튼을 눌러 UI 이동.
별도 CMD 터미널에서 같은 `octv` 폴더로 이동한 뒤 MOBILE 브라우저 확인:

```cmd
npm run dev:mobile:web
```

MOBILE: `http://localhost:8081`. 실제 기기는 `npm run dev:mobile` 후 Expo 안내를 따른다.
Backend·DB·API 키는 UI 실행에 필요하지 않다.

처음 받은 순서: **VS Code에서 octv 열기 → CMD 선택 → npm ci → 타입 검사 → WEB/MOBILE 실행 → GitHub 업로드·팀원 초대**.
폴더 이동, 빨간 줄 확인, 실행 보조 파일은 [UI 실행 안내](docs/UI_RUN.md), 저장소 생성과 팀원 공유는 [GitHub 안내](docs/GITHUB.md)를 따른다.

## 문서

| 목적 | 파일 |
|---|---|
| 정책 / 작업 범위 | [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) |
| 설치·브라우저·실기기·종료 | [docs/UI_RUN.md](docs/UI_RUN.md) |
| 2인 GitHub 협업 | [docs/GITHUB.md](docs/GITHUB.md) |
| 폴더·패키지 역할 | [docs/STRUCTURE.md](docs/STRUCTURE.md) |
| DB 생성·변환·확인사항 | [docs/DATABASE.md](docs/DATABASE.md) |
| 기능 인수인계 | [docs/TODO.md](docs/TODO.md) |
| 화면·코드·이동 | [docs/SCREENS.md](docs/SCREENS.md) |
| 검증·불일치·제한사항 | [docs/VERIFICATION.md](docs/VERIFICATION.md) |

DDL: `database/schema.sql` / 흐름도: `docs/OCTV_페이지흐름도.pptx` / 원본: `docs/references/`.
