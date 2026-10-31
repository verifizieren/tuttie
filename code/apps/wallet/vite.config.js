// Vite config for the Tuttie wallet.
// The built app is served by the assistant service at /wallet/ (code/assistant/app.py),
// so every URL is based there. In development `npm run dev` serves it on port 4041 and
// forwards API calls and the shared files to the assistant on 4040.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const ASSISTANT = "http://localhost:4040";

export default defineConfig({
  base: "/wallet/",
  plugins: [react()],
  server: {
    port: 4041,
    host: true,
    proxy: {
      "/approvals": ASSISTANT,
      "/events": ASSISTANT,
      "/chat": ASSISTANT,
      "/identity": ASSISTANT,
      "/history": ASSISTANT,
      "/reset": ASSISTANT,
      "/voice": ASSISTANT,
      "/rtc": { target: ASSISTANT, ws: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
