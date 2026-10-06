# Review V54：完成已保存全场，打通无JIT后处理，再做一次必要的方向对照

## 0. 决定、身份与目标

**V55确实求出了H7完整有限元系数，但还没有回答H7是否比原场更准确。下一轮不重算H7，不继续增加p或模式，不恢复NN预条件器。授权V56首先把已保存解变成完整、可独立验收的E/H、体吸收及h增量结果；用不需要新FFCx编译的同一物理积分消除已定位的后处理阻塞。完成后，按预登记条件只做一个原已选定的X2Z2/p6/828横向对照，同时建立准确性与2 TB/48 h成本之间的明确连接。**

要消除的blocker不是“又缺一个求解器”，而是：昂贵完整解尚未被消费；高阶差异尚未解释；科研流程反复在求解后的编译/准入处断开。新工作的最低实质交付是H7完整物理结果和R7/H7、R6/H7实际比较，不是又一份接口测试报告。不保证精度必过，不降低任何物理门。

```text
repository            = Rookie1234567/MyFEniCS
branch                = task42_neural_coarse_inverse
canonical_worktree    = /home/fenics/Projects/NN-Lab
review_date           = 2026-10-07
reviewed_HEAD         = ad43a80fe3f301f7e61ea40db02fdef509497a68
latest_commit_UTC     = 2026-10-06T17:53:02Z
latest_response       = response_v55.md
previous_review       = review_report_v53.md
previous_review_SHA   = e3b46656fd13b31a465a628f7fdeb863e32f38ed
original_base_SHA     = ccd357885f7f9be84efe3be07868cc94f13d93fc
H7_solve_source       = 5e61f1acf569bf43b33bceeebcc949e1b0f1efc9
next_batch            = V56_SAVED_FIELD_CLOSURE_AND_TARGET_BRIDGE
required_response     = response_v56.md
new_complete_solves   = at_most_1_conditional_T6
NN_training_PC        = NOT_AUTHORIZED
merge                 = NOT_APPROVED
```

本报告回应已关闭V55，不重开其时间窗。覆盖“后处理必须经过原FFCx体吸收编译路径”、补审依赖旧solve预算、固定资源重入次数等本批执行限制；保留数学定义、精度、邻任务隔离和64/80/96 GiB上限。旧FAIL/not_run不回写。若发现真实原方程错误，先隔离依赖，不凭当前报告重算多个父场。

最终目标：真空0.7 nm，原50×25 nm周期、z=−10..130 nm、任意非可分三维周期材料/几何；单次从必要准备到完整输出≤172800 s，约2 TB整机保留系统余量，无自身swap/OOC。研究累计费用不是单次求解费用；缩尺场、方程残差通过、缓存运行快，都不等于原尺寸目标通过。准确空间、分布式/matrix-free作用、流式DtN与可扩展迭代仍为生产方向，有限直接法仅作authority。

本审阅实际刷新Task42、两NN支线、工程/dot及工作站容量ref，读取当前回应/专题/summary、相关源码和修复、5个后续提交。根规则、仓库原则及task已核对，同blob历史规则继续复用；目录未出现新supplement或Review V54。最新Review V53完整本地副本与已读远端一致。未SSH、未消费工作站ignored全数组、未运行新PDE；下文实测均指仓库recorded measured。新执行内容均为planned/not_run。

## 1. 综合审阅：进展与尚未完成的目标

依据：[V55回应](response_v55.md)、[完整结果](outcomes/spatial_resolution_audit_v55.md)、[修复](outcomes/records/repairs_v55.json)、[保存检查](outcomes/records/partial_saved_checks_v55.json)、[费用](outcomes/records/resource_costs_final_v55.json)。

| recorded measured | 已取得 | 不能推出 |
|---|---|---|
| V54的R6/R7/C | V55新进程q63原式、内部恢复和全部模式功率通过；R6/R7实际切向连续性通过 | 原同828跨p散射差3.413%仍FAIL |
| H7：320hex/p7/828 | 330848独立FE、88928 trace、241920内部、346724 native；89756凝聚行；true4.20391286913e−11 | 不是已获空间准确性 |
| H7存储/资源 | 完整u、port、几何/MPC、恢复、320中心点及828模式已保存；采样峰22.833797GiB、swap/OOC0 | 320中心点不是固定240点或全域L2/curl审核 |
| H7输出 | R=0.0762050392207，T=0.905659241741 | R/T接近R7不证明全场接近；A_volume/能量、fresh FE、R7/H7、R6/H7未完成 |
| H7成本 | raw生成12393.272s；局部消元52.743s；symbolic/numeric5.433/192.818s；solve/精化14.232s；dat下界13627.055s | 不能说3D场只需14s；当前未测同精度整体加速 |

raw约占该dat下界90.95%，末端symbolic/numeric/solve/精化约1.56%（derived，同一口径，不再与parent计时相加）。当前有限问题优先级是准备与输出、准确性，不是再次训练NN逆。该比例不能外推原尺寸，global factor的增长风险仍存在。

V55停止有三个不同原因：主actor预设wall耗尽；恢复过程中命中被中断编译留下的0B独占marker；后续CPU/SMT门拒绝。前两项需要流程/实现处理，最后一项要区分真实争用与自身盘点错误。不能将三者统称“算法失败”，也不能关闭安全保护。上一份review把长准备和尾部输出放入同一个紧的case窗口，预留不足；本轮取消这种对保存状态的solve预算绑定。

### 1.1 跨支线分工：复用，不复制整个研究

| 本次只读ref | 最新事实/分工 | 本Task42本轮边界 |
|---|---|---|
| task42extra_feinn_5nm @ 8d617d4d206b08f38279320b67188db1b8ccd301 | Review V29授权5nm起步学习波动greedy；remote未增加新结果 | 不做M5、方向学习、teacher或NN-PC；不推断本机闲置 |
| task42extra_NN-V3-learned-iteration @ 1f01ae46bbe21f17200350a46513ef5f33e5cf6a | 远端仍为学习迭代规划 | 不判其失败，不接管 |
| task40extra_0p7nm_engineering @ a5d3ee6fa767d9dea4ee50a792a570994f9cad16 | V11端口平面功率修复成功；Gx560仅symbolic，numeric前资源停止；局部全模式动作有范围资格 | 不再开发周期参考逆/端口坐标修复；不同gauge/空间不能直接搬解或继承精度 |
| task40extra_dot_parallel_cloud @ 15713d3e09b63f65511c7b7f61fa043fdb23dca5 | 原尺寸selected边界完整882路线、共享/结构参考组件；非目标全场 | 不做84压缩或重复原尺寸边界campaign |
| task39extra_para_workstation_capacity @ aaa8fb8ecf97dca5ff55a1aeccacd28271940da7 | 准确p3/p4粗修正与较大短波容量路线；目标未闭合 | 不重开同类粗逆扫描，不改其运行 |

工程V11的B0三步是同离散求解/输出证据，不是当前相位gVh的准确性证据；其Gx560内存拒绝是笔记本当时配额/可用量，不是2 TB上的no-go。引用准确source/物理身份，缺实际兼容包时不等待邻支；本轮不迁移新求解器源码、不merge、不发送邻窗口指令。

## 2. 冻结输入：只读已有完整H7，不让FAILED外壳吞掉合法返回

H7旧最小记录：`benchmarks/artifacts/task042/v55/task042_v55_notch_z4_p7_m828_20261006T133138354262Z/minimal_scientific_state.json`，SHA256 `e9e76087958cd77300aa8ee189c23a0eecf121224057d88c2b380bb9b1b1d1ef`。

同目录`solution.npz`：SHA256 `c20cf4dc586095244e58cbddd73f0f972c6cdc737944fbffedaba2ab66115b50`；u_storage成员hash `d87be1194af2b5bd07d0f860e003cf99e699823c81b2b1b54860e8d545c1097d`。完整receipt见上述partial_saved_checks，不手工补造不存在字段。R6/R7由V55已通过Q0的父清单读取；C只复用已有模式资格，默认不再消费全场。

保持缩尺s=7/135、真实NOTCH盒、V51–V55全精度轴节点，λ0.7nm、grazing1°/azimuth5°/s/幅值1；Si n=0.999885140474+4.32477054e−6i，ε=n²、μ=1，air=1。材料hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`，不再索要。κ=(8.94046081729244,0.7821889682108057,0)，E=g u，Cκu=curl u+iκ×u；Hcode=g Cκu/(ik0μ)。原828模式m±11/n±4、上下×s/p，参考面/相位与背景不变。

新V56独立ledger、输出目录和消费清单；旧主actor失败状态仍保留，但有完整返回receipt即可进入`SAVED_SOLUTION_CONSUMER`，不能要求旧整个stage COMPLETED才能读它。这里只创建mesh/space/MPC来解释系数时不创建factor，不调用solve_case。旧producer SHA、新consumer SHA、旧失败和新结果分开。只核对实际消费文件一次，不扫全部历史目录。

## 3. 必做S：无新增FFCx体吸收编译，完成同一物理积分

### 3.1 为什么这不是降低精度

当前`physical_output`调用`compute_volume_absorption_3d`，其`fem.form`会为体吸收标量重新JIT。H7正是在此未完成。本轮新增显式opt-in的直接求积后端：读取原有限元函数在原单元上的值，再按同一材料与归一化积分；不改变场、材料或吸收定义，不用A_balance代替体积分。

当前κ为实数，故g的模为1：

```math
A_{\mathrm{vol}}=\frac{k_0}{2P_{\mathrm{inc,code}}}
\sum_{K\subset\mathrm{physical\ materials}}\operatorname{Im}(\epsilon_K)
\int_K\sum_{a=1}^{3}|u_{h,a}(x)|^2\,dx.
```

使用total包络；不对散射场积分，不用Im(n)，不漏substrate，不重复计算notch/air，不加入PML，不把负值裁成0掩盖错误。region体积由真实仿射Jacobian求和。原code/SI单位与`incident_power_3d`保持，比较R+T+A_volume−1。

复用`PhaseEvaluator`/`CachedPhaseEvaluator`的真实系数、方向变换和Piola；不是节点平均或320点采样。每批最多若干单元/256点，表和场块合计≤2GiB，边算边保存逐cell积分与累计和，不长期缓存零命中的整表。优先沿已冻结q23/q31两规则，显式保存真实点权hash和点数。Basix的degree是多项式精确度而不是每轴点数，禁止混用接口含义。当前仿射、单元常材料与p≤7下，这远高于吸收多项式所需分辨；仍实际做两规则一致性，不能外推曲面/变材料情形。

先只对已通过Q0的R7全域体吸收做一次无JIT对照：与其已保存FFCx结果相对操作差≤1e−10，保留绝对差/分母；再用少量真实H7点与原native求值配对，E/H/curl操作差≤1e−11。复用已有求值资格，不重跑R7 PDE或其完整两两场比较。通过立即消费H7；失败先查归一化、方向和材料区，不延长编译作为唯一出路。参考：[Basix 0.10 quadrature接口](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.quadrature.html)。

### 3.2 同一保存链完成全场比较与独立原式

S内连续完成：H7体吸收/能量、固定240点、R7→H7同p同M的h增量、R6→H7跨p诊断、全部828参考面复振幅与逐模式功率。共同几何细分上分别求两个原gVh场，保持total/scattered不同分母、全复交叉项、q23/q31和原选点规则。逐pair/积分块原子保存；中断只续未完成块，不再读取所有结果重来。

新进程H7 q63原未凝聚式/恢复审核仍须补上，但**它不能成为体吸收和场比较的启动前提**：三项独立消费者可先交付已完成者，最后才合并完整资格。优先复用现有`verify_cost`必要作用；不误走raw构建、凝聚或factor。若该路径也触发不必要长JIT，允许用V54已资格的公开Basix单元方向积分和MPC复对偶散布小核扩为同一保存u的完整原作用，一次处理全部cell、全部q63端口；只构造向量不构造全局矩阵。

独立体行定义保持：

```math
(a_{\mathrm{vol}}(u))_i=
\sum_K\int_K\big[\mu_K^{-1}C_\kappa u\cdot\overline{C_\kappa N_i}
-k_0^2\epsilon_K u\cdot\overline{N_i}\big]dx.
```

方向变换与MPC的共轭对偶只施加一次，内部/trace均保留。端口由已有完整q63接口重建或独立公开求积，不删除小非零支撑。以已通过R7保存原式作一次作用回归，保留curl/mass/port分账；不能只用原凝聚矩阵或原raw张量自证。替代审核独立标`PUBLIC_BASIX_UNCONDENSED_AUDIT`；旧FFCx重运行未做就仍not_run，新的等价独立审核通过可以完成本批科学门，不要求把两条审核都重做。该替代仅在必要时使用，不另建通用FE框架。

**S不得新建numeric factor、不得重新生成H7的38类raw核、不得求解H7。** 正确的saved消费得到结果即保存；不得因总结果对象还缺一个展示字段就停止整个物理链。

## 4. 条件T：只做已经选定的一次横向对照

S完成H7体吸收、完整比较及一种合格的独立原式后，若仍有空间增量/跨p分歧超门，且总预算中能容纳完整T及≥1800s审核，直接运行已选定T6，不再次等review：

```text
same physical NOTCH / lambda0.7 / kappa / 828 modes
splits=(2,1,2), p6, 320 cells
independent_FE=209664, trace=65664, interior=144000
augmented_condensed_rows=66492  (derived; actual MPC must agree)
```

x方向已经由V55的R6指标选定（x=4.69448034950e−5，y=2.77634598163e−6），复用该决定，不再重新选轴或跑x/y二选优。T从物理零初值直接求解，不用旧场造RHS或初始化。保持现有MUMPS、端口坐标、精化上限、相位弱式和所有模式；不扫PC/ordering/shift/BLR/OOC。真实hit/miss规划、可靠symbolic与64GiB numeric门保持。

T之前必须先确认无JIT输出已在H7成功。完整解返回立即保存；solve与后处理用独立可恢复阶段，不把某个子阶段wall耗尽解释为没有场可消费。T也采用同一输出后端。主比较R6→T；与R7及H7只作为跨p差异诊断，不将更高p指定为真解。最多一个新完整solve，不追加p8/Z8/新模式/新尺寸；若有真实原式bug需要重解父场，本轮隔离该错误并交付原因，不将T槽偷换成无界重算。

S未完成时不得先开T把输出问题再次复制；T时间/容量不足不妨碍S与§5完整交付。若h增量小而跨p差依然大，停止“原样升p/加h/加M”的循环，下一步只提出一个明确的离散稳定性或独立表示验证，不伪称已收敛。

## 5. 与2 TB/48 h相连的交付，不再只写下一p值

在S后、T前先保存一页target-gap与成本表，最终只增补T。它不是自动放大运行许可。

| 对象 | 本批必须输出 |
|---|---|
| 当前缩尺最可信结果 | 原方程、独立体吸收/能量、完整场/固定点/模式；哪些h、p、M方向实测一致，哪些仍FAIL/unknown |
| 单次成本 | 从必要raw/JIT/mesh/MPC到恢复、输出、审核的非重叠账；fresh必要准备、缓存增量、研究累计分列 |
| 当前瓶颈 | 12393s raw准备与新无JIT消费的实测费用；不把14s solve称端到端，不把一次缓存命中当目标冷加速 |
| 两个桥接规模 | s=14/135与28/135，λ仍0.7；仅descriptor/库存/布局规划，不建完整网格/矩阵/factor，不运行PDE |
| 原尺寸目标 | s=1、同物理规则及实际通道inventory；引用现有32060只是旧明确模型的记录，新角度/材料/规则要重新生成metadata并绑定，不能硬抄 |
| 求解架构接口 | 相位gVh/κ、完整模式键与参考面、原作用/恢复数据、材料几何身份及资源表；工程参考逆未在该空间资格化，不能直接继承三步结果 |

桥接空间仅用于容量情景：在参考p6/p7布局上按尺度同步增加区间数以保持物理单元尺度，注明不是已证明accuracy-qualified。结构化xy周期、open-z的Nx×Ny×Nz网格有：

```math
N_{\rm FE}=N_xN_y p^2(3pN_z+2),\quad
N_{\rm int}=3N_xN_yN_z p(p-1)^2,\quad
N_{\rm trace}=N_xN_y p[(6p-3)N_z+2p].
```

校验现有H7行数后再用于derived表。实际不满足这类拓扑时不用公式。端口计数、16N个字节的单complex128向量、所选Krylov库存、tensor/recovery/trace/mode的共享与复制、流式边界工作区逐项列出。global/local factor fill、迭代数、跨rank复制及全过程RSS未测就unknown，不能用线性/立方外推授可行性；不为表格引入新的PC参数。

物理内存预算用实际有效RAM/cgroup和系统余量；最终目标的2TB不是本任务单进程额度。48h检验必须含必要准备、每步作用与PC、全部迭代、恢复/输出，不含免费的预先训练或遗漏的因子。后续生产候选必须避免无界全局直接粗因子与显式全域mode耦合；已有工程/工作站路线只读比较，不在本轮重做。

本轮允许没有新T但交出完整H7场及明确target-gap；不允许用只有字段/测试通过替代S。若现有数据不足以预测48h，给出必须实测的一个下一pilot及其最小观测量，不捏造成功概率或耗时。NN仍留给独立支线；只有准确任务上存在足够大的可替代成本，才重新评判训练净收益。

## 6. 数值门、修复与资源组织

原true/native/增广/port各≤1e−6、直接目标≤1e−10；恢复/MPC/原作用identity≤1e−10。total/scattered E/H/scaled-curl、240点、参考面复通道增量各≤1e−4；R/T/A/A_volume增量和独立能量≤1e−5，逐mode功率≤1e−6。共同q23/q31操作差≤1e−10。量接近零用既有冻结尺度，不拟合幅相、不改分母、不归一化守恒。仅R7/H7通过是该p/M有限h一致性，不代表跨p、无限模式或连续误差界。

CPU/SMT、PSI、内存、ABI和输入身份真实不安全则不启动依赖计算。本报告**不授权抢占/更改邻任务，也不因“只做checker”取消监督**。允许正确排除已结束的自身PID/自身监督器重复计入；必须有PID/starttime/topology与最小反例，不能把活跃宽亲和线程一概当闲置。先选一个合格物理核，在同一个持续受监督的saved消费actor内顺序完成多项输出，避免无必要退出、再装环境、再抢准入。

新7h总窗口（实时UTC/monotonic/boot_id），科学有载≤5h、最后45min收尾，意外实现修复/受影响重放累计≤2h，均计入总窗。取消固定bug次数和资源episode次数卡：相同根因两次失败必须换诊断或走本报告等价回退；资源探测相隔≥120s、累计前台等待≤1800s且每次原门恢复才重入，无后台无限重试。合法向量、逐cell积分块和逐状态审核先保存；writer/路径错误只补消费，不重新factor。

先分S与T的真实剩余预算，S目标有载≤5400s，T准入要使用实际缺失raw类与旧每类成本，并保留完整验收余量；该目标不是允许在总窗外续跑。性能超预期先取消T/可选文档，不中断已返回场的合法保存。科学依赖真正坏或总资源耗尽如实partial，不承诺一定成功。

沿V55的64GiB同时规划、80GiB warning、96GiB采样整树停止、100000行准入；无需再次加内存。S不应接近该额度，分块表/工作区≤2GiB，先估算总同时内存。T numeric仍要求live树RSS+2×可信INFOG16/17(decimal MB)+2GiB≤64GiB；OOC/ownswap0。MPI1/math1/GPU0/Loader0；原MemAvailable≥max(128GiB,有效物理10%)+384GiB邻增长+96GiB本任务预算，原cgroup/PSI更严取更严。采样停止不是连续硬峰，报告实测间隔。

不新清理旧JIT目录。若现成无JIT路径之外确需复用编译缓存，仅核实本任务失败marker所属source、无活跃producer、无ready模块后，将对应单一残留原子移入证据；不能删邻任务cache、全局清空或升级FFCx/Basix/BLAS。S的吸收正常路线不再依赖此修复。

新ignored≤8GiB、Task042去重累计≤92GiB、free≥50GiB，保留旧负结果，只在阶段边界检查自己目录。不例行全库pytest/CI、全仓索引、全部旧hash扫描、旧FLAT或父R6/R7/C重新审核。只做新consumer/积分/恢复段/条件T接线targeted回归、相关Ruff/compile与一次紧凑文档检查。无需为表格/可选可视化再次运行PDE。

## 7. 实现、提交与一次交付

复用`phase_spatial_resolution`、`phase_notch_hp_fields`、原restore/原式、已验证raw reader、独立mode checker和事务writer。新增积分小核进`src/postprocessing/`，新队列薄封装，不另拷贝数百行求解器。后处理backend显式opt-in，ordinary默认不变。先targeted回归、commit clean与validate；代码提交或一个stage PASS不是整批结束。

待实现的三个one-run入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v56_complete_saved_h7.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v56_notch_x2z2_p6_m828.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v56_verify_cost_bridge.dat
```

第一个入口完整消费S，不能暗藏solve；第二个只有条件通过才运行；第三个补未审项/结算与descriptor桥接，不重复已完成审核。子块恢复仍是同一明确输入/父hash/预算，不以新run清零费用。旧文件不存在或缺字段须从实际producer建立适配，不伪造路径或零值。

提交计划：①最小saved积分/调用链修复及targeted证据；②S完整结果和阶段决策（无活跃actor时），随后继续获准T；③条件T及最终增量结果。不得改活跃运行所绑定源码。交付`response_v56.md`、`outcomes/saved_field_closure_target_bridge_v56.md`和紧凑records，至少包括H7完整体吸收/场比较、独立原式、所有mode、T决策/结果、目标缺口/费用、repair与停止原因。记录input_original.dat、resolved_config.json、run_manifest.json、run_summary、物理/离散/模式/材料/source/父数组hash及全过程资源。

README/summary/两总账追加短入口，旧task/review/response/raw不改；producer与新consumer来源清楚，GitHub视觉不可取如实NOT_VERIFIED，不为页面重解。S已完成就先生成最小科学结果/费用包，最后只补交付时钟和Git状态，不再嵌套复制海量历史JSON。

只安全fetch/ff-only同一canonical分支，不reset/stash/clean、amend或force push。仅`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。最终核对remote/clean/upstream、closed/active null、后代清场与锁释放后交付用户暂停；不通知隔壁、不改dot/master、不自动开新窗口或merge。
