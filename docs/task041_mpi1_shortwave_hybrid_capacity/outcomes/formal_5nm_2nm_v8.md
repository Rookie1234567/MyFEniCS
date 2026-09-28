# Task041 V8：5 nm 与 2 nm 正式计算进度

> 进度快照（2026-09-28T09:09:29Z），不是最终资格结论。文档基线与运行源码 SHA 分列；本快照基于仓库 HEAD `d86ee4afb352304c9ff0d5042256ad9a7d0c9a4f`，S1 运行也冻结在该 SHA。

## S1：5 nm 完整 consumer 正在运行

本场使用 cell-condensed 后端：先消去单元内部自由度以降低保留系统规模，再恢复完整解并继续检查原物理方程。它是正式注册的 5 nm 路线；当前只确认入口和参数已传入，不把请求参数当成实际因子审计或数值通过。

| 项目 | 当前记录 |
|---|---|
| 状态 | `active / system_setup_stage`；service `task041-v8-5nm-cellcond-formal-20260928.service`；Invocation `755aeb44c48a4d1cbc8bbf6db9f6fd3e`；MainPID `527794`，start ticks `51092431` |
| 时间/源码 | 启动 `2026-09-28T08:58:49Z`；运行源码 SHA `d86ee4afb352304c9ff0d5042256ad9a7d0c9a4f`；累计 wall 最新采样 `403.645936 s` |
| 模型/入口 | 5 nm，W，p6/h4，M480，MPI8×1；注册的 `cell_condensed` DAT；正式 consumer，不是 selected-side 诊断 |
| 实际路径 | public runroot `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8_cell_condensed/task041_5nm_p6h4_m480_mpi8_cell_condensed__hybrid_iterative__mpi8__M480/20260928T085850.487306Z`；worker 位于其 `consumer/` |
| 参数绑定 | worker 实际命令含 target `5e-13`、最多两次修正的注册合同及 `task041_v8_swap_observe_continue`；factor 级实际后端/target 审计尚未输出，记为 `not_yet_observed` |
| 算例进度 | 最近 worker marker 为 `system_setup_stage / one_cell_factor_destroyed`（wall `492.169282 s`）；正式响应完成数、当前 RHS 迭代/残差、R/T/A/E/H 均 `not_run / not_emitted`；`time_target_met=null` |
| 当前资源样本 | 最新可读样本 wall `653.757583 s`：process-tree RSS/authority `32,041,730,048 B`；专属 cgroup current `30,164,492,288 B`、peak `30,228,844,544 B`；低于 warning `47,899,046,707 B`，hard cap `53,221,163,008 B`；启动前 reserve 门已通过 |
| 交换观察 | job/cgroup swap `0 B`；global swap `1,224,704 B`，相对启动基线增量 `0 B`；pswpout `299` 页、增量 `0` 页，pswpin `0`。按 V8 只观察、不单独拒绝或停止 |
| 并行背景 | Task39/Metrology 的启动前 CPU 集与 Task041 CPU1–8 不重叠；邻任务未操作。运行并行，性能不作为无竞争基准 |
| 终态与资格 | 仍运行；finalizer、完整物理/数值 Gate、24 h 目标和 2 nm 均未完成/未判定 |

MPI rank 0–7 实际绑定 CPU 1–8，`numactl --membind=0`；每 rank 数学线程为 1。启动时 ABI、complex128/Int32、同栈、packet descriptor 与正式入口验证通过。最终 swap 策略允许沿用启动时非零的 global 计数；这些观测不替代 RSS/reserve、OOM、磁盘或数值门。

## 可复核入口

| 证据 | 路径 |
|---|---|
| 本阶段机器记录 | [Task041 V8 progress record](records/task041_v8_formal_5nm_2nm.json) |
| service 配置与 argv | `results/task041_review_v8_swap_observe_continue/s1_preparation_20260928T084551Z/task041_v8_5nm_cellcond_formal_service_config.json`；同目录 `systemd_run_argv.json` |
| 启动身份 | `results/task041_review_v8_swap_observe_continue/s1_preparation_20260928T084551Z/startup_identity.json` |
| 持续日志 | `results/task041_v8_5nm_cellcond_formal_run_20260928/markers.jsonl`、`memory_stages.jsonl`；实际 consumer 的 `markers.jsonl` 与 `rank_numa_evidence.jsonl` |
| producer 输入 | legacy descriptor `results/task041_side_balh_component_audit/task041_h3b_legacy_native_packet_descriptor.json`；producer source `b01a5932e4dfaf895e81e0424e0dd88c276fb0d3`，未重跑 QEP |

后续每小时更新同一 progress record；阶段变化、异常和终态及时同步。运行期间只改文档和结果记录，不改冻结数学源码，不重启当前作业。
