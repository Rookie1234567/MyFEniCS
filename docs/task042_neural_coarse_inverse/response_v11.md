# Response V11：稳定头大系数回收未过 Gate，隐藏更新未准入

按 [Review V8](review_report_v8.md) 完成 S0、S1、S2 的实际稳定性与物理基线计算；S1/S2 经唯一同分解修正仍未通过，故 S3 真实变量投影 FD 与 S4 隐藏更新按合同停止。求解队列冻结后，独立 S5 读取旧同mesh/p3参考，确认完整原方程与散射场负结果。本批不是“固定空间未达研究正信号所以不准训练”；阻止训练的是**制造回收及实际线性头的数值 Gate**。旧 V1–V10 全部负结果、task/review/response/raw 不改。

| 身份与边界 | 实际记录 |
|---|---|
| worktree／branch／upstream | `/home/fenics/Projects/NN-Lab`；`task42_neural_coarse_inverse`；`origin/task42_neural_coarse_inverse`，canonical linked worktree common Git dir `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`。最终完整 HEAD、ahead/behind 以推送后的 Git 与最终答复为准；本文不在自身内容中伪嵌将来文档提交SHA。 |
| 接手／合同 | 从被审 V10 HEAD `6246b525077779e2f9a538beff3af9df70bdb8bf` 安全快进至 Review V8 `38a68de138fc01537dc8a63f122e25c64b820a37`；冻结 base `ccd357885f7f9be84efe3be07868cc94f13d93fc` 与初始任务提交 `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7` 为历史祖先。 |
| 运行时实际源码 | MAIN `a2cba71533edafb4fa1c701eae503e7ab526eac4`；一次同分解 REPLAY 与独立 VERIFY `036e36ec637488b1baddd9b061c80c6f34cde254`。三份 dat/input/source/数组/hash/资源见[run index](outcomes/records/run_index_v11.json)。checker 源码另为 `c6c650ad18f278aa1a33cddd9395f899104b3bc2`，不冒充运行源码。 |
| 固定模型 | 0.7 nm、384hex/p3、Si canonical user-supplied 表、原双Floquet/DtN，上20＋下20复通道；full FE34050、trace18144、内部13824、slave2082。原 physical/mode/action SHA 与 review一致，见[输入身份](outcomes/records/plan_and_input_identity_v11.json)。 |
| 新路线与所有权 | 只用 seed420906 随机隐藏、原q15矩映射、economic QR、原S逐列重算 `A=barS Z`、固定 `gelsd/cond1e-12` 与40维 `Hhat` 端口闭合；输出头写回真实 Torch 网络。无 global p4 factor、完整S/global CSR、ILU/Riesz逆、正规方程或 hidden fallback。 |

小系数 M1 的稳定头原制造 RHS 相对残差 **1.23470e-14**≤1e-8、已知 `z` 差 **5.53650e-13**≤1e-6、齐次恢复配对 **9.25845e-17**≤1e-10；raw 头也通过，不能归为稳定坐标独有收益。V10-B0 大系数 M2 的 raw／初始稳定残差分别 **1.29159e-7／3.11751e-7**；同一已验 `A` 仅一次残差修正到 **2.89518e-8**，仍高于1e-8。制造 `b_m` 由**原 action.apply(已知 z)** 得到，包含非零 trace/port RHS，绝不覆盖物理 `b`；参考场和D1参考拟合未进入求解。[全部数值与hash](outcomes/records/manufactured_recovery_v11.json)。

`P`、`A` 均数值 rank1560/1560；这只证明按冻结阈值满列秩。`P` 奇异端点约8.028e-10与20.200、比值约2.52e10；`Hhat` cond13284、端口配对通过。实际物理网络回写 trace 与 `Pγ` 相差2.461e-11，但修正后的**实际网络残差对薄LS预测差 3.95983e-8＞1e-8**；`Uᴴr` 为9.6224e-9，只是另一项通过。数值满秩、单个驻点数小或相同空间 `Zc` 较好，都不足以授予真实 head Gate。[输出头检查](outcomes/records/stable_head_checks_v11.json)。原 V10 raw 的过强“exact optimum”字段只解释为数值满秩，新字段没有重复该声明。

| 物理基线／原门限 | 修正后的实际值 | 结论 |
|---|---:|---|
| 原Schur／native；各≤1e-6 | **0.797721737837／0.309359506591** | 两项失败；port固定RHS为2.051e-19、恢复6.104e-13／slave-zero0分别通过，不代替整方程资格 |
| total E／scaled-curl 同离散相对差；各≤1e-4 | 0.0768362／0.0768486 | 失败 |
| scattered E／scaled-curl 同离散相对差；各≤1e-4 | **0.7342568／0.7343616** | 失败；不以背景主导total场掩盖散射遗漏 |
| selected E／H 与完整40复通道；≤1e-4 | 0.0855310／0.0669867／0.0494152 | 失败，完整键/极化/参考面见[通道](outcomes/records/channel_observables_v11.csv) |
| R_total／T_total／A_balance／A_volume，能量闭合≤1e-5 | 0.0849663／0.7980459／0.1169878／0.00485487；闭合**0.112133** | 仅 `UNQUALIFIED_DIAGNOSTIC`，无新 official R/T/A |

原方程真实残差平台未突破。相较 V10-B0，Hhat闭合使 native 从10.9645降到0.30936，但 V11 的Schur仍约0.7977、散射误差仍约0.734；比较条件含头算法改变与共享负载，不称因果神经收益或无争用加速。真实 VarPro FD点0、Armijo试探0、接受 hidden 更新0；不是对可变隐藏空间的失败判决。复数非 Hermitian／非零端口合成梯度小测试通过，但不替代真实 S3。[checker与分流](outcomes/records/qualification_and_dispatch_v11.json)。

S5 只在求解队列冻结后独立读取原 REF7 SHA `a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355`，FE环境一次性验算基线，未作新LU或p4 enrichment、未把参考反馈训练。大系数数值稳定性与当前固定表示／原残差目标的困难可能并存；目前无法宣布唯一根因，也不能称真实 VarPro 梯度或隐藏学习机制本批已经证伪。[完整解释和负结果](outcomes/stable_head_varpro_v11.md)。

本批 start=`2026-09-29T22:58:57Z`，heavy 截止=`2026-09-30T02:43:57Z`、总截止=`02:58:57Z`，窗口不因上下文压缩重置。三个one-run的监督 wall **426.511501414＋135.925127663＋12.543487691＝574.980116768s**；最大同时采样整树RSS **4668329984B≈4.347GiB**、own swap0，外层launcher wall总579.083391703s。事前常驻规划6092700024B＜8GiB，MAIN 的QR/S/LS成本均嵌在阶段wall中而不重复累加。V6–V10有载carry **11159.165418899036s**，加V11正式监督wall的可核对下界 **11734.145535666961s**；其余实现／测试／整理在总elapsed内，不虚构精确有载秒。[完整费用](outcomes/records/resource_costs_v11.json)。

现场核验空闲CPU0、MPI1、数学／Torch线程1、DataLoader0，独立FE/ML及缓存、自有nonblocking锁、nice10/idle I/O、16GiB hard/12GiB warn整树watchdog、swap0；只监督自身后代，均已清场。无cgroup委派，0.5秒采样不是连续内核限额。原heavy/两忙GPU未动，Task042无GPU；没有持续系统压力的现场迹象，但缺邻任务可比阶段，干扰与性能结论 **INCONCLUSIVE shared-workstation**。原0.7nm目标几何、存储、48小时可行性仍 unknown，不以微型模型外推。

最终12项相关 pure-array pytest、ML原矩小回归、compileall及独立raw-field checker通过；坏 saved status、坏场、缺通道与功率反例未误判通过。Review V8 的实际 GitHub richText 为5表／5数学块、表列一致；结果文档的发布网页核验单列，不冒称浏览器像素级检查。没有 full repository pytest、MPI2/4 或 CI 声明。MAIN 数值 `physical` 键受同名身份元数据覆盖的封装问题已在下一 clean source 修正，原 raw 不修改，原始数值由 MAIN journal 与 REPLAY before 复核。详见[测试](outcomes/test_summary.md)、[变更与选择性合并](outcomes/changed_files.md)、[渲染](outcomes/records/review_render_check_v11.json)。

**唯一下一建议，未实施：**下一 review 若批准，可针对冻结 M2 做一次同算子、同 P/A 与真实网络回写的有界浮点敏感性归因，分离薄LS、原作用及大系数回写的残差来源；保留1e-8内部 Gate、原物理标准、rank与模型规模。本轮不自动增加网络、训练预算、p4逆或最大模型。只交付 `task42_neural_coarse_inverse`，不merge master；推送后等待审阅。
