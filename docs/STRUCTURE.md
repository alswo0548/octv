# 폴더·의존성

| 위치 | 용도 / 현재 상태 |
|---|---|
| frontend/web/src/pages | WEB 9개 화면, JSX 컴포넌트 |
| frontend/web/src/components | 지도 도식·CCTV 연출·기관 선택·모달 |
| frontend/web/src/styles | 샘플 원본 CSS + React용 보정 |
| frontend/mobile/src/screens | Expo 네이티브 화면, 웹에서도 렌더링 |
| frontend/mobile/src/components | 공통 UI·VideoView·CCTV 연출·SVG 경로 도식 |
| shared/src | 고정 JSON 목업, 타입, 화면 목록 |
| backend/app | FastAPI 최소 진입점과 기능별 TODO |
| ai | 향후 AI 기능 폴더만 있음 |
| database | schema.sql, ERD 전사 JSON |
| docs/references | 첨부 원본 4개. 수정하지 않음 |
| scripts / tests | 실행 보조·범위 검사 / 향후 기능 테스트 위치 |
| .github | PR·Issue 양식, UI 검사 CI |

## 지금 필요한 패키지
npm workspaces를 사용한다. **루트 package-lock.json 한 개**를 npm이 생성했다. 설치는 루트에서 `npm ci`.

| 패키지 | 역할 |
|---|---|
| React / React DOM 19.2.3 | WEB 렌더링 |
| Vite 8.3.1 / TypeScript 6.0 | WEB 개발 서버·빌드 / 타입 검사 |
| Expo 57 / React Native 0.86.3 | MOBILE 앱 실행 구조 |
| React Native Web 0.21 | MOBILE 브라우저 렌더링 |
| react-native-svg | 편집 가능한 모바일 지도 도식 |
| expo-video | 확보한 배경 영상 재생. 실제 CCTV 스트림 아님 |
| @octv/shared | 이 저장소의 공통 목업·타입 |

정확한 설치 버전·무결성 값은 package-lock.json이 기준이다.
호환성 기준: Expo 공식 blank TypeScript SDK57 템플릿의 React/RN/TS 조합과 환경변수 EXPO_OFFLINE을 1로 지정한 `expo install --check`(로컬 SDK 매핑 검사). 온라인 검사는 검증 환경의 네트워크 제한으로 실행하지 못했다.
참고: https://docs.expo.dev/versions/latest/ / https://vite.dev/guide/

## 선택 설치
Backend: Python 3.12, `backend/requirements.txt`. UI와 독립이며 FastAPI 객체 생성만 한다. octv 루트의 **CMD**에서 실행한다. 가상환경을 활성화하지 않고 그 안의 Python을 직접 사용한다.

```cmd
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
종료는 `Ctrl+C`. 이 터미널에서 프론트 명령을 실행하려면 `cd ..`로 octv 루트에 돌아온다.
업무 API가 없으므로 `/`는 404다. `/docs`에는 업무 엔드포인트가 없다.
AI 패키지는 장비·개발 범위를 정한 뒤 별도로 추가한다. UI를 위해 설치하지 않는다.
