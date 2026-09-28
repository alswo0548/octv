import { View, Text } from "react-native";
import Svg, { Rect, Path, Circle, Text as SvgText, G } from "react-native-svg";
import { mock } from "@octv/shared";
import { s } from "../styles/theme";
export function RoadMap({
  active,
  choose,
}: {
  active: string;
  choose: (id: string) => void;
}) {
  return (
    <View
      style={{
        borderRadius: 10,
        overflow: "hidden",
        borderWidth: 1,
        borderColor: "#2b4152",
      }}
    >
      <Svg width="100%" height={240} viewBox="0 0 820 430">
        <Rect width="820" height="430" fill="#0b1925" />
        <Path
          d="M260 -30L370 150 230 320 210 480"
          stroke="#1b4355"
          strokeWidth="42"
          fill="none"
        />
        <Path
          d="M-20 140L425 255 850 395M30 385L800 65M145 440L280 90 700 105M145 340L620 340 780 -20M-10 245L440 280 740 130"
          stroke="#293f50"
          strokeWidth="9"
          fill="none"
        />
        {mock.mapPaths[0].map((p, i) => (
          <G key={p} onPress={() => choose("ABC"[i])}>
            <Path d={p} fill="none" stroke="transparent" strokeWidth={24} />
            <Path
              d={p}
              fill="none"
              stroke={
                i === 1
                  ? "#eb8e91"
                  : active === "ABC"[i]
                    ? "#ffcd78"
                    : "#62bbef"
              }
              strokeWidth={active === "ABC"[i] ? 7 : 4}
              strokeDasharray={i === 1 ? "8 7" : undefined}
            />
          </G>
        ))}
        <Circle cx="145" cy="340" r="8" fill="#73dceb" />
        <SvgText x="90" y="382" fill="#9ce7f0" fontSize="21">
          강남소방서
        </SvgText>
        <Circle cx="690" cy="105" r="9" fill="#ff8d9f" />
        <SvgText x="625" y="75" fill="#ffa4b2" fontSize="21">
          사건 현장
        </SvgText>
        <SvgText x="445" y="242" fill="#ffcd78" fontSize="24">
          A
        </SvgText>
        <SvgText x="550" y="365" fill="#eb8e91" fontSize="24">
          B
        </SvgText>
        <SvgText x="370" y="78" fill="#62bbef" fontSize="24">
          C
        </SvgText>
      </Svg>
      <Text
        style={[
          s.muted,
          { fontSize: 10, padding: 10, backgroundColor: "#0b1925" },
        ]}
      >
        사건 위치 · 접근 경로
      </Text>
    </View>
  );
}
