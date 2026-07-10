<script setup lang="ts">
import { provide } from 'vue'
import { designWorkerKey, useDesignWorker } from './composables/useDesignWorker'

// The one worker for the whole app, created at the root so its tens-of-seconds
// Pyodide/OCP boot starts *immediately* — while the user is still browsing the
// gallery, so opening a design feels instant. It's a SharedWorker, so this single
// connection (and its booting backend) persists across `/` → `/m/:slug`
// navigation and is even shared with designs opened in new tabs. Provided down to
// every route via inject; the views never construct their own.
const worker = useDesignWorker()
provide(designWorkerKey, worker)
</script>

<template>
  <UApp>
    <RouterView />
  </UApp>
</template>
