# Review V5 执行记录：R13_PAIR_RELEASE → F5 完成 → 5 nm setup-only 通过 → F2 fresh 准入待核

## 当前状态（2026-09-24）

5 nm F5 setup-only `20260924T092250.568977Z` 已自然结束：exit 0、`SETUP_ONLY_COMPLETED`、`setup_checks=PASS`；setup-only 为 `2023.440526 s`，完整 workflow 为 `2028.390414 s`。watchdog 整树 RSS 峰 `37236830208 B`，低于 `1300000000000 B` RSS Gate；6192 个样本全可读、最大间隔 `0.653519 s`、swap 0，`descendants_cleared=true`。详细身份、阶段、p6/p4 tensor 组和哈希见 [setup-only compact](outcomes/records/f5_setup_only_v5_compact_v1.json)。

正式 F5 的 setup 为 `11263.076 s`；本次setup-only约快 `5.57×`。本次在3780个cell上实际将p6和p4各175个raw几何类归为6个tensor组，分组kernel实测`292.039/33.847 s`；旧F5的`8571.805/988.356 s`是完整F5使用raw类时的kernel计时。源、分组策略与缓存状态不同，故这是setup与局部kernel的候选路径证据，不是完整求解加速或场等价证明。

主审已批准准备并在fresh prelaunch Gate全部通过时启动唯一F2：2 nm Si、p6/h1.5、q4、3904通道。F2仍须先确认干净source、完整输入/物理/通道身份、CPU24空闲与CPU9监督、MPI1/数学线程1、preferred node1可回落、旧树清场，以及有效可用内存不少于`1437438953472 B`；运行使用整树RSS-only `1300000000000 B`硬线、15秒只读observer且无时间截止。任一条件失败即不启动并报告。

**截至 2026-09-24。** R13 Q4/Q3 均以 source `6d989b4b9cbca12fcc35455d7ff381e66ef7ca6d` 完成；离线 checker source `515b0c653fc25bc1da2f319da9b7e658de049a2e` 的 attempt4 为 `NUMERICAL_PAIR_PASS`，结合共同路径、source-compact、连续 watchdog 与持续硬件证据记录 `R13_PAIR_RELEASE`。详见 [R13 release compact](outcomes/records/r13_pair_release_v1.json)。

性能差异主要落在 p6 凝聚 setup 的 raw tensor class 工作量：冻结源正式调用使用其 `rounded_12` 几何规则，当前已存 raw 几何按该规则派生为12组，而 V5 `raw_unrounded` 保留96组（8倍 distinct-kernel 工作单元；12是派生值，非源 run 实测）。Q4/Q3 p6 kernel 实测4721.61/4680.91 s，稳定；H1同工作量 node0/node1 与990-cell FE配对未见旧 node1 严重慢化，两次正式 observer 的 thermal-throttle 计数均为0。忙频 MSR/APerf/MPERF 仍 unknown；这不证明普遍硬件状态，也不授权改 raw identity policy。现有 A4/Aq 审计保留，额外成本按已记录操作范围描述，不做未测的精细拆账。

F5 正式场 `20260923T231207.264441Z` 已以 source `b468907cf54d04280b461cae5fc9078186302d54` 完成：121步，显式 A6 residual `8.60422e-7`，244/244 次 p4 返回通过 `1e-10`，checker 为 `BALANCED_OUTPUT_PASS`、旧5nm匹配比较为 `MATCHED_REFERENCE_PASS`；600通道及 R/T/A/体吸收 Gate 通过。整树 RSS 峰 `38,934,622,208 B`，swap0，watchdog `COMPLETED` 且清场。逐项身份、artifact hash及 Gate 指标见 [F5 compact](outcomes/records/f5_5nm_q4_terminal_compact_v1.json)。

F5 setup 实测 `11263.076 s`，其中 p6/p4 raw tensor kernel `8571.805/988.356 s`、Schur `29.46/2.23 s`。两者各175个 raw 几何类；按 `round(width,12)` 从已存几何派生为6组，但这只是类数推导，绝非时间提速或安全合并证明。H1/990-cell对照未见本次测试负载下旧 node1 严重慢化，observer throttle 计数为0；忙频 MSR/APerf/MPERF 仍 unknown。

### 105-cell 几何代表组件（不是 setup-only）

在源 `b468907cf54d04280b461cae5fc9078186302d54` 的未提交工作树上，使用原5 nm Si输入与物理身份、派生 `(5,3,7)` 即105-cell网格、`MPI.COMM_SELF`，从完整600-mode inventory中选4个真实零阶mode完成一次真实FE/MPC组件测试。每阶18个raw几何类合为9个tensor组；Schur/LU/recovery仍按raw float64宽度+orientation区分，MPC expansion仍逐cell。所有raw类逐一与组代表tensor对比，最大相对差 p4=`6.29475e-16`、p6=`4.34826e-16`；p6 condensed action差=`3.13911e-13`、独立原A6 residual/action差=`3.01989e-13`；原Aq体积/DtN投影差=`4.10e-15/1.08e-14`；原A4非零内部RHS返回rho raw/candidate=`2.38159e-11/1.65771e-11`。另有显式非零port RHS的增广矩阵解残差=`6.39e-14/8.56e-14`，这是独立检查，不是该RHS下的原A4恢复资格。

生产构建段计时 raw→candidate：p6 tensor `892.56→447.23 s`、p4 `43.45→21.26 s`；全raw类附加复算另耗p6 `1434.48 s`、p4 `64.51 s`。整项测试`1 passed/2986.99 s`。这里只能作为105-cell、四零阶mode的组件证据；不代表正式3780-cell setup、全600通道、资源资格或setup整体提速。逐文件hash、输入身份、命令、日志hash及边界见[compact](outcomes/records/v5_5nm_geometry_105_component_v1.json)。

与较早同5nm离散的698步结果对照：旧 solve/workflow=`206568.519/217665.164 s`，旧观测RSS峰=`50,161,172,480 B`；当前为121步、`10671.216/22680.912 s`、`38,934,622,208 B`。workflow墙钟约9.60倍，但旧CPU23与当前CPU24跨插槽，且source/runtime不同，不能把该比值全归因于算法提速；旧RSS记录有约8小时34分监督断档，不是连续资源PASS。旧run原记录不改写，当前 compact 只作对照。

setup-only之后尚未重新打开数值求解，因此本条不报告新的正式场结果。新F5 setup-only的`outer_solve`、`full_a6_recovery`、RTA和physical checker均为`NOT_RUN`；同对象setup QA中的p4逻辑调用不是outer迭代。旧F5完整数值/物理PASS保留其原run/source范围。Q4 attempt1序列化错误的负记录继续保留，见[compact](outcomes/records/v5_r13_q4_attempt1_failure_v1.json)。

## H0/H1

H0 只证明拓扑，不代表空闲或性能：在线逻辑 CPU 为 0–47，CPU48 不存在；CPU24 属 socket1/node1、sysfs `core_id=0`、SMT siblings=`24`；CPU9 属 socket0、sysfs `core_id=11`、siblings=`9`。正式启动前仍须实时复核 CPU24 邻占用及资源准入。

H1 是合成负载，不是 FE 结果。CPU23/node0 与 CPU24/node1 的 60 秒算术吞吐分别约 `7.287e9`、`7.329e9 updates/s`；两组相同固定工作量中位数分别为 `7.3555e9`、`7.3686e9 updates/s`。三对 STREAM-like 名义值中位数为 node0 `8.270720`、node1 `9.086460 GB/s`，逻辑流量指标不等于实测内存控制器带宽。无 APERF/MPERF/MSR 忙频证据；TSC 与 sysfs 频率不冒充忙频。原始记录见 [`v5_h0_h1_m_a_profile_checks_v1.json`](outcomes/records/v5_h0_h1_m_a_profile_checks_v1.json)。

## M/C 组件资格边界

- V5 q3/q4 使用同一 retained-condensed workflow，粗阶 `q`、直接 `(6,q)` levels、A6/H6 sum-factorized 路径和 owner-transfer opt-in；保留 D2 的精化 ledger、raw geometry 身份、释放顺序及独立原算子核验。迁移来源按 4bf2/cad282 的冻结 blob 逐文件登记，未整体覆盖目标文件。
- 已验证实际 990-cell Aq 投影：80 modes；q3/q4 的 volume 与 DtN 投影各自均低于 `1e-10`。另有 18-cell q3/q4 workflow setup、实际材料局部组件、H6/A6 小 FE 对照、真实 Floquet 保存—恢复—canonical 往返，以及 PORD64 小 fixture。合并的 13 项轻回归通过；这些结果不等同于完整 990-cell 长场、全 80 模态端到端结果或持续资源资格。各测试名称、范围、库与来源 blob 见 [`v5_m_c_and_four_input_contract_v1.json`](outcomes/records/v5_m_c_and_four_input_contract_v1.json)。
- 私有 ABI 激活显式使用 base `tmp/task39extra_v5_abi_restore_20260923/base` 和 PORD64 overlay `.../base/prefix/pord64-overlay`；旧 int32/普通 int64 激活入口未替换。库、petsc4py cfg、MPC 包及激活脚本 hash 在上述 compact 中。PORD64 小 fixture 为组件资格，不是正式大图通过。

## 历史：R13Q4 attempt1 的实现错误与原 replay 合同

输入固定为 [`v5_node1_13p5nm_p6h7p5_q4.dat`](../../input/task39extra_para_workstation_capacity/v5_node1_13p5nm_p6h7p5_q4.dat)，input SHA256=`f9e20874ed86e8697b307ca9d2539ec04be8dd77dc7211cc9e0be8dae30746b5`，physical SHA256=`255837330af27827d15ef43dfb01876187589a3b5e129f1d0882e24b955484c0`；冻结 V21 轴，990 cells、80 DtN modes、粗阶4。不得使用 h10 输入或短波输入。

父监督 CPU9；worker CPU24；MPI1、数学库线程1；`preferred_node1`，允许 node0/node1；PORD64 私有激活。实时启动准入要求 `effective_available_bytes >= 1437438953472`（1300000000000 B RSS Gate + 137438953472 B 本轮选定的启动余量），另核验当前 cgroup 和 CPU24 邻占用。运行期唯一自动资源停止为整个任务树 measured RSS 达到 `1300000000000 B`；1170000000000 B 为观察警戒值。没有时间截止；128 步只作进展观察，FGMRES restart32、zero retained start、max2048。swap、fault、预测值、温度、频率和吞吐均记录而不新增停止条件。

监督复用原 native parent/watchdog；另以 task-local 只读 `scripts/task39extra_event_observer.py`（SHA256=`aeded7a3f3447a186d223aec61502d0b54e60e8f1bf83d68b2cb28ac9c0f9757`）在 CPU9 每15秒读取该 run 与固定 root/worker PID+start_ticks，并将可读的 CPU24 hwmon/thermal-zone 温度、thermal-throttle 计数、`scaling_cur_freq`/`cpuinfo_cur_freq` 旁证写入 observer JSONL。helper 使用 `/home/fenics/Projects/Maxwell3D-Lab/task-control/codex-thread-notify-v2.py`。忙频保持 unknown（除非另有获准的 APERF/MPERF 证据）；缺失传感器不失败、不停止、不杀进程。观察器没有信号或重启能力，RSS 硬 Gate 仍由既有 watchdog 实施。observer 自测已覆盖 PID/tick 绑定、缺项仅记录和忙频不推断。

该启动合同对应已完成的 R13Q4 replay，不能覆盖 attempt1 的原始负记录。当前 R13 pair、F5完整场与5 nm setup-only均已完成；F2按主审决定已批准有条件执行，仍须fresh prelaunch Gate全通过。


## 2026-09-28 运行中证据交接（仅文档提交推送，非最终收口）

截至2026-09-28T02:34:15.838437+00:00（UTC+8 2026-09-28T10:34:15.838437+08:00），F2 run `20260924T104936.107285Z` / 数值source `64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa` 为RUNNING，最后完成64步，最新独立原A6 residual=0.022358747111508717，尚未过最终资格。最新PC sequence65含setup一次，actual outer PC64；logical131已通过1次精化后返回，未据此冒充外层65完成。

总workflow/setup/实时KSP阶段分别315878.685780/184388.380644/131490.305148 s，最终KSP内部累计timer尚未写。当前/既有前缀峰RSS=1151172259840/1154356473856 B，task swap0、global pswpout增量229页仅机器诊断；watchdog固定RSS硬线1.3e12 B、无截止未改变。完整marker numeric44111.673835 s与44110.416671 s采样覆盖有区别；两次C的主要时间落在p4 ledger，MatSolve/恢复/native A4验算未分项计时，不称全部LU回代，也不保证H6关闭PSS后只需5小时。

本次按用户授权仅核验现有运行身份、读取已有日志和轻量证据，新增[运行中outcome](outcomes/f2_running_handoff_20260928.md)、[compact](outcomes/records/f2_running_handoff_20260928_compact_v1.json)及相应小型CSV/选字段日志摘录，更新summary；保留原失败与旧snapshot。未改任何求解代码、task/review、默认配置、运行参数、绑定、资源或swap/watchdog策略，未发信号、重启或启动额外计算。本次新commit只含这些文档，在隔离sparse detached worktree基于运行SHA提交并向执行分支推送；canonical执行worktree HEAD/clean不变，避免终态source gate因文档提交误拒。正常快进push携带既有3个批准提交，运行SHA不变。远端提交完成身份以主控最终回读HEAD为准，报告数值只对应上述冻结快照。


## 2026年10月2日 F2 内核 OOM 终态证据交接

按用户“把这些记录写成报告推送到远程”的授权，追加[终态报告](outcomes/f2_terminal_oom_20261002.md)、[compact](outcomes/records/f2_terminal_oom_20261002_compact_v1.json)、[选字段证据](outcomes/records/f2_terminal_oom_20261002_evidence_v1.json)、完整已有A6检查CSV与近期完成步CSV，以及内核/MPI小摘录；summary和运行索引记录本场异常终态，历史RUNNING与旧失败原文保留。

冻结时间 `2026-10-02T04:49:18.771814+00:00` UTC / `2026-10-02T12:49:18.771814+08:00` UTC+8。F2 `20260924T104936.107285Z` / source `64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa` 为 `WORKER_FAILED / exit137`，后代清场。内核确认node1 `CONSTRAINT_MEMORY_POLICY` OOM，victim341839；触发分配PID1172428的所属任务和实际策略unknown。任务RSS峰 `1154381864960` B未达1.3e12 B；任务swap峰 `8574500864` B，全机pswp从0/0到3138800/5146004页独立记账。

最后外层完成228步，Schur `9.373049823814199e-05`；最近独立原A6第224步 `9.758316562442362e-05`，未过1e-6，NOT_QUALIFIED_INTERRUPTED，无正式RTA/checker。第224步full/retained解manifest与文件存在/尺寸已核对，没有重读或重hash大型数组。完整workflow/setup/末次callback solve为 `666232.838509/184388.380644/479635.727603 s`；最终纯KSP内部timer unknown。最后PC sequence230含setup一次及outer229次，不称外层229/230步已完成；两次C `1607.683174 s`，ledger `1537.870988 s`，MatSolve/恢复/native A4分项仍unknown。

本次没有源码、参数、CPU/NUMA、线程、资源、watchdog或swap策略改动，没有新计算、重启或master合并。文档提交在已有canonical detached文档worktree上，基线为 `ccd357885f7f9be84efe3be07868cc94f13d93fc`，向同一远端执行分支正常追加；运行工作树HEAD/clean保持64ca6048。远端最终SHA由提交后回读给出，不在文件内自引用伪造运行源码。

文档提交 `3f63f551d9456f10e833de998c54510c97683905` 已正常推送并回读远端HEAD一致。本地11项轻量检查通过：固定source/input/physical身份、小文件与摘录hash、CSV行号/字节范围/重复callback、时间与平均值、checkpoint元数据/尺寸、历史记录保留、Markdown表格/链接及staged diff；未运行FEM、factor、pytest或性能测试，详见[校验记录](outcomes/records/f2_terminal_oom_20261002_validation_v1.json)。新CSV仅规范LF行尾，内核摘录只去行尾空白且保存转换说明与原摘录hash，原日志保持不变。

自动审批拒绝将报告上传到独立Markdown API，未重试或另行上传。改为只读检查已授权仓库的已推送版本，5份Markdown的176张表格通过GitHub实际渲染核对，详见[渲染记录](outcomes/records/f2_terminal_oom_20261002_github_render_v1.json)。本段及回执为文档校验补记，后续remote HEAD仍不作为运行source SHA。
