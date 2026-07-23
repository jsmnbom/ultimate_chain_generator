<script setup lang="ts">
import type { DesignWorker } from '../composables/useDesignWorker'
import type { JsonSchema } from '../lib/protocol'
import { onKeyStroke, useClipboard, useDebounceFn, useLocalStorage } from '@vueuse/core'
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { branding } from '../branding'
import { getDesign } from '../designs/manifest'
import { decodeParams, encodeParams, exportFilename } from '../lib/paramsUrl'
import ParamForm from './ParamForm.vue'
import PrintabilityPanel from './PrintabilityPanel.vue'

// The generator body for one design: the parameters form on the left + the 3D
// viewer. The design's source is a read-only layer that slides over the form on
// demand. The engine (worker) is already booted; this component is keyed by slug
// so each design gets a clean slate. It copes with a not-yet-loaded schema (the
// design's source is exec'd asynchronously).
const props = defineProps<{
  worker: DesignWorker
  slug: string
  designName: string
}>()

// Heavy, lazily-loaded panes — kept out of the main bundle.
const Viewer = defineAsyncComponent(() => import('./Viewer.vue'))
const CodeEditor = defineAsyncComponent(() => import('./CodeEditor.vue'))

const {
  schema,
  shapes,
  building,
  fieldErrors,
  report,
  reloadError,
  reloading,
  build,
  exportModel,
} = props.worker

const route = useRoute()
const router = useRouter()

const params = ref<Record<string, number | string>>({})
const exporting = ref<string | null>(null)

// Handle on the (async) Viewer, so the Screenshot button can grab a canvas PNG.
const viewerRef = ref<{ captureScreenshot: () => Promise<string | null> } | null>(null)

// The source view is a layer over the form, not a mode you switch into. Monaco is
// mounted on first open and then kept alive (hidden with v-show), so reopening is
// instant and the form underneath never loses its scroll position.
const showCode = ref(false)
const codeMounted = ref(false)
function openCode() {
  codeMounted.value = true
  showCode.value = true
}
onKeyStroke('Escape', () => {
  if (showCode.value)
    showCode.value = false
})

// The design's source, from the bundled manifest. Shown read-only for now — live
// editing hot-swapped the design on every keystroke, which the error surface isn't
// set up to handle.
const source = getDesign(props.slug)?.source ?? ''

// Per-design footer links (Printables, shop, …), scraped from the design's LINKS
// constant into the manifest. Empty for designs that declare none.
const designLinks = getDesign(props.slug)?.links ?? []

// Auto-generated link to this design's source `.py` on GitHub, pinned to the
// build's commit for accuracy (falls back to HEAD outside a git checkout). This
// replaces the old global commit link with a design-specific one.
const sourceRef = __GIT_HASH__ === 'dev' ? 'HEAD' : __GIT_HASH__
const sourceUrl = `${branding.repoUrl}/blob/${sourceRef}/src/designs/${props.slug}/design.py`

// Split-button: the primary action remembers the last format the user picked.
const exportFormat = useLocalStorage<'3MF' | 'STEP'>('lab-export-format', '3MF')
const exportItems = computed(() =>
  [[
    {
      label: '3MF',
      description: 'Works with most 3D programs and slicers. Recommended.',
      icon: 'i-lucide-download',
      onSelect: () => downloadExport('3MF'),
    },
    {
      label: 'STEP',
      description: 'CAD interchange format.',
      icon: 'i-lucide-download',
      onSelect: () => downloadExport('STEP'),
    },
  ]],
)

function defaultsFor(s: JsonSchema): Record<string, number | string> {
  const defaults: Record<string, number | string> = {}
  for (const [name, prop] of Object.entries(s.properties)) {
    defaults[name] = (prop.default as number | string) ?? prop.sliderMin ?? prop.minimum ?? 0
  }
  return defaults
}

// Seed the form whenever the schema arrives or changes. On the first load, URL
// query params layer over the defaults so a shared link boots into its exact
// configuration. On an in-place schema change (a Code-tab edit that alters
// Parameters), current values are *preserved* for fields that still exist — a
// keystroke must not reset the form — with defaults filling any newly-added
// field. Seeding kicks off a build via the params watcher below.
watch(schema, (s) => {
  if (!s)
    return
  const defaults = defaultsFor(s)
  const urlParams = decodeParams(route.query, s)
  const kept: Record<string, number | string> = {}
  for (const name of Object.keys(s.properties)) {
    if (params.value[name] !== undefined)
      kept[name] = params.value[name]
  }
  params.value = { ...defaults, ...urlParams, ...kept }
}, { immediate: true })

// Mirror the current params into the URL query (debounced), carrying only values
// that differ from the defaults so shared links stay short. The path (the design
// slug) is owned by the router; we only rewrite the query.
const writeUrl = useDebounceFn((p: Record<string, number | string>) => {
  if (!schema.value)
    return
  const query = encodeParams(p, schema.value)
  router.replace({ name: 'generator', params: { slug: props.slug }, query })
}, 200)

// Every param change (initial seed included) requests a debounced, latest-wins
// build and syncs the URL.
watch(
  params,
  (p) => {
    if (Object.keys(p).length) {
      build(p)
      writeUrl(p)
    }
  },
  { deep: true },
)

// Copy a link to the exact current configuration.
const { copy, copied } = useClipboard()
function copyLink() {
  copy(window.location.href)
}

// Save a screenshot of the current viewer render as a PNG (named after the design
// + params, like exports). Doubles as the source for a gallery thumbnail: rename it
// to `thumb.png` in `src/designs/<slug>/`. Silently no-ops if nothing is rendered.
async function saveScreenshot() {
  const dataUrl = await viewerRef.value?.captureScreenshot()
  if (!dataUrl)
    return
  const base = schema.value ? exportFilename(params.value, schema.value, props.slug) : props.slug
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = `${base}.png`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function downloadExport(format: 'STEP' | '3MF') {
  if (exporting.value)
    return
  exportFormat.value = format
  exporting.value = format
  try {
    const bytes = await exportModel(format, params.value)
    const blob = new Blob([bytes as BlobPart], { type: 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const base = schema.value ? exportFilename(params.value, schema.value, props.slug) : props.slug
    a.download = `${base}.${format.toLowerCase()}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
  catch (err) {
    console.error('Export failed', err)
  }
  finally {
    exporting.value = null
  }
}
</script>

<template>
  <!-- Two resizable panes (drag the handle between them). Sizes in rem so the
       control pane matches the old fixed w-96; persisted to localStorage. -->
  <UDashboardGroup storage="local" storage-key="lab-layout" unit="rem">
    <!-- Left: tabbed form / code + export -->
    <UDashboardPanel id="controls" resizable :default-size="24" :min-size="18" :max-size="44" class="bg-white">
      <header class="flex flex-col border-b border-primary-200 bg-primary-50">
        <div class="flex items-start justify-between gap-2 px-5 py-3">
          <div class="flex min-w-0 items-start gap-2">
            <UButton
              size="xs"
              variant="ghost"
              color="neutral"
              icon="i-lucide-arrow-left"
              :to="{ name: 'gallery' }"
              title="Back to gallery"
              class="mt-0.5 shrink-0"
            />
            <div class="min-w-0">
              <h1 class="truncate text-lg font-semibold text-neutral-800">
                {{ designName }}
              </h1>
              <p class="text-sm text-neutral-500">
                {{ branding.galleryName }}
              </p>
            </div>
          </div>
          <div class="flex shrink-0 flex-col items-end">
            <UButton
              size="xs"
              variant="ghost"
              color="neutral"
              :icon="copied ? 'i-lucide-check' : 'i-lucide-link'"
              :label="copied ? 'Copied!' : 'Copy link'"
              @click="copyLink"
            />
            <UButton
              size="xs"
              variant="ghost"
              color="neutral"
              icon="i-lucide-camera"
              label="Screenshot"
              title="Save a PNG of the current view"
              :disabled="!shapes"
              @click="saveScreenshot"
            />
          </div>
        </div>
      </header>

      <!-- Pane body: the form, with the source view layered over it on demand. -->
      <div class="relative flex min-h-0 grow flex-col">
        <!-- The footer (export + project links) is pinned at the bottom of the
             form, so it's specific to a design's parameters. -->
        <div class="flex min-h-0 grow flex-col">
          <div class="min-h-0 grow overflow-y-auto px-5 py-5">
            <UAlert
              v-if="reloadError"
              color="error"
              variant="subtle"
              icon="i-lucide-circle-alert"
              class="mb-5"
              title="Design failed to load"
            >
              <template #description>
                <pre class="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs">{{ reloadError }}</pre>
              </template>
            </UAlert>
            <div v-if="!schema" class="flex items-center gap-2 text-sm text-neutral-400">
              <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
              Loading design…
            </div>
            <template v-else>
              <ParamForm v-model="params" :schema="schema" :field-errors="fieldErrors" />

              <div v-if="report" class="mt-6 border-t border-neutral-200 pt-5">
                <PrintabilityPanel :report="report" />
              </div>
            </template>
          </div>

          <footer class="border-t border-neutral-200 px-5 py-2">
            <!-- Split button: primary action remembers the last-used format; the
                 dropdown chevron switches between 3MF and STEP. -->
            <UFieldGroup class="w-full">
              <UButton
                class="grow justify-center" color="primary" variant="solid" icon="i-lucide-download"
                :loading="!!exporting" :disabled="!!exporting || !schema" @click="downloadExport(exportFormat)"
              >
                {{ exporting ? `Exporting ${exporting}…` : `Export ${exportFormat}` }}
              </UButton>
              <UDropdownMenu :items="exportItems" :disabled="!!exporting || !schema" :content="{ align: 'end' }">
                <UButton color="primary" variant="solid" icon="i-lucide-chevron-down" :disabled="!!exporting || !schema" />
              </UDropdownMenu>
            </UFieldGroup>

            <!-- Per-design links: the design's own LINKS plus an auto-generated
                 link to its source .py on GitHub. -->
            <div class="mt-2 flex justify-between border-t border-neutral-200 pt-1">
              <div class="flex flex-wrap items-center gap-1">
                <UButton
                  v-for="link in designLinks"
                  :key="link.url"
                  size="xs"
                  variant="ghost"
                  color="neutral"
                  :icon="link.icon"
                  :label="link.label"
                  :to="link.url"
                  external
                  target="_blank"
                />
              </div>
              <UButton
                size="xs"
                variant="ghost"
                color="neutral"
                icon="i-lucide-code"
                label="View code"
                title="View this design's source"
                @click="openCode"
              />
            </div>
          </footer>
        </div>

        <!-- Source view: read-only, slides over the form. Mounted on first open
             and kept alive after that (see `codeMounted`). -->
        <Transition
          enter-active-class="transition-transform duration-200 ease-out"
          leave-active-class="transition-transform duration-150 ease-in"
          enter-from-class="translate-x-full"
          leave-to-class="translate-x-full"
        >
          <div
            v-if="codeMounted"
            v-show="showCode"
            class="absolute inset-0 z-10 flex flex-col bg-white"
          >
            <div
              class="flex items-center gap-1.5 border-b border-neutral-200 py-2 pr-2 pl-3
                     text-xs text-neutral-500"
            >
              <UIcon name="i-lucide-lock" class="size-3 shrink-0" />
              <span class="truncate">Read-only — {{ slug }}/design.py, as it runs.</span>
              <div class="grow" />
              <UButton
                size="xs"
                variant="ghost"
                color="neutral"
                icon="i-lucide-external-link"
                :to="sourceUrl"
                external
                target="_blank"
                title="View on GitHub"
              />
              <UButton
                size="xs"
                variant="ghost"
                color="neutral"
                icon="i-lucide-x"
                title="Close (Esc)"
                @click="showCode = false"
              />
            </div>
            <Suspense>
              <CodeEditor
                :model-value="source"
                :loading="reloading"
                class="min-h-0 grow"
              />
              <template #fallback>
                <div class="flex grow items-center justify-center text-sm text-neutral-400">
                  Loading editor…
                </div>
              </template>
            </Suspense>
          </div>
        </Transition>
      </div>
    </UDashboardPanel>

    <!-- Right: viewer -->
    <UDashboardPanel id="viewer" class="bg-neutral-100">
      <Suspense>
        <Viewer ref="viewerRef" :shapes="shapes" :building="building" />
        <template #fallback>
          <div class="flex h-full items-center justify-center text-sm text-neutral-400">
            Loading viewer…
          </div>
        </template>
      </Suspense>
    </UDashboardPanel>
  </UDashboardGroup>
</template>
