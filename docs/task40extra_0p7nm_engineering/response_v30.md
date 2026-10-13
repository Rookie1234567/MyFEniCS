# Response V30：Ny=8 目标试跑受控停止，完整 PDE 未完成

本轮有5次早期入口失败，最后一次正式服务实际进入 FE/编译；没有追加第二次数值运行。冻结数值源码为 `1e9109cb62343b13c850da03432def2109fee481`。服务在时间门限处受控停止，没有 OOM，也没有官方 R/T/A 结果。

| 项目 | 状态 | 证据边界 |
|---|---|---|
| V29 q0 reference | ACCEPTED legacy evidence | 两个旧 RHS 残差 1.9776283e-14、1.6069610e-14 ≤1e-10；旧 factor 已释放，V30 未重建。 |
| V30 q0–q7 新资格 | 0/8；NOT_RUN | 没有本轮 q-pattern/CSR/native 资格文件。 |
| 原尺寸 Ny=8 pilot | PARTIAL_WORKER_ATTEMPT | service 已启动；最后持久阶段为 preflight。运行观察到编译与 Python FE/JIT 活动，但没有持久收据证明 FE/MPC setup 完成。 |
| 因子库、完整 action、全空间 residual | NOT_RUN / UNKNOWN | 没有逐 q 阶段或计数收据；因子、MatSolve 数为 UNKNOWN。 |
| 官方物理输出 | NOT_RUN | 没有通过 residual 与物理 Gate 的场；R/T/A、A_volume、衍射及目标精度都未测。 |

运行身份：`myfenics-case-20261012T201214-356306.service`，run ID `task40extra_0p7nm_target_original_ny8_resource_pilot_v20`，目录 `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_resource_pilot_v20__full3d_iterative__mpi1__Mna/20261012T201216.837020Z`。ABI 为 native Linux、PETSc complex128/int32、MPI1。profile 中 30,464 cells、32,060 modes、各 q 行数是配置预期，不是本次测量结果。

最终 worker 分类为 `PERFORMANCE_CONTROLLED_STOP`，exit -9；在 SIGTERM 后等待 30 秒再 SIGKILL，后代进程已清理。树 RSS 同时采样峰值为 18,555,887,616 B，专用 cgroup 峰值为 26,902,548,480 B；它们是不同资源口径。任务 tree/cgroup swap 峰值均为 0；主机全局 swap 诊断增加 1 页但无法归属本任务。无 OOM 或 memory Gate。自定义标签 “target retained and fast backend complete” 所在资源行的真实 stage 仍是 preflight，inventory/workspace 为 0；不能据此声称目标已构建。空库存也不能排除未持久化的短暂 native allocation。

T0 为 2026-10-12 12:23:42Z，数值截止 2026-10-13 00:03:42Z，总截止 00:23:42Z，均未刷新。最终 launcher 观测的连续 campaign 父账累计 42,033.09600802868 秒，包含准备、早期失败、审计和最终 service；service 子时长 13,918.292 秒不重复加总。截止后的 required-checker supervisor 报 TimebaseInconsistency；另一次只读 partial-checker 用时 0.202125 秒、return 2、NO_PARTIAL_FOOTER、checker_passed=false。两个失败都按原样保留，第二项也不是数值或 FE 重跑。

之前的 preparation/route 失败也保留：service `180401-344369`（无 launcher result object）、`182719-346141`（约 1.87 秒退出且无 partial footer）、`190848-350143`（无 launcher result object）、`191843-351626`（约 6 秒且无 partial footer）、`195057-353069`（约 6.6 秒且无 partial footer）。这些是准备/路由/checker 失败，不代表 PDE 数值失败，也不代表求解成功。

执行者不提交推送；主控负责审查并集中提交。此次 closeout 不改数值源码、不重跑 FE/PDE 或pytest。主控独立审计见 [controller audit](outcomes/records/review_v30_controller_audit.json)（SHA-256 `588f5476552fa3dfdaf2e517e6ab8bcc0400b580ac97c98fbb1bac2cd2cc074f`）。紧凑证据见 [q/operator](outcomes/records/target_operator_probe_v30.json)、[reference qualification](outcomes/records/reference_qualification_v30.json)、[time/resource](outcomes/records/time_resource_accounting_v30.json)、[pilot](outcomes/records/target_pilot_v30.json) 与 [artifact inventory](outcomes/records/v30_run_artifact_inventory.json)。

主控补充：实际批准cap为1649267441664B，host reserve68719476736B，PSS关闭记null。旧q0 COMPLETE/native、旧factor销毁和本轮live bank未完成分列。[真实交接](outcomes/handoff_v30.md)与[测试/失败记录](outcomes/test_summary.md)列出下一次q4独立CSR/native、逐twist生产、完整bank/reference/target的真实依赖；本窗不重启。内部细分JIT/owner/q构建耗时缺原子边界，保持UNKNOWN，不将13918s全部归因给JIT。原尺寸工程pilot的网格/mode精度与2TB/48h冷流程均未资格，不合并master。
