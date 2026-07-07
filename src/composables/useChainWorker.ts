import type { Shapes } from 'three-cad-viewer'
import type {
  FieldError,
  JsonSchema,
  MeasureChanges,
  Preset,
  PrintabilityReport,
  WorkerRequest,
  WorkerResponse,
} from '../lib/protocol'
import { onScopeDispose, ref, shallowRef } from 'vue'
import { resolveSchema } from '../lib/resolveSchema'
import { useMockChainWorker } from './useMockChainWorker'

/**
 * Bridge for the viewer's measure tools: forward the viewer's selection/tool
 *  changes to the Python backend, and route its BREP-measurement responses back
 *  to a single handler (the Viewer, which feeds them to handleBackendResponse).
 */
export interface MeasureBridge {
  send: (changes: MeasureChanges) => void
  onResponse: (handler: ((response: Record<string, unknown>) => void) | null) => void
}

export type BootStatus = 'booting' | 'ready' | 'error'

const BUILD_DEBOUNCE_MS = 120

export function useChainWorker() {
  // UI-prototyping mode: skip the Pyodide/OCP boot entirely and serve a static
  // schema with an empty viewer. Enabled via VITE_MOCK_WORKER (`pnpm dev:mock`).
  // Returning here means the real Worker below is never constructed, so nothing
  // is fetched from the CDN. In a normal build the flag is statically `undefined`,
  // so this branch (and the mock) are dead-code-eliminated.
  if (import.meta.env.VITE_MOCK_WORKER) {
    return useMockChainWorker()
  }

  const status = ref<BootStatus>('booting')
  const bootStage = ref('Starting…')
  const bootProgress = ref(0)
  const bootError = ref<string | null>(null)

  const schema = ref<JsonSchema | null>(null)
  const presets = ref<Preset[]>([])
  const shapes = shallowRef<Shapes | null>(null)
  const building = ref(false)
  const fieldErrors = ref<FieldError[]>([])
  const report = ref<PrintabilityReport | null>(null)

  // One SharedWorker backs every tab of the origin, so a second tab connects to
  // the already-booted Python instead of re-paying the tens-of-seconds boot. We
  // talk to it over its MessagePort. SharedWorker (module type) is Baseline; a
  // browser too old to have it can't run the app, so surface a clear message
  // instead of a blank screen (no dedicated-worker fallback).
  function unsupported(message: string) {
    status.value = 'error'
    bootError.value = message
    return {
      status,
      bootStage,
      bootProgress,
      bootError,
      schema,
      presets,
      shapes,
      building,
      fieldErrors,
      report,
      build: () => {},
      exportModel: () => Promise.reject(new Error('SharedWorker unsupported')),
      measure: { send() {}, onResponse() {} } as MeasureBridge,
    }
  }

  if (typeof SharedWorker === 'undefined') {
    return unsupported('This app needs a current browser (SharedWorker support). Please update.')
  }
  let port: MessagePort
  try {
    const sw = new SharedWorker(new URL('../worker/pyodide.worker.ts', import.meta.url), {
      type: 'module',
    })
    port = sw.port
    port.start()
  }
  catch {
    // Has SharedWorker but rejects module workers — same "please update" path.
    return unsupported('This app needs a current browser (module SharedWorker support). Please update.')
  }

  let nextId = 1
  let latestBuildId = 0
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  // Last params we built, so a dev model hot-reload can re-render immediately.
  let lastParams: Record<string, unknown> | null = null
  const pendingExports = new Map<
    number,
    { resolve: (b: Uint8Array) => void, reject: (e: Error) => void, format: string }
  >()
  let measureResponseHandler: ((response: Record<string, unknown>) => void) | null = null

  function send(msg: WorkerRequest, transfer?: Transferable[]) {
    port.postMessage(msg, transfer ?? [])
  }

  port.onmessage = (e: MessageEvent<WorkerResponse>) => {
    const msg = e.data
    switch (msg.type) {
      case 'boot':
        bootStage.value = msg.stage
        bootProgress.value = msg.progress
        break
      case 'boot-error':
        status.value = 'error'
        bootError.value = msg.message
        break
      case 'ready':
        // Dereference pydantic's `$ref`/`$defs` (the enum choice fields) into the
        // flat schema the form renderer reads. See resolveSchema.
        schema.value = resolveSchema(msg.schema)
        presets.value = msg.presets ?? []
        status.value = 'ready'
        break
      case 'shapes':
        // ocp-tessellate already emits the nested-array Shapes tree that
        // three-cad-viewer.render() consumes directly — just parse it.
        try {
          shapes.value = JSON.parse(msg.data) as Shapes
        }
        catch (err) {
          console.error('Failed to parse shapes', err)
        }
        break
      case 'build-result':
        if (msg.id === latestBuildId) {
          fieldErrors.value = msg.ok ? [] : (msg.errors ?? [])
          report.value = msg.report ?? null
          building.value = false
        }
        break
      case 'export-result': {
        const p = pendingExports.get(msg.id)
        if (p) {
          pendingExports.delete(msg.id)
          if (msg.bytes)
            p.resolve(msg.bytes)
          else p.reject(new Error(msg.error ?? 'Export failed'))
        }
        break
      }
      case 'measure-response':
        measureResponseHandler?.(msg.response)
        break
      case 'log':
        // Surface Python stdout/stderr for debugging.
        // eslint-disable-next-line no-console
        (msg.stream === 'stderr' ? console.warn : console.debug)('[py]', msg.text)
        break
      case 'model-reloaded':
        // Dev-only: chain.py was re-exec'd in place (no Pyodide reboot). Swap in
        // the fresh schema/presets and rebuild with the current params.
        schema.value = resolveSchema(msg.schema)
        presets.value = msg.presets ?? []
        if (lastParams)
          build(lastParams)
        break
      case 'reload':
        // Dev-only: the SharedWorker is closing itself because its code changed
        // (HMR). Reload onto fresh code; the reload spawns a new worker.
        location.reload()
        break
    }
  }

  const measure: MeasureBridge = {
    send(changes) {
      if (status.value !== 'ready')
        return
      send({ type: 'measure', changes })
    },
    onResponse(handler) {
      measureResponseHandler = handler
    },
  }

  /** Debounced, latest-wins build request. */
  function build(params: Record<string, unknown>) {
    if (status.value !== 'ready')
      return
    if (debounceTimer)
      clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      latestBuildId = nextId++
      building.value = true
      // Snapshot to a plain object: a Vue reactive proxy isn't structured-cloneable.
      const snapshot = { ...params }
      lastParams = snapshot
      send({ type: 'build', id: latestBuildId, params: snapshot })
    }, BUILD_DEBOUNCE_MS)
  }

  function exportModel(format: string, params: Record<string, unknown>): Promise<Uint8Array> {
    return new Promise((resolve, reject) => {
      const id = nextId++
      pendingExports.set(id, { resolve, reject, format })
      send({ type: 'export', id, format, params: { ...params } })
    })
  }

  // Tell the shared worker to drop this tab's per-port state and close our port.
  // The worker keeps running for other tabs (the browser tears it down once the
  // last port closes). `pagehide` covers tab close / navigation, which does not
  // trigger onScopeDispose.
  function disconnect() {
    port.postMessage({ type: 'disconnect' })
    port.close()
  }
  window.addEventListener('pagehide', disconnect)

  onScopeDispose(() => {
    if (debounceTimer)
      clearTimeout(debounceTimer)
    window.removeEventListener('pagehide', disconnect)
    disconnect()
  })

  return {
    status,
    bootStage,
    bootProgress,
    bootError,
    schema,
    presets,
    shapes,
    building,
    fieldErrors,
    report,
    build,
    exportModel,
    measure,
  }
}
