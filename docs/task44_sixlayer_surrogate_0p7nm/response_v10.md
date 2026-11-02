# Task44 Response v10：owned-member 复核修复与 v2 训练样本登记

## 本轮范围

本轮修复 CPU 邻居监控器在短进程退出竞态中的身份复核，并将已完成的 train_008、train_009 运行状态登记到结果文档。数值方程、离散、边界条件、solver 和冻结输入均未改变；没有重算 train_007/008/009，也没有启动 PDE。

## 监控器改动

同一轮 owned-member 复核中，完整 candidate 检查最多会执行 4 次有界 systemd identity 查询，最多 3 次尝试，因此上限为 12 次查询、每次 0.25 s，即最多 3 s 的**systemd 查询等待预算**，另加本地检查和调度耗时；这不是总 wall-time 的硬上界。证据新增每次查询耗时、累计查询耗时、次数上限和等待预算。

若已读到 MainPID/Invocation、PID start ticks、cgroup 或 affinity 冲突，监控器立即 fail-closed；后续 systemd 查询超时不能覆盖已确认的漂移。candidate recheck 已确认 PID 重用、cgroup 漂移或 affinity 改变时，也会保留该冲突状态，不会因随后 identity query timeout 转入 retry。

## 测试与原生宿主生命周期核验

| 检查 | 结果 | 范围 |
|---|---|---|
| 原生 ABI preflight | `pass` | Task44 marker=1；Python 来自项目 venv；PETSc complex128/int32；MPI1；原生 Basix、DOLFINx。 |
| monitor 定向回归 | `11 passed, 63 deselected` | 覆盖固定查询 timeout/retry、耗尽 fail-closed、漂移后 timeout 不掩盖、PID reuse/cgroup/Invocation hard negatives 和 zombie fixture；未运行 74 项完整文件。 |
| 补充终态 selector | `2 passed, 72 deselected` | `test_train_007_transient_assembler_exit_uses_one_fresh_context_query` 与 `test_owned_candidate_exit_during_bounded_gap_recheck_is_nonfatal`。 |
| Ruff / compileall / diff | `pass` | 仅对本轮 service 与定向测试文件运行。 |
| 实际 systemd/cgroup 生命周期 | `pass` | `task44-preflight-owned-member-live-20261102c.service`，Invocation `bf0f3de01961467588a85bbd394ee776`，MainPID `452651`、start ticks `350722982`，CPU2，4 GiB MemoryMax、swap cap 0；seccomp 对 `sched_setaffinity` 返回 EPERM。 |

真实 unit 运行了 Task44 的 `_verify_filtered_unit` 与 `_cpu_neighbor_gate`，候选快照由真实 `_numerical_processes()` 读取，systemd 身份、`/proc` 与 cgroup membership 均未 stub。自然退出且已 reap 的 PID `452657` 被复核为 `gone`，systemd identity 查询 1 次。父进程保留的 PID `452664` 被真实观察为 `Z` 且不在直接 cgroup 成员列表，production gate 返回 `confirmed_zombie_exit`；随后父进程 reap 该 child。两种状态期间 service Invocation/MainPID 保持不变；child 清理后的 gate 通过。`systemd-run --collect` 以 exit 0 完成，unit 和 cgroup 已清理；没有启动 solver 或 PDE。

持久化 evidence 位于 ignored 目录 [`live_host_validation_20261102`](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/live_host_validation_20261102/)，其中包含原始 receipt、精确 harness、命令、source-file hash 关联和先前两个 harness 失败记录。receipt SHA-256 为 `5c7826a9251214f4b02eb77dfde2e5e63b373bace6339cdc2e3b0eab68d74e6f`。receipt 是在 monitor-fix commit 前生成且本身没有 source SHA 字段；附带的 validation context 明确记录这一点，并将当时验证的 service 文件字节 hash 关联到其后获批的 commit，不声称 receipt 原先包含该 SHA。

## train_008 / train_009 结果登记

| 样本 | 状态 | 数值与资源边界 |
|---|---|---|
| train_008 | `MONITORING_FAILED / not_run`，无训练标签 | service `5026.268644832075 s`。GNU `as` PID `442705` 初始两次 `/proc` 读取保持 start ticks `350497372`、同一 Task44 cgroup、state `R`，但两次 direct `cgroup.procs` 均不含该 PID；之后有界复核两次确认 `/proc/442705` 已消失且成员仍缺失。最后一次 systemd context 查询仅有 `0.0019582887180149555 s` 请求预算而超时；整轮复核耗时 `0.050792000256478786 s`，以 `deadline_expired` 结束。候选子进程退出码及自然/信号退出原因未知。worker exit `-9`，后代清空，任务 swap peak `0 B`；没有 full true residual、能量闭合或 official R/T/A。详见 [training_results_v2.md](outcomes/training_results_v2.md) 和 ignored [terminal audit](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/terminal_audit_008.json)。 |
| train_009 | `qualified_v2_training_label_with_post_completion_monitor_failure` | 固定 v2 离散模型的数值 worker exit `0`；160 行模态功率独立聚合、模式身份与幅值核对、官方结果、full true residual `8.566954013563746e-10` 和能量闭合误差 `1.7128520823916915e-12` 均通过。watchdog 在 manifest 结束 `0.256415 s` 后将 zombie wrapper 分类为 `MONITORING_FAILED`；保留数值 worker 与外层 service 两个状态。service wall `5351.293956477661 s`，cgroup peak `13,871,992,832 B`，swap 0，后代清空。详见 [training_results_v2.md](outcomes/training_results_v2.md) 与 ignored [post-completion audit](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/postcompletion_review_009.json)。 |

`sample_design_v2.json` 保持不变，仍保留计算前冻结计划及原字段。原始 train_009 数值输出 [run_summary.json](../../results/task44_sixlayer_0p7nm/task44_train_009_v2__full3d_direct__mpi1__Mna/20261101T231624.067994Z/numerical_output/run_summary.json)（SHA-256 `24279639828931b6c2387e87a4bfc1364e9772f7e369833feb89e89ec9ba15e4`）记录 `validation_role="numerical_sanity_only"` 和 `physical_benchmark_candidate=false`；hash-bound 的独立 [post-completion review receipt](../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/postcompletion_review_009.json) 中 `generic_flags_preserved` 子对象仍为 `null`，保留该 receipt 原样，通用值以原始数值输出为准。这些宽泛标记不独立决定 Task44 固定离散训练标签资格。train_009 标签只针对冻结 P6 离散模型，不证明连续解精度、全厚度范围准确度或 GP 泛化/盲测精度。旧版 A–D 的 y/顶部空气稳定性结果仅适用于旧版冻结字段；v2 的 train_005/006/009 资格保持有效，v2 D 仍因生命周期证据缺口而 held，不是因旧版空气稳定性结果。

## 分支与证据状态

- 执行分支：`task44_sixlayer_surrogate_0p7nm`
- monitor-fix commit：`89d998f6ec79ce1d71a82edbf88752ed8dfc4920`
- 本 commit 的 merge-base (`origin/master`)：`438caf150439343ee7c4c58ad7e02a3da812a23c`
- monitor service 文件 SHA-256：`82ce678ac68761883c15a1bbc3b1ac73d27b0b9ec4c98068931878f2e729977c`
- 定向测试文件 SHA-256：`f7668cca31da0e0525643d80efe6ca50bcf9059738602dbd6548ae30cb990c34`

本响应记录代码与结果登记的当前阶段；train_010/train_011 的材料化、公共验证及正式 service 状态将在之后的响应中按实际证据更新。
