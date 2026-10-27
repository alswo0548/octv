/**
 * 전체 흐름: 기존 app.json 읽기 → Android/Firebase 공개 설정 추가 → 네이티브 빌드 전 확인.
 * 주요 기능: 기존 화면 설정 보존, 알림 채널 plugin, Android APK용 Firebase 파일 검증.
 * 서버 서비스 계정·비밀키·FCM 토큰을 앱 설정이나 extra에 넣지 않습니다.
 */
/// <reference types="node" />
import { existsSync, readFileSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import type { ConfigContext, ExpoConfig } from "expo/config";
import { withAndroidManifest, withDangerousMod } from "expo/config-plugins";

const CHANNEL_ID = "octv_incident_delivery";

// Android 빌드에서만 Firebase 클라이언트 설정과 application ID의 일치를 확인합니다.
function validateAndroidFirebase(config: ExpoConfig): ExpoConfig {
  return withDangerousMod(config, [
    "android",
    async (mod) => {
      const configured = mod.android?.googleServicesFile;
      const path =
        configured &&
        (isAbsolute(configured)
          ? configured
          : resolve(mod.modRequest.projectRoot, configured));
      if (!path || !existsSync(path)) {
        throw new Error(
          "OCTV Android 빌드에는 Firebase의 google-services.json이 필요합니다. OCTV_ANDROID_GOOGLE_SERVICES_FILE 또는 EAS 파일 변수 GOOGLE_SERVICES_JSON을 설정해주세요.",
        );
      }
      let firebase: Record<string, unknown>;
      try {
        firebase = JSON.parse(readFileSync(path, "utf8")) as Record<
          string,
          unknown
        >;
      } catch {
        throw new Error(
          "Firebase Android 클라이언트 설정 파일을 읽지 못했습니다. 올바른 google-services.json인지 확인해주세요.",
        );
      }
      // 서버용 서비스 계정을 잘못 지정해 APK에 자격증명이 들어가는 것을 방지합니다.
      if (
        !firebase ||
        typeof firebase !== "object" ||
        firebase.type === "service_account" ||
        "private_key" in firebase
      ) {
        throw new Error(
          "Android 앱에는 서버 서비스 계정을 사용할 수 없습니다. Firebase Android 앱의 google-services.json을 선택해주세요.",
        );
      }
      const clients = Array.isArray(firebase.client) ? firebase.client : [];
      const matched = clients.some(
        (client) =>
          client?.client_info?.android_client_info?.package_name ===
          mod.android?.package,
      );
      if (!matched) {
        throw new Error(
          "Firebase Android 앱의 패키지 이름과 OCTV_ANDROID_PACKAGE가 일치하지 않습니다. 두 설정을 확인해주세요.",
        );
      }
      return mod;
    },
  ]);
}

// 기존 설정을 확장하며 기본 com.octv.mobile은 실제 Firebase 등록 이름에 맞춰 바꿉니다.
export default function configureApp({ config }: ConfigContext): ExpoConfig {
  const packageName =
    process.env.OCTV_ANDROID_PACKAGE?.trim() || "com.octv.mobile";
  if (!/^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$/.test(packageName)) {
    throw new Error(
      "OCTV_ANDROID_PACKAGE에는 점으로 구분된 올바른 Android 패키지 이름을 입력해주세요.",
    );
  }
  const googleServicesFile =
    process.env.GOOGLE_SERVICES_JSON?.trim() ||
    process.env.OCTV_ANDROID_GOOGLE_SERVICES_FILE?.trim() ||
    "./google-services.json";
  const easProjectId = process.env.OCTV_EAS_PROJECT_ID?.trim();
  // 공개 Native App Key: Kakao Developers 등록 앱과 Android package가 일치해야 합니다.
  // Expo 네이티브 빌드에서 설정하지 않으면 기존의 안전한 '설정 대기' 안내를 유지합니다.
  const kakaoNativeAppKey = process.env.OCTV_KAKAO_NATIVE_APP_KEY?.trim();
  const plugins = (config.plugins ?? []).filter((plugin) => {
    const name = typeof plugin === "string" ? plugin : plugin[0];
    return name !== "expo-notifications" && name !== "expo-secure-store" && name !== "@react-native-kakao/core";
  });
  let next: ExpoConfig = {
    ...config,
    name: config.name || "OCTV",
    slug: config.slug || "octv-ui",
    android: { ...config.android, package: packageName, googleServicesFile },
    plugins: [
      ...plugins,
      [
        "expo-build-properties",
        {
          android: {
            extraMavenRepos: [
              "https://devrepo.kakao.com/nexus/content/groups/public/",
            ],
          },
        },
      ],
      ["expo-notifications", { defaultChannel: CHANNEL_ID, color: "#82f8fa" }],
      "expo-secure-store",
      ...(kakaoNativeAppKey ? [["@react-native-kakao/core", { nativeAppKey: kakaoNativeAppKey }] as [string, { nativeAppKey: string }]] : []),
    ],
    extra: {
      ...config.extra,
      octvKakaoNaviConfigured: !!kakaoNativeAppKey,
      ...(easProjectId
        ? { eas: { ...config.extra?.eas, projectId: easProjectId } }
        : {}),
    },
  };
  // 휴대폰에서 로컬 PC의 HTTP 서버를 테스트할 때만 명시적으로 허용합니다. 기본은 꺼짐입니다.
  next = withAndroidManifest(next, (mod) => {
    const application = mod.modResults.manifest.application?.[0];
    if (application) {
      application.$["android:usesCleartextTraffic"] =
        process.env.OCTV_ANDROID_ALLOW_HTTP === "1" ? "true" : "false";
    }
    return mod;
  });
  // 웹 미리보기·타입 검사는 Firebase 파일 없이 가능하며 Android prebuild는 파일을 요구합니다.
  return validateAndroidFirebase(next);
}
