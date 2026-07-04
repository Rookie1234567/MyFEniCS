# REVIEW REPORT 20260704：真实 3D 光栅 p=2 内存、OOC 与迭代法资源估算

## 1. 审查对象

本报告审查分支：

```text
codex/20260703-stage4-real-grating-memory-estimation
```

对应任务目录：

```text
docs/task005_stage4_real_grating_memory_estimation/
```

重点阅读文件：

```text
docs/task005_stage4_real_grating_memory_estimation/outcomes/summary.md
docs/task005_stage4_real_grating_memory_estimation/outcomes/assemble_matrix_scale.csv
docs/task005_stage4_real_grating_memory_estimation/outcomes/direct_default_scale.csv
docs/task005_stage4_real_grating_memory_estimation/outcomes/mumps_ooc_scale.csv
docs/task005_stage4_real_grating_memory_estimation/outcomes/direct_vs_ooc_comparison.csv
docs/task005_stage4_real_grating_memory_estimation/outcomes/iterative_memory_estimates.csv
docs/task005_stage4_real_grating_memory_estimation/outcomes/extrapolated_workstation_requirements.csv
docs/task005_stage4_real_grating_memory_estimation/outcomes/failure_boundary.md
docs/task005_stage4_real_grating_memory_estimation/outcomes/parameters.json
docs/task005_stage4_real_grating_memory_estimation/outcomes/changed_files.md
src/studies/run_3d_matrix_scale.py
```

本轮任务性质是计算资源评估，不是物理 R/T/A 收敛 benchmark。

---

## 2. 总体结论

本轮 task005 可以评价为：

```text
通过，可以作为真实 3D 光栅 p=2 直接法资源边界的初步依据。
```

更具体地说：

```text
已完成：
- 真实 100 nm x 100 nm x 150 nm stage4_block_grating 的 p=2 / MPI=8 资源扫描；
- assemble-only 从 h=20 nm 扫描到 h=2 nm；
- default MUMPS direct 从粗网格跑到 h=4 nm 失败边界；
- MUMPS OOC 对照扫描；
- h=4 nm tuned OOC 超时诊断；
- 迭代法内存估算；
- 工作站 RAM/SSD 外推；
- failure_boundary 记录。
```

主要结论：

```text
1. A 矩阵本体不是当前最先爆掉的内存瓶颈。
2. 真实瓶颈是 MUMPS direct LU factorization / fill-in。
3. 当前本机 default direct 可完成到 h=5 nm，h=4 nm 被 signal 9 kill。
4. 默认 MUMPS OOC 可完成到 h=5 nm，但没有让 h=4 nm 正式完成。
5. h=4 nm 是当前 direct/OOC 路线的第一关键失败边界。
6. 若未来希望推进 h=3~2.5 nm，需要 512 GB 级别工作站更稳妥。
7. 若希望推进 h≈2 nm，1 TB RAM 级别更合理，或者必须考虑可收敛的迭代/预条件/域分解路线。
```

---

## 3. 主要数值结果解读

### 3.1 Assemble-only 结果

assemble-only 完成到：

```text
h = 2 nm
```

其中关键规模为：

| h/nm | cells | rows | nnz | estimated AIJ matrix GB | status |
|---:|---:|---:|---:|---:|---|
| 5 | 12000 | 301648 | 35633876 | 0.7987 | completed |
| 4 | 28431 | 705918 | 81208016 | 1.820 | completed |
| 3 | 62475 | 1538710 | 173190752 | 3.883 | completed |
| 2.5 | 96000 | 2356188 | 262332636 | 5.881 | completed |
| 2 | 195075 | 4764870 | 523627904 | 11.74 | completed |

这说明矩阵本体在 `h=2 nm` 仍然可以 assemble。即使 `h=2 nm` 的系统已经达到约 476 万行、5.24 亿 nnz，AIJ 稀疏矩阵估算仍约 11.74 GB。

因此，后续资源瓶颈不能只看 matrix memory，而必须看 direct LU factorization 的峰值内存。

### 3.2 Default MUMPS direct 边界

default MUMPS direct 完成到：

```text
h = 5 nm
```

第一个失败点：

```text
h = 4 nm
```

失败阶段：

```text
stage4_dtn_augmented_ksp_setup
```

代表性结果：

| h/nm | rows | matrix GB | RSS upper GB | elapsed s | status |
|---:|---:|---:|---:|---:|---|
| 8 | 121050 | 0.3346 | 10.43 | 47.65 | completed |
| 6 | 245862 | 0.6585 | 16.16 | 416.97 | completed |
| 5 | 301648 | 0.7987 | 18.67 | 698.63 | completed |
| 4 | 705918 | 1.820 | unavailable | 1496.57 | killed |

`h=5 nm` 时：

```text
estimated_AIJ_matrix_memory ≈ 0.7987 GB
estimated_total_RSS_upper ≈ 18.67 GB
rss_to_matrix_ratio ≈ 23.37
```

因此，direct solve 的实际峰值内存已经约为矩阵本体的二十多倍。`h=4 nm` 的矩阵本体约 1.82 GB，但仍在 MUMPS factorization 阶段被 OS signal 9 kill，说明主要瓶颈是 LU fill-in / factorization workspace，而不是 A 矩阵本体存储。

### 3.3 MUMPS OOC 对照

默认 OOC 完成到：

```text
h = 5 nm
```

但没有让 `h=4 nm` 正式完成。

代表性结果：

| h/nm | matrix GB | OOC RSS upper GB | OOC disk GB | elapsed s | status |
|---:|---:|---:|---:|---:|---|
| 8 | 0.3346 | 9.945 | 3.159 | 65.24 | completed |
| 6 | 0.6585 | 14.86 | 8.350 | 225.73 | completed |
| 5 | 0.7987 | 16.24 | 10.07 | 332.92 | completed |
| 4 | 1.820 | 23.89 | 0 | 1283.12 | failed, INFOG(1)=-90 |

OOC 对 h=5 有一定 RAM 降低作用：

```text
default RSS upper: 18.67 GB
OOC RSS upper:     16.24 GB
OOC disk:          10.07 GB
```

但是 OOC 并没有突破 h=4。默认 OOC h=4 返回 PETSc error code 76 / MUMPS INFOG(1)=-90。调参 OOC `ICNTL(14)=200` 在 h=4 运行 90 分钟超时，保留约 30.09 GB OOC 文件。

因此，OOC 目前应理解为：

```text
可缓解 RAM 压力，但不是根本解决方案；
h=4 nm 仍是当前机器上的 direct/OOC 边界。
```

### 3.4 迭代法内存估算

迭代法只是内存估算，不代表当前已经有可收敛的迭代求解器。

代表性结果：

| h/nm | matrix GB | GMRES(50) GB | ASM+ILU low GB | ASM+ILU high GB |
|---:|---:|---:|---:|---:|
| 5 | 0.7987 | 1.046 | 2.643 | 7.436 |
| 4 | 1.820 | 2.399 | 6.040 | 16.96 |
| 3 | 3.883 | 5.144 | 12.91 | 36.20 |
| 2.5 | 5.881 | 7.812 | 19.57 | 54.86 |
| 2 | 11.74 | 15.64 | 39.12 | 109.56 |

这说明如果未来能找到可收敛的 Maxwell 迭代法/预条件器，内存需求可能显著低于 direct LU。但该估算只能作为：

```text
memory_possible_if_converges
```

不能作为收敛保证。

---

## 4. 对工作站采购的解释

task005 的 extrapolated table 给出了 RAM/SSD 推荐，但需要谨慎解读。表格中的 `recommended_RAM_GB` 更接近最低可尝试配置，而不是 direct LU 的安全配置。

我建议后续按三档理解：

| 目标 | 推荐理解 |
|---|---|
| h≈5 nm | 128 GB 已经明显比当前 14 GB WSL 从容，可用于调试和中等规模测试 |
| h≈4 nm | 128~256 GB 是第一阶段压力测试范围，但 direct/OOC 是否稳定仍需实测 |
| h≈3~2.5 nm | 建议 512 GB 级别更稳妥，SSD scratch 至少 1 TB 级别 |
| h≈2 nm | 建议 1 TB RAM 起步，或转向迭代/预条件/域分解路线 |
| h≤1.5 nm | 低置信外推；direct LU 不应作为主路线 |

当前最合理的真实 3D 大规模分析网格是：

```text
主力网格：h = 5 nm, p = 2
边界测试：h = 4 nm, p = 2
更细网格：h = 3 / 2.5 / 2 nm 暂时更适合 assemble-only、外推或迭代法预研
```

---

## 5. 数据质量与注意事项

### 5.1 RSS 当前是保守上界

当前 `rss_rank_sum_GB` 和 `estimated_total_RSS_upper_GB` 使用：

```text
max_rss_mb * mpi_ranks
```

这不是逐 rank RSS 实测求和，而是保守上界。因此它适合做采购安全估算，但可能高估真实总内存。

后续若要更精确，应增加：

```text
per-rank RSS sum
per-rank RSS max/min/mean
rank imbalance
```

### 5.2 PETSc matrix memory 字段不可作为主依据

CSV 中 `PETSc_matrix_memory_GB` 多数为 0，说明 PETSc 没有返回有效 memory 字段。当前应以：

```text
estimated_AIJ_matrix_memory_GB
```

作为 A 矩阵本体估算依据。

### 5.3 h=10 和 h=12 实际网格相同

`h=10` 和 `h=12` 实际 mesh_cells_resolved 都是：

```text
[11, 11, 15]
```

因此 rows/nnz/matrix memory 相同。这不是错误，而是 mesh generator 的离散取整结果。后续做外推时，应优先使用实际 cells/rows/nnz，而不是 nominal h。

### 5.4 raw_runs 中部分 OOC 文件为空

compare 中显示部分 OOC raw files additions=0。顶层 CSV 和 summary 已经足够支撑主要结论，但 raw_runs 归档不够整洁。后续可以清理空 raw 文件或补充说明。

---

## 6. 对源码改动的审查

本轮主要源码改动在：

```text
src/studies/run_3d_matrix_scale.py
```

改动目标合理：

```text
- GB 换算；
- RSS 上界；
- OOC 文件大小；
- stdout/stderr tail；
- per-case timeout；
- row JSON 输出；
- failure recovery。
```

这些属于 study / diagnostics 脚本增强，不改变主求解器物理逻辑。可以接受。

需要注意的是，目前 per-rank RSS 仍然没有真实收集，`rss_rank_sum_GB` 只是 `max × ranks`。字段名可能让人误以为是真实 sum，后续最好改名或补充真实 per-rank 采集。

---

## 7. 是否建议合并

建议合并 task005 分支。

合并含义应写成：

```text
完成真实 100x100x150 nm Stage 4 block grating p=2 的资源评估：矩阵规模、direct MUMPS 边界、MUMPS OOC 对照、迭代法内存估算和工作站配置外推。
```

不要写成：

```text
完成真实 3D EUV grating 的物理收敛 benchmark。
```

---

## 8. 后续建议

后续可以开 task006，围绕缩小计算域做新的资源与 R/T 收敛测试：

```text
100 nm x 100 nm x 70 nm reduced-height domain
substrate_thickness = 10 nm
grading/grating_height = 50 nm
top air above grating = 10 nm
```

若代码中的 `air_height` 表示从 substrate top 到 top boundary 的总空气高度，则应设置：

```text
air_height = grating_height + top_air_thickness = 60 nm
substrate_thickness = 10 nm
```

这个 task006 应同时测试 p=1 和 p=2，并记录 R/T/A 与资源指标，从而判断缩小 z 向计算域是否在不影响 R/T 的前提下降低内存，使 p=2 h=1 nm 更接近可计算。

---

## 9. 最终结论

```text
task005 通过，建议合并。
```

当前 direct LU 路线下，`h=5 nm, p=2` 是真实 100x100x150 nm 光栅的实用主力网格；`h=4 nm, p=2` 是当前本机失败边界和下一阶段工作站压力测试网格。若目标继续推进到 `h=2.5 nm`、`h=2 nm` 或更细，单纯堆 direct LU 的成本会快速上升，应同步考虑 reduced-height domain、OOC 调参、迭代法/预条件器或域分解路线。
