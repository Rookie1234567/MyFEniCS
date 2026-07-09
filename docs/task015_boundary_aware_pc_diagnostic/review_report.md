# REVIEW REPORT 20260708：Task015 reduced Stage 4 DtN/Floquet boundary-aware PC diagnostic

## 1. 审查对象

审查分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task015_boundary_aware_pc_diagnostic/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/boundary_residual_decomposition.csv
outcomes/aux_modal_residual_decomposition.csv
outcomes/dtn_aux_block_diagnostic.csv
outcomes/dtn_schur_diagnostic.csv
outcomes/rayleigh_floquet_modal_diagnostic.csv
outcomes/fe_proxy_upper_bound_diagnostic.csv
outcomes/boundary_ablation_summary.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
src/studies/run_stage4_boundary_pc_diagnostic.py
src/studies/run_stage4_real_split_block_pc.py
```

本轮是 boundary-aware diagnostic，不是 production solver 验证。

---

## 2. 总体结论

Task015 通过，且比 Task014a 更进一步：它没有得到可用 solver，但成功把停滞原因定位到一个非常具体的低维方向。

最终判断：

```text
Task014a 的停滞最可能来自 top zero-order Rayleigh/Floquet mode 与 FE trace/volume 的 coupled Schur slow direction。
```

更具体地说，当前主 residual 在 FE-AMS 之后几乎全部集中在：

```text
port = top
order = (m,n) = (0,0)
polarization = y
```

因此下一步不应继续 broad profile sweep、不应继续 aux-only correction、不应做 full 708-mode Schur，而应专攻：

```text
dominant zero-order mode 的 FE+aux lifted coarse correction / residual-dominant low-rank sampled Schur。
```

---

## 3. Baseline 复现审查

Task015 复现了 Task014a default100 p=1 h=5 baseline：

| profile | iterations | true residual | 判断 |
|---|---:|---:|---|
| Jacobi | 1000 | 3.436e-2 | 复现 Task014a baseline |
| FE-AMS + aux identity | 1000 | 2.147e-2 | 复现 Task014a baseline，改善约 1.60x |
| zero-order local Robin + Jacobi | 1000 | 4.397e-1 | 明显更差 |
| zero-order local Robin + FE-AMS | 1000 | 5.337e-1 | 更差 |

结论：baseline 可信，后续比较口径一致。

---

## 4. Residual decomposition 审查

残差分解是本轮最重要结果。

| profile | true residual | FE fraction | aux fraction | dominant |
|---|---:|---:|---:|---|
| Jacobi | 3.436e-2 | 0.888 | 0.459 | FE |
| FE-AMS + aux identity | 2.147e-2 | 0.043 | 0.999 | aux |
| Schur_diag | 4.427e-1 | 0.997 | 0.074 | FE |

解释：

```text
Jacobi 时 residual 主要在 FE block；
FE-AMS 后 FE residual 被显著压低；
剩余 residual 几乎全部进入 auxiliary modal equation；
因此继续单独强化 FE-only AMS 不是第一优先级。
```

这说明 Task014a 的停滞不再是“FE 主体完全没预条件好”，而是 FE 场和某个 DtN/Rayleigh 模态之间的 coupled correction 没有被处理。

---

## 5. Auxiliary block diagnostic 审查

Task015 测试了：

```text
FE-AMS + aux identity
FE-AMS + aux exact
FE-AMS + aux diag
```

结果完全相同：

| profile | true residual | improvement vs identity | 判断 |
|---|---:|---:|---|
| aux identity | 2.146555954e-2 | 1.00x | baseline |
| aux exact | 2.146555954e-2 | 1.00x | 无改善 |
| aux diag | 2.146555954e-2 | 1.00x | 无改善 |

结论：

```text
A_aux diagonal/identity-like block 本身不是瓶颈。
```

这也解释了为什么只对 auxiliary coordinates 做 exact correction 不会有效：真正的慢方向不是 `a` 自己难解，而是 `a` 与 FE trace/volume 的耦合没有被预条件器联合修正。

---

## 6. Schur diagnostic 审查

Task015 尝试了：

```text
S_aux ≈ A_aux - D diag(A_FE)^(-1) C
```

结果明显变差：

| profile | true residual | improvement vs aux identity | 判断 |
|---|---:|---:|---|
| FE-AMS + Schur_diag | 4.427e-1 | 0.048x | 明显变差 |

结论：

```text
diag(A_FE)^(-1) 不是可用的 FE response approximation；
full Schur_diag 方向应停止；
如果继续 Schur，只应做 residual-dominant low-rank sampled Schur，并使用更合理的 FE lift / P_FE apply。
```

本结果不是否定 Schur 思想，而是否定“用 FE diagonal inverse 构造全量 Schur”的粗糙做法。

---

## 7. Rayleigh/Floquet modal diagnostic 审查

Aux modal decomposition 显示，在 FE-AMS + aux identity 后，aux residual 几乎全部集中在：

```text
top, (m,n)=(0,0), y
```

该 mode 占 aux residual 约 0.999999999。

但 Task015 的 modal correction 是 aux-space only：

| profile | modal space | dim | true residual | improvement |
|---|---|---:|---:|---:|
| modal_zero_order | aux-space only | 4 | 2.147e-2 | 1.00x |
| modal_propagating | aux-space only | 708 | 2.147e-2 | 1.00x |

解释：

```text
aux-space-only modal correction 只修改 auxiliary coordinate，不能修改对应的 FE trace / volume field；
因此它等价于继续处理 A_aux，而没有处理 coupled slow direction。
```

结论：

```text
下一步必须构造 FE+aux lifted modal correction，而不是 aux-only modal correction。
```

---

## 8. FE proxy upper-bound 审查

Tiny10 对照：

| case | profile | iter | true residual | 判断 |
|---|---|---:|---:|---|
| tiny10 auto | same-H1 AMS + aux identity | 37 | 9.601e-7 | 小问题已可收敛 |
| tiny10 auto | exact FE + exact aux | 8 | 1.375e-15 | exact FE 更强 |

这说明 FE exact solve 比 same-H1 AMS 更强，但 tiny10 不能直接代表 default100。

结合 default100 的 residual decomposition，当前第一瓶颈仍更像 dominant aux/modal coupled direction，而不是单纯 FE local inverse。

---

## 9. Boundary ablation 审查

对照结果：

| case | profile | true residual | 解释 |
|---|---|---:|---|
| default100 auto auxiliary DtN | FE-AMS | 2.147e-2 | 物理 DtN 边界较好，但 residual 集中在 aux mode |
| default100 zero_order local Robin | FE-AMS | 5.337e-1 | local Robin 明显更差 |
| no_aux | unavailable | - | 当前 Stage 4 path 无安全 no-aux 对照 |

结论：

```text
不要把失败归因于 DtN 边界本身错误；
DtN/Rayleigh modal boundary 是必要的；
问题是 preconditioner 没有处理 DtN modal coupling。
```

---

## 10. 代码审查

新增核心代码：

```text
src/studies/run_stage4_boundary_pc_diagnostic.py
```

它完成了：

```text
1. residual decomposition；
2. aux modal decomposition；
3. aux exact / diag diagnostic；
4. Schur_diag diagnostic；
5. aux-space modal diagnostic；
6. tiny10 exact FE + exact aux upper-bound diagnostic。
```

该代码仍应被视为 research runner，不是 production solver。原因：

```text
1. 依赖 explicit matrix export 和 Python PC；
2. 使用 SciPy SuperLU 做小块诊断；
3. 尚未形成可维护的正式 PETSc PC 接口；
4. 本轮没有产生通过 gate 的 solver。
```

---

## 11. 合并建议

建议：

```text
merge_code: no
merge_docs_only: optional
```

理由：

```text
1. Task15 是成功的诊断任务，但不是成功的 solver 任务；
2. 代码仍是 research runner；
3. default100 p=1 h=5 没有 profile 达到 10x 改善或 1e-6；
4. p=2 h=5 和 full p=2 h=2 gate 仍关闭。
```

可以保留在研究分支：

```text
src/studies/run_stage4_boundary_pc_diagnostic.py
src/studies/run_stage4_real_split_block_pc.py
src/constraints/floquet_3d.py
```

若 Task016 的 lifted coarse correction 成功，再考虑抽取最小、干净、可维护的 PC 构造接口进入 production solver。

---

## 12. 下一步建议

建议下一任务：

```text
Task016：dominant zero-order FE+aux lifted coarse correction / low-rank sampled Schur
```

具体目标：

```text
只从 dominant mode 开始：top,(0,0),y；
构造包含 FE trace/volume lift 和对应 aux coordinate 的 coarse basis Z；
用 Z^T A Z 或 complex counterpart 做低维 exact coarse correction；
在 default100 p=1 h=5 上比较 true residual；
若有效，再扩展到 top/bottom zero-order x/y 共 4 个 modes。
```

不要一上来做：

```text
full 708-mode Schur；
all propagating mode volume deflation；
p=2 h=5；
full p=2 h=2；
未收敛 R/T/A。
```

---

## 13. Task16 必须包含的执行原则

Task16 遇到问题时不能简单停止。必须按问题类型进行定位和替代尝试：

```text
1. 若 coarse matrix 病态：先规范化 Z、缩小 mode set、加轻微 regularization、检查 sign convention。
2. 若 correction 变差：尝试 sign flip、real/imag pair、top/bottom partner、post-correction 与 PC-in-KSP 两种模式。
3. 若 FE lift 构造困难：先用 algebraic lift q=-P_FE^{-1}C_j，再在 tiny10 上用 exact FE lift 验证。
4. 若 aux mode mapping 可疑：先核对 mode_id、port、m/n、polarization 与 residual decomposition。
5. 若 default100 太复杂：退回 tiny10 证明 lifted coarse correction 机制，再回 default100。
```

只有在这些排错步骤之后仍无改善，才允许给出停止结论。

---

## 14. 最终结论

```text
Task015 通过；
它没有产生可用 solver，但成功定位主瓶颈；
当前停滞最可能来自 top zero-order Rayleigh/Floquet mode 的 FE/aux coupled slow direction；
下一步应专攻 dominant zero-order FE+aux lifted coarse correction / low-rank sampled Schur；
代码不建议合并 production，文档可选合并。
```
