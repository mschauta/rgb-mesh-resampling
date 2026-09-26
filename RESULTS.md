# Preliminary benchmark results

These results are preliminary and describe the current experimental implementation, not a universal ranking of image resamplers.

The benchmark contained **17 methods**, **59 transforms**, **4 images/scenes** and **3162 result rows**. The main synthetic scenes have known geometry and a separately rendered reference; one real photograph is used for cumulative-resampling checks. The source scenes are quantized to 8-bit sRGB before reconstruction, so the source raster itself already differs slightly from the unquantized scene reference.

The report aggregates many different properties. A method can therefore be better by one criterion and worse by another. That is expected and is useful: the goal is to understand what the mesh representation preserves, not to force a single method to win every test.

## 1. Overall result

The current report's composite quality rank places the methods in this order at the top:

| Method | Mean quality rank ↓ | Linear PSNR dB ↑ | SSIM ↑ | Mean ΔE00 ↓ | Deformation RMS px ↓ | Render ms/Mpx ↓ |
|---|---:|---:|---:|---:|---:|---:|
| **m41zf** | **4.769** | 49.853 | 0.996189 | **0.16150** | **0.02550** | 191.7 |
| **m25zf** | 5.077 | 49.797 | 0.996112 | 0.16159 | 0.02555 | 145.6 |
| **m13zf** | 5.846 | 49.752 | 0.996056 | 0.16240 | 0.02559 | 76.1 |
| **m09z** | 5.923 | 49.335 | 0.995840 | 0.16838 | 0.02640 | 66.0 |
| **Lanczos-3** | 6.077 | **50.756** | 0.995833 | 0.17403 | 0.02816 | 21.9 |
| **bicubic** | 7.385 | 49.473 | **0.996282** | 0.16647 | 0.02685 | 9.4 |
| bilinear | 10.000 | 45.195 | 0.994830 | 0.21025 | 0.03379 | **8.0** |
| m09 (no Z) | 11.308 | 43.145 | 0.993767 | 0.26505 | 0.03778 | 65.7 |

The important point is that **m41zf does not win every metric**.

- Lanczos-3 has the best aggregate linear PSNR.
- Bicubic has the best aggregate SSIM.
- m41zf has the lowest mean and p95 ΔE00 among the tested methods, the smallest deformation RMS, the lowest line wobble, and very strong thickness preservation.
- Lanczos-3 is better in the aggregate edge-width metric, Siemens-star RMSE and thickness-modulation metric.
- The final-grid Z-calibrated mesh family is strongest when several colour, geometry and thin-feature metrics are considered together.

The composite rank should therefore be read as a convenient multi-metric summary, not as a proof that one method is universally superior.

### Important ranking caveat

The current rank aggregation is sensitive to tiny floating-point differences.

For example, `m09` and `m25` are mathematically the same Q2 surface and have effectively identical metrics, yet their reported mean ranks differ slightly. The same is true for `m09z` and `m09z_25`.

This means the reporting code should eventually use **tolerance-based ties** or effect-size normalization. A numerically meaningless difference should not earn a full rank position.

For this reason, the small rank difference between m41zf, m25zf and m13zf should not be over-interpreted.

## 2. What appears to create the gain

The experiments distinguish three different operations:

1. constructing the raw continuous Q2 field;
2. subdividing/refining that field;
3. applying area calibration (Z correction).

The results strongly suggest that **plain Q2 refinement is not the source of the quality gain**.

The 25-point Q2 subdivision is numerically equivalent to the original 9-point Q2 surface. Accordingly:

- `m25 ≡ m09`;
- `m09z_25 ≡ m09z`.

They are slower and consume more memory, but do not create a better field.

By contrast, applying area calibration on the **final, finer mesh** changes the field:

```text
raw reconstruction
        ↓
fine representation
        ↓
final-grid area calibration
        ↓
m13zf / m25zf / m41zf
```

These final-grid calibrated variants consistently outperform their uncorrected counterparts in the current benchmark.

The working interpretation is therefore:

> The useful ingredient is not denser Q2 sampling by itself, but **conservative spatial recalibration represented at finer spatial resolution**.

## 3. Final-grid calibration versus refinement of a 9Z field

Two superficially similar constructions behave differently.

### A. Correct once at 9 points, then refine

Examples:

- `m09z_13`
- `m09z_25`
- `m09z_41`

Here the refined nodes are sampled from the already corrected 9-point field.

### B. Build the final mesh and calibrate it there

Examples:

- `m13zf`
- `m25zf`
- `m41zf`

The benchmark clearly favours the second approach.

In particular, `m09z_25` is exactly the same Q2 field as `m09z`; refinement alone adds no new behaviour. The 13- and 41-point fan approximations inherited from the 9Z field also perform worse than their final-grid-calibrated counterparts.

This is evidence that final-grid calibration is not merely a numerical convenience. It defines a different reconstructed field.

## 4. Rotation

From 0.5° to 89°, no tested high-quality method shows a catastrophic angle-specific failure.

Linear-PSNR variation over that interval:

| Method | Mean PSNR dB | Range dB |
|---|---:|---:|
| Lanczos-3 | 52.103 | **0.518** |
| bicubic | 50.433 | 0.716 |
| m41zf | 50.108 | 0.845 |
| m25zf | 50.098 | 0.847 |
| m13zf | 50.067 | 0.871 |
| m09z | 49.854 | 1.036 |

The raw, uncorrected meshes can be even flatter with angle, but at much lower absolute quality; flatness alone is therefore not a quality measure.

The `m09z` curve has a visible dip around 40–50°. Refining and calibrating on the final grid reduces this effect, although Lanczos remains flatter by PSNR.

So the current evidence supports **good rotational isotropy**, but not the stronger claim that the mesh is the most angle-invariant method by every metric.

## 5. Scaling

Linear PSNR for selected methods:

| Scale | m41zf | m09z | Lanczos-3 | bicubic | bilinear |
|---:|---:|---:|---:|---:|---:|
| 0.50× | **67.07** | **67.07** | 42.05 | 45.64 | **67.07** |
| 0.75× | **53.26** | 53.06 | 49.95 | 51.78 | 48.84 |
| 1.50× | 46.54 | 45.73 | **48.78** | 46.69 | 42.00 |
| 2× | 45.06 | 45.07 | **47.05** | 45.18 | 40.88 |
| 3× | 43.73 | 42.48 | **46.00** | 44.29 | 40.71 |
| 4× | 43.58 | 41.65 | **45.54** | 43.87 | 40.17 |
| 5× | 43.58 | 41.29 | **45.34** | 43.70 | 40.16 |

### Downscaling

The final-grid calibrated meshes are very strong in downscaling.

At 0.75×, m41zf reaches about 53.26 dB, ahead of bicubic (~51.78 dB) and Lanczos-3 (~49.95 dB).

The 0.50× result needs special caution. Bilinear, box-area and the Z-calibrated meshes all reach the same ~67.07 dB. This is an alignment/sampling special case of the benchmark geometry, not evidence that bilinear is generally an ideal downsampler.

The 0.75× result is therefore more informative about general downscaling behaviour than the exact 0.50× case.

### Upscaling

The picture reverses for strong magnification.

Lanczos-3 has the best PSNR from 1.5× through 5×. Bicubic is also strong. The fine calibrated mesh improves substantially over m09z at 4–5×, but does not overtake Lanczos.

At 5×:

```text
Lanczos-3  45.34 dB
bicubic    43.70 dB
m41zf      43.58 dB
m25zf      42.42 dB
m13zf      41.98 dB
m09z       41.29 dB
```

Thus the current method is best understood as a continuous, conservative resampling representation, **not as a super-resolution method**.

## 6. Source blur changes the winner

The benchmark contains synthetic scenes with σ = 0, 0.6 and 1.2 Gaussian blur.

| σ | m41zf | m25zf | m13zf | m09z | Lanczos-3 | bicubic |
|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | **38.98** | 38.97 | 38.94 | 38.87 | 38.17 | 38.37 |
| 0.6 | 50.90 | 50.85 | 50.78 | 50.38 | **53.92** | 50.73 |
| 1.2 | 59.68 | 59.57 | 59.53 | 58.76 | **60.18** | 59.32 |

This is one of the clearest results in the benchmark:

- on the sharp scene, the calibrated mesh variants lead;
- once the source is already blurred, Lanczos becomes better by PSNR.

This makes physical sense. The mesh calibration helps reconstruct and preserve sharp, spatially localized transitions. When the source field has already been strongly low-pass filtered, a classical band-limited reconstruction becomes a very good match.

This crossover is a strength of the benchmark, not a weakness of the method: it shows that the test can distinguish regimes instead of declaring one algorithm universally best.

## 7. Colour and thin structures

The final-grid Z-calibrated meshes preserve colour very well.

Overall:

- m41zf chroma ratio: ~1.0009;
- m25zf: ~1.0009;
- m13zf: ~1.0009;
- m09z: ~1.0012.

The raw meshes are systematically lower:

- m09: ~0.9843;
- m41: ~0.9835;
- m13: ~0.9816.

The thin-line peak-ratio metric shows the same effect:

- m09z: ~0.982;
- m13zf/m25zf/m41zf: ~0.968–0.970;
- m09: ~0.895;
- m41: ~0.891;
- m13: ~0.879.

Lanczos-3 is also excellent on this metric (~0.988).

The interpretation is that area calibration restores much of the contrast/colour energy lost by the uncorrected smooth mesh.

## 8. Geometry

The best overall deformation RMS values are clustered tightly:

```text
m41zf     0.02550 px
m25zf     0.02555 px
m13zf     0.02559 px
m09z      0.02640 px
bicubic   0.02685 px
Lanczos   0.02816 px
bilinear  0.03379 px
m09       0.03778 px
```

The differences at the top are very small. It would be misleading to describe m41zf as dramatically more geometrically accurate than m25zf or m13zf.

What is clear is that Z calibration substantially improves the raw mesh family and places the calibrated variants among the strongest methods on shape preservation.

## 9. Edge behaviour

The benchmark does **not** show the new method winning every edge metric.

Overall edge-width ratio (ideal = 1):

```text
Lanczos-3  1.0807
m09z       1.1013
m25zf      1.1107
m41zf      1.1130
bicubic    1.1224
bilinear   1.2594
m09        1.3273
```

Lanczos is therefore sharper according to this analytic 10–90% edge-width measure.

Similarly, Lanczos has the best Siemens-star RMSE among the principal high-quality methods and lower aggregate overshoot than the calibrated meshes in this synthetic benchmark.

This does not invalidate visual observations of haloing on particular photographs: it means that the benchmark's analytic edge/overshoot metric and a specific photographic edge can favour different methods. Both should be reported.

## 10. Z correction as an edge/high-pass field

The corrected-minus-uncorrected image was analysed separately.

| Difference pair | edge corr | −Laplacian corr | transform consistency |
|---|---:|---:|---:|
| m09z − m09 | 0.6647 | 0.8889 | 0.9798 |
| m09z_13 − m13 | 0.6645 | 0.8890 | 0.9801 |
| m09z_41 − m41 | 0.6642 | 0.8882 | 0.9788 |
| m13zf − m13 | 0.6675 | 0.8975 | 0.9941 |
| m25zf − m25 | 0.6678 | 0.8979 | 0.9944 |
| **m41zf − m41** | **0.6707** | **0.9028** | **0.9993** |

Several things follow.

First, the correction is more strongly related to a second-derivative/high-pass signal than to simple gradient magnitude. Calling it “edge-like” is reasonable, but it is more specifically **Laplacian-like**.

Second, final-grid calibration greatly improves transform consistency. The m41zf correction field is almost unchanged, in a correlation sense, when compared with the correctly transformed identity correction field.

Third, the inherited 9Z refinements do not gain this property merely by adding nodes. Again, the important step is final-grid recalibration.

This may be one of the most interesting structural results of the experiment.

## 11. Identity and conservation

At identity, all final-grid Z-calibrated methods preserve the source raster to floating-point accuracy.

However, the reference is the **unquantized analytic scene**, while the input is an 8-bit sRGB raster. Therefore their identity PSNR against the analytic reference is finite (~65.68 dB).

That 65.68 dB is primarily the source quantization floor, not reconstruction error.

The raw meshes do not return the source raster at identity because their area average differs from the centre sample. For example, m09 is only ~44.52 dB against the analytic reference at identity.

This test is a direct demonstration of what the Z calibration changes: it converts the point-centred reconstruction into an area-consistent representation.

## 12. Repeated rasterization is a weakness

The cumulative test repeatedly performs:

```text
transform → rasterize → reconstruct → transform → rasterize → ...
```

For 12 × 30° rotation, synthetic-scene PSNR is approximately:

| Method | PSNR dB |
|---|---:|
| **Lanczos-3** | **44.71** |
| bicubic | 40.88 |
| m09z | 39.72 |
| m25zf | 39.58 |
| m13zf | 39.49 |
| m41zf | 39.46 |
| m09 | 30.44 |

The real photograph gives the same broad ordering:

```text
Lanczos-3  53.44 dB
bicubic    51.38 dB
m09z       50.75 dB
m41zf      50.61 dB
m09        41.67 dB
```

Thus the current mesh family does **not** solve repeated-resampling degradation when it is rebuilt from a newly rasterized image after every step.

This is conceptually important. The representation is intended to reduce dependence on a raster grid; repeatedly collapsing it back to a raster throws away that advantage.

A separate future experiment should distinguish:

1. repeated rasterize/reconstruct cycles;
2. keeping one continuous mesh and composing coordinate transforms until the final rasterization.

The present report tests the first case.

## 13. Speed and memory

Current render time, milliseconds per output megapixel:

```text
bilinear      8.0
bicubic       9.4
box          16.2
Lanczos-3    21.9
m09z         66.0
m13zf        76.1
m25zf       145.6
m41zf       191.7
```

The mesh implementation is currently much slower than the classical kernels.

The field representation also grows rapidly:

```text
m09z    ~11.0 MB
m13zf   ~21.9 MB
m25zf   ~43.9 MB
m41zf   ~87.7 MB
```

for the benchmark field.

These are implementation costs, not fundamental lower bounds. The current code prioritizes exact integration and experimental clarity over production optimization.

### Practical quality/speed trade-off

m41zf has the best composite rank, but the numerical gain over m25zf and m13zf is small:

- m41zf vs m25zf: only ~0.055 dB aggregate PSNR improvement, while rendering is ~1.32× slower and the field uses ~2× the memory;
- m41zf vs m13zf: ~0.10 dB PSNR improvement, but ~2.52× slower and ~4× the memory.

This makes **m13zf a particularly interesting practical operating point** in the current CPU implementation.

m09z is cheaper still and remains strong, though final-grid calibration improves several properties.

## 14. What the benchmark currently supports

The present evidence supports the following claims:

1. A pixel-centre raster can be converted into a continuous Q2-derived colour field and resampled by output-pixel area footprints.
2. Area calibration is crucial; the uncorrected mesh family loses colour/contrast and performs poorly overall.
3. Pure Q2 subdivision does not improve the field.
4. Calibration on the final refined mesh gives a measurable improvement over inheriting a correction from the original 9-node Q2.
5. Fine-grid correction behaves like a highly transform-consistent Laplacian-like detail field.
6. The calibrated mesh is especially competitive on sharp synthetic content, downscaling, colour preservation and geometric stability.
7. Lanczos remains stronger in aggregate PSNR, already blurred content, strong upscaling, several edge-frequency metrics and repeated rasterization.
8. The highest-resolution mesh is not automatically the best engineering choice; m13zf/m25zf may provide a better quality-cost trade-off.

## 15. What the benchmark does **not** establish

The current experiments do not yet establish that:

- the reconstruction is the unique or physically correct subpixel image;
- the method is universally better than classical resampling;
- the 0.5× result generalizes to arbitrary downscale factors;
- the current quality-rank ordering is statistically robust;
- the current Python/Numba speed represents an optimized implementation;
- the method performs like super-resolution or recovers information absent from the source;
- the overall construction is novel relative to the full image-processing literature.

Those require further testing and literature review.

## 16. Recommended next experiments

### 16.1 Fix rank ties

Use numerical tolerances so mathematically equivalent methods receive equal rank. Prefer effect sizes or normalized errors over raw ordinal ranks when differences are tiny.

### 16.2 More scale factors

Add irregular scales such as:

```text
0.33, 0.4, 0.6, 0.66, 0.8, 1.25, 1.37, 1.75, 2.5, 3.7
```

to avoid grid-alignment special cases.

### 16.3 More analytic edge phases

Move the same line/edge through many subpixel offsets. This can reveal grid-phase dependence separately from angle dependence.

### 16.4 More natural images

Use a larger, legally distributable image set with:

- hair,
- text,
- foliage,
- skin,
- architecture,
- high-contrast edges,
- already blurred images,
- sensor noise.

### 16.5 Keep the mesh between transforms

Compare cumulative operations when all transforms are composed in continuous coordinates and rasterization occurs only once at the end.

### 16.6 Optimize the representation

Investigate whether exact Q2 integration or a compact equivalent formulation can reproduce the best final-grid-calibrated behaviour without storing 41 explicit points per source pixel.

### 16.7 Literature comparison

Compare explicitly against:

- conservative remapping,
- finite-volume reconstruction,
- Q2 finite elements,
- EWA/elliptical footprint filtering,
- edge-directed interpolation,
- spline and reconstruction-filter methods.

Only after that should novelty claims be considered.

## 17. Current interpretation

The most interesting result is not simply that one mesh variant obtains the lowest composite rank.

The deeper result is that converting pixel-centre samples into a continuous field makes it possible to separate:

```text
source sampling grid
from
image representation
from
output sampling grid
```

and to study conservation, refinement and transformation as separate operations.

The current benchmark suggests that a particularly useful representation is:

```text
pixel-centre samples
→ reconstructed mesh
→ fine-grid conservative area calibration
→ continuous field
→ exact output-footprint integration
```

The final-grid calibration behaves like a spatially localized, Laplacian-like correction field that is remarkably stable under transformation.

That is the part of the method that currently appears most worth investigating further.
