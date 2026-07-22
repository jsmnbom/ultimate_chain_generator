from pathlib import Path
from typing import Sequence, TypeVar

from build123d import Align, Compound, Location, Shell, Solid, Vertex, Wire
from build123d.topology.shape_core import Shape

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid


__all__ = [
  "align",
  "Shape",
  "make_compound",
  "flip",
  "lift",
  "raise_to",
  "make_solid",
]

T = TypeVar("T", bound=Shape)


def flip(shape: T) -> T:
  return shape.__class__(shape.wrapped.Reversed())


def lift(shape: T, dz: float) -> T:
  """Translate along +Z."""
  return shape.moved(Location((0, 0, dz)))


def raise_to(shape: T, z: float) -> T:
  """Translate so its start point sits at absolute height ``z``."""
  return lift(shape, z - (shape.position).Z)


def align(
  obj: T,
  align: tuple[Align, Align, Align] = (Align.CENTER, Align.CENTER, Align.CENTER),
  rot=(0, 0, 0),
) -> T:
  """Move a shape so its bounding box aligns to the given anchors.

  Args:
    obj: The shape to reposition (not mutated; a moved copy is returned).
    align: Per-axis anchor (X, Y, Z), each MIN, CENTER, or MAX. CENTER
      centres the bounding box on the origin along that axis; MIN/MAX put the
      box's low/high face on the origin.

  Returns:
    A copy of `obj` translated to the requested alignment.
  """
  if rot != (0, 0, 0):
    obj = obj.moved(Location((0, 0, 0), rot))
  bb = obj.bounding_box()
  return obj.moved(Location(bb.to_align_offset(align)))


def make_compound(label="", children=None, type=Compound, **named_children):
  children = list(children or [])
  for l, c in named_children.items():
    if isinstance(c, Sequence):
      for i, part in enumerate(c):
        part.label = f"{l}_{i}"
        children.append(part)
    else:
      c.label = l
      children.append(c)
  compound = type(None, label=label, children=children)
  return compound


def make_solid(*shells: Shell) -> Solid:
  """
  Make a solid from one or more shells.
  If multiple shells are given, the first is treated as the outer shell and the rest as inner shells (holes).
  """
  mk = BRepBuilderAPI_MakeSolid()
  for shell in shells:
    mk.Add(shell.wrapped)
  if not mk:
    raise ValueError("Failed to create solid from shells.")
  return Solid(mk.Solid())
