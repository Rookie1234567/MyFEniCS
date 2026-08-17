# Task037-extra Response V14：W18A nested auxiliary 正式负结果

本文件记录 W18A 的唯一正式 action-only 运行和冻结证据 checker v2。`response_v13.md` 保持冻结，W14A–W17A 的旧 raw、watchdog、compact 和负结果均不改写。

## 一页结论

W18A 的“nested auxiliary”意思是：外层每一步先调用一个固定的辅助近似逆，再把得到的方向交给物理 action 检查。它不是把完整物理方程重新求解一遍。本路线固定使用 `B=S(beta1)+T`，其中 `S` 是 beta=1 的 shifted volume action，`T` 是同一个 matrix-free DtN80；每个外层 PC 都是 fixed40 内层。物理检查使用 `A=beta0 volume+T`。全程没有 PDE、physical KSP、场恢复、R/T/A 或 physical screen。

| 路线 | 关键结果 | 状态 |
|---|---|---|
| W14A | physical rho `0.8943645606070599`；peak `1,158,553,600 B` | action/resource 通过；不是 PDE/RTA |
| W14B | fixed4 inner4 `0.01751006766159766 > 0.01` | `W14B_FIXED4_CORRECTION_FAIL`；W14C locked |
| W15A | cumulative rho `0.8937535419182971` | `W15A_RESTART1_NUMERIC_FAIL`；W15B locked |
| W16A/W16R/W16B | W16R rho `0.8814092210776835`；W16B rho2 `0.8796856414991869` | W16B 数值 Gate 失败；W16C locked |
| W17A | physical rho `0.8917790380896942`；cycle40 `0.12567225369307264` | `W17A_GLOBAL_PHYSICAL_SHIFTED_NUMERIC_FAIL`；W17B locked |
| W18A | inner/outer/rho 均有明确数值失败 | `W18A_NESTED_AUXILIARY_NUMERIC_FAIL`；physical screen locked |

## W18A 唯一正式运行

正式 producer source SHA 为 `839ce6733db2dc737f5c8bfb6347633f53161d82`。运行自然完成；没有 timeout、RSS termination、swap 或 compiler descendant。authoritative checker v2 的 checker source SHA 为 `26ea955690b1541c2bd43856799508bc85ffe1e6`。

v2 的顶层 checks 共 23 项，其中 22 项为 `true`，唯一为 `false` 的是 `worker_action_gate`；`problems` 也只有 `worker_action_gate`。worker 的数值子检查明确保留了 `inner_residual=false`、`outer_auxiliary_residual=false` 和 `measurements=false`，其余 worker checks 均通过。因此这是数值 Gate 负结果，不是执行或资源失败。

| 项目 | v2 结果 | 解释 |
|---|---:|---|
| inner final true residuals | `0.008234328428613734 / 0.012917460577236278` | 第二个超过硬门 `<=1e-2` |
| outer checkpoint residuals | `0.09956749409891383 / 0.03857856488992854` | 两个都未达到 `<=1e-2` |
| physical rho | `0.8814092210776835 / 0.8918283239976347` | 第二个超过 `0.85`，且比第一个更差 |
| repeat identity | z、outer action、physical p 均 exact；relative differences 为 `0` | 重复性通过 |
| normal closure | `0` | 通过 |
| projection orthogonality | finite，约 `4.66e-16 / 3.73e-16` | 通过 |
| measured process-tree peak | `1,546,248,192 B` | action-only resource evidence |
| swap / compiler descendants | `0 / []` | 资源证据通过 |
| derived prediction | `1,734,993,014 B` | 预测值，不是 PDE 实测峰值 |

精确 action 账本为：`outer_auxiliary=8`、`outer_pc=4`、`inner_global_shifted=172`、`local_pc=160`、`local_exact_shifted=160`、`shifted_total=340`、`auxiliary_DtN=8`、`physical_volume=4`、`physical_DtN=4`、`total_DtN=12`。这些计数来自 checker 读取的 audit 和 raw evidence，不是从状态字段盲信。

## v1 与 v2 的权威关系

旧 v1 保持完整原样，但不再作为 W18A 权威结论。v1 的 checker 把真实生产 audit 的动态字段和 descriptor 形状当成错误结构，导致 `action_audit`/`vector_evidence` 被误判，原分类为 `W18A_EXECUTION_OR_EVIDENCE_FAIL`。修复后的 v2 分离 producer 与 checker source，重新读取同一冻结 raw/watchdog，并独立验证真实数组、audit、scratch 和资源字段；因此 v2 才是本轮权威分类。

这次修正没有重跑 worker，也没有改写 raw、watchdog 或 v1 compact。v2 只是在同一正式证据上重新执行 checker，结果仍为数值负结果。

## 根因边界与下一步

本轮结果支持的主要边界是：`B=S(beta1)+T` 的 nested solve 能明显降低部分辅助 residual，但由它产生的方向与物理 `A=beta0+T` 的校正并未充分对齐。当前证据不支持把失败归因于 timeout 或资源不足，也不支持仅靠增加同一路线步数解决；这不是对 modal decomposition 的数学证明。

W18A 的 physical screen、PDE、RTA 和后续路线继续锁定。下一步只允许先对 W18A 已保存的 `p1/p2` 做离线二维 span 诊断：只读数组，`0 action / 0 PDE`，不盲目重跑、不延长 fixed40、不启动新的 physical run。该诊断尚未运行，因而没有新的资格结论。

## 证据索引

| 证据 | 路径 | SHA / 说明 |
|---|---|---|
| raw summary | `benchmarks/artifacts/task037_extra_development/m6b_w18a_839ce67_formal_run1/m6b_w18a_summary.json` | `a82fb01c60b48575c2df59649375e3d330f85ba3edf43f1bd59c84bb2b29a4b5` |
| watchdog summary | `benchmarks/artifacts/task037_extra_development/m6b_w18a_839ce67_formal_watchdog_run1/w18a_watchdog_summary.json` | `a32275d426cfe826f80be46dc8fbeba481e5bd8047589454f77b77b7c7a953eb` |
| v1 compact | `benchmarks/cases/101_task37_extra_development/records/m6b_w18a_839ce67_formal_resource_closeout_v1.json` | `0c86b687fd76f366bd9148fec734794fdf21b2a3d0bf300fc502981cb48c210f`；保留但非权威 |
| v2 compact | `benchmarks/cases/101_task37_extra_development/records/m6b_w18a_839ce67_formal_resource_closeout_v2.json` | `3d9110cf7127333b676e96c5e7dd5cace23ecadc30127063d7f87171d510eb61`；权威 |
| v2 embedded evidence | 同上 v2 compact | `2132d54aacd70f38ea93e8c0886f7d2a5b86b8da6748d322edfc1d85afebc45f` |

W18A 的资源结果只说明 action-only 进程的这次峰值和 swap 证据闭合；它不能替代完整 PDE 的内存资格。full time-harmonic PDE、official field/RTA、direct-authority physics comparison 和最终 PDE `<2,000,000,000 B` 仍为 `not_run`。
