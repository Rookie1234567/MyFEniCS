# 3D 场重构、RTA 与输出

## 场重构

`common_3d_fields` 提供解析 plane wave、layered Fresnel background、incident mode 和字段相加。scattered/correction 路径必须在后处理前恢复 `E_total`；DtN total-field 路径直接从增广 FE segment 赋值。

H 场由 `curl(E)/(i*k0*mu_r)` 重构。低阶 E 的 curl 会降低 H 后处理阶次，因此 H 误差通常比 E 大；这不是修改 Maxwell 方程的理由。

## official port R/T

`dtn_port_3d._port_power_metrics` 读取 auxiliary amplitudes，扣除 top incident，按 mode power 求 top outgoing R 和 bottom outgoing T。输出同时保存 mode 数、order/polarization 和 trace diagnostics。

## 体吸收

`rta_3d.compute_volume_absorption_3d`：

1. 对 grating/substrate tag 统计 cell 与体积；
2. 使用各自 `epsilon_r=n^2`；
3. 积分 `0.5*k0*Im(epsilon_r)|E_total|^2`；
4. 除以相同 incident power；
5. 输出分项、总 A、与 port/probe/flux 的差。

`power_summary_rows/write_power_summary_csv` 把嵌套 JSON 扁平化，不重新计算物理量。

## diagnostic diffraction

`diffraction_3d.compute_diffraction_orders_3d` 在 probe plane 采样 E/H，提供 E-Fourier、E/H directional fit 和 net flux。它检查 official 结果但不覆盖它。sample count 会按最大 order 进行最低 Nyquist 检查。

## ParaView

`postprocess_3d.save_airbox_3d_fields` 把 complex vector 拆成 real/imag/abs，在 MPI 中只写 owned cells；每 rank `.vtu` 由 `.pvd` 聚合。`domain_tag` 用于筛选材料。`component_l2`、解析误差和全局 max 用 MPI reduction。

## 平层参考

`flat_layer_reference_3d` 计算 Fresnel、probe plane 功率和有限复基座吸收，并与数值 RTA 写一致性差。它是 Stage 4A 参考，不适用于有几何 grating 的解析解。
