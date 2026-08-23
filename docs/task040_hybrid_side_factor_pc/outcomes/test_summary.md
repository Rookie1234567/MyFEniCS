# Task040 测试与证据检查

本页区分已绑定的实现/focused Gate、V1-8 文档合同检查和正式 Run B。没有把缺少
`worker/run_summary.json` 的资源停止伪装成 checker 数值通过。

| 检查 | 结果 |
|---|---|
| test297 serial/MPI2/MPI4 | 各 `8/8 passed`；由未变更的 solver/core commit 绑定 |
| test298 watchdog/runner | `3 passed after package-invocation repair` |
| test299 raw checker tamper regression | `1 passed`；hash-valid status/gate 篡改不改变重算结论 |
| test300 Petrov / test302 core / test303 checker | 实现阶段通过 serial/MPI2/MPI4 focused selectors；详见对应提交审计 |
| V1-2 formal checker | attempted；因 resource stop 前没有 `worker/run_summary.json`，不能完成 numeric recomputation |
| raw watchdog resource audit | completed from `watchdog_summary.json`、markers 和 process samples；hard stop/peak/swap/process-group exit 可复核 |
| JSON parse | passed for compact record and frozen probe manifest |
| Markdown links / math delimiters | passed；无缺失相对链接、无双美元数学分隔符 |
| compileall | passed in qualified environment |
| git diff --check | passed |
| check_benchmarks --no-write | `302/302 passed` |
| Ruff / format | implementation stages passed；本轮仅修改 Markdown/JSON |
| full repository pytest | `not_run` |
| new PDE/QEP/heavy | `not_run` |

V1-2 Run B 的独立 checker 命令为：

```text
python -m benchmarks.check_task040_v1_run_b --run-root results/task040_v1_2_v1_3_run_b_mpi8_16ecba56
```

它因 `worker/run_summary.json` 不存在而不能完成完整 checker schema；这与 watchdog 的
resource hard stop 一致。compact record 只记录 raw watchdog/marker/process evidence 和
该 checker blocker，不伪造 V1-2/V1-3 numerical Gate。

## V2-A1 producer 与 checker-fix

| 检查 | 结果 |
|---|---|
| producer formal | 已完成一次；source `942c43881e4162085348c48b09c79fbbdac18cd9`，未重跑 |
| 首次 checker | implementation schema failure；physical report 缺少 `finite` marker，producer raw 保留 |
| checker 修复 | commit `bd70ab98009de2a2b45561793be6418a6a9bfcc8`；改为从真实 physical schema 的显式数值字段重算 finite；未放宽任何数值阈值/Gate |
| test306 serial / MPI2 / MPI4 | 各 `6/6 passed` |
| fresh independent checker | `rc=0`；packet_complete 与全部 checks 通过 |
| packet | 34 files / 653,804,117 B；24 owner-row shards |
| resource | peak `28.706954956054688 GiB`，preferred `<=45 GiB` pass，swap `0`，55 GiB 未触发 |
| V2-B consumer / PDE / QEP / FGMRES | `pending / not_run / not_run / not_run` |

fresh checker 读取原 packet，不修改 producer 数值 artifact；输出为
`checker_recomputed_after_fix.json`，首次空的 `checker_recomputed.json` 仍作为失败现场保留。
本阶段没有把 checker schema 修复误写成 producer 或算法负结果。
