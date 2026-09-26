"""Affine transforms composed in continuous coordinates, and output canvases.

A transform is a 3x3 matrix T mapping source coordinates to output (world)
coordinates. Operations are composed *before* rasterization, so any chain
(rotate, scale, rotate, translate, ...) is rendered from the mesh exactly once.

Conventions: x to the right, y down; positive angles rotate
counter-clockwise on screen; rotation and scaling act about the current image
centre (the centre of the source image mapped by the operations so far).
"""

from __future__ import annotations

import math

import numpy as np


def rotation(deg, cx=0.0, cy=0.0):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if abs(c) < 1e-15:
        c = 0.0
    if abs(s) < 1e-15:
        s = 0.0
    R = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    return translation(cx, cy) @ R @ translation(-cx, -cy)


def scaling(sx, sy=None, cx=0.0, cy=0.0):
    sy = sx if sy is None else sy
    if sx == 0 or sy == 0:
        raise ValueError("scale factors must be non-zero")
    S = np.diag([float(sx), float(sy), 1.0])
    return translation(cx, cy) @ S @ translation(-cx, -cy)


def translation(tx, ty):
    return np.array([[1.0, 0.0, tx], [0.0, 1.0, ty], [0.0, 0.0, 1.0]])


class Chain:
    """Builder for a composed source -> output transform."""

    def __init__(self, width, height):
        self.W, self.H = width, height
        self.T = np.eye(3)

    def centre(self):
        c = self.T @ np.array([self.W / 2.0, self.H / 2.0, 1.0])
        return c[0], c[1]

    def rotate(self, deg):
        self.T = rotation(deg, *self.centre()) @ self.T
        return self

    def scale(self, sx, sy=None):
        self.T = scaling(sx, sy, *self.centre()) @ self.T
        return self

    def scale_about(self, sx, sy, px, py):
        self.T = scaling(sx, sy, px, py) @ self.T
        return self

    def corner(self):
        c = self.T @ np.array([0.0, 0.0, 1.0])
        return c[0], c[1]

    def translate(self, tx, ty):
        self.T = translation(tx, ty) @ self.T
        return self

    def affine(self, a, b, c, d, e, f):
        self.T = np.array([[a, b, c], [d, e, f], [0, 0, 1.0]]) @ self.T
        return self


def canvas(T, W, H, mode="expand", size=None):
    """Return (M, (h, w)): M maps output pixel coords -> source coords.

    expand : bounding box of the transformed image (integer aligned; keeps
             the sub-pixel phase of translations)
    same   : W x H canvas centred on the transformed image centre
    size   : explicit (w, h) canvas centred on the transformed image centre
    """
    corners = np.array([[0, 0, 1], [W, 0, 1], [W, H, 1], [0, H, 1]], dtype=np.float64)
    t = corners @ T.T
    if mode == "expand" and size is None:
        lo = np.floor(t[:, :2].min(axis=0) + 1e-6)
        hi = np.ceil(t[:, :2].max(axis=0) - 1e-6)
        w, h = (hi - lo).astype(int)
        origin = lo
    else:
        w, h = (W, H) if size is None else size
        c = T @ np.array([W / 2.0, H / 2.0, 1.0])
        origin = np.array([c[0] - w / 2.0, c[1] - h / 2.0])
    Ti = np.linalg.inv(T)
    M = np.empty((2, 3))
    M[:, :2] = Ti[:2, :2]
    M[:, 2] = Ti[:2, :2] @ origin + Ti[:2, 2]
    return M, (int(h), int(w))
