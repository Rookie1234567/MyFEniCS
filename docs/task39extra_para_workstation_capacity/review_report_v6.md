# Review V6：保留准确p4逆，迁移setup/单步加速并核算0.7 nm / 48小时差距

## 0. 决定、身份与用户最新边界

**接受F2为“成功构建离散算子和准确因子、完成228步，但尚未收敛的OOM中断证据”，不称合格参考解。批准Codex选择性迁入Task39extra最终已测性能组件：先处理低扰动监督和H6对角，再加速同一准确p4求解的应用与完整验算。正常完成一场新5 nm回归、一次2 nm同模型16步性能pilot及0.7 nm容量/48小时路线账；不原样重复一周长跑，不直接启动最大0.7 nm模型。**

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task39extra_para_workstation_capacity
review_date                 = 2026-10-02
reviewed_target_HEAD        = c6a7ea25753f116cb7fa7ca871fd8cf29d449444
previous_review_response    = review_report_v5.md / response_v5.md
F2_numerical_source         = 64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa
F2_run                      = 20260924T104936.107285Z
donor_branch                = task39extra
donor_closeout_HEAD         = 3804ede8acfd120d0d8d312415ec5e7a2c296cd7
donor_review_response       = review_report_v30.md / response_v34.md
donor_V31_numerical_source  = d9b545e824296fce1b489c32a5d96e5e9303ff3c
donor_V29_cost_source       = 780f58918b0e5a9868cd2ea3de26d451bc6b5d86
batch_id                    = review_v6_exact_p4_speed_and_0p7nm_48h
execution                   = E0 -> E1 -> E2 -> E3 -> F5 -> P2 -> R48 -> Z
response_required           = response_v6.md
coarse_solver               = existing exact condensed p4 MUMPS; unchanged
low_memory_p4_inverse       = NO_NEW_RESEARCH_OR_RETRY
resource_stop_policy        = measured_tree_rss_only_v3
rss_hard_limit_bytes        = 1300000000000
normal_new_full_PDE         = one 5nm p6/h4 q4
normal_2nm_work             = one p6/h1.5 q4 setup + 16 outer steps
0p7nm_target_full_PDE       = NOT_AUTHORIZED_IN_THIS_BATCH
ChatGPT_changes             = this review only; no migration/merge/PDE
Codex_changes               = selective integration, tests, runs, evidence
master_merge                = NOT_APPROVED
```

本批消除的blocker：TB工作集的监督反过来干扰计算；H6对角仍有昂贵重复工作；每次粗修正内部耗时未拆清；已有准确路线缺少可信的并行吞吐和0.7 nm/48小时容量账。最终目标不变：约2 TB整机内存内，complex128、Nédélec H(curl)、双Floquet、Fourier-DtN、任意非可分三维周期单胞的0.7 nm解。

**用户本轮明确要求不再研究低内存p4逆。** 本批固定准确p4凝聚MUMPS，不复试递归p2、实体patch、recycling、宏块、ILU、BLR，也不以“有界粗层”“子域替代”改名重新安排。是否仍有科学可能性与是否值得当前投入分开；本轮该方向新增试验数为0。若48小时目标仍有缺口，如实量化，不自动恢复旧研究。

本review覆盖V5旧批次继续运行和过期额度，建立独立新批次；不重跑已通过的R13 pair，不把本批首场算作旧bug replay。仅第6节明确授权有限线程/内存放置对照，其余保留现有算法。旧任务书、review、输入、失败、OOM和成本账不改写。ChatGPT只新增本文件；代码迁移、测试和计算由Codex执行，不整体merge/squash/reset研究分支。

48小时是最终目标模型的端到端验收目标，不是开发工期，不追溯变成旧run的杀进程门槛。P2的16步是预先声明的诊断终点，不是换页或时间预测触发的资源中断。

## 1. 已核对结果及因果边界

执行前读根/目录AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、[V5](review_report_v5.md)、[response](response_v5.md)、[summary](outcomes/summary.md)。源task、两份补充授权、[最终报告][S1]、[收口review][S2]、[Response V34][S3]按固定SHA读取。远程审查覆盖已提交证据和关键源码；未通过SSH重测主机、重读所有大型场数组或重跑PDE。

### 1.1 F2已知是node1受限分配OOM，不是RSS Gate触发

来源：[终态报告][T1]、[内核摘录][T2]、[运行路径与成本][T3]。以下属于同一2 nm Si、54332-cell、p6/h1.5、q4、3904通道run。

| 项目 | 实测或原始记录 | 解释边界 |
|---|---:|---|
| 结束 | 2026-10-02 11:52:46 UTC+8内核OOM，exit137，后代清场 | 不是RSS watchdog主动停止 |
| OOM范围 | CONSTRAINT_MEMORY_POLICY，nodemask=1；触发PID1172428，victim为worker341839 | 触发进程的任务归属与具体策略unknown，不指责任何邻项目 |
| 事件时内存 | node1 Normal free约448.629 MiB，低于min约451.973 MiB；全机free约887.976 GB | node受限分配和整机余量不同 |
| 整树RSS采样峰 | 1154381864960 B | 未观测达到1.3e12 B |
| 任务VmSwap峰 | 8574500864 B | 不能称zero-swap生产资格；全机换页不可全算入本任务 |
| 外层进展 | 完成228步，Schur报告9.3730498238e-5 | 最近独立原A6在224步，为9.7583165624e-5，未达1e-6 |
| p4调用 | 460条logical return通过；symbolic/numeric/MatSolve=1/1/686 | 粗返回通过不等于fine收敛；无正式RTA |
| 保存内容 | 224步full/retained解和恢复packet | solution-only，无factor/Krylov basis，不承诺免setup续算 |

原worker使用CPU24、`numactl --preferred=1`、MPI1并允许node0/node1，不能称strict membind。触发OOM的分配掩码不能直接当成本worker的策略。OpenMPI通用“Per user-direction”不是用户手动停止证据。旧9月20日global-swap停止与本次10月2日kernel OOM必须分开。

### 1.2 setup和单步的主要成本

| 同run计时 | 秒 | 占比或范围 |
|---|---:|---|
| 中断workflow | 666232.838509 | 185.06468 h，非完成时间 |
| setup | 184388.380644 | 51.218995 h |
| H6 diagonal | 118597.092899 | 32.94364 h，约setup的64.32% |
| H6准备父区间 | 120224.788820 | 含对角与power10，不与子项相加 |
| p4 numeric包围区间 | 44111.673835 | 12.25324 h，一次factor，非独立API timer |
| native/packed作用及端口对象准备 | 8844.889649 | 约2.46 h，内部份额未全部取得 |
| p6 / p4 tensor核 | 292.124320 / 33.861449 | 合计仅setup约0.177%，已经6组复用 |
| 最近221–228步callback均值 | 2136.747273 | 35.61 min/步，含检查/保存，非纯KSP API时间 |
| 最近完整PC的两次C | 1607.683174 | 26.79 min；其中ledger内部1537.870988 s |
| 同PC两个A6 / 一个H6 | 222.840168 / 146.099034 | 三类已计时子项中C约81.33%，不是完整PC严格占比 |

p4 ledger含RHS缩减、MatSolve、内部恢复、原A4体积/DtN验算及闭合，不能把26.79分钟全叫LU回代。该PC的第一粗修正有一次额外精化、第二次没有，比较必须计入实际工作量。

[PSS观察][T4]记录每次smaps_rollup约6.58 s、parent CPU约6.33 s。旧5 s调度在扫描前更新，扫描超过间隔后连续重复，并看到worker分配等待；H6父区间worker CPU采样差约18044 s、parent约115503 s。这是强性能疑点，但没有TB同工作集PSS-off配对，不能把33小时全归因PSS，也不能宣称关闭后一定只需5小时。

### 1.3 不能把已有优化重新算作新成果

本场p4已经是4586288行、2070391064 stored NNZ的凝聚增广矩阵，不是旧1061万行full-p4增广分解。p6 retained+ports为10803256行，full storage为35594790行；每阶54 raw几何类、6 tensor组、87定向Schur/LU/recovery类。双凝聚、类型共享和sum-factorization已经存在。

未全部继承的重点是：A6 curl/mass融合、快速完整A4验算、reference-metric H6对角、H6自然积分点顺序、低扰动监控、blocked Gram。优先级不同：完全消除约326秒tensor积分也不能解决51小时setup。

## 2. 低内存p4逆的取舍与迁移范围

### 2.1 有限候选失败不是数学不可能性，但本批不继续投入

| 已试方向 | 历史真实结果 | 当前决定 |
|---|---|---|
| V6 p4迭代+p2粗层 | 固定RHS 0/6达1e-4；外层13步原A6约0.66784；控制中剩余场误差约99.8%，准确C约38% | 不扫inner次数/p2参数 |
| V7实体/顺序patch | 121/88步后原A6约0.04256/0.06386，未达冻结进度线，未得到合格场 | 不因工作站内存较大重试同一方案 |
| V9等新工作量recycling | 控制RHS部分改善；正式38步残差约0.1292，增加方向管理成本，未完成 | 控制改善不等于完整外层收益 |
| V17 BLR | RSS仅较准确基线低约5.45%；控制场误差约0.60–0.68，质量门未过 | 不扫描压缩阈值 |

依据：[V6][L1]、[V7][L2]、[V9][L3]、[V17][L4]。这些结果关闭具体候选和本轮投入，不证明所有低存储算法永远无效。将来只有真正不同的机制已提供独立、同工作量的完整PC/外层收益证据，且用户另行授权时才重新讨论；本批不新增试验争取这一资格。

双凝聚属于准确消元；旧p3是改用另一个准确的中间离散空间，都不是“廉价近似p4逆”成功。加速原积分、正向验算、数据搬运和同一准确因子的执行成本仍属本批范围，不故意降低求逆质量。

### 2.2 源阶段收口不代表性能已全局最优

Task39extra为CLOSED_WITH_QUALIFICATIONS。V31补跑126步、原A6约9.2832e-7、worker workflow2313.526 s、RSS7331401728 B；V29可比较parent workflow2422.426 s。V31/V30保存场相同、与V29差异约1e-14，仍缺独立direct及连续精度资格。[S1][S3]

以d9b545...已测数值行为和3804ede...收口说明为锚点，不自动追随源新提交。旧51.90分钟r2及最终38.56分钟都不是工作站短波ETA。V31清单本身没有授权工作站，本review只对下列明确组件作新迁移授权，不扩大源证据的适用范围。

| 优先级/资产 | 解决什么、收益方向 | 代价和验证 |
|---|---|---|
| P0：PSS/USS停采、低扰动RSS | 避免TB地址空间扫描持续干扰分配，保持快速安全监督 | PSS=null/disabled；RSS、身份、swap观察、后代清场仍有效 |
| P0：reference-metric H6对角 | 用参考能量张量和实际几何metric收缩代替重复积分，针对32.94 h主项 | 同积分/方向/复MPC；多主或目标合并保留交叉项，必要fallback计数 |
| P1：快速完整A4验算 | 降低每次粗返回/精化必做的正向作用成本 | 不删检查，不只验凝聚方程；保留独立native oracle和完整DtN |
| P1：融合A6 curl/mass | 共享取数、变换、回写，避免重复动作 | 保留各自积分及系数；不得分别凝聚curl/mass后相加 |
| P1：H6直接后端/自然序 | 减少旧对象准备及积分点重排 | 对角语义、Chebyshev、power10次数/seed不变 |
| P2：blocked Gram | 按原积分用分块乘法生成局部矩阵 | 当前tensor份额小；不宣称单独节省几十小时，不扩大几何资格 |
| P1：完整C分项计时 | 分离PH、缩减、MatSolve、恢复、A4体积/DtN、闭合、P | 低扰动累计记录，不复制factor或每步扫描大数组 |

参考[V30依赖][S4]、[V31清单][S5]，按实际import追踪必要文件，不全文件无条件覆盖：

```text
src/solvers/fullspace_metric_positive_diagonal.py
src/solvers/fullspace_quadrature_diagonal.py
src/solvers/fullspace_n1e_sum_factor.py
src/solvers/fullspace_partial_assembly.py
src/solvers/physical_light_setup.py
src/solvers/physical_equivalent_fast.py
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/p6_cell_condensed_action.py
src/solvers/p4_cell_condensed_inverse.py
src/solvers/physical_interface_balanced.py
src/solvers/physical_reference_diagnostics.py
src/runners/physical_retained_condensed_v20.py
src/runners/physical_retained_outer_adapter.py
benchmarks/subreaper_watchdog.py
benchmarks/task038_full3d_jit_staging.py
src/io/native_capacity_profile.py
```

源大runner只抽取必要数据流，目标已有框架增量适配。manifest逐依赖组记录donor commit/blob、目标原blob、冲突和测试。保留工作站int64/PORD64、短波完整模式、原始几何身份及已验证tensor分组；不搬笔记本int32、80模式常量、8 GiB/4687 MB额度、WSL路径、旧批次账本。

重要语义冲突：源final_report允许精化耗尽后best-finite继续外层，工作站合同要求逐次原Aq≤1e-10。本批只迁性能组件，不迁这一返回政策变化；保持原Aq≤1e-10及最多两次额外同因子精化。完整验算可以用合格的等价快速作用，native保留作独立见证，不要求继续执行慢实现。

p3/p4必须共用新增优化机制，阶次造成的必要差异单列。本批只做q3组件回归，不新增短波q3长场，不以旧4.03 GB/361步成绩代表新内核。未采用的局部多RHS、流式端口、固定matmul/实虚堆叠等不顺手启用；其小模型负结果也不证明所有大规模分块方法无效。

## 3. NUMA与监督：实测RSS线不是防OOM保证

### 3.1 保留RSS-only，不恢复换页提前中断

保持整树RSS硬线1.3e12 B、警戒1.17e12 B。swap、global pswp、fault、预测内存和预计耗时只观察；历史1.154 TB不是新kill线。实际资源触线、用户停止、不可恢复数值/程序错误、max2048及持续失去安全监控分别分类。OS OOM不是合格停止，也不能承诺RSS尚未达线就绝不被内核杀掉。

启动前继续要求effective_available≥1437438953472 B，并核对可见物理RAM、cgroup、磁盘和系统余量。新TB试验取得独占heavy窗口，核对全机heavy进程、锁及per-node容量。存在未协调大任务时WAITING_FOR_SHARED_WORKSTATION，不杀邻进程；此为本批重型准入安排，替代旧共享运行许可，不限制另一台笔记本。

### 3.2 新进程的内存放置和归因

E0只读核对内核摘录、触发PID可得历史归属、task/VMA/cpuset策略及本任务所有launcher/worker/helper的Mems_allowed。PID消失则unknown，不用同号新PID回填。检查本任务有无strict node1或VMA限制，不把preferred误叫membind。

允许对本任务比较双node `numactl --interleave=0,1`与旧preferred。在分配前设置并检查实际分布；大场优先选经资格的双node interleave，避免把约1 TB集中在单node，承认单核远端访存可能增加。它不能保证防住其他未知受限分配触发的OOM；独占窗口、每node低开销观察仍有必要。[W1]

node meminfo/status可周期读取；numa_maps等较重扫描仅在有界诊断/阶段边界按需计时。不关闭OOM或PROCHOT，不提高oom保护权限，不全机swapoff/清page cache，不改BIOS/governor或邻项目cgroup。cgroup memory.current不等于RSS，不静默替换原Gate。温度、频率、node余量仍观察，不新加未经声明的运行期kill条件。

### 3.3 PSS禁用必须贯通全链

新heavy profile显式pss_policy=disabled。parent、worker、observer、JIT staging、checker不得暗中周期调用memory_full_info、smaps/rollup或全memory_maps。RSS/status/stat安全采样独立运行，覆盖launcher/MPI/worker/compiler后代，PID+start_ticks去重，不累计各进程历史峰假装同期峰。

PSS填null/disabled，不填0。验证关闭时provider零调用、开启的小控制采用扫描完成后排下次且无追赶连扫、慢诊断不阻塞RSS安全采样、实测RSS越线清场、正常退出不制造第二根因。无需重建TB旧工作集验证控制流。记录采样耗时/间隔和parent CPU，不以删除监督换较低峰值。

## 4. 固定数学与正确性合同

最终仍求同一p6 Maxwell方程，准确p4只产生修正：

```math
A_6x=b,\qquad C=P_{64}A_4^{-1}P_{64}^{H},\qquad
M_6=C+(I-CA_6)H_6(I-A_6C).
```

外层保持p6 retained trace/port right FGMRES32，zero start，max2048。保留完整增广逆桥、非零内部/端口RHS、Bi/Di/Hhat、Nédélec方向与Floquet共轭；不能截断P64后假设两个Schur自动Galerkin等价。每场一个p4准确因子，重复回代；两次C有数据依赖，不能当独立RHS并发。

| Gate | 固定要求 |
|---|---|
| 作用/传递/局部恢复 | 操作尺度相对差≤1e-10，原更严映射门保留；覆盖非Hermitian端口、方向、多主/目标合并、非零内部与端口RHS |
| H6 | 原正定算子、对角语义、Chebyshev次数、power10次数/seed不变；记录对角/谱窗/H6差异及fallback |
| 原Aq返回 | ≤1e-10；最多两次额外同因子精化；状态及计数一致，不减少检查或精化换提速 |
| 完整解 | 独立完整原A6残差≤1e-6；保存/恢复/释放后检查闭合，Schur残差另列 |
| 物理 | abs(R+T+A_volume−1)≤1e-5，abs(A_balance−A_volume)≤1e-5，全部模式求和/被动性/归一化正确 |
| 同离散回归 | FE L2/scaled-curl、同坐标E/H及复模式向量相对差≤1e-4；R/T/A/A_volume绝对差≤1e-5，逐模式功率差≤1e-6；近零按原绝对规则，不拟合相位 |

快速A4验算仍作用于原未凝聚完整方程。独立native用于实际短波系数、不同几何/方向的组件见证与规定检查，不只由同一缓存自证。旧224步解可以作固定输入/等价见证，不能作为exact参考或要求其物理输出通过。

不同实现可改变舍入、精化和迭代次数，不硬编码121/228/126，也不把步数变化全算作单步加速。实际factory/module/blob、后端、线程和所有开关进入resolved_config/manifest。必要JIT优先在大factor前完成，仍计入完整workflow；后端借用矩阵期不可提前销毁。

## 5. E1/E2：迁移与热点验证

先迁低扰动监督、H6 metric对角/直接后端，再迁快速A4、融合A6、H6自然序和blocked Gram。允许明确移植bug最小修复；可选优化不合格时退回已验证实现，不无限搜索候选。

组件使用真实5/2 nm材料、几何类、方向、周期及端口规则。核对全部必要局部类；昂贵旧全局动作只取有界固定向量，不重做旧33小时对角基线。MPC合并类必须专测，fallback数、代价、唯一缓存和临时池都记录。现有metric缓存有固定容量，不靠无界复制局部矩阵换速度。

完成组件后，做一次54332-cell实际2 nm H6-only准备：同p6/h1.5网格、材料和约束，只构造新对角/H6，不建p4 MUMPS或无用全局矩阵。测真实O(cells)成本、fallback、工作区与RSS；这不是完整PDE，也不是与TB因子同时驻留的PSS对照。可在同进程必要步骤复用对象时复用，但销毁后不声称跨进程零成本。

为C增加低开销分项：PH、RHS缩减、MatSolve、局部恢复、A4 volume、A4 DtN、端口闭合、P；同时记录A6/H6、外层Schur、正交化、独立残差、checkpoint/输出。计时父子范围明确，不强行求和闭合。先记每次初解rho、精化rho、真实回代次数，再比较速度；不复制大向量或重复factor只为计时。

## 6. E3：受控线程加速同一准确算法

先用CPU24、MPI1/math1作为固定工作量对照，parent CPU9、observer独立空闲核。本批明确只授权1与4线程组件比较；4线程稳定受益后至多追加8线程。按现场空闲物理核心/NUMA核对选择；旧拓扑CPU24–47属于node1、CPU48不存在，仍须重新读回，不占邻任务核心。

仅使用当前兼容库具备的共享内存能力，核对OpenBLAS/MUMPS/PETSc构建、实际线程与affinity。设置环境变量不等于MUMPS已并行；不能把多线程进程仍绑一核。Python线程不得并发调用非线程安全PETSc/MPI对象，只用合格数学库或纯数组内核并行。[W2][W3]是机制说明，不保证当前PETSc3.19.6/MUMPS5.5.1支持最新选项，不借机升级共享ABI。

在≤990-cell真实FE fixture上测一次factor及其多次回代、完整PC，至多三轮AB/BA，初次/预热分列。同配置复用一个factor，不每个向量重新numeric，不在2 nm建多套因子调参数。未支持或无收益即保留单线程，不阻断其余迁移。

F5前冻结唯一线程配置、NUMA策略和clean source，scratch全部计入整树RSS。只有真实数值等价且固定工作量受益的配置可采用；采用线程后的收益是实现与执行条件联合结果，不是纯PC数学收益。本批不直接开多个复制全局对象的MPI rank，也不开发新分布式求解框架；后续准确MPI工程只在R48列依赖与缺口。

## 7. 有限正式试验：F5、P2与独立账本

| 阶段 | 工作 | 完成/停止边界 |
|---|---|---|
| E0 | 旧终态、检查点/身份、实际NUMA资源范围、迁移manifest | 不新factor；缺历史字段unknown，不再全量扫描巨大资源日志 |
| E1/E2 | 监督、性能组件、一次2 nm H6-only、相关回归 | 无完整PDE；不按版本号直接宣称更快 |
| E3 | 有界线程选择、冻结正式配置 | 不支持则单线程，不扫描排序/主元/BLR |
| F5 | 一场5 nm Si、p6/h4、q4、3780 cells、600原通道完整回归 | 原A6/物理/同离散回归及资源证据通过才进P2 |
| P2 | 一次2 nm Si、p6/h1.5、q4、54332 cells、3904原通道setup+16步 | QA、必要动作和16步同factor；PILOT_COMPLETED_NOT_SOLVER_QUALIFICATION，不自动继续一周 |
| R48 | 无目标大factor的0.7 nm planner、通道、对象、时间账 | 不分配最大目标全局矩阵、不运行0.7 nm PDE |
| Z | response_v6、对照、可达范围及缺口 | 同分支提交，集中审阅，未运行项明确原因 |

正式入口统一`python scripts/run_case.py <one-case.dat>`。创建显式v6输入而非覆盖v5。F5/P2分别绑定原5 nm/2 nm物理与实际网格；Si折射率为0.99396854453+0.00435380777i和0.99880148307+0.000213688647i，epsilon=n*n，1° grazing、azimuth0°、s、完整DtN保持。2 nm physical SHA为fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef；5 nm按旧F5 manifest逐项核对。新input/schema SHA重新计算，不硬填旧值；H6-only、16步pilot在输入和manifest中标明范围。

F5复用已有同离散场，不重跑旧60小时方法。双凝聚旧F5为121步、setup11263.076 s、solve10671.216 s、workflow22680.912 s、RSS38934622208 B；随后2023.440526 s的setup-only没有outer/物理资格。更早698步方法workflow217665.163842 s、RSS记录断档；三类证据分列，不混分母。[T5]

P2从零初值开始，与旧F2前16步同号原始记录比较，不拿末尾221–228步作严格配对。16步未收敛按计划结束，不输出official RTA；candidate场明确未资格化。旧224步向量可用作一次额外late-RHS动作检查，单列成本，不新跑224步采向量。

P2只建立一次准确p4因子，QA/动作/16步共用。本批不默认从旧224步续完整场，也不再跑第二个fresh 2 nm；未来续算要单列新profile、setup/factor成本，与cold-start48h目标分开。若粗因子仍主导，记录真实MatSolve和内存，转R48量化准确路线范围，不改p3、不启用近似p4逆。

明确移植bug可以修复并对受影响正式case至多一次登记重放；数值方法慢、资源不足或未收敛不算bug。保存全部负结果。正常scope内连续推进，不每完成小测试就等批准；受影响核心改变时重新核对测试及已运行证据资格，不以旧source承接新代码。

## 8. 0.7 nm / 48小时：可量化目标，不承诺靠本批全部实现

### 8.1 h减三倍对应三维单元约27倍

同体积、同p、三轴都从h1.5细化到h0.5，54332×27=1466964是情景派生值，不是实际新网格计数。h0.5是用户提出的容量/精度候选，不是已证明必须或足够；精度仍需场、模式、体吸收与h/p证据。

| 情景量 | 派生示意 | 限制 |
|---|---:|---|
| retained+port行数按27倍 | 约2.917e8 | 边界、约束、模式数要重新计数 |
| FGMRES32约65根complex128 V/Z向量 | 约303.36 GB | 16字节载荷，不含PC/全场scratch/端口/RSS |
| p4矩阵NNZ按27倍 | 约5.59e10 | 非symbolic结果；仅16字节值+8字节列索引约1.34 TB |
| MUMPS内部used约916.7 GB按27倍 | 约24.75 TB | 非实测、非下界；填充不必线性，仅显示风险 |

在全体积h0.5、全域准确p4因子、2 TB预算同时成立时，目前没有支持0.7 nm/48小时通过的证据。减少算子时间或增加核数不直接消除总因子存储；这不构成重开低内存逆研究的授权，而是必须报告的缺口。[S1][T3]

### 8.2 48小时包括完整数值流程

```math
T_{\rm total}=T_{\rm mesh/setup/factor}+N_{\rm outer}\,\bar t_{\rm step}
+T_{\rm recovery/check/output/cleanup}\le172800\ {\rm s}.
```

设计分配暂为12h setup、32h solve、4h恢复/检查/输出与余量。必要JIT、冷数值构建、第一次factor和全部检查入账；工具链安装/开发另列，warm-cache或续算单列，不隐藏预计算。

若solve预算32h，256/512/1024步分别需要平均完整step≤450/225/112.5 s。将当前35.61 min/步乘27仅得到约16 h/步的粗情景，对应约128/256/513倍改善需求；它不是0.7 nm ETA，也不是不可能性证明，只说明缺口不能靠相乘若干微基准speedup填平。

R48从实际planner读取候选轴/实体/FE/trace及完整external keys，0.7 nm材料须有正式来源，不照搬2 nm Si。材料缺失只阻断0.7 nm物理结论，不阻断已授权5/2 nm优化。分列measured/derived/predicted、真实线程/MPI、唯一类型、缓存/Krylov/DtN/矩阵/因子生命周期，不机械相加不同口径当RSS。端口已有大载荷应单独审计；旧80-mode流式负结果不自动代表3904或0.7 nm规模，但本批不据此另开端口算法研究。

### 8.3 不重开低内存p4逆时的下一步判断

| 范围 | 本批交付 | 不能推出什么 |
|---|---|---|
| 固定原离散与准确p4 | 最新内核、监控、线程/NUMA后的真实setup/单步及准确factor容量 | 核数不等于加速倍数，单核变快不等于因子能装下 |
| 精度支持的网格需求 | 复核已有h/p证据；h0.5及少量各向异性/局部加密候选的元数据账与缺失证据 | 不用粗网格、减mode、均匀化伪装目标精度；本批不新增精度PDE campaign |
| 后续准确并行工程 | 列准确MUMPS分布式存储/单节点MPI和局部数组并行所需接口与热点 | 分摊不等于减少总因子；本批不重写MPI，不换弱PC |

**明确禁止本批或本报告默认下一步安排低内存近似p4逆、递归p2、局部/子域逆替代p4、BLR、recycling和普通ILU扫描。** 真正新的方法需新的证据与用户决策，不在本review预授权。p3仅保留共同路径组件，不自动作为内存超限后的fallback。

若本批显著改善2 nm，把它登记为准确路线的工程提升；若全体积0.7 nm仍超出包络，写TARGET_0P7NM_48H_NOT_ESTABLISHED并量化缺口。不将目标偷偷改成更大内存、更小几何或Hybrid，不因本机阶段结束声称全球最优，也不保证此次迁移后0.7 nm必在48小时内完成。

未来精度合格的各向异性/hp/局部加密可避免无依据全域h0.5，但不假设内部可分离。少量局部类型共享在一般三维几何中未必成立，必须有唯一类型/缓存增长账。GPU只在实际硬件与明确授权后讨论，本批不假定存在可用GPU。

## 9. 交付、提交与证据要求

数值核心放可复用src，profile显式opt-in，runner编排，checker从raw字段重算。正式clean source，每场保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、ABI/int64/PORD64、实际库/线程/CPU/node/内存政策、完整资源与artifact hash。文档提交SHA不能冒充运行SHA。

推荐提交顺序：监督/NUMA与测试；核心选择性迁移及2 nm H6-only；线程/输入/profile与最终回归；冻结正式源码；F5、P2、R48证据和收口。遇到并发合法提交先核对，不reset/强推。只写本执行分支，不改task39extra、Hybrid或master。

交付可合并但不得漏义：

```text
response_v6.md
outcomes/performance_transfer_v6.md
outcomes/records/v6_migration_manifest.json
outcomes/records/v6_resource_numa_policy.json
outcomes/records/v6_component_and_h6_only.json
outcomes/records/v6_thread_selection.json
outcomes/records/v6_5nm_terminal.json
outcomes/records/v6_2nm_16step_pilot.json
outcomes/records/v6_0p7nm_48h_capacity_plan.json
outcomes/summary.md / test_summary.md / records/run_index.json
```

更新项目progress/model_registry，保留所有旧负结果。大矩阵/factor/场/checkpoint/JIT/资源日志留ignored，compact绑定路径/hash。定向pure/FE/监督、文档合同、compileall、diff和Markdown检查据实报告；全仓pytest、CI未跑不得声称通过。

Response首屏回答：OOM已知/未知；低内存逆本批是否零试验；PSS全链停采及RSS可靠性；H6对角新实测与fallback；完整C哪项主导；实际选了哪些内核/线程；新5 nm完整收益及2 nm16步成本；准确p4下0.7 nm/48小时剩余容量、精度与时间缺口。非受控配对只能称工程比较，不宣称因果提速。

**最终裁决：保留准确p4凝聚逆，优先兑现已验证的setup/单步组件和受控并行收益；不再消耗本批时间研究低内存p4逆。0.7 nm/48小时必须由精度、实际对象容量和完整时间共同支撑，未建立就如实说明，不拿同一批失败方向继续试。**

## 10. 固定证据与外部定义

[T1]: outcomes/f2_terminal_oom_20261002.md
[T2]: outcomes/records/f2_kernel_oom_20261002_excerpt.txt
[T3]: outcomes/f2_running_handoff_20260928.md
[T4]: outcomes/records/f2_pss_observation_20260926.json
[T5]: response_v5.md
[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/final_report.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/review_report_v30.md
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/response_v34.md
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/outcomes/selective_workstation_handoff_v30.md
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/outcomes/selective_workstation_handoff_v31.md
[L1]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/outcomes/coarse_inverse_replacement_v6.md
[L2]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/outcomes/bounded_inexact_outer_v7.md
[L3]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/outcomes/equal_work_recycled_p4_v9.md
[L4]: https://github.com/Rookie1234567/MyFEniCS/blob/3804ede8acfd120d0d8d312415ec5e7a2c296cd7/docs/task039_extra_physical_multilevel/outcomes/p4_blr_tradeoff_v17.md
[W1]: https://www.kernel.org/doc/html/v6.7/admin-guide/mm/numa_memory_policy.html
[W2]: https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/
[W3]: https://petsc.org/main/manual/blas-lapack/

外部文档只解释机制，不替代实际内核/ABI/分配证据；本任务相对链接按reviewed_target_HEAD读取。提交后的Markdown结构、本地预览与GitHub在线视觉核验分别记录，不预先声称已完成。新批次未运行项不写成通过。
