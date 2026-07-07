// Serialize the form's parameters to/from the URL query so a configured chain is
// shareable by link. Pure (no DOM): App.vue owns the reactive `useUrlSearchParams`
// bridge and just calls these to translate.

import type { JsonSchema } from './protocol'

type Params = Record<string, number | string>

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
 * parameters, so a downloaded model self-documents the settings it was built
 * from. Only values differing from their schema default are included (matching
 * the URL encoding); an all-default chain is just `"chain"`.
 */
export function exportFilename(params: Params, schema: JsonSchema): string {
  const changed = encodeParams(params, schema)
  const parts = Object.entries(changed).map(
    ([key, value]) => `${key}-${value.replace(/[^a-z0-9.]+/gi, '_')}`,
  )
  return parts.length ? `chain_${parts.join('_')}` : 'chain'
}

/**
 * Decode a URL query (string map) into a partial params object, coercing numeric
 * fields per the schema `type` and ignoring unknown keys or values that don't
 * parse. Values still pass through the model's real validation on build, so this
 * only needs to produce plausibly-typed inputs.
 */
export function decodeParams(
  query: Record<string, string | string[]>,
  schema: JsonSchema,
): Params {
  const out: Params = {}
  for (const [name, prop] of Object.entries(schema.properties)) {
    const raw = query[name]
    if (raw === undefined)
      continue
    const value = Array.isArray(raw) ? raw[0] : raw
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
