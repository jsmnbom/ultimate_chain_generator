import type { Plugin } from 'vite'
import { execSync } from 'node:child_process'
import { copyFileSync, existsSync } from 'node:fs'
import { resolve as resolvePath } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { NuxtIconBundle } from '@nuxt/icon/vite'
import ui from '@nuxt/ui/vite'
import vue from '@vitejs/plugin-vue'
import webpackStatsPlugin from 'rollup-plugin-webpack-stats'
import { defineConfig } from 'vite'
import vueDevTools from 'vite-plugin-vue-devtools'

// GitHub Pages has no server-side rewrite, so a deep-link refresh (e.g.
// /reponame/m/chain) would 404. The convention is to serve a copy of index.html
// as 404.html: Pages returns it for any unmatched path, the SPA boots, and
// vue-router resolves the real route client-side. Vite injects base-prefixed
// absolute asset URLs into index.html, so the copy loads assets correctly under
// the project's base. Runs after the bundle is written.
function spaFallback(): Plugin {
  return {
    name: 'spa-404-fallback',
    apply: 'build',
    closeBundle() {
      const dist = fileURLToPath(new URL('./dist', import.meta.url))
      const index = resolvePath(dist, 'index.html')
      if (existsSync(index))
        copyFileSync(index, resolvePath(dist, '404.html'))
    },
  }
}

// Short git hash of the build, surfaced in the UI (links back to the commit on
// GitHub). CI passes it via GIT_HASH (from the workflow); locally we fall back to
// asking git, then to 'dev' outside a git checkout.
function gitHash(): string {
  if (process.env.GIT_HASH)
    return process.env.GIT_HASH
  try {
    return execSync('git rev-parse HEAD').toString().trim()
  }
  catch {
    return 'dev'
  }
}

// Plain Vue 3 + Vite. Fully client-side (no SSR). Pyodide runs in a web worker.
export default defineConfig({
  base: process.env.BASE_URL ?? '/',

  define: {
    __GIT_HASH__: JSON.stringify(gitHash()),
  },

  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        // Use a supported file pattern for Vite 5/Rollup 4
        // @doc https://relative-ci.com/documentation/guides/vite-config
        assetFileNames: 'assets/[name].[hash][extname]',
        chunkFileNames: 'assets/[name].[hash].js',
        entryFileNames: 'assets/[name].[hash].js',
      },
    },
  },

  plugins: [
    spaFallback(),
    vueDevTools(),
    vue(),
    ui({
      ui: {
        colors: {
          primary: 'pink',
          neutral: 'zinc',
        },
      },
    }),
    NuxtIconBundle({
      scan: {
        globInclude: [
          'src/**/*.{vue,jsx,tsx,ts,md,mdc,mdx}',
          'node_modules/@nuxt/ui/dist/**/*.{mjs,js}',
        ],
        globExclude: ['**/*.d.ts', '**/*.d.mts'],
      },
    }),
    webpackStatsPlugin(),
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
