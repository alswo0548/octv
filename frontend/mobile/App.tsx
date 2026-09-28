import { useState, useRef } from "react";
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
import { Brand, Link, Dialog, type DialogState } from "./src/components/UI";
import { s, color } from "./src/styles/theme";
import type { Screen, Navigate } from "./src/navigation/types";
import { AuthScreens } from "./src/screens/AuthScreens";
import { IncidentScreens } from "./src/screens/IncidentScreens";
import { DetailScreen } from "./src/screens/DetailScreen";
import { RoutesScreen } from "./src/screens/RoutesScreen";
import { RequestScreen } from "./src/screens/RequestScreen";
import { NotificationScreen } from "./src/screens/NotificationScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";
/** UI navigation only: no auth guard, user object, network or persistence. */
export default function App() {
  const [screen, setScreen] = useState<Screen>("login"),
    [id, setId] = useState("SEL-001"),
    [dialog, setDialog] = useState<DialogState | null>(null);
  const scroll = useRef<ScrollView>(null);
  const go: Navigate = (next, incident) => {
    setScreen(next);
    if (incident) setId(incident);
    scroll.current?.scrollTo({ y: 0, animated: false });
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
    detail: ["incidents", "사건 목록"],
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
      setDialog({
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
                  {mock.profile.agency}에 전달된 사건입니다.
                </Text>
              )}
            </View>
          )}
          <View
            key={screen + "|" + id}
            style={{ paddingHorizontal: 20, paddingTop: 20 }}
          >
            {auth ? (
              <AuthScreens screen={screen} go={go} show={setDialog} />
            ) : screen === "home" || screen === "incidents" ? (
              <IncidentScreens home={screen === "home"} go={go} />
            ) : screen === "detail" || screen === "live" ? (
              <DetailScreen incident={d} live={screen === "live"} go={go} />
            ) : screen === "routes" ? (
              <RoutesScreen incident={d} show={setDialog} />
            ) : screen === "request" ? (
              <RequestScreen incident={d} go={go} show={setDialog} />
            ) : screen === "notifications" ? (
              <NotificationScreen go={go} show={setDialog} />
            ) : (
              <SettingsScreen go={go} show={setDialog} />
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
