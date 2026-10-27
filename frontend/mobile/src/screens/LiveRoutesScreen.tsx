/**
 * 후속-05 실제 모바일 경로: 인증된 사용자의 기관 ID로 기존 경로 API만 조회.
 * DB 저장 후보 0~N개를 정확히 표시하며 서버에서 내려온 검증 상태·제외 사유를 유지합니다.
 * NEEDS_REVIEW는 추가 확인 경고, DISQUALIFIED는 내비 실행을 제한합니다.
 * 카카오내비에는 사건 목적지 좌표만 전달하고 OCTV 검증 경로와 같다고 주장하지 않습니다.
 */
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { View, Text, Pressable, ActivityIndicator } from "react-native";
import type { IncidentDto } from "@octv/shared";
import { s, color } from "../styles/theme";
import { Button, T, type ShowDialog } from "../components/UI";
import { mobileSession } from "../mobileSession";
import { ApiError } from "../api";
import {
  loadMyAgencyRoutes,
  validLine,
  validDestination,
  type RouteResponse,
} from "../liveRoutes";
import { LiveRouteMap } from "../components/LiveRouteMap";
import { openKakaoNavi } from "../kakaoNavi";
import type { Navigate } from "../navigation/types";
import { incidentDisplayNo } from "../incidentLabel";

function resultMessage(status: RouteResponse["result_status"]): string {
  switch (status) {
    case "NOT_ANALYZED":
      return "아직 LangGraph 분석이 저장되지 않았습니다.";
    case "NO_RECOMMENDATION":
      return "현재 기관의 추천 기록이 없습니다.";
    case "NO_ROUTES":
      return "저장된 경로가 없습니다.";
    case "ALL_DISQUALIFIED":
      return "모든 후보가 제외되었습니다. 내비 안내를 실행할 수 없습니다.";
    case "NEEDS_REVIEW":
      return "추가 확인이 필요한 경로만 있습니다.";
    case "AVAILABLE":
      return "저장된 후보를 비교하고 도로 통제 여부를 확인하세요.";
  }
}

export function LiveRoutesScreen({
  incident,
  show,
  go,
}: {
  incident: IncidentDto;
  show: ShowDialog;
  go: Navigate;
}) {
  const session = useSyncExternalStore(
    mobileSession.subscribe,
    mobileSession.getSnapshot,
    mobileSession.getSnapshot,
  );
  const [result, setResult] = useState<{
    api: typeof session.api;
    data: RouteResponse;
  } | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const api = session.status === "ready" ? session.api : null;
  const data =
    result?.api === api && result.data.incident_id === incident.id
      ? result.data
      : null;

  // 실제 기관과 사건이 바뀐 경우 이전 경로를 즉시 화면에서 제거합니다.
  useEffect(() => {
    if (!api) return;
    let alive = true;
    const owner = api;
    setLoading(true);
    setError(null);
    setResult(null);
    setSelected(null);
    void loadMyAgencyRoutes(incident.id)
      .then((response) => {
        if (!alive || mobileSession.getSnapshot().api !== owner) return;
        setResult({ api: owner, data: response });
        setSelected(response.items[0]?.id ?? null);
      })
      .catch((caught) => {
        if (!alive || mobileSession.getSnapshot().api !== owner) return;
        if (caught instanceof ApiError && [403, 404].includes(caught.status))
          setError(
            "이 사건의 경로 조회 권한이 없거나 기관에 전달되지 않았습니다.",
          );
        else
          setError(
            "경로를 조회하지 못했습니다. 연결 상태를 확인하고 다시 시도해주세요.",
          );
      })
      .finally(() => {
        if (alive && mobileSession.getSnapshot().api === owner)
          setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [incident.id, api, refresh]);

  const route = data?.items.find((item) => item.id === selected) ?? null;
  const lines = useMemo(
    () =>
      data?.items.flatMap((item) => {
        const coords = validLine(item.route_path_json);
        return coords ? [{ id: item.id, coords }] : [];
      }) ?? [],
    [data],
  );
  const destination = validDestination(incident)
    ? ([incident.longitude, incident.latitude] as const)
    : null;
  const blocked =
    !route ||
    route.disqualify_reason !== null ||
    route.verification_status === "DISQUALIFIED" ||
    !route.navigation_available ||
    !validLine(route.route_path_json) ||
    !destination;

  const confirmNavi = () => {
    if (blocked || !route || busy) return;
    const needsReview =
      route.verification_status !== "VERIFIED" || route.requires_review;
    show({
      title: needsReview ? "도로 통제·안전 확인 필요" : "카카오내비 안내",
      body: `${needsReview ? "선택 경로는 도로 통제·안전 확인이 필요합니다. " : ""}카카오내비로 연동하시겠습니까?`,
      confirm: "카카오내비 열기",
      onConfirm: () => {
        setBusy(true);
        void openKakaoNavi(incident)
          .then((status) => {
            if (status === "not-configured")
              show({
                title: "설정 대기",
                body: "카카오 네이티브 앱 키 설정과 Android APK 재빌드가 필요합니다.",
                confirm: "확인",
                cancel: false,
              });
            if (status === "install")
              show({
                title: "카카오내비 설치",
                body: "카카오내비가 없어 설치 페이지를 열었습니다. 설치 후 다시 시도해주세요.",
                confirm: "확인",
                cancel: false,
              });
            if (status === "unsupported")
              show({
                title: "지원 기기",
                body: "Android 설치 앱에서만 카카오내비를 실행합니다.",
                confirm: "확인",
                cancel: false,
              });
          })
          .catch(() =>
            show({
              title: "내비 연결 실패",
              body: "카카오내비 실행을 확인하지 못했습니다. 설치·앱키·네트워크를 확인해주세요.",
              confirm: "확인",
              cancel: false,
            }),
          )
          .finally(() => setBusy(false));
      },
    });
  };
  if (!api) return <T>로그인 후 본인 기관의 경로를 확인할 수 있습니다.</T>;
  return (
    <>
      <View style={s.info}>
        <T>
          사건 {incidentDisplayNo(incident)} · {incident.cctv_name}
        </T>
        <T muted>
          현재 기관: {session.user?.agency_name ?? "소속기관 확인 필요"}
        </T>
      </View>
      <View
        style={[s.row, { justifyContent: "space-between", marginBottom: 14 }]}
      >
        <Text style={s.h2}>기관별 저장 경로</Text>
        <Button secondary onPress={() => setRefresh((n) => n + 1)}>
          새로고침
        </Button>
      </View>
      {loading && <ActivityIndicator color={color.cyan} />}
      {error && (
        <View style={s.info}>
          <T>{error}</T>
        </View>
      )}
      {data && (
        <>
          <T muted>{resultMessage(data.result_status)}</T>
          {lines.length > 0 && (
            <View style={{ marginTop: 12 }}>
              <LiveRouteMap
                lines={lines}
                selectedId={selected}
                destination={destination}
              />
            </View>
          )}
          {data.items.map((item) => {
            const isExcluded =
              item.disqualify_reason !== null ||
              item.verification_status === "DISQUALIFIED";
            const path = validLine(item.route_path_json);
            return (
              <Pressable
                key={item.id}
                accessibilityRole="button"
                accessibilityLabel={`저장된 경로 ${item.route_name}`}
                onPress={() => setSelected(item.id)}
                style={[
                  s.panel,
                  {
                    marginTop: 10,
                    borderColor: selected === item.id ? color.cyan : color.line,
                    opacity: isExcluded ? 0.75 : 1,
                  },
                ]}
              >
                <View style={[s.row, { justifyContent: "space-between" }]}>
                  <Text style={s.h2}>{item.route_name}</Text>
                  <T muted>
                    {isExcluded
                      ? "제외"
                      : item.verification_status === "VERIFIED"
                        ? "검증 기준 충족"
                        : "추가 확인"}
                  </T>
                </View>
                <T>
                  {(item.distance_m / 1000).toFixed(1)} km ·{" "}
                  {(item.duration_sec / 60).toFixed(1)}분 · 점수{" "}
                  {item.total_score ?? "없음"}
                </T>
                {item.disqualify_reason && (
                  <T muted>제외 사유: {item.disqualify_reason}</T>
                )}
                {!path && (
                  <T muted>경로 좌표 없음·형식 오류 (지도/내비 제한)</T>
                )}
                {!isExcluded && item.requires_review && (
                  <T muted>도로 통제·안전 추가 확인 필요</T>
                )}
              </Pressable>
            );
          })}
          <Button disabled={!!blocked || busy} onPress={confirmNavi}>
            {busy
              ? "카카오내비 연결 중…"
              : "카카오내비로 연동하기 ↗"}
          </Button>

        </>
      )}
      <Button secondary onPress={() => go("detail")}>
        사건 상세로 돌아가기
      </Button>
    </>
  );
}
