# PARA-Task006 执行状态

## 当前 Gate

| 阶段 | 状态 | 结论 |
|---|---|---|
| P0 provenance / clean baseline | **PASS** | 允许进入 P1 |
| P1 borrowed exact action | **PASS** | 16/16 等价，允许进入 P2 |
| P2 proxy Q0 calibration | **FAIL** | false-reject/usability Gate |
| P3-P7 | `not_run_by_gate` | 无 usable locked proxy |
| P8 decision | **PASS** | `audit_architecture_false_reject_failure` |

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
无需 persistent local CSR。

## P2 与最终处置

P2 只访问 Q0/Task005 V，比较 q=64–2048、one/two procedural CountSketch seeds。
所有 12 个 family 都能用保守阈值得到 Q0 false accept 0，但最佳 non-harmful
acceptance 仅 43.37%；满足最终 two-seed 结构的最佳值为 42.96%，最差 slab
false reject 81.89%。

Q0 的未修改模型输出本身有 58/1024 harmful samples，因此若 99% acceptance
覆盖全部 unmodified outputs，zero-false-accept 下理论上限也只有 94.34%。
没有 family 被选择或冻结，Q1-Q5 未读取。按 Gate 停止 P3-P7，最终分类为
`audit_architecture_false_reject_failure`。

最终 validation：complete `src/test` 218 passed、12 skipped；MPI2/MPI4 每 rank
3 passed；Task006 Ruff、compileall、diff-check 与 artifact-ignore audit 全部通过。
