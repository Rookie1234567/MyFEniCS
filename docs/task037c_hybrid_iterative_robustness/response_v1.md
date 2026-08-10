# Task037c R7 Response：robustness negative closeout

## 回应审查范围

本 response 对应 Task37c task.md §8 的 R7。closeout 本身只新增/修改六份 Markdown；另有
独立 test-only contract commit `12a12647f89f1b0b4f6deb080046510b8e53821a`，仅登记 Case102
空 records。没有修改 solver、runner、watchdog、checker、threshold、config 或 ordinary
default，也没有删除/覆盖任何 ignored artifact。

## 最终状态

| 事项 | 状态 | 证据 |
|---|---|---|
| numerical code/config parent | `65556637dd10f2de674a800d575983f24336c9d3`，clean | branch/source records |
| test-only Case102 contract | `12a12647f89f1b0b4f6deb080046510b8e53821a` | 空 records 登记；不改变数值代码/config |
| R2 Full3D direct | 三个 phi 全部通过 | `outcomes/summary.md`、R2 records |
| R3 Hybrid direct | 六个有效 M120/M160 全部 own pass | `outcomes/summary.md` |
| full repository pytest | `940 passed, 48 skipped, 0 failed`，exit `0`，`1336.24s` | tested HEAD `12a12647f89f1b0b4f6deb080046510b8e53821a`；日志 SHA `b0c7b108c9f56dadc50818a6bfad12892cd9c9787838bdfcf4eb133f75baa32a` |
| M120-vs-M160 | 三个 phi 全部通过 | `three_way_comparison.md` |
| Hybrid-vs-Full3D | phi=0通过；±5°显著 power Gate失败 | `three_way_comparison.md` |
| M_robust | `not_established` | selection SHA `2d7861...` |
| R4/R5/R6 formal | `not_run_by_gate` | task gate |
| allowed diagnostics | -5/+5 M160 solver-vs-direct，均 linear negative | `summary.md` |
| ordinary defaults | unchanged | source audit / records |

## 诊断语义

两份 iterative diagnostic 的 comparator 输出是 controlled load failure：因为 online record
已经明确 `online_pass=false`，离线比较器没有假装比较 traction、recovery、RTA、orders、
canonical、selected E/H 或 modal magnitude。它们应读作 `not_run_due_linear_gate`，不是
“与 direct 比较失败”。

modal residual 约 `1e-15`，而 global/bottom/top FEM residual 仍约 `1e-5`--`1e-4`；这支持
“fixed endcap/FEM preconditioned convergence 在 1° 非零方位角下未达资格”的解释。不能据此
宣称 solver 有代码 bug，也不能通过 derived iteration extrapolation 改写 `max_it=1600`。

## 交付边界

本轮不把 best available discrete result 写成 continuum convergence，不把 Full3D direct 的
大内存峰值混称为 Hybrid iterative 资源，不把 MPI1 not_run 写成估算值，不添加 M200、新 PC、
P 偏振、更多角度、Task036 或 0.7 nm 结果。后续若继续，必须由新的 review 明确重新打开
相应 numerical stage。

## R7 Gate 记录

测试和静态检查均在 qualified activation 下完成：Task37c focused 集合为 `65 passed in
3.67s`；repository documentation/Markdown contract 集合为 `27 passed in 0.17s`；实际 15
个 Task37c touched Python 文件的 Ruff check 与 Ruff format check 通过；
`python -m compileall -q src benchmarks` 与 `git diff --check` 通过。

完整 pytest 只运行一次，命令为 qualified shell 中的 `python -m pytest -q`，tested HEAD 为
`12a12647f89f1b0b4f6deb080046510b8e53821a`，exit code 为 `0`，结果为 `940 passed, 48
skipped, 0 failed`，报告用时 `1336.24s`。日志位于
`/tmp/task037c_r7_full_pytest_12a1264.log`，大小 1165 bytes，SHA256 为
`b0c7b108c9f56dadc50818a6bfad12892cd9c9787838bdfcf4eb133f75baa32a`；命令自然结束，没有
rerun 或 PDE。上述 tested HEAD 是 test-only Case102 contract commit；本 response 不把未来
R7 docs commit 的 SHA 写入自身证据。
