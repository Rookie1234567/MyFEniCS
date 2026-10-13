# Review V31 P0 执行回应：入口就绪，数值窗口仍待批准

本轮没有新增 q 的矩阵、因子、完整参考或目标场。旧 q0 资格按原 source/window 保留；V31 的新 q 数值覆盖仍为 **0/8，NOT_RUN**，完整参考、目标 PDE、R/T/A 与 2 TB/48 h 仍未资格化。完成的是重型窗口前的 P0：把失败后重试固定 T0、生成批准合同和执行命令的路径接通并用临时 fixture 验证，随后完成定向回归。新重型窗口仍为 **PENDING**。

## P0 结果

| 项目 | 状态与解释 |
|---|---|
| 重试时间锚 | 两次模拟准备失败后，第三次成功准备沿用第一次写下的三时钟 T0、campaign window 字节和 SHA；没有重新调用 T0 时钟采样。fixture 使用临时目录及伪造批准收据，不代表真实用户授权，也没有留下可启动的真实窗口。 |
| 获批包 | 真实 `prepare_v31_pending_package` 从 canonical DAT 和小型 q0 selector fixture 生成 pending 路由；真实 `prepare_v31_approved_package` 生成 approved contract、selector、registration 与命令。随后真实 `require_v31_execution_contract`、`v31_launcher_values` 和 campaign 校验器接受产物。该 fixture 仅证明准备入口与身份合同，不重复资格化 q0 数值。 |
| q4 保存优先 | worker 先从已保存 q4 contribution 构建并持久化自己的数值 CSR pending，再进入完整 reference builder；native 失败时不把 pending 冒充 COMPLETE/PASS。 |
| 恢复与跨窗导入 | numeric-pending 重开不重复 pattern/fill；COMPLETE consumer 按原始身份导入；跨窗消费要求明确 source/window/producer 收据。旧 q0 PASS 不重写。 |
| owner 与真实 callback | twist0 owner 交给 reference callback 后由统一 cleanup 释放；销毁失败会使 worker/checker 结果失效。q1/q5 callback 使用实际 twist1 builder 输入，覆盖非 q4 执行顺序。 |
| 分阶段准入 | reference-only、target build、target ready 分开检查；target 未构建时 actual 保持 null，planned 值不代替实测资源或身份。 |
| closeout 与费用分类 | 窄修 service、watchdog 启动/采样和 checker 的 cutoff/closeout 合同；strict 与 V15 reference 层分别记录，AllQ RHS MatSolve 按类别、q 和嵌套阶段计数。 |
| 执行链 | V31 launcher/service 参数、同窗 campaign window 路由、partial checker 与 official checker 命令由代码生成并在成功 fixture 中核对。没有运行正式 q factor、FE、JIT、PDE、完整大数组扫描、pattern/fill/native。五文件单测包含小型精确 MUMPS API fixture；它不是 Task40 数值资格。 |
| 新数值结果 | 未运行。q4、q1–q7 的新矩阵与 native 资格、八 q live factor bank、完整参考逆和条件原尺寸 pilot 均为 NOT_RUN。 |
| 固定窗口 | 旧 V30 T0/cutoff/deadline 原样保留且已结束。V31 T0、cutoff、deadline、window JSON 和真实批准收据都不存在；不得从测试 fixture 推断为已批准。 |

## 验证

Task40 资格化本地环境的轻量 ABI preflight 通过：`_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`，解释器与 PETSc/SLEPc、DOLFINx、Basix、mpi4py 均来自本仓库配置的 Linux runtime；PETSc scalar 为 `complex128`、integer 为 `int32`。

最终定向回归覆盖五个修改相关测试文件：

```bash
python -m pytest -q \
  src/test/test_task40_v10_p6_mumps.py \
  src/test/test_task40_v30_qualified_q_csr.py \
  src/test/test_task40_v30_selected_q_csr.py \
  src/test/test_task40_v31_admission.py \
  src/test/test_task40_v31_closeout.py
```

结果为 **67 passed in 4.43 s**。原始日志位于 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_preparation/test_final_targeted_20261013.log`，SHA-256 为 `a70135c082be352369ff51d0f9df41e7626d602527e52ef89290428a173af5f6`。新增失败重入及成功准备路径的小 fixture 单独为 2 passed；五文件回归已包含这两个测试。

第一次五文件回归发现一个旧 fixture 未提供新的 `q` 分类索引，第二次发现其 audit fixture 缺少按 q 计数的三个小映射；均为测试夹具接线问题，已修正后以最终五文件回归通过。第二次失败原始日志保留在 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_preparation/test_final_targeted_after_fixture_fix_20261013.log`。第一次失败发生在复用同名日志路径之前，原始日志文件随后被最终通过日志覆盖；主控从执行记录另存了 `controller_recovered_failure_transcripts.json`，其中逐项标明这是 `recovered_from_tool_transcript` 的回执副本，并非原始日志字节，不声称原始 SHA-256。

本次不是全仓 pytest、MPI2/4、Ruff、CI 或数值资格运行；没有据此声称 CI、PDE 或最终精度通过。

## 源码与成本身份

生成测试和本回应记录时，分支为 `task40extra_0p7nm_engineering`，工作树含未提交 P0 修改，`HEAD=d7ffbfea952bc160742b18739369f2e3f656ee8e` 是 Review V31 基线，不是冻结源码。每个修改源码/测试文件的 SHA-256、测试原始日志、ABI 收据和工作包时钟观察列在 [V31 P0 evidence index](outcomes/records/review_v31_p0_evidence_index.json)。主控将集中审核、冻结、提交推送并回读最终 SHA；该 SHA 应与 compact 中绑定的文件内容对应。

工程成本以连续 P0 锚点和观测值保留，包含会话间空闲时间，不能解释为纯编码工时。新数值窗口的 T0 仍为 null；P0 花费不会从后续完整冷流程账中删除。

下一步由主控先审核/冻结当前源码，再集中提交与推送；只有之后用户明确批准新的 12 小时固定窗口，才能在真实审批收据验证后第一次采样 T0 并进入批准流程。旧 V30 窗口、失败与 `NO_PARTIAL_FOOTER` 证据均不改写。可执行交接见 [handoff V31](outcomes/handoff_v31.md)；项目汇总与 run index 仅追加本轮 P0 状态。
