/** Only conceal these two identified test cameras in the web UI; never delete DB rows. */
const WEB_HIDDEN_TEST_CCTV_IDS = new Set(["OCTV_FOLLOWUP06_TEST", "STEP01-CCTV-001"]);
export const isTestCamera = (camera: { external_cctv_id: string }) =>
  WEB_HIDDEN_TEST_CCTV_IDS.has(camera.external_cctv_id.trim().toUpperCase());
