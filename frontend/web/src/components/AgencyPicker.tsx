/**
 * 기관 선택 창: 연결 전에는 기존 화면을 미리보기로 표시하고 실제 전달을 막습니다.
 * 인증·사건 담당이 delivery.ts에 실제 세션을 연결하면 서버 사건과 추천 기관만 표시합니다.
 * 선택 기관 전달 → DB 저장 결과·Push 작업 등록 상태 표시 → 필요시 목록 재조회 순서입니다.
 * 실제 전달 결과를 상위의 예시 사건·지도·기관 선택 상태에 섞어 반영하지 않습니다.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  agencyById,
  recommendationsFor,
  routesFor,
  type Incident,
} from "@octv/shared";
import {
  deliverToAgencies,
  deliveryErrorMessage,
  getDeliveryContext,
  loadDeliverySnapshot,
  pushStatusLabels,
  subscribeDeliveryContext,
  type DeliveryContext,
  type DeliveryResult,
  type DeliverySnapshot,
} from "../delivery";
export type AgencyUI = { viewing: string; checked: string[] };
// 기존 샘플 화면의 체크 요약이며 실제 서버의 전달 상태로 사용하지 않습니다.
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
// 실제 연결 여부를 안내하고 같은 기관 선택 창을 엽니다. 로그인 화면은 만들지 않습니다.
export function AgencyEntry({
  state,
  open,
}: {
  state: AgencyUI;
  open: () => void;
}) {
  const context = useSyncExternalStore(
    subscribeDeliveryContext,
    getDeliveryContext,
    () => null,
  );
  return (
    <div className="panel agency-entry">
      {context ? (
        <div className="agency-summary">
          <strong>서버 사건 연결됨</strong>
          <span>실제 전달 창에서 사건번호와 기관을 확인해 주세요.</span>
        </div>
      ) : (
        <AgencySummary state={state} />
      )}
      <button className="primary" onClick={open}>
        기관 선택·전달
      </button>
    </div>
  );
}
// 세션 변경 시 실제 창을 새로 구성하여 이전 사용자의 결과·선택을 즉시 제거합니다.
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
  const context = useSyncExternalStore(
    subscribeDeliveryContext,
    getDeliveryContext,
    () => null,
  );
  useEffect(() => {
    if (ref.current && !ref.current.open) ref.current.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      id="agency-dialog"
      aria-label="기관 선택·전달"
      onCancel={close}
    >
      {context ? (
        <LiveDeliveryPicker
          key={context.version}
          context={context}
          close={close}
        />
      ) : (
        <PreviewDeliveryPicker
          incident={incident}
          state={state}
          set={set}
          close={close}
        />
      )}
    </dialog>
  );
}

// 기존 샘플 기관은 미리보기로만 유지합니다. mock ID를 실제 요청에 넣는 경로는 없습니다.
function PreviewDeliveryPicker({
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
  return (
    <>
      <div className="modal-head">
        <div>
          <span className="eyebrow">{incident.id} · 대응기관 추천</span>
          <h2>기관 선택·전달</h2>
        </div>
        <button className="close" aria-label="기관 선택 닫기" onClick={close}>
          ×
        </button>
      </div>
      <p className="agency-help" role="status">
        현재는 화면 미리보기입니다. 실제 로그인 정보와 서버 사건이 연결되면 추천
        기관을 조회하고 전달할 수 있습니다.
      </p>
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
          disabled
          title="실제 로그인 정보와 서버 사건 연결이 필요합니다."
        >
          선택 기관에 전달
        </button>
      </div>
    </>
  );
}

// 실제 세션으로 확인한 사건·기관만 선택하며 전송 중복과 늦은 화면 업데이트를 막습니다.
function LiveDeliveryPicker({
  context,
  close,
}: {
  context: DeliveryContext;
  close: () => void;
}) {
  const [snapshot, setSnapshot] = useState<DeliverySnapshot | null>(null);
  const [checked, setChecked] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeliveryResult | null>(null);
  const requestVersion = useRef(0);
  const sendingRef = useRef(false);

  // 서버를 다시 조회한 목록만 사용합니다. 화면을 닫거나 세션이 바뀌면 이전 응답은 무시합니다.
  const reload = useCallback(async () => {
    if (sendingRef.current) return;
    const requestId = ++requestVersion.current;
    setLoading(true);
    setSnapshot(null);
    setChecked([]);
    setResult(null);
    setError(null);
    setNeedsRefresh(false);
    try {
      const next = await loadDeliverySnapshot(context.version);
      if (
        requestId === requestVersion.current &&
        getDeliveryContext()?.version === context.version
      ) {
        setSnapshot(next);
      }
    } catch (failure) {
      if (
        requestId === requestVersion.current &&
        getDeliveryContext()?.version === context.version
      ) {
        setError(deliveryErrorMessage(failure));
      }
    } finally {
      if (
        requestId === requestVersion.current &&
        getDeliveryContext()?.version === context.version
      ) {
        setLoading(false);
      }
    }
  }, [context.version]);

  useEffect(() => {
    void reload();
    return () => {
      requestVersion.current += 1;
    };
  }, [reload]);

  // ref로 빠른 연속 클릭도 차단합니다. 전달 POST 결과가 불명확해도 자동 재전송하지 않습니다.
  const send = async () => {
    if (!snapshot || sendingRef.current || loading || needsRefresh) return;
    sendingRef.current = true;
    setSending(true);
    setError(null);
    const requestId = requestVersion.current;
    try {
      // 경로 상세를 펼친 것은 선택이 아닙니다. 여기서는 체크한 실제 기관 ID만 전달합니다.
      const response = await deliverToAgencies(
        snapshot,
        checked.map((agency_id) => ({ agency_id })),
      );
      if (
        requestId === requestVersion.current &&
        getDeliveryContext()?.version === context.version
      ) {
        setResult(response);
      }
    } catch (failure) {
      if (
        requestId === requestVersion.current &&
        getDeliveryContext()?.version === context.version
      ) {
        setError(deliveryErrorMessage(failure));
      }
    } finally {
      sendingRef.current = false;
      if (
        requestId === requestVersion.current &&
        getDeliveryContext()?.version === context.version
      ) {
        setSending(false);
        setNeedsRefresh(true);
      }
    }
  };
  const canDeliver =
    snapshot && ["CONFIRMED", "SENT"].includes(snapshot.incident.status);

  return (
    <>
      <div className="modal-head">
        <div>
          <span className="eyebrow">실제 전달 대상 · 서버 확인</span>
          <h2>
            {snapshot ? snapshot.incident.incident_no : "전달 대상 사건 확인"}
          </h2>
          {snapshot && (
            <p>
              {snapshot.incident.cctv_name} · {snapshot.incident.hazard_type} ·{" "}
              {result?.incident_status ?? snapshot.incident.status}
            </p>
          )}
        </div>
        <button className="close" aria-label="기관 선택 닫기" onClick={close}>
          ×
        </button>
      </div>
      <p className="agency-help">
        서버에서 사건 정보와 추천 기관을 다시 조회했습니다. 이 창의
        사건번호와 CCTV를 확인한 뒤 전달 기관을 선택해 주세요.
      </p>
      {loading && (
        <p role="status">
          로그인 정보와 서버 사건·추천 기관을 확인하고 있습니다.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {snapshot && !canDeliver && (
        <p role="status">
          확인된 사건만 전달할 수 있습니다. 기존 사건 확인 절차를 먼저 진행해
          주세요.
        </p>
      )}
      {snapshot && !snapshot.candidates.length && (
        <p>저장된 추천 기관이 없습니다.</p>
      )}
      <div className="agency-picker-list">
        {snapshot?.candidates.map((candidate) => {
          // 전달 응답의 실제 상태를 표시하되, 상위 샘플 화면의 상태는 바꾸지 않습니다.
          const serverStatus =
            result?.items.find((item) => item.agency_id === candidate.agency_id)
              ?.status ?? candidate.recommendation_status;
          const selectable = serverStatus === "RECOMMENDED";
          return (
            <section
              key={candidate.agency_id}
              className={
                "agency-card " +
                (checked.includes(candidate.agency_id) ? "chosen" : "")
              }
            >
              <label className="agency-check">
                <input
                  type="checkbox"
                  checked={checked.includes(candidate.agency_id)}
                  disabled={
                    !canDeliver || !selectable || sending || needsRefresh
                  }
                  onChange={(event) =>
                    setChecked((previous) =>
                      event.target.checked
                        ? [...previous, candidate.agency_id]
                        : previous.filter((id) => id !== candidate.agency_id),
                    )
                  }
                  aria-label={candidate.agency_name + " 전달 대상"}
                />
                <span>
                  <span className="rank">
                    기관 추천 {candidate.recommendation_rank}순위 ·{" "}
                    {candidate.agency_type}
                  </span>
                  <strong>{candidate.agency_name}</strong>
                </span>
              </label>
              {!selectable && (
                <p>
                  {serverStatus === "COMPLETED"
                    ? "기관 대응 완료"
                    : "전달된 기관"}
                </p>
              )}
              {candidate.routes.length ? (
                <details className="agency-route-details">
                  <summary>후보 경로 {candidate.routes.length}개 확인</summary>
                  {candidate.routes.map((route) => (
                    <p key={route.id}>
                      {route.route_name} ·{" "}
                      {(route.distance_m / 1000).toFixed(1)} km /{" "}
                      {(route.duration_sec / 60).toFixed(1)}분
                      <br />
                      {route.disqualify_reason !== null
                        ? "제외 경로: " + route.disqualify_reason
                        : route.total_score === null
                          ? "경로 평가 대기"
                          : "평가 점수 " + route.total_score}
                    </p>
                  ))}
                </details>
              ) : (
                <p>
                  저장된 후보 경로가 없습니다. 기관만 선택해 전달할 수 있습니다.
                </p>
              )}
            </section>
          );
        })}
      </div>
      {snapshot && (
        <p>
          선택 기관 {checked.length}곳 · 경로 조회와 기관 선택은 별개입니다.
        </p>
      )}
      {result && (
        <section role="status" aria-live="polite">
          <h3>
            {result.items.some((item) => item.newly_delivered)
              ? "기관 전달 내용이 저장되었습니다."
              : "이미 처리된 기관의 상태를 확인했습니다."}
          </h3>
          <p>
            서버 사건 상태: {result.incident_status} · 앱 내 새 알림{" "}
            {result.created_notification_count}건
          </p>
          <ul>
            {result.items.map((item) => (
              <li key={item.agency_id}>
                {
                  snapshot?.candidates.find(
                    (candidate) => candidate.agency_id === item.agency_id,
                  )?.agency_name
                }
                {" · "}
                {item.status === "COMPLETED"
                  ? "기관 대응 완료 유지"
                  : item.newly_delivered
                    ? "새로 전달됨"
                    : "기존 전달 상태 유지"}
              </li>
            ))}
          </ul>
          <p>{pushStatusLabels[result.push_status]}</p>
          <p>
            기관 전달 저장 결과입니다. 휴대폰의 실제 수신·표시 여부는 별도로
            확인해야 합니다.
          </p>
        </section>
      )}
      <div className="confirm-actions">
        <button className="secondary" onClick={close}>
          닫기
        </button>
        <button
          className="secondary"
          disabled={loading || sending}
          onClick={() => {
            void reload();
          }}
        >
          기관 전달 상태 다시 조회
        </button>
        <button
          className="primary"
          disabled={
            !canDeliver || !checked.length || loading || sending || needsRefresh
          }
          onClick={() => {
            void send();
          }}
        >
          {sending ? "전달 결과 확인 중" : "선택 기관에 전달"}
        </button>
      </div>
    </>
  );
}

// 후속-03: 실제 사건 선택 시 mock 미리보기로 되돌아가지 않는 전달 모달입니다.
// LiveDeliveryPicker 자체의 검증·POST·결과 표시는 기존 코드 그대로 재사용합니다.
export function LiveAgencyPicker({ close }: { close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const context = useSyncExternalStore(
    subscribeDeliveryContext,
    getDeliveryContext,
    () => null,
  );
  useEffect(() => {
    if (ref.current && !ref.current.open) ref.current.showModal();
  }, []);
  return (
    <dialog ref={ref} aria-label="실제 기관 선택·전달" onCancel={close}>
      {context ? (
        <LiveDeliveryPicker key={context.version} context={context} close={close} />
      ) : (
        <p role="status">사건·로그인 연결이 변경됐습니다. 창을 닫고 다시 조회해 주세요.
          <button className="secondary" onClick={close}>닫기</button>
        </p>
      )}
    </dialog>
  );
}
