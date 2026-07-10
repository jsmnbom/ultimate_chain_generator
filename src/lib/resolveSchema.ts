import type { JsonSchema, JsonSchemaProperty } from './protocol'

/**
 * Resolve a raw JSON Schema (as emitted by pydantic's `model_json_schema()`) into
 * the flat form the form renderer reads directly: each choice property's `$ref`
 * into `#/$defs/*` (the enum defs for `link_shape` / `cross_section`) is
 * dereferenced and `$defs` is dropped. Non-`$ref` properties pass through.
 *
 * Why a merge, not just the resolved target: pydantic 2.x emits `$ref` *with
 * sibling keywords* (JSON Schema 2020-12) — our `json_schema_extra` (`label`,
 * `options`) and the field `default` sit next to the `$ref`. We overlay the raw
 * property's own keys over the resolved target so the property's siblings always
 * win and nothing authored in design.py is lost.
 *
 * This is a deliberately minimal dereferencer (local `#/...` pointers only) — the
 * whole pipeline only ever produces intra-document refs into `$defs`, so a full
 * JSON Schema library would be dead weight.
 */
export function resolveSchema(raw: unknown): JsonSchema {
  const schema = raw as JsonSchema

  const properties: Record<string, JsonSchemaProperty> = {}
  for (const [name, rawProp] of Object.entries(schema.properties)) {
    const { $ref, ...siblings } = rawProp as JsonSchemaProperty & { $ref?: string }
    const target = $ref ? derefProperty(schema, $ref) : {}
    properties[name] = { ...target, ...siblings }
  }

  const { $defs: _defs, ...rest } = schema as JsonSchema & { $defs?: unknown }
  return { ...rest, properties }
}

/**
 * Follow a local JSON Pointer `$ref` (`#/$defs/Name`) to its target schema,
 * transitively resolving a chain of refs. Returns an empty object if the pointer
 * can't be resolved (mirrors the previous resolver degrading gracefully).
 */
function derefProperty(root: JsonSchema, ref: string): JsonSchemaProperty {
  const seen = new Set<string>()
  let current = ref
  while (current && current.startsWith('#/') && !seen.has(current)) {
    seen.add(current)
    const node = resolvePointer(root, current.slice(2))
    if (!node || typeof node !== 'object') return {}
    const next = (node as { $ref?: unknown }).$ref
    if (typeof next === 'string') {
      current = next
      continue
    }
    return node as JsonSchemaProperty
  }
  return {}
}

/** Resolve a `/`-separated JSON Pointer body against `root` (RFC 6901 unescape). */
function resolvePointer(root: unknown, pointer: string): unknown {
  let node: unknown = root
  for (const raw of pointer.split('/')) {
    if (node == null || typeof node !== 'object') return undefined
    const key = raw.replace(/~1/g, '/').replace(/~0/g, '~')
    node = (node as Record<string, unknown>)[key]
  }
  return node
}
