# Task034 测试汇总（Review V2）

## 最终结论

Review V2 修改后的全仓 pytest、Task034 serial/native、文档契约、scoped Ruff 与 bytecode compile 均通过。本轮只修改离线聚合、资源模型、测试和报告，没有修改 Maxwell/Floquet/QEP/Hybrid 数值核心；因此按 Review 权威不重跑已经接受的 p3/h3、p4/h5 与 MPI 重型矩阵。

| 层级 | 命令/范围 | 结果 | 判定 |
|---|---|---:|---|
| Review V2 targeted | `test_85 + test_86` | 5 passed，0.79 s | pass |
| Task034 serial/native | `test_73 ... test_86` | 102 passed，3.92 s | pass |
| documentation contract | `test_26` | 13 passed，0.06 s | pass |
| Review V2 aggregation retest | `test_86` | 3 passed，0.81 s | pass |
| scoped Ruff | resource model、Review 聚合器及对应测试 | clean | pass |
| bytecode compile | 同上四个 Python 文件 | exit 0 | pass |
| full repository pytest | `python -m pytest -q` | 496 passed，18 skipped，243.68 s | pass |
| diff hygiene | `git diff --check` | clean | pass |

## Review V2 新覆盖

- `test_85_task034_resource_model_v2.py` 验证 largest component、local/modal subtotal、cumulative envelope 与 simultaneous peak 的语义分离；没有 overlap model 时禁止生成预测 peak。
- `test_86_task034_review_v2_aggregation.py` 验证 `all_model_results` 的 36 列 schema、40 行覆盖、S 入射与 `R00_p/T00_p` cross-polarized 输出语义、M/MPI 矩阵和三个补充 p/h 点的精确状态。
- 文档契约验证根 `AGENTS.md`、Task034 文档和 Markdown 结构。
- 全仓 pytest 覆盖 Task032/Task033 回归、Task034 Gate、Case093、adaptive、资源模型及统一聚合。

## 已接受重型证据边界

本轮没有重跑下列已接受证据：

- p3/h3、p4/h5 Full3D/Hybrid 主矩阵；
- p3/h5 Full3D 与 Hybrid MPI1/8/16，及 MPI32 exploratory；
- P polarization 的完整矩阵。

原因是 Review V2 没有修改 Maxwell/Floquet/QEP/Hybrid 数值核心。S polarization 仍是正式生产主线；既有 p2/h5 P capability sample 只证明 P 路径可执行，不参与 S 主线收敛结论。

## Ruff 边界

本轮 Review V2 scoped Ruff 为 clean。Review V1 已记录的全仓 Ruff 15 项历史问题仍位于未由 Task034 修改的五个旧文件；本轮未扩大范围修复，也未将该历史全仓状态改写为 clean。
