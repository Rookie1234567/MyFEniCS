# Task041 Response V12：Review V10-r2现场进度

**状态：进行中。** 本轮基于执行分支HEAD `899b0acbd9fda3bc55f9bc1d7cd7fe0774ef0b50`完成一次W5离线候选产物比较、复核PETSc薄桥serial/MPI2小矩阵测试attempt与账目，并封存本机MUMPS 5.6.2原文说明；没有新增求解、QEP或FE。W0.7运行的数学源码仍为`5025fdd31a1edc4ce34a8df3150a12ca90009c01`，V10-r2同步review为`174ad73a78dcb8a584ea9739007ddbd1e2ef39cc`。保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`保留，旧raw不改。

## 本轮唯一W0.7运行：受控内存停止

| 项目 | 已核事实 | 状态边界 |
|---|---|---|
| 身份 | Invocation `10d761079d90473dadce79d3f7eb6457`；unit `task041-v9-w0p7-matched-cell-p6-fixed-h6-warm-sorted-map10-11-12-14-15-16-17-18-20261007T174630Z.service`；MPI8 CPU `[10,11,12,14,15,16,17,18]`；复用已验证producer packet，本次QEP运行数为0 | 单次warm consumer；不改写早先cold失败或其wall |
| 终止 | service reason=`absolute_memory_limit`，分类`controlled_stop`；public return code `-15`，finalizer terminal exit 3 | 数值失败不是已证明结论；资源门先终止 |
| 资源 | process-tree RSS峰`53,541,888,000 B`，比`53,221,163,008 B` cap高`320,724,992 B`；专属job-cgroup峰`51,229,249,536 B`，是另一口径；PSS/USS峰`43,305,919,488/42,881,789,952 B` | cap/warning/reserve仍为`53,221,163,008/47,899,046,707/412,316,860,416 B`；swap仅观察，job swap为0 |
| 服务收尾 | finalizer `status=completed`、`result_classification=controlled_stop`，常规检查7/10；false项为`pre_exit_members_clean`、`public_result_completed`、`service_terminal_normal` | finalizer流程已完成不等于service正常完成；本次仍是受控停止 |
| 工作量/计费 | 唯一public-to-finalizer wall`2,350.819163285 s`；V5 ledger 160项，此Invocation恰一条 | 不把public phase、consumer内部marker或rank时间重复收费 |

外层runroot的`markers.jsonl`只有public command开始/结束记录，不能据此说setup没有执行。consumer自己的`markers.jsonl`共44条内部事件，284,367 B，SHA256=`b1f338ca12f9abf8c6fd5f8e9e03112086b29c4d2007a8f73e18074989121996`。实际已到达：one-cell因子ready `702.915 s`；底侧P4因子/woodbury ready `2262.027/2262.070 s`；顶侧full action ready `2279.519 s`；顶侧P4凝聚trace/port ready `2317.396/2329.365 s`。固定H6反馈门和outer迭代均未到达，五项真实残差、recovery与physics门未评估。

底侧P4矩阵为`64,966×64,966`、`27,929,686`个非零项；marker同时给出active trace `64,320`、interior `77,760`、port `646`。底侧因子创建数1、solve数0，ready时因子仍live。顶侧已形成的P4矩阵为相同维度、`39,242,250`个非零项；这证明矩阵形成，不证明顶侧因子完成。逐因子字节数、MUMPS fill/INFO统计及精确numeric完成点均为unknown。根级`factor_inventory.json`中的`not_run`占位不能覆盖consumer内部真实ready marker，也不能据此声称因子字节已测。

`p4_condensed_port_ready`之后，源码立即构造顶侧`ResearchExactFactorInverse`。该构造器调用`ksp.setUp()`，其中包含LU symbolic与numeric设置；本路径的factor lifecycle callback只把事件加入局部列表，没有转发到consumer marker。因此可把超cap峰定位在顶侧P4因子构造区间，不能从末marker断定峰对应symbolic还是numeric，更不能称顶侧factor ready。接近最后内部marker的consumer采样（elapsed `2329.231 s`）为tree RSS`46,439,280,640 B`、job-cgroup current`44,137,930,752 B`；接近停止前的外层样本（`2347.906 s`）为`52,890,804,224/50,623,971,328 B`。两者是全consumer进程树与cgroup样本，不能把其增量全部归因于该因子。

## 当前阻塞和下一步

顶侧P4输入矩阵规模已知，但factor fill、symbolic估计和下一步numeric新增字节未知。最后内部marker附近cap余量约`6,781,882,368 B`，而停止前最近常规样本余量约`330,358,784 B`，最终tree采样超过cap。当前没有可审的`Delta_next`与工作区余量，不能原样再次跨入该因子numeric阶段。先从现有符号分析调用链和已安装PETSc接口找可在numeric前停下的最薄方法；在获得因子估计或有界分配计划前不启动下一场。W2仍按V10真实对象阶段推进，不用该pilot的RSS代替W2容量资格。

匹配轴向步长控制已有serial与MPI2证据：serial attempt父wall`237.46574084204622 s`；后续MPI2 attempt两rank各`1 passed`、父wall`189.02536411304027 s`，test源SHA为`a718ee1af1ebfb6f4527b84d7928219faf24fa4c10b1a3954f17ef04cecdf731`。serial报告当时的“MPI2 not_run”只描述其冻结时点，后续MPI2结果独立补充，不改写serial raw。该证据仍限于均匀W正入射控制，不是光栅pilot资格。

该matched-h结果只支持均匀W、正入射、常切向场下同轴向离散的拼接方向，不资格化光栅QEP模态或本pilot物理解。当前pilot尚未到反馈/outer/五残差/recovery/physics；0.7 nm完整目标、2 TB容量和48 h冷启动目标都未达成。更细内部marker、内存阶段与文件SHA见[本轮实测进度](outcomes/shortwave_measured_progress_v10.md)和[hash-bound record](outcomes/records/task041_v10_controlled_stop_20261007.json)。

## 2026-10-08：W5离线候选比较与PETSc薄桥测试

### W5产物比较：身份通过，外部通道数值门失败

对照器把两个输入都作为candidate；“explicit-Schur reference”只是右侧产物的显示角色，不是exact-side真值。它读取并比较旧reference（consumer summary SHA `bd8cf3d9696c17a54c64239334acab90de3e9dc1cae383c4b9fe537991eb332d`）与fixed-H6 candidate（SHA `4257b309c5381498c6a84110d5c49e86eb0e3ca78272b09b7bb6ee731dd18526`），共调用一次。两者W 5 nm、p6/h4、M480、MPI8、cell-condensed，input SHA相同为`a788489e9d3d582d2abbdf21b3edd535a35c9649c6d5cf7dd53952f30594c5dc`，resolved SHA为`278d5813aa0227d3a8ddcfb2759b197436e9f0e74fef82b7c7b01c00ce1421eb`。18项产物身份检查与两侧public input envelope均通过。

| 比较门 | 实测 | 结果 |
|---|---:|---|
| R/T/A/A_volume差值（candidate−reference） | `+3.543842996833746e-11 / −2.6720737168056674e-13 / −3.5171199286310184e-11 / +1.7145174169286292e-12`；各限值`1e-8` | 4项通过 |
| 选定E/H场 | relative L2=`5.688326111234493e-10 / 5.742838138430747e-10`；限值`1e-6` | 两项通过；五个z平面值是诊断项 |
| 四角色canonical数据 | bottom active/full=`1.7128976856531144e-8 / 1.6977718026171218e-8`；top active/full=`1.1038152408073086e-10 / 1.102299390456392e-10`；限值`1e-5` | 4角色通过；两侧key/shape/order一致 |
| 外部600通道 | keys精确一致；26个显著通道中唯一失败项`["bottom",-15,0,"s"]`的幅度/功率相对差为`1.0880143757234042e-6 / 2.074050200051092e-6`，门限`1e-6` | 其余25个显著项通过；该项超门，故外部门失败并导致`numeric_gate_fail`与`full_comparison=false` |
| 法向通量 | relative L2=`1.7488283863630695e-11`；限值`1e-4` | 通过 |

本次full结果是**comparison gate失败**，不是把此前W5 public/service自身的RTA、五残差或physics通过改写为失败；也不代表精确端点或所有通道均失败。失败行完整记录candidate/reference复幅值分别为`1.2722851397777249e-5+i1.8844696398659447e-5`与`1.2722870794837975e-5+i1.884471175312024e-5`；幅度差的分母为`2.2737515306654094e-5`、绝对差`2.4738743521870602e-11`，功率为`2.241901911321927e-8`与`2.2419065611486787e-8`、分母`2.2419065611486787e-8`、绝对差`4.6498267516462735e-14`。参考功率高于显著性floor`1e-8`，所以绝对差很小也不能豁免原相对门`1e-6`。细节见[失败行派生记录](../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_significant_external_failure_record.json) SHA `9fe88ab05dfb1b448935e127103a3d871b5d07f4626133ef23943f51ebf7cb3a`。未做raw-Q跨场逐向量比较（`not_run_not_defined`），资源与workflow可比性均`inconclusive`，integrated full-3D checker及solver/FE均`not_run`。两run共64个canonical shards、合计`1,313,610,614 B`；对照调用wall `533.9173726618756 s`，wrapper父wall `534.6402724480722 s`，Python单进程`ru_maxrss=5,691,043,840 B`。RSS是单进程口径，不是process-tree/cgroup峰；本比较`performance_not_isolated`且不计FE账。此前一次比较调用因候选method不属于注册route而被拒，checker/wrapper wall分别`122.18274498195387/122.91199241997674 s`，数值项未评估；其raw继续保留。原compact SHA `c088bd14872e924d990cdb4e1eed94af96c3f9bbf477cbc376389815ae96a032`原样封存；符号更正后的[compact](../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_offline_comparison_compact_corrected.json) SHA `f9505f6b92cc14cec3da9b863f21cb6bbbaacf98393db9eed56ad56c94b70f63`及[更正回执](../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_compact_correction_receipt.json) SHA `21320f82533a74bcfb066e9d207a24b2189759a289122dd9a176a505a03e724e`给出原字段到派生值的链。原derived JSON SHA `b65537515682987ea7e5eac15e655cf231af885eb66ea9170dbb4669231e9fcc`；两run输入未修改。

### PETSc LU阶段桥：tiny API证据与V5补账

桥测试只用8×8复矩阵证明MUMPS symbolic与numeric调用可以分开、factor/source矩阵所有权及清理顺序可观测，并以原矩阵残差校验显式numeric示例；不预测大型因子内存。三次真实pytest attempt（含一次失败）父wall分别为`1.0088105599861592 s`（serial失败：测试尝试allgather不可pickle的PETSc Mat，第二项被`-x`跳过）、`1.0088530050124973 s`（serial两项通过）、`1.0087709960062057 s`（MPI2每rank两项通过）。V5从162项增至165项，新增`3.026434561004862 s`；账本SHA `b983f17697a2b17e9fd6d7ef2141a3945a9b86689d2f6b048e36a51aa947711e`。MPI2结果绑定桥C SHA `7b365663b6e4278dc0a089671bf144e566efa9f9674ab66d4ca5ad864e42af9e`和test SHA `2aea4200bf7db9b0382ba9c2392738964154cd3afead045d578b37e77a9f012f`；serial初次失败绑定旧test SHA `e415c6f42ccdfa4e730ed1725138b0a6fbafe7490f145df2db0f9fc687f226d1`。失败raw保留且未改写。桥结果只表明小矩阵接口证明通过，不等于大P4因子的symbolic预算。

本机安装包为MUMPS `5.6.2-2.1build2`。对应Ubuntu源归档及其内含手册副本见[ignored reference目录](../../results/task041_petsc_lu_stage_bridge_retry_20261008T000705Z/mumps_5.6.2_reference/)；原tar SHA `13a2c1aff2bd1aa92fe84b7b35d88f43434019963ca09ef7e8c90821a8f1d59a`，PDF SHA `32acdd3e09fb69f9fab16c94ae67768d15c61ac9c27abf66eb1e0e6ecd904050`，derived source record SHA `9f2e93cf0e31410715db2d912bfef7f876ad9d050845c1fd1621c037720a4af1`。手册p93–94/p97–99说明：`INFO(15)`是考虑当前`ICNTL(14)`的本rank in-core工作区估计（million bytes），`INFOG(16/17)`分别为rank最大/总和；`INFOG(17)`已是总和，不能再跨rank累加。`INFO(3)`是本rank因子复数entries，负数按绝对值乘1e6解码；`INFO(4)`为本rank整数entries，但手册未给其负数编码，不套用全局字段语义。`INFOG(3)`是全rank因子复数entries、`INFOG(4)`是全rank因子整数entries；其负数分别按绝对值乘1e6解码为entries。`INFOG(18/19)`是numeric后实际已分配内部数据的rank最大/总和，不是analysis阶段估计。所有这些内存估计都不是RSS保证上界。此前raw里的INFO未知字段仍原样保留，不据这份说明倒填；本轮未运行矩阵。
