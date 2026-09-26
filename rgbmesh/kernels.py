"""Numba kernels: exact footprint integration and point sampling.

Conventions
-----------
* Source pixel (i, j) covers [i, i+1] x [j, j+1]; its sample sits at (i+.5, j+.5).
* ``M`` (2x3) maps *output pixel coordinates* to *source coordinates*. Output
  pixel (i, j) covers [i, i+1] x [j, j+1]; its footprint in the source is the
  parallelogram spanned by the images of those corners.
* Images are premultiplied linear RGBA. Everything outside the source rectangle
  [0, W] x [0, H] is transparent, so AREA sampling integrates the field over
  footprint ∩ image and divides by the *whole* footprint area: the alpha
  channel then carries the exact geometric coverage.

Field kinds
-----------
* Lattice of order k (k = 0, 1, 2): tensor Lagrange polynomial per cell,
  nodes (k*Ny+1, k*Nx+1, C) for k >= 1, (Ny, Nx, C) for k = 0.
  Cell (cy, cx) covers [ox + cx*h, ox + (cx+1)*h] x [oy + cy*h, ...].
* Fan mesh: grid nodes (Ny+1, Nx+1, C) plus face centres (Ny, Nx, C); each
  square is four triangles meeting at its centre, linear on each triangle.

Exactness: footprints are clipped against cells / triangles
(Sutherland-Hodgman), fan-triangulated, and integrated with a degree-4
Dunavant rule, which is exact for the bi-quadratic Q2 polynomial.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange

_DW = np.array([0.223381589678011, 0.223381589678011, 0.223381589678011,
                0.109951743655322, 0.109951743655322, 0.109951743655322])
_DL = np.array([[0.108103018168070, 0.445948490915965, 0.445948490915965],
                [0.445948490915965, 0.108103018168070, 0.445948490915965],
                [0.445948490915965, 0.445948490915965, 0.108103018168070],
                [0.816847572980459, 0.091576213509771, 0.091576213509771],
                [0.091576213509771, 0.816847572980459, 0.091576213509771],
                [0.091576213509771, 0.091576213509771, 0.816847572980459]])

# Half-planes a*u + b*v + c >= 0 selecting the four fan triangles of a unit square.
_TRI_PLANES = np.array([
    [[1.0, -1.0, 0.0], [-1.0, -1.0, 1.0]],   # top    v <= u, v <= 1-u
    [[1.0, -1.0, 0.0], [1.0, 1.0, -1.0]],    # right  v <= u, v >= 1-u
    [[-1.0, 1.0, 0.0], [1.0, 1.0, -1.0]],    # bottom v >= u, v >= 1-u
    [[-1.0, 1.0, 0.0], [-1.0, -1.0, 1.0]],   # left   v >= u, v <= 1-u
])


@njit(cache=True, inline="always")
def _clip(src, n, dst, a, b, c):
    """Clip polygon src[:n] to a*x + b*y + c >= 0, write into dst."""
    if n == 0:
        return 0
    m = 0
    px = src[n - 1, 0]
    py = src[n - 1, 1]
    pv = a * px + b * py + c
    for i in range(n):
        cx = src[i, 0]
        cy = src[i, 1]
        cv = a * cx + b * cy + c
        if (pv >= 0.0) != (cv >= 0.0):
            t = pv / (pv - cv)
            dst[m, 0] = px + t * (cx - px)
            dst[m, 1] = py + t * (cy - py)
            m += 1
        if cv >= 0.0:
            dst[m, 0] = cx
            dst[m, 1] = cy
            m += 1
        px = cx
        py = cy
        pv = cv
    return m


@njit(cache=True, inline="always")
def _clip_unit_square(A, B, n):
    n = _clip(A, n, B, 1.0, 0.0, 0.0)
    n = _clip(B, n, A, -1.0, 0.0, 1.0)
    n = _clip(A, n, B, 0.0, 1.0, 0.0)
    n = _clip(B, n, A, 0.0, -1.0, 1.0)
    return n


@njit(cache=True, inline="always")
def _poly_area_centroid(P, n):
    area = 0.0
    sx = 0.0
    sy = 0.0
    x0 = P[0, 0]
    y0 = P[0, 1]
    for t in range(1, n - 1):
        ax = P[t, 0] - x0
        ay = P[t, 1] - y0
        bx = P[t + 1, 0] - x0
        by = P[t + 1, 1] - y0
        a = 0.5 * (ax * by - bx * ay)
        area += a
        sx += a * (ax + bx) / 3.0
        sy += a * (ay + by) / 3.0
    if area == 0.0:
        return 0.0, x0, y0
    return abs(area), x0 + sx / area, y0 + sy / area


@njit(cache=True, inline="always")
def _basis(k, t, out):
    if k == 0:
        out[0] = 1.0
    elif k == 1:
        out[0] = 1.0 - t
        out[1] = t
    else:
        out[0] = 2.0 * (t - 0.5) * (t - 1.0)
        out[1] = -4.0 * t * (t - 1.0)
        out[2] = 2.0 * t * (t - 0.5)


@njit(cache=True, inline="always")
def _clipped_footprint(M, X, Y, W, H, P, B):
    """Footprint of output pixel (X, Y) clipped to the image [0,W]x[0,H]; returns n."""
    P[0, 0] = M[0, 0] * X + M[0, 1] * Y + M[0, 2]
    P[0, 1] = M[1, 0] * X + M[1, 1] * Y + M[1, 2]
    P[1, 0] = P[0, 0] + M[0, 0]
    P[1, 1] = P[0, 1] + M[1, 0]
    P[2, 0] = P[1, 0] + M[0, 1]
    P[2, 1] = P[1, 1] + M[1, 1]
    P[3, 0] = P[0, 0] + M[0, 1]
    P[3, 1] = P[0, 1] + M[1, 1]
    n = _clip(P, 4, B, 1.0, 0.0, 0.0)
    n = _clip(B, n, P, -1.0, 0.0, W)
    n = _clip(P, n, B, 0.0, 1.0, 0.0)
    n = _clip(B, n, P, 0.0, -1.0, H)
    return n


@njit(cache=True, inline="always")
def _bbox_cells(P, n, ox, oy, h, ncx, ncy):
    xmin = P[0, 0]
    xmax = P[0, 0]
    ymin = P[0, 1]
    ymax = P[0, 1]
    for q in range(1, n):
        xmin = min(xmin, P[q, 0])
        xmax = max(xmax, P[q, 0])
        ymin = min(ymin, P[q, 1])
        ymax = max(ymax, P[q, 1])
    cx0 = max(0, int(math.floor((xmin - ox) / h)))
    cx1 = min(ncx - 1, int(math.floor((xmax - ox) / h)))
    cy0 = max(0, int(math.floor((ymin - oy) / h)))
    cy1 = min(ncy - 1, int(math.floor((ymax - oy) / h)))
    return cx0, cx1, cy0, cy1


@njit(parallel=True, cache=True)
def lattice_area(nodes, k, ox, oy, h, ncx, ncy, W, H, M, out):
    """Exact AREA sampling of a lattice field over footprint ∩ image."""
    out_h, out_w, C = out.shape
    DW = _DW
    DL = _DL
    fp_area = abs(M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]) / (h * h)   # local units
    for j in prange(out_h):
        P = np.empty((24, 2))
        A = np.empty((24, 2))
        B = np.empty((24, 2))
        lu = np.empty(3)
        lv = np.empty(3)
        acc = np.empty(C)
        for i in range(out_w):
            for c in range(C):
                acc[c] = 0.0
            n0 = _clipped_footprint(M, float(i), float(j), W, H, P, B)
            if n0 >= 3:
                cx0, cx1, cy0, cy1 = _bbox_cells(P, n0, ox, oy, h, ncx, ncy)
                for cy in range(cy0, cy1 + 1):
                    y0 = oy + cy * h
                    for cx in range(cx0, cx1 + 1):
                        x0 = ox + cx * h
                        for q in range(n0):
                            A[q, 0] = (P[q, 0] - x0) / h
                            A[q, 1] = (P[q, 1] - y0) / h
                        n = _clip_unit_square(A, B, n0)
                        if n < 3:
                            continue
                        r0 = k * cy
                        c0 = k * cx
                        ax = A[0, 0]
                        ay = A[0, 1]
                        for t in range(1, n - 1):
                            bx = A[t, 0]
                            by = A[t, 1]
                            qx = A[t + 1, 0]
                            qy = A[t + 1, 1]
                            ta = 0.5 * abs((bx - ax) * (qy - ay) - (qx - ax) * (by - ay))
                            if ta == 0.0:
                                continue
                            if k == 0:
                                for c in range(C):
                                    acc[c] += ta * nodes[cy, cx, c]
                                continue
                            for p in range(6):
                                u = DL[p, 0] * ax + DL[p, 1] * bx + DL[p, 2] * qx
                                v = DL[p, 0] * ay + DL[p, 1] * by + DL[p, 2] * qy
                                _basis(k, u, lu)
                                _basis(k, v, lv)
                                w = DW[p] * ta
                                for b in range(k + 1):
                                    wb = w * lv[b]
                                    for a in range(k + 1):
                                        wab = wb * lu[a]
                                        for c in range(C):
                                            acc[c] += wab * nodes[r0 + b, c0 + a, c]
            for c in range(C):
                out[j, i, c] = acc[c] / fp_area


@njit(parallel=True, cache=True)
def lattice_point(nodes, k, ox, oy, h, W, H, M, out):
    out_h, out_w, C = out.shape
    for j in prange(out_h):
        lu = np.empty(3)
        lv = np.empty(3)
        for i in range(out_w):
            X = i + 0.5
            Y = j + 0.5
            px = M[0, 0] * X + M[0, 1] * Y + M[0, 2]
            py = M[1, 0] * X + M[1, 1] * Y + M[1, 2]
            if px < 0.0 or py < 0.0 or px > W or py > H:
                for c in range(C):
                    out[j, i, c] = 0.0
                continue
            sx = (px - ox) / h
            sy = (py - oy) / h
            cx = int(sx)
            cy = int(sy)
            if k == 0:
                for c in range(C):
                    out[j, i, c] = nodes[cy, cx, c]
                continue
            _basis(k, sx - cx, lu)
            _basis(k, sy - cy, lv)
            for c in range(C):
                s = 0.0
                for b in range(k + 1):
                    for a in range(k + 1):
                        s += lv[b] * lu[a] * nodes[k * cy + b, k * cx + a, c]
                out[j, i, c] = s


@njit(cache=True, inline="always")
def _fan_value(tri, u, v, grid, faces, cy, cx, c):
    V00 = grid[cy, cx, c]
    V10 = grid[cy, cx + 1, c]
    V01 = grid[cy + 1, cx, c]
    V11 = grid[cy + 1, cx + 1, c]
    F = faces[cy, cx, c]
    if tri == 0:  # top: tl, tr, centre
        return V00 + (V10 - V00) * u + (2 * F - V00 - V10) * v
    if tri == 1:  # right: tr, br, centre
        return V10 + (V11 - V10) * v + (2 * F - V10 - V11) * (1.0 - u)
    if tri == 2:  # bottom: bl, br, centre
        return V01 + (V11 - V01) * u + (2 * F - V01 - V11) * (1.0 - v)
    return V00 + (V01 - V00) * v + (2 * F - V00 - V01) * u  # left


@njit(parallel=True, cache=True)
def fan_area(grid, faces, ox, oy, h, W, H, M, out):
    """Exact AREA sampling of a centre-fan mesh over footprint ∩ image."""
    out_h, out_w, C = out.shape
    ncy, ncx = faces.shape[0], faces.shape[1]
    TP = _TRI_PLANES
    fp_area = abs(M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]) / (h * h)
    for j in prange(out_h):
        P = np.empty((24, 2))
        A = np.empty((24, 2))
        B = np.empty((24, 2))
        T1 = np.empty((24, 2))
        T2 = np.empty((24, 2))
        acc = np.empty(C)
        for i in range(out_w):
            for c in range(C):
                acc[c] = 0.0
            n0 = _clipped_footprint(M, float(i), float(j), W, H, P, B)
            if n0 >= 3:
                cx0, cx1, cy0, cy1 = _bbox_cells(P, n0, ox, oy, h, ncx, ncy)
                for cy in range(cy0, cy1 + 1):
                    y0 = oy + cy * h
                    for cx in range(cx0, cx1 + 1):
                        x0 = ox + cx * h
                        for q in range(n0):
                            A[q, 0] = (P[q, 0] - x0) / h
                            A[q, 1] = (P[q, 1] - y0) / h
                        n = _clip_unit_square(A, B, n0)
                        if n < 3:
                            continue
                        sq_area, _, _ = _poly_area_centroid(A, n)
                        if sq_area == 0.0:
                            continue
                        if sq_area > 1.0 - 1e-12:
                            for c in range(C):
                                acc[c] += ((grid[cy, cx, c] + grid[cy, cx + 1, c] + grid[cy + 1, cx, c]
                                            + grid[cy + 1, cx + 1, c]) / 6.0 + faces[cy, cx, c] / 3.0)
                            continue
                        for tri in range(4):
                            m = _clip(A, n, T1, TP[tri, 0, 0], TP[tri, 0, 1], TP[tri, 0, 2])
                            m = _clip(T1, m, T2, TP[tri, 1, 0], TP[tri, 1, 1], TP[tri, 1, 2])
                            if m < 3:
                                continue
                            pa, gx, gy = _poly_area_centroid(T2, m)
                            if pa == 0.0:
                                continue
                            for c in range(C):
                                acc[c] += pa * _fan_value(tri, gx, gy, grid, faces, cy, cx, c)
            for c in range(C):
                out[j, i, c] = acc[c] / fp_area


@njit(parallel=True, cache=True)
def fan_point(grid, faces, ox, oy, h, W, H, M, out):
    out_h, out_w, C = out.shape
    for j in prange(out_h):
        for i in range(out_w):
            X = i + 0.5
            Y = j + 0.5
            px = M[0, 0] * X + M[0, 1] * Y + M[0, 2]
            py = M[1, 0] * X + M[1, 1] * Y + M[1, 2]
            if px < 0.0 or py < 0.0 or px > W or py > H:
                for c in range(C):
                    out[j, i, c] = 0.0
                continue
            sx = (px - ox) / h
            sy = (py - oy) / h
            cx = int(sx)
            cy = int(sy)
            u = sx - cx
            v = sy - cy
            if abs(u - 0.5) >= abs(v - 0.5):
                tri = 1 if u >= 0.5 else 3
            else:
                tri = 2 if v >= 0.5 else 0
            for c in range(C):
                out[j, i, c] = _fan_value(tri, u, v, grid, faces, cy, cx, c)


# ---------------------------------------------------------------- classics

@njit(cache=True, inline="always")
def _keys(x):
    a = -0.5
    x = abs(x)
    if x < 1.0:
        return ((a + 2) * x - (a + 3)) * x * x + 1
    if x < 2.0:
        return ((a * x - 5 * a) * x + 8 * a) * x - 4 * a
    return 0.0


@njit(cache=True, inline="always")
def _lanczos3(x):
    if x == 0.0:
        return 1.0
    if abs(x) >= 3.0:
        return 0.0
    px = math.pi * x
    return 3.0 * math.sin(px) * math.sin(px / 3.0) / (px * px)


@njit(parallel=True, cache=True)
def classic_point(S, kind, M, out):
    """kind: 0 nearest, 1 bilinear, 2 Keys bicubic (a=-0.5), 3 Lanczos-3.

    Point samples on the original pixel grid (edge-clamped taps), transparent
    outside the source rectangle.
    """
    H, W, C = S.shape
    out_h, out_w, _ = out.shape
    for j in prange(out_h):
        wx = np.empty(6)
        wy = np.empty(6)
        for i in range(out_w):
            X = i + 0.5
            Y = j + 0.5
            px = M[0, 0] * X + M[0, 1] * Y + M[0, 2]
            py = M[1, 0] * X + M[1, 1] * Y + M[1, 2]
            if px < 0.0 or py < 0.0 or px > W or py > H:
                for c in range(C):
                    out[j, i, c] = 0.0
                continue
            x = px - 0.5
            y = py - 0.5
            if kind == 0:
                ix = min(max(int(math.floor(x + 0.5)), 0), W - 1)
                iy = min(max(int(math.floor(y + 0.5)), 0), H - 1)
                for c in range(C):
                    out[j, i, c] = S[iy, ix, c]
                continue
            r = kind  # support radius 1, 2, 3
            x0 = int(math.floor(x))
            y0 = int(math.floor(y))
            n = 2 * r
            sx_ = 0.0
            sy_ = 0.0
            for t in range(n):
                dx = x - (x0 - r + 1 + t)
                dy = y - (y0 - r + 1 + t)
                if kind == 1:
                    wx[t] = max(0.0, 1.0 - abs(dx))
                    wy[t] = max(0.0, 1.0 - abs(dy))
                elif kind == 2:
                    wx[t] = _keys(dx)
                    wy[t] = _keys(dy)
                else:
                    wx[t] = _lanczos3(dx)
                    wy[t] = _lanczos3(dy)
                sx_ += wx[t]
                sy_ += wy[t]
            for c in range(C):
                s = 0.0
                for b in range(n):
                    yy = min(max(y0 - r + 1 + b, 0), H - 1)
                    row = 0.0
                    for a in range(n):
                        xx = min(max(x0 - r + 1 + a, 0), W - 1)
                        row += wx[a] * S[yy, xx, c]
                    s += wy[b] * row
                out[j, i, c] = s / (sx_ * sy_)
