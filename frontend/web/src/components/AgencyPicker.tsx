import { useEffect, useRef } from "react";
import {
  agencyById,
  recommendationsFor,
  routesFor,
  type Incident,
} from "@octv/shared";
import { type ShowModal } from "./Primitives";
import { go } from "../routing/useRoute";
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
  incident,
  state,
  open,
  show,
}: {
  incident: Incident;
  state: AgencyUI;
  open: () => void;
  show: ShowModal;
}) {
  return (
    <div className="panel agency-entry">
      <AgencySummary state={state} />
      <div className="action-row">
        <button className="secondary" onClick={open}>
          대응기관 선택
        </button>
        <button
          className="primary"
          disabled={!state.checked.length}
          onClick={() =>
            show({
              title: "전달 정보 확인",
              body: (
                <>
                  <strong>
                    {incident.id} · {incident.type}
                  </strong>
                  <p>
                    {incident.location} · 위험도 {incident.risk} ·{" "}
                    {incident.priority}
                  </p>
                  {state.checked.map((id) => (
                    <section className="delivery-agency" key={id}>
                      <h3>{agencyById(id).name}</h3>
                      {routesFor(incident.id, id).map((r) => (
                        <p key={r.id}>
                          경로 {r.id} · {r.distance} km / {r.minutes}분 ·{" "}
                          {r.verdict}
                        </p>
                      ))}
                    </section>
                  ))}
                  <p className="demo-note">
                    전달 확인 UI입니다. 확인하면 닫히며 사건 상태는 변경되지
                    않습니다.
                  </p>
                </>
              ),
              confirm: "확인 (미리보기)",
            })
          }
        >
          선택 기관에 전달
        </button>
      </div>
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
      aria-label="대응기관 선택"
      onCancel={close}
    >
      <div className="modal-head">
        <div>
          <span className="eyebrow">{incident.id} · 대응기관 추천</span>
          <h2>대응기관 선택</h2>
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
              <button
                className="text-button"
                onClick={() => {
                  set({ ...state, viewing: a.id });
                  close();
                  go("routes/" + incident.id);
                }}
              >
                {a.name} 경로 조회 ↗
              </button>
            </section>
          );
        })}
      </div>
      <AgencySummary state={state} />
      <p className="agency-help">선택 표시는 현재 미리보기에서만 유지됩니다.</p>
      <div className="confirm-actions">
        <button className="secondary" onClick={close}>
          선택 유지하고 닫기
        </button>
        <button
          className="primary"
          disabled={!state.checked.length}
          onClick={() => {
            set({ ...state, viewing: state.checked[0] });
            close();
            go("routes/" + incident.id);
          }}
        >
          선택 기관 경로 확인
        </button>
      </div>
    </dialog>
  );
}
