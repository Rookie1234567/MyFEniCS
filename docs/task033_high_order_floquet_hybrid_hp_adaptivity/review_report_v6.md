# REVIEW REPORT V6：Task033 Phase D 固定阶次等精度、variable-p 审计与自适应准入

## 0. 审阅身份与决定

```text
review = Task033 review_report_v6
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
review_v5_control_commit = 737c699c287268d587a594fe514eb515bb1012bc
reviewed_response = response_v6.md
reviewed_equal_accuracy_payload_sha256 = 3c322f4bb2864facf5076570c8f57d70972912cd60435d0debe7acdd110ebe0f
review_status = PHASE_D_ACCEPTED_WITH_QUALIFICATIONS
D0_document_and_evidence_closure = PASS_WITH_MINOR_HARDENING
D1_p3_h10 = ACCEPTED_NEGATIVE_NOT_EQUAL_ACCURACY
D1_p3_h7p5 = ACCEPTED_FIXED_P_EQUAL_ACCURACY_POSITIVE_WITH_QUALIFICATIONS
D2_variable_p_hcurl = ACCEPTED_FAIL_CLOSED
p2_h5_conforming_graded_h_mechanism = APPROVED_WITH_STOP_GATES
p2_h3_adaptive_compression = WAIT_FOR_E1_REVIEW
p3_h3 = NOT_APPROVED
p4_target = RESOURCE_GATED
interface_buffer = DEFERRED_UNTIL_DEFECT_GEOMETRY
updated_1TiB_0p7nm_projection = WAIT_FOR_ADAPTIVE_MEASUREMENT
whole_original_Task033 = PARTIAL_NOT_COMPLETE
same_branch_continuation = APPROVED
selective_merge = NOT_YET_APPROVED
whole_branch_merge = NOT_APPROVED
```

本轮审阅覆盖 Review V5 之后完成的三个阶段：

1. D0：历史状态、source compatibility、缩减矩阵和文档口径收口；
2. D1：`p3/h10 -> 条件 p3/h7.5` 的固定阶次等精度漏斗；
3. D2：当前冻结 DOLFINx/Basix 环境下的 native variable-p H(curl) 能力审计。

没有运行 Review V5 禁止的 `M240`、`p3/h3`、p4 target、adaptive、buffer 或 0.7 nm PDE。执行边界得到遵守。

---

# 1. D0 文档与证据收口

## 1.1 已完成事项

D0 已完成以下修正：

- 历史 `phaseC_summary.json` 被明确标记为已被 p3/h5 full3D closure 推进的历史阶段；
- `hybrid_vs_full3d_summary.md` 不再把旧 C0 内存否决写成当前 p3 状态；
- p3/h5 full3D source 与 Hybrid closure source 已建立 fail-closed compatibility audit；
- 12 个关键数值 kernel blob 完全一致；
- Phase6 runner 去除 reference registry 差异后的规范化 AST 完全一致；
- 原始 20 项 p/h 矩阵已缩减为 Review V5 指定的决策矩阵；
- completion matrix、negative results、capability matrix 和项目路线已同步；
- planning checker 继续正确保持 `claims_task033_complete=false`。

### 决定

```text
D0_scope = ACCEPTED
D0_requires_PDE_rerun = FALSE
```

## 1.2 仍需补强的 D1 source audit

当前 tracked `source_compatibility_audit.json` 的正式 scope 是 p3/h5 full3D reference 与 p3/h5 Hybrid closure。D1 的新记录还有两组相邻 source split：

```text
p3/h10 full3D source = bb03ad4557e4cf8ada2a7448e9a4e8386ec196b6
p3/h10 Hybrid source = 6cb63a5b49ef2db0491ef21a5536eef5f54e1feb

p3/h7.5 full3D source = 6cb63a5b49ef2db0491ef21a5536eef5f54e1feb
p3/h7.5 Hybrid source = 7a7db5874b1eca5e60e5367e0e8bfb3fe0fd0d73
```

独立比较显示：

- `bb03ad4 -> 6cb63a5` 只增加 p3/h10 descriptor，并更新 variable-p capability record；
- `6cb63a5 -> 7a7db58` 只增加 p3/h7.5 descriptor；
- 没有修改 Maxwell、Floquet、QEP、Hybrid coupling、Schur solver 或后处理数值 kernel。

因此 D1 数值比较可以接受。但选择性合并前应生成一份 tracked 的 D1 source-compatibility audit，显式保存上述 changed-path 分类和 kernel-unchanged 结论。该补强不需要重跑 PDE。

---

# 2. D1 等精度方法审阅

## 2.1 比较定义合理，但必须保留离散参考边界

D1 使用 p3/h5 full3D 作为：

```text
provisional_best_available_discrete_reference
not_continuum_reference
not_grid_converged
```

所有 p2/h3、p3/h10 和 p3/h7.5 都相对同一个 p3/h5 reference 计算：

- R/T/A 与体吸收绝对误差；
- 五个选定平面的 E/H relative L2；
- 两个接口的切向 E/H relative L2；
- 显著衍射级功率和复振幅的 max/RMS 相对误差；
- full true residual。

候选只有在所有规定误差均不劣于 p2/h3 时，才通过等精度 Gate。该方法能回答“候选是否至少达到当前 p2/h3 的离散精度水平”，但不能证明连续解误差，也不能证明 p3/h5 已收敛。

### 决定

```text
equal_accuracy_methodology = ACCEPTED_FOR_PROVISIONAL_DISCRETE_RANKING
continuum_accuracy_claim = NOT_ALLOWED
grid_convergence_claim = NOT_ALLOWED
```

---

# 3. p3/h10 负结果

## 3.1 full3D direct

```text
Nedelec DoF = 23,073
true residual = 1.349e-11
memory authority = 1.980 GiB
elapsed = 22.390 s
R/T/A = 0.0553985 / 0.4060679 / 0.5385336
swap = 0
```

p3/h10 虽然便宜且资源安全，但除线性残差外，所有 12 个物理等精度指标均劣于 p2/h3，包括：

- R/T/A 和体吸收；
- 五平面 E/H；
- 接口切向 E/H；
- 显著级功率 max/RMS；
- 显著级复振幅 max/RMS。

因此它不能作为等精度候选。

## 3.2 Hybrid M120/M160

p3/h10 的 M120 和 M160：

- 代数、QEP、残差、R/T/A、体吸收及中间平面 Gate 通过；
- sampled interface H-t Gate 未通过；
- M120 到 M160 几乎无变化；
- direct 候选本身已经等精度失败。

所以不运行 M240 是正确的。该负结果更接近粗网格/interface field representation 限制，而不是 modal truncation 不足。

### 决定

```text
p3_h10_equal_accuracy = FAIL
p3_h10_low_resource = TRUE
p3_h10_selected = FALSE
p3_h10_M240 = NOT_REQUIRED
```

---

# 4. p3/h7.5 等精度正结果

## 4.1 full3D direct

```text
Nedelec DoF = 63,747
true residual = 6.449e-12
memory authority = 3.667 GiB
elapsed = 44.487 s
R/T/A = 0.003090727 / 0.591160863 / 0.405748409
swap = 0
```

相对 p3/h5 provisional reference，p3/h7.5 的全部规定误差均不劣于 p2/h3：

| 指标 | p2/h3 误差 | p3/h7.5 误差 |
|---|---:|---:|
| abs ΔR | 0.003523 | 0.002001 |
| abs ΔT | 0.016969 | 0.009462 |
| abs ΔA | 0.013446 | 0.007461 |
| abs ΔAvol | 0.013446 | 0.007461 |
| 五平面 max E L2 | 0.496254 | 0.286621 |
| 五平面 max H L2 | 0.499354 | 0.290470 |
| 接口 max Et L2 | 0.496254 | 0.286621 |
| 接口 max Ht L2 | 0.456215 | 0.272020 |
| 显著级 power max/RMS | 0.765156 / 0.350882 | 0.649135 / 0.293093 |
| 显著级 amplitude max/RMS | 0.724457 / 0.400581 | 0.554958 / 0.324776 |

这些误差仍然不是“小误差”，尤其场和逐阶复振幅相对 p3/h5 仍有明显差异。因此正确措辞是：

> p3/h7.5 在当前 provisional reference 下不劣于 p2/h3，而不是 p3/h7.5 已达到最终生产精度。

## 4.2 Hybrid M 漏斗和同网格 direct 闭合

p3/h7.5 的 M120 与 M160：

- 两档均通过全部 16 项物理和代数 Gate；
- M120→M160 的 R/T/A 差约为机器精度；
- 显著级复振幅最大相对变化为 `1.405e-10`；
- M160 相对同网格 full3D 的最大 R/T/A 差为 `1.264e-6`；
- M160 selected-plane E/H 相对同网格 full3D 为约 `8.737e-5 / 3.500e-4`；
- M240 没有必要。

### 决定

```text
p3_h7p5_equal_accuracy_vs_p2_h3 = PASS
p3_h7p5_M120_to_M160 = PASS
p3_h7p5_Hybrid_full3D_same_grid = PASS
selected_mode_count_per_direction = 160
```

---

# 5. 资源效率审阅

## 5.1 同口径比较

资源比较使用：

```text
baseline = p2/h3 Hybrid M160 Schur-minimal
candidate = p3/h7.5 Hybrid M160 Schur-minimal
MPI = 4
swap = 0
```

| 指标 | p2/h3 | p3/h7.5 | baseline/candidate | 正式等级 |
|---|---:|---:|---:|---|
| local FE DoF | 68,396 | 26,598 | 2.571x | clear success |
| local-system rows | 68,476 | 26,678 | 2.567x | clear success |
| total rows | 68,796 | 26,998 | 2.548x | clear success |
| factor-inventory NNZ | 60,672,040 | 17,057,414 | 3.557x | engineering target |
| memory authority | 3.224 GiB | 2.008 GiB | 1.606x | useful positive |
| wall time | 99.686 s | 74.908 s | 1.331x | useful positive |

相应减少比例约为：

```text
local FE DoF reduction ≈ 61.1%
total-row reduction ≈ 60.8%
factor-inventory reduction ≈ 71.9%
measured-memory reduction ≈ 37.7%
wall-time reduction ≈ 24.9%
```

## 5.2 正式总分类需要收紧

当前 summary 使用：

```text
equal_accuracy_engineering_positive_with_qualification
```

该自然语言结论可以保留，但不能映射为原 Task33 的正式：

```text
hp_compression_engineering >= 3x combined
```

因为：

- local DoF/rows 为 2–3x，只达到 `clear_success`；
- 只有 factor-inventory NNZ 超过 3x；
- 实测内存和时间为 1.3–2x，只达到 `useful_positive`；
- variable-p/hp 并未实现；
- adaptive compression 尚未测量。

建议在 completion matrix 和最终 summary 中冻结为：

```text
fixed_p_equal_accuracy_clear_success
with_useful_memory_and_time_positive
factor_inventory_engineering_target
```

不得把本轮结果写成“Task33 已达到联合 hp 3x 工程目标”。

## 5.3 跨提交资源可比性

DoF、local rows、total rows 和 factor-inventory NNZ 是最稳健的结构指标。

内存与时间虽然使用相同 solver family、MPI4、zero-swap 和 watchdog 口径，但 p2/h3 baseline 与 p3/h7.5 来自不同 clean source SHA。Review V5 已批准复用，且数值主路径兼容，但仍应将：

- 1.606x memory improvement 标为 measured engineering comparison；
- 1.331x wall-time improvement 标为 indicative measured comparison；
- 不把 1.331x 外推为普适 speedup。

选择性合并前，reduced summary 应显式保存 container digest、solver path、MPI、memory-authority definition、one-heavy-case 和 zero-swap 的跨记录兼容性检查。

### 决定

```text
fixed_p_equal_accuracy_resource_result = ACCEPTED_WITH_QUALIFICATIONS
strict_structural_compression = PASS
measured_memory_positive = PASS_WITH_CROSS_SOURCE_QUALIFICATION
universal_wall_clock_speedup = NOT_PROVEN
formal_hp_3x_combined_target = NOT_ACHIEVED
```

---

# 6. 内存预测模型负结果

Review V5 的预测为：

```text
p3/h10 center/upper = 1.693 / 1.947 GiB
p3/h7.5 center/upper = 2.142 / 2.463 GiB
```

实测为：

```text
p3/h10 assembly = 1.406 GiB
p3/h10 solve = 1.980 GiB
p3/h7.5 assembly = 2.556 GiB
p3/h7.5 solve = 3.667 GiB
```

p3/h7.5 assembly 比预测 upper 高约 3.8%，full solve 比该 upper 高约 48.9%。由于绝对值仍远低于 watchdog controlled line，继续运行在本次是安全的；但这再次证明旧的高阶资源预测不能作为精确估计。

### 要求

```text
p3_h7p5_prediction_underestimated = TRUE
prediction_is_launch_guard_not_measurement = TRUE
old_high_order_model_for_1TiB_projection = NOT_ALLOWED_WITHOUT_RECALIBRATION
```

下一阶段资源表应把 p3/h10、p3/h7.5、p3/h5 三个实测 anchor 纳入校准。不得仅因这次未触发内存问题而忽略预测偏差。

---

# 7. D2 variable-p / hp 审阅

冻结环境为：

```text
Basix 0.10.0
DOLFINx 0.10.0.post2
UFL 2025.2.0.post0
```

审计确认公开 API 中存在：

- mixed element；
- function space；
- submesh；
- mixed-topology form；
- MixedFunctionSpace。

但这些 API 的存在不能证明：

- adjacent unequal-p Nédélec 的切向连续；
- periodic paired face 的 p 同步；
- edge/face orientation；
- variable-p trace；
- MPI ownership；
- 稀疏、可维护的原生 cellwise variable-degree 路径。

因此 fail closed 是正确处置：

```text
native_cellwise_variable_p_hcurl = NOT_QUALIFIED
bespoke_unequal_p_constraints = FORBIDDEN
variable_p_target_PDE = NOT_RUN
p2_p3_microfixture = NOT_TRIGGERED
hp_zoning = DESIGN_REPORT_ONLY
```

该结论只适用于当前冻结版本和现有证据，不是对未来 DOLFINx/Basix 的永久否定。

### 决定

```text
D2_variable_p_capability_audit = ACCEPTED
D2_requires_more_PDE = FALSE
```

---

# 8. 当前 Task33 完成度

当前已完成：

- p3/p4 高阶 Floquet；
- Case090 144 PDE；
- p3/p4 QEP、tracking 和 matched trace；
- p4 四模态近简并迹；
- p3/h5 Hybrid/full3D 同阶闭合；
- p4 当前主机资源负结果；
- p3/h10 与 p3/h7.5 固定阶次等精度研究；
- variable-p capability fail-closed audit；
- Review V5 缩减后的 D0/D1/D2。

尚未完成：

- p2 conforming graded-h / h-adaptive h5 mechanism；
- p2 adaptive h3 compression；
- adaptive measured compression 后的 1 TiB / 0.7 nm 更新；
- 原始 21-role formal manifest；
- 最终 publication/merge closure。

按用户决定，interface buffer 等待 defect/nonuniform-end geometry，不再作为当前 Task33 的阻塞项。

---

# 9. Phase E：最终 h-adaptive 数值阶段准入

## 9.1 本次只批准 E1：p2/h5 机制验证

```text
Phase_E1_p2_h5_conforming_graded_h = APPROVED
Phase_E2_p2_h3_compression = WAIT_FOR_E1_REVIEW
```

E1 的目标不是立即追求 3x，而是证明一个可维护的 conforming graded-h 路线可以在减少 local DoF 的同时复现 uniform p2/h5 reference。

## 9.2 允许的离散路线

只允许：

- fixed p=2；
- conforming hexahedral graded mesh；
- 周期两侧完全同步；
- matching 3D interface / 2D cross-section trace；
- 10/110 nm 已资格化接口；
- physics-informed material/interface/strong-gradient refinement；
- smooth region coarsening。

禁止：

- hanging-node H(curl) 自定义约束；
- variable-p；
- mortar/nonmatching interface；
- p3/h3 或 p4 target；
- DWR 作为第一阶段阻塞项；
- buffer sweep。

## 9.3 执行阶梯

### E1-0：文档和证据硬化

先完成且不运行 PDE：

1. 新增 D1 source compatibility audit；
2. 在 equal-accuracy summary 中保存跨记录资源口径检查；
3. 收紧正式 fixed-p compression 分类；
4. 将 p3/h7.5 预测低估写入资源模型 calibration negative。

### E1-1：mesh-only / trace preflight

最多提出一个 primary graded profile，并验证：

- 周期 paired faces 的网格完全一致；
- 无 hanging nodes；
- material interfaces 和几何特征精确保留；
- 3D interface mesh 与 2D QEP trace mesh 一致；
- Floquet entity pairing 和 orientation smoke 通过；
- candidate local FE DoF 小于 uniform p2/h5 baseline；
- no dense boundary square / no full gather；
- candidate-specific memory Gate 通过。

若 primary profile 不满足上述 mesh contract，只允许修正一次；不得铺开 profile sweep。

### E1-2：Hybrid M 漏斗

对通过 mesh Gate 的候选只运行：

```text
p2 graded-h Hybrid M120
p2 graded-h Hybrid M160
```

M160 只有在 M120→M160 通过后才作为候选结果；不得运行 M240，除非新审阅明确批准。

### E1-3：accuracy Gate

相对现有 uniform p2/h5 reference，至少要求：

```text
full true residual <= 1e-9
max abs R/T/A delta <= 1e-5
significant-order complex-amplitude relative delta <= 1e-3
sampled interface E relative error <= 5e-3
sampled interface H relative error <= 1e-2
selected-plane E/H relative error <= 5e-3
abs volume-energy closure <= 1e-5
M120 -> M160 convergence pass
```

### E1-4：compression 处置

使用：

```text
baseline = uniform p2/h5 Hybrid M160
candidate = graded p2/h5-equivalent Hybrid M160
```

记录：

- local FE DoF；
- local-system rows；
- total rows；
- assembled NNZ 与 factor inventory；
- memory authority；
- wall time；
- QEP/trace DoF 与 modal storage；
- accuracy metrics。

分类保持：

```text
<1.3x = weak
1.3-2x = useful positive
2-3x = clear success
>=3x = engineering target
```

若 accuracy 通过但 compression <1.3x，记录 weak signal 并停止。若 accuracy 未通过，只允许一次 physics-informed profile 修正；第二次仍失败则保存 negative 并停止。

## 9.4 E1 停止点

E1 summary 完成后必须停止复审。不得自动进入 p2/h3 adaptive compression。

---

# 10. 最终处置

```text
Task033 Review V5 D0 = ACCEPTED
Task033 Phase D1 p3/h10 = ACCEPTED_NEGATIVE
Task033 Phase D1 p3/h7.5 = ACCEPTED_FIXED_P_EQUAL_ACCURACY_POSITIVE_WITH_QUALIFICATIONS
Task033 Phase D2 variable-p = ACCEPTED_FAIL_CLOSED
fixed_p_equal_accuracy_clear_success = ACHIEVED
measured_memory_useful_positive = ACHIEVED
formal_combined_hp_3x_target = NOT_ACHIEVED
p2_h5_conforming_graded_h_mechanism = APPROVED
p2_h3_adaptive_compression = NOT_YET_APPROVED
updated_1TiB_projection = DEFERRED
same_branch_continuation = APPROVED
selective_merge = AFTER_D1_HARDENING_AND_E1_REVIEW
whole_original_Task033 = PARTIAL
whole_branch_merge = NOT_APPROVED
```

本轮最重要的工程结论是：

> 在当前最好可用但尚未网格收敛的 p3/h5 离散参考下，p3/h7.5 的全部规定物理误差均不劣于 p2/h3；使用同为 M160 的 Schur-minimal Hybrid 路径时，local FE DoF 和 total rows 约减少 61%，factor inventory 约减少 72%，实测内存约减少 38%，时间约减少 25%。这是 fixed-p 等精度的明确工程正结果，但不是联合 hp 3x 成功、连续解收敛或 0.7 nm 可行性证明。下一步只批准 fixed-p p2 的 h5 conforming graded-h 机制验证。