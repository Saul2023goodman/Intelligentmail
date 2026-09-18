import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { corePlugin } from "./core-plugin.ts";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Non-VITE variables are private server settings. Loading them explicitly
  // lets an intentional Vite mode configure the Python Core without exposing
  // capability gates to browser code.
  const environment = { ...process.env, ...loadEnv(mode, process.cwd(), "") };
  return {
    plugins: [react(), corePlugin(environment)],
    server: { host: "127.0.0.1" },
  };
});
