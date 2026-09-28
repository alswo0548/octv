import { useState } from "react";
import { mock, incidentById } from "@octv/shared";
import { Badge, Panel, Pair } from "../components/Primitives";
import { RoadMap } from "../components/RoadMap";
import { go } from "../routing/useRoute";

export function OverviewPage({ select }: { select: (id: string) => void }) {
  const [page, setPage] = useState(0);
  const pages = Math.ceil(mock.overviewIds.length / 5);
  const visibleIds = mock.overviewIds.slice(page * 5, page * 5 + 5);
  const d = incidentById(visibleIds[0]);
  const openIncident = (id: string) => {
    select(id);
    go("incidents");
  };
  return (
    <>
      <div className="stat-grid">
        {mock.uiSnapshot.overviewCards.map(([t, n, u, path]) => (
          <button className="panel stat-card" key={t} onClick={() => go(path)}>
            <span>{t}</span>
            <strong>
              {n}
              <small>{u}</small>
            </strong>
          </button>
        ))}
      </div>
      <div className="two-col overview-layout">
        <Panel title="사건 지도 · 우선순위별 현황">
          <RoadMap
            incident={d}
            overview
            incidentIds={visibleIds}
            onIncident={openIncident}
          />
          <p className="type-caption">
            마커를 선택하면 해당 사건의 상세정보로 이동합니다.
          </p>
        </Panel>
        <Panel
          title="긴급 사건 / P1 우선"
          className="overview-list-panel"
          action={
            <button className="text-button" onClick={() => go("incidents")}>
              전체 사건 보기 →
            </button>
          }
        >
          <div className="overview-incident-list">
            {visibleIds.map((id) => {
              const row = incidentById(id);
              return (
                <button
                  className="incident-card"
                  key={id}
                  onClick={() => openIncident(id)}
                >
                  <div className="incident-card-top">
                    <Badge priority={row.priority} />
                    <span className="subtle">{row.time}</span>
                  </div>
                  <h3>
                    {row.type} · {id}
                  </h3>
                  <p>{row.location}</p>
                </button>
              );
            })}
          </div>
          <nav
            className="pagination overview-pagination"
            aria-label="통합관제 사건 페이지"
          >
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>
              이전
            </button>
            {Array.from({ length: pages }, (_, i) => (
              <button
                key={i}
                aria-current={page === i ? "page" : undefined}
                className={page === i ? "current" : ""}
                onClick={() => setPage(i)}
              >
                {i + 1}
              </button>
            ))}
            <button
              disabled={page === pages - 1}
              onClick={() => setPage(page + 1)}
            >
              다음
            </button>
          </nav>
        </Panel>
      </div>
      <Panel title="외부 상황">
        <div className="weather-alert info-strip">
          <span>☂</span>
          <div>
            <strong>{mock.uiSnapshot.weather.title}</strong>
            <p>{mock.uiSnapshot.weather.summary}</p>
          </div>
        </div>
        <dl>
          <Pair label="강수량 / 수위" value={`${d.rain} mm / ${d.water} m`} />
          <Pair label="도로 통제" value={d.traffic} />
          <Pair
            label="특보 감시 CCTV"
            value={mock.uiSnapshot.weather.watchCount}
          />
          <Pair label="최근 수집" value={mock.uiSnapshot.weather.collectedAt} />
        </dl>
        <div className="quick-links">
          <button className="secondary" onClick={() => go("monitor")}>
            CCTV 상태 확인
          </button>
          <button className="primary" onClick={() => go("settings")}>
            감시 설정
          </button>
        </div>
      </Panel>
    </>
  );
}
