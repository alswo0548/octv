import { StyleSheet, View, Image, AccessibilityInfo } from "react-native";
import { useEffect, useState } from "react";
import { VideoView, useVideoPlayer } from "expo-video";
export function Background() {
  const [reduce, set] = useState(false);
  const player = useVideoPlayer(
    require("../../assets/night-traffic.mp4"),
    (p) => {
      p.loop = true;
      p.muted = true;
    },
  );
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(set);
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", set);
    return () => sub.remove();
  }, []);
  useEffect(() => {
    if (reduce) player.pause();
    else player.play();
  }, [reduce, player]);
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <Image
        source={require("../../assets/road.jpg")}
        style={[StyleSheet.absoluteFill, { width: "100%", height: "100%" }]}
        blurRadius={2}
      />
      {!reduce && (
        <VideoView
          player={player}
          style={[StyleSheet.absoluteFill, { opacity: 0.65 }]}
          nativeControls={false}
          contentFit="cover"
        />
      )}
      <View
        style={[
          StyleSheet.absoluteFill,
          { backgroundColor: "rgba(4,10,17,.72)" },
        ]}
      />
    </View>
  );
}
