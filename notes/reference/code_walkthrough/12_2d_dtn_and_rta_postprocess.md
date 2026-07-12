# 2D DtN 与 RTA 后处理

## TM DtN

`solve_port_maxwell.py` 先装配物理域 total-field FE 矩阵。对每个上下端口 order：

1. 计算 `alpha_m`、介质 beta 和传播分类；
2. 组装边界 Fourier trace vector；
3. explicit 路径把低秩 outer product 加到 CSR；
4. auxiliary 路径扩展矩阵，加入 FE/modal coupling 与 modal block；
5. top incident mode 加入 RHS；
6. 解后恢复 `E_total` 和 auxiliary amplitudes。

TE DtN 的 `_add_scalar_fourier_port_operators` 独立实现标量 admittance，避免把 TM traction 套到 Ez。

## `power_metrics.py`

| 函数组 | 作用 | 身份 |
|---|---|---|
| `_line_*`, `_fourier_line_coefficients` | probe line Fourier | diagnostic |
| `_compute_*_power_metrics_from_lines` | TM/TE up/down 分解 | diagnostic |
| `_volume_absorption_metrics` | `Im(eps)|E|^2` | official A 候选 |
| `compute_dtn_port_power_metrics` | TM boundary trace | cross-check |
| `compute_dtn_auxiliary_power_metrics` | TM auxiliary amplitudes | DtN official |
| `compute_te_dtn_port_power_metrics` | TE DtN | official/cross-check |

`_attach_absorption_metrics` 把 A_balance、A_volume 和差值放入同一 payload。`compute_near_field_integrals` 使用 `near_field_2d.py` 的固定区域，不参与远场功率归一化。

`_is_propagating` 不要求 lossy `beta` 的虚部为零，而用 `Re(beta)`/`Re(beta^2)` 判断是否携带法向实功率。`_modal_power_on_plane` 始终使用实际 top/bottom port 的边界系数；`reflected_amp/transmitted_amp` 的去相位版本只用于报告。这个区分保证有限有耗基座的端口 T 与域内 `A_volume` 不重复计数。

## 输出

每个 case 保留场文件、`power_metrics.json`、`run_summary.json` 和 solver log；runner 汇总关键 R/T/A。读取时以 `power_source/role` 区分 official/diagnostic，详见 theory `official_and_diagnostic_rta_methods.md`。

## 交叉证据

case 002 要求 auxiliary 与 explicit/trace 一致；case 003 检查 complex material 的 `A_balance≈A_volume`。这两种检查覆盖不同错误，不能互相替代。
