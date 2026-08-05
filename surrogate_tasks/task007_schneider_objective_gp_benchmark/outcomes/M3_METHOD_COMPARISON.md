# Task007 M3 Level-A continuous BO comparison

本报告只调用冻结 Task006 Legendre-3 surrogate oracle；没有运行 FEM。主指标是 best actually evaluated point 与 queries-to-MAP。

实现身份：`555abf1`。该 SHA 绑定连续 oracle、Matérn-5/2 ARD GP、连续 EI、oracle query/update、低 EI bounded local refinement 和 Case147 checker。

| contract | noise | method | targets | MAP hits | median queries-to-MAP | p90 | gate |
|---|---|---|---:|---:|---:|---:|---|
| J0 | N1 | P0_cold5 | 12 | 8 | 8.0 | 12.3 | negative |
| J0 | N1 | P1_sobol12 | 12 | 12 | 5.0 | 7.0 | PASS |
| J0 | N1 | P2_sobol37 | 12 | 11 | 3.0 | 5.0 | negative |
| J0 | N1 | P3_train37 | 12 | 8 | 4.0 | 9.799999999999999 | negative |
| J0 | N2 | P0_cold5 | 12 | 10 | 10.0 | 13.299999999999999 | negative |
| J0 | N2 | P1_sobol12 | 12 | 11 | 2.0 | 7.0 | negative |
| J0 | N2 | P2_sobol37 | 12 | 12 | 2.0 | 4.9 | PASS |
| J0 | N2 | P3_train37 | 12 | 9 | 1.0 | 7.800000000000001 | negative |
| J1 | N1 | P0_cold5 | 12 | 8 | 8.5 | 10.3 | negative |
| J1 | N1 | P1_sobol12 | 12 | 12 | 5.5 | 7.9 | PASS |
| J1 | N1 | P2_sobol37 | 12 | 12 | 3.0 | 4.800000000000001 | PASS |
| J1 | N1 | P3_train37 | 12 | 9 | 7.0 | 11.2 | negative |
| J1 | N2 | P0_cold5 | 12 | 11 | 10.0 | 12.0 | negative |
| J1 | N2 | P1_sobol12 | 12 | 12 | 5.0 | 6.0 | PASS |
| J1 | N2 | P2_sobol37 | 12 | 12 | 2.0 | 3.0 | PASS |
| J1 | N2 | P3_train37 | 12 | 10 | 3.5 | 5.6999999999999975 | negative |

## Baselines

| contract | noise | method | oracle queries | MAP hit/query result |
|---|---|---|---:|---|
| J0 | N1 | B0_random | 2000.0 | 12/12 |
| J0 | N1 | B1_local | 871.5 | 12/12 |
| J0 | N2 | B0_random | 2000.0 | 12/12 |
| J0 | N2 | B1_local | 646.5 | 12/12 |
| J1 | N1 | B0_random | 2000.0 | 12/12 |
| J1 | N1 | B1_local | 847.5 | 12/12 |
| J1 | N2 | B0_random | 2000.0 | 11/12 |
| J1 | N2 | B1_local | 550.5 | 12/12 |

## GP audit

- sequential GP updates: `1361`
- selected-run warnings recorded: `2028`
- selected-run boundary collisions: `196`
- bounded local refinement switches: `473`
- one-shot posterior-mean P3 is retained only in Task007 V1 and is not used as this M3 primary gate.
