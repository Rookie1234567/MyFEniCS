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

没有改写Task041 V5或旧账目。早期失败收据保留，不把“12 passed”扩展为Full3D或资源合同通过。A1资源/软48小时策略仍待接线，所有正式PDE相关项都是`not_run`。
