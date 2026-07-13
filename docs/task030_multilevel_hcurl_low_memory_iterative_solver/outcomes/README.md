# Task030 outcomes

本目录保存 Task030 的轻量、可审查证据。重型网格、矩阵、逐 rank transfer cache、完整迭代历史和场输出保留在 `benchmarks/artifacts/cases/060/`，不进入 Git。

当前结论：`workstation_success`（显式 experimental opt-in）。h5/h3/h2 均通过真残差、80 modes、official R/T/A 和内存 Gate；h2 在 1873 步达到 full true residual `9.972228e-7`，含 R/T/A 峰值 9.374729 GB，较 Task27 降低 28.33%。它没有达到 `<=1200` 步工程偏好，普通默认未改变。

轻量入口：

- `summary.md`：完整技术回顾与最终分类；
- `candidate_funnel.csv`：正负候选漏斗；
- `candidate_comparison.csv`：正式 full solve 对比；
- `hierarchy_design.md` / `transfer_validation.md`：H(curl) 层级基础设施；
- `h2_memory_prediction.md` / `h2_launch_decision.md`：h2 解锁和实测；
- `negative_results.md`：不得提升的失败机制；
- `benchmarks/cases/060_multilevel_hcurl_iterative_solver/records/`：可提交的结构化摘要。
