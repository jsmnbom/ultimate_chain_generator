<script setup lang="ts">
import { defineAsyncComponent, watch } from 'vue'
import { useRouter } from 'vue-router'
import BootProgress from '../components/BootProgress.vue'
import { injectDesignWorker } from '../composables/useDesignWorker'
import { getDesign } from '../designs/manifest'

// One generator for a design, addressed by slug (`/m/:slug`). The engine (the
// shared worker) is already booting — or booted — from the app root; here we just
// select this design by handing its source to the worker, and show boot chrome
// until both the engine is warm and the design's schema has arrived.
const props = defineProps<{ slug: string }>()

const router = useRouter()
const worker = injectDesignWorker()
const { status, bootStage, bootProgress, bootError, schema } = worker

const AppContent = defineAsyncComponent(() => import('../components/AppContent.vue'))

// Select the design: clear any stale schema (so the previous design's form
// vanishes during the swap) and, once the engine is ready, hand its source to the
// worker. An unknown slug bounces back to the gallery.
function selectDesign() {
  const meta = getDesign(props.slug)
  if (!meta) {
    router.replace({ name: 'gallery' })
    return
  }
  if (status.value === 'ready')
    worker.reloadDesign(meta.source, meta.slug)
}

watch(
  () => props.slug,
  () => {
    // Hide the outgoing design's form immediately; the fresh schema re-seeds it.
    schema.value = null
    selectDesign()
  },
  { immediate: true },
)
// The engine may still be booting when we mount — reselect once it's ready.
watch(status, selectDesign)

const meta = () => getDesign(props.slug)
</script>

<template>
  <!-- Engine boot / fatal boot error take the whole screen. -->
  <div v-if="status === 'error'" class="fixed inset-0 z-50">
    <BootProgress :stage="bootStage" :progress="bootProgress" :error="bootError" />
  </div>
  <div v-else-if="status === 'booting'" class="fixed inset-0 z-50">
    <BootProgress :stage="bootStage" :progress="bootProgress" :error="bootError" />
  </div>

  <!-- Engine ready: the generator. AppContent copes with a not-yet-loaded schema
       (shows its own loading state) while the design's source is exec'd. -->
  <Suspense v-else>
    <AppContent
      :key="slug"
      :worker="worker"
      :slug="slug"
      :design-name="meta()?.name ?? slug"
      :blank="meta()?.blank ?? false"
    />
  </Suspense>
</template>
