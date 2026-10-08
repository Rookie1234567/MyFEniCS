# Review V10-r2：W0.7现场证据

## 2026-10-08 最新Invocation：numeric前预算拒绝

唯一warm run为Invocation `3d6b63c763414ad984beb60f1296458e`，unit `task041-v10r2-w0p7-deferred-amd-warm-20261008T082944Z.service`，runtime source `819ed980502783f4a11b8ea2c690dc8add44e81a`。它复用已完成producer packet，本次QEP调用为0。数值条件为W0.7缩减`10×5 nm`、接口`2/22 nm`、p6/h0.70/M400/MPI8、全段L20/N29/h20/29、fixed-H6，P4 target `5e-13`/最多2次同因子修正；CPU为`[10,11,12,14,15,16,17,18]`，每rank一个数学线程。

| 因子阶段 | 实测矩阵/分析 | 生命周期结论 |
|---|---|---|
| one-cell | source matrix `15120×15120`；8 rank的local NNZ一次求和`7,123,680`；`INFOG(7/32)=4/1`，公开控制回读为null | 顺序PORD，numeric已完成，随后destroy；marker `rows=17,280`是端口/输出行数，`interior_rows=15,120`，不能混为factor source rows |
| bottom P4 | `64966×64966`、NNZ `27,929,686`；AMD；`INFOG(16/17)=2766/19460` million bytes | symbolic完成；numeric调用0；pending句柄清理destroy一次、error=0 |
| top P4 | `64966×64966`、NNZ `39,242,250`；AMD；`INFOG(16/17)=4193/19299` million bytes | symbolic完成；numeric调用0；pending句柄清理destroy一次、error=0 |

bottom numeric门读取当次fresh `B=35,915,554,816 B`，加单份全rank `INFOG(17)=19,460,000,000 B`和政策余量`W=5,322,116,301 B`，预测筛查值`60,697,671,117 B`，高于cap `53,221,163,008 B` `7,476,508,109 B`。它是numeric前预算拒绝，不是测得完整factor峰值或数值算法失败证明。INFOG(17)按MUMPS 5.6.2定义取全rank sum的一份；`W`是固定政策预留，不是对误差或RSS的数学上界。

原始分类保持：consumer `IMPLEMENTATION_FAILURE`；public `task041_public_command_nonzero`、rc 3；service parent `pre_exit_failed`；finalizer `failed/service_boundary_failure`且`controlled_stop.active=false`。Finalizer 8/10；仅`public_result_completed`和`service_terminal_normal`为false，其余清理/账目检查通过。唯一public-to-finalizer wall `2395.81151869 s`，175项V5 ledger中本Invocation恰一次，ledger SHA `962d31d906d22ec39d6a0e534021caa5fbcc8d1f521a966f245129d6768985ba`。tree RSS峰`35,915,563,008 B`，dedicated cgroup峰`33,178,259,456 B`，不是预算预测值；performance为`performance_not_isolated`。outer、五残差、recovery及physics均未到达。原始摘要及所有阶段SHA见[compact](../../../results/task041_v10r2_w0p7_deferred_amd_warm_run_20261008T082944Z/terminal_compact.json)。

## 历史：2026-10-07 首次warm consumer受控停止

本节以下保留Invocation `10d761079d90473dadce79d3f7eb6457`的独立旧结果。该run确实是`controlled_stop/absolute_memory_limit`；不得与2026-10-08的`IMPLEMENTATION_FAILURE/service_boundary_failure`合并或互相改写。

## 2026-10-08 更新：deferred-AMD组件通过，warm consumer尚待fresh准入

原下文记录的Invocation `10d761079d90473dadce79d3f7eb6457`仍为`controlled_stop/absolute_memory_limit`，tree峰超过冻结cap；反馈门、outer、五项真实残差、recovery与physics未到达。以下新组件证据不改写该结果，也没有启动第二场。

已提交并推送代码提交`6caf43ebd52b14bf0c9423b33353e7fc8f38f27f`。PETSc 3.19.6/MUMPS 5.6.2的W0.7 deferred P4路径现在把JOB_NULL缓存请求、source-derived控制输入和symbolic后实测控制分开。仅注册W0.7路径要求MPI>1/MPIAIJ并检查factor options冲突；symbolic后实际读取ICNTL7=0、ICNTL28=1、ICNTL14=40及INFOG7=0、INFOG32=1。普通KSP/default路径与one-cell既有排序保持不变。

当前预算在同一生命周期内按阶段核算：symbolic使用`fresh B + Δ + W <= cap`；numeric使用`fresh_numeric_B + one INFOG(17) × 1,000,000 + W <= cap`。INFOG(17)是rank总和，取单份，不再乘MPI size。`W=5,322,116,301 B`只作为政策预留，不是内存估计误差界。bottom/top预测Δ分别为`1,382,983,004/1,925,986,076 B`，根据已绑定的源码计数模型；它们不是实际RSS增量保证。bottom与top的矩阵、端口和pending factor均计入fresh `B`，numeric在同一factor句柄上先bottom后top。

serial两selector 2 passed，父wall`3.040390633046627 s`；MPI2三个selector每rank各3 passed，父wall`2.0312472369987518 s`。两条pytest唯一合计`5.071637870045379 s`计入V5；ledger 174项SHA `531d777d369c8d84e58120ec79eabb638dd7fb8e4c03b2fdac3a33f5290515d2`。MPI2 tiny中三个symbolic阶段的`MatLUFactorNum`增量为0、正例numeric为1；残差与清理通过。它们只证明8×8桥和预算控制合同，不证明W0.7大factor可支付。

ignored warm准备目录为`results/task041_w0p7_deferred_amd_warm_preparation_20261008T082944Z/`。该包仍需先保存原字节，再重绑代码与后续文档提交后的clean HEAD、源码、精确`.so`、既有producer packet及argv；之后才做fresh unit/资源门与MPI8 native ABI。当前没有fresh production MPI8 ABI、dispatch或本轮FE；不存在可声称运行中的新Invocation。cap/warning/floor维持`53,221,163,008/47,899,046,707/412,316,860,416 B`，swap observe-only，W2不执行。完整小测试attempt与SHA见[Test summary](test_summary.md)，提交和资格边界见[Response V12](../response_v12.md)。

**分类：`controlled_stop / absolute_memory_limit`。** 这是一个真实MPI8 consumer已经深入setup、在顶侧P4因子构造阶段越过process-tree cap后受控终止的记录；不是“setup未到达”，也不是数值残差失败。它尚未运行fixed-H6反馈门、outer solve、五项残差、recovery或physics。

## 身份、结果与服务终态

| 字段 | 实际值 |
|---|---|
| Review / branch | V10-r2；`codex/20260902-task41-mpi1-shortwave-hybrid-capacity` |
| 文档同步HEAD | `174ad73a78dcb8a584ea9739007ddbd1e2ef39cc`；运行数学source `5025fdd31a1edc4ce34a8df3150a12ca90009c01` |
| Invocation / unit | `10d761079d90473dadce79d3f7eb6457` / `task041-v9-w0p7-matched-cell-p6-fixed-h6-warm-sorted-map10-11-12-14-15-16-17-18-20261007T174630Z.service` |
| 数值输入 | W0.7 reduced `10×5 nm`、`z=-2..26 nm`、Hybrid接口`2/22 nm`、p6/h0.70/M400/MPI8；fixed-H6，matched local/global `h=20/29 nm`、`L=20 nm/N=29`；复用已有packet，本Invocation QEP=0 |
| CPU与线程 | MPI8×1，rank CPU `[10,11,12,14,15,16,17,18]`，node0；六个线程环境变量为1（含BLIS） |
| 终止/计费 | `absolute_memory_limit`，service finalizer=`controlled_stop`；唯一public-to-finalizer wall`2350.819163285 s`，V5 ledger 160项且本Invocation一项 |
| finalizer | 普通检查7/10；false=`pre_exit_members_clean`、`public_result_completed`、`service_terminal_normal`；controlled-stop绑定与清场/RSS下降检查通过 |

该研究运行仍`performance_not_isolated`。同宿主Task039计算未被干预。旧cold失败与此次warm受控停止分别保留，不拼成一次cold成功。

## 外层监督记录与consumer内部进度必须分开

外层service runroot为`results/task041_w0p7_matched_cell_warm_consumer_run_map10_11_12_14_15_16_17_18_20261007T174630Z`。其`markers.jsonl`只有public command开始/结束记录，SHA256为`7f2e6e335b2b9a91c6c0ba97f0fb2cf0a7262522c1a1486be5ea5d75ffd19378`。consumer内部结果在该运行绑定的真实W0.7 result tree：

`results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261007T180353.062546Z/consumer/markers.jsonl`

此文件284,367 B、44条内部阶段事件、SHA256=`b1f338ca12f9abf8c6fd5f8e9e03112086b29c4d2007a8f73e18074989121996`。内部阶段顺序如下；时间是consumer marker的elapsed wall，不与service完整wall重复累加：

| 内部阶段 | elapsed s | 事实 |
|---|---:|---|
| `one_cell_factor_ready` | 702.914996 | one-cell exact factor已ready |
| `one_cell_factor_destroyed` | 973.611411 | 该临时factor已销毁 |
| `system_ready` | 1804.320732 | coupling侧setup完成，随后进入bottom side |
| bottom `full_action_ready` | 1869.288052 | bottom full action已生成 |
| bottom `p4_condensed_trace_ready` / `p4_condensed_port_ready` | 1943.747304 / 1946.384603 | bottom P4矩阵与port项已形成 |
| `bottom_factor_ready` / `bottom_woodbury_ready` | 2262.026595 / 2262.069679 | bottom factor已ready并仍驻留；bottom Woodbury action已就绪 |
| top `full_action_ready` | 2279.518989 | top full action已生成 |
| top `p4_condensed_trace_ready` / `p4_condensed_port_ready` | 2317.395731 / 2329.365189 | top P4矩阵与port项已形成；之后进入顶侧factor构造 |

因此，service报告`controlled_stop`与“已完成多项setup”并不矛盾。feedback gate和outer尚未开始；所有正式数值及physics门均为`not_reached/not_evaluated`，不是通过，也不是失败值。

## 因子矩阵、驻留样本和下一项预算

| 对象 | 已有实测结构 | lifecycle/资源未知 |
|---|---|---|
| bottom cell-condensed P4 matrix/factor | matrix `64,966×64,966`，NNZ `27,929,686`；active trace `64,320`、interior `77,760`、port `646`；factor created=1、solve=0、live=true | factor bytes/fill未持久化；不从NNZ按比例估算 |
| top cell-condensed P4 matrix | matrix `64,966×64,966`，NNZ `39,242,250`；trace/port marker存在 | 矩阵已形成；factor-ready事件未出现；top factor bytes/fill/symbolic估计未知 |
| one-cell exact factor | factor-ready `702.914996 s`；destroyed `973.611411 s` | 独立factor字节数未知；已在bottom/top侧factor前释放 |

consumer内部sample在顶侧最后marker附近（elapsed `2329.231413 s`）为process-tree RSS=`46,439,280,640 B`、dedicated cgroup current=`44,137,930,752 B`；当时相对tree cap还余`6,781,882,368 B`。停止前最近普通sample（`2347.906314 s`）为tree RSS=`52,890,804,224 B`、cgroup current/peak=`50,623,971,328/50,624,233,472 B`，tree cap余量只剩`330,358,784 B`。supervisor所记完整run tree peak为`53,541,888,000 B`，超cap`320,724,992 B`；dedicated cgroup历史peak=`51,229,249,536 B`。RSS/cgroup及其各自采样时刻分列，不能把全过程树RSS增量全归于顶侧factor。

源码`src/solvers/physical_balanced_physical_operator.py::_build_p4_condensed_from_physical`在`p4_condensed_port_ready`后立即调用`ResearchExactFactorInverse`。该构造器在`src/solvers/hybrid_local_dtn_woodbury.py`执行`ksp.setUp()`，普通PCLU setup含symbolic与numeric；当前P4 builder的内部factor lifecycle callback只追加到本地`events`列表，没有向consumer marker转发。于是峰只能定位到顶侧factor构造区间，不能精确确定已到symbolic或numeric哪一步，也不能称top factor完成。根级`factor_inventory.json`的`{"status":"not_run"}`是旧/空占位；consumer的真实`bottom_factor_ready`及top matrix marker保留为更具体证据。

下一项若要安全测量，必须先取得top P4 factor的symbolic/工作区估计或可审的受控分配计划。顶侧矩阵已有NNZ，但`Delta_next`、pivot/workspace margin和可释放的并存对象仍未知；因此下一numeric分配目前没有可证明预算。不要重跑同一路径探下一次cap，也不应把全tree峰减某个对象字节臆造为factor占用。运行峰和停前样本足以确认当前精确cap被触发；未得到MUMPS fill/RINFOG等原始因子统计。

## workflow、ledger与绑定证据

| 文件 | SHA256 |
|---|---|
| `summary.json` | `b3bcec419161df8088756ee764ae72397680404438c743724fcdc4e4f8d50e08` |
| `service_parent_summary.json` | `b81db090e4ea6831a449362602cdde26a581b0e5d6324fc01d42c695e0f01a1a` |
| `finalizer/finalizer_summary.json` | `669e3ee0349725ec1ef1057c253b8c6b2195b29df43070abccf619c5304bdbc6` |
| `finalizer/artifact_hashes.json` | `822dec2079590117f9e4fae384666c3e688c16bef2351c6a47f11dd433b8af82` |
| outer `memory_stages.jsonl` | `592de00a7d693770fe095d231f3ff995440e73f3ee6ed1abf4b9903d110b201d` |
| consumer inner `memory_stages.jsonl` | `1519477ff8d8f31f246295c0505a3e0dbacc7ec5d22ba2aa7493727018056fb7` |
| consumer internal `markers.jsonl` | `b1f338ca12f9abf8c6fd5f8e9e03112086b29c4d2007a8f73e18074989121996` |
| V5 ledger（160 entries） | `a7022ccc177cf604dea1e0bff4bcd96735e2e82aded33645016455163927abd4` |
| compact record（仓库） | [`task041_v10_controlled_stop_20261007.json`](records/task041_v10_controlled_stop_20261007.json) |

## 后续只读/小阶段

匹配轴向步长的真实FE控制selector已有serial和MPI2 raw：serial父wall`237.46574084204622 s`；后续MPI2两rank各`1 passed`，父wall`189.02536411304027 s`。MPI2 test源SHA `a718ee1af1ebfb6f4527b84d7928219faf24fa4c10b1a3954f17ef04cecdf731`，stdout SHA `7b08cbbd15b2214be8c2f448fafaf080fbf682cbfc08fc584cef973fb00deaed`，attempt SHA `9e031df580d64100a101dedb26f312cad5b390dc171348635ca0fc510bc21d97`，compact SHA `7cffe5c742f14c91001d6175ffa3f37d67e35615f8ac0828b21b6ced6f7c8c1e`见[MPI2结果](../../../results/task037c_matched_h_stitch_control_mpi2_20261007T232353Z/mpi2_test_compact.json)。串行attempt仍绑定其当时SHA/wall；其旧skip逻辑不代表后续MPI2 skip。该控制只覆盖均匀W正入射，不是光栅pilot资格。另从公开PETSc C API与当前native headers定位可执行symbolic-only最薄桥；不得把生产`ksp.setUp()`当symbolic-only或用大矩阵numeric试探。W0.7下一场和W2 numeric均不在本阶段启动。

## 2026-10-08：PETSc桥attempt收口、W5离线比较与MUMPS 5.6.2来源

### PETSc LU薄桥pytest父wall补账

检查桥目录的`pytest.attempt.started.json`、`pytest.attempt.json`、argv、stdout/stderr和清场字段，确认有三次实际启动，且这些ID此前不在V5 ledger。第一次serial attempt rc1，失败点是测试试图让mpi4py pickle PETSc Mat；`-x`后第二selector未执行。修正后的serial两项通过；MPI2两rank各两项通过。桥C SHA为`7b365663b6e4278dc0a089671bf144e566efa9f9674ab66d4ca5ad864e42af9e`，最终测试SHA `2aea4200bf7db9b0382ba9c2392738964154cd3afead045d578b37e77a9f012f`；首次失败绑定当时test SHA `e415c6f42ccdfa4e730ed1725138b0a6fbafe7490f145df2db0f9fc687f226d1`。

| attempt ID | rc/结果 | 唯一父wall |
|---|---|---:|
| `task041_petsc_lu_stage_bridge_20261008T000055Z:serial:pytest` | 1；首个symbolic-only节点测试收集时失败，原因是PETSc Mat不可pickle；第二selector未运行 | `1.0088105599861592 s` |
| `task041_petsc_lu_stage_bridge_retry_20261008T000705Z:serial:pytest` | 0；两个8×8桥节点通过 | `1.0088530050124973 s` |
| `task041_petsc_lu_stage_bridge_retry_20261008T000705Z:mpi2:pytest` | 0；rank0/rank1各两个8×8节点通过 | `1.0087709960062057 s` |

V5 append receipt见[reconciliation record](../../../results/task041_petsc_lu_stage_bridge_retry_20261008T000705Z/v5_ledger_reconcile_20261008T003131Z/v5_ledger_reconciliation_receipt.json)，SHA `a8e400ed3a35f0a49c7da8e1e51667783465cb8dc978749cd349806d12e3302c`。ledger从162项/SHA `32479e18035e341633073a0982b798e7fdca5208dda0d1b79677f2a6faa2a47c`变为165项/SHA `b983f17697a2b17e9fd6d7ef2141a3945a9b86689d2f6b048e36a51aa947711e`，只加上述3个父wall，共`3.026434561004862 s`；ABI、compile、static不计。此测试只验证小矩阵stage API与调用/所有权，不证明生产规模factor的内存值。

### W5离线artifact-only对照

本次完整比较前有一次identity拒绝：`task041_w5_candidate_artifact_comparison_20261007T235317Z`因candidate authority method不是注册route而停止，numeric `not_evaluated_due_to_artifact_validation_failure`，checker/parent wall分别`122.18274498195387/122.91199241997674 s`；该attempt及raw保留。之后完整比较器调用一次；左侧为W5 fixed-H6 candidate，右侧为explicit-Schur candidate reference，两者不是exact和approximate真值关系。reference/candidate consumer summary SHA分别为`bd8cf3d9696c17a54c64239334acab90de3e9dc1cae383c4b9fe537991eb332d`与`4257b309c5381498c6a84110d5c49e86eb0e3ca78272b09b7bb6ee731dd18526`；同一W5/p6/h4/M480/MPI8/cell-condensed input/resolved，18项身份和输入封套通过。R/T/A/A_volume差值为`+3.543842996833746e-11 / −2.6720737168056674e-13 / −3.5171199286310184e-11 / +1.7145174169286292e-12`（限`1e-8`）；选定E/H相对L2=`5.688326111234493e-10/5.742838138430747e-10`（限`1e-6`）；canonical四角色相对系数L2分别为bottom active/full `1.7128976856531144e-8 / 1.6977718026171218e-8`和top active/full `1.1038152408073086e-10 / 1.102299390456392e-10`（限`1e-5`）；法向通量相对L2=`1.7488283863630695e-11`（限`1e-4`）。这些比较门均通过。

26个显著外部行中的唯一失败项`["bottom",-15,0,"s"]`幅度/功率相对差为`1.0880143757234042e-6 / 2.074050200051092e-6`，高于`1e-6`，所以结果为`numeric_gate_fail`、full comparison false。该行参考功率`2.2419065611486787e-8`超过显著性floor`1e-8`；candidate/reference复幅值、分母与绝对差均见[失败行记录](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_significant_external_failure_record.json)，SHA `9fe88ab05dfb1b448935e127103a3d871b5d07f4626133ef23943f51ebf7cb3a`。资源与workflow仍`inconclusive`，raw-Q跨场向量`not_run_not_defined`，integrated full-3D checker及solver/FE未运行。双方共64个canonical shards、`1,313,610,614 B`；checker调用wall`533.9173726618756 s`，Python父wall`534.6402724480722 s`，单进程`ru_maxrss=5,691,043,840 B`（非tree/cgroup）。输入未修改；performance=`not_isolated`；offline checker不计FE ledger。完整[derived comparison](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/derived_comparison.json) SHA `b65537515682987ea7e5eac15e655cf231af885eb66ea9170dbb4669231e9fcc`；原compact [w5_offline_comparison_compact.json](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_offline_comparison_compact.json) SHA `c088bd14872e924d990cdb4e1eed94af96c3f9bbf477cbc376389815ae96a032`保持封存；[更正compact](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_offline_comparison_compact_corrected.json) SHA `f9505f6b92cc14cec3da9b863f21cb6bbbaacf98393db9eed56ad56c94b70f63`及[更正回执](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_compact_correction_receipt.json) SHA `21320f82533a74bcfb066e9d207a24b2189759a289122dd9a176a505a03e724e`保留有符号差值及派生链。

### MUMPS 5.6.2手册字段解释（派生说明；旧raw不回填）

本机dpkg安装版本为`5.6.2-2.1build2`。对应Ubuntu source归档及归档内手册原文已复制到[ignored来源目录](../../../results/task041_petsc_lu_stage_bridge_retry_20261008T000705Z/mumps_5.6.2_reference/)，上游URL为`https://archive.ubuntu.com/ubuntu/pool/universe/m/mumps/mumps_5.6.2.orig.tar.gz`。tar SHA `13a2c1aff2bd1aa92fe84b7b35d88f43434019963ca09ef7e8c90821a8f1d59a`，PDF SHA `32acdd3e09fb69f9fab16c94ae67768d15c61ac9c27abf66eb1e0e6ecd904050`，纯文本 SHA `6228d0dd158a2a3a677664760c58c3297c52733fb88212e7c66a0b468b7dc941`；读取手册印刷页93–94及97–99。来源record SHA `9f2e93cf0e31410715db2d912bfef7f876ad9d050845c1fd1621c037720a4af1`，目录SHA256SUMS文件SHA `6ca047db5d54954b086174891a1cc476cdeafc15ddf1961cf91dc5c51b3f47f1`。

| 字段 | 本机版本手册含义 | 使用限制 |
|---|---|---|
| `INFO(3)` | 本rank因子复数entries；若为负，取绝对值乘`1e6`解码entries | 不是内存字节数 |
| `INFO(4)` | 本rank整数entries | 手册未给本地负值编码，不套用`INFOG(4)`规则 |
| `INFO(15)` | 分析后的本rank in-core工作内存估计，million bytes；依赖当前`ICNTL(14)` | estimate，不是RSS或保证上界 |
| `INFOG(16)` / `(17)` | 分别是上述估计的rank最大值 / rank总和 | `(17)`已经是全局总和，不能再把各rank副本相加 |
| `INFOG(3)` / `(4)` | 因子复数entries / 整数entries的全rank总量；若为负，分别取绝对值乘`1e6`解码entries | `(4)`全局规则不适用于本rank `INFO(4)` |
| `INFOG(18)` / `(19)` | numeric后实际已分配内部数据的rank最大值 / 总和 | numeric后实分配，不是analysis-only estimate |

因此，旧symbolic-only raw里尚未解释的INFO值继续保持`unknown`，本段只是有精确MUMPS版本、原文哈希和页码支持的后续释义；没有matrix/factor运行，也没有从entries或estimate换算大因子RSS。
