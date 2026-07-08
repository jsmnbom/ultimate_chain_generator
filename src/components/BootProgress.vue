<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  stage: string
  progress: number
  error: string | null
}>()

const showDetails = ref(false)

// The worker forwards whatever the boot failure produced. A clean Python/JS
// error starts with a readable message ("RangeError: …"); a low-level WASM trap
// during OCP.wasm instantiation has no message at all — its first line is
// already a stack frame. Surface the former as the headline, fall back to a
// friendly summary for the latter.
const headline = computed(() => {
  const first = props.error?.split('\n')[0]?.trim() ?? ''
  const looksLikeFrame = /wasm-function|@\S+\.(?:mjs|js):\d/.test(first)
  if (!first || looksLikeFrame)
    return 'The CAD kernel failed to load — usually a temporary network hiccup or low memory.'
  return first
})

// Only bother offering the expander when there's more than the headline to show.
const hasDetails = computed(() => (props.error?.trim().length ?? 0) > 0 && props.error!.trim() !== headline.value)
</script>

<template>
  <div class="flex h-full w-full select-text items-center justify-center bg-neutral-50 p-6">
    <div class="w-full">
      <h1 class="mb-6 text-center text-xl font-semibold text-neutral-800">
        Ultimate Chain Generator
      </h1>

      <div v-if="error" class="max-w-xl mx-auto">
        <UAlert
          color="error" variant="soft" icon="i-lucide-triangle-alert" title="Failed to start"
          :description="headline"
        />
        <p class="mt-3 text-center text-xs text-neutral-400">
          The first load fetches the CAD kernel (OCP.wasm) from a CDN. Try reloading —
          if it keeps failing, check your connection and close other memory-heavy tabs.
        </p>

        <div v-if="hasDetails" class="mt-3 text-center">
          <UButton
            :icon="showDetails ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
            color="neutral" variant="ghost" size="xs"
            :label="showDetails ? 'Hide details' : 'Show details'"
            @click="showDetails = !showDetails"
          />
          <pre
            v-if="showDetails"
            class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-neutral-100 p-3 text-left text-xs leading-relaxed text-neutral-600"
          >{{ error }}</pre>
        </div>
      </div>

      <div v-else class="max-w-md mx-auto">
        <div class="h-2 w-full overflow-hidden rounded-full bg-neutral-200">
          <div
            class="h-full rounded-full bg-neutral-800 transition-all duration-300 ease-out"
            :style="{ width: `${Math.round(progress * 100)}%` }"
          />
        </div>
        <div class="mt-3 flex items-center justify-between text-sm text-neutral-500">
          <span>{{ stage }}</span>
          <span class="tabular-nums">{{ Math.round(progress * 100) }}%</span>
        </div>
        <p class="mt-6 text-center text-xs text-neutral-400">
          First load downloads and compiles the CAD kernel — this can take a
          while. It should be faster on subsequent loads.
        </p>
      </div>
    </div>
  </div>
</template>
