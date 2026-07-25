# Task035 Response V3：真实 B1/B2 Gate 与 Phase C-low-cost 入口

## 1. 权威、分支与执行身份

本响应对应 `review_report_v2.md`，没有创建其他 response 或 addendum。

```text
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
review_v2_start_head = ad038f6a27db96ffe6d94a400b80a5ccc05f06d7
implementation_commit = 563593b2195edd951c5a4f4d089e04c4f73045a1
task035_base_sha = 5002636852ffb67b4711443da70eb536c303e34e
windows_codex_client = approved_orchestrator
execution_backend = WSL_Ubuntu_24_04
canonical_activation = source scripts/activate_myfenics_wsl.sh
```

所有 Git、Python、MPI、PETSc/DOLFINx 与测试命令均在
`/home/Projects/MyFEniCS` 的 WSL Ubuntu 仓库执行。没有使用 Windows Python、Git、MPI，
也没有把 Windows Codex 客户端当作 blocker。

本轮只运行了一次不含 MUMPS/PEP solver microfixture 的 lightweight ABI rank probe，确认
repo venv、PETSc `complex128`/`int32` 和 Linux ABI identity；没有重复 Phase A 完整资格化。

## 2. Review V2 状态修正

原 NumPy 小向量和小矩阵 fixture 已准确重命名：

```text
R1/R3/R5/G1/G2/B1/M1 = algebraic_precursor_pass
R2 = resolution_diagnostic_pass
R4 = formula_defined
phase_b_algebraic_precursor = pass
```

R2 现在只返回 `chi=|k|h/p` 与未缩放的 R1 值，不再计算或暴露
`eta_R1/sqrt(1+chi^2)`，因此不会对未解析单元错误降权。

## 3. B1 real periodic Nédélec/H(curl)

新增的真实 B1 fixture 使用 3D hexahedral mesh、Basix N1curl p1/p2、解析斜入射
plane wave 和真实 DOLFINx/UFL quadrature。它装配 cell curl-curl residual 与 interior
curl jump，并用固定数量 FE trace probe 的 scalar-size allreduce 验证 Floquet phase；
不 gather 全局 field/vector/cell array。

| 点 | global cells | Nédélec DoF | relative L2 error | R1 indicator | Floquet residual |
|---|---:|---:|---:|---:|---:|
| p1, 2×2×2 | 8 | 54 | 6.0837e-2 | 1.5326 | 9.28e-12 |
| p2, 2×2×2 | 8 | 300 | 1.6905e-3 | 1.0031e-1 | 4.79e-12 |

orientation fault residual 为 2.71/2.81，phase fault residual 为 0.257/0.266，均被检测。
真实 MPI-owned global cell count/sum/sum-square identity 通过。

```text
B1_real_FE_fixture = pass
```

## 4. B2 real flat lossy layer / official goal

B2 使用界面对齐的 hexa mesh、N1curl p1/p2、piecewise-complex DG0 epsilon、解析 lossy
Fresnel 场和三个实际 h/p 离散点。实测 field error 与 R1 indicator 均下降：

| 点 | relative L2 error | R1 indicator | external DtN norm | fixture R00 error |
|---|---:|---:|---:|---:|
| p1, 1×1×2 | 1.7331e-1 | 9.4576 | 1.3388 | 5.55e-17 |
| p1, 2×2×4 | 4.5161e-2 | 5.2798 | 7.2875e-1 | 1.39e-16 |
| p2, 2×2×4 | 2.2355e-3 | 5.9303e-1 | 5.8582e-2 | 4.09e-16 |

official fixture goal 是实际 FE top trace 的规范化零级反射功率。它的解析方向导数与对
实际 Nédélec coefficient vector 做中心差分的最大绝对差为 2.40e-10。external DtN
fault injection 直接测量算子扰动范数 8.73e-2；不使用“扰动后的总残差必须单调增大”这一
无数学保证的条件。

```text
B2_real_FE_official_goal_fixture = pass
```

这些 fixture 使用真实有限元空间与 form，但只离散解析/制造场，没有进行 Task035 PDE solve，
也不是目标 13.5 nm 光栅的正式 R/T/A。

## 5. serial/MPI2 与 provenance

serial 和 MPI2 分别独立运行，比较所有 compact scalar fixture metrics：

```text
serial_mpi2_identity = pass
differences = {}
reduction = scalar_metrics_only_no_field_vector_gather
```

两份 record 均记录：

- WSL venv Python `/home/Projects/MyFEniCS/.venv/bin/python`；
- qualification marker = `1`；
- PETSc scalar/int = `complex128`/`int32`；
- run-time Git HEAD；
- runner 与真实 FE validation module 的 SHA-256 content binding。

## 6. Phase C-low-cost 已进入

最低 Gate 结论为：

```text
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
phase_c_low_cost = in_progress
phase_c_formal_completion = pending_B3_B4
production_estimator_selected = false
heavy_p4_authorized = false
```

已生成 `records/phase_c_low_cost_entry.json`。初始 measured screen 仅使用 B1/B2 真实 FE
fixture，不冒充 task.md 要求的目标 `p2/h5`、`p2/h3`、`p3 coarse` screen：

- R1 与 external DtN split 进入 low-cost bake-off；
- R2 只作 diagnostic，明确排除出 marking；
- R5 等待真实 enriched/two-level fixture；
- G1 等待实际离散 residual 与 adjoint；
- G2 已通过真实 goal derivative，但当前 fixture R00 在所有点均为机器精度，受控记录为
  `controlled_not_rankable_on_machine_precision_fixture_goal`，下一 Gate 是非平凡低成本目标上的
  实际离散 adjoint；
- 未选择任何 production estimator。

## 7. B3/B4/R4 并行状态

```text
B3_material_interface_corner_real_FE = pending_parallel
B4_hybrid_Et_Ht_M_DtN_real_microfixture = pending_parallel
R4_equilibrated = research_lane_formula_defined
```

B3/B4 在 Phase D production backend 决策或任何 p4/h5 adaptive heavy case 前仍必须完成，
或形成明确 `controlled_negative`。本轮没有把任何 research-only adaptive mesh、runner 或
equilibrated estimator 提升为 production。

## 8. 测试与未重复项

最终实现改动后的验证：

| 检查 | 结果 |
|---|---:|
| Task035 focused + governance/document suite | 49 passed |
| real FE provenance + Phase C entry targeted | 8 passed |
| B1/B2 serial | pass |
| B1/B2 MPI2 | pass |
| serial/MPI2 identity | pass |
| scoped Ruff | pass |
| scoped compileall | pass |
| git diff --check | pass |

按 Review V2 没有重跑：

- Phase A full pytest 或环境完整资格化；
- MPI1/2/4/8、MUMPS/PEP qualification matrix；
- Task034 artifact 全量 hash；
- Task034 p3/h3、p4/h5、M funnel 或其他 heavy PDE；
- full repository pytest。

历史 `phase_a_regression_failure.json`、`phase_b_regression_failure.json` 与 recovery records
均保留，未删除、覆盖或改写为通过。没有修改 Maxwell、Floquet、DtN、QEP、Hybrid、材料、
几何或 solver production numerical core。

## 9. 证据索引

| 证据 | 路径 |
|---|---|
| algebraic precursor | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/fixture_summary.json` |
| real FE serial | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/real_fe_mpi1.json` |
| real FE MPI2 | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/real_fe_mpi2.json` |
| MPI identity | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/real_fe_mpi_identity.json` |
| Phase C entry | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_c_low_cost_entry.json` |
| outcomes summary | `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md` |

`response_v3.md` 将作为单独文档提交；该提交后的精确远程 branch HEAD 由交付消息报告，
不通过改写或新增 response 文件制造自引用 SHA。
