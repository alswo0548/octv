import { useState } from "react";
import { View, Text, Pressable } from "react-native";
import { mock, type Incident } from "@octv/shared";
import {
  Badge,
  T,
  Field,
  Button,
  previewOnly,
  type ShowDialog,
} from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate } from "../navigation/types";
export function RequestScreen({
  incident: d,
  go,
  show,
}: {
  incident: Incident;
  go: Navigate;
  show: ShowDialog;
}) {
  const [type, set] = useState(mock.support.type);
  const cancel = () =>
    show({
      title: "작성 취소",
      body: "입력 중인 내용을 두고 사건 상세로 돌아갈까요?",
      confirm: "돌아가기",
      onConfirm: () => go("detail", d.id),
    });
  return (
    <>
      <Badge priority={d.priority} />
      <Text style={[s.title, { marginTop: 12 }]}>
        {d.type} · {d.id}
      </Text>
      <T muted>{d.location}</T>
      <View style={{ height: 24 }} />
      <T>요청 유형</T>
      <View
        style={{
          flexDirection: "row",
          flexWrap: "wrap",
          gap: 10,
          marginTop: 10,
          marginBottom: 24,
        }}
      >
        {mock.support.options.map((x) => (
          <Pressable
            accessibilityRole="radio"
            accessibilityState={{ checked: type === x }}
            key={x}
            onPress={() => set(x)}
            style={{
              width: "47%",
              borderWidth: 1,
              borderColor: type === x ? "#5dbad6" : color.line,
              padding: 12,
              borderRadius: 9,
              backgroundColor: type === x ? "#2e789536" : "transparent",
            }}
          >
            <T>
              {type === x ? "◉" : "○"} {x}
            </T>
          </Pressable>
        ))}
      </View>
      <Field
        label="요청 내용"
        defaultValue={mock.support.message}
        multiline
        textAlignVertical="top"
        style={[s.input, { height: 150 }]}
      />
      <View style={s.info}>
        <T>요청은 상황실에 전달되며 자동 출동 지령으로 처리되지 않습니다.</T>
      </View>
      <Button secondary onPress={cancel}>
        취소
      </Button>
      <Button
        onPress={() =>
          show({
            title: "추가 대응 요청 확인",
            body: previewOnly,
            confirm: "확인 (미리보기)",
          })
        }
      >
        요청 전달
      </Button>
    </>
  );
}
