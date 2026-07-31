# Training-only CV: 112 Ny4 p5 samples

Dataset: `task003_m3t_round2_p5_ny4_112_v1` (112 training rows plus the
unchanged 16-row frozen-validation identity). Feature contract B was used;
the validation targets were not accessed.

| target | NRMSE | p95 absolute | p95 relative |
|---|---:|---:|---:|
| R_total | 0.0340471 | 0.0391579 | 0.183940 |
| T_total | 0.0205960 | 0.0235539 | 0.147012 |
| A_balance | 0.0447340 | 0.0441211 | 0.0838327 |

The training-only hard Gate remains failed. CV selected
`G1_constant_gp:features=B:jitter=1e-08`; no model-selection lock was
created. P2 side-total/masked-fraction power diagnostics and OOF records are
stored in `training_cv_112.json` and `training_cv_112_oof.json`.
