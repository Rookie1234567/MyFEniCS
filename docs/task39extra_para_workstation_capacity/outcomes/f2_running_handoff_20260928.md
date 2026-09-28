# 2 nm p6/h1.5 工作站运行中证据交接（2026-09-28）

**RUNNING，尚未收敛；这不是正式数值/物理结果通过或最终收口。**

统一快照读取时间：`2026-09-28T02:34:15.838437+00:00`；UTC+8为`2026-09-28T10:34:15.838437+08:00`。各文件在同一次有界读取中冻结，读取耗时0.063609 s，并非跨文件原子快照。以下“当前”均指此时，不指提交或推送完成时。计算按原合同继续。

本次仅核对固定PID/start_ticks与已有文件，整理小型摘录；没有发送信号、读取新的smaps/numa_maps、改参数/源码/线程/CPU/NUMA/上限/watchdog/swap，没有启动PDE、因子分解、算子配对或性能试验。已有resources前缀只流式归约一次（CPU10、nice15，读日志耗时9.298 s）；没有反复解析整个增长日志，也没有复制矩阵、因子、场或大向量。

## 1. 身份和证据入口

| 项目 | 本场事实与证据 |
|---|---|
| canonical worktree | `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity` |
| Git目录 | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git/worktrees/task39extra_para_workstation_capacity` |
| 分支 / upstream | task39extra_para_workstation_capacity / origin/task39extra_para_workstation_capacity |
| 整理前HEAD / 工作树 | `64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa`；tracked及nonignored untracked clean |
| 整理前远端HEAD | b468907cf54d04280b461cae5fc9078186302d54；非交互ls-remote实读；本地ahead3/behind0 |
| 运行源码SHA | **64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa**；来自启动manifest/worker命令，绝不以文档提交HEAD替代 |
| logical run_id / execution_id | v5_node1_2nm_p6h1p5_q4 / 20260924T104936.107285Z |
| 启动UTC / UTC+8 | 2026-09-24T10:49:36.107349+00:00 / 2026-09-24T18:49:36.107349+08:00 |
| 结果目录R | `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/results/euv_grazing1_phi0/v5_node1_2nm_p6h1p5_q4__full3d_iterative__mpi1__Mna/20260924T104936.107285Z` |
| 输入路径 / SHA | `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/input/task39extra_para_workstation_capacity/v5_node1_2nm_p6h1p5_q4.dat`；e3febbe6a785d3866e37fd3353565111952fbfe0926ee0b2c5a42eaef32149e1 |
| physical-model SHA | fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef |
| resolved-config SHA | ceb5d3123ff856c70ca685f1a9df5492e23cead9edad5168997ac101331de291 |
| mode SHA / 通道 | 4b62741e84970cc5312c88039244ad5ba30065ea92dcf72a949773fef8de6364 / 3904；本次未读独立传播计数，propagating为unknown |
| root / MPI / worker | 341799/t17196977；341830/t17197099；341839/t17197130，快照中逐一匹配 |
| 监督 | detached父root为既有subreaper/watchdog，CPU9、PPID1；worker/MPI CPU24；独立15 s只读observer 341987/t17219061、CPU10、PPID1 |
| 服务身份 | 启动记录start_new_session=true；不是本次新建systemd服务；cgroup=/user.slice/user-1000.slice/session-129.scope |
| CPU/NUMA | manifest实际worker命令taskset24 + numactl --preferred=1；status允许Mems0-1；本次未另读numa_maps确认实际页面落点 |
| 启动dirty/patch | manifest没有单独clean布尔字段/patch记录；实际native→launch_specification执行路径启动前强制_physical_source_gate，dirty或SHA不符拒绝。因此启动clean为执行合同推断；快照clean为Git实读。未把缺失的producer字段伪装为存在 |
| 启动JIT缓存 | manifest.execution_cache.empty_before_launch=true；本run独立jit_cache |

启动命令（来自launch.json，实际worker完整argv与环境见evidence JSON）：

    taskset -c 9 bash -lc 'source scripts/activate_task39extra_pord64.sh && exec python scripts/run_case.py input/task39extra_para_workstation_capacity/v5_node1_2nm_p6h1p5_q4.dat'

ABI实际映射只有任务私有PORD64 overlay的libpetsc.so.3.19.6；同路径headers为PETSc 3.19.6、64-bit索引、complex。worker实际映射OpenMPI libmpi.so.40.30.6、OpenBLAS pthread libopenblasp-r0.3.26.so及其BLAS/LAPACK。数学线程环境OMP/OPENBLAS/MKL/NUMEXPR/VECLIB/BLIS均1，观测worker有3个OS线程，全部允许CPU24；OS线程数不等于数学并行线程数。MUMPS 5.5.1按该overlay headers与既有静态链接资格记录绑定，本场INFOG(7)=4实际PORD，ICNTL(23)=0；没有新增backend探针，也没有给映射库热替换。历史库hash见[v5 ABI合同](records/v5_m_c_and_four_input_contract_v1.json)，本次maps/headers/source blob核验见[evidence](records/f2_running_handoff_20260928_evidence_v1.json)，未重算大型loaded-library内容hash。

## 2. 本场实际生效路径

所有源解释绑定运行SHA 64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa；evidence.running_source_blob_index给出对应Git blob和SHA256，并核对当前文件字节与该运行commit一致。证据是本场manifest/profile、实际stage audits与该条调用链相互对应；并非“代码仓库存在某实现就算启用”。

| 问题 | 实际执行路径 | 原始定位 |
|---|---|---|
| p6外层空间 | 凝聚后的独立trace+端口，FGMRES/RIGHT/restart32；不是完整p6空间Arnoldi。BAL_H bridge仍进入fullspace PC与独立恢复验算 | stage7.p6_build；physical_retained_fgmres.py:21；runner:1595 |
| p4因子 | 装配时直接单元凝聚形成的trace+port增广AIJ；不是完整A4增广矩阵先装配再全局凝聚 | runner:263-309、362；stage7.p4_build/矩阵identity |
| A6快速作用 | PC用两个独立curl/mass的isotropic_sum_factorized_n1e_v26；**没有融合curl/mass**。独立原A6 residual仍用native authority | stage5.facts.kernels.component；physical_equivalent_fast.py:59；runner:688 |
| 原A4完整验算 | p4 native physical_action，经apply_original_a4；没有接入新的快速原A4验算 | runner:595-615、407；每次p4 decision返回原A4 rho |
| p6局部矩阵 | 原FFCx编译cell积分核tabulate_tensor_complex128，按材料与默认积分求和；**没有blocked Gram** | hcurl_assembly_time_condensation.py:177、856、876；runner:262-266 |
| H6 | 原positive diagonal、degree3原窗口；positive_sum packed/sum-factorized backend，batch8；power10/20次作用；lambda范围见compact | stage16-17；physical_light_setup；runner:635 |
| P/PH | 共享mesh的(6,4)直接传递，AlgebraicOwnerTransfer；fixed_serial_owner_route/optimized_owner_apply=true；PH adjoint/P primal；balance另做PH审核 | runner:647-681；physical_balanced_coupling.py:98 |
| 几何身份 | 已批准rounded_12_representative：只对tensor group key作decimal-round12，FFCx输入仍是组内lexicographic-min未舍入坐标；raw geometry与raw+orientation的LU/Schur/recovery身份保留 | stage2、7；builder:1368-1470；54 raw→6 tensor groups、87 oriented classes |
| 粗精化与耗尽 | 原A4 rho与独立port closure都以1e-10验算，最多额外2次，同一因子；累积FE及port状态。耗尽写failure packet并raise，不返回不合格修正 | p4_cell_condensed_inverse.py:646、787、890 |
| 外层耗尽/后处理 | 每8步独立检查，32步checkpoint；max2048终态真实残差仍不合格则ITERATION_BUDGET_EXHAUSTED并在正式输出前拒绝。没有自动换算法或以report residual代替资格 | physical_retained_fgmres.py:49-168；runner后续TRUE_RESIDUAL_PASS门 |

| 空间/结构 | 行数或NNZ（本场audit实测，注明派生） | 证据 |
|---|---|---|
| 单元 / 端口 | 54332 cells / 3904 channels | stage7 |
| p6完整storage / 独立完整FE | 35594790 / 35248752（派生full-slaves）；slave346038 | p6_build.full_rows、trace_constraints |
| p6完整trace / 独立trace / 内部 | 11145390 / 10799352 / 24449400 | p6_build.trace_rows、active_rows、interior_rows |
| p6保留KSP行数 | 10803256 = 10799352 + 3904；global A6/S6未物化，NNZ unknown（不写0） | p6_build.matrix_rows、p6_cell_condensed_action |
| p4完整storage / 独立完整FE | 10604228 / 10450240（派生full-slaves）；slave153988 | p4_build.full_rows、trace_constraints |
| p4完整trace / 凝聚独立trace / 内部 | 4736372 / 4582384 / 5867856 | p4_build.trace_rows、active_rows、interior_rows |
| p4实际凝聚增广因子行数 | 4586288 = 4582384 + 3904；完整FE+port为10608132（仅派生，未分解） | p4_build.matrix_rows |
| p4 NNZ / 预分配结构NNZ | 2070391064 stored / 2284367488 structural；原完整A4 NNZ unknown | p4_matrix_identity.nnz、trace_preallocation |
| 原始局部矩阵/类型 | p6维度882=450+432；p4维度300=108+192；每阶54 raw geometry、6实际积分tensor groups、87定向Schur类 | p6/p4 build维度、raw_geometry_class_count、tensor_group_count、oriented_schur_class_count |

p6 audit的active_full3d_equivalent_dofs原字段值为35594790；此处完整独立FE行数另按slave推导，不能将该原字段误当独立编号数。p4矩阵CSR/values/mapping SHA见evidence.stage7，未再遍历活跃矩阵。

## 3. 最新进展与残差口径

| 指标 | 快照事实 | 原始字段 |
|---|---|---|
| 状态/退出/最终Gate | RUNNING，阶段solve；exit unknown/null；未到正式数值/物理/RTA资格 | 活跃PID、最新stage21；launcher summary还是launching占位 |
| 最后完成外层iteration | **64**；无65完成记录 | iterations最后行 |
| PC及粗调用 | bridge sequence65已完成，含setup一次，实际已完成64次outer PC；下一sequence66/outer PC65为从后续粗调用推断；最新完成logical131；当前精确子操作unknown | pc_applies最后行、scope统计、p4_decisions最后行 |
| 最新reported residual | 0.022358747111689517：KSP UNPRECONDITIONED reported norm / retained RHS norm；不是独立原A6 | iterations.reported_schur_relative |
| 最近独立原A6真实残差 | **0.022358747111508717**，iteration64、physical_residual_pass=false | monitor_residuals.original_A6_relative/explicit_true_residual |
| 独立检查时间 | solve_seconds=130416.063935；派生UTC=2026-09-28T02:16:21.597259+00:00；row没有独立UTC字段 | solve phase UTC起点+该row monotonic solve_seconds |
| 恢复/端口检查 | native_identity=2.7569192908843146e-11；internal=3.2075152862946513e-18；port closure=7.760795722004254e-16 | 同一monitor row |
| 总workflow | 315878.685780 s = 87.744079 h，worker workflow起点→快照；launcher起点另为315879.731119 s | snapshot clock - stage21.workflow_started_clock |
| 完整setup | 184388.380644 s = 51.218995 h；conservative budget184388.380665 s另列 | stage21.workflow_clock_interval |
| 已执行KSP阶段 | 131490.305148 s = 36.525085 h，含监测/恢复/checkpoint；最后已写monitor为130416.063935 s。最终直接ksp_solve_monotonic_seconds尚未写，unknown | snapshot - solve phase origin；solver:146-161 |
| 粗层返回资格 | 保存的131条logical return全P4_RETURN_PASS，实际最多额外1次精化；最新sym/num/solve=1/1/193 | p4_decisions前缀 |

iterations在iteration64有两次convergence callback（restart边界），最后step_wall=1445.166410 s是重复callback间隔，不是第65步。最新monitor的solution_source=live_buildSolution。两个残差数值接近仍属于不同定义，不合并拟合收敛率或据此外推剩余时间。

最近8个不同完成步57–64采用各iteration第一次callback的step_wall_seconds，均值 **2008.827413 s（33.480457 min）**；其中57步为3142.779920 s，包含前一56步独立检查影响，其余58–64均值1846.834198 s。callback时间差包含上一callback之后的场检查/监测/输出及本步工作；不是纯算子或KSP核时间，也不包含各callback之后尚未完成的检查。逐点和重复64记录见[iteration CSV](records/f2_iterations_20260928.csv)。

## 4. setup时间边界、CPU与内存采样

全部相邻stage为同场monotonic差，CSV提供完整UTC开始/结束、原始行号以及resource第一/最后/峰值样本行号。以下20个**相邻父区间互不重叠**；p6/p4与H6的内部计时为其中子计时，不能再次相加。CSV中的worker/parent CPU差只覆盖该区间第一至最后已有resource样本，不是完整区间精确CPU计时，更不是CPU线程总工作量；compiler子进程CPU未另归账。零/一个样本的CPU记unknown。

| CSV区间 | 边界内容 | wall (s) | worker CPU采样差 (s) | 区间整树RSS采样峰 (GB十进制) | 原始边界 |
|---|---|---|---|---|---|
| 1 | workflow→runtime入口 | 0.008879 | unknown | unknown | CSV 1；stage 1,2 |
| 2 | 共享mesh/空间/Floquet准备 | 151.476955 | 150.860 | 2.922 | CSV 2；stage 2,3 |
| 3 | volume quadrature metadata | 0.339953 | unknown | 3.420 | CSV 3；stage 3,4 |
| 4 | native fine/p4 action、端口与packed PC作用准备（合计） | 8844.889649 | 8417.360 | 29.376 | CSV 4；stage 4,5 |
| 5 | p6+p4凝聚form编译 | 64.918579 | 19.000 | 31.635 | CSV 5；stage 5,6 |
| 6 | p6/p4凝聚组件、端口及矩阵身份（父区间） | 2841.504761 | 2704.440 | 185.528 | CSV 6；stage 6,7 |
| 7 | 后处理JIT预编译 | 57.475693 | 20.080 | 184.929 | CSV 7；stage 7,8 |
| 8 | 后处理JIT释放 | 0.542070 | 0.310 | 184.510 | CSV 8；stage 8,9 |
| 9 | runtime收尾 | 0.001470 | unknown | unknown | CSV 9；stage 9,10 |
| 10 | symbolic调用前 | 0.042330 | unknown | unknown | CSV 10；stage 10,11 |
| 11 | p4 symbolic区间 | 79.626349 | 74.540 | 217.826 | CSV 11；stage 11,12 |
| 12 | symbolic→预算记录 | 0.032350 | unknown | unknown | CSV 12；stage 12,13 |
| 13 | 预算记录→p4 numeric完成 | 44111.673835 | 44087.110 | 1143.415 | CSV 13；stage 13,14 |
| 14 | numeric→inverse/ledger factor收尾 | 273.337195 | 162.810 | 1122.934 | CSV 14；stage 14,15 |
| 15 | H6入口前 | 0.001872 | unknown | unknown | CSV 15；stage 15,16 |
| 16 | H6准备（父区间） | 120224.788820 | 18044.230 | 1120.527 | CSV 16；stage 16,17 |
| 17 | H6→传递与BAL_H bridge | 1127.286036 | 158.020 | 1131.745 | CSV 17；stage 17,18 |
| 18 | 原Aq投影QA | 869.311902 | 812.050 | 1131.868 | CSV 18；stage 18,19 |
| 19 | 同对象启动QA（包含一次PC） | 5741.118165 | 5132.610 | 1137.528 | CSV 19；stage 19,20 |
| 20 | QA→solve marker | 0.003760 | unknown | unknown | CSV 20；stage 20,21 |

[完整stage/资源边界CSV](records/f2_setup_stages_20260928.csv)。网格、function spaces、Floquet/MPC、port/native action准备、传递及JIT在这些区间内交错；没有独立子计时的项目均为unknown。区间4包含fine和p4 native action、端口以及packed PC对象构建，不将其全部叫JIT或局部积分。区间6包含builder以外的port装配、cache、matrix final assembly与identity，不将剩余差额改名Python开销。

| 已有子计时 | wall (s) | 所属父区间 / 内存对象 | CPU时间 |
|---|---|---|---|
| p6 build total | 463.355848 | CSV6；action-only，共享LU/Schur/recovery，不物化全局A6/S6 | unknown |
| p6 FFCx tensor kernel | 292.124320 | p6 build子计时；6组tensor | unknown |
| p6内部LU/Schur | 12.275616 | p6 build子计时，原字段local_schur_seconds_max；恢复数据无单独timer | unknown |
| p4 build total | 292.202399 | CSV6；稀疏trace+ports预分配，凝聚矩阵 | unknown |
| p4 FFCx tensor kernel | 33.861449 | p4 build子计时；6组tensor | unknown |
| p4内部LU/Schur | 0.959826 | p4 build子计时；恢复单独timer unknown | unknown |
| p4结构/预分配 | 91.632152 | p4 build子计时；2284367488结构NNZ | unknown |
| p4局部稀疏插入 | 57.492479 | p4 build子计时 | unknown |
| p4最终全局装配 | unknown | audit当时deferred，final_assembly_seconds=0只是递延占位；runner随后ports插入后确实assemble，无独立timer | unknown |
| H6 diagonal | 118597.092899 | CSV16子计时；原positive diagonal与inverse_sqrt | unknown（CSV16总CPU不能分配到本项） |
| H6 positive/native作用对象 | 83.425555 | CSV16子计时；packed positive_sum对象 | unknown |
| H6 power10 | 1352.128188 | CSV16子计时；20次mult，其中mult合计1320.326423 s | unknown |
| H6 B6 shell | 0.000213048 | CSV16子计时 | unknown |

**“LU44110秒”核对：**一次p4 numeric确实完成，numeric_calls=1、symbolic_calls=1、solve_calls=0，INFOG(1)=0。reference_budget_evaluated→reference_numeric_complete的完整marker区间为 **44111.673835 s（12.253243 h）**。该区间包住一次factor.numeric和其后的info读取/marker，不是严格独立numeric API内部timer。旧44110.416671 s来自同区间的watchdog第一/最后样本覆盖，短于marker边界约1.26 s；不能把该采样跨度冒充完整调用计时。原文件事件范围及原始INFOG均保存在evidence stage13/14。setup减numeric marker区间为140276.706809 s，仅为同钟未归因差额，不称装配、积分或Python开销。

H6父区间120224.788820 s≈33.396 h，覆盖样本worker CPU18044.23 s、parent CPU115503.09 s。已有[9月26日PSS观察](records/f2_pss_observation_20260926.json)记录约6.58 s一次smaps_rollup、每次parent CPU约6.33 s以及同时出现的worker mmap等待；5 s schedule在扫描前设定导致扫描超过间隔后连续重复。它是观察证据，**没有PSS关闭对照**，不能说H6“本来只需5小时”或将全部差额归因PSS。本次不修改诊断策略。

## 5. 最近完整PC的两次C

最近完整记录为pc_applies sequence65（第64次outer PC），logical129/130；同一因子累计solve188→191，共3次实际MatSolve，没有新symbolic/numeric。原始记录行、字节范围与行hash见evidence.completed_pc_records/p4_logical_records。PC记录没有单独UTC开始/结束或整段wall timer；只能给记录mtime上界和已有组件计时，不能事后热加计时。

| 项目 | 第一次粗修正logical129 | 第二次反馈粗修正logical130 | 证据/缺项 |
|---|---|---|---|
| PH限制 | unknown | unknown | C closure在ledger前调用apply_adjoint；无独立timer |
| p4 RHS缩减/打包 | unknown | unknown | inverse.apply内部；无独立timer |
| 现有因子MatSolve | 时间unknown；实际2次 | 时间unknown；实际1次 | 初解+第一次额外精化；cumulative solve188→190→191 |
| 单元内部恢复 | unknown（2个RHS） | unknown（1个RHS） | 同inverse.apply；无独立timer |
| 原A4完整体积作用 | unknown（2次验算） | unknown（1次验算） | native apply_original_a4；无独立timer |
| 原A4 DtN作用 | unknown（2次验算） | unknown（1次验算） | 与volume一起调用native physical_action，无分项timer |
| 原A4 rho | 1.3044651893961795e-10→1.969659317230412e-13 | 3.46261638118308e-11 | 原始每次验算rows |
| 端口闭合 | 2.8052966982840957e-12→2.8052864457293465e-12；耗时unknown | 5.562006183010052e-12；耗时unknown | 独立H*a-D*c检查，累积状态 |
| 额外精化 | 实际1次，上限2；每次timer unknown | 实际0次，上限2 | 每次rho与MatSolve计数保留 |
| p4 ledger完整wall | **879.549533 s** | **439.942629 s** | 从solve(rhs)入口到合格return；含缩减/MatSolve/恢复/A4/closure/范数 |
| P延拓 | unknown | unknown | ledger后apply_primal；无独立timer |
| C各自含传递的完整wall | unknown | unknown | 只累计两次C timer，未分别保存 |

两次C累计 **1371.435401 s（22.857257 min）**；两次p4 ledger累计1319.492162 s，占C计时约96.212%；C减ledger为51.943239 s，包含两侧传递、日志/分配/清理等外围工作，不能全归入P/PH。故现有实测说明主要时间落在p4 ledger内部，传递外围不是主要部分；**仍无法分清MatSolve、恢复和原A4验算谁占主要份额，不能把整个C叫LU回代。** 不拿笔记本占比代替本场。

两个A6调用合计186.846761 s（每次unknown），一次H6为136.814053 s；主要timer相加1695.096214 s，仅为子项和，**完整PC wall unknown**，还遗漏balance中的两次PH审核、向量norm/copy/释放以及外层bridge工作。外层Schur、正交化、单独原A6与输出累计timer运行结束前未写，均unknown；最新reported callback→monitor append差1315.253938 s只代表explicit Schur+恢复/native验算等组合延迟，不是A6单项，也不含随后checkpoint。

| bridge序号（含setup） | 已完成outer PC数 | 两次logical | 两次C合计(s) | p4两次ledger(s) | 两次A6(s) | H6(s) | 精化次数 | MatSolve数 |
|---|---|---|---|---|---|---|---|---|
| 2 | 1 | 3/4 | 1309.278 | 825.459+433.702 | 185.622 | 132.376 | 1+0 | 3 |
| 33 | 32 | 65/66 | 1371.252 | 879.495+441.318 | 183.138 | 133.814 | 1+0 | 3 |
| 64 | 63 | 127/128 | 1369.669 | 883.614+435.062 | 183.980 | 134.472 | 1+0 | 3 |
| 65 | 64 | 129/130 | 1371.435 | 879.550+439.943 | 186.847 | 136.814 | 1+0 | 3 |

第64序号PC的两次C为1369.669443 s，即22.827824 min；“22.83分钟”对应这条较早完整记录。最近第65序号为22.857257 min。early sequence2、mid sequence33也仅沿用已有记录，没有增加测量。随后logical131已合格返回（1次精化、2次MatSolve、874.034572 s），但sequence66未有完整PC记录，不把部分记录算成完成PC或第65步。

## 6. 内存、上限及生命周期

统一采用B与十进制GB（1 GB=10^9 B）；不混用GiB。

| 指标 | 数值 / 范围 | 口径与定位 |
|---|---|---|
| 当前任务树RSS | **1151172259840 B = 1151.172259840 GB** | resources第104020行，2026-09-28T02:34:08.657526+00:00 |
| 当前任务树PSS | 1151090952192 B | 同条既有样本；没有本次新做PSS扫描 |
| 既有前缀RSS峰 | **1154356473856 B = 1154.356473856 GB** | [0,985992617) bytes，104020条；峰第103455行、2026-09-28T01:28:16.296977+00:00 |
| 既有前缀PSS峰 | 1154478180352 B | PSS与status/RSS非原子读取，可略大于RSS采样值；不是可相加对象 |
| 任务swap当前/峰 | 0 / 0 B | 同过程树；未将全机计数归因到任务 |
| 全机pswpin/out | 当前0/229 pages，启动稳定基线0/0，delta0/229 | manifest.native_capacity_isolation.swap_launch与resource.global_swap_pages；observe-only |
| watchdog可读/新鲜 | age=7.180942 s；104020/104020 status可读；unreadable/vanished为空；最大相邻间隔7.406119 s | 冻结resource前缀；PSS样本49957条，均可读 |
| 实际硬线/警戒 | 1300000000000 / 1170000000000 B，warning=false | resource.launch_cap_bytes/rss_warning_bytes；唯一停止authority为整树实测RSS；无time deadline |
| 当前内存envelope | effective_available=950933897216 B；动态planning cap626468839424 B | 是resource.memory_envelope诊断，**不替代本场固定1.3e12 RSS硬线** |
| numeric期MUMPS allocated/used | 1091654000000 / 916713000000 B（百万字节转换） | stage14 INFOG19/22；numeric阶段allocated/effectively-used后端范围，非当前整树RSS |
| 因子条目估计表达 | INFOG29=-54415 →约54415000000 entries（百万精度） | MUMPS 5.5.1负值按百万条；complex128值载荷约870640000000 B，仅派生，不当实际RAM |
| 预测峰 | 2392236814208 B | stage13/14 predicted_peak_is_diagnostic_only=true；未用来停机，不与实测相加 |

后端INFOG解释来自本overlay的MUMPS 5.5.1 userguide第93–94页：INFOG18/19为factorization allocated内部数据，21/22为effectively-used，负INFOG20/29为百万条。原PDF路径为tmp/task39extra_v5_abi_restore_20260923/base/src/petsc/int64-complex/externalpackages/MUMPS_5.5.1/doc/userguide_5.5.1.pdf；未把RINFOG内存字段误叫计时。阶段峰的范围另见CSV，不能累加不同阶段峰。

| 已记录对象 | 载荷或后端范围 (B) | 生命周期/限制 |
|---|---|---|
| p4凝聚矩阵 | 4586288行、2070391064 stored NNZ；独立resident bytes unknown | factor输入保留至求解完成后release；不能按NNZ乘值宽直接等同全矩阵RAM |
| p4 MUMPS因子 | 上述allocated/used与百万精度entries；当前独立因子resident unknown | 只建一次，后续重复MatSolve，factor常驻，未复制或扫描 |
| p6 assembly临时raw/oriented | 74680704 / 259780608 | builder peak字段；raw/oriented临时引用在return后释放，Schur另被retained对象持有，不能将同载荷算两次 |
| p4 assembly临时raw/oriented | 8640000 / 51314688 | builder临时峰，不是当前常驻值 |
| p6 builder retained cache | 1084646808（其中LU282036600、recovery270604800、Schur259780608） | 同类型数组共享；rhs/trace等细项见compact，不另加到RSS |
| p4 builder retained cache | 74096208（LU16273872、recovery28864512） | 原A4恢复/精化使用；与完整action/port对象不是完整分账 |
| p6 action array inventory | unique_cache108004276088；port子集106341066752；retained子集93211397240；cell carrier payload91060468992 | setup结束时统计；这些子集重叠。unique按ndarray对象id去重，view可能共享backing，不是allocator或RSS分账 |
| p4端口内部数据 | stored_interior_term_bytes3708766240；578 port cells；B/D direct各69078276 entries | 与常驻矩阵/port缓存可能重叠；不作独立resident归因 |
| p6直接端口数据 | B/D direct各154092488 entries，无global dense trace-port/full A6/S6 | 包括在action inventory相关范围；不复制 |
| retained / full p6单向量 | 172852096 / 569516640（complex128载荷派生） | 不含PETSc/allocator overhead；bridge/检查需要完整向量 |
| Krylov与其余workspace | restart32名义65个retained向量载荷11235386240；实际已分配/常驻unknown | 这是尺寸公式，不是全过程精确向量清单；其他临时/桥接/传递/JIT残留独立RAM unknown |

raw几何54类、tensor6组、定向Schur87类为本场实际audit；本次不改分组或舍入。setup前/后cache身份与上述inventory相同，证明同对象setup QA未增长；运行中后续cache增量unknown，未触发新的hash全量扫描。正式解尚未完成，求解栈release、完整原A6恢复后验、RTA/checker最终Gate未完成，不称已释放或正式PASS。

## 7. 可追溯交接与推送边界

- [compact JSON](records/f2_running_handoff_20260928_compact_v1.json)：状态、身份、计数、派生公式、所有unknown和摘录hash；SHA256=c5a5b15db69dd4b01260abb4b2930ab1ffb5b144db470503a602a09fe9dd122a。
- [evidence JSON](records/f2_running_handoff_20260928_evidence_v1.json)：固定PID/环境/maps、启动记录、选取stage字段、early/mid/recent完整PC与每次粗精化row、最近monitor、原始行/字节/hash、resource归约及运行source blob清单。
- [setup边界CSV](records/f2_setup_stages_20260928.csv)、[iteration CSV](records/f2_iterations_20260928.csv)、[已有PSS观察](records/f2_pss_observation_20260926.json)：均为小型稳定摘录，hash/长度登记在compact.evidence_artifacts。
- 原始R目录与观察日志继续在ignored artifacts；此次保留副本目录为`/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/tmp/f2_handoff_20260928T023415Z`。原始增长文件的hash仅声明冻结的byte range，绝不声明未来整个文件hash不变。选字段JSON不是原始整行的替代，原行hash可在本机原路径相应区间复核。
- 当前manifest/run_summary仍为launching/not_run占位、exit=null，尚未终态回写；本次没有覆盖这些活跃producer文件。任务summary/response追加有时间戳的RUNNING交接，保留全部旧失败、旧快照和partial证据。
- 本次在基于运行SHA的隔离sparse detached文档worktree提交；保持canonical执行worktree的分支/HEAD/clean不变，避免终态_physical_source_gate因文档HEAD变化失败。新提交只含本任务文档/轻量摘录；既有ahead3个已批准提交会随远端分支正常快进推送。文档提交不替代运行source；不动task/review、普通默认配置、master或其他任务，不pull/merge/rebase/切分支，不强推。

未完成的主要证据缺口是：C内部MatSolve/恢复/native A4体积与DtN的独立timer、完整PC wall、KSP各累积timer及真实resident对象分账。此交接保存这些缺项供后续审阅，本次不开展优化、重跑或额外测量。
