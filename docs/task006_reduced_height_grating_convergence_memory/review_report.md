# REVIEW REPORT 20260704：70 nm 缩短计算域真实 3D 光栅资源与 R/T/A 测试

## 1. 审查对象

本报告审查分支：

```text
codex/20260704-reduced-height-grating-convergence-memory
```

对应任务目录：

```text
docs/task006_reduced_height_grating_convergence_memory/
```

重点阅读文件：

```text
docs/task006_reduced_height_grating_convergence_memory/outcomes/summary.md
docs/task006_reduced_height_grating_convergence_memory/outcomes/assemble_matrix_scale.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/direct_default_scale.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/mumps_ooc_scale.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/mumps_ooc_tuned_extra_scale.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/rta_convergence.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/reduced_vs_original_domain_comparison.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/mpi1_vs_mpi8_comparison.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/memory_profile_summary.csv
docs/task006_reduced_height_grating_convergence_memory/outcomes/failure_boundary.md
docs/task006_reduced_height_grating_convergence_memory/outcomes/parameters.json
docs/task006_reduced_height_grating_convergence_memory/outcomes/changed_files.md
src/postprocessing/diffraction_3d.py
src/solvers/common_3d_solve.py
src/studies/run_3d_matrix_scale.py
src/studies/run_3d_memory_profile.py
```

本轮任务目标是测试 reduced-height 70 nm domain 对资源和 R/T/A 的影响，并探索 p=1/p=2、MPI=1/MPI=8、default MUMPS 与 MUMPS OOC 的边界。

---

## 2. 总体结论

本轮 task006 的资源测试部分完成度较高，可以作为 reduced-height domain 的资源边界依据。

但是，本轮也暴露出一个关键后处理问题：

```text
当前 3D Stage 4 block grating 的所谓 official R/T/A 仍来自 E/H Fourier probe-plane modal fitting，
而不是直接来自 DtN port auxiliary modal amplitudes。
```

因此，task006 的 R/T/A 结果只能理解为：

```text
在当前 E/H Fourier probe-plane modal fitting 后处理口径下的结果。
```

不能直接作为“DtN port 端口幅值定义下的正式 R/T/A”。

本轮最重要的审查结论是：

```text
1. reduced-height 70 nm domain 显著降低计算资源；
2. 但 70 nm 与 150 nm 的 R/T/A 差异明显，目前不能视为物理等价替代；
3. 差异很可能与当前后处理 reference plane / probe plane 口径有关，尤其是在有损 substrate 中；
4. 下一轮应优先恢复/实现基于 DtN port modal amplitudes 的 official R/T/A；
5. E/H Fourier fitting、E-only Fourier、sampled net flux 应统一归入 diagnostic 后处理。
```

所以本轮可作为资源探索结果保留，但不建议把其 R/T/A 作为最终物理结论。

---

## 3. 几何设置审查

本轮 reduced-height domain 的几何设置正确：

| 参数 | 数值 |
|---|---:|
| period_x / period_y | 100 nm / 100 nm |
| substrate_thickness | 10 nm |
| grating_height | 50 nm |
| top air above grating | 10 nm |
| `air_height` 参数 | 60 nm |
| total z height | 70 nm |
| lambda0 | 13.5 nm |

代码中 `--air-height` 的语义是：

```text
interface z=0 到 top boundary 的高度。
```

因此 70 nm 总高度应传入：

```text
air_height = 60 nm
substrate_thickness = 10 nm
```

这点在 `summary.md` 和 `parameters.json` 中已正确记录。

---

## 4. 资源扫描结果

### 4.1 Assemble-only

assemble-only 结果：

| p | h/nm | rows | nnz | AIJ matrix GB | RSS upper GB | status |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 5 | 19,482 | 1.654e6 | 0.037 | 2.368 | completed |
| 1 | 4 | 45,844 | 3.375e6 | 0.076 | 2.880 | completed |
| 1 | 3 | 98,628 | 6.400e6 | 0.144 | 3.102 | completed |
| 1 | 2.5 | 142,896 | 8.830e6 | 0.198 | 3.887 | completed |
| 1 | 2 | 286,292 | 1.615e7 | 0.363 | 4.696 | completed |
| 1 | 1.5 | 689,052 | 3.468e7 | 0.780 | 7.312 | completed |
| 1 | 1 | 2,148,978 | 9.676e7 | 2.179 | 13.552 | completed |
| 2 | 5 | 142,896 | 1.880e7 | 0.421 | 4.655 | completed |
| 2 | 4 | 347,318 | 4.337e7 | 0.972 | 7.217 | completed |
| 2 | 3 | 759,698 | 9.126e7 | 2.045 | 10.621 | completed |
| 2 | 2.5 | 1,106,844 | 1.311e8 | 2.939 | 17.343 | completed |
| 2 | 2 | 2,235,190 | 2.585e8 | 5.794 | 19.237 | completed |
| 2 | 1.5 | 5,416,432 | 5.634e8 | 12.632 | 14.442 | timeout |
| 2 | 1 | 16,992,540 | 1.767e9 | 39.628 | 18.632 | failed |

这个结果说明 reduced-height domain 的确显著降低矩阵规模，但 p=2 h=1 nm 仍然不可行：A 矩阵本体已经约 39.6 GB，并在 swap 大幅增长后失败。

### 4.2 Default direct

Default MUMPS direct 完成边界：

```text
p=1：完成到 h=2 nm，h=1.5 nm 在 stage4_dtn_augmented_ksp_setup 被 signal 9 kill。
p=2：完成到 h=4 nm，h=3 nm 在 stage4_dtn_augmented_ksp_setup 被 signal 9 kill。
```

完成点的能量闭合很好，`R+T+A_volume` 基本闭合到 `1e-14 ~ 1e-13`。

但注意：这些 R/T/A 是当前 E/H Fourier probe-plane modal fitting 口径，不应等同于直接 DtN port modal amplitudes。

### 4.3 MUMPS OOC tuned

本轮修正了 MUMPS OOC profile 与 `--petsc-option` 的覆盖顺序。修正后，`mat_mumps_icntl_14=200` 能够真正覆盖 `mumps_ooc` profile 的默认值。

关键 tuned OOC 结果：

| p | h/nm | status | AIJ GB | RSS upper GB | OOC disk GB | elapsed s | note |
|---:|---:|---|---:|---:|---:|---:|---|
| 2 | 5 | completed | 0.421 | 16.91 | 4.95 | 140.7 | 与 default direct R/T/A 一致 |
| 2 | 4 | completed | 0.972 | 23.63 | 14.24 | 1180.4 | 突破 default OOC timeout 边界 |
| 2 | 3 | failed | 2.045 | 18.13 | 0 | 358.5 | MUMPS INFOG(1)=-90 |
| 1 | 1.5 | failed | 0.780 | 15.29 | 0 | 230.9 | MUMPS INFOG(1)=-90 |

因此，当前 reduced-height direct/OOC 路线可完成的最细 p=2 点是：

```text
p=2, h=4 nm
```

下一失败边界是：

```text
p=2, h=3 nm
```

---

## 5. R/T/A 结果与收敛判断

Default direct R/T/A：

| p | h/nm | R | T | A_volume | R+T+A | status |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 5 | 2.6207e-3 | 0.969913 | 0.027466 | 1.000000 | completed |
| 1 | 4 | 4.9308e-3 | 0.966183 | 0.028886 | 1.000000 | completed |
| 1 | 3 | 1.4020e-3 | 0.967219 | 0.031379 | 1.000000 | completed |
| 1 | 2.5 | 6.6172e-4 | 0.967196 | 0.032143 | 1.000000 | completed |
| 1 | 2 | 6.9763e-6 | 0.966357 | 0.033636 | 1.000000 | completed |
| 2 | 5 | 7.0797e-4 | 0.964603 | 0.034689 | 1.000000 | completed |
| 2 | 4 | 1.0006e-6 | 0.963855 | 0.036144 | 1.000000 | completed |

初步判断：

```text
1. 能量闭合很好。
2. p=1 R/T/A 随 h 变化明显，尤其 R 从 h=2.5 到 h=2 仍变化较大。
3. p=2 只有 h=5 和 h=4 两个 completed direct 点，不能充分判断收敛。
4. p=2 h=4 比 p=2 h=5 更接近 p=1 h=2 的 T/A，但还缺 p=2 h=3 或更细点。
5. 当前不能声称 reduced-height 70 nm 模型已经物理收敛。
```

---

## 6. 70 nm vs 150 nm 对照

对照结果：

| p | h/nm | R_70 | R_150 | dR | T_70 | T_150 | dT | A_70 | A_150 | dA |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 0.002621 | 0.021129 | -0.018508 | 0.969913 | 0.905253 | 0.064660 | 0.027466 | 0.073619 | -0.046152 |
| 2 | 5 | 0.000708 | 0.000196 | 0.000512 | 0.964603 | 0.905421 | 0.059183 | 0.034689 | 0.094383 | -0.059695 |

这说明：

```text
在当前后处理口径下，70 nm 和 150 nm 的 R/T/A 差异明显。
```

但这个差异不能简单解释为“70 nm 物理域一定错误”。当前 3D 代码的 official R/T 来源是 E/H Fourier probe-plane fitting，而不是直接的 DtN port auxiliary amplitudes。对于有损 substrate，T 在不同深度 probe plane 上评价会产生传播吸收差异；A_volume 也会随 substrate 厚度改变。

因此，更准确的结论是：

```text
当前 R/T/A 后处理口径不足以公平判断 70 nm 和 150 nm 是否物理等价。
```

---

## 7. 后处理口径问题：必须修正

本轮最重要的审查问题是：

```text
求解边界已经是 dtn_port，
但 official R/T 后处理仍是 E/H Fourier probe-plane modal fitting。
```

当前代码中：

```text
OFFICIAL_STAGE4_DIFFRACTION_POWER_SOURCE = "eh_fourier_orders"
```

这一路径比 E-only Fourier 和 sampled net flux 更可靠，因为它用切向 E/H 分离上下行波；但它仍然依赖 probe plane 位置。因此，在有损基座中，T 和 A 会受 reference plane 影响。

从项目目标看，应改为：

```text
official R/T/A = DtN port modal amplitudes
```

而以下路径应明确作为 diagnostic：

```text
E/H Fourier probe-plane modal fitting
E-only Fourier
sampled net flux
```

这与前面 task002-task005 的 DtN port 主线目标保持一致，也能避免 70 nm vs 150 nm 对照被 probe plane/reference plane 污染。

---

## 8. Memory profiling 审查

新增 `src/studies/run_3d_memory_profile.py` 是合理的阶段性诊断工具。

它能够：

```text
- 包装一个 3D run command；
- 周期性扫描子进程树；
- 记录 rss_sum/rank-like max/rss_mean/rss_min；
- 记录 swap；
- 记录 OOC scratch 目录大小；
- 读取 latest progress stage；
- 在 timeout 时杀掉整棵进程树。
```

代表 case：

```text
p=2, h=5 nm, MPI=8, default direct
```

结果：

```text
peak process-tree RSS sum = 13.646 GB
peak single-process RSS = 2.030 GB
peak swap = 0.161 GB
completed
```

对应 matrix-scale 中 `estimated_total_RSS_upper_GB = max_rss * ranks = 16.68 GB`，说明 `max_rss * ranks` 是保守上界，不是真实进程树总 RSS。

这个工具可保留为 diagnostic-only，不应作为常规大规模运行必需路径。

---

## 9. MPI=1 vs MPI=8

MPI=1 和 MPI=8 的 R/T/A 基本一致，说明并行结果没有明显数值偏差。

但 MPI=1 明显更慢：

| p | h/nm | MPI1 elapsed | MPI8 elapsed | speedup |
|---:|---:|---:|---:|---:|
| 1 | 5 | 52.3 s | 18.1 s | 2.89x |
| 1 | 3 | 884.5 s | 43.9 s | 20.1x |
| 2 | 5 | 1695.7 s | 135.5 s | 12.5x |

因此，MPI=1 只适合小规模一致性对照，不适合作为真实 3D direct 主计算路线。

---

## 10. 是否建议合并

建议合并 task006 分支，但合并时必须明确边界：

可以合并的内容：

```text
- 70 nm reduced-height 资源扫描；
- p=1/p=2 default direct 边界；
- MUMPS OOC tuned 边界；
- MPI=1/MPI=8 对照；
- memory profiling diagnostic 脚本；
- MUMPS OOC PETSc extra options 覆盖顺序修正；
- top probe 自动位置修正。
```

不能把本轮合并解读为：

```text
- 70 nm reduced-height domain 已证明与 150 nm 物理等价；
- p=2 h=4 或 p=1 h=2 已经完成物理收敛；
- 当前 R/T/A 已经是严格 DtN port modal amplitude 后处理；
- p=2 h=1 nm direct/OOC 可行。
```

---

## 11. 后续建议：task007

下一轮应优先做：

```text
Task007: Restore DtN-port modal R/T/A as official Stage 4 power output
```

目标：

```text
1. 检查当前 dtn_port auxiliary unknowns 是否已经保存 top/bottom modal coefficients；
2. 若已保存，则直接用其计算 official R/T；
3. 若未保存，则把 DtN auxiliary modal coefficients 暴露到 run_summary / port_power.json；
4. 将 official power source 改为 dtn_port_modal_amplitudes；
5. 将 E/H Fourier fitting 改为 diagnostic_eh_fourier；
6. 重新跑 70 nm vs 150 nm 的 p=2 h=5 对照；
7. 判断在 unified port/modal reference 下两者是否接近；
8. 更新文档，明确 official 和 diagnostic 后处理的边界。
```

在 task007 完成之前，不建议继续基于当前 E/H probe-plane R/T/A 做 height 物理判断。

---

## 12. 最终结论

```text
task006 资源探索部分通过，建议合并；
但 R/T/A official 后处理口径需要在 task007 中修正。
```

当前 reduced-height 70 nm 的直接法资源结论是：

```text
p=1 default direct 可完成到 h=2 nm；
p=2 default direct 可完成到 h=4 nm；
p=2 tuned OOC 可完成 h=4 nm，但 h=3 nm 仍失败；
p=2 h=1 nm direct/OOC 路线不现实。
```

当前物理结论是：

```text
70 nm 与 150 nm 在当前 probe-plane E/H fitting 后处理下差异明显；
但在恢复 DtN port modal official R/T/A 之前，不能最终判断 reduced-height domain 是否物理等价。
```
