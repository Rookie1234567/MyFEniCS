# Outcome Summary

## Task

task006：在 100 nm x 100 nm x 70 nm reduced-height Stage 4 真实 3D 光栅中，继续评估 p=1/p=2 网格收敛、R/T/A、MUMPS direct/OOC 边界、memory profiling 和工作站资源建议。

本次补充重做的重点是：

- 把 `src/studies/run_3d_memory_profile.py` 的进程树内存结果写进 summary。
- 解释为什么 assemble-only 的 RSS 看起来可接受，但 direct/OOC 仍会失败。
- 对比 task005 中 `RSS upper = 39.38 GB` 仍可完成 assemble-only 的原因。
- 补跑更多 MUMPS OOC tuned 点。
- 外推 h=1、0.5、0.25 nm 的 RAM/SSD 需求。

## Branch

`codex/20260704-reduced-height-grating-convergence-memory`

## Geometry And Physics

本轮 reduced-height domain 使用：

| 参数 | 数值 |
|---|---:|
| period_x / period_y | 100 nm / 100 nm |
| substrate_thickness | 10 nm |
| grating_height | 50 nm |
| top air above grating | 10 nm |
| `air_height` 参数 | 60 nm |
| total z height | 70 nm |
| `lambda0` | 13.5 nm |
| n_substrate / n_grating | `0.999002304859 + 0.00182649365j` |
| 入射 | normal incidence, s polarization |
| 边界 | `stage4_boundary_model=dtn_port` |
| DtN | `stage4_dtn_assembly=auxiliary`, `stage4_dtn_order_policy=auto_propagating` |

代码里 `--air-height` 的含义是从 interface `z=0` 到 top boundary 的高度，所以 70 nm 总高对应 `air_height=60 nm` 和 `substrate_thickness=10 nm`。

## Code Changes

本轮保留并新增了这些代码改动：

- 修正真实 block grating 的 automatic top probe：有光栅块时，top probe 从 `grating_z_max` 到 `physical_z_max` 之间取点，而不是从 interface 到 top boundary 取点。70 nm 域中默认 top probe 从错误的 `z=45 nm` 修正为 `z=57.5 nm`。
- `run_3d_matrix_scale.py` 支持几何、材料、网格、R/T/A、progress fallback 和增量 CSV 输出。
- 新增 `run_3d_memory_profile.py`：对子进程树 RSS、单进程 RSS、swap、OOC scratch 和最新 progress stage 做采样，并在 timeout 时杀掉整个进程树。
- 修正 MUMPS OOC PETSc extra options 优先级：profile 先给默认值，`--petsc-extra-option` 再覆盖默认值。否则 `mat_mumps_icntl_14=200` 会被 `mumps_ooc` profile 的默认 `80` 覆盖，导致 tuned OOC 实际没有生效。

## Memory Profiling

memory profiling 运行点：

| 项 | 数值 |
|---|---:|
| case | p=2, h=5 nm, MPI=8, default direct |
| status | completed |
| profiler elapsed | 131.58 s |
| run summary elapsed | 119.94 s |
| peak process-tree RSS sum | 13.646 GB |
| peak single-process RSS | 2.030 GB |
| peak swap used | 0.161 GB |
| peak OOC disk | 0 GB |
| last stage | `stage4_dtn_augmented_solve:end` |

对应的 matrix-scale CSV 中，p=2 h=5 default direct 的 `estimated_total_RSS_upper_GB` 是 16.68 GB。这个字段不是实测进程树总内存，而是 `max_rss_mb x ranks` 的保守上界。memory profiler 给出的 13.65 GB 说明：上界有参考价值，但不能直接等同于实际物理内存占用。

更重要的是，失败算例的 RSS 更容易低估，因为进程可能在 MUMPS factorization 峰值阶段被 OS 杀掉，来不及写出最后的 progress 或 run summary。因此，像 p=1 h=1.5 default direct 里看到的 7.01 GB 只是最后一次成功记录的 RSS 上界，不是失败瞬间的真实峰值。

## Assemble-only Scale

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

这里要特别区分两个概念：

- `estimated_AIJ_matrix_memory_GB` 是稀疏矩阵 A 本体的估计存储。
- `estimated_total_RSS_upper_GB` 是 `max_rss_mb x 8 ranks` 的保守上界，不是实际进程树 RSS，也不是 LU factorization 峰值。

## Why Assemble Can Pass But Solve Fails

p=1 h=1.5 的 assemble-only 确实完成了，最后记录 RSS upper 约 7.31 GB。但 p=1 h=1.5 default direct 失败时，最后一次 progress 停在：

```text
stage4_dtn_augmented_ksp_setup begin
matrix_rows = 689,052
nnz = 34,676,382
AIJ matrix estimate = 0.780 GB
last recorded max RSS = 897.7 MB per rank
```

随后 MPI 进程被 signal 9 kill。也就是说，记录里的 7.01 GB 发生在 MUMPS factorization 真正冲高之前。它只能说明“进入 KSP setup 前还没有爆”，不能说明“factorization 峰值也只有 7 GB”。

direct LU 的内存不等于矩阵 A 本体。它还包括：

- DtN auxiliary unknowns 和 coupling block。
- MUMPS symbolic/numeric factorization workspace。
- LU fill-in。
- MPI rank 上的不均衡临时分配。
- PETSc/MUMPS 内部 buffer。

所以 14 GB WSL 内存是否足够，不能只看 assemble-only 的 RSS。

## Task005 39.38 GB Why Could Complete

task005 中的 `RSS upper = 39.38 GB` 对应的是 150 nm 原始域 p=2 h=2 assemble-only。它能完成并不矛盾，原因是：

1. 39.38 GB 是 `max_rss_mb x 8` 的保守上界，不是实测进程树总 RSS。
2. 那个点的 AIJ matrix 本体约 11.74 GB，不是 39.38 GB。
3. 它只做 assemble-only，不做 MUMPS LU factorization。
4. Docker/WSL 可以使用 swap 和内存 overcommit，短时间 assemble 峰值不等于稳定可求解内存。

task006 中 p=2 h=1 则不同：这里 AIJ matrix 本体估计已经达到 39.63 GB，nnz 约 1.77e9，swap 峰值记录约 37.85 GB，并且在 base matrix assembled 后被 signal 9 kill。这已经不只是 RSS 上界大，而是矩阵本体也进入本机不可承受范围。

## Default Direct R/T/A

| p | h/nm | R | T | A_volume | R+T+A | status |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 5 | 2.6207e-3 | 0.969913 | 0.027466 | 1.000000 | completed |
| 1 | 4 | 4.9308e-3 | 0.966183 | 0.028886 | 1.000000 | completed |
| 1 | 3 | 1.4020e-3 | 0.967219 | 0.031379 | 1.000000 | completed |
| 1 | 2.5 | 6.6172e-4 | 0.967196 | 0.032143 | 1.000000 | completed |
| 1 | 2 | 6.9763e-6 | 0.966357 | 0.033636 | 1.000000 | completed |
| 2 | 5 | 7.0797e-4 | 0.964603 | 0.034689 | 1.000000 | completed |
| 2 | 4 | 1.0006e-6 | 0.963855 | 0.036144 | 1.000000 | completed |

default direct 边界：

- p=1 完成到 h=2，h=1.5 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill。
- p=2 完成到 h=4，h=3 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill。
- 已完成点的 `R+T+A_volume` 都在约 `1e-14` 到 `1e-13` 闭合。

## MUMPS OOC Extra Runs

新增补跑了 tuned OOC，关键变化是 `mat_mumps_icntl_14=200` 现在能覆盖 profile 默认值。

| p | h/nm | profile | status | AIJ GB | RSS upper GB | OOC disk GB | elapsed s | R | T | A_volume | note |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2 | 5 | OOC tuned | completed | 0.421 | 16.910 | 4.946 | 140.7 | 7.0797e-4 | 0.964603 | 0.034689 | 和 default direct 数值一致 |
| 1 | 1.5 | OOC tuned | failed | 0.780 | 15.286 | 0 | 230.9 |  |  |  | PETSc 76, MUMPS INFOG(1)=-90 |
| 2 | 4 | OOC tuned | completed | 0.972 | 23.626 | 14.242 | 1180.4 | 1.0006e-6 | 0.963855 | 0.036144 | 突破默认 OOC 超时边界 |
| 2 | 3 | OOC tuned | failed | 2.045 | 18.130 | 0 | 358.5 |  |  |  | PETSc 76, MUMPS INFOG(1)=-90 |

结论：

- OOC tuned 对 p=2 h=4 有效：default OOC 曾 5400 s timeout，tuned OOC 完成。
- OOC tuned 没有把 p=2 推到 h=3，也没有把 p=1 推到 h=1.5。
- p=2 h=4 OOC 比 default direct 慢，但 RSS upper 从 direct 的 31.67 GB 降到 23.63 GB，并用约 14.24 GB OOC scratch 换取完成。
- p=2 h=3 和 p=1 h=1.5 的失败都是 MUMPS numerical factorization 错误 `INFOG(1)=-90`，不是正常收敛失败。

## 70 nm vs 150 nm

| p | h/nm | R_70 | R_150 | dR | T_70 | T_150 | dT | A_70 | A_150 | dA |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 0.002621 | 0.021129 | -0.018508 | 0.969913 | 0.905253 | 0.064660 | 0.027466 | 0.073619 | -0.046152 |
| 2 | 5 | 0.000708 | 0.000196 | 0.000512 | 0.964603 | 0.905421 | 0.059183 | 0.034689 | 0.094383 | -0.059695 |

70 nm 域确实显著降低资源，但目前不能视为 150 nm 的物理等价替代。R/T/A 差异说明后续需要单独做 top/bottom port distance 或空气/基座厚度扫描。

## Workstation Recommendation

这个外推基于 p=2 reduced-height domain 的矩阵规模：

- h=5 到 h=1 使用本轮实际记录的 AIJ matrix 规模，其中 h=1.5 是 timeout 前 progress 记录，h=1 是 failed 前 progress 记录。
- h=0.5 和 h=0.25 使用细网格拟合：`matrix_GB = 39.824 * h^(-2.823)`。
- direct RAM 粗估取 `40 x matrix_GB`，参考 p=2 h=5/h=4 default direct 的 RSS upper/matrix ratio。
- tuned OOC RAM 粗估取 `25 x matrix_GB`，参考 p=2 h=4 tuned OOC。
- tuned OOC SSD scratch 粗估取 `18 x matrix_GB`，比 p=2 h=4 实测 14.65x 留余量。
- iterative low 只是“如果未来有可收敛迭代法”的低内存方向，不代表当前已经可用。

| h/nm | source | matrix GB | direct RAM est GB | tuned OOC RAM est GB | OOC SSD est GB | iterative low GB | 建议 |
|---:|---|---:|---:|---:|---:|---:|---|
| 5 | observed completed | 0.421 | 16.9 | 10.5 | 7.6 | 1.7 | 当前机器可跑，32-64 GB 更从容 |
| 4 | observed completed | 0.972 | 38.9 | 24.3 | 17.5 | 3.9 | 64 GB 级工作站更合适 |
| 3 | observed completed assemble only | 2.045 | 81.8 | 51.1 | 36.8 | 8.2 | 建议 128 GB 起步，当前 OOC tuned 仍失败 |
| 2.5 | observed completed assemble only | 2.939 | 117.6 | 73.5 | 52.9 | 11.8 | 建议 128-256 GB |
| 2 | observed completed assemble only | 5.794 | 231.8 | 144.9 | 104.3 | 23.2 | 建议 256-512 GB |
| 1.5 | observed timeout | 12.632 | 505.3 | 315.8 | 227.4 | 50.5 | 建议 512 GB-1 TB，置信度低 |
| 1 | observed failed | 39.628 | 1585.1 | 990.7 | 713.3 | 158.5 | 建议 2 TB 级，direct LU 不经济 |
| 0.5 | extrapolated | 281.720 | 11268.8 | 7043.0 | 5071.0 | 1126.9 | 已超常规 workstation，考虑集群/迭代法 |
| 0.25 | extrapolated | 1992.925 | 79717.0 | 49823.1 | 35872.6 | 7971.7 | 不建议 direct/OOC 路线 |

对“h 能不能突破 1 nm”的判断：

- 以当前 direct LU/OOC 路线，h=1 nm 的 p=2 reduced-height 已经不适合 14 GB WSL，也不适合普通 128 GB 工作站。
- h=0.5 nm 和 h=0.25 nm 的 direct/OOC 估计进入多 TB 到数十 TB 级别，不能靠简单换普通工作站解决。
- 如果未来目标是 h<=1 nm，应优先开发可收敛迭代法、问题分解、阶数截断策略、局部加密或更物理等价的 reduced domain，而不是继续堆 direct LU。

## Validation

本轮补充后的验证：

```text
python -m json.tool parameters.json
python -m py_compile src/solvers/common_3d_solve.py src/test/test_18_3d_direct_solver_profile_cleanup.py src/postprocessing/diffraction_3d.py src/studies/run_3d_matrix_scale.py src/studies/run_3d_memory_profile.py
git diff --check
Docker complex mode: python3 -m unittest src.test.test_18_3d_direct_solver_profile_cleanup src.test.test_11_stage4_diffraction_modes
Docker complex mode: python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
targeted tests: 16 tests OK
full tests: 69 tests OK, skipped=10
```

outcomes 中未发现 `vtu/bp/h5/xdmf/pvd` 或 `mumps_ooc_files` 大体积文件。

## Known Issues

- `estimated_total_RSS_upper_GB` 是保守上界，不是实测进程树 RSS。当前只有 `run_3d_memory_profile.py` 的 p=2 h=5 default direct 代表真实进程树采样。
- 失败点的 RSS 可能低估，因为进程被 kill 后没有机会写出峰值。
- OOC tuned 需要额外 PETSc 参数覆盖，现在代码已修正；旧的 default OOC 结果不能代表 tuned OOC。
- 70 nm 与 150 nm R/T/A 差异明显，reduced-height domain 当前只能作为资源探索，不应作为最终物理 benchmark。

## Next Questions for Review

1. 是否接受把 p=2 h=4 tuned OOC 作为当前 reduced-height direct/OOC 的最细可完成边界？
2. 是否开新 task 做 top/bottom port distance 扫描，判断 70 nm、90 nm、110 nm、150 nm 的 R/T/A 是否趋于稳定？
3. 是否下一阶段转向迭代求解器/预条件器原型，而不是继续扩大 MUMPS direct/OOC？
