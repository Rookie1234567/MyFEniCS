# Task037b 测试汇总

## 已完成 Gate

| 阶段 | 命令/范围 | 结果 |
|---|---|---|
| H0 继承 focused suite | 12 个指定文件 | 76 passed / 1 skipped，225.86 s |
| H0 轻量重核 | test24 + test26 | 21 passed |
| H1-A implementation Gate | test181、test53 hash、test59、test79 | 40 passed |
| H1-A static | Ruff check、Ruff format-check、compileall、git diff --check | 全部 pass |
| H1 preflight | ABI、authority hash、pinned reference gate、parser/launch admission、资源/空 run-dir | pass |

所有测试均为本地结果，不表示 CI 结果。

## H1 首次 formal（3f72ef3）

H1 唯一 MPI8 formal 返回 1，并在生成解以前失败。分类是 failed_before_solve / controlled_stop / inherited correctness regression；不是 residual、R/T/A 或物理 Gate 的负结果。由于停止点早于最终 targeted Gate，H1 formal 后没有再运行 full pytest，也没有重跑 H1。

## H1 post-fix recovery（2990f357）

| 项目 | 结果 |
|---|---|
| post-fix formal return/status | 0 / measured_shard_pass |
| true residual | 1.4476013948489319e-12 |
| task.md §9 H1 numerical contract | pass；frozen-reference power/amplitude 12/12 + 12/12，Full3D pairwise 12/12 + 12/12 |
| post-fix targeted tests | 14 passed |
| H1-A targeted tests | 43 passed |
| Ruff check / format-check | pass |
| compileall / git diff --check | pass |
| early unified session | 12 dots、无 exit；infrastructure_indeterminate，不计入 pass/fail |
| full pytest / CI | 未运行 / 不声称 CI |

post-fix H1 只修复近简并分组与 partition audit 范数语义的窄回归，未放宽 `1e-6`、未加入 fallback/retry、未改变 ordinary defaults。上述 post-fix formal 与离线既有 comparator 证据均绑定 source `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc`。

## H0-H10 测试状态

| 阶段 | 状态 |
|---|---|
| H0 | pass |
| H1 | pass（post-fix；首次 failed_before_solve 历史保留） |
| H2a | pass；assembled-block MatPython action identity |
| H2b | pass；Matrix-free local endcap exact action identity |
| H3-H10 | not_run_yet；按阶段顺序等待 H3 |

## 运行边界

H1 recovery checkpoint 当时没有修改 H1 solver、没有放宽阈值、没有扫描 M/角度/p-h；随后完成 H2a 与 H2b code checkpoint。ignored artifacts 保留在本地证据目录，tracked docs 只保存路径和 SHA 引用。

## H2a assembled-block action identity

| 范围 | 结果 |
|---|---|
| focused test | `src/test/test_234_task037b_hybrid_block_operator.py` |
| MPI1 / MPI2 / MPI4 | 3 passed / 每 rank 3 passed / 每 rank 3 passed |
| existing direct minimal regression | 1 passed |
| action Gate | global 与 bottom/top/modal block relative error 全部 `<=1e-11` |
| layout / pack-split | missing/extra/duplicates `0/0/0`；三项 pack/split `0` |
| H3 | not_run；H3 第一次 outer FGMRES / exact block-LDU iterative oracle尚未运行 |

完整 H2a 逐 probe 数值与 H2b 汇总见 [block identity](block_operator_identity.md)。

## H2b Matrix-free local endcap exact action identity

| 范围 | 结果 |
|---|---|
| H2b-L MPI1 | `1 passed`；bottom action/recovery/RHS `3.058e-16 / 4.352e-16 / 0`，top `3.730e-16 / 4.297e-16 / 6.993e-17`；均通过 `1e-11` |
| H2a+H2b MPI1 | `5 passed`，6.04 s |
| H2a+H2b MPI2 | 每 rank `5 passed`，4.52 s |
| H2a+H2b MPI4 | 每 rank `5 passed`，9.11 s |
| 相关回归 test224/test230/test231 | `5 passed / 1 skipped`，5.89 s |
| static Gate | import、Ruff check/format-check、compileall、git diff --check 全部 pass |

H2b-G 每个 MPI 的七 probes、global/bottom/top/modal 四块合计最大 relative error
分别为 MPI1/MPI2/MPI4 的 `2.942e-16 / 2.988e-16 / 3.539e-16`，每行四块逐项均不
超过该行总体最大值，且均低于 `1e-11`；MPI1/2/4 的 pack/split bottom/top/modal
均为 `0`，mapping missing/extra/duplicates 均为 `0/0/0`。
H2b production 从构造开始使用 matrix-free local-Schur 与 matrix-free DtN action；
test-only oracle 才使用 explicit-condensed local blocks。H3 的 outer solve 尚未运行。
