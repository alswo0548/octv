# OCTV 로컬 실시간 YOLO 바운딩박스 검증 (운영 무관)

## 실행

Windows CMD에서 기존 프로젝트 루트 `C:\KDT2604\최종 프로젝트\octv` 기준:

```bat
git fetch origin fix/live-bbox-visual-tracking-20261102
git worktree add --detach ..\octv-bbox-preview FETCH_HEAD
cd /d "C:\KDT2604\최종 프로젝트\octv-bbox-preview"
tools\run_live_bbox_preview.bat
```

* 별도 worktree이므로 기존 브랜치·미커밋 파일은 변경하지 않습니다.
* 첫 실행 때 작업 폴더 전용 `npm ci`가 실행될 수 있습니다. 기존 venv(보통 `../octv/.venv`)를 읽고, 프로젝트 코드는 수정하지 않습니다.
* `http://127.0.0.1:4173/live-bbox-preview.html`에 접속합니다.
* **52초 침수 구간부터 보기**를 클릭합니다. 이것은 실제 N001 MP4 및 실제 `N052_S2_epoch005.pt` YOLO 추론을 사용하며, 약 3초 주기로 새로운 추론을 생성합니다.
* 실시간 추론값은 청록색, 이후 브라우저 영상 추적은 노란색으로 구분합니다. 시간 불일치/저텍스처/차단/구간 만료 시 화면에서 숨깁니다.
* 현재 개발 중인 UI와 동일한 `LiveBboxOverlay.tsx` 모듈을 사용하지만, **독립 로컬 테스트이며 운영 서버·DB·알림의 처리 성능을 재현하지는 않습니다.** 로컬 원본 MP4의 재생 성능은 DigitalOcean 모바일 압축본과 다를 수 있습니다.
* '영상 시각', '실제 탐지', '브라우저 프레임 드롭'을 직접 확인합니다.

## 종료 / 롤백

테스트 화면에서 **테스트 중지**를 누르고, 새로 열린 터미널 2개에서 `Ctrl+C`로 종료합니다. 운영 서버는 원래대로 유지됩니다. 필요하면 원본 프로젝트에서 `git worktree remove ..\octv-bbox-preview`로 이 별도 폴더만 삭제할 수 있습니다. (로컬 폴더에 임의 변경사항이 있으면 먼저 확인하세요.)

## 제한 / 보호

- `127.0.0.1:8765` (Python API) / `127.0.0.1:4173` (Vite)로만 연결합니다.
- PostgreSQL, Redis, FCM, DigitalOcean, API 키, 운영 JWT와 통신하지 않습니다.
- 서버 YOLO 분석 주기를 약 3초로 재현하지만, 오버레이 성공률은 로컬 CPU/브라우저 동기화에 따라 달라집니다.
- 실제 운영용 Docker 이미지 일부가 누락되어 있어 **운영 배포 롤백은 이 테스트와 별개로 검증해야 합니다.**
