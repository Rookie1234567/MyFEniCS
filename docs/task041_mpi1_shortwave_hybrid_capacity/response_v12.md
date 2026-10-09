# Task041 Response V12：Review V10-r2现场进度

## 2026-10-09：W0.7 identity-sharing warm场终态、转录更正与top预算审计（Invocation a598ab0a491649eda4060eef6a102b56）

本节是新一场独立warm consumer的终态记录。模型为W0.7缩减pilot：10×5 nm、接口z=2/22 nm、p6/h0.70、M400、MPI8，matched传播L=20 nm、N=29、h=20/29 nm，fixed-H6；复用已有producer packet，本Invocation没有重跑QEP。把同一内部单位矩阵在多个局部几何类之间改为只读共享，目的是减少重复数组；这不改变方程、因子或RTA计算。

| 项目 | 本场记录 | 口径 |
|---|---|---|
| 身份 | source HEAD `6e072bd640b5c140ba64745c350ddf9916a566dc`；Invocation `a598ab0a491649eda4060eef6a102b56`；unit `task041-v10r2-w0p7-identity-sharing-numeric-cleanup-warm-cpu10-11-14-15-16-17-18-19-20261008T233316Z.service` | 唯一dispatch；rank map `[10,11,14,15,16,17,18,19]`；MPI8；QEP=0 |
| 封套 | config SHA `d53a8b8cf0d7845f4e7a776c2e968fbf569686ccaf4b3a7646eb163129aff107`；systemd argv SHA `53f3b753de63857d72d525f318e96ea6b82f75e82ac7e3308e0cca9fcafda117` | 与已核执行包绑定 |
| 固定资源政策 | cap/warning/W/node0 floor = `53,221,163,008 / 47,899,046,707 / 5,322,116,301 / 412,316,860,416 B` | swap仅观察；W是政策预留，不是MUMPS误差界 |
| 终态 | consumer `IMPLEMENTATION_FAILURE`；public rc=3、`task041_public_command_nonzero`；finalizer `failed/service_boundary_failure`；`controlled_stop.active=false` | finalizer 8/10；只有`public_result_completed`和`service_terminal_normal`为false；不是controlled stop，也不是数值方法失败结论 |
| 唯一账目 | service wall `1860.62936514 s`；V5 ledger `186`项，SHA `d344166517fbbaa6f66c29a9687828f5e74c78b6dcba303c142c47e7f99477dd`；runroot匹配唯一一项 | ledger row无Invocation字段；由launch/finalizer与runroot绑定，不说row本身保存Invocation |

| 阶段/对象 | 实测或派生结果 | 判定 |
|---|---|---|
| one-cell | source矩阵`15,120×15,120`、八rank NNZ一次求和`7,123,680`；numeric完成后销毁 | 不是失败点 |
| bottom P4 | `64,966×64,966`、NNZ `27,929,686`；analysis INFOG(16/17)=`2,879/18,865`百万十进制字节 | symbolic与numeric均完成；bottom实际INFOG(18/19)=`2,879/18,865`百万字节 |
| bottom numeric gate | cleanup前B `29,373,919,232`；cleanup后fresh B `28,704,886,784`；加单份INFOG(17) `18,865,000,000`与W后为`52,891,003,085 B` | 低于cap `330,159,923 B`，门通过；bottom因子之后仍live |
| top P4 | `64,966×64,966`、NNZ `39,242,250`；post-symbolic记录ICNTL(7)=0、ICNTL(28)=1；INFOG(17)=`19,299`百万字节 | top symbolic完成；INFOG(17)是分析阶段的MUMPS内部数据估计，不是RSS上界 |
| top numeric gate | cleanup前B `47,043,870,720`，cleanup后fresh B `45,211,955,200`；加单份INFOG(17) `19,299,000,000`与W后为`69,833,071,501 B` | 超cap `16,611,908,493 B`；top numeric未调用，top INFOG(18/19)=not_run。按同一公式，fresh B须≤`28,600,046,707 B` |
| 清理与求解范围 | top pending factor destroy一次；bottom numeric factor在最终cleanup销毁。没有fixed-H6反馈、outer、五真残差、recovery、physics或official结果 | 失败发生在top numeric之前的预算拒绝；整场无数值资格 |

### P6/P4标量审计更正

前一条执行消息把P4 identity-projection payload误记为P6。现在按consumer markers原字段作派生更正；旧通知、raw与ledger均保留未改。`wall_seconds`是consumer运行内marker时刻，不是该构造的独立耗时。

| 原始marker字段 | nᵢ / rank-sum class数 | identity共享减少的数组payload | retained P6 Schur payload |
|---|---:|---:|---:|
| P6 bottom，wall `1572.1085634171031`，`detail.object_inventory.p6_assembly_time_condensation_build_audit` | `450 / 475` | `756,540,000 B` | `1,418,342,400 B` |
| P6 top，wall `1690.8518208200112`，同字段 | `450 / 423` | `672,300,000 B` | `1,263,071,232 B` |
| P4 bottom，wall `1585.9632914850954`，`detail.object_inventory.identity_projection_*` | `108 / 475` | `43,576,704 B` | 不适用 |
| P4 top，wall `1704.0842770701274`，同字段 | `108 / 423` | `38,724,480 B` | 不适用 |

P6两侧identity payload合计`1,428,840,000 B`；P4独立合计`82,301,184 B`。它们是跨rank求和的暴露数组字节，表示已经避免了旧式重复identity数组，不是RSS下降。当前compact transfer的rank-sum unique array payload为bottom `145,735,392 B`、top `131,566,816 B`，也不等于RSS节省。

### top门的存活对象与预算限制

P6 raw显示bottom/top分别475/423个rank-sum class实例，nᵢ=450、trace维度432。由源码数组形状和complex128推得两侧可见payload：LU主数组`2,909,520,000 B`，`interior_from_trace`与`trace_from_interior_rhs`各`2,793,139,200 B`，加上markers实测的retained Schur `2,681,413,632 B`，合计`11,177,212,032 B`。前三项按形状和class数派生；合计不包括pivot、Python/native分配器开销，也不代表RSS。该payload数值比top筛查缺口小`5,434,696,461 B`，但数组payload不是RSS减量或可回收量上界；这些数组仍被P6动作、P4右端处理/求解与恢复使用，不能据此证明可释放量足够或不足。

P4 markers的`detail.port_audit.cells_with_port_terms`在`detail.resource_scope=rank_local`下记录bottom 0、top 15；源码中的计数遍历本rank的`cell_recovery_maps`，它们按本rank owned cells构造，因此该数是写出marker的rank局部owned-cell循环计数，不是两侧全局cell总数。本run未保存全rank计数、各rank Bi/Di/xiB数组字节、ghost与缓存别名/重复总量；全局总量unknown。历史算式`720×108×646×16=803,727,360 B`仅是一侧在假设720个owned cells及每cell尺寸为108×646个complex128值时的条件式尺寸示例，不是实测或全局上界，也不能代表两侧总量。源码中Bi在`P4CellCondensedInverse`构造时用于预热xiB；Di参与每次右端处理，xiB用于局部恢复。xiB预热后释放Bi-only buffers可作为最窄候选，但当前没有足量可释放证据；该条件式示例不能作为排除完整全局节省的证明。

top fresh B采样时bottom numeric因子仍存活，其驻留贡献已计入该次B，因此不另加bottom INFOG(19)；INFOG(19)是MUMPS内部allocated-data统计，不与RSS一一对应。MUMPS 5.6.2手册将INFOG(16/17)定义为分析后对in-core full-rank数值阶段全部MUMPS内部数据的估计（max/sum，百万十进制字节）；INFOG(18/19)是数值因子完成后已分配的MUMPS内部数据（max/sum），用户WK_USER除外。bottom INFOG(19)=18,865百万字节；top尚无INFOG(18/19)。手册和raw没有把top symbolic已占字节从INFOG(17)中拆开，所以不能从top估计中扣除符号阶段内存。现有数据尚未确认足量可安全释放的对象；P6数组仍在使用，Bi条件式单侧尺寸示例不代表全局上界。

**保留的证据与来源：**当前runroot `results/task041_w0p7_identity_sharing_warm_run_20261008T233316Z`；consumer markers SHA `e5f4644f9ad70fbbd2f785f317b3e3773fd6aacb11dc57348d910e449ede1bd4`，factor inventory SHA `3284fe583c56e51effe76191d3f424a9d3528711ac5c1135693480c0d1112084`，consumer summary SHA `16830a9f2c4905245e9742610166db90485c5bb04a9430a76cbe2e6d9651c980`，service summary SHA `1b8d4a573de76cf9f19bf23dcaa908a126971973f29b3e6bca3b85f990ac60c2`，finalizer SHA `92e4aa4fbb7b19587b7544ff273f5dd66c3f58c77a910588a6b75837929ca847`。MUMPS手册文字见`results/task041_petsc_lu_stage_bridge_retry_20261008T000705Z/mumps_5.6.2_reference/userguide_5.6.2.txt`，原包SHA `13a2c1aff2bd1aa92fe84b7b35d88f43434019963ca09ef7e8c90821a8f1d59a`，PDF SHA `32acdd3e09fb69f9fab16c94ae67768d15c61ac9c27abf66eb1e0e6ecd904050`。新增ignored terminal compact：[terminal compact](../../results/task041_w0p7_identity_sharing_warm_run_20261008T233316Z/terminal_compact_20261009.json)，SHA `bead944a1d4bd4f5f35097c8bf8cb43ee9478c0721f663e722634896a17235b3`。

#### 当前阶段决定

本场不是W0.7 reduced数值通过，也不资格化50×25 nm、2 TB或48 h。没有足量且已证实可在top numeric前释放的对象，故不建议原样重建试运行。若主控继续考虑代码，最窄候选是xiB预热后的Bi-only生命周期缩短，但先补本run逐rank Bi/Di/xiB nbytes以及保持P4 solve/recovery结果的定向证据；即使该项上界也不足以解除当前top门。更大范围需先明确P6 class-cache重算与MUMPS分配重叠的证据，不能靠预测节省启动。

## 历史快照：W0.7 compact-transfer warm场终态（Invocation a6a67fc93a1d45cfa69cce0469cb0672）

本场是W0.7缩减pilot：10×5 nm，Hybrid接口z=2/22 nm，p6/h0.70、M400、MPI8，matched全段L=20 nm/N=29/h=20/29 nm，fixed-H6，P4目标5e-13且最多2次同因子修正。复用既有合格producer packet，本Invocation的QEP=0。compact orientation把每个方向重复保存的整幅插值矩阵改为共享canonical矩阵并保存方向实体块；它减少了数组payload，但payload不是RSS，也不能单独解释跨场RSS变化。

| 身份/资源 | 实际记录 | 说明 |
|---|---|---|
| Invocation与unit | Invocation a6a67fc93a1d45cfa69cce0469cb0672；unit task041-v10r2-w0p7-compact-transfer-numeric-cleanup-warm-cpu10-11-14-15-16-17-18-19-20261008T142600Z.service；MainPID 3255582 | 唯一dispatch；runroot为 results/task041_w0p7_compact_transfer_warm_run_20261008T142600Z |
| 运行源码与封套 | source 47b8b655ee9a9cc72dc1f89928b770f7061b22ea；config SHA ab0be17b8980c19b8511a05cae5347874afd4da15d36d74416dde3bb470f29ec；argv SHA 3eaaae8eb92d92d0d09e4385e8c1f0a45484dfad9626329c0254e618574314b7；source binding SHA 251cdf04a93629aaadd625e015183921c95d8c279a267183d2137a6b7efc6b94 | MPI8 rank map [10,11,14,15,16,17,18,19]；exact bridge .so SHA 7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b |
| Producer身份 | 复用source 2708214386d38bd69f73e6b196c8ed843bb53d81的既有packet；manifest SHA 63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2；identity SHA 73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6 | 原producer raw保留；本Invocation QEP=0 |
| 数值与资源合同 | cap/warning/floor为53,221,163,008/47,899,046,707/412,316,860,416 B；swap observe-only，无elapsed强停 | 真实ABI、native complex128/Int32、membind0、每rank六线程1通过；performance_not_isolated |

| 阶段/门 | 实际记录 | 结论 |
|---|---|---|
| one-cell | source矩阵15,120×15,120；MPI rank-local NNZ一次求和7,123,680；INFOG(7/32)=4/1，PORD；numeric完成后因子销毁 | marker rows=17,280是端口/输出行口径，不能误写成source矩阵行数 |
| bottom P4 | 64,966×64,966、NNZ 27,929,686；sequential AMD symbolic完成；INFOG(17)=18,004 million decimal bytes | pending factor保留到预算门，numeric未调用 |
| top P4 | 64,966×64,966、NNZ 39,242,250；sequential AMD symbolic完成；INFOG(17)=15,601 million decimal bytes | pending factor保留到预算门，numeric未调用 |
| bottom numeric门 | cleanup前/后authority fresh B=31,398,424,576/30,729,564,160 B（max(process-tree RSS, dedicated cgroup current)）；对应dedicated cgroup current为28,504,768,512/27,921,858,560 B；单份INFOG(17)=18,004,000,000 B；W=5,322,116,301 B；合计54,055,680,461 B | 高于cap 53,221,163,008 B共834,517,453 B，故numeric前预算拒绝。清理实测降低authority 668,860,416 B；不保证下次同量释放 |
| top numeric条件门 | 若沿本次top INFOG(17)与W，fresh B必须不超过32,298,046,707 B | bottom numeric未执行，故bottom之后的top fresh B及INFOG(19)均unknown；不是已通过的后续门 |
| pending清理 | bottom与top各destroy一次，numeric attempts均为0，destroy error=0 | pending handle已清理，不存在同场因子重建或第二dispatch |

## 只读驻留对象审计

下表把内存字段按它代表的内容区分：数组payload是程序可见的数组字节；fresh B是当前整组进程树与专属cgroup的authority；二者不能相加或互相替代。一个rank持有的共享对象只在该rank计一次，跨rank总和按raw已有语义报告，不把记录引用重复加总。

| 对象与证据 | 字节/形状 | 所有者、后续用途和释放边界 |
|---|---|---|
| P6 retained local Schur及同类恢复缓存 | 本场consumer raw未持久化P6 condensed.build_audit、oriented class counts或retained_local_schur_bytes_sum；not_persisted。不能用P4 audit中的retained_local_schur_bytes_sum=0替代 | hybrid_local_dtn_action.py:331-339调用hcurl_assembly_time_condensation.py；该调用启用retain_local_schur_for_matrix_free。hcurl_assembly_time_condensation.py:1436-1473对同一class-key持有Schur、LU、恢复与投影缓存。full action/外层BAL-H仍用局部Schur；HybridLocalDtnActionSystem.destroy沿condensed.destroy释放。当前没有可信P6 unique nbytes，因而无法把它列为可兑现节省 |
| P6 mode-projection/traction暴露数组 | consumer markers的full_action_ready.object_inventory：rank-local payload汇总为bottom 27,128,520 B、top 23,844,560 B，每侧array_count=2,584；native workspace仍unknown | FullSpacePhysicalDtnAction与H6/外层作用会继续使用；side.full_action持有至side inverse/action销毁。marker不提供每数组shape，因此这里只报汇总，不把它当factor或RSS |
| compact orientation transfer | consumer markers的transfer_ready.object_inventory.compact_orientation_storage.cross_rank_total：每侧K_local跨rank求和为766（不是全局唯一键数）；canonical R 33,868,800 B、方向实体块116,949,248 B、索引75,648 B，总unique array payload 150,893,696 B。bottom和top各有自己的adapter；records对同key共享，不重复加总 | P/PH transfer仍供side action使用，安全释放点是对应SideBalancedInverse销毁。它是跨rank payload和对象库存，不是本场测得的RSS节省 |
| P4 CellPortTerms与xiB | consumer markers的p4_condensed_port_ready.port_audit报告bottom cells_with_port_terms=0、top=13；Bi/Di/ports的逐cell shape及MPI逐rank向量没有持久化。基于源码的条件上界：若该记录所指rank的13个cell各取n_i=108、p_i=646，Bi、Di、xiB各自每cell至多1,116,288 B，ports索引至多2,584 B；合计三数组+索引至多43,568,824 B。此为shape上界，不是实测值，也不乘8 | physical_balanced_physical_operator.py:884-1020构造Bi/Di；p4_cell_condensed_inverse.py:514-548在P4CellCondensedInverse构造时另以共享class LU生成独立xiB_by_cell。p4_cell_condensed_inverse.py:1010-1013的回代使用xiB @ port_values，且Bi/Di参与凝聚端口矩阵；bottom/top数值求解与恢复前不能释放。top实际unique bytes和各rank合计仍unknown |
| ModalTraceProjection（modal_trace_projection.py:508-523创建，hybrid_internal_modes.py:2303-2318传入one-cell builder，后续2375-2435构建两侧blocks） | 每rank 400个right和400个left复数trace；按已绑定截面layout每rank 1,813个local+ghost条目及complex128推导为23,206,400 B/rank，MPI8 rank-sum为185,651,200 B；derived payload，不是RSS。稀疏mass矩阵字节未记录 | traces由packet模态向量复制成fem.Function；HybridInternalModeCoupling还持有正/负basis用于后续路径。one-cell builder和bottom/top block构建期间需要projection；src/solvers/hybrid_strong_trace_direct.py:369,398的强迹direct路径也读取它。ModalTraceProjection.destroy只销毁mass，不清空trace tuple。一个窄候选是仅对W0.7 fixed-H6在该调用链最后一次projection用途完成后显式detach trace引用；强迹默认路径必须保留。即使释放已知trace payload，也比本次834,517,453 B门缺口少648,866,253 B，mass与实际可回收RSS未知，单独不足以支持重跑 |
| P4/H6装配临时项 | _prepare_physical_p4_port_terms中的cell_b/cell_d/interior_locations与assemble_port_condensed_terms中的xib、b_hat/d_hat/h_hat为局部暂存；返回后Python引用退出，但allocator是否向OS归还未测 | 顶侧13个端口cell的临时区间位于p4 port assembly；之后已有numeric前cleanup。没有对象级释放样本，不把cleanup前后RSS变化归因于这些临时数组 |
| H6 window/runtime与basis | raw显示window_action在runtime action安装时destroy、seed在构建后离开局部作用域；runtime仍持有约11 MB values、11 MB curls及系数/输出向量等本地buffer；P6 basis底层数组完整nbytes未暴露 | window与seed生命周期已结束，但RSS变化不能归因到这些对象。runtime数组在H6/side action和外层迭代期间仍使用；P6正负basis在恢复前仍由coupling持有 |

可继续审的单一候选是W0.7专属地在projection最后使用后解除其trace引用，而不是同时改Bi、Schur和allocator策略。它的已知trace payload约185.7 MB process-tree rank-sum，小于本次834.5 MB预算拒绝差额；稀疏mass大小、basis/allocator影响及实际RSS下降未知，所以该候选本身不能形成足够的重跑依据。当前证据不支持再次构建：P6 retained Schur准确字节缺失，P4逐rank缓存形状缺失，top numeric后的B/INFOG(19)也未测。任何后续实施需另审窄hunk，并仍按新的fresh资源与分阶段门判断。

本场原始分类不改：consumer IMPLEMENTATION_FAILURE，public task041_public_command_nonzero/rc3，finalizer status=failed、classification=service_boundary_failure，controlled_stop.active=false；finalizer 8/10，false项仅public_result_completed和service_terminal_normal。没有固定H6反馈、outer、五真残差、recovery、physics或official observables，故无pilot数值通过，不资格化50×25 nm、2 TB或48 h。

唯一service-finalizer wall为1,979.603254005 s。V5 ledger共183项，SHA cd4c69f03e89b67350478b6c37655bc03ca77893ef5f6d96959fae32dcaaaa6e；该runroot恰有一条对应记录。ledger entry自身没有Invocation字段，runroot与Invocation的绑定由launch/finalizer证据建立；不称entry直接保存Invocation。原始文件均保留且未重写：summary SHA 5311cfa56d0643e3e91fafb6d33451af7f9c335d39972995ec662a6ac4fac366；service_parent_summary SHA 5037bdfe05ccd90f54a5cb37352ac22cfeecdc7af1465f0dae612c6a7a27e058；finalizer_summary SHA 7c00774e836ce40b322ee3472e6c913706781135cc1552c0ac8bdd40869a55f4；artifact_hashes SHA 26093e1128527828ffa402b205ed0170439d4f6c4ed8fc144381e91ddfacfe09；consumer markers SHA ce821d82fb0eb79e11315d427f856efd78c71e9ae865862a7e037217e0fbeb16；consumer memory stages SHA 2e6d73cabd5b6bc1d80f14190f18bd9d31985ea403c20c40545b8675ada143db；rank NUMA SHA a319c3fd7883d142eb0fc2c1bca594a365a497c2c4dde2609da7bfe72a18c1af。finalizer SHA以原文件重算值为准，前一通知漏掉的末位4在此更正。

原始证据入口：[service summary](../../results/task041_w0p7_compact_transfer_warm_run_20261008T142600Z/summary.json)、[finalizer summary](../../results/task041_w0p7_compact_transfer_warm_run_20261008T142600Z/finalizer/finalizer_summary.json)、[artifact hashes](../../results/task041_w0p7_compact_transfer_warm_run_20261008T142600Z/finalizer/artifact_hashes.json)、[consumer markers](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261008T144717.194059Z/consumer/markers.jsonl)。本轮没有测试、ABI、QEP、FE或第二dispatch。

## 历史快照：W0.7 compact-transfer warm场终态（Invocation c38a11ae711846599601ac3c06286327）

唯一compact-transfer warm Invocation 为 c38a11ae711846599601ac3c06286327，unit 为 task041-v10r2-w0p7-compact-transfer-warm-cpu10-11-14-15-16-17-18-19-20261008T125520Z.service，source HEAD 为 e890c1c12feb90dd4f7695d31402d63ff788d186。本场复用已验证 producer packet，QEP=0；没有第二次dispatch。

compact orientation把各单元方向变换重复存下的稠密矩阵改为共享canonical插值矩阵和每个方向所需的实体块。它减少了可见的数组payload，但数组字节不等于RSS，也不能单独解释整场B变化。此次实际consumer marker SHA为 bb2a466b84bd98216e2120938d9679c90cf2e81ef71f09b97d80db937a6703aa；finalizer SHA为 8c987379232be4ebd2dea1f159118cd99fc4efcd8fe11f2995541c20a9e7e981。

| 阶段/门 | 实际记录 | 结论 |
|---|---|---|
| one-cell | source matrix 15120×15120、NNZ 7,123,680；INFOG(7/32)=4/1，PORD；numeric完成后销毁 | ready marker的rows=17,280是端口/输出行口径，不是source矩阵行数 |
| bottom P4 | 64,966×64,966、NNZ 27,929,686；sequential AMD symbolic完成，INFOG(17)=20,150 million bytes | numeric未调用，factor保持pending至预算拒绝 |
| top P4 | 64,966×64,966、NNZ 39,242,250；sequential AMD symbolic完成，INFOG(17)=15,697 million bytes | numeric未调用；top numeric门未评估 |
| bottom numeric门 | fresh B=30,895,177,728 B；单份INFOG(17)=20,150,000,000 B；W=5,322,116,301 B；合计56,367,294,029 B，对cap 53,221,163,008 B超3,146,131,021 B | before-numeric预算筛查拒绝；这不是实测numeric峰或算法数值失败证明 |
| pending清理 | bottom与top各destroy一次，destroy error=0；两侧numeric attempts均为0 | 同一Invocation无遗留pending因子 |

两侧transfer的对象统计另列，不与RSS混加：bottom K_local合计733、rank-sum payload 133,147,520 B；top K_local合计766、rank-sum payload 150,893,696 B。两者均为canonical R、方向实体块和索引的rank-local对象总量；ghost重复按各rank实际持有统计，不是可回收RSS的实测差值。全run process-tree RSS峰35,009,921,024 B，专属cgroup peak 32,935,227,392 B，口径不同。

| 跨场描述性对照 | 前一场 | 本场 | 差值 |
|---|---:|---:|---:|
| bottom numeric门fresh B | 35,915,554,816 B | 30,895,177,728 B | −5,020,377,088 B |
| bottom INFOG(17) | 19,460,000,000 B | 20,150,000,000 B | +690,000,000 B |
| numeric筛查缺口 | 7,476,508,109 B | 3,146,131,021 B | −4,330,377,088 B |

该表只描述不同Invocation的门读数，不能将B的全部下降归因于compact表示。对当前top的INFOG(17)与同一政策W计算，未来top numeric门要求fresh B不超过32,202,046,707 B；本场没有测得该fresh B，也没有进入top numeric。

最终raw分类保持原值：consumer IMPLEMENTATION_FAILURE；public task041_public_command_nonzero、rc=3；finalizer status=failed、result_classification=service_boundary_failure；controlled_stop.active=false。finalizer为8/10，只有public_result_completed与service_terminal_normal为false，其余清理和账目检查通过。fixed-H6反馈、outer、五项真残差、recovery、physics及official observables均未到达；本缩减pilot没有数值结果，不能资格化50×25 nm目标、2 TB容量或48 h冷启动。

唯一service-finalizer wall为1,956.390568298 s。V5 ledger共181项，本Invocation恰有一条，SHA fc930c8c8c689cf61d08948e4aa768c2bd307bb24e61068a64833bf4f66af7d5；不另计嵌套consumer阶段。原始summary、service、finalizer、consumer markers和ledger均保留，未改写raw。证据入口：[consumer markers](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261008T131610.846014Z/consumer/markers.jsonl)、[service summary](../../results/task041_w0p7_compact_transfer_warm_run_20261008T125520Z/summary.json)、[finalizer summary](../../results/task041_w0p7_compact_transfer_warm_run_20261008T125520Z/finalizer/finalizer_summary.json)。

## 历史：前一场 W0.7 deferred-AMD warm Invocation 3d6b63c763414ad984beb60f1296458e

唯一获准的warm consumer Invocation `3d6b63c763414ad984beb60f1296458e`已结束；没有第二次dispatch。此前组件和warm包准备段落是运行前快照，现由本节终态取代，历史raw及原分类不变。

| 阶段/门 | 实际记录 | 结论 |
|---|---|---|
| one-cell exact factor | source matrix `15120×15120`；MPI8各rank `MatGetInfo.local_nnz_used`一次求和为`7,123,680`；`INFOG(7/32)=4/1`；`public_mumps_control_readback=null`；numeric完成并销毁 | PORD，保留one-cell原排序。ready marker的`rows=17,280`是端口/输出行口径；`interior_rows=15,120`才与source矩阵维数相符，不能把17280写成factor source rows |
| bottom P4 | `64966×64966`、NNZ `27,929,686`；sequential AMD，`INFOG(16/17)=2766/19460` million bytes | symbolic完成；numeric未执行；清理销毁一次、error=0 |
| top P4 | `64966×64966`、NNZ `39,242,250`；sequential AMD，`INFOG(16/17)=4193/19299` million bytes | symbolic完成；numeric未执行；清理销毁一次、error=0 |
| bottom numeric预算门 | fresh `B=35,915,554,816 B`；单份`INFOG(17)=19,460,000,000 B`；政策预留`W=5,322,116,301 B`；合计筛查`60,697,671,117 B`，高于cap `53,221,163,008 B` `7,476,508,109 B` | 在numeric前拒绝。该差额是估算门的筛查缺口，不是实测所需峰，也不是算法数值失败证明 |
| 整场数值/最终化 | 固定H6反馈门、outer、五项真实残差、recovery、physics均未到达；finalizer检查8/10 | 不得登记物理结果或通过；仅`public_result_completed`与`service_terminal_normal`为false，其余清理/账目检查通过 |

原始状态必须保持为consumer `IMPLEMENTATION_FAILURE`、public `task041_public_command_nonzero`/rc `3`、finalizer `failed`/`service_boundary_failure`，且`controlled_stop.active=false`。这不是先前Invocation `10d761079d90473dadce79d3f7eb6457`的`controlled_stop/absolute_memory_limit`；两次run分类和账目分别保留。本Invocation的唯一service-finalizer wall为`2395.81151869 s`，V5 ledger共175项、本Invocation恰1项，SHA `962d31d906d22ec39d6a0e534021caa5fbcc8d1f521a966f245129d6768985ba`。tree RSS峰`35,915,563,008 B`、dedicated cgroup峰`33,178,259,456 B`分口径报告；numeric预测筛查总量不得称作实测峰。性能仍`performance_not_isolated`。

最终hash-bound派生记录：[terminal compact](../../../results/task041_v10r2_w0p7_deferred_amd_warm_run_20261008T082944Z/terminal_compact.json)。它引用原始summary、service/finalizer、consumer markers、memory stages、stdout及ledger SHA；不修改这些raw。W0.7缩减pilot没有完成求解，不能外推为50×25 nm、2 TB容量或48 h冷启动资格。

## 历史快照：2026-10-08 deferred-AMD组件与warm包准备

以下文字记录dispatch前状态；其中“尚未启动/待准入”只适用于该快照时点，已由上方终态更新。

**当前状态：组件小测试通过，下一步是重新绑定后的fresh准入；production warm场尚未启动。** 当前代码提交为 `6caf43ebd52b14bf0c9423b33353e7fc8f38f27f`，父提交 `24b6431370f20510f795df75c38fa5d5a66f4296`，已推送原分支。该阶段把大型LU拆成两个可检查的动作：先由MUMPS分析稀疏矩阵结构并估计工作区，再在同一个factor句柄上执行数值分解；这样可在数值分配前按实际阶段预算拒绝。代价是两侧矩阵、端口和pending symbolic对象会同时驻留，仍须以fresh资源采样和每阶段门判定。

| 范围 | 当前证据 | 边界 |
|---|---|---|
| PETSc/MUMPS控制 | 仅注册W0.7 deferred P4、MPI>1、MPIAIJ、PETSc 3.19.6/MUMPS 5.6.2路径使用AMD候选ICNTL7=0、ICNTL28=1、ICNTL14=40；JOB_NULL请求缓存、版本推导值和symbolic后的真实读值分开记录；MUMPS options冲突会在分析前拒绝 | 普通KSP/default与one-cell原排序不变；没有调用私有初始化函数或普通KSP setup冒充symbolic阶段 |
| 分阶段预算 | symbolic：`fresh B + source-counted Δ + W <= cap`；numeric：`fresh_numeric_B + INFOG(17) × 1,000,000 + W <= cap`，INFOG(17)只取一份；`W=5,322,116,301 B`是政策预留，不是误差上界 | bottom/top预测Δ `1,382,983,004/1,925,986,076 B`是源码计数模型，不是RSS上界。每一步仍需fresh B与真实MUMPS报告 |
| tiny验证 | serial `2 passed`，父wall `3.040390633046627 s`；MPI2每rank `3 passed`，父wall `2.0312472369987518 s`；V5合计唯一新增`5.071637870045379 s`，ledger 174项、SHA `531d777d369c8d84e58120ec79eabb638dd7fb8e4c03b2fdac3a33f5290515d2` | 仅8×8桥、预算和同句柄生命周期证据，不是大factor容量或W0.7数值资格 |
| 当前唯一下一门 | 已准备ignored warm包，待重绑到最终文档HEAD，再做fresh宿主资源/unit门与MPI8 native ABI | 不复用旧资源样本作准入，不再重跑QEP；当前授权规定这些门通过后直接执行sealed argv一次 |

PETSc扩展由词法`/usr/bin/mpicc`构建并从精确`.so`路径加载，SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b`。MPI2中one-cell/bottom/top symbolic的`MatLUFactorNum`事件增量均为0，显式numeric正例为1；预算拒绝不进入numeric并完成清理。向量相对残差约`2.46e-16`，两列分布式全局Frobenius相对残差约`1.68e-16`。原生扩展源码、构建命令、`.so`与测试raw由ignored准备包绑定；这些小矩阵数字不能外推到64966阶因子。

两次预启动脚手架错误均保留：首次build脚本在调用编译器前因`NameError: shutil`退出；首次serial runner在pytest子进程启动前因`NameError: TESTS`退出。它们没有pytest父wall，不进V5。成功retry分别使用fresh serial ABI和MPI2 ABI；测试stderr/stdout、attempt、资源采样和ledger receipt见`results/task041_petsc_lu_stage_bridge_jobnull_tests_retry_20261008T081956Z/`。Ruff相对HEAD没有新增告警，但相关文件仍有23条既有baseline告警。

当前W0.7范围仍是W材料缩减pilot（10×5 nm、接口2/22 nm、p6/h0.70/M400/MPI8、matched全段L20/N29/h20/29、fixed-H6/P4目标5e-13最多2次修正）。拟复用producer source `2708214386d38bd69f73e6b196c8ed843bb53d81`的既有packet，producer manifest SHA `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`、identity SHA `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`；该producer阶段已完成并写出packet，本次QEP=0。route-plan和leading-PH保持false。先前唯一warm consumer仍是top P4构造阶段`controlled_stop/absolute_memory_limit`：tree峰`53,541,888,000 B`高于cap`53,221,163,008 B`，其最终因子/残差/physics未完成；本次tiny组件测试没有改变该失败分类，也没有证明新的大因子可支付。Full 50×25 nm目标、2 TB容量与48 h冷启动目标均未达。

已在`results/task041_w0p7_deferred_amd_warm_preparation_20261008T082944Z/`生成ignored准备包；原字节已单独tar封存。当前代码与五份文档分别以普通提交推送，下一步把包重绑到最终clean HEAD、源码、编译扩展、producer与完整argv，再做fresh宿主门和MPI8 ABI。当前runroot不存在，尚无fresh production MPI8 ABI、service dispatch或FE；fresh门和ABI通过后按当前授权直接唯一dispatch。W2不执行。

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

## 2026-10-08：compact transfer接线阶段收口

compact orientation组件serial与MPI2各自通过；随后W0.7注册consumer接线的五个selector分三次attempt完成。首attempt的selector 2因测试替身把只读`audit`属性当可写而失败，`-x`后selector 3–5未执行；只修了fixture，再单独重跑selector 2，并运行剩余3项。各次SHA和wall分列在[test summary](outcomes/test_summary.md)。因此这是分批合同验证，不是同一最终测试文件SHA上的一轮五项全过，更不是新FE。

compact表示为每个adapter共享一份canonical插值矩阵与元素对象，并保留实体方向块；P/PH按原方向变换和复共轭伴随公式执行。每侧transfer创建后仅做一次小型标量汇总；K、cell counts及payload bytes描述持久对象，不代表RSS。普通路径仍默认稠密，只有已注册W0.7 deferred fixed-H6路径开启。MPI8真实驻留收益尚无测量，既往`7,476,508,109 B` numeric筛查缺口未证明消失；当前只完成组件和consumer接线合同阶段。warm准备包只作静态准备，未做fresh ABI或dispatch；原producer/QEP、数值门和资源合同不变。该研究路径尚无新的FE资格。

## 2026-10-08：W0.7 numeric前清理门合成合同

注册W0.7 bottom/top P4各自的`after_symbolic_before_numeric`入口现沿用既有collective heap cleanup：rank 0在清理前后采集同一全作业资源口径，所有rank进入同一清理调用，预算使用清理后的B。原top `before_symbolic`记录保持不变；普通路径和one-cell路径不新增清理。该改动不销毁pending factor、source matrix或recovery数据，也不承诺allocator释放或RSS下降。

唯一实际pytest attempt `task041_w0p7_numeric_gate_cleanup_serial_retry3_20261008T143000Z:serial:two_selectors`绑定HEAD `708f8ce8ab0631466930dddd395b8421f69a8b0a`、exact-side SHA `632c0a5e79e3a6c6441462d7556a85b8d161792efc7faaea87a171d01e06f7dd`、test351 SHA `90f1866734be47bad1610e1068e32f8ac81e06dc0911aa22cdfdf31df13edd1e`。`test_task041_w0p7_numeric_gates_cleanup_and_use_post_cleanup_authority`与`test_task041_w0p7_pending_p4_factors_complete_bottom_top_before_admission`均通过（`2 passed in 2.56s`）；顶层pytest父CLOCK_MONOTONIC wall为`3.2357035228051245 s`，attempt SHA `7f32831ff60e0fe0bf1832c03602733f5adbbdaa4c263d44a1552581af4ea476`，stdout SHA `1c0691b8549cf0ebdb3b80d38096681dc7f9d04ba98fe789d966afa6dd1f445e`。该wall在V5唯一追加一次，条目数181→182，账本SHA `e0bf2619c9f0f851b06cab44caa9b702df168a1ac793328fa556bd7fdfb3e13b`；ABI复用和静态检查不计。

三个前置attempt都没有启动pytest、没有pytest wall：初次runner的源码路径快照仍列六个旧路径，在identity门退出；retry1资源门通过但`BLIS_NUM_THREADS`缺失，线程环境门拒绝；retry2资源门通过但使用`python3`词法解释器且复用ABI的CPU身份不匹配，ABI复用门拒绝。原始记录分别保存在`results/task041_w0p7_numeric_gate_cleanup_serial_20261008T142200Z/`、`results/task041_w0p7_numeric_gate_cleanup_serial_retry1_20261008T142000Z/`和`results/task041_w0p7_numeric_gate_cleanup_serial_retry2_20261008T142500Z/`；通过attempt及source前后SHA见`results/task041_w0p7_numeric_gate_cleanup_serial_retry3_20261008T143000Z/`。这些合成fixture只证明清理调用顺序、rank入口、post-cleanup样本选择和预算控制流；不证明PETSc pending factor实际清理、RSS回收、numeric容量或FE资格。没有MPI、FE或dispatch；原生产容量缺口和既有raw不变，保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`未触碰。

## 2026-10-09：P6 identity projection 单次构建内共享验证

P6凝聚器的三个投影映射在每个材料/单元类别上都需要单位变换。此次改动让同一次凝聚构建中的类别共享同一个只读`float64`单位矩阵；空owner rank不分配它，不同builder调用之间也不共享。减少的是NumPy数组payload，不代表同等字节数的进程树RSS下降。构建审计在各rank记录类别数、按对象身份去重后的数组数/字节数和旧逐类别存储量，并在构建时进行一次标量`allgather`；不是每次作用或PC调用时通信。

实现绑定基线HEAD `9aeee6e3c7939bdd893b1b443990fea4a75438e4`，本次源/test最终SHA为：`hcurl_assembly_time_condensation.py` `85c5b70ca420b448396bd28d45b09856447e94529f6befe54a1dfd35ea15baf0`；`physical_balanced_side_inverse.py` `30932e60882e5ae71da2c529074a68ac5482f2b55a3c3f38ddecc03c3d409a88`；`test_115_task035b_assembly_time_condensation.py` `8888d9cc32c8f18b26903d932cac570807034117c97485d6c53884dbde8052a9`。这些源只由下述serial/MPI2小型有限元凝聚、恢复和empty-owner测试覆盖；不证明W0.7大模型节省、numeric预算可支付或完整物理资格。

| Attempt | 测试 | 结果 | pytest父`CLOCK_MONOTONIC` wall | 资源与原始证据 |
|---|---|---|---:|---|
| `task035b_projection_identity_serial_mpi2_20261008T232208Z:serial:post_assembly_reference_recovery` | `test_matches_post_assembly_reference_and_recovers_interiors` | 1 passed | `10.659502683905885 s` | runner authority peak `450416640 B`；stdout SHA `72b2c4cc16e81f88f61c2cc56d622ef552ebe589c3fc26e8a1972639997960f7`；attempt SHA `ff6ae7e856ff27bc2a31c8c6c65a053f0c1250bfdb473927529ce206a323bdeb` |
| `task035b_projection_identity_serial_mpi2_20261008T232208Z:mpi2:distributed_reference_and_empty_owner` | `test_mpi2_matches_post_assembly_reference`；`test_mpi2_single_cell_empty_owner_has_no_identity_payload` | 两个rank各报告2 passed | `6.456301460042596 s` | runner authority peak `618975232 B`；stdout SHA `a20534be89ec9a7debc5c0dd12cf8a12e826ee6237778ec47893895d34ccdd67`；attempt SHA `bb499975a7123113929f8df18a9c58fed0aca5ed149aed131b26b24668e8bebd` |

两条pytest父wall各按attempt唯一记账，合计`17.11580414394848 s`；V5 ledger从183项增至185项，SHA从`cd4c69f03e89b67350478b6c37655bc03ca77893ef5f6d96959fae32dcaaaa6e`变为`d5390d12f2fe362b675205f3758672429be7c20b19fafdafa64fd0b4aa15d28b`。serial与MPI2 append receipt SHA分别为`36af30f433f3c42add7f5da65f418fc1574152ccc1bdcaa8e718fdf22905e3e2`和`89fed62e00bef370a4b98c3567511190a7e260355322d926f252a8bc9826c75e`。ABI、资源preflight与静态检查不计入pytest ledger；保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`未改动。

这组测试只证明共享对象的别名、只读性、不同构建间隔离、MPI2汇总、恢复/装配对照及empty-owner零payload。它没有启动Task041/W0.7 consumer，也没有证明此前numeric预算缺口已消失。下一步是把当前三个源绑定纳入新的compact identity-sharing warm准备包；仍需fresh宿主准入与MPI8 ABI，当前没有dispatch或新Invocation。
