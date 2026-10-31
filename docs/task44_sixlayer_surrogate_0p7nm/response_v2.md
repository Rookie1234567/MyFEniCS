# Task44 执行响应 v2：切换凝聚直接求解路线

## 本轮裁定与范围

本响应承接 `response_v1.md`。用户在主控复核后批准：保留六层物理与完整端口模型，将正式样本 A 从完整全局矩阵路径切换为装配期静态凝聚，再由直接 LU 求解缩减系统。静态凝聚先在每个六面体单元内消去单元内部自由度，拼装较小的边界/迹自由度与 DtN 端口系统，求解后再恢复完整场；它减少全局矩阵装配与存储，但增加局部因子、缓存及恢复步骤，P6 的时间和峰值内存仍须由正式运行测量。

Task44 实际起点是 `db790f92a186988c5147f1828d15c07034e7c430`。本轮修改前 HEAD 为 `101b19e0b7e99ad9f608c532fa4ceca450fecba6`；`438caf150439343ee7c4c58ad7e02a3da812a23c` 只是当前 `origin/master` 的 merge-base，不替代 Task44 起点。代码和新输入提交后的精确 SHA 由同一 ignored evidence 目录的 provenance 记录绑定。

## 旧 A 的受控停止

| 对象 | 状态 | 原始事实 |
|---|---|---|
| 原 `sample_A`，P6 / 144 六面体 / `standard_full` | `controlled_stop`，无数值结论 | service `task44-sample-a-dynamic2.service`，Invocation ID `a8c344fee90d459899cbad5785880a3b`；最终报告 8433.239279829897 s；watchdog exit `-15`；停止后 service cgroup 与已记录 PID/start_ticks 均清空 |
| systemd 单元终态 | `failed` 原样保留 | `Result=exit-code`、`ExecMainStatus=1`；watchdog/attempt 分类仍是用户要求的 `USER_CONTROLLED_STOP`，不能改记为求解器数值失败 |
| 物理结果 | `not_run` | 最后进度记录仍在 `stage4_full3d_assembly_backend`；旧 `run_summary.json` 仍是 `launching / not_run / null`，没有 full residual、R/T/A 或 `A_volume` |

停止凭据：`benchmarks/artifacts/task44_native_services/task44-sample-a-dynamic2.service/user_controlled_stop.json`。原始日志和资源快照均保留，未覆盖或重写。

## 新 A 输入与实现

新增 `input/task44_sample_a_condensed_direct_v1.dat`。它从原六层示例派生，只修改唯一 `run_id`、`assembly_backend=assembly_time_static_condensed` 和 `direct_solver_profile=mumps_exact`。几何、六个层厚、材料、λ₀=0.7 nm、1° 掠角、90° 方位、S 偏振、P6、3×6×8 贴体网格、双 Floquet、完整自动传播 DtN 与 auxiliary 端口保持一致；不截断传播模态、不引入参考项目中的 V7 surface cache。

凝聚实现现对分层模型启用精确几何键、重复积分核累加、严格局部检查、共享只读 identity cache 与 dense appended block。审计中的 `cell_form_kernel_invocation_count_global_unique` 是从每个唯一材料/几何类对应的编译核映射派生的结构计数，不是运行时动态计数器；本轮小算例共 14 个唯一类、144 次 cell use、130 次重复 use、14 次派生核调用。

## 定向资格与证据

| 检查 | 状态 | 结果和边界 |
|---|---|---|
| 原生 complex ABI 与 MUMPS 包 | `pass` | Task44 activation；Linux；PETSc 3.19.6 `complex128` / `int32`；SLEPc 3.19.2；MPI1；PETSc 报告 MUMPS package 可用 |
| 公共输入 adapter | `pass` | `python scripts/run_case.py input/task44_sample_a_condensed_direct_v1.dat --validate-only` 返回 `status=valid`；未创建网格或求解 PDE |
| Task44 定向测试 | `pass` | 新输入合同、六层标签/体积、P2 标准与凝聚直接等价，共 `3 passed` |
| Ruff 同路径比较 | `pass_with_existing_findings` | 原 HEAD 与当前 3 个源码路径均为 77 项；新增诊断 0 项；`git diff --check` 通过 |
| P2 完整矩阵独立复算 | `pass`，仅数值 sanity | 凝聚恢复场在 MPC slave rows 置零以表达装配矩阵代数向量后，对标准全局矩阵独立计算 `Ax-b` 相对残差 `2.4258989122760487e-12`，限值 `1e-6`；真实物理 FE 系数仍完整比较 |
| P2 场与 observable 比较 | `pass`，非正式样本 | E/H 最大绝对差分别 `5.3619e-14 V/m`、`1.6475e-16 A/m`；R/T/A_volume 差分别 `1.2213e-15`、`4.8898e-17`、`3.3087e-22`；层吸收最大差 `3.7012e-20`。该测试的 factor solver/profile 是 `petsc` / `default`，只证明凝聚算法与恢复一致，不是 MUMPS 实测 |
| 新 P6 正式 A | `not_run`（本响应生成时） | 仅在提交推送后的 clean HEAD 上，通过 fresh dynamic CPU、邻任务、资源、filtered ABI 与 service preflight 后启动；官方运行必须记录实际 factor solver 和 MUMPS control readback，不允许把配置请求当作读回证据 |

测试写出的精确独立 residual、run summaries、scientific field NPZ、ABI preflight、输入/源文件哈希收录于 ignored artifact：`benchmarks/artifacts/task44_condensed_direct_validation_20261031/`。P2 用例是 144-cell 的 P2 numerical sanity fixture，不构成 P6 性能、标准尺寸或代理精度资格。

## 下一步

按用户授权，将本响应、outcomes、三项源码修改和独立 P6 输入作为一个普通提交推送至 Task44 upstream；以 clean HEAD 重新绑定输入与证据。随后使用现有 `scripts/start_task44_native_sample.sh` 唯一启动 `task44-sample-a-condensed.service`。保留 128 GiB cgroup cap、384 GiB host reserve、至少 8 GiB job buffer、零 task swap、MPI1、单数学线程及动态 CPU/邻任务检查；运行不设时钟强停。新样本的实际因子后端、控制读回、stage、wall time、cgroup/进程树峰值与 R/T/A/residual 在运行证据中单独记录。
