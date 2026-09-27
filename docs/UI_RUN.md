# UI 실행 (Windows CMD)

## 준비
- 명령어는 Windows **CMD(명령 프롬프트)** 기준이다. Node 24 LTS / npm 11을 사용한다. 실행 검증은 Linux에서 Node **24.19.0**, npm **11.9.0**로 수행했다. Windows CMD 자체 실행은 미검증이다.
- 모든 명령은 압축 해제한 **octv 폴더**에서 실행한다.
- Python·PostgreSQL·GPU·API 키·실제 계정은 필요 없다.

## 1. VS Code와 CMD 열기

VS Code에서 `frontend`만 열지 말고 루트 `package.json`과 `package-lock.json`이 있는 **octv 폴더 전체**를 연다.
이미 CMD 터미널을 사용 중이면 그대로 진행한다. 변경하려면 `Ctrl+Shift+P` → `Terminal: Select Default Profile` → `Command Prompt`를 선택하고 **새 터미널**을 연다.

아래 경로는 예시다. 실제 폴더 위치로 바꾼다. `cd /d`는 드라이브와 폴더를 함께 이동하며, 공백이 있는 경로도 큰따옴표로 감싼다.

```cmd
cd /d "D:\프로젝트경로\octv"
dir package.json
node --version
npm --version
git --version
```

Node/npm은 설치·실행에, Git은 이후 팀 공유에 필요하다. 명령을 찾지 못하면 해당 프로그램 설치와 PATH를 확인한 뒤 VS Code를 다시 연다.

## 2. 패키지 설치와 빨간 줄 확인

**octv 루트에서** 아래 명령을 한 줄씩 실행한다. `npm ci`가 오류 없이 끝난 다음 타입 검사를 진행한다.

```cmd
npm ci
npm run typecheck
```

압축에는 `node_modules`가 없으므로 설치 전에는 React·Expo 등의 모듈을 찾지 못해 빨간 줄이 나타날 수 있다. 실제 오류 원인은 오류 메시지를 보고 판단한다.

- 타입 검사까지 통과했는데 에디터에만 빨간 줄이 남으면 `.tsx` 파일을 열고 `Ctrl+Shift+P` → `TypeScript: Select TypeScript Version` → `Use Workspace Version`을 선택한다. 이어서 `TypeScript: Restart TS Server`를 실행한다.
- 타입 검사에 실패하면 터미널의 첫 오류 메시지와 해당 파일을 확인한다. 빨간 줄만 보고 패키지 버전이나 `tsconfig.json`을 임의로 바꾸지 않는다.
- 설치 오류가 나면 첫 오류 내용을 확인한다. 설치 실패 상태에서 서버를 실행해도 누락된 모듈 문제는 해결되지 않는다.

## 3. WEB

```cmd
npm run dev:web
```
`http://localhost:4173` → 로그인 화면. 아무 값이나 입력하거나 비워 두고 로그인 버튼으로 이동한다.
메뉴로 9개 화면을 확인한다. 직접 경로는 `SCREENS.md` 참고.

## 4. MOBILE 브라우저

WEB 서버를 켜 둔 채 **새 CMD 터미널**을 열고 같은 octv 폴더로 이동한다.

```cmd
npm run dev:mobile:web
```
`http://localhost:8081` → 출동대원 로그인 화면. 개발자 도구의 기기 모드로 폭 390~460px을 선택한다.
Expo가 포트 변경을 제안하면 터미널에 표시된 주소를 사용한다. 브라우저용 명령은 localhost로 바인딩한다.

개발 서버 대신 정적 UI만 확인하려면:
```cmd
npm run build:mobile:web
npm run preview:mobile:web
```
접속 주소는 같은 `http://localhost:8081`. 코드를 수정하면 다시 빌드한다. Android/iOS 번들 검사를 실행한 뒤에는 웹 빌드를 다시 만든다.

## MOBILE Android / iPhone
```cmd
npm run dev:mobile
```
PC와 휴대폰을 같은 Wi-Fi에 연결하고 SDK 57과 호환되는 Expo Go로 QR 코드를 연다.
Android는 Expo Go의 QR 스캔, iPhone은 카메라로 열 수 있다. 호환 버전은 https://expo.dev/go 에서 확인한다.
현재 버전의 Expo Go가 SDK 57을 지원하지 않으면 팀에서 개발 빌드 환경을 준비해야 한다. 이 패키지는 APK/IPA나 서명 설정을 포함하지 않는다.
실기기·에뮬레이터 실행은 이번 환경에서 미검증이다. 웹에서 성공해도 실기기 성공을 의미하지 않는다.

## 종료·검사
서버를 실행한 각 CMD 터미널에서 `Ctrl+C`. 일괄 작업 종료 확인이 나오면 `Y`를 입력한다.

```cmd
npm run typecheck
npm run build:web
npm run build:mobile:web
npm run build:mobile:native
npm run check:scope
```
`build:mobile:native`는 Android/iOS 번들 생성 검사이며 설치형 앱 제작이 아니다.

## CMD 실행 보조 파일

`npm ci`를 마친 뒤 octv 루트의 CMD에서 아래 중 필요한 명령을 실행해도 된다. 각 파일은 스스로 octv 루트로 이동한다. WEB과 MOBILE을 함께 띄우려면 터미널을 각각 사용한다.

| CMD 명령 | 실행 대상 |
|---|---|
| `scripts\start-web.cmd` | WEB 개발 서버 (`npm run dev:web`) |
| `scripts\start-mobile-web.cmd` | MOBILE 브라우저 개발 서버 (`npm run dev:mobile:web`) |
| `scripts\start-mobile.cmd` | MOBILE 실기기용 Expo 서버 (`npm run dev:mobile`) |

## 5. GitHub에 올리고 팀원 공유

로컬 UI 실행을 확인한 다음 [GITHUB.md](GITHUB.md)의 순서대로 빈 저장소 생성 → 최초 업로드 → 팀원 초대 → 팀원 clone을 진행한다.

## 최소 오류 대응
| 증상 | 조치 |
|---|---|
| node/npm/git 명령을 찾을 수 없음 | 해당 프로그램 설치·PATH 확인 후 VS Code와 CMD 다시 열기 |
| package.json을 찾을 수 없음 / ENOENT | `cd /d "실제 경로\octv"`로 루트 이동. `dir package.json`으로 확인 |
| 모듈을 찾을 수 없음 | octv 루트에서 `npm ci` 재실행 |
| lockfile 불일치 | package.json 변경 여부 확인 후 팀과 합의해 `npm install`, lockfile 함께 커밋 |
| 제한된 실행환경에서 Expo Bonjour/DevTools 오류 | 위의 정적 UI 빌드·미리보기 사용. 실기기는 일반 PC 환경에서 확인 |
| 포트 사용 중 | 먼저 띄운 개발 서버 창에서 Ctrl+C |
| 휴대폰 연결 실패 | 같은 Wi-Fi·방화벽 허용 여부 확인. 우선 웹 실행으로 소스 오류 구분 |
| 모바일 번들 캐시 문제 | 모바일 서버를 종료한 뒤 아래 캐시 초기화 명령 실행 |

캐시를 초기화하며 MOBILE 브라우저 서버를 시작하려면 octv 루트에서 실행한다.

```cmd
cd frontend\mobile
npx expo start --web --localhost --port 8081 --clear
```

실기기용은 두 번째 줄 대신 `npx expo start --port 8081 --clear`를 사용한다. 서버 종료 후 `cd ..\..`로 octv 루트에 돌아온다.

## 환경변수
현재 UI는 환경변수를 읽지 않는다. 포함된 `.env`는 빈 값만 있고 `.env.example`은 Git 양식이다.
`VITE_`·`EXPO_PUBLIC_` 이름은 클라이언트에 노출된다. 비밀키는 향후 서버 `.env`에만 둔다.

VS Code 참고: [터미널 프로필](https://code.visualstudio.com/docs/terminal/profiles), [TypeScript 버전 선택](https://code.visualstudio.com/docs/typescript/typescript-transpiling).
