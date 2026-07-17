# Task033 内存预测与启动决策

> 2026-07-17：完整 p/h 启动矩阵已因用户缩小范围而停止。已完成的 Case090/QEP
> 与 Hybrid p1 局部运行均由外部 watchdog、零 swap 和 clean-source Gate 控制；
> review v3 批准的 p3/h5 Phase C 已完成候选级 C0：full3D 被内存 Gate 阻止，
> M80/M120/M160 与 augmented M160 安全运行。p3/h3、p4 target 与 adaptive
> 仍未批准，不沿用 planning 表中的“即将启动”含义。

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

Phase C0 没有沿用上表的旧 Phase-0 快照。现场 container limit 为 13 GiB、host
available 为 12.8433 GiB，因此 effective ceiling 为 12.8433 GiB；center/upper/
termination 相应收紧到 `10.5498 / 11.7424 / 11.9259 GiB`。

## 2. 已执行阶段的 launch contract

| Check | Required condition | 当前状态 | 数据身份 | Action on failure |
|---|---|---|---|---|
| tracked source | clean commit and captured SHA | pass for completed records | measured | original source `6613f94...`; Phase A selected runs `bb830ba...` |
| candidate prediction/guard | candidate-specific gate before launch | pass for launched Case090/QEP/Hybrid p1 | measured | external watchdog summaries |
| host/container authority | refreshed and readable | pass for completed records | measured | cgroup + simultaneous worker RSS |
| swap | zero use for formal case | pass for completed records | measured | cgroup swap and pswpin/pswpout delta zero |
| watchdog | warning/termination thresholds active | pass | measured | no memory termination in retained records |
| concurrency | one large case at a time | pass | measured | serialized campaign runner |
| Phase C p3/h5 | review v3 + candidate-specific C0 | Hybrid pass；full3D veto | measured + predicted negative | `p3_h5_phaseC.md` |
| p3/h3、p4 target、adaptive | new review authorization required | deferred | not_run | no launch now |

## 3. Candidate decisions

| Candidate group | Prediction | Launch decision | Current status | 数据身份 | Evidence |
|---|---|---|---|---|---|
| pure 3D microfixtures | watchdog-qualified | launch complete | 144 PDE pass | measured | Case090 aggregate |
| QEP MPI1 matrix | watchdog-qualified | launch complete | 36/36 shards pass | measured | stage summary |
| Hybrid p1/h5 | watchdog-qualified | launch complete | funnel negative by modal capacity | measured | ignored campaign |
| Hybrid p1/h3 | watchdog-qualified | stopped by user scope | M80/M120 complete; M160 incomplete | measured + incomplete | stage summary |
| p3/h5 full3D direct | centers 6.445 / 15.031 GiB；upper 18.038 GiB | do_not_launch | `not_run_by_memory_gate` | predicted negative | Phase C0 |
| p3/h5 Schur-minimal M80/120/160 | upper 6.011 GiB | serialized launch | three measured passes；2.278/2.492/2.641 GiB | measured | stage3 summary |
| p3/h5 augmented M160 | upper 10.123 GiB | launch after funnel | path-equivalence pass；4.148 GiB | measured | stage3 summary |
| remaining uniform/adaptive combinations | not approved | do_not_launch | deferred | not_run | `summary.md` |

full3D 的停止原因明确是内存 Gate；p3/h3、p4 和 adaptive 的停止原因是未获批准。
两者不能混写。Hybrid 候选已由各自预测与 watchdog 管理，不会把安全运行反向用作
full3D 的许可。
