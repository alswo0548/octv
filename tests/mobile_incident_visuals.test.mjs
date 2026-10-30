import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { readIncidentDetectionBox } from "../frontend/mobile/src/incidentDetectionBox.ts";

const detail = readFileSync(new URL("../frontend/mobile/src/screens/DetailScreen.tsx", import.meta.url), "utf8");
const routeMap = readFileSync(new URL("../frontend/mobile/src/components/LiveRouteMap.tsx", import.meta.url), "utf8");

test("mobile representative image reads only a valid saved server bbox", () => {
  assert.deepEqual(readIncidentDetectionBox({ x1: 100, y1: 35, x2: 230, y2: 170 }), { x1: 100, y1: 35, x2: 230, y2: 170 });
  assert.equal(readIncidentDetectionBox({ x1: 120, y1: 12, x2: 100, y2: 88 }), null);
  assert.equal(readIncidentDetectionBox([100, 35, 230, 170]), null);
  assert.equal(readIncidentDetectionBox({ x1: "foo", y1: 35, x2: 230, y2: 170 }), null);
  assert.equal(readIncidentDetectionBox(null), null);
});

test("mobile bbox overlay uses natural JPEG size with contain aspect alignment", () => {
  assert.match(detail, /readIncidentDetectionBox\(incident\.detection_bbox_json\)/);
  assert.match(detail, /onLoad=\{\(event\) =>/);
  assert.match(detail, /viewBox=\{\x60 0 0 \$\{imageSize\.width\} \$\{imageSize\.height\}\x60\}/);
  assert.match(detail, /preserveAspectRatio="xMidYMid meet"/);
  assert.match(detail, /resizeMode="contain"/);
  assert.match(detail, /\{imageSize && box &&/);
});

test("mobile route map keeps saved geometry and emphasizes selected route", () => {
  assert.match(routeMap, /makeMapViewport\(lines, destination, width, HEIGHT\)/);
  assert.match(routeMap, /orderedPaths/);
  assert.match(routeMap, /stroke=\{path\.id === selectedId \? "#ff5968" : "#69b2c4"\}/);
  assert.match(routeMap, /사건 위치/);
  assert.match(routeMap, /출발측/);
  assert.match(routeMap, /© OpenStreetMap contributors/);
});
