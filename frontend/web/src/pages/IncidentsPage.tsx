import { useState } from "react";
import {
  mock,
  incidentById,
  agencyById,
  recommendedRouteFor,
  recommendationsFor,
  supportRequestsFor,
  type Incident,
} from "@octv/shared";
import {
  Badge,
  Pair,
  Select,
  Segments,
  Pagination,
  type ShowModal,
} from "../components/Primitives";
import { Camera } from "../components/Camera";
import { RoadIcon } from "../components/RoadIcon";
import { type AgencyUI } from "../components/AgencyPicker";
import { go } from "../routing/useRoute";
export function IncidentsPage({
  incident: d,
  select,
  state,
  set,
  show,
}: {
  incident: Incident;
  select: (id: string) => void;
  state: AgencyUI;
  set: (value: AgencyUI) => void;
  show: ShowModal;
}) {
  const [page, setPage] = useState(0);
  const rows = mock.webIncidentIds.slice(page * 5, page * 5 + 5);
  const a = agencyById(state.viewing),
    r = recommendedRouteFor(d.id, a.id);
  const requests = supportRequestsFor(d.id),
    latest = requests[0];
  return (
    <>
      <section className="panel list-panel">
        <div className="section-title">
          <h2>
            확정 사건 목록{" "}
            <span className="count">{mock.uiSnapshot.incidentCount}</span>
          </h2>
          <span className="subtle">서울특별시 · 탐지 시각 기준</span>
        </div>
        <div className="filters">
          <div className="priority-filter">
            <label>우선순위</label>
            <Segments options={["전체", "P1", "P2", "P3"]} />
          </div>
          <Select
            label="상태"
            options={["상태 전체", "전달 완료", "사건 확인", "탐지됨"]}
          />
          <Select
            label="유형"
            options={[
              "유형 전체",
              "도로 침수",
              "쓰러진 나무",
              "시설물 파손",
              "도로 장애물",
            ]}
          />
          <Select label="기간" options={["오늘", "최근 7일", "전체 기간"]} />
          <label>
            검색
            <input placeholder="사건번호 / 위치 검색" />
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "사건번호",
                  "유형",
                  "우선순위",
                  "상태",
                  "위치",
                  "발생시각",
                ].map((t) => (
                  <th key={t}>{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((id) => {
                const row = incidentById(id);
                return (
                  <tr
                    tabIndex={0}
                    key={id}
                    className={d.id === id ? "selected" : ""}
                    onClick={() => select(id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") select(id);
                    }}
                    aria-label={id + " 상세 보기"}
                  >
                    <td>{id}</td>
                    <td>{row.type}</td>
                    <td>
                      <Badge priority={row.priority} />
                    </td>
                    <td>
                      <span className="status">{row.status}</span>
                    </td>
                    <td>{row.location}</td>
                    <td>09.23 {row.time}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Pagination
          page={page}
          onChange={setPage}
          total={mock.webIncidentIds.length}
        />
      </section>
      <section className="selected-heading">
        <div>
          <span className="eyebrow">SELECTED INCIDENT</span>
          <h2>
            {d.type} · {d.id} <Badge priority={d.priority} />
          </h2>
        </div>
        <span className="subtle">
          {d.location} · {d.date}
        </span>
      </section>
      <div className="detail-grid">
        <section className="panel camera-panel">
          <Camera
            incident={d}
            onExpand={() =>
              show({
                title: "CCTV 확대 · " + d.camera,
                body: <Camera incident={d} />,
                cancel: "",
              })
            }
          />
          <div className="camera-caption">
            <span>대상 탐지 · 추적 중</span>
          </div>
          <button
            className="primary camera-live-button"
            onClick={() => go("monitor/" + d.camera)}
          >
            실시간 CCTV 영상
          </button>
        </section>
        <section className="panel info">
          <div className="section-title">
            <h2>사건 정보</h2>
            <span className="tag">{d.statusCode}</span>
          </div>
          <dl>
            <Pair label="CCTV" value={d.camera} />
            <Pair label="위치" value={d.location} />
            <Pair label="최초 / 최근 탐지" value={`${d.time} / ${d.time}`} />
            <Pair label="상태" value={d.status} />
          </dl>
          <div className="analysis-note">
            <span>AI DETECTION</span>
            <div>
              <strong>
                {d.confidence}
                <small>%</small>
              </strong>
              <div className="confidence-track">
                <i style={{ width: d.confidence + "%" }} />
              </div>
            </div>
            <small>모델 탐지 신뢰도</small>
          </div>
        </section>
        <section className="panel risk">
          <div className="section-title">
            <h2>위험도 · 우선순위</h2>
          </div>
          <div className="scores">
            <div>
              <label>
                위험도 <span>{d.riskLabel}</span>
              </label>
              <strong>
                {d.risk}
                <small> / 100</small>
              </strong>
              <div className="bar red">
                <i style={{ width: d.risk + "%" }} />
              </div>
            </div>
            <div>
              <label>
                대응 우선순위 <span>{d.priority}</span>
              </label>
              <strong>
                {d.score}
                <small> / 100</small>
              </strong>
              <div className="bar blue">
                <i style={{ width: d.score + "%" }} />
              </div>
            </div>
          </div>
          <div className="reasons">
            <span>주요 근거</span>
            <div>
              {d.reasons.map((x) => (
                <span key={x}>{x}</span>
              ))}
            </div>
          </div>
        </section>
        <section className="panel external">
          <div className="section-title">
            <h2>외부 상황</h2>
            <span className="subtle">{d.time} 수집</span>
          </div>
          <div className="weather">
            <div>
              <span className="weather-icon">☂</span>
              <div>
                <label>강수량</label>
                <strong>
                  {d.rain}
                  <small> mm</small>
                </strong>
              </div>
            </div>
            <div>
              <span className="weather-icon">≋</span>
              <div>
                <label>수위</label>
                <strong>
                  {d.water}
                  <small> m</small>
                </strong>
              </div>
            </div>
          </div>
          <div className="external-row">
            <span>교통 통제</span>
            <b>{d.traffic}</b>
          </div>
          <div className="external-row">
            <span>인근 주요 시설</span>
            <b>{d.facility}</b>
          </div>
        </section>
      </div>
      <section className="panel incident-routes">
        <button className="primary" onClick={() => go("routes/" + d.id)}>
          경로 비교 상세 <RoadIcon />
        </button>
        <div
          className="agency-tabs"
          role="tablist"
          aria-label="현재 경로 조회 기관"
        >
          {recommendationsFor(d.id).map((rec) => {
            const agency = agencyById(rec.agencyId);
            return (
              <button
                role="tab"
                key={agency.id}
                aria-selected={state.viewing === agency.id}
                onClick={() => set({ ...state, viewing: agency.id })}
              >
                {agency.name}
                <small>기관 추천 {rec.rank}순위</small>
              </button>
            );
          })}
        </div>
        <div className="route-panel route-summary">
          <div className="route-title">
            <span className="route-symbol">
              <RoadIcon />
            </span>
            <div>
              <h2>출동 및 접근 경로</h2>
              <small>후보 기관별 추천 · 최종 출동 판단은 기관에서 진행</small>
            </div>
          </div>
          {r ? (
            <div className="route-data">
              <span className="recommend">추천 {r.id}</span>
              <div>
                <strong>
                  {r.minutes}
                  <small>분</small>
                </strong>
                <span>예상 소요</span>
              </div>
              <div>
                <strong>
                  {r.distance}
                  <small>km</small>
                </strong>
                <span>이동 거리</span>
              </div>
              <div className="agency">
                <b>{a.name}</b>
                <span>현재 경로 조회 기관</span>
              </div>
            </div>
          ) : (
            <p>이용 가능한 추천경로가 없습니다.</p>
          )}
        </div>
      </section>
      <section className="panel support-panel">
        <div className="section-title">
          <h2>현장 상황 · 추가 지원요청</h2>
        </div>
        {latest ? (
          <div className="support-summary-row">
            <div>
              <span className="status check">추가 지원 필요</span>
              <h3>{latest.title}</h3>
              <p>{latest.message}</p>
              <p>
                {latest.agency} · {latest.requester} · {latest.time}
              </p>
            </div>
            <button
              className="secondary"
              onClick={() =>
                show({
                  title: "추가 지원요청 목록 · " + d.id,
                  body: (
                    <ol className="support-request-list">
                      {requests.map((request) => (
                        <li key={request.id}>
                          <h3>{request.title}</h3>
                          <p>{request.message}</p>
                          <p className="subtle">
                            {request.agency} · {request.requester} ·{" "}
                            <time dateTime={request.requestedAt}>
                              {request.time}
                            </time>
                          </p>
                        </li>
                      ))}
                    </ol>
                  ),
                  cancel: "",
                })
              }
            >
              요청 내용 확인
            </button>
          </div>
        ) : (
          <p className="subtle">접수된 추가 지원요청이 없습니다.</p>
        )}
        <p className="content-footnote">
          대응완료 보고·사건 종결은 기관의 기존 체계에서 진행합니다.
        </p>
      </section>
    </>
  );
}
