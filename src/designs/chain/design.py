"""The chain design — a reference implementation of the ``Design`` seam.

This module is the single source of truth for both the form (via
``Chain.Parameters.model_json_schema()``) and the geometry (via ``Chain(params)``).
It is loaded verbatim into the Pyodide worker; nothing here is browser-specific,
so it can also be imported and exercised natively (see ``README.md``).

It defines exactly one ``Design`` subclass (``Chain``); the runtime discovers it
with ``proto.load_design``. The Code tab plugs in at this same seam — its own
``Design`` subclass swaps in with no change to the schema / build / export
pipelines. See ``proto.py`` for the full contract.
"""

from __future__ import annotations

import math
from typing import Callable, ClassVar, Literal, cast

from build123d import *  # pyright: ignore[reportWildcardImportFromLibrary]
from proto import *  # pyright: ignore[reportWildcardImportFromLibrary]

# Gallery metadata — plain module-level constants the build-time manifest scrapes
# (see src/designs/manifest.ts). Co-located with the design so they can't drift;
# every field is optional (the manifest falls back to the slug). LINKS is the
# per-design footer link list ({"label", "url"} dicts); each icon is auto-derived
# from the URL's host.
NAME = "Chain"
AUTHOR = "jsmnbom"
DESCRIPTION = "Parametric 3D-printable interlocking chains."
LINKS = [
    {"label": "Printables", "url": "https://www.printables.com/@jsmnbom"},
    {"label": "GitHub", "url": "https://github.com/jsmnbom/ultimate_chain_generator"},
]

# --------------------------------------------------------------------------- #
# Choice types — link outlines and cross-sections
# --------------------------------------------------------------------------- #
#
# These are both form types (Parameters fields, with SVG previews) and geometry
# builders (ChainLink/Chain sweep along / around them), which is why the design
# stays one interconnected module.


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


# --------------------------------------------------------------------------- #
# Parameters — the form/validation source of truth
# --------------------------------------------------------------------------- #


class Parameters(BaseModel):
  """Parameters for a line chain of interlocking links (all lengths in mm)."""

  link_shape: ChainLinkOutline = Field(
    default=cast(ChainLinkOutline, ChainLinkOutline.chamfered),
    json_schema_extra=choice_field(
      ChainLinkOutline,
      "Link shape",
      preview=lambda m: m(2.0, 1.2),  # representative icon size
      size="lg",
    ),
  )
  cross_section: ChainLinkCrossSection = Field(
    default=cast(ChainLinkCrossSection, ChainLinkCrossSection.octagon),
    json_schema_extra=choice_field(
      ChainLinkCrossSection,
      "Cross-section",
      preview=lambda m: m(1.0).wire(),
      size="lg",
    ),
  )
  link_count: int = Field(
    default=6,
    ge=1,
    le=60,
    json_schema_extra=slider_field(
      "Link count", 1, 40, step=1, description="Number of links in the chain."
    ),
  )
  link_length: float = Field(
    default=25.0,
    gt=0,
    le=120.0,
    json_schema_extra=slider_field(
      "Link length",
      5,
      80,
      step=0.5,
      description="Long axis of each link. Must be at least the link width.",
    ),
  )
  link_width: float = Field(
    default=13.0,
    gt=0,
    le=60.0,
    json_schema_extra=slider_field(
      "Link width",
      3,
      40,
      step=0.5,
      unit="millimeter",
      description="Short axis of each link. Must be at least the thickness.",
    ),
  )
  link_thickness: float = Field(
    default=3.5,
    gt=0,
    le=20.0,
    json_schema_extra=slider_field(
      "Link thickness",
      0.5,
      15,
      step=0.1,
      unit="millimeter",
      description="Bar diameter of each link — thinner links open a print gap "
      "between neighbours; too thick and they fuse.",
    ),
  )
  tilt_mult: int = Field(
    default=1,
    ge=1,
    le=max(_TILT_MULT_MAX.values()),
    json_schema_extra=slider_field(
      "Tilt multiplier",
      1,
      max(_TILT_MULT_MAX.values()),
      step=1,
      description="How many cross-section faces to skip when tilting each link.",
      # Only shown for cross-sections with enough faces; the slider max then
      # depends on which one is selected (see _TILT_MULT_MAX).
      show_if={"cross_section": list(_TILT_MULT_MAX)},
      slider_max_by={"cross_section": _TILT_MULT_MAX},
      size="xs",
    ),
  )
  brim: Literal["none", "ears"] = Field(
    default="none",
    json_schema_extra=select_field(
      "Brim",
      [
        {"value": "none", "label": "None", "description": "No brim."},
        {
          "value": "ears",
          "label": "Mouse ears",
          "description": "Thin discs at each link's contact points.",
        },
      ],
      description="Adds small discs under each link to widen bed contact and "
      "prevent lifting on hard-to-print settings.",
    ),
  )
  brim_diameter: float = Field(
    default=8.0,
    gt=0,
    le=30.0,
    json_schema_extra=slider_field(
      "Brim diameter",
      4,
      15,
      step=0.5,
      unit="millimeter",
      show_if={"brim": "ears"},
      size="xs",
      description="Diameter of each mouse-ear disc.",
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


class Chain(Design[Parameters]):
  """A line of interlocking links tiled along X with alternating tilt so
  successive links interlock. Instantiating with a ``Parameters`` builds the
  geometry into ``self`` (a ``Compound``)."""

  # Curated, manually-verified starting points offered by the form's preset
  # picker. Each entry is ``{name, description, params}`` where ``params`` is a
  # partial (or full) ``Parameters`` dict merged over the schema defaults on the
  # frontend, so an entry only needs to spell out the fields it changes.
  PRESETS: ClassVar[list[dict]] = [
    {
      "name": "Default",
      "description": "The stock chain — a balanced starting point.",
      "params": {},
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

  def __init__(self, params: Parameters):
    self.params = params
    count = params.link_count
    if count < 1:
      raise ValueError("count must be >= 1")

    # Build one link once; keep it out of the active context.
    self.link = ChainLink(
      length=params.link_length,
      width=params.link_width,
      thickness=params.link_thickness,
      outline=params.link_shape,
      cross_section=params.cross_section,
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
    self.tilt = base_tilt + (params.tilt_mult - 1) * face_step
    pitch = inner_long_edge_length

    self.base_links: list[Compound] = []
    for i in range(count):
      rx = self.tilt if i % 2 else -self.tilt
      loc = Location((i * pitch, 0, 0), (90 + rx, 0, 0))
      self.base_links.append(self.link.moved(loc))

    z_min = self.base_links[0].faces().sort_by(Axis.Z)[0].bounding_box().min.Z

    self.links = self._add_brim(
      z_min=z_min, brim=params.brim, brim_diameter=params.brim_diameter
    )

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

  # ------------------------------------------------------------------------- #
  # Printability analysis
  # ------------------------------------------------------------------------- #
  #
  # The chain is a row of near-vertical, alternately ±tilted loops. Each loop
  # touches the bed only along the bottom of its straight run; how much area that
  # is (a facet strip vs. a knife edge) decides whether the first layer sticks.
  # Because the chain is translationally periodic with mirror-tilt, every link's
  # bed contact is identical and every adjacent pair is congruent, so the
  # analysis is O(1) regardless of link count.

  def analyze(self) -> Report:
    """Assess the built chain's printability (bed contact + link interlock + lean).

    The generic checks (bed contact, interlock, floating) come from ``proto``'s
    finding-builders; only the chain-specific choices — which face stands for the
    per-link footprint (periodicity), brim messaging, and the alternating-tilt lean
    — live here."""
    report = Report()

    # 0. Degenerate geometry — if the build collapsed to slivers / invalid solids the
    # measurements below are meaningless (and may raise), so bail early.
    if not check_degenerate(report, self):
      return report

    # 1. Bed-contact footprint (one link stands for all, by periodicity).
    bare_area = self.base_links[0].faces().sort_by(Axis.Z)[0].area
    if self.params.brim == "ears":
      check_bed_contact(report, bare_area, label="Bare link")
      eff_area = self.links[0].faces().sort_by(Axis.Z)[0].area
      check_bed_contact(report, eff_area, label="Bed contact with mouse ears")
    else:
      check_bed_contact(
        report,
        bare_area,
        label="Bed contact per link",
        suggestion="Try the mouse-ears brim.",
      )

    # 2. Interlock: overlap (error) / clearance (warning) for one adjacent pair.
    if len(self.base_links) >= 2:
      check_interlock(
        report,
        self.base_links[0],
        self.base_links[1],
        overlap_label="Links overlap",
        clearance_label="Clearance between links",
      )
    else:
      report.add(
        "Single link", 1, detail="Only one link — no interlock to check.", status="ok"
      )

    # 3. Floating sections — every link is bedded by construction, so this is a cheap
    # ok-guard, but it catches a future regression that lifts a link off the bed.
    check_floating(report, self)

    # 4. Lean — each link tilts ``self.tilt`` from vertical (mirror-alternated).
    # ``_max_tilt_mult`` only holds tilt below 90°, so it can pass 45° (e.g. a square
    # cross-section's 45° base tilt), where the link's flank becomes an unsupported
    # overhang. Analytical from the known tilt — O(1), no geometry walk.
    self._check_lean(report)

    return report

  def _check_lean(self, report: Report) -> None:
    """Flag when a link leans past the overhang limit (unsupported without support)."""
    lean = self.tilt
    status = "error" if lean > _MAX_LEAN_DEG else "ok"
    detail = (
      f"Links lean {lean:.0f}° from vertical — past {_MAX_LEAN_DEG:.0f}° the flank "
      "overhangs and needs support. Lower the tilt multiplier or add cross-section faces."
      if status == "error"
      else "Links stay within the self-supporting overhang angle."
    )
    report.add("Link lean", round(lean, 1), unit="°", detail=detail, status=status)


# --------------------------------------------------------------------------- #
# Printability constants (chain-specific)
# --------------------------------------------------------------------------- #

_FIRST_LAYER_HEIGHT = 0.2  # mm, assumed slicer first-layer height
_BRIM_HEIGHT = _FIRST_LAYER_HEIGHT  # mm, mouse-ear disc height (a single first-layer)
_MAX_LEAN_DEG = 45.0  # deg from vertical past which a link's flank overhangs
