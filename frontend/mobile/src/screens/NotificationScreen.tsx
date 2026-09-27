import { View, Text, Pressable } from "react-native";
import { mock, incidentById } from "@octv/shared";
import {
  Segments,
  Link,
  T,
  previewOnly,
  type ShowDialog,
} from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate } from "../navigation/types";
export function NotificationScreen({
  go,
  show,
}: {
  go: Navigate;
  show: ShowDialog;
}) {
  return (
    <>
      <Segments options={mock.uiSnapshot.mobile.notificationSegments} />
      <Link
        onPress={() =>
          show({ title: "모두 읽음", body: previewOnly, cancel: false })
        }
      >
        모두 읽음
      </Link>
      {mock.notificationIds.map((id, i) => {
        const d = incidentById(id);
        return (
          <View key={id}>
            {(i === 0 || i === 3) && (
              <Text style={[s.muted, { marginVertical: 16 }]}>
                {i === 0 ? "오늘" : "어제"}
              </Text>
            )}
            <Pressable
              accessibilityRole="button"
              onPress={() => go("detail", id)}
              style={s.panel}
            >
              <View style={s.row}>
                <Text style={{ color: color.cyan, fontSize: 13 }}>
                  사건 전달
                </Text>
                <T muted>{mock.notificationTimes[i]}</T>
              </View>
              <Text style={[s.h2, { marginTop: 14, marginBottom: 4 }]}>
                {d.type} · {id}
              </Text>
              <T muted>
                {d.location} · {d.camera}
              </T>
              <T muted>
                위험도 {d.riskLabel} · 대응 우선순위 {d.priority}
              </T>
            </Pressable>
          </View>
        );
      })}
    </>
  );
}
