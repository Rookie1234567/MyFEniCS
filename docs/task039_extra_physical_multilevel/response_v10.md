# Response V10：V9 等新工作量复用对照收口

## 当前结论

V9 已完成 L0、L1 等新工作量 controls 和唯一授权的 L2 original。L1 的池更新、A4 配对、eps 闭合和固定 16 新 B4 记录均通过；但这项有限控制质量没有转化为完整 p6 outer 的足够进展。L2 在首个约 1800 s 的安全检查点以 `TIME_PROGRESS_SCREEN_STOP` 收口：PC38、solve `1842.2495024400364 s`、full explicit true residual `0.1292009191903606 > 0.10`。本轮登记为 `EQUAL_WORK_RECYCLE_BOUNDED_NEGATIVE`。

worker 的原始状态、独立 checker 和 launcher parent 分类并列保留：worker/checker=`TIME_PROGRESS_SCREEN_STOP`，runner=`WORKER_FAILED`、exit `4`。watchdog 清场完成，process-tree RSS 峰 `1426276352 B`，job swap peak `0 B`，global pswpin/pswpout delta `0/0`；因此这是外层数值进展不足的受控负结果，不是 OOM、swap、MPI 清场或实现异常。

正式运行绑定 source `55b7325cae8477ded7b04cfab42181f18e035a0f`、input `5d77f0f05273f04c2459aedcc581a9c5614c400104f42262e50ec6bfd70b05db`、physical `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` 和 mode `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。

## 关键证据

| 阶段 | 实测结果 | 边界 |
|---|---|---|
| L0 | clean-SHA probe `1.853111845 s` | 仅 partial；完整实现准备时间 `unknown`，不能把 reserved `3600 s` 当实测，整个 preparation Gate 无法由现存 partial ledger 完整追认 |
| L1 | 12/12 sequence I4 完成 16 新 B4，另有 4 个 complete-control I4；总 I4=`16`；6 对、5 对进入 admission；`G=0.4822327326491708`、q<1=`0.8`、qmax=`1.5802611912316964`、时间比=`1.1568289908802627` | `L1_ADMISSION_OPEN`；质量信号有效但时间收益不一致 |
| L2 I4 | 76/76 行完成 16 新 B4；B4=`1216`、A4 matvec=`1292`、explicit A4=`168` | bounded I4/screen/cost 完整校验通过；逐行标量已 compact 化 |
| L2 screen | PC38、solve `1842.2495024400364 s`、rho=`0.1292009191903606` | 超过 `0.10`，未进入 5400 s gate，未达到 `1e-6` |
| official output | `None` | E/H、near-field、R/T/A、`A_volume`、80 模式、notch/recovery 均 `not_run` |

L2 的 I4 payload peak `90099456 B` 和最终持久池 `12533760 B` 是 derived/instrumented ledger，不是完整 PDE RSS。完整逐 I4 标量 cost、terminal solution/checkpoint hash、raw artifact hash、账本和资源 authority 见 [V9 compact](outcomes/records/equal_work_recycled_p4_v9.json) 与 [V9 中心结果](outcomes/equal_work_recycled_p4_v9.md)。

L1 全六个序列行（含 admission 排除的冷启动 pair）的累计 RESET/CARRY 时间为 `96.98303711495828 s / 112.19278895820025 s`，CARRY 多 `15.68%`；冷启动及六行明细绑定在 compact 的 `sequence_rows` 中，五个有效 pair 才用于 admission。

## 比较与解释边界

复用此前求解方向，是为了把已经发现的有效子空间再次用于新 RHS，减少一部分难误差的探索；但固定 16 个新方向仍需支付更高的正交化和细化费用。`G`/`q` 是由实测残差推导出的指标，不是独立 measured 物理量。V9 PC32→PC38 的 residual 只从 `0.1312380111087104` 降到 `0.1292009191903606`，约 `1.55%`（derived），不足以支持继续投入。V5 exact-p4、V7 A、V8 和 V9 的每步成本、池策略和停止规则不同；共同 PC32 与接近 1800 s 的实际节点已在[中心结果比较表](outcomes/equal_work_recycled_p4_v9.md)中分别列出，不构成完整 solver speedup 排名。L1 的五个有效 pair 中四个 q<1，也不能推广为所有 RHS、所有 rank 或所有 recycling 都有效；同样，L2 不能证明 rank8 不足是唯一谱根因。

V5 原始/notch 的完整成功 baseline、V6/V7/V8 的历史负结果和 swap 归因限制全部保留。V9 不启动 notch、recovery、rank/参数扫描、第二候选、5 nm/0.7 nm 或 workstation heavy case；ordinary default 不变。

## 费用与文档收口

L1 外层 charge=`530.530732766 s`，L2 外层 charge=`2071.995232478 s`；不把 nested stage 重复加入。V9 batch ledger 总 charge=`2604.379077089 s` 只包括实际记录的 L0 partial、L1 和 L2 charge，不含未知的完整实现准备时间，因此不能写成包含完整 `3600 s` preparation Gate；remaining=`33395.620922911 s`。L2 runner 的 `14400 s` 是独立 reservation，不是额外 elapsed。L1/L2 raw、watchdog、checkpoint 和 ledger 均保留；不上传大型 field/matrix/factor/cache。

本轮新增/更新：[中心结果](outcomes/equal_work_recycled_p4_v9.md)、[compact](outcomes/records/equal_work_recycled_p4_v9.json)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index.json)、[test summary](outcomes/test_summary.md)、[workstation handoff](outcomes/workstation_handoff.md)、[development progress](../development_progress.md) 和 [model registry](../development_model_registry.md)。本轮只做 docs/compact 与轻量合同检查；不声称 full repository pytest、CI 或新的 PDE 通过。V9 研究 profile 不提升 production default，也不构成 `master` merge approval。
