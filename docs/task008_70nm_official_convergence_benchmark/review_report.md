# REVIEW REPORT 20260706：50×25×140 nm、80° 斜入射本机 benchmark 审查

## 1. 审查对象

分支：

```text
codex/20260706-target-50x25x140-oblique80-official-benchmark
```

任务目录：

```text
docs/task008_70nm_official_convergence_benchmark/
```

重点审查：

```text
outcomes/summary.md
outcomes/geometry_validation.md
outcomes/oblique_incidence_validation.md
outcomes/assemble_matrix_scale.csv
outcomes/direct_solve_plan.md
outcomes/official_convergence.csv
outcomes/p1_convergence.csv
outcomes/p2_convergence.csv
outcomes/failure_boundary.md
outcomes/parameters.json
README.md
notes/reference/current_version_boundaries.md
src/studies/run_3d_matrix_scale.py
src/solvers/dtn_port_3d.py
```

本轮目标是：针对新尺寸和 80° 斜入射，先做 matrix-scale / assemble-only 资源评估，再运行本机可承受的 default direct official R/T/A benchmark，并记录本机边界。

---

## 2. 总体结论

Task008 主目标已经完成。

可以接受：

```text
p=2, h=2 nm, default MUMPS direct
```

作为当前个人电脑可完成的 official benchmark 主结果。

但必须明确：

```text
p=2 h=2 是当前本机可完成的 best-effort direct benchmark，不是最终网格收敛物理解。
```

当前本机边界为：

```text
p=1 default direct：完成到 h=1 nm；
p=2 default direct：完成到 h=2 nm；
p=2 h=1.5 nm：在 stage4_dtn_augmented_ksp_setup 阶段被系统终止；
p=2 h=1 nm：assemble-only 在 base matrix assembled 后超时，并出现大量 swap。
```

建议合并前让 Codex 做一次轻量收尾：

```text
1. 清理 raw_runs/ 中大量 0-byte / 0-line placeholder 文件；
2. 微调 summary/README/current_version_boundaries 中关于 80° 斜入射 R 的表述；
3. 保留 p=2 h=2 为当前本机主 benchmark，但标注 non-final convergence result。
```

---

## 3. 几何和斜入射设置

本轮几何设置正确：

| item | value |
|---|---:|
| period_x | 50 nm |
| period_y | 25 nm |
| domain | 50 × 25 × 140 nm |
| grating | 17 × 25 × 120 nm |
| substrate thickness | 10 nm |
| top air above grating | 10 nm |
| air_height | 130 nm |

代码中 `air_height` 表示从界面 `z=0` 到顶部边界的高度，因此：

```text
air_height = 120 + 10 = 130 nm
total_height = 10 + 130 = 140 nm
```

`grating_width_y = period_y = 25 nm` 被原 mesh builder 合法支持，没有改成 `24.999 nm` fallback。该结构应理解为 y 方向全周期填充的 ridge / full-span periodic block，而不是 y 方向有空气间隙的孤立柱。

斜入射设置也符合用户需求：

| item | value |
|---|---:|
| theta_from_z | 80 deg |
| phi | 0 deg |
| kx | 0.458350341046137 |
| ky | 0 |
| kz | -0.0808195317433606 |
| Floquet phase x | -0.600741134898 - 0.799443612046j |
| Floquet phase y | 1 + 0j |
| polarization | s, E=(0,1,0) |
| k dot E | 0 |
| DtN modes | top 40 + bottom 40 = 80 |

因此，本轮确实是 x-z 平面内、方位角为 0 的 80° 斜入射。

---

## 4. Assemble-only 资源评估

本轮没有直接套用 task005/task006 的旧经验，而是重新做了新几何和新入射角下的 matrix-scale / assemble-only 评估，这是正确的。

关键结果：

| p | h/nm | status | rows | nnz | AIJ matrix GB | RSS upper GB | note |
|---:|---:|---|---:|---:|---:|---:|---|
| 1 | 1.0 | completed | 559626 | 1.902e7 | 0.429 | 4.47 | p=1 最细 assemble completed |
| 2 | 2.0 | completed | 615188 | 6.545e7 | 1.467 | 8.91 | p=2 direct completed 点 |
| 2 | 1.5 | completed | 1347314 | 1.427e8 | 3.199 | 13.89 | assemble completed，但 direct failed |
| 2 | 1.0 | timeout | 4379752 | 4.599e8 | 10.313 | 14.13 | base matrix assembled 后超时，swap +33.4 GB |

判断：

```text
1. p=2 h=2 处于本机 default direct 可完成范围；
2. p=2 h=1.5 的 AIJ 矩阵本体不算特别大，但 direct solve 的 factorization / workspace 超过本机可承受范围；
3. p=2 h=1 已不适合继续 default direct。
```

---

## 5. Direct solve 边界

Direct solve 实际边界：

| p | completed direct h | first failed h | failure stage | note |
|---:|---|---:|---|---|
| 1 | 5, 4, 3, 2.5, 2, 1.5, 1 | 未尝试 h<1 | not reached | p=1 h=1 completed |
| 2 | 5, 4, 3, 2.5, 2 | 1.5 | stage4_dtn_augmented_ksp_setup | 本机 direct 边界 |
| 2 assemble | 1.5 completed | 1.0 timeout | stage4_dtn_base_matrix_assembled | h=1 不建议 direct |

p=2 h=1.5 失败位置说明瓶颈在求解器设置/因子化准备阶段，而不是几何、Floquet、DtN mode construction 或 R/T/A 后处理。

本轮没有强制尝试 tuned MUMPS OOC 可以接受，因为 task008 的定位是 default direct 本机 benchmark 和边界；OOC/迭代法可以之后单独处理。

---

## 6. Official R/T/A 结果

### 6.1 p=1

p=1 结果变化很大：

| h/nm | R | T | A_volume |
|---:|---:|---:|---:|
| 5 | 0.999977 | 7.567e-6 | 1.565e-5 |
| 2 | 0.991687 | 2.985e-6 | 0.008310 |
| 1.5 | 0.944379 | 4.263e-5 | 0.055579 |
| 1 | 0.094582 | 0.423887 | 0.481531 |

因此 p=1 不能作为最终物理解，只适合作为低阶对照、压力测试和资源边界参考。

### 6.2 p=2

p=2 official R/T/A：

| h/nm | R | T | A_volume | R+T+A |
|---:|---:|---:|---:|---:|
| 5 | 0.0890216 | 0.442588 | 0.468390 | 1.000000 |
| 4 | 0.0035540 | 0.561917 | 0.434529 | 1.000000 |
| 3 | 0.0046130 | 0.583653 | 0.411734 | 1.000000 |
| 2.5 | 0.0027122 | 0.592824 | 0.404464 | 1.000000 |
| 2 | 0.0013429 | 0.599213 | 0.399444 | 1.000000 |

当前本机主结果为：

```text
p=2 h=2 nm
R = 0.0013429328462348958
T = 0.5992132294442478
A_volume = 0.3994438377095067
R + T + A_volume = 0.9999999999999893
closure = -1.07e-14
```

从 h=2.5 到 h=2，R 仍变化约 0.00137，T 变化约 0.00639，A 变化约 0.00502。因此它是当前本机最好的结果，但还不是最终收敛解。

---

## 7. 关于 80° 斜入射下 R 的解释

本轮确实验证了斜入射路径，但 R 的物理解读要谨慎。

p=2 中：

```text
h=5:   R≈0.0890
h=4:   R≈0.00355
h=3:   R≈0.00461
h=2.5: R≈0.00271
h=2:   R≈0.00134
```

`p=2 h=5` 的 R 明显包含粗网格误差，不应作为真实物理反射率。更稳妥的说法是：

```text
80° 斜入射下，R 不再像部分垂直入射细网格结果那样接近 1e-6；但 p=2 细化后当前本机结果为 R≈1.3e-3。粗网格 h=5 的 R=0.089 不应作为物理结论。
```

---

## 8. Official 与 diagnostic

本轮 official R/T/A 仍然来自：

```text
dtn_port_modal_amplitudes + A_volume
```

Diagnostic E/H Fourier probe 仍不能作为 official。以 p=2 h=2 为例：

| quantity | official | diagnostic EH probe |
|---|---:|---:|
| R | 0.0013429 | 0.0042359 |
| T | 0.599213 | 0.57951 |

这说明 task007 修正后的 official/diagnostic 边界在 task008 中仍保持清楚。

---

## 9. 能量闭合

所有 completed direct cases 的：

```text
R_total_dtn_port_modal + T_total_dtn_port_modal + A_volume_total
```

均闭合到约 `1e-14 ~ 1e-13`。这说明 port modal power 与体吸收 A_volume 的能量账本自洽。

注意：能量闭合好并不等于网格已经收敛，只说明当前后处理口径没有明显能量账错误。

---

## 10. 代码改动

本轮主要代码改动：

```text
src/studies/run_3d_matrix_scale.py
src/solvers/dtn_port_3d.py
```

`run_3d_matrix_scale.py` 增加入射角参数透传，并在 CSV 中记录 kx/ky/kz、Floquet phase、polarization、elapsed、max RSS、mode count 等字段。

`dtn_port_3d.py` 在 assemble-only DtN port 结果中写出 top/bottom/propagating mode count，避免资源表字段为空。

这些改动与 task008 目标匹配，未发现明显方向性错误。

---

## 11. 合并前收尾建议

建议让 Codex 做一次轻量收尾，不需要开新任务。

### 11.1 清理 raw_runs 空文件

删除 raw_runs 中所有 0-byte / 0-line placeholder 文件，只保留有实际内容的轻量文件，例如：

```text
matrix_scale_row.json
run_summary.json
progress_3d.jsonl
solver_log.txt
stdout_tail.txt / stderr_tail.txt
关键失败点记录
```

目的：减少仓库噪声，避免以后误以为空 raw files 是有效归档。

### 11.2 微调 R 的表述

建议把 summary / README / current_version_boundaries 中关于 R 的表述统一为：

```text
当前本机最可信 completed direct 点为 p=2 h=2，得到 R≈0.00134；p=2 h=5 的 R≈0.089 明显受粗网格影响，不应作为物理结论。
```

### 11.3 固定 p=2 h=2 为当前 benchmark

建议将 `p=2 h=2` 固定为当前本机 official benchmark 主点，使用语义为：

```text
当前个人电脑可完成的 best-effort direct benchmark，而非最终收敛物理解。
```

---

## 12. 是否建议合并

完成上述轻量收尾后，建议合并。

可以合并的内容：

```text
1. 新目标几何和 80° 斜入射 outcomes；
2. p=1/p=2 assemble-only 资源表；
3. p=1/p=2 default direct completed / failed 边界；
4. p=2 h=2 本机 official benchmark 主结果；
5. 斜入射参数记录与 Floquet phase 验证；
6. run_3d_matrix_scale.py 对入射参数和资源字段的增强；
7. dtn_port_3d.py 对 assemble-only mode count 输出的增强。
```

不要过度声称：

```text
1. p=2 h=2 是最终物理收敛解；
2. p=2 h=5 的 R=0.089 是真实物理反射率；
3. p=1 h=1 可以替代 p=2；
4. diagnostic probe R/T 可以作为 official；
5. p=2 h=1.5 只要稍微增加内存就一定能跑。
```

---

## 13. 最终结论

```text
task008 主目标通过；
建议合并前轻量收尾；
p=2 h=2 可接受为当前本机 official benchmark 主结果，但不是最终收敛解。
```

当前最重要的记录：

```text
Geometry: 50×25×140 nm domain, 17×25×120 nm grating
Incidence: theta_from_z=80°, phi=0°, s polarization
Official power source: dtn_port_modal_amplitudes + A_volume
Best completed direct benchmark: p=2 h=2
R = 0.0013429328462348958
T = 0.5992132294442478
A_volume = 0.3994438377095067
R+T+A_volume = 0.9999999999999893
Direct boundary: p=2 h=1.5 stopped at stage4_dtn_augmented_ksp_setup
Assemble boundary: p=2 h=1 timeout at stage4_dtn_base_matrix_assembled with large swap
```
