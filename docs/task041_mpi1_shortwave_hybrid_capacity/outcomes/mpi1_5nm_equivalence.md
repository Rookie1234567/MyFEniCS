# 5 nm MPI1 equivalence

5 nm 必须区分 Task039 inherited MPI8 baseline、本机 MPI8 reproduction、MPI1 attempt 和 source-only audit。下表保留实际失败阶段，不把失败概括为数值不等价。

| attempt | source SHA | wall (s) | 轻量 summary 分类 | 精确结论 |
|---|---|---:|---|---|
| `20260902T230819.318085Z` | `812118af52333acdfb6ad9675790853e2730c797` | `13659.649299055978` | `task041_resource_sample_failure` | resource-sample 阶段失败；equivalence 未建立 |
| `20260904T101800.303093Z` | `def547cfd139b6377b0cae2ba1736ec3591814b0` | `3301.179331702064` | `task041_producer_failure` | producer 阶段失败；equivalence 未建立 |
| `20260904T112637.063178Z` | `24392bfcc76dc3012ae628ae9a210434707f36a7` | `13316.443165645935` | `task041_resource_sample_failure` | resource-sample 阶段失败；equivalence 未建立 |
| `20260904T152109.607989Z` | `d6c71401a7105d2c67e22596e40461354cfda21f` | `49346.574875007966` | 外层 `task041_resource_sample_failure` | consumer solve/recovery/physics 与候选 RTA 通过；但 `external_key_binding_pass=false`，600 keys 数量相同而 hash 不符；terminal process-tree sample unreadable |

最后一次 attempt 不能形成合格 consumer/workflow 内存 authority 或完整 equivalence。外层 resource-sample failure 与 consumer 内部通过的 solve/physics Gate 必须同时保留，不能只写笼统 resource failure。

## source-only semantic audit

root=`task041_s1_source_only_p6h4_m480_mpi1_6ae90799`，source=6ae907991ceb3323c06b351d13a9557685e4d713：keys、roundtrip、repeat 通过，但 `current_vs_persisted=3.826978841496932e-9 > 1e-12`，正式分类=`REFERENCE_SOURCE_SEMANTICS_CHANGED`。旧 MPI8 authority 保留；corrected MPI1 不得声明完整 MPI 等价。

## MPI8 reference separation

Task039 inherited record 为 `benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json`，peak=`80.0258560180664 GiB`、wall=`10126.231902 s`、full numerical/recovery/physics PASS。本机 MPI8 reproduction peak=`80.2187461853 GiB`、elapsed=`8357.347033 s`、swap=`0`，也通过 solve/recovery/physics，但它是用户授权的独立本机复现。

因此 5 nm MPI1/MPI8 equivalence 结论为 `equivalence not established`，而不是 `numerical inequivalence`。Task041 3 nm physics Gate 后的 MPI1 lane 不再运行，统一为 `NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE`。
