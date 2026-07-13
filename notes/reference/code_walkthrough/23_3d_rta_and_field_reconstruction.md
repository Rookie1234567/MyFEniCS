# 3D 场重构、R/T/A 与可视化输出

本模块的关键规则是：先形成与 formulation 一致的 total field，再计算 official port power 和体吸收；采样衍射与 Poynting 只做 diagnostic。

## 1. 入口和调用者

| 文件 | 入口 | 调用者 |
|---|---|---|
| `solvers/common_3d_fields.py` | plane wave、layered background、field combine | common case flow |
| `postprocessing/postprocess_3d.py` | `save_airbox_3d_fields(...)` | common case flow |
| `solvers/dtn_port_3d.py` | `_port_power_metrics(...)` | Stage4 DtN solve |
| `postprocessing/rta_3d.py` | `compute_volume_absorption_3d(...)` | common case flow |
| `postprocessing/diffraction_3d.py` | `compute_diffraction_orders_3d(...)` | 可选 diagnostic |

## 2. Formulation 与 total field

| formulation | 求解向量 | 后处理使用的 `E_total` |
|---|---|---|
| analytic total/reference | total 或 correction | 按 wrapper 加回 reference |
| incident-scattered | `E_scat` | `E_scat+E_incident` |
| layered-scattered | `E_scat` | `E_scat+E_layered_background` |
| DtN total-field | augmented FE segment | 直接使用 FE segment |

`common_3d_case_flow::run_prepared_3d_case_flow` 在 solver 之后集中完成这个选择。体吸收若错误使用 `E_scat`，会漏掉背景吸收和干涉项。

## 3. H 场重构

项目采用 `exp(-i omega t)`，代码单位下：

$$H_{code}=\frac{curlE}{i k_0\mu_r}.$$

`diffraction_3d::_h_from_curl_function` 和场输出遵循同一约定。Nedelec p 阶 E 的 curl 阶次更低，因此 H 误差可高于 E；这是离散后处理特性，不应通过改 Maxwell 符号“修正”。

## 4. Official port R/T

Stage4 official R/T 来自 `dtn_port_3d::_port_power_metrics`：

1. 读取每个辅助 total-field projection；
2. top 减去已知 incident projection；
3. bottom 直接作为 outgoing amplitude；
4. 在实际 top/bottom boundary phase 上计算 unit-cell power；
5. 只累计 propagating order/polarization；
6. 除以 `modes_3d::incident_power_3d`。

输出记录 `power_source=dtn_port_modal_amplitudes`、端口参考 z、mode count、Rayleigh warnings 和 amplitude convention。它是 official；boundary trace/采样 fit 只交叉检查。

## 5. 体吸收

`rta_3d::compute_volume_absorption_3d(mesh_data,cfg,E_total,...)` 对 grating 与 substrate tag 分别执行：

$$P_{abs,r}=\frac{k_0}{2}\int_{\Omega_r}
\operatorname{Im}(\epsilon_{r})|E_{total}|^2\,dV.$$

公共真空常数已按项目 code units 省略；分子和入射功率使用同一 convention，归一化 A 不受该公共常数影响。函数同时记录每个 tag 的 global cell count、volume、absorbed power、A 分项和总和。

PML、空气和 ghost cells 不进入吸收积分。每个 rank 积分 owned local cells，MPI allreduce 得到全局值。

## 6. 能量字段

```text
A_balance = 1 - R_total - T_total
A_volume_total = A_grating + A_substrate
closure = 1 - R_total - T_total - A_volume_total
```

`common_3d_case_flow::_merge_volume_closure_into_dtn_port_outputs` 把独立体积分并入 port payload。`power_summary_rows/write_power_summary_csv` 只扁平化，不重新计算或替换物理值。

## 7. Diagnostic diffraction

`diffraction_3d::compute_diffraction_orders_3d` 可在 top/bottom probe plane 采样 E/H：

- `_fourier_e_coefficient`：E-only Fourier coefficient；
- `_fit_directional_eh_amplitudes_for_order`：E/H directional fit；
- `_sampled_flux_code_units`：采样 Poynting net flux；
- `_validate_sample_counts`：按最大 order 检查最低采样数。

这些方法受 probe 位置、条件数、采样 alias 和上下行分离影响，字段必须标记 diagnostic。它们不得覆盖 auxiliary official R/T，也不得为了闭合而调换结果源。

## 8. 场输出、PETSc/MPI ownership 与 shape

`postprocess_3d::save_airbox_3d_fields` 把 H(curl) 解插值/投影到可视化空间，写出 E/H 的 real、imag 和 magnitude，以及 domain tag。complex vector 每个点有 3 分量；可视化数组 shape 与输出 mesh points/cells 对齐，不等于原 Nedelec coefficient shape。

MPI 时每个 rank 只写 owned cells 的 `.vtu`，`.pvd` 聚合所有 piece；这避免 ghost cell 被重复计数或在 ParaView 中形成重影。`component_l2`、global max 和解析误差使用 MPI reduction。

求解阶段的 PETSc FE vector 仍按 row ownership 分布，场函数只借用/复制其 FE segment；后处理不拥有原 KSP 或增广矩阵。case flow 必须在 RTA 与文件写完后再销毁这些 solver 对象。

## 9. 一次真实调用顺序

```text
Stage4 augmented solve
-> E_total from FE segment + MPC backsubstitution
-> dtn_port_3d::_port_power_metrics
-> save_airbox_3d_fields
-> optional compute_diffraction_orders_3d
-> compute_volume_absorption_3d
-> merge closure
-> write power JSON/CSV and run_summary
```

iterative Case031 在回代 auxiliary 后调用相同 official RTA 逻辑，并在 RTA 前先通过 reported、condensed 和 full residual Gate。

## 10. 结果判读

| 字段 | 判断 |
|---|---|
| `R_total/T_total` | 查 `power_source` 和 mode list |
| `A_volume_total` | 查材料分项、tag cell count 和 total field |
| closure | 守恒一致性，不是网格收敛证明 |
| probe/flux | 看 role，应为 diagnostic |
| field PVD | 检查材料内场、边界和周期连续性 |
| residual | 先于 RTA 判断线性解可信度 |

## 11. 测试与 benchmark

- `test_11/test_14`：order、DtN mode 与功率 helper。
- Case020：平层解析 sanity。
- Case021：target direct official RTA。
- Case031：h5/h3/h2 iterative official RTA、残差和内存。
- `test_26_documentation_contract.py`：official/diagnostic 文档身份与链接。

## 12. 限制

绝对 code-unit 功率不能在 2D 与 3D 模块间直接比较；各自归一化的 R/T/A 可比较物理比例。sampled diffraction 不具备 official 身份。对新材料、角度或 Rayleigh 邻域必须重新检查 mode set、采样和网格。定义详见 [`../../theory/official_and_diagnostic_rta_methods.md`](../../theory/official_and_diagnostic_rta_methods.md)。
