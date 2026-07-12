# 求解器指南

## 选择表

| 场景 | 推荐求解器 | 状态 |
|---|---|---|
| 小案例、回归、Stage1-4 smoke | 既有 direct 默认 | 稳定 |
| 目标 p=2 h=2 direct reference | MUMPS/direct 或显式 BLR 备用 | 已验证，内存较高 |
| 目标 p=2 h=5/3/2，MPI4，14 GB 级工作站 | `workstation_p2_fixed_coarse_physical_slab` | 显式 opt-in 生产候选 |
| h=1.5 或更细 | 无正式推荐 | 未验证 |
| 任意新角度/波长/几何 | 先 direct/粗网格交叉验证 | 参数鲁棒性尚未证明 |

## Workstation Profile

| 参数 | 固定值 |
|---|---|
| polynomial degree | 2 |
| outer Krylov | right FGMRES |
| restart / rtol | 100 / 1e-6 |
| operator | matrix-free exact `F-C H^-1 D` |
| coarse | 24 z intervals，25 nodes x 3 components = 75D |
| local subdomains | 16 complete physical z slabs |
| overlap | 0.25 slab width |
| local factor | shifted-F ILU(1)，owner computes |
| smoothing | 两个 fixed GMRES steps |
| interpolation | basic additive，two-color reverse assembly |
| MPI | 4 ranks |

不要把 profile 名称理解为严格 mesh-independent。Task027 在 h=5/3/2 的迭代数为 1201/993/1804，三者都通过 1e-6 gate，但不单调。

## 可信停止条件

正式结果必须同时记录：

| 指标 | 要求 |
|---|---|
| PETSc reported relative residual | <= 1e-6 |
| explicit condensed residual | <= 1e-6 |
| full augmented residual | <= 1e-6 |
| 三口径一致性 | 数值误差范围内一致 |
| official R/T/A | 仅在 residual gate 后计算 |
| peak total RSS | 记录所有 MPI ranks 总和 |

## 已排除路线

普通接口不包含 spectral/GenEO coarse、HPDDM recycling、sampled-Schur、cached-Q、FE-only AMS 或 serial SciPy SPILU。这些是有价值的负结果或研究原型，不是用户可选 production profile。
