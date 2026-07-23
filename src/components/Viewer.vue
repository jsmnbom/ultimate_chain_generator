<script setup lang="ts">
import type { ChangeNotification, Shapes } from 'three-cad-viewer'
import { Display, Viewer as TCVViewer } from 'three-cad-viewer'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
// The published bundle carries no CSS import of its own — the stylesheet ships
// as a separate export — so pull it in here to style the viewer chrome.
import 'three-cad-viewer/css'

const props = defineProps<{
  shapes: Shapes | null
  building: boolean
}>()

const host = ref<HTMLDivElement | null>(null)
let display: any = null
let viewer: any = null
let hasRendered = false
let resizeObserver: ResizeObserver | null = null

// reset_camera="Keep" emulation (ports vscode-ocp-cad-viewer's viewer.html).
// Instead of snapping back to the default iso view on every rebuild, preserve the
// user's current view (direction, target, zoom). Camera state is captured live
// from change notifications (orbit/pan/zoom) and after each render, then
// re-applied — rescaled to the new shape's bounding box — on the next render.
let keptPosition: number[] | null = null
let keptQuaternion: number[] | null = null
let keptTarget: number[] | null = null
let keptZoom: number | null = null
let keptCameraDistance: number | null = null

const TREE_WIDTH = 240
const GLASS = true

const renderOptions = {
  ambientIntensity: 1.0,
  directIntensity: 1.1,
  metalness: 0.3,
  roughness: 0.65,
  edgeColor: 0x707070,
  defaultOpacity: 0.5,
  normalLen: 0,
}

const viewerOptions = {
  axes: true,
  axes0: true,
  blackEdges: false,
  grid: [false, false, false] as [boolean, boolean, boolean],
  ortho: true,
  ticks: 10,
  transparent: false,
  up: 'Z',
  control: 'trackball',
  glass: GLASS,
  tools: true,
  collapse: 1,
}

// Change-notification callback. v5 measures geometry with its own built-in
// mesh-based backend, so the only thing we need from notifications is the live
// camera — tracked here so a rebuild can restore whatever the user is looking at.
function handleNotify(changed: ChangeNotification) {
  if (changed.position)
    keptPosition = changed.position.new as number[]
  if (changed.quaternion)
    keptQuaternion = changed.quaternion.new as number[]
  if (changed.target)
    keptTarget = changed.target.new as number[]
  if (changed.zoom)
    keptZoom = changed.zoom.new as number
}

// The height we pass to the viewer sizes only the canvas. tcv wraps that canvas
// in .tcv_cad_viewer alongside a toolbar, a tick-size bar and margins, so the
// rendered container is taller than the canvas by that chrome (~44px). Measure it
// from the live DOM (canvas height vs. wrapper's occupied height) and subtract it
// so the whole viewer fits the container instead of overflowing it.
function chromeHeight() {
  const el = host.value
  const cad = el?.querySelector('.tcv_cad_viewer') as HTMLElement | null
  const view = el?.querySelector('.tcv_cad_view') as HTMLElement | null
  if (!cad || !view)
    return 2 // elements not built yet; first render corrects it
  const cs = getComputedStyle(cad)
  const margins = parseFloat(cs.marginTop) + parseFloat(cs.marginBottom)
  return cad.offsetHeight + margins - view.offsetHeight
}

// Horizontal analogue of chromeHeight(): .tcv_cad_viewer carries a 4px margin on
// every side (ui.css) and the cad body is sized to cadWidth + 2, so the viewer's
// footprint is wider than the canvas by those margins plus that fudge. Subtract it
// so the toolbar's right-anchored controls (filter/help) aren't clipped by the
// container's overflow-hidden. Measure live; fall back to 4+4+2 before build.
function chromeWidth() {
  const cad = host.value?.querySelector('.tcv_cad_viewer') as HTMLElement | null
  if (!cad)
    return 10 // elements not built yet; first render corrects it
  const cs = getComputedStyle(cad)
  return parseFloat(cs.marginLeft) + parseFloat(cs.marginRight) + 2
}

function dims() {
  const el = host.value!
  const width = GLASS ? Math.max(10, el.clientWidth - chromeWidth()) : Math.max(10, el.clientWidth - TREE_WIDTH)
  const height = Math.max(10, el.clientHeight - chromeHeight())
  return { width, height }
}

function createViewer() {
  if (!host.value)
    return
  const { width, height } = dims()
  // three-cad-viewer accepts a single flat bag of display+render+view options at
  // runtime (as its own examples do); its stricter split types don't model that.
  const options: any = {
    ...renderOptions,
    ...viewerOptions,
    cadWidth: width,
    height,
    treeWidth: TREE_WIDTH,
    theme: 'light',
    pinning: false,
    newTreeBehavior: true,
    measureTools: true,
    // v5 default (false) uses the built-in mesh-based measurement backend, so we
    // no longer wire up an external Python measurement backend.
    externalMeasurementBackend: false,
    selectTool: true,
    explodeTool: false,
    zscaleTool: false,
    zebraTool: false,
    // Studio mode (PBR / env-maps / post-processing) is hidden.
    studioTool: false,
  }
  display = new Display(host.value, options)
  viewer = new TCVViewer(display, options, handleNotify)
  display.glassMode(GLASS)
  display.showTools(true)
  display.setTheme('light')
}

function normalize([x, y, z]: number[]) {
  const len = Math.hypot(x, y, z) || 1
  return [x / len, y / len, z / len]
}

// Build the camera keys for viewer.render() that reproduce the kept view,
// re-seated to the freshly-built shape's bounding box. Returns null on the first
// render (no camera captured yet) so the viewer picks its own default framing.
function keepViewOptions(shapes: Shapes) {
  const bb = shapes.bb
  if (!keptPosition || !keptTarget || !bb)
    return null

  const center = [(bb.xmax + bb.xmin) / 2, (bb.ymax + bb.ymin) / 2, (bb.zmax + bb.zmin) / 2]
  const diag = Math.hypot(bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin)
  const bbRadius = Math.max(diag, Math.hypot(center[0], center[1], center[2]))
  const cameraDistance = 2.5 * bbRadius

  // Keep the viewing direction (camera relative to target) but push the camera out
  // to the new bounding distance so the object stays fully framed.
  const dir = normalize([
    keptPosition[0] - keptTarget[0],
    keptPosition[1] - keptTarget[1],
    keptPosition[2] - keptTarget[2],
  ])
  const position = [
    dir[0] * cameraDistance + keptTarget[0],
    dir[1] * cameraDistance + keptTarget[1],
    dir[2] * cameraDistance + keptTarget[2],
  ]

  return {
    position,
    ...(keptQuaternion ? { quaternion: keptQuaternion } : {}),
    target: keptTarget,
    ...(keptZoom != null ? { zoom: keptZoom } : {}),
  }
}

function renderShapes(shapes: Shapes) {
  if (!viewer)
    return
  if (hasRendered)
    viewer.clear()

  const keep = keepViewOptions(shapes)
  // Zoom compensation only applies once a previous frame established a distance.
  const priorZoom = keep ? keptZoom : null
  const priorDistance = keep ? keptCameraDistance : null

  viewer.render(shapes, renderOptions, { ...viewerOptions, ...(keep ?? {}) })

  // Re-seating to a new bounding box changes the orthographic camera distance;
  // rescale the kept zoom by the distance ratio so the object holds the same
  // apparent on-screen size across rebuilds (matches ocp-cad-viewer's "keep").
  if (priorDistance != null) {
    viewer.setCameraZoom(((priorZoom ?? 1.0) * viewer.camera.camera_distance) / priorDistance)
  }

  // Capture the resulting camera as the baseline for the next rebuild.
  keptPosition = viewer.getCameraPosition()
  keptQuaternion = viewer.getCameraQuaternion()
  keptTarget = viewer.getCameraTarget()
  keptZoom = viewer.getCameraZoom()
  keptCameraDistance = viewer.camera.camera_distance

  hasRendered = true
  onResize() // fit to the current container now that a scene exists
}

function onResize() {
  // resizeCadView is only valid once render() has established a scene.
  if (!viewer || !hasRendered || !host.value)
    return
  const { width, height } = dims()
  viewer.resizeCadView(width, TREE_WIDTH, height, GLASS)
}

// Capture the current scene as a PNG data URL (a screenshot of the current view —
// also handy as a gallery thumbnail). getImage() grabs the canvas only (no toolbar)
// and hides the orientation marker itself; we additionally hide the coordinate axes
// for a clean shot, then restore them. Returns null when nothing is rendered yet.
async function captureScreenshot(): Promise<string | null> {
  if (!viewer || !hasRendered)
    return null
  try {
    viewer.setAxes(false)
    viewer.setAxes0(false)
    const { dataUrl } = await viewer.getImage('screenshot')
    return typeof dataUrl === 'string' ? dataUrl : null
  }
  finally {
    viewer.setAxes(viewerOptions.axes)
    viewer.setAxes0(viewerOptions.axes0)
  }
}

defineExpose({ captureScreenshot })

onMounted(() => {
  createViewer()
  if (props.shapes)
    renderShapes(props.shapes)
  resizeObserver = new ResizeObserver(onResize)
  resizeObserver.observe(host.value!)
})

watch(
  () => props.shapes,
  (shapes) => {
    if (shapes)
      renderShapes(shapes)
  },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  try {
    viewer?.dispose?.()
    display?.dispose?.()
  }
  catch {
    /* ignore teardown errors */
  }
})
</script>

<template>
  <div class="relative h-full w-full min-h-0 min-w-0 overflow-hidden">
    <div ref="host" class="h-full w-full" />
    <Transition name="fade">
      <div
        v-if="building"
        class="pointer-events-none absolute right-3 top-3 flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-sm text-neutral-600 shadow-sm ring-1 ring-neutral-200 backdrop-blur"
      >
        <span class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-600" />
        Rebuilding…
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

<style>
/* Reskin three-cad-viewer's light theme to design 1b "Studio Pink":
   frosted-glass floating chrome, a warm near-white backdrop, and a pink accent.
   Everything is scoped under .tcv_cad_viewer — that both keeps the overrides off
   the rest of the app and lets them win: the --tcv-* custom properties are
   re-declared on .tcv_cad_viewer (closer to the chrome than tcv's own
   [data-theme="light"] host rule, so all descendants inherit these), and the
   structural rules gain a class of specificity over tcv's single-class rules. */
.tcv_cad_viewer {
  /* Anchor the (now absolutely-positioned) floating toolbar to the viewer. */
  position: relative;
  margin: 0 !important;

  /* Pink accent — drives the active-tab underline + selected borders. */
  --tcv-theme-blue: #db2777;
  /* Frosted-white glass panels (toolbar / tree / info). */
  --tcv-bg-overlay-color: rgba(255, 255, 255, 0.9);
  --tcv-bg-overlay-rest-color: rgba(255, 255, 255, 0.82);
  /* Pink-tint hover / pressed states. Icons keep tcv's dark data-URI glyphs —
     recoloring those (1b's white-on-pink button) would mean overriding dozens of
     baked-in SVG urls, so the pink tint is the accent we carry here instead. */
  --tcv-bg-highlight-color: #fce7f3;
  --tcv-bg-pressed-color: #fdf2f8;
  --tcv-bg-pressed-border-color: #db2777;
  /* Axis + orientation-marker colors (X/Y/Z per 1b). */
  --tcv-x-color: #dc2626;
  --tcv-y-color: #16a34a;
  --tcv-z-color: #2563eb;
  /* Pink-tinted shadows + tooltip. */
  --tcv-shadow: rgba(157, 23, 77, 0.25);
  --tcv-menu-shadow: rgba(157, 23, 77, 0.25);
  --tcv-bg-tooltip-color: #fdf2f8;
  --tcv-font-color: #3f3f46;

  --tcv-ui-row-gap: 4px;

  /* Warm near-white radial backdrop, shown through the transparent WebGL canvas
     (the renderer clears with alpha 0 and .tcv_cad_view is otherwise unpainted). */
  .tcv_cad_view {
    background: radial-gradient(circle at 55% 42%, #fffdfe, #faf5f7);
  }

  /* Float the toolbar as a centered frosted pill over the canvas. tcv sizes it
     with an inline width/height, so override those with !important and let the
     buttons determine the pill's natural size. */
  .tcv_cad_toolbar {
    position: absolute;
    z-index: 100;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    width: auto !important;
    height: auto !important;
    align-items: center;
    gap: 4px;
    padding: 5px 8px;
    background: rgba(255, 255, 255, 0.82);
    backdrop-filter: blur(8px);
    border: 1px solid #f4f4f5;
    box-shadow: 0 6px 20px -8px rgba(157, 23, 77, 0.25);
  }

  /* Frost the floating tree card, keep it permanently open (glass mode otherwise
     collapses it behind a "Tools" toggle), and let it read slightly see-through so
     the model shows behind it. */
  .tcv_cad_tree {
    /* display: flex !important; */
    /* Compact floating card, not a full-height slab — the node list scrolls. */
    /* max-height: 300px !important; */
    background-color: rgba(255, 255, 255, 0.72) !important;
    border: 1px solid rgba(255, 255, 255, 0.6) !important;
    box-shadow: 0 10px 30px -12px rgba(157, 23, 77, 0.45);
    backdrop-filter: blur(10px);
    transform: translateY(50%);
  }

  /* Drop the collapsible "Tools" header (tcv shows it inline in glass mode). */
  /* .tcv_toggle_tools_wrapper {
    display: none !important;
  } */

  /* Remove the Material tab (hide its whole flex cell, not just the input). */
  .tcv_tabnav span:has(.tcv_tab_material) {
    display: none !important;
  }

  /* Pull the canvas flush to the viewer's left edge (glass insets it by 4px). */
  .tcv_cad_view_glass {
    left: 0 !important;
  }

  /* Float the tree card clear of the toolbar pill so they never overlap on
     narrow panes (toolbar sits at top:12px and is ~42px tall). */
  /* .tcv_cad_navigation {
    margin-top: 56px;
    margin-left: 8px;
  } */

  /* Warm the tree header + selected-tab text toward 1b's deep pink. */
  .tcv_tools_label,
  .tcv_info_label,
  .tcv_tab-selected {
    color: #9d174d;
  }

  .tcv_cad_info_wrapper {
    display: none !important;
  }

  .tcv_round {
    border-radius: 0 !important;
  }
}
</style>
