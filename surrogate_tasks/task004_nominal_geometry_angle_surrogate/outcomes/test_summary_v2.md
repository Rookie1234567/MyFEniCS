# 测试和独立 checker

M0R 后的 targeted regression：

```text
python -m pytest -q \
  src/test/test_task004_m0r.py \
  src/test/test_surrogate_task002_foundation.py \
  src/test/test_18_3d_direct_solver_profile_cleanup.py \
  src/test/test_28_direct_memory_telemetry.py
64 passed, 1 skipped
```

CPU 解释器下的 M0R-only 测试为 `3 passed`。修改过的 solver、campaign、
angle pipeline 和 checker 模块均通过 `compileall`；synthetic angle pipeline
测试覆盖 OOF truth isolation、overlapping region labels、mask agreement、
composition reconstruction 和 non-zero uncertainty。

```text
python benchmarks/cases/124_task004_mumps_workspace_and_anchor_requalification/checker.py
status = pass
```

checker 只读 design JSON、campaign manifests、execution JSON 和 compact
records；它不运行 PDE，不读取 Task003 frozen validation，也不打开 Task004
blind-validation response。
