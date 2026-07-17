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
