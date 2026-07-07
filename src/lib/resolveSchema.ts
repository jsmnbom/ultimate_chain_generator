import type { JsonSchema as LibJsonSchema } from 'json-schema-library'
import type { JsonSchema, JsonSchemaProperty } from './protocol'
import { compileSchema } from 'json-schema-library'

/**
 * Resolve a raw JSON Schema (as emitted by pydantic's `model_json_schema()`) into
 * the flat form the form renderer reads directly: each choice property's `$ref`
 * into `#/$defs/*` (the enum defs for `link_shape` / `cross_section`) is
 * dereferenced and `$defs` is dropped. Non-`$ref` properties pass through.
 *
 * Why a merge, not just the resolver's output: pydantic 2.x emits `$ref` *with
 * sibling keywords* (JSON Schema 2020-12) — our `json_schema_extra` (`label`,
 * `options`) and the field `default` sit next to the `$ref`. json-schema-library
 * resolves the ref but drops sibling keywords it doesn't recognise (notably our
 * `label`), so we overlay the raw property's own keys over the resolved target.
 * The property's siblings always win, so nothing authored in chain.py is lost.
 */
export function resolveSchema(raw: unknown): JsonSchema {
  const schema = raw as JsonSchema
  const root = compileSchema(schema as unknown as LibJsonSchema)

  const properties: Record<string, JsonSchemaProperty> = {}
  for (const [name, rawProp] of Object.entries(schema.properties)) {
    const resolved = root.getNodeChild(name)?.node?.schema
    const target = resolved && typeof resolved === 'object' ? (resolved as JsonSchemaProperty) : {}
    const { $ref: _ref, ...siblings } = rawProp as JsonSchemaProperty & { $ref?: unknown }
    properties[name] = { ...target, ...siblings }
  }

  const { $defs: _defs, ...rest } = schema
  return { ...rest, properties }
}
