# Review V10-r2：W0.7现场证据

## 2026-10-09：W0.7 identity-sharing warm场终态与payload更正

本场是唯一Invocation `a598ab0a491649eda4060eef6a102b56`，source HEAD `6e072bd640b5c140ba64745c350ddf9916a566dc`，W0.7 reduced-p6/M400/MPI8，matched L20/N29/h20/29，复用producer、QEP=0。程序把多几何类共用的内部identity矩阵改为只读共享以避免重复数组；这些数组payload不等于RSS收益。

| 阶段/门 | 记录 | 结论 |
|---|---|---|
| bottom P4 | 64966²，NNZ 27,929,686；cleanup后fresh B 28,704,886,784 B；INFOG17 18,865,000,000 B；W 5,322,116,301 B | 合计52,891,003,085 B，比cap低330,159,923 B；bottom numeric完成，INFOG18/19=2,879/18,865 million bytes |
| top P4 | 64966²，NNZ 39,242,250；cleanup后fresh B 45,211,955,200 B；INFOG17 19,299,000,000 B；W 5,322,116,301 B | 屏查69,833,071,501 B，超过cap16,611,908,493 B；top numeric未调用，所需fresh B≤28,600,046,707 B |
| 终态与唯一wall | consumer IMPLEMENTATION_FAILURE；public rc3；finalizer failed/service_boundary_failure；controlled_stop.active=false；finalizer 8/10 | false仅public_result_completed/service_terminal_normal；bottom因子完成后清场，top pending因子销毁；feedback/outer/真残差/recovery/physics未到达；service wall 1860.62936514 s |
| V5 | 186项，SHA `d344166517fbbaa6f66c29a9687828f5e74c78b6dcba303c142c47e7f99477dd` | runroot唯一匹配一项；账目本身不带Invocation ID，由launch/finalizer/runroot绑定 |

转录更正：先前执行消息将P4 identity audit误标为P6。原消息和raw没有改写。consumer markers P6字段`detail.object_inventory.p6_assembly_time_condensation_build_audit`在wall 1572.1085634171031/1690.8518208200112分别记录nᵢ=450、rank-sum class数475/423、节省payload 756,540,000/672,300,000 B，合计1,428,840,000 B；同两侧P6 retained Schur payload为1,418,342,400/1,263,071,232 B。P4的独立字段`identity_projection_*`是nᵢ=108、class数475/423、节省43,576,704/38,724,480 B，合计82,301,184 B。所有payload均不是RSS。

只读对象审计按源码形状推得P6局部LU/两个恢复映射/Schur的可见rank-sum payload为11,177,212,032 B；该数组payload数值比top门差额小5,434,696,461 B，但不是RSS减量或可回收量上界，不能据此证明可释放量足够或不足；这些数组在后续P6作用、P4右端处理/求解与恢复中仍有用途。P4 `port_audit.cells_with_port_terms`的bottom 0/top 15来自`resource_scope=rank_local`的本rank循环，不是全局side cell数。源码计数遍历按本rank owned cells构造的`cell_recovery_maps`；本run未保存全rank计数、逐rankBi/Di/xiB字节及ghost/cache别名总量。`720×108×646×16=803,727,360 B`仅是一侧720个owned cells假设下的条件尺寸示例，不是全局或两侧上界。top fresh B采样时bottom因子仍存活，其驻留贡献已计入B，不另加bottom INFOG(19)；INFOG(19)不是RSS的一一对应值。top INFOG(17)与已驻留symbolic字节没有可审拆分，不能相减。现有证据尚未确认足量可释放量，也未证明全局潜在释放总量不足。对象用途、last-use位置和证据缺口见[Response V12](../response_v12.md)。

原始证据SHA：consumer markers `e5f4644f9ad70fbbd2f785f317b3e3773fd6aacb11dc57348d910e449ede1bd4`；factor inventory `3284fe583c56e51effe76191d3f424a9d3528711ac5c1135693480c0d1112084`；service summary `1b8d4a573de76cf9f19bf23dcaa908a126971973f29b3e6bca3b85f990ac60c2`；finalizer `92e4aa4fbb7b19587b7544ff273f5dd66c3f58c77a910588a6b75837929ca847`。派生terminal compact：[terminal compact](../../../results/task041_w0p7_identity_sharing_warm_run_20261008T233316Z/terminal_compact_20261009.json)，SHA `bead944a1d4bd4f5f35097c8bf8cb43ee9478c0721f663e722634896a17235b3`。raw分类、ledger、source与stash均未改；没有新测试、ABI、QEP或FE。

## 历史快照：2026-10-08 W0.7 compact-transfer warm场终态

本场Invocation a6a67fc93a1d45cfa69cce0469cb0672，unit task041-v10r2-w0p7-compact-transfer-numeric-cleanup-warm-cpu10-11-14-15-16-17-18-19-20261008T142600Z.service，runroot results/task041_w0p7_compact_transfer_warm_run_20261008T142600Z，运行source 47b8b655ee9a9cc72dc1f89928b770f7061b22ea。模型为W0.7 reduced 10×5 nm、接口2/22 nm、p6/h0.70/M400/MPI8、matched L20/N29/h20/29、fixed-H6；复用既有producer，QEP=0。

| 阶段 | 实测 | 边界 |
|---|---|---|
| one-cell | source 15120×15120、NNZ 7,123,680、PORD；numeric完成并销毁 | ready marker rows=17280是port/output数，不是source rows |
| bottom/top P4 | 64966²；NNZ 27,929,686/39,242,250；sequential AMD symbolic完成；INFOG(17)=18,004/15,601 million decimal bytes | 两侧numeric attempts=0，pending各销毁一次 |
| bottom numeric门 | authority fresh B由31,398,424,576降至30,729,564,160 B（max(tree RSS, dedicated cgroup current）；对应cgroup current为28,504,768,512/27,921,858,560 B）；单份INFOG(17)=18,004,000,000 B；W=5,322,116,301 B；合计54,055,680,461 B | 超cap 53,221,163,008 B共834,517,453 B，numeric前拒绝；清理实测降低authority 668,860,416 B，不保证复现 |
| 后续top门 | 以本次top INFOG(17)和W计算，fresh B需≤32,298,046,707 B | bottom numeric未运行，bottom后的top B/INFOG(19)未知 |
| 运行终态 | consumer IMPLEMENTATION_FAILURE；public task041_public_command_nonzero/rc3；finalizer failed/service_boundary_failure；controlled_stop.active=false | finalizer 8/10，仅public_result_completed与service_terminal_normal为false；反馈门、outer、五真残差、恢复与physics未到达 |
| 唯一计费 | service-finalizer wall 1,979.603254005 s；ledger 183项、SHA cd4c69f03e89b67350478b6c37655bc03ca77893ef5f6d96959fae32dcaaaa6e | runroot恰一条账目；账目自身无Invocation字段，通过launch/finalizer/runroot绑定；不重复加内部阶段 |

本场top P4转移每侧K=766；compact方向缓存的canonical矩阵、方向实体块和索引rank-sum payload各侧共150,893,696 B。它是数组payload，不是RSS节省。对象审计显示P6 retained-local-Schur字节未持久化；P4 top记录13个带端口cell，但逐rank Bi/Di/xiB shapes缺失；ModalTraceProjection trace payload按截面layout推导为185,651,200 B MPI8 rank-sum，mass矩阵字节未知。可审的窄候选是W0.7固定H6路径在projection最后使用后释放trace引用，但已知payload小于本次834,517,453 B拒绝差额，因此单独不足以支持重跑。细节见[Response V12](../response_v12.md)和[Task041 summary](summary.md)。

raw未修改。service summary SHA 5311cfa56d0643e3e91fafb6d33451af7f9c335d39972995ec662a6ac4fac366；finalizer summary SHA 7c00774e836ce40b322ee3472e6c913706781135cc1552c0ac8bdd40869a55f4；consumer markers SHA ce821d82fb0eb79e11315d427f856efd78c71e9ae865862a7e037217e0fbeb16。此前消息遗漏的finalizer SHA末位4已按实际文件更正。没有pilot数值pass或50×25 nm、2 TB、48 h资格。

## 历史快照：上一Invocation c38a11ae711846599601ac3c06286327（compact-transfer warm场终态）

Invocation c38a11ae711846599601ac3c06286327，unit task041-v10r2-w0p7-compact-transfer-warm-cpu10-11-14-15-16-17-18-19-20261008T125520Z.service，runroot results/task041_w0p7_compact_transfer_warm_run_20261008T125520Z，运行source e890c1c12feb90dd4f7695d31402d63ff788d186。此为W0.7 reduced 10×5 nm、接口2/22 nm、p6/h0.70/M400/MPI8、matched L20/N29/h20/29、fixed-H6、P4 target 5e-13/max2。复用已资格producer packet，producer source为2708214386d38bd69f73e6b196c8ed843bb53d81，本次QEP=0。

| 阶段/门 | 实测 | 状态 |
|---|---|---|
| one-cell | source矩阵15120×15120；跨rank一次求和NNZ 7,123,680；INFOG(7/32)=4/1，PORD；numeric已完成并销毁 | ready marker rows=17,280是端口/输出口径，不是source行数 |
| bottom P4 | 64,966×64,966，NNZ 27,929,686；sequential AMD；INFOG(16/17)=2766/20150 million bytes | symbolic完成，numeric attempts=0 |
| top P4 | 64,966×64,966，NNZ 39,242,250；sequential AMD；INFOG(16/17)=2392/15697 million bytes | symbolic完成，numeric attempts=0 |
| bottom numeric门 | fresh B 30,895,177,728 B + 单份INFOG(17) 20,150,000,000 B + W 5,322,116,301 B = 56,367,294,029 B | 比cap 53,221,163,008 B高3,146,131,021 B，故numeric前拒绝；不是实测峰或算法失败证明 |
| pending清理 | bottom与top各destroy一次、error_code=0；两侧numeric均未调用 | pending factors已清理；top numeric门未评估 |

compact transfer对象统计与RSS分列：bottom K_local跨rank合计733、rank-sum数组payload 133,147,520 B；top K_local合计766、rank-sum数组payload 150,893,696 B。payload含跨rank实际持有的canonical R、方向实体块和索引；它不是进程RSS，也不是RSS节省。process-tree RSS峰35,009,921,024 B，dedicated cgroup peak 32,935,227,392 B。

与上一场同阶段只作描述性对照：fresh B从35,915,554,816降至30,895,177,728 B（−5,020,377,088 B）；bottom INFOG(17)从19,460,000,000增至20,150,000,000 B（+690,000,000 B）；预算筛查缺口从7,476,508,109降至3,146,131,021 B（缩小4,330,377,088 B）。不能将fresh B变化全部归因于compact表示。当前top symbolic信息对应的未来numeric fresh-B限额为32,202,046,707 B；本场未测该值。

consumer marker SHA bb2a466b84bd98216e2120938d9679c90cf2e81ef71f09b97d80db937a6703aa；finalizer SHA 8c987379232be4ebd2dea1f159118cd99fc4efcd8fe11f2995541c20a9e7e981。原始分类为consumer IMPLEMENTATION_FAILURE、public task041_public_command_nonzero/rc3、finalizer failed/service_boundary_failure、controlled_stop.active=false。finalizer 8/10，仅public_result_completed与service_terminal_normal为false，其余清理/账目检查通过。唯一service-finalizer wall 1,956.390568298 s；V5 ledger 181项，本Invocation一条，SHA fc930c8c8c689cf61d08948e4aa768c2bd307bb24e61068a64833bf4f66af7d5。无fixed-H6反馈、outer、五残差、recovery、physics或official observables；此reduced pilot不资格化50×25 nm、2 TB或48 h。

原始证据：[consumer markers](../../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261008T131610.846014Z/consumer/markers.jsonl)、[public summary](../../../results/task041_w0p7_compact_transfer_warm_run_20261008T125520Z/summary.json)、[service parent](../../../results/task041_w0p7_compact_transfer_warm_run_20261008T125520Z/service_parent_summary.json)、[finalizer](../../../results/task041_w0p7_compact_transfer_warm_run_20261008T125520Z/finalizer/finalizer_summary.json)。

## 历史快照：前一Invocation 3d6b63c763414ad984beb60f1296458e（deferred-AMD，numeric前预算拒绝）

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

## 2026-10-08：compact transfer接线进度（尚无新FE）

方向缓存的compact表示把每个cell方向单独保留的完整稠密方向矩阵，收敛为每adapter共享一份canonical插值矩阵/元素，加按实体分块的`T_f`和`T_c^{-1}`。`P=T_f R T_c^{-1}`，伴随`PH=(T_c^{-1})^H R^H T_f^H`；已有tiny serial/MPI2节点覆盖复数P/PH、entity-closure支撑与释放。它减少重复存储的设计目标尚未在MPI8真实场测量，不能将理论payload字节当成RSS节省。

| 阶段 | 实际证据 | 边界 |
|---|---|---|
| 组件serial/MPI2 | transfer SHA `af6d4009eb219f91184f436beeb83d6f7a34d47800c2a5a68c70cb1ee3c2955b`、test346 SHA `cc6f2400000d43b4a720d0e40553f51508dab7079a274767280bf9e095356e41`；serial 1 passed/`72.66264551295899 s`，MPI2每rank 1 passed/`75.71961162285879 s` | 小型组件合同，不是大矩阵RSS或FE资格 |
| W0.7 consumer hookup initial | 生产SHA不变；test349 SHA `ae5eb4b0a160b5d22b5f0cdbbdba358499a24d19ff4644f564f5627cd24097e8`；selector 1 passed、selector 2 fixture失败，selectors 3–5因`-x`未运行；`4.063483553007245 s` | 失败是test fake把只读audit属性当作可写 |
| 定向与剩余selectors | test349修正SHA `7c92ad0628dce1f825abfb408064307dde61dd732842b2e8903e7616b35c0efd`；selector 2为1 passed/`3.041036447044462 s`，selectors 3–5为3 passed/`8.140667369123548 s`；test351 SHA `cfd14262f0fb818243d03225bc4e42a17a7c453b8384e433038a112681127a8b` | 分批通过；不合并称为同一最终SHA上的一次全组通过 |

接线限定在已注册W0.7 deferred fixed-H6路径。transfer建成后每侧只做一次标量汇总，inventory本身不含collective；K/seed口径、owned与owned+ghost cell数、canonical及方向块payload字节都只是对象库存描述，不代表进程树RSS，也不对共享records重复计数或把单rank值乘MPI大小。普通/default与其他注册模型保持原路径。

上述三次consumer-hook pytest父wall合计`15.245187369175255 s`，各按attempt唯一计账；连同组件serial/MPI2，本阶段wall共`163.62744450499303 s`。V5 ledger从177项增至180项，累计`527353.9467369274 s`，SHA `634dd5925f164bd2a6e7190687d2203ffdeba2924cb3a33f3fd091c125a361e1`；ABI和静态检查未计。首次失败raw、两次后续attempt、组件compact均位于`results/task041_w0p7_compact_orientation_consumer_hook_serial_20261008T122800Z/`、`results/task041_w0p7_compact_orientation_consumer_hook_serial_fixture_retry_20261008T123300Z/`、`results/task041_w0p7_compact_orientation_consumer_hook_serial_remaining_20261008T123500Z/`及`results/task041_compact_orientation_serial_mpi2_20261008T1203Z/`。

旧deferred-P4试算筛查差额`7,476,508,109 B`仍是未由本次测试或真实运行消除的历史预算缺口。compact表示及setup inventory还没有新MPI8真实驻留、factor numeric或RSS证据；W0.7 FE/五残差/恢复物理门均无新结果，不能登记pilot资格。下一步只是以最终clean源码准备独立warm静态包，fresh准入与真实运行另行审核。

## 2026-10-08：numeric前清理门合同更新（无新FE）

在W0.7注册bottom/top P4各自symbolic完成、numeric开始前，现有rank入口都调用同一个collective heap cleanup；rank 0在前后采样并把清理后B交给既有numeric预算门。top pre-symbolic cleanup保持原样；默认路径及one-cell无新增清理。pending factor、源矩阵和恢复数据仍保持强引用，不主动销毁对象，不预扣潜在释放量。

合成serial attempt `task041_w0p7_numeric_gate_cleanup_serial_retry3_20261008T143000Z:serial:two_selectors`在exact-side SHA `632c0a5e79e3a6c6441462d7556a85b8d161792efc7faaea87a171d01e06f7dd`、test351 SHA `90f1866734be47bad1610e1068e32f8ac81e06dc0911aa22cdfdf31df13edd1e`下两项通过，父wall `3.2357035228051245 s`，attempt SHA `7f32831ff60e0fe0bf1832c03602733f5adbbdaa4c263d44a1552581af4ea476`。该wall仅在V5记一次；账本182项，SHA `e0bf2619c9f0f851b06cab44caa9b702df168a1ac793328fa556bd7fdfb3e13b`。三个更早的启动前错误均未启动pytest且不计wall，原记录仍在各自attempt目录。

这不是实际MPI8/PETSc清理或RSS回收实测，不证明历史numeric缺口已缩小，也不证明bottom/top numeric可支付。该记录没有启动新的W0.7 consumer、FE或dispatch；原停止raw、数值门和容量口径保持不变。

## 2026-10-09：P6 identity projection 共享组件验证

本次在assembly-time condensation builder内减少重复单位映射数组：同一次builder调用中的各类别，以及RHS projection / solution embedding / residual projection三个映射，共用一个只读`float64` identity；不同builder调用仍各自持有独立对象，empty-owner rank不创建数组。收益口径是去重后的NumPy payload，不是RSS；build audit只在一次构建期间执行小型标量`allgather`，不在每次apply通信。普通路径及其他构造器行为未改。

| 模式 | 实际验证 | 父wall / runner authority peak | 结果边界 |
|---|---|---|---|
| serial | `test_matches_post_assembly_reference_and_recovers_interiors` | `10.659502683905885 s` / `450416640 B` | 1 passed；小型复数FE凝聚与内部恢复，不代表W0.7真实规模 |
| MPI2 | `test_mpi2_matches_post_assembly_reference`及`test_mpi2_single_cell_empty_owner_has_no_identity_payload` | `6.456301460042596 s` / `618975232 B` | 两个rank各2 passed；分布式装配对照与empty-owner检查，不是MPI8资源资格 |

两次pytest父wall各按唯一attempt计账，共`17.11580414394848 s`。V5 ledger由183项/SHA `cd4c69f03e89b67350478b6c37655bc03ca77893ef5f6d96959fae32dcaaaa6e`更新为185项/SHA `d5390d12f2fe362b675205f3758672429be7c20b19fafdafa64fd0b4aa15d28b`；ABI、host preflight和静态检查不计。receipt SHA：serial `36af30f433f3c42add7f5da65f418fc1574152ccc1bdcaa8e718fdf22905e3e2`，MPI2 `89fed62e00bef370a4b98c3567511190a7e260355322d926f252a8bc9826c75e`。三文件SHA及stdout/attempt SHA见[Response V12](../response_v12.md)。

本组件尚未在真实P6两侧测量identity payload与进程树RSS，也未运行production consumer。历史numeric预算缺口没有因本测试改变；下一步仅按授权派生identity-sharing warm准备包，保留matched-cell、compact transfer、deferred AMD、numeric cleanup、原cap/warn/W/floor与数值门，并重新做fresh宿主准入。当前没有FE资格、dispatch或新Invocation。
