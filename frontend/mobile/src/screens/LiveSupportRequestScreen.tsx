/**
 * 후속-06 · 모바일 실제 추가 지원 요청
 * 흐름: 기존 로그인 JWT + 전달받은 사건 → 본인 기관 권한 API → 요청 등록/목록 재조회.
 * 기존 예시 RequestScreen은 보존하고, 이 화면은 서버가 확인한 실제 사건만 받습니다.
 * POST 응답을 못 받았다고 자동 재전송하지 않습니다. 저장 여부는 먼저 목록에서 확인합니다.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import type { IncidentDto } from "@octv/shared";
import { ApiError } from "../api";
import { mobileSession } from "../mobileSession";
import { Badge, Button, Field, T, type ShowDialog } from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate } from "../navigation/types";
import { incidentDisplayNo, agencyDeliveryStatusLabel } from "../incidentLabel";

type SupportType = "PERSONNEL" | "EQUIPMENT" | "TRAFFIC_CONTROL" | "OTHER";
type SupportItem = {
  id: number;
  incident_id: number;
  agency_id: number;
  responder_id: number;
  support_type: SupportType;
  request_content: string;
  created_at: string;
  responder_name: string | null;
  agency_name: string | null;
};
type AgencyRouteState = { recommendation_status: string | null };
type SaveStatus = "idle" | "saving" | "unknown" | "blocked";
const types: ReadonlyArray<{ value: SupportType; label: string }> = [
  { value: "PERSONNEL", label: "인력" },
  { value: "EQUIPMENT", label: "장비" },
  { value: "TRAFFIC_CONTROL", label: "교통 통제" },
  { value: "OTHER", label: "기타" },
];
const typeName = (value: SupportType): string =>
  types.find((item) => item.value === value)?.label ?? value;

function koreanTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "시각 확인 불가"
    : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

export function LiveSupportRequestScreen({
  incident,
  go,
  show,
}: {
  incident: IncidentDto;
  go: Navigate;
  show: ShowDialog;
}) {
  const session = useSyncExternalStore(
    mobileSession.subscribe,
    mobileSession.getSnapshot,
    mobileSession.getSnapshot,
  );
  const api = session.status === "ready" ? session.api : null;
  const agencyId = session.user?.agency_id ?? null;
  const [type, setType] = useState<SupportType>("PERSONNEL");
  const [content, setContent] = useState("");
  const [items, setItems] = useState<SupportItem[]>([]);
  const [agencyStatus, setAgencyStatus] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const saveGuard = useRef<SaveStatus>("idle");
  const mounted = useRef(false);
  const requestVersion = useRef(0);
  const [listStatus, setListStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [listError, setListError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const resource = `/api/support-requests/incidents/${incident.id}`;
  const busy = saveStatus === "saving";

  function changeSaveStatus(next: SaveStatus) {
    // ref는 같은 확인 콜백의 재진입을 즉시 막고, state는 화면 표시를 갱신합니다.
    saveGuard.current = next;
    setSaveStatus(next);
  }

  useEffect(() => {
    mounted.current = true;
    changeSaveStatus("idle");
    setContent("");
    setType("PERSONNEL");
    setMessage(null);
    return () => {
      mounted.current = false;
      requestVersion.current += 1;
    };
  }, [api, agencyId, incident.id]);

  useEffect(() => {
    if (!api || !agencyId) {
      setItems([]);
      setAgencyStatus(null);
      return;
    }
    let active = true;
    const ownerApi = api;
    const version = ++requestVersion.current;
    // 결과 불명인 POST가 끝난 뒤 시작한 조회만 재등록 잠금을 해제할 수 있습니다.
    const canResolveUnknown = saveGuard.current === "unknown";
    const isCurrent = () =>
      active &&
      mounted.current &&
      version === requestVersion.current &&
      mobileSession.getSnapshot().api === ownerApi;
    setItems([]);
    setAgencyStatus(null);
    setListStatus("loading");
    setListError(null);
    // 지원요청 내역과 본인 기관 전달 상태는 서로 독립적으로 조회합니다.
    void ownerApi<SupportItem[]>(resource)
      .then((rows) => {
        if (!isCurrent()) return;
        if (!Array.isArray(rows))
          throw new Error("지원요청 목록 응답 확인 필요");
        setItems(rows);
        setListStatus("ready");
        if (canResolveUnknown && saveGuard.current === "unknown") {
          changeSaveStatus("idle");
          setMessage(
            "목록을 다시 조회했습니다. 같은 요청이 이미 저장됐는지 확인하고, 없는 경우에만 다시 등록해주세요.",
          );
        }
      })
      .catch((error) => {
        if (!isCurrent()) return;
        setListStatus("error");
        if (error instanceof ApiError && error.status === 401) {
          void mobileSession.invalidate(ownerApi);
        } else
          setListError("지원요청 목록 조회에 실패했습니다. 다시 확인해주세요.");
      });
    void ownerApi<AgencyRouteState>(
      `/api/routes/incidents/${incident.id}/agencies/${agencyId}`,
    )
      .then((response) => {
        if (isCurrent()) setAgencyStatus(response.recommendation_status);
      })
      .catch(() => {
        if (isCurrent()) setAgencyStatus(null);
      });
    return () => {
      active = false;
    };
  }, [api, agencyId, incident.id, reload]);

  const canSend =
    !!api &&
    saveStatus === "idle" &&
    listStatus === "ready" &&
    incident.status === "SENT" &&
    agencyStatus === "DELIVERED" &&
    content.trim().length > 0 &&
    content.trim().length <= 2000;

  async function submit(): Promise<void> {
    if (
      !canSend ||
      !api ||
      !mounted.current ||
      saveGuard.current !== "idle" ||
      mobileSession.getSnapshot().api !== api
    )
      return;
    const ownerApi = api;
    const version = ++requestVersion.current;
    const requestContent = content.trim();
    const isCurrent = () =>
      mounted.current &&
      version === requestVersion.current &&
      mobileSession.getSnapshot().api === ownerApi;
    changeSaveStatus("saving");
    setMessage(null);
    try {
      const saved = await ownerApi<SupportItem>(resource, {
        method: "POST",
        body: JSON.stringify({
          support_type: type,
          request_content: requestContent,
        }),
      });
      if (!isCurrent()) return;
      // 다른 사건·기관의 응답이나 불완전한 성공 응답을 저장 완료로 표시하지 않습니다.
      if (
        !saved ||
        !Number.isSafeInteger(saved.id) ||
        saved.id <= 0 ||
        saved.incident_id !== incident.id ||
        saved.agency_id !== agencyId ||
        saved.responder_id !== session.user?.id ||
        saved.support_type !== type ||
        saved.request_content !== requestContent
      )
        throw new Error("지원요청 저장 응답 확인 필요");
      setContent("");
      changeSaveStatus("idle");
      setMessage("요청이 DB에 저장됐습니다. 목록에서 확인할 수 있습니다.");
    } catch (error) {
      if (!isCurrent()) return;
      if (error instanceof ApiError && error.status === 401) {
        void mobileSession.invalidate(ownerApi);
      } else if (
        error instanceof ApiError &&
        (error.status === 403 || error.status === 404)
      ) {
        changeSaveStatus("blocked");
        setMessage(
          "이 사건에 지원요청을 등록할 권한이 없습니다. 사건 목록에서 접근 가능한 사건을 다시 확인해주세요.",
        );
      } else if (error instanceof ApiError && error.status === 409) {
        changeSaveStatus("blocked");
        setMessage(
          "사건 또는 기관 상태가 변경되어 등록하지 못했습니다. 사건 목록에서 사건을 다시 조회해주세요.",
        );
      } else if (error instanceof ApiError && error.status === 422) {
        changeSaveStatus("idle");
        setMessage(
          "요청 입력값이 올바르지 않습니다. 요청 유형과 내용을 확인해주세요.",
        );
      } else {
        // 응답 유실 시 실제 저장됐을 수 있습니다. POST를 자동으로 반복하지 않습니다.
        changeSaveStatus("unknown");
        setMessage(
          "요청 결과를 확정할 수 없습니다. 목록에서 저장 여부를 확인해주세요.",
        );
      }
    } finally {
      if (isCurrent()) {
        setListStatus("loading");
        setReload((value) => value + 1);
      }
    }
  }

  function refresh() {
    if (
      !mounted.current ||
      saveGuard.current === "saving" ||
      mobileSession.getSnapshot().api !== api
    )
      return;
    // 새 조회를 선택하면 이전 조회 결과와 이전 확인창 콜백을 즉시 무효화합니다.
    requestVersion.current += 1;
    setListStatus("loading");
    setReload((value) => value + 1);
  }

  if (!api || !agencyId) return <T>로그인한 기관의 세션을 확인해주세요.</T>;
  return (
    <>
      <Badge priority={incident.priority ?? "평가 대기"} />
      <Text style={[s.title, { marginTop: 13 }]}>
        추가 지원요청 · {incidentDisplayNo(incident)}
      </Text>
      <T muted>기관: {session.user?.agency_name ?? `#${agencyId}`}</T>
      <View style={[s.info, { marginVertical: 16 }]}>
        <T>현재 기관 전달 상태: {agencyDeliveryStatusLabel(agencyStatus)}</T>
        <T muted>
          기관에 전달된 사건만 추가 지원요청을 등록할 수 있습니다.
        </T>
      </View>
      <T>요청 유형</T>
      <View
        style={{
          flexDirection: "row",
          flexWrap: "wrap",
          gap: 10,
          marginVertical: 12,
        }}
      >
        {types.map((option) => (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: type === option.value }}
            disabled={busy}
            onPress={() => setType(option.value)}
            style={{
              width: "47%",
              padding: 12,
              borderWidth: 1,
              borderRadius: 9,
              borderColor: type === option.value ? "#5dbad6" : color.line,
              backgroundColor:
                type === option.value ? "#2e789536" : "transparent",
            }}
          >
            <T>
              {type === option.value ? "◉" : "○"} {option.label}
            </T>
          </Pressable>
        ))}
      </View>
      <Field
        label="요청 내용"
        value={content}
        onChangeText={setContent}
        editable={!busy}
        placeholder="필요한 인력이나 장비, 현장 상황을 입력해주세요."
        maxLength={2000}
        multiline
        textAlignVertical="top"
        style={[s.input, { height: 150 }]}
      />
      <T muted>{content.length}/2000자 · 요청은 자동 출동 지령이 아닙니다.</T>
      {message && (
        <View style={s.info}>
          <T>{message}</T>
        </View>
      )}
      <Button
        disabled={!canSend}
        onPress={() => {
          if (!canSend || saveGuard.current !== "idle") return;
          const version = requestVersion.current;
          let consumed = false;
          show({
            title: "추가 지원 요청 확인",
            body: "현재 로그인 기관 이름으로 요청을 등록합니다. 계속할까요?",
            confirm: "요청 등록",
            onConfirm: () => {
              if (consumed) return;
              consumed = true;
              if (version !== requestVersion.current) return;
              void submit();
            },
          });
        }}
      >
        {busy ? "전달 중…" : "추가 지원 요청 등록"}
      </Button>
      <Button secondary disabled={busy} onPress={refresh}>
        저장 목록 새로고침
      </Button>
      <View style={{ marginTop: 18 }}>
        <Text style={s.h2}>우리 기관의 지원 요청 이력</Text>
        {listStatus === "loading" && <ActivityIndicator color={color.cyan} />}
        {listError && <T>{listError}</T>}
        {listStatus === "ready" && items.length === 0 && (
          <T muted>등록된 요청이 없습니다.</T>
        )}
        {items.map((item) => (
          <View key={item.id} style={s.panel}>
            <T>
              {typeName(item.support_type)} · {koreanTime(item.created_at)}
            </T>
            <T muted>{item.responder_name ?? `작성자 #${item.responder_id}`}</T>
            <T>{item.request_content}</T>
          </View>
        ))}
      </View>
      <Button secondary onPress={() => go("detail")}>
        사건 상세로 돌아가기
      </Button>
    </>
  );
}
