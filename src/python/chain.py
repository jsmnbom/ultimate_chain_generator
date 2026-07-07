"""Static Python asset: the ``Parameters`` / ``build`` contract.

This module is the single source of truth for both the form (via
``Parameters.model_json_schema()``) and the geometry (via ``build``). It is
loaded verbatim into the Pyodide worker; nothing here is browser-specific, so it
can also be imported and exercised natively (see ``uv run python -m ...``).

The future Code tab plugs in at exactly this seam: it will provide ``Parameters``
and ``build`` from user-authored source instead of this file, with no change to
the schema-generation, build, or export pipelines.
"""

from __future__ import annotations

import math
from typing import (
  Callable,
  Literal,
  cast, 
)

from build123d import *  # pyright: ignore[reportWildcardImportFromLibrary]
from ocp_tessellate.ocp_utils import dist_shapes
from pydantic import BaseModel, Field, model_validator

from proto import Choice, wire_choice_field_extra, slider_field_extra

__all__ = [
  "Parameters",
  "build",
  "analyze",
  "PRESETS",
]


# --------------------------------------------------------------------------- #
# Parameters — the form/validation source of truth
# --------------------------------------------------------------------------- #


ChainLinkOutlineBuilder = Callable[[float, float], "Wire"]


class ChainLinkOutline(Choice[ChainLinkOutlineBuilder]):
  """Link centerline outlines. Each builds a closed ``Wire`` from the half-extents
  ``(cx, cy)`` — used both as the sweep path and, at icon size, the form preview.
  Returns a ``Wire`` (not a raw BuildLine ``Curve``); ExportSVG IndexErrors on a
  straight-line ``Curve``."""

  @staticmethod
  def rect(cx: float, cy: float):
    """Rectangle

    Sharp 90° corners."""
    with BuildLine() as bl:
      Polyline((cx, cy), (-cx, cy), (-cx, -cy), (cx, -cy), close=True)
    return bl.wire()

  @staticmethod
  def chamfered(cx: float, cy: float) -> Wire:
    """Chamfered rect

    Corners cut flat at 45° — a sturdy default."""
    cl = min(cx, cy) * 0.5  # cut-back distance per corner
    with BuildLine() as bl:
      Polyline(
        (cx, cy - cl),
        (cx - cl, cy),
        (-cx + cl, cy),
        (-cx, cy - cl),
        (-cx, -cy + cl),
        (-cx + cl, -cy),
        (cx - cl, -cy),
        (cx, -cy + cl),
        close=True,
      )
    return bl.wire()

  @staticmethod
  def rounded(cx: float, cy: float) -> Wire:
    """Rounded rect

    Smoothly filleted corners."""
    with BuildLine() as bl:
      FilletPolyline(
        (cx, cy), (-cx, cy), (-cx, -cy), (cx, -cy), radius=min(cx, cy) * 0.5, close=True
      )
    return bl.wire()


ChainLinkCrossSectionBuilder = Callable[[float], RegularPolygon]


class ChainLinkCrossSection(Choice[ChainLinkCrossSectionBuilder]):
  """Swept cross-sections — regular polygons. Each returns the ``RegularPolygon``
  at circumradius ``radius``: ``.side_count`` gives the side count (which fixes the
  profile's radius correction and the interlock tilt) and ``.wire()`` the preview
  outline."""

  @staticmethod
  def square(radius: float) -> RegularPolygon:
    """Square

    4 sides — chunky, angular links."""
    return RegularPolygon(radius=radius, side_count=4, rotation=90)

  @staticmethod
  def hexagon(radius: float) -> RegularPolygon:
    """Hexagon

    6 sides — a middle ground."""
    return RegularPolygon(radius=radius, side_count=6, rotation=90)

  @staticmethod
  def octagon(radius: float) -> RegularPolygon:
    """Octagon

    8 sides — smooth and reliable, the default."""
    return RegularPolygon(radius=radius, side_count=8, rotation=90)

  @staticmethod
  def decagon(radius: float) -> RegularPolygon:
    """Decagon

    10 sides — rounder; unlocks the tilt multiplier."""
    return RegularPolygon(radius=radius, side_count=10, rotation=90)

  @staticmethod
  def dodecagon(radius: float) -> RegularPolygon:
    """Dodecagon

    12 sides — roundest, with the most tilt range."""
    return RegularPolygon(radius=radius, side_count=12, rotation=90)


def _max_tilt_mult(sides: int) -> int:
  """Largest tilt multiplier whose alternating tilt stays below 90° for a
  ``sides``-gon. The tilt is ``(360/sides) * (tilt_mult - 0.5)``; at 90° the link
  stands vertical and can no longer interlock flat, so this is the last value
  strictly under that."""
  return math.ceil(sides / 4 + 0.5) - 1


# Tilt multiplier is only meaningful with enough faces, so the control is hidden
# below a decagon (see tilt_mult's `show_if`). This maps each *shown* cross-section
# to its max multiplier — the single source of truth for the slider range and the
# normalisation in `Parameters._check_relations`. A hidden field's value stays
# inert (max 1), mirroring how `brim_diameter` is ignored unless `brim == "ears"`.
_TILT_MULT_MAX = {
  "decagon": _max_tilt_mult(10),  # 2
  "dodecagon": _max_tilt_mult(12),  # 3
}


class Parameters(BaseModel):
  """Parameters for a line chain of interlocking links (all lengths in mm)."""

  link_shape: ChainLinkOutline = Field(
    default=cast(ChainLinkOutline, ChainLinkOutline.chamfered),
    json_schema_extra=wire_choice_field_extra(
      ChainLinkOutline,
      "Link shape",
      preview=lambda m: m(2.0, 1.2),  # representative icon size
      size="lg"
    ),
  )
  cross_section: ChainLinkCrossSection = Field(
    default=cast(ChainLinkCrossSection, ChainLinkCrossSection.octagon),
    json_schema_extra=wire_choice_field_extra(
      ChainLinkCrossSection,
      "Cross-section",
      preview=lambda m: m(1.0).wire(),
      size="lg"
    ),
  )
  link_count: int = Field(
    default=6,
    ge=1,
    le=60,
    json_schema_extra=slider_field_extra(
      "Link count", 1, 40, step=1, description="Number of links in the chain."
    ),
  )
  link_length: float = Field(
    default=25.0,
    gt=0,
    le=120.0,
    json_schema_extra=slider_field_extra(
      "Link length", 5, 80, step=0.5,
      description="Long axis of each link. Must be at least the link width.",
    ),
  )
  link_width: float = Field(
    default=13.0,
    gt=0,
    le=60.0,
    json_schema_extra=slider_field_extra(
      "Link width", 3, 40, step=0.5, unit="millimeter",
      description="Short axis of each link. Must be at least the thickness.",
    ),
  )
  link_thickness: float = Field(
    default=3.5,
    gt=0,
    le=20.0,
    json_schema_extra=slider_field_extra(
      "Link thickness", 0.5, 15, step=0.1, unit="millimeter",
      description="Bar diameter of each link — thinner links open a print gap "
      "between neighbours; too thick and they fuse.",
    ),
  )
  tilt_mult: int = Field(
    default=1,
    ge=1,
    le=max(_TILT_MULT_MAX.values()),
    json_schema_extra=slider_field_extra(
      "Tilt multiplier",
      1,
      max(_TILT_MULT_MAX.values()),
      step=1,
      description="How many cross-section faces to skip when tilting each link.",
      # Only shown for cross-sections with enough faces; the slider max then
      # depends on which one is selected (see _TILT_MULT_MAX).
      show_if={"cross_section": list(_TILT_MULT_MAX)},
      slider_max_by={"cross_section": _TILT_MULT_MAX},
      size="xs"
    ),
  )
  brim: Literal["none", "ears"] = Field(
    default="none",
    json_schema_extra={
      "label": "Brim",
      "description": "Adds small discs under each link to widen bed contact and "
      "prevent lifting on hard-to-print settings.",
      "options": [
        {"value": "none", "label": "None", "description": "No brim."},
        {
          "value": "ears",
          "label": "Mouse ears",
          "description": "Thin discs at each link's contact points.",
        },
      ],
    },
  )
  brim_diameter: float = Field(
    default=8.0,
    gt=0,
    le=30.0,
    json_schema_extra=slider_field_extra(
      "Brim diameter", 4, 15, step=0.5, unit="millimeter", show_if={"brim": "ears"},
      size="xs", description="Diameter of each mouse-ear disc.",
    ),
  )

  @model_validator(mode="after")
  def _check_relations(self) -> "Parameters":
    if self.link_width < self.link_thickness:
      raise ValueError("link_width must be >= link_thickness")
    if self.link_length < self.link_width:
      raise ValueError("link_length must be >= link_width")
    # tilt_mult's usable range depends on cross_section (see _TILT_MULT_MAX). The
    # form's slider already caps it, but a value left over from a since-changed
    # cross-section can be stale, so normalise it here — this keeps the guarantee
    # in the model and lets Chain trust its params. Clamped (not rejected) so a
    # hidden field stays inert, mirroring brim_diameter when brim != "ears".
    max_tilt_mult = _TILT_MULT_MAX.get(self.cross_section.value, 1)
    self.tilt_mult = min(self.tilt_mult, max_tilt_mult)
    return self


# --------------------------------------------------------------------------- #
# Presets — curated, manually-verified starting points
# --------------------------------------------------------------------------- #
#
# Optional module-level data the shell offers as a "Preset" picker at the top of
# the form. Each entry is ``{name, description, params}`` where ``params`` is a
# partial (or full) ``Parameters`` dict merged over the schema defaults on the
# frontend, so an entry only needs to spell out the fields it changes. The
# future Code tab can supply its own ``PRESETS`` the same way.

PRESETS: list[dict] = [
  {
    "name": "Default",
    "description": "The stock chain — a balanced starting point.",
    "params": Parameters().model_dump(mode="json"),
  },
  # TODO: replace the two entries below with real, print-verified values.
  {
    "name": "Chunky (placeholder)",
    "description": "TODO: verified — short, thick links.",
    "params": {
      "link_count": 5,
      "link_length": 30.0,
      "link_width": 18.0,
      "link_thickness": 5.0,
      "cross_section": "hexagon",
    },
  },
  {
    "name": "Fine (placeholder)",
    "description": "TODO: verified — many slim links.",
    "params": {
      "link_count": 12,
      "link_length": 18.0,
      "link_width": 9.0,
      "link_thickness": 2.5,
      "cross_section": "dodecagon",
    },
  },
]


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #


class ChainLink(BasePartObject):
  """A single link: a regular-polygon cross-section swept along a named
  centerline outline (a ``ChainLinkOutline``)."""

  _applies_to = [BuildPart._tag]

  def __init__(
    self,
    length: float = 30.0,
    width: float = 12.0,
    thickness: float = 4.0,
    outline: ChainLinkOutlineBuilder = ChainLinkOutline.chamfered,
    cross_section: ChainLinkCrossSectionBuilder = ChainLinkCrossSection.octagon,
    rotation: RotationLike = (0, 0, 0),
    align: Align | tuple[Align, Align, Align] = Align.CENTER,
    mode: Mode = Mode.ADD,
  ):
    if thickness <= 0:
      raise ValueError("thickness must be positive")
    if width < thickness:
      raise ValueError("width must be >= thickness")
    if length < width:
      raise ValueError("length must be >= width")

    cx = length / 2 - thickness / 2  # half-width of centerline outline in X
    cy = width / 2 - thickness / 2  # half-width of centerline outline in Y
    path = outline(cx, cy)  # closed centerline wire for this outline
    radius = thickness / 2

    # Regular-polygon cross-section swept along the path.
    with BuildPart() as link:
      with BuildSketch(Plane(origin=path @ 0, z_dir=path % 0)):
        cs = cross_section(radius)
        self.side_count = cs.side_count
      sweep(path=path, is_frenet=False, transition=Transition.RIGHT)

    assert link.part is not None
    link.part.label = "chain_link"

    super().__init__(part=link.part, rotation=rotation, align=align, mode=mode)


class Chain(Compound):
  """A line of ``count`` interlocking links tiled along X with alternating
  tilt so successive links interlock."""

  def __init__(
    self,
    count: int = 6,
    length: float = 25.0,
    width: float = 13.0,
    thickness: float = 3.5,
    outline: ChainLinkOutlineBuilder = ChainLinkOutline.chamfered,
    cross_section: ChainLinkCrossSectionBuilder = ChainLinkCrossSection.octagon,
    tilt_mult: int = 1,
    brim: str = "none",
    brim_diameter: float = 8.0,
  ):
    if count < 1:
      raise ValueError("count must be >= 1")

    # Build one link once; keep it out of the active context.
    self.link = ChainLink(
      length=length,
      width=width,
      thickness=thickness,
      outline=outline,
      cross_section=cross_section,
      mode=Mode.PRIVATE,
    )

    inner_long_edge_length = (
      self.link.edges()
      .filter_by(Axis.X)
      .filter_by(lambda e: e.start_point().Y > 0)
      .sort_by(SortBy.LENGTH)[0]
      .length
    )

    sides = self.link.side_count
    base_tilt = 360.0 / sides / 2
    face_step = 360.0 / sides
    self.tilt = base_tilt + (tilt_mult - 1) * face_step
    pitch = inner_long_edge_length

    self.base_links: list[Compound] = []
    for i in range(count):
      rx = self.tilt if i % 2 else -self.tilt
      loc = Location((i * pitch, 0, 0), (90 + rx, 0, 0))
      self.base_links.append(self.link.moved(loc))

    z_min = self.base_links[0].faces().sort_by(Axis.Z)[0].bounding_box().min.Z

    self.links = self._add_brim(z_min=z_min, brim=brim, brim_diameter=brim_diameter)

    super().__init__(None, label="chain", children=self.links)

  def _add_brim(self, z_min: float, brim: str, brim_diameter: float) -> list[Compound]:
    if brim != "ears" or brim_diameter <= 0:
      return self.base_links

    links = []

    for i, link in enumerate(self.base_links):
      bottom_face_bb = link.faces().sort_by(Axis.Z)[0].bounding_box()
      center = bottom_face_bb.center()
      ears = [
        self._brim_ear(
          Vector(center.X, center.Y), Vector(cx, center.Y), z_min, brim_diameter
        )
        for cx in (bottom_face_bb.min.X, bottom_face_bb.max.X)
      ]
      links.append(link + ears)

    return links

  @staticmethod
  def _brim_ear(
    center: Vector, pos: Vector, z_min: float, brim_diameter: float
  ) -> Cylinder:
    """A single mouse-ear brim disc at the end of a link's bottom-contact run."""
    direction = center - pos
    pos -= direction.normalized() * (brim_diameter * 0.4)
    return Cylinder(radius=brim_diameter / 2, height=_BRIM_HEIGHT).moved(
      Location((pos.X, pos.Y, z_min + _BRIM_HEIGHT / 2))
    )


def build(params: Parameters) -> Compound:
  """Build the chain described by ``params`` and return it as a Compound,
  ready to tessellate or export."""
  return Chain(
    count=params.link_count,
    length=params.link_length,
    width=params.link_width,
    thickness=params.link_thickness,
    tilt_mult=params.tilt_mult,
    outline=params.link_shape,
    cross_section=params.cross_section,
    brim=params.brim,
    brim_diameter=params.brim_diameter,
  )


# --------------------------------------------------------------------------- #
# Printability analysis
# --------------------------------------------------------------------------- #
#
# Generic, JSON-serializable report consumed by the shell's printability panel.
# Only the geometry math here is chain-specific; the report shape (overall
# verdict + sections of labelled items with a status) is generic, so a future
# Code-tab module can supply its own ``analyze`` and the panel renders it
# unchanged.

# --------------------------------------------------------------------------- #
# Printability constants + shared bed-contact helpers
# --------------------------------------------------------------------------- #
#
# The chain is a row of near-vertical, alternately ±tilted loops. Each loop
# touches the bed only along the bottom of its straight run; how much area that
# is (a facet strip vs. a knife edge) decides whether the first layer sticks.
# Because the chain is translationally periodic with mirror-tilt, every link's
# bed contact is identical and every adjacent pair is congruent, so both the
# ear placement and the analysis are O(1) regardless of link count.

_FIRST_LAYER_HEIGHT = 0.2  # mm, assumed slicer first-layer height
_BRIM_HEIGHT = _FIRST_LAYER_HEIGHT  # mm, mouse-ear disc height (a single first-layer)
_CLEARANCE_WARNING = 0.2  # mm, gap below which separate links may still fuse
_OVERLAP_TOL = 1e-6  # mm, min distance below which links are treated as touching
# Interpenetration volume (mm³) at/above which links are clearly fused (error);
# any smaller overlap still interpenetrates but is flagged as a warning. The
# generator packs links with no clearance, so a well-formed chain sits just at
# the overlap boundary (a few mm³); real fusion is tens–hundreds of mm³.
_OVERLAP_ERROR_MM3 = 5.0

# Per-link effective contact footprint (mm²), ordered high -> low.
# band -> (min_area_mm2, item_status); below the smallest min -> _IMPOSSIBLE.
_DIFFICULTY_BANDS: dict[str, tuple[float, str]] = {
  "easy": (40.0, "ok"),
  "medium": (20.0, "ok"),
  "hard": (10.0, "warning"),
  "expert": (5.0, "warning"),
}
_IMPOSSIBLE = ("impossible", "error")  # below the smallest band -> needs a brim
_STATUS_RANK = {"ok": 0, "warning": 1, "error": 2}


def _classify(area: float) -> tuple[str, str]:
  """Map a contact footprint area (mm²) to a (difficulty band, status)."""
  for band, (min_area, status) in _DIFFICULTY_BANDS.items():
    if area >= min_area:
      return band, status
  return _IMPOSSIBLE


_DIFFICULTY_DETAIL = {
  "easy": "Plenty of bed contact.",
  "medium": "Should adhere on most beds.",
  "hard": "Small patch; adhesion may be marginal.",
  "expert": "Very little contact; likely to lift.",
  "impossible": "Too little contact to adhere.",
}


def _difficulty_item(label: str, area: float, *, suggest_brim: bool) -> dict:
  band, status = _classify(area)
  detail = f"{band.capitalize()} — {_DIFFICULTY_DETAIL[band]}"
  if suggest_brim and band in ("hard", "expert", "impossible"):
    detail += " Try the mouse-ears brim."
  return {
    "label": label,
    "value": round(area, 1),
    "unit": "mm²",
    "detail": detail,
    "status": status,
  }


def analyze(
  params: Parameters, obj: Compound, first_layer_height: float = _FIRST_LAYER_HEIGHT
) -> dict:
  """Assess the built chain's printability. Returns a generic report:
  ``{overall_status, summary, sections: [{title, items: [{label, value, unit?,
  detail?, status?}]}]}`` with ``status`` in ``{"ok","warning","error"}``."""
  links = list(getattr(obj, "links", None) or getattr(obj, "children", []) or [])
  base_links = list(getattr(obj, "base_links", None) or []) or links
  if not links:
    return {
      "overall_status": "error",
      "summary": "No links to analyze.",
      "sections": [],
    }

  # 1. Bed-contact footprint (one link stands for all).
  bare_area = base_links[0].faces().sort_by(Axis.Z)[0].area
  if params.brim == "ears":
    eff_area = links[0].faces().sort_by(Axis.Z)[0].area
    contact_items = [
      {
        "label": "Bare link",
        "value": round(bare_area, 1),
        "unit": "mm²",
        "detail": f"{_classify(bare_area)[0].capitalize()} without a brim.",
        "status": _classify(bare_area)[1],
      },
      _difficulty_item("With mouse ears", eff_area, suggest_brim=False),
    ]
  else:
    contact_items = [
      _difficulty_item("Bed contact per link", bare_area, suggest_brim=True)
    ]

  # 2. Interlock: overlap (error) and clearance (warning) for one adjacent pair.
  if len(base_links) >= 2:
    a, b = base_links[0], base_links[1]
    dist, _p1, _p2 = dist_shapes(a.wrapped, b.wrapped)
    if dist <= _OVERLAP_TOL:
      overlap_vol = (a & b).volume
      if overlap_vol >= _OVERLAP_ERROR_MM3:
        overlap_detail = (
          "Links fuse into one solid. Thin them, add sides, or enlarge the link."
        )
        overlap_status = "error"
      else:
        overlap_detail = "Links touch with no clearance — may fuse. Thin them slightly."
        overlap_status = "warning"
      connection_items = [
        {
          "label": "Links overlap",
          "value": round(overlap_vol, 2),
          "unit": "mm³",
          "detail": overlap_detail,
          "status": overlap_status,
        }
      ]
    else:
      clearance_status = "warning" if dist < _CLEARANCE_WARNING else "ok"
      connection_items = [
        {
          "label": "Overlap",
          "value": 0.0,
          "unit": "mm³",
          "detail": "None — links are separate.",
          "status": "ok",
        },
        {
          "label": "Clearance between links",
          "value": round(dist, 3),
          "unit": "mm",
          "detail": (
            "Tight gap — links may fuse."
            if clearance_status == "warning"
            else "Healthy gap; links stay separate."
          ),
          "status": clearance_status,
        },
      ]
  else:
    connection_items = [
      {
        "label": "Single link",
        "value": 1,
        "detail": "Only one link — no interlock to check.",
        "status": "ok",
      }
    ]

  sections = [
    {"title": "Bed contact", "items": contact_items},
    {"title": "Link interlock", "items": connection_items},
  ]

  overall = "ok"
  for section in sections:
    for item in section["items"]:
      status = item.get("status")
      if status and _STATUS_RANK[status] > _STATUS_RANK[overall]:
        overall = status

  summary = {
    "ok": "Looks printable.",
    "warning": "Printable, but check the flagged tolerances before printing.",
    "error": "Not printable as-is — resolve the errors below.",
  }[overall]
  print(f"analyze: {overall} — {summary}")
  print(sections)
  return {"overall_status": overall, "summary": summary, "sections": sections}
