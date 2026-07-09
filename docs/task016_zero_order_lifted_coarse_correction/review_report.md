# REVIEW REPORT 20260708：Task016 dominant zero-order FE+aux lifted coarse correction

## 1. 审查对象

审查分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task016_zero_order_lifted_coarse_correction/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/selected_mode_mapping.csv
outcomes/lifted_coarse_vector_diagnostic.csv
outcomes/one_shot_coarse_correction.csv
outcomes/lifted_coarse_ksp_summary.csv
outcomes/sampled_schur_diagnostic.csv
outcomes/residual_history_summary.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
src/studies/run_stage4_lifted_coarse_correction.py
```

本报告审查 Task016 的 zero-order lifted coarse correction qualification，不把本轮研究 runner 当作 production solver。

---

## 2. 总体结论

Task016 通过，但结论是负结果：

```text
Dominant zero-order FE+aux right-only lifted coarse correction 不能显著降低 default100 p=1 h=5 的 true residual。
```

Task016 的价值在于排除了一个非常具体的假设：

```text
Task015 定位到 top,(0,0),y aux residual 后，
只构造右粗空间 Z=[-P_FE^{-1}C_j; e_j] 并不能形成有效预条件器。
```

本轮没有产生可用 solver；不允许进入 reduced p=2 h=5，更不允许 full p=2 h=2。

---

## 3. 关键数值结果

Task016 的 baseline 是：

```text
FE-AMS + aux identity true residual = 2.1465559540488233e-2
```

最好的 one-shot correction：

```text
residual_after = 2.146459669e-2
improvement = 1.000045x
```

最好的 KSP lifted profile：

```text
residual_after = 2.146563635e-2
improvement = 0.999996x
```

因此本轮不满足任何成功门槛：

```text
residual <= 2e-3: no
improvement >= 10x: no
residual <= 1e-6: no
```

---

## 4. Mode mapping 审查

Task016 的 selected mode mapping 与 Task015 一致。

关键 mode：

```text
top,(m,n)=(0,0),y -> mode_id 177
bottom,(m,n)=(0,0),y -> mode_id 531
```

还测试了 top/bottom zero-order x/y 共 4 个 mode 的组合。

审查判断：

```text
失败不是因为 dominant mode 选错。
```

---

## 5. Lifted vector 审查

Task016 构造并检查了：

```text
aux_only
diag_lift
pfe_lift
pfe_lift_balanced
sign flip / aux sign flip
top_y / top_bottom_y / top_bottom_xy
```

关键发现：

```text
1. lifted vector 的 FE component 非零；
2. coarse matrix condition 约 1 到 1.05，不病态；
3. balanced FE/aux scaling 也无改善；
4. sign flip 和 aux sign flip 均无改善。
```

因此失败不能简单归因于：

```text
Z 退化为 aux-only；
coarse matrix 病态；
FE/aux 尺度不平衡；
符号选错；
top/bottom 或 x/y mode set 太小。
```

---

## 6. One-shot correction 审查

Task016 做了 Galerkin 与 minres 两类 one-shot correction：

```text
x1 = x0 + Z alpha
alpha = (Z^T A Z)^(-1) Z^T r0
```

以及最小残差式：

```text
min ||r0 - A Z alpha||
```

结果：

```text
best default100 one-shot improvement ≈ 1.000045x
```

审查判断：

```text
one-shot 已经说明当前 Z space 与停滞 residual 的可修正方向几乎不重合。
```

这意味着即使把同样的 Z 放入 KSP PC，也不应期待明显改善。

---

## 7. KSP lifted PC 审查

Task016 测试了：

```text
additive coarse correction
residual-corrected coarse correction
minres_additive
omega = 1.0 / 0.1 / 0.01 damping
gmres outer KSP
```

未阻尼的 coarse PC 部分 profile 会触发 PETSc FPE；阻尼后可以稳定运行，但 residual 不改善。

审查判断：

```text
稳定化后仍无效，说明失败不是单纯 PETSc FPE 或数值崩溃导致。
```

---

## 8. Sampled Schur 审查

Task016 没有构造 full 708-mode Schur，而是只对 selected modes 做 sampled Schur / lifted correction。

结果：

```text
top_y / top_bottom_y / top_bottom_xy 的 improvement 均约 1.000038x
```

审查判断：

```text
用当前 P_FE^{-1}C_j 构造 selected-mode Schur 仍不能解释 slow direction。
```

这说明问题不是 full Schur 规模不够，而是当前 FE lift / right coarse space 不对。

---

## 9. 对 Task015 理解的修正

Task015 的 residual 定位仍然有效：residual 的确集中在 top,(0,0),y auxiliary mode。

但 Task016 说明：

```text
aux residual 集中在某个 mode，并不等价于 solution error 可以用对应的 right lifted vector Z 修正。
```

原因可能是：

```text
1. Stage 4 real-split system 非正规 / 非 Hermitian；
2. 需要 left/test space W，而不是只有 right space Z；
3. P_FE^{-1}C_j 使用 positive same-H1 AMS lift，可能太偏离真正 indefinite A_FE^{-1}C_j；
4. residual-dominant equation 与 correction direction 之间存在 Petrov / adjoint mismatch。
```

---

## 10. 合并建议

建议：

```text
merge_code: no
merge_docs_only: optional
```

原因：

```text
1. 没有产生可用 solver；
2. default100 p=1 h=5 没有 10x 改善或 1e-6；
3. lifted coarse PC 仍是研究 runner；
4. undamped KSP 部分 profile 有 PETSc FPE 风险；
5. p=2 gate 仍关闭。
```

可保留在研究分支：

```text
src/studies/run_stage4_lifted_coarse_correction.py
docs/task016_zero_order_lifted_coarse_correction/outcomes/
```

---

## 11. 下一步建议

建议最多再做一个小而明确的 Task017：

```text
Task017：Petrov / adjoint-aware zero-order coarse correction and true-FE sampled Schur qualification
```

Task017 只回答两个问题：

```text
1. 引入 left/test space W 后，dominant zero-order coarse correction 是否有效？
2. 用更准确的 selected-mode FE solve 近似 A_FE^{-1}C_j 后，是否有效？
```

限制：

```text
只跑 default100 p=1 h=5；
只处理 top,(0,0),y 和 top/bottom y；
不跑 p=2；
不跑 full p=2 h=2；
不输出未收敛 R/T/A。
```

如果 Task017 仍不能把 residual 降到 `1e-2` 以下，或没有至少 2x 改善，则建议暂停 real-split AMS + modal coarse 主线，转向更全局的波传播预条件器，例如 layered-background / RCWA-like approximate inverse、sweeping 或 domain-decomposition。

---

## 12. 最终结论

```text
Task016 通过；
它排除了 current right-only lifted coarse correction；
没有可用 solver；
不建议合并 production code；
下一步若继续，应只做小范围 Petrov/adjoint-aware coarse correction 与 true-FE sampled Schur qualification；
若 Task017 仍失败，应准备暂停 real-split AMS 主线。
```
