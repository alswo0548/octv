/** Saved agency recommendations + saved route preview, read-only. */
import { useState } from "react";
import { useOperations } from "../operationsData";
import type { WebIncidentSession } from "../incidentData";

type Recommendation = {agency_id:number;agency_name:string;recommendation_rank:number;recommendation_status:string};
type Route = {id:number;route_name:string;distance_m:number;duration_sec:number;total_score:number|null;navigation_available:boolean;disqualify_reason:string|null;};
export function AgencyRoutePreview({session, incidentId}: {session:WebIncidentSession;incidentId:number}) {
  const [selectedAgency, setSelectedAgency] = useState<number|null>(null);
  const agencies = useOperations<{items:Recommendation[]}>(session, `/api/agencies/incidents/${incidentId}/recommendations`, 0, 10000);
  const chosen = agencies.data?.items.find(item=>item.agency_id===selectedAgency) ?? null;
  const routes = useOperations<{items:Route[]}>(session, chosen ? `/api/routes/incidents/${incidentId}/agencies/${chosen.agency_id}` : null, 0, 10000);
  const best = routes.data?.items.find(item=>item.navigation_available && !item.disqualify_reason) ?? routes.data?.items[0];
  return <div className="octv-agency-preview">
    {agencies.error && <p role="alert">추천기관을 조회할 수 없습니다.</p>}
    {!agencies.loading && agencies.data?.items.length===0 && <p>저장된 추천기관이 없습니다. 분석 및 추천 상태를 확인해주세요.</p>}
    <div className="octv-agency-preview-list">
      {agencies.data?.items.slice(0,3).map(item=><button key={item.agency_id} className={chosen?.agency_id===item.agency_id ? "secondary selected" : "secondary"} onClick={()=>setSelectedAgency(item.agency_id===selectedAgency ? null : item.agency_id)}>
        {item.recommendation_rank}순위 · {item.agency_name} <small>경로 미리보기</small>
      </button>)}
    </div>
    {chosen && <p className="octv-agency-route-preview" role="status">{routes.loading ? "추천 경로 조회 중…" : best ? `${chosen.agency_name} → 사건 위치 · ${best.route_name} · ${(best.distance_m/1000).toFixed(1)}km / ${Math.ceil(best.duration_sec/60)}분 · ${best.navigation_available ? "이동 가능" : "추가 확인 필요"}${best.disqualify_reason ? " · " + best.disqualify_reason : ""}` : "저장된 추천 경로가 없습니다."}</p>}
  </div>;
}
