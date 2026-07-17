# REVIEW REPORT V5：Task033 p3 同阶闭合、p4 四模态迹与目标资源 Gate 复审

## 0. 审阅身份与最终决定

```text
review = Task033 review_report_v5
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
reviewed_head = f3e5421a16f1594ffa62bafeb8ecb9cf79bc0c78
phaseC1_assembly_source = 35fa6a0c454d96875f9865260b13d22b43d06838
p3_full3d_reference_source = bd828f24dc1546263210d73d08bf7bc16ba8a129
p3_hybrid_closure_and_p4_trace_source = 95921ab76e39eb1a7c5b3321b93d36939afb4075
review_status = PHASE_C_P3_ACCEPTED_P4_RESOURCE_GATED
p3_h5_same_degree_numerical_closure = PASS_WITH_QUALIFICATIONS
p3_h5_hybrid_memory_reduction = PASS
p3_h5_wall_clock_speedup = NOT_DEMONSTRATED
p4_four_mode_matched_trace = PASS
p4_h5_target_full3d = NOT_RUN_BY_MEASURED_MEMORY_GATE
p4_h5_target_hybrid = NOT_RUN_BY_RESOURCE_GATE
p3_h3 = NOT_AUTOMATICALLY_APPROVED
h_adaptivity = DEFERRED_TO_FINAL_PHASE
whole_task033 = PARTIAL_NOT_COMPLETE
documentation_hardening = CHANGES_REQUIRED_NO_PDE_RERUN
whole_branch_merge = NOT_YET_APPROVED
same_branch_continuation = APPROVED
```

本轮新增了三个相互独立的结果：

1. p3/h5 目标 full3D direct reference 实际完成；
2. p3/h5 Hybrid M160 与同阶 full3D 的 R/T/A、体吸收和五个 E/H 截面完成正式闭合；
3. p4 四模态近简并迹组件通过，但 p4/h5 目标装配在当前机器上触发受控内存终止，full3D factorization、full solve 与 Hybrid target 均未启动。

审阅接受 p3/h5 的同离散数值闭合，同时保留以下边界：

- p3/h5 full3D reference 的 `grid_converged=false`，所以这是同阶、同网格离散一致性，不是连续解或 h 收敛证明；
- Hybrid 在内存上明显优于 full3D，但当前记录没有证明墙钟时间更快；
- p4 的目标负结果是当前宿主机和当前 direct/Hybrid 实现下的资源否决，不是 p4 数学方法永久不可用，也不是求解器数值崩溃；
- p3/h3、buffer、自适应、variable-p/hp 和 0.7 nm 仍未进入本轮资格范围。

---

# 1. 对 review V4 执行情况的审阅

## 1.1 证据合同修正

review V4 要求 Phase C 聚合器不得把一般 `formal_not_pass` 当作组件通过，并要求把接口、traction、QEP 和模态容量的实测值提升到 tracked summary。

本轮已经完成：

- M80、M120、M160 只有精确 `measured_shard_pass` 才能进入 component pass；
- 新增负向测试，任一所需 M 被替换为 `formal_not_pass` 时 Phase C 必须 fail closed；
- `phaseC_summary.json` 已补充 interface-E projection、FE–modal traction equilibrium、左右 QEP 残差、双正交误差和有限有效模态统计；
- mixed source SHA 仍被聚合器拒绝。

### 决定

```text
review_v4_evidence_contract_fixes = ACCEPTED
PDE_rerun_for_these_fixes = NOT_REQUIRED
```

## 1.2 Phase C1 assembly-only 校准

p3/h5 assembly-only 在 clean source `35fa6a0...` 上得到：

| 指标 | 实测值 |
|---|---:|
| Nédélec DoF | 145,863 |
| Floquet constraint rows | 8,703 |
| base assembled NNZ | 35,441,847 |
| final rows | 145,943 |
| final assembled NNZ | 35,566,727 |
| 显式 AIJ payload 估计 | 815.17 MiB |
| assembly-only memory authority | 4.148 GiB |
| assembly 时间 | 75.19 s |
| factorization / solve | 未进入 |
| swap | 0 |

该记录满足 review V4 的 assembly-only 合同。它也证明原 Case090 迁移得到的 rows/NNZ 预测偏低，但使用 p2 fill 关系得到的 factor/RSS 预测仍然非常保守：第二中心约 15.87 GiB、上界约 19.04 GiB，因此原 review Gate 仍按合同返回 `not_run_by_memory_gate`。

### 解释

旧预测 Gate 在当时是合理的，因为当时没有 p3 target factor 或 full-solve 实测，不能只选择较低的 6.44 GiB 中心启动。随后用户明确授权一次带受控 swap 后备的 p3 full solve，属于 review V4 之后的资源授权变化；它没有把旧预测记录改写为 pass。

---

# 2. p3/h5 full3D direct reference 审阅

## 2.1 运行身份

full3D reference 使用：

```text
degree = 3
h = 5 nm
wavelength = 13.5 nm
incidence = 10° grazing
polarization = S
MPI = 4
solver = direct LU / MUMPS
container memory = 13 GiB
swap fallback allowed by user = yes
actual cgroup swap used = 0
```

记录绑定 clean source `bd828f24...`，导出了 complex128 的五个 E/H 截面和上下接口迹，并保存 NPZ、逐衍射级与功率记录的 SHA-256。

## 2.2 数值结果

| 指标 | full3D p3/h5 |
|---|---:|
| Nédélec DoF | 145,863 |
| 外部 DtN auxiliary DoF | 80 |
| final rows | 145,943 |
| assembled NNZ | 35,566,727 |
| true relative residual | `5.442e-12` |
| R | 0.001090107012 |
| T | 0.600622478293 |
| A balance | 0.398287414695 |
| A volume | 0.398287414695 |
| energy closure | `4.552e-14` |
| memory authority | 7.781 GiB |
| cgroup swap peak | 0 |
| elapsed | 103.59 s |

### 决定

```text
p3_h5_full3d_reference = PASS
resource_identity = VALID_CONTROLLED_MEASUREMENT
no_swap = TRUE
memory_below_user_p4_precondition_10_GiB = TRUE
grid_converged = FALSE
```

虽然命令允许 swap 后备，但实际运行没有使用 swap。允许后备不会降低物理和代数资格；真正的资格仍要求进程完成、KSP 收敛、真残差通过、参考场成功导出、所有 MPI rank 可见和源码运行前后 clean。上述条件均满足。

---

# 3. p3/h5 Hybrid–full3D 同阶闭合

## 3.1 参考绑定与源码兼容性

full3D reference 产生于 `bd828f24...`，闭合 Hybrid 产生于其后继 `95921ab7...`。两个 SHA 之间的改动包括：

- 将 p3/h5 reference 注册到 Hybrid reference map；
- p4 四模态迹测试和 p4 launch prerequisite；
- full3D watchdog 证据与 p4 资源门禁；
- 测试和记录文件。

没有修改 p3 full3D Maxwell 体离散、材料、几何、Floquet 核心、DtN 物理或 p3 Hybrid 求解代数。新增 reference map 只使 Hybrid 可以读取并校验已冻结 NPZ。

因此该 source split 可以接受，但正式收口文档必须显式保存以下审计：

```text
full3d_source_is_ancestor = true
full3d_numerical_core_changed = false
hybrid_numerical_core_changed_after_reference = false
reference_wiring_changed = true
reference_npz_hash_verified = true
```

## 3.2 M160 Hybrid 结果

| 指标 | Hybrid p3/h5 M160 |
|---|---:|
| retained modes / direction | 160 |
| candidate modes / direction | 320 |
| local rows | 21,847 × 2 |
| local assembled NNZ | 5,156,503 × 2 |
| true relative residual | `2.343e-12` |
| R | 0.001090095685 |
| T | 0.600622368221 |
| A balance | 0.398287536094 |
| A volume | 0.398287536096 |
| energy closure | `1.885e-12` |
| memory authority | 2.618 GiB |
| swap | 0 |
| total time | 111.94 s |

M80→M120 和 M120→M160 已在前一阶段分别通过 R/T/A、显著逐阶功率和复振幅的 mandatory/strong Gate，因此本轮只重跑 M160 与新 full3D reference 闭合是合理的；无需重跑 M80/M120、augmented anchor 或 M240。

## 3.3 同阶差异

| 指标 | Hybrid − full3D / 最大误差 |
|---|---:|
| ΔR | `-1.133e-8` |
| ΔT | `-1.101e-7` |
| ΔA balance | `+1.214e-7` |
| ΔA volume | `+1.214e-7` |
| 最大 R/T/A 绝对差 | `1.214e-7` |
| 五截面最大 E relative L2 | `1.100e-5` |
| 五截面最大 H relative L2 | `1.098e-4` |
| 中间截面最大 E relative L2 | `8.387e-6` |
| 中间截面最大 H relative L2 | `1.098e-4` |

这些结果明显优于冻结 Gate：

```text
max |ΔR/T/A| <= 1e-5
middle-plane E <= 5e-3
middle-plane H <= 5e-3
volume absorption delta <= 1e-5
```

Hybrid 自身的 16 项物理和代数 Gate 也全部通过，包括：

- 160 个正向和 160 个反向有限有效模式；
- 左右 QEP 残差；
- 双正交性；
- 传播因子无增长；
- interface-E projection；
- FE–modal traction equilibrium；
- sampled E/H interface continuity；
- R/T/A 与体吸收闭合；
- full true residual。

## 3.4 内存与时间解释

Hybrid 的内存为 full3D 的约 `0.336×`，约降低 66.35%。这是明确的工程正结果。

但时间为：

```text
full3D = 103.59 s
Hybrid = 111.94 s
```

因此当前尺度没有证明 Hybrid 的墙钟时间更快。合理结论是：

> p3/h5 Hybrid 在保持同离散高精度一致性的同时，显著降低峰值内存；当前 direct 实现的总时间与 full3D 同量级且略慢。

不得把内存成功写成 speedup。

## 3.5 Phase C 决定

```text
p3_h5_M_funnel = PASS
p3_h5_augmented_vs_schur_minimal = PASS
p3_h5_same_degree_full3d_reference = PASS
p3_h5_RTA_and_field_closure = PASS
whole_phaseC_p3_h5_numerical_closure = PASS
continuous_solution_or_h_convergence = NOT_PROVEN
```

---

# 4. p3 预测模型的校准结论

p3/h5 的 assembly-only 预测在使用真实 assembled NNZ 后仍得到约 15.87 GiB 中心和 19.04 GiB 上界，而实际 full solve 峰值只有 7.781 GiB。

这说明：

1. 旧模型用于 fail-closed 启动保护是安全的；
2. 旧模型不适合继续作为 p3/p4 的精确资源预测；
3. p2 fill ratio 和 factor-payload→RSS 映射不能未经重新校准直接外推到高阶；
4. 未来资源矩阵应加入 p3/h5 的真实 full-solve anchor；
5. 不应因为 p3 预测过于悲观，就反向忽略 p4 的实测 assembly 内存。

### 要求

在下一次资源规划中必须保存：

```text
p3_predicted_center = 15.870 GiB
p3_actual_memory_authority = 7.781 GiB
prediction_is_conservative = true
prediction_is_not_calibrated_for_high_order = true
```

不得修改历史记录来隐藏预测偏差。

---

# 5. p4 四模态近简并迹复审

review V4 要求 p4 target 前补一个四模态近简并迹测试。本轮使用：

```text
degree = 4
h = 10 nm small matched fixture
QEP requested modes = 8
selected source basis indices = [4,5,6,7]
interface mode count = 4
MPI = 1 and 4
```

## 5.1 结果

| 指标 | MPI1 | MPI4 |
|---|---:|---:|
| Gram rank | 4/4 | 4/4 |
| Gram condition | 5.663 | 5.592 |
| coefficient round-trip | `2.434e-15` | `8.967e-16` |
| reconstruction residual | `9.532e-16` | `4.488e-16` |
| block normalization error | `1.304e-11` | `2.345e-13` |
| min principal cosine | 1.0 | 1.0 |
| max right QEP residual | `4.648e-14` | `1.694e-14` |
| max left QEP residual | `5.259e-14` | `4.177e-15` |

MPI1→MPI4 的最大 beta assignment 相对差为 `5.226e-13`。

raw Gram condition 和 singular-value spectrum 在 MPI1/MPI4 间有约 1.24% 和 0.62% 的变化。对于近简并块，单独 Gram 谱依赖块内基底选择，不是严格的物理不变量。本轮聚合器改用：

- 满秩；
- 精确四维块身份；
- Petrov round-trip；
- block normalization；
- beta assignment；
- principal-angle/subspace invariant。

该处理合理，没有降低 Petrov、残差或 beta Gate。

### 决定

```text
p4_four_mode_matched_trace = PASS
p4_near_degenerate_trace_basis_handling = PASS
p4_target_physical_solve = NOT_IMPLIED
```

---

# 6. p4/h5 目标资源负结果复审

p4 的前置条件已经满足：

- p3/h5 full solve 通过；
- p3 实测零 swap，内存 7.781 GiB < 10 GiB；
- p4 四模态迹 MPI1/MPI4 通过。

因此启动一次 p4/h5 assembly-only 资源校准是合理的。

## 6.1 实测

| 指标 | p4/h5 assembly-only |
|---|---:|
| Nédélec DoF | 339,892 |
| Floquet constraint rows | 15,412 |
| base rows | 339,892 |
| base NNZ | 155,205,040 |
| base payload 估计 | 3.555 GiB |
| base assembly time | 463.11 s |
| internal RSS after base copy | 10.990 GiB |
| internal RSS after DtN insert | 10.995 GiB |
| external memory authority | 12.616 GiB |
| cgroup swap peak | 0 |
| pswpout delta | 4 pages |
| factorization stage | 未进入 |
| solve stage | 未进入 |
| OOM killed | false |
| termination | controlled SIGTERM |

尽管 cgroup swap peak 为零，`pswpout` 增加 4 页，因此 formal `no_swap=false` 的 fail-closed 分类正确。

## 6.2 处置

```text
p4_h5_full3d_factorization = DO_NOT_LAUNCH_ON_CURRENT_HOST
p4_h5_full3d_solve = DO_NOT_LAUNCH_ON_CURRENT_HOST
p4_h5_hybrid_M160 = DO_NOT_LAUNCH_ON_CURRENT_HOST
p4_target_status = NOT_RUN_BY_MEASURED_MEMORY_GATE
```

p4 full3D 在 factorization 前就越过受控线；p4 Hybrid 的独立资源矩阵中心/上界为约 37.04/42.59 GiB，也不满足当前机器 Gate。因此停止是合理的。

这不是：

```text
p4 numerical solver failure
p4 physics failure
p4 method universally infeasible
```

而是：

```text
current-host resource infeasibility for current p4 target implementation
```

如果未来在更大内存机器上继续，必须重新建立 candidate-specific C0；不得把本机受控负结果直接改写成 pass。

---

# 7. 发现的文档与证据一致性问题

以下问题不影响本轮数值结论，但必须在选择性合并或下一阶段前修正。

## 7.1 历史 `phaseC_summary.json` 状态已过期

当前 tracked `phaseC_summary.json` 仍保存历史状态：

```text
hybrid_component_closed_full3d_not_run_by_memory_gate
whole_phaseC_pass = false
```

这是当时正确的历史阶段记录，但现在已有新的：

```text
full3d_closure_summary.json
status = same_degree_p3_h5_hybrid_full3d_numerical_closure_pass
```

不得删除或篡改历史记录。应在旧文件中增加：

```text
historical_stage = true
superseded_for_current_disposition_by = records/stage3_p3_h5/full3d_closure_summary.json
```

或在目录 README/索引中明确优先级。

## 7.2 `hybrid_vs_full3d_summary.md` 内部自相矛盾

该文档顶部已经写入 p3/h5 同阶比较，但底部“高阶边界”仍声称 p3 full3D 未生成、正式对比只收口在 p2。

必须更新底部历史段，明确：

```text
p3/h5 same-degree comparison = closed
p4 target comparison = unavailable
p3/h5 grid convergence = not proven
```

## 7.3 closure summary 应增强 source compatibility 与累积证据依赖

`full3d_closure_summary.json` 应增加：

- full3D source 是 Hybrid source 的祖先；
- 两个 SHA 之间的 changed-file 分类；
- p3 full3D numerical core 未变化；
- reference NPZ 绑定和 SHA；
- 前一阶段 M80/M120/M160 funnel summary 的 SHA；
- augmented vs Schur-minimal anchor 的 SHA；
- current M160 closure watchdog/solver record SHA。

这样 `whole Phase C` 才能由一个 tracked closure record 显式引用全部累积证据。

## 7.4 full3D reference 建议增加最终矩阵规模字段一致性

`full3d_reference.json` 已保存 FE DoF、aux DoF、残差和物理结果，但建议同时直接保存：

```text
final_rows = 145943
final_assembled_nnz = 35566727
```

当前这些值存在于 closure 和 raw run summary 中；提升到 reference record 可减少后续依赖跳转。

### 处置

```text
documentation_and_evidence_hardening = REQUIRED
PDE_rerun = NOT_REQUIRED
p3_numerical_acceptance_blocked_by_these_issues = FALSE
selective_merge_blocked_until_fixed = TRUE
```

---

# 8. 后续执行边界

## 8.1 禁止重复

不需要重新运行：

- p3/h5 full3D；
- p3/h5 Hybrid M80/M120/M160；
- augmented vs Schur-minimal M160；
- p4 四模态迹；
- p4 assembly-only；
- Case090 144 PDE；
- QEP36。

## 8.2 当前分支允许的下一步

第一步只做轻量收口：

1. 修正第 7 节的文档和证据索引；
2. 新增一个 fail-closed 的 Phase C closure checker，读取 full3D reference、Hybrid M160、M funnel、augmented anchor 和 NPZ hash，重新计算关键差值；
3. 更新 selective merge manifest 到文件级精确清单；
4. 提交 response 和最终阶段 summary 后停止复审。

完成后，组件优先阶段可以分类为：

```text
high-order Floquet p3/p4 = qualified
QEP p3/p4 components = qualified
matched trace p3/p4 = qualified
p3/h5 target Hybrid/full3D = qualified at same discretization
p4 target = resource-gated on current host
```

## 8.3 下一项数值工作

用户此前决定自适应放在最后。因此若继续 Task033，推荐顺序仍是：

```text
fixed-order equal-accuracy synthesis using existing p2/p3 evidence
→ interface/buffer tradeoff
→ final p2 conforming h-adaptivity feasibility
```

但不得自动启动。p3/h3、buffer 或自适应需要用户再次指定范围和独立 review。

p4 target 应转移到更大内存环境或未来低内存/迭代路线，不应继续占用当前机器做 direct 尝试。

---

# 9. 最终处置

```text
Task033 Phase A QEP/tracking = ACCEPTED
Task033 Phase B p3/p4 matched trace = ACCEPTED
Task033 p4 four-mode trace addendum = ACCEPTED
Task033 Phase C p3/h5 same-degree numerical closure = ACCEPTED_WITH_QUALIFICATIONS
p3/h5 Hybrid memory benefit = ACCEPTED
p3/h5 Hybrid wall-clock speedup = NOT DEMONSTRATED
p3/h5 grid convergence = NOT PROVEN
p4/h5 target full3D = NOT RUN BY MEASURED MEMORY GATE
p4/h5 target Hybrid = NOT RUN BY RESOURCE GATE
p4 method universal feasibility = UNRESOLVED, NOT REJECTED
p3/h3 = NOT APPROVED
h adaptivity = DEFERRED
whole original Task033 = NOT COMPLETE
same branch continuation = APPROVED
selective merge = AFTER REQUIRED DOCUMENTATION HARDENING
whole branch merge = NOT YET APPROVED
```

本轮最重要的工程结论是：

> p3/h5 Hybrid 已经用同阶 full3D reference 正式证明，在 R/T/A、体吸收和五个 E/H 截面上保持高精度一致，同时将峰值内存从 7.781 GiB 降至 2.618 GiB；但当前 direct Hybrid 没有获得墙钟时间优势。p4 的高阶数学组件已经成立，但目标规模在当前宿主机上连装配阶段都接近或超过安全内存边界，因此正确处置是停止目标求解，而不是继续强跑。
