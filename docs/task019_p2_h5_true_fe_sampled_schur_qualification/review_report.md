# REVIEW REPORT 20260709：Task019 p=2 h=5 true-FE sampled Schur qualification

## 1. 审查对象

审查分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task019_p2_h5_true_fe_sampled_schur_qualification/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/p2_h5_export_preflight.csv
outcomes/p2_h5_baseline_summary.csv
outcomes/p2_h5_selected_fe_rhs_solve.csv
outcomes/p2_h5_one_shot_summary.csv
outcomes/p2_h5_long_segment_summary.csv
outcomes/p2_h5_mode_set_escalation.csv
outcomes/p2_h5_adaptive_experiment_log.csv
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
notes/theory/maxwell_iterative_preconditioners_task012.md
```

本报告审查 Task019 是否成功把 Task018 的 `p=1 h=5` residual-corrected true-FE sampled Schur process 扩展到 `p=2 h=5`。

---

## 2. 总体结论

Task019 审查通过，但结论是否定当前主线：

```text
p=2 h=5 上，top_bottom_y low-dimensional true-FE sampled Schur 不再是有效主路线。
```

关键判断：

```text
export and real split equivalence: pass
p=2 h=5 baseline availability: partial pass
required top_bottom_y one-shot minimum gate: fail
best creative low-dimensional variant: weak positive only
strong gate: fail
production-like gate: fail
p=2 h=2 preflight: closed
```

因此：

```text
continue top_bottom_y sampled-Schur as p=2 mainline: no
merge failed research solver code into production: no
keep docs/outcomes/review as research evidence: yes
next route: impedance DDM / sweeping / two-level Schwarz / matrix-free support
```

---

## 3. p=2 h=5 export / real split 审查

Task019 的 p=2 matrix export 和 real split equivalence 是可靠的。

| item | value |
|---|---:|
| complex dofs | `301648` |
| real dofs | `603296` |
| FE complex dofs | `300940` |
| aux complex dofs | `708` |
| complex nnz | `35633876` |
| real nnz estimate | `142535504` |
| relative matvec error | `2.293628988e-16` |
| relative rhs error | `0.0` |
| export RSS | `3.356 GB` |

审查判断：

```text
失败不是 real-split 等价性错误，也不是 export/mode count 错误。
```

---

## 4. baseline 审查

Task019 没有得到完整 1000-step single-run baseline：

```text
1000-step single-process attempt: timeout after 7200s
observed RSS: about 12.78 / 13.65 GiB
```

可恢复 baseline 使用 120-step FE-AMS + aux identity：

```text
iterations = 120
true residual = 1.638606e-2
solve_time_s = 1420.8 s
rss_gb = 12.964
```

继续到约 240 steps：

```text
residual = 1.581607e-2
improvement vs iter120 = 1.036x
```

审查判断：

```text
1. p=2 assembled real path 已接近 workstation memory/time 边界；
2. 仅靠继续 FE-AMS 迭代下降很慢；
3. 这支持后续 matrix-free + physics preconditioner 的工程方向。
```

---

## 5. residual structure 审查

Task019 的 residual 结构很关键。p=2 baseline residual 仍然强烈集中在 selected auxiliary components：

| block | relative to b | relative to total residual |
|---|---:|---:|
| `fe_real` | `4.547862e-03` | `0.278` |
| `aux_real` | `6.012441e-03` | `0.367` |
| `fe_imag` | `4.137961e-03` | `0.253` |
| `aux_imag` | `1.394803e-02` | `0.851` |
| `selected_top_bottom_y_aux_components` | `1.518858e-02` | `0.927` |
| `all` | `1.638606e-02` | `1.000` |

审查判断：

```text
mode mapping 没错；top_bottom_y 仍然是 residual-dominant scalar component。
```

但这次低维 correction 无法有效降低 residual，说明 p=2 的失败不是“找不到 residual 在哪里”，而是：

```text
low-dimensional FE lift / sampled Schur space 不能同时消除 selected auxiliary residual 和由 C-coupling 诱发的 FE bulk 后效应。
```

---

## 6. required top_bottom_y one-shot 审查

最佳 required `top_bottom_y` one-shot：

```text
solver_label = offline_scipy_gcrotmk_diag_rtol_0.01_maxit_16_top_bottom_y
baseline residual = 1.6386055485257574e-2
one-shot residual = 1.635705295598139e-2
improvement = 1.0017730901375834x
minimum_signal = fail
strong_signal = fail
```

这远低于 gate：

```text
minimum useful: residual < 1e-2 or improvement >= 2x
strong: residual <= 2e-3 or improvement >= 10x
```

selected FE RHS sweep 显示，GMRES/LGMRES/GCROTmk/BiCGStab 及不同 low-iteration budget 都无法让 required `top_bottom_y` basis 达到有用信号。

审查判断：

```text
Task018 p=1 的 filtered selected FE response 没有迁移到 p=2。
```

---

## 7. low-dimensional variants 审查

Task019 也尝试了创造性低维扩展，最强结果是：

```text
selected_fe_lift_plus_fe_residual_gcrotmk_maxit_32
residual = 1.516624e-2
improvement = 1.0804x
```

其它变体：

| variant | residual after | improvement | decision |
|---|---:|---:|---|
| `selected_fe_lift_plus_fe_residual_gcrotmk_maxit_32` | `1.516624e-02` | `1.080x` | weak positive only |
| `selected_fe_lift_plus_fe_residual_lgmres_maxit_32` | `1.516883e-02` | `1.080x` | weak positive only |
| `aux_only_plus_fe_residual_lgmres_maxit_32` | `1.519766e-02` | `1.078x` | weak positive only |
| `aux_only_top_bottom_y` | `1.638567e-02` | `1.000x` | no useful signal |

审查判断：

```text
加入 FE residual direction 有弱正反馈，说明 p=2 需要更宽的 FE/interface/global propagation correction；
但 1.08x 不足以继续把 low-dimensional sampled Schur 包装成主线。
```

---

## 8. mode-set escalation 审查

Task019 做了最小 mode-set escalation：

```text
top_y
top_bottom_xy
```

结果都不优于 primary top_bottom_y：

```text
top_y one-shot residual       = 1.6382918958e-2, improvement ≈ 1.00019x
top_bottom_xy one-shot        = 1.6382748810e-2, improvement ≈ 1.00020x
```

审查判断：

```text
简单扩大 zero-order x/y symmetry set 不解决 p=2 失败。
```

这也支持停止 full 708-mode Schur。问题不只是“mode 太少”，而是当前 correction 形式不能处理 p=2 的高阶 FE coupling / propagation。

---

## 9. 为什么 residual outer loop 没有运行

Task019 的 gate rule 是：

```text
只有 Stage C one-shot 达到 residual < 1e-2 或 improvement >= 2x，才进入 residual outer loop。
```

本轮 required one-shot 只有 `1.0018x`，最强低维扩展只有 `1.0804x`。考虑到 p=2 每个 120-step FE-AMS segment 约 20 分钟，继续 outer loop 缺少合理依据。

审查判断：

```text
不运行 residual outer loop 是正确停止，不是执行不足。
```

---

## 10. Gate 决策

| gate | decision | reason |
|---|---|---|
| p2_h5_export_real_split_equivalence | pass | matvec error `2.29e-16` |
| baseline_available | partial_pass | 120-step baseline completed；1000-step single run timed out near memory limit |
| minimum_useful_top_bottom_y_one_shot | fail | best improvement `1.0018x` |
| best_creative_low_dimensional_variant | weak_positive_only | best improvement `1.0804x` |
| residual_outer_loop_stable | not_run | one-shot gate failed |
| strong | fail | best observed residual `1.516e-2` |
| production_like | fail | no `1e-6` convergence |
| p2_h2_preflight_next | closed | p=2 h=5 gate failed |
| next_solver_route | switch_route | low-dimensional sampled Schur nontransfer |

---

## 11. Merge / branch hygiene recommendation

Task019 之后，当前 `codex/20260707-real-split-ams-hx-qualification` 分支应被视为 research evidence branch，而不是 production merge branch。

与 `master` 对比：

```text
status = ahead
behind_by = 0
ahead_by = 59
merge_base = master commit 64fc9985cee90193f2cf97460fd5c3566ac6f251
```

不合并该分支不会影响 `master` 当前 direct/BLR/official R/T/A code path。

建议 Codex 在下一轮先做 branch hygiene / selective merge audit：

```text
1. 审查过去所有相关分支和当前 research branch；
2. 把失败尝试的 research runner / prototype solver code 保留在各自分支中，不合入 master；
3. 把有长期价值的文档、review_report、outcomes summary、theory notes、bibliography、negative-result evidence 作为 docs-only 候选；
4. 仅在确认不改变 production default solver 的情况下，选择性合并文档；
5. 不合并 failed solver code、offline SciPy selected RHS production hook、PETSc selected FE-AMS same-process path、ordinary Stage4 solver 默认改动；
6. 合并前输出 merge manifest，列出 include_docs、exclude_code、reason。
```

推荐合并策略：

```text
merge_failed_code: no
merge_production_default_change: no
merge_docs: yes, selective
merge_research_runners: no by default; only if explicitly needed as opt-in and isolated
```

---

## 12. 下一步：Task020

Task020 应由 Codex 自行从合适 base 分支创建；ChatGPT 不创建分支。Task020 第一阶段必须先做 branch audit / selective docs merge plan，然后再进入新 solver search。

Task020 不应继续：

```text
top_bottom_y low-dimensional sampled Schur as p=2 mainline
Petrov W expansion
right additive PC with true-FE basis
full 708-mode Schur
p=2 h=2 preflight before p=2 h=5 success
production R/T/A integration from failed iterative solver
```

Task020 应同时覆盖四条更全局路线：

```text
Route A: impedance DDM / optimized Schwarz
Route B: layered / sweeping / moving-PML preconditioner
Route C: two-level weighted Schwarz + adaptive coarse space
Route D: matrix-free high-order FE matvec + physics preconditioner support
```

四条路线都必须至少做最小可判定 prototype；若某方向出现正信号，必须继续加深到明确成功、明确失败或资源边界，不得停在“建议后续可以试试”。

---

## 13. 最终审查结论

Task019 审查通过。它证明 p=1 成功的 residual-corrected `top_bottom_y` true-FE sampled Schur 路线不能直接扩展到 p=2 h=5。当前低维 sampled Schur 可以保留为诊断证据，但不应继续作为 p=2 生产求解器主线。下一步应先做 branch hygiene / selective docs merge audit，随后开启 Task020，系统测试 impedance DDM、sweeping、two-level adaptive Schwarz、matrix-free+physics PC 四条 wave-aware 路线。
