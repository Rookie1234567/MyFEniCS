# Task032 distributed cross-section QEP

## Call chain

```text
target_stage4_config
-> stage4_axis_plan
-> build_matching_cross_section
-> build_cross_section_spaces
-> build_cross_section_floquet_constraints
-> build_distributed_constraint_transform
-> assemble_quadratic_beta_operators
-> solve_quadratic_beta_modes
```

`build_matching_cross_section` reuses the reviewed Stage-4 x/y tensor axes. A
cross-section cell is therefore the exact x/y face of a future local 3D
hexahedron; no second material-plane fitting policy is maintained.

## Mixed space and polynomial

The mode field is represented by `Et` in 2D `N1curl(p)`, `Ez` in
`Lagrange(p)`, and `W=Et x Ez`, with
`E(x,y,z)=(Et,Ez) exp(i beta z)`. The assembled polynomial is

```text
Q(beta) = K0 + beta K1 + beta^2 K2.
```

`K0` contains transverse curl-curl, longitudinal grad-grad and both electric
mass terms. `K1` contains the two signed transverse/longitudinal couplings.
`K2` is the transverse mass block and has a zero longitudinal block. The
leading coefficient is therefore singular by physical design; the code must
not relabel this problem as a regular Hermitian generalized eigenproblem.

## Double Floquet constraints

The transverse Nedelec trace uses polynomial probe fields to recover the
orientation transform on each matching boundary facet. The scalar trace uses
coordinate pairing with a direct top-right to bottom-left corner constraint,
so no master is also a slave. Only periodic-boundary records are all-gathered.
Interior matrices and eigenvectors remain distributed.

`dolfinx_mpc` cannot directly create periodic constraints for this vector
space in the qualified DOLFINx 0.10 image. The Task032 implementation maps
collapsed transverse/scalar dofs into the parent mixed space and constructs a
distributed sparse transformation `u=Cq`. Each QEP coefficient is reduced as
`C^H K C` with PETSc sparse matrix products.

Two implementation details are intentional:

- `locate_dofs_topological(..., remote=False)` is used per local boundary
  facet; default remote lookup inside rank-dependent loops can deadlock.
- petsc4py `hermitianTranspose()` is in-place when no output matrix is passed.
  Task032 supplies an explicit output matrix, preserving `C` across all four
  reductions (`K0`, `K1`, `K2`, electric mass).

## Solver, ownership and normalization

The primary backend is native `SLEPc.PEP/TOAR` with target-magnitude
shift-invert and MUMPS LU. The singular leading block is submitted directly;
there is no dense solve and no default companion doubling. Returned reduced
vectors stay PETSc-distributed and are reconstructed with `C.mult`; no full
eigenvector is gathered to rank 0.

Phase 2 applies a reproducible cross-section electric-L2 normalization using
the separately reduced mass matrix. This proves a stable field scale but is
not the final lossy-mode power/biorthogonal normalization. Poynting direction,
left modes, `Q'(beta)` normalization and near-degenerate subspace handling are
Phase 3 responsibilities.

## Validation and limits

`test_32_task032_cross_section_qep.py` covers matching mesh/material fields,
double Bloch phase, orientation-probe residual, chain-free reduction, analytic
air beta, complex lossy beta, reciprocal `+/- beta` pairs, polynomial residual,
electric-L2 normalization and MPI ownership. The Phase 2 benchmark runner is
`benchmarks.run_task032_phase2_qep`; it keeps eigenvectors/matrices out of Git
and writes only lightweight scalar evidence.

For a formal Windows bind-mount run, `--verified-clean-sha` is the host-side
clean attestation and the container rechecks the mounted `HEAD`. Container-side
`git status` is not authoritative here because host `core.autocrlf=true` makes
the Linux Git client report every CRLF file as modified.

This module does not yet classify modes by Poynting flux, propagate them
through 100 nm, project 3D traces, or assemble a Hybrid direct system.

## Formal Phase 2 evidence

The clean MPI4 record is
`benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/qep_phase2.json`
on source `33211a4ac6d4f6717351197a93c506e1adec609f`. It contains six cases:
air h5/h3/h2/h1.5, homogeneous lossy h2 and current Stage4 x/y material h3.
Air analytic errors decrease strictly to `1.12629%` at h2 and `0.454640%` at
h1.5; the maximum selected QEP relative residual is `1.8177e-15`. Case080's
full checker passes `277/277` gates. Per-rank process-lifetime memory peaks in
this record are diagnostics only and are not summed or used as the final
Hybrid memory authority.
