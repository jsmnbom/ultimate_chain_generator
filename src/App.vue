<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import BootProgress from './components/BootProgress.vue'
import { useChainWorker } from './composables/useChainWorker'

// The worker is created here, at the app root, so its tens-of-seconds Pyodide/OCP
// boot starts as soon as the (tiny) root mounts — BootProgress is statically
// imported and paints immediately with live progress. Everything else (the Nuxt
// UI dashboard, the form, the viewer) is a single heavy async chunk loaded via
// <Suspense> while the boot runs, so it stays off the critical path. The booting
// worker bundle is handed down to it as a prop.
const AppContent = defineAsyncComponent(() => import('./components/AppContent.vue'))

const chain = useChainWorker()
const { status, bootStage, bootProgress, bootError } = chain
</script>

<template>
  <UApp>
    <!-- Full-screen overlay while booting/on error; the async content mounts and
         loads underneath so its chunk downloads during the boot. -->
    <div v-if="status !== 'ready'" class="fixed inset-0 z-50">
      <BootProgress :stage="bootStage" :progress="bootProgress" :error="bootError" />
    </div>

    <Suspense>
      <AppContent :chain="chain" />
    </Suspense>
  </UApp>
</template>
