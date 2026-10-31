// Vite config for the Tuttie owner view.
// The built app is served by the assistant service at /owner/ (code/assistant/app.py),
// so every URL is based there. In development `npm run dev` serves it on port 4042; it reads
// the business node directly (see src/lib/api.js), so no proxy is needed.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/owner/",
  plugins: [react()],
  server: { port: 4042, host: true },
  build: { outDir: "dist", emptyOutDir: true },
});
