from __future__ import annotations
import inspect
import io
import re
from typing import (
  TYPE_CHECKING,
  Any,
  Callable,
  Generic,
  Iterator,
  TypeVar,
)

from build123d import ExportSVG, Wire

__all__ = [
  "Choice",
  "outline_svg",
  "wire_choice_field_extra",
  "slider_field_extra",
]

T = TypeVar("T")
C = TypeVar("C", bound="Choice[Any]")


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


def wire_choice_field_extra(
  choices: type[Choice[Any]],
  label: str,
  *,
  preview: Callable[[Choice[Any]], Any],
  **kwargs: Any,
) -> dict:
  return {
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


def slider_field_extra(
  label: str,
  slider_min: float,
  slider_max: float,
  *,
  step: float,
  unit: str | None = None,
  description: str | None = None,
  **kwargs: Any,
) -> dict:
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
