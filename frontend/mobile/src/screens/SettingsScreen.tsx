/**
 * 흐름: 현재 로그인 사용자 확인 → 서버 Push 설정 조회·변경 → 로그아웃 전 기기 연결 해제.
 * 주요 기능: DB 수신 설정 저장, 실패 시 스위치 원래 값 유지, 기기 재등록 요청.
 * 실제 JWT 삭제는 인증 담당이 전달하는 onLogout에 맡기며 이 파일에서는 로그인하지 않습니다.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { View, Text, Switch, Linking } from "react-native";
import { mock } from "@octv/shared";
import {
  Panel,
  Pair,
  T,
  Button,
  Link,
  type ShowDialog,
} from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate } from "../navigation/types";
import { notificationController } from "../notifications";

// 사용자 설정과 OS 권한은 별개이며, 로그아웃은 기기 해제 성공 뒤 인증 담당에게 넘깁니다.
export function SettingsScreen({
  go,
  show,
  onLogout,
}: {
  go: Navigate;
  show: ShowDialog;
  onLogout?: () => void | Promise<void>;
}) {
  const state = useSyncExternalStore(
    notificationController.subscribe,
    notificationController.getSnapshot,
    notificationController.getSnapshot,
  );
  const [saving, setSaving] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const ready = state.status === "ready" && !!state.user;
  const hasSession = ready || state.status === "logout-failed";
  useEffect(() => {
    if (ready) void notificationController.getSettings();
  }, [ready, state.user?.id]);

  // 서버 응답을 받은 뒤만 스위치를 바꿔 저장에 실패한 설정을 성공으로 표시하지 않습니다.
  async function saveEnabled(enabled: boolean) {
    if (!ready || saving) return;
    const current = notificationController.getSnapshot();
    if (current.user !== state.user || current.status !== "ready") return;
    setSaving(true);
    try {
      if (await notificationController.setEnabled(enabled)) {
        const saved = notificationController.getSnapshot();
        // 저장을 기다리는 사이 계정이 바뀌었다면 새 계정의 기기 등록을 시작하지 않습니다.
        if (enabled && saved.user === state.user && saved.status === "ready") {
          void notificationController.refreshDeviceRegistration();
        }
      }
    } finally {
      setSaving(false);
    }
  }

  // 인증 담당은 onLogout에 실제 JWT 삭제·로그아웃을 연결합니다. 해제 실패 시 먼저 재시도합니다.
  async function logout() {
    if (loggingOut) return;
    if (hasSession && !onLogout) return;
    const current = notificationController.getSnapshot();
    // 확인창을 연 뒤 계정이 바뀌었다면 이전 확인으로 새 계정을 로그아웃시키지 않습니다.
    if (current.user !== state.user || current.status !== state.status) return;
    setLoggingOut(true);
    try {
      if (!(await notificationController.prepareNotificationLogout())) return;
      const prepared = notificationController.getSnapshot();
      if (prepared.status !== "waiting" || prepared.user !== null) return;
      await onLogout?.();
      go("login");
    } catch {
      show({
        title: "로그아웃 확인",
        body: "로그아웃을 완료하지 못했습니다. 다시 시도해주세요.",
        cancel: false,
      });
    } finally {
      setLoggingOut(false);
    }
  }
  return (
    <>
      <Panel>
        <View style={[s.row, { justifyContent: "flex-start", gap: 15 }]}>
          <View
            style={{
              borderRadius: 30,
              width: 50,
              height: 50,
              backgroundColor: "#243748",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text style={s.title}>{state.user?.name.slice(0, 1) ?? "?"}</Text>
          </View>
          <View>
            <Text style={s.h2}>
              {state.user?.name ?? "로그인 정보 확인 필요"}
            </Text>
            <T muted>
              {state.user?.role ?? "로그인 후 계정 정보를 확인할 수 있습니다."}
            </T>
            <T muted>
              {state.user?.agency_name ?? (ready ? "소속기관 확인 필요" : "—")}
            </T>
          </View>
        </View>
      </Panel>
      <Panel title="계정 정보">
        <Pair label="이메일" value={state.user?.email ?? "—"} />
        <Pair label="역할" value={state.user?.role ?? "—"} />
        <Pair
          label="소속기관"
          value={
            state.user?.agency_name ?? (ready ? "소속기관 확인 필요" : "—")
          }
        />
      </Panel>
      <Panel title="알림">
        <View style={s.row}>
          <T>사건 전달 알림</T>
          <Switch
            accessibilityLabel="사건 전달 알림"
            value={state.enabled === true}
            disabled={!ready || saving || state.enabled === null}
            onValueChange={(enabled) => void saveEnabled(enabled)}
            trackColor={{ false: "#425769", true: "#398aaa" }}
            thumbColor="#dceaf3"
          />
        </View>
        {!ready && <T muted>로그인 후 알림 수신 설정을 변경할 수 있습니다.</T>}
        {ready && (
          <T muted>알림을 꺼도 전달받은 사건의 알림 목록은 유지됩니다.</T>
        )}
        {ready && state.deviceStatus === "permission-denied" && (
          <>
            <T muted>휴대폰의 알림 권한이 꺼져 있습니다.</T>
            <Link
              onPress={() => void Linking.openSettings().catch(() => undefined)}
            >
              휴대폰 설정 열기
            </Link>
          </>
        )}
        {ready &&
          (state.deviceStatus === "error" ||
            state.deviceStatus === "permission-denied") && (
            <Link
              onPress={() =>
                void notificationController.refreshDeviceRegistration()
              }
            >
              알림 권한·연결 다시 확인
            </Link>
          )}
        {state.error && <T muted>{state.error}</T>}
      </Panel>
      <Panel title="앱 정보">
        <Pair label="버전" value={mock.uiSnapshot.mobile.appVersion} />
      </Panel>
      <Button
        secondary
        disabled={loggingOut || (hasSession && !onLogout)}
        onPress={() =>
          show({
            title: "로그아웃하시겠어요?",
            body: "이 기기의 알림 연결을 해제하고 로그아웃합니다.",
            confirm: "로그아웃",
            onConfirm: () => void logout(),
          })
        }
      >
        {loggingOut ? "처리 중…" : "로그아웃"}
      </Button>
    </>
  );
}
