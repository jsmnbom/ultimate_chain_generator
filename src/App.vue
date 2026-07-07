<script setup lang="ts">
import { ref, watch } from "vue";
import { useClipboard, useDebounceFn, useUrlSearchParams } from "@vueuse/core";
import { useChainWorker } from "./composables/useChainWorker";
import { encodeParams, decodeParams, exportFilename } from "./lib/paramsUrl";
import type { JsonSchema } from "./lib/protocol";
import BootProgress from "./components/BootProgress.vue";
import ParamForm from "./components/ParamForm.vue";
import PrintabilityPanel from "./components/PrintabilityPanel.vue";
import Viewer from "./components/Viewer.vue";

const {
  status,
  bootStage,
  bootProgress,
  bootError,
  schema,
  shapes,
  building,
  fieldErrors,
  report,
  build,
  exportModel,
  measure,
} = useChainWorker();

const params = ref<Record<string, number | string>>({});
const exporting = ref<string | null>(null);

// Reactive bridge to the URL query (kept in the real search string, before the
// router's hash, so links stay shareable and independent of the hash router).
const query = useUrlSearchParams("history");

function defaultsFor(s: JsonSchema): Record<string, number | string> {
  const defaults: Record<string, number | string> = {};
  for (const [name, prop] of Object.entries(s.properties)) {
    defaults[name] = (prop.default as number | string) ?? prop.sliderMin ?? prop.minimum ?? 0;
  }
  return defaults;
}

// Seed the form from the schema defaults once the worker is ready, with any
// params carried in the URL layered on top so a shared link boots into its exact
// chain. Seeding kicks off the first build (via the params watcher below).
watch(schema, (s) => {
  if (!s) return;
  params.value = { ...defaultsFor(s), ...decodeParams(query, s) };
});

// Mirror the current params into the URL (debounced), carrying only values that
// differ from the defaults so shared links stay short.
const writeUrl = useDebounceFn((p: Record<string, number | string>) => {
  if (!schema.value) return;
  const encoded = encodeParams(p, schema.value);
  for (const key of Object.keys(query)) {
    if (!(key in encoded)) delete query[key];
  }
  Object.assign(query, encoded);
}, 200);

// Every param change (initial seed included) requests a debounced, latest-wins
// build and syncs the URL.
watch(
  params,
  (p) => {
    if (Object.keys(p).length) {
      build(p);
      writeUrl(p);
    }
  },
  { deep: true },
);

// Presets are disabled for now — see the commented-out picker in the template and
// the plumbing kept in useChainWorker/protocol/runtime for when they return.
//
// // Presets replace the whole param set (merged over defaults so every field is
// // present); the URL then updates via the params watcher.
// function applyPreset(preset: Preset) {
//   if (!schema.value) return;
//   params.value = { ...defaultsFor(schema.value), ...preset.params };
// }
//
// const presetItems = computed(() => presets.value.map((p) => p.name));
//
// function onPresetSelect(name: string) {
//   const preset = presets.value.find((p) => p.name === name);
//   if (preset) applyPreset(preset);
// }

// Copy a link to the exact current chain.
const { copy, copied } = useClipboard();
function copyLink() {
  copy(window.location.href);
}

async function downloadExport(format: "STEP" | "3MF") {
  if (exporting.value) return;
  exporting.value = format;
  try {
    const bytes = await exportModel(format, params.value);
    const blob = new Blob([bytes as BlobPart], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const base = schema.value ? exportFilename(params.value, schema.value) : "chain";
    a.download = `${base}.${format.toLowerCase()}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("Export failed", err);
  } finally {
    exporting.value = null;
  }
}
</script>

<template>
  <UApp>
    <BootProgress v-if="status !== 'ready'" :stage="bootStage" :progress="bootProgress" :error="bootError" />


    <!-- Two resizable panes (drag the handle between them). Sizes in rem so the
         control pane matches the old fixed w-96; persisted to localStorage. -->
    <UDashboardGroup v-else storage="local" storage-key="ucg-layout" unit="rem">
      <!-- Left: generated form + export -->
      <UDashboardPanel id="controls" resizable :default-size="24" :min-size="18" :max-size="40" class="bg-white">
        <header class="flex items-start justify-between gap-2 border-b border-neutral-200 px-5 py-4">
          <div class="min-w-0">
            <h1 class="text-lg font-semibold text-neutral-800">Ultimate Chain Generator</h1>
            <p class="text-sm text-neutral-500">Parametric 3D-printable chains</p>
          </div>
          <UButton
            size="xs"
            variant="ghost"
            color="neutral"
            :icon="copied ? 'i-lucide-check' : 'i-lucide-link'"
            :label="copied ? 'Copied!' : 'Copy link'"
            @click="copyLink"
          />
        </header>

        <div class="min-h-0 grow overflow-y-auto px-5 py-5">
          <!-- Presets disabled for now. Curated, verified starting points; applying
               one replaces the whole param set, so the picker holds no persistent
               selection. Re-enable alongside the script bits in App.vue.
          <USelectMenu
            v-if="presetItems.length"
            :model-value="undefined"
            :items="presetItems"
            :search-input="false"
            placeholder="Load a preset"
            icon="i-lucide-bookmark"
            class="mb-5 w-full"
            @update:model-value="onPresetSelect"
          />
          -->

          <ParamForm v-if="schema" v-model="params" :schema="schema" :field-errors="fieldErrors" />

          <div v-if="report" class="mt-6 border-t border-neutral-200 pt-5">
            <PrintabilityPanel :report="report" />
          </div>
        </div>

        <footer class="border-t border-neutral-200 px-5 py-4">
          <p class="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-400">
            Export
          </p>
          <!-- 3MF is the preferred format (OrcaSlicer project); STEP is secondary. -->
          <div class="flex items-center gap-2">
            <UButton class="grow" color="primary" variant="solid" icon="i-lucide-download"
              :loading="exporting === '3MF'" :disabled="!!exporting" @click="downloadExport('3MF')">
              3MF <span class="ml-1 text-xs opacity-75">· recommended</span>
            </UButton>
            <UTooltip
              text="Works with most 3D programs and slicers, and best with OrcaSlicer (it's an OrcaSlicer project)."
              :delay-duration="0"
            >
              <UIcon name="i-lucide-circle-help" class="size-4 shrink-0 cursor-help text-neutral-400" />
            </UTooltip>
          </div>
          <UButton class="mt-2" block color="neutral" variant="outline" icon="i-lucide-download"
            :loading="exporting === 'STEP'" :disabled="!!exporting" @click="downloadExport('STEP')">
            STEP
          </UButton>
        </footer>
      </UDashboardPanel>

      <!-- Right: viewer -->
      <UDashboardPanel id="viewer" class="bg-neutral-100">
        <Viewer :shapes="shapes" :building="building" :measure="measure" />
      </UDashboardPanel>
    </UDashboardGroup>
  </UApp>
</template>
