# M4A standalone acquisition replay

本审计没有调用 M3 `run_sequential_bo` 或 `_continuous_acquisition`；从 stored initial `(x,F)` 逐步重拟合 ExactARDGP，并独立重算 EI、fallback、chosen query 和 objective。

| quantity | result | Gate |
|---|---:|---|
| primary J1 P2 trajectories | 24 | 24 required |
| exact replay pass | 24/24 | geometry <= 1e-7, EI <= 1e-8, mode/query/final identity |

This is an acquisition replay audit, not a claim that the checker is a second physical oracle.
