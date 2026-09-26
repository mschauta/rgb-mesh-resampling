import numpy as np
import pytest

import rgbmesh as rm
from rgbmesh.core import PAD, build_q2_lattice, q2_cell_means

RNG = np.random.default_rng(3)
IMG = np.concatenate((RNG.random((11, 13, 3)), np.ones((11, 13, 1))), axis=-1)
IDENTITY = np.array([[1.0, 0, 0], [0, 1.0, 0]])
AREA = ["box", "tent", "m09", "m09z", "m09z_13", "m09z_41", "m13", "m41", "m13zf", "m25zf", "m41zf"]
CALIBRATED = ["box", "m09z", "m13zf", "m25zf", "m41zf"]


def _dense(field, method, M, shape, n):
    """Midpoint supersampling of the point-evaluated field (independent reference)."""
    Ms = M.copy()
    Ms[:, :2] /= n
    fine = rm.render(field, method, Ms, (shape[0] * n, shape[1] * n), sampling="point")
    return fine.reshape(shape[0], n, shape[1], n, -1).mean(axis=(1, 3))


@pytest.mark.parametrize("method", CALIBRATED)
def test_identity_area_returns_the_source(method):
    out = rm.resample(IMG, IDENTITY, IMG.shape[:2], method)
    assert np.abs(out - IMG).max() < 1e-12


@pytest.mark.parametrize("method", ["nearest", "bilinear", "bicubic", "lanczos3", "m09@pt"])
def test_identity_point_sampling_returns_centre_samples(method):
    out = rm.resample(IMG, IDENTITY, IMG.shape[:2], method)
    assert np.abs(out - IMG).max() < 1e-12


@pytest.mark.parametrize("method", AREA)
def test_exact_area_matches_dense_sampling_inside(method):
    T = rm.Chain(13, 11).rotate(23.7).scale(1.3).T
    M, shape = rm.canvas(T, 13, 11)
    field = rm.build_field(method, IMG)
    exact = rm.render(field, method, M, shape)
    inside = exact[..., 3] > 1 - 1e-12        # footprint completely inside the image
    e24 = np.abs(exact - _dense(field, method, M, shape, 24))[inside].max()
    e48 = np.abs(exact - _dense(field, method, M, shape, 48))[inside].max()
    assert e48 < (4e-3 if method == "box" else 4e-4)
    assert e48 < e24


@pytest.mark.parametrize("method", ["box", "m09z", "m13zf", "m41zf"])
@pytest.mark.parametrize("angle,scale", [(17.3, 1.0), (45.0, 2.0), (33.0, 0.6)])
def test_alpha_is_exact_geometric_coverage(method, angle, scale):
    H, W = IMG.shape[:2]
    T = rm.Chain(W, H).rotate(angle).scale(scale).T
    M, shape = rm.canvas(T, W, H)
    out = rm.resample(IMG, M=M, shape=shape, method=method)
    # sum of coverage * output pixel area = area of the transformed image
    assert abs(out[..., 3].sum() - W * H * scale * scale) < 1e-8 * W * H


def test_calibration_conserves_pixel_means():
    P = np.pad(IMG, ((PAD, PAD), (PAD, PAD), (0, 0)), mode="edge")
    L = rm.core.z_correct_q2(build_q2_lattice(P), P)
    assert np.abs(q2_cell_means(L) - P).max() < 1e-13


def test_chain_composition_is_exact():
    img = IMG
    H, W = img.shape[:2]
    T = rm.Chain(W, H).rotate(30).T
    T12 = np.linalg.matrix_power(T, 12)
    M, shape = rm.canvas(T12, W, H, "same")
    out = rm.resample(img, M, shape, "m13zf")
    assert shape == (H, W)
    assert np.abs(out - img).max() < 1e-9


def test_resize_gives_exact_size():
    T = rm.Chain(13, 11).scale_about(40 / 13, 7 / 11, 0, 0).T
    M, shape = rm.canvas(T, 13, 11)
    assert shape == (7, 40)
