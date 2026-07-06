# 当前版本能力边界说明

本说明用于防止合并后误读当前分支的能力范围。

对应分支：

```text
codex/20260706-target-50x25x140-oblique80-official-benchmark
```

对应任务闭环：

```text
docs/task002_rta_output_volume_absorption/
docs/task003_stage4_power_consistency/
docs/task004_small_cell_p_convergence_mpi_regression/
docs/task005_stage4_real_grating_memory_estimation/
docs/task006_reduced_height_grating_convergence_memory/
docs/task007_dtn_port_modal_official_rta/
docs/task008_70nm_official_convergence_benchmark/
```

---

## 0. task008 目标几何 80° 斜入射本机边界

task008 在 task007 的 official DtN-port modal R/T/A 口径上，固定如下目标几何和入射：

```text
period = 50 x 25 nm
domain = 50 x 25 x 140 nm
grating = 17 x 25 x 120 nm
substrate_thickness = 10 nm
top_air_above_grating = 10 nm
air_height = 130 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s, E along y
n_substrate = n_grating = 0.999002304859 + 0.00182649365j
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
power_source = dtn_port_modal_amplitudes
```

几何和入射验证：

```text
grating_width_y = period_y = 25 nm 合法支持，未使用 24.999 nm fallback；
kx = 0.458350341046137
ky = 0
kz = -0.0808195317433606
Floquet phase x = -0.600741134898 - 0.799443612046j
Floquet phase y = 1
k dot E = 0
DtN mode count = top 40 + bottom 40 = 80
```

本机 default MUMPS direct 边界：

```text
p=1:
  completed direct: h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
  first failed direct: 未尝试 h < 1 nm

p=2:
  completed direct: h = 5, 4, 3, 2.5, 2 nm
  first failed direct: h = 1.5 nm
  failure stage: stage4_dtn_augmented_ksp_setup
  returncode: 9 / signal 9 / Killed

p=2 h=1 nm:
  assemble-only timeout at stage4_dtn_base_matrix_assembled
  estimated AIJ matrix = 10.313 GB
  RSS upper = 14.129 GB
  swap delta ≈ 33.4 GB
```

当前建议使用的本机 official benchmark 主点：

```text
p=2 h=2 nm, personal-computer best-effort direct benchmark:
  R = 0.0013429328462348958
  T = 0.5992132294442478
  A_volume = 0.3994438377095067
  R + T + A_volume = 0.9999999999999893
  closure = -1.07e-14
```

注意：

```text
p=1 h=1 虽然能完成，但与 p=2 finest completed 仍不接近，不应作为最终物理收敛解；
p=2 h=2 是当前个人电脑 best-effort direct benchmark，不是最终网格收敛物理解；
p=2 h=5 的 R≈0.089 明显受粗网格影响，不应作为真实物理反射率结论；
p=2 h=1.5 的 assemble-only AIJ 矩阵约 3.20 GB，但 direct MUMPS 在 KSP setup 被 kill，瓶颈来自 LU fill-in / solver workspace；
后续若要推进 p=2 h=1.5 或更细网格，应单独评估 tuned MUMPS OOC 或迭代法。
```

主要记录：

```text
docs/task008_70nm_official_convergence_benchmark/outcomes/summary.md
docs/task008_70nm_official_convergence_benchmark/outcomes/assemble_matrix_scale.csv
docs/task008_70nm_official_convergence_benchmark/outcomes/official_convergence.csv
docs/task008_70nm_official_convergence_benchmark/outcomes/failure_boundary.md
```

---

## 1. task007 official DtN port modal 口径

task007 已把 Stage 4 `dtn_port` 主线的 official R/T/A 统一为：

```text
power_source = dtn_port_modal_amplitudes
```

含义：

```text
R_total = R_total_dtn_port_modal
T_total = T_total_dtn_port_modal
A_volume_total = volume_integral_Im_epsilon_E2
energy_closure_error_port_volume
  = R_total_dtn_port_modal + T_total_dtn_port_modal + A_volume_total - 1
```

probe-plane 方法现在只作为 diagnostic：

```text
diagnostic_eh_fourier_probe
diagnostic_e_only_fourier_probe
diagnostic_sampled_net_flux
```

不要再把 E/H Fourier probe 的 `R/T` 当作 Stage 4 dtn_port official 结论。

本轮 height scan 的 `T_total` 是 bottom physical port plane 上的功率。由于 substrate 为有损 Si，70 / 110 / 130 / 150 nm 的 bottom port reference plane 不同，`T_total` 随 substrate 厚度变化是当前定义下的预期现象。若要比较不同 total height 是否物理等价，下一轮应新增统一 reference plane 或界面处外推功率。

主要记录：

```text
docs/task007_dtn_port_modal_official_rta/outcomes/summary.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_modal_investigation.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_power_formula.md
```

---

## 2. task006 reduced-height domain 补充

task006 对真实 `100 nm x 100 nm x 70 nm`、`stage4_block_grating`、`dtn_port + auto_propagating` 路径做了资源和初步 R/T/A 检查。几何传参为：

```text
air_height = 60 nm
substrate_thickness = 10 nm
grating_height = 50 nm
top air above grating = 10 nm
total z height = 70 nm
```

当前结论：

```text
assemble-only:
  p=1 h=1 nm 可完成；
  p=2 h=2 nm 可完成；
  p=2 h=1.5 nm 超时；
  p=2 h=1 nm 在 base matrix assembled 后被 signal 9 kill，
  rows ≈ 16.99M，nnz ≈ 1.77e9，AIJ matrix ≈ 40.6 GB。

default MUMPS direct:
  p=1 最后完成 h=2 nm，h=1.5 nm 被 signal 9 kill；
  p=2 最后完成 h=4 nm，h=3 nm 被 signal 9 kill。

MUMPS OOC:
  p=1 h=2 nm 完成，但 h=1.5 nm 仍失败；
  p=2 h=4 nm 运行 5400 s 超时。
```

70 nm 域显著降低矩阵资源，但 `h=5 nm` 与 150 nm 原域的 R/T/A 差异明显。因此当前不能把 70 nm reduced-height domain 当作与 150 nm 原域等价的物理 benchmark；后续应做 top/bottom port distance 或空气/基座厚度扫描。

task006 还修正了真实光栅 reduced-height domain 下的自动 top probe 位置：有光栅块时，top probe 从 `grating_z_max` 到 `physical_z_max` 之间取，而不是从 interface 到 top boundary 之间取。

2026-07-05 补充运行后，边界更新为：

```text
memory profiling:
  p=2 h=5 default direct 的进程树 RSS 峰值约 13.65 GB；
  matrix-scale 中的 RSS upper 是 max_rss_mb x ranks 的保守上界，不是实测总 RSS。

tuned MUMPS OOC:
  p=2 h=5 完成，OOC scratch 约 4.95 GB；
  p=2 h=4 完成，OOC scratch 约 14.24 GB；
  p=2 h=3 失败，MUMPS INFOG(1)=-90；
  p=1 h=1.5 失败，MUMPS INFOG(1)=-90。

workstation:
  p=2 h=3 建议至少按 128 GB 级别压力测试；
  p=2 h=2 建议 256-512 GB；
  p=2 h=1 约为 TB 级内存问题；
  h=0.5 / 0.25 nm 不建议继续 direct/OOC workstation 路线。
```

失败点中记录到的 RSS 可能低估，因为 signal 9 或 MUMPS error 发生后，进程可能来不及写出 factorization 峰值。

---

## 3. 当前可以较有信心使用的能力

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

## 4. 当前必须谨慎解读的能力

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

## 5. 合并后推荐表述

推荐说法：

```text
当前版本完成了 Stage 4 R/T/A 输出重构、A_volume 体吸收、flat-layer 解析参考、small-cell p 收敛、MPI 一致性与全阶段 smoke 回归。port + A_volume 是当前主线。
```

避免说法：

```text
当前版本已完成真实 3D EUV 光栅物理 benchmark。
```

---

## 6. 后续可能任务

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

---

## 7. task005 资源边界补充

task005 对真实 `100 nm x 100 nm x 150 nm`、p=2、MPI=8、`stage4_block_grating`、`dtn_port + auto_propagating` 路径做了资源评估。当前结论是：

```text
assemble-only:
  h=2 nm 仍可完成；
  rows ≈ 4.76M；
  nnz ≈ 5.24e8；
  AIJ matrix ≈ 11.74 GB。

default MUMPS direct:
  h=5 nm 可完成；
  h=4 nm 在 stage4_dtn_augmented_ksp_setup 被 signal 9 kill；
  主要瓶颈是 LU fill-in 峰值内存，不是矩阵本体。

MUMPS OOC:
  默认 OOC 可完成到 h=5 nm；
  h=4 nm 返回 MUMPS INFOG(1)=-90；
  tuned OOC h=4 在 90 分钟超时，保留约 30 GB OOC 文件。
```

这说明当前小电脑可以用于资源摸底，但不适合继续硬跑真实 3D p=2 的 h=4 nm 及更细 direct LU 计算。若目标是 `h=3` 到 `h=2.5 nm` 的真实 3D 计算，应考虑 512 GB RAM 和 1 TB 级别 SSD scratch；若目标包含 `h=2 nm` 或更细，应按 1 TB RAM 起步，或优先开发可收敛的迭代求解器与预条件器。
