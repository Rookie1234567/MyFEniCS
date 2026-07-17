# REVIEW REPORT V6：Task033 缩减范围完成、遗留项移交与合并准入

## 0. 审阅身份与修正后决定

```text
review = Task033 review_report_v6 revised
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
review_v5_control_commit = 737c699c287268d587a594fe514eb515bb1012bc
reviewed_phaseD_commit = c1029ddf9feee31844f555d3f351237f4d84abd9
reviewed_equal_accuracy_payload_sha256 = 3c322f4bb2864facf5076570c8f57d70972912cd60435d0debe7acdd110ebe0f
review_status = TASK033_REDUCED_SCOPE_ACCEPTED_MERGE_PREPARATION_APPROVED

D0_document_and_evidence_closure = PASS_WITH_LIGHT_FINAL_HARDENING
D1_p3_h10 = ACCEPTED_NEGATIVE_NOT_EQUAL_ACCURACY
D1_p3_h7p5 = ACCEPTED_FIXED_P_EQUAL_ACCURACY_CLEAR_SUCCESS_WITH_QUALIFICATIONS
D2_variable_p_hcurl = ACCEPTED_FAIL_CLOSED
p3_h5_same_degree_hybrid_full3d = ACCEPTED
p4_target = ACCEPTED_RESOURCE_GATED_NEGATIVE

h_adaptivity = TRANSFER_TO_NEXT_TASK
updated_1TiB_0p7nm_projection = TRANSFER_TO_NEXT_ADAPTIVE_SCALABILITY_TASK
interface_buffer = DEFERRED_UNTIL_DEFECT_OR_NONUNIFORM_END_GEOMETRY
variable_p_target_prototype = NOT_REQUIRED_BY_CAPABILITY_GATE
p3_h3 = NOT_REQUIRED_IN_TASK033_REDUCED_SCOPE

task033_reduced_scope = COMPLETE_WITH_QUALIFICATIONS_AND_NEGATIVE_RESULTS
original_task033_full_scope = PARTIAL_BY_EXPLICIT_USER_SCOPE_TRANSFER
additional_task033_PDE = NOT_APPROVED
same_branch_light_closure = APPROVED
selective_merge_to_master = APPROVED_AFTER_F0_MERGE_CLOSURE
whole_branch_merge = NOT_APPROVED
```

本修正吸收用户的最新决定：固定 p=2 的 conforming graded-h / h-adaptive 研究不再属于 Task033 的最后阶段，而是移交到一个新的独立任务。与自适应直接相关的压缩率、1 TiB / 0.7 nm 更新和 adaptive profile 研究一起移交，不再阻塞 Task033 收口。

因此，Task033 当前不再需要新的大型 Maxwell、QEP、Hybrid、p3/h3、p4 target 或 adaptive PDE。剩余工作全部属于不需要重跑 PDE 的合并前轻量收口。

---

# 1. Task033 当前接受的主要成果

## 1.1 高阶 Floquet 与解析资格化

已接受：

- p=3、p=4 六面体 Nédélec 高阶双 Floquet；
- edge/face entity transformation 与 orientation；
- 双周期角点、边和面 ownership；
- 稀疏、分布式约束路径；
- topology cache 与 phase-only update；
- Case090 空气盒与 air-Si Fresnel fixture；
- p1-p4、S/P、h、MPI1/2/4 共 144 个正式 PDE；
- 无 boundary-size dense square；
- 无完整边界场或完整模态向量 gather。

该组件链不需要重复运行 Case090。

## 1.2 高阶 QEP、tracking 与 matching trace

已接受：

- p3/p4 横截面 QEP；
- right/left modes；
- Poynting classification；
- biorthogonality；
- near-degenerate block tracking；
- p3/p4 matching trace；
- p4 四模态近简并迹 MPI1/MPI4；
- p1、p2 的真实负结果按原样保留。

当前冻结环境中 native cellwise variable-p H(curl) 没有合格证据，因此 fail closed 是正式结果，不是未完成的实现缺口。

## 1.3 p3/h5 Hybrid-full3D 同阶闭合

p3/h5 full3D：

| 指标 | 实测值 |
|---|---:|
| Nédélec DoF | 145,863 |
| final rows | 145,943 |
| assembled NNZ | 35,566,727 |
| true relative residual | `5.442e-12` |
| memory authority | 7.781 GiB |
| elapsed | 103.59 s |
| swap | 0 |

p3/h5 Hybrid M160：

| 指标 | 实测值 |
|---|---:|
| retained modes / direction | 160 |
| local rows | 21,847 x 2 |
| local assembled NNZ | 5,156,503 x 2 |
| true relative residual | `2.343e-12` |
| memory authority | 2.618 GiB |
| elapsed | 111.94 s |
| swap | 0 |

同阶差异：

| 指标 | Hybrid-full3D / 最大误差 |
|---|---:|
| max abs R/T/A delta | `1.214e-7` |
| five-plane max E relative L2 | `1.100e-5` |
| five-plane max H relative L2 | `1.098e-4` |
| middle-plane max E relative L2 | `8.387e-6` |
| middle-plane max H relative L2 | `1.098e-4` |

决定：

```text
p3_h5_M_funnel = PASS
p3_h5_augmented_vs_schur_minimal = PASS
p3_h5_same_degree_full3d_reference = PASS
p3_h5_RTA_and_field_closure = PASS
p3_h5_Hybrid_memory_reduction = PASS
p3_h5_wall_clock_speedup = NOT_DEMONSTRATED
p3_h5_grid_convergence = NOT_PROVEN
```

## 1.4 p4 目标资源负结果

p4 的 Floquet、QEP、近简并 block 和四模态迹组件已经通过，但目标 h5 装配得到：

```text
Nedelec DoF = 339,892
base NNZ = 155,205,040
external memory authority = 12.616 GiB
factorization stage = not entered
solve stage = not entered
OOM killed = false
termination = controlled
```

p4 Hybrid M160 的独立资源预测中心/上界约为 37.04/42.59 GiB。因此：

```text
p4_h5_full3d = NOT_RUN_BY_MEASURED_MEMORY_GATE
p4_h5_hybrid = NOT_RUN_BY_RESOURCE_GATE
p4_numerical_method_failure = FALSE
p4_current_host_target_feasibility = FALSE
```

该负结果可随 Task33 一并合入 master，作为资源边界证据。

---

# 2. Phase D 固定阶次等精度结论

## 2.1 等精度定义

p3/h5 full3D 被用作：

```text
provisional_best_available_discrete_reference
not_continuum_reference
not_grid_converged
```

p2/h3、p3/h10 和 p3/h7.5 均相对该同一离散参考比较：

- R/T/A 和体吸收；
- 五个选定截面 E/H；
- 上下接口切向 E/H；
- 显著衍射级功率 max/RMS；
- 显著衍射级复振幅 max/RMS；
- full true residual。

该方法只支持 provisional discrete ranking，不支持连续解误差或网格收敛声明。

## 2.2 p3/h10 负结果

```text
Nedelec DoF = 23,073
memory authority = 1.980 GiB
elapsed = 22.390 s
true residual = 1.349e-11
```

除真残差外，p3/h10 的全部 12 个物理等精度指标均劣于 p2/h3。Hybrid M120/M160 的 sampled interface H-t Gate 均失败，且 M 增加不改善。因此：

```text
p3_h10_equal_accuracy = FAIL
p3_h10_low_resource = TRUE
p3_h10_selected = FALSE
p3_h10_M240 = NOT_REQUIRED
```

## 2.3 p3/h7.5 固定阶次正结果

```text
full3D Nedelec DoF = 63,747
full3D memory = 3.667 GiB
full3D elapsed = 44.487 s
full3D true residual = 6.449e-12
```

p3/h7.5 的全部规定误差均不劣于 p2/h3。Hybrid M120、M160 均通过 16 项 Gate，M120->M160 收敛，M160 相对同网格 full3D 的最大 R/T/A 差为 `1.264e-6`。

资源比较：

| 指标 | p2/h3 M160 | p3/h7.5 M160 | baseline/candidate | 分类 |
|---|---:|---:|---:|---|
| local FE DoF | 68,396 | 26,598 | 2.571x | clear success |
| local-system rows | 68,476 | 26,678 | 2.567x | clear success |
| total rows | 68,796 | 26,998 | 2.548x | clear success |
| factor-inventory NNZ | 60,672,040 | 17,057,414 | 3.557x | engineering target |
| memory authority | 3.224 GiB | 2.008 GiB | 1.606x | useful positive |
| wall time | 99.686 s | 74.908 s | 1.331x | useful positive |

正式分类冻结为：

```text
fixed_p_equal_accuracy_clear_success
with_useful_measured_memory_positive
with_indicative_measured_time_positive
factor_inventory_engineering_target
formal_hp_3x_combined_target = NOT_ACHIEVED
```

不得将其写成“联合 hp 压缩达到 3x”，也不得将 1.331x 时间改善外推为普适 speedup。

---

# 3. variable-p / hp zoning 的最终处置

当前冻结环境：

```text
Basix = 0.10.0
DOLFINx = 0.10.0.post2
UFL = 2025.2.0.post0
```

公开 API 中虽然存在 mixed element、submesh、mixed-topology form 和 MixedFunctionSpace，但没有合格证据证明：

- unequal-p Nédélec 邻接单元切向连续；
- periodic paired faces 的 p 同步；
- edge/face orientation；
- variable-p trace；
- MPI ownership；
- 原生、稀疏、可维护的 cellwise variable-degree H(curl) 路径。

因此：

```text
native_cellwise_variable_p_hcurl = NOT_QUALIFIED
bespoke_unequal_p_constraints = FORBIDDEN
variable_p_target_PDE = NOT_RUN
p2_p3_variable_p_microfixture = NOT_TRIGGERED
hp_zoning = DESIGN_REPORT_ONLY
D2_requires_more_Task033_PDE = FALSE
```

该负结果已经完成 Task33 在 variable-p 方面的审计职责。

---

# 4. 从 Task33 移交到后续任务的内容

以下内容不再视为 Task33 的 merge blocker。

| 内容 | Task33 处置 | 后续重启条件 |
|---|---|---|
| p2/h5 conforming graded-h / h-adaptive | 移交下一任务 | 新 task、独立 mesh/accuracy Gate |
| p2/h3 adaptive compression | 移交下一任务 | h5 mechanism 先通过 |
| adaptive measured compression | 移交下一任务 | 至少一条合格 graded-h 结果 |
| 1 TiB / 0.7 nm 更新 | 移交 adaptive/scalability task | adaptive 实测 + 重新校准的高阶资源模型 |
| interface buffer sweep | 等待 defect/nonuniform-end geometry | 新几何有实际接口位置问题 |
| p4 target | 等待更大内存或低内存算法 | candidate-specific 新资源 Gate |
| p3/h3 | 当前范围取消 | 新的明确科研问题与资源授权 |
| variable-p target prototype | capability Gate 关闭 | 未来原生 API/语义证据 |

原始 Task033 的 full-scope 21-role manifest 应继续保留为 `NOT_RUN` 历史身份，不能改写为 full-scope pass。与此同时，应新增一个 **reduced-scope completion record**，准确说明用户批准的缩减范围已经完成。

---

# 5. 除自适应外仍需完善的事项

当前不再有数值算法或大型 PDE 缺口。合并前只剩以下轻量事项。

## 5.1 D1 source compatibility audit

需新增 tracked D1 audit，覆盖：

```text
p3/h10 full3D source = bb03ad4557e4cf8ada2a7448e9a4e8386ec196b6
p3/h10 Hybrid source = 6cb63a5b49ef2db0491ef21a5536eef5f54e1feb
p3/h7.5 full3D source = 6cb63a5b49ef2db0491ef21a5536eef5f54e1feb
p3/h7.5 Hybrid source = 7a7db5874b1eca5e60e5367e0e8bfb3fe0fd0d73
```

已独立确认这些相邻 source split 只增加 descriptor/audit 记录，没有修改 Maxwell、Floquet、QEP、Hybrid coupling、Schur solver 或后处理数值 kernel。正式文件只需冻结该结论，不需要重跑 PDE。

## 5.2 跨记录资源口径

`reduced_equal_accuracy_summary.json` 应显式冻结：

- container image/digest；
- solver path；
- MPI=4；
- zero-swap；
- one-heavy-case-at-a-time；
- memory authority 定义；
- p2/h3 与 p3/h7.5 不同 clean SHA；
- wall-time 只作为 indicative measured comparison。

## 5.3 高阶内存预测负结果

必须把以下事实写入资源模型：

```text
p3_h10_predicted_upper = 1.947 GiB
p3_h10_full_solve_actual = 1.980 GiB
p3_h7p5_predicted_upper = 2.463 GiB
p3_h7p5_full_solve_actual = 3.667 GiB
prediction_is_launch_guard_not_measurement = TRUE
old_high_order_model_for_1TiB_projection = NOT_ALLOWED_WITHOUT_RECALIBRATION
```

## 5.4 scoped completion record

新增一个轻量、tracked、fail-closed 的 scoped completion record，至少绑定：

- Case090 Stage1 summary；
- QEP/tracking summary；
- Phase B matched trace；
- p3/h5 full3D closure；
- p4 resource negative；
- D1 equal-accuracy summary；
- D2 variable-p audit；
- source compatibility audits；
- test summary；
- selective merge manifest；
- adaptive/buffer/1TiB transfer disposition。

该记录应声明：

```text
task033_reduced_scope_complete = true
original_task033_full_scope_complete = false
adaptive_transferred_to_next_task = true
ordinary_default_changed = false
```

---

# 6. 合并策略

## 6.1 不批准 whole-branch merge

当前分支相对 master 为 46 个提交，包含：

- 已资格化高阶数值内核；
- 正式 runner、watchdog、聚合器和测试；
- 大量历史任务书、规划器和 full-scope schema；
- 未资格化的 adaptive、buffer 和 1 TiB 规划/runner；
- 原始 21-role full-scope NOT_RUN 路线。

直接 whole-branch merge 会把已接受能力和未资格化研究脚手架混在一起。因此：

```text
whole_branch_merge = NOT_APPROVED
selective_merge = REQUIRED
```

## 6.2 当前 manifest 需要收紧

现有 `selective_merge_manifest.csv` 的：

```text
src/**
```

过宽，不可作为最终合并清单。必须改成文件级精确 allowlist。

### 应纳入的类别

1. 已资格化的高阶 Floquet、QEP、mode tracking、matching trace 和 Hybrid 兼容改动；
2. p3 full3D reference 接线和必要的通用 watchdog；
3. D1 fixed-p equal-accuracy 聚合与资源 Gate；
4. D2 variable-p capability audit；
5. 与上述能力一一对应的测试；
6. Case090/091 的轻量 hash-bound 记录；
7. Task33 当前 summary、completion matrix、negative results、review/response 和 quick-start/theory 文档。

### 不应纳入本次 master 能力合并的类别

- `benchmarks/run_task033_adaptive_mesh.py`；
- `src/geometry/task033_periodic_graded_mesh.py`；
- adaptive profile/mesh prototype tests；
- buffer sweep runner/资格化声明；
- 1 TiB projection runner 及未资格化 production claim；
- full-scope campaign 自动执行脚本；
- 任何 heavy artifacts、mesh、field、matrix、factor、timeline 和 log；
- 仅为原 20 项矩阵服务、但未进入缩减范围的自动批量执行路径。

规划文档和 `NOT_RUN` 记录可作为历史文档保留，但不得作为 master 当前可执行能力宣传。

---

# 7. Phase F0：合并前最后收口

F0 不允许运行新的 Maxwell/QEP/Hybrid PDE。

按顺序完成：

1. 生成 D1 source compatibility audit；
2. 加强 equal-accuracy 跨记录资源口径；
3. 将正式分类统一为 fixed-p clear success；
4. 记录高阶内存预测低估；
5. 新增 reduced-scope completion record/checker；
6. 将 selective merge manifest 收紧为精确文件 allowlist；
7. 更新 summary、completion matrix、capability matrix 和 roadmap，明确 adaptive 已移交；
8. 运行合并前测试；
9. 生成 merge response，停止等待最终合并。

## 7.1 合并前最低测试

至少包括：

```text
Task033 focused tests
Task032 regression anchors
Case090/091 lightweight evidence checker
D1 equal-accuracy aggregator tests
D2 capability-audit tests
source compatibility tests
documentation contracts
Ruff
compileall
git diff --check
```

涉及 DOLFINx/Basix/PETSc 的测试应在冻结 Docker image 中运行；host-only 环境缺依赖不能替代容器验证。

## 7.2 变更冻结规则

F0 只允许修改：

- 文档；
- tracked summary/manifest；
- checker/aggregator；
- merge allowlist；
- 与证据合同直接对应的测试。

若 F0 修改 Maxwell、Floquet、QEP、Hybrid coupling、solver 或 physical postprocess 数值 kernel，则本审阅的 no-PDE-rerun 许可失效，必须重新评估受影响证据。

---

# 8. 修正后的最终处置

```text
Task033 high-order Floquet p3/p4 = ACCEPTED
Task033 QEP/tracking p3/p4 = ACCEPTED_WITH_LEGACY_NEGATIVES_PRESERVED
Task033 matched trace p3/p4 = ACCEPTED
Task033 p3/h5 Hybrid-full3D closure = ACCEPTED_WITH_GRID_CONVERGENCE_QUALIFICATION
Task033 p4 target = ACCEPTED_RESOURCE_GATED_NEGATIVE
Task033 p3/h10 = ACCEPTED_ACCURACY_NEGATIVE
Task033 p3/h7p5 = ACCEPTED_FIXED_P_EQUAL_ACCURACY_CLEAR_SUCCESS
Task033 variable-p Hcurl = ACCEPTED_FAIL_CLOSED
Task033 adaptive work = TRANSFERRED_TO_NEXT_TASK
Task033 interface buffer = DEFERRED_TO_DEFECT_GEOMETRY_TASK
Task033 1TiB/0p7nm update = TRANSFERRED_TO_ADAPTIVE_SCALABILITY_TASK
Task033 reduced scope = COMPLETE_AFTER_F0_LIGHT_CLOSURE
original full scope = PARTIAL_BY_USER_SCOPE_TRANSFER
additional Task033 PDE = NOT_APPROVED
selective merge to master = APPROVED_AFTER_F0
whole branch merge = NOT_APPROVED
```

Task33 当前最准确的工程结论是：

> p3/p4 高阶 Floquet、QEP 和 matching-trace 组件已经资格化；p3/h5 Hybrid 已用同阶 full3D 正式闭合，并显著降低峰值内存；在当前最好可用离散参考下，p3/h7.5 相对 p2/h3 获得约 2.55-2.57x 的行数/DoF 改善、3.56x 的因子库存改善、1.61x 的实测内存改善和 1.33x 的指示性时间改善。p4 目标规模在当前主机上被资源 Gate 合理否决，variable-p 在当前框架中 fail closed。自适应及其后的 1 TiB 推演移交新任务后，Task33 只需完成无 PDE 的 F0 证据和精确选择性合并收口，即可进入 master。