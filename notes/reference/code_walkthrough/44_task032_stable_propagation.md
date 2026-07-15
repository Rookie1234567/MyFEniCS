# Task032 Phase 4 stable two-sided propagation

## 1. Scope

Phase 4 is deliberately independent of 3D interface coupling. It consumes the
Phase 3 fields `beta`, `direction`, and `passive_branch_valid` and maps modal
coefficients across the uniform 100 nm middle segment. It does not extract a
3D trace, assemble a Hybrid matrix, or introduce interface reflection.

The implementation is `src/modes/stable_propagation.py`. Unit and integration
coverage is in `src/test/test_34_task032_stable_propagation.py` and the existing
Phase 3 air-basis test. The research/formal entry point is
`benchmarks.run_task032_phase4_propagation`.

## 2. Directed exponent

For a mode with the repository convention `exp(i beta z)`, the forward block
maps bottom to top with

```text
p+ = exp(+i beta+ L).
```

The backward block maps top to bottom, so its coordinate displacement is
`-L` and it uses

```text
p- = exp(-i beta- L).
```

For a reciprocal pair `beta- = -beta+`, both directed factors are identical.
If `Im(beta+) > 0` and `Im(beta-) < 0`, both magnitudes are at most one. This
explicit travel sign removes the ambiguity of writing one `exp(i beta L)` for
both directions.

`_stable_factor` separates attenuation from phase. A small positive log
magnitude caused only by tolerance-level roundoff is clipped to zero; a real
growing branch fails closed. Very strong attenuation may underflow to zero,
which is finite and physically harmless. No inverse factor is constructed.

## 3. Two-port API

`TwoSidedPropagation.apply` uses the scattering ordering

```text
incoming = [bottom_forward, top_backward]
outgoing = [bottom_backward, top_forward].
```

Each outgoing array depends only on the incoming array travelling toward that
port. Therefore the uniform block contains no local reflection term. Storage
is one factor per forward/backward mode, or O(M); a dense transfer matrix is
not materialized.

`compose` multiplies directed diagonal factors and checks mode indices and beta
identity before composition. It implements `P(L1+L2)=P(L2)P(L1)` without any
growing inverse propagation.

## 4. Diagnostics and negative controls

`diagnose_reciprocity_and_passivity` pairs forward beta with negative backward
beta using a small Hungarian assignment. It reports beta error, directed-factor
error, unmatched modes, and maximum factor magnitude. The diagnostic does not
claim reciprocity for arbitrary nonreciprocal media; it checks the reciprocal
Case080 contract.

The tests cover:

- reflection-free single-mode forward/backward propagation;
- lossy and strongly evanescent decay over 100 nm;
- exact two-segment composition within floating-point tolerance;
- reciprocity/passivity plus a nonreciprocal negative control;
- rejection of growing, ambiguous, uncertified, and incompatible branches;
- direct consumption of real Phase 3 classified air modes.

The formal runner also reads the frozen Phase 3 record for air, homogeneous
lossy, and current Stage4 x/y cases. Where Phase 3 intentionally did not solve
the negative lossy/patterned basis, the runner labels and uses the reciprocal
`-beta` mirror; only the air case uses two independently solved bases.

The clean MPI4 record is
`benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/propagation_phase4.json`
on source `9206e9c964db387448551cdefdc88081ef705441`. Its maximum 100 nm
composition error is `9.42e-16`, all local reflection norms are zero, and the
largest factor magnitude is `0.9999999999999997`. The record is tied to the
exact Phase 3 record SHA-256 and Case080 passes `286/286` gates.
