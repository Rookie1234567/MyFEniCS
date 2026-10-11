# Review V43：不把停滞直接归因于小网络；一次可辨别的宽度与内层求解对照

## 0. 裁决、范围与身份

**接受V43完整实施和联合FAIL。第4至8轮的散射E误差由13.263%降到12.229%，但后两轮原残差只下降约0.60%，继续学习并未稳定优于同态冻结控制；停止原样延长这份配置。用户提出“网络是否太简单”是合理假设，但目前不是已证根因。批准一个完整数值工作包：从同一第8轮实际网络出发，保持TT秩8与物理不变，只做一次16→32宽度扩展；设置小网络和宽网络冻结隐藏层两个控制，并对三条采用同一有界内层补足规则。**

它消除的是“把容量不足、隐藏特征未学好和条件线性问题未充分求解混成一个失败”的blocker。不是再次做任意权重的容量证明，不是照用户猜测宣布加宽必成功。三条必须交真实原方程、完整场和成本；普通工程错误同批修复，不能只交接口或设计说明。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42extra_feinn_5nm
canonical_worktree     = /home/fenics/Projects/NN-Lab-V2
original_base_SHA      = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD   = 7e6a4b308abd83243eea1467ecd79fe530e3fac0
result_commit_time     = 2026-10-11T02:36:49Z / 2026-10-11 10:36:49 +08:00
review_date            = 2026-10-11 Asia/Singapore
previous_review        = review_report_v42.md
reviewed_response      = response_v43.md
campaign               = V44_FTT_WIDTH_VS_OPTIMIZATION
required_response      = response_v44.md
new_total_window_s     = 57600
production_merge       = NOT_APPROVED
```

最终目标不变：原尺寸0.7 nm、任意非可分三维周期单胞、complex128 Nédélec H(curl)、双Floquet、Fourier-DtN、复E/H、衍射、独立体吸收；十进制2e12 B为整机内存且保留余量，ownswap/OOC=0，单场必要准备至完整验收≤172800 s。**本支还没有承担该目标的合格方案。**16 h为新研发上限，不是目标48 h成绩。

本报告显式覆盖旧review对“宽度不变、每核仅300迭代、不得续算”的限制，仅授权本文矩阵；不重开V43预算，不取消历史FAIL。旧稠密波库、无相位路线及其他同类续扫仍关闭。本支只做神经，不恢复W0/W1、全口面、模式恢复、传统Maxwell PC、存储工程或主线接入；不改Task42、主线、dot、master及其他工作树。

## 1. 证据与当前判断

回读远端branch、Response V43全文、summary当前段、内层CSV、路线与parent身份、FTTField及相关条件核心实现；比较Review V42以后5次提交。根AGENTS、仓库原则和任务目录清单已核对。前版review从本会话原件完整读取，blob为01521bab1798d5a6b2ded81c2384629b5c6f645b；原task/目录规则与此前未变blob衔接。最新目录未见Review V43。未SSH、未检查工作站实时进程、未在审阅端重跑M5或逐数组复算大型artifact。

主要依据：[Response V43](response_v43.md)、[summary](outcomes/summary.md)、[逐核CSV](outcomes/records/conditional_inner_solver_v43.csv)、[完整Gate](outcomes/records/full_numerical_gates_v43.json)、[路线与checkpoint](outcomes/records/conditional_core_routes_v43.json)、[费用](outcomes/records/resource_costs_v43.json)、[网络](../../src/solvers/ftt_field.py)、[条件线性求解](../../src/solvers/ftt_conditional_core.py)。资格/训练source为dce792d18a45a1c874c29dfa4a42a8052fffe40f，独立物理核验与目录恢复source另列，不用发布HEAD冒充数值source。

| measured；M5/5nm/384hex/p3/N31968/40端口 | 追加隐藏学习 | 同态冻结隐藏 | 原门 |
|---|---:|---:|---:|
| 总轮数 / 本批新核心访问 | 8 / 12 | 8 / 12 | 数量不是精度 |
| 原native及augmented相对残差 | 0.426368073351 | 0.426728354382 | 1e-6 |
| 散射E相对误差 | 0.122287212177 | 0.122022405592 | 1e-4 |
| 散射H/curl相对误差 | 0.122543035005 | 0.122269414211 | 1e-4 |
| 独立能量闭合误差 | 0.0330435842880 | 0.0328998929907 | 1e-5 |
| 实际网络完整矩重建相对差 | 1.2264e-14 | 1.7334e-14 | 1e-10 |
| 新内层迭代 / 到300上限次数 | 3547 / 10次 | 3565 / 10次 | 各12次核心访问 |
| 新正式attempt秒 / 同时树采样峰B | 1625.04398280 / 916746240 | 1597.94472169 / 843309056 | loaded-packet，非冷单场 |

两条实际网络和producer均联合FAIL；保存、MPC、端口和求积合格，不能用已修writer解释12%的场误差。学习路线从第6到8轮R/E/H比为0.993955/0.925067/0.925401，延长原配置的依据已经弱于V42。共同第8轮冻结场略好、学习残差略低，不能授稳定神经增量或资源收益。

### 1.1 对“网络太简单”的独立回答

有可能，特别是轴向隐藏函数覆盖不足；但不能据9072个参数或训练停滞直接下结论。每个分量是三个核的连乘，TT秩限制跨轴耦合；每轴两个16宽sin层又把所有输出限制为同一组16个隐藏函数加常数的组合。这是两种不同容量。扩大rank不自动增加轴向特征数，增加宽度也不取消rank8限制。

[V40诊断](outcomes/ftt_capacity_decision_v40.md)的纯r8条件性尾能量约1.90e-5，低于E门1e-4；它未排除rank8，但也未证明足够，且实际FE统一桥接未建立。固定隐藏特征近相关是警告，不是所有可再训练隐藏层的排除证明。本批不重新追1e-15 nm几何项的统一证明，也不再跑相同oracle。

另一个独立问题是内层精度：V43学习新增12次LSMR中10次到上限，最大真实伴随残差相对初值为0.236；停止码2也不等于原方程收敛或所有参数联合最优。不能把有限内层未解尽误认成网络全部容量耗尽。LSMR停止意义见[官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.lsmr.html)。

单个场具有结构，网络参数少于实FE未知量不是该场不可表示的证明。反之，宽度更大只是给出了更大的可选函数族，不保证有限优化会找到更好解；内层成本还会增长。下面用实际对照而不是口头判断处理这个问题。

## 2. 唯一起点：保留已付结果，不重训八轮

三条都取V43 **LEARNED最终完整第8轮状态**，不是共同wall中的较好点或冻结路线终态。

```text
parent_route       = BLOCH_FTTNN_R4_LEARNED_CONTINUE
checkpoint_name    = committed_000023.pt
checkpoint_sha256  = ba2523341b7d1fa1cc339ea1b9544a7468e9fe7faa9dd2f93a8c000cad68e9f8
checkpoint_bytes   = 1895143
parent_source      = dce792d18a45a1c874c29dfa4a42a8052fffe40f
phase_sha256       = 32824e3063679681f77f6bb103fbb1ec9264f09f3441201407f6d0144cdc2ecc
native_sha256      = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
moments_q30_sha256 = 22715fac468c4e364c3947e99672117f0f855dfe424914f9fce16be090a693f5
```

真实路径由原run/index解析并现场核对。继承8轮、24核心、6905内层迭代、109隐藏调用；历史停止和费用不改。恢复全部模型、输出层、buffers、c/r和RNG，原mapping/A重算配对≤1e-10。后续parent-fork复用V43机制，不把导入另一个架构叫作逐位优化器恢复；原隐藏LBFGS每轮fresh，既有状态只留证据。

## 3. 一次宽度扩展：初始物理场不变，但新增方向不能死亡

### 3.1 明确扩展方式

宽模型每轴由1→16→16→输出改为1→32→32→相同输出，rank仍(1,8,8,1)，输出维数仍48/384/48。原9072实参数、912隐藏参数，扩展后推导为19200实参数、3360隐藏参数，输出系数15840；现场核实，不以数字凑模型。

设旧核为W3 sin(W2 sin(W1 t+b1)+b2)+b3。采用以下零输出嵌入，保留原子网络：

```math
W'_1=\begin{bmatrix}W_1\\U_1\end{bmatrix},\quad
b'_1=\begin{bmatrix}b_1\\v_1\end{bmatrix},\quad
W'_2=\begin{bmatrix}W_2&0\\U_{21}&U_{22}\end{bmatrix},\quad
b'_2=\begin{bmatrix}b_2\\v_2\end{bmatrix},\quad
W'_3=[W_3\ \ 0],\quad b'_3=b_3.
```

实/虚输出存储、三个物理分量、三核连乘、相位buffers均按原顺序。由公式直接知初始化时新旧核函数相同；不靠参考场拟合达到相同初态。思路属于函数保持扩展，参见[Net2Net原始论文](https://arxiv.org/abs/1511.05641)；此处具体零输出块嵌入单独验证，不声称是论文算法逐项复现。

新块只初始化一次，CPU独立Generator seed4214401，按axis顺序生成；U1采用16×1 Xavier均匀，拼接[U21 U22]采用16×32 Xavier均匀；v1/v2独立均匀[-0.5,0.5]。不重置旧参数、不挑seed、不根据参考误差挑特征、不增加额外频率乘子。非零新bias避免复制相同特征，但这是预登记的具体扩展初始化，不能把收益泛化成“只要参数数量翻倍就有效”。

新增输出列初始为零，因此新增隐藏参数的首个梯度可以为零；**先做输出核心LSMR更新再更新隐藏层**，以激活这些路径。需要验证新增输出方向的K不恒零，以及非零新输出后新增隐藏导数可用。不能把新增所有层都置零，或仅复制16个神经元而保持完全对称后宣称容量已实际利用。

### 3.2 三条路线与公平范围

| 路线 | 宽度/rank | 隐藏更新 | 用途 |
|---|---|---|---|
| W16_REFINED_CORE_LEARNED | 16/8 | 原912个隐藏参数继续学习 | 同容量、补足内层的控制 |
| W32_REFINED_CORE_LEARNED | 32/8 | 全3360个隐藏参数学习 | 具体宽度扩展候选 |
| W32_REFINED_CORE_FROZEN | 32/8 | 全隐藏固定在扩展初态 | 新增固定函数与真正隐藏学习分离 |

三条初始实际场和原残差相同；两宽模型初始全部参数逐位相同。冻结控制继承旧训练并含新增固定函数，不能叫“从未使用NN”。本批不增rank、不加深、不同时改变loss/相位/网格、不重跑Cheb和旧波库。

## 4. 共同内层补足规则：不能仍用不充分的300步就断言加宽无效

保持B=AK/||f||、b=(f−Ac)/||f||，只在一个神经核输出系数空间内求解，damp=0、conlim=1e12。采用统一的两段有界规则，而非无限加迭代：

1. 第一段复用原LSMR，atol=btol=1e-8，最多300次；独立计算e1=b−Bδ1和g1=B*e1、g0=B*b，保存原分子/分母及完整条件增量。第一段返回不即写入训练模型。
2. 若停止码7，或s1=||g1||/||g0||>1e-3，且安全余时允许，自动进行**唯一一次**残差补足：求min||Bδ2−e1||，增量零初值、atol=btol=1e-10、最多900次，合并δ=δ1+δ2。这是同一线性子问题的有界残差重解，不修改物理或正则化；两段全部计费。
3. 独立复算b−Bδ与B*(b−Bδ)，记录第一段与合并后的目标、真伴随、作用量、时间和参数增量范数。若补足使原目标更坏或实际写回不稳定，退回已验证的第一段；两段失败费用保留，不扫描第三组参数。
4. g0严格为0时记录该块一阶驻点，不做0/0；极小非零g0照实记录，另列绝对量和算子尺度，不以大floor制造通过。s≤1e-3只是本批内层下降充分性的诊断，不是系数误差界、全局最优或PDE资格。仍未达到就INNER_ACCURACY_UNRESOLVED，可以接受真实下降方向，但最终不得把失败写成容量排除证明。

若余时不足补足，记录REFINEMENT_DEFERRED_BY_BUDGET，保留可验证增量或旧完整状态，继续独立工作。三条规则相同，但有限迭代精度未必一样；必须报告实际内层质量与代价，不能仅凭同一个maxiter宣称公平最优比较。原网络在相同初态下第一段应与V43算法配对，新增机制对旧结果不追认。

K/K*、B/B*全部matrix-free，不建N×d矩阵、B*B或A*A，不用全FE完成器、Gram逆、global Maxwell/Gram因子或新的PC。较大参数块每轴大小改变，不能沿用硬编码17列或912参数；bias列始终最后一列，实复共轭与相位反传正确。

## 5. 实际执行：资格之后三条连续运行，不再只交诊断

先最小实现、定向测试、clean commit，随后按同样总轮序从第9轮z→x→y开始、第10轮反向。三条各默认完成4个新增轮次（至总第12轮），最多12核心访问、14400计费内层迭代、10800 s路线wall；学习路线各最多80个实际隐藏loss/gradient调用。fresh隐藏LBFGS保持lr1/history10/strong-Wolfe/max_iter10/实际max_eval20，输出层固定；不称精确VarPro梯度。

第10轮只保存无标签R并取得隔离E/H标量，不因未到0.1就提前停止；第12轮全部冻结完整验收。每条可以因安全、非有限数、正确性、有效输入丢失或自身预算结束，一条结束不取消另两条。原V43趋势false只保存在parent，不重新执行，也不自动续到第16轮。

首次R≤1e-8立即联合验收；仍有场差时只允许在原剩余额度中继续同算法至R目标1e-10一次。其余终态不按参考误差挑best。共同轮次和共同新增wall最近已提交边界分别比较，保存滞后如实报告；不同型号/忙碌程度的共享CPU不能冒称严格隔离性能实验。

若三条均运行完，宽学习模型已有明显联合改善（R、散射E、H均≤小模型对应量的0.5，且R≤1e-2、E/H均≤1e-2）但未正式PASS，可在总窗和本路线**原10800s**剩余额度内自动加两个轮次一次；这部分最多6核心/7200迭代/40隐藏调用，因此仅该路线的新增上限变为6轮、18核心、21600迭代、120隐藏调用，10800s路线wall不变；额外轮次单独计为不匹配工作量的探索，不据此授公平优势。没有达到这条固定信号则不加；不重开路线wall或campaign。正式PASS优先停止训练并验收。

## 6. 必需资格与结果解释

测试必须覆盖：16宽默认回归；旧权重精确保留；新旧核/点值/完整c及Ac配对≤1e-10；宽模型三轴纯虚/bias/多分量K/K*和复伴随≤1e-10；至少三个非零隐藏FD方向稳定段≤1e-5；新增输出方向非零；输出激活后新增隐藏梯度可用；模型参数/用途/相位缓存失效；partial、两段增量恢复和合并回滚。新核q30/q60系数与原A作用≤1e-8，不能削掉非零矩或扩大求积误差门。

小型复数矩阵测试两段LSMR与独立小SVD残差配对，包含秩亏、纯虚和中断；不对实际M5构造稠密教师矩阵。第一段δ及其基点hash/预算原子保存后，第二段中断只能恢复这一已保存对象；不能宣称恢复未保存的LSMR双对角化。所有丢失作用照计。

宽模型独立验证应直接评价一般宽度的逐点MLP，再用保留的旧StreamingMomentMap完整矩，而不让新factored路径与自己互证。通用维数由实际layer/shape取得；旧宽16输出不得被新default改变。原参考仅由隔离checker读取，reference_used_for_training=false；标量参加分流、设计受历史诊断影响均显式披露。

| actual网络与producer分别完整验收 | 原阈值不变 |
|---|---:|
| native、augmented、独立total原方程 | 各1e-6 |
| total/scattered E/H/curl、六点、四类完整40复通道向量 | 各1e-4 |
| R/T/A/A_volume、独立体吸收一致性与能量闭合 | 1e-5 |
| 逐级功率绝对差 | 1e-6 |
| 实际模型重建、MPC、端口恢复 | 1e-10 |
| 网络及原A作用/独立FE求积配对 | 1e-8 |

最终必须给出下列因果限定，而非只写三份FAIL：

- W16补足已经明显改善：旧容量不是唯一解释，内层/优化贡献实际存在。
- W32学习明显优于同政策W16，且新增方向实际参与：支持**本次宽度扩展方案**，不证明所有大网络有效；还须排除单纯更多计算量的解释。
- W32冻结与学习相当：更多固定轴函数有用，但新隐藏学习的净贡献未证。
- 三条未过且内层仍未解准：该配置无合格收益，容量与优化仍未完全可辨；不能宣布网络数学上无解，也不自动再扩大。
- 联合Gate通过但费用更高：NUMERICAL_PASS_NO_VERIFIED_RESOURCE_GAIN；不得只报新阶段秒数。

不得使用条件性内部矩谱当作当前最终场Gate，不再开新oracle/监督拟合、rank扫描或无穷超参试验。

## 7. 资源、0.7 nm晋级和同批修复

本批唯一总窗57600 s，立即持久记录首准备时刻；A实现/资格软7200 s，三路线各硬10800 s，最终验收/发布至少3600 s；剩余用于修复与以下条件pilot，不叠加历史剩余额度。不承诺PASS，不为了继续运行修改科学门。

原父学习路径至少2920.6633467029314+1625.0439828秒的两段attempt仍需归属，约4545.71秒不是完整冷成本；历史总账不重复收费。网格/native/moments、资格、内层补足、模型扩展、审核与输出不能免费；loaded-packet、新增/归属前缀、研发历史及冷N=1分别报告，缺项UNKNOWN。

CPU-only/MPI1/math/Torch1，现场单空闲物理核；numeric warn12/hard16GiB、临时规划12GiB、新cache/AD≤1GiB，轻2GiB，ownswap/OOC0。原PSI/SMT、系统max(128GiB,10%有效内存)及至少384GiB邻增长保护不变。正常成功60s准入计墙钟，不套旧耗尽观察池；真实拒绝后额外前台等待≤900s。2TB不授权本支占满整机。

普通API/schema/参数维数/导数/目录/角色/保存错误同批定位→最小修复→受影响targeted测试→健康边界继续，没有bug次数交棒卡。数学改变新commit并绑定新source，旧默认/负结果/产物不覆盖。存在合法run时不改HEAD、不kill或重复启动。durable全链、deadline前150s收口、至少120s保存，健康producer不因checker/网页错误重算。

仅W32学习实际M5联合PASS、两控制已验收、安全且总窗剩余≥10800s（其中3600s保留给最终交付），才运行既有长度×0.14的0.7nm非可分三维pilot一次；整体≤7200s，训练≤1800s。统一正式0.7nm材料，实际网格/模式/背景/chi/参考全部重绑定，不硬套40通道或缩放旧FE系数。该缩放不增加近似几何/波长比，不能冒充原尺寸或连续精度通过。

任何原尺寸预测必须包含准确离散、所需rank/宽度与算子/端口/O(N)数组和峰值重叠；19200参数小不意味着全过程小。只有同严格精度、完整成本和同时峰可比，才可能授≥20%资源收益；主线通用Full3D iterative的任务不由本支代做。

## 8. 输入、commit和一次交付

同分支安全fetch/ff-only；若纯本任务review与未推送实现分歧，只有无活跃run且clean、无数值冲突时沿既有执行补充允许的普通merge保留双方历史，不reset/stash/rebase/amend或merge master。正式数值进src，复用现有runner、parent-fork、独立评分，不复制第三套训练循环。

按依赖串行执行，stage必须先实现/validate/定向测试并clean提交：

```text
input/task042extra_feinn_5nm/v44_width_and_inner_checks.dat
input/task042extra_feinn_5nm/v44_w16_refined_learned.dat
input/task042extra_feinn_5nm/v44_w32_refined_learned.dat
input/task042extra_feinn_5nm/v44_w32_refined_frozen.dat
input/task042extra_feinn_5nm/v44_width_independent_compare.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

wrapper选择合格FE/ML/pure activation并调用scripts/run_case.py，每项清场后再下一项。绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境/线程、资源与artifact hash。母PT不改；新schema记录parent、宽度、嵌入seed和参数布局。

交response_v44.md、outcomes/ftt_width_vs_optimization_v44.md及compact扩展/参数/起点、两段内层、隐藏/新方向激活、轮次R/E/H、actual/producer完整Gate、共同成本与限定、resource/repair/test/source记录。summary、README、progress、模型总账、tests/changed_files仅更新本分支，历史与UNKNOWN永久保留。禁止full pytest、重装、全仓反复hash或大规模重新渲染。

**不在接口、commit、一次bug或一条候选失败时交棒。** 完成三条及独立验收和获准条件工作，或真实安全/不可恢复数据/对应科学或总预算出口后一次交付。只推本分支，报告完整HEAD、显式tracking/ahead-behind、clean及自身清场；不得强推或生产合并。

审阅端仅验证小型扩展代数、参数数、复杂梯度及文档结构，不代替工作站M5测试。GitHub视觉无法取得时如实NOT_VERIFIED，有限补查后继续数值，不把它当新计算前置。最终回答的是“这次具体加宽是否有用、内层补足和真正学习各贡献多少”，不是附和用户猜测，也不是预设网络路线失败。
