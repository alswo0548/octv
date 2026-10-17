/**
 * 전체 흐름: 실제 push.ts·app.config.ts를 메모리에서 변환 → 가짜 Android SDK 주입 → 동작 확인.
 * 주요 기능: 실제 네이티브·Firebase·자격증명을 사용하지 않는 알림 adapter와 빌드 설정 개별 검사.
 * 이 결과는 APK 설치·휴대폰 수신 검증을 대신하지 않습니다. 프로젝트 루트에서 실행합니다.
 * 실행: node --test --test-isolation=none tests/mobile_push.test.mjs (Node 24).
 */
import fs from "node:fs";
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";
import test, { before, after } from "node:test";
import { createNotificationController } from "../frontend/mobile/src/notifications.ts";
const projectRequire = createRequire(path.resolve("package.json"));
const ts = projectRequire("typescript");

// TypeScript를 실행 가능한 메모리 문자열로 바꾸며 프로젝트 파일은 수정하지 않습니다.
function compile(file) {
  return ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
    },
  }).outputText;
}
const compiledPush = compile("frontend/mobile/src/push.ts");
const payload = {
  schema_version: "1",
  type: "INCIDENT_DELIVERED",
  incident_id: "42",
  notification_id: "7",
};
const tick = () => new Promise(setImmediate);

// 실제 Firebase의 네 필드와 Android가 덧붙이는 기본 응답 형태를 구성합니다.
function event(id = "message-1", data = payload) {
  return {
    actionIdentifier: "default",
    notification: {
      request: {
        identifier: id,
        content: { data },
        trigger: { type: "push" },
      },
    },
  };
}

// 네이티브 SDK 대신 호출 기록과 알림 이벤트를 직접 조절할 수 있는 가짜 SDK를 제공합니다.
function fixture(platform = "android", environment = "standalone") {
  const state = {
    calls: [],
    stored: null,
    granted: true,
    canAskAgain: true,
    grantOnRequest: true,
    token: "mock-fcm-token-for-adapter-test-only",
    last: null,
    handler: null,
    received: null,
    response: null,
    tokenChanged: null,
    removed: 0,
    emitWhenRead: false,
  };
  const notifications = {
    AndroidImportance: { HIGH: 4 },
    AndroidNotificationVisibility: { PRIVATE: 0 },
    DEFAULT_ACTION_IDENTIFIER: "default",
    async setNotificationChannelAsync(id, options) {
      state.calls.push("channel");
      state.channel = { id, ...options };
    },
    async getPermissionsAsync() {
      state.calls.push("permissions");
      return { granted: state.granted, canAskAgain: state.canAskAgain };
    },
    async requestPermissionsAsync() {
      state.calls.push("request");
      return { granted: state.grantOnRequest };
    },
    async getDevicePushTokenAsync() {
      state.calls.push("token");
      if (state.calls.filter((value) => value === "token").length > 3)
        throw new Error("토큰 재조회가 반복됩니다.");
      // SDK 57 Android 실제 구현도 getDevicePushTokenAsync에서 onNewToken을 발생시킵니다.
      if (state.emitWhenRead)
        state.tokenChanged?.({ type: "android", data: state.token });
      return { type: "android", data: state.token };
    },
    async dismissAllNotificationsAsync() {
      state.calls.push("dismiss");
    },
    clearLastNotificationResponse() {
      state.calls.push("clear");
      state.last = null;
    },
    getLastNotificationResponse() {
      return state.last;
    },
    setNotificationHandler(handler) {
      state.handler = handler;
    },
    addNotificationReceivedListener(callback) {
      state.received = callback;
      return {
        remove() {
          state.removed++;
        },
      };
    },
    addNotificationResponseReceivedListener(callback) {
      state.response = callback;
      return {
        remove() {
          state.removed++;
        },
      };
    },
    addPushTokenListener(callback) {
      state.tokenChanged = callback;
      return {
        remove() {
          state.removed++;
        },
      };
    },
    scheduleNotificationAsync() {
      throw new Error("Android가 표시한 알림을 중복 생성하면 안 됩니다.");
    },
  };
  const modules = {
    "react-native": { Platform: { OS: platform } },
    "expo-constants": {
      __esModule: true,
      default: { executionEnvironment: environment },
      ExecutionEnvironment: { StoreClient: "storeClient" },
    },
    "expo-notifications": notifications,
    "expo-secure-store": {
      async getItemAsync() {
        state.calls.push("read-id");
        return state.stored;
      },
      async setItemAsync(key, value) {
        state.calls.push("write-id");
        state.stored = value;
      },
    },
    "expo-crypto": {
      randomUUID() {
        state.calls.push("uuid");
        return "12345678-1234-4123-8123-123456789abc";
      },
    },
  };
  const module = { exports: {} };
  new Function("module", "exports", "require", compiledPush)(
    module,
    module.exports,
    (name) => {
      state.calls.push("load:" + name);
      if (!(name in modules))
        throw new Error("허용하지 않은 실제 모듈 호출: " + name);
      return modules[name];
    },
  );
  return { api: module.exports, state };
}

test("FCM data와 일반 종료 extras에서 네 필드만 전달", () => {
  const { api } = fixture();
  assert.deepEqual(
    api.extractAndroidNotificationData(
      event("m", {
        ...payload,
        "google.message_id": "m",
        url: "https://ignored.example",
      }),
    ),
    payload,
  );
  assert.deepEqual(
    api.extractAndroidNotificationData({
      request: {
        content: { data: payload },
        trigger: { type: "push", remoteMessage: { data: payload } },
      },
    }),
    payload,
  );
});
test("remoteMessage·Expo body 보완과 충돌 데이터 거부", () => {
  const { api } = fixture();
  assert.deepEqual(
    api.extractAndroidNotificationData({
      request: { content: {}, trigger: { remoteMessage: { data: payload } } },
    }),
    payload,
  );
  assert.deepEqual(
    api.extractAndroidNotificationData({
      request: {
        content: {},
        trigger: { remoteMessage: { data: { body: JSON.stringify(payload) } } },
      },
    }),
    payload,
  );
  assert.equal(
    api.extractAndroidNotificationData({
      request: {
        content: { data: payload },
        trigger: { remoteMessage: { data: { ...payload, incident_id: "99" } } },
      },
    }),
    null,
  );
});
test("잘못된 버전·ID·표시용 본문은 사건 이동에 사용하지 않음", () => {
  const { api } = fixture();
  for (const data of [
    null,
    [],
    { ...payload, schema_version: "2" },
    { ...payload, incident_id: 42 },
    { ...payload, notification_id: "0" },
    { ...payload, type: "OPEN_URL" },
  ]) {
    assert.equal(api.extractAndroidNotificationData(event("m", data)), null);
  }
  assert.equal(
    api.extractAndroidNotificationData({
      request: { content: { body: JSON.stringify(payload) } },
    }),
    null,
  );
});
test("web·iOS·Expo Go에서 native 알림 모듈을 실행하지 않음", async () => {
  for (const [platform, environment] of [
    ["web", "standalone"],
    ["ios", "standalone"],
    ["android", "storeClient"],
  ]) {
    const { api, state } = fixture(platform, environment);
    assert.equal(state.calls.length, 0);
    assert.equal(await api.createAndroidPushDriver(), null);
    assert.ok(!state.calls.includes("load:expo-notifications"));
  }
});
test("채널 → 권한 → FCM 토큰 순서와 설치 UUID 유지", async () => {
  const { api, state } = fixture();
  state.granted = false;
  const driver = await api.createAndroidPushDriver();
  const first = await driver.prepareDevice();
  const second = await driver.prepareDevice();
  assert.equal(first.platform, "android");
  assert.equal(first.deviceId, second.deviceId);
  assert.ok(
    state.calls.indexOf("channel") < state.calls.indexOf("permissions"),
  );
  assert.ok(state.calls.indexOf("request") < state.calls.indexOf("token"));
  assert.equal(state.calls.filter((value) => value === "uuid").length, 1);
  assert.equal(state.channel.id, "octv_incident_delivery");
  assert.equal(state.channel.sound, "default");
});
test("권한 거부 시 토큰 미요청·로그아웃 UUID는 별도로 조회", async () => {
  const { api, state } = fixture();
  state.granted = false;
  state.canAskAgain = false;
  const driver = await api.createAndroidPushDriver();
  assert.equal(await driver.prepareDevice(), null);
  await driver.getInstallationId();
  assert.ok(!state.calls.includes("token"));
  assert.ok(!state.calls.includes("request"));
});
test("Expo Push Token을 FCM으로 등록하지 않음", async () => {
  const { api, state } = fixture();
  state.token = "ExpoPushToken[invalid-for-fcm]";
  const driver = await api.createAndroidPushDriver();
  await assert.rejects(driver.prepareDevice(), /FCM/);
});
test("일반 종료 복원과 listener의 동일 터치는 한 번 전달", async () => {
  const { api, state } = fixture();
  state.last = event();
  let opened = 0;
  let release;
  const done = new Promise((resolve) => {
    release = resolve;
  });
  const cleanup = api.startAndroidPush({
    shouldPresent: () => true,
    onResponse() {
      opened++;
      return done;
    },
    onReceived() {},
    onTokenChanged() {},
  });
  await tick();
  state.response(event());
  release(true);
  await tick();
  assert.equal(opened, 1);
  assert.equal(state.last, null);
  cleanup();
  assert.equal(state.removed, 3);
  assert.equal(state.handler, null);
});
test("실행 중 알림은 인증 상태와 중복 표시 여부를 확인", async () => {
  const { api, state } = fixture();
  let allowed = false;
  let received = 0;
  const cleanup = api.startAndroidPush({
    shouldPresent: () => allowed,
    onResponse() {},
    onReceived() {
      received++;
    },
    onTokenChanged() {},
  });
  await tick();
  const notification = event().notification;
  assert.equal(
    (await state.handler.handleNotification(notification)).shouldShowBanner,
    false,
  );
  allowed = true;
  assert.equal(
    (await state.handler.handleNotification(notification)).shouldShowBanner,
    true,
  );
  assert.equal(
    (await state.handler.handleNotification(notification)).shouldPlaySound,
    false,
  );
  state.received(notification);
  await tick();
  assert.equal(received, 1);
  cleanup();
});
test("토큰 갱신·listener 정리·로그아웃 이후 설치 UUID 보존", async () => {
  const { api, state } = fixture();
  let refreshed = 0;
  const cleanup = api.startAndroidPush({
    shouldPresent: () => true,
    onResponse() {},
    onReceived() {},
    onTokenChanged() {
      refreshed++;
    },
  });
  await tick();
  state.tokenChanged({ type: "ios", data: "ignored" });
  state.tokenChanged({ type: "android", data: "unused-event-token" });
  await tick();
  assert.equal(refreshed, 1);
  const driver = await api.createAndroidPushDriver();
  const before = await driver.getInstallationId();
  state.last = event();
  await driver.clearPresentedNotifications();
  assert.equal(await driver.getInstallationId(), before);
  assert.equal(state.last, null);
  cleanup();
  const other = fixture();
  other.api.startAndroidPush({
    shouldPresent: () => true,
    onResponse() {
      throw new Error("취소된 작업");
    },
    onReceived() {},
    onTokenChanged() {},
  })();
  await tick();
  assert.equal(other.state.response, null);
});
test("오래된 터치 처리가 더 최근 터치 캐시를 지우지 않음", async () => {
  const { api, state } = fixture();
  let release;
  const deferred = new Promise((resolve) => {
    release = resolve;
  });
  state.last = event("old");
  const cleanup = api.startAndroidPush({
    shouldPresent: () => true,
    onResponse: () => deferred,
    onReceived() {},
    onTokenChanged() {},
  });
  await tick();
  const newer = event("new", { ...payload, notification_id: "8" });
  state.last = newer;
  release();
  await tick();
  assert.equal(state.last, newer);
  cleanup();
});
test("SDK getToken의 자체 토큰 이벤트가 무한 재등록을 만들지 않음", async () => {
  const { api, state } = fixture();
  state.emitWhenRead = true;
  let refreshed = 0;
  const driver = await api.createAndroidPushDriver();
  const cleanup = api.startAndroidPush({
    shouldPresent: () => true,
    onResponse() {},
    onReceived() {},
    async onTokenChanged() {
      refreshed++;
      await driver.prepareDevice();
    },
  });
  await tick();
  await driver.prepareDevice();
  await tick();
  assert.equal(refreshed, 0);
  const replacement = "mock-token-replacement-for-test";
  state.tokenChanged({ type: "android", data: replacement });
  await tick();
  assert.equal(refreshed, 1);
  assert.equal((await driver.prepareDevice()).fcmToken, replacement);
  state.tokenChanged({ type: "android", data: replacement });
  await tick();
  assert.equal(refreshed, 1);
  assert.equal(state.calls.filter((value) => value === "token").length, 1);
  cleanup();
});

test("콜백 false 후 같은 알림을 다시 눌러 처리할 수 있음", async () => {
  const { api, state } = fixture();
  state.last = event();
  let attempts = 0;
  const cleanup = api.startAndroidPush({
    shouldPresent: () => true,
    onResponse() {
      return ++attempts >= 2;
    },
    onReceived() {},
    onTokenChanged() {},
  });
  await tick();
  assert.equal(attempts, 1);
  assert.notEqual(state.last, null);
  state.response(event());
  await tick();
  assert.equal(attempts, 2);
  assert.equal(state.last, null);
  cleanup();
});
test("콜백 예외 후 원래 터치를 유지하고 재시도 성공 때 정리", async () => {
  const { api, state } = fixture();
  state.last = event();
  let attempts = 0;
  const cleanup = api.startAndroidPush({
    shouldPresent: () => true,
    onResponse() {
      if (++attempts === 1) throw new Error("모의 통신 오류");
      return true;
    },
    onReceived() {},
    onTokenChanged() {},
  });
  await tick();
  assert.equal(attempts, 1);
  assert.notEqual(state.last, null);
  state.response(event());
  await tick();
  assert.equal(attempts, 2);
  assert.equal(state.last, null);
  cleanup();
});
test("뒤늦은 acknowledge는 일치하는 원래 터치만 삭제", async () => {
  const { api, state } = fixture();
  const driver = await api.createAndroidPushDriver();
  const original = event("old");
  state.last = event("new", { ...payload, notification_id: "8" });
  await driver.acknowledgeResponse(
    api.androidNotificationResponseKey(original),
  );
  assert.notEqual(state.last, null);
  const latestKey = api.androidNotificationResponseKey(state.last);
  await driver.acknowledgeResponse(latestKey);
  assert.equal(state.last, null);
});

// 실제 controller와 native adapter를 함께 사용하고 HTTP와 SDK 실행 부분만 대체합니다.
function integrationFixture(readError = null) {
  const native = fixture();
  const controller = createNotificationController();
  const calls = [];
  let fail = readError;
  const user = {
    id: 3,
    email: "staff@example.test",
    name: "테스트 담당자",
    role: "AGENCY_STAFF",
    agency_id: 7,
    agency_name: "테스트 기관",
    is_active: true,
    notification_enabled: true,
  };
  const api = async (route) => {
    calls.push(route);
    if (route === "/api/notifications/devices") return { registered: true };
    if (route === "/api/settings/me/notifications") return { enabled: true };
    if (route.startsWith("/api/notifications?")) return [];
    if (route === "/api/notifications/7/read") {
      if (fail) {
        const error = fail;
        fail = null;
        throw error;
      }
      return {
        id: 7,
        incident_id: 42,
        created_at: "2026-10-17T06:00:00Z",
        read_at: "2026-10-17T06:01:00Z",
      };
    }
    if (route === "/api/incidents/42")
      return { id: 42, incident_no: "TEST-42", cctv_name: "테스트 CCTV" };
    throw new Error("예상하지 않은 모의 API: " + route);
  };
  const start = () =>
    native.api.startAndroidPush({
      shouldPresent: () =>
        controller.getSnapshot().status === "ready" &&
        controller.getSnapshot().enabled === true,
      onResponse: controller.handleNotificationResponse,
      onReceived: controller.refreshNotifications,
      onTokenChanged: controller.refreshDeviceRegistration,
    });
  return {
    ...native,
    controller,
    calls,
    start,
    connect: () => controller.connectNotificationSession({ user, api }),
  };
}
test("controller 통합: 로그인 대기 중 OS 응답 유지·합류 후 권한 확인과 acknowledge", async () => {
  const f = integrationFixture();
  const driver = await f.api.createAndroidPushDriver();
  f.controller.setDeviceDriver(driver);
  f.state.last = event();
  const cleanup = f.start();
  await tick();
  assert.equal(f.calls.length, 0);
  assert.notEqual(f.state.last, null);
  await f.connect();
  await tick();
  assert.equal(f.controller.getSnapshot().incident?.id, 42);
  assert.equal(f.state.last, null);
  assert.ok(f.calls.includes("/api/notifications/7/read"));
  assert.ok(f.calls.includes("/api/incidents/42"));
  cleanup();
});
test("controller 통합: 네트워크 실패 후 동일 알림 재터치로 상세 복구", async () => {
  const f = integrationFixture(
    Object.assign(new Error("모의 서비스 오류"), { status: 503 }),
  );
  f.controller.setDeviceDriver(await f.api.createAndroidPushDriver());
  await f.connect();
  f.state.last = event();
  const cleanup = f.start();
  await tick();
  assert.equal(f.controller.getSnapshot().incident, null);
  assert.notEqual(f.state.last, null);
  f.state.response(event());
  await tick();
  assert.equal(f.controller.getSnapshot().incident?.id, 42);
  assert.equal(f.state.last, null);
  assert.equal(f.calls.filter((route) => route.endsWith("/read")).length, 2);
  cleanup();
});
test("controller 통합: 다른 계정 알림 거부 시 상세 요청 없이 OS 응답 소비", async () => {
  const f = integrationFixture(
    Object.assign(new Error("모의 조회 거부"), { status: 404 }),
  );
  f.controller.setDeviceDriver(await f.api.createAndroidPushDriver());
  await f.connect();
  f.state.last = event();
  const cleanup = f.start();
  await tick();
  assert.equal(f.controller.getSnapshot().incident, null);
  assert.equal(f.state.last, null);
  assert.equal(
    f.calls.some((route) => route.startsWith("/api/incidents/")),
    false,
  );
  cleanup();
});

// 실제 파일과 빌드를 사용하지 않고 Android 전용 검사 callback만 실행합니다.
function configFixture() {
  let nativeCheck;
  let manifestCheck;
  const file = { exists: false, text: "" };
  const module = { exports: {} };
  const compiled = compile("frontend/mobile/app.config.ts");
  new Function("module", "exports", "require", compiled)(
    module,
    module.exports,
    (name) => {
      if (name === "node:fs")
        return { existsSync: () => file.exists, readFileSync: () => file.text };
      if (name === "node:path") return path;
      if (name === "expo/config-plugins")
        return {
          withAndroidManifest(config, callback) {
            manifestCheck = callback;
            return config;
          },
          withDangerousMod(config, [platform, callback]) {
            assert.equal(platform, "android");
            nativeCheck = callback;
            return config;
          },
        };
      throw new Error("허용하지 않은 config import");
    },
  );
  const config = module.exports.default({
    config: {
      name: "OCTV",
      slug: "octv-ui",
      ios: { supportsTablet: true },
      plugins: ["expo-video"],
    },
  });
  return {
    config,
    file,
    nativeCheck,
    manifestCheck,
    mod: { ...config, modRequest: { projectRoot: "/virtual/mobile" } },
  };
}
test("웹 설정은 Firebase 파일 없이 기존 app.json·plugin 유지", () => {
  const { config } = configFixture();
  assert.equal(config.android.package, "com.octv.mobile");
  assert.equal(config.ios.supportsTablet, true);
  assert.deepEqual(
    config.plugins.map((value) => (Array.isArray(value) ? value[0] : value)),
    ["expo-video", "expo-notifications", "expo-secure-store"],
  );
});
test("Android 빌드의 Firebase 파일 누락 오류", async () => {
  const f = configFixture();
  await assert.rejects(f.nativeCheck(f.mod), /google-services.json/);
});
test("Firebase JSON 해석 오류의 본문을 노출하지 않음", async () => {
  const f = configFixture();
  f.file.exists = true;
  f.file.text = "{";
  await assert.rejects(f.nativeCheck(f.mod), /읽지 못/);
});
test("Firebase 서버 자격증명을 Android 파일로 사용하지 않음", async () => {
  const f = configFixture();
  f.file.exists = true;
  f.file.text = JSON.stringify({
    type: "service_account",
    private_key: "mock-private-value",
  });
  await assert.rejects(f.nativeCheck(f.mod), /서버 서비스 계정/);
});
test("Firebase package 불일치 거부", async () => {
  const f = configFixture();
  f.file.exists = true;
  f.file.text = JSON.stringify({
    client: [
      {
        client_info: { android_client_info: { package_name: "com.other.app" } },
      },
    ],
  });
  await assert.rejects(f.nativeCheck(f.mod), /일치하지/);
});
test("일치하는 Firebase Android client 확인", async () => {
  const f = configFixture();
  f.file.exists = true;
  f.file.text = JSON.stringify({
    client: [
      {
        client_info: {
          android_client_info: { package_name: "com.octv.mobile" },
        },
      },
    ],
  });
  assert.equal(await f.nativeCheck(f.mod), f.mod);
});
test("로컬 HTTP는 명시적으로 켠 빌드만 허용", () => {
  const f = configFixture();
  const manifest = { modResults: { manifest: { application: [{ $: {} }] } } };
  f.manifestCheck(manifest);
  assert.equal(
    manifest.modResults.manifest.application[0].$[
      "android:usesCleartextTraffic"
    ],
    "false",
  );
  process.env.OCTV_ANDROID_ALLOW_HTTP = "1";
  f.manifestCheck(manifest);
  assert.equal(
    manifest.modResults.manifest.application[0].$[
      "android:usesCleartextTraffic"
    ],
    "true",
  );
  delete process.env.OCTV_ANDROID_ALLOW_HTTP;
});

// 테스트 프로세스 안에서만 빌드 환경을 비우고 종료 후 원래 값을 복원합니다.
const configKeys = [
  "OCTV_ANDROID_PACKAGE",
  "OCTV_ANDROID_GOOGLE_SERVICES_FILE",
  "GOOGLE_SERVICES_JSON",
  "OCTV_EAS_PROJECT_ID",
  "OCTV_ANDROID_ALLOW_HTTP",
];
const originalEnvironment = Object.fromEntries(
  configKeys.map((key) => [key, process.env[key]]),
);
before(() => {
  for (const key of configKeys) delete process.env[key];
});
after(() => {
  for (const key of configKeys) {
    if (originalEnvironment[key] === undefined) delete process.env[key];
    else process.env[key] = originalEnvironment[key];
  }
});
