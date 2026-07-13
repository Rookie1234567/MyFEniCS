# 输出 Schema 与可视化

## 普通 2D/3D summary

必须包含 resolved config、case/stage、mesh cells/DoF、constraint 统计、solver/backend、残差、计时、RSS（可用时）、field metrics、power metrics 和 status。complex 值以 `[real,imag]` 或明确字符串序列化。

## benchmark record

| 字段组 | 关键字段 |
|---|---|
| 身份 | `benchmark_id`, `metadata.commit_sha/branch/git_dirty/command/timestamp` |
| 环境 | image、digest、host id、PETSc/DOLFINx environment file |
| 来源 | actual source command/root、canonical rerun command/root、provenance |
| 物理 | geometry/material/wavelength/angles/polarization/degree/h/MPI |
| 迭代 | profile、coarse/slab/sm2、reason、iterations |
| 可信度 | reported/condensed/full residual、qualified/deviations |
| 资源 | current/final/RTA/overall peak total RSS |
| 物理结果 | official R/T/A、closure |

## progress/parameters

`*_parameters.json` 保存启动参数，`*_progress.json` 可在中断时恢复最后 stage/iteration/RSS；最终 record 才是 Gate 输入。progress 不等于 pass。

## Task29 Case050 内存字段

Case050 同时保存三种不可混写的量：worker-rank 当前 RSS 的同刻和、MPI 进程树当前 RSS、cgroup charged current/peak；另把各 rank 历史峰值之和标成 upper bound。`historical_peak_source` 必须说明它取所有完整 progress checkpoint 与 solver summary 的最大值。

`matrix_inventory` 区分 base、augmented 与 factor。`factor_inventory.derived_ratios` 只做 nnz/统一 estimator 的代数相除；若 PETSc factor `fill_ratio_*` 或 `memory` 返回 0，则保留 raw 0 并标记 unavailable，不能替换成猜测的 MUMPS INFOG/RINFOG 含义。

Task29 OOC timeline 新增 `ooc_scratch_file_count/ooc_scratch_bytes`、`mpi_process_tree_read_bytes/write_bytes` 和 `mpi_process_tree_blkio_delay_seconds`。summary 中保存这些字段的最大观测值及明确语义：scratch 是同刻目录占用，I/O bytes 是存活进程树累计 counter，delay 是各进程 block-I/O delay 之和，不可冒充 wall time。候选 record 的 `lifecycle_options.release_base_after_augmentation` 说明 H1 opt-in 是否启用；ordinary default 为 `false`。

## 场文件

2D/串行可直接写单 VTU；3D MPI 写 rank-local VTU 与 PVD。`postprocess_3d` 过滤 ghost cells，避免 ParaView 数量/积分重复。场名区分 `E_total/E_scat/E_background` 和 real/imag/abs。

## 日志

`run_log.txt` 记录阶段与错误；solver log 记录参数/残差；PETSc `-log_view` 可输出性能但不应替代项目 summary。大文本日志不塞进 canonical JSON。

## 可视化边界

图用于理解场，不用于自动 Gate。数值判定来自 JSON/CSV。`render_stage4_comsol_views.py` 只读结果生成切面；不编辑场数据。
