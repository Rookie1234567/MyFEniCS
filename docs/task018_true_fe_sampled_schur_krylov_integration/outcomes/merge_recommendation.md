# Merge Recommendation

## Decision

```text
merge_code: yes, research runner only
merge_docs: yes
production_default_change: no
p2_h5_next_gate: yes
```

## Rationale

| item | decision | reason |
|---|---|---|
| Task018 runner | merge | opt-in script, does not alter default solver behavior |
| production solver path | do not change | residual is `1.66e-3`, not production-like `1e-6` |
| SciPy selected FE RHS | keep as research method | strongest signal and reproducible in stable runner, but not MPI production |
| PETSc selected FE-AMS RHS | keep disabled by default | same-process path triggers PETSc error 101 / communicator lifecycle issues |
| p=2 h=5 | next task only | p=1 strong gate passed, but p=2 resource/robustness must be separately verified |

## Safe Merge Scope

The safe code scope is limited to:

```text
src/studies/run_stage4_true_fe_sampled_schur_krylov.py
```

It is a research runner. It must remain opt-in and should not be called by production R/T/A scripts.

## Engineering Risk B：SciPy selected FE RHS is not production MPI

Task018's best basis uses:

```text
SciPy GMRES + diagonal preconditioner, rtol=1e-2
```

This selected FE response path is:

```text
single-process / exported-matrix / research runner
```

It is not yet:

```text
MPI-distributed PETSc production solver infrastructure
```

Therefore a code merge is acceptable only as a research runner. Productionization must first provide one of:

```text
1. MPI-distributed selected FE RHS solve;
2. isolated-process selected FE response service;
3. offline/cache selected response construction;
4. another service layer that does not pollute ordinary Stage4 solve state.
```

## Engineering Risk C：PETSc selected FE-AMS lifecycle issue

The PETSc selected FE-AMS opt-in path was reattempted and failed in `KSPSetUp/PCSetUp` with error 101 / communicator lifecycle symptoms.

This is not evidence that the sampled Schur idea is mathematically wrong. It is an engineering risk in same-process PETSc/hypre AMS setup and teardown.

Productionization must address:

```text
1. avoid late/repeated setup/destroy of multiple hypre AMS helpers;
2. if PETSc selected FE-AMS is used, set it up early and reuse it;
3. prefer isolated process / subprocess service if communicator ownership remains fragile;
4. redesign MPI communicator ownership, PC lifetime, and destroy order before default use.
```

## Do Not Merge As Production

Do not wire this profile into the ordinary Stage 4 solver yet. Missing pieces:

1. no `1e-6` production-like convergence;
2. no p=2 h=5 validation;
3. SciPy FE RHS path is not MPI production code;
4. PETSc selected FE-AMS needs isolated-process or lifecycle redesign;
5. no official R/T/A should be emitted from this research workflow until convergence and production integration are validated.
