import { View, Text, Pressable } from "react-native";
import { mock, incidentById, type Incident } from "@octv/shared";
import { Badge, T, Link, Segments, Choice } from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate } from "../navigation/types";
export function IncidentCard({
  incident: d,
  onPress,
}: {
  incident: Incident;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={d.id + " 사건 상세"}
      onPress={onPress}
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
        <Badge priority={d.priority} />
        <Text style={[s.muted, { color: "#b9d1df" }]}>● 전달 완료</Text>
      </View>
      <Text style={[s.h2, { marginTop: 15, marginBottom: 4 }]}>
        {d.type} · {d.id}
      </Text>
      <T muted>
        {d.location} · {d.camera}
      </T>
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
        <T muted>{d.time} 탐지</T>
        <T muted>위험도 {d.risk}</T>
      </View>
    </Pressable>
  );
}
export function IncidentScreens({
  home = false,
  go,
}: {
  home?: boolean;
  go: Navigate;
}) {
  return (
    <>
      {home ? (
        <>
          <View style={[s.info, { flexDirection: "row", gap: 15 }]}>
            <Text style={{ color: color.cyan, fontSize: 30 }}>☂</Text>
            <View style={{ flex: 1 }}>
              <T>{mock.uiSnapshot.weather.title}</T>
              <Text style={[s.muted, { fontSize: 12 }]}>
                {mock.uiSnapshot.weather.summary}
              </Text>
            </View>
          </View>
          <View style={s.row}>
            <Text style={s.h2}>우선 확인 사건</Text>
            <Link onPress={() => go("incidents")}>
              {mock.uiSnapshot.mobile.total}
            </Link>
          </View>
        </>
      ) : (
        <>
          <Segments options={mock.uiSnapshot.mobile.segments} />
          <Choice
            label="사건 유형"
            options={["전체 유형", "도로 침수", "쓰러진 나무", "시설물 파손"]}
          />
        </>
      )}
      {mock.mobileIds.map((id) => (
        <IncidentCard
          key={id}
          incident={incidentById(id)}
          onPress={() => go("detail", id)}
        />
      ))}
      <Text style={[s.muted, { marginTop: 20, fontSize: 12 }]}>
        기관에 전달된 사건정보와 추천경로의 고정 예시입니다. 출동 여부는 기관의
        기존 체계에서 결정합니다.
      </Text>
    </>
  );
}
