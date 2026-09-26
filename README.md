# RGB Mesh Resampling

Experimental image reconstruction and resampling based on a continuous RGB mesh built from pixel-centre samples.

The project explores a simple idea: instead of treating a raster pixel as a coloured square, treat its RGB value as a sample at the pixel centre, reconstruct a continuous local surface, and resample transformed output pixels by integrating that surface over their source-space footprints.

The code and experiments are intended to make the method reproducible and to compare it against standard resampling methods without claiming that any one reconstruction is the unique ground truth for real photographs.

## Core model

For a source pixel value `P[i,j]`, the sample location is the pixel centre.

Each source pixel cell is reconstructed as a 9-node biquadratic (`Q2`) patch:

- 4 corner nodes,
- 4 edge-midpoint nodes,
- 1 centre node (the original pixel sample).

Corner nodes are reconstructed from the four surrounding pixel-centre samples. Edge-midpoint nodes are reconstructed from the two adjacent pixel centres and the two edge endpoints.

The resulting 3×3 node set defines a tensor-product quadratic surface in linear-light RGB.

Two main variants are studied:

- **raw Q2** — no area correction;
- **conservative Q2** — the centre node is adjusted once so that the exact area average of the Q2 cell equals the original source pixel value.

For a unit cell with corner sum `ΣV`, edge-midpoint sum `ΣE`, and centre `C`, the Q2 cell average is

```text
A = (ΣV + 4 ΣE + 16 C) / 36
```

and the conservative centre correction is

```text
C' = C + (36/16) (P - A)
```

No intermediate clamping is required; calculations are performed in floating-point linear light.

## Resampling

An output pixel is treated as an area footprint, not just a point.

For an affine transform, the output pixel footprint is inverse-mapped into source coordinates and the reconstructed field is averaged over that footprint:

```text
P_out = (1 / area(Ω)) ∫∫_Ω C(x,y) dx dy
```

This allows the same continuous field to be used for rotation, translation, scaling, and combined affine transforms.

## Refinement experiments

The repository also studies denser explicit representations of the same reconstructed field:

- 9-node Q2,
- 13-node centre-fan triangulation,
- 25-node subdivided Q2 representation,
- 41-node centre-fan triangulation.

A key distinction is kept between:

1. **subdivision of a fixed reconstructed field**, and
2. **re-calibration after refinement**, which creates a different field.

The 25-node Q2 subdivision of a fixed Q2 surface is numerically equivalent to the original 9-node Q2 representation.

## Validation

The experimental framework uses both real images and analytically generated scenes with known geometry. Measurements include:

- PSNR / SSIM / ΔE,
- colour bias and saturation preservation,
- edge width and overshoot,
- thin-line thickness and peak contrast,
- positional and shape deformation,
- grid-dependent wobble,
- Siemens-star behaviour,
- round-trip and cumulative-transform error.

The conservative correction is also analysed directly through the difference between corrected and uncorrected fields.

## Status

This repository is an experimental research implementation. The mathematical construction is documented in [METHOD.md](METHOD.md).

The complete benchmark code used during development is being prepared for publication here together with a small runnable reference implementation.

## Related concepts

The method is related to, but not identical with:

- cell-centred to nodal reconstruction,
- Q2 finite-element interpolation,
- conservative remapping / finite-volume ideas,
- reconstruction filtering,
- area / footprint resampling.

A literature comparison is still needed before making any claim of novelty.

## License

MIT.
