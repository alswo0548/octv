import { View, Text, Pressable } from "react-native";
import { mock, type Incident } from "@octv/shared";
import { Badge, T, Button, Panel, Pair } from "../components/UI";
import { Camera } from "../components/Camera";
import { s, color } from "../styles/theme";
import type { Navigate } from "../navigation/types";
export function DetailScreen({
  incident: d,
  live = false,
  go,
}: {
  incident: Incident;
  live?: boolean;
  go: Navigate;
}) {
  const camera = mock.cctvs.find((c) => c.id === d.camera),
    connected = camera?.connected !== false;
  return (
    <>
      <Badge priority={d.priority} />
      <Text style={[s.title, { marginTop: 13 }]}>
        {d.type} · {d.id}
      </Text>
      <T muted>
        {d.location} · {d.camera}
      </T>
      <View style={[s.info, { marginTop: 18 }]}>
        <T>수신 기관 · {mock.profile.agency}</T>
        <T muted>소속 기관을 통해 전달된 사건정보입니다.</T>
      </View>
      {!live && (
        <View style={[s.row, { marginBottom: 22 }]}>
          {[
            ["위험도", d.risk],
            ["우선순위", d.score],
            ["신뢰도", d.confidence + "%"],
          ].map(([label, value]) => (
            <View key={label} style={{ flex: 1, alignItems: "center" }}>
              <T muted>{label}</T>
              <Text style={{ color: color.fg, fontSize: 27, marginTop: 6 }}>
                {value}
              </Text>
            </View>
          ))}
        </View>
      )}
      <View style={s.tabs}>
        {[
          ["사건 정보", "detail"],
          ["실시간 영상", "live"],
        ].map(([label, route]) => (
          <Pressable
            key={route}
            accessibilityRole="tab"
            accessibilityState={{ selected: live === (route === "live") }}
            onPress={() => go(route as "detail" | "live", d.id)}
            style={[s.tab, live === (route === "live") && s.tabActive]}
          >
            <T>{label}</T>
          </Pressable>
        ))}
      </View>
      <Camera incident={d} live={live} connected={!live || connected} />
      <Text style={[s.muted, { fontSize: 10, marginVertical: 10 }]}>
        {live ? "실시간 영상" : "대표 탐지 캡처"}
      </Text>
      {live ? (
        <Panel title="CCTV 상태">
          <Pair
            label="연결 상태"
            value={
              connected ? mock.uiSnapshot.cameraStatus.online : "연결 끊김"
            }
          />
          <Pair
            label="영상 품질"
            value={
              connected ? mock.uiSnapshot.cameraStatus.quality : "확인 불가"
            }
          />
          <Pair
            label="분석 상태"
            value={connected ? mock.uiSnapshot.cameraStatus.analysis : "중지"}
          />
          <Pair
            label="마지막 프레임"
            value={mock.uiSnapshot.cameraStatus.lastFrame}
          />
        </Panel>
      ) : (
        <Panel title="사건 상세정보">
          <Pair label="탐지 유형" value={d.type} />
          <Pair label="기상·수위" value={`${d.rain} mm / ${d.water} m`} />
          <Pair label="도로 통제" value={d.traffic} />
          <Pair label="수신 기관" value={mock.profile.agency} />
          <Pair label="판단 근거" value={d.reasons.join(" · ")} />
        </Panel>
      )}
      <Button onPress={() => go("routes", d.id)}>경로 비교 상세</Button>
      <Button secondary onPress={() => go("request", d.id)}>
        추가 지원요청
      </Button>
    </>
  );
}
