# 结果字段说明

## 普通 Results

普通运行继续在 `results/<case>_<timestamp>/` 保存完整场、网格说明、日志和后处理文件。该目录不提交 Git，可由用户自行检查或清理。正式 benchmark 的重型输出独立写入同样不提交 Git 的 `benchmarks/artifacts/`。

普通 3D `run_summary.json` 同时保留 `max_rss_mb`（单个 rank 的最大峰值）和 `total_peak_rss_mb/gb`（所有 ranks 的峰值总和）。容量规划应优先使用后者。

## Benchmark Record

`benchmarks/records/*.json` 是轻量可提交摘要。核心字段如下：

| 字段 | 含义 |
|---|---|
| `case` | 唯一案例标签 |
| `profile` | 求解器 profile 名称 |
| `ordinary_default_changed` | 普通默认是否被修改；Task28 必须为 false |
| `h_nm`, `mpi_size` | 网格目标尺寸与 MPI rank 数 |
| `n_fe`, `n_aux` | 凝聚前 FE 与辅助自由度 |
| `coarse_dimension/rank/condition` | coarse 可逆性认证 |
| `coarse_action_relative_error` | 缓存 coarse 与真实算子作用误差 |
| `iterations`, `ksp_reason` | Krylov 迭代与 PETSc 状态 |
| `reported_relative_residual` | PETSc 报告口径 |
| `condensed_true_residual` | 对 exact condensed A 的显式残差 |
| `full_augmented_true_residual` | 辅助回代后完整块系统残差 |
| `final_peak_total_gb` | 所有 MPI ranks 的总峰值 RSS |
| `slab_diagnostics` | owner、每 rank 行数、factor nnz 与 apply 统计 |
| `official_rta` | residual gate 后的 R/T/A 与能量闭合 |
| `history` | 定期显式真残差与内存历史 |

## 功率字段

| 字段 | 口径 |
|---|---|
| `R_total` | top DtN outgoing modal power / incident power |
| `T_total` | bottom DtN outgoing modal power / incident power |
| `A_volume_total` | 有损材料体积分吸收 / incident power |
| `R_plus_T_plus_A_volume` | 能量总和 |
| `energy_closure_error` | port 与 volume absorption 闭合误差 |

probe-plane Fourier 与 sampled net flux 只作 diagnostic，不替代 official modal R/T。
