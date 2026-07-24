# Task035b outcomes summary

## 当前状态

```text
status = in_progress
geometry = Task034 fixed rectangular block grating only
formal_MPI = 8
ordinary_default_changed = false
irregular_geometry = out_of_scope_by_user / not_run / not_a_completion_gate
```

Task035b 已冻结可信的同网格 global p4/p5/p6 controls，完成高阶 entity DoF、
assembly-time exact cell condensation、MUMPS 生命周期优化、连续 p
smoothness classifier 和首个真实 physical regionwise-p 候选。首候选资源
显著改善，但 same-error Gate 明确失败，已作为 controlled-negative 保留。

## 正式结果

| path | Full3D-equivalent DoF | solved rows | matrix / factor NNZ | peak | build / MUMPS setup | true residual | numerical status |
|---|---:|---:|---:|---:|---:|---:|---|
| global p4 assembly-time | 53,084 | 21,824 | 8,184,464 / 40,151,936 | pair peak 10.590 GiB | 35.64 / 13.36 s | `2.35e-11` | control |
| global p5 assembly-time | 101,815 | 35,000 | 20,140,928 / 98,588,300–101,062,900 | pair peak 10.590–20.581 GiB | 187.89–198.19 / 37.26–42.15 s | `9.87e-12–1.04e-11` | control |
| global p6 assembly-time canonical | 173,802 | 51,272 | 41,989,040 / 211,651,232 | 15.964 GiB | 770.89 / 142.12 s | `1.36e-11` | accepted discrete baseline |
| p4-trace, p4/p6-interior regionwise | **88,994** | **21,824** | **8,184,464 / 42,888,832** | **6.072 GiB** | **175.43 / 11.45 s** | `1.17e-11` | **controlled negative accuracy** |

pair peak 包含顺序执行的两个 field 生命周期，不冒充单个 p5/p6 阶段峰值。
global p6 canonical 与 regionwise candidate 使用独立 MPI8 process-tree
memory authority，均为 0 swap。

## regionwise 候选 Gate

| Gate | result | decision |
|---|---:|---|
| active DoF minimum | 88,994 `<=90,000` | pass |
| matrix physically reduced | no full matrix/trace matrix/inactive p6 rows | pass |
| full explicit true residual | `1.1657e-11` | pass |
| geometry/tag/periodic/orientation | exact fixed-target identity | pass |
| strict R00 error / band | `2.9281e-4 / 3.1953e-5` | fail |
| strict R error / band | `2.9770e-4 / 3.2005e-5` | fail |
| T error / band | `3.8558e-3 / 2.1768e-4` | fail |
| Aclosure error / band | `3.5581e-3 / 1.8568e-4` | fail |
| normalized R/T/Aclosure | `27.704`, radius `1.732` | fail |
| significant orders/amplitudes | 12/12 significant channels fail | fail |
| selected volume complex-E | 9.8467%, band 0.5183% | fail |
| selected interface complex-E | 9.7778%, band 0.5220% | fail |

结论：成本信号为正，但固定 p4 trace 是精度瓶颈。该 lane 已关闭，不接入
Hybrid，也不因成本改善而放宽 R00/R/T/Aclosure、order、amplitude 或 field
Gate。

## classifier 与下一 lane

同网格 classifier 在 252 cells 上得到：

| action | cells |
|---|---:|
| p-down | 0 |
| p-keep | 147 |
| p-up | 105 |
| h-refine | 0 |

下一研究路线为 p5 shared trace、p4 low interior、selected p6 interior。
预算为 `68,551 + 342 * N_p6_cells`；`N_p6_cells <=62` 保持 minimum
`<=90k`，`N_p6_cells <=18` 保持 preferred `<=75k`。先完成 mixed
trace/interior element、exact embedding、all-low matrix equivalence 和 MPI
periodic tests；只有这些 Gate 通过后才允许下一次 MPI8 heavy PDE。

## Evidence index

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p4_p5_h10_assembly_time_condensed_independent_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_assembly_time_condensed_independent_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/same_mesh_p4_p5_p6_r5_hp_classifier_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/regionwise_p4trace_p6interior_h10_mpi8.json`
- ignored raw evidence:
  `benchmarks/artifacts/task035/actual_global_r5/hexahedron_regionwise_p4trace_p6interior_h10_pols_mpi8_20260724T061121Z/`

## 尚未完成

- p5-trace/p4-low/p6-selected mixed interior candidate；
- >=2x or <=90k 的 same-error positive candidate；
- best 1–2 candidates 的 Hybrid closure；
- 0.7 nm / 2 TiB resource model v3 更新；
- final Task035b response 和 selective-merge proposal。
