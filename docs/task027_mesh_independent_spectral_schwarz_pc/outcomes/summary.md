# 结果总结

## 最新结论

Task027 的实际求解目标已经突破。新的统一 MPI4 配置在 `h=5/3/2 nm` 上分别以 `1201/993/1804` 步达到显式真残差小于 `1e-6`：

```text
最大/最小迭代比 = 1804 / 993 = 1.8167170191 < 2
h=2 含 official R/T/A 峰值总 RSS = 12.958454 GB < 14 GB
h=2 显式真残差 = 9.9973779520e-7
```

因此可以标记：

```text
mesh_independent_parallel_production_candidate_fixed_coarse
```

需要同时保留一个重要限定：本轮原设想的 operator-adaptive spectral coarse、PCHPDDM/GenEO、interface harmonic 等路线仍然没有性能正收益。真正解决问题的是：

```text
完整物理 z-slab 的 MPI owner-computes Schwarz
+ shifted local ILU1
+ 两步 matrix-free shifted-F 全局平滑
+ 固定 75 维 no-RHS z-hat 粗空间
```

所以这是“并行物理 Schwarz + 固定粗空间”的成功，不能改写成“谱粗空间成功”。

## 任务

在精确 auxiliary-free 凝聚算子

```math
A=F-CH^{-1}D
```

上寻找可在 14 GB 工作站内运行的 MPI4 迭代求解器，并用同一算法规则完成 `p=2, h=5/3/2 nm` 的真残差、内存、网格迭代比和 official R/T/A 闭环。

## 分支

```text
codex/20260711-task27-mesh-independent-spectral-schwarz
```

## 最终求解器

| 组成 | 最终设置 |
|---|---|
| 外层真实算子 | matrix-free `F-C H^-1 D` |
| 外层 Krylov | 右预条件 FGMRES，restart=100 |
| MPI | 4 ranks |
| 物理子域 | 16 个完整 z-slab |
| overlap | 0.25 slab，即 2.1875 nm |
| 子域分配 | 按子域行数 largest-first 分配给 owner rank |
| 子域因子 | shifted-F 局部 ILU1，每个完整 slab 全局只因子化一次 |
| 一层 action | forward VecScatter 取 RHS，reverse ADD_VALUES 汇总 overlap 修正 |
| 平滑 | 以上一层 PC 对 matrix-free shifted-F 做固定两步 GMRES |
| 粗空间 | 24 个 z 区间生成的固定 75 维 no-RHS z-hat basis |
| 粗算子 | 真 Galerkin `Z^H A Z`，加载 cache 后再次做真实 action 认证 |
| 停止口径 | PETSc residual 与显式 condensed/full true residual 双重检查 |
| 后处理 | auxiliary back-substitution + modal R/T + volume absorption |

三个网格没有逐网格调整 slab 数、overlap、shift、ILU、平滑步数、粗空间规则或 restart；只使用与网格对应且通过真实 action 认证的 basis/coarse cache。

## 核心结果

| h (nm) | FE DoF | F nnz | 迭代数 | 显式真残差 | solve (s) | 总时间 (s) | 含 R/T/A 峰值 RSS (GB) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 4,840,396 | 1,201 | 9.8395e-7 | 91.10 | 110.91 | 1.957 |
| 3 | 198,438 | 21,167,444 | 993 | 9.9326e-7 | 317.85 | 361.74 | 5.070 |
| 2 | 615,108 | 65,122,664 | 1,804 | 9.9974e-7 | 2,179.96 | 2,328.13 | 12.958 |

严格迭代比：

```text
max(1201, 993, 1804) / min(1201, 993, 1804)
= 1804 / 993
= 1.8167170191
```

该值不是由 50 步 checkpoint 取整得到，而是三个 PETSc 求解器的实际终止迭代数。

## 关键架构修复

旧 MPI4 物理 ASM 把每个物理 slab 切成 rank-local fragment；每个 rank 都拥有 16 个 fragment，最终形成 64 个局部因子。这样既重复存储 overlap，又使 h=2 MatMult/PC apply 在高内存压力下极慢。

新实现先在 Floquet/MPC reduction 后收集每个 slab 的全局 reduced-DoF 集合，再采用 owner-computes：

1. 16 个完整 slab 各自只分配给一个 owner rank；
2. `Mat.createSubMatrices` 允许每个 rank 请求不同数量的顺序子矩阵；
3. 每个 owner 只建立自己负责的 ILU1 因子；
4. 每次一层 apply 只做一次分布式到顺序的 RHS gather；
5. overlap 修正通过 reverse scatter 加回分布式向量；
6. 两步全局 shifted-F GMRES 使用该一层 action，但外层残差始终来自真实凝聚算子。

h=2 的 938,300 个累计子域行被分配为每个 owner 230,202 至 238,948 行；全局子域因子 nnz 为 95,617,608。没有 rank0 gather 完整 FE 矩阵，也没有每个 rank 重复 16 个完整因子。

## 配置漏斗

| 配置 | h5 100 步 | h3 100 步 | h2 100 步 | 完整迭代数 h5/h3/h2 | 比值 | 判定 |
|---|---:|---:|---:|---|---:|---|
| owner-slab，一步平滑 | 6.266e-3 | 2.246e-3 | 3.782e-3 | 2765/1836/3682 | 2.0054 | 只差 10 步，未通过 |
| owner-slab，两步全局平滑 | 2.574e-3 | 1.203e-3 | 2.000e-3 | 1201/993/1804 | 1.8167 | **最终通过** |
| overlap=0.375 | 1.985e-3 | 2.651e-3 | 3.313e-3 | 878/-/- | - | 过度偏向 h5，内存更高 |
| 12 slabs | 1.389e-3 | 2.110e-3 | - | - | - | 过度偏向 h5 |
| 局部 GMRES2 | 3.633e-3 | 1.796e-3 | 2.874e-3 | 2356/1542/- | - | h2 单 100 步 solve 389.6 s，成本过高 |
| post-smooth 0.05 | 5.227e-3 | 2.015e-3 | 3.292e-3 | 2291/1644/3324 | 2.0219 | 比值和成本失败 |
| restart=50 | 7.324e-3 | 2.421e-3 | 5.104e-3 | - | - | h2 前 100 步恶化约 35% |
| CGS 条件/强制重正交 | 与基线一致 | - | 3.782e-3 | - | - | 排除外层正交性损失 |

完整漏斗见 `distributed_slab_profile_funnel.csv`。正信号出现后继续追到完整三网格 Gate；负方向在统一低成本筛选后停止，没有把失败配置包装成成功。

## 与既有并行配置比较

| MPI4 配置 | h5/h3/h2 迭代数 | 比值 | h2 solve (s) | h2 峰值 RSS (GB) | 结论 |
|---|---|---:|---:|---:|---|
| BJacobi/ILU1 + sm5 | 559/1154/2903 | 5.1932 | 4,030.1 | 11.272 | 生产收敛，但非网格鲁棒 |
| 完整 owner-slab + sm1 | 2765/1836/3682 | 2.0054 | 1,705.3 | 13.014 | h2 最快，但严格比值差 10 步 |
| 完整 owner-slab + sm2 | 1201/993/1804 | **1.8167** | 2,180.0 | 12.958 | **最终选择** |

两步平滑把 h2 迭代数相对 sm1 降低 51.0%，但平均 PC apply 从 0.325 s 增至 1.032 s，因此 h2 solve 时间比 sm1 增加约 27.8%。它仍比旧 BJacobi-sm5 的 4,030 s 快约 45.9%，并且首次同时通过 MPI4 production 和网格比门槛。

## 官方 R/T/A 与能量

| h (nm) | R | T | A_volume | R+T+A_volume | 能量闭合误差 |
|---:|---:|---:|---:|---:|---:|
| 5 | 0.0890216032 | 0.4425882752 | 0.4683901190 | 0.9999999974 | -2.551e-9 |
| 3 | 0.0046130324 | 0.5836533646 | 0.4117336036 | 1.0000000006 | 6.180e-10 |
| 2 | 0.0013429363 | 0.5992132418 | 0.3994438284 | 1.0000000066 | 6.579e-9 |

所有 official 输出都来自通过 `1e-6` 显式真残差 Gate 的场。h=2 的 PETSc reported residual 与显式真残差之差约 `4.0e-16`，不存在 projected-residual 假收敛。

R/T/A 在每个网格内能量闭合，但跨网格仍未物理收敛，特别是反射率 R 对网格很敏感。因此可以声明“线性求解器在三个网格上鲁棒”，不能声明“物理量已经网格收敛”。

## 内存与成本

| h (nm) | basis 存储 (MB) | 平均一层 apply (s) | 平均完整 PC apply (s) | 最终 swap (GB) | 峰值总 RSS (GB) |
|---:|---:|---:|---:|---:|---:|
| 5 | 10.85 | 0.0155 | 0.0650 | 0.107 | 1.957 |
| 3 | 49.88 | 0.0685 | 0.2805 | 0.107 | 5.070 |
| 2 | 157.43 | 0.2520 | 1.0319 | 0.454 | 12.958 |

h=2 从第一轮 Krylov 周期到 1,804 步期间峰值没有继续增长，swap 没有持续爬升或出现 thrashing。强制门槛 `<14 GB` 通过，优选目标 `<=12 GB` 尚未达到；距离 14 GB 上限约有 1.04 GB 余量。

## 谱路线结论

PoU、局部 SPD energy、SLEPc 特征残差和正交性都通过代数检查，但求解性能失败：

| 路线 | coarse dim | h5 100 步真残差 | 判定 |
|---|---:|---:|---|
| 固定 hand no-RHS 参照 | 75 | 6.272e-3 | 参照 |
| full-slab tau=2.0 | 32 | 2.454e-1 | 失败 |
| full-slab tau=1.8 | 56 | 2.458e-1 | 失败 |
| full-slab tau=1.5 | 64 | 2.467e-1 | 失败 |
| interface harmonic | 60 | 2.504e-1 | 失败 |
| hand + interface | 135 | 7.162e-3 | 负收益 |
| shifted near-null | 64 | 2.588e-1 | 失败 |
| HPDDM Ritz + 真 Galerkin | 95 | 7.435e-3 | 负收益 |
| PCHPDDM energy GenEO | - | 2.187e-1 | 失败 |

这表明当前非正规、复系数、带 Floquet DtN 的慢误差没有被这些局部能量特征模式捕获。代数正确性不能替代统一预算下的真残差性能 Gate。

## 物理模型

| 项目 | 设置 |
|---|---|
| 几何 | 50 x 25 x 140 nm，17 x 25 x 120 nm grating |
| 离散 | 3D p=2 Nedelec + 双 Floquet 周期 |
| 波长 | 13.5 nm |
| 入射 | 从 z 轴计 80 度，s 偏振，E 沿 y |
| 材料 | 复折射率，体吸收纳入 A_volume |
| 端口 | 上下边界 periodic modal DtN |
| auxiliary 模态 | 80 |
| 真实外层算子 | matrix-free `F-C H^-1 D` |

## 代表运行命令

```bash
mpiexec -n 4 python -m src.studies.run_task027_mesh_independent_spectral_schwarz \
  --h-nm 2 --coarse-type hand \
  --num-slabs 16 --overlap-layers 0.25 \
  --no-include-physical-rhs \
  --local-pc-type distributed_slab \
  --distributed-slab-interpolation basic \
  --distributed-slab-assembly two_color \
  --distributed-slab-local-iterations 1 \
  --distributed-slab-local-ksp gmres \
  --ilu-levels 1 --smoother-iterations 2 --no-post-smooth \
  --hand-basis-cache results/task027_hand_basis_h2_no_rhs_mpi4_local.npz \
  --coarse-matrix-cache results/task027_coarse_h2_no_rhs_universal.npz \
  --outer-ksp fgmres --restart 100 \
  --max-it 3000 --rtol 1e-6 --monitor-stride 25 \
  --case-label task027_h2_mpi4_distributed_slab_sm2_gate_rtol1e6
```

实际使用 `code-dolfinx-task027-hpddm:latest` complex PETSc 容器。每次 Stage-4 运行仍在 `Results/` 保留完整 case 结果；Git 只提交小型 JSON/CSV/日志。

## 改动文件

主要实现：

```text
src/solvers/spectral_schwarz.py
src/studies/run_task027_mesh_independent_spectral_schwarz.py
src/test/test_23_task027_spectral_schwarz.py
```

文档与数据：

```text
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/
notes/theory/task027_shifted_impedance_spectral_schwarz_convergence_framework.md
notes/reference/current_version_boundaries.md
docs/README.md
notes/README.md
```

完整清单见 `changed_files.md`。

## 验证

当前已完成：

```text
python -m py_compile：通过
ruff check：通过
MPI1 Task026 + Task027 全套：20 passed，1 个既有 LOBPCG 非失败 warning
MPI2 Task026 condensed：每个 rank 7 passed
MPI2 Task027 distributed slab/coarse/matrix-free shift：每个 rank 5 passed
新增 distributed physical-slab 定向测试 MPI1：2 passed
新增 distributed physical-slab 定向测试 MPI2：每个 rank 2 passed
h=5/h=3/h=2 MPI4 完整真残差 Gate：通过
h=5/h=3/h=2 official R/T/A：通过
h=2 内存 Gate：通过
```

全套 Task026/Task027 回归的最终结果记录在 `run_log.txt`。

## 已知问题

1. 最终粗空间仍是固定 75 维 z-hat，不是 operator-adaptive spectral coarse。
2. h=2 峰值 12.958 GB 通过强制 14 GB Gate，但没有达到优选 12 GB 目标。
3. h=2 在 `9.9974e-7` 刚进入 Gate；当前 run 的 reported/true residual 一致，若后续批量生产希望额外安全余量，可显式使用 `rtol=8e-7`。
4. 三网格 R/T/A 尚未物理收敛，不能把 solver mesh robustness 当成物理网格收敛。
5. `two_color` 当前是确定性的两批 additive 汇总，不是 multiplicative Schwarz；sm1 中它与 combined 轨迹一致。
6. 两步平滑比一步平滑更鲁棒，但单次 PC 更贵；当前选择优先保证严格网格 Gate。

## 下一步审查问题

1. 是否接受该 MPI4 owner-computes physical-slab profile 作为当前显式选择的 workstation production candidate？
2. 是否在后续独立任务中复跑 `rtol=8e-7` 安全余量，并做角度/波长/材料参数鲁棒性，而不是继续扫描本轮已失败的谱 tau/cap？
3. 是否继续优化两步平滑的 3 次一层 apply 开销，以降低 36.3 分钟的 h=2 solve 时间？
