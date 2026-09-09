# V6粗逆替换：有界原型未资格化，V5双模型成功保留

G1/G2已完成，旧新C真实负结果保留；用户补充授权继续有依据的p4/p2诊断，G5与response_v8尚未最终收口。该授权超出V6原停止分流，不改变物理、精度或安全线；不复跑G1/G2。

| 范围与结论 | 证据及限制 |
|---|---|
| 当前进度 | `G1_G2_COMPLETED_DIAGNOSTIC_CONTINUATION_AUTHORIZED`；新C=`COARSE_APPROXIMATION_UNQUALIFIED` |
| 原始LO正式求解 | 13步，full explicit true=0.6678430800368991；1800秒首段不合格，`SCREEN_BUDGET_NO_QUALIFIED_PROGRESS` |
| 正确性与质量分开 | 映射/RHS桥、native/Galerkin、eps闭合及成本账通过；内层26次均未达1e-4，不等于真实A/P错误 |
| 后续分流 | G1六输入0/6达LO，HI不具资格；原始未通过，notch/恢复不运行；用户补充授权继续限定p4/p2诊断 |
| 基线 | V5准确p4粗逆的原始564步、notch576步完整解与物理Gate通过，仍是可移交数学基线 |
| 资源边界 | G2峰1491857408B，仅失败screen（含cold编译）；不能称2GB成功solver、完整解峰或`MEMORY_TIME_TRADEOFF`资格 |

本报告执行[Review V6](../review_report_v6.md)，机器记录见[compact](records/coarse_inverse_replacement_v6.json)，移交边界见[workstation_handoff](workstation_handoff.md)。V5原始输出平面错误、同解恢复和notch参考448页全局换出归因UNRESOLVED均保留；本轮没有重跑旧基线或参考。

## 方法与冻结身份

粗修正C把细网格上难以消除的误差送到较小空间求解，再送回细网格。V5用准确p4全局LU：先分解一个大矩阵，之后每个右端项回代较便宜，但因子占内存。V6只将这个内部求解替换为迭代I4，意图取消大p4因子；代价是每次修正可能需要许多p2回代，而且近似解可能不足。外层仍按“粗修正—细层平滑—粗反馈”顺序工作，平滑指用少量廉价操作削弱部分误差，并不独立求完整散射场。

I4求原物理A4 c=g，right FGMRES16/max64/零初值，LO目标1e-4，单次60秒保守边界，末次显式残差与安全返回另记录。它的B4采用同样平衡顺序，物理p2底层加p4三阶Chebyshev/Jacobi平滑H4，窗口在p4上按power10单独估计。物理层只有6/4/2，无p3/p1辅助栈，无p4/p6全局AIJ/LU；p2不是任意扩大容量的替代大因子。

| 身份 | 固定值 |
|---|---|
| G1冷缓存成功source | `2edcf84888a7e989246b0fae28bc4555b61fc48d` |
| G2正式source | `ddd090ebbae2a6fdcd5d2ef8d728c48b600d66e7` |
| base SHA | `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` |
| 模型 | 原始13.5nm、1°、s、Full3D、p6/h10nm、252六面体、MPI1/线程1、80 modes |
| 自由度 | p6存储173802/独立164592；p4存储53084/独立48960；p2增广7326=7246FE+80端口 |
| physical SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| mode SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| G2 input SHA256 | `592651b0e5a8dac45867c65cda7fd815c0e889738afd76794aad08c34921b9b7` |
| 新旧身份桥 | native map逐字段相等、原b差0；native/Galerkin≤1e-10；求解前不读取参考解作为初值 |
| ABI | qualified Linux activation；complex128/int32；PETSc3.19.6/SLEPc3.19.2、DOLFINx0.10.0.post2、Basix0.10、mpi4py3.1.5、OpenMPI4.1.6 |

## 统一模型结果

R/T/A是入射功率归一化的反射/透射/平衡吸收；A_volume由场在材料内部耗散独立计算。未通过真实残差的场不能产生official功率。R00_s/p为零衍射级两偏振的功率，total为两者之和。V5是同离散参考资格，不是连续真解。

| 模型/方法 | 步数 / true residual | R | T | A | A_volume | solve保守s / 采样树RSS峰B |
|---|---:|---:|---:|---:|---:|---|
| V5 原始准确C | 564 / 9.93228922e-07 | 0.365625790955 | 0.0129906323212 | 0.621383576724 | 0.621383574645 | 6102.614283 / 3466235904 |
| V5 非可分缺口准确C | 576 / 9.351705517e-07 | 0.337120584975 | 0.0162886742427 | 0.646590740782 | 0.646590748463 | 6261.471126 / 3600924672 |
| V6 原始LO递归C | 13 / 0.667843080037 | not_run | not_run | not_run | not_run | 1804.967924 / 1491857408（失败screen） |
| V6 HI、notch | not_run | not_run | not_run | not_run | not_run | 未具条件资格 |

V5 原始：R00_s=0.365589112902，R00_p=4.58891259532e-25，R00_total=0.365589112902。

V5 非可分缺口：R00_s=0.337079616921，R00_p=6.43835224702e-27，R00_total=0.337079616921。

其余重要衍射级、全部80复振幅及场差继续以[V5完整结果](balanced_coupling_v5.md)和其compact为权威；新C没有这些official量。p/h、M、MPI>1与Hybrid比较均not_run；本轮只改C，不能给出这些参数的资源/收敛规律。

## G1：六个固定右端项与三次完整校正

六输入来自既有真实误差q=A6e，经原准确C路径得到g1和反馈g2；保存的准确解只在测量端比较。下表场差是新粗解相对准确粗解的FE范数差，越小越好；不是p2最佳表示误差。

| 固定输入 | I4步数 | 原A4相对残差（目标1e-4） | 保守s | 粗修正场L2差 | scaled-curl差 |
|---|---:|---:|---:|---:|---:|
| A2R160_BAL_H_p4_01_I4 | 23 | 0.940685927 | 64.737822 | 0.99672646 | 0.99670271 |
| A2R160_BAL_H_p4_02_I4 | 23 | 0.07587544081 | 65.558273 | 1.0244617 | 1.0239397 |
| JOINT448_BAL_H_p4_17_I4 | 23 | 0.9256111673 | 61.102786 | 0.99910302 | 0.99908506 |
| JOINT448_BAL_H_p4_18_I4 | 23 | 0.05963445357 | 61.084837 | 1.0241478 | 1.0236356 |
| LIGHT448_BAL_H_p4_09_I4 | 23 | 0.9349333057 | 64.922457 | 0.99883319 | 0.99882148 |
| LIGHT448_BAL_H_p4_10_I4 | 23 | 0.05910609031 | 60.967792 | 1.0253522 | 1.0248492 |

全部有限但0/6达标，状态均INNER_INEXACT_AT_CAP；约61–66秒包含检查边界和末次显式作用，没有增加64步或延长内部预算。下表remaining是单次校正后剩余真实场误差/原误差，rho是残差范数比。旧准确C的rho虽大却消除大量场误差，新C的rho接近1不能解释为更好。

| 输入 | V5 L2/curl remaining | V6 L2/curl remaining | V5 rho | V6 rho | eps1/eps2绝对范数 | 实际闭合相对误差 |
|---|---|---|---:|---:|---|---:|
| A2R160 | 0.387035993/0.387481465 | 0.997973933/0.997962096 | 10.815429 | 0.993261844 | 0.58920322/0.030272454 | 1.92377e-13 |
| LIGHT448 | 0.382173998/0.382623672 | 0.998487348/0.998482168 | 22.653392 | 1.059281464 | 0.98097685/0.03150578 | 2.53537e-13 |
| JOINT448 | 0.379978542/0.380407158 | 0.998918111/0.998909647 | 26.170024 | 1.066439500 | 1.0698687/0.033689179 | 2.19988e-13 |

两次内部残差eps1=g1−A4c1、eps2=g2−A4c2预测最终粗空间中剩下的误差：PH(q−A6z)=eps1−eps2。闭合检查比较等式两边的差，并用两次rhs与A4c范数之和归一化，门槛1e-8。它通过仅说明误差记账正确，不要求剩余缺陷为零。三例实际缺陷范数为0.5947541、0.9893180、1.079993（精确数值以compact为准）；大的eps说明近似质量差。未测最佳p2投影/谱，不足以证明p4/p2空间表示容量根本不足。

G1恰为6个固定I4+3PC，总12I4/276B4/552p2 MatSolve，零精化。冻结源码中finish每PC自动audit，再由controls.audit_last复核一次，派生额外A6/PH各6；此为derived成本解释，原G1 totals未单列它们，独立计时not_measured，不改raw。

## G2：有限screen负结果与成本

| 终态 | 原始记录 |
|---|---|
| screen | 第13步、1800.799460404s、true0.6678430800368994；>1e-2且无完整32步周期趋势 |
| terminal | 原A6数组独立重算0.6678430800368991；terminal计时1802.171814204s |
| solve含退出审计 | 1804.967923523s；单live KSP create/solve/destroy各1；FGMRES32/max2048/zero |
| wrapper与checker | parent WORKER_FAILED/worker exit4/CLI exit3；checker为SCREEN_BUDGET_NO_QUALIFIED_PROGRESS，recursive账本PASS，非工程bug |
| 内层质量 | 26I4、0/26达LO，真实残差范围[0.0559405629436,0.947311116589] |
| 工作量 | 609B4/H4、1218H4 positive；635A4 matvec+130explicit A4；13H6/26H6 positive；1218p2 MatSolve/0精化 |
| 审计 | 首PC与退出各1；额外A6/PH各2，A6=2.703945611s、PH=0.217552282s、审计总2.923563969s（嵌套，不能相加） |
| 输出 | official不可用是未收敛的预期负项；不是输出恢复错误，不重新求场 |

| step | 显式true | solve保守s |
|---|---:|---:|
| 0 | 1 | 4.431838 |
| 1 | 0.907963580992 | 145.206065 |
| 2 | 0.863835092251 | 280.549798 |
| 3 | 0.811567358457 | 413.948270 |
| 4 | 0.800523532899 | 554.270119 |
| 5 | 0.788476786403 | 697.254384 |
| 6 | 0.76357025854 | 837.014924 |
| 7 | 0.740702516463 | 978.295680 |
| 8 | 0.726780363092 | 1118.735199 |
| 9 | 0.717682744896 | 1259.426483 |
| 10 | 0.707962784291 | 1398.115878 |
| 11 | 0.693000274647 | 1530.927400 |
| 12 | 0.680409362161 | 1667.475464 |
| 13 | 0.667843080037 | 1800.799460 |

同口径成本从各正式pc_applies.jsonl的PhysicalBalancedCoupling.operation_seconds读取，以下是monotonic组件计时的中位数；不含PH审计、外层正交化、显式残差和checkpoint，不冒充完整PC墙钟。小计为每行组件和再取中位数，不是各中位数相加。

| 数据集 / PC数 | 两次C中位s | 两次A6中位s | H6中位s | 组件小计中位s |
|---|---:|---:|---:|---:|
| V5_original / 564 | 3.208314 | 2.666567 | 2.185457 | 8.065459 |
| V5_notch / 576 | 3.197528 | 2.662717 | 2.157311 | 8.027803 |
| V6_LO_screen / 13 | 119.350002 | 2.699282 | 2.218363 | 124.516155 |

旧原始每PC两次p4回代，新screen平均1218/13=93.692次p2回代；粗修正C中位约3.208→119.350s。两组迭代轨迹不同，不能据此预测完成时间。因新C未得到真解，不授予MEMORY_TIME_TRADEOFF，只报告“取消p4因子、局部峰值下降，但精度和时间不足”。

## 对象生命周期、资源和费用

| 阶段 | 同时存活对象 / 口径 |
|---|---|
| cold setup | 几何/材料/6-4-2空间、传递、真实DtN、H6/H4表、p2矩阵与factor、编译器；G1峰2052198400B、G2峰1491857408B均含compiler，不是稳态 |
| solve | 上述必要对象（无编译器）+外层V/Z+I4内层V/Z+双eps及有界last q/z/difference；普通历史仅标量，最慢/失败数组有界保存 |
| 内层载荷 | p4 restart16按33×53084×16=28028352B，是derived基向量载荷，不含工作Vec/分配器；外层完整restart32上界65×173802×16=180754080B，G2只13步未充满 |
| p2预算 | 7326rows≤8192、818100NNZ；矩阵CSR16391308B，reported-padded factor270000000B；矩阵/转换/预留+factor总341069688B<512MiB，政策预算非RSS/严格allocator证明 |
| release | KSP已毁，p2 factor/matrix、粗actions、H4/H6与closure释放，fine恢复对象保留；G2 before1142194176B→after1140097024B，分配器未归还全部内存，不以对象载荷推断RSS下降量 |
| 终结 | 失败场不恢复；最终全部parent/MPI/worker/compiler清场，无swap/OOC；G2最低available11256262656B>4GiB |

动态cap=min(12e9B,可用内存−reserve)，reserve=max(4GiB,总可见内存15%)，同时守住可见物理/cgroup较小容量。G1/G2树VmSwap峰0、global in/out新增0。V5条件参考448页换出归因UNRESOLVED不因本轮零增量而消失。

| 费用项 | 保守s / 性质 |
|---|---|
| 初始focused测试全部尝试 | 322.079194330 measured；包含失败，详细见test_summary |
| 原预留 | 20 policy reserve，not_measured；ABI/短只读准备 |
| G1旧JIT失败 | 59.856457986；0I4/0PC，遗留.c无完成模块，原cache保留 |
| G1冷缓存完整校准 | 1113.340604647；mono1002.094415506/UTC1113.339304569，保守值计费 |
| G2接线测试两批 | 2.327659698+5.265852279；16passed→新增桥fixture后17passed |
| G2父/外层账 | parent2039.934619649；batch收费2039.988395687，包含前后处理，二者不相加 |
| G5局部文档检查 | 10 policy reserve，not_measured；编辑/等待另列 |
| 本批合计 / 剩余 | 3572.858164627 / 39627.141835373，上限43200 |
| G0/G1已计 / 剩余 | 1522.869768940 / 3877.130231060，上限5400 |

单项预算不是可相加的运行承诺。内层时间嵌于C、C嵌于PC、PC嵌于solve、solve嵌于workflow；UTC与monotonic偏差保留，不单独当数学失败。G1失败为已定位的pre-measurement缓存生命周期错误，隔离新root缓存后唯一重试；G2为真实数值负结果，不再抽样重跑。

## 证据与选择性合入

完整raw路径和SHA256在compact.evidence，G1每输入及三PC、G2逐inner/PC/exit/曲线另有绑定。输入、manifest、resolved、ABI、source、资源和原始残差数组均保留。全80 observable与参考链由V5 compact绑定；未复制factor、cache或巨型artifact进Git。

| 依赖组 / 建议顺序 | 数值行为、依赖、验证与边界 |
|---|---|
| production numerical/core：1审 | 现有A/P与V5默认不变；p2 rowcap例外、I4、inexact ledger改变opt-in研究数值，不能提升production；依赖通用action/transfer/有界MUMPS；tiny/单Vec测试及fresh G1/G2记录 |
| reusable runner/watchdog：2审 | 冷cache、global-swap opt-in、停止信号与专用release；依赖core/qualified activation；17focused含旧V5兼容，fresh G1/G2清场 |
| checker/benchmark：3审 | 原字段重算target/计数/闭合/screen；依赖完整标量/NPZ/manifest；篡改fixture拒绝、G2checker确认负分类 |
| compact evidence/docs：4审 | 本中心/总账/移交manifest；Response V8尚未最终编写；依赖上列SHA证据；仅JSON/hash/link检查 |
| research-only | LO/HI dat/profile、物理6/4/2递归、p2 pilot；本次未资格化，不默认启用，不扩8192到短波 |
| do-not-merge | results、raw NPZ/checkpoint/field、LU/matrix、JIT cache、timeline、临时脚本；均ignored |

当前无master merge approval。下一步执行已审p4/p2限定诊断，结合V5成功基线及V6负结果供集中review；W0位置/迁移必须另授权。5nm非可分压力例与0.7nm/2TB容量规划属后续任务，不能从7326行底层或一个失败screen外推。


## 中途因果诊断：已测证据与下一组件（G5仍开放）

为了分辨“低阶空间装不下误差”与“低阶求逆方向不对”，本阶段先把原p4误差按真实场能量投影到p2，再检查各部分如何进入原Maxwell方程。这里M0表示场的空间平方积分，scaled curl表示按波数缩放后的旋度平方积分；表内场误差比是剩余误差范数除以原误差范数，越小越好。所有输入来自同一个冻结A2R160 g1，不重新求参考场。

| 已测步骤 | 核心结果 | 费用与边界 |
|---|---|---|
| p4/p2失效诊断，33de3c343d84de8a56f40a425534013f485e48f9 | p2可表示97.9197%的M0能量，但M0投影之外仍有49.9662%的scaled-curl范数；进入粗方程的两部分几乎抵消，相加后仅占两者范数之和1.20508% | 254.465748861 s保守全流程；RSS峰1,479,798,784 B；I4/outer均0。不是求解资格 |
| 投影互补修正，c027cacaeed8aa2640f30dcf5e19015120029179 | 一次零初值FGMRES在33步停止，原g归一化真残差2.768678226，未过1e-4；旧同输入残差0.940685927。M0/scaled-curl误差比改善至0.943669169/0.943477716，仍远未解决误差 | 284.593272153 s保守全流程；RSS峰1,507,844,096 B。60 s在完整回调边界触发，显式终点61.486 s、连末次核验62.353 s，未延长或重启 |
| 原网格单个air单元bubble首检，84d41982351fdd6dcab5c82b615d7ce92dde82cc | 局部300个p4自由度中保留全部54个p2方向（含6个内部方向），仅处理102个额外内部方向。物理张量核对3.754e-15，LU残差3.596e-14，RW恒等式1.175e-14，Schur恒等式2.063e-14；边/面切向差2.152e-14/7.353e-15 | 23.594851925 s保守全流程；RSS峰1,148,182,528 B；最少可用11,402,002,432 B。LOCAL_TENSOR_PASS，仅局部构造通过，无全局因子/I4/outer |

三个流程均由专用父进程监督、进程树swap峰0、全系统swap页计数增量0并清理后代。峰值均为同一时刻整棵进程树RSS采样最大值，包含编译子进程；不可相加，也不是完整新求解的峰值。单元首检选中cell217，尺寸8.5×8.333333333333334×10 nm；原网格没有满足优先条件的10 nm立方air单元，使用预先固定的最大体积/坐标排序规则，没有换单元试过关。

“bubble富集”是在每个单元内部调整低阶基函数，让原物理方程在额外内部方向上的响应为零；外边界切向场保持，所以全局仍使用p2未知量与原80个端口。代价是每种实际几何/材料类要做一个102×102复数LU，并保存新的局部W。它是辅助粗空间候选，不改变真正fine A6/A4，不是完整(P,Q)块精确逆。W的对偶必须是Wᴴ；非Hermitian材料下左耦合PᴴAQ不能换成(QᴴAP)ᴴ。

下一组件只完成代码与一个复数MPC/局部插入fixture，等待主线程审阅。计划同一cold setup最多900 s，先检查全类、W/Wᴴ全局伴随、S装配对WᴴA4W和range(W)身份；使用新S的唯一有界p2因子，matrix/conversion/factor及额外缓存统一≤512 MiB。通过后只测一次C_W(g)与一次原V6 BAL_H内层FGMRES16/max64/60 s/1e-4，原参考仅用于M0/curl测量，不跑outer。准确class键用未舍入的J/width、复材料、k0、quadrature、element及orientation，P/R/Q按orientation缓存；每个物理类仍核对原FFCx并通过原LU/Schur Gate。全网格候选尚未正式运行，不能把单元通过解释为收敛成功。

紧凑身份与raw索引见[因果研究记录](records/p4_causal_research_v6.json)。旧诊断input_bridge的字段名覆盖仅影响标签；原NPZ未改，`v6_recursive/bridge_labels_companion.json`以原输入hash独立恢复对应关系。G1/G2/projected负结果、V5成功边界和原swap归因限制全部保留，G5/response_v8未关闭。


## 全网格bubble组件实测补记（仍为中途研究）

| 项目 | d9462e486360a86e9635b504f37a0b762c2bf896 实测 |
|---|---|
| 类与正确性 | 252 cells/18精确物理类/5方向；Wᴴ伴随2.9463e-15，S装配对WᴴA4W为1.9021e-14，range身份4.1916e-13。仅构造身份通过 |
| 一次C_W(g) | 原A4残差4.052124485；M0/curl场误差剩余0.931283538/0.931271755，较旧C的约0.98759改善，但本身不是残差收敛 |
| 唯一原V6 I4 | 15步，原A4真残差0.981425253，未达到1e-4；M0/curl剩余0.996615448/0.996601698，仍几乎未消除真实场误差 |
| 时间边界 | 60s边界完整回调显式60.723383347s，末次显式61.147076748s；没有延长或重启。父mono328.996389188s、UTC361.394431144s，保守计费361.394641579s |
| 底层与缓存 | p2总行7326、NNZ818100，原体图801316未扩；matrix/conversion/workspace/cache+reported factor政策346769400 B≤512 MiB。额外局部缓存政策9699712 B（含4 MiB reserve）；这些不是RSS |
| 调用 | I4/Cg/range各1，B4=15、p2 logical/MatSolve/S_true各32、refine0；原A4总84=external21+B4结构30+composed33，含setup composed1。H4 positive50含setup20；M0/curl metric各3次；outer0 |
| 全树资源 | RSS采样峰1702248448 B，h4_window_complete阶段含compiler1；最低系统可用10972098560 B；tree/global swapΔ0。父清场，host独立确认全部73个已观察PID退出 |

260项独立原数组/哈希/账本检查通过，确认的是计算记录和负分类，没有把0.9814变成solver pass。三项旧负结果与V5成功边界不受影响；本轮无新official R/T/A。原始证据入口已加入[中途compact](records/p4_causal_research_v6.json)。

## 内部特解定位已测，左限制诊断待审

内部特解E r=Q D⁻¹Qᴴr，只在每个单元额外内部方向响应方程右端，用于分辨遗漏内部响应和更高阶切向误差。本次复用旧张量，18个小LU处理两个冻结右端；成本低，但不能代替完整非Hermitian块逆。

| 55a795e5b31b5c6b0323b92c517f6e989faf5803 实测 | 结果与解释 |
|---|---|
| E(g)/y的M0、scaled-curl范数比 | 0.003091639/0.003815295；减去Eg后误差剩余0.999308817/0.999308421 |
| 内部方程Qᴴ(g−A4Eg) | 参与项归一化1.2834e-14；全dual残差比1.637625109，不能称全方程收敛 |
| y=w+q+t的curl范数比 | 0.953247125/0.352317605/0.394524433；q/t交叉项−7410.853673，显示抵消，不能将各部分能量直接相加 |
| 时间与调用 | 保守父流程9.496253621 s，raw审计0.939217091 s另计；mesh1/space0、LU18、local RHS504、cached A4两次；无全局因子/I4/outer |
| 资源 | 同时全树RSS采样峰251469824 B，最低系统可用12148039680 B；tree/global swap增量0，全部3个PID退出 |

129项原数组独立检查通过，只确认诊断。Eg小不能排除C_W A4Eg很大：CUg=Eg+C_Wg−C_W A4Eg，Vᴴ=Pᴴ(I−AE)一般不等于Wᴴ。唯一固定delta/CUg诊断已实现，正式运行待diff审阅：复用旧Eg/A4Eg/Cg/y及18类W/S_cell，仅恢复(4,2) FE/MPC metadata和p2 S/80端口；一个因子/一个logical RHS，最多原两次同因子修正，独立S_cell+DtN残差≤1e-10。总cold流程300 s、8192行/统一512 MiB、原动态全树上限/4 GiB余量/zero swap。只测真实场范数和复交叉项，全A4CUg残差为not_run，不关闭G5，不新增I4/outer。

原始入口 `benchmarks/artifacts/task39extra/v6_recursive/bubble_particular_readout.json` 的hash及分类见[中途compact](records/p4_causal_research_v6.json)。
