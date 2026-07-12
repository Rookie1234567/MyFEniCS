# REVIEW REPORT V2：Task024 response_v1 复审

## 1. 最终状态

```text
review_status = reproducibility_pass_algorithm_fail
remote_reproducibility = pass
numerical_infrastructure = pass_research
algorithm_improvement = fail
production_solver = no
production_default_change = no
```

Codex 已有效回应 `review_report_v1.md`：完整 runner、独立数值模块、测试、干净容器复现和哈希证据都已进入远程分支；同时也正确撤回了“h=2/h=1.5 求解器突破”和“6.31x/6.67x 算法提升”的表述。

因此，本轮应当区分两个结论：

```text
Task024 远程可复现性修复：成功。
Task024 production-level 迭代求解器目标：失败。
```

---

## 2. 远程源码复审

当前远程已经包含完整文件：

```text
src/studies/run_task024_engineering_iterative_solver.py
src/studies/task024_numerics.py
src/studies/audit_task024_export.py
src/test/test_20_task024_numerics.py
```

runner 已包含 CLI，并覆盖：

```text
PETSc MatNest real split
manual right-preconditioned FGMRES
complex 2x2 weighted Jacobi
particular FE solve
selected FE-response solve
m=1 reduced outer correction
full true residual reconstruction
AMS/HX 与 GMG-lite 实验路径
向量化 CSR 导出
```

`task024_numerics.py` 已将 manual FGMRES 和 CSR 过滤拆成独立函数。此前“outcomes 存在但产生结果的源码不在远程”的阻塞项已经关闭。

判定：

```text
complete_remote_source = pass
```

---

## 3. 干净环境复现

指定复现提交：

```text
6bc55e352ff3d48d17cca9b9a8b7ffef522a95ad
```

Codex 在新容器和新 clone 中从零完成：

```text
h=5 MPI1/MPI4 manual FGMRES smoke
h=5 PETSc/manual residual 对照
h=5 MPI1/MPI4 旧/新 CSR 对照
h=2 MPI4 从零装配、导出、20-step response、20-step particular 和 m=1 correction
```

h=2 复现值：

| 指标 | 值 |
|---|---:|
| FE rows | 615108 |
| FE nnz | 65122664 |
| response cancellation | 0.25994923155379307 |
| particular full residual | 0.270255331002689 |
| m=1 selected outer residual | 0.1789916662050465 |
| export peak RSS | 7.641 GB |
| solve peak RSS | 4.044 GB |

结果与原 Task024 20-step 数据逐值一致，且记录了 commit、命令、MPI、scalar type 和输入输出哈希。

判定：

```text
clean_reproduction = pass
h2_20_step_reproduction = pass
```

剩余小问题：镜像仍记录为 `code-dolfinx-mpc:latest`。长期工程复现应改为记录 image digest、Dockerfile/build commit 以及 PETSc、DOLFINx、dolfinx_mpc 和 Python 版本。

---

## 4. Manual FGMRES 正确性

独立实现已验证：

| 检查 | 结果 |
|---|---:|
| real-split 小矩阵 vs SciPy/PETSc | pass |
| native complex 小矩阵 vs SciPy/PETSc | pass |
| h=5 manual/PETSc 10-step residual | 完全一致 |
| residual history 最大差 | 5.0e-16 |
| Arnoldi orthogonality error | 7.198e-16 |
| Hessenberg residual与显式残差差 | 4.996e-16 |
| reconstruction error | 0 |
| h=5 MPI1/MPI4 residual差 | 4.0e-16 |
| MPI collective smoke | pass |

Codex 还修复了 native complex PETSc 模式下 `Vec.dot` 共轭方向问题。原 Task024 主路径使用 real split，不受旧问题影响；修复后 real/complex 两种模式均通过。

判定：

```text
manual_fgmres_correctness = pass_research
```

但当前实现保存全部 Arnoldi basis 和 preconditioned basis，内存随 Krylov 步数线性增长，且没有 restart、basis compression 或 Krylov-memory guard。因此只适合作为 research implementation，不能直接进入普通 solver API。

---

## 5. 向量化 CSR 导出器

向量化过滤已独立实现并检查：

```text
indptr 单调性
indices 范围
nnz 一致性
FE/aux entry 守恒
selected RHS 提取
复数值保留
rank packet 顺序无关重构
```

结果：

| case | 结果 |
|---|---|
| h=5 MPI1 vectorized vs reference | 逐数组完全相等 |
| h=5 MPI4 每rank vectorized vs reference | 逐数组完全相等 |
| h=5 MPI1/MPI4 physical residual | 差 4e-16 |
| h=2/h=1.5 invariant/hash audit | pass |
| h=5 过滤速度 | 约 21.5x 提升 |

判定：

```text
vectorized_csr_exporter = pass_candidate
```

这是 Task024 最适合选择性合并的工程成果。后续建议移入通用矩阵分块/导出模块，并保留小型 MPI 测试。

---

## 6. 基线与算法收益

Codex 已正确撤回相对零解的 `6.31x` 作为成功指标。

当前数据：

| 方法 | 预算 | full true residual | 相对 Task022 baseline |
|---|---:|---:|---:|
| Task022 GCROT/Jacobi | 20 history points | 0.163120 | 1.000x |
| Task024 m=1 | 20 response + 20 particular | 0.178992 | 更差 9.73% |
| Task024 m=1 | 100 response + 100 particular | 0.158592 | 仅好 2.78%，预算更大 |

Task022 history point 与 Task024 FE matvec 仍不是严格相同预算单位。因此最强可接受结论是：

```text
Task024 在更大预算下与旧 baseline 大致相当；
没有证明有意义的算法提升；
没有达到 production-level。
```

判定：

```text
algorithm_improvement = fail
minimum_signal_vs_existing_baseline = fail
```

未来必须统一 operator、初值、MPI、true residual、matvec 数、wall time 和内存上限后再比较。

---

## 7. 当前方法的准确性质

Codex 已将当前结果正确命名为：

```text
m=1 reduced FE-response approximation
```

它由 particular FE approximation、一根 selected FE-response column 和一个复数最小二乘系数组成。

它不是：

```text
完整 FE + 80 auxiliary outer Krylov solve
完整 Schur iterative solver
工程 production solver
```

summary 已正确区分 FE response cancellation、one-shot residual、particular residual、selected outer residual 和 full 80-aux residual。未收敛配置继续禁止输出 official R/T/A。

判定：

```text
terminology_correction = pass
```

---

## 8. AMS/HX 与 GMG 的结论边界

当前证据仅允许说明：

```text
特定 full-p2 same-H1 AMS/HX hierarchy 在14 GB下进入资源边界；
特定 p2到p1 root-SPLU coarse correction 为负收益；
native MatNest + block Jacobi 可低内存运行，但 FE inverse 很弱；
Task024 没有实现完整 COMSOL-style h-GMG。
```

不能推广为所有 AMS/HX、所有 GMG 或所有 coarse space 均失败。Codex 已在 response 和 summary 中修正了这一点。

判定：

```text
ams_hx_gmg_claim_scope = pass
```

---

## 9. Gate V2

| Gate | 状态 |
|---|---|
| 完整远程源码 | pass |
| py_compile / CLI | pass |
| 干净容器复现 | pass |
| h=2 20-step逐值复现 | pass |
| manual FGMRES正确性 | pass_research |
| vectorized CSR exporter | pass_candidate |
| 准确术语和残差定义 | pass |
| equal-budget算法收益 | fail |
| h=2 strong convergence | fail |
| production-like | fail |

最终：

```text
reproducibility gate = pass
algorithm gate = fail
production gate = fail
```

---

## 10. 合并建议 V2

可以选择性合并：

```text
复现修正文档
向量化 CSR filter/exporter
CSR invariants 与审计工具
相应单元测试和小型 MPI 测试
```

只保留在 research branch：

```text
Task024 综合 runner
manual FGMRES experimental implementation
AMS/HX/GMG-lite 探索路径
m=1 reduced FE-response profile
h=2/h=1.5 outcomes
```

不允许：

```text
不修改 ordinary default solver
不将 h=2/h=1.5 称为 engineering solver
不输出未收敛 official R/T/A
不使用相对零解 improvement 作为算法成功指标
```

---

## 11. 下一步

Task024 的可复现性问题已经解决，后续可以重新进入算法研究，但不建议直接盲目增加 m=2/4。

优先顺序：

```text
1. 建立严格 equal-budget benchmark harness；
2. 将 Task022 baseline 与 Task024 particular/m=1 放入同一计数框架；
3. 优先提高 A_FE inverse 的近似质量；
4. FE response 或 full residual 对严格 baseline 有明显收益后，再试 m=2/4；
5. production目标必须是完整 augmented FGMRES + FieldSplit/Schur。
```

建议算法 gate：

```text
minimum research signal：equal-budget full residual 至少改善2x
strong engineering signal：full residual <= 1e-2 且显著优于baseline
production-like：full residual <= 1e-6，official R/T/A与MPI一致性通过
```

若 m=2/4 相对 m=1 改善不足10%，应停止 mode enrichment，转向更强的 multilevel H(curl) FE inner solver。

---

## 12. V2 最终结论

Codex 的 `response_v1.md` 对 V1 做出了有效且诚实的回应：

```text
远程可复现性问题已解决；
manual FGMRES研究级正确性通过；
向量化CSR导出器具有合并价值；
结果命名和基线解释已纠正。
```

但算法事实没有改变：

```text
20+20步 residual 0.178992，比Task022 baseline更差；
100+100步 residual 0.158592，仅在更大预算下改善约2.78%；
FE response cancellation仍约0.22到0.26；
没有strong convergence，也没有production-like convergence。
```

Task024 V2 最终判定：

```text
reproducibility remediation = success
low-memory infrastructure = useful
production iterative solver objective = failed
```

下一阶段应在可信、可复现的代码基础上，集中开发更强的低内存 multilevel H(curl) FE inverse，并在完整 augmented solver 中相对严格同预算 baseline 获得显著收敛收益。
