# UI 실행·포맷 (Windows CMD)

Node 24 / npm 11을 사용합니다. 모든 명령은 루트 package.json이 있는 octv 폴더에서 실행합니다. DB·API 키·실제 계정 없이 UI만 실행할 수 있습니다.

```cmd
cd /d "D:\프로젝트경로\octv"
node --version
npm --version
npm ci
npm run typecheck
npm run dev:web
```
WEB: http://localhost:4173. 인증 없이 로그인 버튼으로 화면 이동합니다.

새 CMD 창을 열어 같은 폴더에서:

```cmd
npm run dev:mobile:web
```
MOBILE: http://localhost:8081. 개발자 도구에서 390/430px 폭 또는 PC 크기로 확인합니다. 모바일 콘텐츠의 최대 폭은 460px이며 배경은 브라우저 전체 크기에 맞춥니다.

Expo 개발 서버 대신 빌드 결과를 보려면:

```cmd
npm run build:mobile:web
npm run preview:mobile:web
```
같은 8081 포트이므로 이미 실행 중인 자신의 모바일 개발 서버는 먼저 Ctrl+C로 종료합니다. 배포용 빌드 검사는 `npm run build:web`, `npm run build:mobile:web`입니다.
네이티브 Android/iOS: `npm run dev:mobile` 후 Expo 안내를 따릅니다. 이번 수정의 실제 기기 실행은 미검증입니다.

## 포맷과 검사

```cmd
npm run format
npm run format:check
npm run typecheck
npm run check:scope
npm run build:web
npm run build:mobile:web
```
Prettier 3.6.2를 lockfile로 고정했습니다. CSS·TSX의 줄바꿈·들여쓰기를 정리하며 import나 CSS 속성 순서를 정렬하지 않습니다.
대상은 frontend의 편집 소스·설정과 shared/src입니다. node_modules·dist·.expo·생성물·package-lock.json은 포맷에서 제외합니다.
패키지 설치 전 빨간 밑줄은 모듈 미설치 때문일 수 있습니다. 타입 검사 통과 후에도 남으면 VS Code의 TypeScript 버전을 Workspace로 선택하고 TS 서버를 재시작합니다.

배경 영상은 재생 이벤트 이후 표시되며 오류·재생 차단·움직임 줄이기 설정에서는 기존 이미지가 남습니다. 강한 크롭 대신 contain을 사용하므로 화면 비율에 따라 흐린 보조 배경이 보입니다.
시연 문구는 제거했지만 데이터·동작은 UI 목업입니다. 실제 업무 기능을 구현한 상태로 해석하지 마세요.

## 이번 환경에서 검증한 빌드 확인 방식

```cmd
npm run build:web
npm run build:mobile:web
npm run preview:web
```
WEB http://localhost:4173. 새 CMD에서 `npm run preview:mobile:web`, MOBILE http://localhost:8081.
실제 화면 검증은 같은 빌드 결과를 내부 미리보기에서 열어 수행했습니다. 개발 서버는 이 환경의 네트워크 인터페이스 제한을 받으므로 Windows 실행 검증과 구분합니다.
