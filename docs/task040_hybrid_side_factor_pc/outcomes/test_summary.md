# Task040 测试与证据检查

以下是 T40-13 closeout 使用的实际结果；历史通过项与本轮 checker 结果分开记录。

| 检查 | 结果 |
|---|---|
| test297 serial | 8/8 passed（此前已绑定，core 未变） |
| test297 MPI2 | 8/8 passed（此前已绑定，core 未变） |
| test297 MPI4 | 8/8 passed（此前已绑定，core 未变） |
| test298 watchdog/runner | 3 passed after package-invocation repair |
| test299 raw checker tamper regression | 1 passed；hash-valid status/gate 篡改不改变重算结论 |
| formal raw checker | executed；`gate_pass=false`，五个 rho Gate 真实失败 |
| Ruff / format / compileall / git diff --check | passed for the recorded implementation/checker stages |
| check_benchmarks --no-write | 302/302 passed |
| full repository pytest | not_run |

test299 的负对照先修改 worker raw，再在 hash-valid 场景同步 watchdog hash；若不更新
hash，watchdog check 会先失败。这证明 checker 不是单纯相信 worker 的 status/gate 字段。
