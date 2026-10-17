/**
 * 실행: node --test --test-isolation=none tests/mobile_notifications.test.mjs (Node 24).
 * 실제 알림 controller의 HTTP·기기 경계만 대체하여 소유권, 계정 변경, 중복, 등록·로그아웃 경쟁을 검사합니다.
 * Firebase 접수·Android 권한·휴대폰 표시 성공을 검증하는 실기기 테스트는 아닙니다.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  createNotificationController,
  parsePushData,
  parseNotificationTime,
} from "../frontend/mobile/src/notifications.ts";

const user = {
  id: 3,
  email: "test-staff@example.test",
  name: "테스트 담당자",
  role: "AGENCY_STAFF",
  agency_id: 7,
  agency_name: "테스트 기관",
  is_active: true,
  notification_enabled: true,
};
const otherUser = {
  ...user,
  id: 4,
  agency_id: 8,
  agency_name: "다른 테스트 기관",
};
const row = {
  id: 11,
  incident_id: 41,
  created_at: "2026-10-17T06:00:00",
  read_at: null,
};
const readRow = { ...row, read_at: "2026-10-17T06:01:00" };
const incident = { id: 41, incident_no: "TEST-41", cctv_name: "테스트 CCTV" };
const push = {
  schema_version: "1",
  type: "INCIDENT_DELIVERED",
  notification_id: "11",
  incident_id: "999",
};
const deviceId = "6f5fe440-548d-4181-8d45-d5438cb089b9";
const token = "test-fcm-registration-token-only";

// 네트워크 응답 시점을 직접 조절하여 요청 순서가 뒤집히는 상황을 재현합니다.
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

// 요청 기록을 남기고 이 테스트가 지정한 경로 외에는 명확한 기본 응답만 제공합니다.
function fakeApi(override = () => undefined) {
  const calls = [];
  const api = async (path, options = {}) => {
    calls.push({ path, method: options.method ?? "GET", body: options.body });
    const result = override(path, options);
    if (result !== undefined) return await result;
    if (path === "/api/settings/me/notifications") {
      return {
        enabled:
          options.method === "PATCH" ? JSON.parse(options.body).enabled : true,
      };
    }
    if (path === "/api/notifications/devices") return { registered: true };
    if (path.startsWith("/api/notifications/devices/"))
      return { removed: true };
    if (path.startsWith("/api/notifications?")) return [{ ...row }];
    if (path === "/api/notifications/11/read") return { ...readRow };
    if (path === "/api/incidents/41") return { ...incident };
    throw new Error(`Unexpected test path: ${path}`);
  };
  return { api, calls };
}

// 네이티브 SDK 대신 설치 UUID·현재 토큰·트레이 정리 경계만 제공합니다.
function fakeDriver(
  prepare = async () => ({ deviceId, platform: "android", fcmToken: token }),
) {
  let cleared = 0;
  return {
    prepareDevice: prepare,
    getInstallationId: async () => deviceId,
    clearPresentedNotifications: async () => {
      cleared++;
    },
    get cleared() {
      return cleared;
    },
  };
}

test("Push 계약은 타입·버전·양의 ID·추가 필드까지 검사한다", () => {
  assert.deepEqual(parsePushData(push), push);
  for (const invalid of [
    null,
    [],
    "message",
    { ...push, schema_version: 1 },
    { ...push, type: "OTHER" },
    { ...push, notification_id: 11 },
    { ...push, incident_id: "0" },
    { ...push, incident_id: "1/other" },
    { ...push, incident_id: "01" },
    { ...push, incident_id: "9223372036854775808" },
    { ...push, user_id: "3" },
  ])
    assert.equal(parsePushData(invalid), null);
});

test("로그인 복원 전 터치는 API를 호출하지 않고, 복원 뒤 서버 사건 번호만 사용한다", async () => {
  const controller = createNotificationController();
  const { api, calls } = fakeApi();
  assert.equal(await controller.handleNotificationResponse(push), false);
  assert.equal(calls.length, 0);
  assert.equal(controller.getSnapshot().status, "waiting");
  await controller.connectNotificationSession({ user, api });
  assert.ok(calls.find((call) => call.path === "/api/notifications/11/read"));
  assert.ok(calls.find((call) => call.path === "/api/incidents/41"));
  assert.equal(
    calls.some((call) => call.path === "/api/incidents/999"),
    false,
  );
  assert.equal(controller.getSnapshot().incident.id, 41);
  assert.equal(controller.getSnapshot().navigationVersion, 1);
});

test("다른 사용자 알림의 404 뒤에는 사건 상세 요청과 화면 이동을 하지 않는다", async () => {
  const controller = createNotificationController();
  const { api, calls } = fakeApi((path) => {
    if (path.endsWith("/read"))
      throw Object.assign(new Error("sensitive request must not appear"), {
        status: 404,
      });
  });
  await controller.connectNotificationSession({ user, api });
  assert.equal(await controller.handleNotificationResponse(push), false);
  assert.equal(
    calls.some((call) => call.path.startsWith("/api/incidents/")),
    false,
  );
  assert.equal(controller.getSnapshot().incident, null);
  assert.equal(controller.getSnapshot().navigationVersion, 0);
  assert.equal(controller.getSnapshot().error.includes("sensitive"), false);
});

test("서버가 다른 알림 행을 반환하면 상세 조회를 진행하지 않는다", async () => {
  const controller = createNotificationController();
  const { api, calls } = fakeApi((path) =>
    path.endsWith("/read") ? { ...readRow, id: 12 } : undefined,
  );
  await controller.connectNotificationSession({ user, api });
  assert.equal(await controller.openNotification(11), false);
  assert.equal(
    calls.some((call) => call.path.startsWith("/api/incidents/")),
    false,
  );
});

test("초기 알림 응답과 리스너가 겹쳐도 한 번만 읽고 이동한다", async () => {
  const controller = createNotificationController();
  const reading = deferred();
  const { api, calls } = fakeApi((path) =>
    path.endsWith("/read") ? reading.promise : undefined,
  );
  await controller.connectNotificationSession({ user, api });
  const first = controller.handleNotificationResponse(push, "initial");
  assert.equal(
    await controller.handleNotificationResponse(push, "listener"),
    false,
  );
  reading.resolve(readRow);
  assert.equal(await first, true);
  assert.equal(
    await controller.handleNotificationResponse(push, "later"),
    false,
  );
  assert.equal(calls.filter((call) => call.path.endsWith("/read")).length, 1);
  assert.equal(
    calls.filter((call) => call.path === "/api/incidents/41").length,
    1,
  );
  assert.equal(controller.getSnapshot().navigationVersion, 1);
});

test("사건 상세 응답 대기 중 계정이 바뀌면 이전 계정 자료를 반영하지 않는다", async () => {
  const controller = createNotificationController();
  const detail = deferred();
  const entered = deferred();
  const first = fakeApi((path) => {
    if (path.startsWith("/api/incidents/")) {
      entered.resolve();
      return detail.promise;
    }
  });
  const next = fakeApi();
  await controller.connectNotificationSession({ user, api: first.api });
  const opening = controller.openNotification(11);
  await entered.promise;
  await controller.connectNotificationSession({
    user: otherUser,
    api: next.api,
  });
  detail.resolve(incident);
  assert.equal(await opening, false);
  assert.equal(controller.getSnapshot().user.id, 4);
  assert.equal(controller.getSnapshot().incident, null);
  assert.equal(controller.getSnapshot().navigationVersion, 0);
  assert.deepEqual(controller.getSnapshot().notifications, []);
});

test("이전 계정의 늦은 목록 응답과 오류도 현재 계정 화면을 덮지 않는다", async () => {
  const controller = createNotificationController();
  const late = deferred();
  const first = fakeApi((path) =>
    path.startsWith("/api/notifications?") ? late.promise : undefined,
  );
  await controller.connectNotificationSession({ user, api: first.api });
  const loading = controller.listNotifications();
  const next = fakeApi();
  await controller.connectNotificationSession({
    user: otherUser,
    api: next.api,
  });
  late.reject(Object.assign(new Error("old expired session"), { status: 401 }));
  assert.deepEqual(await loading, []);
  assert.equal(controller.getSnapshot().status, "ready");
  assert.equal(controller.getSnapshot().user.id, 4);
  assert.equal(controller.getSnapshot().error, null);
});

test("같은 계정의 목록 요청도 마지막 요청의 응답만 화면에 반영한다", async () => {
  const controller = createNotificationController();
  const first = deferred();
  const second = deferred();
  let count = 0;
  const { api } = fakeApi((path) =>
    path.startsWith("/api/notifications?")
      ? ++count === 1
        ? first.promise
        : second.promise
      : undefined,
  );
  await controller.connectNotificationSession({ user, api });
  const one = controller.listNotifications();
  const two = controller.listNotifications({ offset: 30 });
  const laterRow = { ...row, id: 12 };
  second.resolve([laterRow]);
  await two;
  first.resolve([row]);
  await one;
  assert.deepEqual(controller.getSnapshot().notifications, [laterRow]);
  assert.equal(controller.getSnapshot().loading, false);
});

test("현재 JWT가 만료되면 보던 알림·사건 자료를 지우고 인증 복원을 기다린다", async () => {
  const controller = createNotificationController();
  let expired = false;
  const { api } = fakeApi((path) => {
    if (expired && path.startsWith("/api/notifications?"))
      throw Object.assign(new Error("expired"), { status: 401 });
  });
  await controller.connectNotificationSession({ user, api });
  await controller.listNotifications();
  await controller.openNotification(11);
  expired = true;
  await controller.listNotifications();
  assert.equal(controller.getSnapshot().status, "waiting");
  assert.equal(controller.getSnapshot().user, null);
  assert.equal(controller.getSnapshot().incident, null);
  assert.deepEqual(controller.getSnapshot().notifications, []);
});

test("Push 읽음 요청의 401 뒤 같은 사용자가 재로그인하면 대기한 알림을 이어서 연다", async () => {
  const controller = createNotificationController();
  const expired = fakeApi((path) => {
    if (path.endsWith("/read"))
      throw Object.assign(new Error("expired"), { status: 401 });
  });
  await controller.connectNotificationSession({ user, api: expired.api });
  assert.equal(await controller.handleNotificationResponse(push), false);
  assert.equal(controller.getSnapshot().status, "waiting");
  // 인증 담당의 유실 통보가 한 번 더 와도 같은 사용자 재인증 대기는 유지합니다.
  controller.disconnectNotificationSession();
  const restored = fakeApi();
  await controller.connectNotificationSession({ user, api: restored.api });
  assert.equal(controller.getSnapshot().incident.id, 41);
  assert.equal(controller.getSnapshot().navigationVersion, 1);
  assert.equal(
    restored.calls.filter((call) => call.path.endsWith("/read")).length,
    1,
  );
});

test("재인증을 기다리던 이전 사용자 Push는 다른 계정 로그인에서 자동 재개하지 않는다", async () => {
  const controller = createNotificationController();
  const expired = fakeApi((path) => {
    if (path.endsWith("/read"))
      throw Object.assign(new Error("expired"), { status: 401 });
  });
  await controller.connectNotificationSession({ user, api: expired.api });
  await controller.handleNotificationResponse(push);
  const other = fakeApi();
  await controller.connectNotificationSession({
    user: otherUser,
    api: other.api,
  });
  assert.equal(
    other.calls.some((call) => call.path.endsWith("/read")),
    false,
  );
  assert.equal(controller.getSnapshot().incident, null);
});

test("일시 네트워크 오류로 실패한 Push 터치는 다시 시도할 수 있다", async () => {
  const controller = createNotificationController();
  let offline = true;
  const { api, calls } = fakeApi((path) => {
    if (offline && path.endsWith("/read")) throw new Error("offline");
  });
  await controller.connectNotificationSession({ user, api });
  assert.equal(
    await controller.handleNotificationResponse(push, "same-os-response"),
    false,
  );
  offline = false;
  assert.equal(
    await controller.handleNotificationResponse(push, "same-os-response"),
    true,
  );
  assert.equal(calls.filter((call) => call.path.endsWith("/read")).length, 2);
  assert.equal(controller.getSnapshot().navigationVersion, 1);
});

test("로그인 대기 후 성공하면 원래 OS 응답 키만 정리하고 더 새로운 알림은 보존한다", async () => {
  const controller = createNotificationController();
  const acknowledged = [];
  let lastKey = "newer-response|notification-12";
  const native = fakeDriver();
  native.acknowledgeResponse = async (key) => {
    acknowledged.push(key);
    if (lastKey === key) lastKey = null;
  };
  controller.setDeviceDriver(native);
  await controller.handleNotificationResponse(
    push,
    "original-response|notification-11",
  );
  assert.deepEqual(acknowledged, []);
  const { api } = fakeApi();
  await controller.connectNotificationSession({ user, api });
  assert.deepEqual(acknowledged, ["original-response|notification-11"]);
  assert.equal(lastKey, "newer-response|notification-12");
});

test("401 재인증 대기에서는 OS 마지막 응답을 유지하고 재로그인 성공 후 같은 키만 정리한다", async () => {
  const controller = createNotificationController();
  const acknowledged = [];
  const native = fakeDriver();
  native.acknowledgeResponse = async (key) => {
    acknowledged.push(key);
  };
  controller.setDeviceDriver(native);
  const expired = fakeApi((path) => {
    if (path.endsWith("/read"))
      throw Object.assign(new Error("expired"), { status: 401 });
  });
  await controller.connectNotificationSession({ user, api: expired.api });
  assert.equal(
    await controller.handleNotificationResponse(push, "reauth-response"),
    false,
  );
  assert.deepEqual(acknowledged, []);
  const restored = fakeApi();
  await controller.connectNotificationSession({ user, api: restored.api });
  assert.equal(native.cleared, 0);
  assert.deepEqual(acknowledged, ["reauth-response"]);
  assert.equal(controller.getSnapshot().incident.id, 41);
});

test("네트워크 실패는 OS 응답을 소비하지 않고 재터치 성공 뒤에만 정리한다", async () => {
  const controller = createNotificationController();
  const acknowledged = [];
  const native = fakeDriver();
  native.acknowledgeResponse = async (key) => {
    acknowledged.push(key);
  };
  controller.setDeviceDriver(native);
  let offline = true;
  const { api } = fakeApi((path) => {
    if (offline && path.endsWith("/read")) throw new Error("offline");
  });
  await controller.connectNotificationSession({ user, api });
  assert.equal(
    await controller.handleNotificationResponse(push, "retry-response"),
    false,
  );
  assert.deepEqual(acknowledged, []);
  offline = false;
  assert.equal(
    await controller.handleNotificationResponse(push, "retry-response"),
    true,
  );
  assert.deepEqual(acknowledged, ["retry-response"]);
});

test("알림을 먼저 처리한 뒤 드라이버가 준비되어도 해당 응답 키를 정리한다", async () => {
  const controller = createNotificationController();
  const { api } = fakeApi();
  await controller.connectNotificationSession({ user, api });
  assert.equal(
    await controller.handleNotificationResponse(push, "early-response"),
    true,
  );
  const acknowledged = deferred();
  const native = fakeDriver();
  native.acknowledgeResponse = async (key) => {
    acknowledged.resolve(key);
  };
  controller.setDeviceDriver(native);
  assert.equal(await acknowledged.promise, "early-response");
});

test("인증 세션이 없는 명시적 로그아웃도 대기 터치와 늦은 중복을 취소한다", async () => {
  const controller = createNotificationController();
  const native = fakeDriver();
  controller.setDeviceDriver(native);
  await controller.handleNotificationResponse(push, "cancelled-response");
  assert.equal(await controller.prepareNotificationLogout(), true);
  assert.equal(native.cleared, 1);
  assert.equal(
    await controller.handleNotificationResponse(push, "late-duplicate"),
    false,
  );
  const { api, calls } = fakeApi();
  await controller.connectNotificationSession({ user, api });
  assert.equal(
    calls.some((call) => call.path.endsWith("/read")),
    false,
  );
  assert.equal(controller.getSnapshot().incident, null);
});

test("알림 연결은 소속 기관이 있는 활성 기관 담당자·출동대원만 준비 상태로 만든다", async () => {
  for (const invalid of [
    { ...user, role: "CONTROL_ADMIN" },
    { ...user, agency_id: null },
    { ...user, is_active: false },
  ]) {
    const controller = createNotificationController();
    const { api, calls } = fakeApi();
    await assert.rejects(
      controller.connectNotificationSession({ user: invalid, api }),
    );
    assert.equal(controller.getSnapshot().status, "waiting");
    assert.equal(calls.length, 0);
  }
});

test("연결 불가능한 역할로 계정을 바꿔도 이전 사용자의 화면 자료를 남기지 않는다", async () => {
  const controller = createNotificationController();
  const { api } = fakeApi();
  await controller.connectNotificationSession({ user, api });
  await controller.listNotifications();
  await controller.openNotification(11);
  await assert.rejects(
    controller.connectNotificationSession({
      user: { ...otherUser, role: "CONTROL_ADMIN" },
      api,
    }),
  );
  assert.equal(controller.getSnapshot().status, "waiting");
  assert.equal(controller.getSnapshot().user, null);
  assert.equal(controller.getSnapshot().incident, null);
  assert.deepEqual(controller.getSnapshot().notifications, []);
});

test("진행 중인 기기 등록 이후 로그아웃 삭제를 완료하여 연결이 되살아나지 않는다", async () => {
  const controller = createNotificationController();
  const native = fakeDriver();
  controller.setDeviceDriver(native);
  const posting = deferred();
  const entered = deferred();
  let owner = null;
  const { api, calls } = fakeApi((path, options) => {
    if (path === "/api/notifications/devices" && options.method === "POST") {
      entered.resolve();
      return posting.promise.then(() => {
        owner = user.id;
        return { registered: true };
      });
    }
    if (options.method === "DELETE") {
      owner = null;
      return { removed: true };
    }
  });
  const login = controller.connectNotificationSession({ user, api });
  await entered.promise;
  const logout = controller.prepareNotificationLogout();
  assert.equal(controller.getSnapshot().status, "signing-out");
  posting.resolve();
  await login;
  assert.equal(await logout, true);
  assert.equal(owner, null);
  assert.equal(calls.at(-1).method, "DELETE");
  assert.equal(calls.filter((call) => call.method === "POST").length, 1);
  assert.equal(controller.getSnapshot().status, "waiting");
  assert.equal(native.cleared, 1);
});

test("같은 사용자 로그인 복원도 기기 등록 API를 다시 호출한다", async () => {
  const controller = createNotificationController();
  controller.setDeviceDriver(fakeDriver());
  const first = fakeApi();
  await controller.connectNotificationSession({ user, api: first.api });
  const restored = fakeApi();
  await controller.connectNotificationSession({ user, api: restored.api });
  assert.equal(first.calls.filter((call) => call.method === "POST").length, 1);
  assert.equal(
    restored.calls.filter((call) => call.method === "POST").length,
    1,
  );
});

test("계정 변경 중 늦은 기기 등록을 정리한 뒤 새 계정에 등록한다", async () => {
  const controller = createNotificationController();
  controller.setDeviceDriver(fakeDriver());
  const oldPost = deferred();
  const entered = deferred();
  let owner = null;
  const changes = [];
  const old = fakeApi((path, options) => {
    if (path === "/api/notifications/devices") {
      entered.resolve();
      return oldPost.promise.then(() => {
        owner = user.id;
        changes.push("old-register");
        return { registered: true };
      });
    }
    if (options.method === "DELETE") {
      if (owner === user.id) owner = null;
      changes.push("old-remove");
      return { removed: true };
    }
  });
  const next = fakeApi((path) => {
    if (path === "/api/notifications/devices") {
      owner = otherUser.id;
      changes.push("new-register");
      return { registered: true };
    }
  });
  const firstLogin = controller.connectNotificationSession({
    user,
    api: old.api,
  });
  await entered.promise;
  const nextLogin = controller.connectNotificationSession({
    user: otherUser,
    api: next.api,
  });
  await Promise.resolve();
  assert.equal(
    next.calls.some((call) => call.method === "POST"),
    false,
  );
  oldPost.resolve();
  await Promise.all([firstLogin, nextLogin]);
  assert.equal(changes[0], "old-register");
  assert.equal(changes.at(-1), "new-register");
  assert.equal(owner, otherUser.id);
  assert.equal(controller.getSnapshot().user.id, otherUser.id);
  assert.equal(controller.getSnapshot().deviceStatus, "registered");
});

test("토큰 갱신 요청은 순서대로 등록하여 늦은 옛 토큰이 최신 토큰을 덮지 않는다", async () => {
  const controller = createNotificationController();
  let currentToken = token;
  let prepared = 0;
  controller.setDeviceDriver(
    fakeDriver(async () => {
      prepared++;
      return { deviceId, platform: "android", fcmToken: currentToken };
    }),
  );
  const firstRefresh = deferred();
  const entered = deferred();
  let storedToken;
  const { api } = fakeApi((path, options) => {
    if (path !== "/api/notifications/devices") return;
    const body = JSON.parse(options.body);
    if (body.fcm_token === "test-fcm-refresh-first") {
      entered.resolve();
      return firstRefresh.promise.then(() => {
        storedToken = body.fcm_token;
        return { registered: true };
      });
    }
    storedToken = body.fcm_token;
    return { registered: true };
  });
  await controller.connectNotificationSession({ user, api });
  currentToken = "test-fcm-refresh-first";
  const one = controller.refreshDeviceRegistration();
  await entered.promise;
  currentToken = "test-fcm-refresh-second";
  const two = controller.refreshDeviceRegistration();
  await Promise.resolve();
  assert.equal(prepared, 2);
  firstRefresh.resolve();
  await Promise.all([one, two]);
  assert.equal(storedToken, "test-fcm-refresh-second");
  assert.equal(prepared, 3);
});

test("서버 토큰 해제 실패를 로그아웃 성공으로 알리지 않고 재시도를 허용한다", async () => {
  const controller = createNotificationController();
  controller.setDeviceDriver(fakeDriver());
  let unavailable = true;
  const { api } = fakeApi((_path, options) => {
    if (options.method === "DELETE" && unavailable) throw new Error("offline");
  });
  await controller.connectNotificationSession({ user, api });
  await controller.listNotifications();
  assert.equal(await controller.prepareNotificationLogout(), false);
  assert.equal(controller.getSnapshot().status, "logout-failed");
  assert.equal(controller.getSnapshot().incident, null);
  assert.deepEqual(controller.getSnapshot().notifications, []);
  unavailable = false;
  assert.equal(await controller.prepareNotificationLogout(), true);
  assert.equal(controller.getSnapshot().status, "waiting");
});

test("Push OFF는 DB 알림 목록과 읽음 API를 유지한다", async () => {
  const controller = createNotificationController();
  const { api, calls } = fakeApi();
  await controller.connectNotificationSession({ user, api });
  await controller.listNotifications();
  assert.equal(await controller.setEnabled(false), true);
  assert.equal(controller.getSnapshot().enabled, false);
  assert.equal(controller.getSnapshot().notifications.length, 1);
  assert.deepEqual(await controller.markRead(11), readRow);
  assert.equal(
    controller.getSnapshot().notifications[0].read_at,
    readRow.read_at,
  );
  assert.equal(
    calls.some((call) => call.method === "DELETE"),
    false,
  );
});

test("설정 스위치의 연속 변경은 마지막 선택 순서대로 서버에 저장한다", async () => {
  const controller = createNotificationController();
  const firstChange = deferred();
  const entered = deferred();
  const saved = [];
  const { api } = fakeApi((path, options) => {
    if (path !== "/api/settings/me/notifications" || options.method !== "PATCH")
      return;
    const enabled = JSON.parse(options.body).enabled;
    if (!enabled) {
      entered.resolve();
      return firstChange.promise.then(() => {
        saved.push(false);
        return { enabled: false };
      });
    }
    saved.push(true);
    return { enabled: true };
  });
  await controller.connectNotificationSession({ user, api });
  const off = controller.setEnabled(false);
  await entered.promise;
  const on = controller.setEnabled(true);
  firstChange.resolve();
  await Promise.all([off, on]);
  assert.deepEqual(saved, [false, true]);
  assert.equal(controller.getSnapshot().enabled, true);
});

test("메뉴를 바꾼 뒤 도착한 상세 응답은 이전 사건 화면을 다시 열지 않는다", async () => {
  const controller = createNotificationController();
  const detail = deferred();
  const { api } = fakeApi((path) =>
    path === "/api/incidents/41" ? detail.promise : undefined,
  );
  await controller.connectNotificationSession({ user, api });
  const loading = controller.openIncident(41);
  controller.clearOpenedIncident();
  detail.resolve(incident);
  assert.equal(await loading, false);
  assert.equal(controller.getSnapshot().incident, null);
  assert.equal(controller.getSnapshot().navigationVersion, 0);
});

test("시간대 없는 알림 시각은 UTC로 해석하고 이미 있는 시간대는 유지한다", () => {
  assert.equal(
    parseNotificationTime("2026-10-17T06:00:00").toISOString(),
    "2026-10-17T06:00:00.000Z",
  );
  assert.equal(
    parseNotificationTime("2026-10-17T15:00:00+09:00").toISOString(),
    "2026-10-17T06:00:00.000Z",
  );
  assert.equal(
    parseNotificationTime("2026-10-17T06:00:00.123456Z").toISOString(),
    "2026-10-17T06:00:00.123Z",
  );
  assert.equal(parseNotificationTime("invalid timestamp"), null);
  assert.equal(parseNotificationTime("2026-10-17T99:00:00"), null);
});
