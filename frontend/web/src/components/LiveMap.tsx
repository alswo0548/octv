/** 기존 모바일 지도 투영 함수를 재사용해 실제 좌표·경로를 표시합니다. 배경 타일 실패를 별도로 알립니다. */
import { useMemo, useState, useRef, useEffect } from "react";
import {
  makeMapViewport,
  type MapLine,
  type LonLat,
} from "../mapViewport";
export type MapMarker = {
  id: number;
  label: string;
  longitude: number;
  latitude: number;
  priority?: string;
  kind?: "incident" | "agency";
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
  onMarkerSelect,
  controls = true,
  emphasizeRoutes = false,
  showResetButton = true,
  resetSignal = 0,
}: {
  lines?: MapLine[];
  markers?: MapMarker[];
  selectedId?: number | null;
  onSelect?: (id: number) => void;
  onMarkerSelect?: (id: number) => void;
  controls?: boolean;
  emphasizeRoutes?: boolean;
  showResetButton?: boolean;
  resetSignal?: number;
}) {
  const [camera, setCamera] = useState({ zoomDelta: 0, dx: 0, dy: 0 });
  const [hovered, setHovered] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; dx: number; dy: number; moved: boolean } | null>(null);
  const geometryKey = JSON.stringify([lines, markers]);
  useEffect(() => { setCamera({ zoomDelta: 0, dx: 0, dy: 0 }); }, [resetSignal]);
  useEffect(() => { setCamera({ zoomDelta: 0, dx: 0, dy: 0 }); setFailed(false); }, [geometryKey]);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !controls) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      setCamera(c => {
        const z = Math.max(-13, Math.min(16, c.zoomDelta + (event.deltaY < 0 ? 1 : -1)));
        const factor = 2 ** (z - c.zoomDelta);
        return { zoomDelta: z, dx: c.dx * factor, dy: c.dy * factor };
      });
    };
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => svg.removeEventListener("wheel", wheel);
  }, [controls]);
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
        camera,
      ),
    [geometryKey, camera],
  );
  return (
    <div className={"map-shell octv-muted-map" + (emphasizeRoutes ? " octv-route-map" : "")}>
      {controls && showResetButton && <button className="secondary map-reset-button" onClick={() => { setCamera({ zoomDelta: 0, dx: 0, dy: 0 }); setFailed(false); }}>전체보기</button>}
      {!view ? (
        <div className="map-empty">표시할 위치 좌표가 없습니다.</div>
      ) : (
        <svg
          ref={svgRef}
          style={{ touchAction: controls ? "none" : "auto", cursor: controls ? "grab" : "default" }}
          onPointerDown={e => {
            if (!controls || e.button !== 0) return;
            drag.current = { x: e.clientX, y: e.clientY, dx: camera.dx, dy: camera.dy, moved: false };
          }}
          onPointerMove={e => {
            if (!controls) return;
            if (e.buttons === 0) { drag.current = null; return; }
            const d = drag.current;
            if (!d) return;
            const scale = 820 / e.currentTarget.getBoundingClientRect().width;
            if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) { d.moved = true; e.currentTarget.setPointerCapture(e.pointerId); }
            setCamera(c => ({ ...c, dx: d.dx + (e.clientX - d.x) * scale, dy: d.dy + (e.clientY - d.y) * scale }));
          }}
          onPointerUp={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); else setTimeout(() => { drag.current = null; }, 0); }}
          onLostPointerCapture={() => { setTimeout(() => { drag.current = null; }, 0); }}
          onClickCapture={e => { if (drag.current?.moved) { e.preventDefault(); e.stopPropagation(); } }}
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
          <rect width="820" height="430" fill="#06121f" opacity="0.30" pointerEvents="none" />
          {view.paths
            .filter((path) => path.id > 0)
            .map((path, index) => {
              // Hover is a temporary preview of one candidate. Leaving the route
              // restores the explicitly selected route; other paths stay subdued.
              const highlighted = emphasizeRoutes && (hovered ?? selectedId) === path.id;
              return (
                <g
                  key={`${path.id}:${index}`}
                  style={{ cursor: onSelect ? "pointer" : "default" }}
                  onMouseEnter={() => setHovered(path.id)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => onSelect?.(path.id)}
                >
                  <polyline
                    points={path.points}
                    fill="none"
                    stroke={emphasizeRoutes ? (highlighted ? "#ff5968" : "#69b2c4") : path.id === selectedId ? "#ffe16d" : ["#26bad2", "#ba99ff", "#60dfa2", "#ffa264"][index % 4]}
                    strokeWidth={emphasizeRoutes ? (highlighted ? 7 : 2.5) : path.id === selectedId || path.id === hovered ? 7 : 3}
                    opacity={emphasizeRoutes && !highlighted ? 0.72 : 1}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {emphasizeRoutes && (
                    <polyline
                      points={path.points}
                      fill="none"
                      stroke="transparent"
                      strokeWidth="18"
                      pointerEvents="stroke"
                    />
                  )}
                </g>
              );
            })}
          {goodMarkers.map((marker) => {
            const point = view.paths
              .find((path) => path.id === -marker.id)
              ?.points.split(",")
              .map(Number);
            return (
              point && (
                <g
                  key={marker.id}
                  className={"incident-pin" + (hovered === marker.id ? " pin-active" : "")}
                  style={{ color: marker.kind === "agency" ? "#56cde2" : marker.kind === "incident" ? "#ec5269" : marker.priority === "P1" ? "#e94c66" : marker.priority === "P2" ? "#ecac35" : marker.priority === "P3" ? "#378acd" : "#b5bdc9" }}
                  onMouseEnter={() => setHovered(marker.id)}
                  onMouseLeave={() => setHovered(null)}
                  transform={`translate(${point[0]} ${point[1]})`}
                  role="button"
                  tabIndex={0}
                  aria-label={marker.label}
                  onClick={() => (onMarkerSelect ?? onSelect)?.(marker.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (onMarkerSelect ?? onSelect)?.(marker.id);
                  }}
                >
                  <ellipse className="pin-ripple" cx="0" cy="0" rx="21" ry="8" />
                  <ellipse className="pin-ripple ripple-late" cx="0" cy="0" rx="21" ry="8" />
                  <g className="pin-body">
                    <path d="M0 0 C-4 -7 -15 -17 -15 -27 A15 15 0 1 1 15 -27 C15 -17 4 -7 0 0Z" fill="currentColor" />
                    <text textAnchor="middle" y="-23" fontSize="10" fontWeight="bold" fill="#fff">{marker.kind === "agency" ? "기관" : marker.kind === "incident" ? "사건" : marker.priority ?? "사건"}</text>
                  </g>
                  <text
                    className="incident-pin-label"
                    y="-48"
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
