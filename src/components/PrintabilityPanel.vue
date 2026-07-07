<script setup lang="ts">
import type { PrintabilityReport, ReportStatus } from "../lib/protocol";

// Generic renderer for an analysis report: an overall verdict banner followed by
// sections of labelled value/status items. Nothing here is chain-specific — it
// draws whatever sections/items the report carries (see chain.py `analyze`).
defineProps<{ report: PrintabilityReport }>();

// Colored classes for the collapsed verdict header (the always-visible summary).
const HEADER_CLASS: Record<ReportStatus, string> = {
  ok: "bg-green-50 text-green-700 ring-green-200",
  warning: "bg-amber-50 text-amber-700 ring-amber-200",
  error: "bg-red-50 text-red-700 ring-red-200",
};
const ALERT_ICON: Record<ReportStatus, string> = {
  ok: "i-lucide-circle-check",
  warning: "i-lucide-triangle-alert",
  error: "i-lucide-circle-x",
};
const ITEM_ICON: Record<ReportStatus, string> = {
  ok: "i-lucide-check",
  warning: "i-lucide-triangle-alert",
  error: "i-lucide-x",
};
const ITEM_CLASS: Record<ReportStatus, string> = {
  ok: "text-green-600",
  warning: "text-amber-600",
  error: "text-red-600",
};
</script>

<template>
  <!-- Collapsed by default to just the colored verdict line; the audience mostly
       knows how to print, so the per-metric detail is opt-in (click to expand). -->
  <UCollapsible class="w-full">
    <template #default="{ open }">
      <button
        type="button"
        class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium ring-1 ring-inset"
        :class="HEADER_CLASS[report.overall_status]"
      >
        <UIcon :name="ALERT_ICON[report.overall_status]" class="shrink-0" />
        <span class="grow">{{ report.summary }}</span>
        <UIcon
          name="i-lucide-chevron-down"
          class="shrink-0 transition-transform"
          :class="{ 'rotate-180': open }"
        />
      </button>
    </template>

    <template #content>
      <div class="flex flex-col gap-4 pt-3">
        <div v-for="(section, si) in report.sections" :key="si" class="flex flex-col gap-2">
          <p class="text-xs font-medium uppercase tracking-wide text-neutral-400">
            {{ section.title }}
          </p>
          <ul class="flex flex-col gap-2">
            <li
              v-for="(item, ii) in section.items"
              :key="ii"
              class="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2"
            >
              <div class="flex items-baseline justify-between gap-2">
                <span class="flex items-center gap-1.5 text-sm font-medium text-neutral-800">
                  <UIcon v-if="item.status" :name="ITEM_ICON[item.status]" :class="ITEM_CLASS[item.status]" />
                  {{ item.label }}
                </span>
                <span class="shrink-0 tabular-nums text-sm font-semibold text-neutral-700">
                  {{ item.value
                  }}<span v-if="item.unit" class="ml-0.5 text-xs font-normal text-neutral-500">{{ item.unit }}</span>
                </span>
              </div>
              <p v-if="item.detail" class="mt-1 text-xs text-neutral-500">{{ item.detail }}</p>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </UCollapsible>
</template>
