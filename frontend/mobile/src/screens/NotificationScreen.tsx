/**
 * 흐름: 인증 연결 확인 → 본인 최근 알림 조회 → 읽음 처리 → 권한 확인된 사건 열기.
 * 주요 기능: 최근 30개 목록, 현재 목록의 미읽음 필터, 표시된 알림 읽음, 오류·빈 상태.
 * 로그인과 JWT 저장은 인증 담당 코드가 수행하고 notifications.ts에 결과를 연결합니다.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { View, Text, Pressable, ActivityIndicator } from "react-native";
import { Link, T, Button, type ShowDialog } from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate } from "../navigation/types";
import {
  notificationController,
  parseNotificationTime,
} from "../notifications";

// DB의 UTC 시각을 한국 시간으로 표시하며, 잘못된 값은 임의 시각으로 꾸미지 않습니다.
function displayTime(value: string) {
  return (
    parseNotificationTime(value)?.toLocaleString("ko-KR", {
      timeZone: "Asia/Seoul",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }) ?? "시각 확인 불가"
  );
}

// 현재 사용자에게 허용된 알림만 표시하고 사건 이동은 공통 권한 확인 흐름에 맡깁니다.
export function NotificationScreen({
  go,
  show,
}: {
  go: Navigate;
  show: ShowDialog;
}) {
  const state = useSyncExternalStore(
    notificationController.subscribe,
    notificationController.getSnapshot,
    notificationController.getSnapshot,
  );
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [marking, setMarking] = useState(false);
  const ready = state.status === "ready" && !!state.user;
  const displayed = state.notifications.filter(
    (item) => !unreadOnly || item.read_at === null,
  );

  // 계정이 바뀌면 controller가 이전 목록을 비우고 새 사용자 목록을 조회합니다.
  useEffect(() => {
    setUnreadOnly(false);
    if (ready) void notificationController.listNotifications();
  }, [ready, state.user?.id]);

  // 전체 DB가 아니라 현재 화면의 미읽음 알림만 기존 개별 PATCH로 처리합니다.
  async function markDisplayedRead() {
    if (marking || !ready) return;
    setMarking(true);
    const user = state.user;
    try {
      for (const item of displayed.filter((row) => row.read_at === null)) {
        const current = notificationController.getSnapshot();
        // 작업 중 계정이 바뀌면 이전 알림에 대한 추가 요청을 멈춥니다.
        if (current.user !== user || current.status !== "ready") break;
        if (!(await notificationController.markRead(item.id))) break;
      }
    } finally {
      setMarking(false);
    }
  }

  if (!ready) {
    return (
      <View style={s.panel}>
        <T>로그인 후 본인 알림을 확인할 수 있습니다.</T>
        <Button onPress={() => go("login")}>로그인 화면으로</Button>
      </View>
    );
  }

  return (
    <>
      <T muted>최근 알림 30개 · 한국 시간</T>
      <View style={s.tabs}>
        {([false, true] as const).map((unread) => (
          <Pressable
            key={String(unread)}
            accessibilityRole="tab"
            accessibilityState={{ selected: unreadOnly === unread }}
            onPress={() => setUnreadOnly(unread)}
            style={[s.tab, unreadOnly === unread && s.tabActive]}
          >
            <T>{unread ? "현재 목록의 미읽음" : "전체"}</T>
          </Pressable>
        ))}
      </View>
      <View style={[s.row, { justifyContent: "space-between" }]}>
        <Link onPress={() => void notificationController.listNotifications()}>
          새로고침
        </Link>
        <Link
          onPress={() => {
            if (marking || !displayed.some((row) => row.read_at === null))
              return;
            show({
              title: "표시된 알림을 읽음 처리할까요?",
              body: "현재 표시된 미읽음 알림만 처리합니다.",
              confirm: "읽음 처리",
              onConfirm: () => void markDisplayedRead(),
            });
          }}
        >
          {marking ? "처리 중…" : "표시된 알림 읽음"}
        </Link>
      </View>
      {state.loading && <ActivityIndicator color={color.cyan} />}
      {state.error && (
        <View style={s.info} accessibilityRole="alert">
          <T>{state.error}</T>
        </View>
      )}
      {!state.loading && !displayed.length && (
        <View style={s.panel}>
          <T>
            {unreadOnly
              ? "현재 목록에 미읽음 알림이 없습니다."
              : "알림이 없습니다."}
          </T>
        </View>
      )}
      {displayed.map((item) => (
        <Pressable
          key={String(item.id)}
          accessibilityRole="button"
          accessibilityLabel={`사건 ${item.incident_id} 알림 ${item.read_at ? "읽음" : "미읽음"}`}
          disabled={marking}
          onPress={() => {
            const current = notificationController.getSnapshot();
            if (current.user === state.user && current.status === "ready") {
              void notificationController.openNotification(item.id);
            }
          }}
          style={s.panel}
        >
          <View style={[s.row, { justifyContent: "space-between" }]}>
            <Text style={{ color: color.cyan }}>사건 전달</Text>
            <T muted>{item.read_at ? "읽음" : "미읽음"}</T>
          </View>
          <Text style={[s.h2, { marginTop: 12 }]}>
            사건 ID {item.incident_id}
          </Text>
          <T muted>{displayTime(item.created_at)}</T>
          <T muted>눌러서 전달된 사건을 확인하세요.</T>
        </Pressable>
      ))}
    </>
  );
}
