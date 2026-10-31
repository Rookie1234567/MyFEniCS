# Task44 outcomes summary（执行中）

## 当前状态

六层材料/输入实现已有定向验证。原 P6 `standard_full` 样本 A 已按用户指令受控停止；没有数值通过或失败。P2 成对求解只验证凝聚算法、场恢复和物理输出与完整矩阵路径一致。新的 P6 凝聚 direct + exact MUMPS A 输入已通过公共 adapter，但在本摘要生成时尚未启动。

## 模型与阶段账

| 对象 | 模型 / 方法 | 结果 | 数值与边界 | 证据 |
|---|---|---|---|---|
| 旧正式 A | 六层全 0.5 nm，P6，144 hex，完整双 Floquet / auto-propagating DtN，`standard_full` | `controlled_stop`；结果 `not_run` | 8433.239279829897 s 后用户停止；watchdog exit -15 且 cgroup 清空。systemd `failed/exit-code/status1` 保留；无 full residual、R/T/A 或 `A_volume` | `benchmarks/artifacts/task44_native_services/task44-sample-a-dynamic2.service/user_controlled_stop.json` |
| 凝聚实现 sanity | 同六层模型但 P2，3×6×8；标准完整矩阵 direct 对照装配期静态凝聚 direct | 两个 case 均 `completed / official_result=true`，分类 `numerical_sanity_only` | 独立 full `Ax-b` 相对 residual `2.4258989122760487e-12`；R `0.9994596016861909/0.9994596016861921`；T `0.000540279641313905/0.0005402796413138561`；总 A_volume `1.184079724682327e-7/1.1840797246823236e-7`。p2 profile 是 PETSc `default`，不是 MUMPS qualification | ignored `task44_condensed_direct_validation_20261031/` 中 evidence JSON、两份 run summary 与字段 NPZ |
| 新正式 A | 六层全 0.5 nm，P6，3×6×8，完整双 Floquet / auto-propagating auxiliary DtN；`assembly_time_static_condensed` + `mumps_exact` | `not_run`（待 clean commit 后 fresh gate） | 物理输入未改变；实际 MUMPS factor/readback、完整残差、R/T/A、峰值内存和耗时均待运行测量 | [新 A 输入](../../input/task44_sample_a_condensed_direct_v1.dat)；公用输入验证 `status=valid` |

P2 对照中 E、H 采样场最大绝对差为 `5.3619e-14 V/m` 和 `1.6475e-16 A/m`；六层吸收最大绝对差 `3.7012e-20`。这些结果支持小规模凝聚实现一致性，不能外推为 P6 成本或正式样本资格。

## Gate 与下一步

- ABI：原生 Linux，PETSc `complex128/int32`，SLEPc 3.19.2，MPI1；PETSc MUMPS package 可用。
- 输入：公共 `run_case.py --validate-only` 成功；除唯一 run ID、assembly backend 和 direct solver profile 外，其余解析配置与原示例一致。
- 测试：3 项 Task44 定向测试通过；Ruff 与原 HEAD 同路径比较新增 0 项（两边各有 77 项既有诊断）。
- 下一步：提交并推送到 `task44_sixlayer_surrogate_0p7nm`，以 clean HEAD 重新绑定后做 fresh dynamic idle CPU、邻任务、内存 reserve、swap、ABI 与 MUMPS preflight。全部 Gate 通过才启动唯一 P6 A；失败时保留真实资源 Gate 分类，不改物理条件或资源限值。

截至本版，P6 正式 A、B/C/D、网格/DtN/上边界精度对照、训练集、开发验证集、最终盲测集及 GP 均为 `not_run`。无任何代理精度或标准尺寸结论。
