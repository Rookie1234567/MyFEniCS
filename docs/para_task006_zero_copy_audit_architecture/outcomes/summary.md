# PARA-Task006 执行状态

## 当前 Gate

| 阶段 | 状态 | 结论 |
|---|---|---|
| P0 provenance / clean baseline | **PASS** | 允许进入 P1 |
| P1 borrowed exact action | **PASS** | 16/16 等价，允许进入 P2 |
| P2 proxy Q0 calibration | in progress | 尚无结论 |
| P3-P8 | not run | 按 Gate 等待 |

P0 在 clean `9822bc5` 上得到 852 iterations、93.347 s solve、三种 residual
约 `9.98025e-7`、R/T/A closure `-1.860e-9`、外部 simultaneous worker peak
1.608 GiB 和 zero swap。完整测试为 209 passed、12 skipped。

R4 checkpoint 复用 `A_D0_R64`，4/4 weights SHA、operator fingerprint 和 teacher
dataset identity 匹配；没有 retraining。H 已明确为 consumed screening split，
V 未用于 Task005 候选选择。

Task006 仍为 research-only qualification。当前没有 proxy、periodic audit、live
shadow、memory-neutral 或恢复 Task005 P3 的结论。

## P1 摘要

| 指标 | 结果 |
|---|---:|
| formal configuration | h5 / MPI4 |
| slabs / probes | 16 / 64 |
| borrowed-vs-CSR action max | `6.030e-16` |
| rho absolute difference max | `3.558e-16` |
| persistent private CSR | 0 bytes |
| per-rank work vectors | 0.753–0.762 MiB |
| mean collective exact audit | 6.207 ms |
| ordinary solve | 852 iterations；numeric/RTA pass |
| external peak ratio vs P0 | `1.00309x` |

P1 证明 exact local action 可复用既有 shifted-F/global operator 与 union scatter，
无需 persistent local CSR。P2 将只用 Q0 校准 reduced/sketch/composite proxy；
在阈值冻结前不会读取 Q1-Q5。
