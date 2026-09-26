"""Image I/O: any Pillow-readable file <-> premultiplied linear-light RGBA float64."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def srgb_to_linear(v):
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0.04045, v / 12.92, ((np.maximum(v, 0) + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(v):
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.maximum(v, 0) ** (1 / 2.4) - 0.055)


def load(path):
    """Read an image as premultiplied linear RGBA (H, W, 4) plus a has-alpha flag."""
    img = Image.open(path)
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):
        g = np.asarray(img, dtype=np.float64) / 65535.0
        rgb = np.repeat(g[..., None], 3, axis=-1)
        a = np.ones(g.shape + (1,))
    else:
        arr = np.asarray(img.convert("RGBA"), dtype=np.float64) / 255.0
        rgb, a = arr[..., :3], arr[..., 3:4]
    lin = srgb_to_linear(rgb) * a
    return np.ascontiguousarray(np.concatenate((lin, a), axis=-1)), has_alpha


def to_display(img, background=None):
    """Premultiplied linear RGBA -> straight sRGB RGBA in [0, 1] (clipped).

    ``background`` (linear RGB triple) composites the image over a solid
    colour; the result is then opaque.
    """
    rgb = img[..., :3]
    a = np.clip(img[..., 3:4], 0.0, 1.0)
    if background is not None:
        rgb = rgb + (1.0 - a) * np.asarray(background, dtype=np.float64)
        a = np.ones_like(a)
        straight = rgb
    else:
        straight = np.divide(rgb, img[..., 3:4], out=np.zeros_like(rgb), where=img[..., 3:4] > 1e-12)
    return np.concatenate((linear_to_srgb(np.clip(straight, 0, 1)), a), axis=-1)


def save(path, img, background=None, keep_alpha=True):
    """Write premultiplied linear RGBA. Formats without alpha get the background (default black)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    alpha_ok = keep_alpha and path.suffix.lower() in (".png", ".webp", ".tif", ".tiff")
    if not alpha_ok and background is None:
        background = (0.0, 0.0, 0.0)
    d = to_display(img, background)
    arr = np.round(d * 255).astype(np.uint8)
    if background is not None or not alpha_ok:
        Image.fromarray(arr[..., :3], "RGB").save(path)
    else:
        Image.fromarray(arr, "RGBA").save(path)


def parse_color(text):
    """'#rrggbb', 'rrggbb', 'white', 'black', 'gray' -> linear RGB, or None for 'transparent'."""
    if text is None or text.lower() in ("none", "transparent"):
        return None
    names = {"white": "ffffff", "black": "000000", "gray": "808080", "grey": "808080"}
    h = names.get(text.lower(), text.lstrip("#"))
    if len(h) != 6:
        raise ValueError(f"bad colour {text!r}")
    return tuple(float(srgb_to_linear(int(h[i:i + 2], 16) / 255.0)) for i in (0, 2, 4))
