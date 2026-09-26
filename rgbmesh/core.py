"""RGB mesh fields and the public resampling API.

Pipeline (see METHOD.md):

    pixel colours P (linear, premultiplied RGBA)
      -> vertex V = mean of the 4 surrounding centres
      -> edge   E = (P1 + P2 + V1 + V2) / 4
      -> 9-node Q2 cell per source pixel
      -> optional area (Z) calibration  C' = C + 36/16 (P - A)
      -> optional refinement (13 / 25 / 41 nodes) sampled from the Q2 surface
      -> optional final-grid calibration of the refined mesh
      -> exact integration over every output-pixel footprint

The field is padded by PAD edge-replicated pixels so that the reconstruction
near the image border is well defined; integration itself is restricted to
the true image rectangle, and everything outside it is transparent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import kernels

PAD = 4


# ------------------------------------------------------------------ fields

@dataclass
class LatticeField:
    nodes: np.ndarray       # (k*Ny+1, k*Nx+1, C) or (Ny, Nx, C) for k = 0
    k: int
    ox: float
    oy: float
    h: float
    width: int              # source image size (unpadded)
    height: int

    def area(self, M, shape):
        out = np.empty(tuple(shape[:2]) + (self.nodes.shape[2],))
        ny = self.nodes.shape[0] if self.k == 0 else (self.nodes.shape[0] - 1) // self.k
        nx = self.nodes.shape[1] if self.k == 0 else (self.nodes.shape[1] - 1) // self.k
        kernels.lattice_area(self.nodes, self.k, self.ox, self.oy, self.h, nx, ny,
                             float(self.width), float(self.height),
                             np.ascontiguousarray(M, dtype=np.float64), out)
        return out

    def point(self, M, shape):
        out = np.empty(tuple(shape[:2]) + (self.nodes.shape[2],))
        kernels.lattice_point(self.nodes, self.k, self.ox, self.oy, self.h,
                              float(self.width), float(self.height),
                              np.ascontiguousarray(M, dtype=np.float64), out)
        return out

    @property
    def nbytes(self):
        return self.nodes.nbytes


@dataclass
class FanField:
    grid: np.ndarray        # (Ny+1, Nx+1, C)
    faces: np.ndarray       # (Ny, Nx, C)
    ox: float
    oy: float
    h: float
    width: int
    height: int

    def area(self, M, shape):
        out = np.empty(tuple(shape[:2]) + (self.grid.shape[2],))
        kernels.fan_area(self.grid, self.faces, self.ox, self.oy, self.h,
                         float(self.width), float(self.height),
                         np.ascontiguousarray(M, dtype=np.float64), out)
        return out

    def point(self, M, shape):
        out = np.empty(tuple(shape[:2]) + (self.grid.shape[2],))
        kernels.fan_point(self.grid, self.faces, self.ox, self.oy, self.h,
                          float(self.width), float(self.height),
                          np.ascontiguousarray(M, dtype=np.float64), out)
        return out

    def face_means(self):
        g = self.grid
        return (g[:-1, :-1] + g[:-1, 1:] + g[1:, :-1] + g[1:, 1:]) / 6.0 + self.faces / 3.0

    @property
    def nbytes(self):
        return self.grid.nbytes + self.faces.nbytes


@dataclass
class ClassicField:
    samples: np.ndarray
    kind: int

    def point(self, M, shape):
        out = np.empty(tuple(shape[:2]) + (self.samples.shape[2],))
        kernels.classic_point(self.samples, self.kind, np.ascontiguousarray(M, dtype=np.float64), out)
        return out

    @property
    def nbytes(self):
        return self.samples.nbytes


# ---------------------------------------------------------- construction

def _q2_basis_matrix(ts):
    t = np.asarray(ts, dtype=np.float64)
    return np.stack((2 * (t - 0.5) * (t - 1), -4 * t * (t - 1), 2 * t * (t - 0.5)), axis=-1)


def _cells(lattice):
    ny = (lattice.shape[0] - 1) // 2
    nx = (lattice.shape[1] - 1) // 2
    r = 2 * np.arange(ny)[:, None, None, None] + np.arange(3)[None, None, :, None]
    c = 2 * np.arange(nx)[None, :, None, None] + np.arange(3)[None, None, None, :]
    return lattice[r, c]


def sample_q2(lattice, ts, chunk=64):
    """Evaluate a Q2 lattice at local positions ``ts`` in every cell."""
    B = _q2_basis_matrix(ts)
    ny = (lattice.shape[0] - 1) // 2
    nx = (lattice.shape[1] - 1) // 2
    m = len(ts)
    C = lattice.shape[2]
    out = np.empty((ny * m, nx * m, C), dtype=lattice.dtype)
    for s in range(0, ny, chunk):
        e = min(ny, s + chunk)
        vals = np.einsum("pb,qa,yxbac->ypxqc", B, B, _cells(lattice[2 * s:2 * e + 1]), optimize=True)
        out[s * m:e * m] = vals.reshape((e - s) * m, nx * m, C)
    return out


def refine_lattice_25(lattice):
    """Quarter-pixel Q2 lattice (four Q2 patches per pixel) sampled from a Q2 lattice."""
    ny = (lattice.shape[0] - 1) // 2
    nx = (lattice.shape[1] - 1) // 2
    C = lattice.shape[2]
    out = np.empty((4 * ny + 1, 4 * nx + 1, C), dtype=lattice.dtype)
    out[:-1, :-1] = sample_q2(lattice, [0.0, 0.25, 0.5, 0.75])
    last_row = sample_q2(lattice[-3:], [0.0, 0.25, 0.5, 0.75, 1.0])[-1]
    out[-1, :-1] = last_row.reshape(nx, 5, C)[:, :4].reshape(4 * nx, C)
    out[-1, -1] = last_row[-1]
    last_col = sample_q2(lattice[:, -3:], [0.0, 0.25, 0.5, 0.75, 1.0])[:, -1]
    out[:-1, -1] = last_col.reshape(ny, 5, C)[:, :4].reshape(4 * ny, C)
    out[::2, ::2] = lattice
    return out


def build_q2_lattice(P):
    """9-node Q2 lattice (half-pixel spacing) from centre samples P (H, W, C)."""
    h, w, C = P.shape
    g = np.pad(P, ((1, 1), (1, 1), (0, 0)), mode="edge")
    V = (g[:-1, :-1] + g[:-1, 1:] + g[1:, :-1] + g[1:, 1:]) / 4.0
    Eh = (g[:-1, 1:-1] + g[1:, 1:-1] + V[:, :-1] + V[:, 1:]) / 4.0
    Ev = (g[1:-1, :-1] + g[1:-1, 1:] + V[:-1, :] + V[1:, :]) / 4.0
    L = np.empty((2 * h + 1, 2 * w + 1, C))
    L[0::2, 0::2] = V
    L[0::2, 1::2] = Eh
    L[1::2, 0::2] = Ev
    L[1::2, 1::2] = P
    return L


def q2_cell_means(L):
    V, Eh, Ev, Cc = L[0::2, 0::2], L[0::2, 1::2], L[1::2, 0::2], L[1::2, 1::2]
    corners = V[:-1, :-1] + V[:-1, 1:] + V[1:, :-1] + V[1:, 1:]
    edges = Eh[:-1] + Eh[1:] + Ev[:, :-1] + Ev[:, 1:]
    return (corners + 4 * edges + 16 * Cc) / 36.0


def _per_pixel_mean(m, s):
    ny, nx, C = m.shape
    return m.reshape(ny // s, s, nx // s, s, C).mean(axis=(1, 3)) if s > 1 else m


def _spread(d, s):
    return np.repeat(np.repeat(d, s, axis=0), s, axis=1) if s > 1 else d


def z_correct_q2(L, P, per_pixel=1):
    """Area calibration: shift Q2 centre nodes so each source pixel's mean is P."""
    delta = (36.0 / 16.0) * (P - _per_pixel_mean(q2_cell_means(L), per_pixel))
    out = L.copy()
    out[1::2, 1::2] += _spread(delta, per_pixel)
    return out


def z_correct_fan(fan, P, per_pixel):
    """Area calibration of a fan mesh: shift every face centre by 3 (P - mean)."""
    delta = 3.0 * (P - _per_pixel_mean(fan.face_means(), per_pixel))
    return FanField(fan.grid, fan.faces + _spread(delta, per_pixel), fan.ox, fan.oy, fan.h,
                    fan.width, fan.height)


# ----------------------------------------------------------------- methods

@dataclass(frozen=True)
class Method:
    id: str
    points: int
    z: str            # none | 9 | final
    sampling: str     # area | point
    description: str


METHODS = {m.id: m for m in [
    Method("nearest", 1, "none", "point", "nearest neighbour"),
    Method("bilinear", 4, "none", "point", "bilinear (point sampling on the pixel grid)"),
    Method("bicubic", 16, "none", "point", "Keys bicubic a=-0.5"),
    Method("lanczos3", 36, "none", "point", "Lanczos-3"),
    Method("box", 1, "none", "area", "piecewise-constant pixels, exact area (classic area resampling)"),
    Method("tent", 4, "none", "area", "bilinear surface, exact area"),
    Method("m09", 9, "none", "area", "9-node Q2 mesh, no calibration"),
    Method("m09z", 9, "9", "area", "9-node Q2 mesh + area (Z) calibration"),
    Method("m09z_13", 13, "9", "area", "9Z refined to a 13-node centre fan (inherits the 9-node calibration)"),
    Method("m09z_41", 41, "9", "area", "9Z refined to a 41-node centre fan (inherits the 9-node calibration)"),
    Method("m13", 13, "none", "area", "13-node centre fan from raw Q2, no calibration"),
    Method("m41", 41, "none", "area", "41-node centre fan from raw Q2, no calibration"),
    Method("m13zf", 13, "final", "area", "13-node fan, area calibration on the final grid (recommended)"),
    Method("m25zf", 25, "final", "area", "four Q2 patches per pixel, calibrated on the final grid"),
    Method("m41zf", 41, "final", "area", "41-node fan, calibrated on the final grid (highest quality, slowest)"),
]}
DEFAULT_METHOD = "m13zf"
# calibrated method -> its uncalibrated counterpart (for the Z-difference image)
Z_PAIRS = {"m09z": "m09", "m13zf": "m13", "m25zf": "m09", "m41zf": "m41",
           "m09z_13": "m13", "m09z_41": "m41"}


def build_field(method: str, image, dtype=np.float64):
    """Build the continuous field of ``method`` for a premultiplied linear image (H, W, C).

    ``dtype=np.float32`` halves the memory of the stored mesh; construction and
    integration still run in float64.
    """
    base = method.split("@")[0]
    img = np.ascontiguousarray(image, dtype=np.float64)
    H, W, _ = img.shape
    classic = {"nearest": 0, "bilinear": 1, "bicubic": 2, "lanczos3": 3}
    if base in classic:
        return ClassicField(img, classic[base])
    P = np.pad(img, ((PAD, PAD), (PAD, PAD), (0, 0)), mode="edge")
    ny, nx, _ = P.shape
    o = -float(PAD)
    cast = lambda a: np.ascontiguousarray(a, dtype=dtype)
    if base == "box":
        return LatticeField(cast(P), 0, o, o, 1.0, W, H)
    if base == "tent":
        # bilinear surface through pixel centres, cells limited to the image interior
        return LatticeField(cast(P[PAD - 1:PAD + H + 1, PAD - 1:PAD + W + 1]), 1, -0.5, -0.5, 1.0, W, H)
    L = build_q2_lattice(P)
    if base in ("m09z", "m09z_13", "m09z_41"):
        L = z_correct_q2(L, P, 1)
    if base in ("m09", "m09z"):
        return LatticeField(cast(L), 2, o, o, 1.0, W, H)
    if base == "m25zf":
        L25 = z_correct_q2(refine_lattice_25(L), P, 2)
        return LatticeField(cast(L25), 2, o, o, 0.5, W, H)
    if base in ("m13", "m09z_13", "m13zf"):
        fan = FanField(L, sample_q2(L, [0.25, 0.75]), o, o, 0.5, W, H)
        if base == "m13zf":
            fan = z_correct_fan(fan, P, 2)
        return FanField(cast(fan.grid), cast(fan.faces), o, o, 0.5, W, H)
    if base in ("m41", "m09z_41", "m41zf"):
        fan = FanField(refine_lattice_25(L), sample_q2(L, [0.125, 0.375, 0.625, 0.875]), o, o, 0.25, W, H)
        if base == "m41zf":
            fan = z_correct_fan(fan, P, 4)
        return FanField(cast(fan.grid), cast(fan.faces), o, o, 0.25, W, H)
    raise KeyError(f"unknown method {method!r}; available: {', '.join(METHODS)}")


def render(field, method: str, M, shape, sampling: str | None = None):
    """Sample ``field`` onto an output grid of ``shape`` = (h, w) via output->source map M."""
    base = method.split("@")[0]
    if sampling is None:
        sampling = "point" if method.endswith("@pt") else METHODS[base].sampling
    return field.area(M, shape) if sampling == "area" else field.point(M, shape)


def resample(image, M, shape, method: str = DEFAULT_METHOD):
    """One-shot convenience: build the field and render it."""
    return render(build_field(method, image), method, M, shape)
