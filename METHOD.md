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
