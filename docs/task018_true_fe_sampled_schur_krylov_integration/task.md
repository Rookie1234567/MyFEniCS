# CODEX TASK 20260708：Adaptive true-FE sampled Schur / AMS-HX Krylov integration

## 0. 任务定位

本任务继续在现有研究分支上执行，不新建分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task018_true_fe_sampled_schur_krylov_integration/
├── task.md
├── outcomes/
└── review_report.md
```

Task018 不是一个固定 checklist 任务，而是 AMS/HX + true-FE sampled Schur 主线的自适应推进任务。目标是把 Task017 的 one-shot 正信号转化为稳定的 Krylov / residual-correction / augmentation 求解过程；如果不能转化，则给出充分证据说明这条 AMS/HX + modal sampled Schur 路线应暂停。

---

## 1. 背景

Task017 的关键结果：

```text
baseline FE-AMS + aux identity residual = 2.146555954e-2
Petrov / adjoint W best improvement     = 1.000045x 或变差
true-FE sampled lift top_y residual     = 1.575120238e-2, improvement 1.363x
true-FE sampled lift top_bottom_y       = 3.688783940e-3, improvement 5.819x
true-FE lift right-PC KSP residual      = 2.354987702e-2, worse than baseline
```

解释：

```text
1. Task015/016 定位的 top/bottom zero-order y modal slow direction 仍然有价值；
2. Task016 的 P_FE^{-1}C_j positive same-H1 AMS lift 太弱；
3. Task017 的 true-FE sampled lift one-shot 有明确正信号；
4. 把 one-shot basis 直接作为 right additive PC 不一致；
5. 下一步必须研究正确的 Krylov 集成方式，而不是继续 Petrov W 扫描。
```

---

## 2. 最高优先级执行规则

本任务必须遵守 adaptive execution rule：

```text
无效方向：用最小必要证据记录后停止，不继续微调。
正信号方向：立即沿该方向继续推进，不停在“可以试试”的报告句式。
任务内允许 Codex 自主新增局部实验，只要仍在 AMS/HX + true-FE sampled Schur 主线内，并且不违反资源和正确性边界。
如果某个方法出现正信号，必须继续追踪它的稳定性、误差来源、KSP 集成形式和资源成本，直到它成功、失效或触发明确边界。
```

这意味着 Task018 的输出不能只是“这些方法都不行，建议后续尝试 X”。如果 X 在本任务边界内、成本可控且由当前证据自然推出，就应直接实现和运行。

---

## 3. 必须阅读的输入

开始前必须读取：

```text
docs/task017_petrov_adjoint_coarse_correction/review_report.md
docs/task017_petrov_adjoint_coarse_correction/outcomes/summary.md
docs/task017_petrov_adjoint_coarse_correction/outcomes/true_fe_sampled_lift_diagnostic.csv
docs/task017_petrov_adjoint_coarse_correction/outcomes/petrov_ksp_summary.csv
docs/task017_petrov_adjoint_coarse_correction/outcomes/residual_history_summary.csv
docs/task017_petrov_adjoint_coarse_correction/outcomes/next_decision.md
docs/task016_zero_order_lifted_coarse_correction/review_report.md
docs/task015_boundary_aware_pc_diagnostic/outcomes/summary.md
src/studies/run_stage4_petrov_adjoint_coarse_correction.py
src/studies/run_stage4_lifted_coarse_correction.py
src/studies/run_stage4_boundary_pc_diagnostic.py
src/studies/run_stage4_real_split_block_pc.py
```

---

## 4. 不再继续的方向

除非为了复现 baseline，不再继续以下路线：

```text
Petrov W_aux_residual / W_residual_projected / W_AZ / W_adjoint_diag / W_adjoint_pfe 扫描
Task016 的 right-only pfe_lift / diag_lift / balanced lift 微调
top_y-only 作为主线
full 708-mode Schur
未达到 gate 前的 p=2 h=5 或 full p=2 h=2
未收敛 R/T/A
```

---

## 5. 主目标

在 `default100 p=1 h=5` 上，把 Task017 的 `top_bottom_y` true-FE sampled lift 正信号转化为至少一个稳定 solver-like 过程。

最低成功标准：

```text
minimum useful: final true residual < 1e-2 或 improvement >= 2x
strong: final true residual <= 2e-3 或 improvement >= 10x
production-like: final true residual <= 1e-6
```

这里的 final true residual 必须来自完整 `||A_real x - b_real|| / ||b_real||`，不能只看 PETSc reported residual。

---

## 6. Stage A：baseline and Task017 signal reproduction

必须先复现：

```text
case = task014a_default100_stage4_block_grating_p1_h5
baseline FE-AMS + aux identity residual = 2.146555954e-2
selected mode set = top_bottom_y
mode ids = 177, 531
Task017 true-FE sampled lift one-shot residual ≈ 3.688783940e-3
```

输出：

```text
outcomes/baseline_and_signal_reproduction.csv
```

如果复现失败，先修正复现，不进入后续阶段。

---

## 7. Stage B：selected FE RHS solve quality escalation

目标：判断 Task017 的 one-shot 信号是否受 FE RHS solve 精度限制。

从低成本到高成本自适应推进：

```text
1. 复现 Task017 SciPy GMRES + FE diagonal fallback；
2. 收紧 selected FE RHS solve tolerance，例如 1e-2 -> 1e-4 -> 1e-6；
3. 记录 FE RHS residual、one-shot residual、time、RSS；
4. 如果更高精度明显改善 one-shot，则继续沿更高精度推进；
5. 如果更高精度无改善，停止该子方向；
6. 如果 SciPy diagonal GMRES 停滞，尝试 shifted/positive FE solve 或 guarded 1-2 RHS BLR/direct，只要内存安全；
7. 不允许 default100 大规模 full direct factorization 失控运行。
```

输出：

```text
outcomes/selected_fe_rhs_solve_sweep.csv
outcomes/true_fe_basis_quality.csv
```

判断：如果更准确 FE response 仍能保持或增强 one-shot `>=2x` 信号，继续进入 Stage C/D；如果 one-shot 信号消失，必须解释是否为复现或 basis normalization 问题。

---

## 8. Stage C：initial correction / restarted KSP

目标：验证 one-shot correction 是否可以作为初始修正，而不是 right PC。

测试形式：

```text
1. 先运行 baseline FE-AMS + aux identity 到 max_it 或停滞，得到 x0,r0；
2. 构造 Z_true_fe(top_bottom_y)，用 minres coarse solve 得到 delta x；
3. x_init = x0 + omega * delta x，omega 可自适应扫描 1, 0.5, 0.3, 0.1；
4. 从 x_init 继续 FGMRES，设置 initial guess nonzero；
5. 比较 initial-corrected residual、continued KSP final residual、history stagnation。
```

如果 initial correction 能保持 `residual < 1e-2` 或 `>=2x`，不要停止；应继续测试重复 correction 或 augmented form。

输出：

```text
outcomes/initial_correction_summary.csv
outcomes/initial_correction_history_summary.csv
```

---

## 9. Stage D：residual-corrected outer loop

目标：把 true-FE sampled correction 当作 residual equation correction，而不是普通 preconditioner。

建议形式：

```text
for cycle in 1..N:
    run FE-AMS baseline KSP for a bounded number of iterations
    compute true residual r = b - A x
    compute alpha = argmin ||r - A Z alpha||
    update x <- x + omega Z alpha
    record residual after correction
    continue if residual improves meaningfully
```

自适应规则：

```text
如果 1 cycle 有正信号，继续 2/4/8 cycles，直到 residual 停滞或变差。
如果 omega=1 变差，扫 0.5/0.3/0.1；如果所有 omega 变差，停止该子方向。
如果 top_bottom_y 正信号稳定，再考虑 top_bottom_xy；否则不扩大 mode set。
```

输出：

```text
outcomes/residual_corrected_loop_summary.csv
outcomes/residual_corrected_cycle_history.csv
```

---

## 10. Stage E：augmented / recycled GMRES prototype

目标：把 `Z_true_fe` 作为 augmentation space，而不是 PC apply。

可实现形式不限，但必须至少覆盖一种低侵入 prototype：

```text
1. projected residual solve: P = I - AZ (AZ^T AZ)^-1 AZ^T；
2. solve projected/preconditioned residual equation in scipy or PETSc prototype；
3. final coarse correction after Krylov solve；
4. compare with Stage C/D。
```

如果 Stage C/D 已经出现强信号，Stage E 应围绕该信号做最小增强；如果 Stage C/D 完全无效，Stage E 可以作为最后确认。

输出：

```text
outcomes/augmented_gmres_summary.csv
outcomes/augmentation_basis_diagnostic.csv
```

---

## 11. Stage F：自适应 gate and optional escalation

只有满足以下条件，才允许进入更大算例：

```text
default100 p=1 h=5 final true residual < 1e-2 或 improvement >= 2x；
且集成形式不是单次离线 one-shot，而是可重复或可作为 Krylov 初值/augmentation/outer loop 使用；
且 residual history 不显示立即反弹；
且内存和时间仍在 workstation-safe 范围。
```

如果仅 minimum gate 通过但 KSP/outer-loop 不稳定：

```text
继续 default100 p=1 h=5，不进 p=2。
```

如果 strong gate 通过：

```text
可以新增 reduced p=2 h=5 qualification，但仍不直接进入 full p=2 h=2。
```

full p=2 h=2 或 h=1.5 在本任务默认关闭。

---

## 12. 停止条件

只有在以下证据都满足后，才可建议暂停当前 AMS/HX + modal sampled Schur 主线：

```text
1. Task017 one-shot 正信号已复现；
2. 更准确 selected FE RHS solve 未能把 one-shot 信号转成稳定过程；
3. initial correction 无法保持 residual <1e-2 或 >=2x；
4. residual-corrected outer loop 无法保持改善，或改善迅速反弹；
5. augmented/recycled prototype 无法保留正信号；
6. top_bottom_y 与必要的最小 symmetry partner 已测；
7. 失败不是由明显 bug、mode mapping、normalization、sign、true residual 口径错误造成。
```

如果这些条件未满足，不要写“建议后续可以尝试”；应继续在本任务内完成可控的下一步实验。

---

## 13. 必须输出文件

```text
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/
├── summary.md
├── baseline_and_signal_reproduction.csv
├── selected_fe_rhs_solve_sweep.csv
├── true_fe_basis_quality.csv
├── initial_correction_summary.csv
├── initial_correction_history_summary.csv
├── residual_corrected_loop_summary.csv
├── residual_corrected_cycle_history.csv
├── augmented_gmres_summary.csv
├── augmentation_basis_diagnostic.csv
├── adaptive_experiment_log.csv
├── gate_decision.csv
├── solver_profile_ranking.md
├── merge_recommendation.md
├── next_decision.md
├── parameters.json
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保留轻量 JSON/CSV/log excerpts。不提交大型 matrix dumps、mesh dumps、HDF5、XDMF、VTU/PVTU 或完整 binary dumps。

---

## 14. summary.md 必须回答

```text
1. Task017 的 top_bottom_y one-shot 正信号是否复现？
2. 更准确的 selected FE RHS solve 是否增强、削弱或不改变 one-shot 信号？
3. initial correction 是否能把 residual 保持在 <1e-2 或 >=2x？
4. residual-corrected outer loop 是否稳定改善，还是反弹？
5. augmented/recycled GMRES prototype 是否比 Stage C/D 更好？
6. 是否有 solver-like profile 允许进入 p=2 h=5？
7. 是否建议合并代码？
8. 如果失败，是否已经满足暂停 AMS/HX + modal sampled Schur 主线的停止条件？
9. 若主线暂停，下一条替代路线是什么？
```

---

## 15. 合并策略

默认：

```text
merge_code: no
merge_docs_only: optional
```

只有满足以下条件，才考虑合并最小研究代码：

```text
default100 p=1 h=5 出现稳定 solver-like improvement；
代码局部、可维护；
不破坏 direct/BLR production path；
不默认启用实验 PC；
所有新 profile 都是 opt-in。
```

---

## 16. 最终目标句

任务结束时必须用一句话回答：

```text
Task017 的 true-FE sampled lift 正信号，能否被转化为稳定的 AMS/HX + sampled Schur Krylov 集成？
```

如果答案是否定的，必须说明当前 AMS/HX + modal sampled Schur 主线是否已被充分排除，以及为什么。
