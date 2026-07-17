# Task033 内存预测与启动决策

## Review V5 Phase D1 实测

Review V5 的减缩矩阵只批准 `p3/h10`，并在其等精度失败后条件批准
`p3/h7.5`。两者均先做 assembly-only C0，再做 full solve 和 Hybrid
M120/M160；一次只有一个重型 case，外部 watchdog 生效，swap 峰值为零。

| candidate/path | predicted center / upper | measured memory | measured time | 决定 |
|---|---:|---:|---:|---|
| p3/h10 full3D assembly | 1.693 / 1.947 GiB | 1.406 GiB | — | C0 pass |
| p3/h10 full3D solve | 同上只作 launch 预测 | 1.980 GiB | 22.390 s | solve pass；equal-accuracy fail |
| p3/h10 Hybrid M160 | — | 1.661 GiB | 66.942 s | formal fail on sampled H-interface；停止，不跑 M240 |
| p3/h7.5 full3D assembly | 2.142 / 2.463 GiB | 2.556 GiB | — | 略超预测 upper，但远低于 termination；C0 pass |
| p3/h7.5 full3D solve | 同上只作 launch 预测 | 3.667 GiB | 44.487 s | solve/equal-accuracy pass |
| p3/h7.5 Hybrid M160 | — | 2.008 GiB | 74.908 s | 16 Gate pass；selected |

`p3/h7.5` 说明经验预测不能当作实测权威：assembly 峰值比上界高约 3.8%，但现场
仍有充足绝对余量，watchdog/no-swap/串行合同全部满足，所以继续 full solve 是合法的。
`p3/h10` 则说明“安全且便宜”不等于物理等精度；其精度失败才是解锁 h7.5 的条件。

Review V6 进一步冻结 full-solve 偏差：`p3/h10` 的 1.947 GiB 上界对应
1.980 GiB 实测，`p3/h7.5` 的 2.463 GiB 上界对应 3.667 GiB 实测。因此旧模型只
是 launch guard；未用新高阶实测重新校准前，禁止把它用于 1 TiB / 0.7 nm 推演。

## 2026-07-17 实测更新

用户给出的 p4 前置条件已经满足：p3/h5 full solve 为 7.781 GiB、cgroup swap 0。
因此 p4/h5 assembly-only 合法启动，并先通过 p3 前置记录和 p4 四模态迹记录两道
fail-closed 门禁。p4 随后失败的是自己的实测资源 Gate：

| 阶段 | 结果 |
|---|---:|
| p4 Nédélec DoF / Floquet constraints | 339,892 / 15,412 |
| base matrix | 339,892 rows / 155,205,040 NNZ |
| base matrix assembly | 463.109 s；约 5.00 GiB 内部 RSS |
| 增广矩阵复制后 | 10.990 GiB 内部 RSS |
| DtN 插入后 | 10.995 GiB 内部 RSS |
| 外部同时 RSS/cgroup 权威峰值 | 12.616 GiB |
| controlled termination / OOM | 是 / 否 |
| factorization or solve | 未进入 |

cgroup swap 峰值为 0，但系统 `pswpout` 增量为 4 页，所以正式 `no_swap` 按
fail-closed 记为 false。不得把“cgroup 没用 swap”改写成 formal no-swap pass。

因此不再重复装配，也不启动 p4 full3D factorization。p4 Hybrid M160 也有独立
否决：资源矩阵中心 37.038 GiB、保守上界 42.594 GiB。两条目标路径都不是因为
四模态数值组件失败，而是因为候选级资源 Gate 失败。详见
`records/stage4_p4_h5/calibration_summary.json`。

> 历史状态（现已被上方实测取代）：review v3 后的候选级 C0 曾阻止 p3/h5
> full3D，而 M80/M120/M160 与 augmented M160 安全运行。用户随后明确授权
> p3/h5 受控 direct，并以 7.781 GiB 完成，因此不得再把旧 C0 写成当前否决。
> p3/h3 与 adaptive 仍按用户范围延期；p4 只获准在 p3 条件满足后做候选级校准。

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
| swap | zero use for formal positive case | p3 pass；p4 calibration fail-closed | measured | p3 cgroup/host delta zero；p4 `pswpout` +4 pages |
| watchdog | warning/termination thresholds active | pass | measured | p3 completed；p4 controlled termination before factorization |
| concurrency | one large case at a time | pass | measured | serialized campaign runner |
| Phase C p3/h5 | user-authorized measured override + candidate watchdog | direct/Hybrid closure pass | measured | `full3d_closure_summary.json` |
| Phase C p4/h5 | p3 prerequisite + four-mode prerequisite + own resource Gate | prerequisites pass；target resource veto | measured + predicted negative | `calibration_summary.json` |
| p3/h3 | Review V5 explicitly not approved | not_run | scope gate | no launch now |
| adaptive | transferred to next task | not_run | scope transfer | new task must rebuild mesh/accuracy Gate |

## 3. Candidate decisions

| Candidate group | Prediction | Launch decision | Current status | 数据身份 | Evidence |
|---|---|---|---|---|---|
| pure 3D microfixtures | watchdog-qualified | launch complete | 144 PDE pass | measured | Case090 aggregate |
| QEP MPI1 matrix | watchdog-qualified | launch complete | 36/36 shards pass | measured | stage summary |
| Hybrid p1/h5 | watchdog-qualified | launch complete | funnel negative by modal capacity | measured | ignored campaign |
| Hybrid p1/h3 | watchdog-qualified | stopped by user scope | M80/M120 complete; M160 incomplete | measured + incomplete | stage summary |
| p3/h5 full3D direct | old centers 6.445 / 15.031 GiB；upper 18.038 GiB | user-authorized controlled override | `full3d_reference_pass`；7.781 GiB、zero cgroup/host swap delta | measured; old prediction superseded | full3D closure summary |
| p3/h5 Schur-minimal M80/120/160 | upper 6.011 GiB | serialized launch | three measured passes；2.278/2.492/2.641 GiB | measured | stage3 summary |
| p3/h5 augmented M160 | upper 10.123 GiB | launch after funnel | path-equivalence pass；4.148 GiB | measured | stage3 summary |
| p3/h5 Hybrid M160 closure rerun | p3 direct available | launch after reference | 16 Gate pass；2.618 GiB | measured | full3D closure summary |
| p4/h5 full3D | p3 condition met；own assembly unknown | assembly-only calibration | 12.616 GiB controlled stop；no factor/solve | measured negative | p4 calibration summary |
| p4/h5 Hybrid M160 | center 37.038 GiB；upper 42.594 GiB | do_not_launch | `not_run_by_memory_gate` | predicted negative | p4 calibration summary |
| p3/h10 full3D + Hybrid M120/M160 | 1.693/1.947 GiB planning center/upper | serialized launch complete | resource safe；equal-accuracy negative | measured | stage5 reduced summary |
| p3/h7.5 full3D + Hybrid M120/M160 | conditional after h10 accuracy fail | serialized launch complete | fixed-p equal-accuracy clear success with qualifications | measured | stage5 reduced summary |
| p3/h3、p4 target、adaptive/buffer | cancelled/resource-gated/transferred/deferred | do_not_launch | not_run | scope/resource decision | Review V6 |

p3 的旧预测否决和当前实测通过必须同时保留身份，但前者不能再冒充当前状态。
p4 停止原因是它自己的实测/预测资源 Gate，不是四模态组件失败，也不是未获准做
校准。p3/h3 已从当前范围取消，adaptive 已移交下一任务，buffer 等待 defect geometry。
这些原因不能混写，且 p3/h7.5 的安全运行不能反向许可 p4 factorization/solve。
