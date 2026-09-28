import { mock } from "@octv/shared";
import { Panel, Pair, Select } from "../components/Primitives";
import { go } from "../routing/useRoute";
export function StatsPage() {
  return (
    <div className="w05-stats">
      <div className="inline-filter">
        <Select label="기간" options={["최근 30일", "오늘"]} />
        <Select label="지역" options={["지역 전체", "강남구", "구리시"]} />
        <Select label="CCTV" options={["전체 CCTV", "CCTV-012", "CCTV-023"]} />
      </div>
      <p className="stats-scope">
        기준일 {mock.uiSnapshot.header.date} · 확정 사건 기준 · 전달 여부는 사건
        단위로 집계
      </p>
      <div className="stat-grid">
        {mock.stats.summary.map(([title, value, unit], i) =>
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
      <Panel title="유형별 확정 사건 수">
        <div className="stats-columns">
          {mock.stats.types.map(([name, count, height]) => (
            <button
              key={name}
              className="stats-column"
              onClick={() => go("incidents")}
            >
              <span className="stats-column-track">
                <i style={{ height: `${height}%` }}>
                  <b>{count}</b>
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
            {mock.stats.confidence.map(([label, count, width], i) => (
              <i
                key={label}
                className={"confidence-bin bin-" + i}
                style={{ width }}
                title={label + ": " + count}
              />
            ))}
          </div>
          <dl>
            {mock.stats.confidence.map(([label, count], i) => (
              <Pair
                key={label}
                label={label}
                value={
                  <>
                    <span className={"confidence-key bin-" + i} />
                    {count}
                  </>
                }
              />
            ))}
          </dl>
          <p className="content-footnote">
            확정 사건 {mock.stats.summary[0][1]}건의 저장된 탐지 점수 기준
            <br />
            현장 정·오탐 판정이나 모델 성능 평가 지표가 아닙니다.
          </p>
        </Panel>
        <Panel title="일별 확정 추이">
          <svg
            className="daily-chart"
            viewBox="0 0 560 270"
            role="img"
            aria-label="최근 7일 날짜별 확정 사건 수 선 그래프"
          >
            <text x="14" y="20" fill="#9bafc0" fontSize="12">
              확정 사건 수 (건)
            </text>
            {[0, 4, 8, 12].map((count) => (
              <g key={count}>
                <line
                  x1="48"
                  x2="525"
                  y1={220 - count * 15}
                  y2={220 - count * 15}
                  stroke="#91cce01d"
                />
                <text
                  x="35"
                  y={224 - count * 15}
                  textAnchor="end"
                  fill="#9bafc0"
                  fontSize="12"
                >
                  {count}
                </text>
              </g>
            ))}
            <polyline
              points={mock.stats.dailyConfirmed
                .map((point, i) => `${60 + i * 76},${220 - point.count * 15}`)
                .join(" ")}
              fill="none"
              stroke="#69d5e7"
              strokeWidth="3"
              strokeLinejoin="round"
            />
            {mock.stats.dailyConfirmed.map((point, i) => (
              <g key={point.date}>
                <circle
                  cx={60 + i * 76}
                  cy={220 - point.count * 15}
                  r="4"
                  fill="#9be9f3"
                >
                  <title>
                    {point.date}: {point.count}건
                  </title>
                </circle>
                <text
                  x={60 + i * 76}
                  y={208 - point.count * 15}
                  fill="#dcf6ff"
                  textAnchor="middle"
                  fontSize="12"
                >
                  {point.count}
                </text>
                <text
                  x={60 + i * 76}
                  y="246"
                  textAnchor="middle"
                  fill="#9bafc0"
                  fontSize="12"
                >
                  {point.date}
                </text>
              </g>
            ))}
            <text x="525" y="265" textAnchor="end" fill="#9bafc0" fontSize="11">
              날짜
            </text>
          </svg>
        </Panel>
      </div>
    </div>
  );
}
