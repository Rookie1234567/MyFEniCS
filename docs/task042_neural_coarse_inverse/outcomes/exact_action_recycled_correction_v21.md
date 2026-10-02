# V21：精确类别作用与固定循环空间校正

按Review V18执行D0、A、B、C和冻结后的独立V（B存在下述历史向量读取缺口），完整资格 **0/5**，分类 **NOT_QUALIFIED**。B/C未取得完整有限元资格；不宣称完整求解、神经训练增量或同严格精度加速。

本轮分别改变两步：把完全相同类别的局部矩阵按最多64个单元一起乘，减少每次重复展开；然后用固定GCROT配置保留少量修正方向及其方程作用，检验是否减少后续重复搜索。前者是精确作用的工程优化，后者是线性残差修正；均未训练隐藏层或改原有限元方程。代价包括类别缓存、最多33对回收向量、内部Krylov向量、副本、端口闭合、逐周期原审核与保存。

原0.7nm、384hex/p3/h0.175/q15、双Floquet、top20+bottom20通道保持；trace18144、内部13824、slave2082、完整z18184。Si从canonical用户表离线读取：n=0.999885140474+4.32477054e-6i、epsilon=n*n，source0.699999988仅明确alias到nominal0.7，不插值。

内部场可以先按单元局部方程消去，剩下边／面系数和端口的方程称为Schur方程；Schur残差衡量这些完整方程还差多少。恢复内部场后再检查原未凝聚方程，得到native残差。二者的归一化不同，必须各自过Gate；端口小方程闭合准确也不能代替体方程通过。

表中原rho为旧oracle的完整norm(b-Sz)/norm(b)，分母固定为原完整物理b；wall含该路线本批失败/恢复费用。measured、无量纲残差及秒；共同baseline为V19 L-GPOLY末态，未用V20 N/ILU结果。证据：[逐周期](records/cycle_history_v21.csv)、[状态](records/checkpoint_inventory_v21.json)。

| 路线 | 完整边界调用 | 原rho起点 | 原rho最终 | 原native最终 | charged S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|---|---|
| B | 16 | 9.67833470962e-06 | 7.73068606402e-06 | 2.99798928999e-06 | 4656 | 393.743535608 | CALL_LIMIT |
| C | 112 | 9.67833470962e-06 | 2.5281170328e-06 | 9.80413346383e-07 | 30645 | 2939.28866421 | TIME_VERIFY_RESERVE_STOP |

冻结后的独立场审核才读取已有REF7；其实际原native=3.01796304395967e-12、独立total-native=1.43744486618839e-12，没有置零、重建准确解或参考反馈。两种native分母不同，不能互换。下表场误差相对同mesh/p3参考，不是离散误差或连续解误差，全部measured；[完整Gate](records/qualification_and_dispatch_v21.json)。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 独立total-native | 散射E≤1e-4 | 散射curl≤1e-4 | 逐通道功率差≤1e-6 | 完整合格 |
|---|---|---|---|---|---|---|---|
| V19-L-GPOLY-FINAL | 9.67833470962e-06 | 3.75329480007e-06 | 1.30239098725e-06 | 7.95003214967e-05 | 7.9510166913e-05 | 1.7855346417e-06 | False |
| V19-L-GNN-FINAL | 1.44393838546e-05 | 5.59964766271e-06 | 1.94307429584e-06 | 9.70793047547e-05 | 9.7083009907e-05 | 5.64706064632e-06 | False |
| B-FINAL | 7.73068606402e-06 | 2.99798928999e-06 | 1.0403004379e-06 | 7.94237400141e-05 | 7.94361776624e-05 | 1.88874663809e-06 | False |
| C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 3.40202831061e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | False |
| C-CALL32 | 4.43845248007e-06 | 1.72124865592e-06 | 5.9727222794e-07 | 7.88465049064e-05 | 7.88620685216e-05 | 1.8483718407e-06 | False |

## 作用资格、成本与循环空间

旧ActionPacket.apply/recover/uncondensed/audit数学路径保留；新ClassBatchAction是独立组合对象，没有audit方法。预算包装只调用旧apply，不把旧audit重定向到新实现。共享数组readonly，旧/新S与SH分别计费。行布局forward用T乘S的转置，adjoint用T乘S的逐项共轭，再按原cell顺序/Floquet累加；精确classes不按近似材料合并。

原/新作用最大运算尺度差 **7.02255037030978e-14**（限1e-10），两个暖点残差差/b最大 **1.4045098620278e-13**（限1e-11）。barS/SH及复dot通过，原close/恢复/MPC通过。nc384/局部trace108/classes122；额外持久缓存22771200B，分块临时上界407808B；旧逐cell展开71663616B只是derived数组载荷，不是实测RSS节省。[作用](records/action_equivalence_v21.json)。

三组交替顺序的10S+10SH微基准及完整L调用均保留。完整调用OLD **44.53653365s**、class64 **23.47186909s**，实测降低 **47.2975%**；两者均257次bar作用、含端口和旧audit，试验更新未作为正式初值。完整调用每backend只有一次，不能把单样本中位称统计稳定估计；kernel配对有共享负载波动。按预登记20%标准冻结EXACT_CLASS_BATCH64，分类EXACT_ACTION_ENGINEERING_GAIN，无争用性能INCONCLUSIVE。[成对成本](records/paired_kernel_cost_v21.json)。

GCROT固定m256/k32/maxiter1/M=None/truncate oldest/discard_C=False；CU严格为(c,u)、c=barS*u，保留None掩码/原顺序及可能k+1=33条返回。首次内部长度288，随后随库存变化；callback是外层状态，内部Arnoldi次数unknown，使用实际S/SH计费。每8调用非None像用旧barS复核，最大运算尺度差 **6.03512192649e-11**；每边界原/新残差差/b最大 **1.44399204138812e-13**，门限未放宽。C正交性只是有限性诊断，不把数值缺陷当全局条件数。

两条路线的实际算法从同一t_b重新定义固定r_b，独立x0=0、方向列表空，物理t=t_b+x；每次完整40端口由原Hhat闭合。未加载旧Q/U/R/K/ILU或参考方向，没有global p3/p4因子、完整S/barS或private audit CSR，只有原局部块和40维Hhat小解。两库历史都有共同神经G0，不能把GPOLY说成全无神经；本批没有神经训练增量。[接口](records/recycle_contract_v21.json)。

共同16调用时，B原rho=7.730686064023909e-6，C=8.251697165038711e-6；在不超过B的作用／wall前缀上，C只到14调用、rho=8.464159136468282e-6。因此短对照没有显示GCROT同工作量更优；B的读取缺口又限制了其合同资格，不能声称胜负已获完整资格。C最终rho更低是112调用与更大成本下的实际改善，不是同严格精度加速。相对暖点，C残差改善3.8283倍，散射E误差只下降约1.68%；其最大通道功率差仍1.7196446511213992e-6，超过1e-6。最后16调用下降约3.06%，实际因时间预留先停止，不把后置统计改写成当时的停止原因。[同工作量](records/paired_same_work_v21.csv)。

## 冻结场与功率

下表为已冻结状态的measured、无量纲功率，参考为同mesh/p3。未通过完整原方程的行全部UNQUALIFIED_DIAGNOSTIC，不能发布official R/T/A。完整selected复E/H、总/散射场及40个原键/极化/reference-plane见[场](records/field_checks_v21.json)、[通道](records/field_channels_v21.csv)。

| 状态 | R00_s | R00_p | R00_total | R_total | T_total | A_balance | A_volume | 能量缺陷≤1e-5 |
|---|---|---|---|---|---|---|---|---|
| V19-L-GPOLY-FINAL | 0.117644927761 | 1.03447616421e-12 | 0.117644927762 | 0.117645984704 | 0.877049568498 | 0.0053044467988 | 0.00530640713048 | 1.9603316801e-06 |
| V19-L-GNN-FINAL | 0.117640790554 | 4.75697216595e-13 | 0.117640790555 | 0.117641847495 | 0.877042135891 | 0.00531601661368 | 0.00530636059989 | 9.65601379288e-06 |
| B-FINAL | 0.117644927513 | 8.96012416199e-13 | 0.117644927514 | 0.117645984458 | 0.87704967169 | 0.00530434385126 | 0.00530640731746 | 2.06346619325e-06 |
| C-FINAL | 0.117644973437 | 7.01536540619e-13 | 0.117644973438 | 0.117646030384 | 0.87704950259 | 0.00530446702554 | 0.00530640688527 | 1.9398597273e-06 |
| C-CALL32 | 0.11764489193 | 7.67049611863e-13 | 0.117644891931 | 0.117645948876 | 0.877049631316 | 0.00530441980848 | 0.00530640712283 | 1.98731435375e-06 |


## 修复、恢复和未运行项

R01是自身父队列过早绑核缩窄了子进程的新核选择范围；在没有数值actor时修正自身调用，不改选核门限。R02给旧LGMRES的代理补齐n=oracle.n，真实B/C dat→stage→求解→close→保存→原audit回归通过。R03仅将回收检查qualified转成Python bool；C第8周期已经完整保存并审核，校验全部文件/数组hash后补写未发布的历史，从该边界继续，没有重算前8次Arnoldi。原WORKER_FAILED、原source和保守上界费用都保留，未追溯改为成功。

R04是在求解期间发现并公开记录的输入reader范围错误：该reader额外解压了V19的x与outer_directions，虽未用于任何求解初值或循环方向，但违反B明确不得读取旧方向的合同。B的装载Gate保持FAIL_RETAINED，16次实际数值结果仅作为带此限制的对照，不宣称完整合同通过。可信C从零校正、空CU计算不受这些未使用数组影响。活跃队列退出后只将reader收窄到trace/port/z/residual，加入遇到旧方向解码立即失败的两种读取回归；没有为了修补记录重跑B或C，也没有追溯改变其source或结果。修复后的独立验证使用新的clean source，见[读取边界](records/data_loading_boundary_v21.json)。

本批自身完整x/CU或L方向先保存再close/audit，失败可补审；未返回内步不能由callback标量恢复。C仅保留最新两次完整CU工作区，所有物理历史向量仍在；更早失去CU工作区的点只作不可直接续算的物理快照，不冒称checkpoint。两代槽、None、半写/kill/坏hash/补审及独立读盘继续反例通过。[恢复/修复](records/repair_reentry_v21.json)。

| 未运行项 | 原因与分类 |
|---|---|
| 条件T/Z | C未达原方程1e-6且残差改善不足10倍；未启动不是冷启动失败 |
| 新p4参考、最大0.7nm模型、其他波长、GPU、hidden训练 | 本批硬边界，not_run |
| ILU ordering/shift/level/drop、旧p4逆或新PC | V20固定natural负结果已收口，本批未授权 |
| full repository pytest、MPI2/4、CI、环境升级 | 共享资源/本批MPI1 focused范围；未声明CI |
| GitHub公式/表格视觉资格 | 精确页未取得视觉证据，NOT_VERIFIED；本地文本结构检查不能替代视觉 |

本批D0运行此前未资格化的V20 reader最小mutation回归，但原V20not_run与TOTAL_ELAPSED_NOT_COMPLIANT原文保持；本批新测试不追溯关闭旧超时Gate。

## 时间、内存、硬件和历史账

不可刷新start **2026-10-02T00:33:31Z**；重负载截止04:03:31Z，总截止04:33:31Z。UTC/monotonic/boot均落盘，恢复上下文、新stage、commit/push及交付前重新读取真实钟，未知间隔不扣除。数值队列结束即时写最小结果/费用包，已清场的交付准备时刻见[截止/回执](records/deadline_stop_v21.json)；最终commit/push/回复的实时时钟另记本地final_git_receipt.json和最终回复，不将准备时刻冒称推送时刻。[原冻结窗口](records/clock_deadline_v21.json)。

新增正式one-run监督wall **3482.12566257s**，launch wall **3490.37979421s**；辅助监督wall **61.5086217693s**（费用快照，后续低负载检查另计总elapsed）。正式历史下界 **70970.5997846s**，旧辅助unknown保留。暖解仍依赖V14/V15建基、V16 image、V17/V18 LSQR和V19 L，上游精确per-solution拆账unknown；本批短校正不代表整个解时间。[完整费用](records/resource_costs_v21.json)。

采样同时整树峰 **870723584B（0.810925GiB）**，own swap/VRAM0。0.5秒监督覆盖launcher/worker及全部后代、warn12/hard16GiB、事前规划<=8GiB；无cgroup委派，不称kernel连续硬限额。嵌套action、port、audit和父队列计时不重复相加，数组容量不是RSS。累计charged旧/新S+SH **36022**、原audit **144**、场状态 **5**，失败/未知调用按保守上界扣费。资源重入0、冷却0.0s。

MPI1、每run实时选择空闲物理核并避开忙SMT、数学线程1/Loader0、GPU不用，独立activation/cache/output/自有锁。其他heavy继续，不改其环境/亲和性/优先级/锁/watchdog或系统ABI/BLAS/CUDA。全部性能shared-workstation；未发现持续PSI/自身swap压力不等于零干扰，缺乏可比邻任务阶段成本时影响INCONCLUSIVE。

actual run source：`97a17aee9a9cc2d91904b4c89f07c4d1cfbd631c`, `c91954c47d55242fd95ae7efcb44272dcce3a0ec`, `d7bfcb58632b344f8ed9b9fd1467c6c224df0bc4`，分阶段在[run index](records/run_index_v21.json)，最后文档HEAD不是运行身份。branch/upstream为task42_neural_coarse_inverse/origin/task42_neural_coarse_inverse；canonical linked worktree为/home/fenics/Projects/NN-Lab，common Git为/home/fenics/Projects/Maxwell3D-Lab/task-repository.git，base ccd357885f7f9be84efe3be07868cc94f13d93fc。只安全fetch/快进此分支，旧历史与其他工作树不改。

## 最终取舍和唯一下一建议

B/C未取得完整有限元资格；不宣称完整求解、神经训练增量或同严格精度加速。作用实现的收益与循环空间的原残差效果分开；功率及场资格仍由全部原Gate决定，低loss/小内存不能替代它们。这里只是micro固定离散对照，最终0.7nm非可分目标、离散误差、目标规模可扩展容量和48小时均NOT_QUALIFIED。

唯一下一建议：在同一冻结micro上，只预登记一次“固定p1原物理粗层＋现有局部修正”的容量／传递资格及最多4个GMRES256周期对照：让更低阶的原Maxwell方程处理远距离耦合，保留负质量项、Floquet及完整40端口，避免把正定AMS/HX成功误当散射资格。先复核可复用高低阶传递与既有负结果；容量不合格就不启动，任何global p1 factor必须明确披露，不能称factor-free或重开p4强逆。依据是本批无PC循环的同工作量无优势、112调用仍不合格且最后16调用降幅不足5%。可用性、低阶色散误差与收益均unknown，只作为下一review的单一有界建议。 本批未实施，等待下一review；不自动增加循环容量/迭代、建PC、启动新参考或放大模型，不merge master。


补充通道证据：legacy物理汇总没有持久化逐通道功率数组；本批从已保存的完整复振幅调用原有解析功率函数，离线重算5×40通道，逐状态最大差与原审核记录完全相同，R/T汇总差≤1.2e-16。该表标derived，不是新的FE求解或新的终测；S/SH、audit和FE状态新增均0，资格未改变。见[逐通道功率](records/per_channel_power_v21.csv)、[原公式配对](records/per_channel_power_check_v21.json)。
