"""Worker orchestration: tessellate build123d geometry with ocp-tessellate and
post it to the JS viewer, plus schema / build / export helpers for the worker.

Exec'd once at boot, after ``chain.py`` (which defines ``Parameters`` and
``build`` in globals) and after ``install.py``.

``show`` reproduces what ocp-tessellate's ``export_three_cad_viewer_js`` does,
minus the file / ``var name = …`` wrapper: convert to an OcpGroup, tessellate,
inline any shared instance geometry, then post the plain-JSON shapes tree over
the host bridge (``builtins.send_data_to_js``, registered by the worker).
three-cad-viewer's ``render()`` consumes that nested-array form directly, so
there is no decode step on the JS side.
"""

import builtins
import io
import json

import build123d as b3d
from ocp_tessellate.convert import tessellate_group, to_ocpgroup
from ocp_tessellate.utils import numpy_to_json
from pydantic import ValidationError

from proto import Design, Report, load_model

# The one Design subclass the loaded model module defines (chain.py's Chain at
# boot; a Code-tab module after reload_model). All schema/build/export/analyze
# flows go through this handle — the seam, bound in one place instead of reaching
# for loose globals. ``chain.py`` was exec'd into these globals before runtime.py.
Model = load_model(globals())

# --------------------------------------------------------------------------- #
# Helpers called by the worker (params cross the boundary as JSON strings)
# --------------------------------------------------------------------------- #


def get_schema_json() -> str:
  """The JSON Schema that drives the form."""
  return json.dumps(Model.Parameters.model_json_schema())


def get_presets_json() -> str:
  """Curated starting-point presets for the form's preset picker, or ``[]`` when
  the loaded model defines none (see ``Design.PRESETS``)."""
  return json.dumps(Model.PRESETS)


def reload_model(source: str) -> str:
  """Swap in a new model module without rebooting Pyodide: exec ``source`` in a
  fresh namespace, rebind ``Model`` to its ``Design`` subclass, and return the
  fresh ``{"schema", "presets"}`` for the form. Used by dev hot-reload of
  ``chain.py`` and, in the same shape, by the future Code tab (editor contents in
  place of the file). On failure the exception propagates and ``Model`` is left
  untouched (rebind happens only after a successful load)."""
  global Model
  # Exec into this module's own globals (``__main__`` in the worker) so pydantic
  # can resolve the model's forward refs via a registered module namespace — a
  # bare dict would leave ``Parameters`` "not fully defined". First drop any
  # previously-loaded Design subclass so a *renamed* model (Code tab) doesn't
  # collide with its predecessor under load_model's one-model rule.
  g = globals()
  for name in [
    n
    for n, v in list(g.items())
    if isinstance(v, type) and v is not Design and issubclass(v, Design)
  ]:
    del g[name]
  exec(compile(source, "<model>", "exec"), g)
  Model = load_model(g)
  return json.dumps(
    {"schema": Model.Parameters.model_json_schema(), "presets": Model.PRESETS}
  )


def _validation_errors(exc: ValidationError):
  return [
    {"loc": [str(p) for p in e["loc"]], "msg": e["msg"], "type": e["type"]}
    for e in exc.errors()
  ]


def _flatten_edges(shape) -> None:
  """Flatten a shape's ``edges`` to a flat ``[x, y, z, …]`` buffer, in place.

  three-cad-viewer expects ``edges`` as a flat array whenever ``segments_per_edge``
  is present, but ocp-tessellate emits them nested as ``[[x, y, z], …]``. The plain
  render path tolerates either form; the viewer's tools (explode, measurement) read
  the edge buffer directly and require the flat form. Normalizing here keeps both
  paths happy. Idempotent: a flat (1-D) edges array is left untouched."""
  if not isinstance(shape, dict):
    return
  edges = shape.get("edges")
  if shape.get("segments_per_edge") is not None and edges is not None and getattr(edges, "ndim", 1) > 1:
    shape["edges"] = edges.reshape(-1)


def _inline_instances(instances, shapes) -> None:
  """Splice tessellated instance geometry into the shapes tree in place.

  ocp-tessellate dedupes repeated shapes (every link of the chain shares one
  mesh) behind an instance list, leaving ``{"ref": i}`` placeholders in the
  tree. three-cad-viewer has no ref indirection, so each leaf must carry its own
  geometry. Mirrors ocp-tessellate's own private decode. Each resolved shape is
  also normalized (see ``_flatten_edges``) so the measure / explode tools work."""

  def walk(node):
    if node.get("type") == "shapes":
      shape = node.get("shape")
      if isinstance(shape, dict) and shape.get("ref") is not None:
        shape = instances[shape["ref"]]
        node["shape"] = shape
      _flatten_edges(shape)
    for part in node.get("parts") or []:
      walk(part)

  walk(shapes)


def show(obj, progress=None) -> None:
  """Tessellate ``obj`` and post the shapes tree to the JS viewer."""
  group, instances = to_ocpgroup(obj)
  instances, shapes, *_ = tessellate_group(group, instances, progress=progress)
  _inline_instances(instances, shapes)
  builtins.send_data_to_js(numpy_to_json(shapes), "DATA")  # type: ignore[attr-defined]


def build_and_show(params_json: str) -> str:
  """Validate + build + tessellate. On success the shapes are posted via the
  bridge (as a side effect of show), the printability report is computed, and
  ``{"ok": true, "report": {...}}`` is returned. On failure a structured error
  list is returned for inline display on the form."""
  data = json.loads(params_json)
  try:
    params = Model.Parameters(**data)
  except ValidationError as exc:
    return json.dumps({"ok": False, "errors": _validation_errors(exc)})

  try:
    obj = Model(params)  # type: ignore[reportGeneralTypeIssues]
  except Exception as exc:  # geometry error -> surface as a form-level message
    return json.dumps(
      {"ok": False, "errors": [{"loc": [], "msg": str(exc), "type": "build_error"}]}
    )

  show(obj, progress=None)

  # Printability report — never let an analysis failure break a successful build.
  try:
    report = obj.analyze().to_dict()
  except Exception as exc:
    report = Report.error(f"Printability analysis failed: {exc}").to_dict()
  return json.dumps({"ok": True, "report": report})


def export_bytes(params_json: str, fmt: str):
  """Rebuild from ``params_json`` and return the exported file as ``bytes``.
  Rebuilding (rather than reusing the last shown object) keeps exports in sync
  with the current form even if the last render was for different params."""
  data = json.loads(params_json)
  params = Model.Parameters(**data)
  obj = Model(params) # type: ignore[reportGeneralTypeIssues]

  fmt = fmt.upper()
  if fmt == "STEP":
    bio = io.BytesIO()
    b3d.export_step(obj, bio)
    return bio.getvalue()
  if fmt == "3MF":
    # OrcaSlicer project via orca123d. save() writes to a path (it tessellates
    # into a zip of model + settings XML), so round-trip through Pyodide's
    # in-memory FS rather than a BytesIO.
    from orca123d import Project

    proj = Project()
    proj.add_object(obj)  # names itself from the compound's "chain" label
    path = "/tmp/chain.3mf"
    proj.save(path)
    with open(path, "rb") as f:
      return f.read()
  raise ValueError(f"Unknown export format: {fmt}")
