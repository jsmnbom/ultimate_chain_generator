import type { Plugin } from 'vite'
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, resolve as resolvePath } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { NuxtIconBundle } from '@nuxt/icon/vite'
import ui from '@nuxt/ui/vite'
import vue from '@vitejs/plugin-vue'
import webpackStatsPlugin from 'rollup-plugin-webpack-stats'
import { defineConfig } from 'vite'
import vueDevTools from 'vite-plugin-vue-devtools'

// three-cad-viewer 5 is not published to npm; it's vendored as a git submodule
// (vendor/three-cad-viewer) and compiled from TypeScript source as part of our
// own Vite build. This `pre` plugin applies the two source-level rewrites that
// build needs:
//
//  1. display.ts does `import template from "./index.html"` expecting the file's
//     raw contents (the upstream Rollup build uses rollup-plugin-string). We
//     reroute that one import to a `\0` virtual module loaded as a default-
//     exported string. A virtual id (not the real .html path, nor Vite's `?raw`
//     query) keeps it away from Vite's HTML asset handling *and* works during the
//     dep-scan — both of which choke on a raw .html import.
//
//  2. StudioComposer is the sole importer of `postprocessing` (~2.7 MB) and
//     `n8ao` (~0.7 MB), for Studio mode's post-processing pipeline. We hide Studio
//     (studioTool: false) and don't ship it, so redirect that module to an inert
//     stub — dropping both heavy deps from the bundle. See stubs/.
const TCV_SRC = fileURLToPath(new URL('./vendor/three-cad-viewer/src', import.meta.url))
const TCV_HTML_PREFIX = '\0tcv-html:'
const STUDIO_COMPOSER_STUB = fileURLToPath(new URL('./stubs/tcv-studio-composer.ts', import.meta.url))

function tcvSource(): Plugin {
  return {
    name: 'tcv-source-rewrites',
    enforce: 'pre',
    resolveId(source, importer) {
      if (!importer?.split('?')[0].startsWith(TCV_SRC))
        return null
      if (source.endsWith('.html')) {
        const abs = resolvePath(dirname(importer.split('?')[0]), source)
        // Drop the `.html` suffix from the virtual id so Vite's HTML plugin
        // (which matches on the `.html` extension) leaves it alone; re-append it
        // when reading the file in `load`.
        return TCV_HTML_PREFIX + abs.slice(0, -'.html'.length)
      }
      if (source.endsWith('/studio-composer.js'))
        return STUDIO_COMPOSER_STUB
      return null
    },
    load(id) {
      if (id.startsWith(TCV_HTML_PREFIX)) {
        const abs = `${id.slice(TCV_HTML_PREFIX.length)}.html`
        return `export default ${JSON.stringify(readFileSync(abs, 'utf-8'))}`
      }
      return null
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

  optimizeDeps: {
    // The vendored three-cad-viewer submodule lives under the project root and
    // ships dozens of .html files (docs, examples). Without pinning the scan
    // entry, Vite's dep scanner treats every one of them as an app entry point.
    // Our app has a single real entry.
    entries: ['index.html'],
  },

  resolve: {
    alias: [
      // Map the vendored CSS subpath so a consumer can import it explicitly.
      // index.ts imports these four sheets as side-effects, but Rolldown's prod
      // build tree-shakes side-effect CSS imports out of the module when only its
      // named exports (Display/Viewer) are consumed — dev serves them, the build
      // drops them. Viewer.vue re-imports them through this alias so they survive.
      { find: /^three-cad-viewer\/css\//, replacement: `${TCV_SRC}/../css/` },
      // Resolve the bare 'three-cad-viewer' import to the vendored source entry
      // (mirrored by tsconfig's `paths`).
      { find: /^three-cad-viewer$/, replacement: `${TCV_SRC}/index.ts` },
    ],
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
    tcvSource(),
    vueDevTools(),
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
