import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const config = readFileSync(new URL("../frontend/mobile/app.config.ts", import.meta.url), "utf8");
const navi = readFileSync(new URL("../frontend/mobile/src/kakaoNavi.ts", import.meta.url), "utf8");

test("Android Kakao native app key is available to the JS SDK only when configured", () => {
  assert.match(config, /\.\.\.\(kakaoNativeAppKey \? \{ octvKakaoNativeAppKey: kakaoNativeAppKey \} : \{\}\)/);
  assert.match(config, /octvKakaoNaviConfigured: !!kakaoNativeAppKey/);
  assert.match(navi, /typeof nativeAppKey !== "string"/);
});

test("Kakao SDK is initialized with the native app key before launching navigation", () => {
  const init = navi.indexOf("await initializeKakaoSDK(nativeAppKey)");
  const navigate = navi.indexOf("await navigateTo({");
  assert.ok(init > 0 && navigate > init, "Kakao SDK must be initialized before navigateTo");
  assert.match(navi, /if \(!kakaoSdkInitialized\)/);
  assert.match(navi, /kakaoSdkInitialized = true/);
});
