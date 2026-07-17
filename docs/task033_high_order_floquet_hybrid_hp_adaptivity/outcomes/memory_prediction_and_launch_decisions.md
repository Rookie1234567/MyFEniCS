# Task033 内存预测与启动决策

> 2026-07-17：完整 p/h 启动矩阵已因用户缩小范围而停止。已完成的 Case090/QEP
> 与 Hybrid p1 局部运行均由外部 watchdog、零 swap 和 clean-source Gate 控制；
> 尚未启动的 p2/p3/p4 Hybrid/adaptive 组合统一记为 `deferred_by_user_scope`，
> 不沿用 planning 表中的“即将启动”含义。

## 1. Effective limits

| Limit | Nominal Task033 | Effective Task033 | Unit | 数据身份 | 证据 |
|---|---:|---:|---|---|---|
| hard upper | 14.000 | 13.6485 | GiB | measured/derived | `environment_and_base.md` |
| center/warning | 11.500 | 11.2113 | GiB | derived by preserved ratio | same |
| conservative upper | 12.800 | 12.4786 | GiB | derived by preserved ratio | same |
| controlled termination | 13.000 | 12.6736 | GiB | derived by preserved ratio | same |

The effective column preserves each task-book fraction of the hard budget and applies it to
the smaller Docker Engine memory total. `memory.max=max` does not override the smaller
numeric Docker VM ceiling.

## 2. 已执行阶段的 launch contract

| Check | Required condition | 当前状态 | 数据身份 | Action on failure |
|---|---|---|---|---|
| tracked source | clean commit and captured SHA | pass for completed records | measured | source `6613f94...` |
| candidate prediction/guard | candidate-specific gate before launch | pass for launched Case090/QEP/Hybrid p1 | measured | external watchdog summaries |
| host/container authority | refreshed and readable | pass for completed records | measured | cgroup + simultaneous worker RSS |
| swap | zero use for formal case | pass for completed records | measured | cgroup swap and pswpin/pswpout delta zero |
| watchdog | warning/termination thresholds active | pass | measured | no memory termination in retained records |
| concurrency | one large case at a time | pass | measured | serialized campaign runner |
| future p2/p3/p4 Hybrid/adaptive | new scope authorization required | deferred | not_run | no launch now |

## 3. Candidate decisions

| Candidate group | Prediction | Launch decision | Current status | 数据身份 | Evidence |
|---|---|---|---|---|---|
| pure 3D microfixtures | watchdog-qualified | launch complete | 144 PDE pass | measured | Case090 aggregate |
| QEP MPI1 matrix | watchdog-qualified | launch complete | 36/36 shards pass | measured | stage summary |
| Hybrid p1/h5 | watchdog-qualified | launch complete | funnel negative by modal capacity | measured | ignored campaign |
| Hybrid p1/h3 | watchdog-qualified | stopped by user scope | M80/M120 complete; M160 incomplete | measured + incomplete | stage summary |
| remaining uniform/adaptive combinations | no longer in current scope | do_not_launch | deferred | not_run | `summary.md` |

本阶段已实际启动并由 watchdog 管理上述候选；未完成项的停止原因是范围调整，不是内存 Gate。
