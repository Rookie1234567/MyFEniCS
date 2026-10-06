# Review V52：分开升阶异常与DtN截断，复用准备包推进0.7 nm完整场

## 0. 裁决、目标与分工

**接受V53两份完整有限方程解、P→A的单方向h增量资格和实际资源证据；不授完整NOTCH准确性、原尺寸0.7 nm、2 TB/48 h或NN收益。授权V54：先用已保存场和张量作一次有界的跨p一致性核对，再在相同Z2网格上实际完成p6/p7 × 532/828模式的配对。模式误差检查不再等待尚未闭合的p/h门。暂不直接批准更大的Z4/p7。**

本批消除的blocker是：p6沿z加密已经稳定，但p7带来约3.45%的散射场变化，尚未分清跨p实现一致性、有限空间响应与有限DtN截断的影响。继续增加z单元或训练NN，均不能代替这个区分。不是预先认定p7有bug，也不是预先认定532模式不足。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task42_neural_coarse_inverse
canonical_worktree      = /home/fenics/Projects/NN-Lab
review_date             = 2026-10-06
reviewed_HEAD           = e3419c0a9f0606c7159c063f4c9f7e588525f4d1
reviewed_commit_UTC     = 2026-10-06T06:08:49Z
previous_review         = review_report_v51.md
previous_review_commit = bc509db93ed905b945bab7cb21a5f6bbaaa23288
latest_response         = response_v53.md
V53_A_B_solve_source    = eec0e75313c91d3daf4d22e72cf04167e58f31f9
original_base_SHA       = ccd357885f7f9be84efe3be07868cc94f13d93fc
sibling_branch          = task42extra_feinn_5nm
sibling_readonly_HEAD   = 8d617d4d206b08f38279320b67188db1b8ccd301
sibling_contract        = Review V29 / V30_ADAPTIVE_WAVE_NEURAL_GALERKIN
next_batch              = V54_P_ORDER_AND_DTN_SEPARATION
required_response       = response_v54.md
NN_training_inference_PC= NOT_AUTHORIZED_THIS_BATCH
merge                   = NOT_APPROVED
```

本Review回应V53，顺延为V52；旧task/review/response/raw均不回写。明确覆盖V53“只有p/h先全部通过才准模式试验”及“只准在P上做一次828”的依赖限制，保留原科学门和32/40/48 GiB资源合同。本批最多四个新完整solve，具体分配见§4，不自动新开研究窗口。

最终目标仍为原50×25 nm周期、z=−10..130 nm、17×25×120 nm Si结构、λ0.7 nm，并保留任意非可分三维材料/几何能力；单次端到端≤172800 s、约2 TB整机保留系统余量、ownswap/OOC=0。有限直接因子只作authority，不是目标尺寸生产方案。生产仍需准确高阶表示、分布式/matrix-free原作用、streaming DtN、有界粗问题及可扩展迭代。

**Task042本批是确定性准确性研究，不是NN。** Task42extra继续自身5 nm起步的学习波动greedy；NN-V3的独立学习迭代也不在本批范围。本支不做M5/teacher/波动字典/网络训练/NN-PC，不迁移新邻支代码，不通知、写入或接管其窗口。未更新remote不代表邻任务闲置，现场资源规则仍有效。NN20%门只用于未来宣称神经增量，不作为本批建立准确基准的先决条件。

本次审阅读取实时三支ref、当前目录/README/summary/response、V53专题/修复/准备与求值源码，以及V51 review之后9个提交的改动清单。原Review V51本地完整副本的Git blob为`1c17f3aae2e4558aad4987c46d85fee68bed2785`，与已读远端一致；同blob治理/task和既有补充限制复用，目录未发现新supplement。未SSH工作站、未取得全部ignored数组、未重跑PDE或测现场资源；以下实测值是仓库recorded measured，而非ChatGPT新测。新队列均为planned/not_run。

## 1. V53结论：有收益，但不是NN收益，也不是完整准确性

证据：[Response V53](response_v53.md)、[完整结果](outcomes/phase_hp_completion_v53.md)、[科学门](outcomes/records/hp_accuracy_checks_v53.json)、[费用](outcomes/records/resource_costs_final_v53.json)、[修复](outcomes/records/repair_journal_v53.json)。

| recorded measured；固定0.7 nm/532模式 | 结果 | 正确结论 |
|---|---|---|
| A：Z4/p6，320cell，65044凝聚行 | 独立true 2.49903e-11；峰11.82278 GiB；dat下界4543.8195 s | 已补齐上轮因配额未算的完整解；有限authority成立 |
| B：Z2/p7，160cell，45780行 | 独立true 1.90999e-11；峰13.44512 GiB；dat下界10396.5729 s | 方程/恢复通过，不能据更高p指定为准确参考 |
| P=V52 Z2/p6 → A | scattered E/H 3.27734e-5/3.86947e-5；selected 4.77303e-5；复通道6.57370e-6 | 完整单方向h增量通过1e-4；不是所有空间/边界误差通过 |
| P → B，同Z2升p | total E/H约0.004962；scattered E/H 0.0344963/0.0344677；逐mode功率3.26655e-5 | 升阶变化显著，不能直接断言p7更好、更差或有bug |
| A → B | scattered E/H约0.0344962/0.0344677 | 与P/B几乎相同；仅再沿p6细z不能解释这个差异 |
| 本批NN | 训练/推理/NN-PC均未使用 | 新神经收益为NOT_TESTED，不把确定性结果算成NN增量 |

V51的解析FLAT准确性继续保留：固定相位表示曾把普通空间约1.0127的总场误差降到E约3.86e-8、H约4.64e-8。这是表示收益，不是训练收益；不为本批复算一轮FLAT。完整NOTCH仍未获准确性锚点，不能凭功率守恒、true residual或某一个h方向通过发布原尺寸目标成功。

成本也要求改变工作顺序：A的raw张量准备3556.0843 s，B为8945.7468 s，分别约占其dat下界78.3%和86.0%；全局symbolic+numeric及solve合计仅约95.87 s/121.36 s。分项/父计时口径见原表，比例为derived，不是合格同精度加速。即使本有限case末端factor/solve免费，也只占约2.11%/1.17%，不支持现在回NN预条件器；不能将这个小模型比例外推至原尺寸。

V53已保存p6 A的38类451.10 MiB和p7 B的26类716.65 MiB完整raw tensor包。它们不是Schur或全局因子，但对**相同p、相同真实单元几何/材料/κ而仅改变端口库存**，体张量没有数学变化，应优先核对复用。场求值的exact cache hit记录为0；不能宣称缓存命中收益，乘法重新结合与同准确性端到端性能仍须分别报告。普通监控/写出bug已修，A/B未因元数据重解；不得把本轮科学差异都归咎于bug。

## 2. 为什么暂不直接Z4/p7，且不能再把模式检查挡在p/h门后

有限元空间误差和DtN截断误差是不同控制轴；同一个有限模式边界也可能对更丰富空间产生不同响应。固定532的p7大变化可以是真实的有限离散响应，也可能涉及跨p实现/数值稳定性；目前没有独立证据能唯一归因。新模式试验的目的就是在**不改变网格和p**时测另一轴，而不是假定多加模式一定变好。

原来的顺序“p/h全部通过再查截断”在本轮不合适：若截断参与这个变化，它就会一直阻止我们检查截断。解除该依赖不是降低准确性门。文献也把三维双周期Maxwell的FE误差与DtN截断误差分开；本文只采用此问题划分，不移植其几何/材料假设下的误差界或指数收敛常数。[Jiang等原论文](https://arxiv.org/abs/1811.12449)

本轮不能要求某个新Z4/p7同时接近当前相差3.45%的p6和p7端点；这会再次产生上一Review已经纠正的三角不等式问题。旧场只是配对控制，不能成为每个新解必须贴近的真解。新字段的判定与增量含义见§5。

## 3. D：一次有界升阶一致性核对，服务实际求解而非单独交棒

本阶段不新建完整因子/求解。优先读取V53 B和V52 P保存场、V53 raw tensor、已保存原作用/边界/物理身份；只补缺的必要作用。总目标≤1800 s（含执行，不是每子项1800 s），不是重做全库或多轮谱诊断。真正的数学不一致先同轮修；仅新诊断适配缺失不自动否定已通过的同p原方程，也不取消独立p6模式路径。

### 3.1 先排真正的跨p输入/求值错误

核对P/B的连续几何、cell材料、物理κ、λ/n/ε、参考面、模式键及归一化相同，差异只有p及其必要DOF布局。读取实际FFCx体求积、Basix family/variant/map type/DOF order和有限p7开关；禁止只看模板。旧q47/q63完整边界资格继续有效，但它不是体积分的高阶资格。

在四个互斥材料区及出现的方向类选定少量实际cell/点，对B保存场用旧`PhaseEvaluator`/公开Basix直接tabulate与新多项式结合求值各算一次E及完整Cκ/H；不能只验证随机场或仅E。若仅新输出解释有错，修比较/输出并重新核对旧保存向量，**不重新factor**。

### 3.2 同网格的p6函数在p7空间中应保持原物理含义

令J为同Z2网格完整独立FE系数的p6→p7嵌入，保留全部内部DOF、方向变换和MPC。采用既有传递小核或Basix`compute_interpolation_operator`，不要选前几个系数、补零或另写多重网格。cell-local作用/对偶散布优先，禁止物化巨大的全局稠密J。[Basix 0.10插值及DOF变换说明](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.interpolation.html)

设A[p,M]为端口按其原方程精确闭合、但**所有体内FE未知量仍保留**的物理算子，f[p,M]为相同闭合后的真实物理载荷。在同532、同几何、积分充分的理想条件下，应有：

```math
A_{6,532}=J^*A_{7,532}J,\qquad f_{6,532}=J^*f_{7,532}.
```

这是比较**未凝聚体空间**的关系，不是要求静态凝聚与p传递可交换；不能直接把J替成trace子块去比较两个Schur矩阵。J的对偶必须是实际线性映射的共轭转置，共享实体只计其正确一次定义。

只做两个固定非零复数方向及保存P场的作用见证；同时核对物理E/Cκ保持和周期切向一致性。对p7缓存的实际raw类，用独立Basix仿射物理积分进行方向作用检查，分别保留curl、κ交叉项和mass，不在大项相消后的近零结果上用不稳定分母。p≤7可用实际张量积Gauss每轴11/13点（写清这是点数，不是旧q标签），独立记录实际多项式精确性；不重新生成26个昂贵完整FFCx矩阵。参考基表分块复用，所有实际raw/方向类覆盖一次。

门：新/旧场与J物理保持操作尺度≤1e-11；原作用/载荷嵌入、独立方向积分及复对偶≤1e-10，并保存分子/分母和物理方向残差。上述少数见证通过只是排除本次明显接线错误，不是认证整个算子条件数；失败也不自动证明旧物理解全错，先定位是新桥接实现还是原离散。

若确认影响原物理方程的错误，按§4的修复槽重新计算受影响的同532 case，再继续模式配对；不改旧raw或追溯填PASS。若只诊断桥接暂未接齐，标`CROSS_P_CONSISTENCY_NOT_ESTABLISHED`，仍可做各自可信的同p模式增量，但不授跨p准确性。

## 4. 两轴完整计算队列：同Z2/p6、p7，各只变模式库存

物理保持V51–V53全精度descriptor：s=7/135，x=s×(0,16.5,25,33.5,50)，y=s×(0,6.25,12.5,18.75,25)，z=s×(−10,0,40,80,120,130)；真实原NOTCH几何盒不变、不沿y复制。三轴原区间倍数(1,1,2)，160hex；λ0.7 nm、grazing1°、azimuth5°、s、幅值1；air1，Si n=0.999885140474+4.32477054e-6i，ε=n²、μ1。材料表SHA256=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。不再索要材料。

E=exp(iκ·x)u，κ=(kx_inc,ky_inc,0)固定，u双周期；所有Cκ trial/test项、物理RHS、全部内部及非零端口支撑、原独立体作用保留。不引入paraxial近似，不把物理场再投回旧多项式空间。

| 比较表 | 532：m=−9..9,n=−3..3 | 828：m=−11..11,n=−4..4 |
|---|---|---|
| Z2/p6 | P，V52已保存；不重跑 | R6，新完整solve；104832 FE/32832 trace/72000内部/33660凝聚行 |
| Z2/p7 | B，V53已保存；不重跑 | R7，新完整solve；166208 FE/45248 trace/120960内部/46076凝聚行 |

行数是原拓扑加模式数的derived，实际MPC核对。两种mode清单均保留上下侧与s/p。**主顺序D→R7→R6→比较，R7不通过/有局部实现阻塞不取消独立R6。** R7优先因为已有同p同几何完整准备包，不是因其被认为更准确。两case均物理零初值，新矩阵/局部和全局因子，不读取旧解warm-start或旧因子；旧场只用于固定对照。

828模式要先检查全部物理键、已有传播模式不遗漏、新对象q47/q63完整配对。仅配对实际失败才允许预先登记的63/79一次调整；调整后同轴比较必须同一有效积分规则，旧科学身份分开。禁止裁剪小行或模式、假设F=C*、丢弃非零内部端口支撑；保留精确端口坐标变换和原H/Hhat区别。仍沿原有限MUMPS、固定ordering及至多两次既有残差精化，无新PC/ILU/BLR/OOC/求解器扫描。

### 4.1 模式影响先用固定旧场解释，再靠新完整解判断

对每p的旧场u[p,532]，在不改变体场下计算新的828端口闭合、全部新增296个物理参考面投影和新闭合FE残差。不能把新增模式设零，不能把新闭合的port写回旧candidate并冒称旧审核通过。使用真实f的变化，不能假设新增RHS严格为零：

```math
r_{828}(u)-r_{532}(u)
=(f_{828}-f_{532})-(A_{828}-A_{532})u.
```

完整向量先按共享行散布再求范数，保留项间复交叉作用；最大单mode只作定位，不当唯一原因。此残差作用诊断不等于物理场误差界，也不是判断必须达到某幅度才准R6/R7的门。

新solve之后计算：同p的532→828场/功率增量；同828的p6→p7增量；与原同532 p差作对照。非嵌套的旧A=Z4/p6可仅作补充，不重跑旧H/A全表。两种机制的影响和相互作用分开，不由任何一个小残差推断收敛。

### 4.2 条件C：一次追加模式稳定性检查，而非无界扫描

R6/R7都实际得到可信结果后，如果R7的532→828完整场或参考面复通道/功率增量超原门，且余量足以保存与审核，允许**仅在同Z2/p7**再做一次C：m=−13..13、n=−5..5，上下×s/p=1188模式，凝聚46436行。继续复用同体张量。对828→1188完整投影/积分/原方程与场功率比较，旧场新360模式不得补零。

C不是因R7“没通过就随便多加模式”：它只在已实测同p对模式库存敏感时启动，使用事先固定的一个更大库存，无第三次加码。只有p6→p7差大但R7同p模式增量已小，不启动C，也不宣称截断是根因。若R7依赖的原方程不可信，不以C绕过。

本批最多四个新完整solve：通常R7/R6两项＋条件C；若D确认方程实现错误，可用剩余槽作同532的精确受影响重解。公共错误需修两份532时取消C，最多两修复参考＋两模式case。普通后处理补审不占solve槽但照计费用。**不运行Z4/p7、p8、新横向网格、原尺寸模型或新NN。** 没有数学错误就不重解P/B来“复现”已存结果。

## 5. 准确性裁决：允许定位，不为任何期望强行授锚点

| Gate | 仍采用的数值要求与解释 |
|---|---|
| 原方程 | 独立未凝聚Cκ＋完整该库存DtN，true/native/增广/port各≤1e-6；直接内部目标≤1e-10 |
| 恢复/约束 | 全内部特解、非零内部port、MPC/slave与操作恒等式≤1e-10；原slave规则 |
| 场增量 | 共同物理积分total/scattered E/H/scaled-curl、固定240 selected点、参考面复通道各≤1e-4 |
| 功率 | R/T/A/A_volume增量及独立能量≤1e-5；最大逐mode功率增量≤1e-6 |
| 积分 | 新全库存边界1e-11/操作1e-10；共同q23/q31操作≤1e-10；近零绝对尺度继承V53 |

raw辅助port、H加权端口行、实际参考面复振幅均保留，不拟合幅相、不归一化守恒、不四舍五入越门。不同M是不同有限边界问题；改变M后旧场不需要满足新矩阵，新求解则必须满足自身完整原式。只在固定同p比较M，在固定同M比较p。

| 观察 | 本批可给出的结论，不扩大资格 |
|---|---|
| 新求值/输入/算子嵌入确认错误，修正后p差消失 | `IMPLEMENTATION_CAUSE_IDENTIFIED`，旧结果留档；指明错在桥接还是原方程以及重解范围 |
| 828使同p场变化显著且p6/p7差明显收缩 | `DTN_SENSITIVITY_MEASURED`，截断参与的证据；不是唯一根因或无限mode收敛证明 |
| 同p的模式增量很小，而跨p仍相差大 | `P_SENSITIVITY_PERSISTS`；优先下一次独立h/p或离散稳定性研究，不再盲增mode/NN |
| p增量和相邻mode增量均过 | `FINITE_P_MODE_PAIR_PASS`；保留已测p6/532的h资格，但不自动升级成828/1188也有h资格 |
| C也对库存敏感或预算耗尽 | 具体`FINITE_MODE_INCREMENT_NOT_QUALIFIED`/not_run；停止增加库存，给出幅度与下一唯一工作 |

原P/A的h门不追溯改变，但它只在p6/532成立。新p/M组合没有相应h证据就不授完整交叉p/h/m或连续真解。若有限p/M稳定已建立，下一项才可选择同一已稳定M的一个h完整pilot；若模式影响弱且p敏感持续，可选择Z4/p7作为下一独立h试验。**本批不再让一个不相容的旧粗解必须跟上新解，也不为得到“通过”修改分母。**

这是一项准确性主线的完整物理判别，结束必须有新R6/R7可达场、模式与成本，而非仅提交嵌入检查。必要依赖确实不可信/安全预算耗尽时允许partial交付，不能承诺一定合格。

## 6. 减少重复准备与无效测试

### 6.1 把已保存raw张量真正消费起来

复用V53 `RawTensorCheckpoint`格式，新增窄的只读provider，不建设通用缓存系统。核对p/family/variant/DOF order、κ/k0/ε/μ、form数学签名、原始未舍入coordinates/tag、dtype、各文件hash和producer后才返回缓存张量；先独立重开并在D阶段做上述方向作用配对。**仅模式清单不同不改变体张量**；C/D/H、端口凝聚项、矩阵/因子必须按新M重新计算。

B(p7/Z2)准备包优先直接服务R7/C；A(p6/Z4)不能因为阶数相同就直接当P(p6/Z2)的包。R6可只复用逐字节相同或已有资格证明等价的raw类，其余类允许一次原路径构建并保存。缺文件/身份不匹配不是自动全批停工，局部回退正确核并校准时间。旧失败/准备费用不能抹去，新增只报实际缓存命中、I/O、必要重建和完整N=1成本。缓存启动单列`CACHE_REUSE_INCREMENTAL`；从几何开始的fresh N=1仍须加入该case必需父准备费用，未完整测量就给下界/unknown，不能把本次读取缓存的秒数冒充全冷时间。

不要重新运行V53的同场cache benchmark：其数学已通过但exact hit=0，额外常驻旧点表没有证据必要。可把相同新参考点在有限块内复用，保持最多2GiB的额外cache/workspace；无命中时释放LRU旧条目只保留当前块，禁止改点位精度追命中。原独立求值oracle保留。本批不开发六Gram扩展或新的准备优化路线。

### 6.2 测试金字塔服务新输入

不例行full pytest、不重新全仓文本索引/历史hash扫描、不重跑FLAT、旧H/P/A/B全积分或已通过q532全库存。只跑raw读取、p嵌入/新模式schema、条件C及受影响writer的targeted检查，相关Ruff/compile和一次紧凑文档检查（目标累计≤20min）。D的有界科学核对不是常规每轮动作，它针对当前3.45%异常；完成后不重复。

同一套新模式/端面原始积分可在严格相同身份下复用散布前数学数据；编号不同要重新散布并绑定，不能挪用旧native行。两个新解统一在最后增量VERIFY做一次原未凝聚/q63审核；已保存的字段/残差可独立重判，不重新factor。新增原数组和增量父hash足够，不再嵌套上千份旧JSON。

## 7. 连续排障、资源与时间

从执行者本批首项真实UTC/monotonic/boot_id冻结7 h总研发窗，科学有载≤5 h，最后45 min收尾。至少预留2000 s用于完整场比较/独立验收，所有修复、读取、准备、失败、等待和交付计入；上下文恢复/新stage/commit前读真实钟，不刷新V53已closed窗口。

先按实际V53 costs分配D与R7/R6，**不把8945 s的p7准备再默认重跑**；缓存接入实现限60 min，D目标1800 s，意外修复及受影响重放累计≤2 h，均包含于总窗。无bug个数式停机门；同根因两次失败必须改变诊断或回退已可信实现，不能第三次盲重放。返回完整向量先原子保存，再后处理/collector；writer、路径或页面错误只补审，不重算科学解。

沿V53显式计划32 GiB、warning40 GiB、采样整树stop48 GiB，稀疏装配/symbolic≤80000行；本批不再增加资源配额。numeric仍要求实时树RSS＋2×可信MUMPS INFOG16/17(decimal MB)＋2GiB余量≤32GiB；ICNTL22=0、ICNTL23沿现场两倍估计，无OOC/BLR/排序/shift扫描。新模式更多，旧symbolic只作规划参考，不能跳过新numeric准入。

MPI1、CPU/math1、GPU0、Loader0、ownswap/OOC0、一个现场合格物理核/避忙SMT、一个actor/一个全局因子。MemAvailable至少满足max(128GiB,有效物理内存10%)+384GiB邻增长+48GiB本任务停止预算，原规则更严则取更严；保留原PSI/cgroup有效余量。只监督和停止自身后代，不改邻任务/系统ABI/BLAS/CUDA/swap/锁/亲和性。资源压力最多一次≤600 s前台冷却，全部门恢复才重入；不以切换case绕过压力。

新ignored≤10GiB，Task042去重累计≤68GiB、free≥50GiB，交付预留256MiB；只在准入和阶段边界查存储，不把监控器变成历史目录扫描器。不删除旧失败或另一项目数组；无需复制已有raw准备包，引用只读父hash。采样峰非连续cgroup硬峰，实际间隔和shared-workstation限制如实报告。

数学输入/ABI/监督可信、局部实现错误可修时直接继续；真正原式/数据身份不可信先隔离依赖。数值不收敛/离散差异不是bug，不能更换物理、精度或模式定义直到成功。只有全批安全/时间/必要依赖耗尽才partial收口，普通代码提交或一个stage完成不停止等新review。

## 8. 最小实现、入口及交付

复用相位/增广凝聚/端口坐标/同物理比较/准备包/监督/补审，仅薄的V54 case和队列扩展。新增可复用数值核进入src，不复制数百行runner；公共默认、旧case保持。显式新端口库存允许1188只限条件C，不为此改成任意无限参数搜索。特别检查旧`complete_modes==828 else ...`分支、父stage指针和模式投影函数：新三种库存应由显式m/n范围映射，未知库存直接拒绝，不能悄悄落回532；只验证新增接线，不重写已正确的公共物理实现。

先核对canonical worktree、branch/HEAD/upstream/origin/活跃run；安全fetch/ff-only本分支，不reset/stash/clean、不改共享Git/其他工作树。只读一次隔壁最新ref，变更范围则记录，本支仍不做NN。不自动发送邻窗口指令。

待实现、测试并commit clean后validate，再按Gate执行：

```text
input/task042_neural_coarse_inverse/v54_p_order_consistency.dat
input/task042_neural_coarse_inverse/v54_notch_z2_p7_m828.dat
input/task042_neural_coarse_inverse/v54_notch_z2_p6_m828.dat
input/task042_neural_coarse_inverse/v54_notch_z2_p7_m1188.dat
input/task042_neural_coarse_inverse/v54_verify_cost.dat
```

统一`python scripts/run_case.py <one-run.dat>`，不存在的入口不声称可运行。确有方程bug时为受影响532修复case创建独立明确dat，并计入四solve总额，不能在诊断dat中暗藏完整求解。每run绑定input_original.dat/resolved_config.json/run_manifest.json/input/physical/discretization/material/mode/source/array hash与run_summary、环境、进程树资源。保留full physicalκ与实际p/M/三轴/内存配置，不复用错误的80cell模板标签。

一次交付`response_v54.md`、`outcomes/p_order_dtn_separation_v54.md`及紧凑records：D的具体判定、2×2结果矩阵、条件C/受影响修复case、完整原式/恢复/E/H/curl/selected/全部模式功率、原场新增模式作用与相消、实际raw复用、全成本/同时峰、修复/未运行原因和**唯一下一完整pilot**。科学表各数字有原分子/分母与父hash，不只抄status。README/summary/development_progress/model_registry仅增短入口；旧历史不改，本地通过不称CI。

最终GitHub精确页面视觉不可取就写NOT_VERIFIED，不为页面重跑PDE。只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`；核对remote完整HEAD、clean/upstream、closed/active null、清场和锁释放后交付用户暂停。不改dot/master、不merge、不自动开下一窗。
