# M4A response-blind stopping audit

停止判据在运行时不读取 hidden oracle MAP：`max grid EI < 1e-3` 连续两次，且最好 log-objective improvement < 1e-3 连续三次；否则最多 20 次 query。MAP 只在运行结束后评分。

| method | noise | MAP hits | median queries | p90 | max | stop-rule stops | Gate |
|---|---|---:|---:|---:|---:|---:|---|
| P1_sobol12 | N1 | 12/12 | 20.0 | 20.0 | 20 | 3 | negative |
| P1_sobol12 | N2 | 11/12 | 10.5 | 15.9 | 20 | 11 | negative |
| P2_sobol37 | N1 | 12/12 | 11.0 | 14.9 | 16 | 12 | negative |
| P2_sobol37 | N2 | 12/12 | 7.0 | 8.0 | 9 | 12 | PASS |
