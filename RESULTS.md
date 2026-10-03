# Preliminary benchmark results

These results are preliminary and describe the current experimental implementation, not a universal ranking of image resamplers.

The benchmark contained **17 methods**, **59 transforms**, **4 images/scenes** and **3162 result rows**. The main synthetic scenes have known geometry and a separately rendered reference; one real photograph is used for cumulative-resampling checks. A separate photographic run with a high-resolution reference is described in section 14. The source scenes are quantized to 8-bit sRGB before reconstruction, so the source raster itself already differs slightly from the unquantized scene reference.

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

### Visual character: calibrated versus uncalibrated

This numerical “loss” in the raw mesh should not automatically be interpreted as an undesirable image.

On real-image crops, the uncalibrated mesh variants (`m09`, `m13`, `m25`, `m41`) often produce visibly smoother and gentler edge transitions than sharper classical kernels. Fine diagonal text and high-contrast contours can look less hard or less outlined. If that softer rendering is the desired visual style, an uncalibrated mesh can be a reasonable intentional choice.

The Z-calibrated family has a different goal. `m09z` and the inherited refinements `m09z_13`, `m09z_25`, `m09z_41` restore the area discrepancy of the 9-node field; the final-grid variants `m13zf`, `m25zf`, `m41zf` perform the corresponding conservation step on the refined representation. In both cases the practical effect is to restore local edge/thin-feature contrast that the smooth reconstruction otherwise attenuates.

A useful practical distinction is therefore:

```text
uncalibrated mesh → softer / smoother edge character
Z-calibrated mesh → stronger area and local-contrast preservation
```

Neither description is a universal perceptual-quality verdict. The benchmark rewards calibrated variants on colour, thin-feature and geometry metrics, while a viewer may still prefer the softer uncalibrated appearance on some photographs.

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

## 12. Repeated rasterization stress test

The cumulative test deliberately performs:

```text
transform → rasterize → reconstruct → transform → rasterize → ...
```

This is **not the intended use of the mesh representation**. The design goal is to construct the continuous representation once, keep it as the image model, compose subsequent coordinate transforms, and rasterize only when an output image is actually required.

Repeated rasterization is nevertheless a useful stress test because every resampling method loses information when forced through repeated raster → reconstruction → raster cycles.

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

These numbers therefore compare **degradation rates under repeated re-rasterization**, not the core grid-independent representation itself. Lanczos degrades least in this artificial repeated-resampling regime among the tested methods; all methods degrade.

The intended pipeline is instead:

```text
source raster
→ continuous mesh (once)
→ compose T1, T2, ..., Tn in continuous coordinates
→ rasterize once to the requested output grid
```

A dedicated benchmark should compare this intended mesh-preserving pipeline against repeated rasterization. Earlier coordinate-composition experiments already indicate that avoiding intermediate rasterization can reduce round-trip error to near floating-point precision for reversible transforms, but that result should be reproduced inside the unified benchmark before being treated as part of the formal result set.

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

## 14. Photographs with a high-resolution reference

A second, separate run tested two real images: a broadcast-style test card and a photographic film poster with text and thin graphic lines. The poster is used only as a local test image and is not redistributed. The run contained **17 methods**, **34 transforms** and **1156 result rows**.

Real photographs normally have no ground truth. Here one was constructed from the high-resolution originals:

```text
high-resolution original (6144×4608 test card, 1206×1786 poster)
→ exact k×k box average in linear light (k = 4 and 2)
→ 8-bit sRGB source (1536×1152, 603×893)
→ resampled by every method
```

The reference for any transform is the **high-resolution original integrated exactly over the same transformed output-pixel footprint**. At identity this reference reproduces the source to 3·10⁻¹⁶ before quantization. The reference is therefore the real image content, not another resampler, although its own resolution is finite. It has k× the source resolution, so the 3× upscale of the test card is close to that limit.

### 14.1 Overall

Mean linear PSNR over all forward transforms except identity:

| Image | m13zf | m41zf | m09z | bicubic | Lanczos-3 | box | m09 (no Z) |
|---|---:|---:|---:|---:|---:|---:|---:|
| test card | **35.61** | **35.62** | 35.51 | 34.27 | 34.25 | 34.30 | 31.44 |
| poster | **37.33** | **37.33** | 37.04 | 36.81 | 36.64 | 36.21 | 34.91 |

On both photographs the final-grid calibrated meshes have the highest PSNR, about +1.3 dB (test card) and +0.5 dB (poster) above bicubic and Lanczos-3. This differs from the blurred synthetic scenes (section 6), where Lanczos led.

`m13zf` and `m41zf` are practically identical here, while `m13zf` renders about 2.5× faster. This supports `m13zf` as the default operating point (section 13).

### 14.2 Rotation

Linear PSNR over 0.5°–89° (15 angles, mean of both images):

| Method | Mean PSNR dB | Range dB |
|---|---:|---:|
| m41zf | **35.686** | 0.181 |
| m13zf | 35.675 | 0.180 |
| m25zf | 35.669 | 0.179 |
| bicubic | 35.574 | 0.173 |
| m09z | 35.538 | 0.200 |
| Lanczos-3 | 35.522 | **0.153** |
| box | 34.499 | 0.227 |
| m09 | 33.750 | 0.127 |

The calibrated meshes are ahead at **every** tested angle, by about 0.1–0.15 dB over bicubic and Lanczos. The angular variation of all good methods is small and similar, with no angle-specific failure.

### 14.3 Scaling

| Scale | m41zf | m13zf | m09z | bicubic | Lanczos-3 | box |
|---:|---:|---:|---:|---:|---:|---:|
| 0.50× | **56.38** | 56.38 | 56.38 | 34.87 | 32.57 | 55.00 |
| 0.75× | **38.69** | 38.62 | 38.62 | 36.90 | 36.23 | 36.84 |
| 1.5× | 32.07 | 32.00 | 31.74 | 32.04 | **32.27** | 30.73 |
| 2× | 31.73 | 31.77 | 31.01 | 31.81 | **31.97** | 30.30 |
| 3× | 29.73 | **29.86** | 29.32 | 29.41 | 29.53 | 27.98 |

- **Downscaling** is a clear strength. At 0.75×, a non-aligned factor, the calibrated meshes lead by about 1.7 dB over bicubic and 2.4 dB over Lanczos. The point-sampling kernels alias, while the area-conserving mesh does not.
- **Moderate upscaling** (1.5–2×): Lanczos-3 is ahead by about 0.2–0.3 dB, and m13zf and m41zf are level with bicubic.
- **3× upscaling**: m13zf is best, unlike the synthetic benchmark where Lanczos led at every magnification. Because of the finite reference resolution, this single point should be confirmed on more images.

Combined rotation + upscaling (10°/30° × 1.5/2) gives essentially a tie: m41zf 31.77, bicubic 31.76, m13zf 31.75 dB, with Lanczos-3 slightly ahead at 31.96 dB.

### 14.4 Colour and overshoot

| Metric | Image | m13zf | m09z | bicubic | Lanczos-3 | box |
|---|---|---:|---:|---:|---:|---:|
| mean ΔE00 | test card | 0.563 | 0.563 | 0.589 | 0.700 | **0.420** |
| mean ΔE00 | poster | **0.996** | 1.037 | 1.047 | 1.131 | 1.000 |
| overshoot (fraction of channel values outside [0,1]) | test card | 1.0 % | 1.1 % | 1.0 % | 1.5 % | 0 % |
| overshoot | poster | 0.5 % | 0.6 % | 0.4 % | 0.8 % | 0 % |

- The chroma ratio of all calibrated meshes is 1.000 on both images, so there is no saturation loss.
- The uncalibrated m09 again loses sharpness: its gradient-energy ratio is 0.72–0.76, against 0.93 for m13zf.
- Box resampling has the lowest ΔE on the test card: it never overshoots, and the card is dominated by large flat colour areas with hard edges. Among methods that preserve sharpness, m13zf has the lowest colour error on both images, and its overshoot is lower than Lanczos-3.

### 14.5 Repeated rasterization and the Z-difference field

The repeated-rasterization stress test (section 12) behaves as on synthetic scenes:

| Test | Image | m13zf | m09z | bicubic | Lanczos-3 |
|---|---|---:|---:|---:|---:|
| rotate + inverse | test card | 34.59 | 35.40 | 36.12 | **41.38** |
| rotate + inverse | poster | 36.26 | 36.96 | 37.55 | **40.11** |
| 12 × 30° | test card | 28.48 | 28.58 | 29.16 | **33.54** |
| 12 × 30° | poster | 31.06 | 31.63 | 32.15 | **35.25** |

This again argues for composing transforms on the continuous mesh and rasterizing once. The demo's `--repeat` option shows the difference directly.

The calibrated-minus-uncalibrated field is Laplacian-like on photographs too (−Laplacian correlation 0.77–0.80). Its transform consistency is 0.997 for m13zf and 0.999 for m41zf, against 0.98 for the 9-node m09z. This matches the synthetic result in section 10.

### 14.6 Reading

With a reference derived from real high-resolution content, the final-grid calibrated mesh is the most accurate method tested for arbitrary-angle rotation and for downscaling on both photographs. It keeps colour and saturation, and it overshoots less than Lanczos-3. Lanczos-3 remains better for moderate upscaling and much better under repeated re-rasterization. Two images are not a representative photographic corpus, so section 17.4 still applies.

## 15. What the benchmark currently supports

The present evidence supports the following claims:

1. A pixel-centre raster can be converted into a continuous Q2-derived colour field and resampled by output-pixel area footprints.
2. Area calibration is crucial; the uncorrected mesh family loses colour/contrast and performs poorly overall.
3. Pure Q2 subdivision does not improve the field.
4. Calibration on the final refined mesh gives a measurable improvement over inheriting a correction from the original 9-node Q2.
5. Fine-grid correction behaves like a highly transform-consistent Laplacian-like detail field.
6. The calibrated mesh is especially competitive on sharp synthetic content, downscaling, colour preservation and geometric stability.
7. Lanczos remains stronger in aggregate PSNR on the synthetic set, already blurred content, strong upscaling, several edge-frequency metrics and repeated rasterization.
8. The highest-resolution mesh is not automatically the best engineering choice; m13zf/m25zf may provide a better quality-cost trade-off.
9. On two photographs with a high-resolution reference, the final-grid calibrated mesh has the highest PSNR for rotation at every tested angle and for downscaling, with no saturation loss (section 14).

## 16. What the benchmark does **not** establish

The current experiments do not yet establish that:

- the reconstruction is the unique or physically correct subpixel image;
- the method is universally better than classical resampling;
- the 0.5× result generalizes to arbitrary downscale factors;
- the current quality-rank ordering is statistically robust;
- the current Python/Numba speed represents an optimized implementation;
- the method performs like super-resolution or recovers information absent from the source;
- the complete construction is novel relative to the full image-processing and numerical-remapping literature.

Those require further testing. An initial related-work review is now included in [METHOD.md](METHOD.md#11-related-work-scope-and-novelty), but it is not exhaustive and does not establish novelty.

## 17. Recommended next experiments

### 17.1 Fix rank ties

Use numerical tolerances so mathematically equivalent methods receive equal rank. Prefer effect sizes or normalized errors over raw ordinal ranks when differences are tiny.

### 17.2 More scale factors

Add irregular scales such as:

```text
0.33, 0.4, 0.6, 0.66, 0.8, 1.25, 1.37, 1.75, 2.5, 3.7
```

to avoid grid-alignment special cases.

### 17.3 More analytic edge phases

Move the same line/edge through many subpixel offsets. This can reveal grid-phase dependence separately from angle dependence.

### 17.4 More natural images

Use a larger, legally distributable image set with:

- hair,
- text,
- foliage,
- skin,
- architecture,
- high-contrast edges,
- already blurred images,
- sensor noise.

### 17.5 Keep the mesh between transforms

Compare cumulative operations when all transforms are composed in continuous coordinates and rasterization occurs only once at the end.

### 17.6 Optimize the representation

Investigate whether exact Q2 integration or a compact equivalent formulation can reproduce the best final-grid-calibrated behaviour without storing 41 explicit points per source pixel.

### 17.7 Extend the literature comparison

The initial review in [METHOD.md](METHOD.md#11-related-work-scope-and-novelty) identifies direct precedents in reconstruction filtering, exact-area biquadratic histosplines, conservative remapping, Active Flux reconstruction, edge-directed interpolation and signed Laplacian representations. Extend it with a systematic database search, citation chaining and a direct mathematical comparison of the reconstruction operators. The current review supports careful statements about similarities and differences, but not a claim of formal novelty.

## 18. Current interpretation

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
