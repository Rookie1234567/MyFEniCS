# 能力矩阵

状态只使用：`recommended`、`supported`、`experimental`、`research_only`、`diagnostic_only`、`deprecated`、`not_implemented`、`not_verified`。

## 2D

| 能力 | 状态 | MPI/入口 | 当前边界 |
|---|---|---|---|
| TM Nedelec | recommended | serial/MPI，`run_cases` | 主验证偏振 |
| TE scalar | supported | serial/MPI | 与 TM 形式不同 |
| real refractive index | supported | config/CLI | 零对比与 Fresnel 可验证 |
| complex refractive index | supported | complex PETSc | 支持体吸收 |
| x-Floquet | supported | manual 或 MPC | DtN 推荐 manual |
| PML | supported | scattered formulation | 与 port total-field 路径分开 |
| Robin port | supported | port workflow | 局部近似边界 |
| DtN port | recommended | manual + port_total | nonlocal DtN 不使用 mpc_official |
| explicit DtN | supported | `--port-dtn-assembly explicit` | 小阶数验证 |
| auxiliary DtN | recommended | `--port-dtn-assembly auxiliary` | 稀疏增广形式 |
| Fresnel reference | supported | flat interface | 用于界面基准 |
| multi-order R_m/T_m | supported | diffraction postprocess | 传播阶筛选 |
| total R/T/A | supported | postprocessing | official 来源取决于求解路径 |
| volume absorption | supported | complex material | 只在有损区域积分 |
| angle scan | supported | scan runner | 每点仍需 residual gate |
| wavelength scan | supported | scan runner | 材料色散由输入负责 |
| field output | supported | results/artifacts | VTU/PVD 不进 Git |
| mesh/order controls | supported | CLI/config | 新组合需网格收敛检查 |
| serial direct | recommended | ordinary default | 小中型案例 |
| MPI direct | supported | PETSc/MUMPS | 受因子内存限制 |
| production iterative | not_implemented | 无 2D production profile | 当前重点为 3D Stage4 |

## 3D

| 能力 | 状态 | MPI/入口 | 当前边界 |
|---|---|---|---|
| Stage1 airbox | recommended | serial/MPI | 快速 sanity |
| Stage2A double Floquet | supported | MPI | x/y 周期约束 |
| Stage2B PML | experimental | MPI | tensor/decay smoke 已有；尚无独立 canonical record 与生产精度资格 |
| Stage2C Fresnel | experimental | MPI | 解析参考/组合测试已有；旧 p2 精度限制尚未关闭 |
| Stage4 flat-layer sanity | recommended | MPI | 能量与参考解闭环 |
| Stage4 block grating | supported | MPI | 当前目标几何 |
| p1 Nedelec | supported | ordinary CLI | 低阶验证 |
| p2 Nedelec | recommended | ordinary/benchmark | workstation qualification 使用 p2 |
| complex material | supported | complex PETSc | substrate/grating 可吸收 |
| auxiliary DtN | recommended | ordinary Stage4 | 稀疏增广系统 |
| explicit condensed DtN | supported | `condensed_dtn.py` | reference helper 仅支持 verified `H=I`；一般 H 用 matrix-free exact action |
| matrix-free condensed DtN | recommended | benchmark runner | `F-C H^-1 D` |
| MUMPS direct | recommended | ordinary default | h=2 内存超当前工作站 |
| Task29 direct-memory telemetry | recommended | Case050 runner | merge candidate；RSS/cgroup/swap/stage/matrix/factor/CPU/thread 证据 |
| Task29 optimized direct profile | not_implemented | 无 | 所有候选均未通过 h3 工程 Gate |
| MUMPS MPI2 low-rank-count direct | diagnostic_only | Case050 显式 `--mpi-size 2` | h3 RSS 只降 15.119%，不是推荐 profile |
| MUMPS out-of-core | diagnostic_only | `mumps_ooc` profile | h5 只降 13.744%，时间 1.539×，需 scratch/I/O 证据 |
| MUMPS BLR | experimental | PETSc extra options | Task29 `1e-5` 数值 Gate 失败，不是当前候选 |
| SuperLU_DIST direct backend | supported | 显式 PETSc package | backend 有效；目标 h5 RSS +14.462%，不推荐该模型 |
| release-base lifecycle control | diagnostic_only | 显式 opt-in | h3 只降 5.462%，不是 low-memory profile |
| OpenBLAS-threaded direct | diagnostic_only | Case050 `--threads-per-rank` | 当前 image MPI1×4 KSPSetUp 仍约 1 核；capability unavailable |
| MPI4 workstation iterative | recommended | 显式 benchmark | 仅固定 p2/h5,h3,h2 profile |
| h=1.5 iterative | not_verified | 无 canonical record | 不得宣称 production |
| field/mesh output | supported | results/artifacts | rank-local + parallel PVD |
| residual telemetry | recommended | ordinary/benchmark | full true residual 是最终口径 |
| total MPI RSS telemetry | recommended | ordinary/benchmark | 所有 ranks 峰值之和 |
| official modal R/T | recommended | DtN modal amplitudes | residual 通过后才有效 |
| A_volume | recommended | volume integral | 与 official port power 闭合 |
| probe-plane Fourier | diagnostic_only | postprocess | 不替代 official R/T |
| sampled net flux | diagnostic_only | postprocess | 用于定位能流问题 |
| spectral/GenEO coarse | research_only | 历史 Task27 分支 | 目标问题未成功 |
| HPDDM recycling | research_only | 历史研究分支 | 稳定 profile 不依赖 |
| AMS/HX FE-only | research_only | 历史研究分支 | 未形成 full Stage4 production PC |

## Qualification 范围

| 参数 | 已验证值 |
|---|---|
| geometry | 50 x 25 nm period，17 x 25 x 120 nm block，130 nm air，10 nm substrate |
| incidence | theta=80 deg，phi=0 deg，s polarization |
| wavelength | 13.5 nm |
| element | p=2 Nedelec |
| mesh target | h=5/3/2 nm |
| MPI | 4 ranks |
| solver | fixed 75D coarse + 16 physical slabs + sm2 + FGMRES(100) |

任何偏离都自动标记为 `experimental`，必须重新取得 direct 或其他可信参考、三残差、R/T/A、能量闭合和总 RSS 证据。

## 能力到使用、理论和证据的映射

| 能力 | Quick Start | Theory / Code Walkthrough | Benchmark case |
|---|---|---|---|
| 2D TM PML/Floquet | [`10_2d_pml_floquet.md`](../notes/quick_start/10_2d_pml_floquet.md) | [`maxwell_strong_weak_and_fem.md`](../notes/theory/maxwell_strong_weak_and_fem.md)、walkthrough 11 | [`001`](../benchmarks/cases/001_2d_tm_pml_floquet/README.md) |
| 2D TM DtN | [`11_2d_dtn_floquet.md`](../notes/quick_start/11_2d_dtn_floquet.md) | [`dtn_modal_ports_and_condensation.md`](../notes/theory/dtn_modal_ports_and_condensation.md)、walkthrough 12 | [`002`](../benchmarks/cases/002_2d_tm_dtn_equivalence/README.md) |
| 2D TE/TM/复材料 | [`12_2d_te_tm_and_complex_material.md`](../notes/quick_start/12_2d_te_tm_and_complex_material.md) | [`official_and_diagnostic_rta_methods.md`](../notes/theory/official_and_diagnostic_rta_methods.md) | [`003`](../benchmarks/cases/003_2d_te_tm_complex_absorption/README.md) |
| 3D Stage1 | [`20_3d_stage1_airbox.md`](../notes/quick_start/20_3d_stage1_airbox.md) | walkthrough 20 | [`010`](../benchmarks/cases/010_3d_stage1_airbox/README.md) |
| Stage2A/B/C | quick start [`21`](../notes/quick_start/21_3d_stage2a_floquet.md)/[`22`](../notes/quick_start/22_3d_stage2b_pml.md)/[`23`](../notes/quick_start/23_3d_stage2c_fresnel.md) | [`3d_stages_and_validation_ladder.md`](../notes/theory/3d_stages_and_validation_ladder.md) | cases [`011`](../benchmarks/cases/011_3d_stage2a_floquet/README.md)-[`013`](../benchmarks/cases/013_3d_stage2c_fresnel/README.md) |
| Stage4A flat | [`30_3d_stage4a_flat_layer.md`](../notes/quick_start/30_3d_stage4a_flat_layer.md) | walkthrough 22/23 | [`020`](../benchmarks/cases/020_3d_stage4a_flat_dtn/README.md) |
| Stage4B direct | [`31_3d_stage4b_grating_direct.md`](../notes/quick_start/31_3d_stage4b_grating_direct.md) | [`direct_solvers_and_factorization.md`](../notes/theory/direct_solvers_and_factorization.md) | [`021`](../benchmarks/cases/021_3d_stage4b_direct/README.md) |
| exact condensation | iterative quick start | walkthrough 31 | [`022`](../benchmarks/cases/022_dtn_condensation_equivalence/README.md) |
| OOC/BLR | [`32_3d_direct_ooc_blr.md`](../notes/quick_start/32_3d_direct_ooc_blr.md) | walkthrough 30 | [`030`](../benchmarks/cases/030_mumps_ooc_blr/README.md) |
| direct memory/thread forensics | solver guide Task029 | walkthrough 30 | [`050`](../benchmarks/cases/050_stage4_direct_memory_forensics/README.md) |
| MPI4 workstation iterative | [`40_3d_workstation_iterative.md`](../notes/quick_start/40_3d_workstation_iterative.md) | [`iterative_solver_and_preconditioner.md`](../notes/theory/iterative_solver_and_preconditioner.md)、walkthrough 32/33 | [`031`](../benchmarks/cases/031_workstation_iterative/README.md) |
| MPI/p/algebra regression | 环境/验证章节 | walkthrough 50 | [`040`](../benchmarks/cases/040_mpi_p_algebra_regression/README.md) |
