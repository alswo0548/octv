/** 실제 사건 통계를 기존 차트에 표시합니다. 기간은 KST, 신뢰도 분포는 모델 정확도와 구분합니다. */
import { useState } from "react";
import { hazardLabel, hazardLabels } from "@octv/shared";
import type { WebIncidentSession } from "../incidentData";
import {
  seoulDate,
  useOperations,
  statusLabel,
  type Stats,
  type Cctv,
} from "../operationsData";
import { Panel, Pair } from "../components/Primitives";
import { go } from "../routing/useRoute";
export function StatsPage({ session }: { session: WebIncidentSession }) {
  const [start, setStart] = useState(() =>
    seoulDate(new Date(Date.now() - 29 * 86400000)),
  );
  const [end, setEnd] = useState(() => seoulDate());
  const [region, setRegion] = useState("");
  const [camera, setCamera] = useState("");
  const [confirmed, setConfirmed] = useState(true);
  const [revision, setRevision] = useState(0);
  const cameras = useOperations<Cctv[]>(session, "/api/cctvs");
  const params = new URLSearchParams({
    start,
    end,
    confirmed_only: String(confirmed),
  });
  if (region) params.set("region_code", region);
  if (camera) params.set("cctv_id", camera);
  const validPeriod =
    !!start &&
    !!end &&
    start <= end &&
    new Date(end).getTime() - new Date(start).getTime() <= 365 * 86400000;
  const { data, error, loading } = useOperations<Stats>(
    session,
    validPeriod ? `/api/stats?${params}` : null,
    revision,
  );
  const typeKeys = Array.from(
    new Set([
      ...Object.keys(hazardLabels),
      ...Object.keys(data?.by_hazard ?? {}),
    ]),
  );
  const maxType = Math.max(1, ...Object.values(data?.by_hazard ?? {}));
  const types = typeKeys.map(
    (key) =>
      [
        hazardLabel(key),
        data?.by_hazard[key] ?? 0,
        ((data?.by_hazard[key] ?? 0) / maxType) * 100,
      ] as const,
  );
  const bins = ["0-50", "50-70", "70-90", "90-100", "UNKNOWN"];
  const confidence = bins.map(
    (key) =>
      [
        key === "UNKNOWN"
          ? "범위 확인 필요"
          : key === "90-100"
            ? "90~100%"
            : key.replace("-", "~") + "% 미만",
        data?.confidence_distribution[key] ?? 0,
        `${((data?.confidence_distribution[key] ?? 0) / (data?.total_incident_count || 1)) * 100}%`,
      ] as const,
  );
  const daily = data?.daily ?? [];
  const maxDaily = Math.max(1, ...daily.map((point) => point.count));
  const x = (index: number) =>
    daily.length <= 1 ? 285 : 60 + (index * 450) / (daily.length - 1);
  const y = (count: number) => 220 - (count / maxDaily) * 165;
  const summary: [string, string | number, string][] = [
    ["조회 사건", data?.total_incident_count ?? "–", "건"],
    ["확정 사건", data?.confirmed_incident_count ?? "–", "건"],
    ["P1 사건", data ? (data.by_priority.P1 ?? 0) : "–", "건"],
    [
      "평균 탐지 신뢰도",
      data?.average_confidence == null
        ? "–"
        : (data.average_confidence * 100).toFixed(1),
      "%",
    ],
  ];
  return (
    <div className="w05-stats">
      <div className="inline-filter">
        <label>
          시작일
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          종료일
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        <label>
          지역
          <select
            value={region}
            onChange={(e) => {
              setRegion(e.target.value);
              setCamera("");
            }}
          >
            <option value="">전체 지역</option>
            {Array.from(
              new Map(
                (cameras.data ?? [])
                  .filter((c) => c.region_code)
                  .map((c) => [
                    c.region_code!,
                    `${c.sido_name ?? ""} ${c.sigungu_name ?? c.region_code}`,
                  ]),
              ).entries(),
            ).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          CCTV
          <select
            aria-label="CCTV"
            value={camera}
            onChange={(e) => setCamera(e.target.value)}
          >
            <option value="">전체 CCTV</option>
            {cameras.data
              ?.filter((c) => !region || c.region_code === region)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          집계 범위
          <select
            value={String(confirmed)}
            onChange={(e) => setConfirmed(e.target.value === "true")}
          >
            <option value="true">확정 사건</option>
            <option value="false">전체 상태 (오탐 포함)</option>
          </select>
        </label>
        <button className="secondary" onClick={() => setRevision((v) => v + 1)}>
          다시 조회
        </button>
      </div>
      <p className="stats-scope">
        {start} ~ {end} (한국시간 · 양 끝 날짜 포함) ·{" "}
        {confirmed ? "CONFIRMED / SENT / RESOLVED" : "전체 사건 상태"} · 최초
        탐지 시각 기준, 사건당 1건
      </p>
      {!validPeriod && (
        <p role="alert">날짜 순서와 조회 범위(최대 366일)를 확인해주세요.</p>
      )}
      {loading && <p role="status">통계 조회 중</p>}
      {error && <p role="alert">{error}</p>}
      {cameras.error && (
        <p role="alert">CCTV·지역 필터 목록을 불러오지 못했습니다.</p>
      )}
      {data?.total_incident_count === 0 && (
        <p role="status">선택한 기간과 조건의 사건이 없습니다.</p>
      )}
      <div className="stat-grid">
        {summary.map(([title, value, unit], i) =>
          i < 3 ? (
            <button
              className="panel stat-card"
              key={title}
              onClick={() => go("incidents")}
            >
              <span>{title}</span>
              <strong>
                {value}
                <small>{unit}</small>
              </strong>
            </button>
          ) : (
            <div className="panel stat-card" key={title}>
              <span>{title}</span>
              <strong>
                {value}
                <small>{unit}</small>
              </strong>
              <p className="metric-note">모델 탐지 점수 · 실제 정탐률과 다름</p>
            </div>
          ),
        )}
      </div>
      <Panel title="유형별 사건 수">
        <div className="stats-columns">
          {types.map(([name, count, height]) => (
            <button
              key={name}
              className="stats-column"
              onClick={() => go("incidents")}
            >
              <span className="stats-column-track">
                <i style={{ height: `${height}%` }}>
                  <b>{data ? count : "–"}</b>
                </i>
              </span>
              <span>{name}</span>
            </button>
          ))}
        </div>
      </Panel>
      <div className="two-col equal">
        <Panel title="탐지 신뢰도 분포">
          <div
            className="confidence-stack"
            aria-label="탐지 신뢰도 구간별 분포"
          >
            {confidence.map(([label, count, width], i) => (
              <i
                key={label}
                className={"confidence-bin bin-" + i}
                style={{ width }}
                title={label + ": " + count}
              />
            ))}
          </div>
          <dl>
            {confidence.map(([label, count], i) => (
              <Pair
                key={label}
                label={label}
                value={
                  <>
                    <span className={"confidence-key bin-" + i} />
                    {data ? count : "–"}
                  </>
                }
              />
            ))}
          </dl>
          <p className="content-footnote">
            조회 사건 {data?.total_incident_count ?? "–"}건의 저장된 탐지 점수
            기준
            <br />
            현장 정·오탐 판정이나 모델 성능 평가 지표가 아닙니다.
          </p>
        </Panel>
        <Panel title="일별 사건 추이">
          <svg
            className="daily-chart"
            viewBox="0 0 560 270"
            role="img"
            aria-label="선택 기간 한국시간 날짜별 사건 수"
          >
            <text x="14" y="20" fill="#9bafc0" fontSize="12">
              사건 수 (건)
            </text>
            {Array.from(new Set([0, Math.ceil(maxDaily / 2), maxDaily])).map(
              (count) => (
                <g key={count}>
                  <line
                    x1="48"
                    x2="525"
                    y1={y(count)}
                    y2={y(count)}
                    stroke="#91cce01d"
                  />
                  <text
                    x="35"
                    y={y(count) + 4}
                    textAnchor="end"
                    fill="#9bafc0"
                    fontSize="12"
                  >
                    {count}
                  </text>
                </g>
              ),
            )}
            <polyline
              points={daily
                .map((point, i) => `${x(i)},${y(point.count)}`)
                .join(" ")}
              fill="none"
              stroke="#69d5e7"
              strokeWidth="3"
              strokeLinejoin="round"
            />
            {daily.map((point, i) => (
              <g key={point.day}>
                <circle cx={x(i)} cy={y(point.count)} r="4" fill="#9be9f3">
                  <title>
                    {point.day}: {point.count}건
                  </title>
                </circle>
                <text
                  x={x(i)}
                  y={y(point.count) - 12}
                  fill="#dcf6ff"
                  textAnchor="middle"
                  fontSize="12"
                >
                  {daily.length <= 14 ? point.count : ""}
                </text>
                <text
                  x={x(i)}
                  y="246"
                  textAnchor="middle"
                  fill="#9bafc0"
                  fontSize="12"
                >
                  {i % Math.max(1, Math.ceil(daily.length / 6)) === 0 ||
                  i === daily.length - 1
                    ? point.day.slice(5)
                    : ""}
                </text>
              </g>
            ))}
            <text x="525" y="265" textAnchor="end" fill="#9bafc0" fontSize="11">
              날짜
            </text>
          </svg>
        </Panel>
      </div>
      <div className="two-col equal">
        <Panel title="상태별 사건 수">
          <dl>
            {[
              "DETECTED",
              "CONFIRMED",
              "SENT",
              "RESOLVED",
              "FALSE_POSITIVE",
            ].map((key) => (
              <Pair
                key={key}
                label={statusLabel(key)}
                value={data ? (data.by_status[key] ?? 0) : "–"}
              />
            ))}
          </dl>
        </Panel>
        <Panel title="위험도 · 우선순위">
          <dl>
            {["HIGH", "MEDIUM", "LOW", "UNASSESSED"].map((key) => (
              <Pair
                key={key}
                label={`위험도 · ${statusLabel(key)}`}
                value={data ? (data.by_risk[key] ?? 0) : "–"}
              />
            ))}
            {["P1", "P2", "P3", "UNASSESSED"].map((key) => (
              <Pair
                key={key}
                label={`우선순위 · ${statusLabel(key)}`}
                value={data ? (data.by_priority[key] ?? 0) : "–"}
              />
            ))}
          </dl>
        </Panel>
      </div>
      <Panel title="시간대별 사건 수 · 한국시간">
        <div className="hourly-bars">
          {(data?.hourly ?? []).map((point) => (
            <div key={point.hour} title={`${point.hour}시: ${point.count}건`}>
              <span>{point.count}</span>
              <i
                style={{
                  height: `${(point.count / Math.max(1, ...data!.hourly.map((p) => p.count))) * 110}px`,
                }}
              />
              <small>{point.hour}</small>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
