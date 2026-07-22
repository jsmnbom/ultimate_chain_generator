import contextlib
import copy
from typing import cast as tcast

from build123d import BoundBox, Location, Plane
from build123d.topology.shape_core import TOPODS, Shape, downcast, fix
from OCP.Bnd import Bnd_Box
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf

USE_FAST_PATCH = True


@contextlib.contextmanager
def no_fast_patch():
  global USE_FAST_PATCH
  old_value = USE_FAST_PATCH
  USE_FAST_PATCH = False
  try:
    yield
  finally:
    USE_FAST_PATCH = old_value


def __copy__(self):
  cls = self.__class__
  result = cls.__new__(cls)
  for key, value in self.__dict__.items():
    if key == "_wrapped":
      result.wrapped = downcast(self.wrapped.Located(self.wrapped.Location()))
    else:
      setattr(result, key, copy.copy(value))
  return result


def _moved(self, loc: Location | Plane):
  if isinstance(loc, Plane):
    loc = loc.location
  if self._wrapped is None:
    raise ValueError("Cannot move an empty shape")
  if loc.wrapped is None:
    raise ValueError("Cannot move a shape at an empty location")
  shape_copy: Shape = copy.copy(self)
  shape_copy.wrapped = downcast(self.wrapped.Moved(loc.wrapped))
  return shape_copy


def _apply_transform(self, transformation: gp_Trsf):
  if self._wrapped is None:
    return self
  shape_copy: Shape = copy.copy(self)
  transformed_shape = BRepBuilderAPI_Transform(
    self.wrapped,
    transformation,
    True,
  ).Shape()
  shape_copy.wrapped = downcast(transformed_shape)
  return shape_copy


def _fix(self):
  if self._wrapped is None:
    return self
  if not self.is_valid:
    shape_copy: Shape = copy.copy(self)
    shape_copy.wrapped = fix(self.wrapped)

    return shape_copy

  return self


def _located(self, loc: Location):
  if self._wrapped is None:
    raise ValueError("Cannot locate an empty shape")
  if loc.wrapped is None:
    raise ValueError("Cannot locate a shape at an empty location")
  shape_copy: Shape = copy.copy(self)
  shape_copy.wrapped.Location(loc.wrapped)  # type: ignore
  return shape_copy


def _bounding_box(
  self, tolerance: float | None = None, optimal: bool = False
) -> BoundBox:
  if self._wrapped is None:
    return BoundBox(Bnd_Box())
  tolerance = 0.001 if tolerance is None else tolerance
  return BoundBox.from_topo_ds(self.wrapped, tolerance=tolerance, optimal=optimal)


Shape.__copy__ = __copy__
Shape.moved = _moved
Shape._apply_transform = _apply_transform
Shape.fix = _fix
Shape.located = _located
Shape.bounding_box = _bounding_box
