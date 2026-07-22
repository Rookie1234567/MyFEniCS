# Task035 当前结果汇总

## 状态

```text
phase_a = accepted
phase_b_algebraic_precursor = pass
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
phase_c_low_cost = in_progress
phase_c_formal_completion = pending_B3_B4
phase_d_production_backend_unlocked = false
heavy_p4_authorized = false
```

Task035 当前只完成低成本真实 FE 最低 Gate，没有运行目标光栅、adaptive cycle、p4/h5
heavy case，也没有选择 production mesh backend。

## Phase B 证据

| 项目 | 结果 | 证据 |
|---|---|---|
| algebraic precursor | pass；不得称 formal FE qualification | `records/fixture_summary.json` |
| R2 | `resolution_diagnostic_pass`；只记录 `chi=|k|h/p` | `src/validation/task035_hcurl_estimator_fixtures.py` |
| B1 real periodic Nédélec | p1/p2 pass；实际 UFL volume/jump、Floquet trace 与 fault injection | `records/real_fe_mpi1.json` |
| B2 real flat lossy layer | 三个实际 h/p 点 pass；piecewise-complex DG0、field/goal/estimator trend、DtN perturbation | `records/real_fe_mpi1.json` |
| serial/MPI2 identity | pass；scalar metrics differences = `{}` | `records/real_fe_mpi_identity.json` |
| B3 material-interface/corner | pending | Phase C-low-cost 并行项 |
| B4 Hybrid Et/Ht、M/DtN | pending | Phase C-low-cost 并行项 |
| R4 equilibrated | `formula_defined` | research lane |

## B1/B2 代表数值

| Fixture | 离散点 | field error | R1 indicator | official fixture goal |
|---|---:|---:|---:|---:|
| B1 periodic | p1, 2×2×2 | 6.0837e-2 | 1.5326 | n/a |
| B1 periodic | p2, 2×2×2 | 1.6905e-3 | 1.0031e-1 | n/a |
| B2 lossy layer | p1, 1×1×2 | 1.7331e-1 | 9.4576 | R00 error 5.55e-17 |
| B2 lossy layer | p1, 2×2×4 | 4.5161e-2 | 5.2798 | R00 error 1.39e-16 |
| B2 lossy layer | p2, 2×2×4 | 2.2355e-3 | 5.9303e-1 | R00 error 4.09e-16 |

这些值来自解析/制造场在真实 Nédélec 空间中的离散与 UFL quadrature，不是 PDE solve，
也不是目标 13.5 nm 光栅的正式 R/T/A。

## 下一步约束

Phase C-low-cost 只允许 estimator bake-off 和低成本 component work。B3/B4 必须在
Phase D backend 决策或任何 p4/h5 adaptive heavy case 前通过或形成明确
`controlled_negative`。R4 不阻塞低成本主线，但不得提升为 production estimator。
