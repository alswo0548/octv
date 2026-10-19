/**
 * 후속-05 좌표를 Web Mercator 지도 픽셀에 투영합니다.
 * 실제 LineString 좌표만 사용합니다. 경로가 없으면 만들어 그리지 않습니다.
 */
export type LonLat = readonly [number, number];
export type MapLine = { id: number; coords: readonly LonLat[] };
export type Tile = { key: string; uri: string; x: number; y: number };
export type PixelPoint = { x: number; y: number };
export type MapViewport = {
  tiles: Tile[];
  paths: { id: number; points: string }[];
  destination: PixelPoint | null;
};
const TILE_SIZE = 256;
const MAX_LAT = 85.05112878;
function worldPoint([lon, lat]: LonLat, zoom: number): PixelPoint {
  const latRadians =
    (Math.max(-MAX_LAT, Math.min(MAX_LAT, lat)) * Math.PI) / 180;
  const scale = TILE_SIZE * 2 ** zoom;
  return {
    x: ((lon + 180) / 360) * scale,
    y:
      ((1 -
        Math.log(Math.tan(latRadians) + 1 / Math.cos(latRadians)) / Math.PI) /
        2) *
      scale,
  };
}
// 많은 CCTV 프레임에서 저장된 긴 경로도 Math.max(...배열) 인자 수 한도에 걸리지 않게 계산합니다.
function bounds(points: readonly LonLat[], zoom: number) {
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;
  for (const point of points) {
    const pixel = worldPoint(point, zoom);
    minX = Math.min(minX, pixel.x);
    maxX = Math.max(maxX, pixel.x);
    minY = Math.min(minY, pixel.y);
    maxY = Math.max(maxY, pixel.y);
  }
  return { minX, maxX, minY, maxY };
}
export function makeMapViewport(
  lines: readonly MapLine[],
  destination: LonLat | null,
  width: number,
  height: number,
): MapViewport | null {
  const all = lines.flatMap((line) => line.coords);
  if (destination) all.push(destination);
  if (all.length === 0 || width <= 0 || height <= 0) return null;
  let zoom = 3;
  const margin = 28;
  for (let candidate = 16; candidate >= 3; candidate--) {
    const box = bounds(all, candidate);
    const spreadX = box.maxX - box.minX;
    const spreadY = box.maxY - box.minY;
    if (spreadX <= width - margin * 2 && spreadY <= height - margin * 2) {
      zoom = candidate;
      break;
    }
  }
  const box = bounds(all, zoom);
  const centerX = (box.minX + box.maxX) / 2;
  const centerY = (box.minY + box.maxY) / 2;
  const translate = (point: LonLat) => {
    const p = worldPoint(point, zoom);
    return { x: p.x - centerX + width / 2, y: p.y - centerY + height / 2 };
  };
  const tiles: Tile[] = [];
  const n = 2 ** zoom;
  const minX = Math.floor((centerX - width / 2) / TILE_SIZE);
  const maxX = Math.floor((centerX + width / 2) / TILE_SIZE);
  const minY = Math.floor((centerY - height / 2) / TILE_SIZE);
  const maxY = Math.floor((centerY + height / 2) / TILE_SIZE);
  for (let x = minX; x <= maxX; x++) {
    for (let y = minY; y <= maxY; y++) {
      if (y < 0 || y >= n) continue;
      const tileX = ((x % n) + n) % n;
      tiles.push({
        key: `${zoom}-${tileX}-${y}`,
        uri: `https://tile.openstreetmap.org/${zoom}/${tileX}/${y}.png`,
        x: x * TILE_SIZE - centerX + width / 2,
        y: y * TILE_SIZE - centerY + height / 2,
      });
    }
  }
  return {
    tiles,
    paths: lines.map((line) => ({
      id: line.id,
      points: line.coords
        .map((point) => {
          const p = translate(point);
          return `${p.x.toFixed(2)},${p.y.toFixed(2)}`;
        })
        .join(" "),
    })),
    destination: destination ? translate(destination) : null,
  };
}
