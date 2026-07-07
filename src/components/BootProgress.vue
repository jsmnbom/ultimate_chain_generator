<script setup lang="ts">
defineProps<{
  stage: string;
  progress: number;
  error: string | null;
}>();
</script>

<template>
  <div class="flex h-full w-full items-center justify-center bg-neutral-50 p-6">
    <div class="w-full">
      <h1 class="mb-6 text-center text-xl font-semibold text-neutral-800">
        Ultimate Chain Generator
      </h1>

      <div v-if="error">
        <UAlert color="error" variant="soft" icon="i-lucide-triangle-alert" title="Failed to start"
          :description="error" />
        <p class="mt-3 text-center text-xs text-neutral-400">
          The first load fetches the CAD kernel (OCP.wasm) from a CDN. Check your
          connection and reload.
        </p>
      </div>

      <div v-else class="max-w-md mx-auto">
        <div class="h-2 w-full overflow-hidden rounded-full bg-neutral-200">
          <div class="h-full rounded-full bg-neutral-800 transition-all duration-300 ease-out"
            :style="{ width: `${Math.round(progress * 100)}%` }" />
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
