# Paired train96 → train112 learning curve

This is a diagnostic paired reference on fixed train96 test rows; it is not a
final model-selection result or an `ANGLE_AGGREGATE_MODEL_SELECTION_LOCK`.

The test rows are the same five-fold train96 test rows; each train112 fit adds all 16 new FEM points.

| candidate | train96 max abs | train112 max abs | max-error reduction | mean-abs reduction |
|---|---:|---:|---:|---:|
| L1_local_rbf_k24_s1e-08 | 0.13349651 | 0.1136339 | 0.019862606 | 0.00033505972 |
| L2_local_matern_k24 | 0.14438023 | 0.093264296 | 0.051115932 | 0.00014561077 |
| L2_local_matern_k32 | 0.14412282 | 0.14386597 | 0.00025685274 | -0.00054924001 |
