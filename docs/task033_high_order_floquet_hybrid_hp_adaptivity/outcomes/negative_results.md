# Task033 负结果与停止边界

## 1. Current findings

| Finding | Observation | Root cause / interpretation | Decision | 数据身份 | Evidence |
|---|---|---|---|---|---|
| p3/p4 base 3D Floquet path unavailable | source dispatcher and mesh guard reject degree above 2 | implementation is explicitly p1/p2-only | generalize before runtime; do not call p3/p4 qualified | static source audit | `high_order_assumption_audit.md` A01–A05 |
| formal high-order 2D Floquet route not yet accepted | current facet transform uses polynomial probes and pseudo-inverse | task requires entity-local verifiable ordinary path | generalize or restrict old path to diagnostics | static source audit | A11 |
| Hybrid interface load uses fixed quadrature 8 | literal compiler option | not yet tied to field/geometry/coefficient degree | generalize and perform raised-order comparison | static source audit | A14 |
| current host-free-memory snapshot is small | 1.811 GiB free during Phase 0 query | other host/VM workloads consume memory | veto large launch until refreshed preflight passes | measured snapshot | `environment_and_base.md` |
| p4 cost without accuracy gain | unknown | no experiment yet | retain as `not_run`; never force a positive claim | not_run | Case090/091 pending |
| h/p compression below target | unknown | no experiment yet | retain measured classification if observed; 3x is not p2 minimum pass line | not_run | adaptive study pending |

## 2. Stop conditions

| Gate failure | Required action | Current status |
|---|---|---|
| p3 or p4 algebra/orientation fails | stop that degree before Hybrid qualification | not_run |
| no native safe variable-p path | close as fixed-p high-order plus h-adaptive feasibility | pending framework audit |
| two memory predictions or upper Gate fail | record `not_run_by_memory_gate`; do not risk OOM/swap | not_run |
| p4 adds cost without accuracy benefit | preserve as a negative engineering result | not_run |
| ordinary p1/p2 or Case080 regression | fix regression before continuing | not_run |

The entries above distinguish static blockers and environment vetoes from numerical
failures. No p3/p4 PDE, adaptive solve or interface trade-off has failed because none has
been run yet.

