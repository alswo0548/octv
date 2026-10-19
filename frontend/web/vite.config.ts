import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "./",
  // 같은 출처의 /api 요청을 로컬 FastAPI로 전달해 개발 중 CORS 변경을 피합니다.
  // VITE_API_BASE_URL을 비워 두면 웹은 이 프록시를 사용합니다.
  server: {
    host: "0.0.0.0", port: 4173, allowedHosts: ["terminal.local"],
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
