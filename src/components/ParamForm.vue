<script setup lang="ts">
import type { FieldError, JsonSchema, JsonSchemaProperty, ShapeOption } from '../lib/protocol'
import { computed } from 'vue'
import ShapeSelect from './ShapeSelect.vue'

const props = defineProps<{
  schema: JsonSchema
  modelValue: Record<string, number | string>
  fieldErrors: FieldError[]
}>()

const emit = defineEmits<{ 'update:modelValue': [Record<string, number | string>] }>()

// Nuxt UI's size scale, shared by the form field and its controls. The schema's
// `size` hint carries these tokens directly; unset falls back to the default.
type UiSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'
const DEFAULT_SIZE: UiSize = 'sm'
function resolveSize(size?: string): UiSize {
  return (size as UiSize) ?? DEFAULT_SIZE
}

// A field is either a slider (numeric) or a dropdown. The discriminator is the
// schema's `widget` hint (see proto.py's field helpers): "shape"/"select" render
// the dropdown, "slider" the slider. A new widget kind is a new branch here. When
// `widget` is absent we fall back structurally (has `options` -> dropdown).
interface SliderField {
  kind: 'slider'
  name: string
  label: string
  description?: string
  size: UiSize
  unit?: string
  // Slider bounds: the comfortable range (json_schema_extra min/max).
  sliderMin: number
  sliderMax: number
  // Number-input bounds: the hard validation limits (pydantic ge/le, i.e.
  // minimum/maximum). These are wider than the slider, so a value can be typed
  // past the slider's range but is still clamped to what the model accepts.
  inputMin: number
  inputMax: number
  step: number
  isInt: boolean
}
interface SelectField {
  kind: 'select'
  name: string
  label: string
  description?: string
  size: UiSize
  options: ShapeOption[]
}
type Field = SliderField | SelectField

// A field with a `show_if` hint is rendered only when the current model value
// matches every entry in it (e.g. brim_diameter shows only when brim === "ears",
// tilt_mult only for a decagon/dodecagon cross_section). An array entry matches
// by membership; a scalar by equality.
// Reading modelValue here makes the computed re-evaluate as values change.
function matchesShowIf(actual: unknown, expected: unknown): boolean {
  return Array.isArray(expected) ? expected.includes(actual) : actual === expected
}
function isVisible(p: JsonSchemaProperty): boolean {
  if (!p.show_if)
    return true
  return Object.entries(p.show_if).every(([k, v]) => matchesShowIf(props.modelValue[k], v))
}

const fields = computed<Field[]>(() =>
  Object.entries(props.schema.properties)
    .filter(([, p]: [string, JsonSchemaProperty]) => isVisible(p))
    .map(([name, p]: [string, JsonSchemaProperty]): Field => {
      const label = p.label ?? p.title ?? name
      const description = p.description
      const size = resolveSize(p.size)
      const widget = p.widget ?? (p.options ? 'select' : 'slider')
      if (widget !== 'slider' && p.options) {
        return { kind: 'select', name, label, description, size, options: p.options }
      }
      const isInt = p.type === 'integer'
      const hardMin = p.minimum ?? p.exclusiveMinimum
      const hardMax = p.maximum ?? p.exclusiveMaximum
      const sliderMin = p.sliderMin ?? hardMin ?? 0
      let sliderMax = p.sliderMax ?? hardMax ?? 100
      let inputMax = hardMax ?? sliderMax
      // A `slider_max_by` hint tightens the max to depend on another field's
      // current value (e.g. tilt_mult's max varies with cross_section). It is a
      // real constraint here, so it caps both the slider and the number input.
      for (const [field, byValue] of Object.entries(p.slider_max_by ?? {})) {
        const dyn = byValue[props.modelValue[field] as string]
        if (dyn != null) {
          sliderMax = dyn
          inputMax = dyn
        }
      }
      return {
        kind: 'slider',
        name,
        label,
        description,
        size,
        unit: p.unit,
        sliderMin,
        sliderMax,
        inputMin: hardMin ?? sliderMin,
        inputMax,
        step: p.step ?? (isInt ? 1 : 0.1),
        isInt,
      }
    }),
)

// Map field name -> first error message. Errors with an empty loc are form-level.
const errorFor = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const e of props.fieldErrors) {
    const key = e.loc[0]
    if (key && !map[key])
      map[key] = e.msg
  }
  return map
})

const formErrors = computed(() => props.fieldErrors.filter(e => e.loc.length === 0))

function setValue(name: string, value: number | string) {
  // UInputNumber re-emits update:model-value on blur, so clicking away from a
  // field (e.g. into the viewer to orbit) fires this with an unchanged value.
  // Bail on no-ops so we don't push an identical params object and trigger a
  // pointless rebuild — which would re-render the scene and reset the camera.
  if (props.modelValue[name] === value)
    return
  emit('update:modelValue', { ...props.modelValue, [name]: value })
}

// Intl.NumberFormat's `style: 'unit'` only accepts CLDR-sanctioned unit
// identifiers ("millimeter", "degree", …) and throws a RangeError on anything
// else ("mm", "°", "links"). Rather than force design authors onto that list,
// fall back to plain decimal formatting for units Intl can't render, so an
// unsupported unit degrades to a bare number instead of crashing the form.
function isSupportedUnit(unit: string): boolean {
  try {
    // eslint-disable-next-line no-new
    new Intl.NumberFormat(undefined, { style: 'unit', unit })
    return true
  }
  catch {
    return false
  }
}

function numberFormatOptions(f: SliderField) {
  if (f.unit && isSupportedUnit(f.unit)) {
    return {
      style: 'unit',
      unit: f.unit,
      unitDisplay: 'narrow',
    }
  }
  return { style: 'decimal' }
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <UFormField
      v-for="f in fields"
      :key="f.name"
      :label="f.label"
      :error="errorFor[f.name]"
      :size="f.size"
    >
      <!-- Label with an optional info icon; hovering it reveals the field's
           description (desktop-only app, so a hover tooltip is the help idiom). -->
      <template #label>
        <span class="inline-flex items-center gap-1">
          {{ f.label }}
          <UTooltip v-if="f.description" :text="f.description" :delay-duration="0">
            <UIcon name="i-lucide-info" class="size-3.5 shrink-0 cursor-help text-neutral-400" />
          </UTooltip>
        </span>
      </template>

      <ShapeSelect
        v-if="f.kind === 'select'"
        :model-value="modelValue[f.name]"
        :options="f.options"
        :size="f.size"
        @update:model-value="(v: number | string) => setValue(f.name, v)"
      />

      <div v-else class="flex items-center gap-3">
        <USlider
          class="grow"
          :size="f.size"
          :model-value="(modelValue[f.name] as number)"
          :min="f.sliderMin"
          :max="f.sliderMax"
          :step="f.step"
          @update:model-value="(v: number | number[]) => setValue(f.name, Array.isArray(v) ? v[0] : v)"
        />
        <UInputNumber
          class="w-28 shrink-0"
          :size="f.size"
          :model-value="(modelValue[f.name] as number)"
          :min="f.inputMin"
          :max="f.inputMax"
          :step="f.step"
          :format-options="numberFormatOptions(f)"
          @update:model-value="(v: number) => setValue(f.name, v)"
        />
      </div>
    </UFormField>

    <UAlert
      v-if="formErrors.length"
      color="error"
      variant="soft"
      icon="i-lucide-triangle-alert"
      :title="formErrors.map((e) => e.msg).join('; ')"
    />
  </div>
</template>
