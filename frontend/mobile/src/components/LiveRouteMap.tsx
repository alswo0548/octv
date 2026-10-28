/**
 * 기관별 저장 경로의 좌표 기반 미리보기입니다.
 * 외부 타일 서버의 정책 차단/거부 이미지를 노출하지 않고 실제 저장 좌표만 그립니다.
 * 도로 배경지도가 아니며 경로 생성·기관별 권한·점수·내비 로직은 변경하지 않습니다.
 */
import { useMemo, useState } from "react";
import { View, Text, type LayoutChangeEvent } from "react-native";
import Svg, { Rect, Line, Polyline, Circle } from "react-native-svg";
import { makeMapViewport, type MapLine, type LonLat } from "../routeMapMath";

const HEIGHT = 245;
const GRID_COLOR = "#2a4a5c";
const MUTED = "#a4c1cf";
const HIGHLIGHT = "#ffe16d";
const OTHER_ROUTE = "#26bad2";
const GRID_STEPS = [0.2, 0.4, 0.6, 0.8];

export function LiveRouteMap({
  lines,
  selectedId,
  destination,
}: {
  lines: readonly MapLine[];
  selectedId: number | null;
  destination: LonLat | null;
}) {
  const [width, setWidth] = useState(328);
  const view = useMemo(
    () => makeMapViewport(lines, destination, width, HEIGHT),
    [lines, destination, width],
  );
  const onLayout = (event: LayoutChangeEvent) => {
    const nextWidth = Math.round(event.nativeEvent.layout.width);
    if (nextWidth > 0 && nextWidth !== width) setWidth(nextWidth);
  };

  if (!view) {
    return (
      <Text style={{ color: MUTED }}>
        유효한 경로 좌표가 없어 미리보기를 표시할 수 없습니다.
      </Text>
    );
  }

  // 출발지는 경로의 첫 번째 실제 좌표입니다. 별도 도로·경로를 생성하지 않습니다.
  const selected = view.paths.find((path) => path.id === selectedId) ?? view.paths[0];
  const first = selected?.points.split(" ")[0]?.split(",").map(Number);
  const origin =
    first?.length === 2 && first.every(Number.isFinite)
      ? { x: first[0], y: first[1] }
      : null;

  return (
    <View
      onLayout={onLayout}
      style={{
        height: HEIGHT,
        borderRadius: 10,
        overflow: "hidden",
        backgroundColor: "#102534",
        borderWidth: 1,
        borderColor: "#2b4152",
      }}
    >
      <Svg width="100%" height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`}>
        <Rect width={width} height={HEIGHT} fill="#102534" />
        {GRID_STEPS.map((fraction) => (
          <Line
            key={`v-${fraction}`}
            x1={width * fraction}
            y1={0}
            x2={width * fraction}
            y2={HEIGHT}
            stroke={GRID_COLOR}
            strokeWidth={1}
            strokeDasharray="3 7"
            opacity={0.6}
          />
        ))}
        {GRID_STEPS.map((fraction) => (
          <Line
            key={`h-${fraction}`}
            x1={0}
            y1={HEIGHT * fraction}
            x2={width}
            y2={HEIGHT * fraction}
            stroke={GRID_COLOR}
            strokeWidth={1}
            strokeDasharray="3 7"
            opacity={0.6}
          />
        ))}
        {view.paths
          .filter((path) => path.id !== selected?.id)
          .map((path) => (
            <Polyline
              key={path.id}
              points={path.points}
              fill="none"
              stroke={OTHER_ROUTE}
              strokeWidth={3}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.55}
            />
          ))}
        {selected && (
          <Polyline
            key={selected.id}
            points={selected.points}
            fill="none"
            stroke={HIGHLIGHT}
            strokeWidth={5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {origin && (
          <Circle
            cx={origin.x}
            cy={origin.y}
            r={6.5}
            stroke="#ffffff"
            strokeWidth={2}
            fill="#72d7bc"
          />
        )}
        {view.destination && (
          <Circle
            cx={view.destination.x}
            cy={view.destination.y}
            r={8}
            stroke="#ffffff"
            strokeWidth={2}
            fill="#fa7070"
          />
        )}
      </Svg>
      <View
        pointerEvents="none"
        style={{
          position: "absolute",
          top: 8,
          left: 9,
          right: 9,
          paddingVertical: 6,
          paddingHorizontal: 9,
          borderRadius: 6,
          backgroundColor: "#0a1b2ae8",
        }}
      >
        <Text style={{ color: "#e5f7ff", fontSize: 12, fontWeight: "600" }}>
          저장된 경로 좌표 미리보기
        </Text>
      </View>
      <View
        pointerEvents="none"
        style={{
          position: "absolute",
          bottom: 5,
          left: 7,
          right: 7,
          paddingVertical: 5,
          paddingHorizontal: 7,
          borderRadius: 5,
          backgroundColor: "#0a1b2ae8",
        }}
      >
        <Text style={{ color: MUTED, fontSize: 10 }}>
          ● 출발(청록)  ● 현장(빨강)  ━ 선택 경로(노랑)
        </Text>
        <Text style={{ color: MUTED, fontSize: 10 }}>
          도로 배경지도 아님 · 서버 저장 좌표만 표시
        </Text>
      </View>
    </View>
  );
}
