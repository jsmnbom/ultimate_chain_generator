<script setup lang="ts">
import { useToast } from '@nuxt/ui/composables'
import { onMounted, watch } from 'vue'
import { branding } from '../branding'
import { injectDesignWorker } from '../composables/useDesignWorker'
import { designs } from '../designs/manifest'

// The gallery landing. The worker (created at the app root) is already booting
// the CAD engine while this renders, so opening a design feels instant — a
// dismissible toast lets the user know it's warming up.
const worker = injectDesignWorker()
const { status, bootProgress } = worker

const gitHash = __GIT_HASH__
const gitHashShort = gitHash === 'dev' ? 'dev' : gitHash.slice(0, 7)
const commitUrl = gitHash === 'dev' ? branding.repoUrl : `${branding.repoUrl}/commit/${gitHash}`

// Warm-up toast: mounted while the engine boots, auto-dismissed once it's ready.
// The worker broadcasts boot progress the moment it's constructed (at app root),
// so by the time the gallery mounts we may already be booting — or done.
const toast = useToast()
let toastId: string | number | undefined

function showWarmup() {
  if (toastId !== undefined || status.value !== 'booting')
    return
  const t = toast.add({
    title: 'Warming up the 3D engine',
    description: 'Designs open instantly once it\'s ready (~20s, one time).',
    icon: 'i-lucide-loader-circle',
    color: 'neutral',
    duration: 0, // sticky until we remove it on ready
    close: true,
  })
  toastId = t.id
}

function dismissWarmup() {
  if (toastId !== undefined) {
    toast.remove(toastId)
    toastId = undefined
  }
}

onMounted(showWarmup)
watch(status, (s) => {
  if (s === 'booting')
    showWarmup()
  else dismissWarmup()
})
</script>

<template>
  <div class="min-h-full bg-neutral-50">
    <div class="mx-auto max-w-6xl px-6 py-10">
      <header class="mb-8 flex items-end justify-between gap-4">
        <div class="min-w-0">
          <h1 class="text-2xl font-semibold text-neutral-900">
            {{ branding.galleryName }}
          </h1>
          <p class="mt-1 text-neutral-500">
            {{ branding.tagline }}
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <UButton
            v-for="link in branding.links"
            :key="link.label"
            size="xs"
            variant="ghost"
            color="neutral"
            :icon="link.icon"
            :label="link.label"
            :to="link.to"
            external
            target="_blank"
          />
        </div>
      </header>

      <!-- Boot progress hint at the top of the grid (in addition to the toast). -->
      <div v-if="status === 'booting'" class="mb-6">
        <UProgress :model-value="Math.round(bootProgress * 100)" size="sm" />
      </div>

      <div class="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <RouterLink
          v-for="d in designs"
          :key="d.slug"
          :to="{ name: 'generator', params: { slug: d.slug } }"
          class="group focus:outline-none"
        >
          <div
            class="flex h-full flex-col overflow-hidden rounded-xl border bg-white transition
                   hover:-translate-y-0.5 hover:shadow-md group-focus-visible:ring-2
                   group-focus-visible:ring-primary-500"
            :class="d.blank
              ? 'border-dashed border-neutral-300'
              : 'border-neutral-200'"
          >
            <!-- Thumbnail / placeholder -->
            <div
              class="flex aspect-[4/3] items-center justify-center bg-neutral-100 text-neutral-300"
            >
              <img
                v-if="d.thumb"
                :src="d.thumb"
                :alt="d.name"
                class="h-full w-full object-cover"
              >
              <UIcon
                v-else
                :name="d.blank ? 'i-lucide-plus' : 'i-lucide-box'"
                class="size-10"
              />
            </div>

            <div class="flex grow flex-col gap-1 p-4">
              <div class="flex items-center gap-2">
                <h2 class="font-medium text-neutral-900">
                  {{ d.name }}
                </h2>
                <UBadge v-if="d.author" size="sm" variant="subtle" color="neutral">
                  {{ d.author }}
                </UBadge>
              </div>
              <p v-if="d.description" class="text-sm text-neutral-500">
                {{ d.description }}
              </p>
            </div>
          </div>
        </RouterLink>
      </div>

      <footer class="mt-10 flex items-center justify-between border-t border-neutral-200 pt-4 text-sm text-neutral-400">
        <span>Powered by <span class="font-medium text-neutral-500">{{ branding.engineName }}</span></span>
        <UButton
          size="xs"
          variant="ghost"
          color="neutral"
          icon="i-lucide-git-commit-horizontal"
          :label="gitHashShort"
          :to="commitUrl"
          external
          target="_blank"
          title="View this build's commit on GitHub"
          class="font-mono"
        />
      </footer>
    </div>
  </div>
</template>
