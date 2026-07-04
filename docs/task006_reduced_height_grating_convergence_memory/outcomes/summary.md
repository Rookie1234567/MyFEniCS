# Outcome Summary

## Task

task006：70 nm 缩短计算域真实 3D 光栅 p=1/p=2 收敛、资源与 R/T/A 分析。

## Branch

`codex/20260704-reduced-height-grating-convergence-memory`

## 几何和传参

代码中 `--air-height` 会同时设置 `air_height` 与 `z_max`，语义是从 substrate top / interface `z=0` 到 top boundary 的总高度。本轮 reduced-height domain 使用：

| 参数 | 数值 |
|---|---:|
| period_x / period_y | 100 nm / 100 nm |
| substrate_thickness | 10 nm |
| grating_height | 50 nm |
| top air above grating | 10 nm |
| air_height 参数 | 60 nm |
| total z height | 70 nm |

基座和光栅均使用复折射率 `0.999002304859 + 0.00182649365j`，法向入射，s 偏振，`stage4_boundary_model=dtn_port`，`stage4_dtn_assembly=auxiliary`，`stage4_dtn_order_policy=auto_propagating`。

## 代码修正

70 nm 域暴露了一个后处理问题：默认 top probe 原先按 interface 到 top boundary 的 0.75 位置给出 `z=45 nm`，会落入 50 nm 高光栅内部。本轮已修正为有光栅块时从 `grating_z_max` 到 `physical_z_max` 之间取自动 top probe；70 nm 域默认 top probe 为 `57.5 nm`。

## Assemble-only 资源规模

| p | h/nm | MPI | rows | nnz | A matrix GB | RSS upper GB | status |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 5 | 8 | 19,482 | 1.654e6 | 0.0371 | 2.368 | completed |
| 1 | 4 | 8 | 45,844 | 3.375e6 | 0.0758 | 2.880 | completed |
| 1 | 3 | 8 | 98,628 | 6.400e6 | 0.1438 | 3.102 | completed |
| 1 | 2.5 | 8 | 142,896 | 8.830e6 | 0.1984 | 3.887 | completed |
| 1 | 2 | 8 | 286,292 | 1.615e7 | 0.3631 | 4.696 | completed |
| 1 | 1.5 | 8 | 689,052 | 3.468e7 | 0.7802 | 7.312 | completed |
| 1 | 1 | 8 | 2,148,978 | 9.676e7 | 2.1787 | 13.552 | completed |
| 2 | 5 | 8 | 142,896 | 1.880e7 | 0.4213 | 4.655 | completed |
| 2 | 4 | 8 | 347,318 | 4.337e7 | 0.9720 | 7.217 | completed |
| 2 | 3 | 8 | 759,698 | 9.126e7 | 2.0455 | 10.621 | completed |
| 2 | 2.5 | 8 | 1,106,844 | 1.311e8 | 2.9389 | 17.343 | completed |
| 2 | 2 | 8 | 2,235,190 | 2.585e8 | 5.7944 | 19.237 | completed |
| 2 | 1.5 | 8 | 5,416,432 | 5.634e8 | 12.632 | 14.442 | timeout |
| 2 | 1 | 8 | 16,992,540 | 1.767e9 | 39.628 | 18.632 | failed |

`p=2, h=1 nm` 在 base matrix assembled 后被 signal 9 kill。该点 rows=16,992,540、nnz=1,767,279,728，AIJ 矩阵估计约 40.58 GB，swap 峰值约 37.85 GB。

## Default Direct 和 R/T/A

| p | h/nm | R | T | A_volume | R+T+A | closure | status |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 5 | 2.6207e-3 | 0.969913 | 0.027466 | 1.000000 | 4.22e-15 | completed |
| 1 | 4 | 4.9308e-3 | 0.966183 | 0.028886 | 1.000000 | -4.88e-15 | completed |
| 1 | 3 | 1.4020e-3 | 0.967219 | 0.031379 | 1.000000 | 7.55e-15 | completed |
| 1 | 2.5 | 6.6172e-4 | 0.967196 | 0.032143 | 1.000000 | -8.77e-15 | completed |
| 1 | 2 | 6.9763e-6 | 0.966357 | 0.033636 | 1.000000 | -1.49e-14 | completed |
| 2 | 5 | 7.0797e-4 | 0.964603 | 0.034689 | 1.000000 | -1.14e-14 | completed |
| 2 | 4 | 1.0006e-6 | 0.963855 | 0.036144 | 1.000000 | 5.04e-14 | completed |

p=1 default direct 完成到 `h=2 nm`，`h=1.5 nm` 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill。p=2 default direct 完成到 `h=4 nm`，`h=3 nm` 在同一阶段被 signal 9 kill。所有完成点的 `R+T+A_volume` 均在约 `1e-14` 到 `1e-13` 量级闭合。

## 收敛判断

p=1 的 R 随 h 细化整体降低，`h=2` 时 `R≈6.98e-6`、`T≈0.96636`、`A≈0.03364`。p=2 在 `h=5` 到 `h=4` 之间 R 从 `7.08e-4` 降到约 `1.0e-6`，T/A 变化约 `1e-3` 到 `1.5e-3`。本轮能跑到的 p=2 finest 是 `h=4`，还不能声称最终物理收敛，但 p=2 比 p=1 在较粗网格上明显更接近低反射结果。

## 70 nm vs 150 nm

| p | h/nm | R_70 | R_150 | dR | T_70 | T_150 | dT | A_70 | A_150 | dA |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 0.002621 | 0.021129 | -0.018508 | 0.969913 | 0.905253 | 0.064660 | 0.027466 | 0.073619 | -0.046152 |
| 2 | 5 | 0.000708 | 0.000196 | 0.000512 | 0.964603 | 0.905421 | 0.059183 | 0.034689 | 0.094383 | -0.059695 |

70 nm 与 150 nm 在 `h=5` 上的 R/T/A 差异明显。缩短 z 向计算域显著降低资源，但当前不能把 70 nm 视为与 150 nm 物理等价的计算域；后续需要专门做 top/bottom port distance 或空气/基座厚度扫描。

## OOC 和 MPI=1

MUMPS OOC 未突破关键边界：p=1 `h=2` 完成，但 p=1 `h=1.5` 仍失败；p=2 `h=4` OOC 运行 5400 s 超时，未继续 h=3。MPI=1 完成了 p=1 `h=5/h=3` 与 p=2 `h=5`，但明显慢于 MPI=8；p=1 `h=2` 在 MPI=1 下超时。

## h=1 nm 可行性

p=1 `h=1 nm` assemble-only 可完成，但没有进入 direct，因为 p=1 `h=1.5` direct 已失败。p=2 `h=1 nm` assemble-only 已经越界：base matrix rows≈16.99M，nnz≈1.77e9，AIJ 矩阵约 40 GB。当前 14 GB WSL 不适合 p=2 `h=1 nm`；即便只 assemble 也不可行。

## 推荐后续组合

本机 reduced-height domain 下，建议后续主力调试组合为 p=2 `h=5` 或 p=2 `h=4`；如果要看更细网格，p=1 `h=2` 可作为低阶参考。p=2 `h=3` 及更细需要更大 RAM，或者转向迭代/预条件/域分解路线。

## Memory Profiling

新增 `src/studies/run_3d_memory_profile.py`，并运行了 p=2 `h=5` MPI=8 default direct。`memory_profile_summary.csv` 显示进程树 RSS 峰值约 13.65 GB，单进程 RSS 峰值约 2.03 GB，主要内存增长集中在 `stage4_dtn_augmented_solve` 附近，而不是单纯 base matrix 组装。

## Known Issues

- RSS 仍是 `max_rss_mb x ranks` 的保守上界；memory profiler 提供了代表算例的进程树 RSS，但尚未接入每个 matrix-scale case。
- p=2 `h=1` 的失败行依赖 `progress_3d.jsonl` fallback，缺少完整 `run_summary.json`。
- 70 nm 与 150 nm 结果差异明显，reduced-height domain 目前只能作为资源缩减探索，不能直接作为最终物理 benchmark。

## Next Questions for Review

1. 是否需要开独立 task 做 top/bottom port distance 扫描，判断 70 nm、90 nm、110 nm、150 nm 的 R/T/A 差异？
2. p=2 h=3 的下一步是更大内存 direct/OOC，还是优先开发迭代预条件器？
3. 是否把 memory profiler 的逐 rank RSS 采集进一步接入 matrix-scale 常规输出？
