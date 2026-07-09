# CODEX TASK 20260708：Petrov / adjoint-aware zero-order coarse correction and true-FE sampled Schur qualification

## 0. 任务定位

本任务继续在现有研究分支上执行，不新建分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task017_petrov_adjoint_coarse_correction/
├── task.md
├── outcomes/
└── review_report.md
```

本任务是 real-split AMS/modal coarse 主线的最后小范围 qualification 之一。目标不是继续扩大实现，而是回答：

```text
Task016 的 right-only lifted coarse correction 失败后，
引入 left/test space W 的 Petrov correction，或更准确的 selected-mode FE solve，是否能显著降低 default100 p=1 h=5 residual？
```

如果本任务仍失败，应明确建议暂停 real-split AMS + modal coarse 主线，转向更全局的波传播预条件器路线。

---

## 1. 背景和基线

Task015 定位：

```text
FE-AMS 后 residual 几乎全部在 aux block；
且几乎全集中在 top,(0,0),y auxiliary mode。
```

Task016 结果：

```text
right-only lifted coarse vector Z=[-P_FE^{-1}C_j; e_j] 无效；
best one-shot improvement ≈ 1.000045x；
best KSP improvement ≈ 0.999996x；
mode mapping 正确；coarse matrix 不病态；sign/scale/top-bottom/x-y variants 均无效。
```

当前 baseline：

```text
case = task014a_default100_stage4_block_grating_p1_h5
baseline profile = FE-AMS + aux identity
baseline true residual = 2.1465559540488233e-2
```

本任务成功门槛：

```text
minimum useful signal: residual < 1e-2 或 improvement >= 2x
strong signal: residual <= 2e-3 或 improvement >= 10x
production-like signal: residual <= 1e-6
```

若不能达到 minimum useful signal，应停止当前 real-split AMS + modal coarse 主线。

---

## 2. 必须阅读的输入

开始前必须阅读：

```text
docs/task016_zero_order_lifted_coarse_correction/review_report.md
docs/task016_zero_order_lifted_coarse_correction/outcomes/summary.md
docs/task016_zero_order_lifted_coarse_correction/outcomes/selected_mode_mapping.csv
docs/task016_zero_order_lifted_coarse_correction/outcomes/lifted_coarse_vector_diagnostic.csv
docs/task016_zero_order_lifted_coarse_correction/outcomes/one_shot_coarse_correction.csv
docs/task016_zero_order_lifted_coarse_correction/outcomes/lifted_coarse_ksp_summary.csv
docs/task016_zero_order_lifted_coarse_correction/outcomes/sampled_schur_diagnostic.csv
docs/task016_zero_order_lifted_coarse_correction/outcomes/next_decision.md
docs/task015_boundary_aware_pc_diagnostic/review_report.md
docs/task015_boundary_aware_pc_diagnostic/outcomes/aux_modal_residual_decomposition.csv
src/studies/run_stage4_lifted_coarse_correction.py
src/studies/run_stage4_boundary_pc_diagnostic.py
```

---

## 3. 核心假设

Task016 失败的可能原因：

```text
1. 系统非正规 / 非 Hermitian，只用 right coarse space Z 不够；
2. 需要 Petrov correction: x <- x + Z (W^T A Z)^-1 W^T r；
3. 当前 q_j = -P_FE^{-1} C_j 中的 P_FE^{-1} 是 positive same-H1 AMS proxy，太偏离真正 indefinite A_FE^{-1}；
4. coarse correction 应基于 adjoint / left residual direction，而不是只基于右响应。
```

Task017 要验证以上假设，而不是继续重复 right-only Z。

---

## 4. 硬边界

本任务只允许：

```text
default100 p=1 h=5；
tiny10 p=1 h=5 sanity / exact reference；
selected modes: top,(0,0),y 和 optional top/bottom,(0,0),y；
1-2 selected modes 起步；最多 top/bottom x/y 共 4 modes。
```

禁止：

```text
full p=2 h=2；
p=2 h=5，除非达到 strong signal；
p=2 h=1.5；
full 708-mode Schur；
all-mode volume deflation；
未收敛 R/T/A；
把实验代码默认接入 production solver。
```

---

## 5. 遇到问题时的处理原则

本任务需要多想、多试，但不能无边界扩张。遇到问题时必须按下列 ladder 处理。

### 5.1 如果 Petrov coarse matrix `W^T A Z` 病态

依次尝试：

```text
1. normalize Z 和 W；
2. 用 QR/SVD 删除近线性相关向量；
3. 从 top_y 单模态改为 top/bottom_y pair；
4. 加小 regularization delta = 1e-12 ~ 1e-8 * ||W^T A Z||；
5. 检查 real split 的 W/Z pair 构造是否成对；
6. 检查 transpose vs Hermitian transpose 口径。
```

### 5.2 如果 correction 变差

不要直接停止，依次尝试：

```text
1. Z sign flip；
2. W sign flip；
3. coarse update damping omega = 1, 0.3, 0.1, 0.03, 0.01；
4. one-shot post-correction vs KSP additive PC；
5. Petrov residual-corrected form；
6. single top_y vs top/bottom_y pair；
7. real-only / imag-only pair sanity。
```

### 5.3 如果 true-FE sampled solve 过贵

不要直接放弃。先做：

```text
tiny10 exact FE sampled solve；
default100 selected-mode iterative solve with loose tolerance；
default100 selected-mode BLR/direct only for 1-2 RHS if feasible；
record cost and stop before memory pressure。
```

### 5.4 如果 default100 仍无改善

必须退回 tiny10 或 smaller smoke case 验证机制。如果 tiny10 成功但 default100 失败，说明方法不可扩展或 lift 不稳定；如果 tiny10 也失败，说明机制错误。

---

## 6. Stage A：selected mode and baseline reproduction

### 6.1 目标

确认 Task016 的 mode mapping 与 baseline 仍然一致。

必须复现：

```text
baseline residual = 2.1465559540488233e-2
selected mode = top,(0,0),y
mode_id = 177 for default100
```

### 6.2 输出

```text
baseline_and_mode_verification.csv
```

字段：

```text
case,mode_set,mode_id,port,m,n,polarization,baseline_residual,real_aux_index,imag_aux_index,notes
```

若 mapping 不一致，停止并修正 mapping，不进入 Stage B。

---

## 7. Stage B：Petrov coarse correction one-shot diagnostic

### 7.1 目标

验证 left/test space `W` 是否能让 dominant zero-order correction 有效。

右空间 `Z` 从 Task016 复用：

```text
Z_pfe = [-P_FE^{-1} C_j ; e_j]
Z_diag = [-diag(A_FE)^-1 C_j ; e_j]
```

测试多个 left/test space：

```text
W_aux_residual: auxiliary residual coordinate / selected row basis
W_AZ: W = A Z
W_AZ_normalized
W_residual_projected: selected component of current residual
W_adjoint_diag: approximate adjoint response using diag(A_FE)^-* D_j^T
W_adjoint_pfe: approximate adjoint response using P_FE^{-*} D_j^T if feasible
```

Petrov correction：

```text
alpha = (W^T A Z)^-1 W^T r
x_new = x + Z alpha
```

或 complex/Hermitian counterpart，必须记录实际口径。

### 7.2 输出

```text
petrov_one_shot_diagnostic.csv
```

字段：

```text
case,mode_set,z_type,w_type,residual_before,residual_after,improvement,fe_fraction_after,aux_fraction_after,petrov_condition,regularization,omega,notes
```

### 7.3 成功标准

```text
minimum useful: residual < 1e-2 或 improvement >= 2x；
strong: residual <= 2e-3 或 improvement >= 10x。
```

如果所有 W choices 都无改善，进入 Stage C 做 true-FE sampled lift，不要直接停止。

---

## 8. Stage C：selected-mode true-FE sampled Schur / lift

### 8.1 目标

验证 Task016 的失败是否因为 `P_FE^{-1} C_j` 太弱。

构造更接近真实 FE response 的 lift：

```text
q_j ≈ -A_FE^{-1} C_j
```

只对 1-2 selected modes 做，不构造 full Schur。

### 8.2 解法顺序

按成本从低到高：

```text
1. tiny10 exact FE lift；
2. default100 selected RHS iterative FE solve with current best PC；
3. default100 selected RHS direct/BLR only if memory safe；
4. default100 loose-tolerance sampled solve, record residual of sampled solve。
```

### 8.3 输出

```text
true_fe_sampled_lift_diagnostic.csv
```

字段：

```text
case,mode_set,fe_lift_solver,fe_lift_rhs_count,fe_lift_solve_residual,fe_lift_time_s,fe_lift_rss_gb,one_shot_residual_after,improvement,notes
```

如果 true-FE lift 显著改善 residual，下一步可围绕 sampled Schur / true FE response 继续；如果仍无改善，说明 lifted coarse 主线应停止。

---

## 9. Stage D：KSP PC with best Petrov / true-FE lift

只有 Stage B 或 C 出现 minimum useful signal，才允许进入 Stage D。

测试：

```text
stage4_real_split_fgmres_petrov_top_y
stage4_real_split_fgmres_petrov_top_bottom_y
stage4_real_split_fgmres_true_fe_lift_top_y
```

输出：

```text
petrov_ksp_summary.csv
residual_history_summary.csv
```

字段：

```text
case,profile,mode_set,z_type,w_type,pc_form,status,iterations,true_relative_residual_norm,improvement,ksp_final_residual,rss_upper_gb,setup_time_s,solve_time_s,condition,regularization,omega,notes
```

成功标准同 Stage B。

---

## 10. Stage E：stop / continuation decision

### A 档

```text
true residual <= 2e-3 或 improvement >= 10x；
建议后续 reduced p=2 h=5 qualification。
```

### B 档

```text
residual < 1e-2 或 improvement >= 2x；
继续针对 Petrov/true-FE lift 强化，但不进 p=2。
```

### C 档

```text
所有 Petrov / true-FE sampled lift 均无 meaningful improvement；
建议暂停 real-split AMS + modal coarse 主线。
```

### D 档

```text
实现需要大幅侵入 production path；
或需要不可接受内存；
或结果不稳定且无法通过 troubleshooting 解释。
```

---

## 11. 如果 Task017 失败，必须明确给出替代路线

如果 Task017 仍不能达到 minimum useful signal，summary 和 next_decision 必须明确建议下一步转向更全局的 wave preconditioner 路线，例如：

```text
1. layered-background / RCWA-like approximate inverse；
2. sweeping / PML preconditioner；
3. two-level domain decomposition with physically meaningful coarse space；
4. shifted Maxwell + stronger inner solver；
5. 保留 BLR 作为 fallback，暂停低内存 real-split AMS 主线。
```

不要写“继续研究 Petrov correction”作为默认结论。

---

## 12. 必须输出文件

```text
docs/task017_petrov_adjoint_coarse_correction/outcomes/
├── summary.md
├── baseline_and_mode_verification.csv
├── petrov_one_shot_diagnostic.csv
├── true_fe_sampled_lift_diagnostic.csv
├── petrov_ksp_summary.csv
├── residual_history_summary.csv
├── solver_profile_ranking.md
├── merge_recommendation.md
├── next_decision.md
├── parameters.json
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保留轻量 JSON/CSV/log excerpts，不提交大型 matrix dumps、HDF5、XDMF、Paraview 或完整 binary dumps。

---

## 13. summary.md 必须回答

```text
1. mode mapping 和 baseline 是否复现？
2. 哪个 W/test space 最有效？
3. Petrov one-shot 是否达到至少 2x 改善？
4. true-FE sampled lift 是否比 P_FE lift 更有效？
5. KSP PC 是否比 one-shot 结果一致？
6. 是否允许进入 reduced p=2 h=5？
7. 是否建议合并代码？
8. 如果失败，是否建议暂停 real-split AMS + modal coarse 主线？
9. 下一步替代路线是什么？
```

---

## 14. 合并策略

默认：

```text
merge_code: no
merge_docs_only: optional
```

只有满足：

```text
default100 p=1 h=5 达到 minimum useful signal；
代码局部、可维护；
不破坏 direct/BLR production path；
不默认启用实验 PC。
```

才考虑合并最小代码。

---

## 15. 最终目标句

任务结束时必须用一句话回答：

```text
Petrov / adjoint-aware coarse correction 或 true-FE sampled lift 是否能挽救 Task016 失败的 right-only lifted correction？
```

如果答案是否定的，必须明确建议暂停当前主线，而不是继续无限细化。
