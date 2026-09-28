import { useEffect, useRef } from "react";
import {
  agencyById,
  recommendationsFor,
  routesFor,
  type Incident,
} from "@octv/shared";
export type AgencyUI = { viewing: string; checked: string[] };
export function AgencySummary({ state }: { state: AgencyUI }) {
  return (
    <div className="agency-summary">
      <strong>선택 기관 {state.checked.length}곳</strong>
      <span>
        {state.checked.length
          ? state.checked.map((id) => agencyById(id).name).join(" · ")
          : "전달할 기관을 선택해주세요"}
      </span>
    </div>
  );
}
export function AgencyEntry({
  state,
  open,
}: {
  state: AgencyUI;
  open: () => void;
}) {
  return (
    <div className="panel agency-entry">
      <AgencySummary state={state} />
      <button className="primary" onClick={open}>
        기관 선택·전달
      </button>
    </div>
  );
}
export function AgencyPicker({
  incident,
  state,
  set,
  close,
}: {
  incident: Incident;
  state: AgencyUI;
  set: (x: AgencyUI) => void;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      id="agency-dialog"
      aria-label="기관 선택·전달"
      onCancel={close}
    >
      <div className="modal-head">
        <div>
          <span className="eyebrow">{incident.id} · 대응기관 추천</span>
          <h2>기관 선택·전달</h2>
        </div>
        <button className="close" aria-label="기관 선택 닫기" onClick={close}>
          ×
        </button>
      </div>
      <p className="agency-help">
        전달 대상은 복수 선택할 수 있습니다. 경로 조회와 전달 대상 체크는
        별개입니다.
      </p>
      <div className="agency-picker-list">
        {recommendationsFor(incident.id).map((rec) => {
          const a = agencyById(rec.agencyId),
            r = routesFor(incident.id, a.id)[0];
          return (
            <section
              className={
                "agency-card " + (state.checked.includes(a.id) ? "chosen" : "")
              }
              key={a.id}
            >
              <label className="agency-check">
                <input
                  type="checkbox"
                  checked={state.checked.includes(a.id)}
                  onChange={(e) =>
                    set({
                      ...state,
                      checked: e.target.checked
                        ? [...state.checked, a.id]
                        : state.checked.filter((id) => id !== a.id),
                    })
                  }
                  aria-label={a.name + " 전달 대상"}
                />
                <span>
                  <span className="rank">
                    기관 추천 {rec.rank}순위 · {a.type}
                  </span>
                  <strong>{a.name}</strong>
                </span>
              </label>
              <p>
                예상 {r.distance} km · {r.minutes}분
              </p>
              <p>{rec.reason}</p>
              <details className="agency-route-details">
                <summary>후보 경로 3개 확인</summary>
                {routesFor(incident.id, a.id).map((route) => (
                  <p key={route.id}>
                    경로 {route.id} · {route.distance} km / {route.minutes}분 ·{" "}
                    {route.verdict}
                    <br />
                    {route.reason}
                  </p>
                ))}
              </details>
            </section>
          );
        })}
      </div>
      <AgencySummary state={state} />

      <div className="confirm-actions">
        <button className="secondary" onClick={close}>
          닫기
        </button>
        <button
          className="primary"
          disabled={!state.checked.length}
          onClick={close}
        >
          선택 기관에 전달
        </button>
      </div>
    </dialog>
  );
}
