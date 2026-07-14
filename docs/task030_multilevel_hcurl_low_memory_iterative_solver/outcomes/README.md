# Task030 outcomes

本目录保存 Task030 的轻量、可审查证据。重型网格、矩阵、逐 rank transfer cache、完整迭代历史和场输出保留在 `benchmarks/artifacts/cases/060/`，不进入 Git。

当前结论：`workstation_memory_success_with_qualifications`。最终成功方法是 Task27-derived physical-slab + 75D wave-coarse 架构上的 `compact physical-slab low-memory experimental profile`，不是成功的 p/h GMG。clean final-HEAD h5/h3 分别为 855/962 步、1.687653/3.792912 GB，三残差、80 modes、official R/T/A 与内存 Gate 全通过；h3 同时通过 3.8 GB 绝对线和较 Task27 降低 25.37% 的相对线。h2 不重跑，保留为 1873 步、9.374729 GB、full true residual `9.972228e-7` 的 reviewed historical dirty-worktree reference。它没有达到 `<=1200` 步工程偏好，普通默认未改变。

Review V2 已完成 clean h5/h3 final-HEAD rerun，h2 identity 明确为历史参考；validated transfer/cache/Galerkin API 已与失败的 p/h/Woodbury research candidates 隔离。Case060 保持 203 项数值 Gate 与 manifest/summary 再生成链。factor nnz 统计不能证明 ILU0 compression；factor-only 仅在 PETSc 3.24.0 complex build 验证，跨版本需回归。

轻量入口：

- `summary.md`：完整技术回顾与最终分类；
- `candidate_funnel.csv`：正负候选漏斗；
- `candidate_comparison.csv`：正式 full solve 对比；
- `hierarchy_design.md` / `transfer_validation.md`：H(curl) 层级基础设施；
- `h2_memory_prediction.md` / `h2_launch_decision.md`：h2 解锁和实测；
- `negative_results.md`：不得提升的失败机制；
- `benchmarks/cases/060_multilevel_hcurl_iterative_solver/records/`：可提交的结构化摘要。
