# Task035 Response V4：Phase C estimator 与 Phase D mesh-backend bake-off

## 1. 权威、范围与执行身份

本响应只对应 `review_report_v3.md`；没有创建其他 response 或 addendum。

```text
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
review_v3_start_head = 4185bc41abc70a618e8ea3a4a00d90a2738fc239
task035_base_sha = 5002636852ffb67b4711443da70eb536c303e34e
final_record_source_sha = db2d1e7a49f5754de8d0dec6dda3622a9635e6bb
execution_backend = WSL_Ubuntu_24_04
canonical_activation = source scripts/activate_myfenics_wsl.sh
```

用户本轮指令、Task035 `task.md` 与 Review V3 是当前权威。旧 Phase1 文档中的
Task033–Task035 编号映射属于过期规划，不用于扩大或缩小本轮范围；相关修正只发生在
Task035 执行分支，不回写 `master`。

Review V3 接受 B1/B2 real-FE minimum Gate，并授权 Phase C 后连续进入 Phase D。本轮未执行
Phase E/F、目标 adaptive cycle、p4/h5 heavy adaptive、ordinary-default change，也没有修改
Maxwell、Floquet、DtN、QEP、Hybrid、材料、几何或 solver production numerical core。

## 2. Phase C：目标结构低成本 screen

复用 Task034 已接受并由 descriptor SHA-256 绑定的 p2/h5、p2/h3、p2/h2、p3/h10、
p3/h7.5、p4/h5 Full3D field samples；没有重跑 p4/h5 reference、M funnel 或 MPI heavy matrix。
物理身份固定为 13.5 nm、10° grazing（`theta=80°`）、S 入射、Task034 rectangular-block
geometry。p4/h5 只称 best-available discrete reference，不称 continuum truth。

筛选项：

- R1：sample grid 上的 strong Maxwell residual proxy；不是 cell-integrated production FE R1；
- R5：accepted coarse/enriched field pair difference proxy；不是 formal hierarchical local FE solve；
- external DtN：bottom/interior/top sampled residual split；
- R2：只记录 `kh/p`，明确排除出 marking；
- G1/G2：没有 actual discrete adjoint，维持未资格化；
- R4：维持 research `formula_defined`，未提升。

| 点 → enriched | R5 effectivity proxy | R5 Pearson / Spearman | R1 Pearson / Spearman | R1/R5 marked Jaccard | observable error reduction |
|---|---:|---:|---:|---:|---:|
| p2/h5 → p2/h3 | 0.9086 | 0.9903 / 0.9918 | -0.0356 / -0.0359 | 0.0998 | 87.46% |
| p2/h3 → p2/h2 | 0.8106 | 0.9981 / 0.9949 | -0.0768 / -0.0622 | 0.1358 | 81.55% |
| p3/h10 → p3/h7.5 | 0.9894 | 0.9892 / 0.9836 | -0.0202 / -0.0361 | 0.1035 | 94.00% |

每个 Dörfler `theta=0.5` marked set 均记录 count、fraction 与 global sample ID SHA-256。
serial estimator wall time 为 0.049 s，process peak RSS 从 87,216 KiB 到 91,500 KiB；这些是
低成本 artifact 分析口径，不是 PDE estimator assembly cost。serial/MPI2 的 4,000 个 global
sample ID count/sum/sum-square 与所有 compact metrics identity 通过，无 full-field gather。

R5 proxy 对离散 field error 排序很好，但未实现 formal enriched local solve；R1 proxy 与局部误差
相关性为负，二者 marked overlap 也低。Task034 strip/tensor actual PDE 对照的 observable error
从 `3.5771e-6` 恶化到 `2.3778e-2`，reduction fraction 为 `-6646.25`，并失败 middle E/H 与
`A_volume` gates；而且该 run 是 geometry-driven，不是 Task035 estimator-marked refinement。
因此 Phase C 只能受控收口：

```text
phase_c_internal_gate = complete_controlled_negative
production_estimator_selected = false
phase_d_low_cost_unlocked = true
```

这遵循 Review V3 的失败策略：保存负结果，停止不合格 estimator lane，但允许 provisional R1
用于 Phase D engineering comparison；不宣称完成 dual estimator。

## 3. B3/B4 并行 fixture

### B3 material-interface/corner

B3 使用实际 DOLFINx 4×4×4 conforming hexa mesh、N1curl p1/p2、DG0 piecewise-complex
coefficient、actual cell MeshTags 和 16 个 material-interface facets。结果：

| 指标 | 值 |
|---|---:|
| material tag counts | air 48 / inclusion 16 |
| R1 global norm | 6.0018 |
| interface curl-jump norm | 2.3443 |
| material-tag fault norm | 4.2539；fault detected |
| p1 / p2 center error | 0.6190 / 0.003104 |
| local proxy correlation | 0.7390 |
| computed direction | y；由 indicator-weighted coordinate deviation `argmax` 产生 |

方向不是 hardcoded；serial/MPI2 identity 通过。`B3 = component_fixture_pass`。

### B4 Hybrid Et/Ht、M/DtN、QEP

B4 复用 Task034 accepted p2/h3 target Et/Ht samples、M80/120/160 funnel 与 p3/p4
MPI2/MPI4 matched-trace/QEP aggregate；没有重跑 Hybrid PDE 或 QEP heavy matrix。

| 指标 | 值 |
|---|---:|
| Et norm | 37.6483 |
| impedance-scaled Ht norm | 6.04298 |
| spatial perturbation | 0.55765 |
| DtN trace / operator-fault residual | 0.87272 / 0.87753 |
| M80→120 max total delta | 1.2033e-11 |
| M120→160 max total delta | 2.4575e-14 |
| QEP beta MPI delta p3 / p4 | 4.8427e-14 / 6.7186e-13 |

QEP 只作 diagnostic，不进入 estimator marking。`B4 = component_fixture_pass`，serial/MPI2
identity 通过。

## 4. Phase D：mesh-backend bake-off

| backend | 结果 | 证据与限制 |
|---|---|---|
| Task034 strip/tensor | `controlled_negative` | actual PDE；conforming/periodic mechanism pass，但 same-error physical gates fail |
| multi-block conforming hexa | `hexa_backend_blocker` | 1000→2275 cell proxy；ideal local added 210，actual added 1275，strip leakage ratio 6.071；没有 qualified transition-cell/hanging-node support |
| tetra marked-refinement control | `control_pass`，research only | actual DOLFINx refine；384→1392 cells；48 marked；min volume 3.2552e-4；inside/outside mean volume 3.2552e-4 / 8.5136e-4；Nédélec error 0.35227→0.27489，降低 21.97% |

tetra 结果只资格化低成本 marked-refine/orientation control，不是目标 Maxwell PDE 或 production
mesh backend。最终没有可信的 target conforming-hexa local backend，也没有通过 same-error Gate 的
现有 strip backend：

```text
phase_d_internal_gate = complete
status = phase_d_complete_controlled_negative
production_backend_selected = false
phase_e_unlocked = false
ordinary_default_changed = false
```

## 5. 首次 MPI2 measurement failure 与修复

第一次 MPI2 C+D run 返回 exit 2。tetra refine 的 cell count、locality 和 Nédélec error improvement
均正常，但 volume checker 用 topology vertex ID 直接索引 refined geometry；MPI2 ghost/geometry
dof mapping 下产生伪 `minimum_signed_volume_proxy = 0.0`。原始失败完整保存在
`records/phase_cd_mpi2_initial_volume_measurement_failure.json`，未删除或改写。

修复只把索引改为 `msh.geometry.dofmap[cell]`，没有改变 mesh refinement 或 numerical core。
修复后 serial/MPI2 均为 `phase_cd_complete_controlled_negative`，identity failures 为 `[]`。

## 6. 测试与 Gate

| 检查 | 结果 |
|---|---:|
| Phase C focused test88–test94 | 25 passed |
| 本轮新增 direct tests | 10 passed |
| final record contract | 3 passed |
| serial / MPI2 C+D | complete / complete |
| serial/MPI2 identity | pass |
| scoped Ruff / compileall | pass / pass |
| C+D focused test88–test97 | 33 passed |
| full repository pytest（C–D 后唯一一次） | 527 passed, 18 skipped in 245.98s |
| git diff --check / pre-commit status scope | pass / expected Task035 changes only；final clean status 由交付消息报告 |

没有重复 Phase A full regression、环境安装/资格化、MPI1/2/4/8 MUMPS/PEP matrix、Task034
artifact 全量验证、Task034 heavy PDE 或 p4/h5 reference。

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| final serial C+D | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi1.json` |
| final MPI2 C+D | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi2.json` |
| MPI identity | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi_identity.json` |
| first MPI2 failure | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi2_initial_volume_measurement_failure.json` |
| result summary | `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md` |
| test summary | `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/test_summary.md` |

## 8. 最终边界

本轮完成的是 Phase C/D 的可审计正/负筛选，不是 adaptive method success。等待 Review V4 前：

```text
Phase E adaptive cycles = not_authorized_and_locked
Phase F p4/h5 mainline = not_authorized_and_locked
p4/h5 heavy adaptive = not_run
ordinary_default_change = false
```

最终 response/docs commit 与远程 branch HEAD 由交付消息报告，不在本文制造自引用 SHA。
