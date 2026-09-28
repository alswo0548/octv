import { StyleSheet, View, Image, AccessibilityInfo } from "react-native";
import { useEffect, useState } from "react";
import { VideoView, useVideoPlayer } from "expo-video";

/** Full viewport background, outside the 460px mobile content column. */
export function Background() {
  const [reduce, setReduce] = useState(false);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const player = useVideoPlayer(
    require("../../assets/night-traffic.mp4"),
    (p) => {
      p.loop = true;
      p.muted = true;
    },
  );
  useEffect(() => {
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled().then((value) => {
      if (active) setReduce(value);
    });
    const sub = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setReduce,
    );
    return () => {
      active = false;
      sub.remove();
    };
  }, []);
  useEffect(() => {
    const status = player.addListener("statusChange", ({ status }) =>
      setReady(status === "readyToPlay"),
    );
    const playback = player.addListener("playingChange", ({ isPlaying }) =>
      setPlaying(isPlaying),
    );
    setReady(player.status === "readyToPlay");
    setPlaying(player.playing);
    return () => {
      status.remove();
      playback.remove();
    };
  }, [player]);
  useEffect(() => {
    if (reduce) player.pause();
    else player.play();
  }, [reduce, player]);
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <Image
        source={require("../../assets/road.jpg")}
        resizeMode="cover"
        style={[
          StyleSheet.absoluteFill,
          { width: "100%", height: "100%", opacity: 0.48 },
        ]}
        blurRadius={18}
      />
      {!reduce && (
        <VideoView
          player={player}
          style={[
            StyleSheet.absoluteFill,
            {
              width: "100%",
              height: "100%",
              opacity: ready && playing ? 0.82 : 0,
            },
          ]}
          nativeControls={false}
          contentFit="contain"
          playsInline
        />
      )}
      <View
        style={[
          StyleSheet.absoluteFill,
          { backgroundColor: "rgba(4,10,17,.46)" },
        ]}
      />
    </View>
  );
}
