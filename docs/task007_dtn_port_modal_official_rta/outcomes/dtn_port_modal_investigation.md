# DtN Port Modal 调查记录

## 结论

本轮确认：当前 `src/solvers/dtn_port_3d.py` 的 Stage 4 `dtn_port + auxiliary` 路径已经包含 top/bottom 端口模态系数。辅助未知量 `a_j` 不是“直接反射振幅”的裸变量，而是端口总场在第 `j` 个端口模态上的投影。

因此官方 R/T 的正确读取方式是：

- top port：`outgoing_amplitude_j = auxiliary_total_projection_j - incident_projection_j`
- bottom port：`outgoing_amplitude_j = auxiliary_total_projection_j`
- 只把 propagating 模态的 outgoing power 纳入 R/T。

本轮已把 Stage 4 dtn_port 主线的官方 power source 统一为：

```text
dtn_port_modal_amplitudes
```

E/H Fourier probe、E-only Fourier probe、sampled net flux 全部只作为 diagnostic。

## Auxiliary Unknown 的定义和索引

在 `solve_stage4_dtn_port_total_field(...)` 中，代码先用 `outgoing_port_modes_3d(cfg)` 选择 top/bottom 端口模态。每一个 `PortMode3D` 对应一个 auxiliary unknown。

索引关系为：

```text
auxiliary_index = modes 列表中的顺序
augmented_global_dof = n_fe + auxiliary_index
```

增广系统中的 modal equation 是：

```text
a_j - projected_total_field_j = 0
```

所以 `a_j` 的物理含义是端口总场投影。top 端口总场中含入射波，计算反射 outgoing amplitude 时必须减去 incident projection；bottom 端口没有入射源，total projection 就是透射 outgoing amplitude。

## 当前输出文件

本轮后 `dtn_port_3d.py` 会写出：

- `port_power.json`
- `port_power.csv`
- `dtn_port_power_metrics_3d.json`
- `dtn_port_diffraction_orders_3d.json`
- `dtn_port_diffraction_orders_3d.csv`
- `dtn_auxiliary_amplitudes_3d.json`

`port_power.json` 是当前官方 R/T/A 入口，关键字段包括：

```text
power_source = dtn_port_modal_amplitudes
R_total
T_total
R_total_dtn_port_modal
T_total_dtn_port_modal
R_plus_T_dtn_port_modal
A_volume_total
R_plus_T_plus_A_volume_dtn_port_modal
energy_closure_error_dtn_port_modal_volume
orders[*].outgoing_amplitude
orders[*].outgoing_amplitude_at_boundary
orders[*].modal_power_code_units
orders[*].power_ratio
```

## Reference Plane

官方 port modal power 的参考面是物理端口边界：

- top：`physical_z_max`
- bottom：`physical_z_min`

对应输出字段：

```text
dtn_port_top_reference_z
dtn_port_bottom_reference_z
reference_planes.top_z
reference_planes.bottom_z
```

对于有损 substrate，bottom modal power 使用 `_mode_boundary_phase(mode, cfg)` 把 outgoing amplitude 推到 bottom 物理边界面后再算功率。因此 `T_total_dtn_port_modal` 是 bottom port plane 的透射功率，不是界面处透射功率。

## Lossy Substrate 归一化

`incident_power_code_units = incident_power_3d(cfg)`，以入射平面波在一个周期单元上的入射功率归一化。

bottom 端口在有损介质中传播时，`boundary_phase` 包含从 modal reference 到物理边界面的相位/衰减。功率计算使用：

```text
P_j = _mode_power_at_boundary(mode, cfg, outgoing_amplitude_j)
R_j or T_j = P_j / incident_power_code_units
```

本轮 flat-layer p=1/p=2 实跑中，`R_total + T_total + A_volume_total - 1` 分别为 `0.0` 和 `6.66e-16`，说明 port modal power 与 volume absorption 的代码单位闭合。

## 与 E/H Fourier Probe 的关系

`src/postprocessing/diffraction_3d.py` 的 E/H Fourier probe 是从内部 probe plane 上采样有限元场，并用 E/H directional fitting 拆分 up/down 波。它的参考面是 probe plane：

- top probe：位于 grating 顶部和 top port 之间
- bottom probe：位于 interface 和 bottom port 之间

因此它与 DtN port modal amplitude 有两个差别：

1. 参考面不同。
2. probe 方法依赖采样和有限元 curl 重建，粗网格或 probe 位置不足时会出现明显偏差。

本轮已经把该路径标记为：

```text
diagnostic_eh_fourier_probe
```

它不再作为 Stage 4 dtn_port 官方 R/T/A。

## 实跑观察

70 nm block grating，p=2，h=5，MPI=8：

```text
official dtn port modal:
R = 7.079669e-04
T = 9.646033e-01
A_volume = 3.468869e-02
R + T + A_volume = 1.0000000000000075

diagnostic E/H Fourier probe:
R = 1.630145e-02
T = 7.522551e-01
```

这说明之前从 probe-plane fitting 得到的高度敏感性不能直接当作官方 R/T/A 结论。官方 port modal 口径下，70 nm 与 150 nm 仍有差异，但差异主要体现在有损材料体吸收随端口距离增加而变化。
