# Response V12：固定头真实损失偏导未取得数值资格，函数值备选为负

按 [Review V9](review_report_v9.md) 执行 `V12_ACTUAL_LOSS_BLOCK_DESCENT`。本批没有放宽 V11 的 M2 制造回收 `1e-8` Gate，也没有把旧实际输出头 Gate 改写为通过。新方法的目标是：暂时固定网络输出层的复数系数，只改变隐藏层，使用原有限元方程及完整 40 端口求得真实残差损失；每一步是否保留由实际网络重新前向和原方程审核决定，而非薄矩阵的预测。与精确变量投影不同，这个普通偏导不需要当前输出头达到驻点。

| 身份与阶段 | 实际情况 |
|---|---|
| 执行分支／工作树／upstream | `task42_neural_coarse_inverse`；`/home/fenics/Projects/NN-Lab` canonical linked worktree；`origin/task42_neural_coarse_inverse`。冻结 base 为 `ccd357885f7f9be84efe3be07868cc94f13d93fc`。最终文档 HEAD 以推送后 Git 报告为准，不能代替下述运行源码。 |
| Review／真正运行源码 | Review V9 `f81e9301d98c7e0a7006ae34981ecc27e11dd2dc`；三个成功 one-run 的 clean source 均为 `d9df7068ca3310a0499164251a57841dbdfbc7f5`。两次受影响 T1 尝试分别绑定 `e35ebd40c598a7f7db7a45fb403ff754661cd698` 和 `74f4a6a42f9525d0c21982d5c0b227e355a7d92e`，失败证据保留。 |
| 物理与环境 | 原 0.7 nm、384 hex、Nédélec p3、Si canonical 材料、q15 矩、双 Floquet/DtN、上/下各 20 个复端口；物理 hash `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`、action packet hash `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454`。CPU0 为本轮现场选核，MPI1，数学/Torch线程1，DataLoader0，GPU0。 |
| 实际路径 | T0 身份与资源通过；T1 有界分账完成；T2 函数值重复性通过、真实有限差分不合格；T3 按 Gate 未运行；F 固定头 8 个函数值试探均未改善；T4 冻结后独立 FE 验证一个状态。 |

T1 对既有 M2 和物理状态分别比较网络真实 trace、`Pγ`、`Zc` 与旧薄列组合。物理 RHS 的三段残差向量差相对量依次为 **`3.80478e-8`、`2.36230e-7`、`1.04273e-12`**；M2 自己制造 RHS 的对应量为 **`6.27733e-8`、`4.05754e-7`、`1.84025e-12`**。向量重组缺陷为 0；齐次恢复配对约 `8.7e-17`。这些是各段向量范数，不能把三数直接相加；M2 使用自己的完整 trace＋port RHS，未覆盖物理 `b`，且没有重新构造 1560 列 `A`。[原值与两次失败证据](outcomes/records/roundoff_decomposition_v12.json)。这说明旧头坐标的浮点敏感性可见，**不**证明原方程残差平台已经由此解决。

T2 实际网络在同一组非零输出系数下，batch8 两次原损失均为 `0.3181799855089551`，完整 batch1 为 `0.31817998550895316`；`delta_eval=2.22045e-14`，trace 相对差 `1.387e-16`。复数非 Hermitian／非零端口／非最优头小测试的偏导相对差 `1.393e-9`，固定头链式法则成立。**但真实 8576 维隐藏参数的三个预登记方向都不满足 Review V9 有限差分稳定区条件。**在规定最小 `h=1e-7`，解析值与中心差分的相对差分别 `0.06346`、`0.07599`、`0.17425`，远高于 `1e-5`；信号分别为 `delta_eval` 的约 `2.28e4`、`3.04e4`、`1.88e6` 倍，因此不能简单归为不可分辨噪声。30 个扰动点、1 次 VJP 均已计费。[完整步长表](outcomes/records/fixed_head_gradient_checks_v12.json)。这不等于证明解析 VJP 错误，亦不允许绕过 Gate 把它用于 L-BFGS。

按合同的 F 备选使用同一物理起点、固定头和精确端口，两个预登记方向的正负号及两档步长共 8 个**实际**损失试探。最小试探损失 `2.804607898`，高于起点 `0.318179986`，native 从 `0.309359507` 恶化到 `0.918466063`；**0 个状态接受，0 次隐藏更新，0 个块末头建议**。因此 T3 是 `NOT_RUN_DEPENDENT_T2_GATE`，不是“执行隐藏训练后失败”；F 是已执行的负结果。旧 V11 的严格头资格仍为 FAIL。[进度与候选](outcomes/records/block_descent_progress_v12.jsonl)、[头建议](outcomes/records/head_proposals_v12.json)。

T4 在求解队列冻结后、独立 FE 进程才读取原 REF7。唯一状态的原 Schur/native/增广残差为 **`0.797721738 / 0.309359507 / 0.309359507`**，相对严格 `1e-6` 均失败；固定 RHS 端口 `2.051e-19`、恢复 `6.104e-13` 和 slave-zero 仍通过，但不能代替整方程。散射 E L2/scaled-curl 同离散误差 **`0.734256809 / 0.734361587`**，相对 `1e-4` 失败；完整 40 复通道误差 `0.0494152`，能量闭合 `0.112133`。当前 `R_total=0.0849663`、`T_total=0.798046`、`A_balance=0.116988`、`A_volume=0.00485487` 仅是**不合格场诊断值**，不是 official R/T/A。研究正信号与 micro 有限元资格均否。[原方程与场CSV](outcomes/records/candidate_comparison_v12.csv)、[逐项40复通道](outcomes/records/channel_observables_v12.csv)、[独立 Gate](outcomes/records/qualification_and_dispatch_v12.json)。

总窗口仍从 `2026-09-30T00:58:28.832520Z` 起算，不因修复或上下文压缩刷新；成功 T1/DESCENT/VERIFY 的监督 wall 分别 `57.582 / 38.398 / 13.523 s`，加上前两次 T1 尝试 `15.681 / 57.084 s` 后，本批正式监督 wall **`182.268 s`**。全批最大同时采样进程树 RSS **`2322427904 B`（约 2.163 GiB）**、自身 swap0，低于 12/16 GiB 警戒／停止线；五次运行后代均已清场。原有 V6–V11 有载下界 `11734.145535666961 s` 加本批正式监督 wall，为可核对的 **`11916.413697 s` 下界**，历史辅助费用仍未知，不能称精确累计。本批共享工作站 CPU 运行，未见持续 memory PSI 压力；没有邻任务可比阶段指标，不宣称零干扰或无争用加速。[逐次 source/CPU/资源](outcomes/records/run_index_v12.json)、[费用口径](outcomes/records/resource_costs_v12.json)。

候选从未构造 global p4 LU、完整全局 `S`/CSR、ILU/Riesz 或隐藏逆；T1 仅复用旧薄 `P/A`，T2/F 仅原 action packet 与 40×40 `Hhat`，T3 未发生新 `P/A` 构建。旧 p4 强逆路线持续关闭。独立 checker 从 raw 字段重算 T1、有限差分、冻结状态、原方程与 40 通道，结论为 `PASS`（证据一致）、`fixed_head_gradient_qualified=false`、`formal_micro_qualification=false`；`PASS` 绝非 solver PASS。最终相关 pure-array／watchdog **26项通过、1项ML专属测试排除**，ML 单线程与实际输出头重写断言另通过；`compileall` 和 dat validate 通过。未安装 Ruff、ML 环境未安装 pytest，均不伪称通过；GitHub Review V9 实际网页渲染尚未取得，发布检查单列。[测试和限制](outcomes/test_summary.md)、[详细结论](outcomes/actual_loss_block_descent_v12.md)。

唯一下一建议，**未在本批实施**：若下一 review 授权，对冻结的同一固定头和这三条方向做一次解析 JVP／VJP 配对及原作用线性化核对，以区分大输出系数造成的有限差分曲率与真实导数链路错误；在厘清前不继续隐藏层训练、改阈值、扩大网络或启动最大 0.7 nm 模型。本批只提交并推送执行分支，停止等待审阅，不合并 master。
