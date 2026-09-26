#!/usr/bin/env python
"""RGB mesh resampling demo: scale, resize, rotate or translate any image.

Examples
--------
  python demo.py photo.jpg --rotate 17.3                     # default method m13zf
  python demo.py photo.jpg --scale 3 --method m41zf
  python demo.py photo.jpg --scale 0.37                      # downscale
  python demo.py photo.jpg --resize 1920x1080                # exact output size (non-uniform ok)
  python demo.py photo.jpg --rotate 30 --scale 2 --rotate -12 --translate 0.5 0
                                                             # composed, rasterized once
  python demo.py photo.jpg --rotate 33 --compare m13zf m09z bicubic lanczos3 box \\
                 --crop 400 300 160 120 --crop-zoom 4        # side-by-side sheet
  python demo.py photo.jpg --rotate 25 --zdiff               # Z-calibration difference ("edge") image
  python demo.py photo.jpg --rotate 30 --repeat 12           # 12x30 deg: re-rasterize vs compose
  python demo.py --make-test-image chart.png                 # synthetic chart with thin lines and text
  python demo.py --list-methods

Operations (--rotate / --scale / --resize / --translate / --affine) are applied
in the order given, about the current image centre, and composed into one
affine map. The mesh is built once and every output pixel is the exact
average of the continuous field over its footprint.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

import rgbmesh as rm
from rgbmesh.imageio import linear_to_srgb, srgb_to_linear


class OrderedOp(argparse.Action):
    """Collect transform operations in command-line order."""

    def __call__(self, parser, ns, values, option_string=None):
        ops = getattr(ns, "ops", None) or []
        ops.append((self.dest, values))
        setattr(ns, "ops", ops)


def build_chain(ops, W, H):
    ch = rm.Chain(W, H)
    cur_w, cur_h = float(W), float(H)
    for name, v in ops:
        if name == "rotate":
            ch.rotate(float(v))
        elif name == "scale":
            sx = float(v[0])
            sy = float(v[1]) if len(v) > 1 else sx
            ch.scale(sx, sy)
            cur_w, cur_h = cur_w * abs(sx), cur_h * abs(sy)
        elif name == "resize":
            w, h = parse_size(v)
            ch.scale_about(w / cur_w, h / cur_h, *ch.corner())   # keep the top-left corner fixed
            cur_w, cur_h = float(w), float(h)
        elif name == "translate":
            ch.translate(float(v[0]), float(v[1]))
        elif name == "affine":
            ch.affine(*map(float, v))
    return ch.T


def parse_size(text):
    w, h = text.lower().split("x")
    return int(w), int(h)


def psnr_srgb(a, b, mask):
    """PSNR of straight sRGB colour inside mask (8-bit style, peak 1)."""
    da = linear_to_srgb(np.clip(a[..., :3], 0, 1))[mask]
    db = linear_to_srgb(np.clip(b[..., :3], 0, 1))[mask]
    mse = float(np.mean((da - db) ** 2))
    return 99.0 if mse == 0 else 10 * math.log10(1 / mse)


def interior_mask(H, W, margin, *alphas):
    m = np.zeros((H, W), bool)
    m[margin:H - margin, margin:W - margin] = True
    for a in alphas:
        m &= a[..., 3] > 0.999
    return m


def run_method(method, img, M, shape, dtype):
    t0 = time.perf_counter()
    fld = rm.build_field(method, img, dtype=dtype)
    t1 = time.perf_counter()
    out = rm.render(fld, method, M, shape)
    t2 = time.perf_counter()
    return out, (t1 - t0) * 1000, (t2 - t1) * 1000, fld.nbytes / 2 ** 20


def warmup(methods):
    s = np.random.default_rng(0).random((6, 7, 4))
    M = np.array([[0.9, 0.2, -0.3], [-0.2, 0.9, 0.4]])
    for m in methods:
        rm.render(rm.build_field(m, s), m, M, (5, 5))


def zdiff_image(method, img, M, shape, dtype):
    """Luminance of (calibrated - uncalibrated) output as a signed heat map."""
    base = rm.Z_PAIRS.get(method.split("@")[0])
    if base is None:
        return None, None
    a, *_ = run_method(method, img, M, shape, dtype)
    b, *_ = run_method(base, img, M, shape, dtype)
    d = a[..., :3] - b[..., :3]
    lum = d @ np.array([0.2126, 0.7152, 0.0722])
    s = np.percentile(np.abs(lum), 99.5) or 1.0
    e = lum / s
    rgb = np.stack((np.clip(e, 0, 1), np.zeros_like(e), np.clip(-e, 0, 1)), axis=-1)
    heat = np.concatenate((srgb_to_linear(np.sqrt(rgb)), np.ones(lum.shape + (1,))), axis=-1)
    return heat, base


def contact_sheet(tiles, path, crop, zoom, bg):
    from PIL import Image, ImageDraw
    ims = []
    for label, img in tiles:
        if crop:
            x, y, w, h = crop
            img = img[y:y + h, x:x + w]
        arr = np.round(rm.imageio.to_display(img, bg if bg is not None else (1.0, 1.0, 1.0)) * 255).astype(np.uint8)
        im = Image.fromarray(arr[..., :3], "RGB")
        if zoom > 1:
            im = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
        ims.append((label, im))
    cols = min(4, len(ims))
    rows = math.ceil(len(ims) / cols)
    tw = max(i.width for _, i in ims)
    th = max(i.height for _, i in ims)
    pad, lab = 8, 22
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + lab + pad) + pad), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    for k, (label, im) in enumerate(ims):
        cx = pad + (k % cols) * (tw + pad)
        cy = pad + (k // cols) * (th + lab + pad)
        draw.text((cx, cy + 3), label, fill=(20, 20, 20))
        sheet.paste(im, (cx, cy + lab))
    sheet.save(path)


def make_test_image(path, size=(960, 640), ss=8):
    """Synthetic chart drawn at ss x resolution and box-filtered in linear light."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = size
    big = Image.new("RGB", (W * ss, H * ss), (235, 235, 230))
    d = ImageDraw.Draw(big)
    S = lambda v: int(round(v * ss))
    cols = [(220, 30, 30), (30, 150, 50), (40, 60, 220), (20, 20, 20), (200, 40, 180), (240, 140, 20)]
    # colour bars
    bars = [(200, 200, 200), (205, 205, 0), (0, 205, 205), (0, 205, 0), (205, 0, 205), (205, 0, 0), (0, 0, 205), (0, 0, 0)]
    bw = W * 0.9 / len(bars)
    for i, c in enumerate(bars):
        d.rectangle([S(W * 0.05 + i * bw), S(20), S(W * 0.05 + (i + 1) * bw), S(80)], fill=c)
    # thin lines at many angles and widths (a fan)
    cx, cy, r = W * 0.22, H * 0.5, H * 0.3
    for k, ang in enumerate(np.arange(0, 180, 7.5)):
        wdt = [0.5, 0.75, 1.0, 1.5, 2.0][k % 5]
        a = math.radians(ang)
        d.line([S(cx + 0.15 * r * math.cos(a)), S(cy - 0.15 * r * math.sin(a)),
                S(cx + r * math.cos(a)), S(cy - r * math.sin(a))], fill=cols[k % len(cols)], width=max(1, S(wdt)))
    # rings of different thickness
    for k, t in enumerate([0.5, 1.0, 2.0, 3.0]):
        x0, y0, rr = W * 0.47, H * 0.28 + k * H * 0.17, H * 0.065
        d.ellipse([S(x0 - rr), S(y0 - rr), S(x0 + rr), S(y0 + rr)], outline=cols[k], width=max(1, S(t)))
    # Siemens star
    sx, sy, sr = W * 0.62, H * 0.5, H * 0.2
    for k in range(24):
        a0, a1 = 2 * math.pi * k / 24, 2 * math.pi * (k + 0.5) / 24
        d.polygon([(S(sx), S(sy)), (S(sx + sr * math.cos(a0)), S(sy + sr * math.sin(a0))),
                   (S(sx + sr * math.cos(a1)), S(sy + sr * math.sin(a1)))], fill=(0, 0, 0))
    # text of several sizes
    y = H * 0.33
    for px in (28, 18, 12, 9):
        try:
            font = ImageFont.load_default(size=S(px))
        except TypeError:  # Pillow < 10.1
            font = ImageFont.load_default()
        d.text((S(W * 0.77), S(y)), f"RGB mesh {px}px", fill=(20, 20, 20), font=font)
        y += px * 1.9
    # gradient strip
    g = np.linspace(0, 1, W * ss)
    arr = np.asarray(big).copy()
    y0, y1 = S(H - 70), S(H - 40)
    arr[y0:y1, :, 0] = (255 * g).astype(np.uint8)
    arr[y0:y1, :, 1] = (255 * (1 - g)).astype(np.uint8)
    arr[y0:y1, :, 2] = 128
    # 1-px vertical/horizontal line groups at the bottom
    for k in range(40):
        x = S(W * 0.05) + k * S(2.0 + 0.1 * k)
        arr[S(H - 30):S(H - 8), x:x + ss] = 0
    lin = srgb_to_linear(arr / 255.0).reshape(H, ss, W, ss, 3).mean(axis=(1, 3))
    out = np.concatenate((lin, np.ones((H, W, 1))), axis=-1)
    rm.save(path, out, background=(0.0, 0.0, 0.0))   # opaque RGB file
    return path


def main(argv=None):
    p = argparse.ArgumentParser(description="RGB mesh resampling demo",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("input", nargs="?", help="input image (any format Pillow reads)")
    p.add_argument("-o", "--output", help="output file (default: <input>_<method>.png)")
    g = p.add_argument_group("transform operations (applied in the given order, composed)")
    g.add_argument("--rotate", action=OrderedOp, metavar="DEG", help="rotate (degrees, CCW positive)")
    g.add_argument("--scale", action=OrderedOp, nargs="+", metavar="S", help="scale (one factor, or SX SY)")
    g.add_argument("--resize", action=OrderedOp, metavar="WxH", help="scale to an exact size (top-left anchored)")
    g.add_argument("--translate", action=OrderedOp, nargs=2, metavar=("TX", "TY"), help="translate (pixels)")
    g.add_argument("--affine", action=OrderedOp, nargs=6, metavar="V", help="extra affine a b c d e f")
    p.add_argument("--canvas", default="expand", help="expand (default) | same | WxH")
    p.add_argument("--method", default=rm.DEFAULT_METHOD, help=f"resampling method (default {rm.DEFAULT_METHOD})")
    p.add_argument("--compare", nargs="+", metavar="METHOD", help="render several methods ('all' = every method)")
    p.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "W", "H"), help="crop of the output for the sheet")
    p.add_argument("--crop-zoom", type=int, default=1, help="nearest-neighbour magnification of sheet tiles")
    p.add_argument("--zdiff", action="store_true", help="also write the Z-calibration difference image")
    p.add_argument("--roundtrip", action="store_true", help="apply the inverse afterwards (re-rasterized) and report PSNR")
    p.add_argument("--repeat", type=int, default=1, help="apply the chain N times: re-rasterize vs compose once")
    p.add_argument("--background", default="transparent", help="transparent (default) | #rrggbb | white | black")
    p.add_argument("--float32", action="store_true", help="store the mesh in float32 (half memory)")
    p.add_argument("--out-dir", default="demo_output", help="directory for --compare/--zdiff/--repeat outputs")
    p.add_argument("--make-test-image", metavar="PATH", help="write a synthetic test chart and use it as input")
    p.add_argument("--list-methods", action="store_true")
    a = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    if a.list_methods:
        for m in rm.METHODS.values():
            star = "*" if m.id == rm.DEFAULT_METHOD else " "
            print(f"{star} {m.id:9s} {m.sampling:5s} {m.points:2d} pts  Z={m.z:5s}  {m.description}")
        print("\nAppend @pt to a mesh method for point sampling instead of area integration.")
        return 0
    if a.make_test_image:
        print(f"test chart -> {make_test_image(a.make_test_image)}")
        a.input = a.input or a.make_test_image
        if not getattr(a, "ops", None):
            return 0
    if not a.input:
        p.error("an input image is required")

    img, has_alpha = rm.load(a.input)
    H, W = img.shape[:2]
    ops = getattr(a, "ops", None) or []
    T = build_chain(ops, W, H)
    if a.canvas in ("expand", "same"):
        M, shape = rm.canvas(T, W, H, a.canvas)
    else:
        M, shape = rm.canvas(T, W, H, size=parse_size(a.canvas))
    bg = rm.parse_color(a.background)
    dtype = np.float32 if a.float32 else np.float64
    methods = a.compare or [a.method]
    if methods == ["all"]:
        methods = list(rm.METHODS)
    for m in methods:
        if m.split("@")[0] not in rm.METHODS:
            p.error(f"unknown method {m!r} (see --list-methods)")
    stem = Path(a.input).stem
    out_dir = Path(a.out_dir)
    desc = " ".join(f"{n} {v if isinstance(v, str) else ' '.join(v)}" for n, v in ops) or "identity"
    print(f"input  {a.input}: {W}x{H}{' (alpha)' if has_alpha else ''}")
    print(f"chain  {desc}  ->  output {shape[1]}x{shape[0]}")

    t = time.perf_counter()
    warmup(set(methods) | ({rm.Z_PAIRS[m] for m in methods if m in rm.Z_PAIRS} if a.zdiff else set()))
    print(f"(numba compile/warm-up {time.perf_counter() - t:.1f}s)\n")
    print(f"{'method':10s} {'build ms':>9s} {'render ms':>10s} {'ms/Mpx':>8s} {'mesh MB':>8s}  file")

    results = []
    for m in methods:
        out, bms, rms, mb = run_method(m, img, M, shape, dtype)
        if a.output and len(methods) == 1:
            path = Path(a.output)
        else:
            path = (out_dir if a.compare else Path(a.input).parent) / f"{stem}_{m.replace('@', '_')}.png"
        rm.save(path, out, bg)
        mpx = shape[0] * shape[1] / 1e6
        print(f"{m:10s} {bms:9.1f} {rms:10.1f} {rms / max(mpx, 1e-9):8.1f} {mb:8.1f}  {path}")
        results.append((m, out))

        if a.zdiff:
            heat, base = zdiff_image(m, img, M, shape, dtype)
            if heat is not None:
                zp = out_dir / f"{stem}_zdiff_{m}-{base}.png"
                rm.save(zp, heat)
                print(f"{'':10s} Z-difference {m} - {base} -> {zp}")

        if a.roundtrip:
            # inverse pass: original grid -> step-1 output pixel coordinates
            M2 = np.linalg.inv(np.vstack((M, [0, 0, 1])))[:2]
            back = rm.render(rm.build_field(m, out, dtype), m, M2, (H, W))
            mask = interior_mask(H, W, 4, back)
            print(f"{'':10s} round trip (re-rasterized): PSNR {psnr_srgb(back, img, mask):.2f} dB (sRGB, interior)")

    if a.repeat > 1:
        m = methods[0]
        Tn = np.linalg.matrix_power(T, a.repeat)
        Mn, shape_n = rm.canvas(Tn, W, H, "same")
        t = time.perf_counter()
        composed = rm.render(rm.build_field(m, img, dtype), m, Mn, shape_n)
        tc = time.perf_counter() - t
        # repeated: rasterize every step on a same-size canvas
        Ms, shape_s = rm.canvas(T, W, H, "same")
        cur = img
        t = time.perf_counter()
        for _ in range(a.repeat):
            cur = rm.render(rm.build_field(m, cur, dtype), m, Ms, shape_s)
        tr = time.perf_counter() - t
        out_dir.mkdir(parents=True, exist_ok=True)
        rm.save(out_dir / f"{stem}_{m}_x{a.repeat}_composed.png", composed, bg)
        rm.save(out_dir / f"{stem}_{m}_x{a.repeat}_rerasterized.png", cur, bg)
        print(f"\nrepeat x{a.repeat} with {m}: composed once {tc:.2f}s, re-rasterized each step {tr:.2f}s")
        if np.allclose(Tn[:2, :2], np.eye(2), atol=1e-9) and np.allclose(Tn[:2, 2], 0, atol=1e-6):
            yy, xx = np.mgrid[0:H, 0:W]
            disk = np.hypot(xx + 0.5 - W / 2, yy + 0.5 - H / 2) < min(W, H) / 2 - 6
            mask = disk & interior_mask(H, W, 4, composed, cur)
            print(f"  chain is the identity -> PSNR vs original: composed {psnr_srgb(composed, img, mask):.2f} dB, "
                  f"re-rasterized {psnr_srgb(cur, img, mask):.2f} dB")

    if a.compare and len(results) > 1:
        sheet = out_dir / f"{stem}_compare.png"
        contact_sheet(results, sheet, a.crop, a.crop_zoom, bg)
        print(f"\ncomparison sheet -> {sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
