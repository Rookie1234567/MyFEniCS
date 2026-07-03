# Outcome Summary

## Task

task005：真实 3D 光栅 p=2 内存、MUMPS OOC 与迭代法资源估算。本轮只做计算资源评估，不把 R/T/A 当作物理收敛结论。

## Branch

`codex/20260703-stage4-real-grating-memory-estimation`

## Physical Model

真实 `stage4_block_grating`：周期 `100 nm x 100 nm`，空气层 `100 nm`，基座 `50 nm`，矩形柱 `50 nm x 50 nm x 50 nm`，`lambda0=13.5 nm`，法向入射，s 偏振。基座和光栅均使用当前 Stage 4 默认 Si 复折射率 `0.999002304859 + 0.00182649365j`。

## Numerical Settings

主线设置：`p=2`，`MPI=8`，`stage4_boundary_model=dtn_port`，`stage4_dtn_assembly=auxiliary`，`stage4_dtn_order_policy=auto_propagating`，`use_pml=false`。

RSS 说明：当前稳定记录的是 `max_rss_mb`，所以 `rss_rank_sum_GB` 和 `estimated_total_RSS_upper_GB` 使用 `max_rss_mb x 8` 的保守上界，不是逐 rank 实测求和。

## Matrix Scale

| h/nm | cells | rows | nnz | AIJ matrix GB | RSS upper GB | status |
|---:|---:|---:|---:|---:|---:|---|
| 20 | 441 | 12738 | 1770216 | 0.03966 | 2.337 | completed |
| 15 | 768 | 21244 | 2827676 | 0.06336 | 2.419 | completed |
| 12 | 1815 | 47950 | 6206384 | 0.1391 | 2.833 | completed |
| 10 | 1815 | 47950 | 6206384 | 0.1391 | 2.849 | completed |
| 8 | 4725 | 121050 | 14930552 | 0.3346 | 4.088 | completed |
| 6 | 9747 | 245862 | 29380416 | 0.6585 | 5.947 | completed |
| 5 | 12000 | 301648 | 35633876 | 0.7987 | 6.303 | completed |
| 4 | 28431 | 705918 | 81208016 | 1.820 | 10.11 | completed |
| 3 | 62475 | 1538710 | 173190752 | 3.883 | 14.68 | completed |
| 2.5 | 96000 | 2356188 | 262332636 | 5.881 | 20.23 | completed |
| 2 | 195075 | 4764870 | 523627904 | 11.74 | 39.38 | completed |

矩阵本体到 `h=2 nm` 仍能完成 assemble-only。此时 rows=4,764,870，nnz=523,627,904，估算 AIJ 矩阵约 11.74 GB。但这只是矩阵本体，不包含 LU fill-in。

## Direct MUMPS Boundary

| h/nm | rows | matrix GB | RSS upper GB | elapsed s | status | failure |
|---:|---:|---:|---:|---:|---|---|
| 20 | 12738 | 0.03966 | 2.889 | 24.736 | completed |  |
| 15 | 21244 | 0.06336 | 3.302 | 8.596 | completed |  |
| 12 | 47950 | 0.1391 | 5.159 | 16.355 | completed |  |
| 10 | 47950 | 0.1391 | 5.023 | 15.913 | completed |  |
| 8 | 121050 | 0.3346 | 10.43 | 47.654 | completed |  |
| 6 | 245862 | 0.6585 | 16.16 | 416.97 | completed |  |
| 5 | 301648 | 0.7987 | 18.67 | 698.63 | completed |  |
| 4 | 705918 | 1.820 | 无 | 1496.57 | killed | stage4_dtn_augmented_ksp_setup |

默认 MUMPS direct 最后完成 `h=5 nm`，第一个失败点是 `h=4 nm`。`h=4` 的矩阵本体在 assemble-only 中约 1.82 GB，但 direct 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill。因此主要瓶颈不是矩阵本体，而是 LU factorization/fill-in 的峰值内存。

`h=5` direct 的保守 RSS 上界约 18.67 GB，是矩阵本体 0.7987 GB 的约 23.37 倍。

## MUMPS OOC

| h/nm | rows | matrix GB | RSS upper GB | OOC disk GB | elapsed s | status | note |
|---:|---:|---:|---:|---:|---:|---|---|
| 15 | 21244 | 0.06336 | 3.184 | 0.3146 | 29.255 | completed |  |
| 12 | 47950 | 0.1391 | 4.447 | 0.9730 | 21.617 | completed |  |
| 10 | 47950 | 0.1391 | 4.638 | 0.9636 | 21.618 | completed |  |
| 8 | 121050 | 0.3346 | 9.945 | 3.159 | 65.238 | completed |  |
| 6 | 245862 | 0.6585 | 14.86 | 8.350 | 225.73 | completed |  |
| 5 | 301648 | 0.7987 | 16.24 | 10.07 | 332.92 | completed |  |
| 4 | 705918 | 1.820 | 23.89 | 0 | 1283.12 | failed | PETSc/MUMPS error |

默认 OOC 完成到 `h=5 nm`，没有让 `h=4 nm` 正式完成。它在 `h=5` 使用约 10.07 GB OOC 文件，保守 RSS 上界约 16.24 GB，低于 default direct 的 18.67 GB。本机 h=5/h=6 中 OOC 反而更快，可能是减少系统内存压力和 swap 的结果，不应泛化成 OOC 总是更快。

调参 OOC `h=4, ICNTL(14)=200` 运行 90 分钟超时，保留约 30.09 GB OOC 文件，说明 `h=4` 已经进入本机不适合继续硬跑的区域。

## Iterative Estimate

迭代法只做内存估算，不代表当前已经实现正式迭代求解器，也不代表频域复数 Maxwell 一定收敛。以 `h=2 nm` 为例，GMRES(50) no heavy PC 估算约 15.64 GB，ASM+ILU 低/高估算约 39.12 到 109.6 GB。它比 direct LU 的外推内存低很多，但风险在收敛性。

## Workstation Recommendation

| h/nm | matrix GB | direct RAM est GB | OOC RAM est GB | OOC SSD est GB | iterative ASM low GB | recommended RAM | recommended SSD | confidence |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2.5 | 5.881 | 147 | 70.57 | 112 | 19.57 | 128 GB | 256 GB | medium |
| 2 | 11.74 | 293.5 | 140.9 | 223 | 39.12 | 256 GB | 512 GB | medium |
| 1.5 | 22.88 | 572.1 | 274.6 | 542.2 | 76.49 | 512 GB | 2048 GB | low |
| 1 | 65.45 | 1636 | 785.4 | 1896 | 219.6 | 2048 GB | 4096 GB | low |
| 0.5 | 394.5 | 9863 | 4734 | 16120 | 1332 | 8192 GB | 32768 GB | low |

建议：如果目标只是继续 `h=5 nm` 左右的 direct/OOC 资源评估，128 GB 工作站已经明显比当前 14 GB WSL 从容。若目标是推进 `h=3` 到 `h=2.5 nm` 的真实 3D p=2 计算，建议至少 512 GB RAM，并准备 1 TB 级别 SSD scratch。若目标包含 `h=2 nm` 或更细，建议按 1 TB RAM 起步，并准备 2 TB 或更大的高速 SSD scratch；`h=1.5/1.0/0.5` 属于低置信外推，当前 direct LU 路线很可能需要超过 1 TB 的资源或改用可收敛的迭代/预条件策略。

## Known Issues

- `h=4` default direct 被 OS signal 9 kill，没有完整 run_summary，只能结合 assemble-only 和 stdout tail 恢复边界。
- 默认 OOC 的 `h=4` 是 MUMPS `INFOG(1)=-90`，不是完成结果。
- tuned OOC 的大体积 OOC 文件保留在本地 `results/`，未归档到 Git。
- 本轮没有运行真实物理收敛 R/T benchmark。

## Next Questions for Review

1. 是否接受以 `max_rss_mb x ranks` 作为保守总 RSS 上界，还是下一轮必须实现逐 rank RSS 聚合？
2. 是否需要把 MUMPS OOC 的 profile 暴露更多参数，例如 `ICNTL(14)`，用于系统化调参？
3. 后续是否转向迭代求解器和预条件器原型，而不是继续扩大 direct LU 资源？
