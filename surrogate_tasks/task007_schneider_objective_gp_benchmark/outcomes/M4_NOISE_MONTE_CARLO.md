# M4A primary J1 noise Monte Carlo

每个 off-grid target/scenario 使用 10 个新的确定性 noise seeds；P1/P2 均使用 response-blind stop，MAP 只在运行结束后评分。

| method | noise | replicates | MAP hits | fraction | median queries | p90 | max | Gate |
|---|---|---:|---:|---:|---:|---:|---:|---|
| P1_sobol12 | N1 | 120 | 115 | 0.958 | 20.0 | 20.0 | 20 | negative |
| P1_sobol12 | N2 | 120 | 118 | 0.983 | 10.0 | 14.0 | 20 | PASS |
| P2_sobol37 | N1 | 120 | 115 | 0.958 | 10.0 | 13.0 | 20 | negative |
| P2_sobol37 | N2 | 120 | 116 | 0.967 | 7.0 | 10.0 | 13 | PASS |
