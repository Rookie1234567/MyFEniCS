# Selective merge manifest V28：fused A6 候选未获 fresh PDE qualification

本 manifest 记录 Review V26 的依赖组与结果边界；当前没有 master merge approval，ordinary default 保持不变。

| 依赖组 | 文件 | 数值行为/依赖 | 测试与 fresh PDE | 建议 |
|---|---|---|---|---|
| production numerical/core | `src/solvers/physical_equivalent_fast.py` | 不改离散或算子值；fused inventory 只从一个共享 MPC owner 计 retained payload，split 仍计两个 owner；fused workspace budget 使用已有 curl+mass 预算 | small-mesh fused/split factory 路径验证；15 focused tests pass；修复后 fresh PDE `not_run` | 可 review source fix；不要据此提升普通默认，必须把缺失 PDE 证据标在合入决策中 |
| reusable runner/watchdog | `src/runners/physical_p4_schur_v14.py` | workspace consumer 读取 factory 的 `kernel_temporary_bytes`；fused 与 split 的预算来源统一；会改变 workspace accounting，不更改公式或求解步骤 | `test_physical_schur_v14_budget.py` 覆盖；无修复后 PDE | 与 core 同组审查，确认 owner facts 和预算字段契约 |
| checker/benchmark | V28 raw results 与 `outcomes/records/fused_operator_speed_v28_*.json` | 记录工程组件表现、启动成本、真实 worker bug 和 `not_run`，不复算/伪造 solver residual | 原始 run summary、worker summary、events 与 watchdog hashes 已绑定；没有正式终态数值 checker | 轻量 evidence 可单独保留；大体积 raw artifacts 留 ignored results |
| compact evidence/docs | `response_v29.md`、`outcomes/fused_operator_speed_v28.md`、`summary.md`、`test_summary.md`、`run_index.json`、development registry/progress | 显式区分组件资格与正式采用；完整求解收益 unknown；R2 baseline 保持 | 文档合同21项与JSON parse pass；不含 fresh PDE | 证据文档先 review，不把 partial failure 描述为性能通过 |
| research-only | 保存向量 A6/H6 component pairs、selected fused profile、thread capability snapshot | 仅支持后续受控候选；A6 fusion-only 未经 fresh full case，shared contraction 不采用，线程未试 | component evidence/hash 在既有记录；fresh PDE `false` | 保留研究证据，不迁移为 production default |
| do-not-merge/default promotion | 将 V28 提升为 fastest profile/default；将 partial RSS/PSS 当作全流程节省；任何无新授权的完整重跑 | 无法从 pre-KSP failure 证明 residual、field、R/T/A、full/KSP timing、生命周期峰值 | 正式回归 `INCOMPLETE_WORKER_FAILED_BEFORE_KSP`；一次 bug replay 已消耗 | 不合并为默认、不宣称提速；下一场需新的明确用户授权 |

实现提交：`f403cf126817a9019d2be59df6b2be6fc0d6bffd`。本 manifest 不是 master merge approval；任何最终合入仍等待主控审阅及用户授权。
