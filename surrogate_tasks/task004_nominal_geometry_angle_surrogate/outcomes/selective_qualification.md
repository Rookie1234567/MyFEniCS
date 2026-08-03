# Required M4H selective qualification

## Frozen identity

| identity | value |
|---|---|
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| immutable dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| training rows | 112 |
| fixed geometry | `h=120 nm, w=17 nm` |
| model / route | `S_PROD_FULL3D_STATIC_P5_H10_NY4` / `full3d_static_uniform_n1curl_p5_h10_ny4` |
| M4H clean implementation SHA | `9325d90479a7d0c9448ca302ee4b438632950d2d` |
| model lock | not created |
| new FEM / blind FEM | 0 / 0 |

The implementation SHA is the clean commit containing the M4H contract,
cross-fit implementation, Case129 checker and pure tests. The later evidence
commit only adds hash-bound records and documents; it does not change the
selector implementation.

## Risk contract

Only three point predictors were compared: local RBF k24, local Matérn k24 and
the existing latent median. S1 uses the pre-frozen M4E2 weights
`0.35/0.25/0.20/0.10/0.10` for calibrated Matérn standard deviation,
Matérn-k24/k32 disagreement, RBF/Matérn disagreement, nearest distance and
cutoff/topology risk. S2 is the maximum of targetwise standard deviation and
the two model disagreements. Quantile normalization and each outer-fold
threshold use only the other four outer folds; the held-out response is not
used to decide its own acceptance.

The exact contracts are in `SELECTIVE_RISK_SIGNAL_CONTRACT.json` and
`SELECTIVE_RISK_CROSSFIT.json`. `SELECTIVE_OOF.json` records every row's risk
components, source-fold hash, threshold, accepted/rejected state and
truth/prediction for audit.

## Training-only Gate result

| pair | accepted OOF | candidate pool | blind-design angles | failing Gate(s) |
|---|---:|---:|---:|---|
| RBF / S1 | 81/112 (0.7232) | 3937/4096 (0.9612) | 22/24 | accepted accuracy; coverage |
| Matérn / S1 | 81/112 (0.7232) | 3937/4096 (0.9612) | 22/24 | coverage |
| latent median / S1 | 81/112 (0.7232) | 3937/4096 (0.9612) | 22/24 | coverage |
| RBF / S2 | 112/112 | 4096/4096 | 24/24 | accepted accuracy; supported-window |
| Matérn / S2 | 112/112 | 4096/4096 | 24/24 | accepted accuracy; supported-window; coverage |
| latent median / S2 | 112/112 | 4096/4096 | 24/24 | accepted accuracy; supported-window; coverage |

The best accepted-set point metrics were from S1 Matérn/latent median, but
their empirical 95% coverage is 1.0 for R/T/A, outside the frozen
`[0.90, 0.99]` interval. This is a Gate failure, not a reason to loosen the
interval. S2 does not reject the known high-error tail and therefore fails the
accuracy contract.

## Separate domains and stopping decision

`ANGLE_AGGREGATE_STRUCTURAL_SUPPORT_DOMAIN.json` reports a response-blind
structural domain: 4074/4096 candidate angles and 24/24 blind-design angles
meet its explicit topology, leave-one-out distance and local-geometry checks.
This is not a prediction-safe domain. The separate
`ANGLE_AGGREGATE_SELECTIVE_ACCEPTANCE_DOMAIN.json` records the six risk-based
acceptance sets and their tuple/index hashes; it does not read responses.

No predictor/rule pair passes all selective Gates. The qualification contract
is therefore `controlled_negative`, no model lock is created, and blind FEM is
not authorized. Rejected angles remain `requires_fem`; Order Level B remains
unqualified. The next valid action is to await Review V7, not to retune the
threshold or run another FEM campaign.

