# Task033 阶段测试摘要

## 1. 源码冻结前验证

正式计算源码 `6613f94b91ebc77eb50e74086475c67df46236f6` 在 campaign 前完成：

| 验证 | 结果 |
|---|---|
| Task33 host pure group | 131 passed, 5 skipped |
| final focused group | 57 passed, 1 skipped |
| Docker DOLFINx test53 + test55 | 12 passed, 10 subtests |
| MPI2 smoke + graded materialization | 每 rank 2 passed, 4 subtests |
| Ruff / compileall | pass |
| PowerShell formal runner parser | pass |
| planning checker | pass |

## 2. 阶段文档收口验证

| 命令/检查 | 结果 |
|---|---|
| `python -m pytest -q test_24 test_44 test_45 test_61` | 39 passed |
| `python -m benchmarks.check_task033 --repo-root .` | planning mode `evidence_verified` |
| `python -m json.tool .../stage_summary.json` | pass |
| `git diff --check` | pass |

本轮没有为文档收口重跑 PDE。host 环境缺少 `basix`/`petsc4py`，因此尝试收集
test46/test50 时在 import 阶段停止；这不是代码回归，DOLFINx 相关测试使用冻结源码前的
Docker 验证结果。

planning checker 继续报告 planner/完整 formal manifest 为 `not_run` 是正确的：
本阶段新增的是独立 stage summary，没有伪造原任务书的 21-role formal closure。

## 3. Review Phase A 验证

| 验证 | 结果 |
|---|---|
| Ruff：QEP tracking + watchdog reuse files | pass |
| host focused Task33 tests | 41 passed，1 skipped |
| watchdog/Case090 reuse focused tests | 29 passed，1 skipped |
| DOLFINx Task032 p2 QEP/mode regression | 13 passed |
| p3/h3 MPI2 positive watchdog | formal pass，no swap |
| p3/h3 MPI4 positive watchdog | formal pass，no swap |
| p4/h3 MPI2 positive watchdog | formal pass，no swap |
| p4/h3 MPI4 positive watchdog | formal pass，no swap |
| p3/p4 MPI1→MPI2/4 maximum beta drift | `2.14815e-12` |
| p3/p4 MPI1→MPI2/4 minimum Fourier overlap | `0.615322` |

host 环境直接导入 Task032 DOLFINx tests 会缺少 `dolfinx/ufl`；相同 13 个测试已在正式
`myfenics-stage4:task28` 环境运行通过。该 host import failure 是环境边界，不是回归失败。

## 4. Phase B matching-interface 验证

| 验证 | 结果 |
|---|---|
| `python -m unittest -v src.test.test_66_task033_matched_trace_qualification` | 4 passed |
| Phase B runner p2/MPI1 dirty-source smoke | 数值 Gate 全过；仅 source identity 按预期 fail |
| Docker MPI4 `test_52_task033_high_order_matched_trace` | 每 rank 1 passed；p1–p4 subtests 全过 |
| Docker MPI1 `test_35` + `test_53` | 6 passed；默认 projection 与 p3/p4 sparse Hybrid blocks 无回归 |
| Ruff：runner、qualification、projection、test66 | pass |
| py_compile：runner、qualification、projection、test66 | pass |
| 正式 p2 MPI1 | pass；无 failed check |
| 正式 p3 MPI1 / MPI4 | pass / pass；无 failed check |
| 正式 p4 MPI1 / MPI4 | pass / pass；无 failed check |
| 独立 Phase B aggregate | `phaseB_p3_p4_matched_trace_pass` |
| `git diff --check` | pass |

四个纯 Python 负向合同测试包括：

1. 五条零误差基准通过；
2. p4 MPI identity 失败时 p3 不被阻塞；
3. p4 shard 数值失败时 p4 独立 fail-closed、p3 仍可通过；
4. 任意 full-mode gather 声明会被复算拒绝。

正式五条记录全部绑定 source
`bd7a6023bde7a7c06d456e702af4b7f9f047b3fc`，并记录
`source_clean_verified=true`、`source_stable_during_run=true`。聚合器绑定 clean source
`9ac29db45b387d4590de084710abe2cc38b25ffe`，没有重跑 Case090、QEP36 或目标 Hybrid。
