/**
 * 흐름: 알림에서 본인 사건 권한 확인 → 실제 IncidentDto 표시 → 필요하면 서버에서 다시 조회.
 * 기존 샘플 상세는 보존하고, 실제 사건에는 샘플 이미지·기관·경로를 섞지 않습니다.
 * 주요 기능: 실제 재난·위치·위험도·시각 표시, 미분석 값 구분, 알림 목록 복귀.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { View, Text, Pressable, Image } from "react-native";
import {
  hazardLabel,
  mock,
  type Incident,
  type IncidentDto,
} from "@octv/shared";
import {
  Badge,
  T,
  Button,
  Panel,
  Pair,
  type ShowDialog,
} from "../components/UI";
import { Camera } from "../components/Camera";
import { s, color } from "../styles/theme";
import { mobileSession } from "../mobileSession";
import { ApiError } from "../api";
import type { Navigate } from "../navigation/types";
import {
  notificationController,
  parseNotificationTime,
} from "../notifications";

// API에서 받은 UTC 시각만 한국 시간으로 변환합니다.
function incidentTime(value: string) {
  return (
    parseNotificationTime(value)?.toLocaleString("ko-KR", {
      timeZone: "Asia/Seoul",
    }) ?? "시각 확인 불가"
  );
}

type RecommendationStatus = "RECOMMENDED" | "DELIVERED" | "COMPLETED";

type RecommendationResponse = {
  items: {
    agency_id: number;
    recommendation_status: RecommendationStatus;
  }[];
};

type CompletionResponse = {
  incident_id: number;
  agency_id: number;
  agency_recommendation_id: number;
  recommendation_status: "COMPLETED";
  incident_status: IncidentDto["status"];
};

// 실제 사건에는 API에 없는 기상·경로·샘플 이미지를 채워 넣지 않습니다.
function DeliveredIncidentDetail({
  incident,
  go,
  backTo,
  show,
}: {
  incident: IncidentDto;
  go: Navigate;
  backTo: "notifications" | "incidents";
  show?: ShowDialog;
}) {
  const notificationState = useSyncExternalStore(
    notificationController.subscribe,
    notificationController.getSnapshot,
    notificationController.getSnapshot,
  );

  const session = useSyncExternalStore(
    mobileSession.subscribe,
    mobileSession.getSnapshot,
    mobileSession.getSnapshot,
  );

  const [agencyStatus, setAgencyStatus] = useState<RecommendationStatus | null>(
    null,
  );

  const [completionBusy, setCompletionBusy] = useState(false);

  const [completionMessage, setCompletionMessage] = useState<string | null>(
    null,
  );

  const api = session.status === "ready" ? session.api : null;

  const agencyId = session.user?.agency_id ?? null;

  const isResponder = session.user?.role === "RESPONDER";

  // 로그인 JWT를 이미지 주소에 붙이지 않고 인증 헤더로 전달합니다.
  const imageSource = mobileSession.incidentImageSource(incident);

  // RESPONDER는 자기 기관의 전달 상태를 먼저 확인합니다.
  useEffect(() => {
    if (!isResponder || !api || !agencyId) {
      setAgencyStatus(null);
      setCompletionMessage(null);
      return;
    }

    let active = true;
    const ownerApi = api;

    setAgencyStatus(null);

    void ownerApi<RecommendationResponse>(
      `/api/agencies/incidents/${incident.id}/recommendations`,
    )
      .then((response) => {
        if (!active || mobileSession.getSnapshot().api !== ownerApi) {
          return;
        }

        const mine = response.items.find((item) => item.agency_id === agencyId);

        setAgencyStatus(mine?.recommendation_status ?? null);
      })
      .catch((error) => {
        if (!active || mobileSession.getSnapshot().api !== ownerApi) {
          return;
        }

        if (error instanceof ApiError && error.status === 401) {
          void mobileSession.invalidate(ownerApi);
        }

        setAgencyStatus(null);
      });

    return () => {
      active = false;
    };
  }, [api, agencyId, incident.id, isResponder]);

  async function completeDelivery(): Promise<void> {
    if (
      !api ||
      !agencyId ||
      !isResponder ||
      completionBusy ||
      agencyStatus !== "DELIVERED" ||
      incident.status !== "SENT"
    ) {
      return;
    }

    const ownerApi = api;

    setCompletionBusy(true);
    setCompletionMessage(null);

    try {
      const result = await ownerApi<CompletionResponse>(
        `/api/agencies/incidents/${incident.id}/complete`,
        {
          method: "PATCH",
        },
      );

      if (
        result.incident_id !== incident.id ||
        result.agency_id !== agencyId ||
        result.recommendation_status !== "COMPLETED"
      ) {
        throw new Error("대응 완료 응답을 확인할 수 없습니다.");
      }

      if (mobileSession.getSnapshot().api !== ownerApi) {
        return;
      }

      setAgencyStatus("COMPLETED");

      setCompletionMessage(
        result.incident_status === "RESOLVED"
          ? "우리 기관의 대응 완료와 함께 사건이 종료됐습니다."
          : "우리 기관의 대응 완료 처리가 저장됐습니다.",
      );

      // 마지막 기관이면 사건 자체가 RESOLVED로 바뀔 수 있으므로 최신 사건 재조회.
      await notificationController.openIncident(incident.id);
    } catch (error) {
      if (mobileSession.getSnapshot().api !== ownerApi) {
        return;
      }

      if (error instanceof ApiError && error.status === 401) {
        void mobileSession.invalidate(ownerApi);

        setCompletionMessage("로그인이 만료되었습니다. 다시 로그인해주세요.");
      } else if (
        error instanceof ApiError &&
        (error.status === 403 || error.status === 404)
      ) {
        setCompletionMessage(
          "이 사건의 대응 완료 권한이 없거나 우리 기관에 전달되지 않은 사건입니다.",
        );
      } else if (error instanceof ApiError && error.status === 409) {
        setCompletionMessage(
          "사건 또는 기관 상태가 변경됐습니다. 사건 정보를 다시 확인해주세요.",
        );
      } else {
        setCompletionMessage(
          "대응 완료 처리를 확인하지 못했습니다. 다시 조회한 뒤 시도해주세요.",
        );
      }
    } finally {
      if (mobileSession.getSnapshot().api === ownerApi) {
        setCompletionBusy(false);
      }
    }
  }

  const canComplete =
    isResponder &&
    !!show &&
    agencyStatus === "DELIVERED" &&
    incident.status === "SENT" &&
    !completionBusy;

  return (
    <>
      <Badge priority={incident.priority ?? "평가 대기"} />

      <Text style={[s.title, { marginTop: 13 }]}>
        {hazardLabel(incident.hazard_type)} · {incident.incident_no}
      </Text>

      <T muted>{incident.cctv_name}</T>

      <View style={[s.info, { marginVertical: 18 }]}>
        <T>
          수신 기관 ·{" "}
          {notificationState.user?.agency_name ?? "소속기관 확인 필요"}
        </T>

        <T muted>현재 계정에 허용된 사건정보입니다.</T>
      </View>

      {incident.representative_image_updated_at && imageSource && (
        <Panel title="대표 탐지 이미지">
          <Image
            source={imageSource}
            resizeMode="contain"
            style={{
              width: "100%",
              height: 200,
            }}
          />
        </Panel>
      )}

      <Panel title="사건 정보">
        <Pair label="사건 번호" value={incident.incident_no} />

        <Pair label="상태" value={incident.status} />

        <Pair label="CCTV" value={incident.cctv_name} />

        <Pair
          label="위도 / 경도"
          value={`${incident.latitude} / ${incident.longitude}`}
        />

        <Pair label="최초 탐지" value={incidentTime(incident.detected_at)} />

        <Pair
          label="최근 탐지"
          value={incidentTime(incident.last_detected_at)}
        />

        <T muted>시각은 한국 시간입니다.</T>
      </Panel>

      <Panel title="위험도 및 우선순위">
        <Pair
          label="분석 상태"
          value={
            incident.analysis_status === "READY" ? "분석 완료" : "분석 대기"
          }
        />

        <Pair label="위험도" value={incident.risk_level ?? "분석 대기"} />

        <Pair label="위험도 점수" value={incident.risk_score ?? "분석 대기"} />

        <Pair label="우선순위" value={incident.priority ?? "분석 대기"} />

        <Pair
          label="우선순위 점수"
          value={incident.priority_score ?? "분석 대기"}
        />

        <Pair
          label="탐지 신뢰도"
          value={`${(incident.confidence * 100).toFixed(1)}%`}
        />
      </Panel>

      {isResponder && (
        <Panel title="현장 대응">
          <Pair label="우리 기관 상태" value={agencyStatus ?? "확인 중"} />

          {completionMessage && <T muted>{completionMessage}</T>}

          <Button
            disabled={!canComplete}
            onPress={() => {
              if (!canComplete || !show) {
                return;
              }

              show({
                title: "현장 대응 완료",
                body: "우리 기관의 대응 상태를 완료로 변경합니다. 완료 처리 후에는 추가 지원요청을 등록할 수 없습니다. 계속할까요?",
                confirm: "대응 완료",
                onConfirm: () => {
                  void completeDelivery();
                },
              });
            }}
          >
            {completionBusy
              ? "대응 완료 처리 중…"
              : agencyStatus === "COMPLETED"
                ? "대응 완료 처리됨"
                : agencyStatus === "DELIVERED" && incident.status === "SENT"
                  ? "현장 대응 완료"
                  : "대응 완료 처리 불가"}
          </Button>
        </Panel>
      )}

      <Button onPress={() => go("routes", String(incident.id))}>
        경로 비교 상세
      </Button>

      <Button secondary onPress={() => go("request", String(incident.id))}>
        추가 지원요청
      </Button>

      <Button
        onPress={() => void notificationController.openIncident(incident.id)}
      >
        사건 정보 새로고침
      </Button>

      <Button secondary onPress={() => go(backTo)}>
        {backTo === "notifications" ? "알림 목록으로" : "사건 목록으로"}
      </Button>
    </>
  );
}

// 호출부에서 실제 사건과 기존 미리보기 사건을 명시적으로 구분합니다.
export function DetailScreen({
  incident: d,
  actualIncident,
  live = false,
  go,
  backTo = "notifications",
  show,
}: {
  incident?: Incident;
  actualIncident?: IncidentDto;
  live?: boolean;
  go: Navigate;
  backTo?: "notifications" | "incidents";
  show?: ShowDialog;
}) {
  if (actualIncident) {
    return (
      <DeliveredIncidentDetail
        incident={actualIncident}
        go={go}
        backTo={backTo}
        show={show}
      />
    );
  }

  if (!d) {
    return (
      <Panel>
        <T>표시할 사건정보가 없습니다.</T>
      </Panel>
    );
  }

  const camera = mock.cctvs.find((item) => item.id === d.camera);

  const connected = camera?.connected !== false;

  return (
    <>
      <Badge priority={d.priority} />

      <Text style={[s.title, { marginTop: 13 }]}>
        {d.type} · {d.id}
      </Text>

      <T muted>
        {d.location} · {d.camera}
      </T>

      <View style={[s.info, { marginTop: 18 }]}>
        <T>수신 기관 · {mock.profile.agency}</T>

        <T muted>소속 기관을 통해 전달된 사건정보입니다.</T>
      </View>

      {!live && (
        <View style={[s.row, { marginBottom: 22 }]}>
          {[
            ["위험도", d.risk],
            ["우선순위", d.score],
            ["신뢰도", d.confidence + "%"],
          ].map(([label, value]) => (
            <View
              key={label}
              style={{
                flex: 1,
                alignItems: "center",
              }}
            >
              <T muted>{label}</T>

              <Text
                style={{
                  color: color.fg,
                  fontSize: 27,
                  marginTop: 6,
                }}
              >
                {value}
              </Text>
            </View>
          ))}
        </View>
      )}

      <View style={s.tabs}>
        {[
          ["사건 정보", "detail"],
          ["실시간 영상", "live"],
        ].map(([label, route]) => (
          <Pressable
            key={route}
            accessibilityRole="tab"
            accessibilityState={{
              selected: live === (route === "live"),
            }}
            onPress={() => go(route as "detail" | "live", d.id)}
            style={[s.tab, live === (route === "live") && s.tabActive]}
          >
            <T>{label}</T>
          </Pressable>
        ))}
      </View>

      <Camera incident={d} live={live} connected={!live || connected} />

      <Text
        style={[
          s.muted,
          {
            fontSize: 10,
            marginVertical: 10,
          },
        ]}
      >
        {live ? "실시간 영상" : "대표 탐지 캡처"}
      </Text>

      {live ? (
        <Panel title="CCTV 상태">
          <Pair
            label="연결 상태"
            value={
              connected ? mock.uiSnapshot.cameraStatus.online : "연결 끊김"
            }
          />

          <Pair
            label="영상 품질"
            value={
              connected ? mock.uiSnapshot.cameraStatus.quality : "확인 불가"
            }
          />

          <Pair
            label="분석 상태"
            value={connected ? mock.uiSnapshot.cameraStatus.analysis : "중지"}
          />

          <Pair
            label="마지막 프레임"
            value={mock.uiSnapshot.cameraStatus.lastFrame}
          />
        </Panel>
      ) : (
        <Panel title="사건 상세정보">
          <Pair label="탐지 유형" value={d.type} />

          <Pair label="기상·수위" value={`${d.rain} mm / ${d.water} m`} />

          <Pair label="도로 통제" value={d.traffic} />

          <Pair label="수신 기관" value={mock.profile.agency} />

          <Pair label="판단 근거" value={d.reasons.join(" · ")} />
        </Panel>
      )}

      <Button onPress={() => go("routes", d.id)}>경로 비교 상세</Button>

      <Button secondary onPress={() => go("request", d.id)}>
        추가 지원요청
      </Button>
    </>
  );
}
