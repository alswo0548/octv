/**
 * 후속-04 로그인 연결: 기존 Backend 인증 API → Android SecureStore의 JWT → 기존 알림 세션.
 * 로그인·JWT 검증을 다시 구현하지 않고 /api/auth/login 및 /api/auth/me를 재사용합니다.
 * 로그아웃 시 SettingsScreen이 먼저 알림 기기를 해제하고, 그 다음 이 모듈이 JWT를 지웁니다.
 * 인증된 사용자와 API는 한 로그인 세션의 토큰에 고정하여 계정 전환 시 섞이지 않게 합니다.
 */
import type { CurrentUserDto, LoginDto, IncidentDto } from "@octv/shared";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { ApiError, createApi, getCurrentUser } from "./api";
import { notificationController } from "./notifications";

type AuthApi = ReturnType<typeof createApi>;
export type MobileSessionSnapshot = {
  status: "waiting" | "checking" | "ready";
  user: CurrentUserDto | null;
  api: AuthApi | null;
  message: string | null;
};

const STORAGE_KEY = "octv.mobile.jwt.v1";
const baseUrl = (process.env.EXPO_PUBLIC_API_BASE_URL ?? "")
  .trim()
  .replace(/\/$/, "");
const listeners = new Set<() => void>();
let snapshot: MobileSessionSnapshot = {
  status: "waiting",
  user: null,
  api: null,
  message: null,
};
let activeToken: string | null = null;
let generation = 0;
let restoreTask: Promise<void> | null = null;
let storageQueue: Promise<void> = Promise.resolve();

// 만료 처리와 새 로그인 저장이 겹쳐 새 JWT를 잘못 지우지 않도록 저장 작업을 순서대로 수행합니다.
function queueStorage(action: () => Promise<void>): Promise<void> {
  const task = storageQueue.then(action, action);
  storageQueue = task.catch(() => undefined);
  return task;
}

function publish(next: MobileSessionSnapshot) {
  snapshot = next;
  listeners.forEach((listener) => listener());
}
function requireServerUrl() {
  if (!/^https?:\/\//.test(baseUrl)) {
    throw new Error(
      "EXPO_PUBLIC_API_BASE_URL에 접속할 Backend 주소를 설정해주세요.",
    );
  }
  return baseUrl;
}
function requireAgencyUser(user: CurrentUserDto) {
  if (
    !user.is_active ||
    !["AGENCY_STAFF", "RESPONDER"].includes(user.role) ||
    !Number.isSafeInteger(user.id) ||
    !Number.isSafeInteger(user.agency_id) ||
    (user.agency_id ?? 0) <= 0
  ) {
    throw new Error("활성 기관 담당자 또는 출동대원 계정으로 로그인해주세요.");
  }
}
async function storedToken(): Promise<string | null> {
  // 웹 미리보기에서는 영구 저장하지 않습니다. 실제 Android에서만 암호화된 저장소를 사용합니다.
  return Platform.OS === "android"
    ? SecureStore.getItemAsync(STORAGE_KEY)
    : null;
}
async function saveToken(token: string): Promise<void> {
  if (Platform.OS === "android") {
    await queueStorage(() => SecureStore.setItemAsync(STORAGE_KEY, token));
  }
}
async function deleteToken(): Promise<void> {
  if (Platform.OS === "android") {
    await queueStorage(() => SecureStore.deleteItemAsync(STORAGE_KEY));
  }
}
async function sessionFromToken(
  token: string,
): Promise<{ user: CurrentUserDto; api: AuthApi }> {
  const api = createApi(requireServerUrl(), () => token);
  // 로그인 응답의 사용자 정보 대신 서버 /me로 JWT 소유자·활성 상태를 다시 확인합니다.
  const user = await getCurrentUser(api);
  requireAgencyUser(user);
  return { user, api };
}

async function restore(): Promise<void> {
  if (restoreTask) return restoreTask;
  const started = ++generation;
  publish({ status: "checking", user: null, api: null, message: null });
  restoreTask = (async () => {
    try {
      const token = await storedToken();
      if (started !== generation) return;
      if (!token) {
        publish({ status: "waiting", user: null, api: null, message: null });
        return;
      }
      const verified = await sessionFromToken(token);
      if (started !== generation) return;
      await notificationController.connectNotificationSession(verified);
      if (started !== generation) return;
      activeToken = token;
      publish({ status: "ready", ...verified, message: null });
    } catch (error) {
      if (started !== generation) return;
      notificationController.disconnectNotificationSession();
      activeToken = null;
      // JWT가 만료되었거나 거부된 경우에만 저장된 인증을 지웁니다.
      if (error instanceof ApiError && [401, 403].includes(error.status)) {
        try {
          await deleteToken();
        } catch {
          /* 실제 토큰 삭제 여부는 다음 복원에서 재확인합니다. */
        }
      }
      publish({
        status: "waiting",
        user: null,
        api: null,
        message:
          "저장된 로그인을 확인하지 못했습니다. 로그인 후 다시 시도해주세요.",
      });
    }
  })().finally(() => {
    restoreTask = null;
  });
  return restoreTask;
}

async function login(email: string, password: string): Promise<void> {
  if (!email.trim() || !password)
    throw new Error("이메일과 비밀번호를 입력해주세요.");
  const started = ++generation;
  try {
    const unauthenticatedApi = createApi(requireServerUrl(), () => null);
    const loginResponse = await unauthenticatedApi<LoginDto>(
      "/api/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      },
    );
    if (
      !loginResponse ||
      typeof loginResponse.access_token !== "string" ||
      !loginResponse.access_token
    ) {
      throw new Error("로그인 응답을 확인할 수 없습니다.");
    }
    const token = loginResponse.access_token;
    const verified = await sessionFromToken(token);
    if (started !== generation) return;
    // 기기 등록에 사용할 JWT를 먼저 보관합니다. Expo SecureStore는 기존 알림 의존성입니다.
    await saveToken(token);
    if (started !== generation) return;
    try {
      await notificationController.connectNotificationSession(verified);
    } catch {
      notificationController.disconnectNotificationSession();
      await deleteToken();
      throw new Error("알림 세션을 연결하지 못했습니다. 다시 로그인해주세요.");
    }
    if (started !== generation) return;
    activeToken = token;
    publish({ status: "ready", ...verified, message: null });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401)
        throw new Error("이메일 또는 비밀번호가 올바르지 않습니다.");
      if (error.status === 403) throw new Error("사용할 수 없는 계정입니다.");
      throw new Error("로그인 서버를 확인해주세요. 잠시 후 다시 시도해주세요.");
    }
    if (
      error instanceof Error &&
      /EXPO_PUBLIC_API_BASE_URL|기관 담당자|출동대원|입력해주세요|로그인 응답|알림 세션/.test(
        error.message,
      )
    ) {
      throw error;
    }
    throw new Error(
      "로그인을 완료하지 못했습니다. 네트워크·기기 설정을 확인해주세요.",
    );
  }
}

// 호출 전에 SettingsScreen의 prepareNotificationLogout()이 true를 반환해야 합니다.
async function logout(): Promise<void> {
  await deleteToken(); // 지우기 실패했는데 로그아웃 성공으로 표시하지 않습니다.
  generation++;
  activeToken = null;
  publish({ status: "waiting", user: null, api: null, message: null });
}

// 만료된 JWT로 목록을 조회한 경우 인증 상태와 이전 사건 자료를 함께 지웁니다.
async function invalidate(expectedApi?: AuthApi): Promise<void> {
  if (expectedApi && snapshot.api !== expectedApi) return;
  generation++;
  activeToken = null;
  notificationController.disconnectNotificationSession();
  publish({
    status: "waiting",
    user: null,
    api: null,
    message: "로그인 유효기간이 지났습니다. 다시 로그인해주세요.",
  });
  try {
    await deleteToken();
  } catch {
    /* 다음 시작 시 서버가 만료를 재확인합니다. */
  }
}

function incidentImageSource(incident: IncidentDto) {
  if (!activeToken || snapshot.status !== "ready") return null;
  if (!Number.isSafeInteger(incident.id) || incident.id <= 0) return null;
  return {
    uri: `${requireServerUrl()}/api/incidents/${incident.id}/image`,
    headers: { Authorization: `Bearer ${activeToken}` },
  };
}

function demoVideoSource(incident: IncidentDto) {
  if (!activeToken || snapshot.status !== "ready") {
    return null;
  }

  if (incident.provider?.trim().toUpperCase() !== "DEMO") {
    return null;
  }

  if (!Number.isSafeInteger(incident.cctv_id) || incident.cctv_id <= 0) {
    return null;
  }

  return {
    uri: `${requireServerUrl()}/api/demo/cctvs/${incident.cctv_id}/video`,
    headers: {
      Authorization: `Bearer ${activeToken}`,
    },
  };
}

export const mobileSession = {
  getSnapshot: () => snapshot,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  restore,
  login,
  logout,
  invalidate,
  incidentImageSource,
  demoVideoSource,
};
