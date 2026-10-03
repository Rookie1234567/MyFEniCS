# Response V34：真实两态完整输入诊断完成，关闭固定单步提案

按[Review V31](review_report_v31.md)连续完成修复、定点复验、唯一真实actor、独立保存数组审核及失败归因。两态原残差分别被放大至2.97739708904112和4.065825954112519倍，判定`FULL_INPUT_FIXED_STEP_INSUFFICIENT`。这次已经有可信数值结论；不再停在“软件已实现、请批准运行”。旧失败、旧closed及V23/V24完整负结果保持。

这里的校正用已有七个区域的局部解，补上旧回流漏掉的外部残差输入，再消除联合块中的反馈。希望用较少存储传播区域间信息，代价是局部因子读取、求解及原方程作用；本轮用缓存避免重新加载六套外块因子，不代表部署时这些费用消失。它是传统块方法，本轮没有神经训练。

| 身份／实际范围 | 记录 |
|---|---|
| 分支／canonical工作树 | `task42_neural_coarse_inverse`／`/home/fenics/Projects/NN-Lab` |
| base／取得合同 | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`58238a4469f36c743a9010bc92b29694c6a63728` |
| 实际诊断source | `fbc5c578e61adc670abda6f723f33192b1617e83`，运行前tracked及nonignored状态clean |
| 最终独立checker source | `a4cf9c0fc7dcb819bcbfe81559f040d5306720f6`；文档HEAD不冒充运行source |
| 物理／接口 | 原0.7nm、384hex/p3/q15、三维缺口、双Floquet、18144trace＋完整40port；用户canonical材料表不变 |
| 输入／固定系数 | 仅`V24-LZ-CYCLE4`、`V24-LCZ-CYCLE4`；复用V25六外块单位权重、V26联合块及V32回流缓存，无第11方向拟合 |
| 结果身份 | [run index](outcomes/records/run_index_v34.json)、[source与全部父状态/hash](outcomes/records/source_inventory_v34.json)、[原始日志索引](outcomes/records/raw_evidence_index_v34.json) |

## 修复与资格

checker先保留新旧残差差/原完整b≤1e-11的身份审核，再统一用已审核的保存`input_residual`计算指标；缓存单位系数、来源、支持和hash仍精确验证，没有把所有逐位检查改成近似相等。存储fixture改为明确检查旧V32已有的5B成员；V34及review_v31纳入同一事前/live/结项库存，旧默认与closed行为保持。

收费重入分别核对单次完整run及全campaign账，并保留失败summary/write-ahead原始hash。暂时资源拒绝使用不可变receipt、收费探针及120–1800秒退避，不永久封死新准入；实际本轮没有资源拒绝、等待或actor重启。所有启动都有fresh现场选核，没有采用永久CPU编号。

| 实际验证／source | 结果及费用口径 |
|---|---|
| 首次前测`79f3d5a…` | 11 passed／2 failed，监督7.912601837s。新WAIT fixture缺目录、旧反例消息匹配遗漏`full_linearity`；不是算法负结果 |
| F1最小修复后`fbc5c578…` | 13 passed，监督11.764919262s，含失败合成载荷的无损归档；编译、actual study→保存→结算→checker、非互伴完整port、残差阈值两侧、库存、closed、收费重入与WAIT通过 |
| 真实单dat actor | `python scripts/run_case.py input/task042_neural_coarse_inverse/v34_full_input_diagnostic.dat`，唯一一次COMPLETED，输入及manifest绑定真实source |
| 最终checker `a4cf9c0…` | 新保存向量分区／复交叉项小测试1 passed及真实缓存CHECKED，监督5.926647831s；零新原作用／因子读取／求解／QR／参考读取 |

[测试](outcomes/records/tests_v34.json)、[修复](outcomes/records/repairs_v34.json)保留每次原始失败和费用。不借用review隔离试验或历史110/162项作当前资格，没有CI、全仓pytest、FE/MPI或Ruff通过声明。

## 实测与负结果归因

rho表示校正后残差范数除以该输入原残差范数：小于1才减少残差。这不是除以原完整物理b的最终解资格，也不是E/H场误差。q0是同七区域直接相加的固定单位系数对照，q_ret是旧回流方向。

| 固定已消费冷末态／measured | rho_full | rho0 | rho_ret | 外域单独补项残差比 |
|---|---:|---:|---:|---:|
| V24-LZ-CYCLE4 | 2.97739708904112 | 2.5444381411607355 | 1.5795794693775491 | 2.7826044305407738 |
| V24-LCZ-CYCLE4 | 4.065825954112519 | 3.4623458468352646 | 2.137828944967003 | 3.9707802967231465 |

正信号要求两态rho_full≤0.75且≤0.8rho0；本次两态均≥0.95，且均比q0更差，达到预登记负分流。输入、J资格、原作用配对、重组／抵消及消费均通过，最大差/完整b为2.21856763996e-14，最大operation-relative为1.10496072039e-14，未放宽门限。详见[独立checker](outcomes/records/full_input_checker_v34.json)。

J=[5,7]内最终残差范数为3.15047093123e-16／1.83427349766e-15，说明反馈确实消除了联合块内作用；六个外域块却都放大，block6贡献最大，其最终残差/原全域输入分别1.73686384266／2.43225345089。补项响应与旧回流后残差的复内积实部为−3.03359761611e-5／−6.36423474721e-4，减去它反而产生正的范数平方交叉项。这解释了本次反馈只消除J、没有改善外域方向；不由此宣称唯一病因、条件数或所有Krylov必失败。完整八区范数、操作数尺度及复交叉项在checker中；它们是canonical残差系数组，不是材料区域的场积分。

## 完整费用与边界

| shared-workstation成本／measured或derived | 实际值／边界 |
|---|---|
| actor／完整launcher（nested） | 20.032767938s／23.541070762s；不能相加 |
| 前后辅助／四次新probe | 25.604168930s／5.347870708s；失败、归档及审核计入 |
| 新收费／历史carry／600秒累计 | 50.984807576s／161.205635980s／212.190443556s，余387.809556444s；队列已closed，不消费余额重复结果 |
| 分阶段采样整树RSS峰 | actor1,019,056,128B；前测323,706,880／333,119,488B；后checker133,902,336B，峰不相加 |
| 资源及线程 | CPU40→11→46→0现场分别准入、MPI1/math1/Loader0，GPU不用；pre及actor实际BLAS getter1，post同activation/math1但未单独保存getter |
| 限制／实际实施 | actor warn12/hard16GiB、aux warn1/hard2GiB，规划4,246,745,088B≤8GiB；subreaper＋完整后代树请求0.5s监督、ownswap0，所有后代清空；无可写委派cgroup，不称内核连续硬限 |
| 真实消费 | S20／SH2，J reader1／RHS solve4／L-U pass8，port factor1／solve21／RHS21；其他reader、新LU/assembly/QR/迭代/FE/训练全0 |
| 因子存在／存储 | `READONLY_JOINT_DENSE_LU_PRESENT`，3888行J原A＋LU载荷483,729,408B；无global p4 LU、无全局fine CSR，不能称factor-free |
| 原生任意RHS部署 | 仍需J两解、六外域solve、两次A传播，另加端口、true residual、恢复、审核与IO；本轮缓存不是免费部署 |
| 历史完整方法费用 | formal下界77,161.55713859801s，旧辅助／因子构建／合格N=1成本unknown保持，不清零或默认摊销 |

[费用](outcomes/records/resource_costs_v34.json)、[完整消费](outcomes/records/actual_consumption_v34.json)、[统一存储](outcomes/records/storage_v34.json)及[完整性](outcomes/records/evidence_integrity_v34.json)给出原始hash及口径。仅删除未引用bytecode23,516,992B；失败合成载荷无损归档且保留成员hash、原路径与还原方法，未删除真实结果／因子／旧closed。未观察到PSI或资源触线；没有邻任务同条件性能对照，影响为INCONCLUSIVE，不声称绝对零干扰。

冻结总start为2026-10-03 12:44:22.975476 UTC；23h有载／24h总日历窗保持原值，等待、实现、读取、发布及未知间隔都算elapsed。这次因全部授权队列完成提前收口；实际交付时钟及最终worktree/upstream另由交付receipt和终端报告记录。

## 资格、唯一下一建议及审阅

本轮没有新场恢复、native完整求解、E/H、curl或official R00_s/p/total、R/T/A/A_volume；全部NOT_RUN。历史V24完整0/5、V23完整0/6保持，不能从J内小残差提升完整物理解。原尺寸0.7nm／2TB／48h仍`NOT_QUALIFIED`，神经≥20%完整N=1时间或同时峰改善仍`NOT_DEMONSTRATED`。

只读dot新发布`3c7458fad7c002babac4e634be4788b664be9ee5`的compact投影文档，更新受影响action/cost项；p4/120cells/532ports与本任务不同，合成数组界不是新PDE资格或实测RSS。[14项身份表](outcomes/records/dot_identity_gap_v34.json)与[神经成本必要条件](outcomes/records/neural_cost_assessment_v34.json)保留unknown，未改dot、读取其大型因子或把等待dot作为本轮前置条件。

**唯一下一建议：根据已保存的外域放大／block6耦合证据，只读评估dot周期／全局信息传播路线与Task042的接口、恢复和完整生命周期成本是否可对应，再决定一个不同机制的最小对照。** 本轮不实施，不再调同p1/tau、同回流系数、添加方向或延长旧迭代。

GitHub精确review页抓取Cache miss，视觉`NOT_VERIFIED`；本地表格／链接／fence另列，不冒称网页或CI通过。仅推送执行分支，清场后等待集中审阅。用户要求通知隔壁对话写review；当前可用接口无跨对话dispatch/send，未伪称消息已发送，交付后提供绑定最终SHA的审阅请求。
