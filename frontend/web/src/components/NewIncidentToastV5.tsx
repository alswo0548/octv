/**
 * 관제 화면에서 새로 생성되는 Incident를 알려주는 읽기 전용 웹 알림.
 * 현재 로그인 세션과 기존 /api/incidents API만 재사용한다.
 * DB, YOLO, VERIFY, 사건화, FCM 코드 변경 없음.
 */
import { useEffect, useState } from "react";
import type { IncidentDto, PageDto } from "@octv/shared";
import { requestWebApi, type WebIncidentSession } from "../incidentData";
import { go } from "../routing/useRoute";

const HAZARD_LABELS: Record<string, string> = {
  flood: "침수",
  fallen_tree: "쓰러진 나무",
  severe_road_damage: "심각한 도로 파손",
  road_obstacle: "도로 장애물",
};

export function NewIncidentToastV5({ session }: { session: WebIncidentSession }) {
  const [notices, setNotices] = useState<IncidentDto[]>([]);

  useEffect(() => {
    // 현재 웹 관제 화면에 들어온 이후 새로 탐지된 사건만 표시한다.
    // 이전 시연에서 남은 DB 사건은 알림으로 재표시하지 않는다.
    const since = new Date().toISOString();
    const seen = new Set<number>();
    const aborter = new AbortController();
    let closed = false;
    let pending = false;

    async function check() {
      if (closed || pending || document.hidden) return;
      pending = true;
      try {
        const q = `/api/incidents?page=1&page_size=100&start=${encodeURIComponent(since)}`;
        const result = await requestWebApi<PageDto<IncidentDto>>(
          session.version, q, { signal: aborter.signal },
        );
        if (closed) return;
        const fresh = result.items.filter((item) => !seen.has(item.id));
        result.items.forEach((item) => seen.add(item.id));
        if (fresh.length) {
          // 최대 3건의 최신 알림만 남기고, 같은 Incident의 갱신은 중복 통지하지 않는다.
          setNotices((old) => [...old, ...fresh].slice(-3));
        }
      } catch {
        // 인증·네트워크 오류로 관제 화면 전체를 막지 않는다.
        // 기존 로그인/사건조회 오류 처리는 변경하지 않는다.
      } finally {
        pending = false;
      }
    }

    void check();
    const interval = window.setInterval(() => void check(), 4000);
    const onVisible = () => { if (!document.hidden) void check(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      closed = true;
      aborter.abort();
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [session.version]);

  if (!notices.length) return null;

  return (
    <aside
      aria-label="새 재난 사건 알림"
      aria-live="polite"
      style={{ position: "fixed", right: 20, bottom: 20, zIndex: 1200,
        width: "min(370px, calc(100vw - 40px))", display: "grid", gap: 10 }}
    >
      {notices.map((item) => (
        <div key={item.id} role="status"
          style={{ padding: "14px 16px", border: "1px solid #4e8399",
            borderRadius: 12, background: "#12232e", color: "#f0f7fc",
            boxShadow: "0 7px 30px #0008" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <strong>🚨 새 재난 사건 #{item.id}</strong>
            <button type="button" aria-label={`사건 ${item.id} 알림 닫기`}
              onClick={() => setNotices((old) => old.filter((x) => x.id !== item.id))}
              style={{ color: "inherit", background: "transparent", border: 0, cursor: "pointer" }}
            >×</button>
          </div>
          <p style={{ margin: "8px 0" }}>
            {HAZARD_LABELS[item.hazard_type] ?? item.hazard_type} · {item.cctv_name}
          </p>
          <small>탐지 신뢰도 {(item.confidence * 100).toFixed(1)}%</small>
          <div style={{ marginTop: 10 }}>
            <button type="button" className="primary" onClick={() => go("incidents")}>
              사건관리에서 확인
            </button>
          </div>
        </div>
      ))}
    </aside>
  );
}
