/**
 * 사건 상세에서 추가 지원 요청과 기관별/소속기관 전달 상태를 표시합니다.
 * CONTROL_ADMIN은 전체 추천기관 상태를,
 * AGENCY_STAFF / RESPONDER는 자기 기관 범위의 상태만 조회합니다.
 *
 * 기존 support-requests GET 및 기관 추천 GET을 재사용하며
 * 이 컴포넌트에서는 상태 변경·대응 완료 처리를 하지 않습니다.
 */
import { useEffect, useState } from "react";
import {
  getWebIncidentApi,
  requestWebApi,
  type WebIncidentSession,
} from "../incidentData";
import { pollWhileVisible } from "../polling";
import { statusLabel } from "../operationsData";

type SupportType = "PERSONNEL" | "EQUIPMENT" | "TRAFFIC_CONTROL" | "OTHER";

type SupportItem = {
  id: number;
  incident_id: number;
  responder_id: number;
  agency_id: number;
  support_type: SupportType;
  request_content: string;
  created_at: string;
  responder_name: string | null;
  agency_name: string | null;
};

type AgencyStatus = {
  agency_id: number;
  agency_name: string;
  recommendation_rank: number;
  recommendation_status: "RECOMMENDED" | "DELIVERED" | "COMPLETED";
};

type RecommendationData = {
  items: AgencyStatus[];
};

const typeLabels: Record<SupportType, string> = {
  PERSONNEL: "인력",
  EQUIPMENT: "장비",
  TRAFFIC_CONTROL: "교통 통제",
  OTHER: "기타",
};

function seoulTime(value: string) {
  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "시각 확인 필요"
    : date.toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
      });
}

export function LiveSupportRequestsPanel({
  session,
  incidentId,
  refreshKey,
}: {
  session: WebIncidentSession;
  incidentId: number;
  refreshKey: number;
}) {
  const [requests, setRequests] = useState<SupportItem[] | null>(null);

  const [agencies, setAgencies] = useState<AgencyStatus[] | null>(null);

  const [requestError, setRequestError] = useState<string | null>(null);

  const [agencyError, setAgencyError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);

  const [reload, setReload] = useState(0);

  const isAdmin = session.user.role === "CONTROL_ADMIN";

  useEffect(() => {
    const api = getWebIncidentApi(session.version);

    setLoading(true);
    setRequests(null);
    setAgencies(null);
    setRequestError(null);
    setAgencyError(null);

    if (!api) {
      setRequestError("로그인 상태를 다시 확인해주세요.");
      setLoading(false);

      return;
    }

    return pollWhileVisible(
      (signal) =>
        Promise.allSettled([
          requestWebApi<SupportItem[]>(
            session.version,
            `/api/support-requests/incidents/${incidentId}`,
            {
              signal,
            },
          ),

          requestWebApi<RecommendationData>(
            session.version,
            `/api/agencies/incidents/${incidentId}/recommendations`,
            {
              signal,
            },
          ),
        ]),
      {
        onValue: ([supportResult, agencyResult]) => {
          for (const result of [supportResult, agencyResult]) {
            if (
              result.status === "rejected" &&
              (result.reason?.status === 401 || result.reason?.status === 403)
            ) {
              throw result.reason;
            }
          }
          setRequestError(null);
          setAgencyError(null);

          if (
            supportResult.status === "fulfilled" &&
            Array.isArray(supportResult.value)
          ) {
            setRequests(supportResult.value);
          } else {
            setRequests(null);
            setRequestError(
              "추가 지원 요청을 조회할 수 없습니다. 연결과 권한을 확인해주세요.",
            );
          }

          if (
            agencyResult.status === "fulfilled" &&
            Array.isArray(agencyResult.value.items)
          ) {
            setAgencies(agencyResult.value.items);
          } else {
            setAgencies(null);
            setAgencyError(
              isAdmin
                ? "기관별 상태를 조회할 수 없습니다. 연결과 권한을 확인해주세요."
                : "우리 기관 상태를 조회할 수 없습니다. 연결과 권한을 확인해주세요.",
            );
          }

          setLoading(false);
        },
        onError: () => {
          setRequests(null);
          setAgencies(null);
          setRequestError("서버 조회에 실패했습니다. 다시 조회해주세요.");
          setLoading(false);
        },
      },
    );
  }, [session.version, incidentId, refreshKey, reload, isAdmin]);

  return (
    <section
      className="panel page-section"
      aria-label={
        isAdmin ? "추가 지원요청·기관별 상태" : "추가 지원요청·우리 기관 상태"
      }
    >
      <div className="section-title">
        <h2>
          {isAdmin
            ? "추가 지원요청 · 기관별 상태"
            : "추가 지원요청 · 우리 기관 상태"}
        </h2>

        <button
          className="secondary"
          onClick={() => setReload((value) => value + 1)}
        >
          새로고침
        </button>
      </div>

      <p className="subtle">
        {isAdmin
          ? "DB에 저장된 지원 요청과 추천·전달 상태를 확인할 수 있습니다."
          : "우리 기관의 현재 대응 상태와 추가 지원 요청을 확인할 수 있습니다."}
      </p>

      {loading && <p role="status">서버 상태를 확인하고 있습니다.</p>}

      <h3>{isAdmin ? "기관별 현재 상태" : "우리 기관 현재 상태"}</h3>

      {agencyError && <p role="alert">{agencyError}</p>}

      {agencies?.length === 0 && (
        <p>
          {isAdmin
            ? "추천된 기관이 없습니다."
            : "우리 기관의 전달 상태를 확인할 수 없습니다."}
        </p>
      )}

      {agencies && agencies.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {isAdmin && <th>추천 순위</th>}

                <th>기관</th>

                <th>현재 상태</th>
              </tr>
            </thead>

            <tbody>
              {agencies.map((agency) => (
                <tr key={agency.agency_id}>
                  {isAdmin && <td>{agency.recommendation_rank}</td>}

                  <td>{agency.agency_name}</td>

                  <td>{statusLabel(agency.recommendation_status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>현장 추가 지원 요청</h3>

      {requestError && <p role="alert">{requestError}</p>}

      {requests?.length === 0 && <p>아직 추가 지원 요청이 없습니다.</p>}

      {requests && requests.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>시각(KST)</th>

                <th>요청 기관/담당자</th>

                <th>유형</th>
                <th>내용</th>
              </tr>
            </thead>

            <tbody>
              {requests.map((request) => (
                <tr key={request.id}>
                  <td>{seoulTime(request.created_at)}</td>

                  <td>
                    {request.agency_name ?? `기관 #${request.agency_id}`} ·{" "}
                    {request.responder_name ??
                      `담당자 #${request.responder_id}`}
                  </td>

                  <td>
                    {typeLabels[request.support_type] ?? request.support_type}
                  </td>

                  <td
                    style={{
                      whiteSpace: "pre-wrap",
                      overflowWrap: "anywhere",
                    }}
                  >
                    {request.request_content}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
