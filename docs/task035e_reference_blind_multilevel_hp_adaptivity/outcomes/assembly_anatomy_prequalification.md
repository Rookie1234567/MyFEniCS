# Task035e 高阶多层 variable-p 装配诊断

## 1. 证据身份

本文件记录 `p4/p5/p6 + 两层 local-h + variable trace` 组件路径的首次
MPI1 诊断。该运行发生在最终周期闭合和分布式 selected-row 内存修复完成
之前，因此：

- `classification = measured_nonformal_component_diagnostic`；
- 不计入 Task035e reference、blind candidate 或 MPI8 资格化；
- 不替代最终干净源码上的 MPI8 组件锚点；
- 数值与资源原始字段见
  `benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/task035e_multilevel_p456_h100_mpi1_diagnostic_prequalification.json`。

运行完成了实际 PDE、静态凝聚、DtN、直接分解、场恢复和 full explicit
residual。晚期 pytest 失败仅来自 summary JSON 路径少一层 `mesh`，离线按
真实 schema 修正后全部数值断言通过。

## 2. 数值和结构结果

| 项目 | 实测值 |
|---|---:|
| nominal mesh | `h100` |
| MPI | 1 |
| p4 / p5 / p6 cells | 12 / 88 / 64 |
| p6 container DoF | 118,398 |
| raw broken active FE DoF | 84,152 |
| conforming Full3D-equivalent active DoF | 78,384 |
| independent active trace DoF | 22,938 |
| augmented condensed rows | 23,018 |
| matrix NNZ used | 15,291,778 |
| factor NNZ | 94,398,336 |
| matrix mallocs | 0 |
| full explicit true residual | `1.096295e-10` |
| energy closure error | `3.299139e-12` |
| peak RSS | 5,090.55 MiB |
| elapsed | 1,781.53 s |

inactive p6 trace/interior modes 未取得全局行号，hanging 与 Floquet 约束均在
全局插入之前物理消元。这个组件点证明“减少 active DoF 和 rows”在真实
compiled PDE 路径中成立，但 MPI1/PETSc serial factor 资源值不是正式
MUMPS MPI8 authority。

## 3. 时间解剖

| 阶段 | 时间 / s | 占总时间 |
|---|---:|---:|
| base variable-p matrix | 1,404.643 | 78.84% |
| DtN modal loop | 54.251 | 3.05% |
| factor / `KSPSetUp` | 300.780 | 16.88% |
| backsolve | 0.418 | 0.02% |
| field recovery | 1.942 | 0.11% |
| explicit residual | 0.594 | 0.03% |
| postprocess | 11.272 | 0.63% |

因此“装配比求解久”不是统计口径错位：这个点的 backsolve 只有约
0.42 s，而高阶 tensor、投影、Schur 和 trace authority 构造占绝对主导。

base matrix 的已测分解为：

| 子阶段 | 时间 / s | base 占比 | 解释 |
|---|---:|---:|---|
| compiled raw p6 tensor kernels | 699.950 | 49.83% | 10 个去重 tensor class，约 70 s/class |
| projection / orientation | 208.744 | 14.86% | 98 个 rank-local reference class |
| Aii LU、Schur 与 recovery data | 62.356 | 4.44% | 约 0.636 s/class |
| 164 次 cell insertion | 28.293 | 2.01% | 约 0.173 s/cell |
| exact preallocation | 0.525 | 0.04% | 不是瓶颈 |
| outer 未细分部分 | 404.764 | 28.82% | 需要新增只读 phase timers |

`outer 未细分部分` 当前只能作根因假设。FFCx cache 在运行窗口没有新 artifact，
所以不是一次新的 cold JIT 编译。最强候选是 trace authority 中保留的 164 个
dense cell expansion（约 281 MiB logical payload）及逐 cell 完整 SVD
rank/condition 审计；在添加独立计时前不得把这个推断写成已测结论。

## 4. 优化顺序

以下优化必须保持 ordinary default 不变，并用 matrix entry hash、residual 和
正式 observable vector 证明数值 blob 未改变：

1. 先细分计时：`fem.form`/cache acquisition、local-h authority、entity
   block、cell expansion/SVD、global transfer、raw tensor、projection、
   Schur、insertion 和 DtN component vector。
2. 对 10 个 raw tensor class 建 SHA/ABI/geometry/material-bound
   offline/warm cache；manifest-last 发布，加载后逐数组 hash 验证。
3. 按 canonical expansion bytes/shape 去重 SVD 审计；不改变实际 expansion
   matrix 或装配顺序。
4. 正式 MPI8 利用已有 tensor-class owner 分配，并实测并行缩短量，不能按
   8 倍线性加速外推。
5. 进一步去重 projected/oriented class、Aii LU 和 Schur/recovery cache。
6. 在保持确定性累加顺序的条件下，研究 chunked CSR/COO insertion，减少
   164 次小块 PETSc 跨层调用。
7. 对 40 个唯一 DtN surface-order component vector 建相同身份约束的 warm
   cache。

factor 的 300.78 s 是另一条 lane；它不应与 23 分钟 base assembly 混称。
最终 MPI8 还必须分别报告 assembly、MUMPS symbolic、numeric、backsolve、
field recovery 和 postprocess。
