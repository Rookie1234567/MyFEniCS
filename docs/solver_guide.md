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
| 目标 p2 h=5/3/2，内存优先 | Task30 compact physical-slab low-memory profile | experimental | `workstation_memory_success_with_qualifications`；clean h5/h3 为 1.688/3.793 GB；h2 9.375 GB 为历史审阅参考；需显式 flags |
| frozen p2 h=5/3/2，约 8 GiB 硬限制 | Task31 assembled-F-free memory-first profile | experimental | h2 external simultaneous peak 7.898 GiB、legacy internal 8.176 GiB；solve 约为 Task30 的 5.01x；显式 opt-in |
| h=1.5 或新物理参数 | 无 production 推荐 | not_verified | 先做 qualification |

完整命令、outer KSP/local smoother 合法性和组件 flag 身份统一见 [`iterative_solver_ports.md`](iterative_solver_ports.md)。

## 2. Ordinary auxiliary direct

入口是 `python -m src.runners.run_3d_cases ...`。Stage4 DtN 组装完整 `[F C; D H]`，PETSc 默认 `preonly + LU/MUMPS`。这是 ordinary 默认，Task28 没有改变。

### 2.1 Full3D assembly backend 单一选择端口

Review V3 后，普通用户只通过一个字段选择 Full3D 装配：

```python
stage4_full3d_assembly_backend = "standard_full"
# 显式 opt-in：
# stage4_full3d_assembly_backend = "assembly_time_static_condensed"
```

CLI 对应：

```bash
python -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --stage4-full3d-assembly-backend assembly_time_static_condensed
```

`standard_full` 始终是 ordinary default。`assembly_time_static_condensed` 只资格化于 `complex128`、H(curl) Nédélec、first-order axis-aligned affine hexahedron、逐 owned-cell 显式 material tag、fixed rectangular target、global insertion 前 Floquet slave elimination、sparse auxiliary DtN、完整场恢复与 full explicit true residual。curved/distorted hexa、未覆盖的 runtime coefficient/constant、tetra、mixed cell、irregular geometry、regionwise/non-exact local-p、production selective trace 与 condensed iterative profile 会 fail closed，并提示改用 `standard_full`；不会静默 fallback。

旧的三个 condensation 布尔量仅供历史 research runner 内部兼容，不是用户 API。日志、progress 和 summary 会登记 requested/actual backend 与 qualification audit。

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

Task029 Review V2 已技术通过：最终身份保持 `diagnostic_success`、`engineering_success=no`、新 optimized direct profile 为 `none`、h2 为 `not_run`，ordinary default 不变。验收没有把任何 MPI2/OOC/BLR/SuperLU/ordering/threaded 候选提升为推荐配置。

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

## 5.1 Task030 compact physical-slab low-memory experimental profile

Task030 没有替换 ordinary/canonical profile。最终成功求解器仍是 Task27-derived exact condensed operator + 75D wave coarse + 16 physical slabs，只在该架构上增加显式组合：

```bash
--post-smooth --subdomain-local-shift --factor-only-storage \
--ilu-levels 0 --restart 90
```

其关键不是单独降低 ILU fill，而是 symmetric pre/post 两步 smoothing；仅去 overlap 或仅减 fill 都不能保证收敛。local shift 避免保留一份完整 shifted-F，factor-only 在 local PREONLY setup 后只保留因子，restart90 减少 Krylov basis。final implementation HEAD 的 clean h5/h3 复跑分别为 855/962 步、1.687653/3.792912 GB，并通过三残差、80 模态 R/T/A、direct delta 与 h3 绝对/相对内存 Gate。h2 不按 Review V2 重跑，保留同候选 1873 步、9.374729 GB、真残差 `9.972228e-7` 的 reviewed historical dirty-worktree reference；迭代数高于 1200 且参数域外未验证，所以整体仍为 experimental，不属于 strong success。

当前 Task27 ILU1 与 Task30 ILU0 记录的 `global_slab_factor_nnz` 完全相同，因此不能声称已经证明 factor-nnz compression。已观测内存下降主要归因于 factor-only 生命周期、subdomain-local shift、释放 source submatrix/KSP/PC wrapper 和 restart90 的 Krylov basis 缩减。factor-only 只在 qualified local image 的 PETSc 3.24.0 complex build 验证；跨 PETSc 版本必须重跑 action/lifecycle 回归。

Task030 还建立了 nonmatching p2/p1 H(curl) transfer 和 exact Galerkin coarse；它们代数正确，但五个 100 步 solver 候选均明显失败。`hcurl_multilevel.py` 只公开 validated transfer/cache/Galerkin API；Jacobi、p/h multilevel、Woodbury 等失败候选只允许 research runner/tests 直接导入，不属于普通 `src.solvers` 公共 API，更不能理解为可推荐 GMG profile。

## 5.2 Task031 assembled-F-free compact memory-first experimental profile

Task031 面向“机器内存不足，但允许明显增加时间”的场景。它保留 Task030 的 75D wave coarse、16-slab ILU0 symmetric pre/post、local shift、factor-only 与 FGMRES90，再显式增加：

```bash
--overlap-layers 0.125 --matrix-free-fine --compact-lifecycle
```

推荐通过带外部采样与 h2 lock/watchdog 的 wrapper 运行：

```bash
mpiexec -n 4 python -m benchmarks.run_task031_memory_forensics \
  --h-nm 5 --num-slabs 16 --overlap-layers 0.125 \
  --ksp-type fgmres --smoother-ksp-type gmres --restart 90 \
  --max-it 5000 --matrix-free-fine --compact-lifecycle \
  --case-label task031_local --run-dir /tmp/task031_local \
  --verified-clean-sha <full-clean-sha>
```

h2 默认锁定，只有 h5/h3 数值、内存、预测、clean source 与无 swap Gate 通过后才可加 `--unlock-h2`；必须保留 9.5 GiB warning 与 11 GiB termination。Case070 的 frozen MPI4 h5/h3/h2 为 1157/1994/1977 步，external simultaneous worker peak 1.620/3.474/7.898 GiB。Task030 的 9.374729 GiB 是历史采样口径；与 Task31 external peak 对照的观察降幅约 15.8%，与 Task31 legacy internal peak 8.176441 GiB 对照约 12.8%。保守结论是 h2 从约 9.4 GiB 压到约 8.0–8.2 GiB。solve 11982.581 s，约慢 5.01x。因此选择规则是：

```text
速度/吞吐优先且可承受约 9.4 GiB -> Task030 compact profile
内存硬约束约 8 GiB、可接受数小时 -> Task031 memory-first profile
普通使用/参数域外 -> ordinary/canonical profile + 重新资格化
```

Task031 的 adaptive local GMRES PC 实测非线性（linearity error `2.374308e-2`），所以必须与 FGMRES 配对。普通 GMRES 是 `port_implemented_but_incompatible_with_current_adaptive_pc`；TFQMR/BCGS 是 `interface_exposed_not_target_qualified`，runner 会对所有非 FGMRES 路线强制 certification 并 fail closed。fixed Richardson 虽线性，但 200 步 residual 0.7703，不能替代。public MPC form action 对 assembled `F` 的误差 `<1e-15`，solve ledger 中不保留 `F`；这只是 frozen target 的资格证据，不是任意参数的数学收敛保证。

当前“matrix-free fine”精确指 assembled-F-free public MPC form-action path，不是已经缓存优化的低层 element-kernel 实现。释放 `F` 只是一次性的必要生命周期动作；主要时间成本是每次 outer apply 都重复执行 Function 写入、MPC backsubstitution、`ufl.action`、`assemble_vector` 和通信。h5 200-step 为 18.478→58.837 s（3.18x），h2 每步平均成本约 4.74x；不能写成“destroy F 本身导致变慢”。

内存判断以 external simultaneous live-rank RSS 为权威，cgroup 与 legacy internal peak 分开记录。release 后 current RSS 下降只能证明 lifecycle 生效，不能单独构成 solve-peak success。完整端口矩阵见 [`iterative_solver_ports.md`](iterative_solver_ports.md)，配置、records 与限制见 Case070。

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

角度、波长、材料、几何、p、MPI 数或 smoother 参数改变后：先在可承受网格运行 direct reference；再运行迭代法；比较 full residual、R/T/A、能量闭合和 RSS；最后把新组合加入 canonical config/manifest。当前 benchmark 只资格化 13.5 nm、固定 Si、theta=80°（10° grazing）、S polarization 的单点；项目第一阶段 `1–10° grazing + S/P` 是后续规划范围，不等于已经通过。只出现 KSP improvement 或 diagnostic flux 正信号不构成 production qualification。

## 9. 研究路线边界

spectral/GenEO coarse、HPDDM recycling、sampled-Schur、cached-Q、FE-only AMS/HX 和 serial SPILU 都是 `research_only`。它们没有进入当前 runner 的正常参数表，防止用户误把失败探索当作稳定求解器。

## Task034 高阶/Hybrid 与 MPI 边界

Task034 的 S 偏振 fixed-geometry evidence 已覆盖 p3/h3、p4/h5 same-degree closure，并在 p3/h5 对 Full3D/Hybrid 做 MPI1/8/16 identity（MPI32 exploratory）。这不改变 ordinary direct default，也不证明所有 p/h/M 对 MPI 数无关。p2/h1、p3/h2、p4/h3 Full3D 仅完成 assembly 后资源 stop；不得作为 solver pass。graded-h mechanism、未资格化 adaptive runner 和 Task035 planning 不进入 solver selector。
