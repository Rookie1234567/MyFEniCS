# Task034 测试汇总（Review V3）

## 最终结论

Review V3 修改后的 targeted tests、Task034 suite、文档合同、scoped Ruff、bytecode compile 与正确复数 PETSc ABI 下的全仓 pytest 均通过。本轮只修改离线聚合、机器可读结果、selective-merge 边界、测试和报告，没有修改 Maxwell/Floquet/QEP/Hybrid 数值核心；因此按 Review 权威没有重跑已接受的 p3/h3、p4/h5 与 MPI 重型矩阵。

| 层级 | 命令/范围 | 结果 | 判定 |
|---|---|---:|---|
| Review V3 targeted | test82–test86 | 20 passed，1.95 s | pass |
| Task034 serial/native | test73–test86 | 104 passed，2.98 s | pass |
| documentation contract | test26 | 13 passed，0.11 s | pass |
| Review V3 aggregation retest | test86 | 5 passed，0.28 s | pass |
| scoped Ruff | Review 聚合器与 test86 | clean | pass |
| bytecode compile | Review 聚合器与 test86 | exit 0 | pass |
| PETSc ABI probe | activate-myfenics 后 ScalarType | numpy.complex128 | pass |
| full pytest diagnostic attempt | 未 source activate-myfenics | 445 passed，18 skipped，36 failed，17 errors，11.57 s | invalid environment invocation；保留 |
| full repository pytest | source activate-myfenics 后 python -m pytest -q | 498 passed，18 skipped，247.58 s | pass |
| diff hygiene | git diff --check | clean | pass |

## Review V3 新覆盖

- test86 验证 p3/h3 Hybrid M160 MPI8 total_seconds 为 661.4100284820015，且不等于 Full3D 1726.3617402129894。
- test86 验证 p3/h3 Full3D factor_nnz 为 1,307,605,045；Hybrid factor_nnz 在无 factor inventory 时保持 null。
- test86 验证 Hybrid external_aux_dofs 为 80，并检查 total_rows = fe_dofs + external_aux_dofs + modal_unknowns。
- test86 验证仓库内 evidence path 全部为相对路径，并验证 p3/h3 current-source M80/M120/M160 使用 MPI8 权威记录。
- test86 验证 src/geometry/task034_adaptive_mesh.py 在 selective manifest 中为 research_only_do_not_merge_yet。
- summary.md 直接覆盖 26 个主/补充模型、6 个 M-funnel 记录和 8 个 MPI identity 记录；缺失 exact total 保持 null。

## 首次全仓 pytest 失败说明

第一次全仓调用直接使用 .venv/bin/python，没有先执行 source .venv/bin/activate-myfenics，因而加载了 real PETSc scalar ABI。失败集中为 complex 写入 real scalar 的 TypeError，不是本轮代码回归。该失败未删除、未改写为通过。随后按 AGENTS/Task034 要求激活环境，确认 PETSc.ScalarType 为 numpy.complex128，并在同一工作树上完整复跑得到 498 passed、18 skipped。

## 已接受重型证据边界

本轮没有重跑：

- p3/h3、p4/h5 Full3D/Hybrid 主矩阵；
- p3/h5 Full3D 与 Hybrid MPI1/8/16，及 MPI32 exploratory；
- P polarization 完整矩阵。

原因是 Review V3 没有修改 Maxwell/Floquet/QEP/Hybrid 数值核心。S polarization 仍为正式主线；既有 p2/h5 P capability sample 只证明 P 路径可执行，不参与 S 主线收敛结论。
