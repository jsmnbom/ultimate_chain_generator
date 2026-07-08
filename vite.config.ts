import process from 'node:process'
import { NuxtIconBundle } from '@nuxt/icon/vite'
import ui from '@nuxt/ui/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Plain Vue 3 + Vite. Fully client-side (no SSR). Pyodide runs in a web worker.
export default defineConfig({
  base: process.env.BASE_URL ?? '/',

  plugins: [
    vue(),
    ui(),
    NuxtIconBundle({
      scan: {
        globInclude: [
          'src/**/*.{vue,jsx,tsx,ts,md,mdc,mdx}',
          'node_modules/@nuxt/ui/dist/**/*.{mjs,js}',
        ],
        globExclude: ['**/*.d.ts', '**/*.d.mts'],
      },
    }),
  ],
  worker: {
    format: 'es',
  },
  server: {
    // The uv-managed Python dev env lives in ./.venv; don't let its thousands of
    // files churn the dev-server file watcher.
    watch: { ignored: ['**/.venv/**'] },
  },
  // Pyodide + OCP.wasm fetch large assets from a CDN at runtime; nothing to
  // pre-bundle for them here.
})
