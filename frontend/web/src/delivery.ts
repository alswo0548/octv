/**
 * WEB 기관 전달 연결: 기존 로그인 세션 주입 → 본인·실제 사건 재확인 → 추천 조회
 * → 선택 기관 전달 → DB 저장 결과와 Push 작업 등록 결과를 구분해 표시합니다.
 *
 * 인증·사건 화면 담당 연결 지점
 * - 로그인 복원과 실제 사건 선택이 끝나면 setDeliveryContext({ user, api, incidentId }).
 * - api는 기존 createApi로 만들되, 해당 세션의 고정 JWT를 읽는 함수를 전달합니다.
 * - 로그아웃·계정/토큰·사건 변경 전에는 setDeliveryContext(null)로 먼저 해제합니다.
 * - 매 렌더링마다 설정하지 말고 세션 또는 실제 선택 사건이 바뀔 때만 설정합니다.
 *
 * 이 파일은 로그인·JWT 저장을 구현하지 않으며 mock 사건번호를 DB ID로 바꾸지 않습니다.
 * /sent 호출·사건 자동 확인·전달 POST 자동 재시도도 하지 않습니다.
 */
import type { createApi } from "./api";

export type DeliveryContextInput = {
  user: { id: number; role: string; is_active: boolean };
  api: ReturnType<typeof createApi>;
  incidentId: number;
};
export type DeliveryContext = Readonly<{
  version: number;
  userId: number;
  incidentId: number;
}>;
export type DeliveryIncident = Readonly<{
  id: number;
  priority?: string | null;
  incident_no: string;
  cctv_name: string;
  hazard_type: string;
  status: string;
}>;
export type DeliveryRoute = Readonly<{
  id: number;
  route_name: string;
  distance_m: number;
  duration_sec: number;
  total_score: number | null;
  disqualify_reason: string | null;
}>;
export type DeliveryCandidate = Readonly<{
  agency_id: number;
  agency_name: string;
  agency_type: string;
  recommendation_rank: number;
  recommendation_status: "RECOMMENDED" | "DELIVERED" | "COMPLETED";
  routes: readonly DeliveryRoute[];
}>;
export type DeliverySnapshot = Readonly<{
  incident: DeliveryIncident;
  candidates: readonly DeliveryCandidate[];
}>;
export type DeliverySelection = {
  agency_id: number;
  route_candidate_id?: number | null;
};
export type PushStatus =
  | "NOT_QUEUED"
  | "QUEUED"
  | "PARTIALLY_QUEUED"
  | "QUEUE_UNCONFIRMED"
  | "DISABLED"
  | "NO_NEW_NOTIFICATIONS";
export type DeliveryResult = Readonly<{
  incident_id: number;
  incident_status: "CONFIRMED" | "SENT";
  items: readonly Readonly<{
    agency_id: number;
    agency_recommendation_id: number;
    status: "DELIVERED" | "COMPLETED";
    newly_delivered: boolean;
    created_notification_count: number;
  }>[];
  created_notification_count: number;
  push_status: PushStatus;
}>;

const messages = {
  NO_CONTEXT: "실제 로그인 정보와 서버 사건이 연결되어야 전달할 수 있습니다.",
  INVALID_CONTEXT: "서버에서 확인한 사용자와 실제 사건 ID를 연결해 주세요.",
  FORBIDDEN: "활성 관제 관리자 계정으로만 기관을 전달할 수 있습니다.",
  SESSION_CHANGED: "로그인 또는 선택 사건이 바뀌었습니다. 다시 조회해 주세요.",
  AUTH_REQUIRED: "로그인을 확인한 뒤 다시 조회해 주세요.",
  NOT_FOUND: "서버에서 해당 사건을 찾을 수 없습니다.",
  STATE_CHANGED:
    "사건 상태가 바뀌었거나 아직 확인되지 않았습니다. 다시 조회해 주세요.",
  INVALID_SELECTION: "현재 추천 목록의 기관과 유효한 경로를 선택해 주세요.",
  BUSY: "기관 전달 결과를 확인하고 있습니다.",
  STALE_SNAPSHOT: "기관 전달 상태를 다시 조회한 뒤 선택해 주세요.",
  INVALID_RESPONSE: "서버 응답을 확인할 수 없습니다. 다시 조회해 주세요.",
  LOAD_FAILED:
    "서버 정보를 불러오지 못했습니다. 연결을 확인하고 다시 조회해 주세요.",
  DELIVERY_UNCONFIRMED:
    "전달 결과 확인이 필요합니다. 기관 전달 상태를 다시 조회해 주세요.",
} as const;

// 화면에 비밀값이 섞인 원문 예외를 출력하지 않고 확인 가능한 상태만 전달합니다.
export class DeliveryError extends Error {
  code: keyof typeof messages;
  constructor(code: keyof typeof messages) {
    super(messages[code]);
    this.name = "DeliveryError";
    this.code = code;
  }
}

type Session = {
  context: DeliveryContext;
  api: DeliveryContextInput["api"];
  controller: AbortController;
  submitting: boolean;
};
let current: Session | null = null;
let version = 0;
const listeners = new Set<() => void>();
const snapshots = new WeakMap<
  DeliverySnapshot,
  { session: Session; attempted: boolean }
>();

// JS에서 정밀도를 보장할 수 없는 BIGINT나 SEL-001 같은 화면 문자열을 거부합니다.
const isId = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value > 0;
const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

// 이전 세션의 조회·전달 결과가 새 사용자나 다른 사건 화면에 나타나지 않게 해제합니다.
export function setDeliveryContext(input: DeliveryContextInput | null): void {
  current?.controller.abort();
  current = null;
  version += 1;
  try {
    if (input === null) return;
    if (
      !input ||
      !isId(input.incidentId) ||
      !isId(input.user?.id) ||
      typeof input.api !== "function"
    ) {
      throw new DeliveryError("INVALID_CONTEXT");
    }
    if (input.user.role !== "CONTROL_ADMIN" || input.user.is_active !== true) {
      throw new DeliveryError("FORBIDDEN");
    }
    current = {
      context: Object.freeze({
        version,
        userId: input.user.id,
        incidentId: input.incidentId,
      }),
      api: input.api,
      controller: new AbortController(),
      submitting: false,
    };
  } finally {
    listeners.forEach((listener) => listener());
  }
}

// React 외부 상태 구독에는 같은 연결 동안 같은 객체를 반환합니다. JWT는 노출하지 않습니다.
export function getDeliveryContext(): DeliveryContext | null {
  return current?.context ?? null;
}

// 기관 선택 창이 로그인·사건 연결 변경을 즉시 반영할 수 있도록 구독을 연결합니다.
export function subscribeDeliveryContext(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

// API 응답이 늦게 돌아와도 현재 세션과 다르면 결과를 사용하지 않습니다.
function assertCurrent(session: Session): void {
  if (session !== current || session.controller.signal.aborted) {
    throw new DeliveryError("SESSION_CHANGED");
  }
}

// 호출 시점과 응답 시점 모두 연결을 검사하며, 자동 재시도 없이 API를 한 번 호출합니다.
async function request<T>(
  session: Session,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  assertCurrent(session);
  try {
    const result = await session.api<T>(path, {
      ...options,
      signal: session.controller.signal,
    });
    assertCurrent(session);
    return result;
  } catch (error) {
    assertCurrent(session);
    throw error;
  }
}

// 주입된 화면 역할만 믿지 않고 JWT의 본인 정보와 동일한 활성 관리자임을 확인합니다.
async function verifyAdmin(session: Session): Promise<void> {
  const user = await request<unknown>(session, "/api/auth/me");
  if (!isRecord(user) || user.id !== session.context.userId) {
    throw new DeliveryError("SESSION_CHANGED");
  }
  if (user.role !== "CONTROL_ADMIN" || user.is_active !== true) {
    throw new DeliveryError("FORBIDDEN");
  }
}

// HTTP 오류의 의미만 보존합니다. POST의 통신 실패는 DB 저장 여부가 미확인일 수 있습니다.
function asDeliveryError(error: unknown, posted = false): DeliveryError {
  if (error instanceof DeliveryError) return error;
  const status = isRecord(error) ? error.status : undefined;
  if (status === 401) return new DeliveryError("AUTH_REQUIRED");
  if (status === 403) return new DeliveryError("FORBIDDEN");
  if (status === 404) return new DeliveryError("NOT_FOUND");
  if (status === 409) return new DeliveryError("STATE_CHANGED");
  if (status === 422) return new DeliveryError("INVALID_SELECTION");
  return new DeliveryError(posted ? "DELIVERY_UNCONFIRMED" : "LOAD_FAILED");
}

// 서버의 사건·기관·경로를 확인하고, 실제 모달에서 필요한 값만 보관합니다.
function parseSnapshot(
  incident: unknown,
  response: unknown,
  incidentId: number,
): DeliverySnapshot {
  if (
    !isRecord(incident) ||
    incident.id !== incidentId ||
    !isText(incident.incident_no) ||
    !isText(incident.cctv_name) ||
    !isText(incident.hazard_type) ||
    !isText(incident.status) ||
    !isRecord(response) ||
    response.incident_id !== incidentId ||
    !Array.isArray(response.items)
  ) {
    throw new DeliveryError("INVALID_RESPONSE");
  }
  if (incident.status !== response.incident_status)
    throw new DeliveryError("STATE_CHANGED");
  const agencyIds = new Set<number>();
  const candidates = response.items.map((item: unknown): DeliveryCandidate => {
    if (
      !isRecord(item) ||
      !isId(item.agency_id) ||
      agencyIds.has(item.agency_id) ||
      !isText(item.agency_name) ||
      !isText(item.agency_type) ||
      !isId(item.recommendation_rank) ||
      !["RECOMMENDED", "DELIVERED", "COMPLETED"].includes(
        String(item.recommendation_status),
      ) ||
      !Array.isArray(item.routes)
    )
      throw new DeliveryError("INVALID_RESPONSE");
    agencyIds.add(item.agency_id);
    const routeIds = new Set<number>();
    const routes = item.routes.map((route: unknown): DeliveryRoute => {
      if (
        !isRecord(route) ||
        !isId(route.id) ||
        routeIds.has(route.id) ||
        !isText(route.route_name) ||
        !isCount(route.distance_m) ||
        !isCount(route.duration_sec) ||
        !(
          route.total_score === null ||
          (typeof route.total_score === "number" &&
            Number.isFinite(route.total_score))
        ) ||
        !(
          route.disqualify_reason === null ||
          typeof route.disqualify_reason === "string"
        )
      ) {
        throw new DeliveryError("INVALID_RESPONSE");
      }
      routeIds.add(route.id);
      return Object.freeze({
        id: route.id,
        route_name: route.route_name,
        distance_m: route.distance_m,
        duration_sec: route.duration_sec,
        total_score: route.total_score,
        disqualify_reason: route.disqualify_reason,
      });
    });
    return Object.freeze({
      agency_id: item.agency_id,
      agency_name: item.agency_name,
      agency_type: item.agency_type,
      recommendation_rank: item.recommendation_rank,
      recommendation_status:
        item.recommendation_status as DeliveryCandidate["recommendation_status"],
      routes: Object.freeze(routes),
    });
  });
  return Object.freeze({
    incident: Object.freeze({
      id: incidentId,
      priority: typeof incident.priority === "string" ? incident.priority : null,
      incident_no: incident.incident_no,
      cctv_name: incident.cctv_name,
      hazard_type: incident.hazard_type,
      status: incident.status,
    }),
    candidates: Object.freeze(candidates),
  });
}

// 실제 사건 상세와 기존 추천 API를 조회합니다. 샘플 자료나 /routes의 미구현 API는 사용하지 않습니다.
export async function loadDeliverySnapshot(
  expectedVersion?: number,
): Promise<DeliverySnapshot> {
  const session = current;
  if (!session) throw new DeliveryError("NO_CONTEXT");
  if (
    expectedVersion !== undefined &&
    session.context.version !== expectedVersion
  ) {
    throw new DeliveryError("SESSION_CHANGED");
  }
  try {
    await verifyAdmin(session);
    const id = session.context.incidentId;
    const [incident, candidates] = await Promise.all([
      request<unknown>(session, `/api/incidents/${id}`),
      request<unknown>(
        session,
        `/api/agencies/incidents/${id}/recommendations`,
      ),
    ]);
    assertCurrent(session);
    const snapshot = parseSnapshot(incident, candidates, id);
    snapshots.set(snapshot, { session, attempted: false });
    return snapshot;
  } catch (error) {
    throw asDeliveryError(error);
  }
}

// 사용자가 체크한 실제 추천 기관만 직렬화하며, 경로 조회를 자동 선택으로 해석하지 않습니다.
function validateSelections(
  snapshot: DeliverySnapshot,
  selections: readonly DeliverySelection[],
): DeliverySelection[] {
  if (!Array.isArray(selections) || !selections.length)
    throw new DeliveryError("INVALID_SELECTION");
  const selected = new Set<number>();
  return selections.map((item) => {
    if (
      !isRecord(item) ||
      !isId(item.agency_id) ||
      selected.has(item.agency_id) ||
      Object.keys(item).some(
        (key) => !["agency_id", "route_candidate_id"].includes(key),
      )
    ) {
      throw new DeliveryError("INVALID_SELECTION");
    }
    const candidate = snapshot.candidates.find(
      (value) => value.agency_id === item.agency_id,
    );
    if (!candidate || candidate.recommendation_status !== "RECOMMENDED") {
      throw new DeliveryError("INVALID_SELECTION");
    }
    selected.add(item.agency_id);
    if (item.route_candidate_id == null) return { agency_id: item.agency_id };
    if (
      !isId(item.route_candidate_id) ||
      !candidate.routes.some(
        (route) =>
          route.id === item.route_candidate_id &&
          route.disqualify_reason === null,
      )
    ) {
      throw new DeliveryError("INVALID_SELECTION");
    }
    return {
      agency_id: item.agency_id,
      route_candidate_id: item.route_candidate_id,
    };
  });
}

// 큐 등록 상태는 휴대폰 수신 결과가 아닙니다. 서버에서 반환한 DB 전달 결과와 구분합니다.
export const pushStatusLabels: Readonly<Record<PushStatus, string>> =
  Object.freeze({
    NOT_QUEUED: "푸시 작업 등록 전",
    QUEUED: "푸시 발송 작업 등록 완료",
    PARTIALLY_QUEUED: "일부 푸시 작업 등록 확인 필요",
    QUEUE_UNCONFIRMED: "푸시 작업 등록 여부 확인 필요",
    DISABLED: "서버 푸시 기능 꺼짐",
    NO_NEW_NOTIFICATIONS: "새로 생성된 앱 내 알림 없음",
  });

// 다른 사건·기관 응답이나 잘못된 알림 개수를 전달 성공으로 표시하지 않습니다.
function parseResult(
  value: unknown,
  incidentId: number,
  selections: readonly DeliverySelection[],
): DeliveryResult {
  if (
    !isRecord(value) ||
    value.incident_id !== incidentId ||
    !["CONFIRMED", "SENT"].includes(String(value.incident_status)) ||
    !Array.isArray(value.items) ||
    value.items.length !== selections.length ||
    !isCount(value.created_notification_count) ||
    typeof value.push_status !== "string" ||
    !Object.hasOwn(pushStatusLabels, value.push_status)
  ) {
    throw new DeliveryError("DELIVERY_UNCONFIRMED");
  }
  const remaining = new Set(selections.map((selection) => selection.agency_id));
  let count = 0;
  const items = value.items.map((item: unknown) => {
    if (
      !isRecord(item) ||
      !isId(item.agency_id) ||
      !remaining.delete(item.agency_id) ||
      !isId(item.agency_recommendation_id) ||
      !["DELIVERED", "COMPLETED"].includes(String(item.status)) ||
      typeof item.newly_delivered !== "boolean" ||
      !isCount(item.created_notification_count) ||
      (item.newly_delivered && item.status !== "DELIVERED") ||
      (!item.newly_delivered && item.created_notification_count !== 0)
    ) {
      throw new DeliveryError("DELIVERY_UNCONFIRMED");
    }
    count += item.created_notification_count;
    return Object.freeze({
      agency_id: item.agency_id,
      agency_recommendation_id: item.agency_recommendation_id,
      status: item.status as "DELIVERED" | "COMPLETED",
      newly_delivered: item.newly_delivered,
      created_notification_count: item.created_notification_count,
    });
  });
  if (count !== value.created_notification_count)
    throw new DeliveryError("DELIVERY_UNCONFIRMED");
  return Object.freeze({
    incident_id: incidentId,
    incident_status: value.incident_status as "CONFIRMED" | "SENT",
    items: Object.freeze(items),
    created_notification_count: count,
    push_status: value.push_status as PushStatus,
  });
}

// 전달 직전 인증을 재확인하고 POST를 한 번만 수행합니다. 결과 미확인 시 먼저 다시 조회해야 합니다.
export async function deliverToAgencies(
  snapshot: DeliverySnapshot,
  selections: readonly DeliverySelection[],
): Promise<DeliveryResult> {
  const session = current;
  if (!session) throw new DeliveryError("NO_CONTEXT");
  const record = snapshots.get(snapshot);
  if (!record || record.session !== session)
    throw new DeliveryError("STALE_SNAPSHOT");
  if (session.submitting) throw new DeliveryError("BUSY");
  if (record.attempted) throw new DeliveryError("STALE_SNAPSHOT");
  if (!["CONFIRMED", "SENT"].includes(snapshot.incident.status))
    throw new DeliveryError("STATE_CHANGED");
  const validated = validateSelections(snapshot, selections);
  session.submitting = true;
  let posted = false;
  try {
    await verifyAdmin(session);
    assertCurrent(session);
    // 응답이 유실되어도 같은 조회 결과로 연속 전송하지 않도록 POST 직전에 소비 처리합니다.
    record.attempted = true;
    posted = true;
    const result = await request<unknown>(
      session,
      `/api/agencies/incidents/${session.context.incidentId}/deliveries`,
      { method: "POST", body: JSON.stringify({ selections: validated }) },
    );
    return parseResult(result, session.context.incidentId, validated);
  } catch (error) {
    throw asDeliveryError(error, posted);
  } finally {
    session.submitting = false;
  }
}

// 사용자에게 보여줄 오류는 안전한 설명만 사용하며 API 원문·JWT를 표시하지 않습니다.
export function deliveryErrorMessage(error: unknown): string {
  return error instanceof DeliveryError ? error.message : messages.LOAD_FAILED;
}
