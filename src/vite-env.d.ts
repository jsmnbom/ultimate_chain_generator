/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * When set (`pnpm dev:mock`), swap the Pyodide worker for a no-Python mock
   *  so the UI can be prototyped without the multi-second CAD-kernel boot.
   */
  readonly VITE_MOCK_WORKER?: string
}

/** Git hash of the build, injected at build time (see vite.config.ts). */
declare const __GIT_HASH__: string

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}
