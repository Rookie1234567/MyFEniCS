# 架构概览

## 分层结构

| 层 | 目录 | 职责 |
|---|---|---|
| 配置与几何 | `src/common`, `src/geometry` | 物理参数、网格与目标几何 |
| 约束 | `src/constraints` | x/y Floquet MPC |
| 变分与端口 | `src/solvers/common_3d_*`, `dtn_port_3d.py` | H(curl) 装配、DtN 模态端口 |
| 稳定求解组件 | `condensed_dtn.py`, `physical_slab_two_level.py` | 精确凝聚、固定 coarse、MPI slab smoother |
| 运行入口 | `src/runners` | 普通 direct 工作流 |
| Benchmark | `benchmarks` | 显式 opt-in workstation profile 与分层验证 |
| 后处理 | `src/postprocessing` | official modal R/T 与 volume absorption |
| 任务记录 | `docs/taskXXX_*` | task、outcomes、review 闭环 |
| 理论笔记 | `notes` | 理论、学习与解释文档 |

## Stage4 迭代数据流

```text
目标配置
  -> mesh + N1curl p=2 + Floquet MPC
  -> augmented [F C; D H]
  -> exact condensation A_c = F - C H^-1 D
  -> fixed 75D Floquet coarse
  -> owner-computes overlapping physical slabs on shifted F
  -> right-preconditioned FGMRES
  -> explicit condensed/full residual
  -> auxiliary back-substitution
  -> official DtN modal R/T + A_volume
```

## 模块边界

`stage4_runtime.py` 只装配目标系统，不选择求解器。`condensed_dtn.py` 不知道网格和物理几何。`physical_slab_two_level.py` 只接受 PETSc 矩阵、全局子域索引和稀疏 coarse vectors。`benchmarks/run_workstation_iterative.py` 负责把这些组件组合成经过验证的 profile。

Task013-Task025 的 sampled-Schur、cached-Q、AMS/HX 原型和 Task027 的 spectral/GenEO/HPDDM 路线不属于普通 API。
