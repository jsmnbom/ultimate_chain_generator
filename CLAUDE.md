# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**build123d-lab** — a browser playground for parametric 3D-printable **designs**.
Everything runs client-side: Python (build123d) executes in a web worker via
Pyodide + OCP.wasm, geometry is tessellated with ocp-tessellate and rendered with
three-cad-viewer. No server. See `README.md` for the stack table.

**Engine vs. content.** `build123d-lab` is the reusable engine (the Vue app shell,
`ParamForm`/`Viewer`, worker, protocol, `proto.py` SDK, `runtime.py`, and the
build/deploy/wheel tooling). **Paws & Parts** is this repo's content: the
`src/designs/` gallery + `src/branding.ts`. The engine depends only on two seams —
the **design manifest** (`src/designs/manifest.ts`) and the **branding config**
(`src/branding.ts`) — never on a specific design's internals, so it stays cheap to
extract later. A single design ("chain") is just one bundled entry.

## Commands

Toolchain is managed with [mise] (`.mise.toml` pins Node 25, pnpm 10, Python 3.13, uv).

```sh
mise install          # toolchain
pnpm install          # JS/TS deps
uv sync --extra dev   # Python dev env, for authoring/type-checking src/python natively

pnpm dev              # Vite dev server (http://localhost:5173)
pnpm dev:mock         # ...Pyodide/OCP boot skipped, static schema, empty viewer (UI work)
pnpm typecheck        # vue-tsc --noEmit
pnpm build            # typecheck + production build to dist/
uv run ruff format src/python   # formatting only (see below)
```

The user runs `ruff format` and tests themselves — don't run them. To verify a
change, instruct the user how to exercise it (dev server, or the native
round-trip below), rather than running a test suite (there is none).

Exercise the Python contract natively — same source the worker runs (`design.py`
is imported by name, with `proto.py` on `sys.path`, so pydantic can resolve the
design's forward refs):

```sh
uv run python -c "import sys; sys.path.insert(0,'src/python'); \
  sys.path.insert(0,'src/designs/chain'); import proto, design; \
  D = proto.load_design(vars(design)); print(D(D.Parameters()))"
```

## The single-source-of-truth contract

The seam is defined in `src/python/proto.py` (the design-authoring **SDK**) and
implemented by each `src/designs/<slug>/design.py` (chain is the reference one).
`proto.py` is the one place that states the whole contract — read its module
docstring first.

A design module exposes exactly one **`Design` subclass**:

- `class Chain(Design[Parameters])` — the generic arg binds the pydantic
  `Parameters` type (auto-extracted in `Design.__init_subclass__`), so the form
  schema is available via `Chain.Parameters.model_json_schema()` before any
  geometry exists.
- **Instantiating** `Chain(params)` *builds* the geometry into `self` (a
  build123d `Compound`, like `BasePartObject`) — construction **is** the build.
- `Chain.analyze(self) -> Report` (optional) returns the printability report,
  reading `self` directly. `Chain.PRESETS` (optional) are curated starting points.
- Optional module-level `NAME` / `AUTHOR` / `DESCRIPTION` string constants, a
  `BLANK = True` flag, and a `LINKS` list (`{"label", "url"}` dicts → per-design
  footer links, icons auto-derived from the URL host) are scraped by `manifest.ts`
  for the gallery card / generator footer (co-located so they can't drift; no
  Python boot needed to read them).

`runtime.py` binds to this via `proto.load_design(namespace)`, holding the active
subclass as `ActiveDesign` — it never reaches for loose `build`/`analyze` globals.
The engine boots **without** a design; the frontend selects one by slug and
`reload_design(source)` execs it and rebinds `ActiveDesign`. Keep the contract clean; don't leak chain-specifics into
`proto.py`/the worker/runtime/frontend.

- Cross-field rules (`link_width >= link_thickness`, etc.) live in a pydantic
  `@model_validator(mode="after")`, **not** duplicated in JS. The form learns
  about violations by attempting a build and rendering the returned
  `ValidationError` inline. There is no separate client-side validation.
- Widget hints ride on each `Field` via `json_schema_extra` — use `proto.py`'s
  `slider_field` / `choice_field` / `select_field`, each of which stamps a
  `widget` discriminator (`"slider"`/`"shape"`/`"select"`) the form switches on.
  Add a new parameter type by adding a helper there + a branch in `ParamForm.vue`.
  "How to show the form" stays co-located with the design. The schema→component
  mapping is in `src/components/ParamForm.vue`; `src/lib/resolveSchema.ts` flattens
  pydantic's `$ref`/`$defs` first.
- The printability report is a flat list of findings built with `proto.Report`
  (`r.add(label, value, ...)`, auto-rolled `overall_status`/`summary`; `value` is
  numeric). Its `to_dict()` is mirrored by `PrintabilityReport` in `protocol.ts` and
  rendered generically by `PrintabilityPanel.vue`. Generic finding-builders live in
  `proto.py` (`check_bed_contact` / `check_interlock` / `check_floating` — they take a
  `Report` and add a finding, owning default thresholds/wording any design can reuse);
  design-specific choices (which face is the footprint, brim messaging, the chain's link
  lean) stay in the design's `analyze`. `Design.analyze`'s default is an empty report —
  a design opts into checks by calling the helpers.
- `proto.py`'s `Choice` is a lightweight enum-like whose members are static
  methods (docstring → label/description) and whose SVG previews are generated
  from the *real* build123d outline, so previews can't drift from the geometry.

## Runtime architecture

Data flows main thread ↔ worker over a typed message protocol in
`src/lib/protocol.ts` (`WorkerRequest`/`WorkerResponse`). Read it first when
touching cross-boundary code.

- **Routing / views.** `src/main.ts` uses `createWebHistory` (real paths, no hash;
  `BASE_URL` carries the Pages subpath). `/` → `src/views/Gallery.vue` (design cards
  from `manifest.ts`); `/m/:slug` → `src/views/Generator.vue` (the form+viewer for
  one design). `App.vue` constructs the **one** worker at the app root and
  `provide()`s it (`designWorkerKey`) so its OCP boot warms while the gallery is
  browsed; both views inject it. `dist/404.html` (a copy of `index.html`, emitted by
  the `spaFallback` Vite plugin) is the GitHub Pages SPA deep-link fallback.
- `src/worker/pyodide.worker.ts` — boots Pyodide once, then serves requests. It
  `exec`s the Python assets in order: `install.py` → writes `proto.py` to the FS
  (it must be *importable*, the rest are exec'd into globals) → `runtime.py`. It
  boots with **no design**; the main thread sends `reload-design` (a bundled
  design's source) to bind one. A `host_bridge` JsModule lets
  Python post the tessellated Shapes tree straight to the main thread. Scheduler
  runs one Python call at a time: design reloads and builds **coalesce to
  latest-wins**, exports are FIFO.
- `src/python/runtime.py` — holds the active seam as `ActiveDesign` (bound by
  `reload_design`), and exposes worker-facing helpers: `get_schema_json`,
  `build_and_show` (validate → `ActiveDesign(params)` build → tessellate →
  `obj.analyze()`), `export_bytes` (STEP via build123d; 3MF OrcaSlicer project via
  orca123d), and `reload_design` (re-exec a design in place — gallery select / dev
  hot-reload; returns `{ok, schema?, presets?, error?}`, surfacing a bad edit's
  traceback instead of throwing).
- `src/composables/useDesignWorker.ts` — worker lifecycle + reactive state (schema,
  shapes, building, fieldErrors, report, `reloadError`, `reloading`), debounced
  `build` and `reloadDesign`, export. `useMockDesignWorker.ts` is the `dev:mock`
  stand-in (serves the default design's schema fixture).
- `src/components/` — `BootProgress`, `ParamForm`, `Viewer` (three-cad-viewer
  wrapper), `PrintabilityPanel`, `ShapeSelect`, `ShapePreview`, `AppContent` (the
  form + viewer body), `CodeEditor` (lazy Monaco; loads only when the source view is
  first opened, so Monaco never touches the main bundle). The source view is
  **read-only** and presented as a layer that slides over the form inside the
  controls pane (a "Code" button in the header opens it; ✕ / Esc closes it) — live
  edits hot-swapping the design on every keystroke outran the error surface, so
  `CodeEditor` doesn't emit and `AppContent` doesn't call `reloadDesign`. With no
  authoring path, `BLANK` designs are filtered out of the gallery
  (`src/views/Gallery.vue`) while still reachable at `/m/<slug>`.

Full regeneration on every parameter change (no incremental updates) — each
change re-runs `ActiveDesign(params)` and re-tessellates the whole design. First
load compiles OCP.wasm (tens of seconds); the boot progress bar covers it and is a
separate UI state from the sub-second per-build spinner.

In dev, editing a `src/designs/<slug>/design.py` triggers a Vite page reload;
because the **SharedWorker survives page reloads**, the page reconnects to the
already-booted backend (no Pyodide reboot) and the Generator re-selects the fresh
source via `reload-design` — effectively a hot-swap with no boot bar. Editing an engine asset (worker/`proto.py`/`runtime.py`/…) still does a full
reload *and* reboots the interpreter (those are in the worker's import graph).

## Version pinning — these move together

The Python packages are installed **in the browser by exact wheel URL with
`deps=False`** (`src/python/install.py`), so no dependency resolution runs at
boot. `REQUIREMENTS` is the human-editable pin list; `_WHEEL_URLS` is generated.
The `-OCP.wasm` wheels are custom OpenCascade builds matched to specific
build123d / ocp-tessellate / three-cad-viewer versions. When bumping any of
these, bump them **as a set**, then regenerate:

```sh
pnpm gen:wheels   # node scripts/gen-pyodide-wheels.mjs — resolves + rewrites _WHEEL_URLS
```

Coupled invariants to keep in sync by hand:
- `PYODIDE_VERSION` in `pyodide.worker.ts` **must equal** the `pyodide`
  devDependency (`gen:wheels` guards this).
- The worker's `loadPackage([...])` list must cover the built-in deps the pinned
  wheels need (they're installed `deps=False`); `gen:wheels` prints the required
  built-in roots.
- `pyproject.toml` deps mirror the browser pins so native authoring/type-checking
  hits the same API surface. `.venv` is not what runs in the browser.
- The `# === MOCKS ===` block in `install.py` stubs out browser-unusable/heavy
  deps (IPython, ezdxf, scipy/sklearn/sympy, lib3mf) that build123d imports at
  load but this app's code paths don't exercise. `gen:wheels` reads this block to
  resolve requirements, so keep the markers intact.

After changing the default design's (`src/designs/chain/design.py`) `Parameters`,
regenerate the mock-mode schema snapshot so `pnpm dev:mock` stays accurate:

```sh
uv run python scripts/gen_schema_fixture.py   # → src/fixtures/schema.json
```

## Linting / type-checking

`ruff` is **formatting only** — `[tool.ruff.lint] select = []` makes `ruff check`
a no-op. Type-checking of `src/python` is Pylance (Pyright) in the editor (see
`.vscode/settings.json`), against `cadquery-ocp-stubs`.

[mise]: https://mise.jdx.dev
