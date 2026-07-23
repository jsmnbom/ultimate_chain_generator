"""A blank starter model — the on-ramp for authoring your own.

This is the minimal thing the ``Design`` seam accepts: one pydantic parameter, a
build that turns it into geometry, and an (empty) printability report. Copy it,
rename ``MyDesign``, and grow it. See ``proto.py`` for the full contract and the
``chain`` model for a fleshed-out example.
"""

from build123d import *  # pyright: ignore[reportWildcardImportFromLibrary]
from proto import *  # pyright: ignore[reportWildcardImportFromLibrary]

# Gallery metadata. BLANK flags this as the "start from scratch" card. The card is
# currently hidden (see src/views/Gallery.vue) — the in-app source view is read-only,
# so there's no authoring path; this file stays as the scaffold to copy.
NAME = "Start from scratch"
DESCRIPTION = "A minimal Design scaffold to build your own model on."
BLANK = True


class Parameters(BaseModel):
  """Parameters drive the form. Each field becomes a control; the helpers in
  ``proto`` (``slider_field`` etc.) add widget hints."""

  size: float = Field(
    default=20.0,
    ge=1.0,
    le=100.0,
    json_schema_extra=slider_field("Size", 5, 60, step=1, unit="mm"),
  )


class MyDesign(Design[Parameters]):
  """Instantiating with a ``Parameters`` builds the geometry into ``self``."""

  def __init__(self, params: Parameters):
    self.params = params
    box = Box(params.size, params.size, params.size)
    box.label = "my_design"
    super().__init__(None, label="my_design", children=[box])
