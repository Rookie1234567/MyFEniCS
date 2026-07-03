# Outcome Summary

## Task

task004_small_cell_p_convergence_mpi_regression：建立 small-cell flat-layer 的 p=1/p=2 收敛、MPI 1/4/8 一致性和全阶段轻量回归记录。

## Branch

`codex/20260702-rta-output-volume-absorption`

## Read Context

本轮开始前已阅读 `docs/task003_stage4_power_consistency/review_report.md` 和本任务 `task.md`。术语沿用 task4：`stage4_flat_layer_sanity` 是平坦界面 sanity；`stage4_block_grating` 才是 3D 周期矩形柱/光栅散射路径。

## Physical Model

small-cell flat-layer 设置为 `period_x=period_y=10 nm`，空气和基座厚度均为 `5 nm`，`lambda0=13.5 nm`，`n_substrate=0.999002304859+0.00182649365j`，normal incidence，s polarization，`dtn_port + auto_propagating + auxiliary`，不使用 PML。

完整结果保留在本地 `results/3D_*_YYYYMMDD_HHMMSS/`；`outcomes/raw_runs/` 只归档轻量 JSON/TXT/CSV。

## 表 1：p=1 / p=2 收敛性总表

| p | mesh_nm | cells | dofs | aux_modes | R_port | T_port | A_volume | closure | R_ref | T_ref | A_ref | dR | dT | dA | elapsed_s | max_rss_mb | pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2.7 | 64 | 300 | 4 | 3.169e-03 | 9.894e-01 | 7.418e-03 | -1.55e-15 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 3.168e-03 | -2.122e-03 | -1.047e-03 | 10.05 | 275.4 | pass |
| 1 | 2.0 | 150 | 636 | 4 | 5.938e-04 | 9.915e-01 | 7.938e-03 | -8.55e-15 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 5.927e-04 | -6.610e-05 | -5.266e-04 | 8.87 | 280.1 | pass |
| 1 | 1.5 | 392 | 1520 | 4 | 1.755e-04 | 9.917e-01 | 8.155e-03 | -1.11e-16 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 1.744e-04 | 1.359e-04 | -3.103e-04 | 9.95 | 285.2 | pass |
| 1 | 1.0 | 1000 | 3630 | 4 | 6.616e-05 | 9.917e-01 | 8.262e-03 | -2.22e-15 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 6.507e-05 | 1.380e-04 | -2.030e-04 | 11.05 | 318.0 | pass |
| 2 | 4.0 | 36 | 1148 | 4 | 5.908e-06 | 9.916e-01 | 8.414e-03 | 2.44e-15 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 4.824e-06 | 4.605e-05 | -5.087e-05 | 11.63 | 288.7 | pass |
| 2 | 3.0 | 64 | 1944 | 4 | 5.908e-06 | 9.916e-01 | 8.414e-03 | 3.11e-14 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 4.824e-06 | 4.605e-05 | -5.087e-05 | 14.09 | 300.0 | pass |
| 2 | 2.0 | 150 | 4312 | 4 | 1.643e-06 | 9.915e-01 | 8.454e-03 | -2.33e-15 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 5.589e-07 | 1.002e-05 | -1.058e-05 | 14.34 | 353.8 | pass |
| 2 | 1.5 | 392 | 10740 | 4 | 1.241e-06 | 9.915e-01 | 8.461e-03 | -1.11e-15 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 1.569e-07 | 3.249e-06 | -3.406e-06 | 21.60 | 548.5 | pass |

`pass` 表示该行主线 `port + A_volume` 完成并满足 `|R_port + T_port + A_volume - 1| < 1e-10`，不表示 probe/net_flux 已经成为主验收口径。

## 表 2：probe/net_flux 与 port 的差异

| p | mesh_nm | R_probe-R_port | T_probe-T_port | A_probe-A_volume | R_flux-R_port | T_flux-T_port | A_flux-A_volume | note |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2.7 | -1.572e-03 | -1.783e-01 | 1.799e-01 | 1.835e-01 | -1.805e-01 | -3.064e-03 | p=1 probe/net_flux 明显偏离 port |
| 1 | 2.0 | 6.329e-03 | -7.777e-02 | 7.144e-02 | 9.109e-02 | -8.904e-02 | -2.049e-03 | p=1 随网格改善但仍为诊断 |
| 1 | 1.5 | 3.528e-03 | -4.836e-02 | 4.483e-02 | 5.339e-02 | -5.120e-02 | -2.187e-03 | p=1 随网格改善但仍为诊断 |
| 1 | 1.0 | 3.684e-03 | -2.949e-02 | 2.580e-02 | 3.484e-02 | -3.212e-02 | -2.719e-03 | p=1 最细网格仍未达到 port 口径 |
| 2 | 4.0 | 7.240e-04 | -5.496e-02 | 5.424e-02 | 5.834e-02 | -5.575e-02 | -2.587e-03 | p=2 port 已很准，probe/net_flux 仍偏 |
| 2 | 3.0 | 7.240e-04 | -5.496e-02 | 5.424e-02 | 5.834e-02 | -5.575e-02 | -2.587e-03 | 与 h=4.0 接近 |
| 2 | 2.0 | 3.575e-06 | -5.303e-03 | 5.299e-03 | 7.466e-03 | -5.309e-03 | -2.157e-03 | probe 明显改善；net_flux 仍偏离 port |
| 2 | 1.5 | 2.061e-04 | 2.916e-02 | -2.937e-02 | -2.710e-02 | 2.898e-02 | -1.873e-03 | probe 过冲，net_flux R 为负；不可作为主验收 |

## 表 3：MPI 一致性

| p | mesh_nm | ranks | R_port | T_port | A_volume | closure | dR_vs_rank1 | dT_vs_rank1 | dA_vs_rank1 | elapsed_s | max_rss_mb | pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1.5 | 1 | 1.755e-04 | 9.917e-01 | 8.155e-03 | -1.11e-16 | 0 | 0 | 0 | 10.66 | 285.2 | pass |
| 1 | 1.5 | 4 | 1.755e-04 | 9.917e-01 | 8.155e-03 | 2.66e-15 | 2.486e-17 | 2.665e-15 | 1.232e-16 | 10.14 | 292.4 | pass |
| 1 | 1.5 | 8 | 1.755e-04 | 9.917e-01 | 8.155e-03 | 0 | 1.228e-17 | 0 | 8.674e-17 | 12.62 | 290.6 | pass |
| 2 | 3.0 | 1 | 5.908e-06 | 9.916e-01 | 8.414e-03 | 3.11e-14 | 0 | 0 | 0 | 12.46 | 300.6 | pass |
| 2 | 3.0 | 4 | 5.908e-06 | 9.916e-01 | 8.414e-03 | 8.88e-16 | -1.063e-17 | -2.986e-14 | -2.862e-16 | 12.72 | 299.8 | pass |
| 2 | 3.0 | 8 | 5.908e-06 | 9.916e-01 | 8.414e-03 | -4.11e-15 | -7.755e-18 | -3.486e-14 | -3.018e-16 | 16.49 | 305.6 | pass |

MPI 主线阈值采用 `|dR|, |dT|, |dA_volume| < 1e-8`，`|dclosure| < 1e-10`。probe/net_flux 仍只作为 diagnostic 信息保存在 `mpi_consistency.csv`。

## 表 4：全阶段轻量回归

| stage | stage_case | command_summary | status | elapsed_s | max_rss_mb | key_metric | note |
|---|---|---|---|---:|---:|---|---|
| Stage 1 | stage1_airbox | stage1 normal p1 h500 | completed | 2.55 | 272.7 | residual=2.715e-18, dofs=57 | smoke 完成 |
| Stage 2A | floquet_airbox | floquet oblique p1 h500 | completed | 3.95 | 276.2 | residual=0, dofs=54 | smoke 完成 |
| Stage 2B | pml_airbox | pml normal p1 h500 | completed | 98.84 | 4032.9 | residual=0, pml_proxy=1.002817 | PML 路径 smoke，不作为 PML 精度验收 |
| Stage 2C | fresnel_interface | fresnel normal p1 h500 | completed | 100.36 | 4034.7 | residual=3.845e-16, R_err=3.857e-04, T_err=0.743538 | 粗网格/PML smoke，不作为 Fresnel 精度验收 |
| Flat-layer sanity | stage4_flat_layer_sanity | small-cell p1 h2.7 | completed | 6.21 | 278.2 | R=0.003169, T=0.989412, Avol=0.007418, closure=-1.554e-15 | small-cell 平坦界面 sanity；不是 grating benchmark |
| 3D grating path smoke | stage4_block_grating | zero-contrast block p1 h5 | completed | 9.71 | 278.9 | R+T=1, Avol=0, closure=2.887e-15 | zero-contrast smoke，仅验证 block grating 路径 |

Stage 2B/2C 使用很粗的 smoke 配置，目的是检查路径不崩溃，不作为 PML/Fresnel 物理精度验收。`stage4_block_grating` zero-contrast 也只验证 3D grating 路径、tag、输出和后处理不崩溃。

## 表 5：最终判断

| 问题 | 回答 |
|---|---|
| p=2 是否比 p=1 更快收敛？ | 是。p=2 h=4.0、DoF=1148 时 dR≈4.82e-6，已显著好于 p=1 h=1.5、DoF=1520 的 dR≈1.74e-4；p=2 h=1.5 时 dR≈1.57e-7。 |
| probe_eh_fourier 是否因 p=2 明显改善？ | 部分改善但不稳定。p=2 h=2.0 时 probe-port 差异明显缩小；p=2 h=1.5 出现 T 过冲和负 A_probe，因此仍为 diagnostic only。 |
| net_flux 是否因 p=2 明显改善？ | 没有稳定改善。p=2 h=2.0 的 net_flux 比 p=1 好一些，但 p=2 h=1.5 出现负 R_flux；仍不能作为主验收口径。 |
| MPI 4/8 与串行是否一致？ | 是。p=1 h=1.5 与 p=2 h=3.0 的 4/8 ranks 主线 R/T/A_volume 差异均低于 1e-8，closure 差异低于 1e-10。 |
| 全阶段轻量回归是否通过？ | 通过。Stage 1、Stage 2A/2B/2C、flat-layer sanity、stage4_block_grating zero-contrast smoke 均 completed。 |
| 当前分支是否可以考虑合并？ | 可考虑进入审查，但仍建议重点审查 p=2 probe/net_flux 异常和 Stage 2B/2C 粗网格 smoke 指标；真实 100 nm grating 仍不是本轮验收目标。 |

## Key Results

- `port + A_volume` 主线在所有 small-cell p/h case 中都闭合到机器精度量级。
- p=2 的端口结果在更粗网格和相近 DoF 下明显优于 p=1，是后续 flat-layer sanity 的更优主线选择。
- probe_eh_fourier 与 net_flux 在 FEM 场下仍不是稳定主线；p=2 能改善部分网格，但不能消除诊断异常。
- MPI 1/4/8 对主线功率结果一致，未发现并行改变 `R_port/T_port/A_volume` 的问题。
- 全阶段轻量回归完成，但真实 100 nm real Si block grating 没有运行，也不是本任务验收目标。

## Known Issues

- `p=2,h=1.5` 的 probe_eh_fourier 出现 `T_probe > 1` 和负 `A_probe`，net_flux 出现负 `R_flux`；这说明内部采样/curl 后处理仍需单独诊断。
- Stage 2B/2C 的 smoke run 使用极粗网格，部分物理指标不应解读为精度验证。
- `stage4_block_grating` zero-contrast 使用低成本设置，只证明代码路径完成，不代表真实 grating benchmark 已完成。

## Next Questions for Review

- 是否接受 p=2 port/A_volume 作为 small-cell flat-layer 的标准 sanity benchmark？
- 下一轮是否专门诊断 probe/net_flux 的 p=2 过冲、负 flux 分量与采样/curl 重构关系？
- 合并前是否需要把 small-cell benchmark 固化成自动化测试或脚本入口？
