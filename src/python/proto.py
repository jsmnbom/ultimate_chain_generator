"""The design-authoring SDK: the seam a parametric design plugs into.

This module is the stable framework side of the contract (it is written to the
Pyodide FS as an *importable* module, and sits next to a ``design.py`` on
``sys.path`` natively). A design — a bundled ``design.py`` or a Code-tab module —
imports from here and exposes exactly one ``Design`` subclass. Nothing
design-specific lives here.

The contract, in one place:

* ``class MyDesign(Design[MyParams])`` — ``MyParams`` is a pydantic ``BaseModel``
  whose JSON schema drives the form. Instantiating ``MyDesign(params)`` *builds*
  the geometry into ``self`` (a build123d ``Compound``), ready to tessellate /
  export.
* ``MyDesign.analyze(self) -> Report`` — optional; returns the printability report.
* ``MyDesign.PRESETS: list[dict]`` — optional; curated starting points.

Form-hint helpers (``slider_field`` / ``choice_field`` / ``select_field``) attach
widget metadata to each pydantic ``Field`` via ``json_schema_extra``; each stamps a
``widget`` discriminator (``"slider"`` / ``"shape"`` / ``"select"``) the frontend
form switches on (see ``src/components/ParamForm.vue``).
"""

from __future__ import annotations
import inspect
import io
import re
from typing import (
  TYPE_CHECKING,
  Any,
  Callable,
  ClassVar,
  Generic,
  Iterator,
  Literal,
  TypeVar,
  cast,
  get_args,
  get_origin,
)

from build123d import Compound, ExportSVG, Wire
from ocp_tessellate.ocp_utils import dist_shapes
from pydantic import BaseModel, Field, ValidationError, model_validator

__all__ = [
  "Choice",
  "outline_svg",
  "slider_field",
  "choice_field",
  "select_field",
  "Status",
  "Report",
  "check_degenerate",
  "check_bed_contact",
  "check_interlock",
  "check_floating",
  "Design",
  "load_design",
  "BaseModel",
  "Field",
  "ValidationError",
  "model_validator",
]

T = TypeVar("T")
C = TypeVar("C", bound="Choice[Any]")
P = TypeVar("P", bound=BaseModel)


class ChoiceMeta(type):
  _members_: dict[str, Any]

  def __new__(mcls, name, bases, ns, **kw):
    cls = super().__new__(mcls, name, bases, ns, **kw)
    cls._members_ = {}
    for key, val in list(ns.items()):
      if key.startswith("_") or not isinstance(val, staticmethod):
        continue
      fn = val.__func__
      member = object.__new__(cls)
      doc = inspect.getdoc(fn) or ""
      first, _, rest = doc.partition("\n")
      object.__setattr__(member, "_impl", fn)
      object.__setattr__(member, "name", key)
      object.__setattr__(member, "value", key)
      object.__setattr__(member, "label", first.strip() or key)
      object.__setattr__(member, "description", rest.strip() or None)
      setattr(cls, key, member)
      cls._members_[key] = member
    return cls

  def __iter__(cls: type[C]) -> Iterator[C]:  # pyright: ignore[reportGeneralTypeIssues]
    return iter(cls._members_.values())

  def __len__(cls) -> int:
    return len(cls._members_)

  def __contains__(cls, key: object) -> bool:
    return key in cls._members_


class Choice(Generic[T], metaclass=ChoiceMeta):
  name: str
  value: str
  label: str
  description: str | None
  _impl: T

  if TYPE_CHECKING:
    # To the checker, calling a member has the signature of T
    # (e.g. Callable[[float, float], Wire]).
    __call__: T
  else:

    def __call__(self, *args, **kwargs):
      return self._impl(*args, **kwargs)

  def __repr__(self) -> str:
    return f"<{type(self).__name__}.{getattr(self, 'name', '?')}>"

  @classmethod
  def __get_pydantic_core_schema__(cls, source, handler):
    from pydantic_core import core_schema

    def validate(v):
      if isinstance(v, cls):
        return v
      try:
        return cls._members_[v]
      except KeyError:
        raise ValueError(f"{v!r} is not a valid {cls.__name__}")

    return core_schema.no_info_plain_validator_function(
      validate,
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda m: m.value, return_schema=core_schema.str_schema()
      ),
    )

  @classmethod
  def __get_pydantic_json_schema__(cls, schema, handler):
    out = {
      "type": "string",
      "enum": [m.value for m in cls._members_.values()],
      "options": [
        {
          "value": m.value,
          "label": m.label,
          **({"description": m.description} if m.description else {}),
          **({"svg": m.svg} if getattr(m, "svg", None) else {}),
        }
        for m in cls._members_.values()
      ],
    }
    return out


def outline_svg(wire: Wire) -> dict:
  """Export a 2D outline wire to a minimal SVG, captured as ``{viewBox, paths}``
  (CAD coords; the frontend flips Y to match SVG's orientation). The frontend
  renders these directly, so previews come straight from the real geometry and
  can never drift from what ``build`` produces.

  ExportSVG pulls in ezdxf only for colour handling; the Pyodide worker mocks
  ezdxf but gives ``ezdxf.colors`` a real ``RGB``/``aci2rgb`` so this path works
  there too (see ``install.py``)."""
  exporter = ExportSVG()
  exporter.add_shape(wire)
  bio = io.BytesIO()
  exporter.write(bio)
  svg = bio.getvalue().decode()
  view_box = re.search(r'viewBox="([^"]*)"', svg)
  return {
    "viewBox": view_box.group(1) if view_box else "",
    "paths": re.findall(r'\sd="([^"]*)"', svg),
  }


# --------------------------------------------------------------------------- #
# Form-hint helpers — attach widget metadata to a pydantic Field.
# --------------------------------------------------------------------------- #
#
# Each returns a dict passed as ``Field(json_schema_extra=...)``. The ``widget``
# key is the discriminator the form switches on; add a new widget kind by adding
# a helper here and a matching branch in ParamForm.vue. Common optional keys:
# ``label``, ``description``, ``unit``, ``size`` (Nuxt UI token), ``show_if``
# (conditional visibility), ``slider_max_by`` (dynamic slider max by another
# field's value).


def slider_field(
  label: str,
  slider_min: float,
  slider_max: float,
  *,
  step: float,
  unit: str | None = None,
  description: str | None = None,
  **kwargs: Any,
) -> dict:
  """A numeric slider + number input. ``slider_min``/``slider_max`` are the
  comfortable range; the pydantic ``ge``/``le`` bounds remain the hard limits."""
  return {
    "widget": "slider",
    "label": label,
    "sliderMin": slider_min,
    "sliderMax": slider_max,
    "step": step,
    "unit": unit,
    "description": description,
    **kwargs,
  }


def choice_field(
  choices: type[Choice[Any]],
  label: str,
  *,
  preview: Callable[[Choice[Any]], Any],
  **kwargs: Any,
) -> dict:
  """A picker over a ``Choice`` type, each option carrying a geometry-derived SVG
  preview (``preview(member)`` returns a ``Wire`` to render)."""
  return {
    "widget": "shape",
    "label": label,
    "options": [
      {
        "value": m.value,
        "label": m.label,
        **({"description": m.description} if m.description else {}),
        "svg": outline_svg(preview(m)),
      }
      for m in choices
    ],
    **kwargs,
  }


def select_field(label: str, options: list[dict], **kwargs: Any) -> dict:
  """A plain dropdown over ``options`` (``[{value, label, description?}, ...]``) —
  for ``Literal``/enum fields with no geometry preview (e.g. ``brim``)."""
  return {
    "widget": "select",
    "label": label,
    "options": options,
    **kwargs,
  }


# --------------------------------------------------------------------------- #
# Report — a flat list of printability findings.
# --------------------------------------------------------------------------- #
#
# Canonical definition of the report shape; ``protocol.ts``'s
# ``PrintabilityReport`` mirrors ``to_dict()``. Build one imperatively while
# walking the geometry; ``overall_status`` / ``summary`` roll up automatically.

Status = Literal["ok", "warning", "error"]

_STATUS_RANK: dict[str, int] = {"ok": 0, "warning": 1, "error": 2}
_DEFAULT_SUMMARY: dict[str, str] = {
  "ok": "Looks printable.",
  "warning": "Printable, but check the flagged tolerances before printing.",
  "error": "Not printable as-is — resolve the errors below.",
}


class Report:
  """A printability report: a flat list of findings plus an auto-derived overall
  status and summary. Pass ``summary`` to override the default one-liner; pass
  ``status`` to force the overall (used by ``Report.error``)."""

  def __init__(self, summary: str | None = None, status: Status | None = None):
    self._items: list[dict] = []
    self._summary = summary
    self._status = status

  def add(
    self,
    label: str,
    value: float,
    *,
    unit: str | None = None,
    detail: str | None = None,
    status: Status | None = None,
  ) -> "Report":
    """Append one finding (a labelled value with optional unit/detail/status).
    Returns ``self`` so calls can chain."""
    item: dict = {"label": label, "value": value}
    if unit is not None:
      item["unit"] = unit
    if detail is not None:
      item["detail"] = detail
    if status is not None:
      item["status"] = status
    self._items.append(item)
    return self

  @property
  def overall_status(self) -> Status:
    if self._status is not None:
      return cast(Status, self._status)
    worst: Status = "ok"
    for item in self._items:
      s = item.get("status")
      if s and _STATUS_RANK[s] > _STATUS_RANK[worst]:
        worst = s
    return worst

  @property
  def summary(self) -> str:
    return self._summary if self._summary is not None else _DEFAULT_SUMMARY[self.overall_status]

  def to_dict(self) -> dict:
    return {
      "overall_status": self.overall_status,
      "summary": self.summary,
      "items": list(self._items),
    }

  @classmethod
  def error(cls, msg: str) -> "Report":
    """A report that reports only an error (e.g. an analysis that itself failed)."""
    return cls(summary=msg, status="error")


# --------------------------------------------------------------------------- #
# Printability helpers — generic finding-builders any model can reuse.
# --------------------------------------------------------------------------- #
#
# These add a finding to a Report given raw geometry, encapsulating the common
# FDM printability knowledge (bed-adhesion by contact area, part fusion vs.
# clearance, floating islands) so a design's ``analyze`` only has to pick *which*
# geometry to feed in. Thresholds/labels default to sensible values and are
# overridable per call. Nothing here is model-specific.

# Per-part effective contact footprint (mm²), ordered high -> low.
# band -> (min_area_mm2, item_status); below the smallest min -> _IMPOSSIBLE.
DEFAULT_CONTACT_BANDS: dict[str, tuple[float, Status]] = {
  "easy": (40.0, "ok"),
  "medium": (20.0, "ok"),
  "hard": (10.0, "warning"),
  "expert": (5.0, "warning"),
}
_IMPOSSIBLE: tuple[str, Status] = ("impossible", "error")  # below smallest band

_CONTACT_DETAIL: dict[str, str] = {
  "easy": "Plenty of bed contact.",
  "medium": "Should adhere on most beds.",
  "hard": "Small patch; adhesion may be marginal.",
  "expert": "Very little contact; likely to lift.",
  "impossible": "Too little contact to adhere.",
}
_MARGINAL_BANDS = frozenset({"hard", "expert", "impossible"})

_CLEARANCE_WARNING = 0.2  # mm, gap below which separate parts may still fuse
_OVERLAP_TOL = 1e-6  # mm, min distance below which parts are treated as touching
# Interpenetration volume (mm³) at/above which parts are clearly fused (error);
# any smaller overlap still interpenetrates but is flagged as a warning.
_OVERLAP_ERROR_MM3 = 5.0

_FLOATING_TOL = 1e-3  # mm, height above the bed plane a solid may sit and still count
_MIN_SOLID_VOLUME = 1e-6  # mm³, below which a solid is a degenerate sliver


def check_degenerate(
  report: Report,
  shape: Compound,
  *,
  label: str = "Geometry",
  min_volume: float = _MIN_SOLID_VOLUME,
) -> bool:
  """Guard against degenerate build output before other checks run: an empty build
  (no solids), zero/near-zero-volume slivers, or an invalid/non-manifold BREP. Value =
  count of degenerate solids (0 -> ok). Returns ``True`` when the geometry is sound, so
  a caller can skip measurements that would be meaningless on broken geometry."""
  solids = shape.solids()
  if not solids:
    report.add(
      label, 0, detail="No solid geometry was produced — the build is empty.",
      status="error",
    )
    return False
  degenerate = 0
  for s in solids:
    try:
      ok = s.is_valid and s.volume >= min_volume
    except Exception:
      ok = False
    if not ok:
      degenerate += 1
  if degenerate:
    report.add(
      label, degenerate,
      detail="Some solids are empty, slivered, or non-manifold — the geometry is "
      "invalid and won't slice.",
      status="error",
    )
    return False
  report.add(label, len(solids), detail="All solids are well-formed.", status="ok")
  return True


def _classify_contact(
  area: float, bands: dict[str, tuple[float, Status]]
) -> tuple[str, Status]:
  """Map a contact footprint area (mm²) to a (difficulty band, status)."""
  for band, (min_area, status) in bands.items():
    if area >= min_area:
      return band, status
  return _IMPOSSIBLE


def check_bed_contact(
  report: Report,
  area: float,
  *,
  label: str = "Bed contact",
  bands: dict[str, tuple[float, Status]] = DEFAULT_CONTACT_BANDS,
  suggestion: str | None = None,
) -> Status:
  """Classify a bed-contact footprint ``area`` (mm²) into a difficulty band and add
  the finding. ``suggestion`` (if given) is appended to the detail on marginal/failed
  bands. Returns the band's status so the caller can branch."""
  band, status = _classify_contact(area, bands)
  detail = f"{band.capitalize()} — {_CONTACT_DETAIL[band]}"
  if suggestion and band in _MARGINAL_BANDS:
    detail += f" {suggestion}"
  report.add(label, round(area, 1), unit="mm²", detail=detail, status=status)
  return status


def check_interlock(
  report: Report,
  a: Compound,
  b: Compound,
  *,
  overlap_label: str = "Parts overlap",
  clearance_label: str = "Clearance",
) -> None:
  """Measure the gap between two parts and add an interlock finding: an overlap
  finding (value = interpenetration volume) when they touch/interpenetrate, else a
  clearance finding (value = gap). Encapsulates the fuse/gap tolerances."""
  dist, _p1, _p2 = dist_shapes(a.wrapped, b.wrapped)
  if dist <= _OVERLAP_TOL:
    overlap_vol = (a & b).volume
    if overlap_vol >= _OVERLAP_ERROR_MM3:
      detail = "Parts fuse into one solid. Thin them, add sides, or enlarge them."
      status: Status = "error"
    else:
      detail = "Parts touch with no clearance — may fuse. Thin them slightly."
      status = "warning"
    report.add(
      overlap_label, round(overlap_vol, 2), unit="mm³", detail=detail, status=status
    )
  else:
    status = "warning" if dist < _CLEARANCE_WARNING else "ok"
    detail = (
      "Tight gap — parts may fuse."
      if status == "warning"
      else "Healthy gap; parts stay separate."
    )
    report.add(clearance_label, round(dist, 3), unit="mm", detail=detail, status=status)


def check_floating(
  report: Report,
  shape: Compound,
  *,
  label: str = "Floating sections",
  tol: float = _FLOATING_TOL,
) -> None:
  """Flag solids whose lowest point sits above the design's global bed plane (nothing
  anchoring them to the print bed). Value = count of floating solids; ``ok`` when none."""
  solids = shape.solids()
  if not solids:
    return
  bottoms = [s.bounding_box().min.Z for s in solids]
  z0 = min(bottoms)
  floating = sum(1 for z in bottoms if z > z0 + tol)
  detail = (
    "All sections reach the bed."
    if floating == 0
    else "Sections float above the bed — they need support or a connection."
  )
  report.add(
    label, floating, detail=detail, status="ok" if floating == 0 else "error"
  )


# --------------------------------------------------------------------------- #
# Design — the design seam.
# --------------------------------------------------------------------------- #


class Design(Compound, Generic[P]):
  """Base for a parametric design. A subclass binds its pydantic params type via
  ``Design[MyParams]``; instantiating it with a validated params instance
  *builds* the geometry into ``self`` (a ``Compound``). Override ``analyze`` for a
  printability report; set ``PRESETS`` for curated starting points.

  The subclass ``__init__(self, params)`` should store ``self.params = params``,
  build, then call ``super().__init__(...)`` with the resulting children — see
  the ``chain`` design."""

  # The pydantic params class, bound automatically from ``Design[MyParams]`` so
  # the form's JSON schema is available before any geometry is built.
  Parameters: ClassVar[type[BaseModel]]
  PRESETS: ClassVar[list[dict]] = []
  def __init_subclass__(cls, **kwargs: Any) -> None:
    super().__init_subclass__(**kwargs)
    for base in getattr(cls, "__orig_bases__", ()):
      origin = get_origin(base)
      if isinstance(origin, type) and issubclass(origin, Design):
        args = get_args(base)
        if args and isinstance(args[0], type):
          cls.Parameters = args[0]

  def analyze(self) -> Report:
    """Printability report for the built model. Default: an empty report."""
    return Report()


def load_design(namespace: dict) -> type[Design]:
  """Find the single ``Design`` subclass in an exec'd module's namespace.

  This is the runtime's binding point (and the Code-tab entry): a design module is
  exec'd, then its one ``Design`` subclass is located here. Raises ``ValueError``
  with a clear message if none — or more than one — is present."""
  found: list[type[Design]] = []
  for value in namespace.values():
    if (
      isinstance(value, type)
      and value is not Design
      and issubclass(value, Design)
      and getattr(value, "Parameters", None) is not None
      and value not in found
    ):
      found.append(value)
  if not found:
    raise ValueError(
      "No Design subclass found — define `class MyModel(Design[MyParams])`."
    )
  if len(found) > 1:
    names = ", ".join(c.__name__ for c in found)
    raise ValueError(f"Expected exactly one Design subclass, found: {names}.")
  return found[0]
