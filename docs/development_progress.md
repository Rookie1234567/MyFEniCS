# 项目开发进度：Task000–Task041

## 2026-10-09：W0.7 fixed physical BAL_H candidate binding 接线事故

后续 warm Invocation 72f92a0cae6f4066a455bea0dba8561c 与此前实际到达 outer iteration 1 的 797ae... 分开记录。本次 sealed request 为 fixed_physical_balh_once，但 candidate setup 重建 fixed-H6 binding 时漏传 selector；注册检查在 factor_setup 拒绝，actual method未建立。consumer IMPLEMENTATION_FAILURE、public rc3、finalizer failed/service_boundary_failure；finalizer 11项为9 true/2 false，仅public结果完成与service正常终止为false，controlled_stop.active=false。这是P4前的接线实现失败，不是BAL_H残差或资源失败。

QEP=0；one-cell完成后清理，bottom/top P4均未构造，P4 numeric、outer、physics/RTA未运行。process-tree peak 33,847,504,896 B、job cgroup history peak 31,681,507,328 B，低于80 GiB cap；唯一service wall 1410.90943187 s沿用原V5服务行，不重复收费。测试最终生产/test SHA 06f59398...10262 / c169028e...41f09；一条真实candidate-helper边界回归通过，前一次fixture参数签名失败与随后通过的两个pytest父wall共 10.756424868945032 s单独入账。V5 206项，SHA e1da804cd152958875b965fc94efaf22823c40dd8f60bfa79f40a820868bd21c。详见response_v13及runroot compact results/task041_v11_w0p7_fixed_physical_balh_once_warm_run_20261009T142126Z/terminal_compact_modal_feedback_candidate_helper_v11.json（SHA b3444f82...e533a）。


## 历史：2026-10-09 Task041 Review V11 W0.7 P1 warm场终态（Invocation 797ae388）

**模型与阶段。** 本场为复用既有producer packet的W0.7缩减pilot：10×5 nm、接口2/22 nm、p6/h0.70、M400/MPI8、matched L20/N29/h20/29；运行源码HEAD `47fc621a478adf26ebe9ca41d54563e188bab1d1`，Invocation `797ae38854d546898a895c81d803a5ec`，当前QEP=0。one-cell及bottom/top P4 numeric完成，fixed-H6 setup repeat/linearity gate通过，outer有iteration 1进度，但后续fixed-H6 modal内层第二次solve未通过显式残差门。

**失败与资源。** 失败solve KSP reason `-3`、8迭代、`rtol=0.001`，显式相对残差`0.005653709235402098`高于限值；solver/total S_H MatMult为8/9，上限9/10，`budget_exhausted=false`。失败发生于outer right-FGMRES PC的后续modal solve，不是top构造；`top_construction_cleanup`仅是cleanup覆盖的最后stage标签。case cap/warning/W为`85,899,345,920/77,309,411,328/8,589,934,592 B`，node0 MemFree reserve/floor `412,316,860,416 B`，host MemAvailable独立检查。service summary tree峰`47,073,288,192 B`、consumer resource summary tree峰`47,027,847,168 B`、专属job cgroup峰`44,504,326,144 B`分列；均低于cap，本场不是资源停止或OOM。

**服务终态与范围。** consumer `IMPLEMENTATION_FAILURE`、public rc3、finalizer `failed/service_boundary_failure`、8/10，`controlled_stop.active=false`；唯一finalizer wall`9,685.695409207 s`，V5 ledger 193项、SHA `803c4cb9c05b0c25426af3d75f6e20d9940bf08c351ed22a911f584e62e0b6ae`。最终五残差、recovery、完整E/H/RTA、A_volume、衍射及physics未到达；不能登记完整数值pass或50×25 nm、2 TB、48 h资格。W5弱显著衍射通道按用户决定延期处理、原失败保留且不作为0.7前置；W2本阶段未推进以免延误主线。完整失败solve及raw入口见[Response V13](task041_mpi1_shortwave_hybrid_capacity/response_v13.md)、[Task041 outcomes](task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)和repo-root ignored证据`results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z/terminal_compact_v11.json`。

## 2026-10-09：Task041 W0.7 PORD warm场终态

本次是W0.7缩减pilot（10×5 nm、接口2/22 nm、p6/h0.70/M400/MPI8、matched L20/N29/h20/29）的独立warm consumer；复用producer packet，QEP=0。source `6ffa7768329b637d96a9dccc2eb5aa00d510bb28`，Invocation `12180bdec9824ec49d60b26aefe3655b`。PORD调整因子分解使用的消元顺序，不改方程；本场bottom P4 numeric完成，top仅完成symbolic，numeric前预算筛查拒绝。

Top门使用cleanup后fresh B 38,544,203,776 B、单份INFOG17 9,647,000,000 B和政策W 5,322,116,301 B，合计53,513,320,077 B，比cap 53,221,163,008 B高292,157,069 B。该估计拒绝不等同RSS越cap或数值失败。进程树RSS峰40,494,215,168 B，专属job cgroup峰37,709,873,152 B，口径分开。

终态原样为consumer `IMPLEMENTATION_FAILURE`、public rc3、finalizer `failed/service_boundary_failure`、`controlled_stop.active=false`；finalizer 8/10，只有public结果完成和service正常终止两项false。bottom numeric完成并清理，top numeric=0；outer、物理门、恢复和official R/T/A均未运行。唯一service wall为3,241.567376339 s，V5共189项、SHA `ffa1a15cc639cf30c064057e9a9749032337882fbaade8b5f0445312ecc424cf`；父层wall不另计。

P4 Bi全rank字节未持久化。raw只给rank-local term数bottom/top=0/16；基于每侧720 owned cells、nᵢ=108、最多646个port的满矩阵条件式大小为803,727,360 B/side，但不是实际payload或RSS收益。Bi预热xiB后不再参与数学乘法，可是现有`_port_data`仍读Bi作校验；Di、ports、xiB仍支撑RHS与恢复。现有证据不能确定足量释放，也不能证明总潜在量不足。细节见[Response V12](task041_mpi1_shortwave_hybrid_capacity/response_v12.md)与[本场compact](../results/task041_w0p7_pord_numeric_cleanup_warm_run_20261009T043645Z/terminal_compact_20261009.json)。此前AMD结果只作不同Invocation的INFOG记录，不据此归因排序收益。保护stash、raw和ledger均未改；无新测试或计算。

## 2026-10-09：Task041 W0.7 identity-sharing warm场终态

**对象和方法。** 本场是W0.7缩减pilot（10×5 nm、接口2/22 nm、p6/h0.70/M400/MPI8、matched L20/N29/h20/29），复用既有producer packet，当前QEP=0。identity-sharing让同一个局部单位矩阵由多个几何类只读共用，从而减少重复数组；它不更改离散或方程，数组字节也不能等同进程RSS下降。

**结果。** bottom P4的MUMPS numeric完成。其after-cleanup fresh B为28,704,886,784 B，单份INFOG17为18,865,000,000 B，政策W为5,322,116,301 B，总筛查52,891,003,085 B，低于cap 330,159,923 B。top symbolic之后另行cleanup，fresh B为45,211,955,200 B，单份INFOG17为19,299,000,000 B，再加W后为69,833,071,501 B，比cap高16,611,908,493 B。top numeric没有调用；它需要fresh B≤28,600,046,707 B。MUMPS 5.6.2记录bottom numeric实际INFOG18/19为2,879/18,865百万十进制字节，top INFOG18/19未运行。full run process-tree peak 47,043,870,720 B、专属job cgroup peak 44,224,434,176 B分列。

**身份和负结果。** Invocation `a598ab0a491649eda4060eef6a102b56`，source HEAD `6e072bd640b5c140ba64745c350ddf9916a566dc`，rank map `[10,11,14,15,16,17,18,19]`。原始终态为consumer IMPLEMENTATION_FAILURE、public rc3 `task041_public_command_nonzero`、finalizer `failed/service_boundary_failure`，`controlled_stop.active=false`。finalizer 8/10，仅`public_result_completed`与`service_terminal_normal`为false；bottom numeric factor完成后与top pending因子均按记录清理。fixed-H6反馈、outer、五真残差、恢复、physics与official result均未到达。这是top numeric前的预算拒绝，不是controlled stop，也不是已证明算法无法数值求解。

**转录更正与存量。** 前一执行消息将P4 identity audit误写成P6，原通知和raw均保留。当前P6 markers真实记录nᵢ=450、rank-sum class数475/423，identity payload节省756,540,000/672,300,000 B，两侧1,428,840,000 B；P6 retained Schur payload为1,418,342,400/1,263,071,232 B。P4另为nᵢ=108、class数475/423、payload节省43,576,704/38,724,480 B，两侧82,301,184 B。它们都是暴露数组payload，不是RSS节省。V5 ledger现在186项，SHA `d344166517fbbaa6f66c29a9687828f5e74c78b6dcba303c142c47e7f99477dd`；runroot只有唯一匹配的1,860.62936514 s记录，Invocation经launch/finalizer/runroot关联而非账目行字段。

**解释与决定。** P6局部LU、两个恢复映射及Schur按真实class计数推得的可见rank-sum数组payload为11,177,212,032 B。它与top筛查差额的纯字节差为5,434,696,461 B，但payload不是RSS减量或可回收量上界，且这些数组仍有后续用途。P4 `port_audit.cells_with_port_terms`的bottom 0/top 15是rank-local owned-cell循环计数，不是全局端口cell数；本run没有全rank计数或逐rankBi/Di/xiB字节，也没有ghost/cache alias总量。`720×108×646×16=803,727,360 B`只是某一侧假设720个owned cells时的条件式尺寸示例，不是两侧或全局上界。top fresh B采样时bottom因子仍存活，其驻留贡献已计入B，不另加bottom INFOG(19)；INFOG(19)的allocated-data统计与RSS不一一对应。top symbolic驻留与INFOG(17)无法拆分。当前尚无足量可释放证据，也不能据此证明全局潜在释放总量不足；不建议同包重建试运气。下一候选仅为xiB预热后审查Bi-only缓冲区释放，其总收益仍未知。50×25 nm、2 TB、48 h仍未资格化。

[Response V12](task041_mpi1_shortwave_hybrid_capacity/response_v12.md)、[Task041 outcomes](task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)与[terminal compact](../results/task041_w0p7_identity_sharing_warm_run_20261008T233316Z/terminal_compact_20261009.json)保留证据；compact SHA `bead944a1d4bd4f5f35097c8bf8cb43ee9478c0721f663e722634896a17235b3`。无新计算、源码改动或ledger/raw更写。

## 历史快照：2026-10-08 Task041 W0.7 compact-transfer warm场终态（Invocation a6a67fc93a1d45cfa69cce0469cb0672）

本场在bottom P4 numeric前由预算门拒绝：fresh B从31,398,424,576 B经既有collective cleanup实测降至30,729,564,160 B，再加单份INFOG(17) 18,004,000,000 B及政策W 5,322,116,301 B，筛查总额54,055,680,461 B，超过cap 53,221,163,008 B共834,517,453 B。清理降低668,860,416 B是本次观测，不是未来可保证收益。bottom/top numeric均未调用，pending句柄各销毁一次。top后续门需fresh B≤32,298,046,707 B，但bottom numeric后的B/INFOG(19)未知。

唯一Invocation a6a67fc93a1d45cfa69cce0469cb0672，source 47b8b655ee9a9cc72dc1f89928b770f7061b22ea；W0.7 reduced 10×5 nm、接口2/22 nm、p6/h0.70/M400/MPI8、matched L20/N29/h20/29，复用既有packet、QEP=0。终态原样为consumer IMPLEMENTATION_FAILURE、public task041_public_command_nonzero/rc3、finalizer failed/service_boundary_failure且controlled_stop.active=false；finalizer 8/10，仅public_result_completed与service_terminal_normal为false。唯一service wall 1,979.603254005 s，V5 ledger 183项、SHA cd4c69f03e89b67350478b6c37655bc03ca77893ef5f6d96959fae32dcaaaa6e；runroot恰一条记录，但entry自身不含Invocation字段。没有反馈门、outer、五真残差、recovery或physics，不登记数值pass；不资格化50×25 nm、2 TB或48 h。finalizer SHA完整值为7c00774e836ce40b322ee3472e6c913706781135cc1552c0ac8bdd40869a55f4，已更正先前漏末位4的通知。

只读对象审计没有找到足以承诺跨过缺口的已知可释放大对象：P6 retained local Schur的unique bytes未进入本场raw；P4 top报告13个带端口cell但Bi/Di/xiB逐rank shapes未持久化；ModalTraceProjection trace数组按layout推导rank-sum 185,651,200 B，小于门缺口且不等于RSS。top factors和H6/transfer/P4恢复项在求解/恢复前仍有用途，不能提前释放。细项及原始文件SHA见[Response V12](task041_mpi1_shortwave_hybrid_capacity/response_v12.md)与[Task041 outcomes summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)。保护stash和raw/ledger未改；本轮无测试、ABI、QEP、FE或第二dispatch。

## 历史快照：上一场Task041 W0.7 compact-transfer warm场（Invocation c38a11ae711846599601ac3c06286327）

唯一Invocation c38a11ae711846599601ac3c06286327（MPI8、W0.7 reduced p6/h0.70/M400、matched L20/N29/h20/29）在bottom P4 numeric前被阶段预算门拒绝。此前compact表示把方向变换矩阵改为共享canonical矩阵与实体方向块；本场bottom/top K_local跨rank总数733/766，对应rank-sum payload 133,147,520/150,893,696 B。这些对象字节不等于RSS，也不能把跨场RSS变化全部归因于该表示。

one-cell source matrix为15120×15120、NNZ一次跨rank求和7,123,680，按INFOG(7/32)=4/1为PORD；numeric完成并销毁。bottom/top P4矩阵均64966×64966、NNZ 27,929,686/39,242,250，sequential AMD symbolic完成；INFOG(17)分别20150/15697 million bytes。bottom numeric筛查为fresh B 30,895,177,728 B + 单份INFOG(17) 20,150,000,000 B + W 5,322,116,301 B，共56,367,294,029 B，比cap 53,221,163,008 B高3,146,131,021 B。两侧pending handles各销毁一次、numeric attempts均0。

原始终态为consumer IMPLEMENTATION_FAILURE、public task041_public_command_nonzero/rc3、finalizer failed/service_boundary_failure、controlled_stop.active=false；finalizer 8/10，只有public_result_completed和service_terminal_normal为false。唯一service wall 1,956.390568298 s，V5 ledger 181项、本Invocation一次，SHA fc930c8c8c689cf61d08948e4aa768c2bd307bb24e61068a64833bf4f66af7d5。tree RSS峰35,009,921,024 B、dedicated cgroup peak 32,935,227,392 B分列。反馈门、outer、五真残差、recovery与physics未到达；不构成pilot数值pass、50×25 nm、2 TB或48 h资格。W2本轮不执行，保护stash和raw未改。完整阶段、跨场对照与marker/finalizer SHA见[Task041 Response V12](task041_mpi1_shortwave_hybrid_capacity/response_v12.md)、[outcomes summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)及[实测进度](task041_mpi1_shortwave_hybrid_capacity/outcomes/shortwave_measured_progress_v10.md)。

## 历史快照：2026-10-08 前一场 Task041 W0.7 deferred-AMD warm场

W0.7 reduced-p6 matched-cell唯一warm Invocation `3d6b63c763414ad984beb60f1296458e`在bottom P4 numeric前被预算门拒绝。One-cell source factor `15120×15120`、NNZ一次跨rank求和`7,123,680`，按`INFOG(7/32)=4/1`为PORD；numeric已完成并销毁。Bottom/top P4分别为`64966×64966`、NNZ `27,929,686/39,242,250`，两侧sequential AMD symbolic完成，numeric调用均为0，pending handles各destroy一次、error=0。One-cell marker `rows=17,280`代表端口/输出口径；source矩阵行数及interior rows为`15,120`。

Bottom numeric门使用fresh `B=35,915,554,816 B`，加单份MUMPS全rank估计`INFOG(17)=19,460,000,000 B`和政策预留`W=5,322,116,301 B`，筛查总额`60,697,671,117 B`，高于冻结cap `53,221,163,008 B` `7,476,508,109 B`。这是预测门拒绝，不是实测所需峰或算法错误证明。终态分类原样为consumer `IMPLEMENTATION_FAILURE`、public `task041_public_command_nonzero`/rc3、finalizer `failed/service_boundary_failure`；`controlled_stop.active=false`。Finalizer 8/10，false仅`public_result_completed`和`service_terminal_normal`，其余清理/账目检查通过。

唯一service-finalizer wall `2395.81151869 s`，175项V5 ledger中本Invocation一次（SHA `962d31d906d22ec39d6a0e534021caa5fbcc8d1f521a966f245129d6768985ba`）；tree RSS峰`35,915,563,008 B`与dedicated cgroup峰`33,178,259,456 B`分列。没有fixed-H6 feedback、outer、五残差、recovery或physics结果；模型仍`performance_not_isolated`，不资格化50×25 nm、2 TB或48 h目标。详见[Response V12](task041_mpi1_shortwave_hybrid_capacity/response_v12.md)、[outcomes summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)、[阶段记录](task041_mpi1_shortwave_hybrid_capacity/outcomes/shortwave_measured_progress_v10.md)与[hash-bound compact](../results/task041_v10r2_w0p7_deferred_amd_warm_run_20261008T082944Z/terminal_compact.json)。本Invocation无新pytest attempt，test summary中的174项仍是上个测试阶段快照；本次service wall由finalizer唯一计账。

## 历史快照：2026-10-08 deferred-AMD组件收口与warm run启动前

以下内容记录本次运行前的组件与准入状态；其“进行中/待执行”只描述当时快照。

代码提交`6caf43ebd52b14bf0c9423b33353e7fc8f38f27f`已推送至Task041原分支。为避免在大因子数值分解前才发现内存不足，注册的W0.7 P4路径将MUMPS流程拆为symbolic结构分析和同句柄numeric分解，并将PETSc 3.19.6 JOB_NULL缓存请求、版本推导输入及symbolic后的实际控制值分开核验。仅W0.7 deferred P4 opt-in启用AMD候选（ICNTL7=0/28=1、14=40）；普通KSP/default和one-cell路径不变。

serial两selector通过，父wall`3.040390633046627 s`；MPI2三个selector每rank各3 passed，父wall`2.0312472369987518 s`。两个pytest attempt合计`5.071637870045379 s`，各唯一记入V5；ledger 174项SHA `531d777d369c8d84e58120ec79eabb638dd7fb8e4c03b2fdac3a33f5290515d2`。这只证明8×8复矩阵桥接口、预算分支和同句柄生命周期，不是生产因子容量、完整FE或0.7 nm目标资格。扩展SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b`。

准备包使用预测阶段门`sym: fresh B + Δ + W <= cap`和`numeric: fresh_numeric_B + one INFOG(17) × 1e6 + W <= cap`；INFOG(17)为全rank总量，只取一份。`W=5,322,116,301 B`是政策预留而非误差上界，源码预测Δ也不是RSS保证。最终包和新MPI8 ABI均通过后，只dispatch一次；当前唯一新warm Invocation为`3d6b63c763414ad984beb60f1296458e`，unit `task041-v10r2-w0p7-deferred-amd-warm-20261008T082944Z.service`，源码HEAD `819ed980502783f4a11b8ea2c690dc8add44e81a`，rank map `[10,11,12,14,15,16,17,18]`，NRestarts=0。它复用已核producer packet，本次QEP调用0。

Consumer已通过one-cell因子的分阶段门：实际factor source matrix为`15,120×15,120`；八个rank的`MatGetInfo.local_nnz_used`分别为`867,744/1,041,192/922,464/803,736/1,045,836/817,164/794,448/831,096`，一次求和为`7,123,680`。`one_cell_factor_ready`的`rows=17,280`是端口/输出行口径，`interior_rows=15,120`，不等同于factor source rows。symbolic后MUMPS `INFOG(17)=2630`按5.6.2手册解释为million bytes的全rank合计，预算只取一份；同一分析记录的`INFOG(7)=4/INFOG(32)=1`表示sequential PORD，公开控制回读为空，符合one-cell保留旧排序，不是AMD。`before_symbolic`使用当次`B=23,705,509,888 B`和已完成one-cell宽阶段窗口`Δ=10,972,278,784 B`，加`W`后的筛查值`39,999,904,973 B`低于cap；该Δ是阶段校准窗口，不是独立因子峰或RSS上界。symbolic后使用fresh `B=23,727,190,016 B`、`INFOG(17)×10^6=2,630,000,000 B`及`W`，筛查值`31,679,306,317 B`也低于cap。因子在`679.020 s` ready；800列lift、forward/back 400列apply和bottom/top projection columns随后完成，top projection结束于`909.782 s`。`factor_stage_release`在`916.423 s`记录symbolic/numeric均完成、destroy一次且error=0，source keepalive已释放；`one_cell_factor_destroyed`于`916.542 s`。elapsed`973.150 s`时process-tree authority仍为`34,576,089,088 B`，专属service cgroup current/peak为`32,496,865,280/32,585,195,520 B`，host `MemAvailable=2,100,405,993,472 B`；factor destroy未带来同量级RSS下降，不据此宣称已回收物理页。不同scope读数不相加；global swap仅观察，job/cgroup swap为0。

One-cell清理后consumer于`1884.602 s`完成既有collective heap cleanup（该事件原字段`max_rss_before/after/released=4419.738/2687.305/1768.188 MB`），随后开始bottom P4。bottom在`1924.038 s`的pre-symbolic门使用fresh `B=24,812,064,768 B`、source-counted `Δ=1,382,983,004 B`和`W`，筛查值`31,517,164,073 B < cap=53,221,163,008 B`；矩阵为`64,966×64,966`、跨rank NNZ一次求和`27,929,686`。`1924.843 s` symbolic完成后factor为`symbolic_live_pending_numeric`，尚未numeric：MUMPS `INFOG(16/17)=2766/19460`（million bytes；全rank和只取一份），`INFOG(7/32)=0/1`，post-symbolic ICNTL7/28/14=`0/1/40`，sequential AMD控制符合。该估计不是RSS上界，也不预先通过numeric门。elapsed`1956.092 s`的现场tree authority=`25,925,132,288 B`、专属cgroup current=`23,455,088,640 B`；bottom pending计入后续fresh B。到该marker止，top P4、固定反馈门、outer、五项真实残差、recovery/physics和finalizer尚未到达，因此仍无整场数值结论。此前top P4超cap的controlled-stop及原始wall照旧保留。运行中仅按V9 allowlist更新进度文档；W2不执行，50×25 nm、2 TB及48 h资格仍未达。

cap/warning/floor保持`53,221,163,008/47,899,046,707/412,316,860,416 B`，swap仅观察，W2不执行。W0.7 reduced pilot尚未到outer、五真残差、recovery或physics；50×25 nm、2 TB及48 h目标均未达。详情见[Task041 Response V12](task041_mpi1_shortwave_hybrid_capacity/response_v12.md)、[outcomes summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)和[测试摘要](task041_mpi1_shortwave_hybrid_capacity/outcomes/test_summary.md)。

## 2026-10-08：Task041 Review V10-r2 W0.7 reduced-p6现场进度

唯一warm matched-cell consumer（Invocation `10d761079d90473dadce79d3f7eb6457`）在top P4因子构造阶段因process-tree RSS达到`53,541,888,000 B`、超过`53,221,163,008 B` cap而受控停止。Public-to-finalizer wall `2350.819163285 s`，V5 ledger 160项且此Invocation恰一项；finalizer为`controlled_stop`、常规检查7/10，清场和RSS下降检查通过。没有启动第二场。

外层service只记录public command开始/结束，不代表consumer没有setup。consumer内部44条marker已到one-cell factor、bottom P4 factor/Woodbury、top full action及top P4 trace/port；bottom矩阵64966²、NNZ 27,929,686且因子live，top矩阵64966²、NNZ 39,242,250但无factor-ready记录。port-ready后源码进入`ResearchExactFactorInverse`，其`ksp.setUp()`含symbolic/numeric而生命周期事件未向marker转发；故停点仅能定位到顶侧factor构造区间，不能拆symbolic/numeric或把整体RSS全算作factor。反馈门、outer、五残差、recovery/physics均未到达。详细原始SHA、内部/外层资源样本见[Task041 V10 measured progress](task041_mpi1_shortwave_hybrid_capacity/outcomes/shortwave_measured_progress_v10.md)及[Response V12](task041_mpi1_shortwave_hybrid_capacity/response_v12.md)。

匹配h的均匀W控制已有serial pass，但测试在MPI size≠1时skip，因此MPI2仍not_run；下一步只审原测试分布式trace/坐标helper的窄适配，不把skip当pass。下一场数值运行先要有顶侧factor symbolic/工作区估计或有界分配计划。W0.7完整目标、2 TB容量和48 h目标仍未达。

## 2026-10-07：Task041 Review V9当前进度（含H0历史基线）

**H0背景与基线。** 为判断已有W短波长工作量，按H0纳入的两场旧5 nm、p6/h4、M480、MPI8×1 consumer共同`consumer/markers.jsonl`阶段边界对照墙钟，并流式读取两份各1980行side RHS审计。两场分别完成1920/1920 formal response与各自残差/物理门；H0当时较新的Oct 3场public-to-finalizer为`202124.563261555 s`，约56.146 h，超过48 h目标。两场运行源码不同且均`performance_not_isolated`，不能用差值证明某优化因果或收益。H0机器记录是其完成时点的只读快照，不覆盖后续W5 fixed-H6新场。

**方法与发现。** 使用相邻marker差值，不把summary里的嵌套KSP/PC计时叠加到阶段wall；monitor独占时间没有marker，保持`unknown`。两场内部KSP迭代合计相同，均30296；较新场P4回代和精化各比旧场多8686次。它们解释了工作量并不等同于KSP步数，但不能换算成精确秒数或归因给A6。局部A6 RHS测量不代表完整工作流；较新场modal相邻marker段多约`12092.900 s`而outer段少约`288.119 s`，因果仍未分离。

**H1当前结果与路线边界。** H1 fixed-H6组件门serial/MPI2测试通过；唯一13.5 nm Si场与唯一W5/p6h4/M480/MPI8 fixed-H6 public/service场都通过各自原五项真残差、恢复、physics与十项finalizer。W5为49 outer、五项残差最大`4.87285789944735e-9 <= 5e-9`、315次总`S_H`、finalizer wall`59914.951233018 s`，专属job-cgroup峰`41376940032 B`；两场都保持`performance_not_isolated`，都不能外推W2或0.7 nm资格。2 nm已有SLEPc PEP/TOAR，旧consumer在历史repeat门停止、formal为0/4800，`ncv/mpd`未记录；不再提出迁移TOAR。0.7 nm现有一个缩减p6/h0.70/M400 pilot `.dat` 和来源派生材料候选record，输入可枚举1292个external-mode候选；producer packet、QEP/FE结果与容量资格仍未获得，Full 0.7 nm目标、2 TB和48 h尚未达标。

**W5当前结果与下一步。** 10月3日完整W5已有legacy-native validator确认的数值/packet/layout身份，包括input/physical/resolved SHA、M480/MPI8、600 external keys和packet manifest/identity；不是缺少数值身份。提交`ce31f3738f469a04d23c50af0a7c7306afde3b38`在注册W5 fixed-H6分支复用旧validator/binder，保持13.5/2 nm新profile及普通legacy默认。唯一W5 fixed-H6 public/service场现已完成并通过原数值、P4/recovery/physics与finalizer门；旧producer资源仍`unqualified`，新场资源独立记录。下一步转到已有W2/M1200/MPI8 packet的只读准备，保留旧consumer负结果与容量风险；H2尚未启动，H3–H4未完成。细节见[Task041 V9 outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/hybrid_0p7nm_2tb_48h_v9.md)、[W5机器记录](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v9_fixed_h6_public_5nm.json)、[W2只读计划](../results/task041_v9_w2_fixed_h6_readonly_preparation_20261007/w2_readonly_plan.json)，SHA `e7f33e11636fc541958a343fae037cff0f14f91568751f1ba62f16ecc89f5aab`，和[Response V11](task041_mpi1_shortwave_hybrid_capacity/response_v11.md)。

## 2026-10-06：Task041 V9 W5 legacy路由与owner计数定向测试

九文件实现已提交到当前任务分支，HEAD为`ce31f3738f469a04d23c50af0a7c7306afde3b38`，普通默认未改变。测试按attempt分开记录：初始serial收集7项，6 passed、1 failed；失败是worker fixture错误地期望CPU map为`None`，生产consumer会把历史默认规范化为`(1,2,3,4,5,6,7,8)`。单行test-only修正后，定向serial三节点通过；MPI2两个test350节点每rank各2 passed。受控非有限PC路径的RuntimeWarning在两次成功attempt中原样保留。该结果只证明路由和小型求解器合同，不是W5真实packet全量验证、MPI8落核或FE结果。

| Attempt | 结果 | 父 `CLOCK_MONOTONIC` wall | 证据 |
|---|---|---:|---|
| 初始serial | 6 passed / 1 failed；`-x`后两个test350 selector未执行 | `10.002066798973829 s` | [stdout](../results/task041_v9_w5_legacy_count_serial_20261006T074100Z/serial_pytest.stdout.log)、[attempt](../results/task041_v9_w5_legacy_count_serial_20261006T074100Z/serial_pytest_attempt.json) |
| 定向serial修正后 | 3 passed，保留1个故障注入RuntimeWarning | `10.00147465406917 s` | [stdout](../results/task041_v9_w5_legacy_count_serial_retry2_20261006T075129Z/serial_pytest.stdout.log)、[compact](../results/task041_v9_w5_legacy_count_serial_retry2_20261006T075129Z/serial_compact.json) |
| MPI2 | 每rank 2 passed，保留1个故障注入RuntimeWarning | `5.00106007209979 s` | [stdout](../results/task041_v9_w5_legacy_count_mpi2_20261006T075409Z/mpi2_pytest.stdout.log)、[compact](../results/task041_v9_w5_legacy_count_mpi2_20261006T075409Z/mpi2_compact.json) |

三次pytest父wall各按attempt唯一计入V5；ABI/static与未启动pytest的线程preflight失败不计。V5 ledger现130项，SHA `11679a139bbcd5f8a40a7b1758a9434df396d50c2e069fd46f115620d2a5c7f4`。保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`仍原样保留。

## 2026-09-30：Task041 Review V8 5 nm 正式 consumer 终态

运行源码 `d86ee4afb352304c9ff0d5042256ad9a7d0c9a4f` 完成注册的 W、5 nm、p6/h4、M480、MPI8×1 cell-condensed consumer，1920/1920正式响应及RTA/EH/衍射输出完成；五项true residual和恢复/物理门通过，`R/T/A/A_volume=0.7331842733877258/0.00022009869572838214/0.2665956279165458/0.2665962726230213`，closure `6.447064755388254e-7`。worker自然exit0；public和finalizer因结束HEAD `499c25de74c30ed0bdee17180f5315765f35efbe` 与运行SHA不相等而保留exit3/failed，差异仅是运行中获准的五条文档路径，属于身份合同冲突，不是数值失败。24 h目标未达到。

worker wall `189308.766050059 s`（`52.585768 h`），public-to-finalizer wall `189323.841971047 s`（`52.589956 h`）；旧`53.239672 h`是worker口径，与当前worker同口径约低`1.23%`。process-tree/authority峰分别`43,153,915,904/43,858,726,912 B`；cgroup `memory.peak=43,867,639,808 B`是历史计数器峰，不能称采样到的`memory.current`峰。cap/warning/reserve为`53,221,163,008/47,899,046,707/412,316,860,416 B`，job/cgroup swap为0；global swap与pswp按V8保留为观察值。并行邻任务未触碰，性能不作无竞争资格。详见[终态outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/formal_5nm_2nm_v8.md)与[record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v8_formal_5nm_2nm.json)。

## Task041 V7 快照（进入 Review V8 前）

本次代码运行 source `c0a077212cc3dd0ed6989ba66ff44ca0a7cbce74` 完成G2c顶部列12/493/666三响应、7冻结PC节点与14独立Q回放；`e_x/e_A`、Q/PC、shared A4与side residual均过原门。G2c冻结输入由本场source生成；full/condensed只确认本场内布局输入匹配，未做G1跨运行组件hash比较。condensed响应合计比full慢`84.964 s`；524次P4 step0中521次原A4两门通过仍执行单修正，故不采纳“原门失败才修正”，也没有在G2c阶段提出更严的内部目标。后续已实现并分侧验证`5e-13`内部精化目标、最多两次修正，原最终A4门`1e-10`不变。service正常完成，authority/tree峰`42588479488 B`、swap bytes为0、pswpin/pswpout为0页，finalizer清场并只计账一次；与邻heavy并行，性能不作无竞争资格。`qualification_pass=false`是诊断资格边界；G2c策略的完整consumer、正式Schur/outer/RTA/EH/全场未运行。G2d随后以bottom/top两场分别完成固定manifest八项分侧target验证并通过原配对门；bottom原service exit3与派生25项复核、top exit0分别保留，仍未证明单个完整consumer双侧同时驻留时的资源或全场资格。G1/G2逐节点与G3热点建议见[Task041 V7 outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/causal_fix_5nm_v7.md)；以下历史正文保留。
## 2026-09-23：Task041 Review V6 组件结果

13.5 nm cell-condensed Hybrid 的五项 true residual/物理 Gate 与 H2 数值向量通过；Full3D secondary 未运行，旧 H2 资源合同令总 checker fail。5 nm fixed-eight full→释放→cell-condensed 完成16次响应，8对中6对通过；top formal column 12、493 的 `e_x/e_A` 超过原 `1e-8` 门。cap64 只授权该场；Finalizer 已执行并唯一计账，但状态为 `failed/service_boundary_failure`。完整5 nm consumer、RTA、EH、24h 未运行。详见 [V6 outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/transfer_fix_5nm_24h_v6.md)、[record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v6_transfer_5nm_24h.json)。

## 2026-09-22：Task041 R3i3 MPI8 tiny-FE 数值 Gate 收口

transfer-row consistency 要求不同单元对同一共享自由度给出的传递值一致；唯一 MPI8 tiny-FE 场在旧 full p4 bottom/Q 阶段测得 `1.3116919128020489e-11 > 1e-11`。原 p4 A4 `6.795828778707217e-11 <= 1e-10`，所以不能称 cell-condensed 失败；cell_condensed、PC、side.apply、top 未进入，root cause unresolved。

| 范围 | 当前事实 | 资格边界 |
|---|---|---|
| 资源/终态 | tree/authority 峰 `4636389376 B`、dedicated current `2565689344 B`、PSS/USS `2828743680/2582614016 B`、minAvailable `2142846394368 B`、swap/pswp `0`；worker `rc=1`、termination null、unit `68.728670s`、清场完成 | 资源门未触发；不是正常求解完成 |
| ABI/NUMA | 8 rank、CPU1–8、complex128/Int32 通过；ABI `numa_maps` 为 default，FE 私有页未观测 | 严格 node0 membind 资格未取得 |
| 后续 | 13.5/5/2nm 新流程 not_run；旧5nm/QEP保留 | master_merge `NOT_APPROVED`，不自动重试 |

证据：[R3i3 compact v2](../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/run_20260921T195057.555038315Z/r3i3_compact_v2.json)；V5 ledger 已追加 `68.728670s`，累计 `7668.882139588s`。生产默认未切换，R3–R6仍未完成。

## 2026-09-22：Task041 Review V5 R3h8 p4 凝聚阶段（R3–R6尚未完成）

p4 单元凝聚先消去单元内部未知量，解较小的保留系统，再回代恢复完整 FE/端口修正，并用原 A4 和完整残差复核；不放宽逆或精度。p6 已凝聚，不重复消元。Task041 当前仅提供显式 cell_condensed 研究后端，默认 full 与正式 runner/workflow 不变。

R3c 是早期 synthetic 单端口资格，R3d2 才证明双端口/preallocation；R3f 是 p4/port 完整逆对照，R3h5 是 side/backend 回归，R3h6 才是同一 side/layout old/new Q/PC tiny FE。R3h6 不代表正式 MPI8、13.5/5/2nm、大模型资源或性能资格，R3h1–3 的 rc59/gdb/trace 负历史和 Cython 未证实根因保留。七个源码 SHA、donor_manifest、raw 索引和结果入口见 [Task041 R3h8 record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v5_condensed_speed.json)；冻结摘要见 [R3h7 compact](../results/task041_review_v5_cpu_numa_condensed_speed/r3h_validation_20260921/r3h7_compact.json)。R3h8 已一次追加 `288.010923037 s`，累计 `7600.153469588 s`；后续文档纠偏未再计费。当前只继续 socket0/node0，正式 MPI8 规划 CPU1–8/membind0；node1 修复/双路比较暂停，5/2nm完整流程及R3–R6仍未完成。

## 2026-09-21：Task041 Review V5 R1i 2666 复测（历史快照）

R1i 仅把 BIOS Memory Frequency 从 `Auto` 改为 `2666 MT/s`，其余保护、刷新、风扇与系统设置不变；这是工作站 CPU/NUMA 内存复制诊断，不是2nm物理模型。local socket0→node0 三窗 `35.63788506479269 / 35.664033252580786 / 35.6967308849817 GB/s` 稳定；local socket1→node1 为 `35.648371306083156 / 31.66995975917892 / 11.024863223982754`，cross socket0→node1 为 `23.562553384022838 / 22.956933903624012 / 13.10402684910857`，两条 node1 路径仍骤降；cross socket1→node0 为 `23.408224743881927 / 22.924688775860275 / 21.682633764800535`，约降7.37%。因此首窗正常不算修复，CPU1仍未准入，R2 blocked。
两批 `rc=0` 并清场；43 PCI raw、43 BMC 文件、688对温度值、六个 TEMPLO 和两个 TEMPMID 事件绑定于 [R1i compact v3](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v5_cpu_numa.json) 的 tracked 记录及 ignored compact。cross P1-DIMMC1 TEMPLO sample4→5 的时间括号按PCI `65→67°C`，异步BMC为`65→66°C`；after_load后续MID置位，触发时刻未知。`TEMP_MID 93→95°C`仍仅只读评估，未改阈值或保护。

## 2026-09-20：Task041 Review V5 R1h 跨 NUMA 复现（历史，已由R1i更新）
R1h 是 Task041 工作站 CPU/NUMA 内存复制诊断，服务于2nm计划但不是2nm物理模型。CPU socket0 的 OS CPU1–8 → memory node1 三窗为 `22.648688106036644 / 21.977584096329075 / 7.395682818558859 GB/s`；CPU socket1 的 OS CPU25–32 → memory node0 为 `19.789193732901627 / 19.759391333017003 / 18.843317623093906 GB/s`。前者第三窗较首窗约降67.35%，后者约降4.78%；状态为 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_ANOMALY_REPRODUCED_NO_UNIQUE_CAUSE`，R2 blocked。

本批 driver rc0、父侧 wall `629.724913916 s`，16 worker 三窗完成并清场；两阶段均观察到预期远端 node `8/8`。22 hardware samples/110 final-read/44个48行MSR文件成功绑定，358 resource samples 的最低 MemAvailable 为 `2114795454464 B`，新增 global swap delta 0；活跃平均 Bzy_MHz 约3.6GHz且 CoreThr=0。16 worker minor/major/stime delta、CPU wait 比和共享 cgroup throttle/high/max/oom 字段均无异常，但完整 process-tree RSS / cgroup memory.peak 未测。R1h 不证明硬件损坏或唯一热控根因；R1e/f/g 与所有历史负结果保留，[R1h compact](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v5_cpu_numa.json) 为证据入口。

历史维护建议（R1i 已执行但未解决）：R1i 已实际执行 Auto→2666 MT/s 对照，node1 路径仍未稳定；原边界为不改电压、Enforce POR、热保护、刷新/纠错。

## 2026-09-20：Task041 Review V5 R1d-B 匹配负载负结果（历史）

Task041 的钨（W）2nm D1e 终态仍保留原 `IMPLEMENTATION_FAILURE`；随后 R1d-B 只做了一次有界 CPU/NUMA 匹配负载，不能把 driver `rc=0` 当硬件资格通过。CPU0/socket0/node0 三个 60 秒窗口总吞吐约 `32.18 GB/s` 且稳定；CPU1/socket1/node1 为 `33.2632 / 28.3382 / 9.2660 GB/s`，第三窗比首窗约低 `72.14%`。两侧启动与 near-end first-touch/NUMA 观察均 `8/8` local，活跃频率约 `3.6 GHz`、CoreThr=0，DIMM 观测峰 `64/78°C`、状态 ok；原因仍未闭合，当前分类为 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_COLLAPSE`。

R1d-B 父侧 wall 为 `630.795106023 s`、driver rc0，16 个 worker 均自然完成；精确 raw/hash、资源采样、硬件采样和清场见 [Task041 R1d-B outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/cpu_numa_condensed_speed_v5.md) 与 [compact record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v5_cpu_numa.json)。R2–R6、R3 p4 草稿测试和新负载保持 `not_run`；无硬件/BIOS/寄存器改动。

## 2026-09-20：Task041 D3a / D1e 终态（当前）

Task041 的钨（W）2nm、p6/h1.5、M1200、MPI8×1 D1e 已终止。producer QEP packet 已完整保存；consumer 在两侧合成 modal Schur 重复一致性检查处以 `IMPLEMENTATION_FAILURE` 退出。该检查的两次样本都由 bottom+top 合成，不能归因于 top；`top_construction_cleanup` 是退出清理 marker。失败值为 `relative=4.427612e-05`、`max_column_relative_error=1.169058e-04`，限值 `1e-10`。这与 32 个 modal 小 RHS 的内层 `reason=2`、true residual `<=0.01` 是不同门。

本次最终记录为 40 行（8 probe+32 modal，bottom/top 各16），formal Schur `0/4800`，outer FGMRES `not_started`/0，RTA/full field `not_run`。producer/consumer wall 为 `29504.116038094042/135717.4772190291 s`，public total `165222.44361121487 s`，finalizer charged `165228.433265082 s`；finalizer status 为 `failed/service_boundary_failure`，不是 PASS。权威 service process-tree RSS peak `642483171328 B`，cgroup peak `647904940032 B`；global swap 从 `8192 B` 基线新增 used `290816 B`、pswpout +71 页，job/cgroup swap 为0。这里的 process-tree RSS / cgroup memory.peak 口径保持分开。D3a 当时的 R1–R6 `not_run` 是历史阶段记录；R1d-B 已在上方单列。

producer packet 与 32 shards 保留；终态 public `supervisor_summary.json` 已存在，既有 producer validator `rc=0` 且 `producer_resource_qualified=true`，但 consumer-only restart 未运行，故仍不是 consumer-only reuse qualified，p4 factor/未完成 Schur/native workspace 没有 checkpoint。旧 D2a 运行中段、D1c/D1d 修复链和全部历史负结果保留，canonical 运行 source `bde0686891af10bb489e4b1cb14500791cb50351` 未被本报告修改。证据入口：[Response V8](task041_mpi1_shortwave_hybrid_capacity/response_v8.md)、[D3a record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_d3a_terminal_20260920.json)、[terminal summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/2nm_d1e_terminal_20260920.md)。

## 2026-09-20：Task041 D2a / D1e 运行中（历史快照，已被上方 D3a 终态覆盖；as-of 01:19:51.480911341Z）

Task041 的模型是钨（W）、2nm、p6/h1.5、M1200、MPI8×1；Schur 是供外层迭代使用的模态耦合预条件矩阵。2nm D1e 已实际运行，不能再沿用旧的“尚未启动”表述。producer QEP 已完整写入
selected-mode packet；consumer 仍在 modal/Schur 候选阶段，formal Schur response `0/4800`，outer
FGMRES `not_started`、outer response `0`（分母不适用），RTA `not_run`，因此没有数值 PASS 或完整容量资格。21 个小 RHS modal
样本（bottom13/top8）给出的固定均值外推为 `133.57896112787233 days`，仅为 derived
sample arithmetic，不是 ETA；21/32 是重复样本，不是 formal 进度，21 行均 `reason=2`、
`explicit_true_target_reached=true`，最大 `relative_residual=0.009981656767193032 <= 0.01`，但不等于最终全局残差。当前 process-tree RSS / cgroup memory.current 分别为
`642483105792/647585968128 B` 的冻结括号值，非完整运行峰值。

运行 source 为 `bde0686891af10bb489e4b1cb14500791cb50351`；报告文件在 detached worktree，
不改变运行 checkout。详细身份、packet hash、memory tail binding 与 reuse 前置条件见
[Task041 Response V7](task041_mpi1_shortwave_hybrid_capacity/response_v7.md) 和
[D2a record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_d2a_progress_20260920.json)。
旧 C2/V4 段落继续作为历史保留。

## 2026-09-16：Task041 C2d 共同布局离线复核收口

Task041 的 C2 已完成一次共同布局组件运行；C2d 没有重启或重算，而是修正既有摘要的
`common_layout_equivalence.apply_count`（`8 → 16`）并用原始 artifacts 复核。原 service
终态保持 `PAIRING_SETUP_FAILURE / service_boundary_failure`、systemd exit3；只有离线
派生视图判为 `COMMON_LAYOUT_EQUIVALENCE_PASS`。这表示同一次 side layout 下的 8 对/16
响应检查通过，不是完整 Schur/outer/RTA、跨 fresh-run row identity 或双侧 full 资格。

| 登记项 | 结果与边界 |
|---|---|
| 源码 checkpoint | `caeb678225d63f16bd95272ba60b08b16caf36af`；C2c raw/checker 绑定源 `5b57375d50c777abb5d0096db843095683f49b5f` |
| C2 身份 | `task041-c1c-common-layout-equivalence-5b57375d.service`，Invocation `a8eac10299194a9a98d0ed18adfdac00`，MPI8、CPU1–8、数学线程配置1 |
| 组件响应 | `16/16` 主响应、`8/8` pairs；`max e_x=3.0316012438358734e-9`、`max e_A=8.229180550916894e-9` |
| 组件 wall | `1981.6339287383016 → 1454.4546840919647 s`，减少 `26.6033%`；仅同进程诊断，不是完整冷启动提速 |
| 资源 | 全树 RSS `51501744128 B`，硬 cap `53221163008 B`；不移除旧 S1f 双侧超 cap 证据 |
| 账本 | used `17762.27669256989 s`，shared remaining `3837.723307430111 s`，SHA `e5803851257eabd643be7048e81fae2c8d5e9957c4309c7f433b75ddd3805e27`；C2d 文档 JSON/diff 检查另计 `0.066910437 s` |
| 证据 | [Response V5](task041_mpi1_shortwave_hybrid_capacity/response_v5.md)、[C2c index](../results/task041_side_balh_component_audit/c2c_validation_20260916_5b57375d/c2c_offline_review_index.json)、[V4 compact](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_common_layout_equivalence_v4.json) |

旧 R2/R2g 的跨 fresh-run `PAIRING_IDENTITY_UNPROVEN`、S1f 的
`53331742720 B > 53221163008 B` 资源受控停止、旧 H3 事故和原始 C2 failure 均保留。
13.5 nm、full 5 nm、full Schur/outer/recovery/RTA、QEP 与额外 optimized run 仍
`not_run`；后续 2 nm 方向尚未启动。

## 2026-09-16：Task041 Review V4-A0 历史启动前阻塞（保留）

V4 的目标是把 legacy 与 V2 owner-transfer/伴随实现放在同一侧、同一 mesh/MPC/凝聚布局和
同一 p4 factor 中逐项比较，消除旧 R2 fresh-run 凝聚行编号无法对应的配对缺口。当前宿主
仍有受保护的 Full3D heavy 作业，故启动前 Gate 为 `BLOCKED_BY_ACTIVE_HEAVY_JOB`；C1 尚未
实现，C2/C3 和 16 项主响应均 `not_run`，没有本轮 RSS、提速或 response 等价结论。

| 维度 | 当前事实 |
|---|---|
| source / branch | V4 review commit `b5d0a39e8f85a2c63d56df28fb8414836e5aef3b`；`codex/20260902-task41-mpi1-shortwave-hybrid-capacity`；clean |
| scope | `representative_rhs`；`common_layout_equivalence` 仅为未实现的显式 opt-in |
| 主响应 | `0/16`、pairs `0/8`、layout/P/PH/PC/response 等价 `not_run` |
| 旧配对 | `PAIRING_IDENTITY_UNPROVEN`；不因 V4 阻塞改写 |
| 旧双侧资源 | S1f `53331742720 B > 53221163008 B`，`process_tree_rss_limit` 受控停止 |
| 证据 | [Response V5](task041_mpi1_shortwave_hybrid_capacity/response_v5.md)、[V4 compact](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_common_layout_equivalence_v4.json)、[A0 host snapshot](../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/active_heavy_protection.json) |
| 文档静态收口 | `json.tool` 与 `git diff --check` 均 exit `0`；wall `0.063355920 s`；ledger used `11145.708812196894 s`，shared remaining `10454.291187803106 s` |

本条只记录 V4-A0 的启动前事实；历史 R1/R2 实现、测试和负结果继续由各自 Task041 outcomes
保存。未创建新 service/daemon，未改变 ordinary/production default。

## 2026-09-02：Task040 Review V9 / Response V10 阶段回顾

这次工作从 side-factor 内存与接口风险开始：目标是在不改变裸物理算子、ordinary default、
physical DtN、M480 或 Task39 的前提下，验证较小的接口/局部预条件器是否能安全支持
Full3D。这里的“预条件器”只帮助迭代求解器更快找到解，不改变要求求解的物理方程；代价
是必须分别证明 source identity、局部算子、全局 residual 和资源生命周期，不能用局部
component 数值替代完整物理 Gate。

| 维度 | 当前 authority |
|---|---|
| 身份/状态 | branch=`codex/20260822-task40-hybrid-side-factor-pc`；pre-docs HEAD=`3bf9441425ca2dd4967551d5a43b2c7031049c0f`；Response status=`OPEN_AWAITING_REVIEW`；selective merge=`NO` |
| 为什么启动 | Review V9 要求在既有 source/full-spectrum 与 coarse 证据后审查低内存 side-factor 路线；不是放宽物理 residual 或资源 Gate |
| 冻结边界 | source bridge/full-spectrum/C0 为 p6h4；S3/LOR/external 为相应 h10/h5 fallback；MPI8、threads1、native complex128/int32；full-spectrum/LOR hard=45 GiB，C0 explicit oracle hard=192 GiB；未启动 0.7 nm PDE |
| 方法 | canonical source bridge；full-spectrum 两源 transform/screen；adaptive Stage A/B/C；C0 one-apply；fixed-LOR action-screen；physical bare-F external pilot |

### 实际运行矩阵

| 路线 | 结果分类 | 关键事实 |
|---|---|---|
| source canonical bridge | measured component pass | `V9_SOURCE_CANONICAL_BRIDGE_PASS`；MPI8 resource pass；source identity/roundtrip 通过 |
| corrected full-spectrum | measured numerical no-signal | 两源均有 one/r8/r16/r32/r64；`FULL_SPECTRUM_SWEEP_NO_SIGNAL`；RSS=`37884526592 B`、swap=`0` |
| C0 explicit coarse | measured numerical no-signal；watchdog metadata gap | one-apply `rho_coarse=6.778773552009804`；worker raw resource rows readable/pass；watchdog terminal sample gap不等于资源 pass |
| S3 J1 ×3 | failed implementation | 形状、canonical token、六层配置三次先后失败；没有 one-apply/FGMRES numerical Gate |
| fixed LOR L2 h10 / h5 | component action-screen pass / h5 refinement-action-screen negative | residual=`9.49183402945266e-9` / `3.743078556589845e-7`；211 / 256 steps；不是 physical V9-E positive |
| physical bare-F external h10 | worker numerical no-signal | corrected worker residual=`0.7349227023138162`；watchdog result/resource wrapper因旧 cleanup terminal bookkeeping待裁决 |
| C1、five-source、top/Hybrid、0.7 nm | not_run | C1由 C0 numerical Gate 阻止；fallback没有 qualified physical positive |

这些状态分别是 measured、failed 或 not_run，而不是把所有路线折叠成一个“成功/失败”数字。
full-spectrum 与 C0 的真实 numerical no-signal 使 V9-E 双入口成立；fallback 仍未得到
qualified physical positive，因此 qualified Full3D architecture candidate 和 0.7 nm capacity
仍为 `NOT_ESTABLISHED`。C1 是 `not_run_by_numerical_gate`；旧 watchdog 的 `next=C1` 仅是
non-governing raw metadata。

### 合并边界、局限与下一步

canonical/source、runner/watchdog、checker/benchmark、compact evidence/docs 需要按依赖组
分别审核；full-spectrum、C0、LOR、structured 和 external pilot 保持 research-only，三次
S3 failure 及其他未闭合实现路径是 do-not-merge。原始失败现场保留在 ignored results，不能
作为 Git merge 项。当前局限是没有 qualified physical positive，且 C0 watchdog 资源尾样本
仍是 authority metadata gap；因此不能外推 h-independent convergence、0.7 nm 可行性或
production default。

下一步不是自动运行 C1、five-source 或 0.7 nm，而是等待主控对 raw/resource 边界和 selective
merge 分组作最终裁决。证据入口：
[`Task040 task.md`](task040_hybrid_side_factor_pc/task.md)、
[`Review V9`](task040_hybrid_side_factor_pc/review_report_v9.md)、
[`Response V10`](task040_hybrid_side_factor_pc/response_v10.md)、
[`outcomes summary`](task040_hybrid_side_factor_pc/outcomes/summary.md)、
[`full-spectrum`](task040_hybrid_side_factor_pc/outcomes/full_spectrum_floquet_sweep.md)、
[`matrix-free coarse`](task040_hybrid_side_factor_pc/outcomes/matrix_free_galerkin_coarse.md)、
[`architecture handoff`](task040_hybrid_side_factor_pc/outcomes/full3d_0p7nm_architecture_handoff.md)。

## 2026-08-23：Task040 V1 Run B resource-stop closeout

Task040 在冻结 5 nm、1°、phi=0、S、p6h4、M480、MPI8 身份下完成了 T40-3 和 V1-1
组件证据；T40-3 是固定一阶人工截面传输的真实数值负结果，V1-1 是固定 scalar
Krylov 的 directional negative。随后唯一的 V1-2/V1-3 Run B 尝试在 exact oracle
ready/release（factor `3 -> 0`）后触发 `45 GiB` watchdog hard stop，峰值为
`48,380,153,856 B = 45.05752944946289 GiB`，swap `0`；没有 serialized V1-2
probe 或 V1-3 checkpoint。该结果是资源/生命周期停止，不是 transmission algebra 失败，
也不是新的 full-workflow memory tier。

两个此前的 Run B implementation-failure roots（resolved-config count schema、selected
manifest/catalog identity）和最新 raw root均保留；V1-3 为
`setup_started_but_not_ready / not_qualified_due_resource_stop`，numerical capacity
为 `NOT_EVALUATED`；V1-4 至 V1-7、Level B、top、full Hybrid 和 h3 scaling 为
`not_run_by_gate`。详见
[`Task040 V1-8 summary`](task040_hybrid_side_factor_pc/outcomes/summary.md)、
[`response_v2`](task040_hybrid_side_factor_pc/response_v2.md) 和
[`compact record`](../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_2_v1_3_run_b_resource_stop_v1.json)。

## 2026-08-10：Task037b frozen M10 结项与 Review V7 selective-merge capability

Task037b 在 reviewed Task37b source `361908dd71fc12734b8ac19881d6e0d3aaae5d56` 的
V7 选择性范围内登记冻结 M10 Hybrid iterative research capability。它是显式 opt-in
研究入口，不改变 ordinary direct Hybrid 默认，也不提前宣称已经发布到 master；master
发布仍受 full pytest 与 integrated anchor Gate 约束。

| 维度 | 结论 |
|---|---|
| 冻结模型 | p6/h10、modal p6/h10、13.5 nm、S、10° grazing、10/110 nm、M120/candidate240、MPI8 |
| 算法 | exact Hybrid action；action-consistent modal Schur；两侧 fixed whole-endcap ILU(0)+40-mode DtN Woodbury；right FGMRES90 |
| 数值/物理 | 792 iterations；五项 residual、bottom/top exact traction、recovery、own-physics、80 orders、canonical 与 `12+12` authority comparison 通过 |
| 资源/生命周期 | process-tree RSS `6018.57421875 MiB`（`5.8775 GiB`），swap `0`；M10 cleanup 顺序与生命周期 Gate 通过 |
| ordinary boundary | `research_only`、explicit opt-in；ordinary direct Hybrid/default unchanged |
| 排除路线 | 0.7 nm、参数扫描、fallback、历史 negative machinery、post-V7 scaling 和 production promotion 不在本次能力范围 |
| 下一任务 | Task37c `planned / no task yet`；未创建 task 文件或实现 |

入口与 compact evidence 见
[`Case101 README`](../benchmarks/cases/101_hybrid_iterative_block_solver/README.md)、
[`M10 qualification compact`](../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_mpi8_traction_aligned_full_qualification_v1.json)
和
[`memory closeout compact`](../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_memory_optimization_closeout_v1.json)。

## 2026-08-07：Task037 静态凝聚 Full3D 迭代正式结项

Task037 在 reviewed source `d8b16c349f7726b4873ce1932668c12a1ba78926` 的选择性
合入线上完成收口。最终数值 formal source 是
`0fcf08a3f09e3beb137212d41f411823cb2e24e8`；后续 test53、格式和文档合同变化
不改变数值结论。

| 主线 | 实际结果 | 状态与边界 |
|---|---|---|
| E0 Matrix-free DtN | 80/80 modes；C/D `0/0`；action/recovery 约 `1e-15` | component Gate pass；ordinary default unchanged |
| M3a iterative | p6/h10 MPI1/2/4/8 full solve 通过；MPI4 official true | explicit opt-in research baseline；不是 production default |
| canonical | active/full relative L2 `1.2553897989392794e-06` / `7.880394014572244e-07` | `1e-5` comparator pass |
| F/E | frozen ideal-capacity negative；E1 pass、E2 late residual `6/6` fail | controlled negatives；不生产化 |
| Task37b | Review V7 selective-merge qualified research capability | frozen M10 MPI8 已完成；master 发布仍受 full pytest + integrated anchor Gate 约束 |

docs closeout 前的 10 个 code/test selective commits、5 个 Case100 compact records 和最终文档见
[`task037_static_condensed_full3d_iterative/outcomes/summary.md`](task037_static_condensed_full3d_iterative/outcomes/summary.md)。

## 2026-08-03：Task036 direct Hybrid 受控结项与选择性整合

Task036 的目标是修复 Hybrid 在小掠射角、P 偏振和弱衍射通道下不能完整复现
Full3D 的问题。最终证明域分解和 M120 长程传播核心本身可用，但低维端口没有覆盖完整
joint-Cauchy 界面信息；因此停止继续扩大 direct 端口，把通用修复和最小 research oracle
选择性保留，ordinary default 不变。

| 主线 | 实际结果 | 数据身份 / 边界 |
|---|---|---|
| compressed direct Hybrid | M120/M240 未闭合完整界面与全部通道 | `controlled_negative / closed`；not production-qualified |
| strong trace | E jump `4.588e-15`；energy `1.531666e-5 > 1e-5`；固定通道 `77/96` | `research_only`；19个通道失败不能忽略 |
| exact FE trace-chain | one-cell Schur、endpoint Cauchy 与 full trace-chain 证明域分解 correctness | `research_only correctness oracle`；不是 scalable solver |
| M120 modal core | 40/60/100 nm selected-space exact FE 对照约 `1.59e-11–1.95e-11` | retained；不等于 complete global port |
| B1/C1 | B1 `d<=360` controlled negative；C1b/C1c 取消且未运行 | 不恢复 capacity/POD/96-RHS campaign |
| 0.7 nm / 2 TiB | 未得到通过精度和资源合同的 solver | `not solved`；不得写成 conditional estimate 已兑现 |
| selective commits | Group1 `7735a261...`；Group2 `a741ad1b...`；Group3 `4c9e1b9...` | Task036 final SHA `7a033400...`；完整历史留远程分支 |
| 当前测试 | Group3 serial `7 passed`、MPI2 recursion 每 rank `1 passed`；最终 compact targeted `24 passed` + DtN/alias `14 passed`；p2 Full3D ordinary/static PDE smoke 各 `1 passed` | combined suite 在41 passed/107.99s后由用户中断；exit2/KeyboardInterrupt不是代码 failure；小时级 full pytest `cancelled/not_run` |
| Task037 | V7 selective master closeout 已完成；E0/M3a/canonical 证据与 A–F/E 关闭表已登记 | `closed`; M3a 仅 explicit opt-in；Task37b 尚未开始 |

结项入口见
[`task036_forward_solver_bugfix_hardening/outcomes/final_summary.md`](task036_forward_solver_bugfix_hardening/outcomes/final_summary.md)
与
[`task036_forward_solver_bugfix_hardening/review_report_v8.md`](task036_forward_solver_bugfix_hardening/review_report_v8.md)。

## 2026-07-26：Task035c Hybrid逐通道与p6/h10内存闭合

Task035c 用低成本p2/h5定位Full3D–Hybrid弱衍射级误差，再以p6/h10 MPI8
完成六路径高阶authority。普通默认保持`standard_full`；p3/h7.5按用户范围
未运行。

| 主线 | 实际结果 | 数据身份 / 边界 |
|---|---|---|
| channel root cause | Full3D z向使用scalar CG(p)离散相位/端点导数；旧Hybrid使用连续beta/traction | p2/h5 measured diagnosis |
| p2/h5 fix | corrected M120/M160均12/12 power + 12/12 boundary-plane amplitude | diagnostic pass |
| p6/h10 physics | Full3D standard/static、Hybrid standard/static M120/M160六路径均12/12+12/12；residual/RTA/Avolume/interface/field pass | measured MPI8；source `244b62e1...` |
| Full3D static | peak `34.041→14.722 GiB`，下降56.75%；total `2581.55→260.74 s` | measured process-tree RSS，zero swap |
| Hybrid static M120 | rows/NNZ/factor分别下降67.17%/79.63%/67.88%；peak `11.077→7.544 GiB`，下降31.89%；total ratio0.343 | mandatory/preferred memory pass |
| Hybrid static M160 | peak下降29.50%；没有物理收益且更耗时/内存 | M120 selected；M240 not run |
| user 50% target | 未达到；峰值在record-and-release，不在modal coupling本身 | lifecycle engineering gap |
| rank study | MPI1 QEP biorthogonality fail；MPI2 terminal-drain resource authority fail | two controlled negatives；MPI4 not run by stop rule |
| scope | p3/h7.5、h13 adaptive、0.7nm、irregular/tetra/mixed static、new iterative均未运行 | compliant |

完整回顾见
[`task035c_hybrid_channel_memory_closure/outcomes/summary.md`](task035c_hybrid_channel_memory_closure/outcomes/summary.md)，
compact authority见
[`../benchmarks/cases/096_hybrid_channel_memory_closure/README.md`](../benchmarks/cases/096_hybrid_channel_memory_closure/README.md)。

## 2026-07-25：Task035b Review V2 setup、内存下限与最终通道续研

Review V2 在同一 fixed rectangular block grating 和执行分支上并行推进
精度、setup 与内存三条主线；普通默认未改变，未合并 `master`。

| 主线 | Review V2 结果 | 数据身份 / 边界 |
|---|---|---|
| 最强精度点 | fixed p5-trace/p6-interior h13 仍为 89,740 DoF、20,120 rows、10/12 power + 10/12 amplitude | measured MPI8；未达 12/12 + 12/12 |
| fixed-DoF z-node | h13 top2 为实际 8/12 + 8/12；h14 exact-reverse 为 7/12 + 8/12 | 两个 bounded controlled negatives；关闭该 lane；先验投影不作实测 |
| physical selective trace | physical expansion、periodic/exact-sequence、Stage4 row omission、pre-release hook 和 owner-aware MatShell 已有 fixture/correctness 能力 | actual DWR、formal runner、candidate/PDE count 均为 0 |
| setup/cache | h15 non-KSP cold/warm 19.242/6.141 s；h13 19.410/6.696 s | hash-bound setup/resource authority；不替代通道精度 |
| direct rank memory | h15 MPI1/2/4/8 peak 为 1.295/2.158/3.100/4.711 GiB | measured、0 swap；MPI1 是最低实测 direct 点，不是理论下限 |
| iterative | Jacobi、ASM/ILU、physical z-slab + DtN 三条 MPI8 screen 均在 200 iter 不收敛 | controlled negatives；无 official R/T/A/channel；后两条含 local factor |
| Hybrid / 0.7 nm | eligible candidate=0；Hybrid、M/DtN funnel、resource model v3 未运行 | fail-closed；2 TiB feasibility unknown |

当前 blocker 是数值/生产集成而非用户环境：reduced fixed-trace local-Schur
捕获与 standard full-p6 generalized recovery 尚不能在同一次正式 run 中
闭合。没有密码、ABI、MPI 或磁盘硬 blocker，也没有理由重复已经完成的 heavy
PDE。集中回应见
[`task035b_high_order_local_hp_resource_envelope/response_v3.md`](task035b_high_order_local_hp_resource_envelope/response_v3.md)。

## 2026-07-24：Task035b Review V1 显著通道恢复批次

Task035b 只研究 Task034 fixed rectangular block grating；原 G1/G2/Phase F
不规则几何全部为
`out_of_scope_by_user / not_run / not_a_completion_gate`。

| 主线 | 结果 | 数据身份 / 边界 |
|---|---|---|
| p4/p5/p6 baseline | 同一 h10 hexa mesh/hash 上资格化；p6 为 173,802 FE DoF、51,272 active rows | measured MPI8；best available discrete，不是 continuum |
| high-p condensation | assembly-time exact cell Schur + Floquet slave elimination；full p6 matrix 不再分配 | measured；opt-in research path |
| memory lifecycle | p6 full 35.024 GiB 降至 isolated 15.964 GiB；factor release/heap trim 后后处理不再叠峰 | measured process-tree；ordinary default unchanged |
| assembly optimization | latest p6 build 102.32 s；fixed h15 preallocation mallocs=0、build 61.61 s、peak 5.803 GiB | measured MPI8；tensor dedup/preallocation positive |
| p6/h15 | 84,492 DoF，scalar/vector/field/resource pass，significant channels 6/12 power、8/12 amplitude | controlled negative |
| fixed p5-trace/p6-interior h15 | 74,890 DoF preferred band；channels 6/12 power、7/12 amplitude | controlled negative |
| significant channel reference v1 | 机械聚合既有高阶 authority；12/12 通道冻结 power/complex amplitude/magnitude/phase numerical bands | best-available same-code convergence authority；不是 continuum truth |
| 失败通道 adjoint | 16/16 Hermitian adjoint、direct-adjoint 与 finite-difference verification 通过 | measured MPI8；entity localization 仍是 coefficient proxy，不是 actual DWR |
| DtN/port 根因 | q31 与安全 scaled buffer-1 均无恢复；manufactured phase/normalization authority 通过 | 两个 independent negative + algebra authority；不宣称排除所有共同 port error |
| Lane A directional h | z-only h14 7/12+9/12，z-only h13 10/12+10/12；x/y controls 负 | h13 89,740 DoF、20,120 rows、6.411 GiB，是最强实测但未通过 |
| R5 slab 判别 | h14 最大 R5 slab 单次二分得到 89,740 DoF，退化为 5/12+9/12 | controlled negative；按预注册条件关闭 split-position scan |
| global p6/h14 discriminator | complex amplitude 12/12，但 power 9/12 且 92,850 DoF | controlled negative；超过 90k cap 2,850 DoF |
| Lane B selective trace | reference complement/Riesz 与预算审计完成；physical selection 所需能力未闭合 | `capability_stop_not_run`；candidate/PDE count=0，不把审计 pass 写成候选 pass |
| condensed iterative parallel direction | h15 direct authority已绑定，未来唯一 GMRES screen contract 已冻结 | `capability_stop_not_run`；当前无 dedicated hook/history/factor-free inventory，不伪造实测 |
| regionwise h10 | p4-trace N105 为有效 accuracy negative；p5-trace N62 缺 66 gradient modes | measured PDE + structural audit |
| multi-goal DWR | independent R00/R/T adjoints 与 normalized R/T marker pass | measured MPI8 |
| classifier v3 | 252-cell projection/decay；p-up102、p-keep150、h-refine0 | research-qualified；production_qualified=false |
| Hybrid / 0.7 nm | eligible candidate=0；Hybrid、M funnel、0.7 nm PDE 未运行 | fail-closed；planning sensitivity only |

最终分类为 `PARTIAL_WITH_CONTROLLED_NEGATIVES`。Task035b 解决了“rows 下降但
内存不降”的工程问题：只有同时消除完整 matrix、inactive rows、tensor
重复、preallocation 浪费和 factor 生命周期后，NNZ、factor、peak 和时间才
按正确方向下降。Review V1 又证明预算内 structured z-resolution 是当前最强
精度杠杆，但单一方向性 knob 仍不能闭合全部弱通道；选择性 trace 和
factor-free iterative 的下一步受可明确实现的 research capability gap 阻挡。
剩余 blocker 是完整 diffraction-channel accuracy 与相应算法能力，不是环境、
MPI、MUMPS 或 residual，也没有需要用户处理的密码/ABI硬 blocker。

详细证据见
[`task035b_high_order_local_hp_resource_envelope/outcomes/summary.md`](task035b_high_order_local_hp_resource_envelope/outcomes/summary.md)
与
[`../benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md`](../benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md)，
集中回应见
[`task035b_high_order_local_hp_resource_envelope/response_v2.md`](task035b_high_order_local_hp_resource_envelope/response_v2.md)。

## 2026-07-21：Task034 WSL、固定几何高阶矩阵与 adaptive 决策收口

Task034 在 WSL Ubuntu 24.04 的 qualified complex ABI 上完成环境资格化与 post-merge hardening；Review V4 当前等待最终批准，未合并 master。

| 项目 | Task034 结论 | 数据身份 / 边界 |
|---|---|---|
| WSL/ABI | native complex PETSc/SLEPc/DOLFINx stack 通过，零 swap 监测和 watchdog 生效 | measured qualification |
| uniform benchmark | Case093 覆盖 p2/p3/p4 的 S 偏振固定几何序列；p3/h10 Hybrid 为 formal negative | measured；非 continuum proof |
| same-degree closure | p3/h3 与 p4/h5 M80/120/160 funnel 和 Full3D–Hybrid closure 通过 | measured accepted evidence |
| MPI | p3/h5 Full3D/Hybrid MPI1/8/16 identity 通过；MPI32 仅 exploratory | measured；不扩展全部矩阵 |
| supplemental resource stops | p2/h1、p3/h2、p4/h3 Full3D 只完成 assembly 后受控停止；factorization/full solve 未启动 | measured assembly + predicted upper；不得写成 solve |
| p4/h3 authority | 3035.139050935 s、80.537712097 GiB，采用 tracked process-tree compact authority | measured；40 行审计仅此两字段发生并已解决漂移 |
| graded-h | conforming mesh/Floquet/marker mechanism pass；三档 same-error compression 全部 controlled negative | research-only mechanism；field-driven adaptive 未资格化 |
| 0.7 nm | current-layout stress test 的多个单组件超过 2 TiB | engineering stress test；production DoF/M/peak unknown |
| merge | governance/docs/compact facts 可按 manifest 合入；未资格化 adaptive runner/mesh 保持 research_only_do_not_merge_yet | final Review V4 + user authorization pending |
| next | Task035 H(curl) field/goal-oriented adaptivity 仅完成 planning/theory package | 未执行 Task035 code 或 PDE |

统一 40 行事实表由 tracked compact fixture 在无 `benchmarks/artifacts` 的 clean checkout 中字节级重建；重型路径只作为 provenance string。详见 [`task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`](task034_workstation_wsl_adaptive_scalability/outcomes/summary.md)。


## 2026-07-17：Task033 Review V6 F0 与选择性合并收口

Review V6 接受 Task33 的用户缩减范围。F0 没有重跑 PDE，也没有修改 Maxwell、
Floquet、QEP、Hybrid coupling、solver 或 physical postprocess kernel；新增的是
D1 descriptor-only source audit、跨记录执行语义、预测偏差、completion checker、
exact manifest 和文档同步。

| 项目 | 结果 |
|---|---|
| direct 3D p3/p4 Floquet | Case090 MPI1/2/4 共 144 PDE，核心 Gate 全过 |
| QEP p3/p4 | Phase A p3/p4 组件与 selected MPI identity 通过；legacy 全阶 aggregate 保留 p1/p2 负结果 |
| matching trace p3/p4 | Phase B p2 MPI1、p3/p4 MPI1/MPI4 五条通过；积分加阶 delta 0；无 full gather/dense square |
| Hybrid/full3D | 复用 Task032 p2/h5、p2/h3 同阶同网格对照；行数降低 65%–69%，NNZ 降低约 59% |
| p3/h5 Hybrid/full3D | 同阶 closure 通过；Hybrid 2.618 GiB vs direct 7.781 GiB，未证明网格收敛或墙钟加速 |
| fixed-p equal accuracy | p3/h10 accuracy negative；p3/h7.5 由 Review V6 接受为 fixed-p clear success，并将 FE DoF/local-system rows/total rows/factor-NNZ/memory/指示性时间改善 2.571x/2.567x/2.548x/3.557x/1.606x/1.331x |
| p4 / variable-p | p4 target 当前主机资源受限；native variable-p H(curl) capability fail closed |
| adaptive/graded/buffer/1 TiB | adaptive 与 1 TiB 更新移交下一独立任务；buffer 等待 defect geometry；不再阻塞 Task33 |
| prediction audit | p3/h10 1.947→1.980 GiB；p3/h7.5 2.463→3.667 GiB；旧模型未重校准前禁止用于 1 TiB |
| completion/merge | reduced scope complete；original full scope partial/NOT_RUN；精确 selective merge 获批，whole branch 禁止 |
| source | Stage1 `6613f94...`；Phase A `bb830ba...`；Phase B `bd7a602...`/`9ac29db...`；Phase C `b636444...` |

详细结论见
[`task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md`](task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md)。

## 1. 文档定位

本文档记录项目从初始代码审查到 Task033 当前阶段的完整开发进程，面向：

```text
- 项目开发者；
- 后续 Codex/ChatGPT 任务；
- 新加入的维护者；
- 需要判断当前能力、历史路线和下一步优先级的用户。
```

本文档不是逐次实验的原始日志。详细证据仍位于：

```text
docs/taskXXX_*/task.md
docs/taskXXX_*/outcomes/
docs/taskXXX_*/review_report*.md
```

本文档负责回答：

```text
1. 每个阶段为什么开始；
2. 实现了什么；
3. 哪些结果成功；
4. 哪些路线失败或被替代；
5. 当前主线最终保留了什么；
6. 项目现在能做什么；
7. 尚未完成什么。
```

更新时间：

```text
2026-07-26
current branch = codex/20260726-task35c-hybrid-channel-memory-closure
Task028 status = V4 closed and merged to master at 2f9e56d
Task029 status = diagnostic_success; review V2 closed; merged to master at bfb6586e
Task030 status = final review V3 passed and merged to master at 545165b
Task031 status = strong_memory_success_slow_but_memory_efficient; Review V2 passed; merged to master at dae03170
Task032 status = hybrid_direct_engineering_success; Phase 0-10 complete; Case080 302/302; h2 locked by mandatory memory prediction gate
Task033 status = review-v6 reduced scope complete; fixed-p p3/h7.5 clear success with qualifications; original full scope partial by transfer
Task034 status = PASS_WITH_QUALIFICATIONS; Review V3 blockers closed; final Review V4 and user merge authorization pending
Task035 status = Review V6 research baseline; Task035b successor active
Task035b status = CLOSED_WITH_CONTROLLED_NEGATIVES by Review V4
Task035c status = mandatory channel/memory closure complete; 50% Hybrid memory target remains open; response_v1 pending review
```

## 1.1 2026-07-15 最新更新

Task032 Review V1 接受 13.5 nm h5/h3 物理与数值实现，但在选择性合并前要求表格化回顾、
0.7 nm 资源评估、长期规则、manifest 和项目文档闭环；addendum 又明确撤回 pure-modal/y-invariant
优先主线，保留未来复杂 3D 两端。当前 review follow-up 的统一结论为：

| 项目 | 结论 | 数据身份 / 边界 |
|---|---|---|
| 13.5 nm Task032 | `hybrid_direct_engineering_success` | measured/derived，h5/h3 same-grid |
| h2 | `not_run_by_gate` | predicted 两方法均失败，未运行 |
| 参数 1–10° S/P | 30/30 interface/API smoke | measured M4；非 production qualification |
| h3 best direct memory | 3.224 GiB，较 augmented -16.31% | measured simultaneous worker RSS |
| full3D→Hybrid algebra | h5/h3 rows -68.62%/-65.35%；NNZ -59.14%/-59.68% | derived from measured rows/NNZ |
| current direct at 0.7 nm | not resource feasible | analytical projection，非 PDE run |
| 1 TiB final Hybrid | credible conditional opportunity | 尚未证明，需 h/p + scalable modal + iterative |
| ordinary default | unchanged | explicit opt-in only |

`M` 的统一含义是每个传播方向保留的中间截面模式数；M160 即 160 forward + 160 backward =
320 internal modal amplitudes。未来主线是 exact complex 3D FEM ends + generic `epsilon(x,y)` modal
middle；y-sector/pure-modal 只作当前简单结构的可选诊断/reference。

历史顺序已由 Task034/Task035 权威更新：Task034 完成 WSL、fixed-geometry benchmark 与
controlled graded-h 决策；Task035 为 H(curl) field/goal-oriented adaptivity；其后分别启动
scalable modal core、low-memory Hybrid iterative 和未冻结编号的
13.5→5→2→1→0.7 nm wavelength continuation。详情见
[`task032_0p7nm_scalability_assessment.md`](task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md)
和 [`response_v1_review_followup.md`](task032_hybrid_fem_modal_direct_baseline/response_v1_review_followup.md)。

Task032 Phase 6f--10 已闭合。clean h5/h3 M120/M160 记录完成物理 E/H、接口连续、
体吸收、五个选面、逐衍射级输出和 augmented/Modal-Schur 对照；两档 M120->M160
最大 total delta 分别为 `6.24e-14/1.22e-14`。h3 M160 相对同网格 full-3D
的 R/T/A 差为 `-2.12e-7/-2.42e-6/+2.63e-6`，场与吸收 Gate 通过。
30 组角度/S-P 参数入口 smoke 全过，但不升级为全区间 production qualification。

六条 clean MPI4 M160 外部内存记录全部数值通过、零 swap。h3
augmented/Schur-fast/Schur-memory-minimal 为 `3.853/3.998/3.224 GiB`；只有顺序
factor 生命周期相对 augmented 下降 `16.31%`。h2 的网格尺度与 factor-payload
预测分别为 `5.365/6.170 GiB` 和 `11.647/13.394 GiB`（中心/上界），均未过
4/5 GiB 强制 Gate，因此 h2 按任务书未运行。最终 Case080 checker 为
`302/302 passed`，分类为 `hybrid_direct_engineering_success`；Review V1 已完成，当前等待
follow-up 复审和用户许可后按 manifest 选择性合并；Task033 在该闭环完成前不启动。

Phase 6a/6b/6c 已按小步完成。上下局部三维 p2 Nédélec/Floquet 网格只覆盖外边界到 z=10/110 nm 接口，中间 100 nm 不再生成三维体单元；每个局部系统只装配其真实拥有的一侧外部 40-mode Fourier-DtN。内部耦合新增分布式 `M x N` trace projection、`N x M` 正/负 traction、`M x M` 负迹映射和无 growing inverse 的 `P+/P-`，内部 unknown/equation 均为 `2M`，没有 dense `N_interface^2`。

Phase 6c 的 MPI 路由按结构化 `(x,y)` cell owner 只交换接口点值，不聚集完整 field/mode；collective 已移出 DOLFINx interpolation callback。修复测试辅助函数的临时 PETSc 包装器后，最终 serial 为 `4/4`、MPI2 每 rank `4/4`、MPI4 每 rank `4/4`，所有具名测试容器均已删除。该子步边界是 block assembly；随后 monolithic augmented matrix 与 MUMPS algebra Gate 已按下一段完成。

Phase 6d 已建立 rank-major monolithic PETSc AIJ：每个 rank 连续保存自身 bottom/top rows，最后一个 rank 再保存 `2M` 内部 modal rows，从而把两个独立 local distributions 合法拼入普通 MPI AIJ。unknown 为 `[u_bottom,u_top,a_b+,a_t-]`，outgoing amplitudes 只通过稳定 `P+/P-` 消元；MUMPS 设置 error-if-not-converged 并显式计算 `||Ax-b||/||b||`。h10 两条解析 Bloch mode 的 serial/MPI2/MPI4 均为每 rank `3/3`；MPI4 矩阵 `2432 x 2432`、`251720` nnz、真相对残差 `3.732133e-13`，setup/solve `0.046960/0.003048 s`。这只分类为 `augmented_algebra_pass`；真实 Phase 3 QEP basis、M 收敛、接口 E/H 连续、official R/T/A 和 full-3D 比较是下一步。

Phase 6e 已完成真实 QEP h5/M2/4/6 研究漏斗，并在 clean source `5c1f12e610dd8c6040389c44c31584ab7fba66cd` 生成 h5/M6 MPI4 集成记录。修复了正负 basis 重复 Poynting evaluator、SLEPc 超额 `nconv`、Windows bind mount 容器内 Git status 卡顿、Nédélec 边界点任意 source-cell 路由和近简并 block threshold 五个问题。clean M6 的 10 个集成 Gate 全过，单体 `13744 x 13744`、约 `1.4704e6` nnz、真残差 `1.8590e-12`；研究漏斗 M4->M6 R/T/A 变化约 `1e-12`，Case080 为 `294/294 passed`。当前仍不称完整 physical pass：pointwise H jump、体吸收、中间选面重建、h3 和 simultaneous RSS 未完成。

### 2026-07-14 前序更新

Task032 已从 Review V2 通过后的 Task031 clean merge `dae03170` 启动。旧目录 `fenics_vector_maxwell_floquet_demo_v2_parallel` 保持 Task031 分支和既有未跟踪材料不变；新目录 `fenics_v3_hybrid_FEM_modal` 从更新后的 `origin/master` clean clone，并创建、推送 `codex/20260714-task32-hybrid-fem-modal-direct-baseline`。迁移、环境和 smoke 证据见 [`task032_hybrid_fem_modal_direct_baseline/outcomes/`](task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md)。

Phase 0 确认本机合格镜像提供 PETSc complex128、DOLFINx 0.10.0.post2 和 SLEPc 3.24 PEP/TOAR；compile/import、8 个 condensation/action 合同测试、最小 Stage4 和 h5 MPI4 target direct 均通过。最小 Stage4 首次暴露 flat preset 仍继承 `50 x 50 x 50 nm` 光栅块的旧回归；通过显式零尺寸 A/B 定位后，只修复三个 preset 几何字段并新增合同测试，原始命令恢复通过。h5 基线为 44,698 FE DoF、80 auxiliary modes、真相对残差 `1.3033e-11`，`R/T/A=0.0890216029/0.4425882787/0.4683901184`，闭合误差 `1.2124e-13`。

Phase 1 已加入默认关闭的 full-3D reference exporter：在 z=`10/30/60/90/110 nm` 输出 40x20 结构化 complex128 E/H，并显式保存 z=10/110 的 x/y tangential traces。接口在单元公共面时从中间模态区单侧取迹，384000-byte 冻结载荷受 64 MiB fail-closed guard 保护，不聚集完整 FE vector。

clean commit `c468c728...` 的正式 MPI4 h5/h3 reference 均通过：DoF 为 44,698/198,438，真相对残差为 `9.734e-12/9.923e-12`，闭合优于 `1.3e-13`；h3 `R/T/A=0.0046130314/0.5836533572/0.4117336114` 与历史 direct h3 一致。h5 与 h3 差异明显，因此 h5 只作快速开发、h3 作为主 reference，不宣称 h5--h3 网格收敛。Case080 已保存 clean identity、命令、image digest、field/diffraction hash 与自动 Gate，checker 为 `271/271 passed`。

Phase 2 已实现匹配 Stage4 x/y 轴的 quadrilateral 截面、`N1curl(p2) x Lagrange(p2)` 混合空间、双 Floquet orientation-aware 约束、无 slave-chain 的分布式 `u=Cq`、`C^H K C` 稀疏约化和原生 SLEPc PEP/TOAR QEP。完整 eigenvector 不聚集到 rank0；Phase 2 electric-L2 只建立稳定场尺度，Poynting/left-right 双正交仍留给 Phase 3。正式 MPI4 record 固定在 clean source `33211a4...`：air h5/h3/h2/h1.5 的 beta 解析相对误差严格降至 `29.5323%/5.58859%/1.12629%/0.454640%`，lossy h2 误差 `1.19656%`，当前材料 h3 beta 为 `0.0753551902+0.00178364869j 1/nm`；最大 QEP 相对残差 `1.8177e-15`，`+/- beta` 配对误差 `7.50e-16`，electric-L2 范数误差 `4.44e-16`。完整 serial suite 为 186 tests/10 skipped，MPI4 Phase 2 为每 rank 5/5，checker 为 `277/277 passed`。接口 coupling 和 Hybrid direct solver 尚未开始，下一步为 Phase 3 分类与最终归一化。

Phase 3 已实现由混合 E 场重构阻抗缩放 H、z 向 Poynting 分类、near-zero flux 的 `Im(beta)` 衰减分支、显式伴随 QEP 左模、`Q'(beta)` left/right 双正交、近简并 block inverse、正反向 identity 和相邻角度/模式数变化的 overlap tracking。全量 serial suite 为 190 tests/10 skipped；Phase 3 serial 4/4 与精简 MPI4 4 项（每 rank 2 skip）通过。clean source `72dca66...` 的正式 MPI4 h10 record 对 air/lossy/current-patterned、air 正反配对和 80°→79.8° tracking 的 9 个 runner Gate 全通过。双正交误差 air/lossy 约 `1e-15`、patterned `2.46e-10`，左右残差约 `1e-16–1e-15`，principal angle 最大 `0.005918 rad`，完整向量不聚集。Case080 checker 增至 `282/282 passed`。h10 仅是分类合同；Phase 4 尚未开始。

Phase 4 已实现 O(M) 存储的 two-port 对角传播：incoming 为 bottom-forward/top-backward，outgoing 为 bottom-backward/top-forward；正反方向分别使用 `+L/-L` 坐标位移，禁止 growing inverse。纯传播 6 项合同、真实 Phase 3 air basis 集成和 MPI4 runner 的 8 个 Gate 均通过；覆盖 100 nm 无反射、lossy/evanescent 被动衰减、37+63 nm composition、reciprocity 负对照和四 rank 一致性。clean source `9206e9c...` 的正式 record 固定 exact Phase 3 record hash；最大 composition 误差 `9.42e-16`，air reciprocity beta/factor 误差 `3.63e-16/2.78e-15`，三个 case reflection norm 为 0。Phase 4 冻结时 Case080 checker 为 `286/286 passed`；Phase 5 见下一段。

Phase 5 已实现匹配网格的 3D Nédélec 切向迹提取、2D mode trace 重构、left/right Petrov 投影、bottom/top 双域法向约定和质量范数 residual。3D→2D 路径只交换接口插值点及两个复切向分量，允许某些 rank 没有本地 source evaluation，不聚集完整 field/mode vector。clean source `b565ac4...` 的正式 MPI4 record 通过 8/8 Gate：bottom/top 各 18 个匹配接口面、162 个 trace DoF，Stage4 两模 Gram 条件数 `30.4995`，系数 round trip/重构 residual 为 `3.78e-16/4.69e-16`，3D→2D 迹误差为 `4.52e-15/6.61e-15`；air 近简并旋转的 projector error 为 `2.11e-8`，且未形成 dense `N_Gamma^2`。完整 serial 回归为 `199 tests / 10 skipped`，Phase 5 MPI4 为每 rank `3/3`，Case080 checker 在 Phase 5 冻结时为 `290/290 passed`；Phase 6 后续进展见本节顶部最新更新。

Task031 Review V1 接受正式 h5/h3/h2 的数值正确性与 absolute memory strong Gate，不要求重跑正式计算；合并前加固集中在 master 同步、端口文档、matrix-free/performance 术语、内存口径和选择性合并边界。分支已真实 merge 当前 `master`，保留 [`project_service_requirements_and_forward_model_roadmap.md`](project_service_requirements_and_forward_model_roadmap.md) 与 [`project_service_requirements_phase1_scope.md`](project_service_requirements_phase1_scope.md)：后续统一规划范围为 `13.5 nm + fixed Si + 1–10° grazing + S/P`，但 Task031 只资格化 theta=80°（10° grazing）、S polarization 的 frozen 单点。

新增 [`iterative_solver_ports.md`](iterative_solver_ports.md)，统一列出 Task27 canonical、Task30 compact、Task31 memory-first 的命令和身份；FGMRES 是当前 adaptive PC 的合法/已资格化 outer port，普通 GMRES 被线性认证阻塞，TFQMR/BCGS 只有未资格化接口，fixed Richardson 与 selective boundary Jacobi 是 research-only numeric negative。Task31 的精确术语是 assembled-F-free public MPC form-action path，不是缓存优化的低层 element-kernel matrix-free；一次性 `release_f()` 不是变慢主因，每次 form action 的装配与通信才是主要成本。

Task030 Review V3 已通过并按用户许可合入 master（merge `545165b`）。Task031 从该 clean merge point 创建独立分支，目标是在 frozen p2/80-mode/exact-condensed target 上继续压缩内存，同时把 explicit true residual 收敛置于所有性能目标之前。

Task031 新增外部 simultaneous RSS/cgroup/swap/stage sampler、public DOLFINx-MPC form action、condensed fine-action lifecycle、PC linearity/determinism certification、exact factor fingerprints 与对象 ledger。研究漏斗否定了 restart50、ordinary GMRES、fixed Richardson、20 slabs、boundary Jacobi 与 factor dedup；保留的组合是 FGMRES90 + Task030 physical-slab/wave coarse + 16 slabs overlap0.125 + assembled-F-free public form action + compact lifecycle。

clean SHA `45a0fc6e...` 的 full h5/h3/h2 分别在 1157/1994/1977 步达到 full residual `9.960e-7 / 9.974e-7 / 9.998e-7`。外部 simultaneous worker peak 为 1.619598/3.474346/7.897675 GiB，h2 legacy internal peak 为 8.176441 GiB。相对 Task030 历史 9.374729 GiB 的辅助观察降幅约 15.8% / 12.8%，因 sampler 不完全同口径，保守结论为从约 9.4 GiB 压到约 8.0–8.2 GiB。h2 达到 strong memory success 且无 swap；代价是 solve 11982.581 s，约为 Task030 的 5.01x，因此分类为 `strong_memory_success_slow_but_memory_efficient`，ordinary default 仍不改变。

Task029 已按用户许可合并；Task030 从 `bfb6586e` clean master 创建独立分支。Task030 建立了 active/master-aware nonmatching H(curl) transfer 与 exact condensed Galerkin 基础设施，但五个正式 p/h 候选 100 步残差均比 Task027 基线差 146–264 倍，证明当前 792D p1 coarse 不是目标慢误差的有效表示。

真正正反馈来自 Task27-derived physical-slab + 75D wave-coarse 架构，并加入 symmetric pre/post sm2、ILU0、subdomain-local shift、factor-only storage 和 FGMRES restart90。Review V2 后，h5/h3 在 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上 clean 复跑，分别用 855/962 步收敛，峰值 1.687653/3.792912 GB；h3 同时通过 3.8 GB 绝对线和相对 Task027 canonical 降低 25.37% 的相对线，iteration ratio 为 1.125。h2 不重跑，保留为 1873 步、full true residual `9.972e-7`、含 R/T/A 峰值 9.374729 GB（-28.33%）的 reviewed historical dirty-worktree reference。因此分类为 `workstation_memory_success_with_qualifications`；ordinary default 未改变。

Review V1 接受数值结果并要求修正 benchmark/provenance。三份正式 records 已从原 artifacts 恢复 source commit、tracked-dirty qualification、完整命令/时间/镜像/host 和 artifact SHA-256；Case060 已接入 203 项真实数值 Gate，三份记录也进入 manifest，使 normal checker 可重复生成完全相同的 summary。当前 ILU1/ILU0 reported factor nnz 相同，不能宣称 factor-nnz compression；factor-only 只在 PETSc 3.24.0 complex build 验证，跨版本需回归。

Task028 已按普通 merge commit 合入 `master`，并完成 master release check。Task029 从该合并点新建独立分支，完成 direct-memory telemetry、外部 0.25 s sampler、matrix/factor inventory、Case050、h5/h3 baseline、H1–H7、profile 筛选和 h2 安全决策。遥测明确区分 simultaneous worker RSS、各 rank 历史峰值和、MPI 进程树与 cgroup；Task28 canonical records 保持只读。

MPI4 h5/h3 baseline simultaneous RSS 为 2328.145 / 8651.098 MB，主峰都位于 KSPSetUp。release-base 公共生命周期候选在 h3 只下降 5.462%；最佳 default MUMPS MPI2 在 h5/h3 分别下降 28.893% / 15.119%，全部 residual/R/T/A Gate 通过且无 swap，但 h3 低于 20% 工程门槛。因此 Task029 分类为 `diagnostic_success`，不产生合格低内存 direct profile。h2 两类外推中央值为 22.214 / 22.330 GiB、区间 18.882–27.913 GiB，G3/G5/G7/G9 失败，未启动 h2。

Review V1 后补充的构建/链接与固定四核审计确认，当前 PETSc/MUMPS 链接可控的 OpenBLAS pthread，但 MPI1×4 在 KSPSetUp 的 CPU 核均值/峰值仅 0.999/1.054，Stage4 相对 MPI1×1 只有 1.054× speedup。最终身份为 `threaded_direct_capability=unavailable_in_current_image`，因此 threaded h3 按 T4 `not_run`；ordinary default 仍不改变。

---

# 2. 项目总体目标

项目目标是建立可验证、可扩展的二维和三维频域 Maxwell 有限元求解框架，重点面向周期微纳结构和 EUV 光栅散射。

长期物理能力目标：

```text
- 2D/3D Maxwell frequency-domain solve；
- real/complex refractive index；
- Floquet periodic boundary conditions；
- PML、Fresnel interface 和 periodic modal port；
- Nedelec H(curl) elements；
- diffraction orders；
- official R/T/A；
- material volume absorption；
- field output；
- mesh/order/angle/wavelength scans；
- direct and iterative solvers；
- low-memory workstation and future HPC execution；
- eventual geometry/material inversion support。
```

当前长期参考模型：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate thickness = 10 nm
top air above grating = 10 nm
wavelength = 13.5 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s
material = complex Si index
space = 3D N1curl p=2
side boundaries = double Floquet
z boundaries = periodic modal DtN ports
```

---

# 3. 阶段总览

| 阶段 | Task | 主要目标 | 最终状态 |
|---|---|---|---|
| A. 初始整理与物理口径 | 000–004 | 整理代码、R/T/A、体吸收、能量闭合、MPI/p 回归 | 基础工程链稳定 |
| B. 目标几何与直接法边界 | 005–010 | 真实 3D 资源、official DtN、目标几何 direct、BLR | h=2 direct reference 建立 |
| C. AMS/HX 与低维模态路线 | 011–019 | 低内存 Krylov、real split、AMS/HX、sampled Schur | p1 有信号，p2 主线失败并关闭 |
| D. wave-aware 与 FE-response/Schur | 020–025 | residual-aware modes、FE response、PETSc/MPI Schur、cached-Q | 数学结构成立，h=2 response 质量不足 |
| E. auxiliary-free 与 workstation solver | 026–027 | exact condensation、matrix-free、physical slab two-level PC | h=5/3/2 MPI4 达 production residual |
| F. 阶段收口与可复现版本 | 028 | clean master 整合、文档、benchmark、阶段版本 | V4 完成并合入 master |
| G. direct memory forensics | 029 | simultaneous RSS、factor inventory、生命周期/profile 筛选、h2 Gate | diagnostic_success，等待审查 |

---

# PART I：阶段 A——初始代码整理与物理口径

## 4. Task000：初始代码审查与工作流整理

### 目标

```text
- 阅读项目结构；
- 识别 2D/3D 代码边界；
- 建立 task -> outcomes -> review 的开发流程；
- 记录代码问题和后续优先级。
```

### 主要成果

```text
- 建立任务目录规范；
- 建立代码审查和结果追踪习惯；
- 明确理论笔记、运行结果和任务记录的目录职责；
- 为后续 Stage4 验证提供审计基线。
```

### 当前状态

```text
success_type = documentation/workflow success
code_status = 被后续稳定实现替代
retained_value = 可追溯开发流程
```

---

## 5. Task001：Stage4 validation cleanup

### 目标

清理早期 Stage4 路径中的配置、输出和验证逻辑，减少不同案例之间的隐式差异。

### 主要成果

```text
- 整理 Stage4 case flow；
- 清理输出与验证标签；
- 建立较一致的运行 summary；
- 为后续功率口径修正做准备。
```

### 局限

```text
- 当时的 R/T/A 仍不是最终 official 口径；
- 真实目标几何和 p=2 资源边界尚未建立。
```

### 当前状态

后续 Task003、Task007 和 Task008 已吸收该任务的有效成果。

---

## 6. Task002：R/T/A 输出与 volume absorption

### 目标

```text
- 输出反射率、透射率和吸收率；
- 增加有损材料的体积分吸收；
- 比较不同功率计算方式；
- 检查能量守恒。
```

### 主要实现

```math
P_{abs}
\propto
\int_{\Omega_{loss}}
\operatorname{Im}(\varepsilon_r)|E|^2\,dV.
```

新增或整理：

```text
- port power；
- probe Fourier power；
- sampled net flux；
- A_volume；
- energy closure fields。
```

### 关键发现

初始不同功率口径不一致，不能直接将 probe 或 sampled flux 作为 official R/T。

### 当前状态

```text
infrastructure_success = yes
diagnostic_success = yes
initial_physical_result = superseded by Task003/007
```

---

## 7. Task003：Stage4 power consistency

### 目标

建立统一、可信的功率和能量闭合口径。

### 主要成果

```text
- flat-layer analytic sanity；
- port + A_volume 能量闭合；
- probe 和 sampled flux 降级为 diagnostic；
- 统一能量 closure 字段；
- 修正后续主线的功率验收规则。
```

### 长期保留结论

```text
official power = modal port power
volume absorption = material loss integral
probe-plane Fourier = diagnostic only
sampled net flux = diagnostic only
```

该结论持续沿用到 Task028。

---

## 8. Task004：small-cell p convergence、MPI consistency 与全阶段回归

### 目标

```text
- 小尺寸 flat-layer benchmark；
- p=1/p=2 比较；
- MPI1/4/8 一致性；
- Stage1、2A、2B、2C、4 smoke；
- 防止前几轮修改破坏已有路径。
```

### 主要成果

```text
- p=2 明显优于 p=1；
- official port + A_volume 在小模型上稳定；
- MPI rank 数不改变主线结果；
- Stage1/2A/2B/2C/4 的基本路径可以运行；
- 建立长期 regression baseline。
```

### 边界

```text
- Stage2B PML 和 Stage2C Fresnel 当时只做 smoke，不代表高精度验证；
- small-cell 不是目标 3D EUV 光栅物理 benchmark。
```

### 当前状态

```text
production/infrastructure baseline = retained in master
```

---

# PART II：阶段 B——目标几何、资源边界与直接法

## 9. Task005：真实 3D 光栅内存和直接法资源估算

### 目标

评估真实 3D 光栅中：

```text
- mesh size；
- DoF；
- matrix nnz；
- assembled matrix storage；
- direct LU fill-in；
- MUMPS OOC；
- workstation resource boundary。
```

### 关键发现

```text
- assembled matrix 并非唯一瓶颈；
- MUMPS LU fill-in 和 factor workspace 才是主要峰值；
- 粗网格可以完成，细网格 direct 很快进入内存边界；
- 继续仅依赖 direct 无法支持更细 p=2 3D 模型。
```

### 当前状态

保留为容量规划和失败边界证据，不作为当前推荐 solver。

---

## 10. Task006：缩短计算域与 OOC 资源分析

### 目标

尝试用较短 z 域降低矩阵规模，评估：

```text
- 70 nm reduced-height domain；
- direct/OOC 可达网格；
- 结果对 domain height 的敏感性；
- 资源外推。
```

### 成果

```text
- 明确 reduced-height 能显著减小矩阵；
- 修正真实光栅 top probe 位置；
- 记录 OOC scratch 和失败边界；
- 区分 matrix RSS 上界与进程树真实峰值。
```

### 负结果

```text
- 70 nm 域的 R/T/A 与更高域明显不同；
- 不能把 reduced domain 当作物理等价 benchmark；
- OOC 不能自动解决细网格 direct。
```

### 当前状态

```text
resource diagnostic retained
physical benchmark superseded by Task008
```

---

## 11. Task007：恢复 DtN modal amplitudes 作为 official R/T/A

### 目标

明确 Stage4 periodic modal port 的官方功率来源。

### 最终口径

```text
R_total = outgoing top DtN modal power / incident power
T_total = outgoing bottom DtN modal power / incident power
A_volume = material volume loss / incident power
closure = R + T + A_volume - 1
```

### 关键成果

```text
- auxiliary DtN modal amplitudes 成为 official power source；
- probe Fourier 和 sampled flux 降为 diagnostic；
- 有损基底的 T 与 port reference plane 相关这一边界被记录；
- 后续所有 Task 使用统一口径。
```

### 当前状态

```text
stable production power definition
```

---

## 12. Task008：目标几何 p=2 direct benchmark

### 目标模型

```text
50 x 25 x 140 nm unit cell
17 x 25 x 120 nm grating
13.5 nm
80 deg from z
s polarization
complex Si
p=2 Nedelec
double Floquet + 80 DtN auxiliary modes
```

### 主要成果

建立目标模型 direct reference：

```text
p=2 h=2 nm
R = 0.0013429328462348958
T = 0.5992132294442478
A_volume = 0.3994438377095067
R+T+A = 0.9999999999999893
```

同时记录：

```text
- p=1 和 p=2 direct 可达边界；
- p=2 h=1.5 direct setup 被内存杀死；
- p=2 h=1 assembled matrix/交换空间压力很高；
- h=2 是 workstation best-effort direct reference，不是最终无限细网格极限。
```

### 当前状态

```text
current direct reference = retained
ordinary direct default = retained
```

---

## 13. Task009：黑盒 PETSc 迭代 profile 筛选

### 目标

快速测试：

```text
GMRES / FGMRES / BiCGStab
Jacobi / BJacobi / ASM / ILU / local LU
GAMG / FieldSplit / BoomerAMG diagnostics
```

### 关键结果

```text
- 没有现成黑盒组合达到 production residual；
- GMRES + Jacobi 只能稳定降低残差，不能收敛；
- ASM/ILU/local LU 多数停滞或恶化；
- 未收敛配置禁止输出 official R/T/A。
```

### 关键纠偏

早期记录的：

```text
residual_final / residual_initial
```

不等于：

```text
||Ax-b|| / ||b||
```

从此建立 reported/KSP residual 与 explicit true residual 的严格区分。

### 当前状态

```text
negative-result baseline retained
black-box PC route closed
```

---

## 14. Task010：MUMPS-BLR 与 shifted Maxwell 原型

### 目标

```text
- 测试 MUMPS-BLR compressed factorization；
- 打通 A/P 双矩阵接口；
- 测试 minimal shifted/positive Maxwell P；
- 为 AMS/HX 做工程预检。
```

### 正结果

h=2：

```text
FGMRES + MUMPS-BLR eps=1e-5
iterations = 4
true residual ≈ 2.09e-8
R/T/A 与 direct 一致到约 1e-9
```

### 边界

```text
- BLR 仍属于近似直接因子，不是最终低内存迭代法；
- h=1.5 仍在 setup 阶段被内存杀死；
- minimal shifted/positive Maxwell + ASM/ILU 未收敛。
```

### 当前状态

```text
BLR = explicit fallback/reference
shifted A/P infrastructure = historical foundation
```

---

# PART III：阶段 C——AMS/HX、real split 与低维 sampled-Schur

## 15. Task011：低内存 Krylov、AMS/HX smoke 与 matrix-free feasibility

### 目标

```text
- low-restart Krylov + Jacobi；
- real FE-only hypre AMS/HX；
- complex AMS safety；
- matrix-free FE action。
```

### 结果

```text
Jacobi-Krylov:
- 低内存；
- 不收敛；
- 路线基本关闭。

real FE-only AMS:
- p1/p2 小模型有真实收敛信号；
- p=2 h=5 可到约 1e-6；
- 但内存和完整 Stage4 兼容性未知。

complex AMS:
- 当前 build 下崩溃，不安全。

matrix-free FE action:
- 与 assembled action 误差约 1e-15；
- 证明少存矩阵可行；
- 但不解决 inverse/PC 问题。
```

### 当前状态

```text
matrix-free foundation retained
AMS result = research signal only
```

---

## 16. Task012：Maxwell 预条件器文献调研与路线设计

### 覆盖方向

```text
- H(curl) auxiliary space / Hiptmair-Xu / hypre AMS；
- shifted Maxwell / complex shifted Laplacian；
- overlapping Schwarz / optimized Schwarz；
- sweeping / moving PML；
- DtN-aware block preconditioner；
- Rayleigh/Floquet modal deflation；
- matrix-free high-order Maxwell；
- BLR/H-matrix fallback；
- layered/RCWA-like approximate inverse。
```

### 结果

停止盲目添加 PETSc profile，转为有 Gate 的物理预条件器研究。

### 当前状态

理论和路线文档长期保留，但每条方法的生产状态以后续数值任务为准。

---

## 17. Task013：real-split AMS/HX qualification

### 目标

绕开 complex hypre AMS 崩溃，将复杂 Maxwell FE operator 写成实数块系统：

```math
\begin{bmatrix}
\operatorname{Re}A & -\operatorname{Im}A\\
\operatorname{Im}A & \operatorname{Re}A
\end{bmatrix}.
```

### 成果

```text
- complex-to-real matvec 等价误差约 1e-16；
- real hypre AMS 可安全运行；
- same-H1 auxiliary 显著降低内存；
- FE-only p=2 h=5 达到 true residual <=1e-6。
```

### 局限

```text
- 不含 Floquet MPC 后完整结构；
- 不含 DtN auxiliary unknowns；
- 不含目标 Stage4 R/T/A；
- isolated serial research runner。
```

### 当前状态

```text
B-grade research positive
production code not merged
```

---

## 18. Task014a：reduced Stage4 real-split FE/aux block PC

### 目标

把 Task013 FE-only 正信号接到约化 Stage4：

```text
FE block -> same-H1 AMS
aux block -> identity/exact small block
```

### 成果

```text
- Stage4 complex-to-real equivalence 通过；
- FE/aux block indexing 通过；
- MPC 后 AMS data 可构造；
- MPI ownership 和数据布局明确。
```

### 负结果

```text
FE-AMS + aux identity
1000 steps
true residual ≈ 2.15e-2
```

只比 Jacobi 改善约 1.6 倍，不能进入 p=2/full Stage4。

### 结论

FE-only AMS 正信号不能直接搬到包含 DtN coupling 的完整问题。

---

## 19. Task015：DtN/Floquet boundary-aware diagnostic

### 目标

定位 Task014a 的 residual 停滞来源。

### 关键发现

FE-AMS 之后，剩余 residual 几乎全部集中在：

```text
top port
Rayleigh order (0,0)
y/s polarization
```

进一步证明：

```text
- aux block identity/exact/diag 本身不是瓶颈；
- aux-only modal correction 无效；
- diag(A_FE)^-1 Schur 明显变差；
- 真正问题是 auxiliary mode 与 FE trace/volume 的 coupled slow direction。
```

### 当前状态

诊断成功，驱动 Task016–Task021；diagnostic runner 不进入生产。

---

## 20. Task016：dominant zero-order lifted coarse correction

### 目标

构造：

```text
Z = [-P_FE^-1 C_j ; e_j]
```

并尝试 Galerkin、minimum-residual、additive 和 residual-corrected coarse correction。

### 结果

最好改善约：

```text
1.000045x
```

几乎无效。

### 关键结论

```text
aux residual 集中在某个 mode
!=
solution error 可由相应 right lifted vector 修正
```

可能需要：

```text
- left/test space；
- 更准确 A_FE^-1 C_j；
- 非正规系统的不同投影形式。
```

### 当前状态

right-only lifted coarse 路线关闭。

---

## 21. Task017：Petrov/adjoint coarse 与 true-FE sampled lift

### 目标

```text
- 增加 left/test space W；
- 测试 adjoint-aware projection；
- 用更真实的 FE response 近似 A_FE^-1 C_j。
```

### 结果

Petrov/adjoint 路线仍无效；但 true-FE sampled response 出现第一个明显正信号：

```text
top+bottom zero-order y modes
one-shot residual ≈ 3.69e-3
improvement ≈ 5.82x
```

### 限制

```text
- 依赖 SciPy exported-matrix research path；
- FE response 并非 exact；
- 直接塞进 right PC 后反而变差；
- 尚未形成稳定 solver。
```

### 当前状态

Petrov 路线关闭；true-FE residual correction 进入 Task018。

---

## 22. Task018：adaptive residual-corrected true-FE sampled Schur

### 目标

将 Task017 的 one-shot correction 转为 solver-like process。

### 最佳流程

```text
bounded FE-AMS segment
-> compute true residual
-> solve small min ||r-AZ alpha||
-> update x
-> repeat
```

### p=1 h=5 结果

```text
baseline residual ≈ 2.146e-2
best residual ≈ 1.662e-3
improvement ≈ 12.91x
```

通过 strong research gate，但未达到 \(10^{-6}\)。

### 关键发现

最有效的 FE response 不是最精确的 solve，而是带过滤作用的较松近似。

### 局限

```text
- SciPy single-process response service；
- 不是 MPI production；
- p=2 迁移尚未验证。
```

### 当前状态

p=1 research strong positive；允许进入 Task019 p=2 qualification。

---

## 23. Task019：p=2 h=5 sampled-Schur qualification

### 目标

验证 Task018 是否迁移到 p=2。

### 结果

```text
baseline 120-step residual = 1.6386e-2
required top_bottom_y best = 1.6357e-2
improvement = 1.0018x
best creative low-dimensional variant = 1.0804x
```

### 结论

```text
- p1 filtered sampled response 不迁移 p2；
- 增加少量 mode 无效；
- 低维 sampled-Schur 主线停止；
- 不进入 h=2。
```

### 当前状态

失败代码保留研究分支；文档作为重要负结果长期保留。

---

# PART IV：阶段 D——wave-aware、FE response 与 full Schur

## 24. Task020：branch hygiene 与 wave-aware solver search

### 目标

```text
- 整理失败分支；
- 比较 impedance DDM、sweeping、two-level adaptive coarse、matrix-free；
- 寻找 p=2 下一条主线。
```

### 结果

在 default100 算法沙盒：

```text
Route A row-layer DDM proxy -> 无明显改善
Route B diagonal slab sweep -> 变差
Route C residual-aware adaptive coarse -> 唯一正信号
Route D matrix-free action -> 代数通过但不是 solver
```

p=1 Route C 可到 \(10^{-6}\)，p=2 仅约 0.0525。

### 边界

Task020 使用 default100 沙盒，不是最终目标物理模型。

### 当前状态

路线排序保留；Task021 切回真实目标几何。

---

## 25. Task021：目标几何 DtN auxiliary residual-aware FE response/Schur

### 目标

在真实 p=2 h=5 目标模型上验证：

```text
residual-dominant auxiliary selector
+ FE response
+ coupled Schur correction
```

### 关键结果

```text
Jacobi baseline ≈ 0.2026
SPILU coupled m=1 ≈ 9.87e-7
SPILU block Schur ≈ 2.43e-7
exact FE-block Schur upper bound ≈ 8.16e-12
```

### 物理发现

主导 auxiliary mode 稳定为：

```text
top (0,0) s-polarized mode
```

### 结论

真正有效的是：

```text
FE response quality + FE/aux Schur structure
```

而不是单独 auxiliary correction。

### 局限

```text
serial SciPy SPILU/SPLU research prototype
no MPI production
no h=2
no official iterative R/T/A reconstruction
```

---

## 26. Task022：p=2 h=2 Schur/FE-response preflight

### 目标

验证 h=2 是否能沿 Task021 路线推进。

### 成果

```text
rows = 615188
FE DoF = 615108
aux = 80
nnz ≈ 65.45M
assembly + CSR 可完成
peak preflight RSS ≈ 6.277 GB
main selected mode 与 h5 相同
matrix-free FE action 误差 ≈ 6e-16
```

### 阻塞

```text
serial SciPy SPILU high fill -> 估计约 27.8 GB
very low fill -> setup 超时或质量不足
```

### 结论

h=2 失败不是矩阵、mode selector 或 Schur 结构错误，而是无法低内存近似 \(A_{FE}^{-1}\)。

---

## 27. Task023：PETSc/MPI-safe FE-response PC

### 目标

将 Task021/022 迁移到 PETSc/MPI，并补齐 field/RTA 回填。

### h=5 成果

```text
selected response ASM + local LU residual ≈ 9.33e-7
full 80-aux Schur one apply ≈ 2.49e-10
FieldSplit FE-LU ≈ 3.80e-9
```

official R/T/A 与 direct 差约 \(10^{-12}\)。

### 工程成果

```text
- MPI FE/aux index ownership；
- PETSc subblocks；
- solution reconstruction；
- MPC back-substitution；
- official modal R/T/A；
- FieldSplit/Schur engineering framework。
```

### h=2 负结果

```text
plain ASM/ILU response 质量不足，甚至方向错误；
local LU/MUMPS 进入时间/资源边界。
```

### 当前状态

h=5 工程闭环成功；h=2 仍缺强 FE inverse。

---

## 28. Task024：工程迭代求解器 fast track 与复现基础设施

### 目标

```text
- manual right FGMRES；
- CSR export；
- real split；
- AMS/HX/GMG-lite experiments；
- clean reproduction；
- h=2/h=1.5 low-memory preflight。
```

### 基础设施成果

```text
- manual FGMRES 与 PETSc/SciPy 小矩阵一致；
- complex dot 共轭方向修复；
- MPI1/MPI4 residual history 一致；
- vectorized CSR exporter；
- CSR invariants/hash audit；
- clean container reproduction。
```

### 算法结果

```text
m=1 reduced FE-response
20+20 budget residual = 0.17899
100+100 budget residual = 0.15859
```

没有证明相对严格 baseline 的有意义收益，更不是完整 80-aux solver。

### 当前状态

```text
infrastructure success
algorithm fail
manual FGMRES research-only
CSR/audit concepts retained
```

---

## 29. Task025：full-aux cached Schur 与 multilevel H(curl) 尝试

### 目标

```text
- 完整 80 auxiliary unknown；
- Q ≈ A_FE^-1 C；
- explicit small Schur；
- shifted FE smoother；
- p/coarse/AMS/BDDC 等多层尝试；
- h=2 14 GB 内完整 augmented solve。
```

### h=2 成果

```text
80 response columns
Q nnz ≈ 49.2M
outer iterations = 100
full true residual = 0.118475
peak RSS ≈ 13.006 GB
```

这是完整 full-aux 架构的重要研究突破。

### 根本瓶颈

response columns 满足：

```text
min relative response residual ≈ 0.286
max relative response residual ≈ 0.541
```

小 Schur 已精确求解，主要误差来自 Q 质量。

### 多层路线结论

```text
- 当前 p2->p1 / H1 / BDDC / 2D coarse 原型未捕获主要慢误差；
- 真正 3D nonmatching h-GMG 未实现；
- 不能据此否定所有 AMS/HX 或 h-GMG；
- ILU2 内存收益比太差。
```

### 当前状态

cached-Q 架构被 Task026 exact condensation 替代；诊断和历史证据保留。

---

# PART V：阶段 E——auxiliary-free 与 MPI4 workstation solver

## 30. Task026：auxiliary-free exact static condensation

### 架构变化

从 augmented system：

```math
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=
\begin{bmatrix}b_F\\b_H\end{bmatrix}
```

转为：

```math
(F-CH^{-1}D)u=b_F-CH^{-1}b_H.
```

### 主要成果

```text
- exact condensed operator；
- matrix-free low-rank port action；
- no auxiliary global unknowns in outer solve；
- no Q=A_FE^-1 C cache；
- auxiliary back-substitution；
- explicit condensed reference；
- transpose/Hermitian action；
- h5 field/RTA equivalence；
- h2 MPI1/MPI4 action equivalence；
- 1000 repeated applies stable RSS。
```

### h=5 迭代结果

problem-informed z-slab two-level prototype：

```text
iterations = 795
full residual ≈ 9.999e-10
peak RSS ≈ 1.829 GB
R/T/A closure ≈ 1e-12
```

### 关键代码修复

petsc4py complex `Vec.dot` 语义被正确处理为：

```python
np.conjugate(left.dot(right))
```

用于：

```text
MGS
Z^H A Z
Z^H r
```

该修复将 200-step residual 从约 0.259 降到约 0.00105。

### h=2 初始状态

plain matrix-free ILU2 residual 约 0.166；早期 two-level 仍未达到 production。

### 当前状态

exact condensation 成为 Task28 长期稳定模块。

---

## 31. Task027：mesh-robust physical-slab two-level solver

### 原始目标

用 operator-adaptive spectral coarse 构造 mesh-independent Schwarz PC。

### spectral 路线结果

```text
full-slab energy spectral -> fail
interface harmonic -> fail
shifted near-null -> fail
PCHPDDM energy GenEO -> fail
HPDDM recycling -> false residual risk
```

因此 spectral 假设没有成功。

### 实际成功结构

```text
exact matrix-free condensed operator
+ fixed 75D no-RHS Floquet z-hat coarse
+ 16 complete physical z-slabs
+ deterministic owner-computes assignment
+ shifted local ILU1
+ two fixed shifted-F GMRES smoothing steps
+ right FGMRES restart=100
+ explicit true-residual checkpoints
```

### 最终 MPI4 结果

| h (nm) | iterations | true residual | peak total RSS |
|---:|---:|---:|---:|
| 5 | 1201 | `9.839e-7` | 约 1.96 GB |
| 3 | 993 | `9.933e-7` | 约 5.07 GB |
| 2 | 1804 | `9.997e-7` | 约 12.96 GB |

三网格比值：

```math
1804/993 = 1.8167 < 2.
```

### 物理结果

```text
h5: R=0.0890216, T=0.4425883, A=0.4683901
h3: R=0.0046130, T=0.5836534, A=0.4117336
h2: R=0.00134294, T=0.59921324, A=0.39944383
```

### 准确定位

```text
production candidate = yes
tested-range mesh robustness = yes
strict asymptotic mesh independence = not proven
parameter robustness = not proven
physical mesh convergence = not completed
ordinary default = unchanged
```

### 当前状态

Task027 的 fixed coarse + complete physical slab + sm2 成为 Task28 选择性整合目标。

---

# PART VI：阶段 F——Task028 阶段收口

## 32. Task028：stage consolidation、master integration 与 benchmark

### 目标

暂停新求解器扩展，完成：

```text
- Task000-Task027 审计；
- selective merge manifest；
- clean master 上抽取稳定代码；
- 重建 README 和用户文档；
- 建立独立 benchmarks/；
- 重新运行 direct/iterative benchmark；
- 给出最终 master candidate。
```

### 当前已完成

```text
- 从 master@0465b5f 建立整合分支；
- 没有整分支 merge Task027；
- 新增 condensed_dtn.py；
- 新增 physical_slab_two_level.py；
- 新增 stage4_runtime.py；
- 新增 workstation benchmark runner；
- 新增 total MPI RSS telemetry；
- 新增 condensation 与 physical slab tests；
- 选择性归档 Task021-Task027 58 份核心文档；
- 新增 benchmarks/ 目录；
- h5/h3/h2 iterative clean rerun；
- h5/h3 direct rerun；
- 80 unit tests passed，10 skipped；
- focused MPI4 tests passed。
```

### Task028 clean rerun

```text
h5: 1201 iterations, full residual 9.839e-7
h3: 993 iterations, full residual 9.933e-7
h2: 1804 iterations, full residual 9.997e-7, peak 13.080 GB
```

### V1 审查发现

```text
core solver integration = pass
numerical reproduction = pass
ordinary default = pass
history audit = pass
```

但：

```text
benchmark output boundary = fail
benchmark scripts = fail
automatic gate checker = missing
environment reproducibility = fail
documentation completeness = insufficient
sm2 test coverage = insufficient
master merge = blocked pending response_v1
```

### 当前状态

```text
Task028 core consolidation = accepted
Task028 productization = changes required
```

详细要求见：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/review_report_v1.md
```

### Response V1

2026-07-12 在同一分支完成六个 P0 修正：

```text
benchmark output boundary = pass
benchmark scripts = pass
automatic gate checker = 58/58 pass
environment = pass_with_qualification
documentation = pass
sm2 production tests = pass
full suite = 91 passed, 10 skipped
focused MPI4 = each rank 14 passed
h5 clean rerun = 1201 iterations, full 9.839e-7, 1.991 GB
```

环境仍有一项诚实限定：complex MPC 基础镜像固定了本机 digest，但没有公开 pull source，因此不能宣称任意 clean machine 可直接在线重建。当前状态为：

```text
Task028 productization = pass_with_environment_qualification
master merge = pending review v2 and user approval
```

逐项证据见：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/response_v1.md
```

### Review V2 与 Response V2

V2 认为核心求解器和数值结果仍通过，但要求把项目从“开发者能追踪”升级为“新用户能运行、每项能力有理论/代码/benchmark 对照”。同一分支已完成：

```text
- main.py 改为 15 个安全命名 preset，默认 10x10x10 nm Stage1 p1/h5；
- 2D CLI 支持 complex index；3D direct 显式区分 default/OOC/BLR；
- 建立 Quick Start 15 篇、Code Walkthrough 15 篇、Theory 9 篇规范文档；
- 建立 13 个编号 feature benchmark case，每个使用 22 字段契约；
- historical h3/h2 record 拆分 actual source 与 canonical rerun provenance；
- checker 新增 ID、qualified、KSP、coarse condition、physical model 与 artifact provenance Gate；
- 新增 documentation/main preset/lossy port tests；
- 修复 Docker 根挂载时 main.py 导入；
- 修复 2D lossy DtN 把 complex beta 误判为 evanescent、以及在错误参考平面计算 T 的问题。
```

复材料实算确认：TM `R+T+A_volume-1=3.33e-15`，TE 为 `-5.50e-16`；probe 结果仍只作 diagnostic。最新验证：

```text
full suite = 105 passed, 10 skipped（最终重跑前的预期计数，以 outcomes/test_summary 为准）
focused MPI4 = each rank 14 passed
benchmark checker = 87/87 pass
h2 heavy solve = not rerun; numerical records unchanged
```

当前状态：

```text
Task028 V2 implementation = complete
environment = qualified_local_image
master merge = blocked only pending final review and user approval
```

逐项证据见 `response_v2.md` 与本任务 `outcomes/`。

### Review V3 与 Response V3

V3 保持 Task026/027 核心 solver 和既有 3D records 通过，但要求把“目录存在”提升为可执行、可复核、技术准确的交付。同一分支完成：

```text
- Case002 在同一网格完成 explicit/auxiliary 两次完整 solve；
- Case003 冻结 TM/TE complex absorption lightweight records；
- checker 扩展到 143/143，含 lossy、lossless、case files 与 SHA references；
- main.py 增至 17 个 preset，demo/target 物理身份分离；
- Case021 target preset 直接复用 target_stage4_config；
- Case031 增加 PyCharm Docker/WSL External Tool MPI4 workflow；
- 15 篇核心 Quick Start 全部扩展为 16 节教程；
- 11 篇核心 Walkthrough 全部达到源码/shape/ownership/公式/Gate 深度；
- 修正 SparseCoarseVector 字段、smoother-first 顺序、显式 inverse 和 H=I 限制；
- 13 个 Benchmark 全部建立 case-contained contract 并扩展 README；
- Theory 增加统一符号表、module::function anchors 和 2D/3D power constants。
```

最新验证：

```text
full suite = 115 passed, 10 skipped
focused MPI4 = each rank 14 passed
documentation contract = 11 passed
benchmark checker = 143/143 pass
h2 direct/iterative = not rerun; existing 3D records unchanged
```

逐项证据见 `response_v3.md`。当前状态为 ready for final review；master 仍未合并。

---

# 33. 当前项目能力

## 33.1 2D 当前能力概览

当前代码具备或历史上已实现：

```text
- TM vector Maxwell；
- TE scalar Maxwell；
- Floquet periodic constraint；
- manual / MPC backends with restrictions；
- scattered-field + PML；
- Robin port；
- Fourier-DtN port；
- explicit/auxiliary DtN variants；
- real/complex refractive index；
- diffraction order postprocessing；
- R/T and absorption-related outputs；
- field/mesh export；
- parameterized geometry and mesh controls。
```

需要 Task028 文档复核的边界：

```text
- exact supported command for each combination；
- 2D DtN manual-only restriction；
- MPI support restrictions；
- which R/T source is official in each formulation；
- current iterative solver status；
- angle/wavelength scan maintenance status。
```

正式能力矩阵以更新后的 `docs/capability_matrix.md` 为准。

---

## 33.2 3D 当前能力概览

```text
- Stage1 airbox；
- Stage2A double Floquet airbox；
- Stage2B PML airbox smoke；
- Stage2C Fresnel interface smoke/reference path；
- Stage4 flat-layer and block grating；
- p=1/p=2 Nedelec；
- complex material；
- double Floquet MPC；
- auxiliary DtN modal port；
- explicit/static condensed DtN；
- matrix-free condensed DtN；
- direct MUMPS；
- MUMPS OOC；
- MUMPS-BLR fallback；
- official modal R/T/A；
- volume absorption；
- field/mesh export；
- residual/memory telemetry；
- MPI4 complete physical-slab iterative candidate。
```

当前正式目标 solver 状态：

```text
ordinary default = direct
workstation iterative = explicit opt-in
h=5/3/2 = qualified reference set
h=1.5 = not completed
new angle/wavelength/material/geometry = not qualified
```

---

# 34. 当前主要里程碑

| Milestone | 状态 | 关键 Task |
|---|---|---|
| official modal R/T/A and A_volume | 完成 | 002–007 |
| small-cell p/MPI regression | 完成 | 004 |
| target 3D direct h=2 reference | 完成 | 008 |
| black-box iterative exclusion | 完成 | 009–011 |
| AMS/HX real-split qualification | 研究完成，生产失败 | 012–014a |
| DtN slow-mode diagnostic | 完成 | 015–017 |
| p1 sampled-Schur strong signal | 完成但不迁移 | 018–019 |
| target p2 FE-response/Schur mechanism | 完成 | 021–023 |
| h2 full-aux cached-Schur research solve | 完成但不生产 | 025 |
| exact auxiliary-free condensation | 完成 | 026 |
| MPI4 h2 <1e-6 under 14 GB | 完成 | 027 |
| clean master candidate integration | V4 三项加固完成，已获合并许可 | 028 |

---

# 35. 已关闭或暂停的路线

以下路线当前不应重新盲扫：

```text
- ordinary Jacobi/BJacobi/ASM/ILU profile tuning；
- complex AMS direct attachment；
- minimal FE-AMS + aux identity；
- aux-only modal correction；
- diag FE Schur；
- right-only lifted coarse；
- broad Petrov/adjoint W scan；
- low-dimensional top_bottom_y sampled-Schur as p2 mainline；
- cached-Q full-aux architecture as final solver；
- energy spectral/GenEO threshold scan；
- HPDDM cross-solve recycling without explicit true residual；
- unconditional h2 direct on 14 GB environment。
```

这些路线的文档仍有价值，但不进入普通 API。

---

# 36. Task029：Stage4 direct memory forensics

## 36.1 最终状态

```text
Task = Task029 — Stage4 direct memory forensics
branch = codex/20260713-task29-stage4-direct-memory-forensics
base = master@2f9e56d2edddb801780504f681b2ff295d993e02
classification = diagnostic_success
engineering_success = no
threaded_direct_capability = unavailable_in_current_image
h2 = not_run
h3_threaded_direct = not_run
review = V2 technical review pass
master = user-approved; merge pending execution
ordinary default changed = no
```

Task029 的成功是“诊断、基础设施和安全决策成功”，不是“获得了新低内存 direct solver”。这一分类贯穿代码、Benchmark、能力矩阵和合并边界。

## 36.2 为什么启动

Task028 已把目标 p2/h5、h3、h2 的 direct reference 与 MPI4 workstation iterative 路径收口，但 direct h3/h2 的因子内存仍是工作站边界：h3 direct 已约 8 GiB，历史 h2 direct 约 20.5 GiB，超过当前约 14 GiB 环境。此前只有最终/历史 RSS，没有足够证据回答内存是在 DtN 增广、MUMPS factorization、KSPSolve 还是后处理中增长，也无法判断对象释放、rank 数、OOC/BLR 或 ordering 是否值得提升。

如果不先完成分阶段剖析，后续容易把统计口径变化误写成优化，把单网格正信号包装成 profile，或在没有安全余量时直接运行 h2。本任务不解决物理网格收敛、新迭代预条件器、adaptive mesh 或跨机器 COMSOL 性能可比性。

## 36.3 冻结问题与 baseline

冻结模型为 50 × 25 × 140 nm 周期单元、17 × 25 × 120 nm complex-Si block、13.5 nm、theta=80°、phi=0、s 偏振、p2 Nédélec、double Floquet + auxiliary Fourier-DtN。模式策略始终为 `auto_propagating`，top/bottom 各 40 个模式、`n_aux=80`。允许改变的是 direct 生命周期、MPI rank/thread 组合、明确 opt-in profile/package/ordering 与遥测；禁止改变物理、模式、official R/T/A、full solve 和 ordinary default。

基线是 default MUMPS、MPI4、每 rank 1 thread。数值资格要求 full explicit true residual、Task28 R/T/A 绝对差和能量闭合均 `<=1e-8`。内存主口径是外部同一时刻所有 worker rank RSS 的和；cgroup current、swap 和各 rank 历史峰值和分别记录，不混写。

| 指标 | h5 MPI4 baseline | h3 MPI4 baseline |
|---|---:|---:|
| FE / auxiliary / augmented rows | 44,698 / 80 / 44,778 | 198,438 / 80 / 198,518 |
| true residual | `5.225e-12` | `1.382e-11` |
| max Task28 R/T/A abs delta | `0` | `1.865e-14` |
| simultaneous worker RSS | 2328.145 MiB | 8651.098 MiB |
| cgroup current peak | 1729.035 MiB | 8353.727 MiB |
| KSPSetUp / KSPSolve | 1.838 / 0.0467 s | 31.200 / 1.603 s |
| augmented / factor nnz | 4,896,156 / 33,862,428 | 21,317,860 / 266,127,836 |
| swap in / out | 0 / 0 | 0 / 0 |

## 36.4 采用的方法

| 方法 | 解决的问题 | 保护措施 |
|---|---|---|
| 0.25 s external sampler | 把 simultaneous RSS/cgroup/swap 峰值映射到 solver stage | 原始 timeline 留在 ignored artifacts，轻量 CSV 入库 |
| matrix/factor inventory | 区分 base/augmented 存储与 LU fill | PETSc 原始 0 memory/fill 不冒充有效 allocator 测量 |
| progress checkpoints | 标记 `before/during/after KSPSetUp`、solve、RTA、field output | 每个 full run 保留 residual/R/T/A |
| H1–H7 单因素假设表 | 按收益、风险和 stop rule 筛选优化 | h5 先筛，最多两个候选进 h3 |
| clean-source candidate runner | 绑定 commit、image digest、command、profile | tracked-source-dirty 直接拒绝 |
| h2 两路径外推 + G1–G10 | 在高内存运行前给出范围与硬 stop | Gate 未全 true 时 runner 保持锁定 |
| 构建/链接与 `/proc` 审计 | 区分 NumPy BLAS、MUMPS 实际 BLAS 和真实 CPU 使用 | 固定 `OMP=1`、CPU `0-3`，只控制 OpenBLAS pthread |

低风险实现包括幂等 `DirectSolveFailure.cleanup()`、OOC scratch/I/O/cleanup telemetry、显式 MPI distributed factor package 选择正确性，以及默认 `false` 的 `direct_release_base_after_augmentation`。这些基础设施与性能 profile 资格分开审查。

## 36.5 主要实验与实施步骤

实际运行顺序为：h5/h3 MPI4 baseline；h5 MPI1/2/4 rank 诊断；H1 release-base h5→h3；H5/H6 的 MPI2、SuperLU_DIST、OOC、BLR、ordering h5 筛选；唯一正式 MPI2 候选 h5→h3；h2 外推与 Gate；最后按 review 进行 PETSc/MUMPS/BLAS 静态审计和固定四核 h5 MPI4×1、MPI2×2、MPI1×4、MPI1×1。

没有运行 h2 direct；没有在 h5 线程 Gate 失败后运行 threaded h3；没有重建 image 或在 Task029 实现 multilevel solver。建议模板中的 MPI1×2 是可选补点，但 MPI1×4 已同时触发 T0/T1/T3 stop，继续补点不会改变能力身份。

## 36.6 关键结果

### KSPSetUp / MUMPS factorization 是主峰

h3 从 `before_ksp_setup` 到 `during_ksp_setup_peak`，worker RSS/cgroup 分别增加约 6472.43 / 6474.57 MiB。KSPSolve 结束只比 factorized checkpoint 多约 6.98 MiB worker RSS；official RTA 增量不足 1 MiB；field output 形成约 129.06 MiB 的较低尾部平台。base/augmented 共存约增加 729 MiB worker RSS，只占总峰值约 8%–9%。

h3 factor/augmented nnz 比为 12.484；统一 nnz-storage estimator 约 6093/489 MiB。前者是结构计数，后者是估算，不是 MUMPS allocator 实测。

### H1–H7 与候选结果

下表中“相对变化”为同 h 的 `baseline - candidate` 再除以 baseline：正数表示内存减少，负数表示恶化。

| 路线 | h5 worker RSS 变化 | h3 worker RSS 变化 | 数值 | 最终处置 |
|---|---:|---:|---|---|
| H1 release-base MPI4 | +4.767% | +5.462% | pass | 合并显式低风险生命周期控制；非 profile |
| H2 preallocation rewrite | not_run | not_run | `mallocs=0`,`nz_unneeded=0` | 无 allocator 正证据，拒绝 speculative rewrite |
| H3 cleanup/temporaries | 非主峰收益 | full flow 保持 | pass | 合并幂等 failure cleanup |
| H4 direct A_aug assembly | not_implemented | not_implemented | 无 public safe API | 不使用 private framework hack |
| H5 MUMPS MPI2 | +28.893% | +15.119% | pass | 最佳诊断点；h3 未达 20%，拒绝 profile |
| H5 SuperLU_DIST | -14.462% | not_run | pass | 内存和时间负向 |
| H6 MUMPS OOC | +13.744% | not_run | pass | 559,715,776 bytes scratch、1.539×时间；仅 fallback |
| H6 BLR 1e-5 | -3.427% | not_run | fail | residual `4.704e-3`，拒绝 |
| H6 ordering ICNTL(7)=3 | -4.093% | not_run | pass | factor nnz/峰值增加，拒绝 |
| H7 early factor release | 只影响尾部 | not_run | 风险较高 | 不是全局峰值修复，本任务不实现 |

### 少 rank + 多线程最终结论

静态审计确认 PETSc 3.24.0 / MUMPS 5.8.1 通过 `-llapack -lblas` 动态链接 system OpenBLAS 0.3.26 pthread；OpenBLAS API 能读取并修改线程数。NumPy 使用独立 scipy-openblas 0.3.29，只作 Python 侧交叉检查，不代表 MUMPS。活动 PETSc/MUMPS 未显示 OpenMP 构建，正式线程运行固定 `OMP_NUM_THREADS=1`，避免 OpenMP 嵌套；但两个 OpenBLAS runtime 可能形成多个线程池，runnable-thread oversubscription 不能完全排除，CPU affinity 只负责把实际执行封顶在 `0-3`。

| 固定 CPU 0-3 | worker RSS | KSPSetUp | Stage4 | KSPSetUp CPU 核均值/峰值 |
|---|---:|---:|---:|---:|
| MPI4×1 | 2351.707 MiB | 2.385 s | 18.311 s | 3.906 / 4.061 |
| MPI2×2 | 1677.062 MiB | 1.953 s | 20.687 s | 3.272 / 4.025 |
| MPI1×4 | 1399.648 MiB | 23.841 s | 48.273 s | 0.999 / 1.054 |
| MPI1×1 | 1401.988 MiB | 25.578 s | 50.891 s | 0.999 / 1.060 |

MPI1×4 的 worker thread 数从 3 增至 12，但 KSPSetUp 仍约 1 核，Stage4 相对 MPI1×1 只有 1.054× speedup。T2 内存比通过（RSS/cgroup 均远低于 1.20×），但 T0 runtime、T1 与 T3 失败；最终身份是 `threaded_direct_capability=unavailable_in_current_image`，T4 要求 threaded h3=`not_run`。

## 36.7 结果解释

主导机制是 LU fill，而不是 auxiliary DoF 或后处理。提前释放 base 对象只能回收次要共存量；减少 rank 能减少进程重复和总 RSS，却削弱分布式 factorization 并行。OOC 把部分 RAM 压力转成 scratch/I/O；BLR 则引入当前阈值不可接受的近似误差。

线程审计进一步说明：有可控 pthread 和更高进程 thread count，不代表 MUMPS factorization 会多核执行。MPI1×4 的实际 CPU 证据与 MPI1×1 相同，因而不能用静态 BLAS 能力或 NumPy matmul 证明 threaded direct 可用。

## 36.8 h2 预测与 G1–G10

DoF 幂律与 factor-nnz/fill 两条路径给出 h2 中央预测 22.214 / 22.330 GiB，敏感性范围 18.882–27.913 GiB。这里属于外推，不是实测 h2。

| Gate | 状态 | 含义 |
|---|---|---|
| G1/G2 | true | h5/h3 MPI2 数值通过 |
| G3 | false | h3 只降 15.119%，没有双网格 20% |
| G4 | true | h3 无 swap |
| G5 | false | 预测上界高于 13.5 GiB |
| G6 | true | 13.5 GiB 安全上限未放宽 |
| G7 | false | 当前可用内存低于预测下界 |
| G8 | true | 只有一个最终诊断候选 |
| G9 | false | 早期 Gate 已失败，未实现/启用 h2 watchdog |
| G10 | true | Task28 h2 record 未覆盖 |

因此 `h2 = not_run`，不是 pass、fail-run 或 skipped-without-reason。

若未来确有 direct h2 需求，资源规划应使用至少 48 GB、优先 64 GB 的机器，并先实现 watchdog/clean-abort；这不构成当前工作站运行许可。

## 36.9 成功路线、失败路线与负结果

成功并建议保留的是 telemetry、matrix/factor inventory、clean provenance、异常 cleanup、factor package 选择正确性、OOC 证据、显式 release-base 控制、Case050 与 h2 guard。它们改善可观测性、正确性或安全性。

失败或只作诊断的是 MPI2、OOC、BLR、SuperLU_DIST、ordering 和当前镜像 threaded direct；都不得提升为 ordinary/recommended profile。COMSOL GMG 只提供“未来可研究完整多层层次”的定性线索，不是本任务 runtime、R/T/A 或每 DoF benchmark。

## 36.10 最终决策与合并边界

| 对象 | 决定 | 原因 |
|---|---|---|
| telemetry / Case050 / h2 guard | V2 通过，允许合并 | 可复用且有合同测试 |
| failure cleanup / package selection fix | V2 通过，允许合并 | 正确性与异常安全 |
| release-base option | 建议合并，保持默认 false | 低风险，收益不足 profile 资格 |
| MPI2/OOC/BLR/SuperLU/ordering | 不提升 | 内存、时间或数值 Gate 失败 |
| threaded direct | 不创建 profile | 当前 image KSPSetUp 仍单核 |
| ordinary default | 不改变 | 无候选同时通过工程 Gate |
| h2 / threaded h3 | 不运行 | 分别被 G/T Gate 阻止 |
| master | 用户已许可，待执行合并 | V2 技术审查通过；Task030 启动请求提供明确许可 |

## 36.11 局限

factor storage 是 nnz estimator；部分 PETSc/MUMPS raw memory/fill 字段不可用。CPU 核数由 0.25 s `/proc` 累计 CPU 时间差分，不是硬件计数器。线程结论只适用于当前 image、目标矩阵与固定四核条件。完整 field/mesh/timeline 保存在本地 ignored artifacts，不进入 Git。物理 residual/closure 通过也不等于 h3/h2 R/T/A 已完成网格收敛。

## 36.12 下一步及原因

由于对象生命周期、ordering 和当前 BLAS 线程都不是主峰解法，停止继续 direct 微调。下一阶段应优先做 h3/h2 物理网格收敛或 graded/adaptive mesh qualification；若继续降低 solver memory，则研究真正 multilevel H(curl)、low-order-refined multigrid 或带受控 coarse direct solve 的并行 physical Schwarz。只有更换为明确支持 threaded factorization 的构建时，才重新执行固定四核 h5 能力审计。

## 36.13 证据入口

- [Task029 outcomes summary](task029_stage4_direct_memory_forensics/outcomes/summary.md)
- [线程能力审计](task029_stage4_direct_memory_forensics/outcomes/threaded_direct_capability_audit.md)
- [h2 launch decision](task029_stage4_direct_memory_forensics/outcomes/h2_launch_decision.md)
- [Task029 review V1](task029_stage4_direct_memory_forensics/review_report_v1.md)
- [Task029 response V1](task029_stage4_direct_memory_forensics/response_v1.md)
- [Task029 review V2](task029_stage4_direct_memory_forensics/review_report_v2.md)
- [Task029 response V2](task029_stage4_direct_memory_forensics/response_v2.md)
- [Benchmark Case050](../benchmarks/cases/050_stage4_direct_memory_forensics/README.md)
- [Task 回顾标准](task_retrospective_standard.md)
- [direct runner](../benchmarks/run_direct_memory_forensics.py)
- [direct profile walkthrough](../notes/reference/code_walkthrough/30_direct_solver_profiles.md)

---

# 37. 当前未完成问题

## 37.1 Task028 收口问题

```text
- Response V4 已关闭 tracked-source-clean、真实 image digest 和最终提交验证，并以 2f9e56d 合入 master；
- complex MPC base image尚无公开pull source，环境保持qualified；
- `SmallDenseInverse`显式逆、内部下划线依赖和异常路径统一清理为非阻断技术债。
```

## 37.2 Task029 当前问题

```text
- h5/h3 baseline、归因和最多两个 h3 候选均已完成；
- 最佳 h3 只下降 15.119%，未达到 engineering_success；
- h2 预测区间 18.882–27.913 GiB，G3/G5/G7/G9 失败并明确 not-run；
- review V1 更正、V2 技术验收与 response_v2 状态同步均完成，用户已许可合并；
- 当前 image 的 threaded direct 不可用，threaded h3 按 T4 未运行。
```

## 37.3 数值和物理问题

```text
- h=1.5 production solve；
- physical R/T/A mesh convergence；
- local/adaptive mesh refinement；
- angle/wavelength/material robustness；
- near-Rayleigh conditions；
- parameter reuse/warm start；
- lower iteration count and higher throughput；
- slab-internal parallelism / true multilevel H(curl) method。
```

这些扩展在 Task028 期间暂停。

---

# 38. 当前推荐开发顺序

Task28 合并与 Task29 执行已完成。当前强制顺序：

```text
1. Task029 `response_v1.md`、全部 P0 更正和 V2 技术验收已完成；
2. 提交 `response_v2.md` 并完成轻量 release checks；
3. 按用户许可合并 Task029 后，从更新的 clean master 新建 Task030 分支；
4. 不提升 MPI2/OOC/BLR/SuperLU/ordering 为低内存 profile；
5. 不在当前工作站运行 h2 direct；
6. 后续优先物理收敛资格化或真正 multilevel H(curl) 研究。
```

Task028 完成后，如重新开启研究，推荐顺序：

```text
A. h=2 physical mesh convergence / local refinement；
B. fixed profile small angle/wavelength/material qualification；
C. warm start and cache reuse for scans；
D. iteration/time reduction；
E. h=1.5 preflight；
F. slab-internal parallel or true H(curl) multilevel solver。
```

---

# 39. 文档维护规则

每个后续阶段完成后，应同步更新：

```text
docs/development_progress.md
docs/capability_matrix.md
notes/reference/current_version_boundaries.md
benchmarks/benchmark_summary.csv
对应 task outcomes/review
```

更新原则：

```text
- 后续证据覆盖早期结论；
- 成功和负结果分开；
- 研究正信号不包装为 production；
- 未收敛不输出 official R/T/A；
- reported residual 必须与 explicit true residual 区分；
- ordinary default 变化必须显式审查；
- benchmark 必须记录 commit 和环境。
```

---

# 40. 当前一句话状态

> 项目已经从基础 2D/3D Maxwell、Floquet 和 DtN 验证，发展到可在约 14 GB 工作站上用 MPI4 对目标 p=2、h=2 三维 EUV 光栅取得全增广真残差小于 \(10^{-6}\) 的限定迭代解；Task028 已合入 master，Task029 以 `diagnostic_success` 收口并确认 MUMPS KSPSetUp/factorization 是 direct 内存主瓶颈。最佳 h3 候选只下降 15.119%，当前 image 的 MPI1×4 KSPSetUp 仍约 1 核，故 engineering_success=no、threaded direct unavailable、threaded h3 与 h2 均按 Gate 未运行。

---

# 41. Task030：3D H(curl) 多层与低内存迭代研究

## 41.1 任务身份与为什么启动

```text
Task = Task030
branch = codex/20260713-task30-multilevel-hcurl-low-memory-iterative
base master = bfb6586e030efd5208ebd796c39fdc31301e1d6e
physical model = Task27/28 frozen p2 Stage4 target
ordinary default changed = no
current classification = workstation_memory_success_with_qualifications
```

Task029 已证明 direct 的内存主峰在 MUMPS analysis/factorization；MPI2、OOC、BLR、ordering 与线程都没有得到可提升的 h3 工程收益。Task027 虽能在约 14 GB 内完成 h2，但 16 个大 slab ILU1、shifted-F 副本和 FGMRES basis 仍让 h2 达到 13.08 GB。因此 Task030 转向 H(curl) 层级、低 fill smoother、对象生命周期和 Krylov memory，而不继续微调 direct。

COMSOL 报告只提供定性依据：真正多层 Maxwell PC 可能明显低于 direct；它不是当前 FEniCS R/T/A reference，也不能用于跨机器时间排名。

## 41.2 冻结基线与数值合同

物理保持 50×25×140 nm cell、17×25×120 nm Si grating、13.5 nm、theta=80°、phi=0、s polarization、p2 Nédélec、双 Floquet、80 个 auto-propagating modal unknowns、exact matrix-free `F-C H^-1D`、full true residual 和 official modal R/T/A。

Task027 baseline 为 h5/h3/h2 的 1201/993/1804 步和 1.991/5.08/13.080 GB。Case031 h5 100-step residual `2.5737371765314062e-3` 由 SHA-256 pinned record 读取，候选不得手写或覆盖基线。

## 41.3 层级与 transfer 基础设施

实现 `ActiveDofMap`，将 MPC slaves 从 coarse columns 中移除，再逐 active column 用 DOLFINx nonmatching interpolation 构造 p1→p2 H(curl) transfer；每列执行 MPC backsubstitution/homogenize，restriction 为 Hermitian transpose。transfer 支持 MPI CSR cache，fresh/cache action 可复核。

MPI4 目标规模：fine h5/p2 full/active/slave 为 44,698/40,800/3,898；coarse h10/p1 为 1,067/792/275；P 有 145,998 nnz、无零列、adjoint error `1.586e-15`、fresh/cache error `6.410e-15`。精确 coarse operator 使用 `P^H(F-CD)P`，保留全部 80 modes；serial/MPI2 action tests 通过。

这部分达到 infrastructure success，但没有直接得到 solver success。

## 41.4 多 lane 漏斗与负结果

| lane | h5 100-step true residual | 相对基线 | 结论 |
|---|---:|---:|---|
| Jacobi + p/h coarse | 0.680155 | 264.27× | negative |
| z-layer patch + p/h coarse | 0.374864 | 145.65× | negative |
| vertical column + p/h coarse | 0.513599 | 199.55× | negative |
| cell patch + p/h coarse | 0.512730 | 199.22× | negative |
| 16-slab ILU0 + p/h coarse | 0.561064 | 218.00× | negative |

相同 slab smoother 不加 p/h coarse 的 20-step residual 为 0.381817，加 coarse 后反而为 0.685751。说明 transfer/Galerkin 正确，但 792D p1 coarse 没有覆盖当前 Maxwell 近核、梯度和 grazing-wave 慢方向。当前不能声称 pure h-GMG、mixed p/h 或 AMS/HX 成功。

全 80 mode Woodbury 只提供很小改善且增加内存；225D x-harmonic coarse、更多 z hats、去 overlap pre-only、单次廉价 post 和 restart80 都未过 Gate。失败实现没有进入 ordinary default。

## 41.5 正反馈如何继续深化

Task027 ILU1 overlap PC 增加真正 post smooth 后，h5 100-step residual 变为 `1.273503e-3`，达到 strong-positive。此后逐步验证：

1. ILU0 仍为 `1.865566e-3`，说明对称组合后 fill1 不是必要条件；
2. local diagonal shift 不保留完整 shifted-F，residual 不变；
3. factor-only 逐块 setup 后销毁 source submatrix/KSP，只保留因子，action serial/MPI2/MPI4 等价；
4. restart90 仍通过 weak-positive，restart80 失败，因此停止继续缩小。

最终候选固定为 75D wave coarse、16 slabs overlap0.25、ILU0、sm2 symmetric pre/post、local shift、factor-only、right FGMRES(90)。这不是“真正多重网格成功”，而是现有有效 coarse 与更低内存 smoother/lifecycle 的工程改进。

这里的 ILU0 结论只表示“该冻结目标在对称组合下不需要配置 ILU1 才能收敛”。Task27 ILU1 与 Task30 ILU0 的 `global_slab_factor_nnz` 完全相同，当前统计口径不能证明 stored fill 下降。可归因的内存改进是 local shift、factor-only 释放 source submatrix/KSP/PC wrapper 以及 restart90；factor nnz 保持 `measurement_unresolved`。

## 41.6 h5/h3/h2 正式结果

| h | DoF | iterations | full true residual | peak incl RTA | R/T/A | direct max delta |
|---:|---:|---:|---:|---:|---|---:|
| 5 | 44,698 | 855 | 9.924905e-7 | 1.687653 GB | 0.0890216035 / 0.4425882732 / 0.4683901222 | 5.438e-9 |
| 3 | 198,438 | 962 | 9.903890e-7 | 3.792912 GB | 0.00461303218 / 0.58365335775 / 0.41173361173 | 7.719e-10 |
| 2 | 615,108 | 1873 | 9.972228e-7 | 9.374729 GB | 0.00134293442 / 0.59921323601 / 0.39944383222 | 6.561e-9 |

h3 较 Task027 canonical 5.082275 GB 下降 25.37%，h3/h5 iteration ratio 为 1.1251。其 3.792912 GB 同时通过 3.8 GB 绝对线和“相对下降至少 25%”分支。reported/condensed/full residual、80 modes、R/T/A 与 closure 全通过；h5/h3 均为 clean final-HEAD rerun。

## 41.7 h2 预测、实测与当前边界

h5/h3 的 DoF–RSS 仿射/幂律两个独立模型预测 h2 中央值为 9.5298/7.0337 GB；较保守仿射值的 15% engineering upper 为 10.9593 GB，满足 G5/G6。唯一候选 attempt1 的实测峰值为 9.342113 GB，较 Task027 降低 28.58%；1800 步 solve time 2220.43 s，也略低于 Task027 2345.26 s。

attempt1 真残差为 `1.461130e-6`，所以未输出 official R/T/A。随后只对同一 PC/restart 将 max_it 延到 2100；共同 monitor 点残差逐位一致，并在 1873 步收敛。最终 full residual `9.972228e-7`、含 R/T/A 峰值 9.374729 GB、closure `2.639e-9`、direct 最大差 `6.561e-9`。Review V2 明确不重跑 h2，因此这些值的身份是 `reviewed_historical_dirty_worktree_reference`，不是 clean final-HEAD evidence；h2/h3 iteration ratio 为 1.947，且 1873 步仍高于 1200 偏好。

## 41.8 合并边界

建议 final review 接受的内容：nonmatching H(curl) transfer/cache、condensed Galerkin 研究基础设施、local shift、factor-only storage、symmetric pre/post opt-in、Case060、tests 和完整文档。不得提升 p/h solver profiles、Woodbury、x-harmonic、AMS/HX、restart80 或 heavy artifacts。validated infrastructure API 已与失败 candidates 隔离；Task027 canonical 和 ordinary default 均保持不变。master 仍等待 Response V2 后的 final review 与用户明确许可。

## 41.9 局限与下一步因果关系

h2 已收敛，但当前 evidence 只覆盖单个角度/波长/材料/分区，且 1873 步仍高于 1200 目标。下一步优先参数鲁棒性、fallback 和 restart/内存监控；若目标是进一步降低迭代数，应研究 Maxwell commuting projection、梯度/近核 auxiliary space 和材料/端口感知的真正多层 hierarchy，而不是继续扩大当前失败 p1 coarse。

证据入口：

- [Task030 outcomes](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md)
- [Case060](../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md)
- [candidate funnel](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/candidate_funnel.csv)
- [transfer validation](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/transfer_validation.md)
- [h2 decision](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/h2_launch_decision.md)

## 41.10 Review V1 更正与证据边界

Review V1 的五项 P0 已在同一分支回应：正式 h5/h3/h2 lightweight records 补齐实际运行 provenance；Case060 checker 从文件存在性升级为 provenance、solver identity、80 modes、三残差、R/T/A、closure、direct delta、内存和分类的 203 项 Gate；manifest 加入三份 experimental entries，normal checker 连续生成保持一致；项目级命名统一为 `compact physical-slab low-memory experimental profile`；理论、walkthrough、capability、benchmark 和边界文档同步说明 p/h multigrid solver 失败。Review V2 又把 h5/h3 更新为 clean final-HEAD rerun，并把 h2 固定为 historical dirty-worktree reference。

最终成功求解器身份固定为 `task27_derived_physical_slab_wave_coarse`。H(curl) transfer/Galerkin 是 validated research infrastructure，不是 successful GMG。factor-only 在 PETSc 3.24.0 complex build 通过生命周期测试；跨版本兼容仍需回归。Task27 ILU1 与 Task30 ILU0 的 reported slab-factor nnz 相同，因而不把内存下降解释为已证明的 factor-nnz compression。

## 41.11 Review V2：clean evidence 与 selective-merge 边界

R1 在 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上重跑 h5/h3。两次 record 均写 `git_dirty=false`、`tracked_source_dirty=false`、`tracked_source_verification=host_git_clean_attestation`，且 verified clean SHA 与容器 HEAD 完全一致。h5 heavy JSON SHA-256 为 `2be05820cf69db67ba72b257c44624c08e15f7f7ceeae6e479eed2a9e68523f3`；h3 为 `48c9bb51b89a99b7ba1653f8c95f8450e7917f987274c1aef631464484275232`。h2 按审查要求不重跑，保留 `reviewed_historical_dirty_worktree_reference` 身份，并显式链接 clean h5/h3 的 solver/physics 等价性。

R2 把 `hcurl_multilevel.py` 的 validated infrastructure API 限定为 active DoF、nonmatching transfer/cache/validation 和 condensed Galerkin。Damped Jacobi、Galerkin multilevel PC、Modal Woodbury 等 solver-negative candidates 只由 research runner/tests 直接导入，普通 `src.solvers` 不导出。最终工程求解器仍是 Task27-derived compact physical-slab profile，不是 p/h GMG。

因此 Task030 最终状态为 `workstation_memory_success_with_qualifications`。ordinary default 不变；当前分支只可提交 Response V2 并等待 final review，不能直接合并 master 或启动 Task31。Task31 必须在用户批准 selective merge 后，从 clean master 新建独立分支。

---

# 42. Task030 后的当前推荐顺序

```text
1. 提交并推送 Task030 Response V2；
2. 等待 ChatGPT final review，ordinary default 不变；
3. 用户明确批准后，按 selective merge 边界合入 master；
4. 在合并后的 clean master 新建 Task31 独立分支；
5. Task31 优先压缩 Krylov、F/condensed 重复对象、slab factors 与生命周期。
```

# 43. 当前一句话状态（Task030）

> Task030 已获得 `workstation_memory_success_with_qualifications`：Task27-derived compact physical-slab profile 的 clean final-HEAD h5/h3 分别为 855/962 步、1.687653/3.792912 GB，h2 保留为 1873 步、9.374729 GB 的 reviewed historical dirty-worktree reference；80 modes 与 official R/T/A 通过，H(curl) transfer/Galerkin validated infrastructure 正确，但 792D p1 coarse 的 p/h multigrid solver 明确失败。ordinary default 未改变，master 等待 final review 与用户选择性合并许可。

---

# 44. Task031：compact physical-slab 内存优先结构优化

## 44.1 最终状态

```text
Task = Task031
branch = codex/20260714-task31-compact-pc-memory-optimization
base = Task030 merged master 545165b3d29396dcc3a8d5b029089175eafa3c4a
clean implementation SHA = 45a0fc6e19535cb8f14fbfb186f099019612fec2
classification = strong_memory_success_slow_but_memory_efficient
ordinary_default_changed = false
review_status = Review V1 response_v1 hardening complete; pending final review
master_decision = pending review and explicit user approval
```

## 44.2 为什么启动

Task030 已把 h2 从 Task027 的 13.08 GiB 压到 9.374729 GiB并真实收敛，但对内存受限工作站仍接近 10 GiB。Task030 也证明当前 p/h coarse 不是有效慢误差空间，因此 Task031 不再扩大失败层级，而是围绕已经能收敛的 physical-slab + 75D wave coarse，逐项审计 Krylov basis、assembled fine `F`、slab factor、对象重叠和 PC 合法性。

如果不做这一步，工程风险有两个：一是用 per-rank historical peak sum 或 current RSS 下降误判真实峰值；二是为了省 Krylov 存储把非线性 PC 错配给普通 GMRES，得到不受支持的算法。Task031 不解决任意材料/角度鲁棒、真正 mesh-independent multigrid或多 RHS 吞吐。

## 44.3 冻结问题与 baseline

物理仍为 50×25×140 nm cell、17×25×120 nm complex-Si block、13.5 nm、theta80/phi0/s、p2 Nédélec、double Floquet、80 个 auxiliary DtN modes、exact `F-C H^-1D` 与 official volume-absorption R/T/A，MPI4。ordinary config、模式数、物理、RTA 定义与 full residual 都禁止改变。

Task030 baseline：h5/h3/h2 为 855/962/1873 步，full residual 都 `<=1e-6`，peak 1.687653/3.792912/9.374729 GiB。Task031 h3 continuation 需要 `<=3.50 GiB` 或降幅 `>=8%`；h2 解锁还要求 h3 full pass 且降幅 `>=8%`、两套中心预测 `<=8.8 GiB`、保守上界 `<=10 GiB`、无 swap、clean source 和 watchdog。

## 44.4 采用的方法

### 外部同时内存权威

`run_task031_memory_forensics.py` 每 0.25 s 同时采样 live MPI ranks 的 RSS sum、MPI process tree、cgroup current/peak、线程/CPU 和 WSL swap，并从 runner 的 stage JSONL 标注峰值阶段。它不把各 rank 在不同时刻的历史最大值相加。h2 额外强制 `--unlock-h2`、9.5 GiB warning 与 11 GiB controlled termination。

### Assembled-F-free public MPC form action

`mpc_form_action.py` 把 active vector 写入 MPC Function，backsubstitute 后通过 public `dolfinx_mpc.assemble_vector(ufl.action(...))` 计算 action，并显式恢复 MPC slave unit rows。最初遗漏 unit rows 时误差约 0.0263；修复后 h5/h3/h2 action error 都 `<1e-15`。`CondensedDtnOperator` 接受 external fine action，并通过 `require_f/release_f` 只让 assembled `F` 存活到 coarse/slab setup 完成；solve ledger 中没有 `F`。该路径只是 solve 阶段 assembled-F-free，不是缓存优化的低层 element-kernel matrix-free；每次 apply 仍发生 Function/MPC/form assembly 与通信。

### Slab、lifecycle 与合法性

overlap0.125 缩小 factor；compact lifecycle 在 RTA 前释放 KSP/PC/factors/work vectors；exact SHA-256 fingerprints 只允许完全相同 factor 共享。PC certificate 用随机向量检查 linearity/determinism：Task030 adaptive local GMRES PC 的线性误差为 `2.374308e-2`，因此普通 GMRES fail closed，必须保留 flexible Krylov。固定 Richardson 虽达到 `3.611e-15`，却失去收敛能力。

## 44.5 实验漏斗与负结果

| lane | 关键观测 | 决定 |
|---|---|---|
| FGMRES50 | worker RSS -1.89%，residual/time 更差 | `<3%` 停止 |
| ordinary GMRES | PC linearity `2.374308e-2` | 算法不合法，fail closed |
| fixed Richardson | linear，但 200 步 residual 0.7703 | numeric negative |
| 16 slab overlap0.125 | factor nnz -19.59%，residual 略差 | weak positive，进入组合 |
| 20 slab overlap0.125 | factor/RSS/residual 均差于16 slab | 停止 |
| boundary Jacobi1 | stored factor -9.95%，residual 恶化约13.7x | 停止 |
| exact factor dedup | 16/16 fingerprints unique | 无可共享 factor，停止 |
| assembled-F-free public form action | action 等价，200步 RSS约 -2–3%，时间3.18x | 内存优先保留 |

h3 第一次在 max_it1600 时 full residual 为 `5.490e-6`，严格判负；任务书允许 h5/h3 上限 5000 且不以高迭代数自动判失败。同一配置提高安全上限后在 1994 步通过，残差历史与第一次共同点逐位一致，证明是延长同一过程而非参数漂移。

## 44.6 h5/h3/h2 正式结果

| h | DoF | iterations | full residual | simultaneous worker peak | cgroup peak | solve/total s |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,157 | `9.959903e-7` | 1.619598 GiB | 1.056248 GiB | 350.851 / 374.342 |
| 3 | 198,438 | 1,994 | `9.973853e-7` | 3.474346 GiB | 2.899216 GiB | 2311.581 / 2370.351 |
| 2 | 615,108 | 1,977 | `9.998454e-7` | 7.897675 GiB | 7.424026 GiB | 11982.581 / 12173.086 |

三份 run 都来自 clean SHA `45a0fc6e...`、同一 image digest 与 MPI4。h3 external simultaneous peak 3.474346 GiB，通过 3.50 GiB 绝对线；相对 Task030 历史口径的观察降幅 8.399% 只作辅助。h2 external simultaneous / legacy internal peak 为 7.897675 / 8.176441 GiB，相对 Task030 历史值的辅助对照约降 15.8% / 12.8%；保守工程结论约 8.0–8.2 GiB。h2 通过 strong `<=8.0 GiB` external Gate，但未达到 stretch `<=7.0 GiB`。峰值在 `outer_krylov_solve`；coarse operator ready 7.867531 GiB，solver release/RTA 约 6.50 GiB。swap in/out=0，watchdog 未触发。

## 44.7 h2 预测与条件解锁

h5/h3 DoF–RSS 仿射外推给出 8.501130 GiB；Task030 h2 按 h3 实测比例迁移给出 8.587349 GiB。以 h5 最弱的 4.032% 收益应用到 Task030 h2 后再加 5% 余量，保守上界为 9.446530 GiB。三者全部过 Gate，才解锁唯一 h2 candidate。实测 7.897675 GiB 低于两套中心预测和上界；没有运行第二个 h2，因为首个已经 `<8.0 GiB`，也没有机制不同且预测 `<=7.5 GiB` 的候选。

## 44.8 数值正确性与 R/T/A

h5/h3/h2 的 reported、condensed true 和 full augmented true residual 一致。official R/T/A 为：

```text
h5 = 0.089021602568 / 0.442588275323 / 0.468390124569
h3 = 0.004613031629 / 0.583653357934 / 0.411733610310
h2 = 0.001342934186 / 0.599213235569 / 0.399443835926
```

energy closure 分别为 `2.460e-9 / -1.270e-10 / 5.682e-9`；对 direct 最大 delta 为 `6.162e-9 / 1.104e-9 / 6.125e-9`，都远低于 `1e-6`。这排除了仅 reported residual 收敛或 public form-action wrapper 改变物理解的可能。

## 44.9 结果解释

Task031 的收益不是来自单一“神奇 PC”。solve 阶段不常驻 assembled `F`、slab factor 规模与 solver/RTA 对象重叠是三个正交来源；restart50 的 payload 模型下降没有转化为足够的 full-process peak。相对 Task030 历史口径的 h5/h3/h2 百分比只能作为趋势证据，不能包装成严格同 sampler 的精确 A/B。

代价同样清晰：public form action 每次需要 MPC field 写入/backsub/assembly，h2 约 13,960 次 form apply，使 solve 达 11982.581 s，是 Task030 的约 5.01x。迭代数只增加约 5.55%，每步平均成本约增加 4.74x；一次性 `release_f()` 不是主要耗时。因此最终分类必须同时包含 strong memory success 和 slow-but-memory-efficient，不能只报道 7.898 GiB。

## 44.10 最终决策与合并边界

建议 review 后选择性合并 external sampler/watchdog、public MPC form action、safe condensed lifecycle、PC certificate、object ledger、测试、Case070 与文档。最终 candidate 只作为显式 opt-in memory-first profile；ordinary default 不变。

不得提升 fixed Richardson、boundary Jacobi、restart50、20-slab 或 approximate factor sharing。16 个 factor 没有 exact duplicate，因此不存在 dedup implementation。不能把 release 后 current RSS 下降冒充 peak success，也不能把冻结 target 的验证写成任意参数数学保证。

## 44.11 局限与下一步因果关系

当前证据只覆盖一个物理/RHS、MPI4 partition 与当前 image；运行方差、其他机器、参数扫描、多 RHS 和跨 PETSc 版本未验证。Task030 与 Task031 的 memory sampler 口径并非完全一致，故所有轻量 record 同时保留 external simultaneous、cgroup 与 legacy internal 值。

下一步若追求平衡，应优化 public form action 的缓存/批量路径，或设计固定线性且有足够平滑能力的 polynomial/Chebyshev local action；不应继续压 restart 或近似共享 factor，因为已有负证据。新路线必须从 h5 action equivalence、PC legality、true residual 与 simultaneous peak 联合 Gate 开始，再进入 h3/h2。

## 44.12 证据入口

- [Task031 task](task031_compact_physical_slab_memory_optimization/task.md)
- [Task031 outcomes](task031_compact_physical_slab_memory_optimization/outcomes/summary.md)
- [迭代求解器端口与合法性](iterative_solver_ports.md)
- [Case070](../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md)
- [h2 prediction](task031_compact_physical_slab_memory_optimization/outcomes/h2_memory_prediction.md)
- [negative results](task031_compact_physical_slab_memory_optimization/outcomes/negative_results.md)
- [matrix-free validation](task031_compact_physical_slab_memory_optimization/outcomes/matrix_free_validation.md)
- [iterative theory](../notes/theory/iterative_solver_and_preconditioner.md)
- [workstation runtime walkthrough](../notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md)

---

# 45. Task031 后的当前推荐顺序

```text
1. 完成 Task031 分支 full tests、Case070 checker 与 clean-tree 审计；
2. 推送分支，等待 ChatGPT Task031 review；
3. 按 review 修正，不静默改变 ordinary default；
4. 用户明确批准后才选择性合并 master；
5. 后续若继续，优先降低 public form-action apply 时间，而不是重复已失败的 restart/dedup 路线。
```

# 46. 当前一句话状态（Task031）

> Task031 在 clean MPI4 frozen target 上以 assembled-F-free public MPC form action、16 slabs overlap0.125 与 compact lifecycle 实现 h5/h3/h2 全部 true-residual + official-RTA 通过；h2 1977 步，external simultaneous / legacy internal 为 7.897675 / 8.176441 GiB，保守工程范围约 8.0–8.2 GiB，达到 `strong_memory_success_slow_but_memory_efficient`，但 solve 约 5.01x，ordinary default 未改变；Review V1 数值/内存通过，文档加固见 response_v1。

---

# 47. Task035 Phase C/D：estimator 与 mesh-backend bake-off

Review V3 接受 B1/B2 real-FE minimum Gate 后，Phase C/D 在同一执行分支连续完成。Phase C
复用 Task034 accepted p2/p3/p4 field samples，对固定 13.5 nm、10° grazing、S 入射结构筛选
sampled R1、discrete two-level R5 proxy、external DtN split 与 R2 diagnostic。R5 proxy 对
p4/h5 best-available discrete error 的局部相关性为 0.989–0.998，但不是 formal hierarchical FE
solve；sampled R1 相关性为负。Task034 strip/tensor actual PDE 细化证据继续失败 physical gates，
且不是 estimator-marked refinement，所以没有 production estimator。

B3 actual material-interface/corner Nédélec fixture 与 B4 accepted Hybrid Et/Ht、M80/120/160、
DtN/QEP microfixture 均通过 serial/MPI2。Phase D 比较三条 backend：strip/tensor 保留
`controlled_negative`；conforming multi-block hexa 因 Cartesian axis-cut leakage 记录
`hexa_backend_blocker`；tetra actual marked-refine control 从 384 到 1392 cells，正体积、局部性与
Nédélec proxy improvement 通过，但只作为 research control。

首次 MPI2 tetra volume measurement 因 topology vertex ID 错用于 refined geometry indexing
产生伪零值，失败 record 已保留；改用 `geometry.dofmap[cell]` 后 final serial/MPI2 identity 通过。
最终状态为：

```text
phase_c_internal_gate = complete_controlled_negative
phase_d_internal_gate = complete
production_estimator_selected = false
production_backend_selected = false
ordinary_default_changed = false
phase_e_unlocked = false
```

未运行 Phase E/F、目标 adaptive cycle、p4/h5 heavy 或 ordinary-default change。

# 48. Task038：input-driven configuration

Task038 用一个显式 `.dat` 文件统一描述 geometry、materials、incidence、discretization、boundary、method、solver、execution 和 output。这样用户提交的是一份可审查、可复现的配置合同，而不是在多个 preset 或命令行参数之间拼接物理值；它改变用户配置方式和入口，不改变 Maxwell、Hybrid、DtN 的数学实现，也不改变 ordinary defaults。

| 项目 | 当前边界与证据 |
|---|---|
| 迁移范围 | 11 个 ordinary preset 已迁移到 dat；6 个 research/history preset 保留原有 Python replay。 |
| 已连接入口 | ordinary 2D、staged 3D、Full3D direct、Hybrid direct、Hybrid iterative adapters；普通入口为一个 `.dat`。 |
| provenance | 运行 manifest 保存 input/source/physical/resolved-config hash 及执行身份，供结果目录和审阅记录回溯。 |
| source branch inherited evidence | source branch full pytest：1119 passed / 48 skipped / 0 failed / 1514.73 s；这是 inherited source evidence，不是本 integration worktree 的测试结论。 |
| integration status | integration full pytest = `not_run_yet`；本阶段不把它写成通过。 |
| T6 resource boundary | RSS `6585.01953125 MiB`；数值 Gate 通过，但 preferred resource boundary 未满足；这不是数值失败。 |
| 尚未运行项 | current-same-SHA Hybrid iterative MPI1 formal = `not_run`；T4/T5 selected-field capability = `not_run_by_capability`。 |
| 详细入口 | [`Task038 outcomes summary`](task038_input_driven_configuration/outcomes/summary.md)、[`response_v1`](task038_input_driven_configuration/response_v1.md)、[`Review V1`](task038_input_driven_configuration/review_report_v1.md)。 |

# 49. Task039 当前结论

Task039 当前固定为 5 nm、1° grazing、phi=0、S、p6/h5、M480、MPI8；本项目级回顾只
索引已经完成的 fixed-case evidence，不改变历史章节编号或把 case 结果推广为通用 solver。

| 项目 | 当前结论 |
|---|---|
| Full3D direct baseline | 93.8976 GiB process-tree RSS |
| Hybrid direct baseline | 85.0236 GiB process-tree RSS |
| DQ1 exact-side explicit opt-in | 49.8236 GiB、4888 s、outer=1 |
| DQ1 局部工作量 | bottom/top action applies=1922/1922；local direct solves=2218/2226 |
| 数值/物理 | 五项 residual Gate 通过；Hybrid-direct integrated checker 通过 |
| Full3D strict channel | 已实测未通过；保留为 nonblocking diagnostic，不否决 Hybrid primary |
| 资格边界 | case-specific explicit opt-in；not general production |
| 全仓测试 | full pytest = `not_run` |
| 详细证据 | [`Task039 summary`](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/summary.md)、[`v3 final outcome`](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_final_iterative_result.md) |
| 响应与 case | [`response_v4`](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v4.md)、[`case README`](../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/README.md) |

## 49.1 Task039 V4-10 h4 与 QEP/memory 收口

Task039 的 V4 h4 证据共享 5 nm、1°、phi=0、S、p6/h4、MPI8 的物理、网格与
external-key identity；只有两条 Hybrid 方法使用并共享 M480 packet，Full3D 的 M/packet
均为 `N/A`。ordinary defaults 未改变，exact-side 仅为 fixed-case explicit opt-in。

| 项目 | 当前结论 |
|---|---|
| Full3D direct | 21600.036032 s 在 MUMPS factor setup timeout；208.315395 GiB；未完成 |
| Hybrid direct | own pass；93.377006531 GiB |
| Hybrid iterative | 1 outer、104.334560394 GiB；numerical/physics pass，resource fail |
| iterative 工作量 | reuse/cold 12357.484926 / 14016.567154 s；不能称高速 |
| Q-A/Q-B/Q-C/Q-D | owner-only 已成立；其余方向未建立完整低 M Gate |
| 项目决策 | 不宣称三方法完整比较、general production 或 0.7 nm PDE 可行 |
| full pytest | `not_run` |

详细结果见 [`Task039 summary`](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/summary.md)、
[`V4 response`](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v5.md)、
[`三方法比较`](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v4_three_method_comparison.md)
和 [`iterative compact`](../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_h4_hybrid_iterative_exact_side_v1.json)。

## 49.2 Task039 V5-2 h4 exact-side setup-only

V5-2 在固定 5 nm、1°、phi=0、S、p6/h4、M480、MPI8 下完成一次 setup-only 归因；不运行
outer solve、recovery、R/T/A 或 field/canonical。exit=0、`setup_only_completed`，15 个
Review marker 全部唯一、有序并与 process-tree RSS 对齐；最终 setup destroyed=true，
bottom/top factor count=`0/0`，packet consumer `qep_calls=0`、swap=0。

| 项目 | 结果 |
|---|---|
| RSS peak | `91672846336 B = 85.376991272 GiB`；位于 bottom Woodbury construction interval |
| 阈值 | warning/critical/hard 未触发；PSS/USS=`not_measured` |
| 资源分类 | baseline positive；相对 advancement line `84.039305878 GiB` 高 `1.337685394 GiB`，因此 advancement not met |
| 边界 | 这是 setup-only memory attribution，不是完整 Hybrid iterative numerical/physics qualification；V5-3 仍具备资格 |
| 证据 | [`V5-2 outcome`](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v5_h4_exact_side_memory_attribution.md)、[`compact record`](../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_h4_exact_side_memory_attribution_v1.json) |

首次错误 packet 路径 run 保留为 `invalid_preflight_invocation`，不计入重型尝试；generic
memory ledger 未覆盖 exact-side action/factor，专用 15-marker stream 与 diagnostic 才是本
次对象证据 authority。普通 defaults 未改变。

## Task039 Review V5 最终证据收口

V5 的两个压缩 family 已关闭：两个冻结 BLR profile 均超过 side setup resource limit；唯一 fixed-budget=32 bottom side Krylov 的 setup interval 资源样本为 `21.677326202393 GiB`，但 modal traction positive/negative true residual 为 `0.748109402736452` / `0.737754681505050`，远高于 `1e-2`，因此按 numerical Gate controlled-stop。该轮没有 top/outer/recovery/RTA/field，也没有生成 official result。

| 状态 | 结论 |
| --- | --- |
| h4 direct | `93.377006531 GiB` matched reference，own numerical/physics pass |
| V4 exact-side iterative | `104.334560394 GiB`，numerical/physics pass but resource regression |
| V5 exact-side setup/compaction/streaming | 既有 measured/derived research evidence；无 fresh h4 full-solve RSS |
| BLR family | resource fail；不得第三 profile或V5-8 BLR full formal |
| fixed-budget family | resource sample pass、mandatory numerical fail，`controlled_stop_numerical_gate_failure` |
| 0.7 nm / Full3D new heavy | not_run；capacity仅 derived/predicted conditional envelope |

当前不存在数值合格且节省内存的 h4 Hybrid iterative；ordinary defaults unchanged。入口：[V5 h4 final](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v5_h4_hybrid_iterative_final.md)、[0.7 nm capacity](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v5_0p7nm_hybrid_capacity.md)。

## 2026-08-19：Task039 Review V6 bottom port/modal 结项

V6-1 post-compaction exact-side setup-only 的唯一 run 在
42.70841979980469 GiB 处超过 42.019652939 GiB setup line，exact-side full formal
关闭为 oracle-only。随后 V6 主 family 的唯一 bottom port/modal component 使用固定
whole-endcap ILU(0)+DtN Woodbury base；在 full right/left packet ephemeral ready 后，
process-tree peak 达到 23,649,669,120 B = 22.025470733642578 GiB，超过 22 GiB
construction hard line 27,348,992 B，swap=0，SIGTERM 完成且无需 SIGKILL。

| 范围 | 状态 | 证据 |
| --- | --- | --- |
| first aac7e33e attempt | implementation failure；right-only left_full 接线错误 | 保留 raw，不作方法结果 |
| second 52f34262 attempt | authoritative resource controlled stop | [compact record](../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v6_port_modal_bottom_component_v1.json) |
| owner-row basis / rank64–512 / six probes | not_run | hard stop before owner-ready |
| top / both-side / outer / recovery / RTA / field | not_run | bottom resource Gate failed |
| layer graph / sweeping | not_available / not_authorized | bottom_F_ready 未取得 |
| 0.7 nm PDE / arbitrary-3D qualification | not_run | capacity remains conditional |

该结果关闭 V6 port/modal bottom family；不调参、不重跑、不继续 top。ordinary
defaults、既有 V5 负结果和两个 raw root 均保留。

## 2026-08-20：Task039 Review V7 Lane A exact-side full formal

V7 唯一一次 Lane A setup→full formal 使用 source
`9e31ecf189081afcb8ca27b0374ec89af0094e2d`，run root 为
`results/task039_v7_h4_exact_side_full_formal_mpi8_9e31ecf1`。完整 process-tree peak
`85,927,108,608 B = 80.025856018 GiB`，低于 matched direct
`93.377006531 GiB`，swap=0；相对 direct 节省
`13.351150513 GiB / 14.298113646%`，分类为
`5NM_EXACT_SIDE_LOWER_MEMORY_CASE_RESULT`、`V7_TIER_5_TO_20_PERCENT`。
V7 setup-only advancement 沿用先前 source
`f4073adabb91bffe5c3954b8ae8b63270efa3e15` 的 run
`results/task039_v7_h4_exact_side_limit_setup_only_mpi8_f4073ada`：
`81.056903839 GiB <= 84.039305878 GiB`；该 Gate 不属于本次 full formal 的正式资源比较。

| Gate | 结果 |
|---|---|
| outer-ready | `76.937850952 GiB`，reached |
| outer solve | fixed `GMRES/restart10`，1 iteration，true residual `3.506501655e-10` |
| recovery / physics / matched h4 direct checker | pass；Full3D secondary `not_available` |
| factor lifecycle | outer-ready `1/1`；final `0/0`；packet/QEP released |
| ordinary defaults / 0.7 nm PDE | unchanged / `not_run` |
| Lane B streamed owner-row Petrov | `not_run`；待独立实现与 focused Gate |

compact evidence：[V7 full-formal record](../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json)，
[V7 outcome](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v7_exact_side_limit.md)。

## 2026-08-21：Task039 Review V7 final closeout

V7 Lane A 是唯一完整 workflow 的低于 matched direct 正结果：h4 direct 为
`93.377006531 GiB`，inherited worker_total `7131.113596 s`；Lane A setup-only 为
`81.056903839 GiB`、observed `10649.634795 s`（独立 `84.039305878 GiB`
advancement authority），Lane A full formal 为 `80.025856018 GiB`、`10126.232 s`、
1 outer iteration，节省 `14.298113646%`，仅属 `5_TO_20_PERCENT`。它没有达到
20/30/40/50/60% full-workflow tier；旧 `42.019652939 GiB` half-memory line 也未达到。

Lane B streamed producer 的 `11.630760193 GiB/~415.6 s` 和 bottom consumer 的
`23.038208008 GiB/~632.8 s` 是 component evidence。producer packet/lifecycle/resource
通过，但 consumer rank64/128/256/512 的 `E=Y^H F Z` condition 均合格，五个 mandatory
source-family true residual 仍失败，因此 top/both/outer/recovery/RTA/field 未运行。

Lane C 已独立完成 local-F graph-only audit：bottom/top 均测得 6 层、132300 rows、
105038640 NNZ、same 75327840、adjacent 29710800、long-range 0、half-bandwidth 1；
wall/RSS/cleanup inventory 为 `not_measured`，不转化为容量或 solver 资格。它只允许后续考虑
z-sweeping、hierarchical Schur、cyclic reduction，未实现、未重型验证。

V5 BLR/fixed-budget、V6 setup/port-modal、V7 首次 ownership/telemetry failures 和 raw
artifacts 均保留。0.7 nm PDE、Full3D 新 heavy、第三 BLR、普通 ILU/budget scan、h5 rerun、
top/both/full Petrov 均 `not_run`；ordinary defaults unchanged，master untouched。
最终内存—残差—时间表见
[V7 memory summary](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v7_memory_limit_summary.md)。

## 2026-08-21：Task039 Review V8-3 bottom layer-sweep

V8-1 的六层 block operator 重构通过真实 F action/graph Gate；V8-3 使用同一 bottom component
顺序评估 `J1/F1/FB1/FB2/FB4`。construction 全区间 peak 为 `23916404736 B =
22.273887634 GiB <=45 GiB`，swap=0，六个 layer factors 从 6 清理到 0，full-side/global direct
factor=0/0；但五个候选的 mandatory residual 与稳定性 Gate 均在 FB4 前后未通过，精确分类为
`LAYER_SWEEP_NUMERICAL_LIMIT_NOT_REACHED_BY_FB4`。该 worker exit3 是数值 Gate 的受控退出，
不是父 watchdog 的资源终止；generic 224 GB ledger 字段不属于 V8 authority。

preferred retained rehydration 没有发生，因此 overall retained interval 是 `not_available/not_run`，
不能使用临时方法 interval 代替 30 GiB Gate。top、both-side、full、matrix-free K、0.7 nm PDE 和
新的 solver development 均停止/未运行。详见 [V8-3 outcome](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v8_layer_sweep_bottom.md) 和
[V8 Pareto](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v8_memory_residual_time_pareto.md)。

## 2026-08-21：Task039 Review V9-1 bare-F/full-side diagnostic

V9-1 在修复后的 source `2faf2a1a89a065e2985e46e462c6b7396f72b051` 上只重评 bottom `J1` 与 `F1`，没有重跑旧 V8 候选。
五个非退化 frozen holdout 的 J1 `r_F` 为 `24.9344 / 30.6816 / 50.7690 / 48.9026 / 50.6202`，`r_A` 为
`24.5337 / 29.9755 / 50.2411 / 47.4220 / 49.1084`；F1 `r_F` 为
`202.576 / 304.921 / 328.362 / 351.646 / 367.213`，`r_A` 为 `81.3295 / 119.177 / 141.076 / 127.163 / 129.898`。
`r_A/r_F` 分别约为 `0.970–0.990` 和 `0.354–0.430`，说明 single-layer sweep 对 bare `F` 本身已严重失效；
DtN/Woodbury 没有放大 J1，反而缓和 F1，但两者都未达到 `1e-2` residual Gate，J1 优于 F1。

J1 repeat/linearity 约 `1e-13`，F1 最大约 `3.63e-11`，均通过 `1e-10`；K rank `296`、condition `63.9432505898`。
construction peak 为 `23.8684272766 GiB <=45 GiB`，swap=0；六层 factor 从 `6` 清理到 `0`，full-side/global
direct factor `0/0`，retained candidate `not_run`。physical zero 只作 degenerate，FB1/2/4 未运行。
compact record 与原始 evidence 绑定见
[V9-1 record](../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_bare_f_full_side_diagnostic_v1.json)
和 `results/task039_v9_h4_bare_f_full_side_diagnostic_mpi8_2faf2a1a/`（ignored local raw）。

## 2026-08-21：Task039 Review V9-2 fixed two-layer supernode

V9-2 只在 bottom 侧运行固定三组 `[0,1]`、`[2,3]`、`[4,5]`，候选为 `SN2-J` 与
`SN2-SGS`。同一组三个 sparse factors 成功构造并严格串行清理；三组 rows 为
`49140/41580/41580`，完整覆盖 `132300` rows，最终 factor inventory `3→0`，
full-side/global/nested factor `0/0/0`，selected packet `false`，QEP `0`。

两个候选对五个非退化 frozen labels 均输出非有限值：SN2-J 为 `Inf`、SN2-SGS 为 `NaN`；
physical zero 仅为 degenerate。正式分类为
`V9_2_FIXED_TWO_LAYER_SUPERNODE_CONTROLLED_NUMERICAL_INSTABILITY`。worker exit3/parent
`worker_nonzero` 是数值失败后的受控退出，parent termination 为 null，不是资源 stop，也
没有证据证明通用 factor API 有 bug。

parent construction/overall process-tree peak 为 `24494911488 B = 22.812664031982422 GiB`
（`<=45 GiB`，swap0），总时长约 `473.941922 s`；retained `not_run/not_available`，
因为没有稳定 preferred action。V9-3 direct full-side FGMRES、V9-4 ranks16/32/64、top、
both、full 和 0.7 nm PDE 均 `not_run`。证据入口为
[V9-2 outcome](task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v9_supernode_side_preconditioner.md)、
[V9-2 compact record](../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_supernode_side_preconditioner_v1.json)
和 ignored raw root `results/task039_v9_h4_layer_supernode_bottom_mpi8_266a1acc/`。

## 2026-08-22：V11-1 bottom response-packet algebra closeout

V11-1 formal action-only audit 在源码 SHA `677ab26dcfef79f0f754b88f2cfb8832edac4285` 上运行一次并按固定 Gate 结束。960 列 metadata identity/order/provenance/layout、physical zero equation、independent zero-map 和 V7 active-trace round trip 通过；十个 sampled AX residual、960-column Schur/modal action 和 V7 bottom trace Gate 失败，分类为 formal algebra negative / controlled stop。没有 sign flip、packet rerun、factor/KSP/QEP、PDE 或完整 Hybrid solve。

component process-tree peak 为 `12.7808799744 GiB`，swap=0，wall 约 `655.209 s`；此前 `45.277 GiB` projection controlled stop 的 row-flush/streamed 修复使本次 projection 完成，但不能据此证明 packet algebra 或 solver correctness。V11-2 至 V11-7、top/full、consumer、0.7 nm 均 not_run。hash-bound compact record 和 response_v12 是本阶段证据入口；raw 仍 ignored。

## 2026-09-09：Task041 3 nm 最终证据收口
Task041 最终状态为 3NM_COMPLETED_NOT_GRID_CONVERGED，merge approval=NO。
3 nm p6/h3 的 M800 和 M1200 均完成 solve 与 recovery mechanics，但 own
physics 分别因 abs(A_balance-A_volume)=1.9160032445286745e-5 和
1.8704745773062692e-5 超过 1e-5 而为 candidate negative。M800 的
20260907 fresh attempt 仍是 diagnostic marker only、IMPLEMENTATION_FAILURE；
M1200 是后来授权的 controlled consumer continuation，不能写成完整
supervisor PASS，也不能追溯改变 M800 结论。

M1200 producer packet 已以 source c3a5bf4a424405c1f1de5cd6ac96be8db576f7b3
完成 1200/1200 delivered，manifest 与 identity hash 有效；producer raw
telemetry peak 为 28.318450928 GiB，compute wall 15386.145391 s。consumer
source c72b3e0d1540a5a891f5906fb0d75dc9146fefd2 的 solve/recovery mechanics
通过，candidate residual 全部低于 5e-9，但 official RTA/canonical/grid
authority withheld；outer terminal authority race 是 bookkeeping failure。

不同阶段 wall 不相加为 workflow authority，workflow peak 取不重叠
producer/consumer 的 max。M800/M1200 的 factors 是实测主导内存对象族；
M1200 consumer process-tree/cgroup peak 为 250.271244049/251.563114 GiB，
swap=0。M1600、h2.5/h2、全部 2 nm 及 post-gate MPI1 均
NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE（M1600 另明确为两次 own physics
Gate 后未释放），不是资源能力失败。关于 0.7 nm 的 factor-free/scalable
architecture 判断是工程推断，不是正式容量外推。

5 nm 继续区分 Task039 inherited、Task041 MPI8 reproduction 和 MPI1；
MPI1 equivalence 未建立。完整 raw evidence 仍在 ignored roots，compact
checkpoint v2 和 Task041 outcomes 为证据入口。

## 2026-09-14：Task041 BAL_H H2/H3 证据收口

Task041 的 BAL_H 是显式 research-only opt-in：它以每侧一个准确 p4 粗因子和迭代平衡响应，替代完整 p6 侧区精确因子的驻留；全局 Maxwell 方程、global action/RHS、P/PH 传递和 recovery 定义保持不变。H2（13.5 nm、M120）与 H3（5 nm、M480）的 exact/BAL_H 数值对照通过冻结合同；H3 BAL_H worker 的数值与物理 own gates 通过，但 public supervisor 早在 `2026-09-13T03:06:53.264Z` 附近丢失，结果落盘后的 orphan sampler 又发生 terminal gate false 与 TERM/KILL 退出竞态，因此完整 consumer/共同 producer 资源资格仍为 `RESOURCE_COMPARISON_INCONCLUSIVE`。

H3 candidate 为 `p6/h4/M480/MPI8`，worker wall `191662.819902868 s`（约 `53.239672 h`），Schur `183016.74211002886 s`；p6 factor=0、每侧 p4=1、每侧 nested KSP=1，清理后归零。旧 public 段观测 RSS/PSS/USS 峰为 `53221163008/50485623808/50090246144 B`（raw 总计 226484 行，其中 consumer 226483 行内 2287 行同时可读、224196 行缺测，另含 preflight 1 行），但仅覆盖该段；orphan 三类记录 `sample/read_only/gate_v2=822/6284/442921` 来自同一文件，不能拼成完整峰。完整 H3 exact public-tree RSS/PSS/USS 为 `89123696640/87368944640/87121264640 B`。详细数值、身份、hash 和失败边界见 [Task041 BAL_H 中心报告](task041_mpi1_shortwave_hybrid_capacity/outcomes/side_balh_transfer_v1.md) 与 [compact record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_side_balh_transfer_v1.json)。

本轮新增 BAL_H numerical/core 组件以及 Floquet empty-rank collective 修复；BAL_H 仍是 research-only opt-in，未提升为 production default 或 master 合入。Task39extra V5 donor source 为 `094204b7281fe867744fe334e8753d2faebaf89b`，只作为迁移来源记录。

## 2026-09-15：Task041 S1f fixed-eight baseline 资源受控停止

在 source `1c1d36b168bfb3939314ee2faf5b943cca804382`、5 nm p6/h4/M480/MPI8、
`task041_schur_speed_v2` profile 下，未优化 fixed-eight RHS baseline 进入
`top_factor_setup_begin`，尚未执行第一条代表性 RHS（`0/8`）。外层 authority memory
raw 为 7350 行、26,113,795 B、SHA=`5a46a99427c7d82e5c4eb9d8209b887e0a33c66f5ff865ae12df0c786e75c5b8`；
line 7313 首次达到 90% warning（elapsed `2210.5727085701656 s`，RSS
`47914586112 B`），line 7349 首次且唯一超过 strict process-tree RSS cap
`53221163008 B`（峰 `53331742720 B`，超 `110579712 B`，逐 PID 求和一致）。

job swap 为 0；global used `8192 B` 是既有 baseline，新增 used/pswpin/pswpout delta 均为
0；host/cgroup reserve 未触发。PSS/USS 为稀疏观测峰 `40538401792/40140140544 B`，74 条
smaps-complete、7276 条缺测，不能替代同一时刻 RSS。外层 phase 返回 `-15`、
`process_tree_rss_limit`；parent pre-exit 仍有 MPI 成员，后续 systemd cgroup 才清空，
finalizer 为 `service_boundary_failure`，所以不称自然 MPI 退出或数值失败。

本条状态为 `controlled_negative_resource_stop/process_tree_rss_limit`，只说明严格资源
入场失败，不提供新的 RHS、等价性或性能结果；shared S0/S1/S3 6 小时预算未触发，不能
与旧 H3 的 `RESOURCE_COMPARISON_INCONCLUSIVE` 混写。S2/S4、optimized/A-D、producer/QEP
和 Full3D secondary 均 `not_run`。紧凑索引与全部原始路径/hash 见 Task041 的[中心报告](task041_mpi1_shortwave_hybrid_capacity/outcomes/schur_speed_v2.md)与[compact JSON](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_schur_speed_v2.json)，以及
`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/s5a_completion_evidence.json`；
unit 六条原始 journal 另存于
`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/task041-s1e-rhs-baseline-1c1d36b1.journal.jsonl`
（SHA=`33b847ddf7206e33e876d290cb9130fcff55c90c07c55eb28aa55889694b2d96`）。BAL_H 仍为
research-only opt-in，未提升普通 production default；用户 04:59 已明确授权 CPU0–7
与 CPU23 保护作业并行，本轮不把该共存误记为违规。

## 2026-09-16：Task041 V3 执行结果与 Response V4 收口

R1 已实现 sequential component 生命周期入口，R2c 已实现并验证显式 profile 下的 A1
owner-row 批量路径与 A2 复数共轭临时量；R1/R2d/R2e 的轻量测试和两场 R2 分侧八项
运行也已完成。R2 baseline source 为 `3ee452ac0adc0c3c88b9610b6446e93a3c02444a`，
R2g 是唯一 optimized source `376a6c2e6ff1d13b8c4f182dd97e5ee2629f85ab`。两次各完成
bottom/top 四项，own reason=2、explicit residual `<=0.01`，R2e P/PH global relative
均为 `0 <= 1e-11`。

组件 apply 为 `1680.27495998214 → 1258.8479048048612 s`，full-service wall 为
`4015.539370124 → 3630.563676387 s`；全树 RSS 峰为
`51975606272 → 51796770816 B`。这些是两场分侧运行的实测，不是完整双侧资格。两次
fresh run 的 132300 condensed rows 缺跨运行稳定 physical key，正式状态为
`PAIRING_IDENTITY_UNPROVEN`；旧 S1f `process_tree_rss_limit` 负证据继续约束完整双侧准入。

证据入口：[Response V4](task041_mpi1_shortwave_hybrid_capacity/response_v4.md)、
[setup/recovery](task041_mpi1_shortwave_hybrid_capacity/outcomes/setup_recovery_v3.md)、
[compact JSON](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_setup_recovery_v3.json)、
[test summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/test_summary.md)。完整 raw、场、
矩阵、factor 和 shard 仍留在 ignored results；本次 R4 只做文档/compact 整理，不新增计算。
`task041_schur_speed_v2`、sequential component 和 A1/A2 仍为显式 opt-in research-only，
ordinary/default 不变，负结果文档可保留，不表示 production 或 master merge approval。

## 2026-09-28：Task041 V7 13.5 nm 终态与资源门

在源码 `c5f95db7f7c2c640b666035a1949f9dc666f4da4` 下，registered 13.5 nm / p6h10 / M120 / MPI8 cell-condensed consumer 自然 exit0，R/T/A、closure 与五项真实残差通过；复用既有 producer，QEP调用0。运行中 global swap 增286720 B、pswpout增70页，job/cgroup swap仍0；该global零增量资源门未通过，来源未知，不能归因于Task041。监督器仅以job/cgroup swap作停止条件，global增量只落遥测。

Bottom与top各自四项的selected-side target诊断通过共同输入与响应门，合计完成固定manifest八项分侧验证并通过原配对门；bottom原service exit3及其25项派生只读合同复核、top原service exit0分别保留。两场不证明单个完整5nm consumer双侧同时驻留时的资源或全场资格。正式5nm cell-condensed target入口修复已推送；完整consumer资格仍未建立。V7详情与hash-bound record见[response](task041_mpi1_shortwave_hybrid_capacity/response_v10.md)、[outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/causal_fix_5nm_v7.md)和[compact record](task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v7_causal_fix_5nm.json)。

## 2026-10-06：Task041 Review V9 H1 fixed-H6反馈门组件阶段

为减少旧路线在正式求解前逐模态列执行昂贵侧响应的工作，V9先在既有fixed-H6研究分支加入一次有界复数重复/线性门。该门检查固定反馈对复数、零和近零输入的定义及有限性；它不改变原全局方程、RHS、P4修正或正式五项真残差门。

| 项目 | 结果 | 边界 |
|---|---|---|
| production core | SHA `64ef9439ee2d527049877edfa88ce8e848e4370600f1a8b9ee41d4684709dea3`，默认off | 尚未接入public单`.dat`入口 |
| 测试 | serial坏输出节点1 passed；MPI2五selector两个rank各8 passed，无warning | 受控最后rank非有限输出共识/清理；不是FE或任意MPI异常安全 |
| 预算与作用 | setup检查8次`S_H`/C；每侧8次H6 apply、16次H6矩阵乘；每个内层GMRES原9次solver作用+1次末检保持 | setup成本须计入后续整场；tiny次数不作5 nm wall预测 |
| ledger | 两条pytest parent wall唯一计入10.003750981064513 s，V5 ledger 124项 | ABI/static/rank-local时间未计；compact与receipt在ignored results |
| 下一步（该组件阶段的当时计划） | public `.dat`入口、supervisor/service命令绑定和受保护dirty hunk梳理后，进行最小路由测试并准备真实W 5 nm运行 | 这是2026-10-06组件阶段快照；随后唯一W5运行已完成，当前H2–H4及0.7 nm/2 TB/48 h仍未完成，见本文件顶部与[W5 outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/hybrid_0p7nm_2tb_48h_v9.md) |

Task041 H0/H1详细记录见[outcomes summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)、[V9 outcome](task041_mpi1_shortwave_hybrid_capacity/outcomes/hybrid_0p7nm_2tb_48h_v9.md)、[测试汇总](task041_mpi1_shortwave_hybrid_capacity/outcomes/test_summary.md)和[Response V11](task041_mpi1_shortwave_hybrid_capacity/response_v11.md)。

## 2026-10-07：Review V9 W0.7 reduced-p6 pilot public-contract测试

当前独立pilot输入为`input/official/task041/side_balh/w0p7nm_p6h0p70_m400_mpi8_cell_condensed_pilot.dat`，材料候选record SHA `fe3bf4e5df2f369907f21033a4aa84e62fdf7b3a0961e05ec29743c9cafd70d2`。输入可枚举1292个external-mode候选；尚无producer packet，本阶段未运行QEP/FE。六个批准selector的12个唯一case最终在13个分批serial attempt中通过；局部测试fixture失败和重试均保留，最终test351 SHA `f92641ffd227f108fd42071103d3ea820d9983db6bfd456230c3dc8405cb33af`没有一次性整组通过。V5对各pytest parent wall各记一次，共`65.0168370383326 s`；ledger为144项、SHA `24a6f6917006275d5035aa220cfb83e5755be9afe0f8036cc9793cc4e3b8bca4`。逐attempt记录见[测试摘要](task041_mpi1_shortwave_hybrid_capacity/outcomes/test_summary.md)。当前仅serial public-contract/输入解析证据，不是MPI8 producer或数值结果；下一步等待新的ignored冷运行包静态审查和单独准入。

## 历史快照：2026-10-09 Review V11 P0资源合同与P1 W0.7启动前准备

本节保留dispatch前的合同、测试与准入快照；其中“等待审核、尚未dispatch”等文字只描述该时点，实际唯一warm场终态见本文件顶部。

**背景和基线。** 近期 W0.7 warm 场在 P4 数值分解前被资源预算门拒绝，没有到 fixed-H6 feedback、outer、五项真残差或完整物理输出。为避免继续复用旧 49.566 GiB 上限，Review V11 给注册的缩减 pilot 单独设 80 GiB case cap，同时保留 node0 384 GiB floor，并继续由父级 host/cgroup 可用量限制。该 cap 是允许的运行上限，不是内存峰值预测。

**改动与验证。** P0 只改 pilot DAT、输入校验、Task041 exact-side 合同和 test351。W5、13.5 nm 与 W2 的共享上限未改，也没有增加 CLI/runner。7 个批准 selector 的12个唯一参数 case分布在三次pytest parent attempt；首轮含一个fixture断言错误（期望键不存在），保留失败后只重跑该预算节点，其他参数化项另跑。三个父wall唯一合计`16.047360067022964 s`，V5 ledger 192项SHA `710b71f59d0109ace55963b2ac909eca5e4fccdcb8ef237259f9abff679ef774`。最终四路径普通提交为`a3332dc12de1ddfec824a8b64ab5dcc23f68261b`，parent `cd43819dc91112b8ca49d1dd2c2066d0074eda44`，原分支upstream同步；这些是合同测试，不能当作一次整组同SHA测试或pilot求解。

| P1 准备/准入 | 当前证据 | 含义和边界 |
|---|---|---|
| 运行包 | ignored package `results/task041_v11_w0p7_pilot80gib_pord_warm_preparation_20261009T074322Z/`；config `b4bf3edc0c7acfca3aa7b1d00c6b2f8a69c19f2caa220e44c05460ef83c22385`；argv `363dbb74f6e23f46665c900dd0e31b4d4fcab48048fe764e5e28b47e30f42236` | 26项内容hash通过；34 runtime + 5 test源码绑定与HEAD blob/工作树匹配；目标unit未加载，runroot/log/dispatch marker不存在 |
| 宿主门 | 真实host双样本 `07:54:18.523917Z` / `07:54:23.603283Z`；node0 MemFree `719,097,163,776 B` | 扣384 GiB floor后 `306,780,303,360 B`，扣80 GiB case cap后余 `220,880,957,440 B`；host/cgroup/disk通过。Task039/Task042进程被观察但未干预；宽affinity使 `performance_not_isolated=true` |
| 原生MPI8 ABI | rank map `[10,11,14,15,16,17,18,19]`，PETSc 3.19.6/MUMPS 5.6.2/OpenMPI 4.1.6 | rc0；complex128、Int32、membind0、六线程变量均为1；精确加载已审 .so SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b`。无factor或矩阵求解 |
| 数值包身份 | W0.7 p6/h0.70/M400/MPI8、接口2/22、matched L20/N29/h20/29、fixed-H6；复用 producer source `2708214386d38bd69f73e6b196c8ed843bb53d81`，本次QEP=0 | manifest SHA `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`；packet identity SHA `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`。只复核11份小封套，不读全shards、不声称完整validator已运行 |

**准备阶段结论（历史）。** PORD source-counted bottom/top Δ为`3,962,155,812/5,500,664,516 B`，仅是symbolic预算筛查量，不是RSS上界；numeric门仍按当场fresh B + 单份INFOG(17)×1,000,000 + W判定，不能预扣历史收益。本表原先记录准备和准入；实际dispatch后完成的阶段、残差失败与终态以本文件顶部为准。W5弱显著衍射通道按用户决定延期处理，保留原失败且不作0.7前置；W2本阶段不推进以免延误0.7。
## 2026-10-09：V11 fixed physical BAL_H 选择路径的准备门

在保留普通pure fixed-H6默认行为的前提下，提交了一个只有显式 `modal_feedback_method=fixed_physical_balh_once` 才可请求的W0.7研究反馈动作；实际方法身份单独标为 `fixed_physical_balh_once_modal_gmres_research`。它使用固定一次P4同因子修正，避免把按RHS残差动态决定修正次数的普通P4设置混入每次模态矩阵作用。本次尚未运行该FE方法。

代码/测试普通提交为 `fcae36494e65751ed918a8b591f4639d27b493c0`（parent `92914c5759281da51d7312040c30768ca0a00e07`，upstream 0/0），包含11条获审路径。其 serial/MPI2合同证据按10个原始attempt分别绑定；V5账本203条、SHA `a4514aa3499fe1df305317b65de91039214b178dd288c3f9e90ac903278c3fa8`。分批结果及fixture失败见[test summary](task041_mpi1_shortwave_hybrid_capacity/outcomes/test_summary.md)，不能合称最终SHA一次整组通过。

W0.7独立 warm package 已完成实际host双样本与MPI8 native ABI门，当前仍未dispatch。CPU map `[10,11,14,15,16,17,18,19]`；8 rank对应落核、membind0、complex128/Int32、六线程1；原生桥SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b`。node0 floor/cap与host/cgroup/disk、精确unit未加载/无活动Task041、root/log/dispatch marker缺席均已核验；宽affinity桌面活动保留 `performance_not_isolated`。

包入口为[Response V13](task041_mpi1_shortwave_hybrid_capacity/response_v13.md)及[delivery V11](task041_mpi1_shortwave_hybrid_capacity/outcomes/shortwave_delivery_v11.md)；机器执行契约为 `results/task041_v11_w0p7_fixed_physical_balh_once_warm_preparation_20261009T142126Z/execution_contract.json`，post-ABI identity receipt为同目录`post_abi_identity_final.json`。producer packet仍复用原manifest/identity，当前QEP=0；正式链的validator/hydration尚未执行。

仍保持PORD、matched L20/N29、P4 target `5e-13/max2`、fixed-Q单修正与 `1e-10` 门、8次SH/9+1、outer五门和完整恢复物理合同。资源cap/warning/W=`85,899,345,920/77,309,411,328/8,589,934,592 B`，node0 floor `412,316,860,416 B`，swap observe-only，不设elapsed强停。以上不是容量或FE资格。本候选等待主控对这一精确sealed argv作最后一次dispatch决定。W5通道问题按用户决定延期处理；W2不得延误0.7主线。
