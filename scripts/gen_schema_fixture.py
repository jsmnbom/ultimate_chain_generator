"""Regenerate the static fixtures used by the UI mock worker.

The mock worker (``src/composables/useMockDesignWorker.ts``) lets you prototype
the UI without booting Pyodide/OCP. It needs the same data the real worker emits
at runtime, so we snapshot the default design's ``Parameters.model_json_schema()``
into ``src/fixtures/schema.json`` and its ``PRESETS`` into
``src/fixtures/presets.json``. Both go through ``proto.load_design`` exactly as
``runtime.py`` does.

Run this whenever the default design's ``Parameters`` or ``PRESETS`` change:

    uv run python scripts/gen_schema_fixture.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "python"))

# The mock worker seeds itself with the *default* design's schema (see
# branding.defaultDesign). Import it from src/designs/<slug>/design.py with proto
# on sys.path. Importing by name registers it in sys.modules so pydantic can
# resolve the design's forward refs (Parameters' `ChainLinkOutline` etc.).
DEFAULT_DESIGN = "chain"
sys.path.insert(0, str(ROOT / "src" / "designs" / DEFAULT_DESIGN))

import design  # type: ignore[reportMissingImports]  (path set up above)
from proto import load_design  # type: ignore[reportMissingImports]

Design = load_design(vars(design)) # type: ignore[reportGeneralTypeIssues]

FIXTURES = ROOT / "src" / "fixtures"


def _write(name: str, data: object) -> None:
  out = FIXTURES / name
  out.write_text(json.dumps(data, indent=2) + "\n")
  print(f"wrote {out.relative_to(ROOT)}")


def main() -> None:
  FIXTURES.mkdir(parents=True, exist_ok=True)
  _write("schema.json", Design.Parameters.model_json_schema())
  _write("presets.json", Design.PRESETS)


if __name__ == "__main__":
  main()
