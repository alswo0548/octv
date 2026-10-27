"""Read-only spatial evidence probe for ITS link IDs near a CCTV.

The hosted geometries reference 2024-12 national node/link data. This is a
*diagnostic*, not confirmation of the camera view, road control or blocked lanes.
It never changes traffic_request_for(), risk Rules, DB or Redis mappings.
"""
from __future__ import annotations

from math import cos, isfinite, pi

import httpx

SPATIAL_REFERENCE_DATE = "2024-12"
SERVICE_BASE = "https://portal.esrikr.com/arcgis/rest/services/Hosted/ITS_LINK/FeatureServer"
LAYER_IDS = (0, 1, 2, 3)


def _coord(value, *, is_lat):
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    bound = 90 if is_lat else 180
    return result if isfinite(result) and -bound <= result <= bound else None


def _segment_distance_m(lat, lon, lat1, lon1, lat2, lon2):
    """Local tangent-plane point-to-segment distance; accurate over this short bbox."""
    cx = cos(lat * pi / 180) * 111_320
    cy = 111_132
    ax, ay = (lon1 - lon) * cx, (lat1 - lat) * cy
    bx, by = (lon2 - lon) * cx, (lat2 - lat) * cy
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = min(1.0, max(0.0, -(ax * dx + ay * dy) / length2)) if length2 else 0
    return ((ax + t * dx)**2 + (ay + t * dy)**2)**0.5


def _polyline_distance_m(lat, lon, geometry):
    """Accept only validated WGS84 paths. An endpoint alone is not road geometry."""
    if not isinstance(geometry, dict):
        return None
    paths = geometry.get("paths")
    if not isinstance(paths, list) or len(paths) > 30:
        return None
    nearest = None
    for path in paths:
        if not isinstance(path, list) or not (2 <= len(path) <= 10000):
            continue
        previous = None
        for point in path:
            if not isinstance(point, (tuple, list)) or len(point) < 2:
                return None
            x = _coord(point[0], is_lat=False)
            y = _coord(point[1], is_lat=True)
            # Fail closed for non-WGS84 geometries or invalid coordinates.
            if x is None or y is None or not (120 <= x <= 135 and 30 <= y <= 45):
                return None
            if previous is not None:
                d = _segment_distance_m(lat, lon, previous[1], previous[0], y, x)
                nearest = d if nearest is None else min(nearest, d)
            previous = (x, y)
    return nearest


def query_spatial_link_candidates(latitude, longitude, *, fetch_json=None, layers=LAYER_IDS):
    """Query public reference map near CCTV; never selects the viewed road.

    Fetch max 100 features per layer, reject over-limit/ambiguous responses.
    Provider data is a hosted 2024-12 copy, NOT authoritative current closure data.
    """
    lat = _coord(latitude, is_lat=True)
    lon = _coord(longitude, is_lat=False)
    if lat is None or lon is None or not (33 <= lat <= 39.5 and 124 <= lon <= 132):
        return {"status": "INVALID_CCTV_COORDINATES", "links": [], "source_version": SPATIAL_REFERENCE_DATE}
    dlat = 350 / 111_132
    dlon = 350 / max(111_320 * cos(lat * pi / 180), 1)
    bbox = ",".join(f"{v:.7f}" for v in (lon - dlon, lat - dlat, lon + dlon, lat + dlat))
    params = {
        "f": "json", "where": "1=1", "outFields": "link_id,road_name,f_node,t_node",
        "geometryType": "esriGeometryEnvelope", "geometry": bbox,
        "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true", "resultRecordCount": 100,
    }
    # Keep only sanitized outcome codes: never print URLs, coordinates or server bodies.
    transport_status = {}

    def _default_fetch(url, data):
        try:
            timeout = httpx.Timeout(connect=4.0, read=8.0, write=3.0, pool=3.0)
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.get(url, params=data)
            if response.status_code != 200:
                transport_status[url] = f"HTTP_{response.status_code}"
                return None
            if len(response.content) > 4_000_000:
                transport_status[url] = "RESPONSE_TOO_LARGE"
                return None
            try:
                return response.json()
            except (ValueError, TypeError):
                transport_status[url] = "INVALID_JSON"
                return None
        except httpx.TimeoutException:
            transport_status[url] = "NETWORK_TIMEOUT"
        except (httpx.RequestError, OSError):
            transport_status[url] = "NETWORK_CONNECT_ERROR"
        return None

    fetch_json = fetch_json or _default_fetch
    reached, failed, checked, matched, overflow = 0, 0, 0, {}, False
    layer_checks = []
    for layer in layers:
        if type(layer) is not int or layer not in LAYER_IDS:
            continue
        url = f"{SERVICE_BASE}/{layer}/query"
        try:
            payload = fetch_json(url, params)
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            payload = None
        if not isinstance(payload, dict):
            failed += 1
            layer_checks.append({"layer": layer, "status": transport_status.get(url, "NO_VALID_RESPONSE")})
            continue
        if "error" in payload:
            error = payload.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            # Only a bounded numeric code, no potentially sensitive body text.
            reason = f"ARCGIS_ERROR_{code}" if type(code) is int and 100 <= code <= 999 else "ARCGIS_ERROR"
            failed += 1
            layer_checks.append({"layer": layer, "status": reason})
            continue
        if payload.get("exceededTransferLimit") is True:
            overflow = True
        features = payload.get("features")
        if not isinstance(features, list) or len(features) > 100:
            failed += 1
            layer_checks.append({"layer": layer, "status": "INVALID_OR_TRUNCATED_FEATURES"})
            continue
        reached += 1
        layer_checks.append({"layer": layer, "status": "OK", "features": len(features)})
        for feature in features:
            if not isinstance(feature, dict):
                continue
            attrs = feature.get("attributes")
            if not isinstance(attrs, dict):
                continue
            # ArcGIS layer uses lower-case fields; tolerate upper-case mocks too.
            raw = str(attrs.get("link_id") or attrs.get("LINK_ID") or "").strip()
            if not (raw.isascii() and raw.isdecimal() and 8 <= len(raw) <= 15):
                continue
            d = _polyline_distance_m(lat, lon, feature.get("geometry"))
            if d is None:
                continue
            checked += 1
            if d > 250:
                continue
            candidate = {
                "link_id": raw,
                "road_name": str(attrs.get("road_name") or attrs.get("ROAD_NAME") or "")[:70],
                "distance_m": round(d),
                "geometry_source": "ESRI_HOSTED_ITS_LINK_REFERENCE_2024_12",
                "camera_direction_verified": False,
            }
            old = matched.get(raw)
            if old is None or candidate["distance_m"] < old["distance_m"]:
                matched[raw] = candidate
    status = ("SPATIAL_SOURCE_UNAVAILABLE" if reached == 0 else
              "SPATIAL_RESULT_INCOMPLETE" if overflow or failed else
              "SPATIAL_CANDIDATES_FOUND" if matched else "NO_SPATIAL_CANDIDATES")
    return {
        "status": status, "links": sorted(matched.values(), key=lambda x: (x["distance_m"], x["link_id"]))[:40],
        "layers_received": reached, "layers_failed": failed, "layer_checks": layer_checks,
        "geometry_links_checked": checked,
        "source_version": SPATIAL_REFERENCE_DATE,
    }


def compare_with_its(geometry_report, traffic_rows):
    """Only exact Link ID equality, no road-name guess or inferred camera bearing."""
    from .auto_match_providers import _field
    link_ids = set()
    for row in (traffic_rows or [])[:5000]:
        value = str(_field(row, "linkid", "roadsectionid") or "").strip()
        if value.isascii() and value.isdecimal():
            link_ids.add(value)
    matched = [row for row in geometry_report.get("links", [])
               if row["link_id"] in link_ids]
    return {
        "status": "LINK_IDS_MATCHED_DIRECTION_UNVERIFIED" if matched else
                  "SPATIAL_SOURCE_UNAVAILABLE" if geometry_report.get("status") == "SPATIAL_SOURCE_UNAVAILABLE" else
                  "SPATIAL_RESULT_INCOMPLETE" if geometry_report.get("status") == "SPATIAL_RESULT_INCOMPLETE" else
                  "LINK_ID_NOT_MATCHED_OR_DATASET_OUTDATED",
        "matching_links": matched[:5],
        "its_links_checked": len(link_ids),
        "geometry_links_nearby": len(geometry_report.get("links", [])),
        "camera_direction_verified": False,
        "closure_verified": False,
    }
