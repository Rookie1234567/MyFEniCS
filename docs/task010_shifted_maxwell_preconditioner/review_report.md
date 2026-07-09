# REVIEW REPORT 20260707：Task010 物理预条件器与 MUMPS-BLR 原型验证

## 1. 审查对象

审查分支：

```text
codex/20260707-maxwell-physics-blr-preconditioner-prototype
```

任务目录：

```text
docs/task010_shifted_maxwell_preconditioner/
```

重点文件：

```text
outcomes/summary.md
outcomes/mumps_blr_feasibility.md
outcomes/preconditioner_profile_ranking.md
outcomes/blr_profile_summary.csv
outcomes/shifted_positive_profile_summary.csv
outcomes/hx_ams_feasibility.md
outcomes/block_preconditioner_feasibility.md
src/solvers/common_3d_solve.py
src/solvers/dtn_port_3d.py
```

## 2. 总体结论

Task010 通过，建议合并，但合并语义必须准确：

```text
Task010 找到了一个短期可用候选：FGMRES + MUMPS-BLR；
但 BLR 仍属于压缩直接 / 近似 factorization 路线，内存相比 direct LU 只小幅下降；
它不是最终低内存迭代法。
```

本轮最可靠的正结果是：

```text
iter_fgmres_mumps_blr_eps1e-5
```

它在 `p=2 h=2 nm` 上收敛，并复现了 task008 direct LU 的 official R/T/A。

## 3. MUMPS-BLR 结果

`p=2 h=2 nm` 关键结果：

| profile | status | iterations | true relative residual | R | T | A_volume | RSS upper GB | wall s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| eps=1e-5 | completed | 4 | 2.085e-08 | 0.0013429328 | 0.5992132289 | 0.3994438376 | 17.85 | 1357.6 |
| eps=1e-4 | completed | 7 | 1.883e-07 | 0.0013429337 | 0.5992132297 | 0.3994438383 | 18.09 | 1233.9 |
| eps=1e-3 | timeout | - | - | - | - | - | 16.27 | 1801.3 |
| direct LU | completed | - | - | 0.001342932846 | 0.599213229444 | 0.399443837710 | 20.53 | 1665.8 |

判断：

```text
eps=1e-5 是当前 BLR 第一候选；
eps=1e-4 是备选；
eps=1e-3 在 h=2 超时，不建议作为主 profile。
```

`eps=1e-5` 与 direct LU 的 R/T/A 差异在 `1e-9` 量级以内，说明它不是只降低 residual，而是能复现物理后处理。

但 BLR 的内存下降有限：

```text
direct LU RSS upper ≈ 20.53 GB
BLR eps=1e-5 RSS upper ≈ 17.85 GB
```

因此 BLR 可作为短期备用路线，但不能作为最终低内存迭代法。

## 4. h=1.5 边界

`eps=1e-5, p=2 h=1.5` 在 KSP setup 阶段被 signal 9 kill。失败前已经完成 base matrix assembly，base nnz 约 `1.421e8`。峰值很可能发生在 MUMPS factor / preconditioner setup 内部。

因此当前本机 production 上限仍是：

```text
p=2 h=2 nm
```

不能说 h=1.5 已经由 BLR 解决。

## 5. shifted / positive Maxwell minimal P

本轮实现了 `KSP.setOperators(A, P)` 路径：

```text
A = original Stage 4 DtN augmented system
P = shifted/positive Maxwell minimal operator preconditioner
```

这个基础设施有价值，但当前 profiles 不能作为 solver。

结果：

```text
shifted Maxwell minimal P + ASM/ILU0: h=5/h=4 未收敛；
positive Maxwell minimal P + ASM/ILU0/local LU: h=5/h=4 未收敛。
```

结论：

```text
A/P 双矩阵通路已打通；
minimal shifted/positive P 不应继续盲目调参；
它只应作为后续 HX/AMS 或 block preconditioner 的基础设施。
```

## 6. HX/AMS 与 block feasibility

本轮文档正确区分了：

```text
positive Maxwell minimal P != Hiptmair-Xu / hypre AMS
```

完整 AMS/HX 仍需要 compatible H1 nodal auxiliary space、discrete gradient / interpolation、Floquet phase 处理，以及 DtN auxiliary unknowns 的 block 处理。

FE/aux block 结构也已经明确：

```text
[ FE Nedelec field unknowns ; DtN auxiliary modal unknowns ]
```

但当前 auxiliary block 只是 identity，不是真实 Schur 近似。后续若继续 block preconditioner，应结合 AMS/HX，而不是重复 task009 的 FieldSplit + ASM/LU。

## 7. 仓库卫生

compare 结果显示 raw_runs 中仍有一些 0-line placeholder 文件。建议合并前或合并后清理空文件，只保留真实有内容的 lightweight raw outputs。

`mumps_blr_compression_ratio` 目前为空。文档已说明原因：当前 PETSc/petsc4py summary 未稳定暴露该字段。这个不阻塞合并，但后续若继续使用 BLR，应补充 MUMPS verbose / INFOG 采集。

## 8. 是否建议合并

建议合并，但只按如下语义合并：

```text
Task010 = MUMPS-BLR production candidate + shifted/positive P infrastructure + HX/AMS feasibility record。
```

不要按如下语义合并：

```text
已经找到最终低内存迭代法；
已经解决 h=1.5；
AMS/HX 已实现；
shifted/positive minimal P 已经可用。
```

## 9. 下一步建议

用户当前目标是得到一个真实低内存迭代求解器：不依赖 global LU/BLR factorization，可以收敛，R/T/A 与 direct 基本一致，内存明显少于 direct/BLR。

因此下一步建议开启：

```text
Task011：Stage 4 3D Maxwell low-memory AMS/HX iterative solver prototype
```

核心方向：

```text
1. low-memory Krylov baseline：GMRES restart 小、TFQMR、BiCGStab、CGS + Jacobi；
2. H(curl) AMS/Hiptmair-Xu smoke test：先在 simplified FE block 上验证；
3. AMS/HX positive Maxwell FE-block preconditioner；
4. Stage 4 FE/aux block diagonal preconditioner；
5. matrix-free matvec feasibility 作为后续降内存基础。
```

评判标准：

```text
不用 LU/BLR；
KSP 收敛；
true residual 可信；
R/T/A 与 direct reference 基本一致；
内存明显低于 direct/BLR。
```

## 10. 最终结论

```text
task010 通过；
建议合并，最好清理空 raw placeholder；
BLR eps=1e-5 是短期可用候选，但不是最终低内存迭代法；
shifted/positive minimal P 不可作为 solver；
下一步应进入 AMS/HX low-memory iterative solver prototype。
```
