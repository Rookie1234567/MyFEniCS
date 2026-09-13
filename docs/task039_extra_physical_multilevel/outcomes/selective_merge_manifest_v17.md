# Task39extra V17 选择性合并边界：p4 BLR V16

本清单只说明依赖组和审查边界，不构成 merge approval。正式 source `24bd767e6b0d158ac20deb360a135f10c0611ede` 的 S2 证据证明一个 p4 BLR control 配置可运行且三 RHS 质量通过，但 `R_peak=R_live=0.9700174654134085`，S3/S4 未准入，不能把该研究路径提升为 ordinary production default。

| 依赖组 | 文件/内容 | 数值行为 | 证据与测试 | 当前边界 / 建议顺序 |
|---|---|---|---|---|
| production numerical/core | BLR controls、p4 augmented solve、`src/solvers/fullspace_v17_p3_oracle.py` 与相关 solver wiring | 有数值行为变化；仅是 explicit-opt-in research profile | S0 128 related tests、S2 raw control/independent checker；无完整 p6 original/notch | **do-not-merge production**；若未来继续，先新 review 明确完整 p6 Gate 与 architecture，再单独 selective review |
| reusable runner/watchdog | V16 input/schema/dispatch、S2 resource and ledger integration | 运行编排和 provenance 有变化；ordinary defaults unchanged | validate/dry-run、launcher/dispatch tests、clean source/resource evidence | 可作为 research-only infrastructure 候选；必须在 core 依赖批准后合并，不能单独宣称 BLR solver 资格 |
| checker/benchmark | `benchmarks/check_p4_blr_v16.py` 与独立 raw-vector/resource checker contract | checker 不改变求解器；从原始字段重算结论 | `s2_independent_check.json`：comparison/control/resource gates 全过，但 decision 为 memory-insufficient | 可后置合并；不得把 checker PASS 改写为 p6 PASS |
| compact evidence/docs | `response_v17.md`、`outcomes/p4_blr_v16.md`、两个 V16 compact/decision、`run_index`、`summary`、`test_summary`、`development_progress`、`development_model_registry` | 不改变数值行为；记录 measured/derived/not_run 边界 | source/input/physical/mode/run/resource/artifact identities | 在最终 review approval 后可优先选择性合并；保持旧负结果与 ledger 不变 |
| research-only | `physical_p4_blr_bal_h_v16` 的 S2 raw summaries、RHS packets、factor/timeline artifacts | 固定配置的研究证据；不代表全局 PC/连续收敛 | S2 packets、MUMPS 5.6.2 identity、Q1 baseline live scope、phase audit | raw heavy artifacts 继续 ignored；只合并轻量 hash-bound索引 |
| do-not-merge | “BLR 已成为完整 p6 PC”、S3/S4未运行项、5 nm/0.7 nm 外推、allocated-only memory claim、任何 default flag change、heavy matrix/factor/field/timeline | 会错误扩大适用范围或污染生产默认 | 与 decision/response 的 explicit not_run/negative boundary 冲突 | 永久保持不合并，除非新任务取得独立完整证据并重审 |

## 推荐顺序

1. 先合并 compact evidence/docs（若最终 review 明确批准），保留 `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN` 和 `not_run` 状态。
2. 只有在新的 solver/production review 通过后，才评估 runner/checker 的最小可复用部分。
3. 不合并 BLR numerical/core 到 ordinary default；不整体合并 task branch，不合并 ignored artifacts。

对应证据：[response V17](../response_v17.md)、[p4 BLR outcome](p4_blr_v16.md)、[decision](records/p4_blr_v16_decision.json)、[independent checker](../../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/s2_independent_check.json)。
