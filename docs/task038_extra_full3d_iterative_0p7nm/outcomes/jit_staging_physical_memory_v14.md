# V14 J5 cold-staged memory outcome

## 结论先行

这一轮把同一份物理 Maxwell 求解的冷启动编译、solver setup 和至少达到 checkpoint-1000 的求解过程放在同一个 parent watchdog 下测量。冷编译阶段和截至用户停止点的 live set 都低于 2 GB，但这不是完整 workflow PASS：用户在观察到 500 到 1000 步几乎没有下降后，于 checkpoint-1500 之前受控停止了唯一一次 J5 v3 formal。正式分类为 `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED`，不是 `PHYSICAL_NUMERICAL_FAIL_AT_FIXED_CAP`。

positive source 资格的通俗含义是：固定的 same-mesh p6→p3→p1 预条件器能在正定辅助算子上压低诊断误差；它不是含波动、Floquet 和 streaming Fourier-DtN 的真实散射求解。J5 才开始测量后者。

## 身份与冷启动范围

| 项目 | measured / fixed fact |
|---|---|
| source SHA | `ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| input | `/home/shenjh/Projects/MyFEniCSx_task37_extra/input/templates/full3d_iterative_example.dat`；SHA `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| physical model | SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode manifest | SHA `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| profile | p6/h10/13.5 nm/s/grazing1/phi0，MPI1，physical RHS |
| workflow | `j5-full`；right GMRES，restart 20，max_it 20000，replacement 20，solution-only checkpoint 500 |
| fresh root | `/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |

该 root 是本次唯一 formal 的 ignored artifact。冷 cache 由 parent 独占创建；七个 precompile child 按 `positive-p6 → positive-p3 → positive-p1 → dtn-surface → incident-rhs → physical-volume-curl → physical-volume-mass` 顺序完成，预编译 inventory 观测到 11 个 `.so`。没有预热或复用旧 cache。

## 截至停止点的实测资源

| 指标 | 实测值 | 解释 |
|---|---:|---|
| parent process samples | 334,915 | 覆盖冷 staging、setup 和 solver 到停止点 |
| raw JSONL | 1,020,808,306 B | 只保存在 ignored root，不追踪进 Git |
| raw JSONL SHA256 | `28c4044f3eebb72ca1991d1c71a67dd30637a7d550e798ffc7f536c28d969cf4` | stream hash |
| raw first → last timestamp | `1788206276386617381` → `1788228581099334131` | observed parent-process window `22304.712716750 s` |
| solve_started timestamp | `1788212103998569034` | solve-start 到 last raw sample `16477.100765097 s` |
| full staged peak RSS | 1,450,262,528 B | 仅到用户停止点的 measured pass-to-controlled-stop，不是完整 workflow PASS |
| max swap | 0 B | 全部样本为零 |
| RSS/status readable | `true` | 334,915 个样本均无 unreadable PID，RSS/status authority 完整 |
| PSS readability | `false` | 6 个 precompile 退出/zombie 瞬时样本缺 PSS；不能写成所有 PSS readable |
| max readable PSS | 1,419,618,304 B | 缺 PSS 的 6 个样本仍有完整 RSS/status |
| max compiler descendants | 2 | 发生在 precompile；solver 样本 compiler count 为 0 |
| last observed stage | `solver` | 最后 marker 为 `035_solve_started` |

资源峰值低于 2,000,000,000 B，只能说明停止之前的阶段没有触发资源硬线。它不能代替 solve-complete、release、recovery 或 official physics 的证据。

## 求解进展与 checkpoint

| checkpoint | iteration | explicit true residual | files | hashes |
|---|---:|---:|---|---|
| `checkpoint-500` | 500 | `0.48387099430079733` | `manifest.json` + `solution_rank0.npy` | manifest `cb38996f71c74929f164e43ea0919b54585b19c42a2b3cb5dc25d31db55fcbbf`；solution `bd9d0da6da45a90b60187cc24fc3c99ea888fbba44d8176a842b16f7ad598a2a` |
| `checkpoint-1000` | 1000 | `0.4837947981092168` | `manifest.json` + `solution_rank0.npy` | manifest `7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139`；solution `00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b` |

500 到 1000 步的 relative drop 为 `0.000157472120623114`，约 `0.01575%`。这只是停止决定所依据的 observed plateau，不是固定 20000 步 numerical Gate 失败。

最后一个有完整权威文件的 checkpoint 是 1000；checkpoint-1000 manifest 的 mtime 后 raw timeline 仍继续约 `3896 s`，但没有 checkpoint-1500。因此实际停止迭代数 unavailable，不能把 1000 写成 stop iteration，也不能从缺失的 worker/parent record 推算 per-cycle residual、matvec、PC apply、KSP destroy 或 driver elapsed。

## 生命周期边界与停止 authority

| 项目 | 事实 |
|---|---|
| marker boundary | 只有 V14 顺序中的 `000_parent_started` 到 `035_solve_started`，共 36 个 marker |
| absent markers | `solve_complete`、`solver_stack_release_*`、`recovery_*`、`official_outputs_written` 均没有发生 |
| records | `parent_record.json`、worker record 和 partial record 均不存在；worker stderr 为 0 B |
| user stop | parent PGID `160439` 收到一次 SIGTERM；随后 orphan worker PGID `161210` 收到一次 SIGTERM；`orted` PID/PGID `161211` 随 worker 消失；没有 SIGKILL |
| stability | 停止后 `parent_process.jsonl` 连续只读检查未增长；checkpoint-500/1000 保留 |

因此 J5 的 raw evidence 是用户控制停止点的生命周期/内存测量，不是完整 workflow 结果。J6 需要 J5 运行到固定 cap 且满足 long-tail eligibility；本次未满足。

## 证据入口与边界

紧凑记录见 [`j5_full_cold_staged_v3_controlled_stop_v14.json`](records/j5_full_cold_staged_v3_controlled_stop_v14.json)。完整 1.02 GB raw JSONL、cache、markers 和 checkpoint 继续留在上述 ignored root，不复制到 Git。

旧 V13 P0 的 `2,024,108,032 B` cold-setup hard stop、C1 四源 positive PASS 和 V11/V12 negative 都保持原样；本轮 J5 v3 不覆盖它们。J5 没有产生 E/H、R/T/A、`A_volume`、near-field 或 12+12 channels。
