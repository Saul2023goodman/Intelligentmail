import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

// Vite is the only HTTP surface. Python communicates over private stdio.
export function corePlugin(): Plugin {
  return {
    name: "smartmail-core",
    configureServer(server) {
      const root = fileURLToPath(new URL("../", import.meta.url));
      const child = spawn(
        process.env.SMARTMAIL_PYTHON || "python",
        [
          "-u",
          "-m",
          "smartmail.ui",
          "--home",
          process.env.SMARTMAIL_HOME || ".smartmail",
        ],
        { cwd: root, windowsHide: true, stdio: ["pipe", "pipe", "inherit"] },
      );
      let sequence = 0;
      let stopped = false;
      const pending = new Map<number, (value: object) => void>();
      createInterface({ input: child.stdout }).on("line", (line) => {
        try {
          const value = JSON.parse(line);
          pending.get(value.id)?.(value);
          pending.delete(value.id);
        } catch {
          /* Ignore non-protocol output. */
        }
      });
      const stop = () => {
        stopped = true;
        for (const resolve of pending.values())
          resolve({ error: "Core is unavailable. Restart the dev server." });
        pending.clear();
      };
      child.on("error", stop);
      child.stdin.on("error", stop);
      child.on("exit", stop);
      server.httpServer?.once("close", () => child.kill());
      server.middlewares.use("/api/core", async (req, res) => {
        res.setHeader("Content-Type", "application/json");
        res.setHeader("Cache-Control", "no-store");
        const origin = req.headers.origin;
        if (
          req.method !== "POST" ||
          req.headers["content-type"] !== "application/json" ||
          (origin && origin !== `http://${req.headers.host}`)
        ) {
          res.statusCode = 403;
          res.end(
            JSON.stringify({ error: "Same-origin JSON requests required" }),
          );
          return;
        }
        try {
          let body = "";
          for await (const chunk of req) {
            body += chunk;
            if (body.length > 16000) throw new Error("Request too large");
          }
          const request = JSON.parse(body);
          if (stopped)
            throw new Error("Core is unavailable. Restart the dev server.");
          const id = ++sequence;
          const response = await new Promise<object>((resolve) => {
            const timer = setTimeout(() => {
              pending.delete(id);
              resolve({
                error:
                  "Core request timed out. Refresh to check the result before retrying.",
              });
            }, 30000);
            pending.set(id, (value) => {
              clearTimeout(timer);
              resolve(value);
            });
            child.stdin.write(JSON.stringify({ ...request, id }) + "\n");
          });
          res.end(JSON.stringify(response));
        } catch (error) {
          res.statusCode = 400;
          res.end(
            JSON.stringify({
              error: error instanceof Error ? error.message : "Invalid request",
            }),
          );
        }
      });
    },
  };
}
