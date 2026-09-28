import { useState } from "react";
import { View, Text, Pressable } from "react-native";
import { mock, routesFor, type Incident } from "@octv/shared";
import { RoadMap } from "../components/RoadMap";
import { T, Button, type ShowDialog } from "../components/UI";
import { s, color } from "../styles/theme";
export function RoutesScreen({
  incident: d,
  show,
}: {
  incident: Incident;
  show: ShowDialog;
}) {
  const routes = routesFor(d.id, mock.profile.agencyId);
  const [active, set] = useState(routes[0].id);
  const selected = routes.find((route) => route.id === active);
  return (
    <>
      <View style={s.info}>
        <T>수신·출발 기관 · {mock.profile.agency}</T>
        <T>
          → {d.location} · {d.id}
        </T>
        <T muted>
          위험도 {d.risk} · 대응 우선순위 {d.priority} ({d.score}점)
        </T>
      </View>
      <RoadMap active={active} choose={set} />
      <Text style={[s.muted, { marginVertical: 12, fontSize: 12 }]}>
        기관 기준 경로 3개 · 지도 강조 {active}
      </Text>
      {routes.map((r) => (
        <Pressable
          key={r.id}
          accessibilityRole="button"
          accessibilityLabel={"경로 " + r.id + " 확인"}
          onPress={() => set(r.id)}
          style={[
            s.panel,
            {
              marginBottom: 8,
              paddingVertical: 9,
              paddingHorizontal: 12,
              borderColor: active === r.id ? "#75cadb" : color.line,
              backgroundColor: active === r.id ? "#1d4b6055" : color.panel,
              opacity: r.blocked ? 0.8 : 1,
            },
          ]}
        >
          <View style={s.row}>
            <Text style={[s.title, { marginBottom: 0 }]}>{r.id}</Text>
            <Text
              style={{
                color: r.blocked ? "#f49caa" : color.cyan,
                fontSize: 13,
              }}
            >
              {r.verdict}
            </Text>
            <T>{r.score}점</T>
          </View>
          <View
            style={[
              s.row,
              { justifyContent: "flex-start", gap: 20, marginVertical: 2 },
            ]}
          >
            <Text style={{ color: color.fg, fontSize: 19 }}>
              {r.distance}
              <Text style={s.muted}> km</Text>
            </Text>
            <Text style={{ color: color.fg, fontSize: 19 }}>
              {r.minutes}
              <Text style={s.muted}> 분</Text>
            </Text>
          </View>
          <Text style={[s.muted, { fontSize: 11, lineHeight: 15 }]}>
            {r.reason}
          </Text>
        </Pressable>
      ))}
      <Button
        disabled={!selected || selected.blocked}
        onPress={() =>
          show({
            title: "선택 경로",
            body: `경로 ${selected?.id} · ${selected?.distance} km / ${selected?.minutes}분`,
            confirm: "추천경로로 돌아가기",
            cancel: false,
          })
        }
      >
        선택 경로 네비게이션 앱에서 보기 ↗
      </Button>
      <Text style={[s.muted, { fontSize: 12, marginTop: 20 }]}>
        경로는 판단을 돕는 예상 정보이며 출동 지령이 아닙니다.
      </Text>
    </>
  );
}
