# V6-1：post-compaction h4 setup-only 受控停止

## 结论

这是 V6-1 唯一一次正式 setup-only attempt。它只准备 h4/M480 的 exact-side 计算对象，不执行外层求解、恢复、场重构或 R/T/A。进程树在 setup 峰值超过冻结上限后被 watchdog 完整终止；因此本阶段分类为 `memory_terminate`，exact-side full formal 被禁止，后续 exact-side 只能作为 oracle。

| 项目 | 实测/分类 |
| --- | --- |
| source SHA | `35b1532ee6498c2e5e6e2579bbfe4a821dbf1b01` |
| run root | `results/task039_v6_h4_post_compaction_exact_side_setup_only_mpi8_35b1532e` |
| exit / classification | `exit_status=1` / `memory_terminate` |
| wall | `2965.129026 s`（run manifest start/end） |
| process-tree RSS peak | `45,857,816,576 B = 42.70841979980469 GiB` |
| effective hard stop | `45,118,258,790 B = 42.019652938470244 GiB` |
| frozen setup limit | `42.019652939 GiB` |
| swap | `0 B`，zero-swap pass |
| termination | process group SIGTERM，5 s grace；无需 SIGKILL，整棵进程组已退出 |

峰值出现在 `2026-08-19T10:27:29.499811+00:00` 的采样，sample elapsed 为 `2963.783183269028 s`。观测峰值比冻结上限高 `0.688766861 GiB`；这是 `0.25 s` 轮询与终止时序产生的观测 overshoot，不是允许的内存余量，也不改变 Gate 失败。

```math
\mathrm{peak\_GiB}=\frac{45{,}857{,}816{,}576}{2^{30}}=42.70841979980469
```

## 身份与执行边界

| 约束 | 证据 |
| --- | --- |
| 输入 | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| packet manifest | `results/task039_v4_h4_m480_shared_packet_eaad0f94/manifest.json`，SHA256 `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| packet identity | `identity.json`，SHA256 `b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690` |
| MPI/ABI | MPI8，qualified complex128/Int32/OpenMPI 栈，线程设为 1 |
| packet/QEP | packet marker `qep_calls=0`；packet mmap 已释放；最终 packet/QEP release Gate 因受控停止为 `not_available` |
| solve/recovery/field/RTA | `not_run` |

正式 raw 的 compact 索引见 [V6-1 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v6_post_compaction_exact_side_setup_v1.json)。完整 raw 保留在 ignored 目录 [V6-1 raw](../../../results/task039_v6_h4_post_compaction_exact_side_setup_only_mpi8_35b1532e)。

## Marker 与生命周期

共落盘 19 个 stage-aligned rows。关键阶段如下；RSS 是 process-tree marker 对齐样本，不是某个对象的单独因果测量。

| marker | worker elapsed | marker-aligned RSS | 状态 |
| --- | ---: | ---: | --- |
| `one_cell_factor_ready` | 544.740779 s | 21.161144 GiB | 一个 one-cell factor 建立，`factor_count=1` |
| `one_cell_lift_columns_end` | 711.447991 s | 24.441360 GiB | lift columns 完成 |
| `one_cell_apply_columns_end`（forward） | 725.377589 s | 26.449730 GiB | apply columns 完成 |
| `one_cell_apply_columns_end`（backward） | 739.032588 s | 27.348118 GiB | apply columns 完成 |
| `bottom_projection_columns_end` | 1661.481725 s | 27.728413 GiB | bottom projection 完成 |
| `top_projection_columns_end` | 2589.291414 s | 28.689415 GiB | top projection 完成 |
| `one_cell_factor_destroyed` | 2598.917558 s | 29.220837 GiB | cleanup completed；这是最后 worker marker |

`one_cell_factor` 在 ready 时为 1，并在最后 marker 中完成销毁；这不等同于 V6 要求的 final bottom/top exact-factor cleanup 0/0。finalizer 未运行到可审计状态，故 `factor_count_after_final_cleanup`、`packet_qep_refs_released` 和最终 action cleanup 均为 `not_available`。`outer_ksp_setup_ready` 没有 marker/sample，outer-ready Gate 为 `not_available`。

## 负结论与后续边界

本阶段 setup resource Gate 为 false。由于硬线触发，exact-side full formal 不得运行，exact-side 仅保留为 oracle；不存在 official R/T/A，也没有 recovery、field、outer solve 结果。ordinary defaults、既有 V5 负结果和 raw 均不改写。V6 side layer graph 未取得，不得从这些 RSS 或对象 marker 推断层结构。

raw hash 与 stage/ledger 路径详见 compact record；本次只提交 compact evidence，不提交 raw artifact。
