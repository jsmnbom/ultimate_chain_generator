<script setup lang="ts">
// Monaco editor for a design's Python source. Loaded only when the Code tab is
// opened (AppContent async-imports this), so Monaco (multi-MB) never lands in the
// main bundle or the Parameters-only flow. Editing emits the new source, which
// AppContent hot-swaps into the running design via the worker.
//
// This is the seam Phase 3 (in-browser Pyright) attaches to: a language client
// wired to Monaco through a lazily-loaded Pyright worker, behind this same async
// boundary. For now it's syntax highlighting + bracket matching only.
import type { editor } from 'monaco-editor'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import * as monaco from 'monaco-editor'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ modelValue: string, loading?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

// Monaco pulls its language services into web workers. We only need the base
// editor worker (Python highlighting is a synchronous Monarch grammar, no
// dedicated language worker). Vite bundles the worker via the `?worker` import.
;(self as unknown as { MonacoEnvironment: monaco.Environment }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
}

const host = ref<HTMLElement | null>(null)
let ed: editor.IStandaloneCodeEditor | null = null
// Guard so applying an external `modelValue` change doesn't echo back out as an
// edit (which would fight the parent and re-trigger reloads).
let applyingExternal = false

onMounted(() => {
  if (!host.value)
    return
  ed = monaco.editor.create(host.value, {
    value: props.modelValue,
    language: 'python',
    theme: 'vs',
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 13,
    tabSize: 2,
    insertSpaces: true,
    scrollBeyondLastLine: false,
    renderWhitespace: 'selection',
    fixedOverflowWidgets: true,
  })
  ed.onDidChangeModelContent(() => {
    if (applyingExternal)
      return
    emit('update:modelValue', ed!.getValue())
  })
})

// External source changes (e.g. switching designs reuses this instance) are
// pushed into the editor without emitting.
watch(() => props.modelValue, (next) => {
  if (ed && next !== ed.getValue()) {
    applyingExternal = true
    ed.setValue(next)
    applyingExternal = false
  }
})

onBeforeUnmount(() => {
  ed?.dispose()
  ed = null
})
</script>

<template>
  <div class="relative min-h-0">
    <div ref="host" class="absolute inset-0" />
    <div
      v-if="loading"
      class="pointer-events-none absolute right-2 top-2 flex items-center gap-1
             rounded bg-white/80 px-2 py-1 text-xs text-neutral-500 shadow-sm"
    >
      <UIcon name="i-lucide-loader-circle" class="size-3 animate-spin" />
      Reloading…
    </div>
  </div>
</template>
