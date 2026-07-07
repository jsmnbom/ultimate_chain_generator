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
from ocp_tessellate.ocp_utils import downcast, make_compound
from ocp_tessellate.tessellator import get_edges, get_faces, get_vertices
from ocp_tessellate.utils import numpy_to_json
from pydantic import ValidationError

# ``get_distance`` / ``get_properties`` come from measure.py, exec'd into globals
# at boot just like chain.py's ``Parameters`` / ``build`` (see the worker's
# initialize()). Referenced as injected globals for the same reason.

# --------------------------------------------------------------------------- #
# Helpers called by the worker (params cross the boundary as JSON strings)
# --------------------------------------------------------------------------- #

_LAST_BUILT = {"obj": None}

# Measurement-tool backend state, refreshed on every ``show``:
#   solids: tessellated leaf id -> (base_shape, location). The id is the same one
#           three-cad-viewer emits when a shape is picked (e.g.
#           "/chain/chain_link(2)"); base_shape is the deduplicated instance
#           geometry, positioned by location.
#   cache:  leaf id -> {faces/edges/vertices: [...]} decomposition, built lazily
#           the first time a sub-shape of that solid is measured.
#   tool:   the active viewer tool ("DistanceMeasurement"/"PropertiesMeasurement"
#           /None), tracked across selection messages. Persists across rebuilds —
#           the frontend only re-sends it on tool toggles, not on geometry change.
_MEASURE = {"solids": {}, "cache": {}, "tool": None}


def get_schema_json() -> str:
  """The JSON Schema that drives the form."""
  return json.dumps(Parameters.model_json_schema())  # type: ignore[no-untyped-call] (from chain.py)


def get_presets_json() -> str:
  """Curated starting-point presets for the form's preset picker, or ``[]`` when
  the loaded module defines none. See chain.py's ``PRESETS``."""
  return json.dumps(globals().get("PRESETS", []))


def _validation_errors(exc: ValidationError):
  return [
    {"loc": [str(p) for p in e["loc"]], "msg": e["msg"], "type": e["type"]}
    for e in exc.errors()
  ]


def _flatten_edges(shape) -> None:
  """Flatten a shape's ``edges`` to a flat ``[x, y, z, …]`` buffer, in place.

  three-cad-viewer's explode / measure code path (``ShapeRenderer._decompose``)
  requires ``edges`` as a flat array whenever ``segments_per_edge`` is present,
  but ocp-tessellate emits them nested as ``[[x, y, z], …]``. The normal render
  path accepts either form, which is why plain viewing works but toggling a
  measure tool throws "Expected Float32Array for edges in binary format".
  Idempotent: a flat (1-D) edges array is left untouched."""
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
  instances, shapes, mapping, *_ = tessellate_group(group, instances, progress=progress)
  _inline_instances(instances, shapes)
  _index_for_measure(mapping)
  builtins.send_data_to_js(numpy_to_json(shapes), "DATA")  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Measurement backend (the Distance / Properties tools in three-cad-viewer)
# --------------------------------------------------------------------------- #
#
# The tools are backend-driven: on selection the viewer emits the picked shape
# ids and waits for real BREP measurements to display. We answer here, in the
# same worker that built the geometry, mirroring ocp_vscode's ViewerBackend but
# without any serialize / websocket round-trip — we resolve ids straight to the
# in-memory OCP topology via the tessellation ``mapping`` (its leaf ids are
# exactly the ids the viewer picks by; face/edge/vertex ordering matches because
# both the tessellator and get_faces/edges/vertices walk the same OCP topology).

_SUBSHAPE_SEPS = {"/faces/": "faces", "/edges/": "edges", "/vertices/": "vertices"}


def _index_for_measure(mapping) -> None:
  """Index the tessellation ``mapping`` (the id/shape/loc tree parallel to the
  shapes tree) by leaf id, so a picked shape id resolves back to OCP topology.
  Rebuilds ``_MEASURE['solids']`` and drops the decomposition cache; leaves the
  active tool untouched."""
  solids = {}

  def walk(node):
    if "parts" in node:
      for part in node["parts"]:
        walk(part)
      return
    shape = node["shape"]
    if isinstance(shape, dict):  # solid / shell / face instance -> {"obj": TopoDS}
      base = shape["obj"]
    elif isinstance(shape, list):  # edge / vertex leaf -> list of TopoDS
      base = make_compound(shape) if len(shape) > 1 else shape[0]
    else:
      base = shape
    solids[node["id"]] = (base, node["loc"])

  walk(mapping)
  _MEASURE["solids"] = solids
  _MEASURE["cache"] = {}


def _resolve_id(shape_id: str):
  """Split a picked shape id into ``(solid_id, kind, index)``. A bare solid id
  like ``/chain/chain_link`` gives ``(id, None, None)``; a sub-shape id like
  ``.../faces/faces_3`` gives ``(".../chain_link", "faces", 3)``."""
  for sep, kind in _SUBSHAPE_SEPS.items():
    if sep in shape_id:
      solid_id, sub = shape_id.rsplit(sep, 1)
      return solid_id, kind, int(sub.rsplit("_", 1)[1])
  return shape_id, None, None


def _decompose(solid_id: str, base, loc):
  """Split ``base`` into its faces / edges / vertices positioned by ``loc``, and
  memoize per solid. Ordering matches the ids the viewer picks by (see above)."""
  cached = _MEASURE["cache"].get(solid_id)
  if cached is None:

    def place(sub):
      return downcast(sub if loc is None else sub.Moved(loc))

    cached = {
      "faces": [place(f) for f in get_faces(base)],
      "edges": [place(e) for e in get_edges(base)],
      "vertices": [place(v) for v in get_vertices(base)],
    }
    _MEASURE["cache"][solid_id] = cached
  return cached


def _measure_shape(shape_id: str):
  """Resolve a picked shape id to its world-positioned OCP topology, or ``None``
  if unknown (e.g. an id from stale geometry)."""
  solid_id, kind, index = _resolve_id(shape_id)
  entry = _MEASURE["solids"].get(solid_id)
  if entry is None:
    return None
  base, loc = entry
  if kind is None or index is None:
    return base if loc is None else base.Moved(loc)
  parts = _decompose(solid_id, base, loc)[kind]
  return parts[index] if 0 <= index < len(parts) else None


def handle_measure(changes_json: str) -> str:
  """Answer a viewer measure-tool notification.

  ``changes`` mirrors three-cad-viewer's change payload, unwrapped to raw new
  values on the JS side: an optional ``activeTool`` string and/or a
  ``selectedShapeIDs`` list whose trailing element is the center/min flag. Returns
  a JSON ``backend_response`` for the viewer's ``handleBackendResponse``, or ``""``
  when there is nothing to answer (wrong tool, too few shapes, unknown ids)."""
  changes = json.loads(changes_json)

  if "activeTool" in changes:
    tool = changes["activeTool"]
    _MEASURE["tool"] = None if tool in (None, "None") else tool

  if "selectedShapeIDs" not in changes:
    return ""

  tool = _MEASURE["tool"]
  selected = changes["selectedShapeIDs"]

  if tool == "DistanceMeasurement" and len(selected) == 3:
    shape1 = _measure_shape(selected[0])
    shape2 = _measure_shape(selected[1])
    if shape1 is None or shape2 is None:
      return ""
    response = get_distance(shape1, shape2, bool(selected[2]))  # type: ignore[reportUndefinedVariable] (measure.py)
    response["tool_type"] = "DistanceMeasurement"

  elif tool == "PropertiesMeasurement" and len(selected) == 2:
    shape = _measure_shape(selected[0])
    if shape is None:
      return ""
    response = get_properties(shape)  # type: ignore[reportUndefinedVariable] (from measure.py)
    response["tool_type"] = "PropertiesMeasurement"

  else:
    return ""

  response["type"] = "backend_response"
  response["subtype"] = "tool_response"
  return json.dumps(response)


def build_and_show(params_json: str) -> str:
  """Validate + build + tessellate. On success the shapes are posted via the
  bridge (as a side effect of show), the printability report is computed, and
  ``{"ok": true, "report": {...}}`` is returned. On failure a structured error
  list is returned for inline display on the form."""
  data = json.loads(params_json)
  try:
    params = Parameters(**data)  # type: ignore[no-untyped-call] (from chain.py)
  except ValidationError as exc:
    return json.dumps({"ok": False, "errors": _validation_errors(exc)})

  try:
    obj = build(params)  # type: ignore[no-untyped-call] (from chain.py)
  except Exception as exc:  # geometry error -> surface as a form-level message
    return json.dumps(
      {"ok": False, "errors": [{"loc": [], "msg": str(exc), "type": "build_error"}]}
    )

  _LAST_BUILT["obj"] = obj
  show(obj, progress=None)

  # Printability report — never let an analysis failure break a successful build.
  try:
    report = analyze(params, obj)  # type: ignore[no-untyped-call] (from chain.py)
  except Exception as exc:
    report = {
      "overall_status": "error",
      "summary": f"Printability analysis failed: {exc}",
      "sections": [],
    }
  print(f"build_and_show: {report['overall_status']} — {report['summary']}")
  return json.dumps({"ok": True, "report": report})


def export_bytes(params_json: str, fmt: str):
  """Rebuild from ``params_json`` and return the exported file as ``bytes``.
  Rebuilding (rather than reusing the last shown object) keeps exports in sync
  with the current form even if the last render was for different params."""
  data = json.loads(params_json)
  params = Parameters(**data)  # type: ignore[no-untyped-call] (from chain.py)
  obj = build(params)  # type: ignore[no-untyped-call] (from chain.py)

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
