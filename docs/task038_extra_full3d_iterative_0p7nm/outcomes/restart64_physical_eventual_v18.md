# V18 eventual restart64 physical continuation：用户授权受控停止

## 当前 authority

本文件记录 V18 E1 的唯一一次 fresh-cold artifact-root checkpoint continuation。它从已经通过 E0 authority
preflight 的 p6/h10 checkpoint-2024 继续使用同一个 physical Maxwell operator、
physical RHS、positive pMG 和 right FGMRES(restart=64)。用户在看到真实残差下降速度后
授权停止：继续到 `1e-6` 预计需要数日，已不具备实用性。这个停止分类为
`USER_AUTHORIZED_PERFORMANCE_CONTROLLED_STOP`，不是 numerical Gate fail，也不是
resource Gate fail。

受控停止发生在 runner 写入最终 parent/worker closeout 之前。原始 timeline、JIT child
记录、probe、restore raw 和 solution checkpoint 均保留；没有伪造 parent record、worker
record、checker 或 completion。

| 项目 | 结果 | 证据口径 |
|---|---|---|
| source SHA | `284c39514e257a01cda2407e1a8baf0c38099116` | measured identity |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` | measured identity |
| phase | E1 checkpoint continuation，MPI1 | measured |
| latest preserved checkpoint | absolute `3048`，total-additional `2048` | raw manifest；这是 `3048 − 1000` 的累计值，不是 E1-local 步数 |
| E1 local progress proven | 至少 `1024` steps | `3048 − 2024`；TERM 时最终 local iteration unknown |
| latest explicit true residual | `0.15346927855972448` | raw checkpoint manifest |
| success `<=1e-6` | not reached / not run to completion | controlled stop |
| two complete 4096-block stagnation stop | not run | controlled stop before that decision |
| E2 fresh / E3 recovery | locked / not_run | E1 did not complete |

## E1 的实际范围与生命周期

固定的 checkpoint origin 是 absolute iteration 1000；E1 恢复点是 absolute 2024，因而
solver 内部从 local/additional `0` 继续，证据层使用
`absolute = 1000 + total_additional`。restart/cycle=64，最大 total-additional
为 32768，每 1024 个 total-additional 保存 solution-only checkpoint。E1 的 solver 从
restore absolute `2024` 的 local/additional `0` 开始，停止前写出 absolute `3048`，
因此只能证明至少 `1024` 个 E1-local steps。`total-additional=2048` 是相对原始
absolute `1000` 的累计坐标，不是本阶段步数；TERM 的最终 absolute/local iteration
未知。没有把该 checkpoint 误写成成功或最终解。

已观察到的 runner marker 顺序是：

```text
paths_ready -> abi_ready -> case_built -> checkpoint_restored
```

`e1_complete`、`record_written` 和 `release_complete` 尚未由 runner 写出，
因为用户授权的 TERM 发生在 worker/parent closeout 前。随后单独写入的
`user_controlled_stop.json` 不是 runner 阶段 marker，而是终止审计证据；它记录了
parent PID 639395、mpiexec PID 639992、worker PID 639995，向 PGID 639367 和 639992
发出 SIGTERM，并以相隔 3 秒的两次空采样确认没有 orphan process。

冷 staging 的 7 个既有 JIT child 记录均已落盘，顺序为
`positive-p6`、`positive-p3`、`positive-p1`、`dtn-surface`、`incident-rhs`、
`physical-volume-curl`、`physical-volume-mass`。E0 checkpoint preflight 已在 case
build 前通过；它绑定旧 V18 checkpoint manifest/solution 的完整 SHA。E1 的 worker
record 尚未形成，所以每周期的 matvec、PC、KSP destroy 和完整 residual history
不能从本 root 合法恢复，也不在此文档中猜测。

本轮身份也与 raw authority 绑定：template/input SHA 为
`819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` /
`754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f`，physical-model
SHA 为 `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`，operator
identity SHA 为 `bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3`；
mode manifest SHA 为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。
这些值由 case-built/E0 raw 与冻结 V18 输入 authority 交叉绑定，完整值也保留在
compact record 中。

## checkpoint 与残差事实

E0 使用的冻结 authority 是旧 V18 `solution-2024`：manifest SHA
`267a933e1f85cd8685efcfc14a2fc8a50b352d6573a19e9781655c19d3f0be31`，solution SHA
`5ab1ec46b588e1a1c38945ceaf5d41b61f066785ff08ccdd493735a01b45ee79`。它的已知显式
true residual 为 `0.27299642739429014`。当前 E1 最新 solution-only checkpoint
`raw/e1/solution_checkpoints/solution-3048` 的 manifest 记录显式 true residual
`0.15346927855972448`，即真实下降，但距离 `1e-6` 仍很远。

E0 的 residual reproduction 另外从 raw 数组独立重算，而非读取 checkpoint 自报值：
`norm(raw/restore/residual.npy) / norm(raw/same_start/rhs.npy) =
0.2729964273942887`，冻结 expected 为 `0.27299642739429014`，absolute difference 为
`1.4432899320127035e-15`，relative difference 为 `5.286845493872169e-15`，满足
`relative <= 1e-11`，因此 E0 reproduction 为 `PASS`。输入数组路径与 SHA 分别是
`raw/same_start/rhs.npy`
(`02b86d9226303bf9b8ae2ee0d28cfef6ed374b3fdf7e637c29b52efa3c14445a`) 与
`raw/restore/residual.npy`
(`b0d5786b6a16ce99bc93ee588f34b705449751845877cfaa37e286ed07078d89`)。

| 量 | 值 | 状态 |
|---|---:|---|
| restore starting residual | `0.27299642739429014` | measured from frozen prior V18 authority |
| latest absolute iteration | `3048` | measured raw manifest |
| latest total-additional | `2048` | derived: `3048 − 1000`；不是 E1-local count |
| E1-local steps proven | `>=1024` | derived: `3048 − 2024`；TERM final iteration unknown |
| latest checkpoint residual | `0.15346927855972448` | measured raw manifest |
| final residual / total iterations / counts | unavailable | worker closeout not written |
| full cycle history | unavailable | not written before controlled stop |

当前保存的 action probe 与 PC probe 都是有限的，重复相对误差分别为 `0.0` 和 `0.0`。
这些 probe 证明可重复性，但不替代 E1 的 full explicit true-residual Gate；owned-slave
和每周期 operation ledger 因 worker record 缺失而标为 unavailable。

## 资源和 checker 边界

`parent_process.jsonl` 共 350,329 条样本，完整 timeline SHA 为
`744ac1407fd9ca097411a7e44eee2d5eac4de5dbae3196620acbeda2959712c7`。其中 process-tree
RSS 最大值为 `1,466,142,720 B`，swap 最大值为 `0 B`，状态全部可读；这低于严格的
`2,000,000,000 B` RSS 线。该峰值是 timeline 的实测 process-tree 峰值，不是
“已经完成正确求解”的证明；没有 parent closeout，不能把它改写成正式 checker PASS。

| 资源/生命周期项 | 结果 |
|---|---|
| process-tree RSS | measured peak `1,466,142,720 B`，资源线未触发 |
| swap | measured max `0 B` |
| compiler descendants at last sample | `0` |
| timeline readability | `all_status_readable=true` |
| RSS 随迭代不增长的完整趋势 | not established；没有完整 worker record |
| parent/worker/checker/completion | 未在 TERM 前写出 |
| post-TERM process groups | 两次间隔采样均为空 |

timeline 的首末 `timestamp_ns` 差为 `23,208.841428983 s`；从
`002_case_built.json` 的时间戳到 timeline 最后一条记录差为 `17,271.760272149 s`。
这两个数都是由 raw 时间戳推导的观察边界，不是完整 solver wall time，也不表示
worker closeout 已完成。

独立 checker 没有运行。它要求 hash-bound `parent_record.json`，而该文件在用户授权
终止时尚未写出；运行一个无输入 checker 只会制造无意义的 infrastructure error。因此
本轮没有创建 `checker.json`，也没有把“缺少 closeout”错误重分类为数值负结果。

## 与 V17/V18 已有结果的关系

| 方法 | 实际对象 | 结果 |
|---|---|---|
| V17 GMRES(20) | checkpoint-1000，500 additional | `0.48362582271206495` |
| V17 disk-backed unrestarted FGMRES | 同一 checkpoint，500 additional | `0.19374101288500692`，ratio `0.4006010510326989`，WEAK signal |
| V18 restart64 screen | 同一 physical case，1024 additional | `V18_RESTART64_NUMERICAL_GATE_FAIL`，旧 immutable outcome |
| V18 E1 eventual continuation | checkpoint-2024 onward | residual 到 absolute 3048 为 `0.15346927855972448`，用户 performance stop |

E1 没有改变 V17/V18 的 solver、PC、物理、checkpoint、restart 或阈值，也没有完成
official complex E/H、near-field、R/T/A、recovery 或 0.7 nm/2 TiB scalable solve。
用户停止只说明这条路线的实际完成时间不具实用性；它不证明数学不可能，也不产生新的
PC 资格。

## Provenance / raw index

compact record：
[restart64_physical_eventual_v18.json](records/restart64_physical_eventual_v18.json)

| root-relative evidence | SHA-256 |
|---|---|
| `user_controlled_stop.json` | `9e6ed6e5b1b7300a5e4e113cbd6e917281e2020431be786c598344089a7653fa` |
| `e0_checkpoint_preflight.json` | `d4802a3a00832c19ae807fa9438cda8212ba5f218ee5be8261779547d3e97db7` |
| `parent_process.jsonl` | `744ac1407fd9ca097411a7e44eee2d5eac4de5dbae3196620acbeda2959712c7` |
| `raw/e1/solution_checkpoints/solution-3048/manifest.json` | `3359f5d36f1784967a32fee90caaca6a8040587be74dc054b2e39387ef8b7ae8` |
| `raw/e1/solution_checkpoints/solution-3048/solution_rank0.npy` | `486171fe0634f30ed55e1c5eccf63597fa3fdfc451240c855b9e84b3444b5ce7` |
| `raw/probes/action_first.npy` / `action_second.npy` | `456ffd483ebc5b178b28d5f95f352b4c66e4ff517f8b6c2cbe9b9dbb83c2d96b` |
| `raw/probes/pc_first.npy` / `pc_second.npy` | `49d29b14c878f2af9be16263c926e90135f2064f6879391a7cfc286af4a14adc` |
| `raw/restore/action.npy` | `456ffd483ebc5b178b28d5f95f352b4c66e4ff517f8b6c2cbe9b9dbb83c2d96b` |
| `raw/restore/residual.npy` | `b0d5786b6a16ce99bc93ee588f34b705449751845877cfaa37e286ed07078d89` |
| `raw/same_start/initial_solution.npy` | `5ab1ec46b588e1a1c38945ceaf5d41b61f066785ff08ccdd493735a01b45ee79` |
| `raw/same_start/rhs.npy` | `02b86d9226303bf9b8ae2ee0d28cfef6ed374b3fdf7e637c29b52efa3c14445a` |

所有 JIT child JSON 的路径和 SHA 也记录在 compact JSON；完整生成 C/cache 与
`parent_process.jsonl` 保持在 ignored artifact root，不复制进 Git。

## E4/E5 decision

E1 没有完成 `<=1e-6`，但也没有触发 numerical/resource Gate；它由用户以性能理由
受控停止。依照 Review V18，E2 fresh zero-start 和 E3 release-before-recovery 均
锁定/未运行，不启动其他 restart、Krylov、FBCGS、PML、Robin、Schwarz 或新的 PC
family。下一步若要继续，必须先由新的 review 明确授权；本轮不把任何 future
architecture 写成已实现或已通过。
