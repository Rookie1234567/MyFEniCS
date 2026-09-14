# Task39extra V18 选择性合并边界：p4 BLR T1 收口

本清单只描述依赖组和审查边界，不构成 merge approval。T1 在 `tau=1e-3` 下的 p4 BLR control 同时未通过质量 Gate 与 RSS memory Gate；T2/T3/T4 未运行。ordinary solver default 保持不变，旧 V17 manifest 保留为历史。

| 依赖组 | 文件/内容 | 数值行为是否改变 | 证据、测试与依赖 | 当前边界 / 建议顺序 |
|---|---|---|---|---|
| production numerical/core | `src/solvers/fullspace_v17_p3_oracle.py` 及 BLR numerical wiring、`physical_p4_blr_tradeoff_v17` profile | 会改变显式 opt-in 数值行为；本轮没有资格化完整 p6 | formal T1 source `a1bc6b54e613ebf91c5c97ecddcc14555b084ee0`；T1 `quality_pass=false`、`memory_pass=false`；无 T2/T3/T4、无 p6 outer residual | **do-not-merge production**。必须有新 review、完整 p6/original/notch 和 fresh resource evidence 后再审，不能提升 ordinary default。 |
| reusable runner/watchdog | T1 input/schema/dispatch、watchdog、phase/resource provenance | 运行编排和证据字段有变化；不改变 ordinary default | `t1_launch_preflight`、`t1_validate`、`final_evidence_tests_v17.log`；资源 raw evidence、zero swap、cleanup 保留 | 可作为 research-only infrastructure 候选；先于 numerical/core 单独审查，不能用 runner 测试宣称 solver 通过。 |
| checker/benchmark | `benchmarks/check_p4_blr_tradeoff_v17.py`、`t1_checker_final_v2.json` | checker-only；不改变求解器 | final checker v2 SHA `63327177a9b9cacf6b5f40dfb28df9b8071b207a8079011c37516de2b8616b4f`；维度匹配与内容 hash 缺失分开；strict slave-zero 仍 exact false；137 related tests | **可后置候选合并**，但必须保留 `matrix_content_hash_available=false`、`all_rhs_evidence=false` 和 Q/M false；旧 checker/initial snapshot 不删除。 |
| compact evidence/docs | `response_v18.md`、`outcomes/p4_blr_tradeoff_v17.md`、V17 compact/decision、`run_index.json`、`summary.md`、`test_summary.md`、development progress/registry、V18 manifest | 不改变数值行为；记录 measured/derived/not_run/failed 边界 | T1 root audit、phase-times、final checker v2、run manifest/resource/event hashes；137 passed、compileall/diff | 在最终 review approval 和用户授权后可优先 selective merge；保留旧 ledger、旧 V16/V17 文档、旧 checker 快照。 |
| research-only raw evidence | T1 raw summary、RHS packets、factor statistics、resource/event streams、ignored artifacts | 只表示这个固定 p4 control 的研究结果 | `t1_root_audit.json`、`t1_phase_times.json`、`physical_p4_blr_v17_summary.json`、三 RHS packets、raw factor/resource logs | heavy matrix/factor/field/timeline 继续 ignored；Git 只保留轻量 hash-bound 索引。 |
| do-not-merge | “BLR 已成为完整 p6 PC”、T2/T3/T4 的未运行项、new epsilon sweep、5 nm/0.7 nm 外推、allocated-only memory claim、strict slave-zero 容差改判、矩阵维度冒充内容 identity、任何 default flag change | 会扩大适用范围或污染生产默认 | 与 T1 decision、response 和 compact 的明确负结果/缺口冲突 | 永久不合并，除非新任务取得独立完整证据并重新审查。 |

## 四路结果身份

| 路线 | 身份 | 状态 |
|---|---|---|
| 原 p4 LU | accepted Q1 source `6a8b273c383d5bd9da37d6630a48bd24d6a90cce` | accepted reference；不因 T1 metadata 缺口重建 |
| 旧 BLR `tau=1e-5` | V16 historical evidence | `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN`；保留，不重跑 |
| T1 BLR `tau=1e-3` | source `a1bc6b54e613ebf91c5c97ecddcc14555b084ee0` | `T1_BLR_CONTROL_REJECTED`；Q=false、M=false |
| T2 BLR `tau=1e-4` | conditional route | `not_run`；不因 T1 失败插入新阈值 |

## 建议顺序

1. 先 selective merge compact evidence/docs（须最终 review approval），不合并 numerical/core，不改变 default。
2. 若未来有新任务，先对 checker/runner 的最小可复用部分做独立 review，再考虑新的数值 profile。
3. 不整体 merge task branch，不合并 ignored heavy artifacts，不把 p4 T1 证据写成完整 p6 资格。

对应证据：[response V18](../response_v18.md)、[p4 BLR tradeoff outcome](p4_blr_tradeoff_v17.md)、[compact](records/p4_blr_tradeoff_v17_compact.json)、[decision](records/p4_blr_tradeoff_v17_decision.json)、[final checker v2](../../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_final_v2.json)。

