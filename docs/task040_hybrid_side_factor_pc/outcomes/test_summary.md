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
| V2-B2 consumer formal | source `40b25d3281d9ce1707f6069607bfdbbf6a3ab48d`；resource/remap/one-apply implementation subset通过；FGMRES 数值负，分类 `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` |
| V2-B2 formal process wall | `1077.3351624270435 s`；producer component wall `1202.5501016210765 s`，两者不相加为 full workflow time |
| V2-B2 immutable checker | `rc=2`；expected numerical negative，resource/identity/lifecycle 独立重算通过；原始 watchdog teardown false 未覆盖 |
| V2-C/D/E/F | `not_run_by_gate` |

fresh checker 读取原 packet，不修改 producer 数值 artifact；输出为
`checker_recomputed_after_fix.json`，首次空的 `checker_recomputed.json` 仍作为失败现场保留。
本阶段没有把 checker schema 修复误写成 producer 或算法负结果。

## V2-B2 与 V2-G 轻量检查

| 命令/检查 | 实际结果 |
|---|---|
| qualified JSON parse（consumer compact + frozen probe manifest） | `passed`，2 files |
| 变更 Markdown 链接/双美元数学分隔符检查 | `passed`，13 files |
| `python -m pytest -q src/test/test_183_development_model_registry_markdown.py` | `5 passed` |
| `python -m benchmarks.check_benchmarks --no-write` | `302/302 passed` |
| immutable consumer checker（formal root + packet，expected source `40b25d328...`） | `rc=2`；resource pass，数值分类 `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` |
| `git diff --check` | `passed` |

仓库通用 `src/test/test_26_documentation_contract.py` 同时报告 `18 passed, 1 failed`；唯一
失败是其既有 numbered-case 白名单未包含已经存在的 `104_5nm_hybrid_side_factor_pc`
目录，不是本轮 Markdown/JSON 内容失败。本轮不改测试/代码，因此该基线问题单独保留。
代码 focused 20 tests、Ruff、format、compileall 沿用同一
`0919ed2fa3bd1541f543057721fff84fa110f3d4` 的已通过结果；文档改动没有触发重复
heavy/MPI/PDE。
