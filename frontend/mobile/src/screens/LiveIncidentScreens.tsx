/**
 * 후속-04 모바일 실사건 목록: 기존 /api/incidents를 기관 JWT로 조회하여 보여줍니다.
 * 화면의 카드 배치·스타일을 재사용하며 샘플 사건을 실제 데이터로 대신 표시하지 않습니다.
 * 로그인·계정 변경 후 이전 서버 응답이 새 계정 화면에 섞이지 않도록 현재 API를 비교합니다.
 * 경로·지원 요청 연결을 유지하며 재난 유형은 웹과 같은 표시 계약을 사용합니다.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { View, Text, Pressable, ActivityIndicator } from "react-native";
import { hazardLabel, type IncidentDto, type PageDto } from "@octv/shared";
import { ApiError } from "../api";
import { mobileSession } from "../mobileSession";
import type { Navigate } from "../navigation/types";
import { Badge, T, Link, Button } from "../components/UI";
import { s, color } from "../styles/theme";

type ListData = {
  ownerApi: NonNullable<ReturnType<typeof mobileSession.getSnapshot>["api"]>;
  requestedPage: number;
  page: PageDto<IncidentDto>;
};
function localTime(utc: string): string {
  const date = new Date(utc);
  return Number.isNaN(date.getTime())
    ? "시각 확인 불가"
    : date.toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

// 기존 사건 카드의 시각 표현을 유지하고 조회 결과의 실제 사건 ID만 상세에 전달합니다.
function LiveIncidentCard({
  incident,
  open,
}: {
  incident: IncidentDto;
  open: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${incident.incident_no} 사건 상세`}
      onPress={open}
      style={({ pressed }) => [
        s.panel,
        {
          backgroundColor: pressed ? "#1a3345" : "rgba(14,28,40,.75)",
          marginTop: 12,
          marginBottom: 0,
        },
      ]}
    >
      <View style={s.row}>
        <Badge priority={incident.priority ?? "평가 대기"} />
        <Text style={[s.muted, { color: "#b9d1df" }]}>● 전달받은 사건</Text>
      </View>
      <Text style={[s.h2, { marginTop: 15, marginBottom: 4 }]}>
        {hazardLabel(incident.hazard_type)} · {incident.incident_no}
      </Text>
      <T muted>{incident.cctv_name}</T>
      <View
        style={[
          s.row,
          {
            borderTopWidth: 1,
            borderColor: color.line,
            paddingTop: 13,
            marginTop: 14,
          },
        ]}
      >
        <T muted>{localTime(incident.detected_at)} 탐지</T>
        <T muted>
          {incident.analysis_status === "READY"
            ? `위험도 ${incident.risk_level ?? "확인 필요"}`
            : "분석 대기"}
        </T>
      </View>
    </Pressable>
  );
}

export function LiveIncidentScreens({
  home = false,
  go,
}: {
  home?: boolean;
  go: Navigate;
}) {
  const session = useSyncExternalStore(
    mobileSession.subscribe,
    mobileSession.getSnapshot,
    mobileSession.getSnapshot,
  );
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [result, setResult] = useState<ListData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const limit = home ? 5 : 20;
  const api = session.status === "ready" ? session.api : null;
  const requestedPage = home ? 1 : page;
  const data =
    result?.ownerApi === api && result.requestedPage === requestedPage
      ? result.page
      : null;

  useEffect(() => {
    setPage(1);
  }, [api, home]);
  useEffect(() => {
    if (!api) return;
    let active = true;
    const requester = api;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const response = await requester<PageDto<IncidentDto>>(
          `/api/incidents?page=${requestedPage}&page_size=${limit}`,
        );
        if (
          !response ||
          !Array.isArray(response.items) ||
          typeof response.total !== "number" ||
          response.items.some(
            (item) => !Number.isSafeInteger(item.id) || item.id <= 0,
          )
        ) {
          throw new Error("INVALID_INCIDENT_RESPONSE");
        }
        if (active && mobileSession.getSnapshot().api === requester) {
          setResult({ ownerApi: requester, requestedPage, page: response });
        }
      } catch (caught) {
        if (!active || mobileSession.getSnapshot().api !== requester) return;
        setResult(null);
        if (caught instanceof ApiError && caught.status === 401) {
          void mobileSession.invalidate(requester);
        } else {
          setError("실제 사건 목록을 불러오지 못했습니다. 다시 조회해주세요.");
        }
      } finally {
        if (active && mobileSession.getSnapshot().api === requester)
          setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [api, home, requestedPage, limit, reload]);

  if (!api)
    return <T>로그인 후 소속기관에 전달된 사건을 조회할 수 있습니다.</T>;
  return (
    <>
      <View style={[s.row, { justifyContent: "space-between" }]}>
        <Text style={s.h2}>{home ? "우선 확인 사건" : "전달받은 사건"}</Text>
        <Link
          onPress={() => {
            if (home) go("incidents");
            else setReload((value) => value + 1);
          }}
        >
          {home ? "사건 목록" : "새로고침"}
        </Link>
      </View>
      {loading && <ActivityIndicator color={color.cyan} />}
      {error && (
        <View style={s.info}>
          <T>{error}</T>
        </View>
      )}
      {!loading && data && data.items.length === 0 && (
        <View style={s.panel}>
          <T>소속기관에 전달된 사건이 없습니다.</T>
        </View>
      )}
      {data?.items.map((incident) => (
        <LiveIncidentCard
          key={incident.id}
          incident={incident}
          open={() => go("detail", String(incident.id))}
        />
      ))}
      {!home && data && (
        <View style={{ marginTop: 16 }}>
          <T muted>
            총 {data.total}건 · {page}페이지
          </T>
          <View style={[s.row, { marginTop: 10, gap: 8 }]}>
            <View style={{ flex: 1 }}>
              <Button
                secondary
                disabled={page <= 1 || loading}
                onPress={() => setPage((n) => Math.max(1, n - 1))}
              >
                이전
              </Button>
            </View>
            <View style={{ flex: 1 }}>
              <Button
                secondary
                disabled={page * limit >= data.total || loading}
                onPress={() => setPage((n) => n + 1)}
              >
                다음
              </Button>
            </View>
          </View>
        </View>
      )}
      <Text style={[s.muted, { marginTop: 20, fontSize: 12 }]}>
        출동 여부는 기관의 기존 체계에서 결정합니다.
      </Text>
    </>
  );
}
