import { hiddenIncidentIds } from "./incidentVisibility";
/**
 * 웹 실제 사건 데이터 연결
 *
 * 역할/흐름
 * 1. 로그인 담당 코드가 확인한 사용자·JWT API 함수를 이 모듈에 전달합니다.
 * 2. CONTROL_ADMIN / AGENCY_STAFF / RESPONDER 웹 세션을 연결합니다.
 * 3. 화면은 이 모듈을 통해 사건 목록/상세/확인/오탐 API를 호출합니다.
 * 4. 세션 또는 선택 사건이 바뀌면 이전 응답을 폐기합니다.
 * 5. 사건 대표 이미지는 JWT 인증이 필요한 별도 JPEG API에서 Blob으로 조회합니다.
 *
 * 이 파일은 로그인·토큰 저장/삭제를 직접 구현하지 않습니다.
 * 로그인 화면이 세션을 연결하고, 로그아웃 시 전달받은 토큰 폐기 함수를 호출합니다.
 */

import type { CurrentUserDto, IncidentDto, PageDto } from "@octv/shared";
import { ApiError, type createApi } from "./api";

export type IncidentDetailDto = IncidentDto & {
  risk_breakdown_json: Record<string, unknown> | null;
  priority_breakdown_json: Record<string, unknown> | null;
  rule_version: string | null;
};

export type IncidentFilters = {
  page?: number;
  page_size?: number;
  priority?: "P1" | "P2" | "P3";
  status?: IncidentDto["status"];
  hazard_type?: string;
  confirmed_only?: boolean;
  q?: string;
  start?: string;
  end?: string;
};

export type WebIncidentSessionInput = {
  // /api/auth/me에서 확인한 사용자와 이 로그인 세션에 고정된 createApi()를 전달합니다.
  user: CurrentUserDto;
  api: ReturnType<typeof createApi>;
  getToken: () => string | null;
  baseUrl: string;

  // 인증 담당 코드에서 JWT 폐기 및 로그인 상태 해제를 수행할 함수입니다.
  logout: () => void | Promise<void>;
};

export type WebIncidentSession = Readonly<{
  version: number;
  user: CurrentUserDto;
}>;

type ActiveSession = {
  visible: WebIncidentSession;
  api: WebIncidentSessionInput["api"];
  getToken: WebIncidentSessionInput["getToken"];
  baseUrl: string;
  logout: WebIncidentSessionInput["logout"];
  controller: AbortController;
};

const WEB_ROLES = ["CONTROL_ADMIN", "AGENCY_STAFF", "RESPONDER"] as const;

type WebRole = (typeof WEB_ROLES)[number];

let active: ActiveSession | null = null;
let version = 0;

const listeners = new Set<() => void>();

const isId = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value > 0;

const isWebRole = (value: string): value is WebRole =>
  WEB_ROLES.includes(value as WebRole);

export function setWebIncidentSession(
  input: WebIncidentSessionInput | null,
): void {
  active?.controller.abort();
  active = null;
  version += 1;

  try {
    if (input === null) return;

    if (
      !isId(input.user?.id) ||
      !isWebRole(input.user.role) ||
      input.user.is_active !== true ||
      typeof input.api !== "function" ||
      typeof input.getToken !== "function" ||
      typeof input.logout !== "function" ||
      typeof input.baseUrl !== "string"
    ) {
      throw new Error("활성 웹 사용자 세션만 연결할 수 있습니다.");
    }

    if (input.user.role !== "CONTROL_ADMIN" && !isId(input.user.agency_id)) {
      throw new Error("기관 사용자에게는 소속기관 정보가 필요합니다.");
    }

    active = {
      visible: Object.freeze({
        version,
        user: input.user,
      }),
      api: input.api,
      getToken: input.getToken,
      baseUrl: input.baseUrl.replace(/\/$/, ""),
      logout: input.logout,
      controller: new AbortController(),
    };
  } finally {
    listeners.forEach((listener) => listener());
  }
}

export function subscribeWebIncidentSession(listener: () => void): () => void {
  listeners.add(listener);

  return () => listeners.delete(listener);
}

export function getWebIncidentSession(): WebIncidentSession | null {
  return active?.visible ?? null;
}

// 기관 전달 모듈이 같은 사용자/토큰 API를 재사용하도록 공개합니다.
export function getWebIncidentApi(sessionVersion: number) {
  return active?.visible.version === sessionVersion ? active.api : null;
}

// 관리자 실시간 CCTV WHEP의 인증용: 기존 JWT를 네이티브 브라우저 fetch의
// Authorization 헤더에만 전달하며 URL·로그·미디어 서버 응답에는 넣지 않습니다.
export function getAdminStreamHeaders(sessionVersion: number): { Authorization: string } {
  const session = requireSession(sessionVersion);
  if (session.visible.user.role !== "CONTROL_ADMIN") throw new Error("관리자 권한이 필요합니다.");
  const token = session.getToken();
  if (!token) throw new Error("로그인 상태를 확인할 수 없습니다.");
  return { Authorization: `Bearer ${token}` };
}

export async function disconnectWebIncidentSession(): Promise<void> {
  const current = active;

  setWebIncidentSession(null);

  // UI 연결 해제와 달리 JWT 삭제는 인증 담당 함수가 수행합니다.
  if (current) {
    await current.logout();
  }
}

function requireSession(sessionVersion: number): ActiveSession {
  if (!active || active.visible.version !== sessionVersion) {
    throw new Error("로그인 또는 사건 조회 세션이 변경되었습니다.");
  }

  return active;
}

// 사용자 계정이 바뀌거나 화면을 벗어난 뒤 도착한 API 응답은 사용하지 않습니다.
async function read<T>(
  sessionVersion: number,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const session = requireSession(sessionVersion);

  const signal = options.signal
    ? AbortSignal.any([session.controller.signal, options.signal])
    : session.controller.signal;

  const response = await session.api<T>(path, {
    ...options,
    signal,
  });

  if (active !== session || signal.aborted) {
    throw new Error("로그인 또는 조회 대상이 변경되었습니다.");
  }

  return response;
}

// 운영 화면도 동일한 JWT·세션 취소 경계를 사용합니다.
export { read as requestWebApi };

export async function listServerIncidents(
  sessionVersion: number,
  filters: IncidentFilters,
  signal?: AbortSignal,
): Promise<PageDto<IncidentDto>> {
  const params = new URLSearchParams();

  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  });

  const current = requireSession(sessionVersion);
  if (current.visible.user.role !== "CONTROL_ADMIN") {
    return read(sessionVersion, `/api/incidents?${params}`, { signal });
  }
  // Filtering a server page would leave holes and incorrect totals. Read every
  // authorized page before applying this web-only archive and pagination.
  const hidden = new Set(hiddenIncidentIds(sessionVersion));
  try {
    const archive = await read<{ archived_ids: number[] }>(sessionVersion, "/api/demo/v5/archive-scope", { signal });
    archive.archived_ids.forEach(id => hidden.add(id));
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
    // Standard non-demo API has no v5 extension; retain original incidents.
  }
  const items: IncidentDto[] = [];
  params.set("page_size", "100");
  for (let page = 1; ; page++) {
    params.set("page", String(page));
    const result = await read<PageDto<IncidentDto>>(sessionVersion, `/api/incidents?${params}`, { signal });
    items.push(...result.items);
    if (items.length >= result.total || result.items.length === 0) break;
  }
  const visible = items.filter(item => !hidden.has(item.id));
  const page = filters.page ?? 1;
  const size = filters.page_size ?? 5;
  return { items: visible.slice((page - 1) * size, page * size), total: visible.length, page, page_size: size };
}

export async function getServerIncident(
  sessionVersion: number,
  id: number,
  signal?: AbortSignal,
): Promise<IncidentDetailDto> {
  if (!isId(id)) {
    throw new Error("서버에서 발급된 사건 ID가 필요합니다.");
  }

  return read(sessionVersion, `/api/incidents/${id}`, {
    signal,
  });
}

export async function changeServerIncident(
  sessionVersion: number,
  id: number,
  operation: "confirm" | "false-positive",
): Promise<IncidentDto> {
  if (!isId(id)) {
    throw new Error("서버에서 발급된 사건 ID가 필요합니다.");
  }

  // 기관 전달과 다른 API입니다.
  // /sent를 임의 호출해 전달 성공을 만들지 않습니다.
  return read(sessionVersion, `/api/incidents/${id}/${operation}`, {
    method: "PATCH",
  });
}

export async function loadIncidentImageUrl(
  sessionVersion: number,
  id: number,
  signal?: AbortSignal,
): Promise<string> {
  if (!isId(id)) {
    throw new Error("서버에서 발급된 사건 ID가 필요합니다.");
  }

  const session = requireSession(sessionVersion);
  const token = session.getToken();

  if (!token) {
    throw new Error("로그인 상태를 확인할 수 없습니다.");
  }

  const combined = signal
    ? AbortSignal.any([session.controller.signal, signal])
    : session.controller.signal;

  // 이미지 요청은 JSON 기반 createApi를 거치지 않고 인증된 Blob으로 받습니다.
  const result = await fetch(`${session.baseUrl}/api/incidents/${id}/image`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal: combined,
    cache: "no-store",
  });

  if (!result.ok) {
    throw new ApiError(result.status, "대표 이미지를 불러올 수 없습니다.");
  }

  const blob = await result.blob();

  if (active !== session || combined.aborted) {
    throw new Error("세션이 변경되었습니다.");
  }

  if (!blob.type.startsWith("image/")) {
    throw new Error("이미지 형식을 확인할 수 없습니다.");
  }

  return URL.createObjectURL(blob);
}

export async function loadDemoVideoUrl(
  sessionVersion: number,
  cctvId: number,
  signal?: AbortSignal,
): Promise<string> {
  if (!isId(cctvId)) {
    throw new Error("CCTV ID를 확인할 수 없습니다.");
  }

  const session = requireSession(sessionVersion);
  const token = session.getToken();

  if (!token) {
    throw new Error("로그인 상태를 확인할 수 없습니다.");
  }

  const combined = signal
    ? AbortSignal.any([session.controller.signal, signal])
    : session.controller.signal;

  const response = await fetch(
    `${session.baseUrl}/api/demo/cctvs/${cctvId}/video`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal: combined,
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new ApiError(response.status, "Demo 영상을 불러올 수 없습니다.");
  }

  const blob = await response.blob();

  if (active !== session || combined.aborted) {
    throw new Error("세션이 변경되었습니다.");
  }

  if (!blob.type.startsWith("video/")) {
    throw new Error("영상 형식을 확인할 수 없습니다.");
  }

  return URL.createObjectURL(blob);
}

export function incidentErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "로그인이 만료되었습니다. 다시 로그인해 주세요.";
    }

    if (error.status === 403) {
      return "이 작업을 수행할 권한이 없습니다.";
    }

    if (error.status === 404) {
      return "사건이 없거나 조회 권한이 없습니다.";
    }

    if (error.status === 409) {
      return "사건 상태가 변경됐습니다. 다시 조회해 주세요.";
    }

    if (error.status === 422) {
      return "검색 조건이나 입력값을 확인해 주세요.";
    }
  }

  return "서버 조회에 실패했습니다. 연결 상태를 확인한 뒤 다시 조회해 주세요.";
}

// DB에는 UTC로 저장되며, 화면 표시는 한국시간으로 변환합니다.
export function formatSeoulTime(value: string): string {
  const timestamp = new Date(value);

  if (Number.isNaN(timestamp.getTime())) {
    return "시각 확인 필요";
  }

  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(timestamp);
}
