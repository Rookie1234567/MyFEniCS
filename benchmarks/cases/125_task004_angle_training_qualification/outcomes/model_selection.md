# Task004 model selection（controlled stop）

Local RBF 与 Chebyshev degree 2–5 仅作为 deterministic baselines；它们没有可信 predictive std，不参与 production lock。Production 候选严格限定为 Matérn-5/2 ARD exact GP：F1/F2/F3 × jitter `{1e-10,1e-8,1e-6}`，每个 latent、每个 fold 使用 8 个确定性初值。

没有任何 production candidate 同时通过 aggregate、spatial、uncertainty 和 power Gate，因此 `ANGLE_MODEL_SELECTION_LOCK.json` 不存在。候选排序中的代表为 `gp:F3/1e-6`，但其 Gate 为 false；这不是一个可公开加载的模型。

主动学习资格也未满足：GP 代表的综合 score 4.9507 没有优于最佳 local-RBF baseline 的 4.4861，且 aggregate/power 失败并非可由已确认的单一 coverage-hole 解释。故按 Review V2 受控停止，不能擅自启动 16 点 FEM。
