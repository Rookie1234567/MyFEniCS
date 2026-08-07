# Task037 V7 测试汇总

## 结果

| 测试层 | 命令/范围 | 结果 |
|---|---|---|
| serial targeted | V7 selective positive suite | `85 passed / 7 skipped` |
| MPI2 targeted | MatPython、DtN、canonical、slab、Hybrid safety | 每 rank `58 passed / 2 skipped` |
| MPI4 targeted | DtN action/recovery 与 owner-local support | 每 rank `9 passed / 1 skipped` |
| explicit smoke | assembled FGMRES tiny；action-only DtN tiny | 各 `1 passed` |
| telemetry patch | final serial / MPI2 slices | serial `8 passed`；MPI2 每 rank `1 passed` |
| E0 formal | MPI1 Matrix-free DtN component | pass，80/80 |
| M3a formal | MPI4 final-source full solve | pass，official result true |
| canonical comparator | active/full | 两组 pass，missing/extra/duplicate 全为 0 |

## Full repository pytest 的真实边界

在最终数值源码 `0fcf08a3f09e3beb137212d41f411823cb2e24e8` 上，完整仓库测试只
运行过一次：

| 字段 | 值 |
|---|---|
| exit | `1` |
| passed | `849` |
| skipped | `48` |
| failed | `3` |
| duration | `1115.51s` |
| 再次 full pytest | `not_run` |

三项失败的最小闭环如下：

| 文件 | 原因 | 后续结果 |
|---|---|---|
| test53 | `interface_quadrature_degree` 陈旧地期待 `2*degree+4`；reviewed contract 是 coefficient degree=`degree`、总 degree=`3*degree+4` | 只替换两条断言；最终格式化后 `3 passed/223.86s` |
| test69 | 5 个历史 Git commit 对象缺失 | 从已确认的本地对象库补入；test69 源码不改，`3 passed/0.25s` |
| 其余 production | 无触及数值源码的已知失败 | 不重跑 full suite |

因此最终文档使用“targeted closure 后无已知剩余 failure”，而不是把原始 full
pytest exit=1 改写为全仓库 PASS。

## 静态与文档合同

| 检查 | 结果 |
|---|---|
| authority task/review/v7.1 byte identity | PASS |
| 5 compact records JSON parse | PASS |
| Case100 records exact set | PASS |
| Markdown relative links | PASS |
| math fences | PASS；仅使用 GFM `math` fenced blocks |
| test26 Ruff check | PASS |
| test26 format-check | PASS；6 个历史 hunk 的机械格式收口，AST 不变 |
| test26 compileall | PASS |
| test26 focused pytest | `14 passed / 0.13s` |

此前 6 个 inherited formatter hunks 已按 V7 机械收口，AST 前后不变，最终 whole-file
check PASS；本轮新增合同代码也通过 Ruff、compileall 和 focused pytest。

## 身份

- reviewed source：`d8b16c349f7726b4873ce1932668c12a1ba78926`
- V7 review commit：`229aaf743072550fa07bb0f03f9c4104e6a25d63`
- V7.1 handoff commit：`d8b16c349f7726b4873ce1932668c12a1ba78926`
- final-source numerical formal：`0fcf08a3f09e3beb137212d41f411823cb2e24e8`

本 docs commit 形成时 Task37b 尚未创建；只有 master 成功 push 后才按 V7.1 创建并
push，且不开发。A–F/E negative test 与 raw artifact 不进入 Case100。详见
[summary](summary.md) 与 [response_v7](../response_v7.md)。
