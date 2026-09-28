# OCTV 인수인계 최종 보고 · 2026-09-28

## 작업본과 보존
- 원본: 9월 28일 첨부 OCTV.zip.
- 이전 저장본: OCTV_final_2026-09-28.zip. 153개 파일의 압축 무결성 및 이전 수정 소스와 바이트 일치를 확인했다.
- 이번 결과물: 이전 저장본을 별도 폴더에 복사하여 보완했다. 원본 ZIP과 이전 저장본은 덮어쓰지 않았다.
- 원본 DDL 및 WEB/MOBILE night-traffic.mp4는 원본 ZIP과 바이트가 같다.

## 추가로 처리한 사항
- 시스템 설정의 외부 서비스 탭에 남은 시연 문구 1곳을 일반 안내로 정리했다.
- `preview:web` 명령을 추가해 WEB·MOBILE 빌드 결과를 각각 확인할 수 있도록 했다.
- README, PROJECT_CONTEXT, 실행·협업·검증 문서를 이번 상태에 맞게 갱신했다.
- 이전 검증 기록은 VERIFICATION_PREVIOUS.md에 보존하고 이번 결과와 분리했다.
- 기존 Penpot 사본 2개를 재확인하고 새 캡처 2장과 브라우저 측정값을 저장했다.

## 이번 실행 결과
| 항목 | 실제 확인 결과 |
|---|---|
| 포맷 / 타입 / 작업 범위 검사 | 통과. WEB·MOBILE 타입 검사, 33개 대상 소스 범위 검사 |
| WEB / Expo 웹 빌드 | 모두 exit 0. 기존 설치 의존성 재사용; npm ci를 새로 실행한 것은 아님 |
| WEB 영상 | 1920×1080·1440×900·1280×800. contain, opacity 0.82, paused=false, 시간 26.25→26.41→26.49초 |
| MOBILE 영상 | 390×844·430×932 및 PC 3종. 영상 박스=뷰포트, PC 콘텐츠 최대 460px, 가로 넘침 없음. PC 측정 13.47→13.97→14.47초 |
| 영상 재로드·이동 | 모바일 재로드 직후 0.14초/로딩 상태에서 26.50초/opacity 0.82로 진행, 화면 이동 후에도 재생. WEB 화면 이동 중 재생 확인 |
| 통합관제 | 목록·마커의 같은 사건 ID 5/5/2개, 페이지 변경 시 이전 마커 제거 |
| 지원요청 | 본문과 첫 목록 항목 동일, 14:38→14:21 최신순, 목록 팝업 열기·닫기 |
| 기관 흐름 | 조회 기관 변경 시 11분/3.6km로 갱신, 맥락 유지하여 경로평가 이동, 3경로 유지, 전달 0개 비활성·2개 선택 시 활성 |
| 모바일 경로 | 제외 B도 조회 가능, 네비 aria-disabled=true. C 선택 시 재활성 |
| 모바일 설정 | 개인정보 처리방침 항목 없음 |
| 로컬 빌드 확인 서버 | npm run preview:web → localhost:4173, npm run preview:mobile:web → localhost:8081 시작 확인 |

화면 크기 검증은 Chrome의 지정 크기 iframe 뷰포트에서 수행했다. Android/iOS 실기기 검증이 아니다. 실제 UI는 React·Expo 빌드이며 단순 HTML로 대체하지 않았다. 검증 전용 컨트롤 페이지는 결과물에 포함하지 않는다.

PPT 14쪽의 텍스트와 캡처 표시 영역을 모두 확인하고 반영 소스를 대조했다. 페이지별 표는 VERIFICATION.md, 변경 파일은 CHANGED_FILES.md를 본다.

## Penpot
- `01 · WEB · 최종수정본 0928`
- `02 · MOBILE · 최종수정본 0928`
- 정확한 사본 링크와 보드 목록은 PENPOT.md.
- 이번에는 원본·공유 요소를 변경하거나 중복 사본을 만들지 않았다. 기존 사본의 기관 탭·추천 1개·지원요청·CCTV 버튼과 모바일 제외 경로·회색 버튼·Description을 재확인했다.
- 새 캡처: screenshots/recheck-penpot-web.jpg, recheck-penpot-mobile.jpg.
- 원시 영상·크기 측정값: screenshots/recheck-browser.json.

## Docker 및 미검증 항목
- PostgreSQL 공식 17.11-bookworm 태그와 17 계열 데이터 경로를 공식 문서에서 확인했다. Compose는 DB 1서비스, localhost 포트, named volume, 읽기 전용 최초 DDL 마운트, healthcheck를 포함한다.
- Docker 명령이 없어 컨테이너 시작·DDL 실제 적용·재시작 후 데이터 유지는 미검증이다. DATABASE.md에 CMD 시작·테이블/FK 확인·종료 절차를 제공한다.
- Windows CMD 자체, Android/iOS 실기기, OS 움직임 줄이기·자동재생 차단 강제 재현, Penpot 전체 보기 모드 연결 재클릭은 미검증이다.
- 마커 호버와 실패 시 이미지 대체 분기는 소스 검토와 이전 기록을 구분한다. 이번에는 마우스 호버를 직접 재현하지 않았다.
- 일반 WEB 개발 서버는 이 실행 환경의 네트워크 인터페이스 제한으로 시작하지 못했다. 빌드 결과 미리보기 명령은 시작 확인했고 같은 빌드의 브라우저 동작을 검증했다.

## 확인 링크와 최신 버전
이전 배포 사이트는 존재하지만 본인 전용 로그인 단계까지만 접속했다. 배포 최신화는 연결 오류로 완료하지 못해 이전 버전을 유지했다. 최신 결과는 이번 ZIP/작업 브랜치를 사용한다. 기존 샘플 사이트는 변경하지 않았다.

```cmd
npm ci
npm run build:web
npm run build:mobile:web
npm run preview:web
```
WEB: http://localhost:4173. 새 CMD에서 `npm run preview:mobile:web` → MOBILE: http://localhost:8081. 각 창의 Ctrl+C로 종료한다. DB 없이 UI를 확인할 수 있다.

## GitHub — 사용자 승인 후 PR 제출
저장소: https://github.com/alswo0548/octv
최초 시도는 정확한 전송 대상 저장소의 사용자 승인이 필요하다는 자동 검토로 중단했다. 이후 2026-09-28 사용자가 해당 저장소의 별도 브랜치·PR 제출을 승인하여 재개했다.
재개 직전 main과 `chore/octv-ui-docker-handover-0928` 브랜치는 첨부 ZIP 기준 커밋 `a5daafa4c487d99cdc46998b907a94dc0afece93`와 같음을 재확인했다.
최종 수정본은 이 작업 브랜치에서 PR로 제출한다. 형식 정리와 UI·설정·문서 변경을 구분하며, main 직접 수정·강제 푸시·자동 병합은 하지 않는다. PR 검토·병합 후 각 PC에서 pull해야 main의 수정본을 받을 수 있다. 병합 전 확인 절차는 GITHUB.md에 있다.
이전에 전달한 ZIP과 실행 소스는 같으며, PR 제출본에는 사용자 승인 이후의 GitHub 상태와 브랜치 확인 안내를 문서에 추가했다.

## 포함·제외
실제 인증·업무 API·DB 연결·AI·CCTV 연결·기관 전달은 구현하지 않았다.
ZIP에는 .git, node_modules, 개인 .env, 빌드·캐시·로그, DB 데이터·덤프를 포함하지 않는다. .env.example, DDL, 소스, 기존 로고·영상, 실행 문서, 수정·검증 표와 캡처는 포함한다.
