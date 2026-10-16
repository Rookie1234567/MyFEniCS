# Task42 A0 测试与独立费用摘要

所有测试均在原生activation环境运行，PETSc标量为complex128、整数为Int32；MPI rank环境路径一致，六个数学线程变量均为1。测试前后对应源码SHA保持不变。以下时间和RSS来自GNU `/usr/bin/time`记录：wall按其输出精度显示至0.01秒，不称作高精度`CLOCK_MONOTONIC`；RSS是计时命令收据值，不是整棵进程树或cgroup峰值。

| 时间/attempt | selector与覆盖 | 状态 | GNU time wall | GNU time peak RSS | 证据 |
|---|---|---|---:|---:|---|
| `20261016T082736Z` | native serial preflight | pytest未启动 | 0 s pytest wall | 未记录 | `results/task42hybrid_az90_50x50_17x20_0p7nm/a0_serial_regression_20261016T082736Z/`；路径断言误判venv Python symlink，后续真实ABI核验通过 |
| `20261016T082837Z` | A0文件及public CLI、direct adapter、动态外通道3个相关selector | 1 failed，`-x`下余项not_run | 2.43 s | 208284 KiB | [`attempt.json`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a0_serial_regression_20261016T082837Z/attempt.json)；Poynting独立公式比较容差过紧，保留原失败 |
| `20261016T082953Z` | 同一冻结serial范围；`src/test/test_task42_physical_entry.py`及上述3个selector | 12 passed | 11.72 s | 320268 KiB | [`attempt.json`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a0_serial_regression_20261016T082953Z/attempt.json)；pytest stdout记12 passed |
| `20261016T083132Z` | `src/test/test_task42_physical_entry.py::test_task42_builds_the_boundary_fitted_material_mesh_with_expected_volumes`，MPI2 | rank 0和1各1 passed，parent rc0 | 1.47 s parent | 113944 KiB parent receipt | [`attempt.json`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a0_mpi2_mesh_regression_20261016T083132Z/attempt.json)及rank-local stdout/exit receipts |

## 独立Task42费用

| 项目 | 记账值 | 口径 |
|---|---:|---|
| 实际pytest parent attempts | 3 | 一次失败serial、一次通过serial、一次MPI2 parent；rank数不乘费用 |
| GNU time wall记录值之和 | 15.62 s | 2.43+11.72+1.47秒，基于各receipt已显示的0.01秒精度 |
| preflight未启动测试 | 0 s pytest费用 | 082736Z仅本地preflight拒绝 |
| ABI检查 | 不另计pytest wall | 不属于pytest parent |
| Full3D/QEP/direct-factor/PDE | 未运行 | 不存在Task42数值求解费用或solver资格 |

没有改写Task041 V5或旧账目。早期失败收据保留，不把A0的“12 passed”扩展为Full3D或正式资源资格通过。A1小型资源/direct合同已接线；正式PDE相关项仍为`not_run`。

## A1小型资源与direct lifecycle合同回归

A1回归验证资源入口/阶段Delta、C bridge INFOG(17) producer→consumer、同一MUMPS factor的symbolic/numeric/MatSolve/packet/destroy、真实packet writer成功与本地写失败传播、恢复gather驻留口径，以及显式ICNTL(14)兼容控制。它没有运行13.5 nm assembly、完整QEP、正式MPI8 PDE或official物理输出。

| Attempt | 覆盖与结果 | parent wall | 状态/说明 |
|---|---|---:|---|
| `a1_resource_contract_serial_20261016T093750Z` | 4 passed/1 failed；随后5 passed/1 failed；最终12 passed | `not_measured` | pytest报告时长依次0.56/0.36/0.41 s；前两次夹具失败保留，不把pytest报告时长当parent费用 |
| `a1_infog17_native_20261016T102000Z/pure_contract_parent` | 纯合同首次失败；`pure_contract_retry1_parent` 17 passed、1 deselected | 1.894561165 s / 1.780148414 s | 两份原收据均保留 |
| `a1_infog17_native_20261016T102000Z/native_serial_parent` / `native_mpi2_parent` | 新编译C bridge真实INFOG(17) producer与Python inventory consumer通过 | 1.626507842 s / 1.812685153 s | C源`c6d1cf56…f24229d`、bridge `.so` `0364aafe…46a0ac9`；MPI2 stdout显示rank 0/1各1 passed |
| `a1_final_direct_lifecycle_20261016T102640Z/serial_pytest_parent` | 首次小型direct链失败 | 2.004267829 s | 保留首错与原stdout；不作为通过 |
| `a1_final_direct_lifecycle_retry1_20261016T102835Z/serial_pytest_parent` / `mpi2_pytest_parent` | serial通过；MPI2首轮失败；之后`a1_final_validation_20261016T102948Z` serial和MPI2通过 | 1.807239021 / 4.022138082 / 1.832894028 / 1.986119170 s | 最终MPI2两rank各4 passed；此前失败receipt保留 |
| `a1_writer_recheck_20261016T103126Z/serial_pytest_parent` | writer selector初次serial失败 | 1.737313955 s | 失败收据保留 |
| `a1_writer_recheck_20261016T103200Z/serial_pytest_parent` | serial writer selector通过 | 1.613241628 s | 同目录MPI2 wrapper的pytest父目录缺失，pytest未启动；其1.303494641 s parent wall不计pytest费，拒绝raw保留 |
| `a1_writer_mpi2_recheck_20261016T103300Z/mpi2_pytest_parent` | MPI2 writer正例/本地拒绝链通过 | 2.007214812 s | 独立新attempt；两rank结果与清场证据见原receipt |
| `a1_recovery_delta_scope_20261016T103600Z/parent.json` | rank-local gather临时驻留公式纯fixture通过 | 1.718021053 s | 每rank按两份同时驻留数组计数，再由阶段callback跨rank求和 |
| `a1_recovery_delta_scope_recheck_20261016T105000Z/parent.json` | 当前源码重验同一rank-local gather纯fixture，1 passed | 1.570869846 s | 当前source SHA在before/after相同；六线程均为1，PETSc complex128/Int32 |
| `a1_icntl14_control_serial_20261016T103900Z/parent.json` | explicit-int控制首次fixture失败 | 1.755496679 s | cleanup路径重复，原失败raw保留 |
| `a1_icntl14_control_serial_20261016T103920Z/parent.json` / `a1_icntl14_control_mpi2_20261016T104000Z/parent.json` | 同一新bridge上`None`默认分支和显式`ICNTL(14)=40`控制均通过；MPI2 stdout中rank 0/1均观测actual/readback 40 | 1.733057743 / 1.894946596 s | 两份receipt绑定同一C源与.so SHA；该轻量MPI2 selector未记录rank affinity |

17个pytest已启动且有parent monotonic wall的attempt合计`32.796723016 s`，不按rank数倍增。资源fixture三次运行的parent wall未测，单列`not_measured`；其pytest-reported 0.56/0.36/0.41 s不作为费用。native ABI/ABI preflight不计pytest费用。共享basetemp父目录缺失的MPI2 wrapper虽有1.303494641 s parent wall，但pytest未启动，不计pytest费用。所有失败输出与attempt目录保留于ignored `results/task42hybrid_az90_50x50_17x20_0p7nm/`。

当前Task42 source manifest、direct bridge与资源合同字段见[A1机器记录](a1_contract_validation.json)。A1只证明小型真实接口/生命周期合同；正式13.5 nm Full3D PDE、正式8-rank affinity/scope、最终R/T/A和衍射结果仍为`not_run`。
