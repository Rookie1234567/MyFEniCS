# Task035 当前结果汇总

## 状态

```text
phase_a = accepted
phase_b_algebraic_precursor = pass
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
phase_c_internal_gate = complete_controlled_negative
B3_B4 = pass
phase_d_internal_gate = complete
execution_mode = continuous_autonomous_research
actual_global_two_level_R5 = pass_hexa_control
periodic_tetra_target_pipeline = in_progress
actual_adaptive_cycles = pending
production_estimator_selected = false
production_backend_selected = false
heavy_p4_authorized = true_by_review_v4_measured_evidence_required
```

Review V4 已把 Task035 切换为连续自主研究。首个真实目标 `p2/h10 -> p3/h10`
global two-level R5 已通过 clean-SHA、watchdog、MPI8、true residual、official R/T/A、
逐 owned cell 非负性与全局能量闭合 Gate。该正结果首先资格化 estimator mechanism；
它仍在 accepted hexa control 上，还没有选择 production mesh backend 或完成 adaptive cycle。

## Phase B 证据

| 项目 | 结果 | 证据 |
|---|---|---|
| algebraic precursor | pass；不得称 formal FE qualification | `records/fixture_summary.json` |
| R2 | `resolution_diagnostic_pass`；只记录 `chi=|k|h/p` | `src/validation/task035_hcurl_estimator_fixtures.py` |
| B1 real periodic Nédélec | p1/p2 pass；实际 UFL volume/jump、Floquet trace 与 fault injection | `records/real_fe_mpi1.json` |
| B2 real flat lossy layer | 三个实际 h/p 点 pass；piecewise-complex DG0、field/goal/estimator trend、DtN perturbation | `records/real_fe_mpi1.json` |
| serial/MPI2 identity | pass；scalar metrics differences = `{}` | `records/real_fe_mpi_identity.json` |
| B3 material-interface/corner | pass；actual Nédélec、DG0 tags、interface facets、fault/enrichment/directional metrics | `records/phase_cd_mpi1.json` |
| B4 Hybrid Et/Ht、M/DtN/QEP | pass；复用 accepted target traces、M80/120/160 与 matched-trace QEP | `records/phase_cd_mpi1.json` |
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

## Review V4：actual global two-level R5

| 项目 | measured result |
|---|---:|
| target | 13.5 nm、10° grazing、S、Task034 fixed geometry |
| pair | Full3D p2/h10 → p3/h10，同一 252-cell hexa control |
| MPI / clean SHA | MPI8 / `307907a1bb5a7a0a08c46ec75881d890fb3d1549` |
| true residual p2 / p3 | `2.304e-13` / `2.765e-12` |
| p2 R/T/A_volume | `0.9976471 / 0.00191059 / 0.000442293` |
| p3 R/T/A_volume | `0.0553985 / 0.4060679 / 0.5385336` |
| correction energy / norm | `1.0943224e7` / `3308.0544` |
| cell sum closure | relative error `5.106e-16` |
| Dörfler theta=0.5 | 99/252 cells；captured `0.501807` |
| marked hash | `4a4545a59164a813e4b08e47a4be94d652c5df0ee342afba988507e24e9c7e7b` |
| estimator time | `4.190 s` |
| watchdog peak / swap | `2.870 GiB` / `0` |

p2 与 p3 的 official observable 差异很大，说明 p2/h10 尚不在可信离散区间；这不是
adaptive 成功，但正是 actual R5 应识别的强 enrichment signal。下一步把这一 estimator
接到周期 tetra target pipeline，完成 orientation/tag/periodic closure，然后执行 p2 marked
cycles 和 cost-matched uniform control。若 tetra 路线通过，再用 p4 或细化解作为独立
local-error reference 测 correlation/effectivity；当前 dimensionful effectivity 只标记为 proxy。

## Phase C 目标 artifact screen

| 目标点 → enriched 点 | R5 effectivity proxy | R5 Pearson/Spearman | R1 Pearson | R1/R5 marked Jaccard | observable error reduction |
|---|---:|---:|---:|---:|---:|
| p2/h5 → p2/h3 | 0.9086 | 0.9903 / 0.9918 | -0.0356 | 0.0998 | 87.46% |
| p2/h3 → p2/h2 | 0.8106 | 0.9981 / 0.9949 | -0.0768 | 0.1358 | 81.55% |
| p3/h10 → p3/h7.5 | 0.9894 | 0.9892 / 0.9836 | -0.0202 | 0.1035 | 94.00% |

所有 marked set 均以 Dörfler `theta=0.5` 的 global sample ID SHA-256 锁定。R5 是 accepted
field-pair difference proxy，不是 formal hierarchical FE solve；R1 是 sample-grid strong residual，
不是 cell-integrated production R1。后者相关性为负，所以不能进入 production marking。Task034
strip/tensor PDE 对照的 observable error 从 `3.577e-6` 恶化到 `2.378e-2`，且不是 Task035
estimator-marked refinement，故 Phase C 受控收口而不选 estimator。

## Phase D backend 决策

| backend | 结果 | 关键证据 |
|---|---|---|
| Task034 strip/tensor | `controlled_negative` | actual PDE；middle E/H 与 A_volume gates fail |
| multi-block conforming hexa | `hexa_backend_blocker` | strip leakage ratio 6.071；无 qualified transition-cell/hanging-node support |
| tetra marked refine control | `control_pass`，research control only | 384→1392 cells；min volume `3.255e-4`；Nédélec proxy error 0.3523→0.2749 |

B3/B4 通过；serial/MPI2 compact identity 通过。首次 MPI2 tetra volume measurement 因错误的
topology-to-geometry indexing 产生伪零体积，失败 record 永久保留；改用
`geometry.dofmap[cell]` 后 targeted serial 与 MPI2 均通过。

## 最终边界

```text
phase_c_internal_gate = complete_controlled_negative
phase_d_internal_gate = complete
actual_global_two_level_R5 = pass_hexa_control
periodic_tetra_target_pipeline = in_progress
actual_adaptive_cycles = pending
production_estimator_selected = false
production_backend_selected = false
ordinary_default_changed = false
```

Review V4 已授权按 measured evidence 连续推进；ordinary default 与 master merge 仍未改变。
