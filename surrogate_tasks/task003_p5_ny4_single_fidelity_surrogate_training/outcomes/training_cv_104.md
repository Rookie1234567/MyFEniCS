# Task003 104+16 training-only CV

The new compact dataset is `task003_m3s_round1_p5_ny4_104_v1` with 104
training rows and the unchanged sealed 16-row validation split. The 104-row
CV uses the same feature-B contract, deterministic folds, G1/G2 finite model
closure, P1 diagnostic and P2 physical power reconstruction. It contains
4,680 OOF records and reports target/region uncertainty calibration.

Selected training candidate: `G2_degree2_trend_residual_gp:features=B:jitter=1e-10`.

| target | NRMSE | p95 absolute | p95 relative |
|---|---:|---:|---:|
| R_total | 0.0296161 | 0.0468790 | 0.309233 |
| T_total | 0.0121282 | 0.0162212 | 0.0719471 |
| A_balance | 0.0366639 | 0.0459915 | 0.1039108 |

The aggregate hard Gate remains failed. P2 side ledgers are exact to numerical
roundoff (`<=1.11e-16`), but this physical reconstruction does not turn the
aggregate or per-channel accuracy into a qualified surrogate. Per the task,
the run stops here for Review V2; frozen-validation targets were not read.
