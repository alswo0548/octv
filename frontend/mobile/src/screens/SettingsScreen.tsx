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
    </>
  );
}
