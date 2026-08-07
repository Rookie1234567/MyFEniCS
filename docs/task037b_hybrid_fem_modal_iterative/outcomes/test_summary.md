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
| H2-H10 | not_run_yet |

## 运行边界

本轮没有修改 solver、没有放宽阈值、没有扫描 M/角度/p-h，也没有进入 H2-H10。ignored artifacts 保留在本地证据目录，tracked docs 只保存路径和 SHA 引用。
