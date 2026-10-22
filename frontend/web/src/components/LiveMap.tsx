/** 기존 모바일 지도 투영 함수를 재사용해 실제 좌표·경로를 표시합니다. 배경 타일 실패를 별도로 알립니다. */
import { useMemo, useState } from "react";
import {
  makeMapViewport,
  type MapLine,
  type LonLat,
} from "../../../mobile/src/routeMapMath";
export type MapMarker = {
  id: number;
  label: string;
  longitude: number;
  latitude: number;
  priority?: string;
};
const SEOUL_DEFAULT_BOUNDS: MapLine = {
  id: 0,
  coords: [
    [126.76, 37.43],
    [127.18, 37.7],
  ],
};
export function geometryLines(id: number, geometry: unknown): MapLine[] {
  if (!geometry || typeof geometry !== "object") return [];
  const item = geometry as { type?: string; coordinates?: unknown };
  const candidates =
    item.type === "LineString"
      ? [item.coordinates]
      : item.type === "MultiLineString" && Array.isArray(item.coordinates)
        ? item.coordinates
        : [];
  return candidates.flatMap((coords) => {
    if (
      !Array.isArray(coords) ||
      coords.length < 2 ||
      coords.length > 30000 ||
      !coords.every(
        (p) =>
          Array.isArray(p) &&
          p.length >= 2 &&
          typeof p[0] === "number" &&
          typeof p[1] === "number" &&
          Number.isFinite(p[0]) &&
          Number.isFinite(p[1]) &&
          Math.abs(p[0]) <= 180 &&
          Math.abs(p[1]) <= 85.05112878,
      )
    )
      return [];
    return [{ id, coords: coords as LonLat[] }];
  });
}
export function LiveMap({
  lines = [],
  markers = [],
  selectedId = null,
  onSelect,
}: {
  lines?: MapLine[];
  markers?: MapMarker[];
  selectedId?: number | null;
  onSelect?: (id: number) => void;
}) {
  const [failed, setFailed] = useState(false);
  const goodMarkers = markers.filter(
    (m) =>
      Number.isFinite(m.longitude) &&
      Number.isFinite(m.latitude) &&
      Math.abs(m.longitude) <= 180 &&
      Math.abs(m.latitude) <= 85.05112878,
  );
  const view = useMemo(
    () =>
      makeMapViewport(
        [
          ...(lines.length === 0 && goodMarkers.length === 0
            ? [SEOUL_DEFAULT_BOUNDS]
            : lines),
          ...goodMarkers.map((m) => ({
            id: -m.id,
            coords: [[m.longitude, m.latitude] as LonLat],
          })),
        ],
        null,
        820,
        430,
      ),
    [lines, markers],
  );
  return (
    <div className="map-shell">
      {!view ? (
        <div className="map-empty">표시할 위치 좌표가 없습니다.</div>
      ) : (
        <svg
          className="road-map"
          viewBox="0 0 820 430"
          role="img"
          aria-label="실제 사건·경로 지도"
        >
          <rect width="820" height="430" fill="#0b1925" />
          {!failed &&
            view.tiles.map((tile) => (
              <image
                key={tile.key}
                href={tile.uri}
                x={tile.x}
                y={tile.y}
                width="256"
                height="256"
                onError={() => setFailed(true)}
              />
            ))}
          {view.paths
            .filter((path) => path.id > 0)
            .map((path, index) => (
              <polyline
                key={`${path.id}:${index}`}
                points={path.points}
                fill="none"
                stroke={path.id === selectedId ? "#ffe16d" : "#26bad2"}
                strokeWidth={path.id === selectedId ? 6 : 3}
                onClick={() => onSelect?.(path.id)}
              />
            ))}
          {goodMarkers.map((marker) => {
            const point = view.paths
              .find((path) => path.id === -marker.id)
              ?.points.split(",")
              .map(Number);
            return (
              point && (
                <g
                  key={marker.id}
                  transform={`translate(${point[0]} ${point[1]})`}
                  role="button"
                  tabIndex={0}
                  aria-label={marker.label}
                  onClick={() => onSelect?.(marker.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSelect?.(marker.id);
                  }}
                >
                  <circle
                    r="11"
                    fill={marker.priority === "P1" ? "#f49caa" : "#66ddeb"}
                    stroke="#fff"
                    strokeWidth="2"
                  />
                  <text
                    y="-19"
                    textAnchor="middle"
                    fill="#fff"
                    stroke="#07131d"
                    strokeWidth="3"
                    paintOrder="stroke"
                  >
                    {marker.label}
                  </text>
                </g>
              )
            );
          })}
        </svg>
      )}
      <div className="map-caption">
        <span>
          {failed
            ? "배경 지도 로딩 실패 · 저장된 좌표만 표시"
            : "실제 저장 좌표 기준"}
        </span>
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          © OpenStreetMap contributors
        </a>
      </div>
    </div>
  );
}
