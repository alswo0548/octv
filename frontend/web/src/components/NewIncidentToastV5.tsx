/** 기존 사건 API만 조회합니다. FCM/알림 DB와 별개인 로그인 세션별 웹 수신함. */
import { useEffect, useState } from "react";
import { hazardLabel, type IncidentDto, type PageDto } from "@octv/shared";
import { requestWebApi, type WebIncidentSession } from "../incidentData";
import { incidentLabel } from "../incidentLabel";
import { pollWhileVisible } from "../polling";

type Notice = { incident: IncidentDto; read: boolean };
export function NewIncidentToastV5({ session, openIncident }: {
  session: WebIncidentSession; openIncident: (id: number) => void;
}) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const [toast, setToast] = useState<IncidentDto | null>(null);
  const [archived, setArchived] = useState<number[]>([]);
  const [opened, setOpened] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const since = new Date().toISOString();
    const seen = new Set<number>();
    return pollWhileVisible(async signal => {
      // 조회 기간 내 모든 페이지를 읽어 우선순위 정렬·100건 제한으로 누락되지 않게 합니다.
      const items: IncidentDto[] = [];
      let page = 1;
      for (;;) {
        const result = await requestWebApi<PageDto<IncidentDto>>(session.version,
          `/api/incidents?page=${page}&page_size=100&start=${encodeURIComponent(since)}`, { signal });
        items.push(...result.items);
        if (items.length >= result.total || !result.items.length) break;
        page++;
      }
      let archivedIds: number[] = [];
      try {
        const archive = await requestWebApi<{archived_ids: number[]}>(session.version, "/api/demo/v5/archive-scope", { signal });
        archivedIds = archive.archived_ids;
      } catch { /* Standard API without the optional v5 extension. */ }
      return { items, archivedIds };
    }, {
      intervalMs: 4000,
      onValue: ({items, archivedIds}) => {
        setArchived(archivedIds);
        setError(null);
        const fresh = items.filter(i => !seen.has(i.id) && !archivedIds.includes(i.id)).sort((a,b) => a.id-b.id);
        items.forEach(i => seen.add(i.id));
        setNotices(old => {
          const updated = old.map(n => ({ ...n, incident: items.find(i => i.id === n.incident.id) ?? n.incident }));
          return [...updated, ...fresh.map(incident => ({ incident, read: false }))].slice(-100);
        });
        if (fresh.length) setToast(fresh[fresh.length-1]);
      },
      onError: () => setError("신규 사건 조회 실패 · 연결과 로그인 상태를 확인해주세요."),
    });
  }, [session.version]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);
  function open(item: IncidentDto) {
    setNotices(old => old.map(n => n.incident.id === item.id ? { ...n, read: true } : n));
    setToast(null); setOpened(false); openIncident(item.id);
  }
  return <div className="new-incident-notice">
    <button className="secondary" aria-label="신규 사건 알림" aria-expanded={opened} onClick={() => setOpened(v => !v)}>
      알림 {notices.filter(n => !n.read).length}
    </button>
    {toast && <div role="status" className="panel incident-notice-popup" style={{ padding: 16, maxWidth: 420 }}>
      <button onClick={() => open(toast)}>새 사건 · {incidentLabel(toast)} · {hazardLabel(toast.hazard_type)}</button>
    </div>}
    {opened && <section className="panel incident-notice-dropdown" aria-label="최근 사건 알림 목록" style={{ padding: 16, width: 360, maxHeight: "65vh", overflowY: "auto" }}>
      <strong>알림</strong>
      {error && <p role="alert">{error}</p>}
      {!notices.length && <p>수신한 새 사건이 없습니다.</p>}
      {[...notices].reverse().map(({incident, read}) => <div className="octv-notice-row" key={incident.id}>
        <button className="octv-notice-main" onClick={() => open(incident)}>
          <span>{archived.includes(incident.id) ? "종료된 시연" : read ? "읽음" : "새 알림"} · {incidentLabel(incident)}</span>
          <small>{hazardLabel(incident.hazard_type)} · {incident.cctv_name}</small>
        </button>
        <button className="octv-notice-dismiss" type="button" aria-label={`${incidentLabel(incident)} 알림 삭제`} title="이 목록에서 삭제" onClick={() => setNotices(old => old.filter(n => n.incident.id !== incident.id))}>×</button>
      </div>)}
    </section>}
  </div>;
}
