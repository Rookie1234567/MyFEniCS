# Outcome Summary

## Task

Stage 4 R/T/A 输出拆分与材料体吸收积分。

## Branch

`codex/20260702-rta-output-volume-absorption`

## Changed Files

- `src/postprocessing/rta_3d.py`
- `src/postprocessing/diffraction_3d.py`
- `src/solvers/dtn_port_3d.py`
- `src/solvers/common_3d_case_flow.py`
- `notes/docs/THEORY_RTA_AND_VOLUME_ABSORPTION.md`
- `notes/outcomes/20260702_rta_output_volume_absorption/*`

## Run Commands

- `python -m compileall -q src`：通过。
- Docker real-mode unittest：失败，原因是 real DOLFINx/PETSc 环境会截断复数场；该结果不作为正式验证。
- Docker complex128 unittest：`python3 -m unittest discover -s src/test -p "test_*.py"`，60 个测试通过，10 个 skipped。
- Stage 4A flat-layer：10/5/3 nm，`dtn_port + auto_propagating`。
- Stage 4B zero-contrast block：10/5/3 nm，保留 block 几何，`n_grating=1+0j`。
- Stage 4B real Si block：10/5/3 nm，`n_grating=n_substrate=0.999002304859+0.00182649365j`。

## Physical Model

所有正式算例使用 `lambda0=13.5 nm`、Si substrate 复折射率 `0.999002304859+0.00182649365j`。real Si block 中 grating 使用相同复折射率；zero-contrast 保留 block 几何但设置 `n_grating=1+0j`。

## Numerical Settings

Stage 4 边界模型为 `dtn_port`，DtN 阶数策略为 `auto_propagating`，DtN assembly 为 `auxiliary`。probe 后处理使用 32 x 32 采样和默认全传播级设置。早期 `zero_order` 诊断试跑走 local Robin sanity branch，结果未纳入正式 metrics。

## Table 1: Run Overview

| case | mesh_nm | stage | dofs | status | elapsed_s | max_rss_mb |
|---|---:|---|---:|---|---:|---:|
| flat_layer | 10 | stage4_flat_layer_sanity | 5335 | completed | 12.558 | 393.5 |
| flat_layer | 5 | stage4_flat_layer_sanity | 39270 | completed | 128.041 | 1732.7 |
| flat_layer | 3 | stage4_flat_layer_sanity | 186235 | completed | 2286.873 | 12467.3 |
| zero_contrast_block | 10 | stage4_block_grating | 6384 | completed | 34.683 | 416.4 |
| zero_contrast_block | 5 | stage4_block_grating | 39270 | completed | 104.164 | 1731.8 |
| zero_contrast_block | 3 | stage4_block_grating | 197136 | completed | 2636.719 | 13201.7 |
| real_si_block | 10 | stage4_block_grating | 6384 | completed | 10.259 | 414.8 |
| real_si_block | 5 | stage4_block_grating | 39270 | completed | 104.212 | 1730.5 |
| real_si_block | 3 | stage4_block_grating | 197136 | completed | 2623.155 | 13213.4 |

## Table 2: Four-Method R/T/A Summary

| case | mesh_nm | method | R | T | A | role | status |
|---|---:|---|---:|---:|---:|---|---|
| flat_layer | 10 | port | 1.000000e+00 | 1.025383e-10 | -1.020143e-09 | primary | ok |
| flat_layer | 10 | probe_eh_fourier | 3.718929e-03 | 2.997539e-11 | 9.962811e-01 | cross_check | ok |
| flat_layer | 10 | net_flux | 1.000000e+00 | -2.199182e-11 | 2.210268e-10 | diagnostic | ok |
| flat_layer | 10 | volume_absorption |  |  | 4.747970e-10 | absorption_check | ok |
| flat_layer | 5 | port | 1.842874e-02 | 1.044098e+00 | -6.252641e-02 | primary | ok |
| flat_layer | 5 | probe_eh_fourier | 6.392455e-01 | 4.357166e-03 | 3.563973e-01 | cross_check | ok |
| flat_layer | 5 | net_flux | 1.515919e+00 | -5.406644e-01 | 2.474582e-02 | diagnostic | ok |
| flat_layer | 5 | volume_absorption |  |  | 2.910111e-02 | absorption_check | ok |
| flat_layer | 3 | port | 1.889043e-03 | 1.071058e+00 | -7.294699e-02 | primary | ok |
| flat_layer | 3 | probe_eh_fourier | 7.620140e-01 | 2.868356e-02 | 2.093025e-01 | cross_check | ok |
| flat_layer | 3 | net_flux | 1.760577e+00 | -8.014460e-01 | 4.086923e-02 | diagnostic | ok |
| flat_layer | 3 | volume_absorption |  |  | 3.395107e-02 | absorption_check | ok |
| zero_contrast_block | 10 | port | 1.000000e+00 | 1.025383e-10 | -1.020139e-09 | primary | ok |
| zero_contrast_block | 10 | probe_eh_fourier | 3.718929e-03 | 2.997565e-11 | 9.962811e-01 | cross_check | ok |
| zero_contrast_block | 10 | net_flux | 1.000000e+00 | -2.199208e-11 | 2.241364e-10 | diagnostic | ok |
| zero_contrast_block | 10 | volume_absorption |  |  | 4.747970e-10 | absorption_check | ok |
| zero_contrast_block | 5 | port | 1.842874e-02 | 1.044098e+00 | -6.252641e-02 | primary | ok |
| zero_contrast_block | 5 | probe_eh_fourier | 6.392455e-01 | 4.357166e-03 | 3.563973e-01 | cross_check | ok |
| zero_contrast_block | 5 | net_flux | 1.515919e+00 | -5.406644e-01 | 2.474582e-02 | diagnostic | ok |
| zero_contrast_block | 5 | volume_absorption |  |  | 2.910111e-02 | absorption_check | ok |
| zero_contrast_block | 3 | port | 1.889043e-03 | 1.071058e+00 | -7.294699e-02 | primary | ok |
| zero_contrast_block | 3 | probe_eh_fourier | 7.620140e-01 | 2.868356e-02 | 2.093025e-01 | cross_check | ok |
| zero_contrast_block | 3 | net_flux | 1.760577e+00 | -8.014460e-01 | 4.086923e-02 | diagnostic | ok |
| zero_contrast_block | 3 | volume_absorption |  |  | 3.395107e-02 | absorption_check | ok |
| real_si_block | 10 | port | 1.000001e+00 | 1.703589e-10 | -8.684792e-07 | primary | ok |
| real_si_block | 10 | probe_eh_fourier | 3.718848e-03 | 3.919008e-11 | 9.962812e-01 | cross_check | ok |
| real_si_block | 10 | net_flux | 9.999998e-01 | -4.870826e-11 | 2.094226e-07 | diagnostic | ok |
| real_si_block | 10 | volume_absorption |  |  | 4.042086e-07 | absorption_check | ok |
| real_si_block | 5 | port | 1.831333e-02 | 1.060863e+00 | -7.917623e-02 | primary | ok |
| real_si_block | 5 | probe_eh_fourier | 6.383845e-01 | 4.426948e-03 | 3.571886e-01 | cross_check | ok |
| real_si_block | 5 | net_flux | 1.515981e+00 | -5.493494e-01 | 3.336810e-02 | diagnostic | ok |
| real_si_block | 5 | volume_absorption |  |  | 3.685029e-02 | absorption_check | ok |
| real_si_block | 3 | port | 1.886333e-03 | 1.090512e+00 | -9.239865e-02 | primary | ok |
| real_si_block | 3 | probe_eh_fourier | 7.620132e-01 | 2.919123e-02 | 2.087956e-01 | cross_check | ok |
| real_si_block | 3 | net_flux | 1.760579e+00 | -8.155431e-01 | 5.496437e-02 | diagnostic | ok |
| real_si_block | 3 | volume_absorption |  |  | 4.300429e-02 | absorption_check | ok |

## Table 3: Consistency Checks

| case | mesh_nm | dR_probe_port | dT_probe_port | dA_flux_port | dA_volume_port | closure_error_port_volume | pass |
|---|---:|---:|---:|---:|---:|---:|---|
| flat_layer | 10 | -9.962811e-01 | -7.256292e-11 | 1.241170e-09 | 1.494940e-09 | 1.494940e-09 | false |
| flat_layer | 5 | 6.208168e-01 | -1.039741e+00 | 8.727223e-02 | 9.162753e-02 | 9.162753e-02 | false |
| flat_layer | 3 | 7.601249e-01 | -1.042374e+00 | 1.138162e-01 | 1.068981e-01 | 1.068981e-01 | false |
| zero_contrast_block | 10 | -9.962811e-01 | -7.256267e-11 | 1.244275e-09 | 1.494936e-09 | 1.494936e-09 | false |
| zero_contrast_block | 5 | 6.208168e-01 | -1.039741e+00 | 8.727223e-02 | 9.162753e-02 | 9.162753e-02 | false |
| zero_contrast_block | 3 | 7.601249e-01 | -1.042374e+00 | 1.138162e-01 | 1.068981e-01 | 1.068981e-01 | false |
| real_si_block | 10 | -9.962820e-01 | -1.311689e-10 | 1.077902e-06 | 1.272688e-06 | 1.272688e-06 | false |
| real_si_block | 5 | 6.200711e-01 | -1.056436e+00 | 1.125443e-01 | 1.160265e-01 | 1.160265e-01 | false |
| real_si_block | 3 | 7.601268e-01 | -1.061321e+00 | 1.473630e-01 | 1.354029e-01 | 1.354029e-01 | false |

## Table 4: Volume Absorption By Region

| case | mesh_nm | A_grating | A_substrate | A_volume_total | A_port_balance |
|---|---:|---:|---:|---:|---:|
| flat_layer | 10 |  | 4.747970e-10 | 4.747970e-10 | -1.020143e-09 |
| flat_layer | 5 |  | 2.910111e-02 | 2.910111e-02 | -6.252641e-02 |
| flat_layer | 3 |  | 3.395107e-02 | 3.395107e-02 | -7.294699e-02 |
| zero_contrast_block | 10 | 0.000000e+00 | 4.747970e-10 | 4.747970e-10 | -1.020139e-09 |
| zero_contrast_block | 5 | 0.000000e+00 | 2.910111e-02 | 2.910111e-02 | -6.252641e-02 |
| zero_contrast_block | 3 | 0.000000e+00 | 3.395107e-02 | 3.395107e-02 | -7.294699e-02 |
| real_si_block | 10 | 4.037291e-07 | 4.794570e-10 | 4.042086e-07 | -8.684792e-07 |
| real_si_block | 5 | 7.281771e-03 | 2.956852e-02 | 3.685029e-02 | -7.917623e-02 |
| real_si_block | 3 | 8.436290e-03 | 3.456800e-02 | 4.300429e-02 | -9.239865e-02 |

## Table 5: Conclusions

| case | mesh_nm | conclusion |
|---|---:|---|
| flat_layer | 10 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| flat_layer | 5 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| flat_layer | 3 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| zero_contrast_block | 10 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| zero_contrast_block | 5 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| zero_contrast_block | 3 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| real_si_block | 10 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| real_si_block | 5 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |
| real_si_block | 3 | code path passes; energy consistency fails; numerical sanity only; not physical benchmark candidate |

## Key Results

本轮实现了正式的 `power_summary.csv`、`port_power.json`、`probe_power.json`、`flux_power.json` 和 `volume_absorption.json` 输出。体吸收来自 `Im(epsilon_r)*|E_total|^2` 的材料区体积分，flat-layer 中 grating 区域按 missing 记录。

## Energy Check

当前 Stage 4 算例的代码路径通过，但 `port/probe_eh_fourier/net_flux/volume_absorption` 的一致性没有整体通过。尤其是 flat-layer 与 zero-contrast 在 5 nm 和 3 nm 上出现 `R+T+A_volume` 明显大于 1，probe 与 port 的 R/T 差异也很大。因此这些结果只能作为 numerical sanity 和后处理接口验证，不能作为物理 benchmark。

## Mesh / DoF / Solver Cost

3 nm hexahedral p1 case 达到约 186k 到 197k N1curl DoF，峰值 RSS 约 12.5 到 13.2 GB，单个 3 nm solve 耗时约 38 到 44 分钟。

## Known Issues

- Stage 4 DtN primary port 与 probe/net-flux 在当前 EUV flat/zero/real block 算例中不一致。
- `zero_order` DtN 诊断分支会走 local Robin sanity branch，flat-layer 结果呈现非物理全反射；正式 metrics 已排除该试跑。
- 本轮没有解决 Stage 4 端口/求解物理口径问题，只把 R/T/A/体吸收输出拆清并量化暴露。

## Next Questions For Review

- ChatGPT 应重点审查 DtN port 的 incident/outgoing modal amplitude 定义和顶部入射源符号。
- 需要确认 `probe_eh_fourier` 的上下行波方向、substrate 复 beta 归一化和 `net_flux` 符号约定。
- 若下一轮修 port 物理口径，应继续用 flat-layer 与 zero-contrast 作为优先回归。
