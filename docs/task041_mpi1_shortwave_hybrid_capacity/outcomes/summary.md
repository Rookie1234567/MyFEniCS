# Task041 outcomes summary

## 2026-10-09：Review V11 W0.7 P1 唯一 warm 场终态

本轮真实计算使用已验证 producer packet，当前 QEP=0。缩减模型为 W 材料10×5 nm、p6/h0.70、M400/MPI8、接口2/22 nm、matched L20/N29/h20/29。one-cell、两侧P4 numeric及fixed-H6 setup repeat/linearity gate完成；outer记录到iteration 1，但fixed-H6 modal内层第二次solve未通过残差门，未生成完整场或物理结果。

| 阶段/对象 | 实测结果 | 资格边界 |
|---|---|---|
| 身份 | Invocation `797ae38854d546898a895c81d803a5ec`；source `47fc621a478adf26ebe9ca41d54563e188bab1d1`；producer source `2708214386d38bd69f73e6b196c8ed843bb53d81`；unit `task041-v11-w0p7-pilot80gib-pord-warm-cpu10-11-14-15-16-17-18-19-20261009T074322Z.service` | 一次warm consumer；producer复用，QEP=0 |
| fixed-H6 modal solve | solve_count=2、not_converged_count=1；失败solve KSP reason `-3`，8迭代，`rtol=0.001`，显式相对残差 `0.005653709235402098`、原始残差门失败；S_H solver/total MatMult=8/9、上限9/10，`budget_exhausted=false` | 不得称9+1预算耗尽或近似通过；失败RHS与iterate未持久化 |
| outer关系与清理 | iteration 1 marker记第一次modal solve及`ITERATING`；失败发生于后续outer right-FGMRES PC中的第二次modal solve。`top_construction_cleanup`是cleanup覆盖的末态stage标签，不是失败源；bottom/top release与cleanup markers均在失败后，destroy error=0 | 第二次solve对应的精确outer KSP iteration号未持久化 |
| 资源 | cap/warning/W=`85,899,345,920/77,309,411,328/8,589,934,592 B`；node0 MemFree reserve/floor=`412,316,860,416 B`，host MemAvailable独立检查。service summary tree峰`47,073,288,192 B`、consumer resource summary tree峰`47,027,847,168 B`、dedicated cgroup峰`44,504,326,144 B` | 独立采样口径不相加；均低于case cap，本场非资源拒绝、OOM或受控停止 |
| 服务终态与账目 | consumer `IMPLEMENTATION_FAILURE`；public `task041_public_command_nonzero` rc3；finalizer `failed/service_boundary_failure` 8/10，false为`public_result_completed`与`service_terminal_normal`；`controlled_stop.active=false`；唯一finalizer wall `9,685.695409207 s` | V5 193项、SHA `803c4cb9c05b0c25426af3d75f6e20d9940bf08c351ed22a911f584e62e0b6ae`；runroot一条匹配记录，ledger行不直接保存Invocation |
| 未到达 | 最终五残差、recovery、完整E/H/RTA、A_volume、衍射及physics均未运行 | 本场不构成W0.7完整数值pass，不资格化50×25 nm、2 TB或48 h |

outer phase的`balh_side_rhs_audits.jsonl`有5个`SideBalancedInverse` side probe以128/128步`INNER_APPROXIMATE_RETURN`返回；六条均为writer-local记录，bottom/top各index 0、1、2，不映射到精确outer iteration。这些与失败的fixed-H6 8步modal solve不同。完整时序、残差与raw SHA见[Response V13](../response_v13.md)及repo-root ignored证据`results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z/terminal_compact_v11.json`。W5弱显著衍射通道按用户决定延期处理，原失败/比较工件保留、不写PASS、不作为0.7前置；W2本阶段未推进以免延误主线。

## 历史快照：2026-10-09 Review V11 P0 完成 / W0.7 P1 准备待审

以下内容记录dispatch前的P0合同与P1准备快照；“尚未dispatch/等待审核”只描述该时点，现由本summary顶部的终态更新。P0为注册缩减W0.7 pilot单独设定资源限制，避免改动其他模型共享上限；P1把producer packet、consumer源码、CPU map、PETSc扩展和启动命令绑定在ignored包里。

| 范围 | 实际记录 | 当前结论与边界 |
|---|---|---|
| P0 四文件 | commit `a3332dc12de1ddfec824a8b64ab5dcc23f68261b`，parent `cd43819dc91112b8ca49d1dd2c2066d0074eda44`；仅 DAT、input_validation、exact-side workflow、test351 | 独立 cap `85,899,345,920 B`、warning `77,309,411,328 B`、W `8,589,934,592 B`；node0 floor `412,316,860,416 B` 未变。W5/13.5/W2 共享合同未变 |
| P0 serial 合同 | 12 个唯一参数 case 在三个 pytest attempt 里通过；首次 test-only fixture 失败保留，受影响 selector 单独 retry，余项另跑 | 唯一 parent wall 合计 `16.047360067022964 s`；V5 ledger 192 项 SHA `710b71f59d0109ace55963b2ac909eca5e4fccdcb8ef237259f9abff679ef774`；没有最终 SHA 全组单轮通过 |
| P1 package | ignored 根 `results/task041_v11_w0p7_pilot80gib_pord_warm_preparation_20261009T074322Z/`；runroot `results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z/` | 26项内容 checksum 与39行源码/测试 blob 绑定通过；目标 unit 未加载、runroot/log/dispatch marker 不存在 |
| Fresh host | post-ABI 样本 `2026-10-09T07:54:18.523917Z` 与 `07:54:23.603283Z` | node0 MemFree `719,097,163,776 B`，扣384 GiB floor后 `306,780,303,360 B`，再扣80 GiB cap后 `220,880,957,440 B`；host/cgroup/disk门通过。Task039/Task042未被干预，performance_not_isolated 保留 |
| Native MPI8 ABI | CPU map `[10,11,14,15,16,17,18,19]`；PETSc 3.19.6、MUMPS 5.6.2、OpenMPI 4.1.6；complex128/Int32，membind0，六线程变量均为1 | rc0、parent wall `1.8218492951709777 s`；只证明 ABI 与 rank 放置，不证明矩阵、factor、FE 或数值结果 |
| 仍未运行 | QEP重算、packet完整validator/shard hydration、factorization、FE、fixed-H6反馈、outer、恢复/物理/最终化、dispatch | 包等待主控审阅；W5弱显著通道按用户决定延期处理，W2不延误当前主线 |

注册 case 是 W 材料 10×5 nm、p6/h0.70、M400/MPI8、接口2/22 nm与 matched L20/N29/h20/29，fixed-H6/P4 target `5e-13`、最多两次同因子修正。producer 复用 source `2708214386d38bd69f73e6b196c8ed843bb53d81`，manifest SHA `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`，packet identity SHA `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`；准备时只核11个小封套文件，未读 shards。当前 MPI8 bridge SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b`。完整 attempt/raw/hash 见[Response V13](../response_v13.md)、[V11交付进度](shortwave_delivery_v11.md)和 package 的 `post_abi_current_admission.json`。

P1的 PORD source-counted Δ bottom/top 为 `3,962,155,812/5,500,664,516 B`，只是symbolic筛查值，不是RSS上界；真实numeric仍需各自fresh B + 当场单份INFOG(17)×1e6 + W。该准备快照之后已发生上方唯一warm场；不要把准备包字段当作终态。

## 2026-10-09：W0.7 PORD warm场终态（top numeric前预算拒绝）

| 模型/阶段 | 实测或派生结果 | 状态、原因与证据 |
|---|---|---|
| 身份 | Invocation `12180bdec9824ec49d60b26aefe3655b`；source `6ffa7768329b637d96a9dccc2eb5aa00d510bb28`；M400/MPI8/p6/h0.70、接口2/22 nm、matched L20/N29/h20/29；producer复用、QEP=0 | unit `task041-v10r2-w0p7-pord-numeric-cleanup-warm-cpu10-11-14-15-16-17-18-19-20261009T043645Z.service` |
| one-cell | source 15,120²、NNZ 7,123,680、PORD | numeric完成并销毁 |
| bottom P4 | 64,966²/NNZ 27,929,686；INFOG16/17=2,685/11,842 MB；numeric INFOG18/19=2,685/11,842 MB | PORD numeric完成 |
| top P4 | 64,966²/NNZ 39,242,250；INFOG7/32=4/1；INFOG16/17=2,211/9,647 MB | symbolic完成；numeric未调用 |
| top预算门 | fresh B 38,544,203,776 B + 单份INFOG17 9,647,000,000 B + W 5,322,116,301 B =53,513,320,077 B | cap 53,221,163,008 B；超292,157,069 B，属于numeric前预测筛查拒绝，不是RSS实测超限 |
| 服务终态 | consumer `IMPLEMENTATION_FAILURE`；public rc3 `task041_public_command_nonzero`；finalizer `failed/service_boundary_failure`；`controlled_stop.active=false` | finalizer 8/10，仅`public_result_completed`、`service_terminal_normal`为false；无outer/物理门/官方RTA |
| 资源与wall | tree RSS峰40,494,215,168 B；专属job cgroup峰37,709,873,152 B；service wall3,241.567376339 s | 两个峰值scope分列；唯一V5计费，父wall不另计 |
| 账本 | V5共189项，SHA `ffa1a15cc639cf30c064057e9a9749032337882fbaade8b5f0445312ecc424cf` | runroot唯一匹配；ledger row无Invocation字段，由launch/finalizer/runroot关联 |

bottom numeric后的INFOG18=2,685是最大rank allocated memory，INFOG19=11,842是rank-sum allocated memory，单位为百万字节。它们不是RSS；INFOG全局结果在rank间复制返回，只记录一次、不再次求和。

本PORD场与前一AMD warm场是不同Invocation，不能作为同矩阵排序隔离实验；只分别记录INFOG估计，不推断RSS收益。完整Bi生命周期及条件尺寸说明见[Response V12](../response_v12.md)和[终态compact](../../../results/task041_w0p7_pord_numeric_cleanup_warm_run_20261009T043645Z/terminal_compact_20261009.json)：Bi全rank逐term payload未持久化，803,727,360 B仅是一侧720个cell均为108×646 complex128满矩阵的条件尺寸，非观测量或RSS节省。当前未形成W0.7数值资格，也不外推到50×25 nm、2 TB或48 h。

## 2026-10-09：W0.7 identity-sharing warm场终态（top numeric前预算拒绝）

同一identity矩阵由多个几何类复用只读数组，减少数组重复；它不改变方程。该payload节省与RSS分别记录。本场继续使用既有W0.7缩减pilot与MUMPS分阶段门，没有启动第二次计算。

| 模型/阶段 | 实测或派生结果 | 状态、原因与证据 |
|---|---|---|
| 身份 | Invocation `a598ab0a491649eda4060eef6a102b56`；HEAD `6e072bd640b5c140ba64745c350ddf9916a566dc`；M400/MPI8/p6/h0.70，接口2/22 nm，matched L20/N29/h20/29；producer复用，QEP=0 | unit `task041-v10r2-w0p7-identity-sharing-numeric-cleanup-warm-cpu10-11-14-15-16-17-18-19-20261008T233316Z.service` |
| bottom P4 numeric | 64966²、NNZ27,929,686；fresh B cleanup后28,704,886,784 B + INFOG17 18,865,000,000 B + W 5,322,116,301 B =52,891,003,085 B | 比cap 53,221,163,008 B低330,159,923 B；bottom numeric完成，INFOG18/19=2,879/18,865 million decimal bytes |
| top P4 numeric门 | 64966²、NNZ39,242,250；fresh B cleanup后45,211,955,200 B + INFOG17 19,299,000,000 B + W 5,322,116,301 B =69,833,071,501 B | 比cap高16,611,908,493 B，门拒绝；top numeric未调用，INFOG18/19 not_run；bottom numeric之后的top所需fresh B上限28,600,046,707 B |
| 资源范围 | process-tree authority峰47,043,870,720 B；dedicated job-cgroup峰44,224,434,176 B；cap/warning/W/floor为53,221,163,008/47,899,046,707/5,322,116,301/412,316,860,416 B | 峰值口径分列；swap observe-only；W只是政策预留 |
| 服务终态 | consumer IMPLEMENTATION_FAILURE；public rc3 `task041_public_command_nonzero`；finalizer `failed/service_boundary_failure`；controlled_stop.active=false；finalizer 8/10 | false为`public_result_completed`、`service_terminal_normal`；这是top数值前预算拒绝，不是controlled_stop |
| 唯一计费 | service wall1,860.62936514 s；V5共186项、SHA `d344166517fbbaa6f66c29a9687828f5e74c78b6dcba303c142c47e7f99477dd` | runroot一条匹配；通过launch/finalizer绑定Invocation，不称账目行包含Invocation |
| 数值结果/资格 | bottom factor完成；top numeric=0；无fixed-H6反馈、outer五真残差、recovery、physics及official R/T/A | W0.7 reduced场无数值pass；不资格化50×25 nm、2 TB或48 h |

**payload转录更正。** 前一执行消息把P4 identity字段误称为P6；现保留原通知/raw，只更正派生说明。P6原始build audit记录两侧nᵢ=450，rank-sum class数475/423，identity数组payload节省756,540,000/672,300,000 B，合计1,428,840,000 B；P6 retained local Schur payload为1,418,342,400/1,263,071,232 B。P4单独nᵢ=108，identity payload节省43,576,704/38,724,480 B，合计82,301,184 B。均为数组payload，不是RSS差值。

**驻留与下一步。** P6按真实class数和源码矩阵形状推得LU、两类恢复映射及Schur可见数组payload合计11,177,212,032 B。它比筛查缺口的字节数少5,434,696,461 B，但payload不是RSS减量或可回收量上界；这些对象仍服务于P6作用及P4右端处理/求解/恢复，不能据此判断总体释放能否跨门。P4 `port_audit.cells_with_port_terms`的bottom 0/top 15是`resource_scope=rank_local`本rank owned-cell循环计数，不是全局side cell数。逐rankBi/Di/xiB字节、全rankport项计数、ghost/cache alias总量均未持久化。历史算式`720×108×646×16=803,727,360 B`仅是一侧720个owned cells假设下的条件式尺寸示例，不是两侧或全局上界。top fresh B采样时bottom numeric因子仍存活，其驻留贡献已计入B，因此不另加bottom INFOG(19)；INFOG(19)是MUMPS allocated-data统计，不与RSS一一对应。top symbolic驻留与INFOG(17)无可审拆分，不能相减。当前尚无足量可释放证据，也没有证明全局潜在释放一定不足；不建议原样重建试跑。最窄候选是后续审查xiB预热后释放Bi-only buffers，但其全局收益未知。详见[Response V12驻留审计](../response_v12.md)。

证据：service summary SHA `1b8d4a573de76cf9f19bf23dcaa908a126971973f29b3e6bca3b85f990ac60c2`；finalizer SHA `92e4aa4fbb7b19587b7544ff273f5dd66c3f58c77a910588a6b75837929ca847`；consumer markers SHA `e5f4644f9ad70fbbd2f785f317b3e3773fd6aacb11dc57348d910e449ede1bd4`；factor inventory SHA `3284fe583c56e51effe76191d3f424a9d3528711ac5c1135693480c0d1112084`；[ignored terminal compact](../../../results/task041_w0p7_identity_sharing_warm_run_20261008T233316Z/terminal_compact_20261009.json)，SHA `bead944a1d4bd4f5f35097c8bf8cb43ee9478c0721f663e722634896a17235b3`。无新测试、ABI、QEP、FE或dispatch；raw、ledger与stash未修改。

## 历史快照：2026-10-08 W0.7 compact-transfer warm场终态——numeric前预算拒绝

compact方向缓存把每个单元重复的整幅方向矩阵换成共享canonical插值矩阵和方向实体块，减少数组重复存储；它不保证同等数量的RSS下降。本场在bottom numeric前由预算门拒绝，数值求解、物理验收尚未开始。

| 模型/阶段 | 当前实测 | 资格边界与证据 |
|---|---|---|
| W0.7 reduced p6/h0.70/M400/MPI8、matched L20/N29/h20/29 warm consumer | Invocation a6a67fc93a1d45cfa69cce0469cb0672；source 47b8b655ee9a9cc72dc1f89928b770f7061b22ea；复用packet，QEP=0；one-cell 15120²/NNZ 7,123,680/PORD并完成numeric后销毁 | unit task041-v10r2-w0p7-compact-transfer-numeric-cleanup-warm-cpu10-11-14-15-16-17-18-19-20261008T142600Z.service；唯一warm场 |
| bottom/top P4 | 64966²；NNZ 27,929,686/39,242,250；sequential AMD symbolic完成；INFOG(17)=18,004/15,601 million decimal bytes | 两侧numeric均未调用，pending各destroy一次、error=0 |
| compact transfer对象 | bottom/top K=766；每侧rank-sum payload 150,893,696 B | canonical R、方向块和索引的对象payload，不是RSS/已测节省 |
| bottom numeric门 | cleanup前/后authority fresh B=31,398,424,576/30,729,564,160 B（对应dedicated cgroup current 28,504,768,512/27,921,858,560 B）；单份INFOG(17)=18,004,000,000 B；W=5,322,116,301 B；预算合计54,055,680,461 B | 比cap 53,221,163,008 B高834,517,453 B，numeric前拒绝；cleanup实测降低668,860,416 B，非未来收益保证 |
| top numeric后续门 | 按top INFOG(17)=15,601,000,000 B与W计算，fresh B需≤32,298,046,707 B | bottom numeric未执行，故后续top fresh B与INFOG(19)未知 |
| 服务终态/账目 | consumer IMPLEMENTATION_FAILURE；public task041_public_command_nonzero/rc3；finalizer failed/service_boundary_failure；wall 1,979.603254005 s；ledger 183项，本runroot一条，SHA cd4c69f03e89b67350478b6c37655bc03ca77893ef5f6d96959fae32dcaaaa6e | controlled_stop.active=false；finalizer 8/10，只有public_result_completed、service_terminal_normal为false；其他清理/账目检查通过 |
| 正式结果与目标资格 | fixed-H6反馈、outer、五真残差、recovery、physics均未到达 | 无缩减pilot数值pass；不资格化50×25 nm、2 TB或48 h。finalizer SHA 7c00774e836ce40b322ee3472e6c913706781135cc1552c0ac8bdd40869a55f4；consumer markers SHA ce821d82fb0eb79e11315d427f856efd78c71e9ae865862a7e037217e0fbeb16 |

唯一账目按runroot与launch/finalizer绑定Invocation；ledger entry本身没有Invocation字段。bottom/top pending因子清理及对象所有权审计见[Response V12](../response_v12.md)。其中P6 retained local Schur实际bytes未持久化；P4 top有13个带端口cell但逐rank Bi/Di/xiB shape缺失；ModalTraceProjection的trace payload为基于已存layout推导值，不能当RSS。可审的W0.7专属projection trace释放候选最多覆盖约185.7 MB已知payload，小于0.835 GB本次门缺口；当前证据不支持据此安排重跑。

## 历史快照：前一场 W0.7 compact-transfer warm Invocation c38a11ae711846599601ac3c06286327

| 范围 | 实测结果 | 状态/资格边界 |
|---|---|---|
| Invocation与身份 | 唯一Invocation c38a11ae711846599601ac3c06286327；unit task041-v10r2-w0p7-compact-transfer-warm-cpu10-11-14-15-16-17-18-19-20261008T125520Z.service；source e890c1c12feb90dd4f7695d31402d63ff788d186；复用既有producer，QEP=0 | warm consumer单场，没有第二次dispatch |
| one-cell | source matrix 15120×15120，NNZ跨rank一次求和7,123,680；INFOG(7/32)=4/1、PORD | numeric完成并销毁；ready marker rows=17,280是端口/输出口径 |
| bottom/top P4 symbolic | 均为64,966×64,966；NNZ 27,929,686/39,242,250；sequential AMD；INFOG(17)=20,150/15,697 million bytes | 两侧symbolic完成，numeric attempts均0；pending handles各destroy一次、error=0 |
| compact transfer对象 | bottom/top K_local跨rank合计733/766；rank-sum payload 133,147,520/150,893,696 B | 是数组对象统计，不是RSS或已测RSS节省；canonical R、方向实体块和索引分列见Response V12 |
| bottom numeric门 | fresh B 30,895,177,728 B + 单份INFOG(17) 20,150,000,000 B + W 5,322,116,301 B = 56,367,294,029 B | 高于cap 53,221,163,008 B 3,146,131,021 B；before-numeric预算拒绝，不是实测峰或算法数值失败证明 |
| 服务终态与计费 | consumer IMPLEMENTATION_FAILURE；public task041_public_command_nonzero/rc3；finalizer failed/service_boundary_failure；service wall 1,956.390568298 s；V5 ledger 181项、本Invocation一条 | controlled_stop.active=false；finalizer 8/10，仅public_result_completed与service_terminal_normal为false，其余清理/计账检查通过。tree RSS峰35,009,921,024 B与dedicated cgroup peak 32,935,227,392 B分列 |
| 尚未到达 | fixed-H6反馈、outer、五真残差、recovery、physics、official observables | 本缩减pilot未完成求解，不资格化50×25 nm、2 TB容量或48 h目标 |

与上一场同阶段的描述性差值：fresh B减少5,020,377,088 B；bottom INFOG(17)增加690,000,000 B；预算缺口从7,476,508,109缩小到3,146,131,021 B（缩小4,330,377,088 B）。这些跨Invocation数字不能把B变化全归因于compact orientation。按当前top INFOG(17)与W计算的后续top numeric fresh-B限额为32,202,046,707 B；本场未测。consumer marker SHA bb2a466b84bd98216e2120938d9679c90cf2e81ef71f09b97d80db937a6703aa，finalizer SHA 8c987379232be4ebd2dea1f159118cd99fc4efcd8fe11f2995541c20a9e7e981。详见[Response V12](../response_v12.md)、[本轮实测进度](shortwave_measured_progress_v10.md)及[原始runroot](../../../results/task041_w0p7_compact_transfer_warm_run_20261008T125520Z/)。

## 历史快照：前一场 W0.7 reduced pilot（Invocation 3d6b63c763414ad984beb60f1296458e）

| 范围 | 实测结果 | 状态/边界 |
|---|---|---|
| 唯一warm Invocation | `3d6b63c763414ad984beb60f1296458e`；unit `task041-v10r2-w0p7-deferred-amd-warm-20261008T082944Z.service`；runtime source `819ed980502783f4a11b8ea2c690dc8add44e81a`；MPI8，CPU `[10,11,12,14,15,16,17,18]`；QEP=0，复用既有packet | 唯一本次warm运行；没有第二dispatch |
| one-cell factor | source matrix `15120×15120`；rank-local NNZ之和`7,123,680`；`INFOG(7/32)=4/1`，公开控制回读null | PORD numeric完成并销毁；`rows=17,280`是端口/输出行口径，`interior_rows=15,120`与factor source矩阵相符 |
| bottom/top P4 | bottom/top均`64966×64966`；NNZ `27,929,686/39,242,250`；各自sequential AMD；`INFOG(16/17)=2766/19460`、`4193/19299` million bytes | 两侧symbolic完成；numeric均未调用；两个pending factor各destroy一次且无destroy错误 |
| bottom numeric预算门 | fresh `B=35,915,554,816 B`；单份`INFOG(17)=19,460,000,000 B`；`W=5,322,116,301 B`；筛查合计`60,697,671,117 B`，cap `53,221,163,008 B`，筛查差`7,476,508,109 B` | before-numeric拒绝；不是实测所需峰，也不是算法数值失败证明 |
| 服务结果与资源 | consumer `IMPLEMENTATION_FAILURE`；public `task041_public_command_nonzero` rc=3；finalizer `failed/service_boundary_failure`；wall `2395.81151869 s`；tree RSS峰`35,915,563,008 B`、dedicated cgroup峰`33,178,259,456 B`；V5 ledger 175项且本Invocation一条 | `controlled_stop.active=false`；finalizer 8/10，只有`public_result_completed`和`service_terminal_normal`为false；清理和计账通过。性能`performance_not_isolated` |
| 尚未运行/资格 | fixed-H6反馈、outer、五真残差、recovery、physics、official observables均未到达 | 本缩减pilot未完成数值求解；不资格化50×25 nm、2 TB或48 h目标 |

终态compact：[terminal record](../../../results/task041_v10r2_w0p7_deferred_amd_warm_run_20261008T082944Z/terminal_compact.json)。V5 ledger SHA `962d31d906d22ec39d6a0e534021caa5fbcc8d1f521a966f245129d6768985ba`。所有阶段数值、classification与raw SHA均按本Invocation单独记录；此前`10d761079d90473dadce79d3f7eb6457`的受控停止继续作为独立历史结果。

## 历史快照：2026-10-08 deferred-AMD组件收口与warm run待执行

以下是本次dispatch前的组件/准备阶段记录；其中“仍active/待执行”等状态只描述当时时点，不能覆盖上方终态。

代码已普通提交并推送：HEAD `6caf43ebd52b14bf0c9423b33353e7fc8f38f27f`，parent `24b6431370f20510f795df75c38fa5d5a66f4296`。PETSc/MUMPS阶段桥把结构分析与数值分解分开，让预算可在大factor分配前检查；bottom/top仍须持有矩阵、端口及pending factor，因此tiny接口证据不能代替fresh容量门。

| 项目 | 本轮结果 | 状态/限制 |
|---|---|---|
| PETSc/MUMPS路线 | W0.7 deferred P4明确使用MPI>1/MPIAIJ、PETSc 3.19.6/MUMPS 5.6.2；requested/cached、source-derived、post-symbolic measured分开；symbolic后核AMD控制及INFOG7/32 | 普通KSP/default与one-cell原设置未变；未知comm/type/版本/option不满足条件时拒绝 |
| Stage预算 | symbolic `fresh B + Δ + W <= cap`；numeric `fresh_numeric_B + one INFOG(17)*1e6 + W <= cap`；`W=5,322,116,301 B`只加一次 | bottom/top source-counted Δ分别`1,382,983,004/1,925,986,076 B`，属于预测模型，不是RSS硬上界；numeric仍需同次真实INFOG(17)与新鲜B |
| 测试 | serial 2 passed/父wall`3.040390633046627 s`；MPI2每rank 3 passed/父wall`2.0312472369987518 s` | 8×8生命周期/控制合同；不是大factor、FE或W0.7数值资格 |
| V5计费 | 两个成功attempt唯一合计`5.071637870045379 s`；ledger 174项，SHA `531d777d369c8d84e58120ec79eabb638dd7fb8e4c03b2fdac3a33f5290515d2` | compile、ABI与static不计；早期脚手架在pytest启动前失败，没有wall、不入账 |
| 既有pilot负结果 | 唯一warm consumer在top P4因子构造阶段`controlled_stop/absolute_memory_limit`；tree峰`53,541,888,000 B`对cap`53,221,163,008 B` | 保留原raw与`2,350.819163285 s`唯一账目；不是本轮tiny测试改写或数值门失败 |
| 当前warm run | Invocation `3d6b63c763414ad984beb60f1296458e`；unit `task041-v10r2-w0p7-deferred-amd-warm-20261008T082944Z.service`；source HEAD `819ed980502783f4a11b8ea2c690dc8add44e81a`；rank map `[10,11,12,14,15,16,17,18]`；QEP调用0 | 单次service仍active、NRestarts=0；复用已验证旧producer packet；源码与运行配置冻结 |
| 已完成阶段 | one-cell factor在`679.020 s` ready；source matrix `15,120×15,120`，八rank `local_nnz_used`一次求和7,123,680；端口`rows=17,280`、interior rows=15,120 | symbolic后MUMPS `INFOG(17)=2630` million bytes（全rank总量只取一份）；`INFOG(7)=4/INFOG(32)=1`为sequential PORD，公开控制回读为空，one-cell未切AMD；两道预算门通过，估值不是RSS上界 |
| one-cell结束 | one-cell factor于`916.423 s` destroy（symbolic/numeric完成、destroy error=0）；800列lift、正反400列apply和两侧projection已完成 | source factor `15,120×15,120`、8-rank local nnz一次求和`7,123,680`；端口rows=17,280。销毁后RSS未立即同量级下降 |
| bottom P4 symbolic | pre-symbolic fresh `B=24,812,064,768 B`，`Δ=1,382,983,004 B`，加`W`筛查为`31,517,164,073 B < cap`；矩阵`64,966×64,966`、NNZ一次rank求和`27,929,686` | symbolic于`1924.843 s`完成、numeric尚未启动；`INFOG(16/17)=2766/19460` million bytes，INFOG(17)全rank和只取一份；实际INFOG(7/32)=0/1、ICNTL7/28/14=0/1/40，确认sequential AMD路径。此分析值不等同RSS上界或numeric准入 |
| 当前资源 | elapsed`1956.092 s`时tree authority `25,925,132,288 B`、专属cgroup current `23,455,088,640 B` | bottom pending factor仍计入live B；该样本不预测top/numeric峰。top P4、固定反馈门、outer、五残差、recovery/physics/finalizer仍未到达 |
| 资源政策 | cap/warning/floor保持`53,221,163,008/47,899,046,707/412,316,860,416 B`；`W=5,322,116,301 B`仅作为政策余量 | swap observe-only、无elapsed强停、`performance_not_isolated`；W2不执行 |
| 既有负结果 | 先前唯一warm场因top P4构造超cap受控停止；tree峰`53,541,888,000 B` | 保留原controlled-stop和`2,350.819163285 s`唯一账目；当前one-cell门通过不改写该结果 |

本机扩展SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b`，由词法`/usr/bin/mpicc`构建。serial/MPI2 raw与V5 receipt在`results/task041_petsc_lu_stage_bridge_jobnull_tests_retry_20261008T081956Z/`；准备包位于`results/task041_w0p7_deferred_amd_warm_preparation_20261008T082944Z/`。包在代码提交前生成，后续必须封存旧字节并重绑；其当前`started=false`不表示准入通过。Ruff相对HEAD无新增告警；相关文件存在23条原有baseline告警。

当前研究模型限定为W0.7 reduced 10×5 nm、Hybrid接口2/22 nm、p6/h0.70/M400/MPI8、matched L20/N29/h20/29、fixed-H6与P4目标5e-13/max2。复用已完成packet，当前Invocation QEP=0；route-plan/leading-PH关闭。当前只观测到one-cell阶段门通过，不能推断bottom/top numeric可支付；缩减pilot尚未到outer或完整验收，也不资格化50×25 nm目标、2 TB容量或48 h冷启动目标。

## Task041 Review V10-r2：W0.7 reduced-p6 matched-cell warm consumer受控停止（2026-10-07）

唯一warm consumer Invocation `10d761079d90473dadce79d3f7eb6457`以`absolute_memory_limit`受控停止。service public-to-finalizer wall为`2350.819163285 s`，V5 ledger 160项中该Invocation恰一条。process-tree RSS峰`53,541,888,000 B`超过冻结cap`53,221,163,008 B`共`320,724,992 B`；dedicated cgroup峰`51,229,249,536 B`另列，不能替代tree资源权威。Finalizer `status=completed`、`result_classification=controlled_stop`，常规检查7/10；进程清场记录如原始检查表列示，不代表service正常完成。

外层markers只记录public command开始/结束；绑定的consumer内部284,367 B marker（SHA `b1f338ca…`）有44条事件，已显示one-cell factor、bottom P4/Woodbury、top full action和top P4 trace/port均已实际到达。Bottom P4矩阵为64966×64966、NNZ 27,929,686，factor ready并live；top矩阵为同维度、NNZ 39,242,250，但factor-ready未记录。port-ready后源码立即进入顶侧`ResearchExactFactorInverse`构造，其`ksp.setUp()`包含symbolic/numeric，factor生命周期事件没有转发到consumer markers。因此资源峰只能定位到顶侧factor构造区间，不能断言精确symbolic/numeric停止点或factor已完成，也不能把所有RSS都归因于因子。

固定H6反馈门、outer、五项残差、recovery及physics均`not_reached/not_evaluated`；这不是数值通过或数值失败。顶侧factor fill/字节、symbolic内存估计、下一笔分配上界仍unknown，故不得原样重跑跨入numeric。完整阶段、采样、finalizer、ledger及SHA见[本轮实测进度](shortwave_measured_progress_v10.md)、[派生记录](records/task041_v10_controlled_stop_20261007.json)和[Response V12](../response_v12.md)。匹配h控制已有serial与MPI2 pass：serial历史父wall`237.46574084204622 s`，MPI2两rank各`1 passed`、父wall`189.02536411304027 s`；MPI2 compact SHA `7cffe5c742f14c91001d6175ffa3f37d67e35615f8ac0828b21b6ced6f7c8c1e`见[记录](../../../results/task037c_matched_h_stitch_control_mpi2_20261007T232353Z/mpi2_test_compact.json)。只支持均匀W正入射控制，不是光栅pilot资格。

## 2026-10-08 后续离线比较与桥测试账目

W5旧explicit-Schur候选与fixed-H6候选的完整离线产物比较中，18项身份和两侧输入封套通过；R/T/A/A_volume、selected E/H、四个canonical角色和法向通量通过。600个外部key中26个显著，唯一失败项`["bottom",-15,0,"s"]`的幅度/功率相对差为`1.0880143757234042e-6 / 2.074050200051092e-6`，超过原`1e-6`门，因此`numeric_gate_fail`，不是两场各自public/service门的改写。完整两侧复幅值、分母、绝对差和阈值见[失败行记录](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_significant_external_failure_record.json)（SHA `9fe88ab05dfb1b448935e127103a3d871b5d07f4626133ef23943f51ebf7cb3a`）。其前另有一次method identity拒绝，numeric未评估、wall`122.18274498195387 s`，旧raw保留。资源/workflow可比性`inconclusive`，raw-Q跨场比较`not_run_not_defined`，integrated checker和solver/FE未运行。原compact SHA `c088bd14872e924d990cdb4e1eed94af96c3f9bbf477cbc376389815ae96a032`保留；带正确R/T/A/A_volume符号的[更正compact](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_offline_comparison_compact_corrected.json) SHA `f9505f6b92cc14cec3da9b863f21cb6bbbaacf98393db9eed56ad56c94b70f63`，回执SHA `21320f82533a74bcfb066e9d207a24b2189759a289122dd9a176a505a03e724e`。

PETSc LU薄桥测试的三次parent pytest attempt（一次失败、serial/MPI2重试通过）合计仅新增父wall`3.026434561004862 s`，各 attempt 独立计费；V5 ledger从162项变为165项，SHA `b983f17697a2b17e9fd6d7ef2141a3945a9b86689d2f6b048e36a51aa947711e`。W5离线checker的534秒不记入FE账。此次MUMPS 5.6.2手册来源及INFO/INFOG语义仅形成ignored派生参考；不能回填旧raw里的unknown，也不是因子峰值或RSS上界。

## Task041 Review V9 H0历史快照与当前进度（截至2026-10-07）

H0是一次只读历史快照：它对照两场W 5 nm、p6/h4、M480、MPI8×1完整consumer，并审查2 nm和0.7 nm证据；当时没有运行数值代码、测试、MPI、QEP或FE。其后H1组件验证、13.5 nm Si和W5 fixed-H6 public/service完整回归均已完成，下文分别登记。两场旧5 nm各完成1920/1920正式响应并通过各自五项真实残差和恢复/物理门；旧场public-to-finalizer为`202124.563261555 s`（56.146 h）。旧场均`performance_not_isolated`，不能用来证明新方法的因果收益。

| H0项目 | 关键事实 | 状态与证据 |
|---|---|---|
| 共同阶段wall | 从两份`consumer/markers.jsonl`相邻`stage`边界重算；较新场marker区间`202108.376 s`，public-to-finalizer为`202124.563 s`，范围不同；monitor独占wall无marker | 分段与原始身份见[H0 outcome](hybrid_0p7nm_2tb_48h_v9.md)和[机器记录](records/task041_v9_h0_readonly.json)，monitor=`unknown` |
| Side/P4工作量 | 两场内部KSP迭代合计均30296；较新场P4 backsolve和refinement各多8686次，不能从计数直接换算秒数 | 详见H0 outcome的全量分组；逐RHS MPI.MAX和嵌套时间不相加成wall |
| 13.5 nm锚点 | 唯一Si public/service场37 outer/264 `S_H`，五项真实残差、recovery/physics与finalizer通过；只存有最后inner独立raw终检值 | 已验证公共身份链和完整生命周期；不是W 5/2/0.7 nm或性能资格 |
| W 5 nm V9 fixed-H6 | 10月3日完整数值身份及legacy-native validator结果存在；后续唯一fixed-H6 public/service场已完成且五残差、physics/recovery和finalizer通过 | 旧producer资源`unqualified`单列；新场`performance_not_isolated`，不外推W2/0.7 nm、2 TB或48 h |
| 2 nm / 0.7 nm | 2 nm已有PEP/TOAR和可复用M1200/MPI8 packet；旧consumer在历史sampled-repeat实现错误处停止、formal响应0/4800，`ncv/mpd`未记录。0.7 nm已有W材料候选及目标/缩减pilot两组derived keys，未绑定正式输入 | W2 fixed-H6为`capacity_blocked_unqualified`：host样本高于1.70 TiB基线，但`predicted_peak+256 GiB`项未知；node0扣384 GiB floor后约442.29 GB，旧642.45–647.90 GB峰仅属不同后端风险信号，新路线峰未知。不是已测超限。0.7材料和keys仍为derived；2 TB与48 h未资格化 |

### H2 当前容量决定与H3候选推进（只读，2026-10-07）

两点host/node0样本与protected node0 gate差异、旧W2峰所处阶段以及fixed-H6新旧对象库存见[原容量/H3机器记录](../../../results/task041_v9_w2_capacity_decision_20261007T020417Z/w2_capacity_h3_assessment_20261007.json)，SHA `10e67f3e8115874f26cfac71af16b0f096019e548d56ed2f0773914fdd001f81`。机器记录绑定样本1/2 SHA `c5b53667b63a5545a3f4954c05b323e845a1417fa284b5dcb894e18093522559` / `2cca36005b6496f0ccc9ddace8e8f3f3d87fdc49e75fe8ade5698507893a7aa8`、task/current registered resource sources及保护stash OID；该快照不是launch admission。资源口径和对象并存的派生更正见[interpretation correction](records/task041_v9_w2_h3_interpretation_correction_20261007.json)，不回写原机器记录。

H2状态为`capacity_blocked_unqualified`，不代表OOM或算法失败。当前node0样本扣除384 GiB floor后有`442288062464/442291187712 B`；保护stash中的node0 gate未应用。正式resource authority为process-tree RSS与专属job cgroup `memory.current`两者最大；当前session cgroup共享且无有限上限。host §10.2门与node0 floor并行：host须有`MemAvailable >= max(predicted_peak+256 GiB,1.70 TiB)`；本次host样本高于1.70 TiB，但`predicted_peak`项未知。扣floor后的node0空间约442.29 GB。旧process-tree/authority峰`642449637376/647904415744 B`分别在top side-factor construction和top pre-formal repeat，来自不同的one-cell exact-P4后端，只是风险信号；packet驻留和cell-condensed fixed-H6的新因子并存未知。新路线删除全Schur列物化和旧每侧16次预付sample，但包含8次setup反馈动作，尚无保守峰值上界。因此维持`capacity_blocked_unqualified`，并行门不冲突；不是已测OOM或新路线必然超限。输入`swap_limit_bytes=0`不会恢复硬swap门，V9为observe-only。

H3派生得到一组**候选材料值**而不是正式输入：`.7 nm`光子能量`1771.202834760004 eV`，Henke 1752.87/1781.22 eV两点线性插值得`f1=29.482678085431722`、`f2=9.276118377813308`；NIST密度`19.3000 g/cm³`与CIAAW原子量`183.84(1)`给出候选`n=0.9995903781323069+i0.00012887909720587614`，项目吸收符号为`n=1−δ+iβ`。50×25 nm目标几何的derived keys为32056个有序项（top16030、bottom16026；32054 propagating、2 nonpropagating、0 Rayleigh），canonical SHA `9f43482413e86c5d2db2e7ba8e5fed0b684d89566f070a88946f4c6bbbc7d4b5`。缩减pilot另有1292项（646/side，1290 propagating、2 nonpropagating），canonical SHA `878f48f650b8807d894a554d7b5ab76dc57edad9c58adae7997027d5c8346a21`。两组key身份各自绑定候选几何，均未进入正式`.dat`/resolved。保留两项nonpropagating及其模式身份，不删作“无效值”。材料不确定度尚无模型/传播，但这不是新增的pilot启动门；正式输入仍须绑定原始来源字节、常数、单位、插值区间、正吸收符号、n/epsilon、几何及resolved hash，不能称实验精度已认证。

最小后续接线审查、5 nm相邻marker分段、1980行/场的side audit工作量、H3材料来源及全部身份限制见[Task041 V9 H0报告](hybrid_0p7nm_2tb_48h_v9.md)。以下V8及更早条目保留为各自阶段的历史记录。

## Task041 Review V9 H1：13.5 nm Si fixed-H6 public/service完整回归

这是一场已完成的公共单`.dat`生命周期回归，不是测试selector或W5算例。固定H6为模态预条件器提供按需反馈，正式结果仍由原全局方程、RIGHT FGMRES、P4、五项真实残差与物理门决定。

| 项目 | 本场数据 | 边界 |
|---|---:|---|
| 身份 | source `836b7dfb377f11d8d9fd591eacb7a982f7cbbbac`；Invocation `443995ec69bd45d0a36a1be48ced33a3`；Si 13.5 nm、p6/h10、M120、MPI8、cell-condensed | 该场是唯一新增13.5 public回归；route-plan和leading-PH开关为false |
| 数值 | 37 outer、264次solver `S_H`；五项真残差最大`2.284003276919731e-9 <= 5e-9`；最终inner raw相对残差`3.4826090281102427e-4 <= 1e-3` | 最终inner有独立终检；更早36次没有逐次保存的独立raw终检 |
| side/P4 | bottom/top apply `74/74`；内部KSP `2410/2608`步；P4回代`4820/5216`、精化`0/0`；side Q/H6/A6分别`4820/2410/4820`与`5216/2608/5216` | side计数保持原rank-local/复制口径，不乘8；`side_A` audit和最终诊断范围不同 |
| fixed反馈工作 | setup门8次`S_H`/C matvec；两侧各8次H6 apply、16次degree-3 MatMult；随后solver 264次`S_H`/C matvec、每侧264次H6 apply和528次MatMult；整场每侧272/544，Schur列0 | legacy cost-probe调用0；setup门动作计入总工作量但与GMRES原9+1预算分列 |
| C-LU | owner rank7建因子1次；rank-local累计字段为`0/0`，owner/last-solve保存`8/8` | 两者是不同scope：rank-local累计不能代表owner次数，last-solve也不是全run累计；owner累计未持久化。C matvec不等于LU solve |
| 时间 | setup至outer `343.619396 s`；outer `2821.718932 s`；恢复段`9.978173 s`；consumer `3176.842516 s`；public-to-finalizer `3180.339667 s`；service父wall `3180.537532 s`；唯一finalizer账`3181.091282263 s` | 相邻marker段不重叠；嵌套、rank和phase计时不叠加。performance=`not_isolated` |
| 资源与终态 | tree RSS `8,936,820,736 B`、PSS `6,437,861,376 B`、USS `6,069,190,656 B`、dedicated job cgroup峰`6,214,434,816 B`；finalizer `10/10` | 专属cgroup不等于共享宿主；secondary checker `not_available` |

详细计数和源文件hash见[13.5 V9 outcome](hybrid_0p7nm_2tb_48h_v9.md)及[只读成本compact](../../../results/task041_v9_13p5_public_fixed_h6_service_preparation_20261006T044333Z/readonly_h1_13p5_cost_compact.json)。consumer summary SHA `21ac7e56c45d90cbe540587bda831540d42077a32477cfae8a1daa2ba11f54d9`；finalizer summary SHA `04d0b4d8c2ade9f85340a363bb38b2abd9f64be4c4a0891bf9608e8fde0682f7`。V5 ledger仍127条、SHA `15d4b5dcb1ed0a867e584dc89d33a52da453575697a16a45d2aed101b5964836`，本Invocation只记一次`3181.091282263 s`。

## W 5 nm fixed-H6 public/service终态

10月3日`run_manifest`、`supervisor_summary`、legacy descriptor和selected-mode binding保存完整的W5/M480/MPI8/p6/h4/cell-condensed身份、输入/physical/resolved hash、packet manifest/identity和600 external-key SHA；supervisor记为`validated_legacy_native_packet`。提交`ce31f3738f469a04d23c50af0a7c7306afde3b38`为注册W5 fixed-H6分支增加窄路由，沿用既有validator/binder，不伪造新profile封套。随后唯一W5 fixed-H6 public/service场已完成并通过原数值、恢复、物理及finalizer门，详见下表和[机器记录](records/task041_v9_fixed_h6_public_5nm.json)。旧producer资源资格仍为`unqualified`；新consumer有独立资源记录。新场`performance_not_isolated`，也不构成W2/0.7 nm、2 TB或48 h资格。

| 项目 | W5新场实测 | 解释与限制 |
|---|---:|---|
| 身份/方法 | source `d6fe6b2b239896e66d8c5d1bf9b8a0e45931a561`；Invocation `2539de4d129f41e2ac49536bfd3b6fde`；W 5 nm、p6/h4、M480、MPI8、cell-condensed、P4 `5e-13` | fixed-H6研究分支；旧legacy-native packet由既有validator/binder复用 |
| 原方程/物理门 | 49 outer；五项真实残差最大`4.87285789944735e-9 <= 5e-9`；R/T/A/A_volume=`0.7331842734229947/0.00022009869546076797/0.2665956278815445/0.2665962726246991` | consumer、恢复、physics、traction、interface、external-Q及official-output身份门通过；secondary full3D checker未运行 |
| 反馈与侧区工作 | setup 8次`S_H`；正式求解307次；总315次；每侧H6 apply/MatMult `315/630`；C matvec 315；侧区KSP `3839/3893` | 旧预付probe 0、完整Schur列0；C-LU因子1次，owner累计solve attempts/successes `307/307`；P4 backsolve `11551/15546`、refinement `3873/7760` |
| 唯一wall与资源 | service finalizer计账`59914.951233018 s`；tree RSS峰`42573258752 B`；专属job-cgroup峰`41376940032 B` | `performance_not_isolated`；两种峰口径分列。与Oct 3约70.36%的wall差是不同source/method下的描述，不是因果提速 |

固定反馈的setup门和正式求解分别计数；侧区保留计数不乘MPI rank。具体非重叠marker wall、各字段scope和原始artifact SHA见[W5 outcome](hybrid_0p7nm_2tb_48h_v9.md)与[机器记录](records/task041_v9_fixed_h6_public_5nm.json)。唯一wall由service finalizer记账，不另计outer、consumer或rank时间。

## Task041 Review V9 H1：fixed-H6反馈门组件验证（2026-10-06）

固定H6反馈门先检查同一固定作用对复数输入的重复性和线性，避免把不固定的反馈冒充线性模态算子；正式外层算子、RHS、P4和最终验收门不因此改变。core SHA `64ef9439ee2d527049877edfa88ce8e848e4370600f1a8b9ee41d4684709dea3`，test350 SHA `941606bba844cdeabad3c44bedfe86c2578df7370690621c0a6611bbc32482a6`。

| 验证 | 实测 | 结论与边界 |
|---|---|---|
| Serial非有限输出节点 | 1 passed；最后rank在原反馈作用完成后产生非有限输出，cleanup后allgather完成；父wall 5.001762014115229 s | 只验证单rank注入下组件门失败路径与清理 |
| MPI2五selector组 | rank0/rank1各8 passed，无RuntimeWarning；最后rank坏输出被全rank一致拒绝且后续collective完成；父wall 5.001988966949284 s | 不泛化到任意rank-local底层异常，也不等于MPI8 packet或FE |
| 工作量合同 | setup repeat/linearity门8次`S_H`，每侧8次H6 apply和16次实际H6矩阵乘，8次C作用；GMRES原9+1预算未改 | setup门和每次求解分列；不据tiny计数估算5 nm成本或提速 |
| 账本 | V5增加两条唯一pytest attempt；新增10.003750981064513 s；ledger 124条，SHA `60ee77b84661f91944ceffb22e9ab544178d607403f20696b5ffcd875f32fe67` | ABI/static/rank-local时间排除；见[receipt](../../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/v5_ledger_append_receipt.json) |

生产代码仍是显式研究分支，普通默认未改变。public `scripts/run_case.py`单.dat接线、13.5 anchor及唯一W5 public/service场均已通过各自合同；W5性能未隔离，H2–H4仍未完成。H1路由实现和组件测试不单独构成W5资格；W5数值结果、资源口径与限制见上方终态表。

## H2：W2 packet与容量只读准备（未启动）

官方输入是`input/official/task041/side_balh/2nm_p6h1p5_m1200_mpi8_cell_condensed.dat`，SHA `28c4dc3f723176693ee8b933b7cd5315a973ebeff0c7a4df5d01dee15ea54307`；W 2 nm、p6/h1.5、M1200、MPI8、cell-condensed。已有producer位于`results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z/producer`，`mode_prep_summary.json`记`TASK041_MODE_PREP_PACKET_READY`、`producer_scope_released=true`。旧producer输入SHA为`0edd17344454939cb2cd439b5221f6d08f03c42b9f36b083469e63f667e75e57`，当前正式`.dat` SHA另列；两输入文本差异只在`model_id`和`run_id`。物理SHA `537056f184c8be19a4688c7e4cc1fef883141b9dbab7380c1df2efc5a3b465fc`，resolved SHA `10835c84bc3c6f6fdbb5630a48a84a538fa87bd621346f068942cb5cdcc9f6b4`，3904 external keys SHA `582ec6db409ecbbaa13254bb52686e330bf4c2ff3cf7939a5d47a410c11c8e95`。packet manifest SHA `7ef2ecc5587f79a123e44cacfe347356d13b36336948ade1672787c6430163d2`，identity SHA `171ef1ca91ce72d3ca2a7ca61d7ab2f5be4759934656e7730afd757d3ab49d17`，mode-prep summary SHA `5810f19d2834c122e16c178ad1346c10e8288aa3ade565bf26ea73006c252be2`。旧`selected_mode_manifest.json`的`consumer_binding.pass=true`只属于历史consumer绑定，不证明新的fixed-H6 consumer已通过。此次只读准备没有读取shards、运行packet checker或正式链validator；新consumer的实际身份绑定仍待新场验证。

producer已用SLEPc PEP/TOAR；正、负方向各请求2400并收敛2422/2423个候选，26次迭代，最后选择每方向1200。`ncv/mpd`未记录，不能由源码默认补成实测。旧2 nm consumer曾在历史sampled-repeat门停止：`absolute=2.637750e-4`、参考范数`5.957499`、relative`4.427612e-5`，高于`1e-10`；formal响应为0/4800。这是旧consumer路线的负结果，不是packet身份失败。fixed-H6分支将以自己的8次setup反馈门替代旧预付sample，不取消后续原方程、P4、五项残差、恢复与物理门。

容量风险仍未闭合：旧失败consumer在formal响应前的process-tree RSS峰为`642449637376 B`，memory authority峰`647904415744 B`、PSS/USS `639186608128/638677749760 B`；它不是fixed-H6完整W2峰值。先前单次node0读数扣reserve后约`442474672128 B`，仅作非准入观察且此处无独立原始快照路径；未来运行必须重新采集宿主、node0、cgroup、磁盘及冻结CPU map门。component级时间、new W2总峰与wall都仍未知。此只读阶段状态为`plan_only`：无新config/argv、无fresh ABI、无unit/root准入、无QEP和FE。

## Task041 Review V9 H1：W5路由与owner计数定向验证

代码提交`ce31f3738f469a04d23c50af0a7c7306afde3b38`包含恰好九个已审核源码/测试文件，保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`仍保留。测试分attempt完成：初始serial按序收集7项后6 passed、1 failed，失败为worker fixture将消费者规范化后的默认CPU map误断言为`None`；受影响断言修正后，定向serial三selector通过。MPI2两个test350节点每rank各2 passed。serial/MPI2都保留一个来自受控非有限PC故障路径的`RuntimeWarning`。这些测试是路由、owner-count与tiny-solver合同验证，不是MPI8真实rank绑定、完整legacy packet验证或W5 FE。

| 实测attempt | 父 wall | 原始证据 |
|---|---:|---|
| 初始serial失败 | `10.002066798973829 s` | [attempt](../../../results/task041_v9_w5_legacy_count_serial_20261006T074100Z/serial_pytest_attempt.json)、[stdout](../../../results/task041_v9_w5_legacy_count_serial_20261006T074100Z/serial_pytest.stdout.log) |
| 定向serial修正后 | `10.00147465406917 s` | [compact](../../../results/task041_v9_w5_legacy_count_serial_retry2_20261006T075129Z/serial_compact.json)、[stdout](../../../results/task041_v9_w5_legacy_count_serial_retry2_20261006T075129Z/serial_pytest.stdout.log) |
| MPI2 | `5.00106007209979 s` | [compact](../../../results/task041_v9_w5_legacy_count_mpi2_20261006T075409Z/mpi2_compact.json)、[stdout](../../../results/task041_v9_w5_legacy_count_mpi2_20261006T075409Z/mpi2_pytest.stdout.log) |

三条pytest父wall各由唯一attempt写入V5一次；ABI、静态检查、未启动pytest的线程preflight失败均未计费。V5 ledger为130项、SHA `11679a139bbcd5f8a40a7b1758a9434df396d50c2e069fd46f115620d2a5c7f4`。修正后的serial只运行worker路由及两个test350节点，不声称原六selector组在最终SHA上一次全过。

## Task041 V8 5 nm 完整 consumer 终态

运行源码 SHA `d86ee4afb352304c9ff0d5042256ad9a7d0c9a4f`；结束 HEAD `499c25de74c30ed0bdee17180f5315765f35efbe` 与之不同，差异仅为运行中获准的五条文档路径。registered W 5 nm `cell_condensed` consumer完成1920/1920正式响应，RTA/EH/衍射、五项 true residual、恢复和物理门通过：`R/T/A/A_volume=0.7331842733877258/0.00022009869572838214/0.2665956279165458/0.2665962726230213`，五残差最大`6.221702926229589e-11`，closure `6.447064755388254e-7`。24 h目标未达到；worker自然exit0，但public/finalizer因严格结束SHA检查以exit3/failed保留，数值通过不覆盖该历史。authority/tree RSS峰`43,858,726,912/43,153,915,904 B`；cgroup `memory.peak=43,867,639,808 B`是历史计数器峰，不是采样current峰；job/cgroup swap峰0，global swap/pswp按V8仅观察。consumer worker wall `189,308.766050059 s`，public至finalizer `189,323.841971047 s`；旧`53.239672 h` worker基线同口径比较约改善`1.23%`，跨worker/public口径约`1.22%`仅是粗比。完整细节见[终态outcome](formal_5nm_2nm_v8.md)及[机器record](records/task041_v8_formal_5nm_2nm.json)。

## Task041 V7 快照（进入 Review V8 前）

本快照基于运行源码 HEAD `c5f95db7f7c2c640b666035a1949f9dc666f4da4`。13.5 consumer 使用target=None，不能替代5nm target正式入口或完整consumer验证。

| 阶段 | 当前结论 |
|---|---|
| G1 | 14 项独立 Q 全部未过 `1e-11`；7 项独立 PC 通过 `1e-8`。 |
| G2r2 | layoutfix-r2 跨运行布局匹配；PC1 的Q1/Q2实际执行0/1/2修正。step0 Q差`4.8268e-11/5.1937e-11`超`1e-11`，A4仍通过；step1/2 Q与A4通过。 |
| G2c | 顶部列12/493/666三响应的`e_x/e_A`均过`1e-8`；7冻结PC节点/14独立Q/7 PC及shared A4均过原门。诊断完成，`qualification_pass=false`不代表动作失败。 |
| G2c修正触发 | 524个响应P4调用中521个原physical/augmented A4均过门仍接受单修正；原A4失败才修正不适用。此结论仅描述G2c当时的触发分析。 |
| 当前内部精化目标 | 后续实现并分侧验证`5e-13`内部目标，最多两次修正；原最终physical/augmented A4门`1e-10`及Q/PC/响应门不变。 |
| G2c响应成本 | full `660.297 s`、condensed `745.262 s`，凝聚慢`84.964 s`；不是加速。authority/tree峰`42,588,479,488 B`，swap 0，cap`53,221,163,008 B`，清场/finalizer通过。 |
| public/service | G2c worker/public诊断合同通过、service exit0。G2r2旧service exit3是public lifecycle schema误读，保留原始失败；只读重校验已通过。 |
| Bottom/top selected-side target | Bottom4与top4分两次运行覆盖固定manifest八项，重复A及共同Q/PC/A4检查和原配对门通过。Bottom原service exit3因策略声明误判保留，派生25项合同复核通过；top原service exit0且25项通过。它们不证明单个完整consumer同时持有两侧时的资源资格或全场资格。 |
| 13.5 nm registered cell-condensed | source `c5f95db7f7c2c640b666035a1949f9dc666f4da4` 下consumer数值/物理门通过并自然exit0；`R/T/A/A_volume=0.3656257890944995/0.012990632409140064/0.6213835784963604/0.6213835794981195`，closure`1.001759120100587e-9`，5项残差全过，复用producer且QEP调用0。 |
| 13.5 nm global资源门 | 运行中global swap增`286720 B`、pswpout增70页（首越门elapsed `2179.15364028397 s`，worker仍存活），归因未知；job/cgroup swap为0、authority/tree峰`8,910,348,288 B`、cgroup峰`6,212,177,920 B`、硬cap`53,221,163,008 B`。自然exit0不改变global零增量资源门未通过的结论。 |
| 13.5终态与入口 | Finalizer 10项全真，wall `2269.036298547 s`；V5 ledger 54条、累计`45194.90092220603 s`。正式5nm cell-condensed target入口修复已随source `c5f95db7f7c2c640b666035a1949f9dc666f4da4`推送；本次13.5使用target=None。 |
| 完整正式 5 nm consumer | 固定八项分侧验证已完成；单个完整consumer双侧同时驻留、资源资格、Schur、outer/RTA/EH与全场资格未运行/未建立。G1旧PC 7/7及G2c本次7/7均保留各自范围。 |

G2c的三响应凝聚比full多`84.964094673 s`；缩减+恢复计时合计`84.001845964 s`，是可节省量的宽松上界、不是预测。原A4门不足以单独触发Q修正；**G2c阶段**不据当时数据提出更严的内部目标。后续G2d已实现并分侧验证`5e-13`内部精化目标、最多两次修正，原最终A4门`1e-10`不变。G2c收口时ledger为45条、`35847.63433988102 s`，当场finalizer追加一次`3315.690725968 s`。截至13.5终态，V5 ledger为54条、`45194.90092220603 s`；本次finalizer单次追加`2269.036298547 s`。逐节点实值及global资源监督缺口建议见[中心outcome](causal_fix_5nm_v7.md)和[机器记录](records/task041_v7_causal_fix_5nm.json)。以下历史正文保留。

## 2026-09-23：Review V6 13.5 nm 与 5 nm fixed-eight 收口

13.5 nm 显式 cell-condensed Hybrid 的五项 true residual/物理 Gate 与 H2 数值全向量对照通过；Full3D secondary 未运行，旧 H2 资源合同令总 checker fail。5 nm 只完成固定八 RHS 组件配对：bottom 4/4、top 2/4；top formal column 12、493 的 `e_x/e_A` 超过原 `1e-8` 门。64 GiB cap 是本场专用授权；完整 5 nm consumer、RTA、EH、24h 均未运行。详细逐 RHS、finalizer、ledger 和16份 manifest 哈希见 [V6 outcome](transfer_fix_5nm_24h_v6.md)、[record](records/task041_v6_transfer_5nm_24h.json) 与 [ignored compact v2](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/preparation/f3c3_cap64_r1_20260923/cap64_r1_postmortem_compact_v2.json)。

## 2026-09-22：R3i3 MPI8 tiny-FE 数值门收口

唯一 MPI8 tiny-FE 场在旧 full p4 bottom/Q transfer consistency 门停止：`1.3116919128020489e-11 > 1e-11`，约 `1.312×`；原 p4 A4 `6.795828778707217e-11 <= 1e-10`。cell_condensed、PC、真实 side.apply、top 未进入，故不是凝聚 p4 失败，也没有响应等价、加速或正式生产 MPI8 资格。

| 结果 | 实测 | 边界 |
|---|---:|---|
| 资源 | tree/authority `4636389376 B`；dedicated current `2565689344 B`；PSS/USS `2828743680/2582614016 B`；minAvailable `2142846394368 B > 412316860416 B`；swap/pswp `0` | 126 samples；资源门未触发，PSS/USS 稀疏 |
| 终态 | worker `rc=1`、termination null、unit `68.728670s`、清场完成 | phase/workflow 嵌套不重复计费 |
| ABI/NUMA | 8 rank、CPU1–8、complex128/Int32 通过 | ABI `numa_maps` 为 default；FE 私有页未观测，严格 node0 资格未取得 |

证据与 hash 见 [R3i3 compact v2](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/run_20260921T195057.555038315Z/r3i3_compact_v2.json) 和 [record](records/task041_v5_condensed_speed.json)。R3i3 是研究资格节点，不改变默认 full/production；13.5/5/2nm 新流程未运行，既有 5nm/QEP 历史不改。V5 ledger 已一次追加 `68.728670s`，累计 `7668.882139588s`。

## 2026-09-22：R3h8 p4 凝聚组件阶段进展（R3–R6尚未完成）

p4 单元凝聚先消去单元内部未知量，再解较小的保留系统并回代恢复完整 FE/端口修正；最后仍检查原 A4 和完整残差，未放宽精度。p6 已凝聚，本阶段不重复消元；cell_condensed 仅显式可选，默认 full 不变，正式 runner 尚未接线。

| 阶段 | 结果 | 资格边界与入口 |
|---|---|---|
| R3c | early synthetic 单端口 serial/MPI2 通过 | 非真实 FE/MPI8/性能资格 |
| R3d2 | synthetic 双端口与 preallocation serial/MPI2 通过 | 非真实 FE/MPI8/性能资格 |
| R3f | tiny real-FE p4/port 完整逆 serial/MPI2 通过 | R3f 的 MPI2运行期资源采样缺测保持 not_observed |
| R3h5 | serial 27 passed/4 skipped；MPI2 每 rank 31 passed | 首轮 ABI NameError 后仍执行的尝试不计资格；最终源码回归关闭 |
| R3h6 | 同一 side/layout tiny FE old/new Q/PC，serial/MPI2 rc0，自然清场，RSS/资源门通过 | 不把 167 秒对 82 秒写成加速，不外推正式 MPI8/大模型 |

七个源码 hash、donor 与 Task041 自研适配边界、56 项 raw 索引和完整入口见 [R3h8 tracked record](records/task041_v5_condensed_speed.json)；冻结摘要见 [R3h7 compact](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3h_validation_20260921/r3h7_compact.json)。R3h8 已一次追加 `288.010923037 s`，累计 `7600.153469588 s`；后续文档纠偏未再计费。当前仅 socket0/node0 方向继续，未来正式 MPI8 规划 CPU1–8/membind0；node1 硬件修复和双路比较暂停，5/2nm全流程、RTA、QEP、正式资源与提速均 not_run，R3–R6 尚未完成。

## 2026-09-21：Review V5 R1i 2666 复测（历史快照）

R1i 只将 BIOS Memory Frequency 从 `Auto` 改为 `2666 MT/s`，其它设置、保护、刷新和风扇状态不变；这是工作站 CPU/NUMA 内存复制诊断，不是2nm物理模型。node1路径仍骤降，CPU1仍未准入；首窗正常不算修复。

| path | window 1（GB/s） | window 2（GB/s） | window 3（GB/s） |
|---|---:|---:|---:|
| local socket0→node0 | `35.6379` | `35.6640` | `35.6967` |
| local socket1→node1 | `35.6484` | `31.6700` | `11.0249` |
| cross socket0→node1 | `23.5626` | `22.9569` | `13.1040` |
| cross socket1→node0 | `23.4082` | `22.9247` | `21.6826` |

两批 `rc=0`、清场完成；43 PCI raw+43 BMC 文件、16 DIMM、688对值的差值为 `[-1,+1]°C`。R1i compact v3 绑定六个 TEMPLO 和两个 TEMPMID 事件；cross `P1-DIMMC1` TEMPLO sample4→5 以 PCI `65→67°C` 作时间括号，异步 BMC 为 `65→66°C`，sample1–10 未见新 MID但 after_load 后置位，触发时间未知。`TEMP_MID 93→95°C` 仍仅只读评估，未改补偿、刷新、保护或80°C观察线。

入口：[R1i tracked compact](records/task041_r1i_2666_retest_20260921.json)，ignored 原件为 [compact v3](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1i_2666_retest_20260921/r1i_2666_two_batch_compact_v3_20260921.json)，SHA `4e7a3d0e21bfe53da457010493a22c71140b7cf734bfdf4b1034f88bc2cacbc6`；v2最终 SHA `ceb19601a337b0d40b6eedd0f260faed018c0b5459904aad24147a11a754bf57`。

## 2026-09-20：Review V5 R1h 跨 NUMA 复现（历史，已由 R1i 更新）

R1h 是一次不改系统设置的内存复制诊断：CPU socket0 的 OS CPU1–8 → memory node1，CPU socket1 的 OS CPU25–32 → memory node0；两阶段各 8 个单线程 worker、3×60 s。两阶段开始和 near-end 都是 `8/8` buffer 位于预期远端 node，driver rc0 不等于硬件资格通过。

| phase | 三窗吞吐（GB/s） | 结果 |
|---|---:|---|
| socket0 / CPU1–8 → node1 | `22.648688106036644 / 21.977584096329075 / 7.395682818558859` | 第三窗较首窗约降 `67.35%`，未准入 |
| socket1 / CPU25–32 → node0 | `19.789193732901627 / 19.759391333017003 / 18.843317623093906` | 第三窗较首窗约降 `4.78%`，不写成零退化 |

R1h 父侧 wall `629.724913916 s`、16/16 worker 三窗完成且精确 PID 清场；22 hardware samples、110 final-read、44 个48行 MSR 文件均已绑定且新读取 rc0。358 resource samples 的最低 `MemAvailable` 为 `2114795454464 B`；swap `299008 B`、`pswpin=0`、`pswpout=73`，新增 global swap delta 0。16 worker 的 minor/major/stime delta 均为0，CPU0/CPU1 最大 wait 比为 `0.0009933352281917688`/`0.0008195138298330328`，shared cgroup 的 throttle/high/max/oom 字段均为0。活跃平均 Bzy_MHz 约 `3600.33/3599.55`、CoreThr=0；BMC 温度是窗口括号（不是同刻极值），且只来自 `P1-DIMMC1/P2-DIMME1`：CPU0→node1 约 `47–54/54–78°C`，CPU1→node0 约 `57–77/76–77°C`。所有 e24 为0只能削弱持续外部 MEMHOT，不能排除瞬态或内部热控。

当前分类为 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_ANOMALY_REPRODUCED_NO_UNIQUE_CAUSE`；R2–R6、R3、PDE/MPI/QEP 均 `not_run`。本批未测完整 process-tree/cgroup RSS 峰，双缓冲约1 GiB仅是对象规模，不是峰值资格。V5 最新 ledger 为 `3327.407495518 s`、SHA `06d8dd9040cdbb306f79337eea80f5f09316b7dc8f04c3d9fe419ad3ac261594`；旧 as-of 字段保留。详见 [R1h outcome](cpu_numa_condensed_speed_v5.md)、[R1h compact](records/task041_v5_cpu_numa.json) 和 [R1h raw summary](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/r1h_result_summary_20260920.json)。

历史维护建议（R1h当时口径；R1i已执行但未解决）：R1h阶段仅提出记录 BIOS Memory Frequency、若菜单有2666才做单项对照的计划；当时不假定原值为 Auto，且未改硬件或 BIOS。R1i 后续已实际执行 Auto→2666 MT/s，但 node1 路径仍未稳定；保护、刷新、风扇和电压边界保持不变。

> **2026-09-20 Review V5 R1d-B 当前状态（as-of 2026-09-20T13:33:25.642281784Z）**：R0 终态证据已整理；R1d-B 唯一一次匹配负载已完成，driver `rc=0` 不等于 CPU1 通过。CPU0/socket0/node0 三窗为 `32.173939890 / 32.183022717 / 32.190473984 GB/s`；CPU1/socket1/node1 为 `33.263204952 / 28.338248830 / 9.265976385 GB/s`，第三窗相对首窗下降约 `72.14%`。两侧启动/near-end NUMA 均 `8/8` local，活跃频率约 `3.6 GHz`、CoreThr=0；DIMM 观测峰 socket0/1 为 `64/78°C`，状态 ok。分类为 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_COLLAPSE`，根因未闭合；R2–R6、R3、PDE/MPI/QEP 和新负载均 `not_run`。详见 [R1d-B outcome](cpu_numa_condensed_speed_v5.md)、[R1d-B compact](records/task041_v5_cpu_numa.json)。

| R1d-B 项目 | 实际证据 |
|---|---|
| 父侧运行 | `2026-09-20T13:14:33.179410647Z`–`13:25:03.994581030Z`，parent `CLOCK_MONOTONIC` wall `630.795106023 s`，driver rc0 |
| worker | 16/16 rc0；各 3/3 窗口完成；CPU1–8/node0 与 CPU25–32/node1 各 8/8 local first-touch/near-end 观察 |
| 资源/热 | 364 resource samples；MemAvailable 最低 `2115000832000 B`；new global swap delta `0`；DIMM 峰 `64/78°C`，无 thermal/resource stop |
| 账本 | V5 唯一 ledger after `1434.768455852 s`，SHA `69aa9738e83d3d9d042124ef3a71e92df3489d6461c3d32a4465c64092ab0508`；只计一次顶层父 wall |

清场使用保存的精确 PID 列表逐项检查，20/20 driver、telemetry、low-load 和 phase worker PID 已从 `/proc` 消失；此前按 `comm` 的零行过滤只作辅助，不能单独证明 bash/python 进程退出。当前 resctrl 未挂载、mc0..mc3 CE/UE 为0仅是终态只读快照，不外推全程。

> **2026-09-20 D3a 终态（as-of 2026-09-20T07:49:33.807349Z / 15:49:33.807349 CST）**：D1e 已结束，不能继续沿用下方 D2a 的“运行中”作为当前状态。producer QEP packet 已保存；consumer 在两侧合成 modal Schur 重复一致性门失败，原始分类 `IMPLEMENTATION_FAILURE`，finalizer 为 `failed/service_boundary_failure`。这不是 OOM、超时、外部 kill 或投影误差结论。40 行=8 probe+32 modal，bottom/top 各16；formal Schur `0/4800`，outer FGMRES `not_started`/0，RTA/full field `not_run`。本段只记录已自然终止的旧 D1e 与 producer metadata 复用核验，作为 Review V5 R0 的已有终态证据；R1–R6 均 `not_run`，不记人工受控停止。详见 [Response V8](../response_v8.md)、[D3a terminal record](records/task041_d3a_terminal_20260920.json) 和 [2nm terminal summary](2nm_d1e_terminal_20260920.md)。

| D3a 终态项 | 实际值 |
|---|---|
| 运行 source / unit | `bde0686891af10bb489e4b1cb14500791cb50351` / `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` |
| producer / consumer | `29504.116038094042 s, rc0` / `135717.4772190291 s, rc1` |
| public / finalizer | `165222.44361121487 s` / charged `165228.433265082 s`; finalizer `service_boundary_failure` |
| repeat gate | combined bottom+top sample: relative `4.427612e-05 > 1e-10`; `max_column_relative_error=1.169058e-04`; side root cause unlocalized |
| modal raw | 40 lines, `87154 B`, SHA `dd06b01eac2928ff0814bef9bd3951ac256d776366ed7fd177392374e0175cde` |
| resources | service-tree RSS peak `642483171328 B`; cgroup peak `647904940032 B`; warning/hard/reserve `1539316278886/1759218604442/412316860416 B`; global swap baseline `8192 B`, new used `290816 B`, pswpout +71 pages; job/cgroup swap `0` |
| producer reuse | packet retained; metadata validator `rc=0`, `producer_resource_qualified=true`; consumer-only restart/shard+ABI consumption validation not run |

底部样本 `16/352 iter/36004.124497986864 s/max residual 0.009981656767193032`，顶部样本 `16/394 iter/40527.54153031926 s/max residual 0.009939510152843832`；这些小 RHS 的 `reason=2` 不等于正式 Schur 或全局物理通过。D1e 的完整终态与旧 D2a 运行中记录分开保存。

> **2026-09-20 D2a 运行中状态纠正（as-of 01:19:51.480911341Z / 09:19:51 CST）**：下列旧段仍是历史登记，不再代表当前最新运行状态。D1e 已实际启动并仍在运行；producer QEP 已完整落盘，consumer 尚未完成 full solve，formal Schur `0/4800`，outer solver `not_started`/outer response `0`（分母不适用），RTA `not_run`。当前不是终态，`systemd Result=success` 不是 solver PASS。

模型是钨（W）、2nm、p6/h1.5、M1200、MPI8×1；Schur 是供外层迭代使用的模态耦合预条件矩阵。当前两侧各 8 列各算两遍的重复性计划共 32 次，已有 21/32 个样本，正式 Schur 仍为 `0/4800`，不是 21 项 formal 进度。

## 2026-09-20：Task041 D2a / D1e 运行中（历史快照，已被上方 D3a 终态覆盖）

| 项目 | 当前事实 |
|---|---|
| source / unit | `bde0686891af10bb489e4b1cb14500791cb50351` / `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` |
| host身份 | Invocation `1cf5e34338754dbfa80df487b322c72c`，MainPID `571560`；CPU1–8，数学线程1 |
| producer | QEP mode-prep wall `29501.598348574014 s`，packet ready，scope released |
| formal Schur / outer | formal Schur `0/4800`；outer FGMRES `not_started`、outer response `0`（分母不适用） |
| 21 modal样本 | bottom13 / top8；固定均值外推 `133.57896112787233 days`，仅 derived sample arithmetic，不是 ETA |
| modal数值审计 | 21行均 `reason=2`、`explicit_true_target_reached=true`；最大 `relative_residual=0.009981656767193032 <= 0.01`，不等于最终全局残差 |
| memory as-of | process-tree RSS `642483105792 B`；cgroup current/peak `647585968128/647695921152 B`；不是完整运行峰值 |
| producer reuse | packet/hash 已核验；缺 public `supervisor_summary.json`，consumer-only reuse 尚未 qualified |
| 状态边界 | 不停止、不重启、不发 signal；无 full solve/RTA/official qualification |

报告与记录：[Response V7](../response_v7.md)、[D2a hash-bound record](records/task041_d2a_progress_20260920.json)、[2nm progress](2nm_d1e_progress_20260920.md)、[D1e evidence index](../../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_evidence_index.json)。

## C2d：共同布局离线复核收口（2026-09-16）

本节为 2026-09-16 历史快照。C2c 没有启动新计算，而是对已有 C2 raw 运行做了最小摘要纠正：
raw 已有两侧各 4 对、每场 8 项，共 8 对/16 主响应；合并摘要把 `apply_count` 写成
`8`，派生视图仅改为 raw 重算的 `16`。因此离线 checker 可判定同布局响应等价通过，但
原 service 的 `PAIRING_SETUP_FAILURE` / `service_boundary_failure`、systemd exit3、旧
summary、run/finalizer/journal 和全部 raw 均保留，不能把原服务改写成成功。

| 维度 | C2d 实际结论 |
|---|---|
| scope / mode | `representative_rhs` / `common_layout_equivalence`；仅既有 C2 raw 的离线派生复核 |
| 主响应 / pairs | `16/16`、`8/8`；每侧 4 对；8 个固定 RHS，两个 variant 均 zero-start |
| 数值 | `max e_x=3.0316012438358734e-9`、`max e_A=8.229180550916894e-9`；原 reason/residual 逐项通过，inner residual 仍≤`1e-2` |
| layout/lifecycle | 同一 side 的 mesh/MPC/凝聚布局、A、p4 factor、P/PH/PC 和 bottom release→top 顺序由 raw checker 复核 |
| 组件耗时 | `1981.6339287383016 → 1454.4546840919647 s`，减少 `26.6033%`；仅同进程诊断，不是完整 cold/service 提速 |
| 资源 | C2 全树 RSS 峰 `51501744128 B`，硬 cap `53221163008 B`；含 service 采样口径，但不构成双侧 full 资格 |
| 正式边界 | `COMMON_LAYOUT_EQUIVALENCE_PASS_OFFLINE_DERIVED`；跨 fresh-run physical-row mapping 仍缺，旧 `PAIRING_IDENTITY_UNPROVEN` 不变 |

原始/派生 summary、16 audits、8 pairs、128+128 shards、诊断包及 checker 结果见
[C2c offline index](../../../results/task041_side_balh_component_audit/c2c_validation_20260916_5b57375d/c2c_offline_review_index.json)
（SHA `db0f4a1d247f6a75002981db927241d162375a82b425f9c0fe9acce2e3940aca`）。当前源码
修复已提交为 `caeb678225d63f16bd95272ba60b08b16caf36af`；C2c checker 绑定的运行源码为
`5b57375d50c777abb5d0096db843095683f49b5f`。唯一 V2 ledger 当前
`17762.27669256989 s`，shared remaining `3837.723307430111 s`，SHA
`e5803851257eabd643be7048e81fae2c8d5e9957c4309c7f433b75ddd3805e27`；C2c 追加
`7.820470533 s`，本次文档 JSON/diff 检查另追加 `0.066910437 s`，没有重复收费。

旧 S1f 双侧 `53331742720 B > 53221163008 B` 的 `process_tree_rss_limit` 受控停止、旧
H3 `RESOURCE_COMPARISON_INCONCLUSIVE`、旧跨运行编号缺口和所有事故证据均单独保留。
这次不启动新的 service/MPI/PDE；full Schur/outer/recovery/official RTA、13.5 nm、
QEP 和额外 optimized run 仍为 `not_run`。

## V4-A0 历史：启动前邻 heavy Gate（2026-09-16，保留）

以下是 A0 当时的历史快照，不覆盖上方已完成 C2 的最新状态：宿主上另一 worktree 的 Full3D
`original_2nm_si_p6h1p5_native.dat/full3d_iterative` 仍在运行。本阶段没有启动 Task041
测试、MPI、PDE 或 service；V4 C1 尚未实现，C2/C3 及 16 项主响应均 `not_run`，因此没有
本轮 RSS、提速或 response 等价数据。

| V4 项目 | 状态/边界 |
|---|---|
| 主响应 | `0/16`；8 对 `0/8`；`not_run` |
| layout、P、PH、PC、response 等价 | `not_run` |
| 新运行 | `scope.new_runs=false`（仅 V4 文档/启动前阶段；历史 R2 baseline 与唯一 R2g 已运行） |
| 历史正式配对 | `PAIRING_IDENTITY_UNPROVEN`，保留旧 R2/R2g 结果，不因本轮阻塞改写 |
| 双侧资源历史 | S1f `53331742720 B > 53221163008 B`，独立的 `process_tree_rss_limit` 受控停止 |
| 现场证据 | [V4-A0 host snapshot](../../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/active_heavy_protection.json)；SHA256 `8b3b1ce344bfcb66ad313db6fd714f01fda53375cbb6509432577b39541ff98d` |

完整状态与固定八项见 [V4 common-layout compact](records/task041_common_layout_equivalence_v4.json) 和
[V4 说明](common_layout_equivalence_v4.md)。本轮不填 runroot，不把旧分侧峰值或旧 apply wall
冒充 V4 测量；旧 H3 的 `RESOURCE_COMPARISON_INCONCLUSIVE` 继续单列。最终两项文档静态
命令 exit `0`、父侧 `CLOCK_MONOTONIC` wall `0.063355920 s`，账本一次追加后为
`11145.889606652894 s`，shared remaining `10454.110393347106 s`，ledger SHA256
`1473ad466c95a05bf4f4c186864d03f3304f58b904873a9ae6ecca08a7535953`；四次此前遗漏的失败
按 `tool_reported_command_duration` 补记 `0.180794456 s`，原始记录见
[`v4a0_final_json_diff_check.json`](../../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/v4a0_final_json_diff_check.json)。

## S5a：S1f fixed-eight baseline 的资源受控停止（2026-09-15）

本轮唯一新增 heavy 是未优化的固定 8 RHS baseline；它在第一条代表性 RHS 之前的
`top_factor_setup_begin` 阶段触发 simultaneous process-tree RSS cap，实际 `0/8`，
因此没有新的数值、物理、等价性或提速结果。状态是
`controlled_negative_resource_stop`，原因是 `process_tree_rss_limit`。本轮 shared
S0/S1/S3 的 21600 秒（6 小时）预算未触发；`RESOURCE_COMPARISON_INCONCLUSIVE` 仅
属于旧 H3 BAL_H 的完整资源比较缺口。这不是数值失败，也不能因为 host 余量充足而提高
cap；严格 cap 为 `53221163008 B`，外层峰为 `53331742720 B`，超出 `110579712 B`。

| S5a 项目 | 实际值/边界 |
|---|---|
| source / model / profile | `1c1d36b168bfb3939314ee2faf5b943cca804382` / `task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8` / `task041_schur_speed_v2` |
| scope | `representative_rhs`；固定 RHS `0/8`；full Schur、outer、recovery、official RTA `not_run` |
| outer wall | `2221.4903851540294 s`；service unit elapsed `2223.491907262 s`；两者不相加 |
| RSS authority | outer raw peak `53331742720 B`，cap `53221163008 B`，delta `110579712 B`；line 7349，PID sum 一致 |
| warning | line 7313，elapsed `2210.5727085701656 s`，RSS `47914586112 B` |
| sparse PSS/USS | `40538401792/40140140544 B`；74 complete、7276 missing；不是同刻度 RSS 替代 |
| swap / reserve | job swap `0`；global baseline `8192 B`，新增 used/pswpin/pswpout delta `0`；reserve 未触发 |
| lifecycle | outer return `-15`/`process_tree_rss_limit`；parent pre-exit members 不清空；finalizer `service_boundary_failure`、systemd exit status3；最终 cgroup 清空但不称自然成功 |
| evidence | [S5a report](schur_speed_v2.md)；[S0/S1 compact](records/task041_schur_speed_v2.json)；ignored compact=`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/s5a_completion_evidence.json`，SHA=`5bae6062f6ad91abf3f4dfd91e21b9ed66c90b4e8c3e8a2a1e0df3d687330c3c` |

完整 raw memory、markers、parent/finalizer、journal 和 public-only 段仍保留在 compact 指向的
ignored root；public `run_summary` 为 `launching/exit_status=null`，本次外层终态不从它推断。
此前 H2/H3 数值比较 PASS、H3 资源不完整、H3g 事故和所有旧负结果均保持不变。

## H4 当前 Task041 BAL_H 终态（2026-09-14）

BAL_H 用每侧一个准确 p4 粗因子和迭代平衡响应替代完整 p6 侧区精确因子；全局 Maxwell 方程、全局 action/RHS 和正式 recovery 定义不变。它是降低因子驻留内存的研究候选，代价是重复侧区求解和更长 wall，仍为显式 `research_only_approximate_candidate`，没有提升为 production default。

| 项目 | 结果 |
|---|---|
| 最终审查分类 | `RESOURCE_COMPARISON_INCONCLUSIVE` |
| 数值/物理 | H2 13.5 nm exact/BAL_H 与 H3 5 nm exact/BAL_H 均通过冻结比较；H3 candidate worker own gates 通过 |
| H3 comparator 原始分类 | `TASK041_SIDE_BALH_NUMERICAL_OR_RESOURCE_FAIL`，exit1；`numerical_pass=true`、`comparison_contract_pass=true`、consumer resource false |
| H3 exact | p6/h4/M480/MPI8，consumer wall `1868.4593736410607 s`，完整 public-tree RSS/PSS/USS `89123696640/87368944640/87121264640 B` |
| H3 BAL_H | p6/h4/M480/MPI8，worker wall `191662.819902868 s`；Schur `183016.74211002886 s`、outer `5486.829851052957 s`；public parent/最终 summary 缺失，资源/正常退出未资格化 |
| H2 consumer 描述 | BAL_H RSS 比 exact 低 `254894080 B`（`2.707606%`），但 consumer wall 约慢 `7.68x`；不裁决跨模型可信节省 |
| 未运行 | `full3d_secondary`、H3/H4 的 5 nm 新 producer/QEP、全仓 pytest、CI；不启动更短波长 |
| 核心证据 | [H4 中心报告](side_balh_transfer_v1.md)、[compact record](records/task041_side_balh_transfer_v1.json)、[H3 completion audit](../../../results/task041_side_balh_component_audit/h3h_final_20260914_51694bbc/h3_completion_audit.json) |

H3 candidate 的完整数值比较仍为 PASS；整体 false 仅表示 public supervisor/资源证据不完整。H3g 的 terminal sampler 最后一行 gate false、实际九组 TERM 与 rank0 组 KILL、`notLoaded` 通知失败和 parent 丢失均保留，不改写成正常 MPI 退出或全流程资源通过。

H3 candidate 的 public memory 段是无 `record_type` 的 synthetic label：226484 行（preflight 1 + consumer 226483），RSS 峰 `53221163008 B`，同时可读 PSS/USS 峰 `50485623808/50090246144 B`（2287 行可读、224196 行缺测），min MemAvailable=`2023682953216 B`。job swap 为 `0`，global used 的既有 baseline 为 `8192 B`，used/pswpin/pswpout delta 为 `0`；这些只是该段观测，不能升级为完整 consumer 峰。

账本当前 `203701.83937335422 s` 仅是显式 measured records 的覆盖和；初始 `6000 s` 是 derived conservative allowance，不是数学上界，不能写成整批完整实测耗时。三段 orphan 记录均来自同一个 hash-bound 文件，按 `record_type` 为 `822/6284/442921`，不是三个独立 raw 文件。

## 历史 3 nm 总结判定

| 字段 | 最终值 |
|---|---|
| final classification | 3NM_COMPLETED_NOT_GRID_CONVERGED |
| 说明性停止状态 | CONTROLLED_STOP_AT_3NM_PHYSICS_GATE |
| merge approval | NO |
| 范围 | 3 nm p6/h3 M800、M1200；5 nm inherited/local MPI8/MPI1 evidence |
| authoritative result | M800/M1200 均 candidate physics negative；official RTA/canonical/grid withheld |

solve/recovery mechanics pass 不等于 own physics pass。以下表格保留每个
独立 evidence/run 的身份、资源 authority 和失败边界；NA 是对应 raw record
没有可可靠提取的字段，不是猜测的零值。

## 正式模型与证据表

| status | 完整 source SHA | input / physical / resolved SHA | active rows | external keys | M delivered | iterations / restart / KSP | 五 true residual（reported/global/bottom/modal/top） | R / T / A / A_volume | grid / M comparison | producer / consumer / workflow RSS/PSS/USS（authority） | wall | swap | factor inventory | classification | 完整 evidence path |
|---|---|---|---:|---:|---|---|---|---|---|---|---|---:|---|---|---|
| failed fresh attempt | 48f56ad46c49519de363b90695d1ed219236c662 | 5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782 | 268272 | 1748 | 800/800（producer packet） | NA（consumer formal fields null） | 7.246419845266236e-10 / 6.711767430501667e-10 / 6.842952026951734e-12 / 7.252171978674087e-11 / 6.339676899706935e-10（diagnostic marker only） | NA（consumer formal fields null） | NA；diagnostic only，不能作 M comparison | producer 16.784275055/15.785678864/15.674812317；consumer/workflow 255.465618134/253.694432259/253.435222626（workflow process-tree summary） | producer 18000.658898；consumer 22215.056788；workflow 40216.175178 s | 0 | bottom/top corrected NNZ 3.259e9/3.716e9；MUMPS factor-only；ICNTL14=40；global direct/coarse/OOC=0 | IMPLEMENTATION_FAILURE at consumer_exit(solution_snapshot_destroyed)；diagnostic marker only | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260907T111441.388055Z |
| candidate retry complete | 2dbe7ff76d734c7689740a656ba7c0fdb5ceadcb | 5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782 | 268272 | 1748 | 800/800（旧 packet 复用） | 1 / 10 / right GMRES | 1.0614289127347946e-09 / 1.3530838051427825e-09 / 9.525482983090863e-12 / 5.059125745287973e-11 / 1.278144562727163e-9 | 0.8048686830648746 / 0.0002839834330554354 / 0.19484733350206998 / 0.19486649353451532 | M800；无合法 M pair，physics negative | producer NA（consumer-only）；consumer 213.299564362/NA/NA；workflow 213.299564362/NA/NA GiB（raw cgroup/process diagnostic；direct PSS/USS NA） | producer NA；consumer/workflow 17047.323762 s | 0 | bottom/top corrected NNZ 3.304e9/2.861e9；MUMPS factor-only；ICNTL14=40；global direct/coarse/OOC=0 | TASK041_CONSUMER_NUMERICAL_FAILURE；measured_candidate_physics_negative；official withheld | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260908T001027.090767Z/consumer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260908T001027.090767Z/numerical_output/v3_7_hybrid_authority.json |
| linked candidate stages complete | producer c3a5bf4a424405c1f1de5cd6ac96be8db576f7b3；consumer c72b3e0d1540a5a891f5906fb0d75dc9146fefd2 | dab4209d2094d8640deaa61d5b6948a37d50362dc6b304762f93feff515b45c0 / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 077624826a392f1ed83e11d3c55bd462ae631a6c2ddcb01e2e2d1daa080d62e0 | 268272 | 1748 | producer 1200/1200；consumer 1200/1200（packet reuse） | 1 / 10 / right GMRES | 5.733598076322987e-10 / 5.650904282024035e-10 / 2.5112691971837548e-11 / 6.142421244928043e-11 / 5.337481450973294e-10 | 0.8048682104336213 / 0.000285259036006279 / 0.19484653053037237 / 0.19486523527614544 | M800→M1200 scalar diff R/T/A/A_volume = 4.726312532454813e-7 / 1.275602950843622e-6 / 8.029716976054591e-7 / 1.2582583698850236e-6；仍无合法 convergence pair | producer 28.318450928/27.452210427/27.341518402（parent telemetry diagnostic）；consumer 250.271244049/248.480698/248.221230（process-tree/control telemetry）；workflow同不重叠 max，不相加 | producer compute 15386.145391；consumer 15750.067281；workflow NA（linked sum 31136.212672 s，非 uninterrupted） | 0 | consumer bottom/top 3.646e9/3.135e9；MUMPS factor-only；ICNTL14=40；modal rank2400、batch32、75/side；producer为QEP packet phase | TASK041_CONSUMER_NUMERICAL_FAILURE + outer bookkeeping_failure；不是 uninterrupted supervisor PASS；measured_candidate_physics_negative | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260908T083844.269710Z/producer/producer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260908T083844.269710Z/producer/selected_mode_packet/manifest.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry/consumer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry/numerical_output/v3_7_hybrid_authority.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry.control/phase_failure.json |
| inherited reference complete | 9e31ecf189081afcb8ca27b0374ec89af0094e2d | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 / NA（tracked record无 physical hash） / NA（tracked record无 resolved hash） | NA（record） | NA（record） | NA（record） | 1 / 10 / GMRES（record） | 3.506501655137575e-10 / 2.8691974587254726e-10 / 1.7320410009968165e-11 / 5.776295396906669e-11 / 2.6600353255738315e-10 | NA（tracked record） | NA；Task039 inherited，不作为 Task041 M comparison | producer NA；consumer NA；workflow 80.0258560180664/NA/NA GiB（tracked process-tree peak） | producer/consumer NA；workflow 10126.231902 s | 0 | NA（tracked record未提供 factor inventory） | Task039 inherited full numerical/recovery/physics pass；不等于 Task041 MPI1 equivalence | /home/fenics/Projects/MyFEniCS/benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json |
| local reproduction complete | def547cfd139b6377b0cae2ba1736ec3591814b0 | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 / 8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c / d6f9de274db352e7b11eafed6867e6535edb7872af3547fa7fd958d02997798 | 132300 | 600 | 480/480 | 1 / 10 / GMRES | 2.754064024849399e-10 / 2.333030625515312e-10 / 3.75139448357935e-11 / 1.7973588584102126e-11 / 2.164825043210854e-10 | 0.7331842733894981 / 0.00022009869572663576 / 0.26659562791477526 / 0.2665962726231523 | NA；独立 5 nm MPI8 reproduction，不与 inherited 合并 | producer/consumer/workflow RSS/PSS/USS=NA/NA/NA；仅有 workflow peak 80.2187461853 GiB（compact authority unspecified） | producer/consumer NA；workflow 8357.347033 s | 0 | MUMPS factor-only；corrected factor NNZ=NA | Task041 local MPI8 solve/recovery/physics pass；不证明 MPI1 equivalence | /home/fenics/Projects/MyFEniCS/results/task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf |
| final MPI1 inner complete, outer unqualified | d6c71401a7105d2c67e22596e40461354cfda21f | 5a6a87882828ae768c92d4f14b45dbcb5f90c0bf141b982b106e52dba2b4c5c0 / 65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4 / 536d0ccb93f6c7bf00c42a12f60ea58bfe44436725da7070af2230fad305dc73 | 132300 | 600 | 480/480 | 1 / 90 / FGMRES | 1.9141387966716752e-10 / 1.914124454116583e-10 / 8.551881036770462e-12 / 1.489643628946544e-11 / 1.7761587180860387e-10 | 0.7331842733878213 / 0.0002200986957195755 / 0.2665956279164591 / 0.266596272621591 | NA；external key identity mismatch prevents equivalence | producer 2.46059799194/2.42841053/2.41315460；consumer 43.2886276245/43.2520036697/43.2368469238；workflow max=43.2886276245/43.2520036697/43.2368469238 GiB（raw telemetry diagnostic） | producer 12285.1455821；consumer 37058.1461057；workflow 49346.574875 s | 0 | MUMPS factor-only；corrected NNZ=NA（compact evidence未提供） | inner solve/recovery/physics/candidate RTA pass；external_key_binding_pass=false；outer task041_resource_sample_failure | /home/fenics/Projects/MyFEniCS/results/task041_5nm_exact_side_hybrid_iterative_p6h4_m480/task041_5nm_p6h4_m480_mpi1__hybrid_iterative__mpi1__M480/20260904T152109.607989Z |

M1200 producer packet 的 manifest SHA 为 c7a36ab977e5fc11505ad27a6e8044fc9e909b42fd37a8ea1abeb72b6e49d71b，canonical identity SHA 为 cef2de437f0b0a247791acc8e4b865d1fd51082b181617ab6621cb9a95ba5d00，packet directory bytes=1370082162，32 shards，write max-rank=1.167526111 s。M1200 producer 与 consumer 是 hash-bound linked evidence，不是 uninterrupted supervisor PASS。

## 最终分类合同

task.md 的最终枚举中，本次唯一适用的是 3NM_COMPLETED_NOT_GRID_CONVERGED。
5nm 的三个枚举均不能诚实采用：

1. 不是 5NM_MPI1_EQUIVALENCE_PASS，因为 external identity binding 和 outer
   resource authority 尚未闭合；
2. 不是 5NM_MPI1_OWN_PASS_REFERENCE_ARRAYS_PARTIAL，因为该条件要求的
   reference identity/authority 仍不完整；
3. 不是 5NM_MPI1_NUMERICAL_OR_PHYSICS_FAIL，因为 final MPI1 inner
   solve/recovery/physics 并未失败。

因此另以 evidence boundary 记录 EQUIVALENCE_NOT_ESTABLISHED，而不伪造
task.md 枚举。CONTROLLED_STOP_AT_3NM_PHYSICS_GATE 只是说明性状态，不是
task.md 的替代枚举。

## M 与未运行项

M800 与 M1200 的 energy failure 分别为
abs(A_balance-A_volume)=1.9160032445286745e-5 和
1.8704745773062692e-5，均大于 1e-5。虽然 scalar absolute difference
较小，但两个 M 都没有 own pass，故不存在合法 convergence pair。

| item | result | final reason |
|---|---|---|
| 3 nm p6/h3 M1600 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE；no valid own-pass M pair，task.md §12.2 true Gate |
| 3 nm h2.5/h2 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |
| all 2 nm | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |
| post-gate MPI1 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |

M1200 是用户后来明确授权的 controlled continuation，不能用上述 reason
暗示它未运行。最细已完成对象是 3 nm p6/h3 M1200 candidate；它未
accuracy-qualify，minimum qualified M 和 accuracy-qualified frontier 均为 NA。

## 资源语义

用户后续指定的本次运行合同为 workflow warning/hard=224/256 GiB、
hard=274877906944 B、envelope=39600 s、swap0；producer=176/192 GiB、
18000 s；consumer=224/256 GiB、21600 s。shortwave timeout 按 phase
elapsed，producer 完全退出后才启动 consumer；workflow peak=max，不相加。
MemAvailable floor=1869169767220 B。该合同不改写 task.md 原 1.50 TiB
规划历史。

## 2026-09-16：Task041 V3 执行结果 / Response V4 收口

本轮不是“只有文档”的整轮：R1 完成 sequential component 生命周期入口，R2c 完成
A1 owner-row 批量路径与 A2 复数共轭临时量，随后有 R1/R2d/R2e 轻量测试和两场 R2
分侧八项运行；当前 R4 只整理已关闭证据，未新增计算。分侧流程先建 bottom、完成
四项并释放，再建 top 四项；全局方程、RHS、传播因子和原检查未被删除。

| run | source | fixed-eight apply（bottom / top / total） | full service wall | full-tree RSS peak | own result |
|---|---|---:|---:|---:|---|
| R2 baseline | `3ee452ac0adc0c3c88b9610b6446e93a3c02444a` | `790.5143905449659 / 889.7605694371741 / 1680.27495998214 s` | `4015.539370124 s` | `51975606272 B` | bottom/top 各4；reason=2，explicit residual `<=0.01` |
| R2g 唯一 optimized | `376a6c2e6ff1d13b8c4f182dd97e5ee2629f85ab` | `592.4704610940535 / 666.3774437108077 / 1258.8479048048612 s` | `3630.563676387 s` | `51796770816 B` | bottom/top 各4；reason=2，explicit residual `<=0.01` |

组件 apply 比为 `0.7491916113647505`，观测减少 `25.0808388635%`；full-service wall
减少 `9.587147784%`。优化峰低 `178835456 B = 170.55078125 MiB`，但不是双侧
内存不增资格；baseline/optimized margin 为 `1245556736/1424392192 B`，硬 cap
仍为 `53221163008 B`。PSS/USS 是稀疏诊断，不替代 RSS；两次 job swap、global 新增
swap 和 pswp 增量均为 `0`，global used 的既有 baseline 为 `8192 B`。

构造 marker 已按两份 consumer raw `markers.jsonl` 的 `(side,event)` 配对：全局
`system_ready` worker wall 为 baseline/optimized `983.0788940798957/1039.0930612850934`；
side `before_build→after_admission` 是侧构造/准入而非全局 setup；factor setup
begin→ready 为 bottom `983.5931301249657→1653.4143726038747`、
`1039.5970036741346→1696.573750832118`，top `2450.2057411340065→3114.250514271902`、
`2293.303577498067→2954.8940188910346`。完整 line/hash 和 outer-origin 对齐见
[setup/recovery](setup_recovery_v3.md) 与 [compact](records/task041_setup_recovery_v3.json)。

两次运行各保留 8 个 response manifest 和 64 个 owned rank shard，每次 shard 总计
`33901312 B`；lifecycle `created_total=2`、simultaneously-live peak=1、每侧释放后
p4/KSP=0。跨 fresh run 的 `132300` 凝聚行缺稳定几何/拓扑/方向/MPC active-row key，
正式状态固定为 `PAIRING_IDENTITY_UNPROVEN`；约 `sqrt(2)` 的按位置差只是未验证编号
诊断，不是 numerical failure 或 pass。

两次 `consumer_summary` 的 physical logical identity 为
`65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4`，resolved logical
identity 为 `95a155334dacf75d30c005338ff689fd676532b49ae392e6fad868d0eee23e51`；两份
public root 均实际保存 `resolved_config.json`，compact 分开记录逻辑字段与文件 SHA。

旧 S1f `53331742720 B > 53221163008 B` 的 `process_tree_rss_limit` 受控停止、旧 H3
`RESOURCE_COMPARISON_INCONCLUSIVE` 以及旧事故均继续保留。新 13.5 nm、完整 5 nm
双侧、full Schur/outer/recovery/official RTA、producer 和新 QEP 均 `not_run`；
`qep_calls=0` 是无新 QEP 调用事实，不等同于完整输出已产生。分侧配对的第二场（唯一
optimized R2g）已完成；整轮实际只有 baseline 一场和这一场 optimized，额外/重复
optimized run `not_run`。预算尚余不等于准入。

R1/R2c 的实现与测试事实、旧负结果和本轮证据入口见 [Response V4](../response_v4.md)、
[setup/recovery](setup_recovery_v3.md)、[compact](records/task041_setup_recovery_v3.json)
和 [test summary](test_summary.md)。ordinary/default 不变；merge 仍按 production
numerical/core、reusable runner/watchdog、checker/benchmark、compact evidence/docs、
research-only、do-not-merge 依赖组说明，负结果文档/compact 保留，临时 orphan sampler、
大型 raw 和未资格化 production promotion 不合入。

<!-- r4b-final-metadata -->
最终 compact：[task041_setup_recovery_v3.json](records/task041_setup_recovery_v3.json)，153382 B，SHA256 `7f5d84e6a2a9a6809d9438bbb6e9444a4ffead9d6272728b394d3346401852df`；R4b 仅完成文档检查，未新增计算。

## 2026-09-18：BAL-H 几何谓词修复与 D1e 准备（Response V6）

旧 D1d 在 top side 几何构造阶段因绝对坐标差的浮点抵消误判 affine，触发 `BAL_H requires affine geometry`；该失败不是 solver、内存、swap 或 MPI 失败。修复提交 `8ad30732a2753b902f5722c6e7c7647365ab0744` 已推送：两条几何使用路径均先减首节点坐标再 contraction，保留 `128*eps*scale` 与有限正 determinant 门。

修复后的 native serial targeted test 为 3 passed，MPI2 为每 rank 3 passed；Ruff check、compileall、diff check 通过，format check 未通过且本轮未扩大 format-only 改动。源码/测试身份和重建复现脚本均记录在 D1e evidence index；旧 D1d 记录保留且不宣称 solver pass。D1e 继续使用 fresh QEP、2nm/p6/h1.5/M1200/MPI8/CPU1--8/math threads1、旧 D1c ledger continuity 和新的实测内存/swap 门。

截至该版，D1e 未 dispatch，fresh QEP 未启动；文档提交后需以最终 source SHA 更新配置、重新做一次 fresh preflight，再按条件批准的精确 argv 单次启动。CPU23 邻项目的真实 worker `402163`/父 `402153` 仅允许在 CPU23、`VmSwap=0`，属于受保护独立作业。
