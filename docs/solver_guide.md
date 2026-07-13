# 求解器指南

## 1. 选择表

| 场景 | 入口/求解器 | 状态 | 资源边界 |
|---|---|---|---|
| 2D、Stage1-4 smoke、小网格 | ordinary auxiliary direct | recommended | 先做物理与代码回归 |
| 目标 p2 h=5/3 | ordinary MUMPS direct | recommended | Task28 为 2.29/8.18 GB |
| Task28 target direct reference | default MPI4 MUMPS | recommended | Task29 不改变该基线和 ordinary default |
| 目标 p2 h=2 direct reference | MUMPS direct | supported | 历史约 20.53 GB，超当前 14 GB |
| direct 内存紧张且 scratch 足够 | MUMPS OOC | diagnostic_only | Task29 收益不足 20% 且 I/O 变慢，必须保留 scratch 证据 |
| direct 内存紧张的压缩尝试 | MUMPS BLR | experimental | 需逐案例验证残差与 RTA |
| 通过减少 MPI rank 降低 direct RSS | MUMPS MPI2 | diagnostic_only | h3 只降 15.119%，不得替代 ordinary default |
| 最少 rank 复制 | MUMPS MPI1×1 | diagnostic_only | h5 RSS 最低但 Stage4 约 50.891 s（固定 CPU 0-3 对照） |
| 替换 distributed LU backend | SuperLU_DIST | supported backend / negative target result | h5 RSS +14.462%，本目标不推荐 |
| 提前释放 base objects | release-base opt-in | diagnostic_only | h3 只降 5.462%，默认保持 false |
| 单 rank + OpenBLAS threads | 当前 image 不推荐 | diagnostic_only | MPI1×4 KSPSetUp 仍约 1 核，Stage4 48.273 s |
| 目标 p2 h=5/3/2，MPI4 | matrix-free condensed workstation | recommended | h=2 为 13.08 GB |
| h=1.5 或新物理参数 | 无 production 推荐 | not_verified | 先做 qualification |

## 2. Ordinary auxiliary direct

入口是 `python -m src.runners.run_3d_cases ...`。Stage4 DtN 组装完整 `[F C; D H]`，PETSc 默认 `preonly + LU/MUMPS`。这是 ordinary 默认，Task28 没有改变。

适用于回归、可信 reference 与内存允许的生产案例。优点是残差口径直接、迭代调参少；代价是 3D p2 的因子 fill 和峰值 RSS 快速增加。

## 3. Explicit condensed direct

`build_explicit_condensed_operator` 是当前端口 `H=I` 的 reference helper，构造 `F-C D`，再用 direct 求解 FE 系统并回代 auxiliary；非单位 H 会抛 `NotImplementedError`。一般可逆 H 的 exact action 由 matrix-free `F-C H^-1D` 路径处理。显式 Schur 项可能增加存储，不是当前 h=2 低内存推荐路径。

## 4. MUMPS OOC 与 BLR

| 路线 | 启用方式 | 使用条件 | 必须验证 |
|---|---|---|---|
| OOC | `--petsc-direct-solver-profile mumps_ooc` | RAM 不足、磁盘空间和 I/O 足够 | scratch 目录、退出清理、full residual |
| BLR | `--petsc-direct-solver-profile mumps_blr`；额外 option 可覆盖阈值 | 接受近似因子并有 reference | residual、R/T/A、压缩率、RSS |

OOC 和 BLR 都是 direct fallback，不会自动启用。不同 MUMPS/PETSc 版本的参数支持可能变化，运行时以 KSP view 和实际 summary 为准。

Task029 的目标 h5 实测进一步收紧使用边界：OOC worker RSS 下降 13.744%，但需要 559,715,776 bytes scratch，Stage4 为 MPI4 baseline 的 1.539×；BLR `1e-5` 的 true residual 为 `4.704e-3`，数值 Gate 失败。因此 OOC 只保留显式诊断/fallback，BLR 不能因进程返回 0 被视为求解通过。

## 4.1 Task029 direct rank/thread 选择结论

| 选择 | h5 结果 | 能力身份 | 是否改变默认 |
|---|---|---|---|
| MPI4×1 default MUMPS | 原 baseline 14.800 s；2328.145 MiB | ordinary reference | 否 |
| MPI2×1 default MUMPS | h3 RSS -15.119% | best diagnostic in-core point | 否 |
| MPI2×2，固定 CPU 0-3 | 20.687 s；KSPSetUp 约 3.27 核均值 | 时间负向诊断 | 否 |
| MPI1×4，固定 CPU 0-3 | 48.273 s；KSPSetUp 0.999/1.054 核均值/峰值 | `unavailable_in_current_image` | 否 |
| h2 direct | 预测 18.882–27.913 GiB | `not_run` | 否 |

线程运行固定 `OMP_NUM_THREADS=1`，通过共享环境控制 OpenBLAS，并用 CPU affinity 将实际执行封顶在四核预算。NumPy 与 PETSc 加载不同 OpenBLAS runtime，所以 runnable-thread oversubscription 不能完全排除；进程 thread 数增加也不代表 MUMPS 因子化多核。当前 image 不应创建 threaded direct profile；更换 PETSc/MUMPS/BLAS 构建后必须从 Case050 h5 重新资格化。

## 5. Matrix-free condensed workstation profile

入口：

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --config benchmarks/configs/workstation_p2.json \
  --h-nm 2 \
  --results-dir benchmarks/artifacts/iterative \
  --record benchmarks/records/workstation_p2_h2_mpi4.json
```

| 组件 | 固定值/职责 |
|---|---|
| operator | exact matrix-free `F-C H^-1D` |
| coarse | 24 z intervals，25 nodes x 3 = 75D |
| subdomains | 16 个完整 physical z slabs |
| overlap | 0.25 slab width |
| local operator | shifted F |
| local solve | owner-computes ILU(1)，一次 local GMRES/preonly |
| smoother | 两步 fixed inner GMRES (`sm2`) |
| outer | right FGMRES，restart 100，rtol 1e-6，max_it 3000 |
| output | heavy artifacts 与 compact record 分离 |

JSON 是唯一 canonical 默认来源，CLI 只做显式 override。任何 override 偏离已验证组合，`qualified_profile=false`，结果只能作为 experimental。

## 6. 可信停止条件

| Gate | 阈值 |
|---|---:|
| PETSc reported relative residual | <= 1e-6 |
| condensed true residual | <= 1e-6 |
| full augmented true residual | <= 1e-6 |
| reported/condensed 相对差 | <= 1e-8 |
| reported/full 相对差 | <= 1e-8 |
| energy closure absolute error | <= 1e-6 |
| h5/h3/h2 iteration ratio | <= 2.0 |
| h2 total peak RSS | <= 14 GB |

未收敛时严禁把当前场的 R/T/A 标记为 official。可以保留 history、残差、失败阶段和 RSS 用于诊断。

## 7. 已验证结果

| h (nm) | FE DoF | iterations | full residual | total peak RSS | R | T | A_volume |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1201 | 9.84e-7 | 1.99 GB | 0.089022 | 0.442588 | 0.468390 |
| 3 | 198,438 | 993 | 9.93e-7 | 5.08 GB | 0.004613 | 0.583653 | 0.411734 |
| 2 | 615,108 | 1804 | 1.00e-6 | 13.08 GB | 0.001343 | 0.599213 | 0.399444 |

迭代数不单调，因此只称为当前三网格 qualification，不称严格 mesh-independent。

## 8. 参数域外流程

角度、波长、材料、几何、p、MPI 数或 smoother 参数改变后：先在可承受网格运行 direct reference；再运行迭代法；比较 full residual、R/T/A、能量闭合和 RSS；最后把新组合加入 canonical config/manifest。只出现 KSP improvement 或 diagnostic flux 正信号不构成 production qualification。

## 9. 研究路线边界

spectral/GenEO coarse、HPDDM recycling、sampled-Schur、cached-Q、FE-only AMS/HX 和 serial SPILU 都是 `research_only`。它们没有进入当前 runner 的正常参数表，防止用户误把失败探索当作稳定求解器。
