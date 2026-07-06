# REVIEW REPORT 20260706：恢复 DtN port modal amplitudes 作为 Stage 4 官方 R/T/A

## 1. 审查对象

本报告审查分支：

```text
codex/20260704-dtn-port-modal-official-rta
```

对应任务目录：

```text
docs/task007_dtn_port_modal_official_rta/
```

重点阅读文件：

```text
docs/task007_dtn_port_modal_official_rta/outcomes/summary.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_modal_investigation.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_power_formula.md
docs/task007_dtn_port_modal_official_rta/outcomes/flat_layer_port_modal_validation.csv
docs/task007_dtn_port_modal_official_rta/outcomes/block_grating_port_modal_vs_eh_probe.csv
docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_official_rta.csv
docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_diagnostic_probe_rta.csv
docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_resource.csv
docs/task007_dtn_port_modal_official_rta/outcomes/reduced_vs_original_port_modal_comparison.csv
docs/task007_dtn_port_modal_official_rta/outcomes/parameters.json
docs/task007_dtn_port_modal_official_rta/outcomes/changed_files.md
src/solvers/dtn_port_3d.py
src/solvers/common_3d_case_flow.py
src/postprocessing/diffraction_3d.py
src/postprocessing/rta_3d.py
src/common/modes_3d.py
```

本轮任务目标是把 Stage 4 `dtn_port` 主线的官方 R/T/A 从 probe-plane E/H Fourier fitting 切换为直接来自 DtN port modal amplitudes，并将 probe / sampled field 路径降级为 diagnostic。

---

## 2. 总体结论

本轮 task007 完成了关键目标：

```text
Stage 4 dtn_port official R/T/A 已切换为 dtn_port_modal_amplitudes。
```

建议合并当前分支。

合并含义应写成：

```text
恢复 Stage 4 dtn_port 主线官方 R/T/A：R_total/T_total 来自 DtN port auxiliary modal amplitudes；E/H Fourier probe、E-only Fourier probe、sampled net flux 均降级为 diagnostic。
```

不要把本次合并解读为：

```text
真实 3D grating 已完成最终网格收敛 benchmark；
不同 total height 下的 T/A 可以直接比较为同一物理界面透射率；
p=2 h=5 已经是最终物理解。
```

本轮最重要的审查判断：

```text
1. official / diagnostic 后处理边界已经基本理顺；
2. DtN port modal amplitude 的 top/bottom outgoing 转换逻辑是自洽的；
3. official R/T/A 与 A_volume 的能量闭合很好；
4. T/A 随 substrate thickness 变化是当前 bottom physical port plane reference 的自然结果；
5. 若只想比较 height 是否影响结构反射，优先比较 R，而且应看绝对差值；
6. p=1 flat-layer h=5 误差大可以先归因于粗网格和低阶单元，后续可单独做 flat-layer p/h 收敛。
```

---

## 3. official R/T/A 口径审查

### 3.1 Auxiliary unknown 的物理含义

本轮调查确认，Stage 4 `dtn_port + auxiliary` 路径中的 auxiliary unknown `a_j` 不是裸反射/透射振幅，而是总场在第 `j` 个端口模态上的投影。

因此正确的 outgoing amplitude 是：

```text
top port:    b_j = a_j - incident_projection_j
bottom port: b_j = a_j
```

这一点已写入 `dtn_port_modal_investigation.md` 和 `dtn_port_power_formula.md`，并在源码中实现。

### 3.2 源码实现

`src/solvers/dtn_port_3d.py` 中已定义：

```text
DTN_PORT_MODAL_POWER_SOURCE = "dtn_port_modal_amplitudes"
```

`_write_port_outputs(...)` 写出：

```text
port_power.json
port_power.csv
dtn_port_power_metrics_3d.json
dtn_port_diffraction_orders_3d.json
dtn_port_diffraction_orders_3d.csv
dtn_auxiliary_amplitudes_3d.json
```

`port_power.json` 中字段包括：

```text
method = port
role = primary
power_source = dtn_port_modal_amplitudes
reference_planes.top_z = physical_z_max
reference_planes.bottom_z = physical_z_min
R_total
T_total
R_total_dtn_port_modal
T_total_dtn_port_modal
orders[*].auxiliary_amplitude_total_projection
orders[*].incident_projection
orders[*].outgoing_amplitude
orders[*].outgoing_amplitude_at_boundary
orders[*].modal_power_code_units
orders[*].power_ratio
```

`_port_power_metrics(...)` 中只累加 propagating 模态，并设置：

```text
R_total = R_total_dtn_port_modal
T_total = T_total_dtn_port_modal
```

### 3.3 符号与转换关系判断

从代码结构看：

```text
auxiliary row: a_j - projection(E_total)_j = 0
```

具体离散上，auxiliary equation 对 FEM dof 加 `-conj(ell)/denominator`，对 auxiliary unknown 加 `1.0`。这与 `a_j = projection(E_total)` 的解释一致。

计算 outgoing power 时：

```text
top:    outgoing_amplitude = aux_value - incident_projection
bottom: outgoing_amplitude = aux_value
```

这与 total-field top incident port 的物理定义一致。目前未发现明显符号混乱。

---

## 4. diagnostic 路径审查

`src/postprocessing/diffraction_3d.py` 中 E/H Fourier probe 已改为：

```text
diagnostic_eh_fourier_probe
```

E-only Fourier probe 与 sampled net flux 分别为：

```text
diagnostic_e_only_fourier_probe
diagnostic_sampled_net_flux
```

`src/postprocessing/rta_3d.py` 中 `power_summary.csv` 已把 port row 标为：

```text
method = port
role = primary
source = dtn_port_modal_amplitudes
```

probe 和 net flux row 标为 diagnostic。

当前仍有一个历史兼容变量名：

```text
OFFICIAL_STAGE4_DIFFRACTION_POWER_SOURCE
```

它现在指向 `diagnostic_eh_fourier_probe`，注释也说明它只是 legacy alias。这个不影响当前 official 输出，但名字仍有潜在误导。后续可以进一步清理为：

```text
LEGACY_STAGE4_DIFFRACTION_POWER_SOURCE
```

或直接减少外部暴露。

---

## 5. Flat-layer sanity 审查

Flat-layer 结果：

| case | R | T | A_volume | R_error | T_error | A_error |
|---|---:|---:|---:|---:|---:|---:|
| p=1 h=5 | 5.12915e-2 | 9.42675e-1 | 6.03359e-3 | 5.12904e-2 | -4.88592e-2 | -2.43126e-3 |
| p=2 h=5 | 1.85506e-3 | 9.90315e-1 | 7.82969e-3 | 1.85398e-3 | -1.21882e-3 | -6.35160e-4 |

判断：

```text
p=2 h=5 明显优于 p=1 h=5，且能量闭合正常；
p=1 h=5 误差较大，现阶段可归因于低阶单元和粗网格；
该问题不阻塞 task007 合并，但建议后续用单独任务补充 flat-layer p/h 收敛验证。
```

---

## 6. Height scan 审查

主线 height scan 设置：

```text
p = 2
h = 5 nm
MPI = 8
height = 70 / 110 / 130 / 150 nm
stage4_boundary_model = dtn_port
power_source = dtn_port_modal_amplitudes
```

官方 DtN port modal 结果：

| total height nm | R_port | T_port | A_volume | R+T+A |
|---:|---:|---:|---:|---:|
| 70 | 7.079669e-4 | 9.646033e-1 | 3.468869e-2 | 1.0000000000000075 |
| 110 | 5.431444e-5 | 9.349102e-1 | 6.503548e-2 | 1.0000000000000018 |
| 130 | 2.212366e-5 | 9.202230e-1 | 7.975483e-2 | 1.0000000000000149 |
| 150 | 1.960416e-4 | 9.054207e-1 | 9.438328e-2 | 0.9999999999999692 |

结论：

```text
T_port 和 A_volume 随 total height / substrate thickness 明显变化，这是合理的。
```

原因是当前官方 T 的参考面为 bottom physical port plane，且基座是有损材料。substrate 越厚，波传播到 bottom port plane 的路径越长，T 下降，A_volume 上升。

因此，不应把不同 height 下的 T/A 差异解释为结构散射本身变化。若未来需要比较同一个物理界面处的透射，需要新增 interface-referenced T 或 common-reference-plane correction。

但当前用户需求下，暂不需要新增 interface-referenced T。

---

## 7. 关于 R 的 height 影响

如果只关心结构反射，R 是比 T/A 更适合比较 height 影响的指标。

当前 official R 结果为：

| total height nm | R_port |
|---:|---:|
| 70 | 7.079669e-4 |
| 110 | 5.431444e-5 |
| 130 | 2.212366e-5 |
| 150 | 1.960416e-4 |

这些 R 值都处于 `10^-4 ~ 10^-3` 或更小量级，最大绝对差约 `6.9e-4`。从绝对量级看，当前结果不支持“R 强烈依赖 height”。

但注意：R 本身很小，不能主要看相对误差；同时 p=2 h=5 仍是粗网格。task007 中 70 nm p=2 h=4 结果为：

```text
R = 1.000623e-6
T = 0.9638547
A_volume = 0.0361443
```

相比 70 nm p=2 h=5 的 `R = 7.079669e-4`，R 对网格仍很敏感。因此后续若要固定 70 nm benchmark，应在 official DtN port modal 口径下补做本机可承受的 70 nm p/h 收敛表。

---

## 8. Diagnostic probe 对比

70 nm p=2 h=5 对比：

| method | R | T | A |
|---|---:|---:|---:|
| official DtN port modal | 7.079669e-4 | 9.646033e-1 | 3.468869e-2 |
| diagnostic E/H Fourier probe | 1.630145e-2 | 7.522551e-1 | 2.314434e-1 |
| diagnostic sampled net flux | 2.350566e-1 | 7.417808e-1 | 2.316260e-2 |

此外，130 nm diagnostic E/H Fourier probe 出现 `T > 1` 和负 `A_balance`。这进一步证明：

```text
probe-plane fitting / sampled net flux 不能作为 official R/T/A。
```

---

## 9. 资源结果

height scan 资源：

| height nm | cells | dofs | rows | nnz | elapsed s | max RSS MB |
|---:|---:|---:|---:|---:|---:|---:|
| 70 | 5600 | 142188 | 142896 | 1.880322e7 | 89.696 | 2206.9 |
| 110 | 8800 | 221564 | 222272 | 2.721855e7 | 305.382 | 2106.5 |
| 130 | 10400 | 261252 | 261960 | 3.142621e7 | 490.162 | 2725.0 |
| 150 | 12000 | 300940 | 301648 | 3.563388e7 | 617.119 | 2620.2 |

结论：p=2 h=5 的 70~150 nm height scan 在本机上均可完成。后续本机 benchmark 应优先集中在：

```text
70 nm reduced-height, official dtn_port_modal, p=1/p=2 本机可完成网格
```

---

## 10. 是否建议合并

建议合并 task007 分支。

合并前应明确：

可以合并：

```text
1. official R/T/A 改为 dtn_port_modal_amplitudes；
2. diagnostic probe / net flux 降级；
3. port_power.json / port_power.csv / dtn_auxiliary_amplitudes_3d.json 输出；
4. volume absorption 与 port modal closure 回写；
5. p=2 h=5 height scan 和表格结果；
6. flat-layer p=1/p=2 sanity；
7. 代码和文档中的 official/diagnostic 边界说明。
```

不要过度声称：

```text
1. 70 nm 和 150 nm 的 T/A 可以直接代表同一界面透射；
2. p=2 h=5 已经收敛；
3. p=1 h=5 flat-layer 误差可忽略；
4. diagnostic probe 可用于正式 R/T/A。
```

---

## 11. 后续建议：task008

下一轮建议开 task008：

```text
70 nm official DtN-port R/T/A 本机可承受收敛 benchmark 与资源报告
```

目标：

```text
1. 在 task007 可信代码口径下，重跑 70 nm reduced-height 的本机可完成网格；
2. 使用 official dtn_port_modal R/T/A，不再使用 task006 的 probe 口径；
3. 固定为后续本机 benchmark；
4. 同步输出资源表：cells/dofs/rows/nnz/A matrix/RSS/elapsed/status；
5. 暂不引入迭代法。
```

建议扫描：

```text
70 nm reduced-height, MPI=8, default MUMPS direct, dtn_port, auto_propagating
p=1: h = 5, 4, 3, 2.5, 2 nm
p=2: h = 5, 4 nm
```

可选：

```text
p=1 h=1.5 或 p=2 h=3 只作为 failure boundary / assemble-only，不作为必须完成项。
```

---

## 12. 最终结论

```text
task007 通过，建议合并。
```

本轮完成了 Stage 4 dtn_port 后处理口径的关键修正：官方 R/T/A 已恢复为 DtN port modal amplitudes；probe 和 net flux 已明确降级为 diagnostic。当前不同 height 下 T/A 的变化来自有损 substrate 和 bottom physical port plane reference，后续比较计算域高度对结构散射的影响时，应优先比较 R，并在 official dtn_port_modal 口径下做本机可完成的 p/h 收敛 benchmark。
