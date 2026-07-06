# DtN Port Modal Power 公式

## 变量约定

对每个 DtN port modal channel `j`：

```text
a_j      = auxiliary unknown = total-field modal projection
i_j      = incident projection on top port mode
b_j      = outgoing modal amplitude
phi_j    = boundary phase at the physical port plane
P_inc    = incident_power_code_units
```

top 端口：

```text
b_j = a_j - i_j
```

bottom 端口：

```text
b_j = a_j
```

写入输出时：

```text
auxiliary_amplitude_total_projection = a_j
incident_projection = i_j
outgoing_amplitude = b_j
outgoing_amplitude_at_boundary = b_j * phi_j
```

## 单模态功率

代码使用 `mode_power(...)` 计算单位振幅端口模态穿过一个周期单元的功率。对有损 bottom substrate，先把 outgoing amplitude 推到物理 bottom port plane：

```text
E_boundary = b_j * phi_j * e_j
P_j = mode_power(k_j, E_boundary, outward_normal_j)
```

等价于当前实现里的：

```text
P_j = _mode_power_at_boundary(mode, cfg, b_j)
```

归一化功率：

```text
power_ratio_j = P_j / P_inc
```

只有 propagating 模态进入总功率：

```text
R_total = sum(power_ratio_j for top propagating modes)
T_total = sum(power_ratio_j for bottom propagating modes)
R_plus_T = R_total + T_total
A_balance = 1 - R_total - T_total
```

## 体吸收闭合

体吸收来自材料区体积分：

```text
P_abs = integral 0.5 * k0 * Im(epsilon_r) * |E_total|^2 dV
A_volume_total = P_abs / P_inc
```

官方能量闭合字段：

```text
R_plus_T_plus_A_volume_dtn_port_modal
    = R_total_dtn_port_modal + T_total_dtn_port_modal + A_volume_total

energy_closure_error_dtn_port_modal_volume
    = R_total_dtn_port_modal + T_total_dtn_port_modal + A_volume_total - 1
```

当前兼容字段保持一致：

```text
R_total = R_total_dtn_port_modal
T_total = T_total_dtn_port_modal
R_plus_T = R_plus_T_dtn_port_modal
energy_closure_error_port_volume = energy_closure_error_dtn_port_modal_volume
```

## 输出口径

官方：

```text
method = port
role = primary
power_source = dtn_port_modal_amplitudes
reference = top=physical_z_max; bottom=physical_z_min
```

诊断：

```text
diagnostic_eh_fourier_probe
diagnostic_e_only_fourier_probe
diagnostic_sampled_net_flux
```

这些诊断值可以用于发现 probe plane 或采样误差，但不能覆盖官方 `R_total/T_total`。
