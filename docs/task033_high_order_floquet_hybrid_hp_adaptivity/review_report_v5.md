# REVIEW REPORT V5：Task033 p3 同阶闭合与后续精简执行范围

## 0. 审阅身份与更新后决定

```text
review = Task033 review_report_v5
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
reviewed_head = f3e5421a16f1594ffa62bafeb8ecb9cf79bc0c78
p3_full3d_reference_source = bd828f24dc1546263210d73d08bf7bc16ba8a129
p3_hybrid_closure_and_p4_trace_source = 95921ab76e39eb1a7c5b3321b93d36939afb4075
review_status = PHASE_C_P3_ACCEPTED_REMAINING_SCOPE_REDUCED
p3_h5_same_degree_numerical_closure = PASS_WITH_QUALIFICATIONS
p3_h5_hybrid_memory_reduction = PASS
p3_h5_wall_clock_speedup = NOT_DEMONSTRATED
p4_four_mode_matched_trace = PASS
p4_h5_target_full3d = NOT_RUN_BY_MEASURED_MEMORY_GATE
p4_h5_target_hybrid = NOT_RUN_BY_RESOURCE_GATE
interface_buffer_study = DEFERRED_UNTIL_DEFECT_GRATING
p3_h3 = NOT_REQUIRED_IN_CURRENT_SCOPE
variable_p_hp = CAPABILITY_AUDIT_ONLY
h_adaptivity = FINAL_NUMERICAL_PHASE
whole_task033 = PARTIAL_NOT_COMPLETE
same_branch_continuation = APPROVED
next_phase_execution = APPROVED_WITH_STOP_GATES
whole_branch_merge = NOT_YET_APPROVED
```

本报告保留前序审阅的数值结论，并吸收用户最新范围决定：

1. 当前结构完全规则，接口位置优化暂不具有足够工程价值，延后到有缺陷或任意三维端部结构；
2. 原始 20 项统一 p/h 矩阵缩减为具有明确决策价值的小矩阵；
3. 下一项核心数值工作是 p3 与 p2 的等精度效率比较；
4. p3/h3 不做，p4 目标解不再在当前机器尝试；
5. variable-p/hp 只做能力与资源审计，无原生可靠路线或资源超限时立即停止；
6. 1 TiB / 0.7 nm 推演在固定阶次比较和最终自适应结果完成后统一更新；
7. 当前分支可直接继续执行，但必须按本报告的阶段边界停止，不得恢复原始大矩阵批量运行。

---

# 1. 已接受的高阶与 Hybrid 证据

## 1.1 高阶组件

当前已接受：

- p3/p4 六面体 Nédélec 高阶双 Floquet；
- edge/face orientation、双周期角点和 MPI ownership；
- Case090 解析空气盒与 air–Si Fresnel fixture；
- p3/p4 截面 QEP、左右模态、Poynting 分类和双正交；
- 近简并 block tracking；
- p3/p4 matching trace；
- p4 四模态近简并迹 MPI1/MPI4；
- 无完整边界稠密方阵、无完整场或模态 gather 的组件合同。

这些组件不需要重复运行 Case090、QEP36 或 Phase B 小夹具。

## 1.2 p3/h5 full3D 与 Hybrid 同阶闭合

### full3D p3/h5

| 指标 | 实测值 |
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
| swap | 0 |
| elapsed | 103.59 s |

### Hybrid p3/h5 M160

| 指标 | 实测值 |
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

### 同阶误差

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

决定：

```text
p3_h5_M_funnel = PASS
p3_h5_augmented_vs_schur_minimal = PASS
p3_h5_same_degree_full3d_reference = PASS
p3_h5_RTA_and_field_closure = PASS
whole_phaseC_p3_h5_numerical_closure = PASS
continuous_solution_or_h_convergence = NOT_PROVEN
```

Hybrid 峰值内存约为 full3D 的 `0.336×`，降低约 66.35%；但 Hybrid 时间 111.94 s，full3D 时间 103.59 s，因此没有墙钟 speedup。

---

# 2. p4 当前处置

## 2.1 四模态迹组件

p4 四模态近简并迹使用 QEP 八个候选中的 `[4,5,6,7]` 四维块。MPI1/MPI4 均满足：

- Gram rank = 4/4；
- coefficient round-trip 约 `1e-15`；
- reconstruction residual 约 `1e-15`；
- principal cosine 约 1；
- MPI beta assignment 最大相对差 `5.226e-13`；
- 无 full-vector gather；
- 无 dense interface square。

```text
p4_four_mode_matched_trace = PASS
p4_near_degenerate_trace_basis_handling = PASS
p4_target_physical_solve = NOT_IMPLIED
```

## 2.2 p4/h5 目标资源负结果

p4/h5 assembly-only 实测：

| 指标 | 实测值 |
|---|---:|
| Nédélec DoF | 339,892 |
| Floquet constraint rows | 15,412 |
| base NNZ | 155,205,040 |
| base payload 估计 | 3.555 GiB |
| base assembly time | 463.11 s |
| internal RSS after DtN insert | 10.995 GiB |
| external memory authority | 12.616 GiB |
| factorization / solve | 未进入 |
| OOM killed | false |
| termination | controlled SIGTERM |

p4 Hybrid M160 的独立资源矩阵中心和上界约为 37.04/42.59 GiB。

```text
p4_h5_full3d_factorization = DO_NOT_LAUNCH_ON_CURRENT_HOST
p4_h5_full3d_solve = DO_NOT_LAUNCH_ON_CURRENT_HOST
p4_h5_hybrid_M160 = DO_NOT_LAUNCH_ON_CURRENT_HOST
p4_target_status = CURRENT_HOST_RESOURCE_INFEASIBLE
```

这不是 p4 数值或物理失败。未来在更大内存环境或低内存迭代路线中，需要重新建立 candidate-specific C0。

---

# 3. 原 Task33 剩余范围的重新定义

## 3.1 接口位置与 buffer 优化延期

当前结构的中间段和上下结构均为规则、无缺陷模型，现有接口 `z=10/110 nm` 已位于规则 z 不变区域，并已得到 p3/h5 同阶 full3D 闭合。

在此模型上继续比较 10、7.5、5、2.5 nm buffer，主要只能测量规则体积裁剪，不能代表未来缺陷、曲边或三维局部扰动附近的衰减模需求。因此本阶段取消接口位置数值矩阵：

```text
interface_buffer_tradeoff_current_regular_model = DEFERRED
restart_condition = defect_grating_or_nonuniform_3d_end_geometry_available
current_interfaces = retain_10_and_110_nm
```

未来引入缺陷光栅后，应重新比较 local FE 减少与所需 M 增加的联合代价。

## 3.2 p3/h3 与 p4 target 不再作为当前必做项

```text
p3_h3 = NOT_REQUIRED_CURRENT_SCOPE
p4_h5_target = CLOSED_AS_RESOURCE_GATED_NEGATIVE
p4_h3_or_finer = LOCKED
```

不得为了填满原始表格而启动这些组合。

## 3.3 原始统一 p/h 矩阵缩减

原计划的：

```text
p = 1,2,3,4
h = 5,3,2.5,2,1.5 nm
```

不再作为强制运行矩阵。新的决策矩阵为：

| 组合 | 身份 | 动作 |
|---|---|---|
| p2/h5 | 既有 full3D + Hybrid 基线 | 复用，不重跑 |
| p2/h3 | 既有较细 full3D + Hybrid 基线 | 复用，不重跑 |
| p3/h10 | 新的第一粗网格候选 | 必做，先 C0 |
| p3/h7.5 | 条件粗网格候选 | 仅 p3/h10 未达到等精度目标时运行 |
| p3/h5 | 当前最高质量同阶闭合参考 | 复用，不重跑 |
| p4/h5 | 当前机器资源负结果 | 保留，不重跑 |

以下组合退出当前执行范围：

- p1 全矩阵；
- p2/h2.5、h2、h1.5；
- p3/h3、h2.5、h2、h1.5；
- p4/h3 及更细；
- 仅为填表而无决策价值的组合。

`uniform_p_h_matrix.csv` 必须更新为上述实际身份，历史未运行项可保留，但要标记 `removed_by_reduced_scope` 或 `locked_by_resource_gate`，不得继续显示为待自动运行。

---

# 4. 下一主任务：p3 与 p2 等精度效率比较

## 4.1 核心问题

下一阶段只回答：

> 在达到与 p2/h3 相当或更好的物理误差时，较粗的 p3 网格能否减少 local DoF、rows、NNZ、峰值内存和总时间？

这比单纯证明 p3/h5 比 p2/h3 更高阶更有工程价值。

## 4.2 参考与边界

当前最高质量可用参考为 p3/h5 full3D。它不是连续解，因此必须称为：

```text
provisional_best_available_discrete_reference
not_continuum_reference
not_grid_converged
```

先将既有 p2/h5、p2/h3 与 p3/h5 reference 比较，得到 p2 两个基线误差。然后评估 p3 粗网格。

## 4.3 执行漏斗

### Candidate A：p3/h10

1. candidate-specific C0；
2. full3D direct reference，只有资源 Gate 通过才运行；
3. Hybrid Schur-minimal M120、M160；
4. 检查 M120→M160；
5. 比较 p3/h10 与 p3/h5 reference；
6. 比较 p3/h10 的误差与 p2/h3 的误差；
7. 记录 full/local DoF、rows、NNZ、RSS 和时间。

### Candidate B：p3/h7.5

仅当 p3/h10 未达到 p2/h3 等精度目标时执行同一流程。若 p3/h10 已达到目标，则停止，不运行 h7.5。

### 禁止项

- 不运行 M240；
- 不重复 p3/h5 M80/M120/M160；
- 不运行 p3/h3；
- 不运行 p4 target；
- 不通过降低 M 或物理 Gate 制造效率优势。

## 4.4 等精度指标

至少比较：

- R/T/A 绝对误差；
- 显著衍射级功率相对误差；
- 显著衍射级复振幅相对误差；
- A volume；
- 五个选定截面的 E/H relative L2；
- full true residual；
- Hybrid/full3D 同网格一致性；
- local FE DoF、total rows、assembled NNZ；
- memory authority；
- wall time。

候选 p3 粗网格只有在物理误差不差于 p2/h3，且至少一个主要资源指标下降时，才能称为等精度工程正结果。

```text
resource_reduction < 1.3x = weak
1.3x_to_2x = useful_positive
2x_to_3x = clear_success
>=3x = engineering_target
```

---

# 5. variable-p / hp zoning 的处置

## 5.1 内存不是首要难点

variable-p/hp 并不必然比 global p3 更耗内存。理想情况下，少量高阶或细网格区与大范围低成本区组合，可能减少总 DoF。

但对 H(curl) 而言，主要难点是：

- 不同 p 相邻单元之间的切向连续；
- 周期配对面同步 p；
- edge/face orientation；
- MPI ownership；
- 高阶 matching trace；
- DOLFINx/Basix 是否提供原生、稀疏、可维护的 cellwise variable-degree 路径。

如果需要自行发明任意 unequal-p H(curl) 约束、mortar 或复杂多空间耦合，其开发风险远大于当前收益。

## 5.2 当前批准范围

```text
variable_p_hp_target_scale_PDE = NOT_APPROVED
variable_p_hp_capability_audit = APPROVED
optional_small_microfixture = CONDITIONAL
```

执行顺序：

1. 静态审计 DOLFINx/Basix 原生支持；
2. 若没有原生可靠路线，记录 `not_implemented_by_capability_gate`，只写 hp zoning 设计报告；
3. 若存在原生路线，只允许建立小型两区 p2/p3 microfixture；
4. microfixture 运行前预测中心必须小于 1.5 GiB、上界小于 2.0 GiB；
5. 只验证切向连续、orientation、周期同步、MPI 和稀疏性；
6. 不在当前目标光栅上运行 variable-p/hp；
7. 不使用 p4 zoning。

因此该项不会成为新的大内存 campaign。若原生能力不足，几乎不需要 PDE 计算即可收口。

---

# 6. 自适应与 1 TiB / 0.7 nm 推演顺序

## 6.1 自适应仍为最后一个数值阶段

固定阶次等精度比较和 variable-p 能力审计完成后，最后一个数值阶段才是固定 p2 的 conforming graded-h / h-adaptive feasibility：

```text
uniform_p2_h5_mechanism_reference
→ uniform_p2_h3_compression_reference
→ conditional finer RTA/order bridge
```

不在第一版引入自定义 hanging-node H(curl) 或复杂 DWR 作为阻塞项。

## 6.2 1 TiB / 0.7 nm 推演

1 TiB / 0.7 nm 推演不是下一步立即运行的 PDE。它应在以下数据齐全后统一更新：

- 最佳固定阶次 p3/p2 等精度压缩率；
- variable-p/hp capability 结论；
- 最终 p2 h-adaptive 压缩率；
- 当前 M 与 trace/QEP 资源数据。

自适应是最后一个数值阶段，1 TiB 推演和文档收口位于其后，不改变“自适应最后做”的原则。

最终推演必须区分：

```text
measured_current_scale
calibrated_scaling
analytical_projection
unresolved_modal_scalability
```

不得宣称 Task33 已证明 0.7 nm 可解。

---

# 7. 当前直接执行授权

## 7.1 可立即执行

当前分支批准直接继续：

### Phase D0：轻量文档与证据收口

- 修正历史 `phaseC_summary.json` 的 superseded 标识；
- 统一 `hybrid_vs_full3d_summary.md`；
- 加强 full3D closure source compatibility audit；
- 更新 `uniform_p_h_matrix.csv`；
- 更新 selective merge manifest；
- 不重跑任何 PDE。

### Phase D1：精简固定阶次等精度研究

- 复用 p2/h5、p2/h3、p3/h5；
- 运行 p3/h10；
- 仅在必要时运行 p3/h7.5；
- 每个新组合先独立 C0；
- 一次只运行一个重型 case；
- no swap；
- 外部 watchdog；
- 完成后生成独立 equal-accuracy summary 并停止。

### Phase D2：variable-p/hp 轻量能力审计

- 可与 D0/D1 的文档工作并行；
- 不启动目标尺度 PDE；
- microfixture 必须满足第 5.2 节资源门禁；
- 完成 capability report 后停止。

## 7.2 尚未批准

```text
p3_h3 = NOT_APPROVED
p4_target = NOT_APPROVED
interface_buffer_matrix = DEFERRED
h_adaptivity = WAIT_FOR_D1_REVIEW
0p7nm_PDE = OUT_OF_SCOPE
```

D1 和 D2 完成后必须提交 phase summary，再决定是否进入最后的 h-adaptive 阶段。

---

# 8. 难点与风险判断

可以直接继续，但不能说完全没有难点。

剩余工作已经没有新的 Maxwell 基础理论难点，也不需要重新开发 Floquet、QEP 或 Hybrid 主链。主要风险缩减为：

1. **等精度口径**：必须使用同一 provisional reference 和同一误差指标，不能只比较 p、h 或 R/T/A 的单个数字；
2. **停止规则**：p3/h10 达标后必须停止，不得机械运行 p3/h7.5；
3. **资源预测**：新 p3 粗网格虽然预计安全，仍必须做 candidate-specific C0；
4. **variable-p 能力**：难点是原生支持与可维护性，而不是小夹具内存；
5. **证据累计**：新 summary 必须引用已有 M funnel、p3/h5 reference 和 source hashes，不能形成互相矛盾的状态文件。

在冻结上述范围后，D0–D2 属于低到中等风险、可直接执行的阶段，不应再出现连续两天的大规模无界 campaign。

---

# 9. 最终处置

```text
Task033 Phase A QEP/tracking = ACCEPTED
Task033 Phase B p3/p4 matched trace = ACCEPTED
Task033 p4 four-mode trace = ACCEPTED
Task033 Phase C p3/h5 same-degree closure = ACCEPTED_WITH_QUALIFICATIONS
p3/h5 Hybrid memory benefit = ACCEPTED
p3/h5 Hybrid wall-clock speedup = NOT DEMONSTRATED
p3/h5 grid convergence = NOT PROVEN
p4 target = CURRENT_HOST_RESOURCE_GATED
interface buffer optimization = DEFERRED_UNTIL_DEFECT_GEOMETRY
reduced fixed-order equal-accuracy phase = APPROVED_TO_START
variable-p/hp capability audit = APPROVED
variable-p/hp target prototype = NOT_APPROVED
h adaptivity = FINAL_NUMERICAL_PHASE_NOT_YET_STARTED
1 TiB / 0.7 nm projection = AFTER_MEASURED_COMPRESSION
whole original Task033 = NOT COMPLETE
same branch continuation = APPROVED
whole branch merge = NOT YET APPROVED
```

当前最重要的工程结论仍是：

> p3/h5 Hybrid 已用同阶 full3D reference 证明，在 R/T/A、体吸收和五个 E/H 截面上保持高精度一致，同时将峰值内存从 7.781 GiB 降至 2.618 GiB；下一步不再扩展高阶组件，而是以极小矩阵回答 p3 粗网格能否在 p2/h3 等精度下进一步降低资源。接口位置优化等待缺陷光栅，variable-p/hp 只做低资源能力审计，自适应保留为最后一个数值阶段。
