import { useState } from "react";
import { View, Text, Switch } from "react-native";
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
export function SettingsScreen({
  go,
  show,
}: {
  go: Navigate;
  show: ShowDialog;
}) {
  const [enabled, set] = useState(true);
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
            <Text style={s.title}>P</Text>
          </View>
          <View>
            <Text style={s.h2}>{mock.profile.name}</Text>
            <T muted>{mock.profile.role}</T>
            <T muted>{mock.profile.agency}</T>
          </View>
        </View>
      </Panel>
      <Panel title="계정 정보">
        <Pair label="이메일" value={mock.profile.email} />
        <Pair label="역할" value={mock.profile.role} />
        <Pair label="소속기관" value={mock.profile.agency} />
      </Panel>
      <Panel title="알림">
        <View style={s.row}>
          <T>사건 전달 알림</T>
          <Switch
            accessibilityLabel="사건 전달 알림"
            value={enabled}
            onValueChange={set}
            trackColor={{ false: "#425769", true: "#398aaa" }}
            thumbColor="#dceaf3"
          />
        </View>
      </Panel>
      <Panel title="앱 정보">
        <Pair label="버전" value={mock.uiSnapshot.mobile.appVersion} />
        <Link
          onPress={() =>
            show({
              title: "개인정보 처리방침",
              body: "정책 문구 준비 위치입니다. 정식 정책은 팀에서 작성합니다.",
              cancel: false,
            })
          }
        >
          개인정보 처리방침 ›
        </Link>
      </Panel>
      <Button
        secondary
        onPress={() =>
          show({
            title: "로그아웃하시겠어요?",
            body: "로그인 UI로 이동합니다.",
            confirm: "로그아웃",
            onConfirm: () => go("login"),
          })
        }
      >
        로그아웃
      </Button>
      <Text
        style={[s.muted, { fontSize: 12, marginTop: 18, color: color.muted }]}
      >
        프로필은 고정 목업이며 토글 값은 현재 화면에만 표시됩니다.
      </Text>
    </>
  );
}
