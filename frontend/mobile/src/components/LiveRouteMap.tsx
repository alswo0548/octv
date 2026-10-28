/**
 * 후속-05 모바일 지도: 기존 react-native-svg와 실제 경로 좌표만 사용합니다.
 * 리허설 모바일 경로 화면은 이용 정책을 확인한 공개 비상업 지도 타일을 사용합니다.
 * 지도 전용 새 네이티브 패키지는 추가하지 않습니다. 경로 계산/판정은 변경하지 않습니다.
 */
import { useMemo, useState, useEffect } from "react";
import { View, Image, Text, type LayoutChangeEvent } from "react-native";
import Svg, { Polyline, Circle } from "react-native-svg";
import { makeMapViewport, type MapLine, type LonLat } from "../routeMapMath";

const HEIGHT = 245;
// 기존 OSM 운영 타일의 403 차단을 다른 서버로 우회하지 않고, 별도 제공자의 공개 이용 정책에 따라 요청합니다.
// OpenMaps.fr: 비상업적/저용량 사용, 식별 가능한 User-Agent 및 눈에 보이는 출처 표시가 필요합니다.
// 외부 환경 변수로 다른 승인된 제공자를 설정하는 기존 기능은 유지합니다.
const tileTemplate = process.env.EXPO_PUBLIC_OCTV_MAP_TILE_URL_TEMPLATE?.trim() ?? "";
const providerAttribution = process.env.EXPO_PUBLIC_OCTV_MAP_ATTRIBUTION?.trim();
const alternateTiles = /^https:\/\//.test(tileTemplate) && !!providerAttribution && ["{z}","{x}","{y}"].every((key) => tileTemplate.includes(key));
const fallbackTileTemplate = "https://tile.openmaps.fr/opentopomap/{z}/{x}/{y}.png";
const fallbackAttribution = "© OpenTopoMap-R · © OpenStreetMap · openmaps.fr/donate";
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
  const [tilesFailed, setTilesFailed] = useState(false);
  useEffect(() => setTilesFailed(false), [lines, destination]);
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
          onError={() => setTilesFailed(true)}
          source={{
            uri: (alternateTiles ? tileTemplate : fallbackTileTemplate)
              .replace("{z}", tile.key.split("-")[0])
              .replace("{x}", tile.key.split("-")[1])
              .replace("{y}", tile.key.split("-")[2]),
            headers: {
              "User-Agent": "OCTV-Mobile/0.1 (com.octv.mobile; +https://github.com/alswo0548/octv)",
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
      {tilesFailed && (
        <Text style={{ position: "absolute", left: 7, top: 7, right: 7, padding: 6, backgroundColor: "#142a34ee", color: "#ffccd3", fontSize: 11 }}>
          지도 배경 일부를 불러오지 못했습니다. 경로 선은 서버 저장 좌표입니다. 타일 제공자 또는 연결을 확인해주세요.
        </Text>
      )}
      <Text
        style={{
          position: "absolute",
          right: 3,
          bottom: 3,
          padding: 3,
          fontSize: 10,
          color: "#fff",
          backgroundColor: "#142a34cc",
        }}
      >
        {alternateTiles ? providerAttribution : fallbackAttribution}
      </Text>
    </View>
  );
}
