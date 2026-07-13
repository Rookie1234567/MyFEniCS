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

`python -m benchmarks.check_benchmarks` 写：

| 文件 | 内容 |
|---|---|
| `benchmarks/benchmark_summary.csv` | 从 manifest/records 重新汇总 |
| `benchmarks/records/benchmark_gate_report.json` | 每个 Gate 的 observed、expected、evidence 和总状态 |

checker 非零退出表示至少一个 canonical Gate 失败，不能只根据旧 CSV 宣称通过。
