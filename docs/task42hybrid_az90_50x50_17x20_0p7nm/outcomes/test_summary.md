# Task42测试与独立费用摘要

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

## A2共享合同serial/MPI2批次（2026-10-19）

合同代码与测试共21个路径已按本轮审核提交为`44f671cefd9a3130897bfc898ba21cde8528fbe4`；测试均针对该提交对应source after map。测试使用小数组、sentinel、mock或轻量公共输入合同，不创建实际A2网格/QEP/FE/factor/solve，不构成A2数值资格。2个MPI-only case在serial中skip，由MPI2批次实际覆盖。

| Attempt | 选择器/覆盖 | pytest结果 | 唯一pytest parent wall | 收据与说明 |
|---|---|---:|---:|---|
| [`a2_contract_regression_20261019T090830Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_regression_20261019T090830Z/serial/pytest_receipt.json) | 首轮串行，`-x` | 5 passed, 1 failed | 4.727081632 s | 保留sentinel首错；receipt绑定本次as-run源码SHA，未声称整组通过 |
| [`a2_contract_native_serial_retry_20261019T092107Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_native_serial_retry_20261019T092107Z/pytest_completion.json) | serial全合同范围 | 26 passed, 6 failed, 2 skipped | 3.545411391 s | 夹具shape/协议错误保留；按本attempt的as-run源码SHA绑定 |
| [`a2_contract_native_serial_final_20261019T092308Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_native_serial_final_20261019T092308Z/pytest_completion.json) | 修后serial全合同范围 | 31 passed, 1 failed, 2 skipped | 3.368963186 s | 保留唯一cfg重复参数失败；按本attempt的as-run源码SHA绑定 |
| [`a2_contract_target_serial_20261019T092343Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_target_serial_20261019T092343Z/completion.json) | coupling selector定向重测 | 1 failed | 2.321764543 s | 保留参数绑定失败；按本attempt的as-run源码SHA绑定 |
| [`a2_contract_target_serial_final_20261019T092417Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_target_serial_final_20261019T092417Z/completion.json) | 同一coupling selector定向重测 | 1 passed | 2.253717981 s | 修复后小选择器通过；按本attempt的as-run源码SHA绑定 |
| `a2_contract_native_serial_final2_20261019T092443Z` | 最终serial合同收口 | 32 passed, 2 skipped | 3.295652662 s | pytest stdout显示2.93 s，仅parent monotonic wall计费 |
| `a2_contract_native_mpi2_20261019T092648Z` | root writer成功、rank-local坏shape拒绝、root writer失败、root resource拒绝 | rank 0/1各4 passed；parent rc0 | 2.878076813 s | 四个MPI2 selector同一parent一次记账；rank私有basetemp |

091322Z、091422Z及092019Z均在pytest启动前因本地source清单读取、tuple键序列化或活动进程检查错误而拒绝，pytest费用为0；这些原失败输出保留。ABI parent wall单列，不并入pytest费用。以上7个实际启动的pytest parent累计为`22.390668208 s`，按每个parent receipt一次相加，不按MPI rank数乘。每个早期attempt绑定它自己的receipt与as-run源码SHA；只有最终serial和MPI2的source after map与提交`44f671cefd9a3130897bfc898ba21cde8528fbe4`相同。最终serial 32 passed/2 skipped的两个skip是`test_task42_collective_output_rejects_single_rank_bad_shape_before_writer`和`test_task42_mpi_root_resource_refusal_propagates_before_allocation`；MPI2分别证明单rank输入坏形状能在writer前全rank拒绝，以及root resource refusal一致传播且guarded allocation未调用。

最终MPI2证据确认：成功时两rank收到相同payload/identity descriptor，只有rank0执行两文件writer；坏shape和预存目标文件写失败均在所有rank得到相同错误，rank1不执行writer；root resource refusal在受保护分配前传播，allocation调用数为0。每个rank证据含错误、descriptor、writer调用数和清场状态。rank0/rank1实际affinity分别为CPU2/CPU10且与请求map一致；PETSc为complex128/Int32，policy为default，`Mems_allowed_list`覆盖`0-1`，数学线程变量均为1。具体收据：

- [MPI2 pytest parent](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_native_mpi2_20261019T092648Z/mpi2_pytest_parent.json)
- [MPI2 ABI rank records](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_native_mpi2_20261019T092648Z/mpi2_abi_ranks.json)
- [post-ABI fresh gate](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_native_mpi2_20261019T092648Z/post_abi_fresh_gate.json)
- 最终serial stdout和parent receipt位于`results/task42hybrid_az90_50x50_17x20_0p7nm/a2_contract_native_serial_final2_20261019T092443Z/`。

这批结果只证明公共合同、预算绑定、root writer/错误传播和分配前拒绝；不证明实际A2网格、QEP、局部凝聚、MUMPS填充或物理结果。A2所有阶段Delta仍`pending-sizing`并保持不可运行。详细资格边界与下一步对象清单见[response_v1](../response_v1.md)。

A2费用仅沿Task42各parent receipt记账，未更改Task041 V5、历史raw或既有账目。所有旧失败attempt均保留；ABI parent独立于pytest parent，未启动pytest的脚手架拒绝不收费。

## P1行级衍射功率修正（2026-10-19）

最终修复selector为`test_task42_hybrid_rows_and_dtn_ports_report_power_classification_difference`。production SHA为`652d19a6540660d870ace9a81ef110fd40c82cd9ec0b541477f65cb55ab557e1`，测试SHA为`f68c7c34e44ab684e2ded565872ee8bfe9faf4f0b3e6df32e7f1dd8423dcf444`；当前代码提交`6d9106b7e956d7c5f0b2ca950e19ba4c8ab3a6ed`。最终attempt目录中的当前21项SUMS均校验通过；通知前的19项版本与当前加入通知/pycache等后的21项是不同清单，不能混称同一SUMS。

| Attempt | pytest结果 | parent wall | 说明/证据 |
|---|---:|---:|---|
| [`a2_p1_port_power_diagnostic_20261019T095509Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_p1_port_power_diagnostic_20261019T095509Z/serial/) | 失败 | 2.342012722 s | 保留原差异；断言错误要求top s和p入射投影都非零，而实际s入射的p投影近零 |
| [`a2_p1_port_power_diagnostic_retry_20261019T095800Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_p1_port_power_diagnostic_retry_20261019T095800Z/serial/) | 失败 | 2.294325196 s | 保留浮点倏逝`power_ratio`非精确零的首错 |
| [`a2_p1_port_power_diagnostic_final_20261019T100144Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_p1_port_power_diagnostic_final_20261019T100144Z/serial/) | 通过，复现修复前差异 | 2.213222336 s | 预修复行T总和0；DtN T合计`0.3282679451110778` |
| `a2_p1_port_power_row_fix_20261019T100954Z` | pytest未启动 | 0 s pytest费用 | activation环境漏`BLIS_NUM_THREADS=1`；原尝试保留 |
| `a2_p1_port_power_row_fix_retry_20261019T101036Z` | pytest未启动 | 0 s pytest费用 | handoff过早解析到`/usr/bin/taskset`；原尝试保留 |
| [`a2_p1_port_power_row_fix_handoff_20261019T101143Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_p1_port_power_row_fix_handoff_20261019T101143Z/serial/) | 失败 | 2.425924026 s | 保留入射标签/配置假设错误的首错 |
| [`a2_p1_port_power_row_fix_retry2_20261019T101228Z`](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_p1_port_power_row_fix_retry2_20261019T101228Z/serial/) | 通过 | 3.038582487 s | 最终source；rc0，owned进程组空，完整逐行/总量对照见`row_power_fix_comparison.json` |

共5个实际启动的pytest parent，wall总和`12.314066767 s`；不以pytest显示时长代替parent wall，不按MPI rank计倍数。两次pytest未启动attempt费用为0。修复后，lossy Si底部s/p行T分别为`0.25778898368788117`和`0.07047896142319664`，与端口贡献及总T=`0.3282679451110778`一致；lossless evanescent以及n=1.2 synthetic s/p控制也符合相同公式判据。n=1.2控制因输入幅度任意而T>1，不是物理能量通过。修复仅调整行级R/T功率纳入判据；不重写旧A1值、历史诊断或P1预修复失败。
