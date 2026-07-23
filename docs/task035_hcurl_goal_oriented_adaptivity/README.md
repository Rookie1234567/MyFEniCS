# Task035：H(curl) 场/目标量驱动自适应与 hp 策略

## 当前身份

```text
status = continuous_autonomous_research
execution_lock_released_by_Task034_final_selective_merge = true
execution_branch_created_by_codex = true
base_sha = 5002636852ffb67b4711443da70eb536c303e34e
phase_b_algebraic_precursor = pass
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
phase_c_internal_gate = complete_controlled_negative
B3_B4 = pass
phase_d_internal_gate = complete
actual_discrete_dtn_adjoint = pass
actual_goal_weighted_dwr = pass
periodic_tetra_target_pipeline = research_pass
actual_adaptive_cycles = two_consecutive_pass
selected_research_strategy_10deg = p4_p5_R_total_DWR_theta0p7_one_cycle
adaptive_50pct_dof_accuracy_gate = controlled_negative
strict_RTA_resource_solution_10deg = structured_p4_h7p5
R_priority_resource_candidate_10deg = uniform_tetra_p5
robust_angle_common_mesh = controlled_negative
multi_angle_lane = closed_by_user_scope_10deg
production_estimator_selected = false
production_backend_selected = false
ordinary_default_changed = false
task035_pde_started = true
heavy_p4_started = true
```

Task035 专门处理 Task034 尚未解决的核心问题：

```text
如何为双周期、复材料、高阶 Nédélec、DtN/Hybrid Maxwell 问题
建立真正由场误差或目标量误差驱动的 h/p/hp 自适应，
而不是手工几何 graded mesh。
```

执行权威：

- [`task.md`](task.md)：正式任务书；
- [`../../notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md`](../../notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md)：文献、候选 estimator、mesh backend 与 hp 策略；
- Task034 最终 `outcomes/summary.md`、Case093 和最终 review：13.5 nm 固定结构基线与能力边界；
- [`../repository_work_principles.md`](../repository_work_principles.md) 和根 `AGENTS.md`：分支、审查、证据与合并规则。

## 执行前置条件

Task035 不得在 Task034 尚未完成最终 selective merge 时启动实现或重型 PDE。

Task034 最终合并后，由 Codex 从最新 clean `origin/master` 创建：

```text
codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

ChatGPT 与 Codex 的 Task035 任务材料、review、代码、outcomes 和 response 全部保存在该执行分支；最终审阅和用户授权前不得合并 `master`。

## 主范围

```text
13.5 nm
fixed physical geometry
S polarization mainline
10° grazing first
p2/p3/p4 Nédélec
Full3D + Hybrid
field-driven h-adaptivity
residual / recovery / equilibrated / two-level / DWR estimator bake-off
DtN and internal-mode truncation error separation
anisotropic conforming mesh regeneration
conditional hp capability audit
```

## 非目标

```text
0.7 nm production PDE
完整 P 入射矩阵
直接进入 arbitrary cellwise variable-p production
在 estimator 未资格化前运行大规模 p4 campaign
在 Task035 中同时重写 scalable modal core 或最终 iterative solve
```

Task035 的成功不要求所有候选方法都成功；要求每条方法都有可审计的 fixture、筛选、正/负决定，并至少判断是否存在一个可信的 field-driven adaptive 主线。

## Phase A 状态

Task035 执行分支已从 clean `master` 创建并推送。WSL、source、ABI、MPI1/2/4/8、
MUMPS/PEP microfixture、Task034 compact baseline 与六份必需 ignored artifact 的哈希
资格化子 Gate 均通过；首次 Case094 文档合同失败已按 Review V1 修复，最终 full pytest 通过，
Phase B 已解锁。仍未启动真实 Task035 PDE 或重型 p4。详见
[`outcomes/environment_and_base.md`](outcomes/environment_and_base.md) 和
[`base_manifest.json`](../../benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json)。

## Phase B 状态

原 NumPy 小向量/小矩阵结果已按 Review V2 准确重命名：R1、R3、R5、G1、G2、B1、M1
为 `algebraic_precursor_pass`，R2 为 `resolution_diagnostic_pass`，只记录
`chi=|k|h/p`，不再缩放 R1；R4 保持 `formula_defined`。

B1 已在真实 3D hexahedral Nédélec p1/p2 空间上装配 UFL cell curl-curl residual 和
interior curl jump，并验证实际 FE Floquet trace、phase/orientation fault injection、真实分布式
cell identity。B2 已使用界面对齐网格、piecewise-complex DG0 材料、三个实际 h/p 点、
Fresnel 场误差、零级反射目标方向导数和 external DtN 扰动完成最低 Gate。serial/MPI2
标量 identity 通过。因此：

```text
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
phase_c_internal_gate = complete_controlled_negative
```

## Phase C/D 状态

Review V3 授权的 Phase C/D 已连续完成。Phase C 复用 Task034 的 p2/h5、p2/h3、p2/h2、
p3/h10、p3/h7.5 与 p4/h5 hash-bound 场样本，在固定 13.5 nm、10° grazing、S 入射、
Task034 geometry 上筛选 sampled R1、discrete two-level R5 proxy、external DtN split；R2 仍只作
`kh/p` diagnostic。R5 proxy 的 local correlation 很高，但不是 formal hierarchical FE R5；
R1 sampled strong residual 与局部误差相关性为负。Task034 strip/tensor 实际 PDE 细化证据仍是
`controlled_negative`，且不是 estimator-marked refinement，因此没有选择 production estimator。

B3 actual material-interface/corner Nédélec fixture 与 B4 measured Hybrid Et/Ht、M/DtN、QEP
microfixture 均通过 serial/MPI2。Phase D 的 strip/tensor 保留负结果；conforming Cartesian
multi-block hexa 因 axis-cut strip leakage 记录 `hexa_backend_blocker`；tetra actual marked-refine
control 通过，但只证明 backend/orientation 机制，不是目标 Maxwell PDE。因此：

```text
phase_cd_complete_controlled_negative = true
ordinary_default_changed = false
phase_e_unlocked = false
```

没有启动 Task035 目标 PDE、adaptive cycle 或 p4/h5 heavy。详见
[`outcomes/estimator_definitions.md`](outcomes/estimator_definitions.md) 和
[`outcomes/summary.md`](outcomes/summary.md)。

## Review V4 后连续研究状态

上节是 Phase C/D 收口时的历史边界。Review V4 解除阶段审批锁后，已完成 actual global R5、
periodic tetra target、两轮 p2/p3 adaptive、cost-matched uniform、actual DtN discrete adjoint、
R/T goal-weighted DWR 以及 p3/p4 MPI8 高阶路线。pure R5 marking 虽然收敛，但在相近成本下
被 uniform level2 明确击败，保留为 diagnostic；DWR `theta=0.5` 的 p3/p4 单轮局部细化则在
约 11% 更少 p4 DoF 下，比 uniform level1 的 observable error 低约 23%，形成当前最佳研究策略。
第二轮 DWR 虽继续收敛，却被 Task034 structured p4/h7.5 在误差、DoF 和内存上同时支配；
`theta=0.3` 又只节省约 4.9% DoF 而误差恶化 2.30 倍。因此固定结构、S、10° grazing 的当前
最新 hp 停止规则是：`p4/p5 + R_total DWR + theta=0.7 + exactly one full-sleeve tetra refinement`；
它相对同阶 uniform tetra 以约少 8.4% DoF 获得低 26.8% 的误差，但仍是相对 structured
p4/h7.5 的 Pareto tradeoff，不是 same-error replacement。

同一网格 MPI8 robust-angle 判别已完成。公共网格 SHA 重放与六次 official solve 全部通过，
但 p4→p5 observable gap 从 10° 的 `0.00587` 增大到 5° 的 `0.02464` 和 1° 的 `0.42375`。
因此 10°-优化网格直接覆盖 1°/5° 是 controlled negative；下一研究 lane 转入 multi-angle
marking 或独立 angle reference，不提升 ordinary default。

这是 hash-bound 的 research selection，不是跨角度、P 入射、Hybrid 或普通默认的生产资格化。
Case094 仍保持 staging，`production_estimator_selected=false`、
`production_backend_selected=false` 与 `ordinary_default_changed=false` 不变。

## 10° 与至少 50% DoF 节约的最终资源决策

按用户最新目标，主线只比较 Task034 fixed geometry、S、10° grazing，并以 accepted
p4/h5 的 339,892 DoF 和 `(R,T,A_volume)=(0.0007663134,0.6026775305,0.3965561561)`
为 best-available discrete reference。研究型 tetra p6 已在 serial/MPI8 periodic MPC Gate
通过，但普通 hexa/default 仍保持 p4 上限。

两个 p6 adaptive 候选都满足 DoF 下限且完整 R/T/A 向量误差优于 p4/h7.5，却都没有满足
预先锁定的 R-only accuracy control：

| route | DoF | saving | R | peak GiB | decision |
|---|---:|---:|---:|---:|---|
| p4/h5 structured reference | 339,892 | 0% | 0.0007663134 | 28.888 | reference |
| p4/h7.5 structured | 147,844 | 56.50% | 0.0008024690 | 12.724 | strict R/T/A resource solution |
| uniform tetra p5 | 116,120 | 65.84% | 0.0007956866 | 8.011 | R-priority candidate |
| DWR theta=.3 tetra p6 | 161,700 | 52.43% | 0.0008194492 | 13.326 | controlled negative |
| DWR theta=.4 tetra p6 | 167,784 | 50.64% | 0.0008176842 | 13.994 | controlled negative |

theta=.4 相对 theta=.3 增加 48 cells 和 6,084 p6 DoF，只把 R 改善约 `1.77e-6`；
剩余 2,162 DoF 预算不足以补足相对 p4/h7.5 R control 的约 `1.52e-5` 差距。因此继续
扫描 theta 或增加 full-periodic sleeve cells 没有合理的 50% DoF 成功路径，lane 已关闭。

工程选择分两种口径：

```text
需要 R/T/A 整体可信且至少节约 50% DoF:
    采用已接受的 structured p4/h7.5

只把 R≈0.0007xxx 作为主目标并优先最低资源:
    uniform tetra p5 是 measured research candidate
    但其完整 R/T/A vector error 不如 p4/h7.5，不能冒充同精度 production replacement
```

当前 full-sleeve DWR adaptive p6 在 DoF、内存和 R 上均未击败上述可用点，故不推荐作为
资源解决方案。ordinary default、production estimator/backend 与 master 均未改变。
