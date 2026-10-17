/**
 * 전체 흐름: Android 실행 환경 확인 → 알림 채널·권한 → 설치 UUID·FCM 토큰
 *           → 알림 수신·터치 이벤트를 notifications.ts의 처리 함수로 전달.
 * 주요 기능: 네이티브 FCM 토큰, 설치 UUID 유지, 토큰 갱신 감지, 일반 종료 후 터치 복원.
 * 로그인·JWT 저장·권한 판단은 담당하지 않습니다. 현재 사용자 확인은 서버 API에서 합니다.
 * 백그라운드 알림은 Android가 표시하므로 별도의 로컬 알림을 다시 만들지 않습니다.
 */
import type { NotificationDeviceDriver } from "./notifications";

export const ANDROID_CHANNEL_ID = "octv_incident_delivery";
const INSTALLATION_KEY = "octv.push.installation_id.v1";
const UUID4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const INCIDENT_ID = /^[1-9][0-9]{0,18}$/;
const MAX_RECENT_EVENTS = 128;

type NotificationsModule = typeof import("expo-notifications");
type AndroidRuntime = {
  notifications: NotificationsModule;
  secureStore: typeof import("expo-secure-store");
  crypto: typeof import("expo-crypto");
};
type RuntimeResult =
  | { runtime: AndroidRuntime; reason?: never }
  | { runtime: null; reason: string };

export type AndroidPushStatus = {
  state: "ready" | "unsupported" | "permission_denied" | "error";
  message: string;
};
export type AndroidIncidentPayload = {
  schema_version: "1";
  type: "INCIDENT_DELIVERED";
  incident_id: string;
  notification_id: string;
};
export type AndroidPushCallbacks = {
  onResponse: (
    data: unknown,
    responseKey: string,
  ) => boolean | Promise<boolean>;
  onReceived: () => unknown | Promise<unknown>;
  onTokenChanged: () => unknown | Promise<unknown>;
  shouldPresent: () => boolean;
  onStatus?: (status: AndroidPushStatus) => void;
};

let runtimePromise: Promise<RuntimeResult> | null = null;
let installationPromise: Promise<string> | null = null;
let handlerOwner: symbol | null = null;
let latestFcmToken: string | null = null;
let tokenPromise: Promise<string> | null = null;
let tokenRequestActive = false;

// 배열·문자열을 객체로 오인하지 않고 외부 알림 데이터를 읽습니다.
function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

// 일부 Expo Android 이벤트에 포함되는 JSON data 문자열만 제한된 크기로 읽습니다.
function jsonRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "string" || value.length > 8192) return null;
  try {
    return record(JSON.parse(value));
  } catch {
    return null;
  }
}

// PR 3의 문자열 data 계약을 검사하며 URL·사용자 ID 같은 추가 지시는 사용하지 않습니다.
function incidentPayload(value: unknown): AndroidIncidentPayload | null {
  const data = record(value);
  if (
    data?.schema_version !== "1" ||
    data.type !== "INCIDENT_DELIVERED" ||
    typeof data.incident_id !== "string" ||
    !INCIDENT_ID.test(data.incident_id) ||
    typeof data.notification_id !== "string" ||
    !INCIDENT_ID.test(data.notification_id)
  )
    return null;
  return {
    schema_version: "1",
    type: "INCIDENT_DELIVERED",
    incident_id: data.incident_id,
    notification_id: data.notification_id,
  };
}

// SDK 57의 content.data와 Android remoteMessage.data에서 실제 서버 payload를 추출합니다.
export function extractAndroidNotificationData(
  value: unknown,
): AndroidIncidentPayload | null {
  const event = record(value);
  const notification = record(event?.notification) ?? event;
  const request = record(notification?.request);
  const content = record(request?.content);
  const trigger = record(request?.trigger);
  const remote = record(trigger?.remoteMessage);
  const contentData = record(content?.data);
  const remoteData = record(remote?.data);
  const candidates = [
    contentData,
    remoteData,
    jsonRecord(contentData?.dataString),
    jsonRecord(remoteData?.body),
  ]
    .map(incidentPayload)
    .filter((data): data is AndroidIncidentPayload => data !== null);
  const first = candidates[0];
  if (!first) return null;
  // 같은 이벤트의 두 위치에 서로 다른 사건 ID가 있으면 임의로 하나를 선택하지 않습니다.
  if (
    candidates.some(
      (data) =>
        data.incident_id !== first.incident_id ||
        data.notification_id !== first.notification_id,
    )
  )
    return null;
  return first;
}

// 수신과 일반 종료 복원이 같은 터치를 가리킬 때 동일한 중복 확인 키를 만듭니다.
export function androidNotificationResponseKey(value: unknown): string | null {
  const event = record(value);
  const data = extractAndroidNotificationData(event);
  if (!data) return null;
  const request = record(record(event?.notification)?.request);
  const identifier =
    typeof request?.identifier === "string" ? request.identifier : "unknown";
  const action =
    typeof event?.actionIdentifier === "string"
      ? event.actionIdentifier
      : "default";
  return `${identifier}|${action}|${data.notification_id}`;
}

// FCM 토큰·기본 오류 본문이 화면이나 로그에 새어 나가지 않도록 정해진 상태 문구만 전달합니다.
function report(
  onStatus: AndroidPushCallbacks["onStatus"],
  status: AndroidPushStatus,
): void {
  onStatus?.(status);
}

// 웹·iOS·Expo Go를 먼저 제외한 다음에만 Android 네이티브 알림 모듈을 불러옵니다.
async function loadAndroidRuntime(): Promise<RuntimeResult> {
  if (!runtimePromise) {
    runtimePromise = (async () => {
      const { Platform } = await import("react-native");
      if (Platform.OS !== "android") {
        return {
          runtime: null,
          reason: "휴대폰 Push는 Android 설치 앱에서 지원합니다.",
        };
      }
      const { default: Constants, ExecutionEnvironment } = await import(
        "expo-constants"
      );
      if (Constants.executionEnvironment === ExecutionEnvironment.StoreClient) {
        return {
          runtime: null,
          reason:
            "Expo Go에서는 원격 Push를 사용할 수 없습니다. Android APK가 필요합니다.",
        };
      }
      const [notifications, secureStore, crypto] = await Promise.all([
        import("expo-notifications"),
        import("expo-secure-store"),
        import("expo-crypto"),
      ]);
      return { runtime: { notifications, secureStore, crypto } };
    })().catch(() => {
      runtimePromise = null;
      throw new Error(
        "Android 알림 모듈을 불러오지 못했습니다. 필요한 패키지를 포함해 APK를 다시 빌드해주세요.",
      );
    });
  }
  return runtimePromise;
}

// 채널을 먼저 만들어 Android 13 이상에서 권한 요청과 토큰 발급 순서가 맞도록 합니다.
async function ensureAndroidChannel(
  notifications: NotificationsModule,
): Promise<void> {
  await notifications.setNotificationChannelAsync(ANDROID_CHANNEL_ID, {
    name: "OCTV 사건 전달",
    description: "소속기관에 전달된 사건 알림",
    importance: notifications.AndroidImportance.HIGH,
    sound: "default",
    vibrationPattern: [0, 250, 250, 250],
    enableVibrate: true,
    showBadge: false,
    lockscreenVisibility: notifications.AndroidNotificationVisibility.PRIVATE,
  });
  // 사용자가 바꾼 채널·무음·방해 금지 설정은 앱이 강제로 되돌리지 않습니다.
}

// 앱 설치 UUID를 한 번 저장하고 로그인·로그아웃·FCM 토큰 변경에도 같은 값을 사용합니다.
async function installationId(runtime: AndroidRuntime): Promise<string> {
  if (!installationPromise) {
    installationPromise = (async () => {
      const existing = await runtime.secureStore.getItemAsync(INSTALLATION_KEY);
      if (existing && UUID4.test(existing)) return existing;
      const created = runtime.crypto.randomUUID();
      if (!UUID4.test(created))
        throw new Error("설치 식별자를 만들지 못했습니다.");
      await runtime.secureStore.setItemAsync(INSTALLATION_KEY, created);
      return created;
    })().catch(() => {
      installationPromise = null;
      throw new Error(
        "앱 설치 식별자를 저장하지 못했습니다. 기기 저장 상태를 확인해주세요.",
      );
    });
  }
  return installationPromise;
}

// 네이티브 이벤트와 최초 조회가 반환한 값 모두 Android FCM 형식인지 확인합니다.
function nativeFcmToken(value: unknown): string | null {
  const token = record(value);
  if (
    token?.type !== "android" ||
    typeof token.data !== "string" ||
    token.data.length < 16 ||
    token.data.length > 4096 ||
    /\s/.test(token.data) ||
    /^(expo|exponent)pushtoken\[/i.test(token.data)
  )
    return null;
  return token.data;
}

// getDevicePushTokenAsync도 토큰 이벤트를 발생시키므로 최초 조회만 하고 이후에는 갱신값을 사용합니다.
async function currentFcmToken(
  notifications: NotificationsModule,
): Promise<string> {
  if (latestFcmToken) return latestFcmToken;
  if (!tokenPromise) {
    tokenRequestActive = true;
    tokenPromise = (async () => {
      const token = nativeFcmToken(
        await notifications.getDevicePushTokenAsync(),
      );
      if (!token) {
        throw new Error(
          "Android FCM 등록 토큰을 확인하지 못했습니다. Firebase와 APK 설정을 확인해주세요.",
        );
      }
      // 조회 도중 토큰 갱신 이벤트가 먼저 왔다면 그 최신 값을 보존합니다.
      latestFcmToken ??= token;
      return latestFcmToken;
    })().finally(() => {
      tokenPromise = null;
      tokenRequestActive = false;
    });
  }
  return tokenPromise;
}

// 현재 플랫폼에 맞는 기기 driver를 만들며 미지원 환경에는 null을 반환합니다.
export async function createAndroidPushDriver(
  options: Pick<AndroidPushCallbacks, "onStatus"> = {},
): Promise<NotificationDeviceDriver | null> {
  const result = await loadAndroidRuntime();
  if (!result.runtime) {
    report(options.onStatus, { state: "unsupported", message: result.reason });
    return null;
  }
  const runtime = result.runtime;
  const notifications = runtime.notifications;
  return {
    // 서버가 기존 등록도 지울 수 있도록 토큰·권한 요청 없이 설치 UUID만 제공합니다.
    getInstallationId: () => installationId(runtime),
    // 로그인 확인 이후 호출하며, Expo Push Token이나 iOS APNs 토큰을 보내지 않습니다.
    async prepareDevice() {
      await ensureAndroidChannel(notifications);
      let permissions = await notifications.getPermissionsAsync();
      if (!permissions.granted && permissions.canAskAgain) {
        permissions = await notifications.requestPermissionsAsync();
      }
      if (!permissions.granted) {
        report(options.onStatus, {
          state: "permission_denied",
          message:
            "기기 알림 권한이 꺼져 있습니다. 휴대폰 설정에서 OCTV 알림을 허용해주세요.",
        });
        return null;
      }
      const fcmToken = await currentFcmToken(notifications);
      return {
        deviceId: await installationId(runtime),
        platform: "android",
        fcmToken,
      };
    },
    // 로그아웃·계정 변경 시 이전 알림 표시를 지우되 설치 UUID는 삭제하지 않습니다.
    async clearPresentedNotifications() {
      await notifications.dismissAllNotificationsAsync();
      notifications.clearLastNotificationResponse();
    },
    // 로그인 대기 후 처리된 터치도 controller가 원래 응답 키로 안전하게 정리할 수 있습니다.
    async acknowledgeResponse(responseKey: string) {
      const last = notifications.getLastNotificationResponse();
      // 비교와 삭제 사이에 await를 두지 않아 다른 새 터치를 지우지 않습니다.
      if (androidNotificationResponseKey(last) === responseKey) {
        notifications.clearLastNotificationResponse();
      }
    },
  };
}

// 제한된 최근 이벤트만 기억하여 화면 재수신에 따른 중복 처리를 줄입니다.
function remember(recent: Set<string>, key: string): boolean {
  if (recent.has(key)) return false;
  recent.add(key);
  if (recent.size > MAX_RECENT_EVENTS)
    recent.delete(recent.values().next().value!);
  return true;
}

// 수신 listener를 먼저 등록하고 마지막 터치를 읽으며 즉시 호출 가능한 정리 함수를 반환합니다.
export function startAndroidPush(callbacks: AndroidPushCallbacks): () => void {
  let stopped = false;
  const owner = Symbol("octv-push-handler");
  const subscriptions: Array<{ remove(): void }> = [];
  const responses = new Set<string>();
  const foreground = new Set<string>();
  let activeNotifications: NotificationsModule | null = null;

  // 외부 callback 실패의 원문에 토큰이 포함될 수 있어 정해진 안내만 사용합니다.
  const failed = () => {
    if (!stopped)
      report(callbacks.onStatus, {
        state: "error",
        message:
          "알림 처리를 마치지 못했습니다. 알림 목록에서 다시 확인해주세요.",
      });
  };

  void (async () => {
    const result = await loadAndroidRuntime();
    if (stopped) return;
    if (!result.runtime) {
      report(callbacks.onStatus, {
        state: "unsupported",
        message: result.reason,
      });
      return;
    }
    const notifications = result.runtime.notifications;
    activeNotifications = notifications;
    await ensureAndroidChannel(notifications);
    if (stopped) return;
    handlerOwner = owner;
    notifications.setNotificationHandler({
      // SDK 57은 실행 중 표시를 명시해야 합니다. 권한 API 호출 없이 즉시 응답합니다.
      handleNotification: async (notification) => {
        const data = extractAndroidNotificationData(notification);
        const show =
          !stopped &&
          callbacks.shouldPresent() &&
          data !== null &&
          remember(foreground, data.notification_id);
        return {
          shouldShowBanner: show,
          shouldShowList: show,
          shouldPlaySound: show,
          shouldSetBadge: false,
        };
      },
    });

    // 실제 화면 이동은 로그인 복원·본인 알림·사건 권한을 확인하는 controller에 맡깁니다.
    const receivedResponse = (
      response: import("expo-notifications").NotificationResponse | null,
    ) => {
      if (
        stopped ||
        !response ||
        response.actionIdentifier !== notifications.DEFAULT_ACTION_IDENTIFIER
      )
        return;
      const data = extractAndroidNotificationData(response);
      const responseKey = androidNotificationResponseKey(response);
      if (!data || !responseKey || responses.has(responseKey)) return;
      // 실행 중인 동일 터치만 막습니다. 로그인 대기·통신 실패 후 재터치는 다시 전달합니다.
      responses.add(responseKey);
      void Promise.resolve()
        .then(() => {
          if (!stopped) return callbacks.onResponse(data, responseKey);
          return false;
        })
        .then((consumed) => {
          if (stopped || consumed !== true) return;
          // 더 최근에 도착한 다른 터치를 실수로 지우지 않도록 마지막 이벤트를 다시 비교합니다.
          const last = notifications.getLastNotificationResponse();
          if (androidNotificationResponseKey(last) === responseKey)
            notifications.clearLastNotificationResponse();
        })
        .catch(failed)
        .finally(() => responses.delete(responseKey));
    };

    subscriptions.push(
      notifications.addNotificationReceivedListener((notification) => {
        if (stopped || !extractAndroidNotificationData(notification)) return;
        // Android가 표시한 알림을 scheduleNotificationAsync로 다시 생성하지 않습니다.
        void Promise.resolve()
          .then(() => !stopped && callbacks.onReceived())
          .catch(failed);
      }),
      notifications.addNotificationResponseReceivedListener(receivedResponse),
      notifications.addPushTokenListener((token) => {
        if (stopped) return;
        const changed = nativeFcmToken(token);
        if (!changed || changed === latestFcmToken) return;
        // 토큰은 현재 실행의 메모리에만 보관합니다. 로그·파일·SecureStore에는 기록하지 않습니다.
        latestFcmToken = changed;
        // 최초 조회가 자체 발생시킨 이벤트는 준비 중인 등록이 처리하므로 재등록을 반복하지 않습니다.
        if (tokenRequestActive) return;
        void Promise.resolve()
          .then(() => !stopped && callbacks.onTokenChanged())
          .catch(failed);
      }),
    );
    receivedResponse(notifications.getLastNotificationResponse());
    report(callbacks.onStatus, {
      state: "ready",
      message: "Android 알림 수신 처리가 준비되었습니다.",
    });
  })().catch(failed);

  // 비동기 준비 중 unmount된 경우에도 뒤늦은 listener·화면 이동이 남지 않게 합니다.
  return () => {
    stopped = true;
    subscriptions.forEach((subscription) => subscription.remove());
    if (handlerOwner === owner && activeNotifications) {
      activeNotifications.setNotificationHandler(null);
      handlerOwner = null;
    }
  };
}
