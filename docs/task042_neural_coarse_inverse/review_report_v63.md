# Review V63：完成被审核开销中断的p6，以系数收缩和可恢复准备闭合全场

## 0. 裁决、目标与唯一执行身份

**接受V64的真实失败费用、已保存准备和明确的未运行分类；不接受将其称为新完整场或精度进展。** P6尚无symbolic、numeric、解或全场；L4仅得到超出本批形状许可的相容网格。下一轮不扩大p/h/M、不训练NN，也不重启同一L4。授权 **V65_COEFFICIENT_FIRST_AUDIT_AND_P6_COMPLETION**：优化不改变方程的独立向量积分，保存昂贵体矩阵，在同一0.7nm问题上完成一次p6全场及与已有p5的比较。

要消除的blocker是：**一次有限参照已经支付数小时体组装，却因独立检查的执行方式和单例预算未能进入求解；昂贵体矩阵又没有可恢复落盘。** 必须同时修正审核运算、阶段保存和完整费用规划，而不是删除物理检查或只延长旧代码运行时间。该路线仍为有限accuracy reference，不能据此把全局直接因子推广到原尺寸生产。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-09 Asia/Singapore
reviewed_HEAD          = 63141f0d4de7b74f6a22414edfedb43c9d458271
latest_result_UTC      = 2026-10-08T18:44:43Z
latest_result_local    = 2026-10-09 02:44:43 +08:00
latest_response        = response_v64.md
previous_review        = review_report_v62.md
previous_review_commit = b2cf084ee0269b87acfacef314475a70702f4266
previous_review_sha256 = b68ed6e8338ae3ed62707b72270a7071ea996ab1a3c47f3031c681e63ac60184
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V65_COEFFICIENT_FIRST_AUDIT_AND_P6_COMPLETION
required_response      = response_v65.md
ordinary_default       = UNCHANGED
NN_training_PC         = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

最终目标保持真空0.7nm、原50×25nm周期/z=-10..130nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet和Fourier-DtN、完整E/H/衍射/吸收；必要构建至输出和独立验收≤172800s。十进制约2e12B是整机物理内存且须留余量。本批仍为s=7/135有限NOTCH，既不是原尺寸，也不是允许本任务占满整机。

本报告覆盖V64已关闭窗口的执行队列和18000s单例上限，明确授权一次新的同空间P6尝试及相应保存后消费；旧失败、费用、报告和形状否决保留，不刷新旧账。不提高P6的192GiB规划额度，不授权L4超限网格、p7、第二轮标记或更多模式。新文件只保留这一版正文，以回读blob和本地文件校验保证交付一致。

## 1. 已审事实：哪些完成，哪些没有

读取固定HEAD的根/文档规则、仓库原则、task身份、最新response/summary及相关记录，核对上一review以来6次提交和当前数值核心。上一份review完整读取本地副本并核对远端blob `875eeacad19c9cc4c1862242e040a3e0ac98f37c`；目录未发现新独立supplement或Review V63。原task等同blob历史正文按原文继承。没有SSH、工作站PDE或大型数组复算；下述measured来自已提交证据。

证据：[回应](response_v64.md)、[summary](outcomes/summary.md)、[失败部署](outcomes/records/deployment_failure_v64.json)、[数组清单](outcomes/records/array_inventory_v64.json)、[最终费用](outcomes/records/resource_costs_final_v64.json)、[决策](outcomes/records/decision_and_not_run_v64.json)、[标记容量](outcomes/records/capacity_and_marking_v64.json)。

| recorded measured | 数值或结果 | 审阅边界 |
|---|---|---|
| P6实际空间 | 7680tet/p6，独立FE980352，native1005528，完整981180行 | 空间已构造；不是已解系统 |
| mesh/MPC | 17.924943s | 阶段时间 |
| q47/q63边界 | 60.583201/63.998702s；每包804624140B | 实际完整828包已保存，独立边界配对通过 |
| UFL/FFCx体组装 | 12203.710183s，约3.390h | 已执行；未细分编译与数值装配，不能把全部称为JIT |
| 未完成独立原式段 | 至少2490.803052s | 两列检查已开始但未完成，嵌套时间不重复相加 |
| 失败入口完整费用 | 15056.335016s，约4.182h | 不是成功T_N1 |
| 采样进程树峰 | 35811266560B，33.351GiB | 最大采样gap2.008412s；无numeric，不能预测factor峰 |
| L4相容网格 | 1267/7680标记，最终25576tet、1043792行 | 超19200tet/800000行；PDE没有运行 |
| 新全域factor/完整解/NN训练 | 0/0/0 | 新场、R/T/A、p/h增量全部not_run |

P6在预留审核/输出的边界受控SIGTERM，原supervisor的WORKER_FAILED/-15与语义CONTROLLED_STOP并列。不是OOM、不是预条件器不收敛，也不是P6物理精度失败。该预算是上一review规定的；执行者没有权限自行延长，不能将遵守预算归咎于“不愿继续”。本轮修正预算安排，不追改V64状态。

L4最初16.4974%单元覆盖50.018973%指标，但相容闭合产生3.3302倍单元；仅增加2条周期mate边，未启动全周期边界同步。故不能归因于True后备或称其已证明局部细化有效；该固定配置也并非一个比P6明显更小的全局系统。保留网格和负结果，不再仅提高形状许可或调theta重试。

数组清单只有标记、相容网格、q47和q63四个NPZ，**没有已发布的体K、全局A、factor或solution checkpoint**。因此不能承诺恢复旧体矩阵。先查直接清单及对应目录一次；若没有合法收据，就明确一次新UFL构建，不反复搜全盘、不从日志造矩阵。

P6实际source为`e28ce30b47797581176f2d5fa752b1f3539387c8`；保存消费者为`687663e2f7210c62808dfc54b7951369469ba520`。新producer、旧准备source、报告HEAD分别登记。

## 2. 针对性的执行优化，不改变Maxwell方程

当前`body_action`用精确键`(J.tobytes(), permutation)`保存整张变换basis/curl表。保存几何的确定性cache walk得到1118类、5932 miss、4814次重复建表；单类11337408B，512MiB只能容纳47类，全存约11.81GiB。**这是derived库存，不是逐类运行剖析，也不证明全部耗时都由cache造成。** 不允许舍入几何合类或把11.81GiB全库当免费缓存。

新方法的意思是：**先把一个单元的系数变到参考基，再用同一张参考表求场；积分后把作用向量按复对偶变回去。** 不必对每个几何类变换整张“积分点×基函数×分量”表。改变的是同一弱式的计算顺序，不是p、网格、求积、材料或残差门。

保持体弱式及完整相位：

```math
C_\kappa u=\nabla\times u+i\kappa\times u,\qquad
 a(u,v)=\int \mu_r^{-1}C_\kappa u\cdot\overline{C_\kappa v}
 -k_0^2\epsilon_r u\cdot\overline v.
```

### 2.1 行向量布局的明确代数合同

令J为真实仿射Jacobian，F=J^{-1}，G=J^T/det(J)；参考基及参考curl表为Phi、Psi，形状均为(nq,ndof,3)。T采用当前`TetraEvaluator.transform`的定义，即定向基等于T乘未定向基。先取本单元原生系数c（已由完整MPC primal P展开），然后：

```math
\widehat c=T^T c,\quad
 U=(\Phi\widehat c)F,\quad
 W=(\Psi\widehat c)G+i\kappa\times U.
```

每个积分点定义h=W/mu_r，z=i*kappa×h-k0²*epsilon_r*U。利用实kappa的恒等式，积分对参考测试基的贡献为：

```math
\widehat r_j=|\det J|\sum_q w_q
 \left[\overline{\Psi_{qj}}\cdot(h_qG^T)
 +\overline{\Phi_{qj}}\cdot(z_qF^T)\right],\qquad
 r_{\rm cell}=\overline T\,\widehat r.
```

最后共享行累加并执行P^H。当前Basix T为实数，但不得凭经验用inverse、忽略test共轭或把T^T和T^{-T}混用；复数合成反例用于检查实现。det符号用于curl，积分用abs(det)。H/curl单位及非零port载荷保持。不额外乘一次carrier，不将mu=1写成通用错误假设。非实kappa/曲几何/张量材料不在新opt-in资格范围，使用原正确路径。

不形成单元刚度矩阵、正规方程、参考Gram逆或新全局矩阵。参考表按basis/p/q/dtype固定，系数与场按cell/列小批次收缩。两个pre-solve见证可同批向量积分，每列仍独立验算与计数。保留原q17；不因优化降低q、抽查少数cell后冒称全域原式通过。

新核独立于生产UFL矩阵、旧15参考表和凝聚。生产A可作配对被比较的一侧，不能被新oracle读取或调用。原旧核保留为局部回归和正确后备，不monkeypatch旧oracle使新旧同调用自证。

### 2.2 最小资格与明确后备

只做本次改变需要的检查：非对角J、两种det方向、非零kappa、有损材料、实/复T的代数配对；保存P6几何上按材料/方向和几何跨度事前选最多24个实际cell，以固定复输入对照旧局部积分；再消费已保存V63 B的完整独立原式向量，做一次新作用复算（q15、原p5），不重求B、不重做它全部输出。

局部/完整作用相对配对门1e-10；显著cell增量不得因最终全局抵消而跳过。对近零项保留绝对量和固定operation scale，不根据结果改分母。必须覆盖MPC共享/复对偶、材料及完整port组合。**V64没有保存完整p6作用见证，不能声称已配对一个不存在的p6真值。** 新P6与UFL的两固定复向量对照在正式构建后完成。

必要资格目标45分钟，实际实现/修复另计但目标合计2小时。只做一次小规模新旧计时，列分配峰/完整作用时间；不要求取得人为速度倍数才准PDE，不重放旧全域p6慢oracle。若系数核未能及时通过，但旧代数可靠，允许唯一后备：**按原精确J/方向键分组处理cell，每组只生成一次旧变换表并及时释放**，固定原geometry不舍入，组外global scatter仍准确计数。后备也须同一局部及保存B配对。不允许全11.81GiB常驻或删材料/积分点救速度。

## 3. 必做的准备checkpoint：先保存昂贵成果，再运行下游

沿用V64相同P6空间，不重建L4。健康的q47/q63包分别按原receipt读取；二者保持独立，不能相互替代。旧包identity不完整就仅重建该包；不重跑完整旧preflight、全部边界资格或p4/p5解。

原P6 q47 SHA256=`458e7c5b109b816b1b53a471f166e9f704ba2a84ae8340c2af22f38985a54493`；q63=`12f0c97da871679ca1ff8211ccb7865214bc6402e60fa6983528a41084300721`。路径与成员hash按V64 array_inventory读取。新p6 mesh/MPC、mode、carrier、未舍入几何及basis签名必须一致，不能只按维数相同继承。

未找到合法K时只允许一次新标准UFL完整体构建。将原body父时间拆成JIT/form、PETSc assemble、CSR复制、P^H K P及IO子段；父子不叠加。不改UFL、编译器、积分或材料来追速度，不另开新的体装配算法研究。

**K在形成并完成形状/finite检查后立即落盘，早于两全域作用见证、symbolic和numeric。** 推荐存未缩放、已周期压缩的K的CSR数据/indices/indptr与shape，几何/tag/MPC/参考基/epsilon/kappa/k0/q/producer源码、边界引用和加载checksum。用分块npy或现有可恢复writer，避免为压缩/哈希再同时复制几GB；同目录临时文件写完后原子seal。

该包先标`ASSEMBLED_NOT_YET_ORACLE_VERIFIED`；只有后续完整独立配对通过才新增资格receipt。不能改写旧状态为PASS，不能从这个包给oracle生成真值。重载只需一致身份、文件hash和必要CSR检查；不重新UFL。保存完整矩阵checkpoint属于本有限参考的恢复机制，不是目标规模可长期存全局矩阵的批准。

不得保存全局factor或启用OOC。后续若已有合法向量返回，则先原子保存完整x/u/port，再审核和输出；JSON/collector/文档失败只补消费。若下游停止而只有K，则从K继续未做的步骤，不能又执行3.4小时组装。旧V64费用不清零，JIT缓存不等于矩阵checkpoint。

## 4. 一条完整P6计算与必要验收

保持7680tet、N1curl p6、独立FE980352、native1005528、系统981180行、完整828模式。物理为原s=7/135三维NOTCH（192个缺口tet），lambda=0.7nm、grazing1°/azimuth5°/s/幅值1；kappa=(8.94046081729244,0.7821889682108057,0)。Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；canonical材料hash=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。材料ready，不索要、不联网替换。

顺序Q系数核资格→PREPARE并保存K→原UFL/新独立作用两列配对→真实symbolic准入→原MUMPS完整求解→保存场→独立原式→释放factor/无用矩阵→完整物理输出→一次B/P6比较。只允许同一个数学case、物理零初值；不读取旧p5作warm start或造RHS。

两pre-solve见证已按输入hash、完整输出和源码保存则不重做；新kernel/数学相关实现改变时仅重判受影响项。两列可在同一次cell遍历中完成，但不能将两列算作一次向量作用。原式在全域每个cell执行，作用向量、rhs及分子分母落盘；新独立checker优先消费这些数组，不重复求解。q63 carrier的稀疏C/D/H可在本进程只建一次只读复用，不能由q47借用以抹去独立性。

formal true/native/augmented/port各≤1e-6；direct内部目标≤1e-10单列，MPC/恢复/操作identity≤1e-10，最多两次既有精化。不因为独立direct略超而无限精化，也不只报生产残差。方程不合格场仍保存diagnostic，不发布其official功率。

完整total/scattered E/H/scaled-curl、固定240点六个向量相对范数、828物理参考面复振幅、逐mode功率、R/T/A/A_volume和独立能量均须给出。与V63 B的主比较保持场/240点/复振幅1e-4、RTA/吸收/能量1e-5、逐mode功率1e-6；原左右分母和近零floor不变。比较在共同真实tet中直接评价原场，不投影、不拟合相位、不选择性删点。

P6冻结后才读取旧B系数用于评分。B/P6通过只授有限同h同828的p5/p6增量，不指定P6真值，不继承无限mode/全h/原尺寸资格。若仍失败，交完整新场、差分所在区域及实际规模费用，停止原样自动p7；不再将升级阶数作为默认无限循环。本批不运行L4、M、旧FLAT或第二个物理模型。

## 5. 时间预算与恢复是同一条账，不再先耗光准备再丢成果

新研发总窗口14h（50400s），科学有载≤11h（39600s），最后1h只收尾。**该完整P6任务本批累计执行配额≤10h（36000s）**，包括PREPARE、CHECK/SOLVE、AUDIT/OUTPUT及保存后恢复；不是每个dat各10h，旧V64的18000s硬编码不得继续暗中生效。旧V64入口15056.335016s保留历史，不能借新窗口写成旧尝试成功。

正式昂贵构建前，以V64实测12203.710183s体准备、新核实际批次工作量、上轮p5 factor和本次可靠symbolic做保守阶段预测。小批次外推标predicted，不给出保证速度。至少为独立原式/完整输出/新比较保留4500s，numeric前以真实剩余预算再次核对；不得为数字好看挪走必要审核费用。

若预测不容纳，先调整同一合同内的阶段排程、取消可选计时/重复消费、启用已资格正确后备，不关闭保护。确实不容纳则保存准备和缺口，不开始无收尾余量的factor；不能未经授权开启第二窗口或后台续跑。这里的控制停止仍允许诚实交付，不承诺必然求得新解。

通常只一个新numeric和完整求解；最多第二次仅用于已定位的科学实现错误修复，均受同一预算。没有返回向量而进程被终止时，新factor尝试仍计数；有合法向量后不准重新factor。标准体矩阵主构建最多一次，只有其数学被确证错误才准第二次受影响构建，否则从checkpoint恢复。

普通API/shape/dtype/路径/metadata/writer错误同轮最小修复、targeted回归后继续，不按bug个数停。累计修复及重放≤2.5h；同根因两次无效须换诊断/正确后备，不盲目第三次重跑。接线测试不成为整轮交付；原式/ABI/监督真不可信先隔离。不full pytest/CI、不重建全仓索引、不扫历史全部hash、不复跑旧FLAT/B/L4标记和原慢p6全域审核。

## 6. 内存、存储与共享硬件保护

| 角色 | planning / warning / sampled stop | 限制 |
|---|---|---|
| Q、默认最终消费者 | 64 / 80 / 96GiB | 无全域factor |
| 唯一P6构建、求解及其必要恢复 | 192 / 224 / 256GiB | 完整行≤1000000；不借给别的case |

numeric仍要求live树RSS+2×可信INFOG16/17(decimal MB)+2GiB≤192GiB。原33.351GiB是未factor的采样峰，397744956是支撑图保守上界，两者都不证明numeric准入。192GiB不是2TB整机可用的替代。内存profile必须贯通plan/dat/resolved/Journal/launcher/watchdog/assembly/factor/consumer，旧defaults不改。

额外工作区≤2GiB；参考表与小批次明确计费，不常驻全部几何表。MPI1/math1/CPU1、GPU0/Loader0、complex128及原int64 ABI、ownswap/OOC0、ICNTL22=0；原PSI/cgroup/宿主/384GiB邻增长余量及空闲物理核避忙SMT保持，一个自身heavy actor/一个factor。不改邻进程、系统BLAS/CUDA、全机swap或共享Git设置。

新ignored≤64GiB、Task去重累计≤344GiB、free≥50GiB、evidence reserve≥512MiB；此磁盘扩展只为有限K checkpoint与完整场，求解前按实际nnz核算临时原子双份，旧失败不删除。只检查本批与直接引用父包；CPU、IO和哈希均计入完整成本。保存事件不能替代落盘数据；max sampling gap与sampled峰分列，不把0.5s配置称连续硬峰。

## 7. 对2TB/48h的诚实贡献和邻支分工

本批必须交付：一份新P6完整场及B/P6差异，或者明确已完成到哪一持久阶段；独立作用每次时间/工作区和新旧局部配对；体JIT/组装/拉回/IO拆分；真实nnz、fill、symbolic与numeric容量、全过程峰和完整N1。不能只交一个快kernel或新的文档版本。

成本分三层：本次成功链；V64失败15056.335016s加本次的研究总投入；可复用boundary/K后的prepared-start。父边界约124.58s及旧构建费用按实际重用和丢失说明，不将读取时间冒充fresh。若没有配平同精度旧完整解，不授生产加速比；仍必须测当前成功进程及恢复链的完整费用。

系数先收缩的向量积分若合格，可以成为以后matrix-free作用的可复用小核，但**本批没有验证可扩展预条件器、MPI吞吐或无因子全局求解**。当前任务继续有限直接参照；长期仍要从无界全局LU/显式大耦合转向凝聚trace迭代、分布式matrix-free、流式DtN、有界粗问题和分块恢复。2TB显著放宽预算，不消除复杂度；原尺寸合格网格/模式/PC/迭代/全流程RSS和172800s仍unknown。

邻支只读：Task42extra `427c1762ea8838f35a13bf2a0ebc1ad3ab46c63c`已封存V33神经结果，保持独立；工程`33614413731d739d2c0f57106df180c359f4343f`仍为此前Ny8/容量合同；dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`仅核对ref。不重复神经训练、M5/teacher、参考PC、通用CSR或dot边界开发，不推断未推送本机状态，不通知/改写邻工作树。

## 8. 最小提交计划、正式入口与交付

C1：新opt-in coefficient-first核、局部/保存B作用资格及必要scope。C2：体checkpoint、prepared-only重开、完整case费用与两向量/原式的可恢复消费。通过相关targeted回归和dat validate后commit clean，再正式运行；活跃actor的受检源码不热改。公共数值进入src/solvers，复用`independent_tetra_reference/study`、原Journal、run_case和writer，不复制大型runner或重写一套缓存系统。

待创建one-run入口，每项只表示明确阶段，全部共用同一P6预算：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v65_oracle_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v65_p6_prepare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v65_p6_solve_complete.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v65_compare_verify_cost.dat
```

PREPARE不暗藏factor/solve；SOLVE从合法准备收据进入两向量资格/因子/完整输出；VERIFY只消费保存场，不重新构建矩阵。中断补消费用额外明确one-run输入，继承同一累计预算，不刷新次数。上述入口尚待实现，审阅报告不声称可运行。

交付`response_v65.md`、`outcomes/coefficient_first_p6_completion_v65.md`及紧凑records：qualification、stage/checkpoint清单、实际P6解/原式/全输出/比较、互斥成本/峰/采样、repair和not_run、唯一下一最小步骤。旧task/review/response/raw保持；summary、README、development_progress和development_model_registry只追加可理解条目。重型CSR/场/基表留ignored，Git只存增量必要身份，不重复扩写数千行历史manifest。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

最终核对精确remote SHA/upstream/clean、closed/active null、后代清场/锁释放后交付用户暂停。不merge、不改master/邻支、不自动开下一窗口。本报告发布只写同一执行分支，并回读Git blob；下载副本必须与远程字节一致，禁止再次出现同编号两种执行合同。

## 方法依据与审阅端边界

[DOLFINx有限元变换说明](https://docs.fenicsproject.org/dolfinx/v0.10.0/cpp/fem.html)给出定向基phi=T*phi_ref对应c_ref=T^T*c，并提醒T未必正交；[Basix 0.10](https://docs.fenicsproject.org/basix/v0.10.0/python/)提供参考表、Piola与实体变换。只能使用现有资格ABI，不能为接口名升级环境。本文行布局公式由原弱式展开，必须在真实Basix对象上验证后使用。

审阅端完成了合成复数非正交变换、正负det、非零载波与有损材料的收缩代数检查，以及文件结构和身份校验；没有执行真实FEniCS/PDE、重新计时旧oracle或重算工作站大数组。新性能与精度均为planned，实测后才能下结论。GitHub视觉若未实际取得则为NOT_VERIFIED，不以本地Markdown检查冒充页面通过。
