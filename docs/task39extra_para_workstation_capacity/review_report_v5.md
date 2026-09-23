# Review V5：node1 性能复核、p3/p4 同路径与 13.5 nm 双复现后推进短波

## 0. 本轮决定与覆盖关系

**按用户最新要求，正式计算改到另一颗物理 CPU / node1：先核实逻辑 CPU 24–48 的真实拓扑和加风扇后的持续性能，再统一 p3/p4 的已优化执行路径；在工作站顺序完成两场 13.5 nm、original p6/h7.5（coarse p4 和 coarse p3）复现。两场通过后，继续一场 5 nm p6/h4、coarse p4，再条件执行一场 2 nm p6/h1.5、coarse p4。代码迁移、适配、测试和计算均由 Codex 执行；ChatGPT 本轮只新增本 review。**

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task39extra_para_workstation_capacity
review_date                 = 2026-09-23
reviewed_target_HEAD        = 0848c214914a40007425553a5b0527f0e1747357
previous_review             = review_report_v4.md
latest_target_response      = response_v4.md; response_v5.md not yet present
reviewed_source_branch      = task39extra
reviewed_source_HEAD        = 55ceb4c84a9041f715dc0c34c72fca689e753cce
source_latest_review        = review_report_v25.md
source_latest_response      = response_v28.md
Q4_speed_numerical_source    = 4bf2bba56cc2e568d56ff3096aeb4a108744f28d
Q3_qualified_source         = cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32
common_ancestor             = 450255f4575792d052c1bac29837d39955ee1039
batch_id                    = review_v5_node1_common_q_paths_and_shortwave
execution                   = H0 -> H1 -> M -> C -> R13Q4 -> R13Q3 -> F5 -> conditional F2 -> Z
normal_full_PDE_count       = 4; two 13.5nm anchors, one 5nm, one 2nm
worker_candidate_logical_ids= 24..48 inclusive; filter by actual socket/node/core topology
worker_cpu                  = one fixed qualified node1 logical CPU, resolved at H0/H1
formal_MPI                  = 1
math_threads                = 1
parent_watchdog_cpu         = 9 if available and not the worker's SMT sibling
memory_policy               = prefer verified node1, allow node0/node1 fallback
resource_policy             = measured_tree_rss_only_v3
rss_hard_limit_bytes        = 1300000000000
response_required           = response_v5.md
full_branch_merge           = NOT_APPROVED
master_merge                = NOT_APPROVED
```

本轮消除三个 blocker：**第二颗 CPU 的外部限频/内存吞吐异常是否仍存在；不同粗阶是否误走不同新旧执行路径；笔记本成功算法在原生工作站上尚无同离散 p4/p3 双复现。** 这服务于约 2 TB 整机内存内的 0.7 nm、complex128、Nédélec H(curl)、双 Floquet、Fourier-DtN、任意非可分三维周期单胞目标，不代表本轮已完成该目标。

本文件是对 [Review V4](review_report_v4.md) 的增量替代，不修改 V4 历史。明确覆盖 V4 的“固定 CPU23”“p3 仅做组件”“不新增完整13.5 nm”“正常仅两场”及“p3未合格也可直接推进q4短波”等冲突要求。V4 的选择性集成、原方程/恢复/精度、Si短波输入、单线程、1300 GB 实测 RSS、历史比较及证据要求继续有效。不得先执行过期 V3/V4 长场，再重复本轮四场；已有 D1/D2 准备继续复用。

这是新的授权批次，不借用或重置旧 replay 账本；旧额度耗尽不得阻止本轮已授权的首场。源分支继续开发不阻塞本批冻结成果，也不自动引入新未资格化实现。本批不增加 MPI/数学库线程，不开发 DD、BLR、PML、recycling、GPU 或新粗空间。

## 1. 仓库依据与已知边界

执行前读根/目录 AGENTS、[仓库工作原则](../repository_work_principles.md)、[原 task](task.md)、V3/V4、本 review、[本分支 response](response_v4.md)、[summary](outcomes/summary.md)；源 task、既有补充授权及最新 review/response 按上表 SHA 读取。本轮远程审查没有通过 SSH 测试用户新风扇或工作站硬件；“已安装风扇”是用户提供的事实，不等于实测修复通过。

### 1.1 源成果仍以 r2 为完整速度基线

以下是源分支已提交实测，GB=10^9 B；不是工作站结果或待运行案例的 ETA。

| 源 13.5 nm original，p6/h7.5，990 cells | 完整 workflow / 纯 KSP（s） | 外层步数 | 原 A6 最终残差 | 整树 RSS（B） |
|---|---:|---:|---:|---:|
| Q4 r2，coarse p4 | 3114.283619607013 / 2284.681783819 | 126 | 9.283165086752956e-7 | 7390937088 |
| Q3，coarse p3 | 7065.949492944987 / 6082.501362726 | 361 | 9.460140452867132e-7 | 4031815680 |

[Q4 r2 compact](https://github.com/Rookie1234567/MyFEniCS/blob/55ceb4c84a9041f715dc0c34c72fca689e753cce/docs/task039_extra_physical_multilevel/outcomes/records/v25_q4_ac_swap_observe_r2_result.json)、[Q3 compact](https://github.com/Rookie1234567/MyFEniCS/blob/55ceb4c84a9041f715dc0c34c72fca689e753cce/docs/task039_extra_physical_multilevel/outcomes/records/a6_h6_coarse_degree_v25_q3.json)与[粗阶比较](https://github.com/Rookie1234567/MyFEniCS/blob/55ceb4c84a9041f715dc0c34c72fca689e753cce/docs/task039_extra_physical_multilevel/outcomes/a6_h6_coarse_degree_v25.md)保留原范围。Q3省内存但不保证更快；统一执行路径也不把p3空间变成p4空间，不要求两者相同步数。

最新 [Response V28](https://github.com/Rookie1234567/MyFEniCS/blob/55ceb4c84a9041f715dc0c34c72fca689e753cce/docs/task039_extra_physical_multilevel/response_v28.md) 是工程收口：六组短配对没有复现 V26 的历史整场减速，R2=NO_ADOPTED_CHANGE，R4完整PDE=NOT_RUN。不能把该提交当作新的51分钟以下整场成果；继续以4bf2bba...快路径及cad282...粗阶能力为迁移锚点，不整体迁移工程探针或全部最新代码。

### 1.2 旧硬件异常必须针对性复核

[环境与迁移记录](outcomes/environment_and_migration.md)记载：CPU24/25曾忙时约1 GHz，正常插槽约3.6 GHz；只读寄存器支持外部平台限频，CPU2附近多个DIMM曾达85–90°C。CPU本身温度正常和普通thermal_throttle计数为0，不能排除这种异常。风扇安装后的温度、有效频率、带宽尚无本轮实测。

只读核对相关 [频率](outcomes/records/cpu_frequency_probe.json)、[硬件限制](outcomes/records/cpu_hardware_limits.json)、[BMC](outcomes/records/cpu2_bmc_thermal.json)。旧样本不冒充当前状态，不关闭PROCHOT、不改MSR/BIOS/governor/全机风扇和swap设置，也不终止隔壁Hybrid。硬件原则参见 [Intel限制原因说明](https://www.intel.com/content/www/us/en/docs/vtune-profiler/user-guide/2023-0/system-overview-analysis.html)。

## 2. H0/H1：选对 CPU，并验证 node1 不是“温度下降但吞吐仍慢”

### 2.1 CPU24–48 是候选范围，不是直接的多核启动命令

H0使用现成只读接口，例如 `lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE`、`numactl --hardware`、sysfs topology/thread_siblings、当前cpuset和affinity。记录实际CPU/内存node集合、socket编号、SMT同胞、在线状态与邻任务占用。**不能假设48也属于第二颗CPU，不能把24–48全部当成25个独立物理核心。** Linux逻辑编号、socket编号、NUMA编号必须现场映射。

在用户范围内选一个空闲、属于目标第二颗CPU/node1且不与邻任务共享忙碌SMT核心的逻辑CPU；优先CPU24，若拓扑或占用不合适则选范围内下一个合格核心，并在首次PDE前冻结 `resolved_worker_cpu`。若范围与node1没有交集，报告明确拓扑冲突，不静默回CPU23。父监督器沿CPU9，不与worker共享物理核心；若CPU9不可用，在不侵占邻任务的前提下选独立监督核心并记录。

**四场正式计算都使用同一个已选核心、MPI1、OMP/BLAS/MKL/NumExpr线程1。** MPI不得重新覆盖绑定，实际读回worker及数学线程affinity。范围授权不等于开启24线程，也不允许单rank在24–48之间不断迁移。编译与必要后代仍属于同一监督范围，工作量和核使用有记录。

CPU绑定与内存策略在启动worker、分配和first-touch之前设置。正式默认prefer经确认的node1，允许两节点内存回落，记录 `/proc/PID/numa_maps` 或 `numastat -p` 的实际分布与回落；**不能把2 nm严格membind到单个node后，因该节点耗尽而早于整机RSS Gate失败。** 小型定位测试可显式membind，正式必须区分policy和实际页位置。[Linux NUMA policy](https://cdn.kernel.org/doc/html/latest/admin-guide/mm/numa_memory_policy.html)解释preferred与bind的差别。

### 2.2 有界硬件诊断：计算效率、内存带宽、FEM作用分别测

先尽量使用没有其他heavy争用的窗口。不得停止邻任务；有共享负载则记录，并将受干扰比较标为inconclusive，不能据此宣布node1异常或彻底修复。只读记录空闲及持续负载时的DIMM/CPU/VRM温度、可得busy有效频率、功率/限制原因、进程CPU time、wall、线程和内存页位置。传感器或perf无权限写unknown，不能虚构读数或要求交互提权。

H1不启动完整PDE或大factor，独立硬件探针正常一组、累计有载窗口不超过10分钟；每项至多3个配对重复，预热另记，保存全部值与中位数，不选最快值。必要的代码仅为小型benchmark，不能演变成安装整套监控平台。

| 检查 | 方法与范围 | 回答的问题 |
|---|---|---|
| 同指令单核计算 | 同一编译内核/固定输入/相同线程与编译选项，在正常node0空闲核心和所选node1核心交错测试；有一段持续负载，不只2秒瞬时频率 | 原约1 GHz外部限频是否仍出现；不是以CPU使用率100%判性能 |
| 单核本地内存带宽 | 同一native/STREAM类固定读写内核，node0核心+node0内存与node1核心+node1内存；数组工作集超过LLC，建议总0.75–2 GiB且与现场余量相容，完成first-touch后计时 | 实际GB/s是否降低，而不是Python解释器循环速度 |
| 必要的交叉NUMA对照 | 本地两组有差异时再加node1核心+node0页、node0核心+node1页，最多形成一个2×2小矩阵；计算与数据类型保持一致 | 差异跟着CPU、内存node、跨插槽路径还是共享负载走 |
| 真实FE组件 | 在C阶段复用实际13.5 nm离散的独立A6/H6及小型Aq/传递固定向量；无额外大factor。若借H1对照CPU，只重建必要action并正确first-touch | 合成内核恢复是否也体现在FEM工作中 |

node0参考核心可沿用CPU23做上述小诊断，**不得把正式四场又放回CPU23**。CPU23忙或不允许时用同socket另一空闲核心并记录；不能从笔记本时长推断node0当前带宽。单核带宽不是node1所有核心同时工作的峰值带宽；本批结论限定于将要使用的MPI1/thread1。

[PETSc性能指南](https://petsc.org/release/manual/performance/)与[STREAMS说明](https://petsc.org/release/manual/streams/)支持将绑核、first-touch与带宽一起核对，但不提供本机一定相等的保证。不要比较不同缓存规模、不同内存流量计数或不同指令负载下的GHz/GB/s。

### 2.3 H1判读与后续启动

工程调查提示线预先固定：同配置本地单核带宽node1/node0低于0.8，或同工作量计算/FE时间node1/node0高于1.25，或持续负载有效频率仍贴近历史约1 GHz且受限原因支持，均需调查。0.8/1.25是排查提示，不是硬件定律、数学Gate或运行中自动kill条件；插槽内存条配置、工作频率、干扰和误差需共同解释。

有明确持续限频、内存热告警或无法解释的显著node1吞吐损失时，先保存 `NODE1_PERFORMANCE_NOT_QUALIFIED`，不启动四场长算例，不靠降低p/少通道/改PC绕过。合成测试正常且真实FE没有未解释的严重异常，可以进入R13双复现；传感器不足但执行性能有有效证据可标 `QUALIFIED_FOR_SINGLE_CORE_PILOT_WITH_SENSOR_LIMITATION`，两场长复现还要继续观察。完全没有有效吞吐对照时，不宣称已解决。

两场13.5 nm结束后再更新硬件裁决：已测持续负载下未见旧异常／异常仍在／证据不足。不能仅凭加了风扇、一个空闲温度或一次短测试写“永久彻底修复”。不新增基于吞吐变慢、短时全机换页或温度采样缺失的自动资源kill；发现异常先保留证据并阻断后续更大case。硬件保护始终保留，真正不可恢复错误按原机制处理。

## 3. M/C：p3 与优化 p4 必须共用执行路径，而不是仅有相同 profile 名

**用户要求是同一套已优化流程参数化为q=3/4，而不是把旧Q3专用慢路径原样装进新目录。** 保持V4第2节的依赖组级选择性集成，源只读，不整体merge/squash/reset，不覆盖整个src。已有工作站V20/D2、PORD64及RSS-only代码增量完善，不重新写一套求解器。

以r2的运行路径为基线逐项检查下表。源schema已有共享A6/H6开关，这不能证明所有传递、粗检查、setup和launcher都实际相同；也不能未经逐项审计就声称旧Q3所有模块都慢。

| 必须共用的执行机制 | 允许的q相关差异 | 需要的证据 |
|---|---|---|
| p6 retained外层、J增广逆桥、BAL_H组织、H6定义、FGMRES32 | q改变粗修正，收敛轨迹/步数可以不同 | 同一dispatcher/factory/source，实际调用计数与trace/port身份 |
| A6 volume与H6 apply/power10使用r2的N1E sum-factorized后端 | 无q导致的p6慢后端切换 | 真实class/module/blob、开关和kernel审计；原native witness独立保留 |
| H6对角/谱窗/seed与setup选择，p6局部凝聚及缓存/编译顺序 | 同一p6网格的几何、积分、H6定义不因q改变 | 相同输入下对角/谱窗与action数值等价；不能q4快setup、q3旧fallback |
| 直接P6q及其共轭限制的owner计划、批处理、gather/scatter | q的Basix局部矩阵、维数和实际工作量不同 | q4的合格单rank优化适用于q3时也启用并测试，不强行padding到p4维数 |
| Aq装配时单元凝聚、准确全局trace/port LU及按需精化 | 各自原A3/A4、局部块/因子维数、稀疏图和精化次数不同 | 同一参数化assembly/inverse/reduce/recover框架，每次返回原Aq≤1e-10 |
| 原Aq质量核验和独立原A6见证 | native核随q合法重编译 | 两条线相同检查策略与优化机制；原native oracle不能由候选自身取代 |
| 生命周期、共享只读buffer、资源/输出/计时/checker | 因对象大小、实际调用数带来的成本差别 | 同一规范和频率，全链policy读回一致，q3不携带p4无用对象 |

允许为q3补齐r2优化的阶次泛化与已知正确性/原生Linux兼容修复，并在同source冻结后运行。不是授权另做V26/V27的优化搜索，也不要求追随源最新工程实现。相同路径指相同算法/后端策略和实现框架，不要求相同数值矩阵、缓存字节数、执行秒数或迭代次数。

产出紧凑 `q3_q4_path_parity` 表：每行给q4与q3的实际factory、source/blob、配置、期望差异、调用/工作量、equivalence和采用结论；不能只静态读字符串。至少覆盖一次真实q3/q4 PC输入及非零内部/端口RHS。若某项只有q4优化而q3回退，必须先泛化验证；无法完成则标 `Q3_PATH_PARITY_BLOCKED`，本批不能把缺项隐藏后直接进入短波。

q3通过后，以该共同实现作为后续q3默认研究入口；新增改动须带q3/q4回归。不能仅在这次13.5 nm里打补丁，随后短波q3又走另一套旧路径。本批短波仍只跑q4，不在失败时自动切q3。

保留V4数学合同：完整curl/复质量项先相加再凝聚；完整Bi/Di、Hp/Hhat、非零内部载荷、MPC primal/dual/方向和strict slave-zero；凝聚与p传递不假定交换。p6仍是最终主空间，q3不是最终p3解，也不是p6→p4→p3递归层级。每场一份粗因子，逻辑粗调用与实际回代/精化分开，最多两次额外同因子修正，绝不复用另一粗阶或波长的factor/初值。

C阶段用一组合并真实小FE、复非Hermitian、MPC/端口、两个q、三种波长材料与监督测试完成接口资格；实际990网格可只构造所需action做配对，不为多个probe各建立大型factor。全部数值目标沿V4，不因路径统一放宽。不以mock-only代替真实FE，也不为证明fast额外重跑多个完整原模型。

## 4. 四场正式模型与执行顺序

### 4.1 13.5 nm 是本地结果的同离散复现

R13Q4/R13Q3均使用源original **p6/h7.5、9×5×22=990 cells、80通道** 的冻结轴坐标和材料tag，不能用目标原13.5 nm的p6/h10代替。源网格plan SHA为 `b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157`；来源是源 `outcomes/records/v21_frozen_geometry_mesh_plan.json`，使用时独立核对内容与实际网格。

两场几何：50×25 nm周期，z=-10…130 nm；original grating x/y宽17/25 nm、高120 nm；Si n=0.999002304859+0.00182649365i，air n=1、mu_r=1；13.5 nm、1° grazing、azimuth0、s、幅值1；原双Floquet/背景/DtN。冻结模型本身相同，只改变coarse_degree。所有输出平面、坐标、相位与通道规则沿源；p6/h7.5不是7.5 nm波长。

预期维数锚点：p6 storage667152、独立trace199260、端口80、retained外层199340；q4凝聚84680行，q3凝聚45440行。由实际对象生成，不通过硬编码绕过检查。不同ABI/索引宽度造成序列化hash变化时，用规范化映射/数组与数学等价桥解释，不强填旧hash。

**仅这两场13.5 nm允许并要求采用源990-cell网格/80通道。** 覆盖V4对源网格常量的笼统排除，不允许把它们泄漏到5/2 nm。

| 顺序/阶段 | 正式输入建议 | 固定模型 | 作用 |
|---|---|---|---|
| R13Q4 | `input/task39extra_para_workstation_capacity/v5_node1_13p5nm_p6h7p5_q4.dat` | 13.5 nm、p6/h7.5、990 cells、q4、80通道 | 复现r2的离散结果，核实长时node1性能 |
| R13Q3 | `input/task39extra_para_workstation_capacity/v5_node1_13p5nm_p6h7p5_q3.dat` | 同上，q3；共同优化路径 | 复现Q3并与同工作站Q4对照 |
| F5 | `input/task39extra_para_workstation_capacity/v5_node1_5nm_p6h4_q4.dat` | 5 nm Si、原p6/h4、q4、600通道 | 比较旧工作站5 nm与新快路径 |
| F2 | `input/task39extra_para_workstation_capacity/v5_node1_2nm_p6h1p5_q4.dat` | 2 nm Si、原p6/h1.5、q4、3904通道 | 验证短波能力/容量；不是旧2 nm续算 |

建议一个参数化native profile族和明确stage/coarse_degree，复用dispatcher；每个dat仍只代表一次计算。正式前冻结四个输入、最终backend/parity选择及源码。两场13.5 nm通过同一实现后，短波不得未经核验切回旧原生慢路径。

### 4.2 “差不多”按数值复现与性能分别判断

所有正式场：独立完整原A6相对残差≤1e-6；每次原Aq返回≤1e-10且最多2次额外精化；代数/传递/恢复操作尺度≤1e-10、端口闭合≤1e-8；abs(R+T+A_volume−1)≤1e-5、abs(A_balance−A_volume)≤1e-5；完整E/H、curl、R/T/A/A_volume、全部通道复幅值和功率、被动性/通道和均检查。原更严约束规则保持，Schur残差单列不替代原A6。

R13分别对本地相应q结果及工作站q3/q4结果比较：规范场L2/scaled-curl、selected E/H及复幅值向量相对差≤1e-4；R/T/A/A_volume绝对差≤1e-5；逐通道功率绝对差≤1e-6。采用既有近零绝对规则，不拟合相位、不重新归一化。原A6每8步和最终检查、独立native witness、每32步场checkpoint与恢复/释放顺序沿r2；输出频率两场一致。

源大型场数组可能在笔记本ignored目录。优先使用已有可取得的hash-bound参考packet；Codex没有对应访问权时不能虚构SSH/路径或要求重跑笔记本。缺失项标 `LOCAL_REFERENCE_ARRAYS_PARTIAL`；有完整新工作站q4/q3互比、独立原A6与全部自身物理、以及所有可用源观察量匹配时，可以给带范围限制的迁移结论并继续。不能把缺失源场比较填成PASS，也不能仅凭R+T+A≈1宣称复现全场。

源126/361步是旧结果，不是新最大步数；FGMRES32/max2048不变。若步数明显变化，核对p空间、H6窗口、相位、精化、舍入与路径，不能要求q3也126步，也不以旧同号迭代残差线中断。输出正确但成本变化须独立解释，不抹去性能负结果。

**51.90/117.77分钟不作跨机时限，也不要求工作站与笔记本耗时精确相同。** 比较full、KSP、setup、每步及单次A6/H6/P/Aq成本和内存；使用H1同工作量硬件对照帮助判断是否异常，不用固定倍数代表所有阶段。node1同机吞吐正常、路径已核验而跨机整体较慢，可以记录硬件/ABI差异并继续；未解释的严重性能退化、错误路径或持续硬件异常必须在放大前收口。

### 4.3 解锁顺序和停止范围

H0/H1→M/C→R13Q4→R13Q3顺序执行，原则上不逐小步骤等用户。两场R13的数值/物理、共同路径、适用回归及长时硬件观察都合格后，Codex保存 `R13_PAIR_RELEASE`，直接进入F5。只通过q4或只做q3组件不再足够；q3存在真实未闭合失败时F5/F2保持not_run，不能援引V4旧豁免绕过。

F5通过V4适用Gate后，保存决定并直接进入F2，无需再等一次用户批准。F5真实数值/物理/身份或监督失败未闭合，不启动F2。缺少连续精度参考按authority limited处理，不新开全局direct reference或h-convergence campaign。

正常四场，不先执行旧V3/V4再补四场，不同时启动两场，不跑notch/3 nm/p2或额外短波q3。真正实现bug允许每个受影响case至多一次登记修复重放；性能不好、RSS到线、真实不收敛不属于bug。后处理问题优先从保存解修复；如果共享核心在复现后改变，必须明确已测证据是否失效，不静默换source继续宣称同一路径。

## 5. 5 nm/2 nm身份和资源政策

F5/F2的物理、网格和输出身份保持V4第4节。Si折射率分别为5 nm `0.99396854453+0.00435380777i`、2 nm `0.99880148307+0.000213688647i`，epsilon=n*n，来源为已提交用户材料，不自行改W或无损。2 nm原网格54332 cells；600/3904是库存核对锚点，必须重新核对全部keys/归一化/相位，不能仅匹配数量。

保留工作站task-local Linux/complex128/int64/PORD64合格环境，核对动态库、NumPy/SciPy/BLAS、DOLFINx/Basix/FFCx/MPC、PETSc/MUMPS和MPI的真实版本与路径。源int32不强搬到工作站；全局NNZ/CSR指针必须安全。所有旧WSL服务路径、8 GiB/4687 MB等笔记本额度不迁入；四场使用同一工作站ABI，不为node1重装共享栈。

```text
resource_stop_policy          = measured_tree_rss_only_v3
rss_hard_limit_bytes          = 1300000000000  # decimal 1300 GB
rss_warning_bytes             = 1170000000000
swap/global_swap/faults       = observe_only
prediction_admission          = record_only
memavailable_runtime         = observe_and_warn_only
time_limit_mode              = none
screen128                     = progress_only
MUMPS_ICNTL23                = 0; read back, no inherited laptop quota
startup_headroom_bytes        = 137438953472  # inherited 128 GiB
```

实际整树RSS达到已声明Gate才触发本策略的资源自动终止；时间、预测、VmSwap或全机换页不单独kill。不得为13.5 nm新设8 GB硬线，或换回旧1537.5 GB与1300 GB相互矛盾的多个guard。四场launcher/service/wrapper/worker/粗层/checker同policy读回；正常退出尾采样不可读不制造第二个根因。RSS/PSS、swap、node页分布、后端allocated/used与derived载荷分别记账。

启动前检查有效内存/cgroup/磁盘及余量，node1严格绑定不作为人为容量上限。持续监控丢失、真正数值失败、不可恢复实现/I/O错误、max2048、用户停止按V3/V4处理；不关闭热保护或试图保证OS永不OOM。发生swap保留事实，RSS-policy通过不等于zero-swap生产资格。

四场heavy顺序排队。硬件对照及R13性能复现优先独占heavy窗口；不得暂停或杀隔壁Hybrid来创造独占。已授权共享运行仍须记录其CPU/内存与阶段，不将受干扰时长归因于算法。更换插槽不等于资源完全隔离，也不允许抢占整机2 TB。

## 6. 成本比较、交付与后续p3约束

新R13建立本工作站node1同环境的q4/q3表，含真实active/slave/interior/port/outer rows、粗矩阵NNZ、因子entries、symbolic/numeric、去重局部cache、Krylov、setup/KSP/每步/恢复/清场、完整与分阶段RSS及实际node页分布。h7.5新结果与笔记本旧结果分别标measured与环境，不拼接各版本最佳数值。

旧5 nm基线仍是698步、solve `206568.51908412296 s`、workflow `217665.16384237396 s`、观察RSS `50161172480 B`；[旧compact](outcomes/records/5nm_formal_attempt1.json)、[资源覆盖](outcomes/records/5nm_resource_coverage.json)中的监督断档必须保留。**新场从CPU23改到node1，因此总时间比同时包含算法、硬件位置/散热和可能的ABI/cache差异，只能称跨执行条件工程比较，不能全归为双凝聚或某一个kernel提速。** 不为消除这个限制重跑旧60小时基线；H1小对照只帮助解释，不是严格的全场校正因子。

旧2 nm在numeric未完、outer未开始时停止，无完整残差/RTA/工期；34.36天仍为假设外推。新2 nm只对比同scope已测阶段和记录真实完整成本，不声称相对旧“实测34天”提速。首次编译、预热、工程探针与正式wall分列，嵌套计时不相加；持续FEM负载阶段更新node1温度/频率/内存吞吐线索，不能从较大case自然更慢推断硬件又降频。

按V4的安全依赖释放KSP/PC/全局因子和无用矩阵，保留恢复必需对象与残差packet；后端借用矩阵时不提前detach。按live需要计入局部缓存，p3低内存是待复现的收益，不预先要求严格等于4.032 GB。该方法仍有增长型全局凝聚粗LU，不是factorization-free，四个固定original案例不是任意三维或0.7 nm正式资格。

建议正常提交：H/M/C诊断与公共q路径/测试；冻结四场输入与clean source；R13双复现及放行；F5；条件F2；最终文档。所有写入只在本执行分支，源码迁移由Codex完成；运行中不pull/切分支/改库，文档提交与运行源码分开；不amend/强推，不整体合并源分支，不改master或邻任务。

至少交付如下信息，可合并文件但不删语义：

```text
docs/task39extra_para_workstation_capacity/response_v5.md
outcomes/node1_qpath_reproduction_v5.md
outcomes/records/node1_v5_topology_and_hardware.json
outcomes/records/q3_q4_v5_migration_and_path_parity.json
outcomes/records/node1_13p5nm_q4_v5_compact.json
outcomes/records/node1_13p5nm_q3_v5_compact.json
outcomes/records/node1_r13_pair_v5_decision.json
outcomes/records/node1_5nm_q4_v5_compact.json
outcomes/records/node1_2nm_q4_v5_compact.json
outcomes/records/node1_v5_comparison_and_decision.json
outcomes/summary.md / outcomes/test_summary.md / outcomes/records/run_index.json
```

独立checker结果和raw/hash索引进入对应compact；每场保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境、CPU/node/threads、完整资源和E/H/衍射证据。大数组/场/因子/日志留ignored；同步项目progress/model_registry，未运行项明确原因。

Response首屏回答：选了哪个逻辑CPU/物理核心/node，48是否属于目标；风扇后忙频率/带宽与真实FEM是否恢复、结论限于何种负载；q3与q4哪些路径原来不同、怎样统一及什么差异仍是数学必需；R13两场是否复现本地、是否有完整参考缺口；5/2 nm是否通过、四场真实时间/内存；swap只观察策略是否全链一致。源V27不是新整场成果，不能把它当成已测优化迁入。

**本轮交付路径：先证实另一插槽可用，再以同一优化实现完成p4/p3两场13.5 nm复现；之后用p4顺序推进5 nm和2 nm。不要仅改CPU字符串，也不要仅把旧Q3挂到新入口。**
