# Task032 mode classification and biorthogonal basis

## Call chain

```text
solve_quadratic_beta_modes
-> build_biorthogonal_mode_basis
   -> PoyntingFluxEvaluator
   -> explicit adjoint QEP
   -> left/right assignment
   -> near-degenerate block normalization
-> pair_reciprocal_mode_bases
-> track_mode_bases
```

The implementation is in `src/modes/mode_classification.py`. It consumes the
distributed right modes from Phase 2 and transfers their ownership into a
`BiorthogonalModeBasis`; destroying the basis destroys both right and left
vectors.

## Poynting direction and normalization

For `E(x,y,z)=(Et,Ez) exp(i beta z)` and the project's `e^{-i omega t}`
convention, the impedance-scaled magnetic field is reconstructed as

```text
Hx = (d_y Ez - i beta Ey) / (i k0 mu_r)
Hy = (i beta Ex - d_x Ez) / (i k0 mu_r).
```

`PoyntingFluxEvaluator` copies only the rank-local part of the distributed
full vector into a mixed DOLFINx function, scatters ghosts and assembles
`0.5 Re integral(Ex conj(Hy)-Ey conj(Hx)) dA`. No full vector is gathered.
Modes with resolved nonzero flux are classified by its sign and scaled to
`abs(Pz)=1`. Near-zero-flux modes instead use the sign of `Im(beta)`: positive
means decay along `+z`, negative means decay along `-z`; an unresolved real
near-zero-flux mode is explicitly marked cutoff/ambiguous.

The missing vacuum-impedance factor is a common positive scale and therefore
does not alter direction or normalized modal coefficients. Physical-unit
power conversion belongs at the eventual interface/output layer.

## Left modes and QEP biorthogonality

SLEPc 3.24 PEP has no two-sided Python interface in the qualified image. The
code therefore solves the sparse distributed adjoint polynomial

```text
K0^H + lambda K1^H + lambda^2 K2^H,
lambda approximately conj(beta).
```

It pairs adjoint and right modes with a maximum-weight assignment. For two
right eigenvalues `beta_i`, `beta_j`, the QEP overlap is

```text
G_ij = left_i^H [K1 + (beta_i + beta_j) K2] right_j.
```

The diagonal is `left_i^H Q'(beta_i) right_i`. Singleton and separated modes
are scaled diagonally. A repeated/near-degenerate block forms its small dense
`G`; when the beta spread is within the block-rotation tolerance, the left
basis is transformed by `(G^{-1})^H`. Singular or condition-greater-than-
`1e12` blocks fail closed rather than using an unstable pseudoinverse.

Only mode-count-sized overlap matrices are dense and replicated. QEP
coefficients and full/reduced left/right vectors remain PETSc-distributed.

An important petsc4py detail is that `VecDot(x,y)` evaluates `y^H x`. The
matrix action must therefore be passed first and the left vector second to
compute `left^H action`. The first research test caught the reversed order:
power signs were correct, but the nominal block inverse produced a large
non-identity overlap. The corrected order reduces the air block error to about
`5e-12` in the h5 probe and below `3e-15` in the MPI4 h10 research record.

## Reciprocal pairing and tracking

Positive and negative bases are paired by a Hungarian assignment combining
`abs(beta_plus+beta_minus)` with electric-mass field overlap. The report keeps
beta error, field overlap, opposite-direction identity and passive-branch
status separately; a field overlap is diagnostic rather than a universal
pass/fail threshold inside a degenerate polarization block.

For adjacent parameters, `track_mode_bases` maximizes the left/right QEP
overlap. Mode-count changes leave explicit unmatched indices. Repeated groups
are additionally compared as subspaces: electric-mass Gram matrices are
whitened, singular values are computed, and the maximum principal angle is
reported instead of forcing arbitrary individual eigenvectors to agree.

This follows the local paper evidence: the 2023 waveguide-mode analysis notes
that complex or repeated propagation constants require a small block system,
and the 2018 nested-FE mode-matching formulation uses a mode transformation
matrix when degenerate FE modes are not already orthonormal.

## Validation and limits

`test_33_task032_mode_classification.py` covers propagating, lossy,
evanescent and cutoff branch rules; air positive/negative power; explicit
adjoint residuals; block `Q'` biorthogonality; reciprocal identity; complex
lossy beta; MPI ownership; angle tracking; mode-count changes; and principal
angles. MPI4 runs the distributed positive-basis core, while repeated negative
and adjacent-parameter solves stay in the serial small-dense contract to avoid
duplicating expensive shift-invert setups in every MPI regression.

`benchmarks.run_task032_phase3_modes` is the research/formal runner. Its clean
MPI4 record is
`benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/modes_phase3.json`
on source
`72dca66b70515bcf6ccef239005afa43028df72b`. It covers air, homogeneous
lossy and current Stage4 x/y materials, an air reciprocal basis and 80 to 79.8
degree tracking. Air/lossy biorthogonality errors are about `1e-15`, the
patterned error is `2.46e-10`, and the tracking principal angle is
`0.005918 rad`. Case080 passes `282/282` gates. h10 is a classification/
normalization contract, not a replacement for Phase 2 beta accuracy or the
later h3 Hybrid comparison.

This phase does not yet build stable 100 nm propagation, extract 3D interface
traces or solve either Hybrid direct formulation.
