/**
 * 알림 흐름: 기존 인증 담당이 검증한 사용자·API 전달 → 기기 재등록 → 본인 알림 조회.
 * 알림 터치 → 본인 알림 읽음 API → 서버가 돌려준 사건 ID → 권한 있는 사건 상세 조회.
 * 네이티브 토큰·권한 처리는 push.ts에 맡기고, 이 파일은 API와 화면 상태만 관리합니다.
 * 로그인 요청·JWT 저장은 하지 않습니다. 계정이 바뀌면 이전 요청 결과와 화면 자료를 버립니다.
 */
import type { CurrentUserDto, IncidentDto } from "@octv/shared";
import type { createApi } from "./api";

export type NotificationApi = ReturnType<typeof createApi>;
export type NotificationDto = {
  id: number;
  incident_id: number;
  created_at: string;
  read_at: string | null;
};
export type DeviceRegistration = {
  deviceId: string;
  platform: "android";
  fcmToken: string;
};
export interface NotificationDeviceDriver {
  prepareDevice(): Promise<DeviceRegistration | null>;
  getInstallationId(): Promise<string>;
  clearPresentedNotifications(): Promise<void>;
  acknowledgeResponse?(responseKey: string): Promise<void>;
}
export type NotificationSnapshot = {
  status: "waiting" | "ready" | "signing-out" | "logout-failed";
  user: CurrentUserDto | null;
  notifications: NotificationDto[];
  loading: boolean;
  enabled: boolean | null;
  deviceStatus:
    | "unavailable"
    | "idle"
    | "registering"
    | "registered"
    | "permission-denied"
    | "error";
  error: string | null;
  incident: IncidentDto | null;
  openedNotificationId: string | null;
  navigationVersion: number;
};
type Session = {
  user: CurrentUserDto;
  api: NotificationApi;
  version: number;
  deviceId: string | null;
};
type PushData = {
  schema_version: "1";
  type: "INCIDENT_DELIVERED";
  incident_id: string;
  notification_id: string;
};
type ListOptions = { unreadOnly?: boolean; limit?: number; offset?: number };

// URL의 ID는 양의 정수만 허용하며, JSON 숫자가 정밀도를 잃은 경우 잘못된 사건을 열지 않습니다.
function idText(value: unknown): string | null {
  if (typeof value === "number") {
    return Number.isSafeInteger(value) && value > 0 ? String(value) : null;
  }
  if (typeof value !== "string" || !/^[1-9]\d{0,18}$/.test(value)) return null;
  return BigInt(value) <= 9223372036854775807n ? value : null;
}

// PR3의 네 필드를 정확하게 확인합니다. payload의 사건 ID는 검증 후에도 이동 힌트로만 사용합니다.
export function parsePushData(value: unknown): PushData | null {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    return null;
  const data = value as Record<string, unknown>;
  if (
    data.schema_version !== "1" ||
    data.type !== "INCIDENT_DELIVERED" ||
    typeof data.incident_id !== "string" ||
    typeof data.notification_id !== "string" ||
    !idText(data.incident_id) ||
    !idText(data.notification_id)
  )
    return null;
  if (
    Object.keys(data).some(
      (key) =>
        !["schema_version", "type", "incident_id", "notification_id"].includes(
          key,
        ),
    )
  )
    return null;
  return data as PushData;
}

// 기존 알림 API의 시간대 없는 값은 UTC입니다. 휴대폰에서 한국 시각으로 잘못 읽지 않게 Z를 붙입니다.
export function parseNotificationTime(value: string): Date | null {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?$/.test(
      value,
    )
  )
    return null;
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

// 인증·권한·네트워크 오류는 고정 문구로 알립니다. 예외 원문에는 토큰 등 비밀값이 있을 수 있습니다.
function errorMessage(error: unknown): string {
  const status =
    typeof error === "object" && error !== null && "status" in error
      ? error.status
      : null;
  if (status === 401) return "로그인 정보를 다시 확인해 주세요.";
  if (status === 403 || status === 404)
    return "현재 계정으로 조회할 수 없는 알림 또는 사건입니다.";
  if (status === 409)
    return "기기 등록 한도를 확인해 주세요. 사용자당 최대 10대입니다.";
  return "알림 요청을 완료하지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.";
}

// 서버 응답의 알림·사건 번호를 검사합니다. 잘못된 응답으로 다른 상세 화면을 열지 않습니다.
function validNotification(row: NotificationDto, expectedId?: string): boolean {
  return (
    !!row &&
    !!idText(row.id) &&
    !!idText(row.incident_id) &&
    (expectedId === undefined || String(row.id) === expectedId) &&
    typeof row.created_at === "string" &&
    (row.read_at === null || typeof row.read_at === "string")
  );
}

// 앱에서 한 개를 공유하며 테스트에서는 별도 인스턴스로 계정·네트워크 경쟁 상황을 확인합니다.
export function createNotificationController() {
  let version = 0;
  let session: Session | null = null;
  let driver: NotificationDeviceDriver | null = null;
  let snapshot: NotificationSnapshot = {
    status: "waiting",
    user: null,
    notifications: [],
    loading: false,
    enabled: null,
    deviceStatus: "unavailable",
    error: null,
    incident: null,
    openedNotificationId: null,
    navigationVersion: 0,
  };
  const listeners = new Set<() => void>();
  let deviceLane: Promise<unknown> = Promise.resolve();
  let settingsLane: Promise<unknown> = Promise.resolve();
  let listVersion = 0;
  let settingsVersion = 0;
  let openVersion = 0;
  let lastList: ListOptions = {};
  let pendingPush: {
    payload: PushData;
    userId: number | null;
    responseKey?: string;
  } | null = null;
  const consumedPushes = new Set<string>();
  const pushInFlight = new Set<string>();
  const pushFailures = new Map<string, "auth" | "denied" | "retry">();
  const pushResponseKeys = new Map<string, Set<string>>();
  const pendingAcknowledgements = new Set<string>();
  let acknowledgementLane: Promise<void> = Promise.resolve();
  let pushVersion = 0;
  let latestPush: {
    payload: PushData;
    target: Session;
    version: number;
    responseKey?: string;
  } | null = null;
  const opening = new Map<string, Promise<boolean>>();
  const readRows = new Map<number, NotificationDto>();

  // 객체를 교체해 React 구독에 변경을 알립니다. 외부 코드는 반환된 snapshot을 수정하지 않습니다.
  function update(patch: Partial<NotificationSnapshot>) {
    snapshot = { ...snapshot, ...patch };
    for (const listener of listeners) listener();
  }

  // 요청 당시 계정과 현재 계정이 모두 같아야 응답을 화면에 반영합니다.
  function current(target: Session): boolean {
    return (
      session === target &&
      version === target.version &&
      snapshot.status === "ready"
    );
  }

  // 기기 등록·삭제는 하나씩 실행하여 늦은 등록 요청이 로그아웃 뒤 연결을 다시 만들지 않게 합니다.
  function withDevice<T>(operation: () => Promise<T>): Promise<T> {
    const task = deviceLane.then(operation, operation);
    deviceLane = task.catch(() => undefined);
    return task;
  }

  // 인증 대기 중 처리한 터치도 드라이버가 준비되면 정리합니다. 드라이버는 같은 OS 응답 키만 지워야 합니다.
  function flushAcknowledgements(): Promise<void> {
    const native = driver;
    if (!native?.acknowledgeResponse) return Promise.resolve();
    const task = acknowledgementLane.then(async () => {
      if (driver !== native) return;
      for (const key of pendingAcknowledgements) {
        try {
          await native.acknowledgeResponse!(key);
          pendingAcknowledgements.delete(key);
        } catch {
          break; /* 화면 이동 성공과 OS 마지막 응답 정리 성공을 혼동하지 않습니다. */
        }
      }
    });
    acknowledgementLane = task.catch(() => undefined);
    return acknowledgementLane;
  }

  // 키만 기억하고 알림·사건 상세 자료는 저장하지 않습니다. 새 알림이 있으면 이전 키의 정리는 아무 효과가 없습니다.
  function acknowledgeResponse(responseKey?: string): Promise<void> {
    if (responseKey) {
      pendingAcknowledgements.add(responseKey);
      if (pendingAcknowledgements.size > 200)
        pendingAcknowledgements.delete(
          pendingAcknowledgements.values().next().value!,
        );
    }
    return flushAcknowledgements();
  }

  // 현재 화면 자료만 비웁니다. 소속이 다른 사용자에게 이전 사건을 잠깐이라도 보여주지 않습니다.
  function resetView(
    status: NotificationSnapshot["status"],
    user: CurrentUserDto | null = null,
  ) {
    listVersion++;
    settingsVersion++;
    openVersion++;
    readRows.clear();
    opening.clear();
    lastList = {};
    update({
      status,
      user,
      notifications: [],
      loading: false,
      enabled: user?.notification_enabled ?? null,
      incident: null,
      openedNotificationId: null,
      error: null,
      deviceStatus: driver ? "idle" : "unavailable",
    });
  }

  // 인증 유실은 메모리와 트레이를 정리합니다. 이 함수는 서버 토큰 해제 성공을 보장하는 로그아웃이 아닙니다.
  function disconnectNotificationSession() {
    // 인증 만료로 중단된 터치는 같은 사용자 재로그인 뒤에만 재개합니다. ID 외 사건 자료는 보관하지 않습니다.
    const resume =
      latestPush?.target === session && latestPush
        ? {
            payload: latestPush.payload,
            userId: latestPush.target.user.id,
            responseKey: latestPush.responseKey,
          }
        : pendingPush;
    const previous = session;
    version++;
    session = null;
    pendingPush = resume;
    resetView("waiting");
    const previousDriver = driver;
    if (previous || previousDriver) {
      void withDevice(async () => {
        if (previous) {
          try {
            await removeDevice(previous, previousDriver);
          } catch {
            /* 만료된 JWT로는 해제 확인을 못 할 수 있습니다. */
          }
        }
        // 재인증을 기다리는 터치는 OS에도 남겨 앱 재실행 시 다시 받을 수 있게 합니다.
        if (previousDriver && !resume) {
          try {
            await previousDriver.clearPresentedNotifications();
          } catch {
            /* 서버 로그아웃 성공으로 표시하지 않습니다. */
          }
        }
      });
    }
  }

  // 만료된 JWT 응답이면 현재 계정 화면을 지우고 인증 담당의 재확인을 기다립니다.
  function fail(target: Session, error: unknown) {
    if (!current(target)) return;
    const unauthorized =
      typeof error === "object" &&
      error !== null &&
      "status" in error &&
      error.status === 401;
    if (unauthorized) disconnectNotificationSession();
    update({ error: errorMessage(error) });
  }

  // Push 처리 실패는 재인증·권한 거부·재시도로 나눕니다. 일시 장애를 영구적인 중복 소비로 기록하지 않습니다.
  function notePushFailure(
    target: Session,
    notificationId: string | null,
    error: unknown,
  ) {
    const key = `${target.version}:${notificationId}`;
    if (!notificationId || !current(target) || !pushInFlight.has(key)) return;
    const status =
      typeof error === "object" && error !== null && "status" in error
        ? error.status
        : null;
    pushFailures.set(
      key,
      status === 401
        ? "auth"
        : status === 403 || status === 404
          ? "denied"
          : "retry",
    );
  }

  // 기존 JWT를 고정 캡처한 API로 삭제합니다. 계정이 바뀐 전역 getToken을 참조하면 안 됩니다.
  async function removeDevice(
    target: Session,
    native: NotificationDeviceDriver | null,
  ) {
    const deviceId =
      target.deviceId ?? (native ? await native.getInstallationId() : null);
    if (deviceId)
      await target.api(
        `/api/notifications/devices/${encodeURIComponent(deviceId)}`,
        { method: "DELETE" },
      );
  }

  // Android 준비 후 현재 계정에 기기를 재등록합니다. PR3 역인덱스를 위해 로그인 복원 때도 호출합니다.
  async function refreshDeviceRegistration(): Promise<boolean> {
    const target = session;
    const native = driver;
    if (!target || !current(target) || !native) return false;
    return withDevice(async () => {
      if (!current(target) || driver !== native) return false;
      update({ deviceStatus: "registering" });
      try {
        const registration = await native.prepareDevice();
        if (!current(target) || driver !== native) return false;
        if (!registration) {
          update({ deviceStatus: "permission-denied" });
          return false;
        }
        if (
          !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
            registration.deviceId,
          ) ||
          registration.platform !== "android" ||
          typeof registration.fcmToken !== "string" ||
          registration.fcmToken.length < 16 ||
          registration.fcmToken.length > 4096 ||
          /\s/.test(registration.fcmToken) ||
          /^(ExpoPushToken|ExponentPushToken)\[/i.test(registration.fcmToken)
        ) {
          throw new Error("INVALID_DEVICE_REGISTRATION");
        }
        target.deviceId = registration.deviceId;
        await target.api("/api/notifications/devices", {
          method: "POST",
          body: JSON.stringify({
            device_id: registration.deviceId,
            platform: registration.platform,
            fcm_token: registration.fcmToken,
          }),
        });
        if (!current(target) || driver !== native) {
          // POST 대기 중 로그아웃했다면 늦게 생성된 연결을 같은 JWT로 제거한 다음 다음 작업을 허용합니다.
          await removeDevice(target, native);
          return false;
        }
        update({ deviceStatus: "registered" });
        return true;
      } catch (error) {
        if (current(target)) {
          fail(target, error);
          if (current(target)) update({ deviceStatus: "error" });
        }
        return false;
      }
    });
  }

  // 네이티브 준비가 로그인보다 늦어져도 드라이버가 연결되는 시점에 등록합니다.
  function setDeviceDriver(value: NotificationDeviceDriver | null) {
    driver = value;
    update({ deviceStatus: value ? "idle" : "unavailable" });
    if (value) void flushAcknowledgements();
    if (value && session && current(session)) void refreshDeviceRegistration();
  }

  // 기존 인증 모듈이 auth/me 검증을 마친 뒤 호출합니다. api는 해당 로그인 JWT를 고정 캡처해야 합니다.
  async function connectNotificationSession(input: {
    user: CurrentUserDto;
    api: NotificationApi;
  }): Promise<void> {
    if (
      !input.user.is_active ||
      !idText(input.user.id) ||
      !idText(input.user.agency_id) ||
      !["AGENCY_STAFF", "RESPONDER"].includes(input.user.role)
    ) {
      pendingPush = null;
      latestPush = null;
      disconnectNotificationSession();
      throw new Error(
        "소속 기관이 있는 활성 기관 담당자 또는 출동대원 정보가 필요합니다.",
      );
    }
    const previous = session;
    const target: Session = {
      user: { ...input.user },
      api: input.api,
      version: ++version,
      deviceId: null,
    };
    session = target;
    resetView("ready", target.user);
    if (previous && previous.user.id !== target.user.id) {
      const native = driver;
      // 다른 계정으로 전환할 때 이전 연결을 먼저 정리합니다. 이후 재등록도 같은 작업열을 사용합니다.
      void withDevice(async () => {
        try {
          await removeDevice(previous, native);
        } catch {
          /* 새 등록 API도 같은 UUID의 이전 소유 연결을 원자적으로 교체합니다. */
        }
        if (native) {
          try {
            await native.clearPresentedNotifications();
          } catch {
            /* 상세 권한은 API에서 다시 확인합니다. */
          }
        }
      });
    }
    const pending = pendingPush;
    pendingPush = null;
    if (pending && pending.userId !== null && pending.userId !== target.user.id)
      void acknowledgeResponse(pending.responseKey);
    await Promise.all([
      refreshDeviceRegistration(),
      getSettings(),
      pending && (pending.userId === null || pending.userId === target.user.id)
        ? handleNotificationResponse(pending.payload, pending.responseKey)
        : Promise.resolve(false),
      flushAcknowledgements(),
    ]);
  }

  // JWT를 지우기 전에 await해야 합니다. 서버 해제나 트레이 정리에 실패하면 false로 알려 재시도합니다.
  async function prepareNotificationLogout(): Promise<boolean> {
    const target = session;
    const logoutVersion = ++version;
    const native = driver;
    // 인증 복원 전이라도 명시적 로그아웃은 대기한 터치를 취소합니다. 드라이버가 늦으면 같은 키만 나중에 정리합니다.
    void acknowledgeResponse(pendingPush?.responseKey);
    void acknowledgeResponse(latestPush?.responseKey);
    // 해제 뒤 늦게 도착한 같은 OS 콜백도 명시적으로 취소한 터치를 다시 대기시키지 못하게 합니다.
    for (const id of [
      pendingPush?.payload.notification_id,
      latestPush?.payload.notification_id,
    ]) {
      if (id) consumedPushes.add(id);
    }
    if (consumedPushes.size > 200)
      consumedPushes.delete(consumedPushes.values().next().value!);
    pendingPush = null;
    latestPush = null;
    pushVersion++;
    resetView("signing-out");
    return withDevice(async () => {
      try {
        if (target) await removeDevice(target, native);
        if (native) await native.clearPresentedNotifications();
        if (session !== target || version !== logoutVersion) return false;
        session = null;
        resetView("waiting");
        return true;
      } catch {
        if (session === target && version === logoutVersion) {
          update({
            status: "logout-failed",
            deviceStatus: "error",
            error:
              "알림 기기 연결 해제를 확인하지 못했습니다. 로그인 정보를 유지한 채 다시 시도해 주세요.",
          });
        }
        return false;
      }
    });
  }

  // 최근 알림은 서버의 사용자·기관 필터를 사용합니다. 늦게 도착한 이전 조회는 화면을 덮지 않습니다.
  async function listNotifications(
    options: ListOptions = {},
  ): Promise<NotificationDto[]> {
    const target = session;
    if (!target || !current(target)) return [];
    const queryVersion = ++listVersion;
    lastList = { ...options };
    const limit = Math.min(100, Math.max(1, Math.trunc(options.limit ?? 30)));
    const offset = Math.min(
      1_000_000,
      Math.max(0, Math.trunc(options.offset ?? 0)),
    );
    update({ loading: true });
    try {
      const rows = await target.api<NotificationDto[]>(
        `/api/notifications?limit=${limit}&offset=${offset}&unread_only=${options.unreadOnly === true}`,
      );
      if (!current(target) || queryVersion !== listVersion) return [];
      if (!Array.isArray(rows) || rows.some((row) => !validNotification(row)))
        throw new Error("INVALID_NOTIFICATION_RESPONSE");
      const notifications = rows.map((row) => readRows.get(row.id) ?? row);
      update({ notifications, loading: false });
      return notifications;
    } catch (error) {
      if (current(target) && queryVersion === listVersion) {
        update({ loading: false });
        fail(target, error);
      }
      return [];
    }
  }

  // 실행 중 Push 수신 시 현재 알림 조회 조건을 유지하며 새 목록을 받습니다.
  async function refreshNotifications(): Promise<void> {
    await listNotifications(lastList);
  }

  // 읽음 API는 본인 소유 알림만 반환합니다. OFF 설정과 관계없이 DB 읽음 기록은 유지됩니다.
  async function markRead(
    notificationId: number | string,
  ): Promise<NotificationDto | null> {
    const target = session;
    const id = idText(notificationId);
    if (!target || !current(target) || !id) return null;
    try {
      const row = await target.api<NotificationDto>(
        `/api/notifications/${id}/read`,
        { method: "PATCH" },
      );
      if (!current(target)) return null;
      if (!validNotification(row, id))
        throw new Error("INVALID_NOTIFICATION_RESPONSE");
      readRows.set(row.id, row);
      update({
        notifications: snapshot.notifications.map((item) =>
          item.id === row.id ? row : item,
        ),
      });
      return row;
    } catch (error) {
      notePushFailure(target, id, error);
      fail(target, error);
      return null;
    }
  }

  // 알림 OFF라도 목록과 읽음 기록은 삭제하지 않습니다. 세션 사용자 정보 대신 서버의 현재 설정을 조회합니다.
  async function getSettings(): Promise<boolean | null> {
    const target = session;
    if (!target || !current(target)) return null;
    const requestVersion = ++settingsVersion;
    try {
      const result = await target.api<{ enabled: boolean }>(
        "/api/settings/me/notifications",
      );
      if (!current(target) || requestVersion !== settingsVersion) return null;
      if (typeof result.enabled !== "boolean")
        throw new Error("INVALID_SETTINGS_RESPONSE");
      update({ enabled: result.enabled });
      return result.enabled;
    } catch (error) {
      if (requestVersion === settingsVersion) fail(target, error);
      return null;
    }
  }

  // 빠르게 여러 번 누른 스위치도 서버에 순서대로 저장하여 마지막 선택이 유지되도록 합니다.
  async function setEnabled(enabled: boolean): Promise<boolean> {
    const target = session;
    if (!target || !current(target) || typeof enabled !== "boolean")
      return false;
    const requestVersion = ++settingsVersion;
    const operation = async () => {
      if (!current(target)) return false;
      try {
        const result = await target.api<{ enabled: boolean }>(
          "/api/settings/me/notifications",
          {
            method: "PATCH",
            body: JSON.stringify({ enabled }),
          },
        );
        if (!current(target) || requestVersion !== settingsVersion)
          return false;
        if (typeof result.enabled !== "boolean")
          throw new Error("INVALID_SETTINGS_RESPONSE");
        update({ enabled: result.enabled });
        return true;
      } catch (error) {
        if (requestVersion === settingsVersion) fail(target, error);
        return false;
      }
    };
    const task = settingsLane.then(operation, operation);
    settingsLane = task.catch(() => undefined);
    return task;
  }

  // 상세 응답이 늦게 도착해도 마지막 선택·현재 계정에 맞을 때만 화면 이동 신호를 보냅니다.
  async function loadIncident(
    target: Session,
    id: string,
    requestVersion: number,
    notificationId: string | null,
  ): Promise<boolean> {
    if (!current(target) || requestVersion !== openVersion) return false;
    try {
      const incident = await target.api<IncidentDto>(`/api/incidents/${id}`);
      if (!current(target) || requestVersion !== openVersion) return false;
      if (!incident || idText(incident.id) !== id)
        throw new Error("INVALID_INCIDENT_RESPONSE");
      update({
        incident,
        openedNotificationId: notificationId,
        navigationVersion: snapshot.navigationVersion + 1,
      });
      return true;
    } catch (error) {
      if (requestVersion === openVersion) {
        notePushFailure(target, notificationId, error);
        fail(target, error);
      }
      return false;
    }
  }

  // 본인 알림 확인을 먼저 하고 반환된 사건 ID만 사용합니다. 다른 계정 알림의 404 뒤에는 상세를 요청하지 않습니다.
  async function openNotification(
    notificationId: number | string,
  ): Promise<boolean> {
    const target = session;
    const id = idText(notificationId);
    if (!target || !current(target) || !id) return false;
    const key = `${target.version}:${id}`;
    const existing = opening.get(key);
    if (existing) return existing;
    const requestVersion = ++openVersion;
    update({ incident: null, openedNotificationId: null, error: null });
    const task = (async () => {
      const row = await markRead(id);
      if (!row || !current(target) || requestVersion !== openVersion)
        return false;
      return loadIncident(target, String(row.incident_id), requestVersion, id);
    })();
    opening.set(key, task);
    try {
      return await task;
    } finally {
      if (opening.get(key) === task) opening.delete(key);
    }
  }

  // 이미 허용된 사건 화면의 다시 조회에도 서버 상세 권한 검사를 다시 적용합니다.
  async function openIncident(incidentId: number | string): Promise<boolean> {
    const target = session;
    const id = idText(incidentId);
    if (!target || !current(target) || !id) return false;
    const requestVersion = ++openVersion;
    update({ incident: null, openedNotificationId: null, error: null });
    return loadIncident(target, id, requestVersion, null);
  }

  // 인증 복원 전 터치는 마지막 요청을 보관합니다. 같은 알림의 초기 응답·리스너 중복으로 두 번 이동하지 않습니다.
  async function handleNotificationResponse(
    data: unknown,
    nativeResponseKey?: string,
  ): Promise<boolean> {
    const payload = parsePushData(data);
    const responseKey =
      typeof nativeResponseKey === "string" && nativeResponseKey.length <= 512
        ? nativeResponseKey
        : undefined;
    if (!payload) return false;
    if (consumedPushes.has(payload.notification_id)) {
      await acknowledgeResponse(responseKey);
      return false;
    }
    if (snapshot.status === "waiting") {
      // 같은 대기 메시지의 리스너 중복이 사용자에 묶인 재인증 대기를 익명 대기로 바꾸지 못하게 합니다.
      if (pendingPush?.payload.notification_id !== payload.notification_id)
        pendingPush = { payload, userId: null, responseKey };
      else if (responseKey) pendingPush.responseKey = responseKey;
      return false;
    }
    if (!session || !current(session)) return false;
    const target = session;
    const key = `${target.version}:${payload.notification_id}`;
    if (responseKey) {
      const keys = pushResponseKeys.get(key) ?? new Set<string>();
      keys.add(responseKey);
      pushResponseKeys.set(key, keys);
    }
    if (pushInFlight.has(key)) {
      if (
        latestPush?.target === target &&
        latestPush.payload.notification_id === payload.notification_id &&
        responseKey
      )
        latestPush.responseKey = responseKey;
      return false;
    }
    pushInFlight.add(key);
    const operation = { payload, target, version: ++pushVersion, responseKey };
    latestPush = operation;
    try {
      const opened = await openNotification(payload.notification_id);
      const failure = pushFailures.get(key);
      if (opened || failure === "denied") {
        consumedPushes.add(payload.notification_id);
        if (consumedPushes.size > 200)
          consumedPushes.delete(consumedPushes.values().next().value!);
        if (pendingPush?.payload.notification_id === payload.notification_id)
          pendingPush = null;
        for (const key of pushResponseKeys.get(
          `${target.version}:${payload.notification_id}`,
        ) ?? [])
          await acknowledgeResponse(key);
      } else if (
        failure === "retry" &&
        current(target) &&
        operation.version === pushVersion
      ) {
        pendingPush = {
          payload,
          userId: target.user.id,
          responseKey: operation.responseKey,
        };
      }
      return opened;
    } finally {
      pushInFlight.delete(key);
      pushFailures.delete(key);
      pushResponseKeys.delete(key);
      if (latestPush === operation) latestPush = null;
    }
  }

  // 메뉴 이동 시 상세 자료와 진행 중인 상세 요청을 비웁니다. 알림 목록 자체는 유지합니다.
  function clearOpenedIncident() {
    openVersion++;
    update({ incident: null, openedNotificationId: null });
  }

  return {
    getSnapshot: () => snapshot,
    // React는 useSyncExternalStore로 구독하고 화면이 닫히면 구독을 해제합니다.
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    connectNotificationSession,
    prepareNotificationLogout,
    disconnectNotificationSession,
    setDeviceDriver,
    refreshDeviceRegistration,
    listNotifications,
    refreshNotifications,
    markRead,
    getSettings,
    setEnabled,
    openNotification,
    openIncident,
    handleNotificationResponse,
    clearOpenedIncident,
    // 다음 사용자 동작에서 기존 안내만 닫고 서버나 토큰 상태는 바꾸지 않습니다.
    clearError() {
      update({ error: null });
    },
  };
}

export const notificationController = createNotificationController();
export const {
  connectNotificationSession,
  prepareNotificationLogout,
  disconnectNotificationSession,
  setDeviceDriver,
  refreshDeviceRegistration,
  refreshNotifications,
  handleNotificationResponse,
  clearOpenedIncident,
} = notificationController;
