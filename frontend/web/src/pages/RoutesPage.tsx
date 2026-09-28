import { useState } from "react";
import {
  recommendationsFor,
  agencyById,
  routesFor,
  type Incident,
} from "@octv/shared";
import { AgencyEntry, type AgencyUI } from "../components/AgencyPicker";
import { Badge, type ShowModal } from "../components/Primitives";
import { RoadMap } from "../components/RoadMap";
import { go } from "../routing/useRoute";
export function RoutesPage({
  incident: d,
  state,
  set,
  open,
}: {
  incident: Incident;
  state: AgencyUI;
  set: (s: AgencyUI) => void;
  open: () => void;
}) {
  const [active, setActive] = useState("A"),
    recs = recommendationsFor(d.id),
    index = recs.findIndex((x) => x.agencyId === state.viewing),
    a = agencyById(state.viewing);
  return (
    <>
      <a className="back-link" href="#/incidents">
        ‹ 사건관리
      </a>
      <div className="page-heading">
        <div>
          <h2>
            {d.id} · {d.type} <Badge priority={d.priority} />
          </h2>
          <p>
            {d.location} · {d.camera}
          </p>
        </div>
      </div>
      <h2>기관별 추천경로</h2>
      <AgencyEntry state={state} open={open} />
      <div
        className="agency-tabs"
        role="tablist"
        aria-label="현재 경로 조회 기관"
      >
        {recs.map((rec) => {
          const x = agencyById(rec.agencyId);
          return (
            <button
              role="tab"
              key={x.id}
              aria-selected={a.id === x.id}
              onClick={() => {
                set({ ...state, viewing: x.id });
                setActive("A");
              }}
            >
              {x.name}
              <small
                className={state.checked.includes(x.id) ? "recipient-tag" : ""}
              >
                {state.checked.includes(x.id)
                  ? "전달 대상으로 선택됨"
                  : "경로 조회만 · 전달 대상 아님"}
              </small>
            </button>
          );
        })}
      </div>
      <p className="agency-origin">
        현재 조회: <strong>{a.name}</strong> → {d.location}
      </p>
      <RoadMap incident={d} index={index} active={active} onRoute={setActive} />
      <section className="panel page-section section-gap">
        <div className="table-scroll">
          <table className="route-table">
            <caption>후보 경로 · {a.name}</caption>
            <thead>
              <tr>
                {[
                  "후보",
                  "거리 / 시간",
                  "총점",
                  "추천 근거 및 선택 정보",
                  "판정",
                ].map((x) => (
                  <th key={x}>{x}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {routesFor(d.id, a.id).map((r) => (
                <tr
                  key={r.id}
                  tabIndex={0}
                  role="button"
                  aria-label={"경로 " + r.id + " 확인"}
                  aria-pressed={active === r.id}
                  className={
                    (active === r.id ? "chosen " : "") +
                    (r.blocked ? "blocked" : "")
                  }
                  onClick={() => setActive(r.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setActive(r.id);
                  }}
                >
                  <td>
                    <b>{r.id}</b>{" "}
                    {active === r.id && (
                      <span className="selected-label">조회 중</span>
                    )}
                  </td>
                  <td>
                    {r.distance} km / {r.minutes}분
                  </td>
                  <td>{r.score}</td>
                  <td>{r.reason}</td>
                  <td>{r.verdict}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="route-feedback">
          지도 강조 {active} ·{" "}
          {routesFor(d.id, a.id).find((route) => route.id === active)?.verdict}
        </p>
      </section>
      <button className="secondary" onClick={() => go("incidents")}>
        사건관리로 돌아가기
      </button>
    </>
  );
}
