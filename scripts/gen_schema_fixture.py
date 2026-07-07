"""Regenerate the static fixtures used by the UI mock worker.

The mock worker (``src/composables/useMockChainWorker.ts``) lets you prototype
the UI without booting Pyodide/OCP. It needs the same data the real worker emits
at runtime, so we snapshot the model's ``Parameters.model_json_schema()`` into
``src/fixtures/schema.json`` and its ``PRESETS`` into ``src/fixtures/presets.json``.
Both go through ``proto.load_model`` exactly as ``runtime.py`` does.

Run this whenever ``src/python/chain.py``'s ``Parameters`` or ``PRESETS`` change:

    uv run python scripts/gen_schema_fixture.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "python"))

import chain  # type: ignore[reportMissingImports]  (path set up above)
from proto import load_model  # type: ignore[reportMissingImports]

Model = load_model(vars(chain)) # type: ignore[reportGeneralTypeIssues]

FIXTURES = ROOT / "src" / "fixtures"


def _write(name: str, data: object) -> None:
  out = FIXTURES / name
  out.write_text(json.dumps(data, indent=2) + "\n")
  print(f"wrote {out.relative_to(ROOT)}")


def main() -> None:
  FIXTURES.mkdir(parents=True, exist_ok=True)
  _write("schema.json", Model.Parameters.model_json_schema())
  _write("presets.json", Model.PRESETS)


if __name__ == "__main__":
  main()
