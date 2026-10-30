/**
 * 후속-05 카카오내비 실행: 공식 Kakao Android Navi SDK를 React Native 브리지로 호출.
 * 임의 URL 스킴이나 웹 길안내 URL은 사용하지 않습니다.
 * OCTV의 선택 경로 전체를 넘기는 것이 아니라 사건 목적지 WGS84 좌표만 전달합니다.
 * 카카오내비는 현재 위치 기준으로 자체 경로를 계산할 수 있습니다.
 */
import Constants from "expo-constants";
import { Platform } from "react-native";
import type { IncidentDto } from "@octv/shared";
import { validDestination } from "./liveRoutes";

export type KakaoNaviLaunch =
  | "opened"
  | "install"
  | "not-configured"
  | "unsupported";

// Initialize only once per running app process; on failure, the next attempt may retry.
let kakaoSdkInitialized = false;

export async function openKakaoNavi(
  incident: IncidentDto,
): Promise<KakaoNaviLaunch> {
  if (Platform.OS !== "android") return "unsupported";
  if (!validDestination(incident))
    throw new Error("사건 목적지의 위도·경도를 확인할 수 없습니다.");
  // config plugin과 빌드 설정이 반영된 Android APK에서만 실행합니다.
  const extra = Constants.expoConfig?.extra;
  const nativeAppKey = extra?.octvKakaoNativeAppKey;
  if (
    extra?.octvKakaoNaviConfigured !== true ||
    typeof nativeAppKey !== "string" ||
    !nativeAppKey.trim()
  )
    return "not-configured";
  // The Kakao Navi native client crashes if KakaoSdk is not initialized.
  // Initialize the native SDK before the first navigation API call.
  if (!kakaoSdkInitialized) {
    const { initializeKakaoSDK } = await import("@react-native-kakao/core");
    await initializeKakaoSDK(nativeAppKey);
    kakaoSdkInitialized = true;
  }
  // 기능 사용 시에만 내비 네이티브 패키지 로드. Expo Go에서는 호출하지 않습니다.
  const { navigateTo } = await import("@react-native-kakao/navi");
  const opened = await navigateTo({
    destination: {
      name: `OCTV 사건 ${incident.incident_no}`,
      x: incident.longitude,
      y: incident.latitude,
    },
    option: { coordType: "WGS84" },
    openWebInstallUrlIfNaviAppNotAvailable: true,
  });
  return opened ? "opened" : "install";
}
