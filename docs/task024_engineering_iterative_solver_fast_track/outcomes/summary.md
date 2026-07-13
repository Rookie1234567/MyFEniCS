# 结果总结

## 任务

Task024 在 14 GB WSL 配额内研究 p=2 大规模 Maxwell FE-response，并测试 h=2 与 h=1.5 的低内存迭代可扩展性。本次 V1 审阅修复重点是源码可复现、manual FGMRES 正确性、CSR 导出等价性和基线定义。

## 分支与复现提交

| 项目 | 值 |
|---|---|
| 分支 | `codex/20260709-task20-wave-solver-search` |
| 干净复现提交 | `6bc55e352ff3d48d17cca9b9a8b7ffef522a95ad` |
| Docker 镜像 | `code-dolfinx-mpc:latest` |
| 大文件证据 | `results/task024_clean_repro_v1/`，Git 忽略 |

## 准确命名

当前最终结果是：

```text
particular FE approximation
+ one selected FE-response column
+ one complex least-squares coefficient
= m=1 reduced FE-response approximation
```

它不是完整 80-aux outer Krylov solve，不是工程求解器，也没有收敛到可输出 official R/T/A 的程度。

## 残差定义

| 名称 | 含义 | h=2 20 步值 |
|---|---|---:|
| FE response cancellation | `||A_FE q_j-r_j||/||r_j||` | 0.259949 |
| zero-solution one-shot residual | 从零解仅缩放一根响应列 | 0.983424 |
| particular FE residual | `||A_FE y-b_FE||/||b_FE||` | 0.259949 |
| particular full residual | particular 解的 FE + 80 auxiliary 真残差 | 0.270255 |
| selected outer true residual | particular + m=1 correction 的完整真残差 | 0.178992 |
| full 80-aux iterative residual | 完整 outer Krylov 解 | 未执行 |

## 核心结果

| case | FE rows | FE nnz | response/particular 步数 | m=1 full residual | peak solve RSS | 结论 |
|---|---:|---:|---:|---:|---:|---|
| h=2 clean V1 | 615,108 | 65,122,664 | 20/20 | 0.1789916662 | 4.044 GB | 可复现低内存证据 |
| h=2 原 Task024 | 615,108 | 65,122,664 | 100/100 | 0.1585916947 | 4.469 GB | 更大预算，仍非 solver breakthrough |
| h=1.5 原 Task024 | 1,347,234 | 142,105,868 | 100/100 | 0.1499668138 | 8.566 GB | 低内存可扩展性证据 |

## 基线修正

| 方法 | 预算 | full true residual | 相对 Task022 `0.163120` | 判定 |
|---|---:|---:|---:|---|
| Task022 GCROT/Jacobi | 20 history points | 0.163120 | 1.000x | 历史基线 |
| Task024 m=1 | 20+20 FE Krylov | 0.178992 | 0.911x | 残差高 9.73% |
| Task024 m=1 | 100+100 FE Krylov | 0.158592 | 1.029x | 仅好 2.78%，预算更大 |

原文的 `6.31x/6.67x` 只是相对零解 residual=1 的归一化比值，不能作为算法突破指标。Task024 没有达到“相对既有基线至少 2x”的 minimum signal，算法 gate 改为 **fail**。

## Manual FGMRES 验证

| 检查 | 结果 |
|---|---:|
| real-split 小矩阵 vs SciPy/PETSc | 通过 |
| native complex 小矩阵 vs SciPy/PETSc | 通过 |
| h=5 manual/PETSc 10 步最终 residual | `0.3885794317434202` / `0.3885794317434202` |
| residual history 最大差 | `5.0e-16` |
| Arnoldi orthogonality error | `7.198e-16` |
| Hessenberg/显式真残差差 | `4.996e-16` |
| reconstruction error | `0` |
| h=5 MPI=1/4 residual 差 | `4.0e-16` |

测试发现并修复了原生 complex PETSc 模式下的 `Vec.dot` 内积方向问题。real-split 生产路径使用实标量，不受旧缺陷影响；修复后两种 scalar mode 都通过。

## CSR 导出验证

| case | 旧/新逐数组 | rank packet 顺序 | 非零虚部项 | 过滤耗时对比 | peak export RSS |
|---|---|---|---:|---:|---:|
| h=5 MPI=1 | 完全相等 | invariant | 1,646,808 | 0.093/2.009 s | 1.245 GB |
| h=5 MPI=4 | 每 rank 完全相等 | invariant | 1,646,788 | 0.036/0.768 s | 2.119 GB |
| h=2 MPI=4 | 大案例不跑慢参考 | invariant | 22,867,093 | 未比较 | 7.641 GB |
| h=1.5 MPI=4 | 大案例不跑慢参考 | invariant | 52,519,047 | 未比较 | 13.14 GB |

不同 MPI 数会改变 DOLFINx 全局自由度编号，跨 MPI 不要求 CSR SHA 相同；跨 MPI 使用物理 residual consistency，h=5 绝对差为 `4e-16`。

## AMS/HX 与 GMG 边界

| 路线 | 当前证据允许的结论 |
|---|---|
| full p2 same-H1 AMS/HX | 本任务特定 hierarchy 在当前 14 GB 配额进入资源边界 |
| p1 root SPLU coarse | 本任务特定 p-coarsening/root-SPLU 组合为负收益 |
| native MatNest + block Jacobi | 低内存、可运行，但 FE inverse 偏弱 |
| Python CSR MatShell | 在本任务中没有优于 native MatNest |

这些结果不能推广成“所有 AMS/HX、GMG 或 coarse space 均失败”。本任务没有实现完整 COMSOL-style h-GMG。

## Gate

| Gate | 状态 |
|---|---|
| 完整源码、py_compile、CLI | pass |
| 干净容器 h=5/h=2 复现 | pass |
| manual FGMRES correctness | pass |
| vectorized CSR correctness | pass |
| h=2 20-step reproducibility | pass |
| 相对既有基线的算法收益 | fail |
| production-like residual 与 official R/T/A | fail |

## 已知问题

1. h=2/h=1.5 只是低内存可扩展性证据，不能设为默认 solver profile。
2. m=1 子空间过小，full residual 仍约为 `0.15-0.18`。
3. Task022 与 Task024 的预算单位并非完全相同，需要未来统一 matvec、wall time 与初值策略后再做严格基线。
4. 未收敛配置禁止输出 official R/T/A。

## 下一步建议

优先改进 FE inner solve，并在统一 true residual、初值、matvec 与 wall-time 预算下重跑基线。只有相对现有基线出现至少 2x 改善时，才继续扩展 m=2/4 response cache；否则停止增加 auxiliary modes。
