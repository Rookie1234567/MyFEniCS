# REVIEW REPORT 20260708：Task014a reduced Stage 4 real-split FE/aux block PC integration

## 1. 审查对象

审查分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task014a_real_split_stage4_reduced_block_pc/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/stage4_real_split_equivalence.csv
outcomes/reduced_stage4_block_pc_summary.csv
outcomes/reduced_stage4_block_pc_memory.csv
outcomes/solver_profile_ranking.md
outcomes/p2_h5_reduced_stage4_decision.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
src/studies/run_stage4_real_split_block_pc.py
src/constraints/floquet_3d.py
```

本报告审查 Task014a 的 reduced Stage 4 integration qualification，不把本轮实验代码视为 production solver。

---

## 2. 总体结论

Task014a 通过，但结论是 B-/C+：

```text
Stage 4 real split 等价性通过；
MPC 后 same-H1 AMS data 可以构造；
FE/aux block split 可以建立；
但当前最小 PC = FE same-H1 AMS + aux identity 太弱；
不允许进入 reduced p=2 h=5，也不允许进入 full Stage 4 p=2 h=2。
```

这不是“real-split AMS 路线完全失败”，而是说明：

```text
Task013 的 FE-only same-H1 AMS 正信号不能直接搬到 Stage 4；
Stage 4 的慢收敛很可能来自 DtN auxiliary、Rayleigh/Floquet modal coupling、FE/aux coupling 或 FE block 不定性共同作用。
```

因此下一步不应继续黑盒 profile sweep，也不应直接 full p=2 h=2，而应做：

```text
Task015：reduced Stage 4 DtN/Floquet boundary-aware PC diagnostic
```

---

## 3. Stage A 审查：Stage 4 real split 等价性

Task014a 验证对象是 constraint 后的 reduced / assembled PETSc matrix，即 `dolfinx_mpc.assemble_matrix` 后再加入 DtN auxiliary rows 的最终 Stage 4 矩阵。这个口径正确，没有混用 constraint 前 full matrix 与显式 C transform。

关键结果：

| case | FE complex dofs | aux complex dofs | n real | nnz real | matvec error | RHS error | RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| tiny10 auto | 144 | 4 | 296 | 18,600 | 1.575e-16 | 0 | 0.262 GB |
| default100 auto | 39,270 | 708 | 79,956 | 9,390,960 | 6.805e-16 | 0 | 0.458 GB |
| default100 zero-order | 39,270 | 0 | 78,540 | 5,228,128 | 2.176e-16 | 0 | 0.378 GB |

审查判断：通过。

这说明：

```text
1. Stage 4 complex matrix 可以正确拆成 real/imag block；
2. DtN auxiliary rows 进入 real split 后没有破坏代数等价性；
3. 当前失败不是 real split 错误导致。
```

---

## 4. FE / aux block split 审查

Task014a 采用 real split 向量布局：

```text
[ real(FE, aux), imag(FE, aux) ]
```

因此切片为：

```text
FE real: 0 : n_fe
aux real: n_fe : n_complex
FE imag: n_complex : n_complex + n_fe
aux imag: n_complex + n_fe : 2*n_complex
```

这个分块口径清楚。default100 auto case 中：

```text
FE real dofs = 78540
aux real dofs = 1416
total real dofs = 79956
```

注意这里的 `aux real dofs = 1416` 对应 complex aux unknowns 708 的 real/imag 分裂。

审查判断：通过。

但当前 preconditioner 对 aux block 只做 identity，因此它没有真正处理 FE trace 与 DtN modal unknowns 之间的 Schur coupling。

---

## 5. AMS data 审查

Task014a 证明 same-H1 AMS data 可以在 reduced Stage 4 normal-incidence real PETSc mode 下构造。

关键数据：

| case | B rows | B nnz | G rows | H1 dofs | G nnz | AMS setup RSS before -> after |
|---|---:|---:|---:|---:|---:|---:|
| tiny10 auto | 144 | 4,574 | 144 | 64 | 1,800 | 0.259 -> 0.261 GB |
| default100 auto | 39,270 | 1,307,032 | 39,270 | 13,671 | 667,340 | 0.683 -> 0.718 GB |
| default100 zero-order | 39,270 | 1,307,032 | 39,270 | 13,671 | 667,340 | 0.470 -> 0.670 GB |

审查判断：通过，但有边界条件：

```text
1. 当前 real-mode MPC 只允许 pure real Floquet phase；
2. 真实 80° oblique incidence 的 complex Floquet phase 尚未进入 real-mode PC 路径；
3. 这意味着 Task014a 不是最终斜入射 production solver 验证。
```

---

## 6. Stage C 审查：reduced p=1 h=5 对比

主 case 是 default100 auto-propagating auxiliary DtN：

| case | profile | status | iter | true residual | KSP residual | RSS | 判断 |
|---|---|---|---:|---:|---:|---:|---|
| default100 auto | Jacobi | max_it | 1000 | 3.436e-2 | 3.199 | 0.683 GB | 不收敛 |
| default100 auto | FE-AMS + aux identity | max_it | 1000 | 2.147e-2 | 1.998 | 0.786 GB | 只改善约 1.60 倍，不通过 |

补充 zero-order local Robin 对照：

| case | profile | true residual | 判断 |
|---|---|---:|---|
| default100 zero-order | Jacobi | 4.397e-1 | 不收敛 |
| default100 zero-order | FE-AMS | 5.337e-1 | 更差 |

审查判断：Stage C 未通过。

原因：

```text
1. FE-AMS + aux identity 只比 Jacobi 改善约 1.60 倍；
2. 没有达到 10 倍改善门槛；
3. 没有达到 true residual <= 1e-6；
4. 1000 iterations 后仍停在 2e-2 量级；
5. p=2 h=5 gate 不具备。
```

---

## 7. 为什么不允许 p=2 h=5 和 full p=2 h=2

Task014a 的 gated execution 是正确的。

当前主 reduced p=1 h=5 case 没有通过，因此继续运行 p=2 h=5 大概率只会生成更贵的负结果。更重要的是，在 p=1 h=5 都没有证明有效前，直接 full p=2 h=2 违反前置条件。

审查判断：同意不运行 p=2 h=5 和 full p=2 h=2。

---

## 8. 对失败原因的判断

Task014a 排除了以下失败原因：

```text
real split 代数错误；
constraint 后矩阵无法 real split；
MPC 后 same-H1 AMS data 无法构造；
FE/aux block 无法切片；
AMS setup 内存不可接受。
```

Task014a 没有排除以下原因：

```text
DtN aux identity 太弱；
FE/aux Schur coupling 未处理；
Rayleigh/Floquet propagation modes 是慢收敛主因；
true oblique complex Floquet phase 尚未被 real-mode PC 支持；
positive proxy AMS 对不定 Maxwell FE block 太弱。
```

因此下一步必须是 boundary-aware diagnostic，而不是继续微调 FE-only AMS。

---

## 9. 合并建议

建议：

```text
merge_code: no
merge_docs_only: yes / optional
```

理由：

```text
1. 本轮代码是研究脚本，不是 production Stage 4 solver；
2. 主 case 没有达到通过门槛；
3. 没有 R/T/A；
4. real-mode Floquet 兼容层目前只适用于 pure real phase；
5. 合并代码可能让后续误以为 real-split Stage 4 PC 已经可用。
```

可保留在研究分支：

```text
src/studies/run_stage4_real_split_block_pc.py
src/constraints/floquet_3d.py
```

如果未来 Task015/Task016 成功，再从研究分支中抽取最小、干净、可维护的代码进入 master。

---

## 10. 下一步建议

建议下一任务改为同时诊断 DtN 和 Floquet，不再武断地分成“先 DtN 后 Floquet”。

推荐任务：

```text
Task015：reduced Stage 4 DtN/Floquet boundary-aware PC diagnostic
```

核心目标：

```text
在 default100 p=1 h=5 上判断当前停滞主要来自：
1. aux block identity 太弱；
2. FE/aux Schur coupling 未处理；
3. Rayleigh/Floquet propagation modes 未处理；
4. FE block positive AMS 本身太弱；
或以上因素耦合。
```

Task015 不应进入 full p=2 h=2，不应输出未收敛 R/T/A，也不应继续黑盒 profile sweep。

---

## 11. 最终结论

```text
Task014a 通过；
但 solver 结果未通过 Stage C；
real split 与 MPC 后 AMS data 是正结果；
FE-AMS + aux identity 太弱；
p=2 h=5 与 full p=2 h=2 不具备进入资格；
不建议合并 production code；
下一步应做 Task015：reduced Stage 4 DtN/Floquet boundary-aware PC diagnostic。
```
