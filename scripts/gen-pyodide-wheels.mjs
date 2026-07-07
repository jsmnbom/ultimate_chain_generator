// Regenerates the pinned `_WHEEL_URLS` block in src/python/install.py.
//
// install.py installs the CAD stack by exact wheel URL with deps=False, so nothing is
// resolved against PyPI at browser boot. This script does that resolution once, offline:
// it boots Pyodide (same version as the worker), applies install.py's mock block,
// installs REQUIREMENTS by name (full dependency resolution), then `micropip.freeze()`s
// the result and writes every PyPI-hosted wheel URL back into install.py.
//
// Run after changing REQUIREMENTS (or bumping the Pyodide version):
//   node scripts/gen-pyodide-wheels.mjs
//
// The `pyodide` devDependency MUST match PYODIDE_VERSION in src/worker/pyodide.worker.ts.

import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { loadPyodide, version as pyodideVersion } from 'pyodide'

const HERE = dirname(fileURLToPath(import.meta.url))
const INSTALL_PY = resolve(HERE, '../src/python/install.py')
const WORKER_TS = resolve(HERE, '../src/worker/pyodide.worker.ts')

const py = readFileSync(INSTALL_PY, 'utf8')

// --- Guard: this Pyodide must match the one the worker loads from the CDN. ---
const workerVersion = /PYODIDE_VERSION\s*=\s*"v?([\d.]+)"/.exec(readFileSync(WORKER_TS, 'utf8'))?.[1]
if (workerVersion && workerVersion !== pyodideVersion) {
  console.error(
    `✖ pyodide npm (${pyodideVersion}) != worker PYODIDE_VERSION (v${workerVersion}). `
    + `Install matching: pnpm add -D pyodide@${workerVersion}`,
  )
  process.exit(1)
}

// --- Extract REQUIREMENTS and the mock block straight from install.py (single source). ---
const reqMatch = /REQUIREMENTS\s*=\s*\[([\s\S]*?)\]/.exec(py)
if (!reqMatch)
  throw new Error('Could not find REQUIREMENTS = [...] in install.py')
const requirements = [...reqMatch[1].matchAll(/"([^"]+)"/g)].map(m => m[1])

const mockMatch = /# === MOCKS START[^\n]*\n([\s\S]*?)\n# === MOCKS END ===/.exec(py)
if (!mockMatch)
  throw new Error('Could not find MOCKS START/END markers in install.py')
const mockBlock = mockMatch[1]

console.error(`[gen] pyodide ${pyodideVersion}; resolving ${requirements.length} requirements…`)
const pyodide = await loadPyodide()
pyodide.setStdout({ batched: () => {} })
pyodide.setStderr({ batched: t => console.error('[py]', t) })
// Same built-in roots the worker preloads, so resolution mirrors runtime exactly.
await pyodide.loadPackage(['micropip', 'numpy', 'requests', 'svgwrite', 'typing-extensions', 'pydantic'])

pyodide.globals.set('_reqs', pyodide.toPy(requirements))
await pyodide.runPythonAsync(`import micropip\n${mockBlock}`)
await pyodide.runPythonAsync('await micropip.install(list(_reqs), keep_going=True)')
const lockJson = await pyodide.runPythonAsync('micropip.freeze()')

const packages = Object.values(JSON.parse(lockJson).packages)
const wheelUrls = packages
  .map(p => p.file_name)
  .filter(f => typeof f === 'string' && f.startsWith('http'))
  .sort()

// Report the built-in roots the wheels depend on, so the worker's loadPackage list can
// be kept in sync by hand (it must, since deps=False won't pull them).
const MOCKS = new Set(['cadquery-ocp-novtk', 'ezdxf', 'ipython', 'lib3mf', 'scikit-learn', 'scipy', 'sympy'])
const byName = Object.fromEntries(packages.map(p => [p.name.toLowerCase(), p]))
const builtinRoots = new Set()
for (const p of packages) {
  if (!String(p.file_name).startsWith('http'))
    continue
  for (const d of p.depends ?? []) {
    const dep = byName[d.toLowerCase()]
    if (!MOCKS.has(d.toLowerCase()) && dep && !String(dep.file_name).startsWith('http')) {
      builtinRoots.add(dep.name)
    }
  }
}

const block = wheelUrls.map(u => `  "${u}",`).join('\n')
const updated = py.replace(
  // eslint-disable-next-line regexp/no-super-linear-backtracking
  /(# === BEGIN GENERATED WHEEL URLS ===\n)[\s\S]*?(\n\s*# === END GENERATED WHEEL URLS ===)/,
  `$1${block}$2`,
)
if (updated === py && !py.includes(block)) {
  throw new Error('Failed to substitute the generated block — markers missing?')
}
writeFileSync(INSTALL_PY, updated)

console.error(`\n[gen] wrote ${wheelUrls.length} wheel URLs to src/python/install.py`)
console.error(`[gen] built-in roots these wheels need (verify worker loadPackage list): ${[...builtinRoots].sort().join(', ')}`)
