# Method

## Representation goal

The method is designed to make the reconstructed image independent of the particular pixel grid on which the source was sampled. The raster is treated as an input measurement lattice, not as the permanent geometry of the image.

The representation pipeline is:

```text
pixel grid
→ pixel colours
→ coloured point samples
→ reconstructed vertices and edges
→ continuous mesh
→ optional area calibration from the original pixel colours
→ refinement by adding further points and edges
→ sampling or integration onto an arbitrary output grid
```

The important transition is from **grid-bound pixel values** to a **continuous colour field**. After that transition, transforms act on coordinates and output-pixel footprints; they do not require the image to remain tied to the source raster.

## 1. Raster interpretation

Let the source raster contain linear-light colour samples `P[i,j]`.

The value of pixel `(i,j)` is interpreted as a point sample at the pixel centre:

```text
P[i,j] = C(i + 1/2, j + 1/2)
```

rather than as a piecewise-constant coloured square.

For RGBA input, RGB should be premultiplied by alpha before reconstruction and integration.

## 2. Nine-node reconstruction

Each original pixel cell is represented by a 3×3 node layout.

### 2.1 Corner nodes

For a regular grid, an interior corner shared by four pixels is reconstructed as the mean of the four surrounding pixel-centre samples:

```text
V = (P00 + P10 + P01 + P11) / 4
```

This can also be viewed geometrically as averaging the values obtained on the two diagonals at their intersection.

### 2.2 Edge-midpoint nodes

For an edge between source pixel centres `P1` and `P2`, with reconstructed edge endpoints `V1` and `V2`:

```text
E = (P1 + P2 + V1 + V2) / 4
```

### 2.3 Centre node

The cell centre initially keeps the original source pixel value:

```text
C = P
```

The nine values form a Q2 tensor-product element.

## 3. Q2 surface

Using local coordinates `ξ,η ∈ [-1,1]`, define the quadratic Lagrange basis

```text
L_-1(t) = t(t-1)/2
L_0 (t) = 1 - t²
L_+1(t) = t(t+1)/2
```

The reconstructed colour field is

```text
C(ξ,η) = Σ_i Σ_j C_ij L_i(ξ) L_j(η)
```

with `i,j ∈ {-1,0,+1}`.

Each colour channel is evaluated independently in linear light.

## 4. Optional conservative area calibration

The raw Q2 reconstruction preserves the source pixel value at the centre but does not in general preserve it as the area average of the entire pixel cell.

For a unit Q2 cell, exact integration gives the cell average

```text
A = (Σ corners + 4 Σ edge_midpoints + 16 centre) / 36
```

Only the centre node is changed:

```text
C' = C + Δ
```

To impose `A' = P`:

```text
A' = A + (16/36) Δ = P
```

therefore

```text
Δ = (36/16) (P - A)
```

and

```text
C' = C + 2.25 (P - A)
```

This correction is local, leaves shared cell boundaries unchanged, and uses one interior degree of freedom to satisfy one scalar area constraint per channel.

The correction should be applied in unclipped floating-point space. Clipping before integration would destroy exact conservation.

## 5. Interpretation of the correction

The conservative correction guarantees only the cell average:

```text
(1 / area(cell)) ∫∫_cell C(x,y) dx dy = P
```

It does not prove that the corrected intra-pixel shape is the unique or physically correct subpixel reconstruction.

Therefore the project treats raw Q2 and conservative Q2 as separate models.

### 5.1 Edge-contrast interpretation

The area residual

```text
P - A
```

is concentrated mainly around edges, thin structures and other high-frequency image content. The resulting correction is therefore visually similar to a localized high-pass / Laplacian-like contrast-restoration field.

This gives the two reconstruction families a deliberately different visual character:

- without Z calibration, the reconstructed mesh is smoother and typically produces softer, finer-looking transitions;
- with Z calibration, local contrast removed by that smoothing is pushed back into the interior degrees of freedom so that the source pixel's area colour is preserved.

The purpose of Z calibration is therefore best described as **area conservation with edge/feature contrast restoration**, not as generic sharpening. The correction is derived from the reconstruction's own area error rather than from an externally chosen sharpening kernel.

A softer uncalibrated result can still be desirable as an aesthetic choice. The calibrated and uncalibrated fields should therefore be treated as two useful reconstruction modes rather than simply “correct” and “incorrect” versions.

### 5.2 Signed area residual, centre displacement and correction field

The following derivation follows the local construction implemented by `build_q2_lattice`, `q2_cell_means` and `z_correct_q2` in `rgbmesh/core.py`. Work in one linear-light channel; the equations apply independently to every premultiplied channel. Distinguish three quantities sometimes informally called “Z”:

```text
Z[i,j] = P[i,j] - A[i,j]                 signed cell-average residual
Δ[i,j] = (36/16) Z[i,j] = (9/4) Z[i,j]  centre-node displacement
D(ξ,η) = C_cal(ξ,η) - C_raw(ξ,η)        continuous correction field
```

Z is an area-average discrepancy, in the same units as the channel value. Multiplying it by the physical cell area gives the missing signed integral. It is not a nonnegative loss, a gradient magnitude or a measured amount of optical energy lost from the scene. Positive Z indicates an underestimated raw cell average; negative Z indicates an overestimated one.

For the nine-node correction, only the centre basis coefficient changes, so within each cell

```text
D(ξ,η) = Δ (1 - ξ²)(1 - η²),    ξ,η ∈ [-1,1].
```

This bubble is zero on every cell boundary, equals Δ at the centre, and has cell average `(4/9) Δ = Z`. Consequently the corrected field is still continuous across shared boundaries, and its cell average is exactly `A + Z = P`. The corrected centre is generally no longer equal to the original point sample P. Area calibration replaces that centre interpolation condition with the prescribed cell average; it does not impose both conditions simultaneously.

For any output footprint Ω, the calibrated-minus-raw output is the average of D over Ω. It equals Z when Ω is exactly one original source cell, as in identity area rendering of `m09z` minus `m09`. For rotated, translated or scaled footprints it is a different integral, potentially spanning several bubbles. The demo's `--zdiff` image visualizes a luminance projection of this rendered difference, not generally the source-grid Z array.

### 5.3 Exact stencil and weighted discrete Laplacian

For an interior source pixel, write `S_axis` for the sum of its four axial neighbours and `S_diag` for the sum of its four diagonal neighbours. Substituting the corner and edge rules of section 2 gives

```text
ΣV = P + (1/2) S_axis + (1/4) S_diag
ΣE = (3/2) P + (1/2) S_axis + (1/8) S_diag
A  = (92 P + 10 S_axis + 3 S_diag) / 144.
```

Thus the raw mesh's source-cell averages are a discrete smoothing of P, with positive unit-sum kernel K, and the signed residual is `Z = (I - K) P`:

```text
           [  3   10    3 ]
K = (1/144) [ 10   92   10 ]
           [  3   10    3 ]

               [  -3  -10   -3 ]
I - K = (1/144) [ -10   52  -10 ]
               [  -3  -10   -3 ]
```

To make the Laplacian sign convention explicit, define

```text
L_axis P = S_axis - 4 P
L_diag P = S_diag - 4 P
L_w P    = (10 L_axis P + 3 L_diag P) / 16.

Z = -(1/9) L_w P
Δ = -(1/4) L_w P.
```

`L_w` is a weighted nine-point discrete Laplacian. For samples of a smooth field p on a square grid of pitch a, Taylor expansion gives

```text
L_w P = a² ∇²p + O(a⁴)
Z     = -(a²/9) ∇²p + O(a⁴)
Δ     = -(a²/4) ∇²p + O(a⁴).
```

The remainder assumes bounded fourth derivatives. Constants and affine ramps have exactly zero interior residual; a nonzero constant slope alone does not create Z. Curvature, including the changes of slope at an edge's shoulders, creates its signed lobes. Bright local peaks typically have positive Z and dark troughs negative Z. A broad linear ramp can have zero Z through most of its interior even though it has a nonzero gradient.

The stencil is exact for the initial nine-node construction, not a fit to the benchmark's Laplacian correlations. The code uses edge-replicated padding: the same stencil can be evaluated on that extended raster, but the extension breaks an affine ramp and translation invariance at the image boundary. Statements about affine cancellation, convolution and Fourier response therefore refer to the interior, an infinite lattice, or an explicitly periodic experiment. Constant cancellation still holds at the borders.

These coefficients must not be assumed for every final-grid variant. The uncalibrated 25-node Q2 subdivision represents the same field and has the same original-cell residual, but final calibration distributes corrections over subcell bubbles. The 13- and 41-node fans have different raw cell averages and different correction shapes. Their residual operators require their own derivations. The rendered difference fields in RESULTS.md also include the transform and output integration, which explains why their measured correlation with a conventional Laplacian need not be one.

### 5.4 Frequency response

On an infinite or periodic source lattice, let `ωx,ωy ∈ [-π,π]` denote angular spatial frequencies in radians per source pixel. A hat denotes the discrete Fourier transform. The preceding stencils give the exact symbols

```text
K_hat(ωx,ωy) = (92 + 20 cos ωx + 20 cos ωy + 12 cos ωx cos ωy) / 144
G_Z(ωx,ωy)   = 1 - K_hat
               = (13 - 5 cos ωx - 5 cos ωy - 3 cos ωx cos ωy) / 36
Z_hat         = G_Z P_hat.
```

`G_Z` is real and even. It is zero at DC and positive at every other frequency, with range `[0,5/9]`. Its values at axial and diagonal Nyquist are `G_Z(π,0) = 4/9` and `G_Z(π,π) = 5/9`. Near DC,

```text
G_Z = (ωx² + ωy²)/9 + O(||ω||⁴).
```

This is an isotropic negative-Laplacian response to leading order, with square-grid directional dependence at higher frequencies. The centre displacement has response `(9/4) G_Z`; the full continuous field and its rendered outputs also depend on the bubble basis and footprint integration. In particular, `(9/4) G_Z` is not the frequency response of the complete resampler.

At identity, the raw cell-average operator is K and the calibrated cell-average operator is `K + G_Z = I`. Calibration compensates the averaging discrepancy introduced by this reconstruction. It does not invert an optical or motion-blur transfer function already present in P.

### 5.5 Relation to pre-existing blur

Suppose a discrete, spatially invariant blur model is appropriate on the same grid:

```text
B = h * S + n,
```

where S is a sharp reference raster, h is a normalized point-spread function (PSF), n is additive noise and `*` is convolution. Since `L_Z = I - K` is a fixed convolution operator,

```text
Z_B     = L_Z B = h * Z_S + L_Z n
Z_B_hat = G_Z H S_hat + G_Z n_hat.
```

This commutation is exact for infinite/periodic discrete convolutions, or where finite-image boundary handling does not interfere. A continuous optical-blur model followed by sampling needs its own forward model: aliasing can prevent it from being represented by a single discrete h. Clipping, gamma-space processing and spatially varying PSFs also invalidate the simple identity.

For a nonnegative unit-sum discrete PSF, `|H| ≤ 1`. It attenuates the spectral magnitude of the noise-free Z signal wherever `|H| < 1`; total squared residual energy cannot increase under periodic convolution. Individual lobes or local statistics need not decrease monotonically. Noise can raise the measured energy, and motion-blur transfer functions have zeros and side lobes.

In a continuous, adequately sampled approximation, isotropic Gaussian blur of standard deviation σ pixels has `H(ω) = exp(-σ² ||ω||²/2)`. It therefore suppresses the high-frequency content to which Z responds. A centred uniform straight-line motion of total displacement vector d pixels instead has

```text
H(ω) = sinc((ω · d)/2),    sinc(q) = sin(q)/q,    sinc(0) = 1.
```

Its effect is directional: an ideal straight edge whose normal is perpendicular to d has no motion-induced broadening. A discrete experiment should use the transfer function of its actual discretized PSF; the continuous Gaussian and sinc expressions are forward-model approximations to that experiment.

For uniform translational motion of a static scene, reversing d gives the same centred PSF and the same Z response. The sharp image can also be translated together with a corresponding change of PSF origin without changing the observed blur. An exposure-midpoint sharp reference fixes this registration convention; it does not identify the direction of time or make that frame uniquely recoverable. Parallax, occlusion, nonuniform motion and rolling shutter require a richer model.

### 5.6 A measurable example: Gaussian-blurred step edges

For a straight rising edge, let u be physical distance along its normal, a the pixel pitch, c the signed contrast and b the background. A Gaussian-smoothed step with physical standard deviation σ is

```text
pσ(u) = b + c Φ(u/σ),
```

where Φ is the standard normal cumulative distribution function. In the well-sampled regime `σ >> a`, the Taylor approximation in section 5.3 predicts

```text
Z(u) ≈ - (a²/9) pσ''(u)
     = c a² u exp(-u²/(2σ²)) / (9 sqrt(2π) σ³).

lobe positions       ≈ -σ, +σ
lobe separation      ≈ 2σ
max |Z|              ≈ |c| a² exp(-1/2) / (9 sqrt(2π) σ²)
10–90% edge width    = 2 Φ^(-1)(0.9) σ ≈ 2.5631 σ.
```

The positive and negative lobes describe signed curvature on the bright and dark sides; they are not two different blur components. For fixed contrast, a wider Gaussian transition has weaker, more widely separated lobes. Replacing Z by Δ multiplies amplitude by `9/4` without changing these positions.

These are asymptotic predictions for an isolated Gaussian edge, not a universal blur calibration. Near one-pixel widths, phase, angle and the exact stencil matter. Fit the exact discrete residual of a sampled forward edge instead of substituting the continuum lobe formula. If the sensor measures pixel-area averages, include that aperture integration before sampling; an inferred edge width then combines optical blur, motion, sensor aperture and any prior processing. It should not automatically be labelled optical σ.

### 5.7 What Z can and cannot identify

Z can support blur-sensitive measurements, but its amplitude alone cannot determine a PSF. Low contrast, a smooth sharp scene, fewer edges, texture orientation and stronger blur can all produce small residual energy. Noise, demosaicing, compression, sharpening and quantization can produce large residuals without corresponding sharp scene detail. A single edge measures only the blur projected onto its normal; multiple orientations are needed to investigate anisotropic motion.

Z is a deterministic linear transform of the source raster. It adds no independent observation: its zero DC response discards the constant component, while its nonzero-frequency response reweights information already present in P. It can be a useful diagnostic or a feature for an estimator under stated scene/PSF/noise assumptions, but it cannot resolve general blind-deconvolution ambiguity. Source-area calibration preserves the measured blurred values just as exactly as it preserves sharp ones. Estimating and undoing physical blur would be a separate inverse problem.

## 6. Transformation and output sampling

The reconstructed field is independent of the output pixel grid.

For each output pixel, inverse-map its footprint `Ω` through the requested transform and compute

```text
P_out = (1 / |Ω|) ∫∫_Ω C(x,y) dx dy
```

For affine transforms the footprint is a parallelogram in source coordinates.

A point-sampling mode may also evaluate the reconstructed field only at the mapped output-pixel centre, but area integration is the primary resampling model.

## 7. Refinement

After a Q2 field has been constructed, additional nodes may be generated by evaluating that fixed field.

Examples used in the experiments:

- 9 nodes: original Q2 element;
- 13 nodes: add four half-cell face centres and form piecewise-linear centre fans;
- 25 nodes: evaluate the same Q2 on a 5×5 quarter-grid and represent it as four Q2 subpatches;
- 41 nodes: add the sixteen quarter-cell face centres and form piecewise-linear centre fans.

When these nodes are sampled from a fixed Q2 field, refinement does not add information.

The 25-node Q2 subdivision is mathematically the same continuous Q2 surface, apart from floating-point error.

Piecewise-linear 13- and 41-node triangulations are approximations to the Q2 surface and converge as the mesh is refined.

## 8. Re-calibration after refinement

A separate experimental family applies area correction to the final refined mesh.

This should not be confused with subdivision of a fixed field: a new area correction introduces a new continuous surface.

For this reason the benchmark keeps the two operations distinct.

## 9. Colour handling

Recommended processing order:

1. decode sRGB to linear RGB;
2. premultiply RGB by alpha when alpha is present;
3. reconstruct and transform in floating point;
4. integrate output footprints;
5. unpremultiply when required;
6. encode to the chosen output transfer function;
7. quantize only at serialization.

## 10. Validation strategy

Pairwise agreement between two resamplers is not ground truth.

The preferred validation uses analytically generated continuous scenes whose transformed output can be rendered independently. The test set includes rings, discs, thin lines at several angles, colour patches, and a Siemens star.

Useful measurements include:

- global error: PSNR, SSIM, ΔE;
- edge width and overshoot;
- thin-feature thickness and peak contrast;
- positional and shape deformation;
- angular/grid-dependent modulation;
- cumulative and round-trip resampling error.

### 10.1 Proposed blur-estimation experiments

The following experiments test the predictions above. They are proposed extensions to the existing benchmark, not completed measurements or a validated blur estimator.

1. **Verify the operator before estimating blur.** On float64 random rasters, compare `P - q2_cell_means(build_q2_lattice(P))` with the stencil in section 5.3, using the same edge extension. Check constant and interior affine cancellation, exact corrected cell averages, and sinusoidal gain against `G_Z`. Compare `m09z - m09` under identity area rendering with Z. Derive and verify the raw residual operators separately before using final-grid fan variants.
2. **Generate controlled forward data.** Start with analytic steps, thin lines, sinusoidal gratings, corners and textured scenes. Sweep Gaussian widths (for example 0, 0.5, 1, 2, 4 pixels), motion lengths (0, 1, 2, 4, 8 pixels) and motion angles. Independently vary contrast, edge normal, subpixel phase and noise. For physical tests, blur the continuous or sufficiently oversampled scene, integrate a known sensor aperture and then sample. Establish convergence of that reference rather than using a resampler as ground truth. Keep noiseless linear data as a baseline before adding sRGB quantization, compression or sharpening.
3. **Measure the signed response.** Retain Z in floating point per channel or use a fixed linear luminance projection. Record contrast-normalized peak magnitude, lobe separation, sign/zero-crossing locations, spatial spectra and residual energy per fixed region or edge length. Compare edge-width estimates with the known Gaussian parameters and the asymptotic formulas of section 5.6. Fit exact forward-model residual profiles when sampling is coarse; vary edge phase and angle to quantify grid bias. A scale-normalized multiscale Laplacian-of-Gaussian baseline and a direct edge-profile fit help test whether Z offers useful estimation behaviour beyond established measurements [10].
4. **Separate reference-based and blind estimation.** With a registered sharp S, test `Z_B ≈ hθ * Z_S` and fit PSF parameters θ using a specified noise-weighted error. In the noiseless periodic case, `Z_B_hat / Z_S_hat = H` wherever the denominator is nonzero. Omit DC and weak spectral bins: division there is unstable, and Z does not add information compared with the corresponding B/S ratio. Without S, restrict the scene model explicitly, for example to isolated step edges with fitted contrast and position, and compare against edge-profile fits. For motion estimation combine edges of several normals and report orientation modulo 180°, not a recovered time direction.
5. **Control confounds and generalization.** Fit or normalize contrast locally; avoid dividing by nearly zero contrast. Measure the noise response separately. For white independent channel noise of variance τ², the nine-node stencil predicts `Var(Z_n) = τ² (52² + 4·10² + 4·3²) / 144² = (785/5184) τ²`; adjacent residuals are correlated. Mask image/alpha boundaries and exclude margins covering both the PSF and stencil support, or use a declared periodic model. Hold out scenes, phases, contrasts, noise levels and PSF families; report parameter bias, absolute error, uncertainty and failures on textureless regions. Test sensitivity to sensor aperture and spatially varying blur separately.
6. **Keep visualization separate from measurement.** Compare calibrated and raw fields using identical transforms and footprints. Record their unnormalized rendered differences separately from source-grid Z. The current demo normalizes each `--zdiff` luminance image by its own 99.5th percentile and applies a nonlinear colour map, so those PNGs cannot compare absolute amplitudes across blur levels. Use a common display scale for inspection and floating arrays for statistics. Report footprint size and method because output integration changes the measured response.

The source-grid diagnostic can be computed with the existing implementation; no estimator API is implied:

```python
import numpy as np
from rgbmesh.core import build_q2_lattice, q2_cell_means

# P: (height, width, channels), linear light, premultiplied if RGBA.
P = np.asarray(P, dtype=np.float64)
Z = P - q2_cell_means(build_q2_lattice(P))
delta = (9.0 / 4.0) * Z
```

This uses the implementation's edge replication. Perform spectral analysis on a suitable interior region or an explicitly periodic construction; retain the original signed values rather than normalizing each array independently.

## 11. Related work, scope and novelty

The construction and implementation were developed experimentally before the references in this section were consulted. The comparison below is therefore an account of subsequently identified prior art, not a claim that those works were used to derive the method. Independent development also does not make an already known mathematical ingredient novel.

### 11.1 Continuous reconstruction from raster samples

The distinction between a pixel sample and a coloured geometric square, and the need to reconstruct a continuous image before transforming or resampling it, are established ideas. Smith [1] gives an explicit point-sample interpretation. Mitchell and Netravali [2] analyse reconstruction filters for continuous/discrete image conversion, and Unser [3] reviews spline reconstruction in signal and image processing.

RGB Mesh belongs to this broad family. Its specific choice is a locally constructed, shared-boundary Q2 field whose corner and edge values are derived from neighbouring pixel-centre samples.

### 11.2 Output footprints and area resampling

Fant [4] describes continuous, complete area resampling for spatial transforms. Heckbert [5] develops reconstruction and antialiasing filters for image warping, including spatially varying filters associated with transformed output footprints.

The present renderer likewise inverse-maps an output-pixel footprint. Its implementation clips that footprint against the piecewise mesh and integrates the local polynomial or triangle exactly with an appropriate quadrature rule.

### 11.3 Average matching and conservative remapping

Conservation under remapping is well established in finite-volume and finite-element computation. Ullrich and Taylor [6], for example, construct high-order conservative maps between nodal finite-element and finite-volume meshes through overlap integration.

The closest image-resampling work found in this review is Robidoux et al. [7]. Their Average Matching method interprets source pixels as averages over cells, constructs a global natural biquadratic histospline with those averages, and averages the surface over new pixel areas. This shares three central ideas with the conservative RGB mesh: a biquadratic continuous model, source-area matching, and area-based output sampling.

The starting assumptions and constructions differ. Average Matching takes the source values as cell averages and solves for global tensor B-spline coefficients. RGB Mesh first treats each source value as a point sample at the cell centre, derives shared corner and edge nodes locally, and then optionally imposes that same source value as an additional cell-area constraint. The final-grid variants repeat this calibration on an explicitly refined representation, and the renderer supports clipped affine pixel footprints rather than only a change of sampling rate.

### 11.4 Active Flux as a close mathematical parallel

The Cartesian Active Flux reconstruction described by Barsukow et al. [8] is a particularly close mathematical precedent. It uses shared point values at the four corners and four edge midpoints of a rectangular cell together with a prescribed cell average to define a globally continuous biquadratic reconstruction. Thus the use of a centre/interior degree of freedom—or an equivalent bubble coefficient—to satisfy the Q2 cell average is not in itself a new mathematical device.

The role of the data differs. Active Flux evolves conservation laws and stores the cell average and boundary point values as degrees of freedom. RGB Mesh starts from a raster of pixel-centre RGB samples, reconstructs the shared boundary values from neighbouring samples, and uses the resulting static field for colour-image transformation and resampling.

### 11.5 Edge-aware and signed high-pass representations

Edge-directed interpolation predates this work; Li and Orchard [9], for example, adapt interpolation coefficients to local covariance and edge orientation. RGB Mesh is not edge-directed in that sense: its reconstruction rule is fixed rather than selected from an estimated edge direction.

Signed second-derivative and high-pass representations are also established. Marr and Hildreth [10] detect intensity changes through zero crossings of a Laplacian-of-Gaussian response, while the Laplacian pyramid of Burt and Adelson [11] stores signed differences between image scales. Consequently, the calibrated-minus-uncalibrated field should not be presented as the invention of a signed edge representation. The experimental result here is narrower: the area-calibration residual emerges from the conservation constraint, is strongly correlated with a negative Laplacian, and becomes highly transform-consistent under final-grid calibration.

### 11.6 Current novelty statement

No publication found in this initial review describes the complete image-processing chain in exactly the same form:

```text
pixel-centre RGB samples
→ locally reconstructed shared corner and edge nodes
→ piecewise Q2 / refined mesh
→ optional final-grid cell-area calibration
→ exact integration over clipped affine output-pixel footprints
```

This is a bounded literature-search result, not proof of novelty. The review is not exhaustive, and several central ingredients have clear precedents. The defensible current description is therefore **an independently developed synthesis and experimental image-resampling application of known reconstruction, conservation and footprint-integration ideas**, with a specific local node construction and final-grid calibration workflow.

## References

1. A. R. Smith, “A Pixel Is Not a Little Square,” Microsoft Technical Memo 6, 1995. [PDF](https://www.cs.princeton.edu/courses/archive/spr05/cos426/papers/smith95b.pdf)
2. D. P. Mitchell and A. N. Netravali, “Reconstruction Filters in Computer Graphics,” *Computer Graphics*, 22(4), 221–228, 1988. [doi:10.1145/378456.378514](https://doi.org/10.1145/378456.378514)
3. M. Unser, “Splines: A Perfect Fit for Signal and Image Processing,” *IEEE Signal Processing Magazine*, 16(6), 22–38, 1999. [doi:10.1109/79.799930](https://doi.org/10.1109/79.799930)
4. K. M. Fant, “A Nonaliasing, Real-Time Spatial Transform Technique,” *IEEE Computer Graphics and Applications*, 6(1), 71–80, 1986. [doi:10.1109/MCG.1986.276613](https://doi.org/10.1109/MCG.1986.276613)
5. P. S. Heckbert, *Fundamentals of Texture Mapping and Image Warping*, UCB/CSD-89-516, 1989. [Report](https://www2.eecs.berkeley.edu/Pubs/TechRpts/1989/5504.html)
6. P. A. Ullrich and M. A. Taylor, “Arbitrary-Order Conservative and Consistent Remapping and a Theory of Linear Maps: Part I,” *Monthly Weather Review*, 143(6), 2419–2440, 2015. [doi:10.1175/MWR-D-14-00343.1](https://doi.org/10.1175/MWR-D-14-00343.1)
7. N. Robidoux, A. Turcotte, M. Gong, and A. Tousignant, “Fast Exact Area Image Upsampling with Natural Biquadratic Histosplines,” in *Image Analysis and Recognition*, LNCS 5112, 85–96, 2008. [doi:10.1007/978-3-540-69812-8_9](https://doi.org/10.1007/978-3-540-69812-8_9)
8. W. Barsukow, J. Hohm, C. Klingenberg, and P. L. Roe, “The Active Flux Scheme on Cartesian Grids and Its Low Mach Number Limit,” *Journal of Scientific Computing*, 81, 594–622, 2019. [arXiv:1812.01612](https://arxiv.org/abs/1812.01612)
9. X. Li and M. T. Orchard, “New Edge-Directed Interpolation,” *IEEE Transactions on Image Processing*, 10(10), 1521–1527, 2001. [doi:10.1109/83.951537](https://doi.org/10.1109/83.951537)
10. D. Marr and E. Hildreth, “Theory of Edge Detection,” *Proceedings of the Royal Society B*, 207(1167), 187–217, 1980. [doi:10.1098/rspb.1980.0020](https://doi.org/10.1098/rspb.1980.0020)
11. P. J. Burt and E. H. Adelson, “The Laplacian Pyramid as a Compact Image Code,” *IEEE Transactions on Communications*, 31(4), 532–540, 1983. [doi:10.1109/TCOM.1983.1095851](https://doi.org/10.1109/TCOM.1983.1095851)
