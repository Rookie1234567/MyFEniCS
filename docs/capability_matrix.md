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
| Stage2B PML | supported | MPI | 用于开放边界验证 |
| Stage2C Fresnel | supported | MPI | 平坦界面参考 |
| Stage4 flat-layer sanity | recommended | MPI | 能量与参考解闭环 |
| Stage4 block grating | supported | MPI | 当前目标几何 |
| p1 Nedelec | supported | ordinary CLI | 低阶验证 |
| p2 Nedelec | recommended | ordinary/benchmark | workstation qualification 使用 p2 |
| complex material | supported | complex PETSc | substrate/grating 可吸收 |
| auxiliary DtN | recommended | ordinary Stage4 | 稀疏增广系统 |
| explicit condensed DtN | supported | `condensed_dtn.py` | exact Schur，可显式构造 |
| matrix-free condensed DtN | recommended | benchmark runner | `F-C H^-1 D` |
| MUMPS direct | recommended | ordinary default | h=2 内存超当前工作站 |
| MUMPS out-of-core | supported | `mumps_ooc` profile | scratch 容量和 I/O 敏感 |
| MUMPS BLR | experimental | PETSc extra options | 仅作为内存 fallback |
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
