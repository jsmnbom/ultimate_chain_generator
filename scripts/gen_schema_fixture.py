"""Regenerate the static fixtures used by the UI mock worker.

The mock worker (``src/composables/useMockChainWorker.ts``) lets you prototype
the UI without booting Pyodide/OCP. It needs the same data the real worker emits
at runtime, so we snapshot ``Parameters.model_json_schema()`` into
``src/fixtures/schema.json`` and ``chain.PRESETS`` into
``src/fixtures/presets.json``.

Run this whenever ``src/python/chain.py``'s ``Parameters`` or ``PRESETS`` change:

    uv run python scripts/gen_schema_fixture.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "python"))

from chain import Parameters, PRESETS  # type: ignore[reportMissingImports]  (path set up above)

FIXTURES = ROOT / "src" / "fixtures"


def _write(name: str, data: object) -> None:
  out = FIXTURES / name
  out.write_text(json.dumps(data, indent=2) + "\n")
  print(f"wrote {out.relative_to(ROOT)}")


def main() -> None:
  FIXTURES.mkdir(parents=True, exist_ok=True)
  _write("schema.json", Parameters.model_json_schema())
  _write("presets.json", PRESETS)


if __name__ == "__main__":
  main()
