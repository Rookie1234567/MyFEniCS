# Cross-fitted per-target uncertainty calibration

校准只使用 training OOF。对每个 outer fold，factor 由其余四个 fold 的 standardized residual 的 95th percentile 决定，再应用于当前 fold；最终报告不复用单一最大 scalar。

| target | raw 95% coverage | cross-fitted 95% coverage | final factor |
|---|---:|---:|---:|
| R_total | 0.8750 | 0.9271 | 2.54033 |
| T_total | 0.9271 | 0.9583 | 1.11469 |
| A_balance | 0.9375 | 0.9479 | 1.05497 |

region-wise coverage 和每折 factor 保存在 `training_cv.json` 的 `selected_result.uncertainty`。Aggregate GP 的 delta-method std 只作为近似 latent uncertainty；fixed-order power 的 fraction std 明确标为 `heuristic_training_residual_scale/not_calibrated_physical_uncertainty`，没有零方差伪装。由于 aggregate 与 power Gate 失败，以上校准不能用于生产 API。
