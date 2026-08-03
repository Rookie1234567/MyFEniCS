# End-to-end power OOF

每个 fold 的 power OOF 使用同一折的 selected aggregate candidate/feature/jitter 的 R/T 预测和 std，再拟合 masked active-channel log-ratio fraction；没有用 test-fold truth 重新构造 side total。analytic top/bottom mask 单独由 runtime authority 计算，mask topology 未见时返回 unsupported 而不是最近邻 fraction。

选定代表 `gp:F3/1e-6` 的结果：

- mask agreement：100%；
- maximum reflection/transmission side ledger error：`2.22e-16`；
- primary channels 的固定阈值 Gate 未通过（例如 reflection m=0,S NRMSE=0.2070，reflection m=0,S p95=0.001742；reflection m=-1,S NRMSE=0.2056；transmission m=-1,S p95=0.01438）；
- 因此 power hard Gate=false。

逐 channel prediction/std/error、fraction-model identity、fold、mask signature、cutoff order/signed margin 和 `truth_leakage=false` 均在 `training_cv.json` 的 `power_oof_records` 中；inactive channels 保持 mask=false/NaN 语义。
