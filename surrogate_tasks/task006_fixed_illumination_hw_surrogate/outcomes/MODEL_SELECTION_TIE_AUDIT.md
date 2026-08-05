# Task006 model-selection tie audit

模型锁未修改；该审计只记录 blind 前已完成的 training-only 选择语义。

| candidate | training selection score |
|---|---:|
| `legendre_2` | 4.21900320264538 |
| `legendre_3` | 1 |
| `legendre_4` | 1.05714285714286 |
| `local_rbf_k8` | 263.70853449141 |
| `matern52_ard_exact_gp` | 1 |
| `degree2_trend_plus_matern52_residual` | 1 |

精确并列组：`legendre_3, matern52_ard_exact_gp, degree2_trend_plus_matern52_residual`，score=1.0。固定顺序中的首项 `legendre_3` 是历史 selected candidate；不得因盲点响应改变。
