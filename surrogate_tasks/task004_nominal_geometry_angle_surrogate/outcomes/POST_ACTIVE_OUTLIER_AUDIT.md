# POST_ACTIVE_OUTLIER_AUDIT

Reference candidate: `L1_local_rbf_k24_s1e-08`.  The audit is training-only and lists the ten highest absolute-error points per target.

| target | rank | index | identity | angle | abs error | classification | distance | disagreement |
|---|---:|---:|---|---|---:|---|---:|---:|
| R_total | 1 | 96 | new16 | [0.90729793068, 82.131933812052] | 0.045250501 | cutoff_high_curvature | 0.0399416 | 0.0431579 |
| R_total | 2 | 39 | old96 | [2.0, 90.0] | 0.036529698 | cutoff_high_curvature | 0.210526 | 0.036221 |
| R_total | 3 | 80 | old96 | [1.536085498054, 67.84780732356] | 0.032799065 | cutoff_high_curvature | 0.186547 | 0.0678287 |
| R_total | 4 | 85 | old96 | [2.980484131724, 37.644248139113] | 0.030151679 | cutoff_high_curvature | 0.250964 | 0.0295823 |
| R_total | 5 | 9 | old96 | [0.5, 90.0] | 0.029845786 | cutoff_high_curvature | 0.0526316 | 0.0285346 |
| R_total | 6 | 38 | old96 | [2.0, 75.0] | 0.029826889 | cutoff_high_curvature | 0.186547 | 0.0433189 |
| R_total | 7 | 84 | old96 | [3.012447152752, 52.573178429157] | 0.029822517 | cutoff_high_curvature | 0.265449 | 0.0319382 |
| R_total | 8 | 89 | old96 | [3.025618610438, 67.084721289575] | 0.024382718 | cutoff_high_curvature | 0.258585 | 0.0206028 |
| R_total | 9 | 105 | new16 | [1.096476651262, 82.267959779128] | 0.024367988 | cutoff_high_curvature | 0.0399416 | 0.142986 |
| R_total | 10 | 37 | old96 | [2.0, 60.0] | 0.022987465 | cutoff_high_curvature | 0.199881 | 0.0233025 |
| T_total | 1 | 92 | old96 | [2.961689197458, 82.168203396723] | 0.10692683 | cutoff_high_curvature | 0.241358 | 0.0753494 |
| T_total | 2 | 48 | old96 | [4.0, 75.0] | 0.069897329 | cutoff_high_curvature | 0.172234 | 0.0694686 |
| T_total | 3 | 111 | new16 | [6.854549495038, 83.504671286792] | 0.033382942 | coverage_hole | 0.230651 | 0.00712038 |
| T_total | 4 | 58 | old96 | [6.0, 75.0] | 0.0318995 | cutoff_high_curvature | 0.230775 | 0.0499595 |
| T_total | 5 | 38 | old96 | [2.0, 75.0] | 0.028071673 | cutoff_high_curvature | 0.186547 | 0.0291924 |
| T_total | 6 | 49 | old96 | [4.0, 90.0] | 0.026245832 | cutoff_high_curvature | 0.164123 | 0.0541417 |
| T_total | 7 | 59 | old96 | [6.0, 90.0] | 0.024522716 | cutoff_high_curvature | 0.212009 | 0.0288143 |
| T_total | 8 | 109 | new16 | [4.106844223104, 82.684139208868] | 0.020904418 | cutoff_high_curvature | 0.132082 | 0.0173316 |
| T_total | 9 | 110 | new16 | [5.308891468216, 83.060868540779] | 0.017844575 | cutoff_high_curvature | 0.121128 | 0.068879 |
| T_total | 10 | 47 | old96 | [4.0, 60.0] | 0.01485821 | cutoff_high_curvature | 0.258585 | 0.0148814 |
| A_balance | 1 | 92 | old96 | [2.961689197458, 82.168203396723] | 0.1129329 | cutoff_high_curvature | 0.241358 | 0.0754516 |
| A_balance | 2 | 48 | old96 | [4.0, 75.0] | 0.065268708 | cutoff_high_curvature | 0.172234 | 0.0640546 |
| A_balance | 3 | 38 | old96 | [2.0, 75.0] | 0.057898563 | cutoff_high_curvature | 0.186547 | 0.0565649 |
| A_balance | 4 | 96 | new16 | [0.90729793068, 82.131933812052] | 0.045644652 | cutoff_high_curvature | 0.0399416 | 0.0357339 |
| A_balance | 5 | 111 | new16 | [6.854549495038, 83.504671286792] | 0.041633976 | coverage_hole | 0.230651 | 0.00619156 |
| A_balance | 6 | 49 | old96 | [4.0, 90.0] | 0.039127384 | cutoff_high_curvature | 0.164123 | 0.0515259 |
| A_balance | 7 | 58 | old96 | [6.0, 75.0] | 0.037972994 | cutoff_high_curvature | 0.230775 | 0.0557973 |
| A_balance | 8 | 80 | old96 | [1.536085498054, 67.84780732356] | 0.034940569 | cutoff_high_curvature | 0.186547 | 0.0212685 |
| A_balance | 9 | 105 | new16 | [1.096476651262, 82.267959779128] | 0.034595201 | cutoff_high_curvature | 0.0399416 | 0.138105 |
| A_balance | 10 | 39 | old96 | [2.0, 90.0] | 0.033840065 | cutoff_high_curvature | 0.210526 | 0.034835 |

The JSON contains every candidate prediction/std/error, nearest training tuples, cutoff/mask/region identity, and the immutable Round1 acquisition metadata when a point was selected.
