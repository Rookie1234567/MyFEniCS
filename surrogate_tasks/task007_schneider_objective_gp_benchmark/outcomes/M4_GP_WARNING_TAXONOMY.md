# M4A GP warning taxonomy

从不可变 M3 BO traces 重建每个 GP update，按 method、contract/noise、observed count、selected jitter、fitted kernel、length scales、constant amplitude、LML 和 warning category 分组。没有改变 kernel bounds。

- fit updates audited: `1361`
- warnings: `2028`
- boundary collisions: `196`
- categories: `{'hyperparameter_boundary_convergence': 200, 'other_convergence_warning': 1828}`

| method | contract | noise | observed n | fits | warnings | boundary collisions | jitter counts | categories |
|---|---|---|---:|---:|---:|---:|---|---|
| P0_cold5 | J0 | N1 | 5 | 12 | 1 | 1 | `{'1e-10': 9, '1e-08': 3}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N1 | 6 | 12 | 6 | 6 | `{'1e-10': 10, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 6}` |
| P0_cold5 | J0 | N1 | 7 | 12 | 9 | 9 | `{'1e-10': 12}` | `{'hyperparameter_boundary_convergence': 9}` |
| P0_cold5 | J0 | N1 | 8 | 12 | 2 | 2 | `{'1e-08': 2, '1e-10': 10}` | `{'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J0 | N1 | 9 | 12 | 1 | 1 | `{'1e-08': 2, '1e-10': 10}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N1 | 10 | 12 | 4 | 3 | `{'1e-08': 2, '1e-10': 10}` | `{'other_convergence_warning': 1, 'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N1 | 11 | 11 | 7 | 1 | `{'1e-10': 10, '1e-08': 1}` | `{'other_convergence_warning': 6, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N1 | 12 | 9 | 18 | 0 | `{'1e-10': 9}` | `{'other_convergence_warning': 18}` |
| P0_cold5 | J0 | N1 | 13 | 7 | 19 | 0 | `{'1e-10': 7}` | `{'other_convergence_warning': 19}` |
| P0_cold5 | J0 | N1 | 14 | 7 | 14 | 3 | `{'1e-10': 7}` | `{'other_convergence_warning': 11, 'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N1 | 15 | 7 | 17 | 2 | `{'1e-10': 6, '1e-08': 1}` | `{'other_convergence_warning': 15, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J0 | N1 | 16 | 7 | 23 | 3 | `{'1e-10': 6, '1e-08': 1}` | `{'other_convergence_warning': 20, 'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N1 | 17 | 5 | 24 | 3 | `{'1e-10': 5}` | `{'other_convergence_warning': 21, 'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N1 | 18 | 4 | 19 | 2 | `{'1e-10': 4}` | `{'other_convergence_warning': 17, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J0 | N1 | 19 | 4 | 17 | 1 | `{'1e-10': 4}` | `{'other_convergence_warning': 16, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N1 | 20 | 4 | 21 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 21}` |
| P0_cold5 | J0 | N1 | 21 | 4 | 18 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 18}` |
| P0_cold5 | J0 | N1 | 22 | 4 | 12 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 12}` |
| P0_cold5 | J0 | N1 | 23 | 4 | 21 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 21}` |
| P0_cold5 | J0 | N1 | 24 | 4 | 19 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 19}` |
| P0_cold5 | J0 | N2 | 5 | 12 | 3 | 3 | `{'1e-10': 7, '1e-08': 5}` | `{'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N2 | 6 | 12 | 1 | 1 | `{'1e-10': 12}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N2 | 7 | 12 | 3 | 3 | `{'1e-10': 11, '1e-08': 1}` | `{'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N2 | 8 | 11 | 1 | 1 | `{'1e-08': 2, '1e-10': 9}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N2 | 9 | 11 | 0 | 0 | `{'1e-10': 9, '1e-08': 2}` | `{}` |
| P0_cold5 | J0 | N2 | 10 | 11 | 0 | 0 | `{'1e-08': 2, '1e-10': 9}` | `{}` |
| P0_cold5 | J0 | N2 | 11 | 10 | 7 | 1 | `{'1e-08': 2, '1e-10': 8}` | `{'other_convergence_warning': 4, 'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N2 | 12 | 10 | 5 | 0 | `{'1e-08': 2, '1e-10': 8}` | `{'other_convergence_warning': 5}` |
| P0_cold5 | J0 | N2 | 13 | 9 | 5 | 0 | `{'1e-08': 2, '1e-10': 7}` | `{'other_convergence_warning': 5}` |
| P0_cold5 | J0 | N2 | 14 | 7 | 4 | 0 | `{'1e-08': 1, '1e-10': 6}` | `{'other_convergence_warning': 4}` |
| P0_cold5 | J0 | N2 | 15 | 7 | 4 | 0 | `{'1e-10': 7}` | `{'other_convergence_warning': 4}` |
| P0_cold5 | J0 | N2 | 16 | 5 | 12 | 2 | `{'1e-10': 4, '1e-08': 1}` | `{'other_convergence_warning': 10, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J0 | N2 | 17 | 4 | 16 | 0 | `{'1e-10': 3, '1e-08': 1}` | `{'other_convergence_warning': 16}` |
| P0_cold5 | J0 | N2 | 18 | 3 | 14 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 14}` |
| P0_cold5 | J0 | N2 | 19 | 3 | 19 | 3 | `{'1e-10': 3}` | `{'other_convergence_warning': 16, 'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J0 | N2 | 20 | 3 | 14 | 2 | `{'1e-10': 3}` | `{'other_convergence_warning': 12, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J0 | N2 | 21 | 2 | 9 | 1 | `{'1e-10': 2}` | `{'other_convergence_warning': 8, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N2 | 22 | 2 | 7 | 1 | `{'1e-10': 2}` | `{'other_convergence_warning': 6, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J0 | N2 | 23 | 2 | 8 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 8}` |
| P0_cold5 | J0 | N2 | 24 | 2 | 7 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 7}` |
| P0_cold5 | J1 | N1 | 5 | 12 | 1 | 1 | `{'1e-10': 9, '1e-08': 3}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N1 | 6 | 12 | 5 | 5 | `{'1e-10': 11, '1e-08': 1}` | `{'hyperparameter_boundary_convergence': 5}` |
| P0_cold5 | J1 | N1 | 7 | 12 | 3 | 3 | `{'1e-10': 12}` | `{'hyperparameter_boundary_convergence': 3}` |
| P0_cold5 | J1 | N1 | 8 | 12 | 2 | 2 | `{'1e-10': 8, '1e-08': 4}` | `{'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J1 | N1 | 9 | 12 | 1 | 1 | `{'1e-10': 8, '1e-08': 4}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N1 | 10 | 11 | 7 | 2 | `{'1e-08': 3, '1e-10': 8}` | `{'other_convergence_warning': 5, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J1 | N1 | 11 | 11 | 7 | 1 | `{'1e-08': 2, '1e-10': 9}` | `{'other_convergence_warning': 6, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N1 | 12 | 11 | 7 | 0 | `{'1e-08': 3, '1e-10': 8}` | `{'other_convergence_warning': 7}` |
| P0_cold5 | J1 | N1 | 13 | 8 | 16 | 0 | `{'1e-10': 5, '1e-08': 3}` | `{'other_convergence_warning': 16}` |
| P0_cold5 | J1 | N1 | 14 | 7 | 17 | 0 | `{'1e-10': 5, '1e-08': 2}` | `{'other_convergence_warning': 17}` |
| P0_cold5 | J1 | N1 | 15 | 5 | 14 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 14}` |
| P0_cold5 | J1 | N1 | 16 | 4 | 18 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 18}` |
| P0_cold5 | J1 | N1 | 17 | 4 | 15 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 15}` |
| P0_cold5 | J1 | N1 | 18 | 4 | 18 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 18}` |
| P0_cold5 | J1 | N1 | 19 | 4 | 18 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 18}` |
| P0_cold5 | J1 | N1 | 20 | 4 | 25 | 1 | `{'1e-10': 4}` | `{'other_convergence_warning': 24, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N1 | 21 | 4 | 21 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 21}` |
| P0_cold5 | J1 | N1 | 22 | 4 | 22 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 22}` |
| P0_cold5 | J1 | N1 | 23 | 4 | 17 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 17}` |
| P0_cold5 | J1 | N1 | 24 | 4 | 18 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 18}` |
| P0_cold5 | J1 | N2 | 5 | 12 | 1 | 1 | `{'1e-10': 10, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N2 | 6 | 12 | 0 | 0 | `{'1e-10': 9, '1e-08': 3}` | `{}` |
| P0_cold5 | J1 | N2 | 7 | 12 | 1 | 1 | `{'1e-10': 11, '1e-08': 1}` | `{'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N2 | 8 | 12 | 0 | 0 | `{'1e-08': 2, '1e-10': 10}` | `{}` |
| P0_cold5 | J1 | N2 | 9 | 10 | 6 | 1 | `{'1e-10': 10}` | `{'other_convergence_warning': 5, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N2 | 10 | 9 | 5 | 2 | `{'1e-10': 9}` | `{'other_convergence_warning': 3, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J1 | N2 | 11 | 8 | 4 | 0 | `{'1e-10': 7, '1e-08': 1}` | `{'other_convergence_warning': 4}` |
| P0_cold5 | J1 | N2 | 12 | 8 | 2 | 0 | `{'1e-10': 7, '1e-08': 1}` | `{'other_convergence_warning': 2}` |
| P0_cold5 | J1 | N2 | 13 | 7 | 5 | 0 | `{'1e-10': 6, '1e-08': 1}` | `{'other_convergence_warning': 5}` |
| P0_cold5 | J1 | N2 | 14 | 7 | 6 | 1 | `{'1e-10': 7}` | `{'other_convergence_warning': 5, 'hyperparameter_boundary_convergence': 1}` |
| P0_cold5 | J1 | N2 | 15 | 5 | 9 | 2 | `{'1e-10': 5}` | `{'other_convergence_warning': 7, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J1 | N2 | 16 | 3 | 8 | 2 | `{'1e-10': 2, '1e-08': 1}` | `{'other_convergence_warning': 6, 'hyperparameter_boundary_convergence': 2}` |
| P0_cold5 | J1 | N2 | 17 | 2 | 5 | 0 | `{'1e-10': 1, '1e-08': 1}` | `{'other_convergence_warning': 5}` |
| P0_cold5 | J1 | N2 | 18 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P0_cold5 | J1 | N2 | 19 | 1 | 7 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 7}` |
| P0_cold5 | J1 | N2 | 20 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P0_cold5 | J1 | N2 | 21 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P0_cold5 | J1 | N2 | 22 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P0_cold5 | J1 | N2 | 23 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P0_cold5 | J1 | N2 | 24 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P1_sobol12 | J0 | N1 | 12 | 12 | 9 | 9 | `{'1e-10': 10, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 9}` |
| P1_sobol12 | J0 | N1 | 13 | 12 | 9 | 9 | `{'1e-10': 4, '1e-08': 8}` | `{'hyperparameter_boundary_convergence': 9}` |
| P1_sobol12 | J0 | N1 | 14 | 9 | 6 | 6 | `{'1e-08': 8, '1e-10': 1}` | `{'hyperparameter_boundary_convergence': 6}` |
| P1_sobol12 | J0 | N1 | 15 | 7 | 0 | 0 | `{'1e-10': 1, '1e-08': 6}` | `{}` |
| P1_sobol12 | J0 | N1 | 16 | 7 | 7 | 7 | `{'1e-10': 2, '1e-08': 5}` | `{'hyperparameter_boundary_convergence': 7}` |
| P1_sobol12 | J0 | N1 | 17 | 4 | 3 | 3 | `{'1e-08': 3, '1e-10': 1}` | `{'hyperparameter_boundary_convergence': 3}` |
| P1_sobol12 | J0 | N1 | 18 | 3 | 0 | 0 | `{'1e-08': 2, '1e-10': 1}` | `{}` |
| P1_sobol12 | J0 | N1 | 19 | 1 | 0 | 0 | `{'1e-08': 1}` | `{}` |
| P1_sobol12 | J0 | N2 | 12 | 12 | 11 | 11 | `{'1e-10': 10, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 11}` |
| P1_sobol12 | J0 | N2 | 13 | 11 | 1 | 1 | `{'1e-10': 9, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 1}` |
| P1_sobol12 | J0 | N2 | 14 | 6 | 0 | 0 | `{'1e-08': 5, '1e-10': 1}` | `{}` |
| P1_sobol12 | J0 | N2 | 15 | 5 | 4 | 4 | `{'1e-08': 4, '1e-10': 1}` | `{'hyperparameter_boundary_convergence': 4}` |
| P1_sobol12 | J0 | N2 | 16 | 4 | 0 | 0 | `{'1e-08': 4}` | `{}` |
| P1_sobol12 | J0 | N2 | 17 | 4 | 2 | 2 | `{'1e-10': 2, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 2}` |
| P1_sobol12 | J0 | N2 | 18 | 3 | 6 | 0 | `{'1e-08': 1, '1e-10': 2}` | `{'other_convergence_warning': 6}` |
| P1_sobol12 | J0 | N2 | 19 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J0 | N2 | 20 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J0 | N2 | 21 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J0 | N2 | 22 | 1 | 6 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 6}` |
| P1_sobol12 | J0 | N2 | 23 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P1_sobol12 | J0 | N2 | 24 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P1_sobol12 | J0 | N2 | 25 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P1_sobol12 | J0 | N2 | 26 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J0 | N2 | 27 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P1_sobol12 | J0 | N2 | 28 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J0 | N2 | 29 | 1 | 7 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 7}` |
| P1_sobol12 | J0 | N2 | 30 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P1_sobol12 | J0 | N2 | 31 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J1 | N1 | 12 | 12 | 13 | 13 | `{'1e-10': 10, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 13}` |
| P1_sobol12 | J1 | N1 | 13 | 12 | 7 | 7 | `{'1e-10': 4, '1e-08': 8}` | `{'hyperparameter_boundary_convergence': 7}` |
| P1_sobol12 | J1 | N1 | 14 | 11 | 3 | 3 | `{'1e-08': 9, '1e-10': 2}` | `{'hyperparameter_boundary_convergence': 3}` |
| P1_sobol12 | J1 | N1 | 15 | 9 | 1 | 1 | `{'1e-10': 4, '1e-08': 5}` | `{'hyperparameter_boundary_convergence': 1}` |
| P1_sobol12 | J1 | N1 | 16 | 8 | 3 | 3 | `{'1e-08': 5, '1e-10': 3}` | `{'hyperparameter_boundary_convergence': 3}` |
| P1_sobol12 | J1 | N1 | 17 | 6 | 1 | 1 | `{'1e-10': 3, '1e-08': 3}` | `{'hyperparameter_boundary_convergence': 1}` |
| P1_sobol12 | J1 | N1 | 18 | 5 | 0 | 0 | `{'1e-08': 4, '1e-10': 1}` | `{}` |
| P1_sobol12 | J1 | N1 | 19 | 2 | 0 | 0 | `{'1e-08': 1, '1e-10': 1}` | `{}` |
| P1_sobol12 | J1 | N2 | 12 | 12 | 3 | 3 | `{'1e-10': 10, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 3}` |
| P1_sobol12 | J1 | N2 | 13 | 10 | 1 | 1 | `{'1e-10': 8, '1e-08': 2}` | `{'hyperparameter_boundary_convergence': 1}` |
| P1_sobol12 | J1 | N2 | 14 | 9 | 0 | 0 | `{'1e-08': 6, '1e-10': 3}` | `{}` |
| P1_sobol12 | J1 | N2 | 15 | 9 | 0 | 0 | `{'1e-08': 7, '1e-10': 2}` | `{}` |
| P1_sobol12 | J1 | N2 | 16 | 7 | 0 | 0 | `{'1e-08': 4, '1e-10': 3}` | `{}` |
| P1_sobol12 | J1 | N2 | 17 | 3 | 1 | 0 | `{'1e-10': 2, '1e-08': 1}` | `{'other_convergence_warning': 1}` |
| P1_sobol12 | J1 | N2 | 18 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J1 | N2 | 19 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J1 | N2 | 20 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P1_sobol12 | J1 | N2 | 21 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P1_sobol12 | J1 | N2 | 22 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P1_sobol12 | J1 | N2 | 23 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P1_sobol12 | J1 | N2 | 24 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P1_sobol12 | J1 | N2 | 25 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P1_sobol12 | J1 | N2 | 26 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P1_sobol12 | J1 | N2 | 27 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P1_sobol12 | J1 | N2 | 28 | 1 | 1 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 1}` |
| P1_sobol12 | J1 | N2 | 29 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P2_sobol37 | J0 | N1 | 37 | 12 | 0 | 0 | `{'1e-08': 2, '1e-10': 10}` | `{}` |
| P2_sobol37 | J0 | N1 | 38 | 9 | 0 | 0 | `{'1e-10': 7, '1e-08': 2}` | `{}` |
| P2_sobol37 | J0 | N1 | 39 | 8 | 0 | 0 | `{'1e-08': 5, '1e-10': 3}` | `{}` |
| P2_sobol37 | J0 | N1 | 40 | 5 | 0 | 0 | `{'1e-08': 4, '1e-10': 1}` | `{}` |
| P2_sobol37 | J0 | N1 | 41 | 4 | 2 | 1 | `{'1e-08': 3, '1e-10': 1}` | `{'other_convergence_warning': 1, 'hyperparameter_boundary_convergence': 1}` |
| P2_sobol37 | J0 | N1 | 42 | 2 | 1 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 1}` |
| P2_sobol37 | J0 | N1 | 43 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J0 | N1 | 44 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J0 | N1 | 45 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P2_sobol37 | J0 | N1 | 46 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P2_sobol37 | J0 | N1 | 47 | 1 | 1 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 1}` |
| P2_sobol37 | J0 | N1 | 48 | 1 | 7 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 7}` |
| P2_sobol37 | J0 | N1 | 49 | 1 | 0 | 0 | `{'1e-10': 1}` | `{}` |
| P2_sobol37 | J0 | N1 | 50 | 1 | 1 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 1}` |
| P2_sobol37 | J0 | N1 | 51 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P2_sobol37 | J0 | N1 | 52 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J0 | N1 | 53 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P2_sobol37 | J0 | N1 | 54 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J0 | N1 | 55 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P2_sobol37 | J0 | N1 | 56 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P2_sobol37 | J0 | N2 | 37 | 12 | 0 | 0 | `{'1e-10': 11, '1e-08': 1}` | `{}` |
| P2_sobol37 | J0 | N2 | 38 | 8 | 1 | 1 | `{'1e-10': 7, '1e-08': 1}` | `{'hyperparameter_boundary_convergence': 1}` |
| P2_sobol37 | J0 | N2 | 39 | 5 | 1 | 0 | `{'1e-08': 4, '1e-10': 1}` | `{'other_convergence_warning': 1}` |
| P2_sobol37 | J0 | N2 | 40 | 3 | 0 | 0 | `{'1e-08': 3}` | `{}` |
| P2_sobol37 | J0 | N2 | 41 | 2 | 1 | 0 | `{'1e-08': 2}` | `{'other_convergence_warning': 1}` |
| P2_sobol37 | J0 | N2 | 42 | 1 | 6 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 6}` |
| P2_sobol37 | J0 | N2 | 43 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J0 | N2 | 44 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P2_sobol37 | J0 | N2 | 45 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P2_sobol37 | J0 | N2 | 46 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P2_sobol37 | J0 | N2 | 47 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J0 | N2 | 48 | 1 | 1 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 1}` |
| P2_sobol37 | J0 | N2 | 49 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P2_sobol37 | J0 | N2 | 50 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J0 | N2 | 51 | 1 | 3 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 3}` |
| P2_sobol37 | J0 | N2 | 52 | 1 | 4 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 4}` |
| P2_sobol37 | J0 | N2 | 53 | 1 | 2 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 2}` |
| P2_sobol37 | J0 | N2 | 54 | 1 | 6 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 6}` |
| P2_sobol37 | J0 | N2 | 55 | 1 | 5 | 0 | `{'1e-10': 1}` | `{'other_convergence_warning': 5}` |
| P2_sobol37 | J1 | N1 | 37 | 12 | 0 | 0 | `{'1e-10': 12}` | `{}` |
| P2_sobol37 | J1 | N1 | 38 | 8 | 0 | 0 | `{'1e-10': 4, '1e-08': 4}` | `{}` |
| P2_sobol37 | J1 | N1 | 39 | 7 | 2 | 2 | `{'1e-08': 6, '1e-10': 1}` | `{'hyperparameter_boundary_convergence': 2}` |
| P2_sobol37 | J1 | N1 | 40 | 2 | 0 | 0 | `{'1e-08': 2}` | `{}` |
| P2_sobol37 | J1 | N1 | 41 | 2 | 0 | 0 | `{'1e-08': 2}` | `{}` |
| P2_sobol37 | J1 | N2 | 37 | 12 | 0 | 0 | `{'1e-10': 12}` | `{}` |
| P2_sobol37 | J1 | N2 | 38 | 8 | 0 | 0 | `{'1e-10': 7, '1e-08': 1}` | `{}` |
| P2_sobol37 | J1 | N2 | 39 | 3 | 0 | 0 | `{'1e-08': 1, '1e-10': 2}` | `{}` |
| P3_train37 | J0 | N1 | 37 | 12 | 0 | 0 | `{'1e-10': 12}` | `{}` |
| P3_train37 | J0 | N1 | 38 | 10 | 0 | 0 | `{'1e-10': 8, '1e-08': 2}` | `{}` |
| P3_train37 | J0 | N1 | 39 | 10 | 1 | 0 | `{'1e-10': 9, '1e-08': 1}` | `{'other_convergence_warning': 1}` |
| P3_train37 | J0 | N1 | 40 | 9 | 6 | 0 | `{'1e-08': 2, '1e-10': 7}` | `{'other_convergence_warning': 6}` |
| P3_train37 | J0 | N1 | 41 | 7 | 11 | 0 | `{'1e-08': 2, '1e-10': 5}` | `{'other_convergence_warning': 11}` |
| P3_train37 | J0 | N1 | 42 | 7 | 30 | 0 | `{'1e-08': 2, '1e-10': 5}` | `{'other_convergence_warning': 30}` |
| P3_train37 | J0 | N1 | 43 | 7 | 25 | 1 | `{'1e-10': 6, '1e-08': 1}` | `{'hyperparameter_boundary_convergence': 1, 'other_convergence_warning': 24}` |
| P3_train37 | J0 | N1 | 44 | 6 | 24 | 0 | `{'1e-08': 1, '1e-10': 5}` | `{'other_convergence_warning': 24}` |
| P3_train37 | J0 | N1 | 45 | 5 | 22 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 22}` |
| P3_train37 | J0 | N1 | 46 | 5 | 23 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 23}` |
| P3_train37 | J0 | N1 | 47 | 5 | 20 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 20}` |
| P3_train37 | J0 | N1 | 48 | 5 | 24 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 24}` |
| P3_train37 | J0 | N1 | 49 | 5 | 17 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 17}` |
| P3_train37 | J0 | N1 | 50 | 5 | 18 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 18}` |
| P3_train37 | J0 | N1 | 51 | 4 | 18 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 18}` |
| P3_train37 | J0 | N1 | 52 | 4 | 15 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 15}` |
| P3_train37 | J0 | N1 | 53 | 4 | 13 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 13}` |
| P3_train37 | J0 | N1 | 54 | 4 | 16 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 16}` |
| P3_train37 | J0 | N1 | 55 | 4 | 22 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 22}` |
| P3_train37 | J0 | N1 | 56 | 4 | 21 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 21}` |
| P3_train37 | J0 | N2 | 37 | 9 | 0 | 0 | `{'1e-08': 1, '1e-10': 8}` | `{}` |
| P3_train37 | J0 | N2 | 38 | 7 | 2 | 1 | `{'1e-08': 3, '1e-10': 4}` | `{'hyperparameter_boundary_convergence': 2}` |
| P3_train37 | J0 | N2 | 39 | 7 | 1 | 0 | `{'1e-10': 7}` | `{'other_convergence_warning': 1}` |
| P3_train37 | J0 | N2 | 40 | 6 | 7 | 0 | `{'1e-10': 5, '1e-08': 1}` | `{'other_convergence_warning': 7}` |
| P3_train37 | J0 | N2 | 41 | 6 | 15 | 0 | `{'1e-10': 6}` | `{'other_convergence_warning': 15}` |
| P3_train37 | J0 | N2 | 42 | 6 | 15 | 0 | `{'1e-10': 4, '1e-08': 2}` | `{'other_convergence_warning': 15}` |
| P3_train37 | J0 | N2 | 43 | 5 | 18 | 0 | `{'1e-10': 4, '1e-08': 1}` | `{'other_convergence_warning': 18}` |
| P3_train37 | J0 | N2 | 44 | 4 | 23 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 23}` |
| P3_train37 | J0 | N2 | 45 | 4 | 17 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 17}` |
| P3_train37 | J0 | N2 | 46 | 4 | 17 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 17}` |
| P3_train37 | J0 | N2 | 47 | 4 | 19 | 0 | `{'1e-10': 4}` | `{'other_convergence_warning': 19}` |
| P3_train37 | J0 | N2 | 48 | 3 | 19 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 19}` |
| P3_train37 | J0 | N2 | 49 | 3 | 10 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 10}` |
| P3_train37 | J0 | N2 | 50 | 3 | 16 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 16}` |
| P3_train37 | J0 | N2 | 51 | 3 | 14 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 14}` |
| P3_train37 | J0 | N2 | 52 | 3 | 12 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 12}` |
| P3_train37 | J0 | N2 | 53 | 3 | 10 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 10}` |
| P3_train37 | J0 | N2 | 54 | 3 | 10 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 10}` |
| P3_train37 | J0 | N2 | 55 | 3 | 11 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 11}` |
| P3_train37 | J0 | N2 | 56 | 3 | 8 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 8}` |
| P3_train37 | J1 | N1 | 37 | 12 | 2 | 2 | `{'1e-08': 1, '1e-10': 11}` | `{'hyperparameter_boundary_convergence': 2}` |
| P3_train37 | J1 | N1 | 38 | 11 | 4 | 4 | `{'1e-08': 2, '1e-10': 9}` | `{'hyperparameter_boundary_convergence': 4}` |
| P3_train37 | J1 | N1 | 39 | 11 | 10 | 2 | `{'1e-08': 3, '1e-10': 8}` | `{'other_convergence_warning': 8, 'hyperparameter_boundary_convergence': 2}` |
| P3_train37 | J1 | N1 | 40 | 11 | 9 | 2 | `{'1e-08': 2, '1e-10': 9}` | `{'hyperparameter_boundary_convergence': 2, 'other_convergence_warning': 7}` |
| P3_train37 | J1 | N1 | 41 | 10 | 12 | 2 | `{'1e-10': 9, '1e-08': 1}` | `{'hyperparameter_boundary_convergence': 2, 'other_convergence_warning': 10}` |
| P3_train37 | J1 | N1 | 42 | 9 | 16 | 0 | `{'1e-08': 2, '1e-10': 7}` | `{'other_convergence_warning': 16}` |
| P3_train37 | J1 | N1 | 43 | 8 | 18 | 0 | `{'1e-08': 1, '1e-10': 7}` | `{'other_convergence_warning': 18}` |
| P3_train37 | J1 | N1 | 44 | 7 | 18 | 0 | `{'1e-10': 7}` | `{'other_convergence_warning': 18}` |
| P3_train37 | J1 | N1 | 45 | 7 | 16 | 1 | `{'1e-10': 7}` | `{'other_convergence_warning': 15, 'hyperparameter_boundary_convergence': 1}` |
| P3_train37 | J1 | N1 | 46 | 5 | 12 | 0 | `{'1e-10': 5}` | `{'other_convergence_warning': 12}` |
| P3_train37 | J1 | N1 | 47 | 5 | 13 | 2 | `{'1e-10': 4, '1e-08': 1}` | `{'other_convergence_warning': 11, 'hyperparameter_boundary_convergence': 2}` |
| P3_train37 | J1 | N1 | 48 | 4 | 18 | 5 | `{'1e-10': 3, '1e-08': 1}` | `{'other_convergence_warning': 13, 'hyperparameter_boundary_convergence': 5}` |
| P3_train37 | J1 | N1 | 49 | 3 | 11 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 11}` |
| P3_train37 | J1 | N1 | 50 | 3 | 14 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 14}` |
| P3_train37 | J1 | N1 | 51 | 3 | 15 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 15}` |
| P3_train37 | J1 | N1 | 52 | 3 | 8 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 8}` |
| P3_train37 | J1 | N1 | 53 | 3 | 16 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 16}` |
| P3_train37 | J1 | N1 | 54 | 3 | 13 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 13}` |
| P3_train37 | J1 | N1 | 55 | 3 | 18 | 2 | `{'1e-10': 3}` | `{'other_convergence_warning': 16, 'hyperparameter_boundary_convergence': 2}` |
| P3_train37 | J1 | N1 | 56 | 3 | 19 | 1 | `{'1e-10': 3}` | `{'other_convergence_warning': 18, 'hyperparameter_boundary_convergence': 1}` |
| P3_train37 | J1 | N2 | 37 | 12 | 0 | 0 | `{'1e-08': 1, '1e-10': 11}` | `{}` |
| P3_train37 | J1 | N2 | 38 | 11 | 3 | 2 | `{'1e-08': 1, '1e-10': 10}` | `{'hyperparameter_boundary_convergence': 3}` |
| P3_train37 | J1 | N2 | 39 | 9 | 0 | 0 | `{'1e-08': 2, '1e-10': 7}` | `{}` |
| P3_train37 | J1 | N2 | 40 | 7 | 4 | 0 | `{'1e-08': 3, '1e-10': 4}` | `{'other_convergence_warning': 4}` |
| P3_train37 | J1 | N2 | 41 | 4 | 13 | 0 | `{'1e-10': 3, '1e-08': 1}` | `{'other_convergence_warning': 13}` |
| P3_train37 | J1 | N2 | 42 | 3 | 12 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 12}` |
| P3_train37 | J1 | N2 | 43 | 3 | 8 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 8}` |
| P3_train37 | J1 | N2 | 44 | 3 | 12 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 12}` |
| P3_train37 | J1 | N2 | 45 | 3 | 11 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 11}` |
| P3_train37 | J1 | N2 | 46 | 3 | 10 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 10}` |
| P3_train37 | J1 | N2 | 47 | 3 | 16 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 16}` |
| P3_train37 | J1 | N2 | 48 | 3 | 9 | 0 | `{'1e-10': 3}` | `{'other_convergence_warning': 9}` |
| P3_train37 | J1 | N2 | 49 | 2 | 6 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 6}` |
| P3_train37 | J1 | N2 | 50 | 2 | 4 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 4}` |
| P3_train37 | J1 | N2 | 51 | 2 | 6 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 6}` |
| P3_train37 | J1 | N2 | 52 | 2 | 5 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 5}` |
| P3_train37 | J1 | N2 | 53 | 2 | 8 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 8}` |
| P3_train37 | J1 | N2 | 54 | 2 | 7 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 7}` |
| P3_train37 | J1 | N2 | 55 | 2 | 9 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 9}` |
| P3_train37 | J1 | N2 | 56 | 2 | 9 | 0 | `{'1e-10': 2}` | `{'other_convergence_warning': 9}` |
