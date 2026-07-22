// Message protocol shared between the main thread and the Pyodide worker.

/**
 * A structured validation / build error, surfaced inline on the form.
 *  `loc` is the pydantic error location; `loc[0]` (when present) is the field.
 */
export interface FieldError {
  loc: string[]
  msg: string
  type: string
}

/** Severity of a printability finding; drives its colour in the panel. */
export type ReportStatus = 'ok' | 'warning' | 'error'

/**
 * One measured/derived finding: a labelled value with optional unit, an
 *  explanatory detail line, and a status colour.
 */
export interface ReportItem {
  label: string
  value: number
  unit?: string
  detail?: string
  status?: ReportStatus
}

/**
 * Generic analysis report — the TS mirror of `proto.py`'s `Report.to_dict()`. A
 *  flat list of findings the panel renders as-is, so it is not chain-specific.
 */
export interface PrintabilityReport {
  overall_status: ReportStatus
  summary: string
  items: ReportItem[]
}

export interface BuildResult {
  ok: boolean
  errors?: FieldError[]
  report?: PrintabilityReport
}

// --- Main thread -> worker ------------------------------------------------- //
export type WorkerRequest
  = | { type: 'build', id: number, params: Record<string, unknown> }
    | { type: 'export', id: number, format: string, params: Record<string, unknown> }
  // Swap the active design: exec `source` (a design.py) in place and hand back
  // its fresh schema/presets. Drives both gallery design-selection (a bundled
  // design's source) and the Code tab (the editor's contents). Latest-wins, like
  // builds. `slug` identifies the design so dev HMR reloads only when active.
    | { type: 'reload-design', id: number, source: string, slug: string }
  // A tab going away (dispose / pagehide): the SharedWorker drops this port's
  // per-port scheduler state. The browser tears the worker down once the last
  // port closes, so this is cleanup, not shutdown.
    | { type: 'disconnect' }

// --- Worker -> main thread ------------------------------------------------- //
export type WorkerResponse
  = | { type: 'boot', stage: string, progress: number }
    | { type: 'boot-error', message: string }
  // The engine (Pyodide/OCP) finished booting. No design is loaded yet — the main
  // thread selects one by slug and sends `reload-design`, whose reply carries the
  // schema. So the gallery can warm the engine before any design is chosen.
    | { type: 'ready' }
    | { type: 'log', stream: 'stdout' | 'stderr', text: string }
    | { type: 'shapes', data: string }
    | ({ type: 'build-result', id: number } & BuildResult)
    | { type: 'export-result', id: number, format: string, bytes?: Uint8Array, error?: string }
  // Reply to `reload-design` (and dev HMR of a design.py — then `id` is absent).
  // On success carries the fresh schema/presets; on failure `ok:false` + the
  // Python compile/exec `error` traceback so the Code tab can surface it inline.
  // The previous design stays active on failure.
    | {
      type: 'design-reloaded'
      id?: number
      ok: boolean
      schema?: JsonSchema
      presets?: Preset[]
      error?: string
    }
  // Dev-only HMR signal: the SharedWorker is about to close itself because its
  // code (or a Python asset) changed, so tabs should reload onto fresh code.
  // Never emitted in a production build (the emitting block is tree-shaken).
    | { type: 'reload' }

// --- JSON Schema (the subset the form renderer walks) ---------------------- //
export interface JsonSchemaProperty {
  type?: string
  title?: string
  default?: unknown
  description?: string
  enum?: unknown[]
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  exclusiveMaximum?: number
  // widget hints (json_schema_extra). `widget` is the discriminator the form
  // switches on (see ParamForm.vue): "slider" (numeric), "shape" (choice with a
  // geometry-derived preview SVG), "select" (plain enum/Literal dropdown). New
  // parameter types add a value here + a branch there. Set by proto.py's
  // slider_field / choice_field / select_field / cards_field. "cards" is a small
  // set of mutually-exclusive options laid out as big inline tiles (not a dropdown).
  widget?: 'slider' | 'shape' | 'select' | 'cards'
  label?: string
  unit?: string
  // Nuxt UI size for the field's widgets (e.g. "lg" for the shape pickers, "xs"
  // for the minor tilt/brim sliders). Absent means the default size.
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  // The slider's comfortable range (as opposed to minimum/maximum, the hard
  // pydantic validation bounds). See ParamForm's SliderField.
  sliderMin?: number
  sliderMax?: number
  // Dynamic slider max: `{ field: { value: max } }`. When the current model value
  // of `field` has an entry, it overrides `sliderMax` (and the hard input max).
  // Used by tilt_mult, whose usable range depends on the chosen cross_section.
  slider_max_by?: Record<string, Record<string, number>>
  step?: number
  // Choice fields carry their options (with a geometry-derived preview SVG). A
  // property with `options` is rendered as a shape dropdown instead of a slider.
  options?: ShapeOption[]
  // Conditional visibility: a map of other-field-name -> required value(s). The
  // field is shown only when the current model value matches every entry — an
  // array entry matches if the value is one of its members (e.g. tilt_mult's
  // `{ "cross_section": ["decagon", "dodecagon"] }`), a scalar by equality (e.g.
  // brim_diameter's `{ "brim": "ears" }`).
  show_if?: Record<string, unknown>
  [key: string]: unknown
}

/**
 * One choice in a shape/cross-section dropdown. `svg` is generated from the real
 *  build123d outline (see design.py `_choice_field`) so previews match the geometry.
 */
export interface ShapeOption {
  value: number | string
  label: string
  description?: string
  svg?: { viewBox: string, paths: string[] }
}

/**
 * A curated starting-point preset (see design.py `PRESETS`). `params` is a
 *  partial parameter set merged over the schema defaults when applied.
 */
export interface Preset {
  name: string
  description?: string
  params: Record<string, number | string>
}

export interface JsonSchema {
  title?: string
  type?: string
  properties: Record<string, JsonSchemaProperty>
  required?: string[]
  $defs?: Record<string, unknown>
}
