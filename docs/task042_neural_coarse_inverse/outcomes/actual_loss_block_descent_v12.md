# V12：固定输出头的真实方程损失与有界隐藏层试验

本页解释 [Review V9](../review_report_v9.md) 的 T0→T4 实测。三维缺口 micro 固定为 0.7 nm、384 个六面体单元、Nédélec p3、双 Floquet 与上下各 20 个原 DtN 复端口，Si 来自仓库 canonical 用户材料表。它只有少数波长跨度，不是最终非可分 0.7 nm 目标规模，也没有证明 48 小时内目标模型可解。

## 为什么本批改用固定头

V11 的输出层是一个 1560 维复线性头；它对当前随机隐藏表示做了稳定 QR/GELSD 后，实际网络与薄模型仍有约 `4e-8` 的残差差，未过精确变量投影所需的 `1e-8` Gate。本批保留该失败，以 V11 唯一修正后的**物理**网络、头和端口作起点。固定输出系数 `γ` 时，隐藏参数 `ψ` 的真实损失定义为原凝聚方程与精确端口闭合后的

```math
J(\psi;\gamma)=\frac{\|\bar b-\bar S t_{\rm net}(\psi;\gamma)\|_2^2}{2\|b\|_2^2},\qquad
\alpha=H^{-1}(b_p-Ft_{\rm net}).
```

其中 `t_net` 是真实 CPU FP64 网络经 q15 原 Nédélec 边／面矩、方向与 MPC 映射得到的 trace；端口随每次 trace 重算，不冻结，也不删通道。偏导通过 `\bar S^H` 和原 batch8 VJP 计算，不假设线性头驻点，不自动对 QR/SVD 建图。`set_hidden` 会清零输出层，因此每次隐藏赋值后重新写入同一 `γ` 并校验 hash。候选不读取目标准确解，旧 REF7 只在 T4 验证阶段打开。

| 阶段／Gate | 实际原值 | 分流 |
|---|---|---|
| T0 身份 | physical `2b532f…e6de`、mode `93795b…262`、packet `9196ed…6454`，原完整 40 端口；V11 修正 state/hash 核对通过 | 不重建 FE、旧 teacher、原 V7–V11 campaign |
| T1 M2 向量残差差 | 网络回写 `6.27733e-8`；`Pγ` 对 `Zc` `4.05754e-7`；原作用对薄列 `1.84025e-12`；自身制造 RHS | 只诊断，旧 M2 严格回收仍 FAIL |
| T1 物理向量残差差 | `3.80478e-8`／`2.36230e-7`／`1.04273e-12`；本模型原物理 `b` | 不把范数相加成向量等式；T2 独立继续 |
| T2 同点完整函数值 | batch8 `0.3181799855089551` 重复相同，batch1 `0.31817998550895316`；`delta_eval=2.22045e-14` | 函数值可分辨，准入真实 FD |
| T2 复数小试验 | 非 Hermitian、非零端口、故意非最优头：解析／中心差分相对差 `1.393e-9` | 只证明小链式代数；不替代物理方向 Gate |
| T2 三条真实方向 | 最小 `h=1e-7` 时相对差 `0.06346`／`0.07599`／`0.17425`，均大于 `1e-5`；无相邻稳定区 | `FIXED_HEAD_PARTIAL_GRADIENT_NOT_QUALIFIED`；不称精确VarPro |
| T3 | 接受 hidden 步 `0`、头建议 `0`、新 P/A 构建 `0` | `NOT_RUN_DEPENDENT_T2_GATE`，不是训练已被证伪 |
| F | 两方向×正负×两步长=8 次；最小真实损失 `2.804607898`＞起点 `0.318179986`，native `0.918466063`＞起点 `0.309359507` | `FUNCTION_ONLY_POLL_NEGATIVE`，无接受状态；不重试新 seed |
| T4 | 只验证初始冻结状态；Schur/native `0.797721738/0.309359507`，散射 E/curl `0.734256809/0.734361587` | 原方程、同离散场及研究正信号全未通过 |

T1 的三段差分别是同一残差向量的**差向量**范数，分母均为该问题自己的完整 RHS；只有向量重组等式可以相加，范数不可以。重组缺陷 0、齐次恢复约 `8.7e-17`，原 `S` 作用与旧薄列组合的独立误差约 `1e-12`；主要可见差在敏感输出坐标及网络回写。它们远小于物理 residual `0.798`，不能把浮点分账直接宣布为整个平台根因。[完整 T1 两项及首次受影响失败](records/roundoff_decomposition_v12.json)。

真实 FD 信号远高于测得的同点分辨率，却在 Review 规定的步长表内没有稳定区；这与大头系数约 `1.28e5`、扰动曲率很强相容，但目前无法从该结果单独排除真实 VJP 链误差。无可信 T2 梯度，按合同只允许一次有限 F poll，不能用普通 Adam/L-BFGS 绕过。八个 F 试探全部使损失上升；后续不把调小步长、扩大网络或再次试 seed 混成本批。[实际解析值、差分步长表与 F 成本](records/fixed_head_gradient_checks_v12.json)、[逐事件进度](records/block_descent_progress_v12.jsonl)。

## 原方程、真实场与物理量

| 量与原门限 | 冻结物理起点／原始值 | 结论 |
|---|---:|---|
| 原 Schur/native/增广相对残差，各 `≤1e-6` | `0.797721738 / 0.309359507 / 0.309359507` | 三项 FAIL |
| 端口固定 RHS 相对残差 `≤1e-6`；恢复 `≤1e-10` | `2.05092e-19`；`6.10374e-13`，slave-zero 0 | 局部 PASS，不能代替原方程 |
| total E/scaled-curl 同离散误差，各 `≤1e-4` | `0.0768362 / 0.0768486` | FAIL |
| scattered E/scaled-curl 同离散误差，各 `≤1e-4` | `0.734256809 / 0.734361587` | FAIL；背景主导的 total 场不能遮盖散射遗漏 |
| selected E/H、完整 40 复端口误差，`≤1e-4` | `0.0855310 / 0.0669867 / 0.0494152` | FAIL |
| `R_total/T_total/A_balance/A_volume`；能量闭合 `≤1e-5` | `0.0849663/0.798046/0.116988/0.00485487`；闭合 `0.112133` | `UNQUALIFIED_DIAGNOSTIC`，不发布 official 结果 |

T4 只在求解队列冻结后读原同 mesh/p3 参考 hash `a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355`。没有新参考 LU、p4 enrichment、完整 S/CSR 或 global p4 factor；参考未回传 T1/T2/F。只有一个候选状态，前后 `rho` 都是 `0.797721738`，无法称神经增量。完整 40 项复振幅和相位、体吸收、功率差与原审核保存在 NN-Lab ignored artifact，入口及 hash 见[run index](records/run_index_v12.json)与[紧凑 Gate](records/qualification_and_dispatch_v12.json)；[逐项复通道CSV](records/channel_observables_v12.csv)保存当前未资格化状态的原键、极化、参考面和实虚部，并经旧相同状态逐项核对。

## 受控共享资源、失败费用和边界

| 执行 | 监督 wall s | 同时采样树 RSS 峰 B | 状态 |
|---|---:|---:|---|
| T1 首次 | `15.681` | `1012584448` | 子进程旧线程探针附带 MPI 初始化遭沙箱 socket 拒绝，T1 `PARTIAL`；原证据保留 |
| T1 第二次 | `57.084` | `2253393920` | 纯 QR 已完成，进度事件参数名冲突，worker failed；原证据保留 |
| T1 最终 | `57.582` | `2322427904` | T1 两 RHS 完成，6 次原 S，复用旧 P/A |
| T2／F | `38.398` | `749621248` | 42 完整 loss forward、30 FD 点、1 VJP、8 F 试探、4 原 audit；0 接受步 |
| T4 | `13.523` | `554733568` | 仅 1 冻结状态 FE 验算；不重新求解参考 |

五次监督 wall 合计 `182.268 s`，不是阶段嵌套计时相加。全批最大同时树 RSS `2322427904 B≈2.163 GiB`，own swap0；CPU0 本轮实时选取，无 SMT 忙核重叠记录，MPI1、BLAS/OpenMP/Torch线程1，DataLoader0，自有锁、nice10、idle I/O、隔离缓存和结果。保留 128 GiB 邻增长与系统 reserve，50 GiB 磁盘门；无 cgroup 委派，0.5 s 采样 watchdog 不冒充连续内核 hard cap。五次任务后代均由自身 supervisor 清场，邻任务及其锁／环境／亲和性／watchdog 未修改。无持续 PSI 压力信号；没有相匹配的邻任务阶段样本，影响和无争用加速均 `INCONCLUSIVE shared-workstation`。旧 V6–V11 有载下界照记，正式费用下界增至 `11916.413697 s`，开发、测试与未独立计时辅助费仍未补造。[资源原口径](records/resource_costs_v12.json)。

独立 [checker](../../../src/io/actual_loss_block_descent_check.py) 对 raw T1 残差等式、三方向 FD、冻结 gamma/hash、原方程、完整复通道与功率重算；其 `PASS` 只表示**记录自洽**，同一输出明确 `fixed_head_gradient_qualified=false`、`same_discrete=false`。坏解析梯度、gamma 改变、假下降、端口错误、缺通道的反例已测。由于本批没有接受 hidden 试探，每个未接受 FD/F 点只保留了实际 loss 与协议内的固定头写回路径，未单独保存各 trial 网络向量；checker 无法对每个试探作离线独立向量重算，这一边界不应被记录自洽误写成完整数值资格。

唯一下一建议：另经 review 授权后，对**同一冻结头和同三方向**做一次解析 JVP/VJP 及原算子线性化配对，以确认 FD 不合格源于强曲率／浮点尺度还是导数链；本批不实施。旧 p4 强逆路线、短波／更大模型、网络／步长扫描、目标参考拟合均未开启。
