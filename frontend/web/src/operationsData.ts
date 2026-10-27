/** 운영 API 타입·조회 훅. 기존 로그인 세션을 재사용하고 화면 이탈 후 응답을 폐기합니다. */
import { useEffect, useState } from "react";
import { ApiError } from "./api";
import { requestWebApi, type WebIncidentSession } from "./incidentData";
import { pollWhileVisible } from "./polling";

export type Cctv = {
  id: number;
  external_cctv_id: string;
  name: string;
  provider: string;
  address: string | null;
  latitude: number;
  longitude: number;
  region_code: string | null;
  sido_name: string | null;
  sigungu_name: string | null;
  is_monitored: boolean;
  monitored_mode: "BASE" | "OFF" | "ALERT" | "POST_ALERT" | "VERIFY" | null;
  connection_status: string;
  video_quality_status: string | null;
  analysis_status: string | null;
  last_frame_at: string | null;
};
export type SettingsValues = {
  base_analysis_interval_sec: number;
  alert_analysis_interval_sec: number;
  verify_analysis_interval_sec: number;
  candidate_confidence_threshold: string | number;
  candidate_min_detection_count: number;
  temporal_validation_sec: number;
  incident_confidence_threshold: string | number;
  reconnect_interval_sec: number;
  max_reconnect_attempts: number;
  quality_threshold: string | number;
};
export type MonitoringSettings = SettingsValues & {
  id: number;
  updated_by: number | null;
  updated_at: string;
  application: Record<
    keyof SettingsValues,
    {
      mode: "NEXT_POLL" | "RESTART_REQUIRED" | "NOT_CONNECTED";
      description: string;
    }
  >;
};
export type Stats = {
  filters: { start: string; end: string; confirmed_only: boolean };
  timezone: string;
  total_incident_count: number;
  confirmed_incident_count: number;
  average_confidence: number | null;
  by_status: Record<string, number>;
  by_hazard: Record<string, number>;
  by_risk: Record<string, number>;
  by_priority: Record<string, number>;
  confidence_distribution: Record<string, number>;
  daily: { day: string; count: number }[];
  hourly: { hour: number; count: number }[];
};
export function operationsError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return "로그인이 만료되었습니다. 다시 로그인해주세요.";
    if (error.status === 403) return "관리자 권한이 필요합니다.";
    if (error.status === 409) return error.message;
    if (error.status === 422) return "입력 범위와 조회 기간을 확인해주세요.";
    if (error.status === 502)
      return "영상 준비 실패 · UTIC·MediaMTX 연결을 확인해주세요.";
  }
  return "조회 또는 저장에 실패했습니다. 연결을 확인하고 다시 조회해주세요.";
}
export function useOperations<T>(
  session: WebIncidentSession,
  path: string | null,
  revision = 0,
  pollIntervalMs = 0,
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setData(null);
    setError(null);
    setLoading(!!path);
    if (!path) return;
    return pollWhileVisible(
      (signal) => requestWebApi<T>(session.version, path, { signal }),
      {
        intervalMs: pollIntervalMs,
        onValue: (value) => {
          setData(value);
          setError(null);
        },
        onError: (reason) => {
          setData(null);
          setError(operationsError(reason));
        },
        onSettled: () => setLoading(false),
      },
    );
  }, [session.version, path, revision, pollIntervalMs]);
  return { data, error, loading };
}
export const monitoringLabels: Record<string, string> = {
  BASE: "ON · 기본 감시",
  OFF: "OFF",
  ALERT: "ON · 특보 감시",
  POST_ALERT: "ON · 특보 해제 후 확인 대기",
  VERIFY: "ON · 집중 검증",
};
export const stateLabels: Record<string, string> = {
  CONNECTED: "연결됨",
  DISCONNECTED: "연결 끊김",
  RECONNECTING: "재연결 중",
  GOOD: "양호",
  LOW: "낮음",
  UNAVAILABLE: "확인 불가",
  RUNNING: "분석 중",
  STOPPED: "분석 중지",
  ERROR: "오류",
  DETECTED: "탐지됨",
  CONFIRMED: "사건 확인",
  SENT: "전달 완료",
  RESOLVED: "종결",
  FALSE_POSITIVE: "오탐",
  HIGH: "높음",
  MEDIUM: "보통",
  LOW_RISK: "낮음",
  UNASSESSED: "분석 대기",
  PENDING: "분석 대기",
  READY: "분석 완료",
  PROCESSING: "처리 중",
  NEEDS_REVIEW: "추가 확인 필요",
  RECOMMENDED: "추천됨",
  DELIVERED: "전달됨",
  COMPLETED: "대응 완료",
  OFF: "중지",
  IDLE: "대기",
  QUEUED: "작업 등록",
  VERIFIED: "검증 완료",
  DISQUALIFIED: "제외",
  PARTIAL: "부분 완료",
  NO_ROUTES: "경로 없음",
  NO_CANDIDATES: "후보 없음",
  NOT_FOUND: "조회 결과 없음",
  UNKNOWN: "상태 미확인",
};
export function statusLabel(value: string | null) {
  return value ? (stateLabels[value] ?? (/^[A-Z][A-Z0-9_]*$/.test(value) ? "확인 필요" : value)) : "미확인";
}
export function seoulDate(value = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${map.year}-${map.month}-${map.day}`;
}
