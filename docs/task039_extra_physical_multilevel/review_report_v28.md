# Task39extra Review V28：工作站2 nm证据驱动的笔记本优化

## 0. 决定、范围与身份

**工作站2 nm已经采用双层单元凝聚，不能再以“迁移凝聚”作为新优化。此次最新证据把主要问题定位到：昂贵PSS监控与分配等待、旧H6对角构建、粗层求解/恢复/验算的持续成本，以及随通道增长的端口缓存。下一轮在笔记本实现和验证对应优化；不接管或修改正在运行的工作站任务。**

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task39extra
review_date               = 2026-09-28
reviewed_laptop_base_SHA   = 77bb6c6d604e04ab5db1f33a8a5e51e2f605d33f
laptop_formal_source       = 780f58918b0e5a9868cd2ea3de26d451bc6b5d86
previous_review_response  = review_report_v27.md / response_v30.md
workstation_evidence_HEAD = ccd357885f7f9be84efe3be07868cc94f13d93fc
workstation_running_source= 64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa
workstation_run_id        = v5_node1_2nm_p6h1p5_q4
workstation_execution_id  = 20260924T104936.107285Z
batch_id                  = review_v28_workstation_guided_local_v30
suggested_profile         = physical_p6_trace_workstation_guided_v30
response_required         = response_v31.md
normal_full_PDE_count     = 1
formal_model              = original / wavelength13.5nm / p6-h7.5 / coarse-p4
numeric_cache_mode        = build
MPI_and_math_threads      = 1 / 1
workstation_execution     = NOT_AUTHORIZED
master_merge              = NOT_APPROVED
```

本轮消除的blocker是：**将TB级常驻工作集放大为严重监控扰动的采样方式、随单元/几何类型重复的辅助对角计算、昂贵粗修正，以及显式局部端口块造成的数据存储和搬运。** 最终目标仍是约2 TB整机内存内的0.7 nm、complex128、Nédélec H(curl)、双Floquet、Fourier-DtN、任意非可分三维周期单胞。本轮是性能与存储实现优化，不是已经解决全局p4因子扩展性。

用户本轮明确要求先在笔记本尝试，成功后由用户决定推广。因此review提交笔记本执行分支，不提交工作站分支；Codex不得SSH改变工作站进程、源码、监控、参数或资源策略，不替换活跃因子，不停止/重启F2，不启动工作站新PDE。工作站证据仅只读引用。

读取根/适用目录AGENTS、[工作原则](../repository_work_principles.md)、[task](task.md)、两份既有用户补充授权、[Review V27](review_report_v27.md)、[Response V30](response_v30.md)、[summary](outcomes/summary.md)，并读取第1节冻结的工作站资料。旧task中被历次review替代的实验范围不重新生效。普通默认与旧strict profile不变。

本批允许必要src内核、测试、显式profile/入口/资源采样和独立checker适配。正常一场fresh h7.5完整回归；局部组件不建无关p4全局因子。完整C配对确需因子时最多另建一份工程工作集、跨所有配对复用，随后释放；不能为每个向量重建因子。真实实现bug有完整失败证据与最小修复后，允许一次必要定向重放；性能无收益、资源不足或普通不收敛不属于bug重放。新batch不占用或清零旧额度。

## 1. 审阅事实：必须更新之前的热点判断

工作站权威是[2026-09-28运行中交接](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/f2_running_handoff_20260928.md)、对应[compact](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/records/f2_running_handoff_20260928_compact_v1.json)、[evidence](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/records/f2_running_handoff_20260928_evidence_v1.json)、[setup CSV](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/records/f2_setup_stages_20260928.csv)与[PSS观察](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/records/f2_pss_observation_20260926.json)。工作站task、Review V5、response_v5和summary也按该HEAD只读核对；它们不是本批执行授权。

快照为2026-09-28 02:34:15.838437 UTC，即10:34:15.838437 UTC+8，不代表提交之后的实时状态。

| 对象 | 已保存事实 | 判断/范围 |
|---|---:|---|
| F2当前资格 | 完成64步；独立原A6残差0.022358747111508717 | RUNNING，未达1e-6；不是正式物理PASS |
| workflow / setup / 已执行solve阶段 | 87.744079 / 51.218995 / 36.525085 h | 最后一项含检查等，不是最终pure KSP timer |
| p4 numeric marker区间 | 44111.673835 s，12.253243 h | 一次factor.numeric及紧邻记录；并非全部setup |
| H6准备父区间 | 120224.788820 s，33.395775 h | 约65.2%的setup；对角子项118597.092899 s |
| H6区间CPU采样差 | worker18044.23 s；parent115503.09 s | 覆盖已有采样窗口；不可相加/相减还原精确阶段CPU |
| p6/p4完整builder | 463.355848 / 292.202399 s | 原FFCx核仅292.124320 / 33.861449 s；不再是几十小时的热点 |
| 实际几何/积分类型 | 各54 raw geometry、6 tensor groups、87 oriented Schur classes | 已批准rounded_12_representative；不是旧96类raw_unrounded场 |
| 最新完整PC两次C | 1371.435401 s；其中两次p4 ledger1319.492162 s | 约96.2%在ledger内；内部MatSolve/恢复/A4尚不能分账 |
| 最新PC因子调用 | 第一次C初解+1次精化，第二次C初解，共3次MatSolve | 两次C不等于两次因子求解；前者879.549533 s、后者439.942629 s |
| 两次A6 / H6 | 186.846761 / 136.814053 s | 来自同一PC；完整PC wall未独立保存 |
| 当前/前缀峰RSS | 1151.172259840 / 1154.356473856 GB | 同一冻结前缀；硬线1300 GB，不是2 TB全部可用 |
| MUMPS allocated / used | 1091.654 / 916.713 GB | 后端内部统计，不是独立因子RSS |
| p6 action/port数组库存 | unique约108.004 GB；port子集约106.341 GB | ndarray-id统计，view和子集可能重叠，不是resident分账 |
| p6/p4局部数值缓存 | 1.084647 / 0.074096 GB | LU/Schur/recovery等；与端口库存不是同一对象 |
| p6保留行数 / p4因子行数 | 10803256 / 4586288 | 已经双层凝聚；p4实际stored NNZ2070391064 |

近期正常步58–64均值1846.834198 s；57–64含一次较贵检查的均值2008.827413 s。iteration64有restart重复callback，不能计为第65步。最近独立检查后的残差下降不能外推ETA，也不能用报告残差替代原A6。

**PSS关键证据：** 已观测单次smaps_rollup约6.58 s、parent CPU约6.33 s；5秒下一次采样时间在扫描开始前设置，扫描超期后连续重扫。还观察到parent读smaps与worker的mmap等待同时出现。没有PSS关闭对照，不能宣称H6关闭PSS必从33小时降至5小时，或把所有慢化归因监控。Linux官方[proc说明](https://docs.kernel.org/filesystems/proc.html)区分廉价但异步的RSS统计和需遍历映射/页表的详细统计；更快的smaps_rollup也不是无成本计数器。

**版本差异：** F2已经用了双层凝聚和优化传递，但仍是split A6、native原A4、旧逐单元/逐target的H6对角、FFCx局部矩阵，以及精化耗尽即拒绝。笔记本V29已有A6融合、快速完整A4、blocked Gram、优化对角及continue_outer_best_finite。这些属于未来迁移清单，不作为本批重新取得的发明。工作站分组策略已经变化，不能拿旧29小时p4装配或96类数据套到本场。

### 1.1 笔记本唯一完整比较基线

[V29 compact](outcomes/records/a4_tensor_h6_v29_compact.json)与[components](outcomes/records/a4_tensor_h6_v29_components.json)绑定source 780f58918b0e5a9868cd2ea3de26d451bc6b5d86。

| measured对象 | 数值 |
|---|---:|
| workflow monotonic / conservative realtime | 2422.426388672 / 2643.634584208 s |
| setup / pure KSP | 533.7549639960052 / 1837.17495212 s |
| iterations / final original A6 | 126 / 9.283162362107749e-7 |
| watchdog RSS / worker PSS峰 | 7326449664 / 7291101184 B；采样器范围分列 |
| A6 / H6累计作用 | 517.1558918120281 / 525.0361430749181 s |
| 完整A4 / p4 F4累计 | 159.091448716179 / 243.56268202979118 s |
| H6 diagonal / power10 | 4.798956676997477 / 39.08678095601499 s |
| p6 raw kernel / builder | 20.289459018968046 / 34.122371820005355 s |

这些是inclusive操作桶，不能机械求和为KSP。V29同离散场/80模式通过，continue分支正式0/262、仅fixture覆盖，H6实虚堆叠未采用。V29评为PASS_WITH_QUALIFICATIONS，仅显式profile；F2是RUNNING，不给最终批准。

## 2. 不变的数学、数据与资源边界

正式模型沿V29输入：13.5 nm、original、1° grazing、azimuth0、s偏振、原Si/air材料、990单元、p6/h7.5、同网格p4、全部80 DtN keys、complex128。p6外层199340行，p4凝聚84680行；不改变物理、积分、MPC、模式归一化与输出。

```math
A_6x=b_6,\qquad C_4=P_{64}F_4P_{64}^{H},\qquad
M_6r=C_4r+H_6(r-A_6C_4r)-C_4A_6H_6(r-A_6C_4r).
```

继续使用right FGMRES32/max2048、零初值、每8步独立原A6与每32步场检查、每次两份逻辑C4和一次H6。H6次数、正定B6定义、对角定义、power10种子/步骤和谱窗规则不变。A6融合与V29完整A4、blocked Gram保留，不重试已否定的H6实虚堆叠/shared-contraction开关。

原A4每次完整验算及每次精化后的完整验算全部保留；不降低频率、不用便宜筛查、不换成凝聚/因子残差。1e-10为内部软目标，初次加最多两次额外同因子精化；仍未达且状态有限完整时返回最佳完整状态并继续外层，保持V27的best/alpha/A4c/e一致性。NaN/Inf、真正因子/映射/端口错误仍拒绝。不为减少精化次数调大阈值或人为改变实际RHS。

**MUMPS冻结：** 不换后端、不调排序/主元/ICNTL、不改BLR/OOC、不改factor线程或ABI。两次C因果串行，不能当作两个同时已知RHS合并求解。新工作不做p3/p2、不重选PC、不改restart、不开发全局DD或GPU；不在笔记本运行2 nm/0.7 nm完整模型。

本轮资源停止权限沿笔记本V29的真实物理压力、系统余量、task swap及监督规则，不借用工作站1300 GB门限。用户允许修改的是PSS诊断的实施方式，不是削弱RSS/watchdog或任何数学检查。实际zero-swap继续是性能资格目标；有swap如实限制结论。新数组、线程/进程及监控器均计入整树；数学线程1，不启动并行factor或多个全局工作集。

## 3. L1：低扰动监控——先避免“为了测内存而反复扫描TB工作集”

### 3.1 实现目标

新增显式、可测试的轻量监控profile，将**停止依据的快速RSS链**与**可选PSS诊断**分开。默认本批heavy setup、factor、solve不在worker或硬watchdog循环同步读取smaps/smaps_rollup；PSS字段为null并标记DISABLED_BY_PROFILE，不填0、不拿旧值冒充新值。不将PSS缺失升级为RSS监控失败。

继续及时读取原进程树成员、PID/start_ticks、status中的RSS/VmSwap、既有系统余量及生命周期信息。保持原轮询目标、失联保护、超限停止、subreaper清场、fork/setsid后代归属和日志可读性。RSS/status为原有采样指标，不将其描述成精确逐页PSS；存在的异步误差与采样空隙照实报告。

如果保留可选PSS调试模式，下一次时间必须基于**完成时刻**安排，漏期直接跳过、不catch-up；禁止无限队列。硬RSS循环不得等待一个潜在慢PSS调用。最简合格实现可以让正式profile完全不启用PSS；不为该项搭建复杂采样平台。不能只把读取移到另一个CPU便宣称无锁竞争，也不能改掉parent却在worker/observer/最终采样分支继续逐次触发同样扫描。

### 3.2 笔记本如何验证

使用fake clock/注入慢PSS provider复现“耗时超过间隔”的调度问题；证明新RSS路径不调用它、不会排队或降低安全轮询。覆盖RSS超限、PID重用、后代退出/孤儿、status不可读、PSS关闭/缺失和清场。用小型子进程工作集作一次真实provider对照，总新增触页数组不超过512 MiB且服从现场余量；最多3个交错重复，不创建TB虚拟映射或故意触发物理内存压力。

记录父/worker CPU秒、wall、RSS最大采样间隔、PSS耗时/次数、分配次数。人工注入延迟为DIAGNOSTIC_CONTROL_FLOW，不能当作工作站实测加速；本机小工作集未复现锁等待不妨碍采用已验证的安全调度修复。禁止推算“删掉parent CPU就是能省下的墙钟”。

## 4. L2：H6准备的可扩展精确对角，避免逐单元大表构造

### 4.1 已有成果先对齐，新增目标要明确

工作站运行源的build_quadrature_positive_diagonal仍在每个cell构造定向物理basis表，再逐target积分。笔记本V29已有batched_target_grouping/reuse_local_types；首先证明这些优化与工作站实际空间、方向、复MPC定义相容，作为可选择迁移的依赖包，不重新声称发明了类型缓存。

新增候选针对**raw几何类型多或target合并时的重复工作、短寿命大数组分配**：以原积分规则的参考能量张量配合每个单元的真实几何metric生成对角；缓存应有界，不依赖给所有真实几何建立永久basis表。H6数学对角不变：

```math
d=\sum_K\operatorname{diag}(C_K^H B_K C_K).
```

C_K为该单元完整约束展开，不能只将无约束对角乘系数平方而遗漏交叉项。无target合并时，可以预存每个参考基函数各分量对的积分；对实Jacobian J，mass/curl的metric分别为：

```math
G_m=|\det J|J^{-1}J^{-T},\qquad
G_c=\frac{J^TJ}{|\det J|}.
```

按原正定材料系数与这些metric收缩，直接得到各局部basis能量，避免每次重建完整物理values/curls。方向变换必须来自实际Basix元素；signed permutation可精确映射对角，一般非单项变换或多master/target合并必须保留所需成对交叉积分，或退回原正确有界分块积分，不擅自套对角公式。

原积分点/权重、geometry与material身份逐项绑定，不新增rounding，不把工作站54 raw→6组当作H6可以照抄的证明。连续不同仿射几何使用各自实际metric；不支持的几何/材料显式正确fallback或报告，不能偷偷用近似几何。缓存和scratch需记录上界与命中/退回次数。

### 4.2 验证与执行顺序

对照三方：工作站旧正确定义的最小适配、笔记本当前合格优化、新候选。组件覆盖复Floquet、多master/同target、方向、平移/不同仿射尺寸、DG0非均匀材料、零和非零边界输入。完整990-cell对角差<=1e-10、正性/约束行保持；固定同一D和谱窗比较H6 apply<=1e-10，再验证原power10流程。

另做有界多几何类型诊断，不增加正式PDE；记录cell数、真实类数、fallback比例、wall/CPU与大表分配次数。不能只在重复单元占绝大多数的小例上宣布任意网格可扩展。

H6不依赖p4因子的部分可以条件前移到factor前，以避免临时分配与最大常驻对象重叠；只在已有接口能安全借用唯一prepared H6对象时做，不复制两套H6、不改变谱窗与物理，不为重排重写整条runner。迁移可行性与新对角算术收益分别记录。新候选无收益就保留V29的优化对角，但交付工作站合同的相容性证据。

## 5. L3：完整C4成本——固定原因子，批量局部缩减/恢复并补齐分项

工作站最新C的96.2%位于ledger内部，尚无证据证明都是MUMPS回代或都是native A4。不能以笔记本占比代替TB因子测量。本轮在同一次local C中分别计PH、RHS缩减/打包、每次MatSolve、内部恢复、完整A4体积/DtN、独立端口闭合、P及额外精化，父子/检查范围闭合；利用已有timer或加入轻量perf_counter/process_time，不热改工作站。

已成功的快速A4不重新做一轮搜索；保留它，并在小型工作站式端口/非零内部RHS fixture上验证完整接线。A4仍按每次原要求完整检查，不把native oracle在每次生产调用都重复执行来抵消收益；native独立资格与最终原A6保留。

真正的新局部候选：按同一局部LU/恢复operator的owner与方向分组，将多个cell的缩减/恢复以**有界多列局部RHS**处理，减少逐cell的小型solve、分配、重复gather和scatter。使用每个cell自己的RHS、trace、port及MPC映射；未出现于原作用中的非零项不能删除。该批处理只发生在独立局部块，不改变全局p4矩阵或MUMPS调用语义，不合并两次依赖的C，也不合并不同FGMRES步。

先在局部块及原真实80-mode小网格验证，随后必要时在唯一工程p4因子上用已存V29真实输入作完整C交错配对，最多3轮。至少覆盖一次需要精化及一次两次后soft-return的fixture，正式不人为制造劣质因子。返回的FE/alpha/A4c/e同一状态，原balance ledger保持。

若本机对应局部步骤已充分批量化，不能包一层新函数称优化；列出现有调用数与布局证明，并将本节实现重点移到L4的端口侧共同批次，不继续扫描MUMPS。独立报告单次C成本和实际MatSolve次数；某实现少触发一次精化不自动证明每次kernel加速。不得为减少修正次数提高1e-10或更改最终精度。

## 6. L4：端口局部耦合流式化，减少大块常驻数据与搬运

### 6.1 问题与候选

工作站p6端口相关数组库存约106 GB，远大于约1.08 GB局部数值缓存；库存存在alias，不能承诺完整回收106 GB。但它揭示了80-mode笔记本测试难以暴露的增长项。本节在小规模做**保留全部通道、非Hermitian耦合和完整原方程的存储实现试验**，不是减少模式或开发Hybrid。

沿现有符号：

```math
\begin{bmatrix}
V_{ii}&V_{it}&B_i\\
V_{ti}&V_{tt}&B_t\\
-D_i&-D_t&H_p
\end{bmatrix}
\begin{bmatrix}x_i\\t\\\alpha\end{bmatrix}
=\begin{bmatrix}f_i\\f_t\\f_p\end{bmatrix}.
```

消元会形成Bhat、Dhat、XiB及端口Schur更新等对象。新候选不必将所有cell的这些大块同时缓存；保留共享局部LU/恢复与原carrier，在固定cell/mode批次中完成同一作用。对当前输入：

```math
X_{it}=V_{ii}^{-1}V_{it},\qquad S_V=V_{tt}-V_{ti}X_{it},\qquad
u_i=V_{ii}^{-1}(B_i\alpha).
```

```math
\begin{aligned}
y_t&=S_Vt+B_t\alpha-V_{ti}u_i,\\
y_p&=-D_tt+D_iX_{it}t+H_p\alpha+D_iu_i.
\end{aligned}
```

对应RHS缩减/恢复保持：

```math
\widetilde f_t=f_t-V_{ti}V_{ii}^{-1}f_i,\qquad
\widetilde f_p=f_p+D_iV_{ii}^{-1}f_i,\qquad
x_i=V_{ii}^{-1}f_i-X_{it}t-u_i.
```

这只是消元恒等式；D不能擅自设成B的共轭转置。原H_p与凝聚Hhat有别，BAL_H桥仍使用规定的原H_p。各cell共享trace/mode的累加、MPC和左右稀疏支撑必须准确，非零内部及端口RHS都验证。

优先避免重复存储Bi/Di、XiB/Bhat/Dhat及每cell dense mode-by-mode更新；从已有稀疏carrier借用/分批取数据，固定batch scratch，不能用另一份全量materialization替代。数组库存按实际底层buffer/owner去重，不仅按view id。若当前表示无需某块就不建立，不扫描数值小项后删耦合。

**代价要实测：** 流式化可能增加局部solve/重计算而变慢。只有完整作用或全流程有时间收益，或明显省内存且时间无可确认退化，才进入本批正式组合；仅省内存但显著变慢留research_only，不能替用户交换指标。不因“公式更matrix-free”就自动采用。

### 6.2 受控验证而非本机大规模短波PDE

先用独立小型复数非Hermitian增广矩阵作为代数oracle，再验证真实80-mode FE carrier、凝聚作用、RHS缩减、恢复、port closure与原A6。新旧作用/非零RHS闭合<=1e-10，零尺度另用已有绝对规则。

通道增长仅做三档组件测试，例如80/512/3904维、固定很少cell/局部块；确定性合成数据必须标DIAGNOSTIC_MODE_SCALING，不冒充2 nm物理通道资格。可用真实keys时绑定来源，但正式h7.5始终80通道。新增活跃对象预算优先<=512 MiB并受现场余量约束；高模式档禁止构建每cell nmode平方oracle或新全局矩阵/因子，靠已验证的代数作用交叉检查和分块统计。不为图表强行跑入场失败的一档。

记录持久/峰值scratch随cell、mode增长的公式与实测，明确被删除的是哪份重复数组，以及新增了几次局部solve。正式只采用一个selected实现，不同时常驻新旧两套大端口工作集。不能借本批自动推广到工作站。

## 7. 优先级、整合回归与停止条件

| 阶段 | 本轮执行内容 | 交付/分流 |
|---|---|---|
| L0 | 轻量身份、环境与scope检查；固定工作站证据；新batch/profile smoke | 不重新读取或操作活跃工作站进程 |
| L1 | 非侵入RSS安全链与可选PSS分离；慢provider和小型真实进程测试 | 必做；不以本机缺少TB工作集跳过调度修复 |
| L2 | 工作站式正确对角与V29相容性；参考能量/metric有界候选 | 必做实际尝试；现有V29成果不重复记新收益 |
| L3 | 完整C细账与局部缩减/恢复批处理 | 必做；无额外机会须给具体已有实现证据，不泛写已到极限 |
| L4 | 局部端口coupling按需/分块作用与小型mode增长 | 必做原型与正确性；性能不合格不进正式组合 |
| L5 | 固定selected组合、clean source、唯一fresh h7.5 | setup成功后同因子继续外层，不逐步停审 |
| L6 | 原始checker、三阶段账、工作站迁移依赖清单、response与推送 | 统一收口；没有远端迁移/合并授权 |

本轮不再把“积分点顺序统一”单独增加为第五条主线；它仍是后续A6/H6在线候选，不能因已讨论就宣称已实施。p6 blocked Gram保留，但不围绕本场仅约292秒raw核再开展大规模矩阵生成平台。参考张量推广可服务L2，不新建全套FE编译器。

必要测试集中完成，使用已有runner参数，数值实现进src，不为每个case复制大脚本。正常一次完整h7.5；新profile一并验证L1及selected数值子项。即使部分候选撤出，也不取消其他合格成果；L1/profile有行为变化且合格时，完成一场整合回归，不再做只有计时器的收口。真实安全/数值错误仍停止保存证据，不能绕过失败Gate硬跑。

通过`python scripts/run_case.py input/task39extra/v30_workstation_guided_original_h7p5.dat`执行，新run_id与独立结果目录。先提交clean源码；本场重建局部数值数据和唯一MUMPS因子，合格JIT按身份正常复用，不加载旧解、Krylov空间或旧因子。记录cold/JIT hit，所有本场数值准备计入workflow。全程接电，固定电源模式，MPI1/数学线程1。

126步和40.37分钟仅基线，不是停止线；保留max2048与原终态检查。初次+两次精化后有限未达不停止外层，仍需所有完整A4检查。PSS缺失不是数学检查缺失。禁止因性能不佳自动再跑完整场、提高内存上限或改物理；不保留不合格候选只为“完成四项”。

## 8. Gate、计时与内存结论

| 类型 | 要求 |
|---|---|
| L1安全 | 快速RSS/task swap/身份/失联/清场链通过；不能因PSS扫描阻塞硬监控。配置关闭PSS是显式缺项，不伪造峰值 |
| 局部数学 | 方向/MPC、多master交叉项、材料/积分、非零RHS、非Hermitian端口保持；各节1e-10等价要求及原零尺度规则 |
| 粗层/PC | 原完整A4检查次数与MatSolve账闭合；soft-return selected完整状态；原inexact balance闭合<=1e-8 |
| 最终原A6 | 完整恢复后独立显式残差及release后检查<=1e-6，不用Schur或报告残差代替 |
| 同离散场 | V29 FE L2/scaled-curl、同坐标E/H/接口与80复模式relative<=1e-4；不拟合相位 |
| 物理 | R/T/A/A_volume绝对差<=1e-5、逐模式功率差<=1e-6、能量闭合与吸收一致性<=1e-5 |
| 资源 | 全过程树RSS与原现场物理压力保护；新增scratch有界，task swap实测为0方可给无swap性能结论 |
| 结论范围 | measured / derived / diagnostic / not_run分开；不将本机profile PASS升级为0.7 nm或工作站推广批准 |

组件配对最多3轮交错重复、warm-up单列，不取最快样本。若均值差小于实际波动则inconclusive，不硬设一个小百分数包装成功。峰值内存与时间目标分别报告；缓存载荷、MUMPS allocated/used、RSS/PSS不是可相加的同口径数据。

新计时至少分三大块：setup的空间/端口/JIT、p4局部装配与factor、H6对角/power10、p6准备、bridge/QA；KSP的C两次及PH/reduce/MatSolve/recover/A4/port/P、精化、A6/H6、Schur、正交化与固定检查；最终恢复、native检查、release、物理输出。使用同一事件ID记录monotonic/CPU，realtime另列。不要用parent CPU或worker CPU差额替代墙钟，不将restart重复callback当新增iteration；已有V28/V29逐32步取点歧义按同一事件规则修正到新比较附件，不覆盖旧记录。

主比较为V29的full2422.426388672、setup533.7549639960052、KSP1837.17495212 s及watchdog RSS7326449664 B。PSS新策略下未采样就写unknown/not_sampled；旧PSS峰不与新RSS比较。工程probe成本、旧实现适配成本与正式求解分开；不要将工作站33小时与笔记本几秒直接相除称speedup。

## 9. 交付、提交及后续大规模边界

建议提交顺序：D1监控策略/安全测试；D2对角与粗层/端口候选、局部证据；D3选择、profile/dat和最终相关测试；D4整合结果、报告与总账。只提交小型记录，完整场、矩阵、因子、日志留ignored artifacts，不amend/force-push，不改旧review/负结果。branch HEAD变化先核对，不自动merge工作站或master。

```text
response_v31.md
outcomes/workstation_guided_local_v30.md
outcomes/records/workstation_guided_local_v30_components.json
outcomes/records/workstation_guided_local_v30_monitor_policy.json
outcomes/records/workstation_guided_local_v30_selection.json
outcomes/records/workstation_guided_local_v30_compact.json
outcomes/records/workstation_guided_local_v30_checker.json
outcomes/selective_workstation_handoff_v30.md
```

文件可合并但事实不能省。正式保留input_original.dat、resolved_config.json、run_manifest.json、input/physical/source hash、run_summary、环境/ABI/MPI/线程、模式/场hash与资源事件。更新summary、test_summary、run_index、development_progress和模型总账。声明测试实际范围，不把fixture覆盖当实场触发，不冒称MPI/CI/全库测试通过。

`selective_workstation_handoff_v30.md`分清三类：已存在的笔记本V26–V29成果、本批新且本机合格成果、未采用/待工作站验证项；列最小依赖文件、接口差异（含int64/PORD64与端口数、几何身份）、已有证据、后续5 nm→2 nm资格步骤。它只是供后续授权选择性迁移的清单，不自动迁移、不改活跃工作站树。

**长期边界：** 即便L1–L4都成功，工作站仍保留MUMPS内部used约916.7 GB量级的全局粗因子。去掉诊断扰动、减少端口数据、优化局部执行都不能改变全局直接法的增长。最终0.7 nm任意三维生产路线仍需要分布式matrix-free算子、可扩展迭代PC与有界粗问题；本批不悄悄启动新粗空间/全局DD研究，也不宣称现有架构扩展已经通过。

只按已保存独立原A6序列分析残差下降；64步0.02236尚不足拟合收敛尾部/ETA。后续工作站资格应同时观察时间/步和达到固定真实残差的成本，而不是只追求某个kernel变快。参考[PETSc性能指南](https://petsc.org/release/manual/performance/)的带宽与NUMA边界：更多内存不自动带来更高单核吞吐；本轮不改工作站绑定、NUMA、线程或MUMPS。

遵守[Markdown标准](../markdown_rendering_standard.md)，公式用fenced math，表格列数统一；检查本地渲染并尝试GitHub rendered view，不可访问则明确披露。最终push同一task39extra，回读完整远端HEAD，等待主控统一审阅。
