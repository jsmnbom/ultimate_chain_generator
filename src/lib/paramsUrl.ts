// Serialize the form's parameters to/from the URL query so a configured design is
// shareable by link. Pure (no DOM): the Generator view owns the reactive
// vue-router `route.query` bridge and just calls these to translate. The path
// (`/m/:slug`) selects the design; the query carries only its non-default params.

import type { JsonSchema } from './protocol'

type Params = Record<string, number | string>

/** vue-router query shape: a value can be a string, repeated (array), or null. */
type RouteQuery = Record<string, string | (string | null)[] | null | undefined>

function isNumeric(type: string | undefined): boolean {
  return type === 'integer' || type === 'number'
}

/**
 * Encode `params` to a flat string map for the URL, **omitting any value equal to
 * its schema default** so shared links stay short and only carry what was changed.
 * Keys not present in the schema are dropped.
 */
export function encodeParams(params: Params, schema: JsonSchema): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [name, prop] of Object.entries(schema.properties)) {
    const value = params[name]
    if (value === undefined || value === prop.default)
      continue
    out[name] = String(value)
  }
  return out
}

/**
 * Build a filesystem-safe export basename (no extension) that encodes the
 * parameters, so a downloaded design self-documents the settings it was built
 * from. `base` is the active design's slug. Only values differing from their
 * schema default are included (matching the URL encoding); an all-default build
 * is just `base`.
 */
export function exportFilename(params: Params, schema: JsonSchema, base: string): string {
  const changed = encodeParams(params, schema)
  const parts = Object.entries(changed).map(
    ([key, value]) => `${key}-${value.replace(/[^a-z0-9.]+/gi, '_')}`,
  )
  return parts.length ? `${base}_${parts.join('_')}` : base
}

/**
 * Decode a URL query (vue-router `route.query`) into a partial params object,
 * coercing numeric fields per the schema `type` and ignoring unknown keys or
 * values that don't parse. Values still pass through the design's real validation
 * on build, so this only needs to produce plausibly-typed inputs.
 */
export function decodeParams(query: RouteQuery, schema: JsonSchema): Params {
  const out: Params = {}
  for (const [name, prop] of Object.entries(schema.properties)) {
    const raw = query[name]
    if (raw === undefined || raw === null)
      continue
    const value = Array.isArray(raw) ? raw[0] : raw
    if (value === null)
      continue
    if (isNumeric(prop.type)) {
      const n = Number(value)
      if (!Number.isNaN(n))
        out[name] = n
    }
    else {
      out[name] = value
    }
  }
  return out
}
