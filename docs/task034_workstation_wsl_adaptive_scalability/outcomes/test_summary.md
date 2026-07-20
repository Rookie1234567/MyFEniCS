# Task034 测试汇总

## 最终结论

Task034 新增/修改路径的 serial、MPI、文档契约、Ruff 与 compileall 均通过；Task032/Task033 回归通过。全仓 Ruff 的 15 个失败均来自未被本任务修改的历史文件，按边界保留，未误报为 Task034 pass。

| 层级 | 命令/范围 | 结果 | 判定 |
|---|---|---:|---|
| Task034 serial/native | `pytest -q src/test/test_73* ... src/test/test_85*` | 99 passed，2.57 s | pass |
| selected MPI2 | test80/test82/test83 | 每 rank 16 passed，0.89 s | pass |
| selected MPI4 | test80/test82/test83 | 每 rank 16 passed，2.34 s | pass |
| Task032/033 regression | `pytest -q src/test/*task032*.py src/test/*task033*.py` | 217 passed，8 skipped，238.69 s | pass |
| final docs + Task034 serial/native | test26 + test73..85 | 112 passed，1.88 s | pass |
| scoped Ruff | Task034 变更的 Python 文件 | clean | pass |
| bytecode compile | `python -m compileall -q benchmarks src` | exit 0 | pass |
| numerical blob audit | `python -m benchmarks.task034_numerical_blob_checker ...` | `numerical_blob_compatibility_pass` | pass |
| full Ruff | `ruff check .` | 15 pre-existing errors | known baseline boundary |

## 数值与 Gate 覆盖

- Phase A 覆盖 PETSc complex ABI、SLEPc PEP、DOLFINx/MPC、MUMPS 与 MPI1/2/4/8/16；MPI32 仅 exploratory。
- heavy runner/checker 测试覆盖 source clean/stable、nonignored untracked、cgroup/process-tree memory/swap、terminal drain、assembly/factorization/full-solve 状态和 true residual。
- Case093 checker 覆盖 fixed physical identity、Full3D/Hybrid reference binding、official R/T/A、field/order observables、MPI identity 和 canonical manifest。
- adaptive checker fail closed：网格/DoF 减少不能替代物理同误差 Gate；失败 profile 保留为 negative。
- resource model v2 测试覆盖 component inventory、单位、校准点、预算分类和 0.7 nm joint-compression 下界。

## 全仓 Ruff 既有问题

未清理的 15 项只位于：

```text
src/postprocessing/diffraction_3d.py
src/postprocessing/full3d_reference.py
src/postprocessing/hybrid_field_reconstruction.py
src/solvers/solve_maxwell_3d_common_old.py
src/studies/run_3d_memory_profile.py
```

这些文件不在 Task034 changed-file set。本任务没有扩大范围修复，也没有将 full Ruff 状态改写为 clean。
