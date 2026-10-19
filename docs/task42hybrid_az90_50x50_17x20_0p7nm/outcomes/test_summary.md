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
| A0阶段Full3D/QEP/direct-factor/PDE | 当时未运行 | 后续正式A1已于2026-10-19运行；见本文件末尾。当前外层资源拒绝，不将worker数值summary等同整场通过 |

没有改写Task041 V5或旧账目。早期失败收据保留；A0的“12 passed”和A1小型合同回归均不代表正式资源资格或完整PDE通过。正式A1实际运行另列于本文件末尾。

## A1小型资源与direct lifecycle合同回归

A1回归验证资源入口/阶段Delta、C bridge INFOG(17) producer→consumer、同一MUMPS factor的symbolic/numeric/MatSolve/packet/destroy、真实packet writer成功与本地写失败传播、恢复gather驻留口径，以及显式ICNTL(14)兼容控制。这批回归本身没有运行13.5 nm assembly、完整QEP、正式MPI8 PDE或official物理输出；后续正式A1结果单列于本文件末尾。

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

当前Task42 source manifest、direct bridge与资源合同字段见[A1机器记录](a1_contract_validation.json)。A1小型合同只证明接口/生命周期；后续正式13.5 nm运行的数值与资源终态见本文件末尾及[只读审计](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/offline_terminal_audit.json)。


## 2026-10-19正式A1：非pytest运行与终态

本次只读closeout没有启动pytest、ABI或数值内核；所以新增pytest费用为0。正式MPI8公共入口run是此前单独授权的数值运行，不应写成测试pass：worker写出完整残差`9.306460504345312e-11`、DtN端口R/T/A与体吸收闭合差`1.2090530798758437e-9`，并落盘PVD/8个VTU、reference field samples与pre-recovery packet。外层RUN因最后runtime样本无法读取8个仍为R的rank之VmRSS/VmSwap而fail-closed拒绝，whole-job J未知；不是已证实超过256 GiB，也不是数值求解失败。诊断probe功率与端口R/T明显不同，且top E/H fit residual=`0.9980693005722018`，详见[response_v1](../response_v1.md)。

| 项目 | 状态 | 口径/证据 |
|---|---|---|
| RUN / public / service | RUN exit1；public rc3；service ExecMainStatus3；Invocation `048a5d671150436f9c05cd1bfb5a9d29` | 三层状态分别记录，进程组TERM后退出，SIGKILL未使用 |
| 最后完整资源样本 | elapsed `312.8408444840461 s`通过；`313.3017449709587 s`拒绝 | 8个worker相同PID/start_ticks复读仍缺VmRSS/VmSwap、状态R；whole-job J unknown，cgroup current不可替代完整树 |
| 唯一正式费用 | parent wall `313.734830358 s` | 单次记入Task42 non-pytest parent费用，不按8 ranks乘、不把阶段采样再相加 |
| 本次closeout检查 | offline JSON/VTK与源码定位；无pytest | 不追加pytest ledger wall |

正式A1历史按范围分列：`20261016T121844.178539Z`原场已发生factor/solve；`20261019T034149.351129Z`必要重建因authority unknown未进入factor/solve，parent wall为`not_measured`；最近一次`20261019T062050.882932Z`已发生factor/solve并写出数值输出，唯一parent wall为`313.734830358 s`。旧packet恢复`20261018T115039.812072Z`另属恢复attempt，没有新增factor/solve；CPU候选、ABI和public prelaunch gate不算PDE，缺失费用不推算。原RUN/raw均保留。额外A1额度已用完，本阶段不授权再跑A1；A2与0.7 nm仍按task前置资格及内部审核推进，目前未启动、未获本阶段放行。sampler错误分类修正与存档探针差异离线复核已完成；没有A1重算。逐文件hash、packet和canonical shard检查、168外通道键集合/顺序、R00与诊断定义见[审计收据](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/offline_terminal_audit.json)。

## 后续定向资源回归（2026-10-19）

4个serial selector通过：`test_task42_runtime_labels_only_known_whole_job_cap_exceedance`、`test_process_tree_sample_bounded_reread_requires_same_pid_start_ticks`、`test_process_tree_sample_keeps_unresolved_and_reused_pid_unknown`、`test_task42_runtime_does_not_reserve_phase_workspace_permanently`。原062050Z末样本重放仍为拒绝/incomplete+unknown，错误向量不含`runtime_whole_job_J_exceeds_Task42_C`；已知完整整树J>C仍保留超限标签，J=C与J<C按原合同通过。pytest原stdout为`4 passed in 0.22 s`，parent monotonic wall `0.505579699 s`是唯一费用；pytest PID未持久化（`not_persisted`）。源码SHA：`4c2c86b57b6c0b98c5503d4c2542f0333dbe7f77e97e5e14ef242ea4835ecd2e`；测试SHA：`cdceb62251304c80b3e7bd318ad94d847053757dc6dfeb9032a540bcaf8ab8`。离线重放、错误向量及10项逐项清单见[回归记录](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/classification_error_vectors.json)和[SHA256清单](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/SHA256SUMS.txt)。早期fixture失败raw保留；本轮未运行MPI、FE、PDE、factor、MatSolve或QEP。
