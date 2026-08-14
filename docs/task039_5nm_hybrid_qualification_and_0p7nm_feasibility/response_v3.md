# Task039 Review V2 最终回应（V2-8）

本回应收口 Review V2，不启动新的 PDE/MPI heavy run。V2-7 的运行是用户明确覆盖下
的 diagnostic-only lane；它没有建立 h5 Hybrid 物理资格。

## 1. 阶段状态

| 阶段 | 状态 | 证据 |
| --- | --- | --- |
| E0/T0 inherited audit | completed | [inherited audit](outcomes/review_v2_inherited_audit.md) |
| E1/T1 contracts and focused wiring | completed | [test summary](outcomes/test_summary.md) |
| E2/T3 Full3D direct h10 | historical authority only | [fixed-grid outcome](outcomes/fixed_grid_full3d_reference.md) |
| E3/T4 Full3D iterative h10 | negative | `5NM_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM` |
| E4/T5 Hybrid direct M funnel | completed negative | `M_robust_h10` not established |
| E5/V2-1 h5 Full3D readiness | completed | [readiness](outcomes/full3d_h5_direct_and_convergence.md) |
| E6/V2-2 h5 Full3D direct | own authority pass | [h5 direct outcome](outcomes/full3d_h5_direct_and_convergence.md) |
| E7/V2-3 h6-vs-h5 convergence | completed negative | `FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_AT_P6H5` |
| E8/V2-4 h5 Hybrid direct readiness | completed | [Hybrid readiness](outcomes/h5_hybrid_direct_readiness.md) |
| E9/V2-5 h5 Hybrid direct | own pass; same-grid model fail | `H5_M480_HYBRID_MODEL_FAIL` |
| E10/V2-6 same-grid and memory | completed negative | [memory attribution](outcomes/h5_hybrid_direct_memory_attribution.md) |
| V2-7 h5 Hybrid iterative M480 MPI8 | numerical negative | [iterative outcome](outcomes/h5_hybrid_iterative_m480_mpi8.md) |
| V2-8 iterative-vs-direct physics | `not_run_not_applicable` | no valid iterative recovery/physics output |

## 2. V2-6 boundary preserved

V2-6 remains `H5_M480_HYBRID_MODEL_FAIL`. Five of nine primary rows failed; the worst
channel is `top(-4,0,s)` with power relative error `0.0506995` and complex-amplitude
relative error `0.1525935`, both against `1e-3`. The weak set has 29 failures of 30.
The all-604 weighted power aggregate is `8.685769e-5 <= 1e-4`, but that aggregate does
not override the primary order failures. The user authorized only a diagnostic continuation;
this is not a physical qualification.

## 3. V2-7 actual result

The iterative method uses Krylov updates to approach the frozen linear equation. A small
modal residual alone is not enough: the FE/interface residuals must also be small before
field recovery and physical observables are valid.

| Gate | actual | limit | status |
| --- | ---: | ---: | --- |
| exit / classification | `4` / `worker_nonzero` | exit 0 | fail |
| iterations / reason | `6000` / `DIVERGED_MAX_IT` | reason >0, at most 6000 | fail |
| global / bottom / top true residual | `0.9679803826 / 0.9882585936 / 0.9641613365` | each `<=5e-9` | fail |
| modal true residual | `4.861832e-12` | `<=5e-9` | pass |
| projection / traction / external q | not_available | `1e-8 / 1e-8 / 1e-10` | fail-closed |
| R/T/A/A_volume / closure | not_available | finite / `<=1e-5` | fail-closed |
| recovery / selected E/H / canonical | not_entered | complete | fail-closed |
| manifest external inventory | `604` | exact identity | manifest only; no valid output |

Raw root as found in the workspace:

```text
/home/Projects/MyFEniCS/results/task039_5nm_hybrid_iterative_m480_candidate/task039_5nm_hybrid_iterative_p6h5_m480_mpi8__hybrid_iterative__mpi8__M480/20260814T134138.138043Z
```

The run source is `be5be4680065268303070bfb10c29f4511d483eb`; it predates the pushed
telemetry patch `29ead2cda47a88bd312913a6101826eaba977f9b`. The run completed naturally;
no signal or retry was issued. Full raw artifact hashes are in the [compact record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_iterative_m480_v1.json).

## 4. Resource and system boundary

| Item | measured value / status |
| --- | --- |
| RSS/PSS/USS | `83155.31640625 / 82055.1220703125 / 81869.0 MiB` |
| swap | `0`; warning and critical crossing false |
| hard policy | `224000000000 bytes` (`208.6162567138672 GiB` display); not reached |
| samples | `47810`; complete smaps `47809` |
| stage markers | setup/solve only, 2 of 18 |
| outer wall | `17187.881117 s` |
| linear solve timer | `14358.243030897 s` |
| recovery | not entered |
| direct factors / nested KSP | `0/0` / `false`; fixed ILU factors `1/1` |
| matrix system | matrix-free; global size `104640`; modal count `960` |

The iterative RSS is below the h5 Hybrid direct measured RSS `86744.54296875 MiB` by
`3589.2265625 MiB`, or `4.1376972771%`. This is a resource comparison from a failed
numerical run, below the Review meaningful-saving threshold of 20%; it is not a qualification.
No valid stage-aligned iterative attribution exists. The old raw has no process-tree sample
file or object ledger, and those missing artifacts are recorded as unavailable rather than zero.

## 5. Physics and next-step boundary

Because the residual Gate failed, iterative recovery, own physics, R/T/A, closure, selected
E/H and canonical packets were not validly formed. The iterative-vs-direct physics comparator
is therefore `not_run_not_applicable`, not a pass and not a fabricated failure number.

The final scientific boundary is:

```text
Full3D h5 own authority: pass
Full3D h6-vs-h5 convergence: negative
H5 M480 Hybrid direct same-grid: H5_M480_HYBRID_MODEL_FAIL
H5 M480 Hybrid iterative: H5_M480_HYBRID_ITERATIVE_SOLVER_FAIL
Hybrid physical qualification: not established
0.7 nm full PDE: not_run
MPI1 / M960 / M>480 / new PC: not_run and forbidden by this closeout
```

The h10 role remains `historical_underresolved_stress_anchor_only`; it is not a Full3D
5 nm reference, Hybrid physical authority, accuracy-qualified result, or 0.7 nm mesh-scaling
anchor. Ordinary defaults, `master`, and solver/input thresholds were not changed.

## 6. Commits, checks and repository state

| Item | status |
| --- | --- |
| prior telemetry fix | pushed `29ead2cda47a88bd312913a6101826eaba977f9b` |
| V2-8 Python changes | none |
| new tracked evidence | compact JSON above |
| full repository pytest | `cancelled / not_run` |
| PDE/MPI heavy after V2-7 | none |
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` |
| master | untouched |

The final docs/evidence commit SHA and post-push clean state are reported after the
lightweight JSON/document checks below.
