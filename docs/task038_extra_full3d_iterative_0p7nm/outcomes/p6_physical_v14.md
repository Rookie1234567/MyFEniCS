# V14 J5 p6/h10 physical Maxwell outcome

## 最终分类

`CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED`

这是一次真实的 p6/h10、13.5 nm、MPI1 physical Maxwell workflow。最后一个有完整权威文件的 checkpoint 是 1000；其后 raw timeline 仍继续约 `3896 s`，并在 checkpoint-1500 出现前由用户受控停止。实际停止迭代数 unavailable，所以不能把 1000 写成 stop iteration，也不能分类为 `PHYSICAL_NUMERICAL_FAIL_AT_FIXED_CAP`；同时没有完成完整 workflow memory PASS。

## 固定身份

| 项目 | 值 |
|---|---|
| source SHA | `ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |
| input SHA | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| physical model SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| mode manifest SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| profile / method | p6/h10/13.5 nm/s/grazing1/phi0；exact split matrix-free Maxwell volume、streaming Fourier-DtN、`same_mesh_hcurl_pmg_v1_requalified` |
| raw root | `/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |

## J5 measured facts

| 项目 | measured fact |
|---|---|
| cold staging | 七个 precompile child 顺序完成；11 个预编译 `.so`；solver 随后启动 |
| samples / raw | 334,915 samples；1,020,808,306 B；SHA `28c4044f3eebb72ca1991d1c71a67dd30637a7d550e798ffc7f536c28d969cf4` |
| process-tree | peak RSS `1,450,262,528 B`；swap `0 B`；RSS/status 全部 readable；PSS 有 6 个 precompile 退出/zombie 瞬时样本不可读；solver compiler descendants `0` |
| marker | 只到 `035_solve_started`；无 `solve_complete`、release、recovery 或 official marker |
| record | parent/worker record absent；partial record absent；worker stderr `0 B` |
| checkpoint-500 | iteration 500；explicit true residual `0.48387099430079733`；solution-only |
| checkpoint-1000 | iteration 1000；explicit true residual `0.4837947981092168`；solution-only |
| observed drop | 500→1000 relative drop `0.000157472120623114`（约 `0.01575%`） |

两个 checkpoint 的 `manifest.json` 与 `solution_rank0.npy` 都完整保留，逐文件 hash 见 [`jit_staging_physical_memory_v14.md`](jit_staging_physical_memory_v14.md) 和 [`records/j5_full_cold_staged_v3_controlled_stop_v14.json`](records/j5_full_cold_staged_v3_controlled_stop_v14.json)。

raw first/last timestamp 为 `1788206276386617381` / `1788228581099334131`，观察窗口 `22304.712716750 s`；`solve_started` 为 `1788212103998569034`，到最后 raw sample 为 `16477.100765097 s`。由于 worker/parent/partial record 均不存在，per-cycle residual history、actual stop iteration、matvec/PC/KSP destroy 计数和 driver elapsed_seconds 都 unavailable，不从代码公式猜测。

## 未运行项

| 项目 | 状态 |
|---|---|
| checkpoint-1500 及 2000/5000/10000/15000/20000 boundaries | `not_run_by_user_controlled_stop`；checkpoint-1500 不存在 |
| final explicit residual / solve-complete | `not_run` |
| J6 | `not_run_by_J5_eligibility`；未到 20000 步，不满足 long-tail 前置条件 |
| J7/J8 | `locked/not_run` |
| official complex E/H、near-field | `not_run` |
| R/T/A、`A_volume`、energy closure | `not_run` |
| 同一 12 个 significant identities 的 12 power + 12 complex boundary-amplitude | `not_run` |

当前 direct authority 仍只有 scalar `R/T/A/A_volume`，缺 E/H 与 12+12 raw arrays；这是下游 comparison blocker，但不是本次停止原因，因为 J5 在 setup/solve 中途即被用户停止。

## 解释边界

`same_mesh_hcurl_pmg_v1_requalified` 的四类 C1 positive qualification 保留。它说明正定辅助预条件器资格成立，不足以宣称 standalone physical Maxwell production qualification；V14 J5 的 controlled stop 关闭了这一 physical production claim。旧 V13 P0 的 `2,024,108,032 B` resource hard stop、V11/V12 negative 和 J5 v1/v2 execution negatives 均不被覆盖或重分类。
