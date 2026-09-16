import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { corePlugin } from "./core-plugin.ts";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), corePlugin()],
  server: { host: "127.0.0.1" },
});
