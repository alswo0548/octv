/**
 * 후속-05 모바일 경로 조회: 기존 JWT API와 /api/routes 조회만 사용합니다.
 * 기관 ID는 사용자 입력을 받지 않고 인증 세션에서 가져옵니다.
 * 실제 데이터 없는 경우 빈 경로로 반환하며 샘플 경로를 대신 보여주지 않습니다.
 */
import type { IncidentDto } from "@octv/shared";
import { mobileSession } from "./mobileSession";
import { ApiError } from "./api";

export type VerificationStatus = "VERIFIED" | "NEEDS_REVIEW" | "DISQUALIFIED" | null;
export type StoredRoute = {
  id: number;
  route_name: string;
  distance_m: number;
  duration_sec: number;
  total_score: number | null;
  score_breakdown_json: Record<string, unknown> | null;
  disqualify_reason: string | null;
  route_path_json: unknown;
  rule_version: string;
  verification_status: VerificationStatus;
  requires_review: boolean;
  navigation_available: boolean;
};
export type RouteResponse = {
  incident_id: number;
  agency_id: number;
  analysis_status: "PENDING" | "READY";
  recommendation_status: "RECOMMENDED" | "DELIVERED" | "COMPLETED" | null;
  result_status: "NOT_ANALYZED" | "NO_RECOMMENDATION" | "NO_ROUTES" |
    "ALL_DISQUALIFIED" | "NEEDS_REVIEW" | "AVAILABLE";
  items: StoredRoute[];
};
export type Point = readonly [number, number];
export function validLine(value: unknown): Point[] | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (v.type !== "LineString" || !Array.isArray(v.coordinates)) return null;
  if (v.coordinates.length < 2 || v.coordinates.length > 30000) return null;
  const points: Point[] = [];
  for (const coordinate of v.coordinates) {
    if (!Array.isArray(coordinate) || coordinate.length < 2) return null;
    const [lon, lat] = coordinate;
    if (typeof lon !== "number" || typeof lat !== "number" ||
        !Number.isFinite(lon) || !Number.isFinite(lat) ||
        Math.abs(lon) > 180 || Math.abs(lat) > 85.05112878) return null;
    points.push([lon, lat]);
  }
  return points;
}
export function validDestination(incident: IncidentDto): boolean {
  return Number.isFinite(incident.latitude) && Number.isFinite(incident.longitude) &&
    Math.abs(incident.latitude) <= 85.05112878 && Math.abs(incident.longitude) <= 180;
}
export async function loadMyAgencyRoutes(incidentId: number): Promise<RouteResponse> {
  const session = mobileSession.getSnapshot();
  const agencyId = session.user?.agency_id;
  const api = session.api;
  if (!api || session.status !== "ready" || !agencyId || !Number.isSafeInteger(agencyId))
    throw new Error("기관 로그인 정보를 확인할 수 없습니다.");
  if (!Number.isSafeInteger(incidentId) || incidentId <= 0)
    throw new Error("실제 사건 ID가 필요합니다.");
  try {
    const response = await api<RouteResponse>(
      `/api/routes/incidents/${incidentId}/agencies/${agencyId}`,
    );
    if (mobileSession.getSnapshot().api !== api)
      throw new Error("로그인 계정이 변경됐습니다.");
    if (!response || response.incident_id !== incidentId ||
        response.agency_id !== agencyId || !Array.isArray(response.items) ||
        response.items.some((route) => !Number.isSafeInteger(route.id)))
      throw new Error("실제 경로 응답을 확인할 수 없습니다.");
    return response;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401)
      await mobileSession.invalidate(api);
    throw error;
  }
}
