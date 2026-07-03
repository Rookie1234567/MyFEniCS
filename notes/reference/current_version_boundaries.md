# 当前版本能力边界说明

本说明用于防止合并后误读当前分支的能力范围。

对应分支：

```text
codex/20260702-rta-output-volume-absorption
```

对应任务闭环：

```text
docs/task002_rta_output_volume_absorption/
docs/task003_stage4_power_consistency/
docs/task004_small_cell_p_convergence_mpi_regression/
```

---

## 1. 当前可以较有信心使用的能力

### 1.1 Stage 4 主功率口径

当前 Stage 4 主线是：

```text
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
unknown = E_total
x/y side = Floquet MPC
z top/bottom = Fourier-DtN auxiliary modal port
```

主功率口径：

```text
port = primary
```

吸收闭合口径：

```text
A_volume = volume_integral_Im_epsilon_E2
P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV
```

在 small-cell flat-layer 中，`R_port + T_port + A_volume - 1` 已经可以达到机器精度量级。

### 1.2 small-cell flat-layer sanity

推荐 sanity benchmark：

```text
stage_case = stage4_flat_layer_sanity
period_x = period_y = 10 nm
air_height = substrate_thickness = 5 nm
lambda0 = 13.5 nm
n_substrate = 0.999002304859 + 0.00182649365j
```

该模型是平坦界面 sanity，不是 3D 光栅散射。

当前结论：

```text
p=2 明显优于 p=1；
port + A_volume 主线稳定；
MPI 1/4/8 不改变主线结果。
```

### 1.3 全阶段 smoke 回归

当前分支中以下路径已完成轻量 smoke：

```text
Stage 1: stage1_airbox
Stage 2A: floquet_airbox
Stage 2B: pml_airbox
Stage 2C: fresnel_interface
Flat-layer sanity: stage4_flat_layer_sanity
3D grating path smoke: stage4_block_grating zero-contrast
```

这些结果说明代码路径没有被 task002/task003/task004 的修改破坏。

---

## 2. 当前必须谨慎解读的能力

### 2.1 probe_eh_fourier / net_flux

当前定位：

```text
probe_eh_fourier = diagnostic only
net_flux = diagnostic only
```

原因：

```text
analytic-only 测试已经通过，说明公式层面基本正确；
但 FEM 场下仍受采样、curl(E) 重构、probe plane 和离散误差影响；
p=2 h=1.5 small-cell 中仍出现 probe 过冲和 net_flux 负分量。
```

因此，当前不能用 probe/net_flux 代替 port 作为主验收。

### 2.2 Stage 2B / Stage 2C

task004 中 Stage 2B/2C 只做了极粗网格 smoke。

当前不能声称：

```text
Stage 2B PML 精度已经通过；
Stage 2C Fresnel 精度已经通过。
```

它们只说明路径可运行。

### 2.3 stage4_block_grating

`stage4_block_grating` 是当前真实 3D 周期矩形柱/光栅散射路径。

当前可以说：

```text
zero-contrast smoke 已通过；
p=1/p=2 路径可以运行；
几何、材料 tag、Floquet、DtN port 和输出结构没有明显崩溃。
```

当前不能说：

```text
真实 100 nm 3D EUV grating 已完成物理收敛 benchmark。
```

真实 100 nm 周期、13.5 nm EUV、h≈1 nm 的计算规模对小电脑不现实，后续应在更高计算资源或更高效求解策略下推进。

---

## 3. 合并后推荐表述

推荐说法：

```text
当前版本完成了 Stage 4 R/T/A 输出重构、A_volume 体吸收、flat-layer 解析参考、small-cell p 收敛、MPI 一致性与全阶段 smoke 回归。port + A_volume 是当前主线。
```

避免说法：

```text
当前版本已完成真实 3D EUV 光栅物理 benchmark。
```

---

## 4. 后续可能任务

后续不需要在当前分支阻塞合并。如果需要继续，可以新开任务：

```text
task005_probe_flux_diagnostic_cleanup
```

重点研究：

```text
probe plane 位置扫描；
采样点加密；
curl(E) 重构 H 的误差；
element-wise Poynting flux integral；
p=2 下 probe/net_flux 过冲原因。
```

真实 100 nm 3D grating benchmark 应作为未来高资源条件下的应用验证目标。
