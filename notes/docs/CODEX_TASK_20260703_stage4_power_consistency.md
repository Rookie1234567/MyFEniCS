# CODEX TASK 20260703：Stage 4 功率一致性修复

## 0. 分支要求

继续在当前分支工作：

```text
codex/20260702-rta-output-volume-absorption
```

开始前先阅读：

```text
notes/docs/REVIEW_REPORT_20260703_rta_output_volume_absorption.md
```

本任务的目标是修复上一轮结果中暴露出的 Stage 4 flat-layer 功率一致性问题。请保留上一轮新增的简洁输出结构：

```text
power_summary.csv
port_power.json
probe_power.json
flux_power.json
volume_absorption.json
```

重要要求：本任务必须在 `notes/outcomes/` 下新建独立的 outcomes 文件夹来保存本轮输出记录。不要覆盖、追加或改写之前任务的 outcomes 文件夹，例如：

```text
notes/outcomes/20260703_stage4_validation_cleanup/
notes/outcomes/20260702_rta_output_volume_absorption/
```

这些目录是历史记录，除非另有明确要求，否则必须保持不变。

---

## 1. 当前问题

上一轮任务已经完成了 R/T/A 输出拆分，并加入了初版 `A_volume` 材料体吸收计算。但 9 个正式算例的一致性检查全部失败。典型现象如下：

```text
flat_layer 10 nm：
  port 和 net_flux 接近 R=1、T=0、A=0；
  probe_eh_fourier 却给出 A 约为 0.996。

flat_layer 5/3 nm：
  port 出现 T>1 和负 A；
  net_flux 出现 R>1 和负 T；
  A_volume 无法与 port 的 A_balance 闭合。
```

这说明当前的核心问题不是输出格式，而是 Stage 4 中功率归一化、模态方向、解析参考、Poynting 通量和体吸收口径之间没有一致。

因此，本轮不要优先扩展复杂光栅物理，也不要继续大量跑真实 block。应先集中修复 flat-layer analytic benchmark。

---

## 2. 本轮目标

本轮唯一核心目标是：

```text
让 Stage 4A flat-layer benchmark 中的四类功率/吸收结果相互一致，并与解析 flat-layer Fresnel/layered reference 一致。
```

四类结果包括：

```text
port
probe_eh_fourier
net_flux
volume_absorption
```

比较时必须使用与数值结果相同的 top/bottom 参考平面。特别是有损基底中的透射功率，不能只用界面处的 Fresnel 透射率，而要考虑从界面传播到底部参考平面的衰减。

---

## 3. 必须完成的实现内容

### 3.1 新增 flat-layer 解析参考模块

新增一个解析参考模块，建议路径：

```text
src/postprocessing/flat_layer_reference_3d.py
```

至少应计算并输出：

```text
R_ref
T_ref_at_bottom_reference_plane
A_ref_between_reference_planes
r_amplitude
t_amplitude
incident_power_ref
reflected_power_ref
bottom_transmitted_power_ref
absorbed_power_ref
reference_plane_z_top
reference_plane_z_bottom
interface_z
```

注意：当前计算域是有限厚度的计算域，不是单独的无限界面问题。因此底部参考平面如果位于有损 substrate 内部，则 `T_ref_at_bottom_reference_plane` 必须包含从界面到底部参考平面的传播衰减。

### 3.2 增加 analytic-only 后处理测试

在跑重型 FEM 之前，先增加只依赖解析场的测试或诊断。也就是说，把解析 layered field 直接喂给后处理路径：

```text
解析 E/H -> probe_eh_fourier
解析 E/H -> net_flux
解析 E/H -> volume_absorption
```

这些测试必须验证：在不经过 FEM 求解的情况下，后处理公式本身能恢复解析的 `R_ref`、`T_ref` 和 `A_ref`。

### 3.3 如果 analytic-only 下 probe_eh_fourier 失败，先修 probe

如果解析场输入后 `probe_eh_fourier` 仍然给出错误 R/T/A，优先检查并修复 probe 后处理，而不是调 FEM 解。

重点检查：

```text
top plane 上的入射场扣除
up/down 波方向命名
vertical_sign 与 k_z 的约定
相位因子 exp(+/- i beta z)
H 场符号约定
有损 substrate 中的 complex beta
模态功率归一化
```

E-only Fourier 仍只能作为 diagnostic，不能作为 official probe R/T。官方 probe 结果仍应使用 E/H Fourier directional fitting。

### 3.4 验证 net_flux 的符号约定

对解析场，显式验证：

```text
top_flux_outward = P_reflected - P_incident
bottom_flux_outward = P_transmitted_at_bottom_plane
R_flux = 1 + top_flux_outward / P_incident
T_flux = bottom_flux_outward / P_incident
A_flux = 1 - R_flux - T_flux
```

解析 flat-layer 场不应得到负的 transmitted flux。如果 analytic-only net_flux 出现 `T_flux < 0`，优先检查 H 场符号、法向量方向、bottom traveling direction 和总场定义。

### 3.5 重新推导并验证 A_volume 归一化

当前 `A_volume` 初版使用：

```text
P_abs = integral 0.5*k0^2*Im(epsilon_r)*|E_total|^2 dV
```

请从项目当前的 code units 重新推导体吸收系数。当前代码中的磁场和 Poynting 通量定义接近：

```text
H_code = curl(E) / (i*k0*mu_r)
S_code = 0.5*Re(E x H_code*)
```

需要检查材料损耗密度是否应改为：

```text
0.5*k0*Im(epsilon_r)*|E_total|^2
```

不要凭直觉修改系数。必须使用解析有损平面波的通量差进行验证。目标检查是：

```text
A_volume_ref 应接近 A_flux_ref
```

如果最终确认仍使用 `k0^2`，必须在理论文档和 json normalization note 中写清楚推导依据。如果改为 `k0`，也要同步更新代码、理论文档和输出说明。

### 3.6 检查 DtN port 的入射/出射幅值

对于 flat-layer FEM 结果，需要将 DtN auxiliary 输出与解析参考逐项比较：

```text
incident_projection
outgoing_amplitude_top
outgoing_amplitude_bottom
R_port
T_port
A_port_balance
```

重点检查：

```text
top incident projection 是否与解析入射幅值一致
top outgoing amplitude 是否等于解析反射幅值
bottom outgoing amplitude 是否等于底部参考平面的解析透射幅值
mode.power_per_unit_amplitude 在有损 substrate 中是否仍适用
top source term 的符号是否正确
auxiliary block 中相位和复共轭是否一致
```

### 3.7 增加 flat-layer 参考输出文件

每个 flat-layer 结果文件夹中额外输出：

```text
flat_layer_reference.json
power_consistency.json
```

`flat_layer_reference.json` 至少包含解析参考值。

`power_consistency.json` 至少包含以下差值：

```text
R_port - R_ref
T_port - T_ref
A_port - A_ref
R_probe - R_ref
T_probe - T_ref
A_probe - A_ref
R_flux - R_ref
T_flux - T_ref
A_flux - A_ref
A_volume - A_ref
closure_error_port_volume = R_port + T_port + A_volume - 1
```

---

## 4. 验证计划

### 4.1 analytic-only 测试

至少增加以下测试：

1. normal incidence Fresnel/layered reference；
2. 解析场输入 `probe_eh_fourier` 后能恢复 R/T；
3. 解析场输入 `net_flux` 后能恢复 R/T；
4. 有损 substrate 的 volume absorption 与解析 flux loss 一致；
5. 无损 substrate 时 `A_volume` 接近 0。

这些测试应尽量轻量，不应依赖重型 FEM 求解。

### 4.2 FEM flat-layer 运行

analytic-only 测试通过后，再运行 Stage 4A flat-layer：

```text
mesh_target_size = 10 nm, 5 nm, 3 nm
lambda0 = 13.5 nm
n_substrate = 0.999002304859 + 0.00182649365j
stage4_boundary_model = dtn_port
stage4_dtn_order_policy = auto_propagating
```

如果 analytic-only 测试没通过，不要急着跑 5/3 nm FEM，先修公式和后处理。

### 4.3 zero-contrast 回归

flat-layer 修复后，再运行 Stage 4B zero-contrast：

```text
mesh_target_size = 10 nm, 5 nm, 3 nm
n_grating = 1 + 0j
```

zero-contrast 应在同网格下接近 flat-layer。

### 4.4 real Si block 轻量确认

flat-layer 和 zero-contrast 都有意义后，再运行真实 Si block。最低要求跑：

```text
Stage 4B real Si block: 10 nm
```

5/3 nm 只有在前面检查通过且资源允许时再跑。本任务的重点不是 real block 收敛，而是先修功率一致性。

---

## 5. Outcomes 输出要求

本任务必须在 `notes/outcomes/` 下新建独立文件夹：

```text
notes/outcomes/20260703_stage4_power_consistency/
```

不要把本任务输出写入任何旧文件夹。尤其不要复用：

```text
notes/outcomes/20260703_stage4_validation_cleanup/
notes/outcomes/20260702_rta_output_volume_absorption/
```

这些旧文件夹应作为历史快照保留。本任务的 summary、metrics、logs 和 changed files 必须全部写入新的 `20260703_stage4_power_consistency` 文件夹中。

新文件夹至少包含：

```text
summary.md
metrics.csv
parameters.json
run_log.txt
changed_files.md
```

### 5.1 summary.md 表格要求

#### 表 1：analytic-only 测试

| test | status | max_error | note |
|---|---|---:|---|

#### 表 2：flat-layer FEM 与解析参考对比

| mesh_nm | method | R | T | A | R_ref | T_ref | A_ref | dR | dT | dA | pass |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

方法至少包括：

```text
port
probe_eh_fourier
net_flux
volume_absorption
```

#### 表 3：zero-contrast 回归

| mesh_nm | method | flat_value | zero_contrast_value | difference | pass |
|---:|---|---:|---:|---:|---|

#### 表 4：根因排查总结

| issue | status | fix |
|---|---|---|

至少覆盖：

```text
probe direction/phase
net flux sign
A_volume normalization
DtN incident/outgoing amplitude
complex substrate beta power normalization
```

#### 表 5：最终建议

明确说明 Stage 4 power postprocess 当前是：

```text
可以进入 zero-contrast / real-block validation
或仍然只能作为 diagnostic only
```

---

## 6. 验收标准

本任务完成的标准：

1. flat-layer case 会输出 `flat_layer_reference.json`。
2. analytic-only 的 probe/net_flux/volume 测试先于重型 FEM 运行并通过。
3. flat-layer FEM 10/5/3 nm 与解析参考完成对比。
4. `probe_eh_fourier` 不再在 flat-layer 10 nm 下给出接近 1 的虚假吸收。
5. analytic net_flux 不再给出负的 transmitted power。
6. `A_volume` 的归一化系数完成推导，并通过解析 flux loss 验证。
7. 使用一致的参考平面检查 `R + T + A_volume`。
8. 修复后 zero-contrast 与 flat-layer 在同网格下仍保持接近。
9. outcomes 明确说明结果是否可以作为 physical benchmark candidate，还是仍为 numerical sanity only。
10. 不提交大型 `results/` 文件夹。
