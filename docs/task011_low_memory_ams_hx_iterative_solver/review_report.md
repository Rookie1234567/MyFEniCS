# REVIEW REPORT 20260707：Task011 low-memory AMS/HX iterative solver prototype

## 1. 审查对象

审查分支：

```text
codex/20260707-low-memory-ams-hx-iterative-solver
```

任务目录：

```text
docs/task011_low_memory_ams_hx_iterative_solver/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/low_memory_krylov_summary.csv
outcomes/ams_hx_smoke_notes.md
outcomes/ams_hx_smoke_summary.csv
outcomes/matrix_free_matvec_feasibility.md
outcomes/solver_memory_comparison.csv
outcomes/profile_ranking.md
outcomes/next_decision.md
outcomes/changed_files.md
src/studies/run_ams_hx_smoke.py
src/studies/run_matrix_free_matvec_smoke.py
```

本报告只审查 task011 的实际完成情况，不再推进新的求解器实现。

---

## 2. 总体结论

Task011 通过，可以合并，但合并语义必须准确：

```text
Task011 没有找到新的 Stage 4 production 低内存迭代求解器；
它完成的是低内存 Krylov 负结果、real hypre AMS/HX 烟测、complex AMS 风险确认、matrix-free FE matvec 可行性验证。
```

本轮最重要结论是：

```text
1. Jacobi-Krylov 低内存路线基本可以停止；
2. real-valued FE-only hypre AMS/HX 有收敛信号，但内存前景未证明；
3. complex hypre AMS 不能直接用于当前 Stage 4 complex 系统；
4. matrix-free FE action 数值上可行，但目前只是 matvec feasibility，不是 solver；
5. 下一步不应继续盲目实现，而应先做文献调研与路线评估。
```

因此 task011 适合作为 task012 文献调研的输入，而不是作为新 production solver 的完成节点。

---

## 3. Stage A：low-memory Jacobi-Krylov baseline 审查

Task011 按任务要求测试了以下低内存 profile：

```text
iter_gmres_jacobi_restart20
iter_gmres_jacobi_restart40
iter_fgmres_jacobi_restart20
iter_lgmres_jacobi_restart20
iter_tfqmr_jacobi
iter_bicgstab_jacobi
iter_cgs_jacobi
```

测试设置为 `p=2 h=5/h=4`、`np=8`、`pc_type=jacobi`、`rtol=1e-6`、`max_it=1000`。

结果清楚：低内存成立，但收敛失败。

代表性结果：

| profile | p | h | true relative residual | RSS upper GB | 结论 |
|---|---:|---:|---:|---:|---|
| GMRES/Jacobi restart 40 | 2 | 5 | 0.2494949774 | 2.647 | 未收敛 |
| GMRES/Jacobi restart 40 | 2 | 4 | 0.2343204328 | 3.284 | 未收敛，本组最好 |
| FGMRES/Jacobi restart 20 | 2 | 4 | 0.2351484757 | 3.243 | 未收敛 |
| LGMRES/Jacobi restart 20 | 2 | 4 | 0.2471943132 | 3.258 | 未收敛 |
| TFQMR/Jacobi | 2 | 4 | 0.6682568382 | 3.276 | 未收敛 |
| BiCGStab/Jacobi | 2 | 4 | 2.1649273487 | 3.242 | 发散 |
| CGS/Jacobi | 2 | 4 | 1.4194e5 | 3.275 | 9 步硬发散 |

判断：

```text
1. Jacobi-Krylov 的内存相对 direct/BLR 明显更低；
2. 但 p=2 h=5/h=4 全部离 rtol=1e-6 太远；
3. 未收敛，因此不允许输出 official R/T/A；
4. 不建议继续加密到 h=3/h=2.5/h=2；
5. 该路线仅作为低内存失败基线保留。
```

这一结论与 task009 的 GMRES+Jacobi 诊断结果一致，并进一步确认：单纯降低 restart 或换 TFQMR/BiCGStab/CGS 不能解决该 Maxwell 系统的收敛问题。

---

## 4. Stage B/C：hypre AMS/HX smoke test 审查

本轮新增 `src/studies/run_ams_hx_smoke.py`，用于 FE-only positive Maxwell 块的 AMS/HX 烟测。

代码构造：

```text
A = curl-curl + k0^2 mass
V = N1curl degree p
Q = Lagrange degree p+1
G = dolfinx.fem.petsc.discrete_gradient(Q, V)
pc_type = hypre
pc_hypre_type = ams
```

real mode 的结果：

| mode | p | h | iterations | true relative residual | RSS upper GB | 结论 |
|---|---:|---:|---:|---:|---:|---|
| real | 1 | 10 | 3 | 1.896e-7 | 0.428 | 通过 |
| real | 1 | 5 | 4 | 4.034e-8 | 0.991 | 通过 |
| real | 2 | 5 | 7 | 4.024e-7 | 6.930 | 通过 |
| real | 2 | 4 | 未完成 | - | 12.86 | host memory pressure |

complex mode 结果：

```text
p=1 h=10 complex AMS smoke failed with malloc invalid size + PETSc signal 11.
```

审查判断：

```text
1. real-valued FE-only AMS/HX 的收敛性信号是真实且有价值的；
2. 但它不是完整 Stage 4 complex DtN augmented system；
3. p=2 h=4 已出现明显内存压力，说明 AMS/HX 内存可扩展性尚未证明；
4. direct complex hypre AMS 在当前 PETSc/hypre build 中不安全，不能直接作为 Stage 4 profile；
5. 后续不能简单写“AMS/HX 是下一步主线”，而应先通过文献调研和内存审计判断是否值得继续。
```

特别需要强调：real AMS/HX 在 `p=2 h=5` 上的 7 次收敛不能与 task008/task010 的 Stage 4 `p=2 h=2` direct/BLR 直接比较。它只是 FE-only positive Maxwell block，不含 Floquet MPC、DtN auxiliary、complex material、official R/T/A。

---

## 5. Stage D：Stage 4 blockdiag AMS 未运行的合理性

Task011 原任务中包含 Stage 4 FE/aux block diagonal AMS preconditioner 的方向。但本轮在最小 complex AMS smoke test 中已经发现 PETSc/hypre AMS 直接用于 complex path 会崩溃，因此没有继续运行 Stage 4 blockdiag AMS。

这个决策是合理的：

```text
如果最小 complex FE-only AMS 已经 signal 11，继续把它接入完整 Stage 4 只会制造不可靠结果。
```

因此 Stage D 未完成不应视为失败，而应视为基于安全边界的提前停止。但 outcomes 中必须保持清楚表述：

```text
Stage 4 blockdiag AMS 未产生 solver result；
不能声称已验证 Stage 4 AMS/HX 预条件器。
```

---

## 6. Stage E：matrix-free matvec feasibility 审查

本轮新增 `src/studies/run_matrix_free_matvec_smoke.py`，验证 FE-only Maxwell 块的 UFL action 路径。

验证方式：

```text
assembled matrix: A.mult(x, y_matrix)
matrix-free action: assemble_vector(action(a, x))
compare: ||y_matrix - y_action|| / ||y_matrix||
```

结果：

| mode | p | h | relative action error | RSS upper GB | 结论 |
|---|---:|---:|---:|---:|---|
| complex | 1 | 5 | 3.259e-16 | 0.359 | matvec 一致 |
| complex | 2 | 5 | 7.563e-16 | 0.445 | matvec 一致 |

判断：

```text
1. FE-only matrix-free action 数值验证通过；
2. 这是后续降低 assembled A 存储的有价值基础设施；
3. 它目前不处理 Floquet MPC、DtN auxiliary、real split 或 KSP/PC MatShell 集成；
4. matrix-free 不能单独解决收敛问题，必须与物理预条件器结合。
```

因此 matrix-free 应被记录为“内存优化层”，而不是当前收敛性答案。

---

## 7. 与 direct/BLR/Jacobi 的对比

本轮 `solver_memory_comparison.csv` 的比较很有帮助：

| case | mode | h | p | status | true residual | RSS upper GB | 说明 |
|---|---|---:|---:|---|---:|---:|---|
| direct LU | complex Stage 4 | 2 | 2 | completed | - | 20.53 | reference |
| MUMPS-BLR eps=1e-5 | complex Stage 4 | 2 | 2 | completed | 2.085e-8 | 17.85 | fallback |
| GMRES/Jacobi restart 40 | complex Stage 4 | 4 | 2 | failed | 0.2343 | 3.284 | 低内存但不收敛 |
| FE-only real AMS | real FE positive Maxwell | 5 | 2 | completed | 4.024e-7 | 6.930 | 不是 Stage 4 |
| FE-only real AMS | real FE positive Maxwell | 4 | 2 | stopped | - | 12.86 | 内存压力 |
| matrix-free UFL action | complex FE positive Maxwell | 5 | 2 | completed | 7.563e-16 | 0.445 | matvec 误差，不是解残差 |

这张表说明了当前状态：

```text
1. 只有 direct LU / BLR 能在 Stage 4 上给出可信 R/T/A；
2. 真正低内存的 Jacobi-Krylov 不收敛；
3. AMS/HX 有收敛潜力但目前不是完整系统，且内存风险明显；
4. matrix-free 有内存潜力但尚未解决预条件器问题。
```

---

## 8. 代码与文档质量审查

### 8.1 正面评价

```text
1. low-memory Krylov profiles 覆盖了任务书要求的主要组合；
2. 未收敛结果没有输出 official R/T/A，符合 task009-task010 安全口径；
3. AMS/HX smoke 明确区分 real 与 complex 路径；
4. matrix-free matvec 采用 assembled/action 对照，误差指标清楚；
5. summary/profile_ranking/next_decision 结论基本诚实，没有把烟测结果夸大成 production solver。
```

### 8.2 需要注意的问题

```text
1. AMS/HX smoke 中 H1 degree = p+1 是一个假设，不一定是最低内存选择；后续若继续 AMS，应先做 H1 degree / G matrix / AMG hierarchy memory audit。
2. p=2 h=4 real AMS 的停止原因是 host/Docker memory pressure，不是数学不收敛；不要把它解读成 AMS 理论失败。
3. complex AMS signal 11 是当前 build/接口层面的强风险；后续如果调研支持 real-split AMS，也必须先小矩阵验证，不可直接上 Stage 4。
4. matrix-free 目前只覆盖 FE-only positive Maxwell block，不应写成 Stage 4 matrix-free solver 已可用。
5. outcomes 中若存在空的 stage4_blockdiag_ams_summary.csv 或 raw_runs placeholder，合并前可清理或保留但必须注明为空原因。
```

---

## 9. 是否建议合并

建议合并，但必须以如下语义合并：

```text
Task011 = low-memory iterative solver feasibility and negative-result record。
```

不要以如下语义合并：

```text
找到了新的 production low-memory solver；
AMS/HX 已经适用于 Stage 4；
real-split AMS 已经验证；
matrix-free solver 已经可用。
```

合并前可做两件轻量清理：

```text
1. 删除或标注 0-line / empty placeholder outcomes；
2. README 中 task011 状态保持“无新的 production 低内存候选”。
```

---

## 10. 下一步建议

基于 task011 结果，下一步不建议继续新增求解器 profile 或硬推 real-split AMS。

更合理的下一步是已经写入的：

```text
Task012：Maxwell 周期光栅低内存迭代求解器文献调研与路线设计
```

Task012 应重点回答：

```text
1. 文献是否支持 real/imag split + real AMS？
2. AMS/HX 是否有 p-coarsening / low-order auxiliary 低内存版本？
3. 是否存在更适合周期光栅的 Rayleigh/Floquet modal coarse correction？
4. DtN auxiliary unknowns 是否能构成自然的 coarse / Schur correction？
5. FEM-RCWA 或 layered-background approximate inverse 是否比 generic AMS 更贴合本问题？
6. matrix-free 应作为主线还是后续内存优化层？
```

在文献调研完成前，不建议继续把时间投入 full Stage 4 real-split AMS 实现。

---

## 11. 最终结论

```text
task011 通过；
可以合并为低内存迭代法 feasibility / negative-result record；
没有新的 production low-memory solver；
Jacobi-Krylov 路线应停止；
real AMS/HX 只证明 FE-only 收敛信号，内存前景未证明；
complex AMS 直接路径不安全；
matrix-free FE action 可作为后续内存优化基础；
下一步应先做 task012 文献调研与路线收敛。
```
