# Case094：Comprehensive All-Slab Learned Local Inverse

本 Case 对应 PARA-Task005，只在当前 research branch 上验证固定 h5 operator 的
16 个 slab-specific learned local inverses。它不改变 ordinary default，也不自动运行
h3/h2。

## 冻结配置

| 项目 | 值 |
|---|---:|
| 物理 | 13.5 nm、当前 complex Si、theta 80°、phi 0°、S polarization |
| 离散 | p2 Nédélec hexahedral，h5，44,698 FE DoF |
| 并行 | MPI4，每 rank/BLAS 1 thread |
| GPU | 单进程 persistent CUDA，GPU 0 Quadro RTX 8000 |
| 外层 | right FGMRES90，rtol 1e-6，max_it 1200 |
| PC | 16 slabs、overlap 0.25、75D coarse、two-step + post-smooth |
| 数据 | 每 slab 1024 train + 256 validation + 256 holdout |
| artifacts | `benchmarks/artifacts/cases/094/`，Git ignored |

## 强制顺序

```text
P0 clean baseline
-> P1 T1/T2/V/H raw capture + sequential LU teacher
-> P2 R4 data/model/backend screen
-> P3 16 independent models
-> P4 shadow
-> P5 diagnostic fallback
-> P6 true no-hidden-ILU replacement
-> P7 three paired A/B
-> conditional P8/P9
-> P10 decision
```

任一 Gate 失败即按任务书停止后续条件阶段并保留负结果。特别是不能用 shadow 或
fallback profile 声称 factor removal，不能在 16-independent 工程 Gate 通过前训练
shared/expert 模型。

## 当前 P0

clean source `f4c0600...` 的初始 baseline 为 852 iterations、97.253 s，
三种 residual 约 `9.9951e-7`，外部 simultaneous worker peak 1.612 GiB，
swap in/out 为 0。该数字是初始 sanity；最终性能声明仍使用 finalist HEAD 上三组
paired A/B。
