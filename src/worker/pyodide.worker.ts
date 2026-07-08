/// <reference lib="webworker" />
//
// Pyodide worker: loads the CAD stack once, then serves build / export requests.
// Keeping OCP (hundreds of ms per build) off the main thread keeps the form and
// viewer responsive. Geometry is tessellated by ocp-tessellate inside Python and
// posted to the main thread as a "shapes" message (a plain-JSON Shapes tree).
//
// Runs as a **SharedWorker**: one Python interpreter serves every tab of the
// origin, so a second tab connects to the already-booted backend instead of
// re-paying the tens-of-seconds boot. Each tab is a MessagePort (`connect`
// below); requests/responses route per port — port identity is implicit in the
// per-connection `port.onmessage` closure, so no sender ids are needed.

import type {
  BuildResult,
  JsonSchema,
  Preset,
  WorkerRequest,
  WorkerResponse,
} from '../lib/protocol'
import chainSrc from '../python/chain.py?raw'
import installSrc from '../python/install.py?raw'
import measureSrc from '../python/measure.py?raw'
import protoSrc from '../python/proto.py?raw'
import runtimeSrc from '../python/runtime.py?raw'

const PYODIDE_VERSION = 'v314.0.2'
const PYODIDE_INDEX_URL = `https://cdn.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/`

let pyodide: any = null
let busy = false
// Per-tab build coalescing: each port keeps only its latest pending build.
const pendingBuilds = new Map<MessagePort, { id: number, params: unknown }>()
const exportQueue: { port: MessagePort, id: number, format: string, params: unknown }[] = []
// Measure requests are small and interactive (they fire while the user hovers /
// clicks in the viewer), so they jump the queue ahead of builds and exports.
const measureQueue: { port: MessagePort, changes: unknown }[] = []
// The port whose build is running right now, so host_bridge's shapes message
// (emitted during the build) reaches the correct tab. Set around doBuild only.
let currentBuildPort: MessagePort | null = null
// Dev-only: pending model hot-reload source (set by the HMR handler). Processed
// with top priority so the new model is live before the next build runs.
let pendingReload: string | null = null

// Every connected tab. `post` targets one port; `broadcast` fans out to all
// (used for boot progress, which is shared across tabs).
const ports = new Set<MessagePort>()

// Cached so a tab that connects *after* boot can be caught up immediately
// instead of watching a boot it missed. Updated as boot progresses.
type BootState
  = | { kind: 'booting', stage: string, progress: number }
    | { kind: 'ready', msg: WorkerResponse }
    | { kind: 'error', message: string }
let bootState: BootState = { kind: 'booting', stage: 'Starting…', progress: 0 }

function post(port: MessagePort, msg: WorkerResponse, transfer?: Transferable[]) {
  port.postMessage(msg, transfer ?? [])
}

function broadcast(msg: WorkerResponse) {
  for (const p of ports) p.postMessage(msg, [])
}

function boot(stage: string, progress: number) {
  bootState = { kind: 'booting', stage, progress }
  broadcast({ type: 'boot', stage, progress })
}

async function initialize(): Promise<void> {
  boot('Loading Python runtime…', 0.05)
  const mod = await import(/* @vite-ignore */ `${PYODIDE_INDEX_URL}pyodide.mjs`)
  pyodide = await mod.loadPyodide({ indexURL: PYODIDE_INDEX_URL })

  pyodide.setStdout({ batched: (text: string) => broadcast({ type: 'log', stream: 'stdout', text }) })
  pyodide.setStderr({ batched: (text: string) => broadcast({ type: 'log', stream: 'stderr', text }) })

  boot('Loading package manager…', 0.15)
  // micropip drives the install; the rest are the built-in deps our pinned wheels need
  // (install.py installs those wheels with deps=False, so their built-in dependencies
  // must be loaded here). loadPackage resolves each one's transitive built-in deps from
  // Pyodide's own lock — no PyPI round-trips. Keep in sync with install.py's
  // REQUIREMENTS / _WHEEL_URLS (see gen-pyodide-wheels.mjs).
  await pyodide.loadPackage([
    'micropip',
    'numpy',
    'requests',
    'svgwrite',
    'typing-extensions',
    'pydantic',
  ])

  // Bridge: Python (runtime.py's show()) calls builtins.send_data_to_js(payload,
  // "DATA") to hand the tessellated Shapes JSON straight to the main thread.
  // Shapes are produced *during* a build (build_and_show calls show()), so they
  // belong to whichever tab's build is currently running. The scheduler runs one
  // Python call at a time, so `currentBuildPort` is unambiguous while set.
  pyodide.registerJsModule('host_bridge', {
    send_data_to_js(data: string, msgType: string): void {
      if (msgType === 'DATA' && currentBuildPort)
        post(currentBuildPort, { type: 'shapes', data })
    },
  })
  await pyodide.runPythonAsync(
    'import builtins, host_bridge\nbuiltins.send_data_to_js = host_bridge.send_data_to_js\n',
  )

  boot('Installing CAD kernel (OCP.wasm)…', 0.25)
  await pyodide.runPythonAsync(installSrc)

  boot('Loading build123d…', 0.75)
  // chain.py pulls its shared form/preview helpers in with `from proto import …`.
  // Unlike the other assets (exec'd straight into the global namespace), proto
  // must therefore exist as a real importable module. Write it to Pyodide's home
  // dir, which is on sys.path — mirroring how proto.py sits next to chain.py on
  // sys.path natively. It imports build123d/pydantic, so this must follow install.
  pyodide.FS.writeFile('/home/pyodide/proto.py', new TextEncoder().encode(protoSrc))
  await pyodide.runPythonAsync(chainSrc)

  boot('Preparing viewer bridge…', 0.9)
  // measure.py before runtime.py: it provides get_distance / get_properties as
  // globals that runtime.py's measure backend calls (same pattern as chain.py).
  await pyodide.runPythonAsync(measureSrc)
  await pyodide.runPythonAsync(runtimeSrc)

  boot('Ready', 1.0)
  const schemaJson: string = await pyodide.runPythonAsync('get_schema_json()')
  const presetsJson: string = await pyodide.runPythonAsync('get_presets_json()')
  const readyMsg: WorkerResponse = {
    type: 'ready',
    schema: JSON.parse(schemaJson),
    presets: JSON.parse(presetsJson),
  }
  bootState = { kind: 'ready', msg: readyMsg }
  broadcast(readyMsg)
}

async function doBuild(params: unknown): Promise<BuildResult> {
  pyodide.globals.set('_params_json', JSON.stringify(params))
  const resultStr: string = await pyodide.runPythonAsync('build_and_show(_params_json)')
  return JSON.parse(resultStr) as BuildResult
}

async function doMeasure(changes: unknown): Promise<Record<string, unknown> | null> {
  pyodide.globals.set('_measure_json', JSON.stringify(changes))
  const resultStr: string = await pyodide.runPythonAsync('handle_measure(_measure_json)')
  // Empty string means "nothing to answer yet" (wrong tool / too few shapes).
  return resultStr ? (JSON.parse(resultStr) as Record<string, unknown>) : null
}

// Dev-only: re-exec the model source (chain.py) into the running interpreter and
// hand back the fresh schema/presets — no Pyodide reboot. Runs through the
// scheduler (below) so it can't interleave with an in-flight build.
async function doReloadModel(source: string): Promise<{ schema: unknown, presets: unknown }> {
  pyodide.globals.set('_model_src', source)
  const resultStr: string = await pyodide.runPythonAsync('reload_model(_model_src)')
  return JSON.parse(resultStr) as { schema: unknown, presets: unknown }
}

async function doExport(params: unknown, format: string): Promise<Uint8Array> {
  pyodide.globals.set('_params_json', JSON.stringify(params))
  pyodide.globals.set('_fmt', format)
  const res = await pyodide.runPythonAsync('export_bytes(_params_json, _fmt)')
  // Python `bytes` may arrive as a PyProxy or an already-converted Uint8Array.
  if (res && typeof res.toJs === 'function') {
    const bytes: Uint8Array = res.toJs()
    res.destroy()
    return bytes
  }
  return res as Uint8Array
}

// --- Scheduler: one Python call at a time. Builds coalesce to latest-wins;
//     exports are queued FIFO so every click gets a response. Work is tagged
//     with its originating port so responses route back to the right tab; two
//     active tabs simply serialize through the one interpreter. ------------- //

function schedule() {
  if (busy || !pyodide)
    return
  if (pendingReload !== null) {
    const source = pendingReload
    pendingReload = null
    busy = true
    doReloadModel(source)
      .then(({ schema, presets }) => {
        const s = schema as JsonSchema
        const p = presets as Preset[]
        // Refresh the cached ready state so tabs connecting after a reload get
        // the new schema, then tell current tabs to re-render the form.
        if (bootState.kind === 'ready') {
          bootState = { kind: 'ready', msg: { type: 'ready', schema: s, presets: p } }
        }
        broadcast({ type: 'model-reloaded', schema: s, presets: p })
      })
      .catch(err => broadcast({ type: 'log', stream: 'stderr', text: `model reload failed: ${err?.message ?? err}` }))
      .finally(() => {
        busy = false
        schedule()
      })
    return
  }
  const meas = measureQueue.shift()
  if (meas) {
    busy = true
    doMeasure(meas.changes)
      .then((response) => {
        if (response)
          post(meas.port, { type: 'measure-response', response })
      })
      .catch(err => post(meas.port, { type: 'log', stream: 'stderr', text: `measure failed: ${err?.message ?? err}` }))
      .finally(() => {
        busy = false
        schedule()
      })
    return
  }
  const nextBuild = pendingBuilds.entries().next()
  if (!nextBuild.done) {
    const [port, req] = nextBuild.value
    pendingBuilds.delete(port)
    busy = true
    currentBuildPort = port
    doBuild(req.params)
      .then(result => post(port, { type: 'build-result', id: req.id, ...result }))
      .catch(err =>
        post(port, {
          type: 'build-result',
          id: req.id,
          ok: false,
          errors: [{ loc: [], msg: String(err?.message ?? err), type: 'worker_error' }],
        }),
      )
      .finally(() => {
        currentBuildPort = null
        busy = false
        schedule()
      })
    return
  }
  const exp = exportQueue.shift()
  if (exp) {
    busy = true
    doExport(exp.params, exp.format)
      .then(bytes =>
        post(exp.port, { type: 'export-result', id: exp.id, format: exp.format, bytes }, [bytes.buffer]),
      )
      .catch(err =>
        post(exp.port, { type: 'export-result', id: exp.id, format: exp.format, error: String(err?.message ?? err) }),
      )
      .finally(() => {
        busy = false
        schedule()
      })
  }
}

// Drop a departed tab's port and any of its queued work. Python keeps running
// for the other tabs; the browser tears the SharedWorker down once the last
// port closes. An in-flight build for this port still completes but its
// response posts to a now-dead port (harmlessly dropped).
function cleanupPort(port: MessagePort) {
  ports.delete(port)
  pendingBuilds.delete(port)
  for (let i = exportQueue.length - 1; i >= 0; i--) {
    if (exportQueue[i].port === port)
      exportQueue.splice(i, 1)
  }
  for (let i = measureQueue.length - 1; i >= 0; i--) {
    if (measureQueue[i].port === port)
      measureQueue.splice(i, 1)
  }
}

// A new tab connected. Register it, catch it up on boot state (so a late joiner
// isn't stuck watching a boot it missed), then serve its requests.
function connect(port: MessagePort) {
  ports.add(port)
  port.start()

  if (bootState.kind === 'ready') {
    // Finish this tab's progress bar, then hand over the cached schema/presets.
    post(port, { type: 'boot', stage: 'Ready', progress: 1 })
    post(port, bootState.msg)
  }
  else if (bootState.kind === 'error') {
    post(port, { type: 'boot-error', message: bootState.message })
  }
  else {
    post(port, { type: 'boot', stage: bootState.stage, progress: bootState.progress })
  }

  port.onmessage = (e: MessageEvent<WorkerRequest>) => {
    const msg = e.data
    switch (msg.type) {
      case 'build':
        pendingBuilds.set(port, { id: msg.id, params: msg.params }) // coalesce: keep only latest
        schedule()
        break
      case 'export':
        exportQueue.push({ port, id: msg.id, format: msg.format, params: msg.params })
        schedule()
        break
      case 'measure':
        measureQueue.push({ port, changes: msg.changes })
        schedule()
        break
      case 'disconnect':
        cleanupPort(port)
        break
    }
  }
}

(globalThis as unknown as SharedWorkerGlobalScope).onconnect = (e: MessageEvent) => {
  connect(e.ports[0])
}

initialize().catch((err) => {
  console.error('Pyodide worker failed to initialize:', err)
  bootState = { kind: 'error', message: formatBootError(err) }
  broadcast({ type: 'boot-error', message: bootState.message })
})

// Assemble the fullest description we can for the boot-error screen. `.stack`
// usually already includes the message, but not always (some WASM traps and
// PythonErrors put the human-readable part on `.message` only), so lead with the
// message and append the stack when it adds anything beyond it.
function formatBootError(err: unknown): string {
  if (err == null)
    return 'Unknown error'
  if (typeof err !== 'object')
    return String(err)
  const e = err as { name?: string, message?: string, stack?: string }
  const message = [e.name, e.message].filter(Boolean).join(': ')
  const stack = e.stack ?? ''
  if (stack && !stack.includes(e.message ?? '\0'))
    return [message, stack].filter(Boolean).join('\n\n')
  return stack || message || String(err)
}

// Dev only: a SharedWorker survives page reloads, so after editing worker or
// Python code it would keep serving stale code until every tab closes. On an HMR
// update, tell tabs to reload and close ourselves — the next `new SharedWorker`
// then spawns a fresh instance on the new (no-cache, dev) code. Tree-shaken from
// production builds (`import.meta.hot` is statically undefined there).
if (import.meta.hot) {
  // The model source (chain.py) is the seam: re-exec it in place instead of
  // rebooting the whole Pyodide/OCP stack (tens of seconds). This dep-scoped
  // handler intercepts chain.py?raw changes so they DON'T fall through to the
  // blanket handler below. It's the same mechanism the future Code tab uses.
  import.meta.hot.accept('../python/chain.py?raw', (mod) => {
    const source = (mod as { default?: string } | undefined)?.default
    if (source != null) {
      pendingReload = source
      schedule()
    }
  })
  // Any other change (worker code, proto/runtime/measure/install.py) still needs
  // a fresh interpreter — full reload.
  import.meta.hot.accept(() => {
    broadcast({ type: 'reload' });
    (globalThis as unknown as SharedWorkerGlobalScope).close()
  })
}
