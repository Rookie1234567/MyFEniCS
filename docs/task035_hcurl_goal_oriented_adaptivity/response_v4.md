# Task035 Response V4：Phase B full regression 恢复通过

## 结论

用户明确授权后，使用任务规定的正确 complex activation 重跑了一次 full pytest：

```bash
source .venv/bin/activate-myfenics
pytest -q
```

结果：

```text
506 passed, 18 skipped in 248.08s
```

因此：

```text
phase_b_targeted_fixture_tests = 12_passed
phase_b_focused_suite = 35_passed
serial_mpi2_mpi4_component_identity = pass
scoped_ruff_compileall_diff_check = pass
phase_b_full_regression_gate = pass
phase_c_unlocked = true
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

## 历史与恢复关系

`records/phase_b_regression_failure.json` 保持原样，继续记录此前直接调用
`.venv/bin/python`、遗漏 `source .venv/bin/activate-myfenics` 所导致的
`operator_launch_environment_mismatch`。该负记录没有删除、覆盖或改写为通过。

新的 `records/phase_b_regression_recovery.json` 绑定被测试源码
`8c85469a5720573f51b784049de7d25bcbe012f4`、用户授权、正确命令和完整测试计数。
正确 activation 下全仓回归通过，确认先前失败不是 Task035 estimator、Maxwell PDE，
也不是已资格化 WSL/PETSc/MPI/MUMPS/SLEPc/DOLFINx 栈的失败。

## 后续边界

Phase C 现已解锁，但本轮没有启动 Phase C。下一步只能按任务书进行低成本 estimator
bake-off：优先 R1、R2、R5、G1、B1；R4 仍为 `formula_defined`，不得冒充已资格化的
equilibrated estimator。不得跳过低成本 point 和 refinement fixture 直接运行真实 p4
adaptive 或其他重型 PDE。
