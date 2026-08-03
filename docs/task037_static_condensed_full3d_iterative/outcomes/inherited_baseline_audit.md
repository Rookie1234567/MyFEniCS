# Task37 Stage 0：继承基线审计

## 审计边界

本审计只覆盖 Task37 继承的 Task036 V8 生产选择性整合、普通默认语义、
研究性路径边界，以及 Task37 允许的 focused baseline。它不宣称 Task37
算法实现完成，也不包含 F0 direct PDE 运行。

审计执行分支为：

    codex/20260803-task37-matrix-free-iterative-development
    base HEAD before inherited-test repair:
    04278d9f7258f8391488962a2440339750ff2ee9
    upstream: origin/codex/20260803-task37-matrix-free-iterative-development
    ahead/behind before repair: 0/0

开始审计时 tracked 工作树干净；没有发现其他 heavy PDE/MPI 进程。修复
期间唯一允许的 tracked source change 是本文件所述的一个 inherited-test
hunk；Task37 production、solver、watchdog、阈值和配置均未修改。

## 环境与 ABI preflight

资格化入口为 source scripts/activate_myfenics_wsl.sh，结果如下：

| 项目 | 实测值 |
|---|---|
| _MYFENICS_WSL_QUALIFIED_ACTIVATION | 1 |
| Python | /home/Projects/MyFEniCS/.venv/bin/python |
| PETSc scalar / integer | numpy.complex128 / numpy.int32 |
| petsc4py | /usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex/... |
| slepc4py | /usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex/... |
| mpi4py | /usr/lib/python3/dist-packages/mpi4py |
| DOLFINx / Basix | 0.10.0.post2 / 0.10.0 |
| MPI | Open MPI 4.1.6 |
| OMP_NUM_THREADS | 1 |
| PETSc/SLEPc directories | complex Linux PETSc 3.19 stack |

因此 Python、MPI、PETSc/petsc4py、SLEPc/slepc4py、DOLFINx 和 Basix
通过了同一 Linux ABI 栈与 complex128/int32 要求。没有启动正式 PDE。

## Task036 V8 选择性整合核对

Task036 V8 的四个选择性提交及其边界为：

| 提交 | 继承结论 |
|---|---|
| 7735a261 | Full3D 正确性、direct telemetry、watchdog/lifecycle；其中 _enrich_factor_inventory 使用显式来源字段，并区分纠正后的 MUMPS INFOG(9) 与 PETSc raw nnz。 |
| a741ad1b | Hybrid 安全性、exact conormal、beta 与 fail-closed 修复；不把完整 direct Hybrid 提升为 production。 |
| 4c9e1b... | strong-trace / exact-trace 仅为 research-only oracle，不改变 ordinary defaults。 |
| b615a130... | controlled-negative closeout 文档；容量、POD、96-RHS 等未资格化路径仍为禁止生产整合项。 |

核对结果：

- ordinary default 仍保持原有语义；没有切换到 strong/exact trace，也没有
  把 Hybrid-P、low-rank direct Hybrid 或 Task036 容量/POD 路径变成生产默认。
- Task036 的 B1/C1 capacity、POD、96-RHS、robustness scan、exact-Cauchy
  大 runner 等研究/负结果路径不在本次生产范围。
- Task037 仍只继承已资格化的 Full3D operator、recovery、residual、R/T/A、
  watchdog 与 telemetry 入口；本阶段没有扩展它们。

## focused baseline 的原始失败与精确修复

### 初次结果

任务书指定的 11 文件命令为：

    source scripts/activate_myfenics_wsl.sh && set -o pipefail && /usr/bin/time -f 'elapsed_seconds=%e exit_code=%x' python -m pytest -q src/test/test_14_stage4_dtn_modes.py src/test/test_28_direct_memory_telemetry.py src/test/test_29_hcurl_multilevel.py src/test/test_30_task031_contract.py src/test/test_68_task033_full3d_watchdog.py src/test/test_80_task034_mpi_identity.py src/test/test_115_task035b_assembly_time_condensation.py src/test/test_179_task035b_hybrid_static_condensation.py src/test/test_181_task035c_p6_h10_runner_gates.py src/test/test_195_task036_mumps_factor_nnz.py src/test/test_196_task036_forward_solver_hardening.py

在 inherited-test repair 前，结果为：

    107 passed, 4 skipped, 1 failed in 113.64s (0:01:53)
    Command exited with non-zero status 1
    elapsed_seconds=114.20 exit_code=1

唯一失败为：

    src/test/test_28_direct_memory_telemetry.py::DirectMemoryTelemetryTests::test_factor_inventory_records_only_algebraic_derived_ratios

原始断言是：

    self.assertIn("not inferred MUMPS", ratios["semantics"])

而 7735a261 已将 production _enrich_factor_inventory 合同改为显式
来源字段，并把语义改为：

    Ratios use the corrected MUMPS INFOG(9) million-entry count when the raw int32 telemetry overflowed, otherwise PETSc-reported nnz; storage ratios use the same matrix-storage estimator.

这不是 Task37 算法回归，而是 Task036 V8 选择性合入时遗漏了测试合同
hunk。原始完整日志保留于：

    /tmp/task037_stage0_baseline_20260803.log

### 允许的 inherited-test repair

监督审查指定的来源提交为：

    5231282f21e799c62b3a10ac1ccb1a8226935dc6

我没有 cherry-pick；仅手工恢复该提交对
src/test/test_28_direct_memory_telemetry.py 的唯一 hunk：

    self.assertEqual(
        ratios["factor_nnz_source"],
        "petsc_factor_matrix_nnz_used_raw",
    )
    self.assertEqual(
        ratios["factor_estimated_storage_source"],
        "petsc_factor_matrix_estimate_raw",
    )
    self.assertIn("otherwise PETSc-reported nnz", ratios["semantics"])

没有修改 production、阈值、测试结构、函数名或任何其他文件。修复后
先运行的 targeted 命令及结果为：

    source scripts/activate_myfenics_wsl.sh && set -o pipefail && /usr/bin/time -f 'elapsed_seconds=%e exit_code=%x' python -m pytest -q src/test/test_28_direct_memory_telemetry.py::DirectMemoryTelemetryTests::test_factor_inventory_records_only_algebraic_derived_ratios src/test/test_195_task036_mumps_factor_nnz.py

    6 passed in 1.68s
    elapsed_seconds=2.11 exit_code=0

原始 targeted 输出保留于：

    /tmp/task037_inherited_repair_targeted_20260803.log

## focused baseline rerun

修复后的同一 11 文件 focused baseline 已按同一资格化 activation 完整
重跑并通过：

    108 passed, 4 skipped in 112.05s (0:01:52)
    elapsed_seconds=112.54 exit_code=0

原始 rerun 输出保留于：

    /tmp/task037_stage0_baseline_repair_rerun_20260803.log

因此 inherited-test repair Gate 通过。该结果只证明继承测试合同与当前
Task036 V8 生产代码一致，不等于 Task37 F0 或后续 iterative Gate 通过。

## 结论边界

Stage 0 inherited-test repair 已完成；没有运行 full repository pytest、
Case100、MPI PDE、F0 direct authority 或任何 F1--F6 iterative candidate。
Task036 的 ordinary default、strong/exact trace research-only 边界以及未
资格化 Hybrid/容量路径仍保持不变。
