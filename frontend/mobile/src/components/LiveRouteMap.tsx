/**
 * 후속-05 모바일 지도: 기존 react-native-svg와 실제 경로 좌표만 사용합니다.
 * 화면에 필요한 온라인 OpenStreetMap 타일만 로드하며 실패하면 배경과 경로를 분리 표시.
 * 지도 전용 새 네이티브 패키지는 추가하지 않습니다. 경로 계산/판정은 변경하지 않습니다.
 */
import { useMemo, useState } from "react";
import { View, Image, Text, type LayoutChangeEvent } from "react-native";
import Svg, { Polyline, Circle } from "react-native-svg";
import { makeMapViewport, type MapLine, type LonLat } from "../routeMapMath";

const HEIGHT = 245;
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
  if (!view)
    return (
      <Text style={{ color: "#b3ccdc" }}>
        유효한 경로 좌표가 없어 지도를 표시할 수 없습니다.
      </Text>
    );
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
      {view.tiles.map((tile) => (
        <Image
          key={tile.key}
          source={{
            uri: tile.uri,
            // OSM 타일 사용 정책: 앱을 식별하고 HTTP 캐시를 사용합니다.
            headers: {
              "User-Agent":
                "OCTV-RouteView/0.1 (+https://github.com/alswo0548/octv)",
            },
            cache: "force-cache",
          }}
          style={{
            position: "absolute",
            left: tile.x,
            top: tile.y,
            width: 256,
            height: 256,
          }}
        />
      ))}
      <Svg
        width="100%"
        height={HEIGHT}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        style={{ position: "absolute", left: 0, top: 0 }}
      >
        {view.paths.map((path) => (
          <Polyline
            key={path.id}
            points={path.points}
            fill="none"
            stroke={path.id === selectedId ? "#ffe16d" : "#26bad2"}
            strokeWidth={path.id === selectedId ? 6 : 3}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={path.id === selectedId ? 1 : 0.6}
          />
        ))}
        {view.destination && (
          <Circle
            cx={view.destination.x}
            cy={view.destination.y}
            r={8}
            stroke="#fff"
            strokeWidth={2}
            fill="#fa7070"
          />
        )}
      </Svg>
      <Text
        style={{
          position: "absolute",
          right: 3,
          bottom: 3,
          padding: 3,
          fontSize: 9,
          color: "#fff",
          backgroundColor: "#142a34cc",
        }}
      >
        © OpenStreetMap contributors
      </Text>
    </View>
  );
}
