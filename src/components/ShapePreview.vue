<script setup lang="ts">
import type { ShapeOption } from "../lib/protocol";

// Renders the outline SVG that Python generated from the real build123d geometry
// (chain.py `_outline_svg`). Nothing is drawn by hand here — we just place the
// exported path(s) into a themed <svg>, so a preview can never disagree with the
// shape `build()` produces. The `scale(1,-1)` mirrors ExportSVG's own Y-flip
// (CAD Y-up vs SVG Y-down).
const props = withDefaults(
  defineProps<{ svg?: ShapeOption["svg"]; size?: number }>(),
  { size: 28 },
);
</script>

<template>
  <svg
    v-if="svg"
    class="shape-preview"
    :width="size"
    :height="size"
    :viewBox="svg.viewBox"
    preserveAspectRatio="xMidYMid meet"
    aria-hidden="true"
  >
    <g transform="scale(1,-1)">
      <path
        v-for="(d, i) in svg.paths"
        :key="i"
        :d="d"
        fill="none"
        stroke="currentColor"
        stroke-linejoin="round"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
      />
    </g>
  </svg>
</template>

<style scoped>
/* non-scaling-stroke keeps the line a constant on-screen weight across shapes of
   very different model dimensions, so every preview reads at the same thickness. */
.shape-preview {
  display: block;
  flex: none;
  stroke-width: 1.4;
  overflow: visible;
}
</style>
