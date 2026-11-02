# Gate-CD M8/N14 32-worker static preparation (2026-11-02)

## Scope

This continuation prepares a separate 0.7 nm Gate-CD finite modal case. It uses the existing mapped Gate-CD geometry and materials, with 27,600 cells, degree-six Nedelec elements, surface quadrature q81, and volume quadrature q21. Visualization files remain disabled. The active port window is the signed rectangle `m=[-8,8], n=[-14,1]`, selected in preserved order from its finite `M8N64` parent. This is a finite-DtN case; `FULL_DTN_NOT_VERIFIED` remains in force.

| Identity | Frozen value | Evidence class |
|---|---|---|
| Parent mode inventory | 4,488 modes; SHA256 `6cf60807239dffc209b47336581e8bb50a5f4d986cba5bbdc06500f6271d3865` | derived from Gate-CD production mode objects |
| Active mode inventory | 1,088 modes; SHA256 `333e201cd5bd368a6f1a70a02949ff3099fdb2c8f6c05e93fc419a77430be353` | derived from the same parent objects |
| Parent selection | 1,088 ordered indices; SHA256 `1fc6bb7886a9858e3288ae45ee3ae50fea0bdf75881f03b52f45a26a3fe41fe1` | derived |
| Signed selected keys | SHA256 `03c5894de4fd5597da93a2971a1914ffca955b61e39a9f8db173d0fd39beebb0` | derived |
| Active classifications | 960 propagating; 1,026 power-carrying | derived; top/bottom counts are profile-validated |
| Execution | MPI size 1; 32 independently launched exact raw-cell-tensor processes; parent condensation, global assembly, and LU remain serial | implementation contract; no full case run |

The new input is `input/task40_gate_cd/gate_cd_0p7_mapped_m8n14_p6_direct_parallel32.dat`. The runner constructs the exact signed `M8N64` parent before selecting the active `M8N14` subrectangle. A centered rectangle is deliberately not used because it would create a different mode inventory.

## Cache and admission contract

The exact-cache template binds the clean source commit, resolved input payload, P6/complex128/q21 operator identity, 32-worker policy, and per-attempt tensor/carrier cache roots. At runtime the template is materialized against a fresh lease containing 32 distinct physical worker cores, a separate supervisor core, and a unique attempt id. The worker verifies that the manifest, scope, template, CPU list, and attempt roots agree before FE dispatch. MPI remains one rank; no parallel global matrix or factorization path is introduced.

The service must begin with the normal full host CPU affinity available to the admission sampler; it must not install a single-CPU cpuset before selection. The lease selects a supervisor and 32 worker cores after excluding observed active solver affinities. The one-shot runtime lease then narrows the supervisor and gives the worker command the sampled 32-CPU list. CPU ownership remains shared. The admission contract retains a 64 GiB host-available floor, observe-only swap, and no profile RSS hard cap.

## Verification and current status

| Gate | Status | Evidence / limitation |
|---|---|---|
| Input/profile and parent-to-active mode wiring | bounded smoke passed before the final admission/cache tests were added | 3 pure-Python tests passed under `/usr/bin/python3`; not a qualified ABI run |
| Syntax | passed | qualified interpreter `py_compile` over changed modules and the new test file |
| Lint | bounded static checks passed | Ruff passed for the new test file and undefined-name checks across changed files; full-file Ruff reports existing repository findings |
| Qualified ABI preflight | blocked in this sandbox | PETSc/MPI initialization failed because socket creation was denied (`errno=1`, PMIx listener failure) |
| Final pytest suite | not run | repository rules stop tests after the qualified MPI preflight fails |
| Fresh admission, systemd submission, FE mesh/carrier/matrix/factor/solve | not run | awaiting exact package review and a new passing full fresh check |

No FE or systemd unit was started. The package must retain `launch_authorized=false` and `fresh_status=NOT_RUN_PENDING_MAIN_REVIEW`. No R/T/A, runtime, or memory result is claimed. The mode truncation is independent of the previously completed G6 N14 comparison and does not inherit its physics identity or qualification.
