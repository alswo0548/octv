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
        시연 기준일 {mock.uiSnapshot.header.date} · 확정 사건 기준 · 전달 여부는
        사건 단위로 집계
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
        <Panel title="현재 CCTV 상태">
          <dl>
            {mock.stats.cctv.map(([k, v]) => (
              <Pair key={k} label={k} value={v} />
            ))}
          </dl>
          <button className="text-button" onClick={() => go("monitor")}>
            연결 오류 CCTV 확인 →
          </button>
          <p className="content-footnote">
            지역·CCTV 선택 표시만 변경됩니다. 통계는 고정 목업입니다.
          </p>
        </Panel>
      </div>
    </div>
  );
}
