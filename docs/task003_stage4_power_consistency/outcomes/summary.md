# Outcome Summary

## Task

task003_stage4_power_consistency：校准 Stage 4 flat-layer 的 `port`、`probe_eh_fourier`、`net_flux`、`volume_absorption` 与解析 flat-layer reference 的一致性。

## Branch

`codex/20260702-rta-output-volume-absorption`

## Physical Model

本轮使用 EUV flat air/Si layer：

- `lambda0 = 13.5 nm`
- `n_substrate = 0.999002304859 + 0.00182649365j`
- `period_x = period_y = 100 nm`
- `z_min = -50 nm`, `z_max = 100 nm`
- normal incidence, s polarization

解析参考现在区分两套参考面：

- port/volume：物理端口面 `z_top=100 nm`, `z_bottom=-50 nm`
- probe/net_flux：默认 probe 面 `z_top=75 nm`, `z_bottom=-37.5 nm`

## Numerical Settings

- `stage4_boundary_model = dtn_port`
- `stage4_dtn_order_policy = auto_propagating`
- `stage4_dtn_assembly = auxiliary`
- `use_pml = false`
- `nedelec_degree = 1`
- direct LU, serial Docker/DOLFINx complex build

## Key Results

本轮修正了三处核心口径问题：

- `A_volume` 归一化改为 `0.5*k0*Im(epsilon_r)*|E_total|^2`。
- `probe_eh_fourier` 和 E-only 诊断在有损基底中按 bottom probe plane 计算 T，不再用界面 T。
- auxiliary DtN traction 改为 `curl(E) x n`，并在有损底部端口使用端口面相位/衰减计算投影分母和功率。

`flat_layer_reference.json` 和 `power_consistency.json` 已接入 flat-layer 输出。

## Analytic-Only Tests

| test | status | max_error | note |
|---|---|---:|---|
| lossy flat reference attenuation | pass | < 1e-11 | `T_ref` 随 bottom plane 衰减，port/probe 参考面分开记录 |
| analytic E/H -> probe_eh_fourier | pass | < 1e-11 | 恢复 probe 面 `R/T/A` |
| analytic E/H -> net_flux | pass | < 1e-11 | transmitted flux 为正 |
| analytic volume absorption | pass | < 1e-11 | `0.5*k0*Im(eps)*|E|^2` 与 flux loss 一致 |
| lossless substrate A_volume | pass | < 1e-14 | lossless 时体吸收为 0 |

## Flat-Layer FEM Vs Reference

| mesh_nm | method | R | T | A | R_ref | T_ref | A_ref | dR | dT | dA | pass |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 10 | port | 1.000000 | 1.01e-10 | 1.02e-09 | 1.08e-06 | 0.918503 | 0.081496 | 0.999999 | -0.918503 | -0.081496 | no |
| 10 | probe_eh_fourier | 0.003719 | 4.94e-11 | 0.996281 | 1.08e-06 | 0.938232 | 0.061767 | 0.003718 | -0.938232 | 0.934514 | no |
| 10 | net_flux | 1.000000 | 2.22e-11 | 2.21e-10 | 1.08e-06 | 0.938232 | 0.061767 | 0.999999 | -0.938232 | -0.061767 | no |
| 10 | volume_absorption |  |  | 1.02e-09 |  |  | 0.081496 |  |  | -0.081496 | no |
| 5 | port | 0.021696 | 0.918733 | 0.059572 | 1.08e-06 | 0.918503 | 0.081496 | 0.021695 | 0.000230 | -0.021924 | no |
| 5 | probe_eh_fourier | 0.109240 | 0.495117 | 0.395643 | 1.08e-06 | 0.938232 | 0.061767 | 0.109239 | -0.443116 | 0.333876 | no |
| 5 | net_flux | 0.485799 | 0.491299 | 0.022902 | 1.08e-06 | 0.938232 | 0.061767 | 0.485797 | -0.446933 | -0.038864 | no |
| 5 | volume_absorption |  |  | 0.059572 |  |  | 0.081496 |  |  | -0.021924 | no |
| 3 | port |  |  |  |  |  |  |  |  |  | timeout |

## Energy Check

| mesh_nm | check | value | status |
|---:|---|---:|---|
| 10 | `R_port + T_port + A_volume - 1` | 6.22e-15 | pass |
| 5 | `R_port + T_port + A_volume - 1` | -5.12e-14 | pass |
| 5 | `T_port - T_ref_port` | 2.30e-04 | pass |
| 5 | `R_port - R_ref` | 2.17e-02 | not converged |

## Mesh / DoF / Solver Cost

| mesh_nm | cells | N1curl DoF | aux modes | elapsed_s | max_rss_mb | status |
|---:|---:|---:|---:|---:|---:|---|
| 10 | 1500 | 5335 | 708 | 26.8 | 395.6 | completed |
| 5 | 12000 | 39270 | 708 | 115.5 | 1731.0 | completed |
| 3 | 58956 | 186235 | 708 | > 900 |  | stopped at direct LU |

## Zero-Contrast Regression

| mesh_nm | method | flat_value | zero_contrast_value | difference | pass |
|---:|---|---:|---:|---:|---|
| 10 | all |  |  |  | not run |
| 5 | all |  |  |  | not run |
| 3 | all |  |  |  | not run |

zero-contrast 本轮没有继续跑，因为 flat-layer 的 FEM probe/net_flux 仍未达到可作为 merge 前基准的状态，且 h=3 direct LU 未完成。

## Root-Cause Summary

| issue | status | fix |
|---|---|---|
| probe direction/phase | partially fixed | analytic-only 已通过；有损基底 T 改为 bottom probe plane 口径 |
| net flux sign | fixed for analytic-only | analytic E/H 下 `T_flux > 0` 且匹配解析参考 |
| A_volume normalization | fixed | `k0^2` 改为 `k0`，并用解析 flux loss 验证 |
| DtN incident/outgoing amplitude | partially fixed | auxiliary traction 符号改为 `curl(E) x n`；有损底部端口功率改为端口面口径 |
| complex substrate beta power normalization | fixed for port/reference | port T 使用端口面相位衰减；reference 同步输出 port/probe 两套平面 |

## Known Issues

- h=10 p1 对 `lambda0=13.5 nm` 明显欠分辨，仍为近全反射。
- h=5 的 port/volume 已闭合，但仍有约 2.17% 数值反射，尚未达到物理 benchmark。
- FEM `probe_eh_fourier` 和 `net_flux` 在 h=5 仍与 port 明显不一致；analytic-only 表明公式本身正确，下一步应查 FE curl/采样平面/粗网格场诊断。
- h=3 auto_propagating 单进程 direct LU 超过 15 分钟未完成，已停止。

## Next Questions for Review

| question | recommendation |
|---|---|
| 能否进入 zero-contrast / real-block validation？ | 暂不建议。先解决 FEM probe/net_flux 与 port 的差异，并给 h=3 或 p=2/h=5 一个可完成配置。 |
| 当前结果是否可作为 physical benchmark candidate？ | 不能，仍为 diagnostic only。 |
| 下一轮优先级 | 优先做 probe/net_flux 的 FEM 采样诊断，其次尝试 p=2 或迭代求解/分块策略完成 h=3。 |
