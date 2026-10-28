/**
 * 실제 기관 경로: 기존 지도 좌표 투영과 DB 저장 경로를 그대로 사용합니다.
 * 도로 배경은 웹과 동일한 OpenStreetMap 타일을 식별 가능한 Android WebView에서 요청합니다.
 * 경로 계산·점수·JWT·기관 접근·내비게이션·시연 영상에는 영향을 주지 않습니다.
 */
import { useEffect, useMemo, useState } from "react";
import { Pressable, Text, View, type LayoutChangeEvent } from "react-native";
import Svg, { Circle, Polyline } from "react-native-svg";
import { WebView } from "react-native-webview";
import { makeMapViewport, type MapLine, type LonLat, type MapViewport } from "../routeMapMath";

const HEIGHT = 245;
const BACKGROUND = "#102534";
// 기존 API 주소의 HTTPS origin만 Referer로 사용합니다. JWT/개인정보는 HTML에 넣지 않습니다.
const mapOrigin = (process.env.EXPO_PUBLIC_API_BASE_URL ?? "")
  .trim()
  .match(/^https:\/\/[^/?#]+/i)?.[0] ?? "";

function tileDocument(view: MapViewport): string {
  // 경로 정보는 HTML에 넣지 않습니다. 화면에 보이는 배경 타일 URL만 넣습니다.
  const tiles = view.tiles
    .filter((tile) => /^https:\/\/tile\.openstreetmap\.org\/\d+\/\d+\/\d+\.png$/.test(tile.uri))
    .map((tile) => {
      const left = tile.x.toFixed(2);
      const top = tile.y.toFixed(2);
      return `<img src="${tile.uri}" loading="eager" draggable="false" style="left:${left}px;top:${top}px" onerror="window.ReactNativeWebView?.postMessage('tile-error')">`;
    })
    .join("");
  return `<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="referrer" content="origin">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https://tile.openstreetmap.org; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<style>html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:${BACKGROUND}}#tiles{position:relative;width:100vw;height:${HEIGHT}px;overflow:hidden}img{position:absolute;width:256px;height:256px;max-width:none;pointer-events:none;user-select:none}</style>
</head><body><div id="tiles">${tiles}</div></body></html>`;
}

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
  const [showTiles, setShowTiles] = useState(true);
  useEffect(() => setTilesFailed(false), [lines, destination]);
  const view = useMemo(
    () => makeMapViewport(lines, destination, width, HEIGHT),
    [lines, destination, width],
  );
  const tileSource = useMemo(
    () => (view && mapOrigin ? { html: tileDocument(view), baseUrl: mapOrigin + "/" } : null),
    [view],
  );
  const onLayout = (event: LayoutChangeEvent) => {
    const nextWidth = Math.round(event.nativeEvent.layout.width);
    if (nextWidth > 0 && nextWidth !== width) setWidth(nextWidth);
  };
  if (!view) {
    return <Text style={{ color: "#b3ccdc" }}>유효한 경로 좌표가 없어 지도를 표시할 수 없습니다.</Text>;
  }

  // 요청 실패 시 저장된 경로선은 계속 표시합니다. 접근 차단 이미지를 우회·저장하지 않습니다.
  const basemapOn = showTiles && !tilesFailed && tileSource !== null;
  return (
    <View
      onLayout={onLayout}
      style={{
        height: HEIGHT,
        borderRadius: 10,
        overflow: "hidden",
        backgroundColor: BACKGROUND,
        borderWidth: 1,
        borderColor: "#2b4152",
      }}
    >
      {basemapOn && tileSource && (
        <WebView
          source={tileSource}
          originWhitelist={["*"]}
          applicationNameForUserAgent="OCTV-Mobile/0.1 (+https://github.com/alswo0548/octv)"
          javaScriptEnabled
          scrollEnabled={false}
          cacheEnabled
          onMessage={(event) => {
            if (event.nativeEvent.data === "tile-error") setTilesFailed(true);
          }}
          onError={() => setTilesFailed(true)}
          onShouldStartLoadWithRequest={(request) =>
            request.url === "about:blank" || request.url === mapOrigin || request.url.startsWith(mapOrigin + "/")
          }
          style={{ position: "absolute", top: 0, left: 0, width: "100%", height: HEIGHT, backgroundColor: BACKGROUND }}
        />
      )}
      <View pointerEvents="none" style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}>
        <Svg width="100%" height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`}>
          {view.paths.map((path) => (
            <Polyline
              key={path.id}
              points={path.points}
              fill="none"
              stroke={path.id === selectedId ? "#ffe16d" : "#26bad2"}
              strokeWidth={path.id === selectedId ? 6 : 3}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={path.id === selectedId ? 1 : 0.65}
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
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={showTiles ? "지도 배경 숨기기" : "도로 배경지도 표시"}
        onPress={() => { setShowTiles((value) => !value); setTilesFailed(false); }}
        style={{
          position: "absolute", left: 8, top: 8, backgroundColor: "#102534ee",
          borderRadius: 7, paddingHorizontal: 9, paddingVertical: 7, borderWidth: 1, borderColor: "#48738a",
        }}
      >
        <Text style={{ color: "#ddf4ff", fontSize: 11 }}>
          {basemapOn ? "도로 배경 숨기기" : "도로 배경 다시 보기"}
        </Text>
      </Pressable>
      {basemapOn ? (
        <Text
          style={{
            position: "absolute", right: 4, bottom: 4, padding: 4,
            fontSize: 10, color: "#ffffff", backgroundColor: "#142a34e8",
          }}
        >© OpenStreetMap contributors</Text>
      ) : (
        <View pointerEvents="none" style={{ position: "absolute", left: 5, right: 5, bottom: 5, padding: 5, backgroundColor: "#142a34e8" }}>
          <Text style={{ color: "#c7deeb", fontSize: 10 }}>
            {tilesFailed ? "배경지도 로딩 실패 · " : ""}실제 DB 저장 경로 좌표만 표시 (도로 배경 아님)
          </Text>
        </View>
      )}
    </View>
  );
}
