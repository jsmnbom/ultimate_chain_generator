<script setup lang="ts">
import type { ShapeOption } from '../lib/protocol'
import { computed } from 'vue'
import ShapePreview from './ShapePreview.vue'

// A rich dropdown for a choice field: each option shows a geometry-derived shape
// preview. Field-agnostic — the same component renders both the link-outline and
// the cross-section pickers; the only difference is the `svg` baked into each
// option by chain.py. A field is rendered with this (vs a slider) purely by having
// `options`, so there is no per-field widget branching.
type UiSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

const props = withDefaults(
  defineProps<{
    options: ShapeOption[]
    modelValue: number | string
    size?: UiSize
  }>(),
  { size: 'sm' },
)

const emit = defineEmits<{ 'update:modelValue': [number | string] }>()

const current = computed(() => props.options.find(o => o.value === props.modelValue))

// Preview pixel sizes tracked to the Nuxt UI size, for the trigger (compact) and
// the dropdown rows (larger). The "sm" pair keeps the original 20 / 28 px.
const PREVIEW_PX: Record<UiSize, { trigger: number, item: number }> = {
  xs: { trigger: 16, item: 24 },
  sm: { trigger: 20, item: 28 },
  md: { trigger: 24, item: 34 },
  lg: { trigger: 30, item: 42 },
  xl: { trigger: 36, item: 50 },
}
const previewPx = computed(() => PREVIEW_PX[props.size])
</script>

<template>
  <USelectMenu
    :model-value="modelValue"
    :items="options"
    :size="size"
    value-key="value"
    label-key="label"
    :search-input="false"
    class="w-full"
    :ui="{ content: 'max-h-96', viewport: 'max-h-96' }"
    @update:model-value="(v: number | string) => emit('update:modelValue', v)"
  >
    <!-- Trigger: preview + label of the current value. -->
    <template #default>
      <span class="flex min-w-0 items-center gap-2">
        <ShapePreview :svg="current?.svg" :size="previewPx.trigger" />
        <span class="truncate">{{ current?.label ?? modelValue }}</span>
      </span>
    </template>

    <!-- Each row: larger preview to the left of the label. -->
    <template #item-leading="{ item }">
      <ShapePreview :svg="(item as ShapeOption).svg" :size="previewPx.item" />
    </template>

    <!-- A muted description subtitle (from the choice member's docstring), via
         USelectMenu's own description slot so it isn't rendered twice.
         Enough vertical room is reserved above so all members show without a scroll. -->
    <template #item-description="{ item }">
      <span class="text-xs text-neutral-500">{{ (item as ShapeOption).description }}</span>
    </template>
  </USelectMenu>
</template>
