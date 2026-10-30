/** 카카오내비는 사건 목적지 좌표로 자체 경로를 계산합니다.
 * 저장된 GeoJSON 선형 경로는 OCTV 지도 표시용이며 카카오내비 실행 필수값이 아닙니다.
 * 단, 제외된 경로 및 검증되지 않은 경로는 기존 정책대로 열 수 없습니다.
 */
import type { StoredRoute } from "./liveRoutes";

export function canOpenKakaoNavi(
  route: Pick<StoredRoute, "disqualify_reason" | "verification_status"> | null,
  validDestination: boolean,
): boolean {
  return Boolean(
    validDestination &&
      route &&
      route.disqualify_reason === null &&
      (route.verification_status === "VERIFIED" ||
        route.verification_status === "NEEDS_REVIEW"),
  );
}
