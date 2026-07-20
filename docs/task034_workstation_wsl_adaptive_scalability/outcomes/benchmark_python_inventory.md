# Benchmark Python inventory（Review V2）

## 审计范围与结论

本 inventory 覆盖 Task034 分支相对 `origin/master` 的全部 31 个 `benchmarks/*.py` 变更，
逐文件机器可读分类见 `benchmark_python_inventory.csv`。分类采用：

- `generic_pde_runner`：通用 PDE 入口；
- `watchdog_telemetry`：资源 Gate、外部监控和诊断；
- `checker_aggregator`：只读校验、聚合和 provenance；
- `one_off_research`：任务限定的离线研究/解释；
- `historical_entrypoint`：Task030–Task033 兼容入口；
- numerical functionality：正式归属 `src/`，不在 benchmark 中另建生产实现。

审计结果：Task034 新增 Python 没有复制一套 Maxwell/Floquet/QEP/Hybrid solver。需要 PDE 的入口
调用 `src/` 现有构件；其余新增文件只做 watchdog、环境检查或离线聚合。`task033_case090_pde_core.py`
是保留的历史 benchmark PDE core，不被提升为生产 API；本轮 Review V2 没有修改数值核心。

## Task034 新增文件的调用与边界

| 文件 | 直接调用/消费 | 重复 orchestration | selective merge 边界 |
|---|---|---|---|
| `run_task034_adaptive_mechanism.py` | `src.geometry.task034_adaptive_mesh`、Floquet/space helpers | task-specific mechanism case | runner 为 research-only；`src` mechanism 单独审查 |
| `run_task034_cache_lifecycle_probe.py` | high-order Floquet cache、mesh builder | cache lifecycle diagnostic | 仅随 cache-hardening tests 合并 |
| `run_task034_wsl_qualification.py` | OS/package/MPI probes | 无 PDE | environment qualification group |
| `task034_adaptive_compression.py` | adaptive/Hybrid 已有记录 | 离线同误差比较 | research evidence，不是 production API |
| `task034_case093.py` | Full3D/Hybrid descriptors | 固定几何与 closure 聚合 | Case093 evidence group |
| `task034_mpi_identity.py` | MPI descriptors | identity 比较 | Case093 evidence group |
| `task034_numerical_blob_checker.py` | Git blobs、provenance | 无 PDE | provenance hardening group |
| `task034_p3_h3_reranking.py` | p3/h3 与候选 descriptors | 离线 reranking | research-only |
| `task034_resource_model_v2.py` | p2/p3/p4 Hybrid inventories | 离线 mechanical scaling | Review evidence；绝不授权 PDE |
| `task034_workstation_resource_gates.py` | cgroup/process-tree/limit | 与 watchdog 共享 Gate | 先于 guarded runners 合并 |
| `task034_wsl_resources.py` | WSL memory/swap | 与 watchdog 共享 telemetry | 先于 guarded runners 合并 |
| `task034_review_v2_aggregation.py` | Case092/093 与 watchdog descriptors | 统一事实表 | Review V2 evidence aggregator |

`run_task032_phase6_augmented.py`、Task033 watchdog/funnel 等历史入口仍有较大 orchestration，
但其通用数值修订均落在 `src/`；selective merge manifest 将这些兼容入口与生产核心分组，
避免把整套 task runner 当成正式 solver API。
