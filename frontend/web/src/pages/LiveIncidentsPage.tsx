import { hideIncident, restoreHiddenIncidents } from "../incidentVisibility";
import { incidentLabel } from "../incidentLabel";
/**
 * 후속-03 · 관제 웹 실제 사건관리 화면
 * 목록 API → 사건 ID 선택 → 상세/판단 근거 → 관리자 확인 → 기존 기관 전달 모달.
 * 샘플 사건번호 SEL-001, 샘플 영상·경로·지원 요청을 실제 서버 결과에 섞지 않습니다.
 */
import { useEffect, useState } from "react";
import {
  CCTV_SOURCE,
  hazardLabel,
  hazardLabels,
  type IncidentDto,
  type PageDto,
} from "@octv/shared";
import { Badge, type ShowModal } from "../components/Primitives";
import { LiveSupportRequestsPanel } from "../components/LiveSupportRequestsPanel";
import {
  changeServerIncident,
  formatSeoulTime,
  getServerIncident,
  incidentErrorMessage,
  requestWebApi,
  listServerIncidents,
  loadIncidentImageUrl,
  type IncidentDetailDto,
  type WebIncidentSession,
} from "../incidentData";
import { IncidentContext } from "../components/IncidentContext";
import { AgencyRoutePreview } from "../components/AgencyRoutePreview";
import { statusLabel } from "../operationsData";
import { pollWhileVisible } from "../polling";
import { go } from "../routing/useRoute";
import "../styles/live-incidents.css";

type Props = {
  session: WebIncidentSession;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  openPicker: () => void;
  show: ShowModal;
  refreshKey: number;
  onRefresh: () => void;
};

type Period = "all" | "today" | "week";

const PAGE_SIZE = 5;

// 브라우저 위치와 관계없이 서울 날짜의 00:00(KST)을 ISO(UTC)로 전송합니다.
function periodStart(period: Period): string | undefined {
  if (period === "all") return undefined;

  const koreaDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());

  const parts = Object.fromEntries(
    koreaDate.map((part) => [part.type, part.value]),
  );

  const start = new Date(
    `${parts.year}-${parts.month}-${parts.day}T00:00:00+09:00`,
  );

  if (period === "week") {
    start.setUTCDate(start.getUTCDate() - 6);
  }

  return start.toISOString();
}

type DetectionBox = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

function readDetectionBox(value: unknown): DetectionBox | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const box = value as Record<string, unknown>;
  const x1 = Number(box.x1);
  const y1 = Number(box.y1);
  const x2 = Number(box.x2);
  const y2 = Number(box.y2);

  if (![x1, y1, x2, y2].every(Number.isFinite) || x2 <= x1 || y2 <= y1) {
    return null;
  }

  return { x1, y1, x2, y2 };
}

// JPEG를 Authorization 헤더로 별도 조회합니다. 사건/세션 변경 시 URL을 해제합니다.
function RepresentativeImage({
  session,
  incident,
  isAdmin,
}: {
  session: WebIncidentSession;
  incident: IncidentDetailDto;
  isAdmin: boolean;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [imageSize, setImageSize] = useState<{
    width: number;
    height: number;
  } | null>(null);

  const detectionBox = readDetectionBox(incident.detection_bbox_json);

  const detectionLabel =
    `${hazardLabel(incident.hazard_type)} ` +
    `${(incident.confidence * 100).toFixed(1)}%`;

  const sourceLabel =
    incident.provider?.toUpperCase().includes("UTIC") || !incident.provider
      ? CCTV_SOURCE
      : `${incident.provider} 제공`;

  useEffect(() => {
    setUrl(null);
    setUnavailable(false);
    setImageSize(null);

    if (!incident.representative_image_updated_at) {
      return;
    }

    const controller = new AbortController();
    let resource: string | null = null;

    void loadIncidentImageUrl(session.version, incident.id, controller.signal)
      .then((next) => {
        resource = next;

        if (!controller.signal.aborted) {
          setUrl(next);
        } else {
          URL.revokeObjectURL(next);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setUnavailable(true);
        }
      });

    return () => {
      controller.abort();

      if (resource) {
        URL.revokeObjectURL(resource);
      }
    };
  }, [incident.id, incident.representative_image_updated_at, session.version]);

  return (
    <section className="panel camera-panel live-incident-image">
      <div className="camera stored-camera">
        <div className="camera-overlay-label">
          저장 이미지 · {incident.cctv_name}
        </div>

        {url ? (
          <>
            <img
              src={url}
              onLoad={(event) => {
                setImageSize({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                });
              }}
              onError={() => {
                setUnavailable(true);
                setUrl(null);
                setImageSize(null);
              }}
              alt={`${incidentLabel(incident)} 사건 대표 JPEG`}
            />

            {imageSize && detectionBox && (
              <div className="incident-detection-summary">
                <span>AI 탐지</span>
                <strong>{detectionLabel}</strong>
              </div>
            )}

            {imageSize && detectionBox && (
              <svg
                className="incident-detection-overlay"
                viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
                preserveAspectRatio="xMidYMid meet"
                aria-label={`${detectionLabel} 탐지 영역`}
              >
                <rect
                  className="incident-detection-box"
                  x={detectionBox.x1}
                  y={detectionBox.y1}
                  width={detectionBox.x2 - detectionBox.x1}
                  height={detectionBox.y2 - detectionBox.y1}
                />
              </svg>
            )}
          </>
        ) : (
          <p className="live-image-empty" role="status">
            {unavailable
              ? "대표 이미지를 조회할 수 없습니다."
              : incident.representative_image_updated_at
                ? "대표 이미지 불러오는 중"
                : "저장된 대표 이미지가 없습니다."}
          </p>
        )}
      </div>

      <div className="camera-caption">
        <span>사건 대표 이미지 · 저장 시점 기준</span>
        <span className="incident-source-credit">{sourceLabel}</span>
      </div>

      {isAdmin && (
        <button
          className="primary camera-live-button"
          onClick={() => go(`monitor/${incident.cctv_id}`)}
        >
          실시간 CCTV 영상
        </button>
      )}
    </section>
  );
}

export function LiveIncidentsPage({
  session,
  selectedId,
  onSelect,
  openPicker,
  show,
  refreshKey,
  onRefresh,
}: Props) {
  const [page, setPage] = useState(1);
  const [priority, setPriority] = useState("");
  const [status, setStatus] = useState("");
  const [hazard, setHazard] = useState("");
  const [period, setPeriod] = useState<Period>("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  const [list, setList] = useState<PageDto<IncidentDto> | null>(null);

  const [detail, setDetail] = useState<IncidentDetailDto | null>(null);

  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [llmBusy, setLlmBusy] = useState(false);
  const [llmResult, setLlmResult] = useState<{status:string;text:string}|null>(null);
  useEffect(() => { setLlmResult(null); setLlmBusy(false); }, [detail?.id]);
  const explainWithLlm = async () => {
    if (!detail || llmBusy) return;
    setLlmBusy(true);
    try {
      const result = await requestWebApi<{status:string;text:string}>(session.version,
        `/api/demo/v5/incidents/${detail.id}/explain`, { method: 'POST' });
      setLlmResult(result);
    } catch { setLlmResult({status:'ERROR',text:'LLM 설명 요청 실패 · API/설정을 확인해주세요.'}); }
    finally { setLlmBusy(false); }
  };

  const isAdmin = session.user.role === "CONTROL_ADMIN";

  // 필터·세션 변경은 초기화하고, 같은 화면의 후속 조회는 현재 선택을 유지합니다.
  useEffect(() => {
    setLoadingList(true);
    setListError(null);
    setList(null);
    return pollWhileVisible(
      (signal) =>
        listServerIncidents(
          session.version,
          {
            page,
            page_size: PAGE_SIZE,
            priority: (priority || undefined) as "P1" | "P2" | "P3" | undefined,
            status: (status || undefined) as IncidentDto["status"] | undefined,
            hazard_type: hazard || undefined,
            q: search || undefined,
            start: periodStart(period),
          },
          signal,
        ),
      {
        onValue: (result) => {
          setList(result);
          setListError(null);
        },
        onError: (error) => {
          setList(null);
          setListError(incidentErrorMessage(error));
        },
        onSettled: () => setLoadingList(false),
      },
    );
  }, [
    session.version,
    page,
    priority,
    status,
    hazard,
    period,
    search,
    refreshKey,
  ]);

  // 목록 조회가 처음 완료됐고 선택된 사건이 없다면 첫 번째 실제 DB ID를 선택합니다.
  useEffect(() => {
    if (selectedId === null && list?.items.length) {
      onSelect(list.items[0].id);
    }
  }, [selectedId, list, onSelect]);

  // 선택된 숫자 DB ID로만 상세 조회. 다른 사건의 늦은 응답은 폐기합니다.
  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      setDetailError(null);
      return;
    }

    setLoadingDetail(true);
    setDetail(null);
    setDetailError(null);
    return pollWhileVisible(
      (signal) => getServerIncident(session.version, selectedId, signal),
      {
        onValue: (result) => {
          setDetail(result);
          setDetailError(null);
        },
        onError: (error) => {
          setDetail(null);
          setDetailError(incidentErrorMessage(error));
        },
        onSettled: () => setLoadingDetail(false),
      },
    );
  }, [session.version, selectedId, refreshKey]);

  // PATCH 후 서버를 다시 조회합니다. 충돌(409) 때는 같은 PATCH를 자동 재시도하지 않습니다.
  const hideSelected = () => {
    if (!detail || !isAdmin) return;
    hideIncident(session.version, detail.id);
    setList(null); onSelect(null); onRefresh();
  };
  const changeStatus = async (operation: "confirm" | "false-positive") => {
    if (!detail || updating || !isAdmin) {
      return;
    }

    setUpdating(true);
    setDetailError(null);

    try {
      await changeServerIncident(session.version, detail.id, operation);
      if (operation === "false-positive") show({
        title: "오탐 처리 완료",
        body: "오탐 처리된 사건을 이번 로그인 세션의 목록에서 제거하시겠습니까? DB와 전달 이력은 보존됩니다.",
        confirm: "목록에서 숨김", onConfirm: hideSelected,
      });
    } catch (error) {
      setDetailError(incidentErrorMessage(error));
    } finally {
      setUpdating(false);
      onRefresh();
    }
  };

  const confirmAction = (operation: "confirm" | "false-positive") => {
    if (!detail || updating || !isAdmin) {
      return;
    }

    show({
      title: operation === "confirm" ? "사건 확인" : "오탐 처리",
      body: `${incidentLabel(detail)} 사건을 ${
        operation === "confirm" ? "확인" : "오탐"
      } 처리할까요?`,
      confirm: operation === "confirm" ? "사건 확인" : "오탐 처리",
      onConfirm: () => {
        void changeStatus(operation);
      },
    });
  };

  const resetPage = (setValue: (value: string) => void) => (value: string) => {
    setPage(1);
    setValue(value);
  };

  const pages = Math.ceil((list?.total ?? 0) / PAGE_SIZE);

  return (
    <>
      <section className="panel list-panel">
        <div className="section-title">
          <h2>
            사건 목록 <span className="count">{list?.total ?? "–"}</span>
          </h2>

          <span className="subtle">탐지 시각 기준 · 한국시간</span>
          {isAdmin && <button className="secondary" onClick={() => { restoreHiddenIncidents(session.version); onRefresh(); }}>직접 숨긴 사건 복원</button>}
        </div>

        <div className="filters live-filters">
          <div className="priority-filter">
            <label>우선순위</label>

            <div className="segments">
              {["", "P1", "P2", "P3"].map((value) => (
                <button
                  key={value}
                  className={priority === value ? "selected" : ""}
                  aria-pressed={priority === value}
                  onClick={() => resetPage(setPriority)(value)}
                >
                  {value || "전체"}
                </button>
              ))}
            </div>
          </div>

          <label>
            상태
            <select
              value={status}
              onChange={(event) => resetPage(setStatus)(event.target.value)}
            >
              <option value="">상태 전체</option>
              <option value="DETECTED">탐지됨</option>
              <option value="CONFIRMED">사건 확인</option>
              <option value="SENT">전달 완료</option>
              <option value="RESOLVED">기존 종결 상태</option>
              <option value="FALSE_POSITIVE">오탐 이력</option>
            </select>
          </label>

          <label>
            유형
            <select
              value={hazard}
              onChange={(event) => resetPage(setHazard)(event.target.value)}
            >
              <option value="">유형 전체</option>

              {Object.entries(hazardLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            기간
            <select
              value={period}
              onChange={(event) => {
                setPage(1);
                setPeriod(event.target.value as Period);
              }}
            >
              <option value="all">전체 기간</option>
              <option value="today">오늘</option>
              <option value="week">최근 7일</option>
            </select>
          </label>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              setPage(1);
              setSearch(searchInput.trim());
            }}
          >
            <label>
              검색
              <input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="사건번호 / CCTV명"
              />
            </label>

            <button className="secondary" type="submit">
              조회
            </button>
          </form>
        </div>

        {loadingList && <p role="status">사건 목록을 조회하고 있습니다.</p>}

        {listError && (
          <p role="alert">
            {listError} <button onClick={onRefresh}>다시 조회</button>
          </p>
        )}

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "사건번호",
                  "유형",
                  "우선순위",
                  "상태",
                  "CCTV",
                  "발생시각",
                ].map((text) => (
                  <th key={text}>{text}</th>
                ))}
              </tr>
            </thead>

            <tbody>
              {list?.items.map((row) => (
                <tr
                  key={row.id}
                  tabIndex={0}
                  className={selectedId === row.id ? "selected" : ""}
                  onClick={() => onSelect(row.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      onSelect(row.id);
                    }
                  }}
                  aria-label={`${incidentLabel(row)} 상세 보기`}
                >
                  <td>{incidentLabel(row)}</td>
                  <td>{hazardLabel(row.hazard_type)}</td>

                  <td>
                    {row.priority ? (
                      <Badge priority={row.priority} />
                    ) : (
                      "분석 대기"
                    )}
                  </td>

                  <td>{statusLabel(row.status)}</td>
                  <td>{row.cctv_name}</td>
                  <td>{formatSeoulTime(row.detected_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {list?.items.length === 0 && !loadingList && (
          <p>조건에 맞는 사건이 없습니다.</p>
        )}

        <div className="table-footer">
          <span>
            총 {list?.total ?? 0}건 / {page}페이지
          </span>

          <nav className="pagination" aria-label="사건 목록 페이지">
            <button
              disabled={page <= 1 || loadingList}
              onClick={() => setPage(page - 1)}
            >
              이전
            </button>

            {Array.from({ length: Math.min(pages, 7) }, (_, index) => {
              const first = Math.max(1, Math.min(page - 3, pages - 6));

              const current = first + index;

              return (
                <button
                  key={current}
                  aria-current={page === current ? "page" : undefined}
                  className={page === current ? "current" : ""}
                  onClick={() => setPage(current)}
                >
                  {current}
                </button>
              );
            })}

            <button
              disabled={page >= pages || loadingList}
              onClick={() => setPage(page + 1)}
            >
              다음
            </button>
          </nav>
        </div>
      </section>

      <section className="selected-heading">
        <div>
          <span className="eyebrow">SELECTED INCIDENT</span>

          <h2>
            {detail
              ? `${hazardLabel(detail.hazard_type)} · ${incidentLabel(detail)}`
              : "선택 사건 상세"}
          </h2>
        </div>

        <button className="secondary" onClick={onRefresh}>
          서버 정보 새로고침
        </button>
      </section>

      {loadingDetail && (
        <p role="status">선택 사건 상세를 조회하고 있습니다.</p>
      )}

      {detailError && <p role="alert">{detailError}</p>}

      {!detail && (
        <div
          className="detail-grid restored-detail-grid"
          aria-busy={loadingDetail}
        >
          <section className="panel camera-panel">
            <div className="camera">
              <div className="live-image-empty">
                {loadingDetail
                  ? "선택 사건 조회 중"
                  : detailError
                    ? "사건 정보를 불러오지 못했습니다."
                    : "조회할 사건을 선택해주세요."}
              </div>
            </div>

            <div className="camera-caption">사건 대표 이미지</div>
          </section>

          <section className="panel info">
            <h2>사건 정보</h2>

            <p className="subtle">
              {loadingDetail ? "조회 중" : "선택 사건 없음"}
            </p>
          </section>

          <section className="panel risk">
            <h2>위험도 · 우선순위</h2>

            <div className="scores">
              <div>
                <strong>
                  –<small> / 100</small>
                </strong>
              </div>

              <div>
                <strong>
                  –<small> / 100</small>
                </strong>
              </div>
            </div>
          </section>

          <section className="panel external">
            <h2>외부 상황</h2>
            <p className="subtle">조회 대기</p>
          </section>
        </div>
      )}

      {detail && (
        <>
          <div className="detail-grid restored-detail-grid">
            <RepresentativeImage
              key={detail.id}
              session={session}
              incident={detail}
              isAdmin={isAdmin}
            />

            <section className="panel info">
              <div className="section-title">
                <h2>사건 정보</h2>
                <span className="tag">{statusLabel(detail.status)}</span>
              </div>

              <dl>
                <div>
                  <dt>CCTV</dt>
                  <dd>
                    {detail.cctv_name} (#{detail.cctv_id})
                  </dd>
                </div>

                <div>
                  <dt>좌표</dt>
                  <dd>
                    {detail.latitude}, {detail.longitude}
                  </dd>
                </div>

                <div>
                  <dt>최초 탐지</dt>
                  <dd>{formatSeoulTime(detail.detected_at)}</dd>
                </div>

                <div>
                  <dt>최근 탐지</dt>
                  <dd>{formatSeoulTime(detail.last_detected_at)}</dd>
                </div>

                <div>
                  <dt>상태</dt>
                  <dd>{statusLabel(detail.status)}</dd>
                </div>
              </dl>

              <div className="analysis-note">
                <span>AI DETECTION</span>

                <div>
                  <strong>
                    {(detail.confidence * 100).toFixed(1)}
                    <small>%</small>
                  </strong>

                  <div className="confidence-track">
                    <i
                      style={{
                        width: `${detail.confidence * 100}%`,
                      }}
                    />
                  </div>
                </div>

                <small>모델 탐지 신뢰도</small>
              </div>

              {isAdmin && (
                <div className="live-actions">
                  {detail.status === "DETECTED" && (
                    <button
                      className="primary"
                      disabled={updating}
                      onClick={() => confirmAction("confirm")}
                    >
                      사건 확인
                    </button>
                  )}

                  {(["DETECTED", "CONFIRMED"] as string[]).includes(
                    detail.status,
                  ) && (
                    <button
                      className="secondary"
                      disabled={updating}
                      onClick={() => confirmAction("false-positive")}
                    >
                      오탐 처리
                    </button>
                  )}
                  <button className="secondary" onClick={() => show({
                    title: '사건 숨김',
                    body: '이 로그인 세션의 웹 목록에서만 숨깁니다. DB 사건·기관·경로·알림 이력은 삭제하지 않습니다.',
                    confirm: '사건 숨김', onConfirm: hideSelected,
                  })}>사건 숨김</button>
                </div>
              )}
            </section>

            <section className="panel risk live-risk">
              <div className="section-title">
                <h2>위험도 · 우선순위</h2>

                <span className="subtle">
                  {detail.analysis_status === "READY"
                    ? "분석 완료"
                    : "분석 대기"}
                </span>
              </div>

              <div className="scores">
                <div>
                  <label>
                    위험도{" "}
                    <span>
                      {detail.risk_level
                        ? statusLabel(detail.risk_level)
                        : "미분석"}
                    </span>
                  </label>

                  <strong>
                    {detail.risk_score ?? "–"}
                    <small> / 100</small>
                  </strong>

                  <div className="bar red">
                    <i
                      style={{
                        width: `${detail.risk_score ?? 0}%`,
                      }}
                    />
                  </div>
                </div>

                <div>
                  <label>
                    대응 우선순위 <span>{detail.priority ?? "미분석"}</span>
                  </label>

                  <strong>
                    {detail.priority_score ?? "–"}
                    <small> / 100</small>
                  </strong>

                  <div className="bar blue">
                    <i
                      style={{
                        width: `${detail.priority_score ?? 0}%`,
                      }}
                    />
                  </div>
                </div>
              </div>

              <p className="content-footnote">
                {detail.risk_breakdown_json?.demo_simulation ? 'DEMO 기준 위험도' : '규칙: ' + (detail.rule_version ?? '분석 결과 없음')}
              </p>

              <div className="live-llm-explanation">
                {isAdmin && <button className="secondary" disabled={llmBusy || detail.risk_score == null} onClick={() => void explainWithLlm()}>
                  {llmBusy ? '분석 내용 생성 중…' : '분석 내용 확인'}
                </button>}
                {llmResult?.status === 'OK' ? <p role="status" aria-live="polite" className="octv-llm-answer">{llmResult.text}</p> :
                  <p role={llmResult ? 'alert' : undefined}>{llmResult?.text ?? '분석 내용을 확인하시려면 ‘분석 내용 확인’을 눌러주세요.'}</p>}
              </div>
              {detail.analysis_status === "PENDING" && (
                <p>분석 결과가 아직 저장되지 않았습니다.</p>
              )}
            </section>

            <IncidentContext incident={detail} session={session} />
          </div>

          <section className="panel page-section live-delivery">
            <div className="section-title">
              <h2>{isAdmin ? "기관 추천 · 선택 전달" : "전달 정보 · 경로"}</h2>

              <button
                className="secondary"
                onClick={() => go(`routes/${detail.id}`)}
              >
                경로 비교 상세
              </button>
            </div>

            <p>
              {isAdmin
                ? "사건 상태를 확인한 뒤 실제 추천 기관을 조회하고 사람의 선택으로 전달합니다."
                : "우리 기관에 전달된 사건의 저장 경로와 대응 정보를 조회할 수 있습니다."}
            </p>

            {isAdmin && <AgencyRoutePreview key={`${session.version}:${detail.id}`} session={session} incidentId={detail.id} />}
            {isAdmin && (
              <button
                className="primary"
                disabled={
                  updating
                }
                onClick={openPicker}
              >
                추천 기관 확인·전달
              </button>
            )}
          </section>

          <LiveSupportRequestsPanel
            key={`${session.version}:${detail.id}`}
            session={session}
            incidentId={detail.id}
            refreshKey={refreshKey}
          />
        </>
      )}
    </>
  );
}
