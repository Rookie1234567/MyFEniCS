# 2 nm p6 h1p5 运行终态与 OOM 证据报告

本报告供 ChatGPT 审阅工作站 F2 已取得的数值进展、性能与异常退出证据。该场在完成第228步后，于 2026-10-02T11:52:46.095318+08:00 被内核 OOM 杀掉，随后以 `WORKER_FAILED / exit137` 结束并清场。最近独立原A6残差仍为第224步的 `9.758316562442362e-5`，未取得 `1e-6` 数值资格；没有正式 R/T/A 或物理 checker 结论。

OOM 是内核因受限范围无法满足内存分配而杀进程的机制。本次触发分配的进程是另一个 Python PID1172428，内核选中本场 worker341839 作为释放内存的对象。内核明确记录 `CONSTRAINT_MEMORY_POLICY, nodemask=1`；整机仍有约888 GB空闲，但这次受限分配发生在node1。任务树实测RSS未达到1.3 TB硬线。触发进程所属任务、完整命令及具体内存策略尚未查明，因此不归因到任何邻近项目，也不把本场允许回落的preferred策略直接认定为根因。

## 记录时间和运行身份

证据冻结读取时间为 **2026-10-02T04:49:18.771814+00:00 UTC / 2026-10-02T12:49:18.771814+08:00 UTC+8**。事件时间与本报告读取时间分别记录，数字来自同一run；本次没有新增计算或性能测试。

| 项目 | 已有实测记录或固定身份 | 证据 |
|---|---|---|
| 执行分支与canonical工作树 | `task39extra_para_workstation_capacity`；`/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity`；upstream `origin/task39extra_para_workstation_capacity` | 本次Git核对；compact.documentation_publication |
| run与开始结束 | `v5_node1_2nm_p6h1p5_q4` / `20260924T104936.107285Z`；start `2026-09-24T10:49:36.107349+00:00`；end `2026-10-02T03:53:28.924683+00:00` | run_manifest.json.start_time/end_time |
| 数值源码SHA | `64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa`；启动及终态均clean | manifest.source_sha/source_after；watchdog.source_state |
| 输入路径与SHA | `input/task39extra_para_workstation_capacity/v5_node1_2nm_p6h1p5_q4.dat`；`e3febbe6a785d3866e37fd3353565111952fbfe0926ee0b2c5a42eaef32149e1` | input_original.dat全文件hash与manifest互核 |
| 物理模型SHA | `fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef`；2 nm Si、p6/h1.5、q4 | manifest.physical_model_sha256/native_capacity_contract |
| resolved与通道SHA | `ceb5d3123ff856c70ca685f1a9df5492e23cead9edad5168997ac101331de291`；mode `4b62741e84970cc5312c88039244ad5ba30065ea92dcf72a949773fef8de6364` | manifest与同run前次ABI/runtime记录 |
| 入口与执行 | `python scripts/run_case.py input/task39extra_para_workstation_capacity/v5_node1_2nm_p6h1p5_q4.dat`；worker前缀 `taskset -c 24 numactl --preferred=1 mpiexec -n 1` | manifest.worker_command及前次运行身份 |
| root / MPI / worker身份 | 341799/t17196977 CPU9；341830/t17197099 CPU24；341839/t17197130 CPU24 | 同run已有身份记录；内核victim PID匹配 |
| observer | 341987/t17219061 CPU10，15秒只读监督；不是本次OOM杀进程的执行者 | 同run启动/前次观察记录 |
| ABI与线程 | MPI1/math1；PETSc3.19.6 int64/complex128；持久PORD64 overlay、MUMPS5.5.1；实际mapped OpenBLAS0.3.26 | [前次同run交接](f2_running_handoff_20260928.md)与compact.abi；死亡后未重载或重新probe |
| 文档提交基线 | `ccd357885f7f9be84efe3be07868cc94f13d93fc`；独立detached canonical文档工作树 | 本次remote base回读；新文档HEAD不能冒充运行SHA |

完整原始目录为 `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/results/euv_grazing1_phi0/v5_node1_2nm_p6h1p5_q4__full3d_iterative__mpi1__Mna/20260924T104936.107285Z`。小文件hash、JSON字段、行号和字节范围在[证据JSON](records/f2_terminal_oom_20261002_evidence_v1.json)；运行源码工作树保持原HEAD和clean，文档从已有远端交接提交追加。

## OOM 事件和资源口径

| 指标 | measured 或 derived 数值与单位 | 来源 |
|---|---|---|
| 首因 | kernel OOM；victim341839；触发分配PID1172428 CPU30；`CONSTRAINT_MEMORY_POLICY, nodemask=1, mems_allowed=0-1` | [内核稳定摘录](records/f2_kernel_oom_20261002_excerpt.txt) |
| node1 Normal空闲与最低水位 | measured `459396` / `462820` KiB；derived `448.628906` / `451.972656` MiB | 同一次内核Mem-Info；不是全机MemAvailable |
| 全机free页 | measured `216791019`页；page `4096` B；derived `887976013824` B即 `887.976014` GB | 内核global free；包含其他节点，不能供node1受限分配任意使用 |
| 内核swap | measured free0 KiB / total `8388604` KiB | 内核事件当时，全机口径 |
| 全程整树RSS采样峰 | measured `1154381864960` B = `1154.381865` GB | watchdog.summary，151234个样本 |
| RSS硬线与比例 | 固定 `1300000000000` B；derived峰值占 `88.798605%` | measured_tree_rss_only_v3；未观测触线 |
| 任务树VmSwap采样峰 | measured `8574500864` B | 同树采样；与kernel全机swap分列 |
| 全机pswp增量 | baseline in/out=0/0；end及delta=3138800/5146004页 | watchdog.global_swap_activity；归因未决，不能全计入本任务 |
| 实际政策与终态 | RSS-only；预测record-only；swap/global observe-only；无时间截止；`WORKER_FAILED`、exit137、descendants cleared | manifest合同与watchdog摘要 |
| 当前活跃求解RSS/PSS与终态PSS峰 | unknown或不适用；求解已终止，未补做PSS扫描 | 本次只读取既有摘要和resource有界尾段 |

本场manifest明确是 `--preferred=1` 且允许node0/node1回落，并非strict membind。上述node1掩码属于触发OOM的那次分配；当前证据不能证明它就是本场worker的preferred规则导致。整机free、node1 free、RSS、VmSwap、后端allocated/used与预测是不同口径，不相加，也不把1.3 TB监控线当作内核永不OOM的保证。

MPI记录rank0被signal9杀死，详见[MPI退出摘录](records/f2_mpi_exit_20261002_excerpt.txt)。其中OpenMPI的“Per user-direction”是通用退出文案，不能据此判断用户手动停止。内核OOM首因有直接记录；observer缺失通知、早期stale/E2BIG疑点和资源尾部的global-swap诊断字段不能替代该首因。

watchdog/resources.jsonl总 `1447468256` B。本次仅读取末尾 `[1446943968,1447468256)` 字节中的完整行，见evidence.resource_terminal_tail，未扫描或hash整个资源日志。最后含worker的样本发生在kill/reaping过程中，member数据可能竞争失效；不能用其已释放后MemAvailable重构kill前内存，不能宣称做了全程采样间隔复审。采样峰值采用生产者终态摘要，当前值与历史峰分列。

## 最后数值进展和检查点

| 指标 | measured 或 derived 记录 | 含义与证据 |
|---|---|---|
| 最后完成外层步数 | 228 | iterations.jsonl最后行，不能由PC序号推步数 |
| 第228步Schur相对量 | `9.373049823814199e-5` | retained KSP报告量；不是独立原A6 |
| 最近独立完整原A6 | 第224步 `9.758316562442362e-5`，容限 `1e-6`，derived为门限的 `97.583166` 倍 | monitor_residuals，physical_residual_pass=false |
| 独立检查的记录时点 | 最后重复callback solve_seconds `471552.965611`，derived `2026-10-02T01:01:58.498935+00:00` | 原row无单独UTC，按solve原点+monotonic偏移推导；较早同224row另存 |
| 最新完整PC记录 | sequence230，setup1次+outer229次 | 该PC已写BALANCED_ACTION_COMPLETED，但第229步外层完成callback未写；不称完成229或230步 |
| p4累计计数 | logical460；symbolic/numeric/MatSolve=1/1/686；已有460条均P4_RETURN_PASS | p4_decisions；粗返回通过不等于最终细层通过 |
| 保存解 | 第224步full与retained解和恢复packet仍在 | 原run目录下 `full_solution_checkpoint_manifests/iteration_000224/manifest.json`；文件存在与尺寸核对，未重读/重hash大型数组 |
| 最终Gate与输出 | 最终KSP reason/timer和终止时原A6 unknown；RTA/checker NOT_RUN；NOT_QUALIFIED_INTERRUPTED | SIGKILL中断，无正常完整收口 |

全部独立A6检查原row见[残差CSV](records/f2_a6_residual_history_20261002.csv)，重复restart callback保留并标记，未合并不同残差来拟合速度。以下只列每32步的最后同iteration独立检查，seconds为自solve起点的记录偏移，包含监测/恢复/输出，单位与身份均为同run measured：

| iteration | 独立原A6相对残差 | solve_seconds |
|---:|---:|---:|
| 0 | 0.999999999999998 | 1299.334677 |
| 32 | 0.0611148758950009 | 64824.137503 |
| 64 | 0.0223587471115087 | 130416.063935 |
| 96 | 0.00802798723580985 | 198317.338303 |
| 128 | 0.0019690582641582 | 266971.158819 |
| 160 | 0.000608439952982521 | 336496.184233 |
| 192 | 0.000213510534366914 | 403270.907693 |
| 224 | 9.75831656244236e-05 | 471552.965611 |

检查点只有解，manifest明确 `solution_only=true`，没有把因子、residual或Krylov basis作为checkpoint。不能据此承诺免setup、免LU或原KSP无缝续算；本次未重启、未开发恢复入口。历史失败、9月28日RUNNING快照和5 nm成功记录继续保留各自范围。

## 已有时间和性能证据

| 口径 | measured 或 derived 秒数 | 说明 |
|---|---:|---|
| 完整launcher workflow | 666232.838508756 | 185.064677小时，即7天17小时3分52.84秒 |
| watchdog包围区间 | 666232.740784148 | 与launcher起点不同，不相加 |
| 完整setup | 184388.380644418 | workflow→solve marker，51.218995小时 |
| 最后完成步callback solve时间 | 479635.727603270 | 第228步；包含检查/输出，不是纯KSP API timer |
| solve marker→watchdog终态 | 481843.339005258 | derived，包含最后未完成工作及终止清理，不能作为最终纯KSP timer |
| 最近221至228步均值 | 2136.747273452 | 每个不同iteration取第一次callback；35.612455分钟/步 |
| 排除225步后的对照均值 | 1950.761694319 | 225步包含前224步检查/checkpoint影响；不当作全部步数均值 |

最近完成步的原始step/callback见[近期iteration CSV](records/f2_recent_iterations_20261002.csv)。step是callback间wall差，包含前一步callback之后的监测/场检查/保存及本步工作，不是纯算子耗时。被杀后直接KSP内部总timer没有写出，保持unknown。

setup不再重复全面解析资源日志。既有[20个相邻stage区间与CPU/采样峰CSV](records/f2_setup_stages_20260928.csv)仍绑定同run的原事件；本次重新核对stages21条边界不变。主要**父区间**如下，独立子timer包含于父区间，不再次相加：

| 同场相邻边界或已有子项 | wall秒 | 数据身份与范围 |
|---|---:|---|
| mesh完成→volume metadata完成 | 0.339953 | measured父边界；mesh准备另为151.476955秒 |
| volume metadata→native/packed物理作用对象完成 | 8844.889649 | measured父区间；不能全部归为JIT或局部积分 |
| p6+p4 form编译 | 64.918579 | measured父区间 |
| forms完成→凝聚组件/端口/矩阵身份完成 | 2841.504761 | measured父区间；不把余差命名Python开销 |
| p4 symbolic | 79.626349 | measured单次symbolic marker区间 |
| p4预算marker→numeric完成 | 44111.673835 | measured完整包围区间，12.253243小时；不是独立numeric API timer |
| H6准备 | 120224.788820 | measured父区间，33.395775小时 |
| H6 diagonal | 118597.092899 | measured子项，32.943637小时 |
| H6 power10 | 1352.128188 | measured子项；20次mult包含1320.326423秒 |
| p6 / p4 build total | 463.355848 / 292.202399 | measured子项，均在凝聚父区间内 |
| p6 / p4 FFCx tensor核 | 292.124320 / 33.861449 | measured子项；每阶54 raw类、6实际tensor组、87定向Schur类 |
| p6 / p4内部LU与Schur | 12.275616 / 0.959826 | measured local_schur_seconds_max子项；恢复无独立timer |
| H6后桥接 / Aq投影QA / 同对象QA | 1127.286036 / 869.311902 / 5741.118165 | measured相邻父区间，后者含一次setup PC |

旧“44110秒LU”来自资源采样覆盖 `44110.416671 s`；完整marker区间是 `44111.673835 s`，本场只做一次numeric。精确API timer unknown。H6父区间已有worker CPU采样差18044.23 s、parent115503.09 s；[PSS已有观察](records/f2_pss_observation_20260926.json)发现扫描及worker等待，但没有关闭PSS对照。因此不能把33小时改写成“本来5小时”，也没有新的提速实测。

## 最近完整 PC 的两次粗修正

粗修正C将细层残差限制到p4，用已有因子求解、恢复并验算，再延拓到p6。该完整记录是sequence230，尚不代表外层第229步完成。只有两次C合计timer，传递、缩减、MatSolve、内部恢复、原A4体积/DtN验算、端口闭合分别没有timer，保持unknown。

| 项目 | 第一次logical459 | 第二次logical460 | 原记录与范围 |
|---|---:|---:|---|
| p4 ledger完整wall秒 | 1038.420879861 | 499.450108476 | 包含缩减/现有因子求解/恢复/原A4/闭合；不能全叫LU回代 |
| 原A4 rho轨迹 | 2.11292967032761e-10 → 3.30869694390692e-13 | 3.97049384964342e-11 | 非零内部FE RHS返回验证 |
| 额外精化次数 | 1 | 0 | 固定上限2，复用同一factor |
| 实际MatSolve次数 | 2 | 1 | 计数683→685→686；没有新增symbolic/numeric |
| 返回端口闭合相对量 | 4.40680122727382e-12 | 4.7746858217508e-12 | 累计状态独立H*a−D*c检查 |

两次C合计 **1607.683174034 s = 26.794720分钟**；两个ledger合计 **1537.870988337 s**，占C **95.657591%**；C减ledger的 **69.812185697 s** 是传递/日志/分配等未细分外围。主要成本确实在ledger内部，但现有记录不能判断因子求解、恢复或native A4验算谁主导。

两个A6动作合计 `222.840167550 s`，H6计时 `146.099033907 s`。这些组件和C相加 `1976.622375491 s` 只是已计时子项之和，不是完整PC wall；完整PC、外层Schur、正交化、原A6独立检查及输出单项timer仍unknown。较早PC两次C约22.86分钟是9月28日快照，本次26.79分钟另记，不用旧值冒充末次。

## 实际运行路径和内存对象

本场p6外层为独立trace加3904端口，共10803256行；p6 full storage35594790行、独立full派生35248752行。p4因子来自装配时直接形成的单元凝聚增广矩阵，4586288行、2070391064 stored NNZ；不是10608132行的full FE增广矩阵。54332 cells、每阶54 raw几何类→6 tensor组，87定向Schur/LU/recovery类；tensor仅按round12键分组，代表kernel坐标不舍入，Schur/LU/recovery仍raw float64 widths加orientation，不新增合并类型。

同run已有实际后端证据显示：PC内A6 curl与mass为分开的sum-factorized动作，未融合；独立原A6和原A4验算仍native；p6局部tensor仍FFCx积分核，非blocked Gram。H6 degree3、positive_sum后端、同mesh直接P6→P4与PH、最多两次同因子粗精化、FGMRES32/max2048等保持原合同。详细factory和ABI/对象载荷见[前次完整交接](f2_running_handoff_20260928.md)与本次compact的复核字段，不从其他run补填unknown。

主要常驻对象仍是p4稀疏矩阵与MUMPS因子、p6/p4局部LU/Schur/recovery、端口数据、Krylov与工作向量。后端allocated/used、数组载荷及预测只是各自口径，不能相加等于RSS。没有额外复制矩阵、因子、场或向量做内存分账；没有本场终态的精确逐字节账。OOM清场属于异常生命周期，不能宣称完成了正常KSP→factor释放→物理恢复的成功流程。

## 交接范围和待审问题

本次只提交报告、compact、选字段证据、CSV、内核/MPI稳定小摘录及相关文档索引；原run目录、历史失败和旧快照不覆盖。JSON/hash/CSV/链接与文档diff检查另记于response。source、输入、算法、CPU/NUMA、线程、资源线、watchdog与swap策略均未修改；没有新PDE、factor、算子配对、额外性能测试、signal、重启、pull/merge/rebase或master改动。

待审缺项是PID1172428所属任务及当时内存策略、触发受限分配的具体调用、最终KSP内部计时/退出reason、kill时独立原A6、MatSolve/恢复/验算各自耗时和全程PSS/资源采样覆盖复审。报告不把unknown补成通过，不承诺重启可免LU，不开始新PC或0.7 nm计算。本场为资源异常中断并且数值尚未资格化，不能据此证明2 nm方法永不收敛或整机2 TB必然不够。
