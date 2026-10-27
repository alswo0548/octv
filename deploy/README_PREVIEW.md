# OCTV 배포 준비 초안 — PR/운영 적용 전 필수 확인

**상태: 로컬 이미지 빌드·라이브러리 Import·HTTP `/health` 및 `/openapi.json`·DB 물리/논리 복원 검증 PASS(이전 검증 기록), 실제 DigitalOcean HTTPS/FCM/CCTV E2E는 미검증.** 이 패키지는 GitHub 기존 파일을 변경하거나 서버를 생성하지 않습니다.

## 코드 보호
- 원래 `compose.yaml`, `mediamtx.yml`, 팀원 담당 Pipeline/로그인, 운영 DB는 변경하지 않습니다.
- `deploy/compose.prod.yaml`은 별도 운영 스택(`octv-prod`)입니다. 기존 로컬 `octv_postgres_data`와 신규 운영 DB 볼륨을 동일하다고 간주하지 마세요. `docker compose down -v`와 `docker system prune --volumes`는 절대 실행하지 않습니다.
- 승인 Demo v5에는 모델 3개 + MP4 3개가 필요하며 `python -m scripts.check_predeploy_readonly` SHA256 검증을 통과해야 합니다.
- 로컬 실제 설정 `ai/.env.runtime.json`과 저장소 공용 `ai/runtime_config.json`은 **내용이 다릅니다**. 저장소 기본 파일을 운영에 대신 사용하지 마세요. 실제 설정은 Git/Docker 이미지에 포함하지 않고 `/etc/octv/runtime-config.json`에 안전하게 복사해 마운트합니다. 로그/채팅/PR에 원문이나 비밀 키를 노출하지 마세요.
- `OCTV_YOLO_MODEL_PATH`는 기본/UTIC 영상에도 사용되는 모델 경로입니다. 현재 이 예시는 로컬에서 사용한 **Cycle7.pt**를 가리키지만, 이 모델은 일반 UTIC 운영용으로 검증된 모델이 아닙니다. DEMO 외 사용 범위는 별도 승인 전 확대하지 않습니다.
- 기존 로컬 데이터베이스는 자동 전송되지 않습니다. pg_dump → 별도 DB로 복구 검증 후에만 운영 이관합니다.

## 준비해야 할 Linux 경로
- 리포지터리 클론: `/opt/octv` (예시)
- 환경: `/etc/octv/production.env` (chmod 600, 비밀정보 Git 제외)
- Firebase 서버 JSON: `/etc/octv/firebase-admin.json` (권한 10001 소유, chmod 400)
- Demo/가중치(읽기 전용): `/srv/octv-assets/demo/videos/{N001_demo.mp4,N002_demo.mp4,N003_demo.mp4,_v5/weights/*.pt}`
- 현재 로컬 설정과 같은 기본 모델(읽기 전용): `/srv/octv-assets/demo/videos/_v5/weights/Cycle7.pt` (UTIC 일반 운영 적합성은 별도 승인 필요)
- LangGraph 유효 설정: `/etc/octv/runtime-config.json` ← 로컬 `ai/.env.runtime.json`의 사본 (컨테이너 내부 `/run/octv/runtime-config.json`에 읽기 전용 연결, 권한 UID 10001)
- DB 백업: `/srv/octv-backups` (서버 외부에도 보존)
- 위 `demo/videos` 구성은 Git에 없으므로 실제 존재 및 SHA256 검사 필수

## 먼저 반드시 풀어야 할 차단 요소
1. 현재 로컬의 `OCTV_YOLO_MODEL_PATH=demo/videos/_v5/weights/Cycle7.pt`를 그대로 반영했습니다. *실제 UTIC 일반 탐지 모델로 검증된 것은 아니며*, 최종 배포 전 사용 범위 확인이 필요합니다.
2. 대용량 `.pt`와 Demo 3개 `.mp4`의 전송 및 SHA256 검증.
3. Linux Docker 이미지 빌드 시 torch+cpu/requirements 버전 설치 및 CPU 메모리 사용 검증.
4. 현재 DB 백업 이관 여부(사건/기관/사용자/알림 유지)와 `DATABASE_URL` 인코딩.
5. 배포용 메인 도메인 소유 및 DNS A 레코드, HTTPS 인증서 자동 발급. 스트림 호스트는 인증이 마련될 때까지 비활성입니다.
6. MediaMTX의 개발용 permissive `authInternalUsers` 때문에 외부 WebRTC 공개를 **기본 차단**했습니다. `Caddyfile`에서 공개 스트림 프록시를 제거했고 UDP 8189는 기본적으로 루프백 주소에만 바인딩합니다. UTIC 외부 실시간 재생은 접근 제어 설계·검증 후 별도로 승인해야 합니다.
7. 실제 데이터·Firebase 자격증명을 서버에 옮기는 방법과 접근 권한.
8. FCM OFF로 시작하며 수신 기관·토큰 확인 뒤 별도 승인하에 ON. 모바일 FCM 기기 토큰은 Redis에 저장되므로 PostgreSQL만 복원하면 기기 등록은 따라오지 않습니다. Redis 이관을 독립 검증하거나, 새 HTTPS API로 APK에서 로그인/토큰 재등록을 확인해야 합니다.
9. Android APK는 빌드 시 `EXPO_PUBLIC_API_BASE_URL`이 새 공개 HTTPS 도메인을 가리키도록 설정하여 다시 빌드/설치 후 실제 연결을 검증합니다. 기존 APK를 그대로 사용한다고 새 서버를 자동으로 바라보지는 않습니다.

## 순서(명령 위치: Linux SSH에서, 서버 생성·비용 승인 후)
```bash
# 1. Clone approved commit and place this package's files in repo root.
# 2. Protect files; adapt hostname and secrets offline (don't paste secrets in chat).
sudo mkdir -p /etc/octv /srv/octv-assets/demo/videos/_v5/weights /srv/octv-assets/models /srv/octv-backups
# 3. Validate all values exist. The sample is NOT safe to launch as-is.
cd /opt/octv
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml config --quiet
# 4. Build only after image/network/dependency review.
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml build
# 5. Create/restore DB safely, before enabling CCTV and Push.
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml up -d db redis mediamtx
# 6. Run read-only preflight in app image (when the DB is ready).
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml run --rm --no-deps api python -m scripts.check_predeploy_readonly
# 7. Start only web/API/analysis after DB restoration. Push and CCTV MUST remain opt-in.
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml up -d api analysis web caddy
# 8. ONLY after verifying models, DB, and single-runtime status, explicitly start CCTV.
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml up -d cctv
# 9. ONLY after Firebase secret file, recipients, Redis tokens and push policy are verified:
# Set OCTV_PUSH_ENABLED=1 and timezone-aware OCTV_PUSH_START_AT in the
# protected production.env first, then recreate API + notifications explicitly.
# Profile is not a permanent reboot block: an opt-in container with
# restart:unless-stopped WILL restart after Docker/host restarts unless stopped.
# docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml up -d notifications
# 10. ONLY with OCTV_PUSH_ENABLED=1 AND OCTV_PUSH_RECOVERY_ENABLED=1:
# docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml up -d beat
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml ps
```

## Inspect logs and health
```bash
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml ps
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml logs --tail=80 api cctv analysis notifications
curl -fsS https://octv.example.com/health
bash deploy/disk-report.sh
bash deploy/backup-db.sh
```
`/health`는 앱 자체 생존 신호이며 DB/AI/FCM 전체 정상 증거는 아닙니다.

## Release and rollback
- 운영에 쓸 Git SHA를 별도 기록하고 PR 리뷰·병합 후 Git fetch/checkout 및 영향 서비스만 `build`/`up -d --no-deps`.
- DB Volume은 컨테이너 재빌드와 분리됩니다. **스키마 이관 후에는 오래된 앱으로 되돌릴 때 호환성 확인 필수**.
- rollback: 저장한 이전 정상 Git SHA로 체크아웃 → 재빌드 → 해당 서비스만 교체. 운영 DB 덮어쓰기는 별도 승인 전 금지.

## 외부 접근 / 서버 이전
- 방화벽: SSH TCP 22 (관리자 IP 한정), HTTP 80, HTTPS 443. UTIC WebRTC는 아직 외부 비활성; UDP 8189 공개는 인증·접근 통제 후 별도 승인 필요.
- DB 5432, Redis 6379, MediaMTX Control API 9997 외부 공개 금지.
- DNS A: `octv.example.com` → 현재 서버 IP; 실제 메인 도메인으로 변경. 스트림용 DNS는 승인·인증 설계 전 불필요.
- Cloud 이동 시 새 서버/동일 Compose/DB·파일 복원/서버 접근 API IP 재등록/DNS 재지정/운영 점검.
- 이 가이드는 실제 Linux/DO 배포 성공 기록이 아니며 Word 학습 문서는 배포 완료 후 작성.

## Optional daily DB backups (only after a successful manual backup and tested restore)
- The included `deploy/systemd/octv-db-backup.service` and `.timer` are templates for `/opt/octv`.
- Install with `sudo cp deploy/systemd/octv-db-backup.* /etc/systemd/system/` and `sudo systemctl daemon-reload`.
- Only after manual backup and restore test: `sudo systemctl enable --now octv-db-backup.timer`.
- Verify with `systemctl list-timers octv-db-backup.timer` and `journalctl -u octv-db-backup.service`.
- **Important:** The timer currently has no retention or remote backup sync; configure both after measuring backup size. Existing backups must not be overwritten or silently deleted. Keep backups off-server and test restoring to a separate database; volume persistence alone is not a backup.

## Database migration gap
- The original local Compose initializes a database from files in `database/init`, while the draft production Compose does not auto-run those files. Restore into a NEW production database/volume (do not overwrite the local or verified backup).
- Do not enable API/CCTV against an empty production DB. First export the existing DB; use a **separate disposable DB** to test logical restore, roles, schema and critical row counts.
- Do not issue `pg_restore --clean` or destructive schema commands against production.

## 2026-10-27 안전 설정 보완
- `cctv`, `notifications`, `beat`는 Compose profiles로 일반 `up -d`에서 자동 시작하지 않습니다. **명시적 서비스 시작 명령은 여전히 실행**되므로 위 절차를 지키세요.
- `FORWARDED_ALLOW_IPS=172.16.0.0/12`는 기본 Docker Bridge 주소 대역을 허용하여 Caddy가 넘긴 HTTPS 원본 스킴을 API가 이해하게 합니다. 실제 Droplet에서 Caddy 컨테이너 IP 대역을 확인하고 조정하세요.
- Caddy는 웹/API만 외부 공개합니다. `Referrer-Policy: no-referrer`로 Demo URL의 짧은 만료 토큰이 외부 Referer로 전파되는 위험을 줄입니다. URL 토큰 노출 자체가 없어지는 것은 아닙니다. 운영 웹에서 UTIC WebRTC 재생 URL은 별도 스트림 호스트가 없어 아직 사용 불가능합니다. 보안 검토 없이 공개하려고 `Caddyfile`에 원래 공개용 스트림 프록시를 다시 붙이지 마세요.
- UDP `8189`도 기본 `127.0.0.1` 바인딩이며, `OCTV_WEBRTC_UDP_BIND=0.0.0.0`으로 전환하기 전에 인증·방화벽·브라우저 재생을 테스트하세요.
- 로컬 검증된 DB 데이터는 백업 시점 사건 55건. 이전 직전 반드시 최신 백업 재생성, 논리 복원 후 사용자/기관/CCTV/경로/알림 레코드 및 JWT 로그인 확인 필요.
- `deploy/production.env.example`는 실제 비밀번호·키의 예시 파일이 아닙니다. 로컬에서 `up -d`하지 마세요.


## 2026-10-27 로컬 실행 설정 일치 패치
- 확인된 로컬 값: 운영 시작 모델 `demo/videos/_v5/weights/Cycle7.pt`, 판단 설정 `ai/.env.runtime.json`, DEMO=1, DECISION=1, PUSH=1, DEMO_RISK=1, AUTO_MAPPING=1, PUSH_RECOVERY=0.
- 운영 서버 초기 PUSH는 **0으로 강제 유지**합니다. 기존 로컬 PUSH=1을 무심코 복제하지 않습니다.
- `OCTV_RUNTIME_CONFIG_FILE`은 호스트 비밀 JSON 파일의 절대 경로, `OCTV_RUNTIME_CONFIG`는 컨테이너 내부 읽기 경로입니다. `${OCTV_RUNTIME_CONFIG_FILE:-/etc/octv/runtime-config.json}`가 바인딩됩니다.
- 파일 준비(Linux, 서버 생성/승인 후): `/etc/octv/runtime-config.json`에 검증된 로컬 파일을 안전하게 전송, `sudo chown 10001:10001 /etc/octv/runtime-config.json; sudo chmod 0400 /etc/octv/runtime-config.json` (실제 경로/디렉터리 접근권한 포함 점검).
- 런타임 설정 JSON은 로컬 환경에서 그대로 가져와야 합니다. 값 차이 여부만 확인했으며 구체적인 키/매핑 차이는 **검증 전**입니다.
- 배포 전에 API/analysis/cctv 컨테이너에서 같은 파일을 실제로 열 수 있는지 확인하고, `get_runtime_config()`가 정상 검증되는지 테스트합니다.
- 현재 Cycle7는 Demo 영상 시연과 연결된 모델일 뿐 UTIC용 일반화 정확도를 보장하지 않습니다. 변경 시 사용자 승인 및 별도 모델 파일/무결성 검사 필요.

## 배포 전 신규 확인 사항 (2026-10-27 최종 파일 검수)
- **FCM/Redis**: `redis_data`는 영속 볼륨이나 백업 자동화 대상은 현재 PostgreSQL만입니다. Redis 기기 토큰과 알림 처리 상태를 이관하지 않으면 새 서버에서 모바일 기기를 다시 등록해야 할 수 있습니다. Redis 백업/복원은 별도 분리된 테스트 컨테이너에서 검증 후에만 수행합니다.
- **알림 Worker 마운트**: Compose의 `notifications`는 기존 공통 마운트 3개와 Firebase JSON 마운트를 함께 선언합니다. YAML `volumes` 목록은 병합되지 않고 통째로 교체되므로 기존 초안의 누락 문제를 수정했습니다.
- **DB 비밀값 격리**: PostgreSQL 컨테이너에는 `POSTGRES_DB/USER/PASSWORD`만 전달합니다. API 키·JWT_SECRET 전체가 DB 컨테이너 환경에 들어가던 초안 설정을 제거했습니다. `docker compose config`를 `--quiet` 없이 출력하면 비밀값이 드러날 수 있으니 공유하지 마세요.
- **권한/FS**: Linux에서 `uid=10001` 앱 사용자가 `/etc/octv/runtime-config.json`, Firebase 비밀 파일을 읽을 수 있고, 세 경로(`/srv/octv-assets/demo/videos`, `/srv/octv-assets/models`, `/etc/octv/runtime-config.json`)가 실제 존재하는지 확인하세요. Docker bind `create_host_path: false`는 누락을 자동 생성하지 않습니다.
- **서비스 시작**: profiles는 처음 `up -d`할 때 빠지게 만들 뿐입니다. 한 번 실행된 `restart: unless-stopped` 서비스는 호스트 재부팅 후 다시 뜰 수 있으니 CCTV·FCM 상태와 중복 Worker를 점검하세요.
- **UTIC 화면 제한**: `MEDIAMTX_WEBRTC_BASE_URL=https://stream.octv.example.com`은 *미개통 주소 예시*입니다. WebRTC WHEP/ICE 공개 엔드포인트와 인증 없이는 외부 브라우저 UTIC 실시간 재생은 **FAIL/미구현**으로 남습니다. 영상 재난 시연(승인 MP4)은 FastAPI 프록시를 통해 별도 제공됩니다. 개발용 MediaMTX 설정의 익명 API 권한을 그대로 공인 인터넷에 내보내지 마세요.
- **운영 유사성**: 로컬 이미지 테스트는 Dockerfile+소스의 실행 가능성 확인입니다. 실제 Droplet에서 같은 Git SHA, 모델·영상 SHA256, 런타임 JSON, 환경변수, 이미지 CPU 아키텍처를 확인한 뒤 컨테이너 시작 검증을 다시 진행합니다. `python:3.12-slim-bookworm`, `node:24-alpine`, `redis:7-alpine`, `caddy:2-alpine`, `mediamtx:1` 같은 변동 태그는 재빌드 시 바이트 동일성을 보장하지 않습니다.
- **복구 범위**: PostgreSQL 백업 복원 PASS(로컬 55건)는 Redis·Caddy 인증서·모델·영상·실행 JSON까지 포함하는 전체 시스템 재해복구 PASS와 다릅니다. 서버 밖 별도 백업 및 복원 연습이 필요합니다.
- **최종 PR 게이트**: 12개 파일 외 변경 금지, `.env`·실제 Firebase JSON·런타임 비밀 JSON·덤프·`.pt`·`.mp4` Git 미포함 확인. 사용자가 승인할 때만 Commit/Push/PR을 생성하세요.
