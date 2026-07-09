# Next Decision

## Decision

当前 AMS/HX + true-FE sampled Schur 主线继续，不暂停。

下一步开启：

```text
Task019: p=2 h=5 qualification for residual-corrected true-FE sampled Schur
```

## Why

Task018 已经在 `default100 p=1 h=5` 上通过 strong gate：

| gate | result |
|---|---:|
| baseline | `2.145878536e-2` |
| best residual-corrected loop | `1.661623468e-3` |
| improvement | `12.914x` |
| strong threshold | `<=2e-3` 或 `>=10x` |

## Next Task Scope

| step | action | stop condition |
|---|---|---|
| A | p=2 h=5 complex export / memory preflight | export RSS or matrix size exceeds workstation-safe range |
| B | p=2 h=5 baseline FE-AMS + aux identity | cannot reproduce stable baseline or true residual |
| C | p=2 h=5 selected `top_bottom_y` SciPy GMRES rtol `1e-2` one-shot | no `<1e-2` or `>=2x` improvement |
| D | p=2 h=5 residual outer loop, one cycle first | rebound or no improvement after cycle 1 |
| E | only if p=2 h=5 remains positive | compare longer segment 500/1000 and minimal mode-set escalation |
| F | only if p=2 h=5 strong positive | consider productionization plan and p=2 h=2 preflight task |

## Keep Closed

```text
full p=2 h=2
h=1.5
full 708-mode Schur
Petrov W expansion
right additive PC with true-FE basis
PETSc selected FE-AMS same-process RHS solve as main path
unconverged official R/T/A
```

## Engineering Risks To Carry Forward

### Risk B: SciPy selected FE RHS is research-only

Task018's best selected FE response uses SciPy GMRES with diagonal preconditioning and `rtol=1e-2`. It is a single-process exported-matrix research path, not an MPI production solver. Task019 may use it for qualification, but productionization must later replace or wrap it safely.

Possible engineering routes:

```text
MPI-distributed selected FE RHS solve
isolated-process selected FE response service
offline/cache selected response construction
safe service layer outside ordinary Stage4 production solve
```

### Risk C: PETSc selected FE-AMS lifecycle issue

The same-process PETSc selected FE-AMS path still fails in setup and may poison later AMS communicator state. Keep it disabled by default. If tested, run it opt-in and isolated from stable runs.

Productionization must redesign:

```text
communicator ownership
hypre AMS setup/reuse policy
PC lifetime and destroy order
selected RHS service isolation
```

## Alternative If p=2 Fails

If p=2 h=5 cannot retain the p=1 residual-correction signal, the next routes are:

| route | reason |
|---|---|
| layered-background / RCWA-like approximate inverse | better physics for periodic layered propagation |
| two-level DDM / sweeping | better for high-frequency indefinite propagation |
| isolated-process selected FE response service | avoids PETSc/hypre communicator lifecycle issues |
