# REVIEW REPORT 20260708：Task018 adaptive true-FE sampled Schur / AMS-HX Krylov integration

## 1. 审查对象

审查分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task018_true_fe_sampled_schur_krylov_integration/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/baseline_and_signal_reproduction.csv
outcomes/selected_fe_rhs_solve_sweep.csv
outcomes/true_fe_basis_quality.csv
outcomes/initial_correction_summary.csv
outcomes/initial_correction_history_summary.csv
outcomes/residual_corrected_loop_summary.csv
outcomes/residual_corrected_cycle_history.csv
outcomes/augmented_gmres_summary.csv
outcomes/augmentation_basis_diagnostic.csv
outcomes/adaptive_experiment_log.csv
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
src/studies/run_stage4_true_fe_sampled_schur_krylov.py
```

本报告审查 Task018 的 adaptive true-FE sampled Schur / AMS-HX Krylov integration。审查对象仍是研究 runner，不把本轮流程视为 production solver。

---

## 2. 总体结论

Task018 通过审查，并且是当前 AMS/HX + modal sampled Schur 主线的强正结果。

核心结论：

```text
Task017 的 true-FE sampled lift 正信号，已经被转化为稳定的 solver-like residual-correction process。
```

最佳结果来自：

```text
profile = residual_outer_zero
case    = task014a_default100_stage4_block_grating_p1_h5
```

数值为：

```text
baseline FE-AMS + aux identity residual = 2.145878536207579e-2
best residual_outer_zero residual       = 1.6616234679826358e-3
improvement                             = 12.914348993956336x
```

该结果同时通过：

```text
minimum useful gate: residual < 1e-2 或 improvement >= 2x
strong gate: residual <= 2e-3 或 improvement >= 10x
```

但它没有达到：

```text
production-like gate: residual <= 1e-6
```

因此本轮判断是：

```text
continue AMS/HX + true-FE sampled Schur line: yes
allow p=2 h=5 next gated qualification: yes
allow full p=2 h=2: no
allow h=1.5: no
merge research runner: yes, opt-in only
merge production solver: no
```

---

## 3. 与 Task017 的关系

Task017 证明：

```text
true-FE sampled lift top_bottom_y one-shot 有正信号；
right additive PC 集成失败。
```

Task018 的关键进步是：

```text
不再把 Z_true_fe 当普通 right PC；
而是把它作为 residual-correction / initial-correction / augmentation space。
```

最有用的 correction space 仍然是：

```text
J = {top,(0,0),y; bottom,(0,0),y}
Z_J = [ -A_FE^{-1} C_J ; I_J ] 的 selected / filtered approximation
```

但 Task018 的数据说明，当前最佳 `Z_J` 不是越精确越好，而是：

```text
SciPy GMRES + diagonal preconditioner, rtol=1e-2
```

得到的 filtered FE response 最有效。

---

## 4. 关键数值审查

| profile | final true residual | improvement | 审查判断 |
|---|---:|---:|---|
| baseline FE-AMS + aux identity | `2.145878536e-2` | `1.000x` | baseline reproduced |
| one-shot `top_bottom_y`, SciPy GMRES rtol `1e-2` | `1.732413109e-3` | `12.387x` | strong positive |
| initial correction omega `1.0` + 200-step continuation | `1.680968603e-3` | `12.766x` | stable positive |
| residual outer loop from baseline solution | `1.698334842e-3` | `12.635x` | stable but slightly weaker |
| residual outer loop from zero | `1.661623468e-3` | `12.914x` | best profile |
| projected residual GMRES + final coarse | `1.708423696e-3` | `12.561x` | positive but more expensive |

审查判断：

```text
Task018 不只是复现 Task017 one-shot；
它已经证明 low-dimensional top_bottom_y correction space 可以被反复用于 residual-corrected outer loop。
```

---

## 5. residual_outer_zero 审查

`residual_outer_zero` 从零初值开始，交替执行：

```text
1. bounded FE-AMS segment；
2. compute true residual r = b - A x；
3. solve min_alpha ||r - A Z alpha||；
4. update x <- x + omega Z alpha。
```

本轮使用：

```text
segment_max_it = 120
cycles_requested = 4
cycles_completed = 3
omega = 1.0 selected adaptively
status = stopped_stagnated
```

cycle residual：

| cycle | residual after correction | 判断 |
|---:|---:|---|
| 1 | `1.706562101e-3` | large drop from baseline scale |
| 2 | `1.662500845e-3` | small improvement |
| 3 | `1.661623468e-3` | stagnated, stopped reasonably |

审查判断：

```text
1. process is stable: no rebound;
2. process is solver-like: not a single offline one-shot;
3. current correction space removes the dominant slow component but leaves a remaining residual floor near 1.6e-3;
4. p=1 strong gate is passed, but production-like convergence is not achieved.
```

---

## 6. selected FE RHS solve 审查

Task018 试了多种 selected FE RHS solver，用于构造：

```text
A_FE q_j = -C_j
Z_j = [q_j; e_j]
```

结果如下：

| selected FE RHS solver | FE RHS max residual | one-shot residual | improvement | 审查判断 |
|---|---:|---:|---:|---|
| SciPy GMRES diag rtol `1e-2` | `5.913e-3` | `1.732e-3` | `12.387x` | best and cheap |
| SciPy GMRES diag rtol `1e-4` | `9.980e-5` | `2.506e-3` | `8.561x` | more accurate but worse |
| SciPy GMRES diag rtol `1e-6` | `9.994e-7` | `2.476e-3` | `8.665x` | more accurate but worse |
| SciPy LGMRES diag rtol `1e-4` | `9.988e-5` | `2.429e-3` | `8.836x` | positive but weaker |
| SciPy GCROTmk diag rtol `1e-4` | `9.995e-5` | `2.468e-3` | `8.696x` | positive but weaker |
| SciPy BiCGStab diag rtol `1e-4` | `4.970e-3` | `4.291e-3` | `5.001x` | positive but not primary |
| top_bottom_xy rtol `1e-4` | `9.980e-5` | `2.506e-3` | `8.561x` | symmetry expansion not helpful |

审查判断：

```text
The best correction basis is not the most accurate FE solve.
```

更准确地说，本轮最佳 basis 应理解为：

```text
Z_filtered = [ -A_FE_filtered^{-1} C_J ; I_J ]
```

而不是单纯追求 exact：

```text
Z_exact = [ -A_FE^{-1} C_J ; I_J ]
```

这很重要。后续不应盲目把 selected FE RHS tolerance 收紧作为主路线；p=2 h=5 首轮应继续使用 `SciPy GMRES diag rtol=1e-2` 作为最强 filtered response。

---

## 7. initial correction 审查

Task018 测试：

```text
x_init = x0 + omega Z alpha
```

并从 `x_init` 继续 FE-AMS KSP 200 步。

结果：

| omega | initial residual | continuation residual | 判断 |
|---:|---:|---:|---|
| `1.0` | `1.732413109e-3` | `1.680968603e-3` | strong positive |
| `0.5` | `1.083378090e-2` | `1.082267371e-2` | weak |
| `0.3` | `1.507201314e-2` | `1.506910300e-2` | weak |
| `0.1` | `1.932766433e-2` | `1.932740943e-2` | weak |

审查判断：

```text
omega=1.0 是正确强度；correction 没有过冲；继续 FE-AMS 只能小幅改善，不会自动达到 1e-6。
```

这说明 initial correction 是可用的，但真正 leading profile 仍是 residual outer loop。

---

## 8. projected / augmented GMRES 审查

Task018 的 projected residual GMRES prototype 使用了：

```text
P = I - AZ (AZ^T AZ)^{-1} AZ^T
```

结果：

```text
final residual = 1.708423696e-3
improvement    = 12.561x
```

审查判断：

```text
augmentation/projection direction is viable;
but current projected GMRES prototype is slower and slightly worse than residual_outer_zero;
therefore it should not be the leading Task019 profile.
```

可以保留为研究对照，但不建议 task019 首轮主攻。

---

## 9. 风险 2：SciPy selected FE RHS 不是并行 production 路径

本轮最佳结果依赖：

```text
SciPy GMRES + diagonal preconditioner, rtol=1e-2
```

它的作用是构造 selected FE response：

```text
A_FE q_j = -C_j
```

但当前实现是在研究 runner 中使用导出的矩阵和 SciPy 稀疏求解器完成，性质是：

```text
single-process / exported-matrix / research path
```

它不是：

```text
MPI-distributed PETSc production path
```

风险解释：

```text
数学方向可以并行化；
当前实现不能直接作为并行 production solver。
```

工程化必须解决：

```text
1. selected FE RHS solve 的 MPI distributed implementation；或
2. isolated-process selected FE response service；或
3. 离线/缓存式 selected response 构造；或
4. production path 中可重复、可控的 PETSc selected RHS solve。
```

在这些问题解决前，不应把 Task018 runner 接到 ordinary Stage4 R/T/A production path。

---

## 10. 风险 3：PETSc selected FE-AMS 同进程生命周期风险

Task018 重新尝试了：

```text
PETSc selected FE-AMS opt-in path
```

它在同一 Python/PETSc 进程中构造 selected FE RHS solve：

```text
KSP + hypre AMS for A_FE q_j = -C_j
```

结果：

```text
KSPSetUp/PCSetUp error 101
possible invalid communicator behavior
can poison later AMS communicator setup
```

风险解释：

```text
这不是 selected Schur 数学路线失败；
而是 PETSc/hypre AMS/KSP 生命周期和 communicator 管理问题。
```

工程化必须注意：

```text
1. 避免在同一进程中 late/repeated setup/destroy 多个 hypre AMS helper；
2. 若使用 PETSc selected FE-AMS，需要 early setup and reuse；
3. 更稳妥方案是 isolated process / subprocess service；
4. 若未来接入 MPI production，需要重新设计 selected FE response solve 的 communicator ownership、PC lifetime、destroy order；
5. 不要在 ordinary Stage4 solve 中默认启用当前 opt-in PETSc selected FE-AMS path。
```

当前稳定 runner 禁用该路径是正确的。

---

## 11. 迭代次数审查

本轮不是所有阶段都用同一个迭代次数。

主要设置：

```text
baseline FE-AMS + aux identity: max_it = 1000, restart = 200
selected FE RHS: fe-max-it = 500, fe-restart = 120
initial correction continuation: max_it = 200
residual outer loop segment: max_it = 120
projected GMRES prototype: max_it = 60
```

审查判断：

```text
baseline already ran 1000 iterations and stagnated near 2.1459e-2;
therefore simply increasing FE-AMS baseline iterations is not the reason for the Task018 improvement.
```

但后续可以做两个 long-iteration sanity：

```text
1. p=1 best residual_outer_zero result -> FE-AMS continuation 1000 steps；
2. p=2 h=5, if cycle-1 correction is positive -> compare segment_max_it 120/500/1000。
```

如果 long segment 只带来小幅下降，就说明 remaining floor 不是靠更多 FE-AMS 迭代能解决，而需要扩大/改造 correction space 或转向更强物理预条件器。

---

## 12. Gate 决策

| gate | decision | reason |
|---|---|---|
| Task017 one-shot reproduction | pass | `top_bottom_y` one-shot `1.732e-3`，比 Task017 更强 |
| minimum useful solver-like | pass | best residual `1.662e-3`，improvement `12.914x` |
| strong gate | pass | residual <= `2e-3` 且 improvement >= `10x` |
| production-like `1e-6` | fail | best residual only `1.662e-3` |
| p=2 h=5 escalation | allow next task | p=1 strong stable gate passed |
| full p=2 h=2 | closed | p=2 h=5 not yet validated |
| h=1.5 | closed | far beyond current gate |
| production solver merge | no | SciPy selected FE RHS and PETSc lifecycle risks unresolved |
| research runner merge | yes | opt-in, does not change default solver behavior |

---

## 13. Merge recommendation 审查

建议：

```text
merge_code: yes, research runner only
merge_docs: yes
production_default_change: no
```

允许合并的代码范围仅限：

```text
src/studies/run_stage4_true_fe_sampled_schur_krylov.py
```

禁止：

```text
把 Task018 profile 接入 ordinary Stage4 production solver；
默认启用 SciPy selected FE RHS；
默认启用 PETSc selected FE-AMS opt-in path；
输出未收敛 R/T/A。
```

---

## 14. 下一步建议：Task019

Task019 应开启：

```text
p=2 h=5 qualification for residual-corrected true-FE sampled Schur
```

推荐最小 adaptive sequence：

```text
A. p=2 h=5 complex export / matrix and memory preflight；
B. p=2 h=5 baseline FE-AMS + aux identity, max_it=1000；
C. top_bottom_y SciPy GMRES diag rtol=1e-2 one-shot；
D. residual_outer_zero, segment_max_it=120, cycles=1 first；
E. if cycle-1 positive, continue cycles 2/3/4；
F. if still positive, compare segment_max_it=500/1000；
G. only if p=2 h=5 strong positive, discuss productionization and p=2 h=2 preflight。
```

Task019 不应首轮做：

```text
full p=2 h=2
h=1.5
full 708-mode Schur
Petrov W expansion
right additive PC with true-FE basis
PETSc selected FE-AMS same-process RHS solve
```

---

## 15. 最终审查结论

Task018 审查通过。它把 Task017 的 one-shot 正信号转化为稳定、可重复的 AMS/HX + true-FE sampled Schur residual-correction 流程，并在 default100 p=1 h=5 上通过 strong gate。当前不应暂停 AMS/HX + modal sampled Schur 主线；下一步应进行 p=2 h=5 gated qualification，同时明确工程化风险：SciPy selected FE RHS 不是并行 production 路径，PETSc selected FE-AMS 同进程 setup/lifecycle 仍需重新设计。
