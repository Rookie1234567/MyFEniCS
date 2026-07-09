# REVIEW REPORT 20260708：Task017 Petrov / adjoint-aware coarse correction and true-FE sampled lift

## 1. 审查对象

审查分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task017_petrov_adjoint_coarse_correction/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/baseline_and_mode_verification.csv
outcomes/petrov_one_shot_diagnostic.csv
outcomes/true_fe_sampled_lift_diagnostic.csv
outcomes/petrov_ksp_summary.csv
outcomes/residual_history_summary.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
src/studies/run_stage4_petrov_adjoint_coarse_correction.py
src/studies/run_stage4_lifted_coarse_correction.py
src/studies/run_stage4_boundary_pc_diagnostic.py
```

本报告审查 Task017 的 Petrov / adjoint-aware coarse correction 与 true-FE sampled lift qualification。不把本轮研究 runner 当作 production solver。

---

## 2. 总体结论

Task017 通过审查，但结论不是 production 成功，而是一个明确的分叉判断：

```text
Petrov / adjoint-aware W 路线没有挽救 Task016；
selected-mode true-FE sampled lift 给出了 real-split AMS/HX 主线的第一个可继续正信号；
当前 KSP 集成方式失败，p=2 gate 继续关闭。
```

因此：

```text
merge_code: no
merge_docs_only: optional
allow_p2_h5: no
continue_ams_hx_line: yes, but only through true-FE sampled Schur / selected FE response integration
```

Task017 的价值在于把 Task016 失败原因进一步收窄：问题不主要是缺一个简单 Petrov left/test space，而是 `P_FE^{-1} C_j` 的 positive same-H1 AMS proxy 太偏离真正 indefinite Maxwell `A_FE^{-1} C_j`。

---

## 3. 关键数值审查

Task017 baseline：

```text
case = task014a_default100_stage4_block_grating_p1_h5
profile = FE-AMS + aux identity
true residual = 2.1465559540488233e-2
```

mode mapping 复现：

```text
top,(0,0),y    -> mode_id 177
bottom,(0,0),y -> mode_id 531
```

关键结果：

| 路线 | residual | improvement | 审查判断 |
|---|---:|---:|---|
| best Petrov / W_AZ / minres | `2.146459669e-2` | `1.000045x` | 无 meaningful improvement |
| best adjoint W | `>=2.146892848e-2` | `<=0.999843x` | 变差或无效 |
| true-FE sampled lift, top_y | `1.575120238e-2` | `1.363x` | 弱正信号，不够 |
| true-FE sampled lift, top_bottom_y | `3.688783940e-3` | `5.819x` | 通过 minimum useful gate |
| true-FE lift right-PC KSP | `2.354987702e-2` | `0.911x` | 集成失败，差于 baseline |

审查结论：Task017 达到了 task.md 要求的最低发现目标，因为 true-FE sampled lift one-shot 达到 `residual < 1e-2` 与 `improvement >= 2x`。但它没有达到 strong gate，也没有形成可用 KSP solver。

---

## 4. 对 Petrov / adjoint W 的审查

Task017 测试了以下 left/test space：

```text
W_aux_residual
W_residual_projected
W_AZ
W_AZ_normalized
W_adjoint_diag
W_adjoint_diag_sign_flip
W_adjoint_pfe
W_adjoint_pfe_sign_flip
```

这些测试覆盖了 task.md 要求的主要 Petrov ladder：selected auxiliary coordinate、residual-phased coordinate、least-squares `W=AZ`、diag adjoint、PFE adjoint、sign flip 与多 omega。

审查判断：

```text
Petrov W 路线应暂停。
```

理由：

1. `W_AZ` 与 `W_AZ_normalized` 的最好结果只等同于 Task016 的 minres 小幅改善。
2. adjoint_diag / adjoint_pfe 没有改善，部分明显变差。
3. W choices 没有触及 true-FE sampled lift 的 `5.819x` 信号。
4. 继续扩大 W 类型很可能是在已经排除的 right/PFE lift 空间上做局部微调，收益低。

---

## 5. 对 true-FE sampled lift 的审查

Task017 的最重要正结果是：

```text
top+bottom,(0,0),y selected-mode FE response
one-shot residual = 3.688783940e-3
improvement = 5.819x
```

这说明 Task015/016 识别的 zero-order modal slow direction 不是误判；真正失效的是 Task016 的 lift 近似。

需要注意的审查限定：

1. default100 的有效 one-shot 结果来自 `SciPy GMRES + FE diagonal` fallback，而不是 PETSc selected FE AMS 成功路径。
2. FE RHS solve residual 约 `9.65e-3`，因此它是 approximate true-FE response，不是 exact Schur sample。
3. PETSc selected FE AMS 在 `PCSetUp()` 阶段失败，下一轮需要专门处理或绕开。
4. default100 direct FE factorization 被 guard out 是合理的，符合 task 边界和内存安全原则。

审查判断：

```text
true-FE sampled lift 是 Task018 唯一值得继续追的正信号。
```

下一步不应停在“可以尝试”的报告句式，而应直接围绕该正信号继续做集成实验，直到它在 KSP / residual-correction / augmentation 形式中成功或被明确排除。

---

## 6. 对 Stage D KSP 失败的审查

Task017 把 best true-FE basis 直接塞进 right-preconditioned FGMRES additive PC 后，结果变差：

```text
baseline residual      = 2.146555954e-2
Stage D KSP residual   = 2.354987702e-2
improvement            = 0.911x
```

审查判断：

```text
Stage D 失败不能否定 one-shot 正信号；它说明当前 right additive PC 形式不一致。
```

原因是 Task017 的 one-shot correction 是针对 baseline 解后的具体 residual 做 `x <- x + Z alpha`；而 right PC apply 需要对任意 Krylov input 近似 `A^{-1}`。这两者不是同一个对象。把 one-shot basis 直接作为 right additive PC 使用，失败是可以理解的。

因此下一轮应优先测试：

```text
1. initial correction：用 one-shot 修正 x0 后再继续 KSP；
2. residual-corrected outer loop：对当前 residual 重复 selected-mode correction；
3. augmented/recycled GMRES：把 Z_true_fe 作为 augmentation space；
4. left/residual-projected form：把 correction 作用在 residual 方程，而不是当普通 right PC；
5. 更准确的 selected FE RHS solve：更严格 GMRES、shifted FE solve、guarded 1-2 RHS direct/BLR。
```

---

## 7. 任务执行方式审查

Task017 产生了有价值结果，但后续任务不能再采用“列一批方法，全跑完后写报告说都不行，或者说某方向可能行”的低效率模式。

从 Task018 开始应采用 adaptive execution rule：

```text
发现无效方向 -> 记录最小证据后停止该子方向；
发现正信号 -> 立即沿该方向继续加深；
只要还在 AMS/HX + true-FE sampled Schur 主线内且未触发资源/正确性边界，就不要停在“建议可以试试”；
必须把可行方向继续跑到成功、失败或明确资源不可承受。
```

这条规则应写入 Task018 的硬要求。

---

## 8. Gate 决策

| gate | decision | reason |
|---|---|---|
| baseline/mode reproduction | pass | Task015/016 mapping 复现 |
| Petrov W gate | fail | best improvement only `1.000045x` |
| true-FE sampled lift minimum gate | pass | top_bottom_y one-shot `5.819x` |
| strong gate | fail | 未到 `2e-3` 或 `10x` |
| KSP consistency gate | fail | right-PC residual `2.355e-2`，差于 baseline |
| reduced p=2 h=5 | closed | KSP 未稳定，strong gate 未过 |
| full p=2 h=2 | closed | p1 reduced solver 未解决 |
| production merge | no | 研究 runner，且 solver gate 未过 |
| docs-only merge | optional | 结果和排除结论有价值 |

---

## 9. 必须进入 Task018 的结论

Task018 不应继续 Petrov W 扫描，也不应继续 Task016 的 right-only `pfe_lift/diag_lift` 微调。

Task018 应围绕这一句继续：

```text
true-FE sampled lift top_bottom_y one-shot 已经证明 selected-mode FE response 能显著降低 default100 residual；下一步任务是把这个 one-shot correction 转化为稳定的 Krylov / residual-correction / augmentation 过程。
```

如果 Task018 证明这个正信号无法稳定集成，且更准确 FE RHS solve、initial correction、residual-corrected loop、augmented GMRES 都不能保留 2x 以上改善，则可以判定当前 AMS/HX + modal sampled Schur 路线已经被充分排除，转向 layered-background / RCWA-like approximate inverse、sweeping 或 two-level DDM。

---

## 10. 最终审查结论

Task017 审查通过；它排除了 Petrov / adjoint W 作为修复 Task016 的主方向，但保留并强化了 true-FE sampled Schur / selected FE response 作为 Task018 的唯一主线。当前不合并 production code，不进入 p=2；立即开启 Task018，自适应追踪 true-FE sampled lift 的 KSP 集成，直到该方向成功或被明确排除。
