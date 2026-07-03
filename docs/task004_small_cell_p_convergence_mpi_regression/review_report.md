# REVIEW REPORT 20260703：small-cell p 收敛、MPI 一致性与全阶段回归

## 1. 审查对象

本报告审查分支：

```text
codex/20260702-rta-output-volume-absorption
```

对应任务目录：

```text
docs/task004_small_cell_p_convergence_mpi_regression/
```

重点阅读文件：

```text
docs/task004_small_cell_p_convergence_mpi_regression/task.md
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/summary.md
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/metrics.csv
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/mpi_consistency.csv
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/regression_metrics.csv
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/parameters.json
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/run_log.txt
README.md
notes/README.md
notes/quick_start/stage4_3d_block_grating_usage_guide.md
notes/theory/stage4_3d_dtn_port.md
notes/theory/THEORY_RTA_AND_VOLUME_ABSORPTION.md
```

本轮 Codex 没有修改源码，主要完成了 small-cell p 收敛验证、MPI 一致性验证、全阶段轻量回归和 outcomes 记录。

---

## 2. 总体结论

本轮 task004 可以评价为：

```text
通过，可以考虑合并当前分支。
```

更具体地说：

```text
可以合并的内容：
- R/T/A 输出结构；
- A_volume 体吸收积分；
- flat-layer 解析参考；
- Stage 4 dtn_port + A_volume 主线；
- small-cell flat-layer p=1/p=2 收敛结果；
- MPI 1/4/8 主线一致性；
- Stage 1/2/flat-layer/stage4_block_grating zero-contrast smoke 回归记录。

不能过度声称的内容：
- 真实 100 nm 3D EUV grating 已完成物理收敛 benchmark；
- probe_eh_fourier / net_flux 已经可以替代 port 作为主 R/T；
- Stage 2B/2C 本轮粗网格 smoke 代表 PML/Fresnel 精度通过。
```

本轮结果已经足够支持将该分支作为一个阶段性稳定版本合并到 `master`。后续如果需要进一步研究 `probe_eh_fourier` / `net_flux`，建议另开新任务，而不是继续阻塞当前分支合并。

---

## 3. task004 完成情况

### 3.1 p=1 / p=2 收敛性

small-cell flat-layer 设置为：

```text
period_x = period_y = 10 nm
air_height = substrate_thickness = 5 nm
lambda0 = 13.5 nm
n_substrate = 0.999002304859 + 0.00182649365j
stage_case = stage4_flat_layer_sanity
stage4_boundary_model = dtn_port
stage4_dtn_order_policy = auto_propagating
stage4_dtn_assembly = auxiliary
```

完成的 p=1 网格：

```text
h = 2.7, 2.0, 1.5, 1.0 nm
```

完成的 p=2 网格：

```text
h = 4.0, 3.0, 2.0, 1.5 nm
```

所有 p/h case 的主线闭合：

```text
R_port + T_port + A_volume - 1 ≈ 机器精度
```

代表性结果：

| p | h/nm | DoF | R_port | T_port | A_volume | dR vs ref | closure |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.0 | 3630 | 6.616e-05 | 9.917e-01 | 8.262e-03 | 6.507e-05 | -2.22e-15 |
| 2 | 4.0 | 1148 | 5.908e-06 | 9.916e-01 | 8.414e-03 | 4.824e-06 | 2.44e-15 |
| 2 | 2.0 | 4312 | 1.643e-06 | 9.915e-01 | 8.454e-03 | 5.589e-07 | -2.33e-15 |
| 2 | 1.5 | 10740 | 1.241e-06 | 9.915e-01 | 8.461e-03 | 1.569e-07 | -1.11e-15 |

结论：

```text
p=2 明显优于 p=1。
```

p=2 在更粗网格和相近甚至更少 DoF 下，就能达到比 p=1 更好的 `port/A_volume/reference` 一致性。因此，后续 small-cell flat-layer sanity 推荐以 p=2 作为主线。

### 3.2 probe_eh_fourier / net_flux 状态

本轮确认：

```text
probe_eh_fourier 和 net_flux 仍然不能作为主验收口径。
```

p=2 h=2.0 时 probe 有明显改善：

```text
port:  R=1.643e-06, T=0.991544, A_volume=0.008454
probe: R=5.218e-06, T=0.986241, A=0.013754
```

但是 p=2 h=1.5 出现过冲：

```text
probe_eh_fourier: T_probe=1.020700, A_probe=-0.020907
net_flux:         R_flux=-0.027102, T_flux=1.020514
```

因此，当前合理定位是：

```text
port = primary
A_volume = absorption_check
probe_eh_fourier = diagnostic only
net_flux = diagnostic only
```

这个问题不应阻塞合并，因为 task004 的目标已经是验证主线和并行一致性，而 probe/net_flux 已明确降级为诊断路径。后续如果需要，可以单独开任务研究 probe plane、采样点、curl(E) 重构、H 场投影或 element-wise flux integral。

### 3.3 MPI 1/4/8 一致性

完成 MPI 检查：

```text
p=1, h=1.5 nm, ranks=1/4/8
p=2, h=3.0 nm, ranks=1/4/8
```

主线指标满足：

```text
|R_port_mpiN - R_port_rank1| < 1e-8
|T_port_mpiN - T_port_rank1| < 1e-8
|A_volume_mpiN - A_volume_rank1| < 1e-8
|closure_mpiN - closure_rank1| < 1e-10
```

结论：

```text
MPI 1/4/8 不改变 port/A_volume 主线结果。
```

本轮 MPI 测试主要证明并行一致性，不证明并行加速。由于 small-cell case 太小，8 ranks 反而可能更慢，这是正常的通信/并行开销现象。

### 3.4 全阶段轻量回归

完成以下轻量回归：

| stage | stage_case | status | 评价 |
|---|---|---|---|
| Stage 1 | `stage1_airbox` | completed | smoke 通过 |
| Stage 2A | `floquet_airbox` | completed | smoke 通过 |
| Stage 2B | `pml_airbox` | completed | smoke 通过，不代表 PML 精度 |
| Stage 2C | `fresnel_interface` | completed | smoke 通过，不代表 Fresnel 精度 |
| Flat-layer sanity | `stage4_flat_layer_sanity` | completed | small-cell sanity 通过 |
| 3D grating path smoke | `stage4_block_grating` zero-contrast | completed | block grating 路径 smoke 通过 |

单元测试：

```text
67 tests passed, 10 skipped
```

这说明当前分支的 task002/task003 修改没有破坏主要代码入口。

---

## 4. 当前版本代码边界

合并后应明确把当前版本定义为：

```text
Stage 4 port/A_volume 主线已形成；
small-cell flat-layer sanity 和 MPI 一致性已通过；
真实 100 nm 3D EUV grating 仍未完成物理收敛 benchmark。
```

当前可信范围：

1. 2D EUV DtN port 主线已经有较完整验证链条。
2. 3D staged framework 已能运行 Stage 1 / Stage 2A / Stage 2B / Stage 2C / flat-layer sanity / stage4_block_grating zero-contrast smoke。
3. `stage4_flat_layer_sanity` 中，`port + A_volume` 在 small-cell p=1/p=2 下稳定闭合。
4. p=2 在 small-cell flat-layer 中明显优于 p=1。
5. MPI 1/4/8 不改变 `R_port/T_port/A_volume` 主线结果。
6. `stage4_block_grating` 真实路径可运行，但当前结果仍应按 smoke / sanity 解读。

当前不可信或不能过度声称的范围：

1. 真实 100 nm 3D EUV grating 尚未完成 h 收敛。
2. 小电脑上不应强制要求真实 grating 的 h≈1 nm 计算通过。
3. `probe_eh_fourier` 和 `net_flux` 仍是 diagnostic only。
4. Stage 2B/2C 本轮使用粗网格 smoke，不能作为 PML/Fresnel 精度结论。
5. MUMPS OOC 和 MPI 只能缓解运行问题，不能消除 3D direct LU 的 fill-in 本质瓶颈。

---

## 5. 合并建议

建议合并当前分支到 `master`。

推荐合并说明：

```text
Merge Stage 4 R/T/A output, volume absorption, flat-layer reference, small-cell p-convergence, MPI consistency, and smoke regression.
```

中文说明可以写：

```text
本次合并完成 R/T/A 输出重构、A_volume 材料体吸收、flat-layer 解析参考、small-cell p=1/p=2 收敛、MPI 1/4/8 一致性与全阶段 smoke 回归。当前版本可作为 Stage 4 port/A_volume 主线的阶段性稳定版本，但不声称真实 100 nm 3D EUV 光栅已完成物理收敛 benchmark。
```

合并后建议删除或归档旧任务分支时，保留 `docs/task000` 到 `docs/task004` 作为历史闭环记录。

---

## 6. 后续建议

不建议继续在当前分支阻塞合并。

后续如果继续开发，建议新开任务：

```text
task005_probe_flux_diagnostic_cleanup
```

可研究：

1. p=2 h=1.5 下 probe/net_flux 过冲原因；
2. probe plane 位置扫描；
3. 采样点加密与 quadrature 风格后处理；
4. `curl(E)` 重构 H 与投影 H 的差异；
5. element-wise Poynting flux integral；
6. 是否保留 probe/net_flux 为纯诊断，或者进一步改造成稳定交叉检查。

另一个未来方向是高资源条件下的真实 100 nm 3D grating benchmark，但这不适合作为当前小电脑合并前条件。

---

## 7. 本报告后同步更新的文档

在写本 review report 的同时，我对以下文档做了边界说明更新：

```text
README.md
notes/README.md
notes/reference/current_version_boundaries.md
docs/README.md
```

更新重点：

1. 明确当前版本可以合并的能力边界；
2. 明确 `stage4_flat_layer_sanity` 是 flat-layer sanity，不是 3D 光栅散射；
3. 明确 `stage4_block_grating` 才是真实 3D 周期矩形柱/光栅路径；
4. 明确 `port + A_volume` 是 Stage 4 当前主线；
5. 明确 `probe_eh_fourier` / `net_flux` 仍为 diagnostic only；
6. 明确真实 100 nm 3D EUV grating 尚未完成物理收敛 benchmark。

---

## 8. 最终结论

```text
建议合并。
```

当前分支已经完成一个清晰的阶段性目标：

```text
3D Stage 4 port/A_volume 主线已经通过 flat-layer small-cell、p=1/p=2 收敛和 MPI 一致性验证。
```

probe/net_flux 的诊断异常不应继续阻塞本分支合并。合并后的 README 和 notes 已经标明当前版本边界，后续若有需要再单独开任务深挖。
