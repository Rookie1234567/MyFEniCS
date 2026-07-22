# Task035 Response V3：Phase B fixture 实现与受控停止

## 结论

Phase B 的 estimator 定义、四类 analytic/manufactured fixtures、compact evidence 和
targeted/component tests 已完成；没有启动真实 PDE、adaptive mesh 或 p4 heavy case。
但是 Phase B 收口 full-regression Gate 失败，因此按任务书停止：

```text
phase_b_targeted_fixture_tests = 12_passed
phase_b_focused_suite = 35_passed
serial_mpi2_mpi4_component_identity = pass
scoped_ruff_compileall_diff_check = pass
phase_b_full_regression_gate = fail
phase_c_unlocked = false
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

## 已完成范围

- 新增纯验证层 `task035_hcurl_estimator_fixtures.py`，定义 R1–R5、G1/G2、B1/M1
  所需的 Hermitian norm、residual component、frequency screen、recovery、局部 SPD
  correction、DWR、goal derivative、truncation split 和 canonical cell reduction；
- 新增 hermetic runner，只执行 analytic/manufactured fixture 与 scalar MPI allreduce；
- 新增 12 个单元测试，覆盖 exact-zero、orientation、Floquet phase、material tag、DtN、
  Et/Ht、uniform-refinement trend、complex conjugation、directional derivative 和
  serial/MPI identity；
- 新增 `outcomes/estimator_definitions.md`、`fixture_matrix.csv/json` 和 Case094
  `records/fixture_summary.json`；
- R4 只有局部 SPD precursor，状态保持 `formula_defined`；没有宣称受约束
  equilibrated guarantee。其余候选为 `fixture_pass`，但均非 production qualification。

## Full regression 失败与分类

我错误地直接执行：

```bash
.venv/bin/python -m pytest -q
```

而没有先执行任务规定的：

```bash
source .venv/bin/activate-myfenics
```

完成的 full run 结果为：

```text
36 failed, 453 passed, 18 skipped, 17 errors in 10.71s
```

代表性错误是 DOLFINx real-valued array 拒绝 complex 材料值。只读检查确认 activation
脚本负责设置 complex PETSc/SLEPc、`PYTHONPATH`、`LD_LIBRARY_PATH` 和项目本地 complex
`dolfinx_mpc`。因此本次分类为 `operator_launch_environment_mismatch`，不是 WSL、PETSc、
MPI、MUMPS、SLEPc、DOLFINx 的既有资格化失败，也不是 Task035 estimator 或 Maxwell PDE
失败。

此前还有一次相同命令被外层 5 秒 timeout 终止，没有形成测试结论；本 response 不把它
计作 pass 或 fail。完整受控失败字段保存在
`records/phase_b_regression_failure.json`。

## 停止决定

没有重跑 full pytest、没有改变阈值、没有修改数值核心。Phase C 维持锁定。
需要用户明确授权后，才能用正确 sourced complex 环境执行一次 full pytest；通过前不得
开始 Phase C low-cost bake-off，更不得启动真实 p4 adaptive 或其他重型 PDE。
