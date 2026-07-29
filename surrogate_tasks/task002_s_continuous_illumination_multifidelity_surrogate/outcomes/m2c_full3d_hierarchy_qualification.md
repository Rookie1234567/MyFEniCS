# Task002 M2C Full3D hierarchy qualification

## Decision

The parameterized Full3D static route is solver-domain qualified, but the
candidate p4→p5 multifidelity hierarchy is not qualified for production. The
frozen next-stage candidate is:

```text
production_surrogate = Full3D static uniform N1curl p5/h10 single fidelity
```

This is a routing decision only. M3, four-dimensional bulk generation,
surrogate fitting, angle DOE, and inversion remain closed pending Review V4.

## Clean implementation and execution identity

All new PDE evidence is bound to clean implementation SHA:

```text
fe0e53571491f21e4774d7576d9285f9a09df705
```

The formal models are `S_LF_FULL3D_STATIC_P4_H10` and
`S_HF_FULL3D_STATIC_P5_H10`. Both use static assembly, a boundary-fitted fixed
logical topology `(6,3,14)`, hexahedra, MPI2, one thread per rank, and actual
uniform Basix/UFL `N1curl` elements of degree 4 or 5. Every new solve was run
alone under the watchdog. No Docker route was used.

## Fixed topology and real-run smoke

For each fidelity, all nine combinations
`h={115,120,125} nm × w={16,17,18} nm` have identical:

- cell count and logical connectivity hash;
- material-tag topology hash;
- Floquet entity topology hash;
- DoF-layout identity hash;
- topology/element hash.

The coordinate hash changes at all nine geometries, as intended. Ten real-run
smokes (center plus four axial geometries, p4 and p5) match the corresponding
static topology audit exactly.

## p5 80-angle map

The center-geometry p5/h10 map is complete at all 80 prescribed angles:

```text
grazing = [0.5,0.75,1,2,4,6,8,10] deg
azimuth = [0,5,10,15,20,30,45,60,75,90] deg
```

Twenty-one Case114 points were reused without rewriting their raw evidence and
59 missing points were run on the M2C clean baseline. The result is 80/80
completed direct solves with residual, energy, fixed-order, zero-swap, and
cleanup Gates passing. For the 59 new points, elapsed time was 61.55–85.27 s;
maximum peak RSS was 4,417,040,384 bytes; peak swap was zero.

## p4→p5 quantitative screen

Aggregate-channel paired metrics over the 80 angles are:

| Channel | Pearson | Spearman | NRMSE | Max absolute discrepancy |
|---|---:|---:|---:|---:|
| R_total | 0.95576 | 0.98174 | 0.25190 | 0.35023 |
| T_total | 0.99856 | 0.98167 | 0.02951 | 0.05415 |
| A_balance | 0.77093 | 0.74587 | 0.26063 | 0.33018 |
| A_volume | 0.77093 | 0.74587 | 0.26063 | 0.33018 |

The mean primary-channel angle-gradient sign agreement is 0.91066, above the
0.85 advisory Gate. The absorption-channel Spearman values are only 0.74587,
below the required 0.90, so the unified LF relation fails.

The frozen nine-angle validation pilot was kept disjoint from the 80-point
training candidates. Three off-grid `g=5.25°` validation angles were added as
paired p4/p5 qualification solves. Mean normalized errors were:

| p5 budget | Raw p4 | p5-only interpolation | p4 + learned discrepancy |
|---:|---:|---:|---:|
| 12 | 0.15483 | 0.09816 | 0.02126 |
| 16 | 0.15483 | 0.09118 | 0.02313 |
| 24 | 0.15483 | 0.04453 | 0.01386 |

Although the discrepancy pilot is favorable, it does not override the failed
absorption correlation Gate.

## Geometry sensitivity pilot

The required 5 geometries × 4 angles × 2 fidelities are complete (40/40). All
four noise-weighted p5 Jacobians have rank 2. LF/HF sensitivity results are:

| grazing/azimuth | cosine | derivative sign agreement | p5 Jacobian condition |
|---|---:|---:|---:|
| 0.5°/0° | 0.68425 | 0.89224 | 14.67 |
| 0.5°/45° | 0.99342 | 0.95455 | 18.73 |
| 2°/15° | 0.82875 | 0.86638 | 16.04 |
| 10°/45° | 0.99997 | 0.95455 | 5.55 |

The 0.5°/0° and 2°/15° cosine values provide an additional reason not to use a
single p4→p5 multifidelity correction for inversion-sensitive geometry effects.

## Discretization semantics

The four Case114 p4/h7.5 anchors remain independent h-refinement audits only.
Their conservative p4/h7.5↔p5/h10 envelope for aggregate channels is:

| Channel | Conservative absolute envelope |
|---|---:|
| R_total | 2.73315e-3 |
| T_total | 3.78696e-4 |
| A_balance | 2.64436e-3 |
| A_volume | 2.64436e-3 |

Full3D p5/h10 is the best available operational HF, not continuum truth. The
downstream uncertainty contract is frozen as:

```text
Sigma_total = Sigma_measurement + Sigma_surrogate + Sigma_discretization
```

The channel-wise envelope is preserved in `discretization_uncertainty.json`.
