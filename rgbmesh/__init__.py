"""RGB mesh resampling: reference implementation.

    >>> from rgbmesh import load, save, Chain, canvas, build_field, render
    >>> img, _ = load("photo.png")                      # premultiplied linear RGBA
    >>> H, W = img.shape[:2]
    >>> T = Chain(W, H).rotate(17.3).scale(2.0).T        # composed, not rasterized
    >>> M, shape = canvas(T, W, H, "expand")
    >>> field = build_field("m13zf", img)                # mesh built once
    >>> out = render(field, "m13zf", M, shape)           # exact footprint integration
    >>> save("out.png", out)
"""

from .core import (DEFAULT_METHOD, METHODS, Z_PAIRS, build_field, render, resample)
from .imageio import load, parse_color, save
from .transform import Chain, canvas, rotation, scaling, translation

__all__ = ["DEFAULT_METHOD", "METHODS", "Z_PAIRS", "build_field", "render", "resample",
           "load", "save", "parse_color", "Chain", "canvas", "rotation", "scaling", "translation"]
__version__ = "0.1.0"
