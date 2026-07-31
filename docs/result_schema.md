# 结果字段说明

## 输出目录

| 运行类型 | 重型输出 | 轻量证据 | Git |
|---|---|---|---|
| ordinary | `results/<case>.../` | 同目录 summary | 整体忽略 |
| benchmark | `benchmarks/artifacts/<category>/` | `benchmarks/records/*.json` | artifact 忽略，record 跟踪 |

普通 runner 的 `--results-root` 缺省时固定回到仓库 `results/`。benchmark scripts 必须显式覆盖；历史 source run 不能伪装成新 canonical artifact。

## Ordinary 3D summary

| 字段 | 含义 |
|---|---|
| `case_status`, `official_result` | 求解是否完成且可作正式结果 |
| `linear_system_relative_residual` | 完整 ordinary 线性系统残差 |
| `max_rss_mb` | 单 rank 最大峰值，仅诊断 |
| `total_peak_rss_mb/gb` | 所有 MPI ranks 峰值之和，容量规划口径 |
| `solver_backend` | MUMPS/direct profile |
| `R_total/T_total/A_volume_total` | official 功率 |
| `energy_closure_error_*` | port-volume 闭合 |

## Benchmark record 元数据

| 字段 | 必需 | 含义 |
|---|---:|---|
| `benchmark_id` | 是 | 与 manifest 对应的稳定 ID |
| `metadata.commit_sha/branch/git_dirty` | 是 | source checkout 身份 |
| `metadata.command` | 是 | 执行命令或 canonical script |
| `metadata.timestamp_utc` | 是 | UTC 时间 |
| `metadata.container_image/digest` | 是 | 运行环境身份 |
| `metadata.host_environment_id` | 是 | 主机/WSL 配置标签 |
| `metadata.provenance` | 是 | clean rerun、historical source 或 reviewed reference |
| `resolved_config` | 新运行必需 | JSON defaults 与 CLI override 合并结果 |
| `qualified_profile` | 新运行必需 | 是否完全落在 canonical qualification 内 |
| `qualification_deviations` | 新运行必需 | 参数域外差异 |
| `artifact_root/directory` | 新运行必需 | 重型输出位置 |

旧记录由 Task28 response v1 补充 provenance；只有新 runner 生成的记录拥有完整 resolved config。

## Task029 direct-memory record

Case050 的 candidate/summary 额外包含：

| 字段 | 含义 |
|---|---|
| `memory.max_simultaneous_total_rss_mb` | 同一外部采样时刻所有 worker rank 当前 RSS 的和；可能重复计算共享页 |
| `memory.max_mpi_process_tree_rss_mb` | `mpiexec` 子树的同时 RSS，包含非 worker helper/launcher |
| `memory.max_container_cgroup_current_mb` | cgroup 实际 charged current 的采样最大值 |
| `memory.container_cgroup_peak_mb_at_end` | 内核 cgroup high-water mark |
| `memory.sum_rank_historical_peaks_mb_upper_bound` | 所有完整 checkpoint 与 solver summary 中最大的 rank 历史峰值和，只作上界 |
| `memory.historical_peak_source` | historical upper bound 的聚合来源，防止误取较早 summary |
| `matrix_inventory.base/augmented` | rows、nnz used/allocated/unneeded、mallocs 与统一 storage estimate |
| `factor_inventory.matrix_stats` | backend 实际暴露的 factored Mat 结构；不得对 factored Mat 再调用 assemble |
| `factor_inventory.derived_ratios` | 仅由 factor/augmented nnz 和同一 estimator 代数相除，不解释 MUMPS raw index |
| `factor_inventory.mumps_raw_infog/rinfog` | raw index telemetry；无官方映射时不赋予语义 |
| `candidate_disposition` | 数值通过后对性能资格的独立处置；不得只读顶层 `status=pass` |
| `qualification.memory_reduction_20pct_gate` | 候选是否达到 h2/engineering 的 20% 门槛 |
| `ooc_telemetry.scratch_peak_bytes` | OOC 目录同刻最大占用，不属于 RAM |
| `ooc_telemetry.process_tree_*` | 存活 MPI 进程树累计 I/O counter 的最大观测值 |

PETSc 返回的 factor `fill_ratio_*` 或 `memory=0` 必须保留为原始值并标记不可用；不得把统一 nnz estimator 当成 allocator-accounted factor memory。

Task29 h2 决策由 `gate_decision.csv` 的 G1–G10 共同决定。`h2_memory_prediction.md` 同时保存 DoF power-law 与 factor-nnz/fill 两条外推、中央值和敏感性区间；`h2_launch_decision=not_run` 是安全处置，不等于 solver failure。当前精简候选 record 中，h5/h3 MPI2 顶层 `status=pass` 表示 full solve 与数值 Gate 通过，但 h3 的 `memory_reduction_20pct_gate=failed` 阻止 profile 提升。

## Iterative 数值字段

| 字段 | 含义 |
|---|---|
| `n_fe`, `n_aux` | 凝聚前 FE 与 auxiliary DoF |
| `coarse_dimension/rank/condition` | coarse 尺寸与可逆性 |
| `coarse_action_relative_error` | cached coarse 真作用认证；fresh coarse 为 `null` |
| `iterations`, `ksp_reason` | outer Krylov 结果 |
| `reported_relative_residual` | PETSc 报告残差 |
| `condensed_true_residual` | 对 exact A_c 显式计算 |
| `full_augmented_true_residual` | back-sub 后对完整块系统计算 |
| `slab_diagnostics` | owners、factor rows/nnz、sm2 与 apply 统计 |
| `peak_total_rss_including_rta_gb` | 包含 official 后处理的 all-rank 峰值 |
| `history` | 定期 reported/true residual、时间、RSS |

fresh coarse 直接由当前真实 action 构造，不存在独立 cache mismatch test，因此 `coarse_action_relative_error=null`；把它写成 `0.0` 会误导为测得机器零误差。

## 功率字段

| 字段 | 口径 | 身份 |
|---|---|---|
| `R_total` | top DtN outgoing modal power / incident | official |
| `T_total` | bottom DtN outgoing modal power / incident | official |
| `A_volume_total` | lossy volume integral / incident | official |
| `R_plus_T_plus_A_volume` | 三者之和 | consistency |
| `energy_closure_error` | port 与 volume 闭合误差 | Gate |
| probe Fourier / net flux | sampled plane diagnostic | diagnostic_only |

`official_rta` 只有 full augmented residual 低于阈值时才允许存在。

## 自动 Gate report

`python -m benchmarks.check_benchmarks --write` 写：

| 文件 | 内容 |
|---|---|
| `benchmarks/benchmark_summary.csv` | 从 manifest/records 重新汇总 |
| `benchmarks/records/benchmark_gate_report.json` | 每个 Gate 的 observed、expected、evidence 和总状态 |

不带 `--write` 的默认命令只读取、验证和打印，不修改这两份 tracked 文件；兼容入口
`--no-write` 具有相同只读行为。checker 非零退出表示至少一个 canonical Gate 失败，不能只
根据旧 CSV 宣称通过。
