/**
 * 흐름: 기존 화면 유지 → Android 알림 이벤트 연결 → 인증 완료 대기 → 본인 사건 상세 표시.
 * 주요 기능: 종료 상태의 알림 터치, 계정 변경 시 상세 차단, 샘플 사건과 실제 사건의 분리.
 * 기존 인증 Backend를 모바일 화면에 연결하고 JWT 복원 후 connectNotificationSession을 재사용합니다.
 * onLogout에서는 기존 알림 기기 해제가 성공한 뒤 저장된 JWT만 삭제합니다.
 * 실제 사건 상세·경로·지원요청은 조회된 사건과 원래 진입 목록을 함께 유지합니다.
 */
import { useState, useRef, useEffect, useSyncExternalStore } from "react";
import {
  View,
  Text,
  Pressable,
  ScrollView,
  SafeAreaView,
  Platform,
  StyleSheet,
} from "react-native";
import Svg, { Path } from "react-native-svg";
import { StatusBar } from "expo-status-bar";
import { incidentById, mobileScreens, mock } from "@octv/shared";
import { Background } from "./src/components/Background";
import {
  Brand,
  Link,
  Dialog,
  Button,
  T,
  type DialogState,
} from "./src/components/UI";
import { s, color } from "./src/styles/theme";
import type { Screen, Navigate } from "./src/navigation/types";
import { AuthScreens } from "./src/screens/AuthScreens";
import { LiveIncidentScreens } from "./src/screens/LiveIncidentScreens";
import { DetailScreen } from "./src/screens/DetailScreen";
import { LiveRoutesScreen } from "./src/screens/LiveRoutesScreen";
import { LiveSupportRequestScreen } from "./src/screens/LiveSupportRequestScreen";
import { RoutesScreen } from "./src/screens/RoutesScreen";
import { RequestScreen } from "./src/screens/RequestScreen";
import { NotificationScreen } from "./src/screens/NotificationScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";
import { notificationController } from "./src/notifications";
import { createAndroidPushDriver, startAndroidPush } from "./src/push";
import { mobileSession } from "./src/mobileSession";

// 인증 담당의 기존 화면을 보존하면서 알림이 검증한 사건만 별도 상태로 엽니다.
export function MobileApp({
  onLogout,
}: {
  onLogout?: () => void | Promise<void>;
}) {
  const notification = useSyncExternalStore(
    notificationController.subscribe,
    notificationController.getSnapshot,
    notificationController.getSnapshot,
  );
  const currentSession = useSyncExternalStore(
    mobileSession.subscribe,
    mobileSession.getSnapshot,
    mobileSession.getSnapshot,
  );
  const [notificationDetail, setNotificationDetail] = useState(false);
  const [pushError, setPushError] = useState<string | null>(null);
  const [pushInitialized, setPushInitialized] = useState(false);
  const navigationVersion = useRef(0);
  // 메뉴 이동 뒤 끝난 이전 조회와 확인창 콜백을 구분합니다.
  const navigationRequest = useRef(0);
  const detailOrigin = useRef<"notifications" | "incidents">("notifications");
  const [screen, setScreen] = useState<Screen>("login"),
    [id, setId] = useState("SEL-001"),
    [dialog, setDialog] = useState<DialogState | null>(null);
  const scroll = useRef<ScrollView>(null);

  // 앱 시작 시 저장된 Android JWT를 서버에서 재검증하고 알림 세션에 인계합니다.
  useEffect(() => {
    void mobileSession.restore();
  }, []);

  // 만료·로그아웃 상태에서는 이전 계정의 사건 화면을 즉시 닫습니다.
  useEffect(() => {
    if (currentSession.status === "ready") {
      setScreen((old) =>
        ["login", "signup-basic", "signup-agency", "signup-complete"].includes(
          old,
        )
          ? "home"
          : old,
      );
    } else if (currentSession.status === "waiting") {
      setNotificationDetail(false);
      setScreen((old) =>
        ["login", "signup-basic", "signup-agency", "signup-complete"].includes(
          old,
        )
          ? old
          : "login",
      );
    }
  }, [currentSession.status, currentSession.user?.id]);

  // 알림 API가 401로 세션을 끊으면 저장된 JWT도 만료 처리합니다.
  useEffect(() => {
    if (
      currentSession.status === "ready" &&
      notification.status === "waiting"
    ) {
      void mobileSession.invalidate(currentSession.api ?? undefined);
    }
  }, [currentSession.status, currentSession.api, notification.status]);

  // 계정·사건·화면이 달라지거나 인증이 풀리면 이전 확인창도 닫습니다.
  useEffect(() => {
    setDialog(null);
  }, [
    notification.user,
    notification.status,
    notification.incident?.id,
    currentSession.api,
    screen,
  ]);

  // 리스너는 앱당 한 번 연결하고, 드라이버 준비 전에 앱이 닫히면 뒤늦게 등록하지 않습니다.
  useEffect(() => {
    let active = true;
    const stop = startAndroidPush({
      onResponse: (data, key) =>
        notificationController.handleNotificationResponse(data, key),
      onReceived: () => {
        void notificationController.refreshNotifications();
      },
      onTokenChanged: () => {
        void notificationController.refreshDeviceRegistration();
      },
      shouldPresent: () => {
        const state = notificationController.getSnapshot();
        return (
          state.status === "ready" && !!state.user && state.enabled === true
        );
      },
      onStatus: (status) => {
        if (active)
          setPushError(status.state === "ready" ? null : status.message);
      },
    });
    void createAndroidPushDriver()
      .then((driver) => {
        if (active) {
          notificationController.setDeviceDriver(driver);
          setPushInitialized(true);
        }
      })
      .catch(() => {
        if (active)
          setPushError(
            "알림 연결을 준비하지 못했습니다. 앱을 다시 열어주세요.",
          );
      });
    return () => {
      active = false;
      stop();
      notificationController.setDeviceDriver(null);
    };
  }, []);

  // 서버 권한 확인이 완료된 새 사건만 화면을 이동시킵니다. ID를 mock 조회 함수에 넣지 않습니다.
  useEffect(() => {
    if (navigationVersion.current === notification.navigationVersion) return;
    navigationVersion.current = notification.navigationVersion;
    if (notification.status !== "ready" || !notification.incident) return;
    if (notification.openedNotificationId)
      detailOrigin.current = "notifications";
    navigationRequest.current += 1;
    setDialog(null);
    setNotificationDetail(true);
    setScreen("detail");
    scroll.current?.scrollTo({ y: 0, animated: false });
  }, [
    notification.navigationVersion,
    notification.status,
    notification.incident,
  ]);

  const go: Navigate = (next, incident) => {
    const session = mobileSession.getSnapshot();
    // 기존 로그인 화면을 거치지 않고 샘플 사건 화면으로 진입하지 않게 합니다.
    if (
      session.status !== "ready" &&
      !["login", "signup-basic", "signup-agency", "signup-complete"].includes(
        next,
      )
    ) {
      navigationRequest.current += 1;
      setDialog(null);
      setScreen("login");
      return;
    }
    const opened = notificationController.getSnapshot();
    const actualIncident =
      notificationDetail &&
      session.api === currentSession.api &&
      opened.status === "ready" &&
      opened.user?.id === session.user?.id
        ? opened.incident
        : null;
    // 같은 실제 사건의 상세·경로·지원요청 이동에서는 사건과 원래 목록을 보존합니다.
    if (
      notificationDetail &&
      ["detail", "routes", "request"].includes(next) &&
      (!incident || incident === String(actualIncident?.id))
    ) {
      if (actualIncident || next === "detail") {
        if (screen !== next) navigationRequest.current += 1;
        setScreen(next);
        scroll.current?.scrollTo({ y: 0, animated: false });
      } else {
        setDialog({
          title: "사건 조회 안내",
          body: "사건 정보를 다시 확인한 뒤 이용해주세요.",
          cancel: false,
        });
      }
      return;
    }
    const requestVersion = ++navigationRequest.current;
    // 실제 DB 번호는 항상 서버 상세 조회로 보내고, 알 수 없는 번호를 샘플 사건으로 대체하지 않습니다.
    if (incident && /^[1-9]\d*$/.test(incident)) {
      if (next === "detail") {
        detailOrigin.current = "incidents";
        const ownerApi = session.api;
        const openedVersion = opened.navigationVersion;
        void notificationController.openIncident(incident).then((opened) => {
          if (
            !opened &&
            requestVersion === navigationRequest.current &&
            mobileSession.getSnapshot().status === "ready" &&
            mobileSession.getSnapshot().api === ownerApi &&
            notificationController.getSnapshot().navigationVersion ===
              openedVersion
          ) {
            setDialog({
              title: "사건 조회 안내",
              body: "사건 상세를 확인하지 못했습니다. 목록에서 다시 시도해주세요.",
              cancel: false,
            });
          }
        });
      } else
        setDialog({
          title: "이용 안내",
          body: "이 사건의 해당 기능은 아직 제공되지 않습니다.",
          cancel: false,
        });
      return;
    }
    if (
      notificationDetail &&
      ["detail", "live", "routes", "request"].includes(next)
    ) {
      setDialog({
        title: "이용 안내",
        body: "이 사건의 해당 기능은 아직 제공되지 않습니다.",
        cancel: false,
      });
      return;
    }
    // 아직 상세가 열리기 전이라도 사용자가 다른 메뉴를 택하면 진행 중인 조회를 취소 처리합니다.
    setNotificationDetail(false);
    notificationController.clearOpenedIncident();
    setScreen(next);
    if (incident) setId(incident);
    scroll.current?.scrollTo({ y: 0, animated: false });
  };
  // 화면을 떠난 뒤 도착한 내비 결과나 이전 사건의 확인창은 현재 화면에 표시하지 않습니다.
  const incidentViewVersion = navigationRequest.current;
  const showIncidentDialog = (value: DialogState) => {
    const isCurrent = () => {
      const session = mobileSession.getSnapshot();
      const opened = notificationController.getSnapshot();
      return (
        incidentViewVersion === navigationRequest.current &&
        session.status === "ready" &&
        session.api === currentSession.api &&
        opened.status === "ready" &&
        opened.user?.id === session.user?.id &&
        !!opened.incident &&
        opened.incident.id === notification.incident?.id &&
        opened.navigationVersion === notification.navigationVersion
      );
    };
    if (!isCurrent()) return;
    setDialog({
      ...value,
      onConfirm: value.onConfirm
        ? () => {
            if (isCurrent()) value.onConfirm?.();
          }
        : undefined,
    });
  };
  const auth = [
      "login",
      "signup-basic",
      "signup-agency",
      "signup-complete",
    ].includes(screen),
    d = incidentById(id),
    title = mobileScreens.find((x) => x[2] === screen)?.[1] || "";
  const back: Partial<Record<Screen, [Screen, string]>> = {
    detail: notificationDetail
      ? detailOrigin.current === "notifications"
        ? ["notifications", "알림 목록"]
        : ["incidents", "사건 목록"]
      : ["incidents", "사건 목록"],
    live: ["incidents", "사건 목록"],
    routes: ["detail", "사건 상세"],
    request: ["detail", "사건 상세"],
    notifications: ["home", "홈"],
    "signup-basic": ["login", "로그인"],
    "signup-agency": ["signup-basic", "회원가입"],
    "signup-complete": ["login", "로그인"],
  };
  function navigate(next: Screen) {
    if (screen === "request")
      (notificationDetail ? showIncidentDialog : setDialog)({
        title: "작성 화면을 나갈까요?",
        body: "입력 내용은 저장되지 않습니다.",
        confirm: "이동",
        onConfirm: () => go(next),
      });
    else go(next);
  }
  return (
    <View style={{ flex: 1, backgroundColor: color.bg }}>
      <StatusBar style="light" />
      <Background />
      <SafeAreaView
        style={{
          flex: 1,
          width: "100%",
          maxWidth: 460,
          alignSelf: "center",
          backgroundColor: "rgba(7,16,24,0.34)",
          borderLeftWidth: 1,
          borderRightWidth: 1,
          borderColor: "#789bad1c",
        }}
      >
        <ScrollView
          ref={scroll}
          contentContainerStyle={{ paddingBottom: auth ? 40 : 104 }}
          keyboardShouldPersistTaps="handled"
        >
          {screen !== "login" && (
            <View
              style={{
                paddingHorizontal: 20,
                paddingTop: 22,
                paddingBottom: 15,
                backgroundColor: "rgba(9,18,26,.86)",
                borderBottomWidth: 1,
                borderColor: color.line,
              }}
            >
              <View style={s.row}>
                <Brand />
                {!auth && (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="알림"
                    onPress={() => navigate("notifications")}
                    style={{
                      padding: 8,
                      marginLeft: "auto",
                      borderWidth: 1,
                      borderColor: color.line,
                      borderRadius: 7,
                    }}
                  >
                    <Svg width={22} height={22} viewBox="0 0 24 24">
                      <Path
                        d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M9 21h6"
                        stroke={color.cyan}
                        strokeWidth={1.6}
                        fill="none"
                      />
                    </Svg>
                  </Pressable>
                )}
              </View>
              {back[screen] && (
                <Link onPress={() => navigate(back[screen]![0])}>
                  ‹ {back[screen]![1]}
                </Link>
              )}
              <Text style={[s.title, { marginTop: 14, marginBottom: 2 }]}>
                {title}
              </Text>
              {(screen === "home" || screen === "incidents") && (
                <Text style={s.muted}>
                  {currentSession.status === "ready"
                    ? "현재 로그인 기관에 전달된 실제 사건 목록입니다."
                    : "로그인 후 소속기관에 전달된 사건을 확인할 수 있습니다."}
                </Text>
              )}
            </View>
          )}
          <View
            key={
              screen +
              "|" +
              (notificationDetail
                ? (notification.incident?.id ?? "restricted")
                : id)
            }
            style={{ paddingHorizontal: 20, paddingTop: 20 }}
          >
            {pushError &&
              (screen === "notifications" || screen === "settings") && (
                <View style={s.info}>
                  <T>{pushError}</T>
                </View>
              )}
            {currentSession.status === "checking" ? (
              <View style={s.panel}>
                <T>저장된 로그인 상태를 확인하고 있습니다.</T>
              </View>
            ) : notificationDetail &&
              ["detail", "routes", "request"].includes(screen) ? (
              currentSession.status === "ready" &&
              notification.status === "ready" &&
              notification.user?.id === currentSession.user?.id &&
              notification.incident ? (
                screen === "routes" ? (
                  <LiveRoutesScreen
                    incident={notification.incident}
                    go={go}
                    show={showIncidentDialog}
                  />
                ) : screen === "request" ? (
                  <LiveSupportRequestScreen
                    incident={notification.incident}
                    go={go}
                    show={showIncidentDialog}
                  />
                ) : (
                  <DetailScreen
                    actualIncident={notification.incident}
                    go={go}
                    backTo={detailOrigin.current}
                  />
                )
              ) : (
                <View style={s.panel}>
                  <T>
                    {notification.error ??
                      (notification.status === "ready"
                        ? "사건 정보를 확인하고 있습니다."
                        : "로그인 후 사건정보를 다시 확인해주세요.")}
                  </T>
                  <Button onPress={() => go(detailOrigin.current)}>
                    {detailOrigin.current === "notifications"
                      ? "알림 목록으로"
                      : "사건 목록으로"}
                  </Button>
                </View>
              )
            ) : auth ? (
              <>
                {currentSession.message && screen === "login" && (
                  <View style={s.info}>
                    <T>{currentSession.message}</T>
                  </View>
                )}
                <AuthScreens
                  screen={screen}
                  go={go}
                  show={setDialog}
                  onLogin={mobileSession.login}
                />
              </>
            ) : screen === "home" || screen === "incidents" ? (
              <LiveIncidentScreens home={screen === "home"} go={go} />
            ) : screen === "detail" || screen === "live" ? (
              <DetailScreen incident={d} live={screen === "live"} go={go} />
            ) : screen === "routes" ? (
              <RoutesScreen incident={d} show={setDialog} />
            ) : screen === "request" ? (
              <RequestScreen incident={d} go={go} show={setDialog} />
            ) : screen === "notifications" ? (
              <NotificationScreen go={go} show={setDialog} />
            ) : (
              <SettingsScreen
                go={go}
                show={setDialog}
                // 설치 UUID를 읽을 준비가 끝나야 기존 기기 연결의 해제를 확인할 수 있습니다.
                onLogout={
                  pushInitialized
                    ? async () => {
                        await onLogout?.();
                        await mobileSession.logout();
                      }
                    : undefined
                }
              />
            )}
          </View>
        </ScrollView>
        {!auth && (
          <View
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              height: 80,
              backgroundColor: "#08121bef",
              borderTopWidth: 1,
              borderColor: color.line,
              paddingHorizontal: 18,
              paddingVertical: 9,
              flexDirection: "row",
              gap: 6,
            }}
          >
            {(
              [
                ["home", "홈", "⌂"],
                ["incidents", "사건", "▤"],
                ["settings", "설정", "⚙"],
              ] as const
            ).map(([next, label, icon]) => (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={label}
                key={next}
                onPress={() => navigate(next)}
                style={{
                  flex: 1,
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 3,
                  borderRadius: 9,
                  backgroundColor:
                    screen === next ||
                    (next === "incidents" &&
                      [
                        "detail",
                        "live",
                        "routes",
                        "request",
                        "notifications",
                      ].includes(screen))
                      ? "#337d9a20"
                      : "transparent",
                }}
              >
                <Text style={{ fontSize: 23, color: color.cyan }}>{icon}</Text>
                <Text style={{ fontSize: 12, color: color.muted }}>
                  {label}
                </Text>
              </Pressable>
            ))}
          </View>
        )}
      </SafeAreaView>
      <Dialog value={dialog} close={() => setDialog(null)} />
    </View>
  );
}

// Expo 진입점은 인자 없이 등록합니다. 인증 담당이 연결할 때 MobileApp의 onLogout을 전달합니다.
export default function App() {
  return <MobileApp />;
}
