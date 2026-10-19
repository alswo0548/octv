/** 개발용 브라우저 회귀 검사: 한 사건의 Mock API만 사용하며 DB·실제 계정·외부 API에 접속하지 않습니다. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";
const require = createRequire(import.meta.url);
const { chromium } = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + "/playwright")
  : await import("playwright");
const { createServer } = await import(
  "../node_modules/vite/dist/node/index.js"
);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.resolve(
  process.env.OCTV_QA_OUTPUT ?? path.join(root, "qa-artifacts"),
);
await fs.mkdir(output, { recursive: true });
const user = {
  id: 73,
  email: "ui-test@example.invalid",
  name: "UI 검증",
  role: "CONTROL_ADMIN",
  agency_id: null,
  is_active: true,
  notification_enabled: true,
};
const now = "2026-10-19T16:30:00Z";
const incident = {
  id: 73,
  incident_no: "OCTV-UI-MOCK-001",
  cctv_id: 12,
  cctv_name: "개발 미리보기 CCTV",
  hazard_type: "severe_road_damage",
  status: "SENT",
  confidence: 0.89,
  detected_at: now,
  last_detected_at: now,
  latitude: 37.5,
  longitude: 127,
  region_code: "R1",
  risk_score: 80,
  risk_level: "HIGH",
  priority_score: 80,
  priority: "P1",
  analysis_status: "READY",
  representative_image_updated_at: now,
  detection_bbox_json: [],
  rule_version: "UI-MOCK",
  risk_breakdown_json: {
    context_snapshot: {
      captured_at: now,
      measurements: {
        rainfall_mm: { status: "OK", value: 32 },
        water_level_m: { status: "NO_MAPPING", value: null },
        blocked_lane_count: { status: "OK", value: 2 },
        nearby_hospital_distance_m: { status: "OK", value: 480 },
      },
    },
  },
  priority_breakdown_json: { risk_score: 80 },
};
const camera = {
  id: 12,
  external_cctv_id: "MOCK-CCTV-012",
  name: "개발 미리보기 CCTV",
  provider: "UTIC",
  address: "개발 검증용 위치",
  latitude: 37.5,
  longitude: 127,
  is_monitored: true,
  connection_status: "CONNECTED",
  video_quality_status: "GOOD",
  analysis_status: "RUNNING",
  last_frame_at: now,
  region_code: "R1",
  sido_name: "검증 시도",
  sigungu_name: "검증 지역",
  monitored_mode: "BASE",
};
const values = {
  base_analysis_interval_sec: 10,
  alert_analysis_interval_sec: 5,
  verify_analysis_interval_sec: 1,
  candidate_confidence_threshold: 0.35,
  candidate_min_detection_count: 3,
  temporal_validation_sec: 5,
  incident_confidence_threshold: 0.7,
  reconnect_interval_sec: 3,
  max_reconnect_attempts: 5,
  quality_threshold: 0.6,
};
const disconnected = [
  "candidate_confidence_threshold",
  "candidate_min_detection_count",
  "temporal_validation_sec",
  "incident_confidence_threshold",
];
const settings = {
  ...values,
  id: 1,
  updated_by: 73,
  updated_at: now,
  application: Object.fromEntries(
    Object.keys(values).map((k) => [
      k,
      {
        mode: disconnected.includes(k)
          ? "NOT_CONNECTED"
          : k.includes("reconnect")
            ? "RESTART_REQUIRED"
            : "NEXT_POLL",
        description: disconnected.includes(k)
          ? "사건화 연결 대기 · 읽기 전용"
          : k.includes("reconnect")
            ? "기존 Worker는 Runtime 재시작 필요"
            : "Runtime 다음 설정 조회 후 반영",
      },
    ]),
  ),
};
const route = {
  id: 90,
  route_name: "후보 A",
  distance_m: 4200,
  duration_sec: 540,
  total_score: 88,
  score_breakdown_json: {},
  disqualify_reason: null,
  route_path_json: {
    type: "LineString",
    coordinates: [
      [126.98, 37.49],
      [126.99, 37.505],
      [127, 37.5],
    ],
  },
  rule_version: "UI-MOCK",
  verification_status: "NEEDS_REVIEW",
  requires_review: true,
  navigation_available: true,
};
const agencies = {
  incident_id: 73,
  incident_status: "SENT",
  items: [
    {
      agency_id: 41,
      agency_name: "개발 검증용 도로관리",
      agency_type: "ROAD_MANAGEMENT",
      recommendation_rank: 1,
      recommendation_status: "DELIVERED",
      routes: [route],
    },
  ],
};
const support = [1, 2].map((n) => ({
  id: n,
  incident_id: 73,
  responder_id: 74,
  agency_id: 41,
  support_type: "EQUIPMENT",
  request_content: `개발 검증용 지원요청 ${n}`,
  created_at: now,
  responder_name: "테스트 대원",
  agency_name: "개발 검증용 도로관리",
}));
const stats = {
  filters: { start: "2026-09-21", end: "2026-10-20", confirmed_only: true },
  timezone: "Asia/Seoul",
  total_incident_count: 1,
  confirmed_incident_count: 1,
  average_confidence: 0.89,
  by_status: { SENT: 1 },
  by_hazard: { severe_road_damage: 1 },
  by_risk: { HIGH: 1 },
  by_priority: { P1: 1 },
  confidence_distribution: { "70-90": 1 },
  daily: Array.from({ length: 7 }, (_, i) => ({
    day: `2026-10-${14 + i}`,
    count: i === 6 ? 1 : 0,
  })),
  hourly: Array.from({ length: 24 }, (_, hour) => ({
    hour,
    count: hour === 1 ? 1 : 0,
  })),
};
let mode = "normal",
  videoMode = "prepareFailure",
  failure = "",
  delayPath = "",
  calls = [],
  unauthorized = [];
const server = await createServer({
  root: path.join(root, "frontend/web"),
  configFile: path.join(root, "frontend/web/vite.config.ts"),
  server: { host: "127.0.0.1", port: 0 },
});
await server.listen();
const base = `http://127.0.0.1:${server.httpServer.address().port}`;
const browser = await chromium.launch({
  headless: true,
  ...(process.env.OCTV_QA_BROWSER
    ? { executablePath: process.env.OCTV_QA_BROWSER }
    : {}),
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1465, height: 1050 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const result = [];
const check = (name) => {
  result.push(name);
  console.log("PASS " + name);
};
async function screenshot(name) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await page.evaluate(() => {
    let b = document.querySelector("#qa-banner");
    if (!b) {
      b = document.createElement("div");
      b.id = "qa-banner";
      b.textContent = "개발 검증용 API Mock · DB 미접속";
      b.style.cssText =
        "position:fixed;bottom:12px;right:12px;z-index:99999;padding:8px 12px;background:#06131f;color:#9be9f3;border:1px solid #66ddeb;border-radius:7px;font-size:12px";
      document.body.append(b);
    }
  });
  await page.screenshot({
    path: path.join(output, name + ".png"),
    fullPage: true,
  });
}
try {
  await page.route("https://tile.openstreetmap.org/**", (r) => r.abort());
  await page.route("**/qa-whep", (r) =>
    r.fulfill({ status: 503, body: "TEST_ONLY" }),
  );
  await page.route("**/api/**", async (r) => {
    const req = r.request();
    const u = new URL(req.url());
    const p = u.pathname;
    calls.push({ path: p, method: req.method(), query: u.search });
    const json = (value, status = 200) =>
      r.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (p === "/api/auth/login")
      return json({
        access_token: "MOCK-UNIT-TEST-TOKEN",
        token_type: "bearer",
        user,
      });
    if (req.headers().authorization !== "Bearer MOCK-UNIT-TEST-TOKEN") {
      unauthorized.push(p);
      return json({ detail: "unauthorized" }, 401);
    }
    if (delayPath === p)
      await new Promise((resolve) => setTimeout(resolve, 600));
    if (failure && p.startsWith(failure))
      return json({ detail: "TEST_ONLY" }, 500);
    if (p === "/api/auth/me") return json(user);
    if (p === "/api/incidents")
      return json({
        items: mode === "empty" ? [] : [incident],
        total: mode === "empty" ? 0 : 1,
        page: 1,
        page_size: 5,
      });
    if (p === "/api/incidents/73/image")
      return r.fulfill({
        contentType: "image/jpeg",
        body: await fs.readFile(
          path.join(root, "frontend/web/public/assets/road.jpg"),
        ),
      });
    if (p === "/api/incidents/73")
      return json(
        mode === "pending"
          ? {
              ...incident,
              representative_image_updated_at: null,
              analysis_status: "PENDING",
              risk_score: null,
              risk_level: null,
              priority_score: null,
              priority: null,
              risk_breakdown_json: null,
              priority_breakdown_json: null,
              rule_version: null,
            }
          : mode === "noimage"
            ? { ...incident, representative_image_updated_at: null }
            : incident,
      );
    if (p === "/api/dashboard")
      return json({
        summary: {
          monitored_cctv_count: 1,
          today_incident_count: 1,
          connection_error_count: 0,
          active_weather_alert_count: 0,
        },
        incidents: {
          items: mode === "empty" ? [] : [incident],
          page: 1,
          page_size: 5,
          total: mode === "empty" ? 0 : 1,
          total_pages: 1,
        },
      });
    if (p.endsWith("/external-status"))
      return json({
        weather_alerts: [],
        rainfall_mm: { status: "NO_MAPPING", value: null },
        water_level_m: { status: "NO_MAPPING", value: null },
        road_control_count: { status: "NO_MAPPING", value: null },
        focused_monitoring_cctv_count: 0,
        last_received_at: null,
      });
    if (p === "/api/support-requests/incidents/73") return json(support);
    if (p === "/api/agencies/incidents/73/recommendations")
      return json(agencies);
    if (p === "/api/routes/incidents/73/agencies/41")
      return json({
        incident_id: 73,
        agency_id: 41,
        analysis_status: "READY",
        recommendation_status: "DELIVERED",
        result_status: "NEEDS_REVIEW",
        items: [route],
      });
    if (p === "/api/settings/monitoring") {
      if (req.method() === "PUT") {
        const body = req.postDataJSON();
        assert.equal(body.updated_by, undefined);
        for (const k of disconnected) assert.equal(body[k], settings[k]);
        Object.assign(settings, body);
      }
      return json(settings);
    }
    if (p === "/api/cctvs") return json(mode === "empty" ? [] : [camera]);
    if (p === "/api/cctvs/12/monitoring") {
      camera.is_monitored = req.postDataJSON().enabled;
      camera.monitored_mode = camera.is_monitored ? "BASE" : "OFF";
      return json(camera);
    }
    if (p === "/api/cctvs/12/stream")
      return videoMode === "prepareFailure"
        ? json({ detail: "Mock 환경: 실제 영상 서버 없음" }, 502)
        : json({
            cctv_id: 12,
            playback_url: base + "/qa-playback",
            whep_url: base + "/qa-whep",
          });
    if (p === "/api/stats")
      return json(
        mode === "empty"
          ? {
              ...stats,
              total_incident_count: 0,
              confirmed_incident_count: 0,
              average_confidence: null,
              by_status: {},
              by_hazard: {},
              by_risk: {},
              by_priority: {},
              confidence_distribution: {},
              daily: stats.daily.map((p) => ({ ...p, count: 0 })),
              hourly: stats.hourly.map((p) => ({ ...p, count: 0 })),
            }
          : stats,
      );
    return json({ detail: "UNEXPECTED_TEST_ENDPOINT" }, 404);
  });
  await page.goto(base + "/#/settings");
  await page.getByText("로그인이 필요합니다.").waitFor();
  assert.equal(calls.length, 0);
  check("운영 화면 비로그인 차단");
  await page.getByRole("button", { name: "로그인 화면으로 이동" }).click();
  await page.getByLabel("이메일", { exact: true }).fill(user.email);
  await page
    .getByPlaceholder("비밀번호", { exact: true })
    .fill("MOCK-TEST-ONLY");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.getByText("긴급 사건 / P1 우선").waitFor();
  await page
    .getByText(incident.incident_no, { exact: false })
    .first()
    .waitFor();
  check("기존 로그인 → 실제 Dashboard API 4개 카드");
  await screenshot("restored-overview");
  await page
    .locator("aside")
    .getByRole("button", { name: "사건관리", exact: false })
    .click();
  await page.getByText("개발 검증용 지원요청 2", { exact: true }).waitFor();
  await page.locator(".stored-camera img").waitFor();
  check("사건 상세·지원요청 2건·기관 상태·대표 이미지");
  await screenshot("restored-incident-image");
  const withImage = await page.locator(".stored-camera").boundingBox();
  mode = "noimage";
  await page.getByRole("button", { name: "서버 정보 새로고침" }).click();
  await page.getByText("저장된 대표 이미지가 없습니다.").waitFor();
  const withoutImage = await page.locator(".stored-camera").boundingBox();
  assert.equal(withImage.height, withoutImage.height);
  check("대표 이미지 유무의 카드 높이 동일");
  await screenshot("restored-incident-no-image");
  mode = "pending";
  await page.getByRole("button", { name: "서버 정보 새로고침" }).click();
  await page.getByText("분석 결과가 아직 저장되지 않았습니다.").waitFor();
  assert.equal(
    await page.locator(".risk .scores strong").first().innerText(),
    "– / 100",
  );
  check("분석 대기: 가짜 점수 없음");
  await screenshot("restored-incident-pending");
  mode = "normal";
  await page.getByRole("button", { name: "서버 정보 새로고침" }).click();
  await page.getByRole("button", { name: "경로 비교 상세" }).click();
  await page
    .getByRole("button", { name: "경로 후보 A 확인", exact: true })
    .waitFor();
  check("기존 경로 API·지도·추가 확인 표시");
  await screenshot("restored-routes");
  await page
    .locator("aside")
    .getByRole("button", { name: "시스템 설정", exact: false })
    .click();
  await page.locator("#base_analysis_interval_sec").waitFor();
  await page.waitForFunction(
    () => document.querySelector("#base_analysis_interval_sec")?.value === "10",
  );
  assert.equal(
    await page.locator("#temporal_validation_sec").isDisabled(),
    true,
  );
  await page.locator("#base_analysis_interval_sec").fill("12");
  await page.getByRole("button", { name: "변경사항 저장" }).click();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await page.getByText("DB에 저장했습니다.", { exact: false }).waitFor();
  await page.waitForFunction(
    () => document.querySelector("#base_analysis_interval_sec")?.value === "12",
  );
  assert.equal(settings.base_analysis_interval_sec, 12);
  check("설정 저장·재조회·미연결 편집 차단");
  await screenshot("restored-settings");
  await page.getByRole("button", { name: "대상 선택", exact: true }).click();
  await page.getByRole("switch").waitFor();
  await page.getByRole("switch").click();
  await page.getByRole("button", { name: "확인", exact: true }).click();
  await page.waitForFunction(
    () => document.querySelector("[role=switch]")?.checked === false,
  );
  assert.equal(camera.is_monitored, false);
  check("CCTV 감시 변경·서버 재조회");
  await screenshot("restored-targets");
  camera.is_monitored = true;
  camera.monitored_mode = "BASE";
  await page
    .locator("aside")
    .getByRole("button", { name: "CCTV 모니터링", exact: false })
    .click();
  await page.getByText("영상 준비 실패", { exact: false }).waitFor();
  assert.equal(
    await page.locator(".camera-overlay-label").innerText(),
    "영상 대기 · MOCK-CCTV-012",
  );
  check("영상 준비 실패와 LIVE 구분");
  await screenshot("restored-monitor-failure");
  videoMode = "displayFailure";
  await page.evaluate(() => {
    window.RTCPeerConnection = class {
      iceGatheringState = "complete";
      localDescription = null;
      addTransceiver() {}
      async createOffer() {
        return { type: "offer", sdp: "TEST_ONLY" };
      }
      async setLocalDescription(value) {
        this.localDescription = value;
      }
      close() {}
    };
  });
  await page.getByRole("button", { name: "영상 다시 연결" }).click();
  await page
    .getByText("스트림 준비됨 · 브라우저 표시 실패", { exact: false })
    .waitFor();
  assert.equal(
    await page.locator(".camera-overlay-label").innerText(),
    "영상 대기 · MOCK-CCTV-012",
  );
  check("준비 성공 뒤 WHEP 표시 실패 구분 (RTC Mock)");
  await screenshot("restored-monitor-display-failure");
  mode = "empty";
  await page.getByRole("button", { name: "현재 상태 새로고침" }).click();
  await page.getByText("표시할 CCTV가 없습니다.").waitFor();
  check("실제 CCTV 0건의 빈 영상 화면");
  await screenshot("restored-monitor-empty");
  mode = "normal";
  await page
    .locator("aside")
    .getByRole("button", { name: "CCTV 운영통계", exact: false })
    .click();
  await page
    .getByRole("heading", { name: "시간대별 사건 수 · 한국시간" })
    .waitFor();
  await page.waitForFunction(
    () => document.querySelector(".stat-card strong")?.textContent === "1건",
  );
  check("실제 통계 응답→기존 차트");
  await screenshot("restored-stats");
  await page.getByLabel("시작일", { exact: true }).fill("2026-10-20");
  await page.getByLabel("종료일", { exact: true }).fill("2026-10-20");
  await page.getByLabel("CCTV", { exact: true }).selectOption("12");
  await page.waitForTimeout(100);
  assert.ok(
    calls.some(
      (c) =>
        c.path === "/api/stats" &&
        c.query.includes("cctv_id=12") &&
        c.query.includes("start=2026-10-20"),
    ),
  );
  check("통계 기간·CCTV 필터 요청");
  mode = "empty";
  await page.getByRole("button", { name: "다시 조회", exact: true }).click();
  await page.getByText("선택한 기간과 조건의 사건이 없습니다.").waitFor();
  await screenshot("restored-stats-empty");
  failure = "/api/stats";
  await page.getByRole("button", { name: "다시 조회", exact: true }).click();
  await page.getByRole("alert").last().waitFor();
  check("0건과 조회 실패 구분");
  await screenshot("restored-stats-error");
  failure = "";
  await page
    .locator("aside")
    .getByRole("button", { name: "사건관리", exact: false })
    .click();
  await page.getByText("조건에 맞는 사건이 없습니다.").waitFor();
  await screenshot("restored-incidents-empty");
  mode = "normal";
  failure = "/api/incidents/73";
  await page.getByRole("button", { name: "서버 정보 새로고침" }).click();
  await page.getByText("사건 정보를 불러오지 못했습니다.").waitFor();
  await screenshot("restored-incident-error");
  failure = "";
  delayPath = "/api/incidents/73";
  await page.getByRole("button", { name: "서버 정보 새로고침" }).click();
  await page.getByText("선택 사건 조회 중", { exact: true }).waitFor();
  await screenshot("restored-incident-loading");
  delayPath = "";
  await page.locator(".stored-camera img").waitFor();
  check("로딩·조회 실패의 카드 배치 보존");
  await page.setViewportSize({ width: 768, height: 1024 });
  await screenshot("restored-incident-tablet");
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  );
  check("태블릿 가로 넘침 없음");
  await page.setViewportSize({ width: 1465, height: 1050 });
  await page
    .locator("aside")
    .getByRole("button", { name: "로그아웃", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "로그아웃", exact: true })
    .click();
  await page.getByRole("button", { name: "로그인", exact: true }).waitFor();
  const before = calls.length;
  await page.goto(base + "/#/stats");
  await page.getByText("로그인이 필요합니다.").waitFor();
  assert.equal(calls.length, before);
  check("로그아웃 후 운영 요청 차단");
  assert.deepEqual(unauthorized, []);
  assert.deepEqual(errors, []);
  check("브라우저 오류 없음·모든 운영 API JWT 첨부");
} catch (error) {
  await screenshot("failure-debug");
  console.log("FAILURE_URL", page.url());
  console.log((await page.locator("body").innerText()).slice(-5000));
  throw error;
} finally {
  await fs.writeFile(
    path.join(output, "browser-results.json"),
    JSON.stringify({ passed: result, errors, unauthorized }, null, 2),
  );
  await browser.close();
  await server.close();
}
