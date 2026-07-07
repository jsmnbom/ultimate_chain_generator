import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import ui from "@nuxt/ui/vite";

// Plain Vue 3 + Vite. Fully client-side (no SSR). Pyodide runs in a web worker.
export default defineConfig({
  plugins: [vue(), ui()],
  worker: {
    format: "es",
  },
  server: {
    // The uv-managed Python dev env lives in ./.venv; don't let its thousands of
    // files churn the dev-server file watcher.
    watch: { ignored: ["**/.venv/**"] },
  },
  // Pyodide + OCP.wasm fetch large assets from a CDN at runtime; nothing to
  // pre-bundle for them here.
});
