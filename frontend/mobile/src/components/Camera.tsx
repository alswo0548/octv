import { useEffect, useRef } from "react";
import { View, Text, Image, Animated, Easing, StyleSheet } from "react-native";
import type { Incident } from "@octv/shared";
import { s, color } from "../styles/theme";
export function Camera({
  incident: d,
  live = false,
  connected = true,
}: {
  incident: Incident;
  live?: boolean;
  connected?: boolean;
}) {
  const motion = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!live || !connected) return;
    const a = Animated.loop(
      Animated.sequence([
        Animated.timing(motion, {
          toValue: 1,
          duration: 6500,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(motion, {
          toValue: 0,
          duration: 6500,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    a.start();
    return () => a.stop();
  }, [motion, live, connected]);
  return (
    <View
      style={{
        height: 266,
        borderRadius: 10,
        overflow: "hidden",
        backgroundColor: "#0c2030",
      }}
    >
      <Image
        source={require("../../assets/road.jpg")}
        style={[StyleSheet.absoluteFill, { width: "100%", height: "100%" }]}
      />
      <View
        style={[StyleSheet.absoluteFill, { backgroundColor: "#091c3240" }]}
      />
      <View
        style={{
          position: "absolute",
          top: 12,
          left: 12,
          right: 12,
          flexDirection: "row",
          justifyContent: "space-between",
        }}
      >
        <Text style={{ color: color.fg, fontSize: 10 }}>
          {live ? "LIVE" : "CAPTURE"} · {d.camera}
        </Text>
        <Text style={{ color: color.cyan, fontSize: 10 }}>AI ANALYSIS</Text>
      </View>
      {connected ? (
        <Animated.View
          style={{
            position: "absolute",
            left: "38%",
            top: "51%",
            width: "38%",
            height: "27%",
            borderColor: "#82f8fa",
            borderWidth: 1,
            backgroundColor: "#62e1ed0a",
            transform: [
              {
                translateX: motion.interpolate({
                  inputRange: [0, 1],
                  outputRange: [0, 5],
                }),
              },
            ],
          }}
        >
          <Text
            style={{
              position: "absolute",
              top: -24,
              left: -1,
              color: "#b6fcff",
              backgroundColor: "#143844",
              fontSize: 10,
              padding: 4,
            }}
          >
            {d.label} {d.confidence}%
          </Text>
        </Animated.View>
      ) : (
        <View
          style={[
            StyleSheet.absoluteFill,
            {
              backgroundColor: "#07111be8",
              alignItems: "center",
              justifyContent: "center",
            },
          ]}
        >
          <Text style={{ color: "#e0a6b1", fontSize: 20 }}>연결 끊김</Text>
          <Text style={s.muted}>연결 상태 예시</Text>
        </View>
      )}
      <View style={{ position: "absolute", bottom: 12, left: 12 }}>
        <Text style={[s.text, { fontSize: 11 }]}>{d.location}</Text>
        <Text style={[s.muted, { fontSize: 9 }]}>
          SIMULATED FEED · {d.time}:36
        </Text>
      </View>
    </View>
  );
}
