import type { Shapes } from 'three-cad-viewer'
import type { FieldError, JsonSchema, Preset, PrintabilityReport } from '../lib/protocol'
import type { BootStatus, MeasureBridge } from './useChainWorker'
import { ref, shallowRef } from 'vue'
import presetsFixture from '../fixtures/presets.json'
import schemaFixture from '../fixtures/schema.json'
import { resolveSchema } from '../lib/resolveSchema'

// Drop-in stand-in for useChainWorker that never boots Pyodide/OCP. Enabled by
// VITE_MOCK_WORKER (see useChainWorker's dispatch + `pnpm dev:mock`). Lets you
// iterate on the form/layout/export UI without the multi-second CAD-kernel boot.
//
// It reports "ready" immediately, serves a real snapshot of the schema (so the
// form renders exactly as in production — regenerate via
// `scripts/gen_schema_fixture.py`), and leaves the viewer empty: there is no CAD
// kernel here to tessellate geometry, which is the whole point.

// Simulated latencies so the "Rebuilding…" / export spinners are still visible.
const MOCK_BUILD_MS = 150
const MOCK_EXPORT_MS = 400

/**
 * Lightweight bound + relational validation mirroring chain.py's Parameters.
 *  Just enough that the form's inline error UI can be exercised in mock mode.
 */
function validate(schema: JsonSchema, params: Record<string, unknown>): FieldError[] {
  const errors: FieldError[] = []

  for (const [name, prop] of Object.entries(schema.properties)) {
    const v = params[name]
    if (typeof v !== 'number' || Number.isNaN(v))
      continue
    if (prop.maximum !== undefined && v > prop.maximum) {
      errors.push({ loc: [name], msg: `Input should be less than or equal to ${prop.maximum}`, type: 'less_than_equal' })
    }
    if (prop.minimum !== undefined && v < prop.minimum) {
      errors.push({ loc: [name], msg: `Input should be greater than or equal to ${prop.minimum}`, type: 'greater_than_equal' })
    }
    if (prop.exclusiveMinimum !== undefined && v <= prop.exclusiveMinimum) {
      errors.push({ loc: [name], msg: `Input should be greater than ${prop.exclusiveMinimum}`, type: 'greater_than' })
    }
  }

  // Relational rules (form-level, loc: []) — mirror chain.py's _check_relations.
  const { link_thickness: t, link_width: w, link_length: l } = params as Record<string, number>
  if (typeof w === 'number' && typeof t === 'number' && w < t) {
    errors.push({ loc: [], msg: 'link_width must be >= link_thickness', type: 'value_error' })
  }
  else if (typeof l === 'number' && typeof w === 'number' && l < w) {
    errors.push({ loc: [], msg: 'link_length must be >= link_width', type: 'value_error' })
  }

  return errors
}

export function useMockChainWorker() {
  const status = ref<BootStatus>('ready')
  const bootStage = ref('Ready (mock)')
  const bootProgress = ref(1)
  const bootError = ref<string | null>(null)

  const schema = ref<JsonSchema | null>(resolveSchema(schemaFixture))
  const presets = ref<Preset[]>(presetsFixture as Preset[])
  const shapes = shallowRef<Shapes | null>(null) // no CAD kernel -> empty viewer
  const building = ref(false)
  const fieldErrors = ref<FieldError[]>([])
  const report = ref<PrintabilityReport | null>(null)

  let buildTimer: ReturnType<typeof setTimeout> | null = null

  // Static stand-in report so the printability panel renders in mock mode (no
  // CAD kernel here to actually measure geometry).
  const MOCK_REPORT: PrintabilityReport = {
    overall_status: 'warning',
    summary: 'Printable, but check the flagged tolerances before printing.',
    items: [
      {
        label: 'Bed contact per link',
        value: 30.2,
        unit: 'mm²',
        detail: 'Easy — plenty of bed contact.',
        status: 'ok',
      },
      {
        label: 'Links overlap',
        value: 1.74,
        unit: 'mm³',
        detail: 'Links touch with no clearance — may fuse. Thin them slightly.',
        status: 'warning',
      },
    ],
  }

  function build(params: Record<string, unknown>) {
    if (buildTimer)
      clearTimeout(buildTimer)
    building.value = true
    buildTimer = setTimeout(() => {
      fieldErrors.value = schema.value ? validate(schema.value, params) : []
      report.value = fieldErrors.value.length ? null : MOCK_REPORT
      building.value = false
    }, MOCK_BUILD_MS)
  }

  function exportModel(format: string): Promise<Uint8Array> {
    // No geometry to export — hand back a labelled placeholder so the export
    // buttons' loading/download flow is still exercisable end to end.
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(new TextEncoder().encode(`mock ${format} export — no geometry in UI mock mode\n`))
      }, MOCK_EXPORT_MS)
    })
  }

  // No CAD kernel in mock mode, so no geometry to measure: accept and drop.
  const measure: MeasureBridge = { send() { }, onResponse() { } }

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
