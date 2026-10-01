# Full3D y-only sparse 凝聚适配：待审查实施包

## 结论与当前状态

把每个单元内部的未知量准确消去、只对边/面和全部真实边界端口分块求解，然后准确恢复所有内部未知量。既有Task39已经完成消去/恢复公式，Task040已经验证全谐波离散背景逆；本包只补上这两者在 **y-only、x-z材料/网格非均匀、完整端口别名** 情况下的连接。没有第二套Schur公式、模式生成器、原算子、因子服务或持久化框架。

当前所有新增文件只在外部staging，canonical没有本worker改动。仅AST语法检查已执行；新增代数测试、真实sparse-p2、p4和任何因子均未运行。必须先审查/最小文件集成、冻结新的完整HEAD和source manifest，再由协调方批准准确命令。其他worker的modal代码独立负责q投影、逐q因子及完整三维外迭代。

| 部分 | 实现/复用 | 资格边界 |
|---|---|---|
| 完整curl+mass在局部消去前相加 | Task39 `build_unconstrained_assembly_time_condensation` | 原公式不改；p2/新reference还须实际oracle资格 |
| 完整Bi/Di/Bhat/Dhat/Hhat和内部RHS、XiB恢复 | Task39 `assemble_condensed_ports`、`P4CellCondensedInverse` | 不假定内部端口为零，不额外施加一次MPC dual映射 |
| 完整原FFCx/DtN action、incident RHS | 既有physical-action builder | 原slave-zero原空间；不以凝聚算子验证自己；volume_action.apply返回action拥有的borrowed reusable Vec，不由adapter销毁，下次apply前使用/复制 |
| 非Hermitian端口残差等式 | 既有 `fullspace_p4_blr.augmented_residual_identity` | 用原D，不替代为B的共轭转置；保留原1e-10门 |
| fullFE→trace restriction | 新adapter；输入既有 `build_y_orbit_layout` | 实测完整trace/interior分割与稀疏支持闭合，R不假定unitary |
| q投影/所有端口别名/因子/outer | modalworker另一模块 | 全off-q审计在任何因子前；全部n mod Ny保留 |
| 紧凑证据 | 复用既有runner的hash-bound ignored writer | 保存原空间向量和cache内容身份；无跨run loader/restart声明 |

## 固定接口与所有权

`build_same_mesh_physical_action(levels,cfg,degree)`的现有返回字典直接作为action_bundle。levels由 `_build_same_mesh_levels(cfg,COMM_SELF,(degree,),include_positive_coefficients=False)` 创建；只含一套p2或p4空间，拒绝隐藏p6。复用现有pilot_config与notch构造，实际三维配置和全部532有序manual modes不删减。

`build_condensed_reference(action_bundle,allocation_gate=gate)` 返回CondensedReference。它拥有system及P4CellCondensedInverse；借用完整原action、FE setup和调用者的全部q factors。system.matrix为实际增广 `[SV,C;-D,Hhat]`。factor的准确接口是 `solve_repeated(rhs:PETSc.Vec,target:PETSc.Vec)`，输入/输出均为native active trace后接原顺序全部ports；填写target，不接管向量；一份native非零FE RHS由既有apply调用它一次。factor创建及其全部资源/整数准入不在此adapter。

`reference.inverse.factor = admitted_factor` 后，`apply_independent(rhs,full_layout)` 调原reduce/solve/recover，返回完整独立FE向量；内部RHS不清零。`inverse.last_port_solution` 保留同次求解的全部alpha，供独立端口闭合核验。destroy清理system矩阵/局部cache，不销毁借用factor/action。调用者先停止factor使用、销毁reference，最后销毁原action/setup；CSR使用者须在reference销毁前释放自己的CSR。

trace_layout_coordinates固定返回：R_t、R_t_inverse、F_t、native_trace_translation、trace_width、ny、trace_original_rows、full_independent_trace_positions、full_canonical_trace_positions、audit。依据实际owned_active_original_dofs的顺序，检查它与所有原cell interiors恰好组成完整independent集合；从完整R/R_inverse/F/translation准确限制。支持闭合使用确切非零结构，连1e-18系数也不删除。原/逆R双向核验与F正交门1e-12。

Q_t=R_t F_t。变分load转换为Q_t^H g，solution恢复为Q_t z；solution到modal为F_t^H R_t_inverse x，不能把它与load转换混用。完整恢复平移见证使用 A T x=T^{-H}g，其中T=R shift R_inverse，dual平移为R_inverse^H shift R^H（已资格real ky使shift unitary）。该门在完整FE恢复后包括全部内部，不只是trace。

原storage索引先在原宽整数类型核验range/重复和PETSc.IntType上限，再缩窄；CSR维数与NNZ offset在getValuesCSR前核验整数范围，返回后核验ptr与index完整性。CSR与port-index数组/scratch字节按实际PETSc.IntType.itemsize（32或64位）估计，不硬编码4/20；complex128数组按明确dtype的16B计算，DOLFINx局部cell/entity位置仍是其原生int32。scipy_csr通过公共PETSc getValuesCSR生成一次CSR，无额外显式numpy副本；不假称PETSc零拷贝。gate保留一次导出加可能SciPy转换共3payload，消费端只读、不在对象内永久cache。coordinate_array_views与return_vectors输出接现有writer。recovery_numeric_identity流式hash既有LU/投影/恢复、cell归属、完整Bi/Di/XiB和MPC trace扩展；共享数组按角色多次计为logical bytes，明确不等于RSS。原FE native map使用现有native_map_arrays，不另写MPC序列化器。

## Sparse-p2先行资格：使用已保存phi5 dense oracle

权威artifact为canonical ignored `benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_phi5_attempt1`；原运行source为ac1410ca1187352fbe398325c5f7aaa33bf0d0bd。独立checker已经通过，2048完整独立行、480内部、532实际端口、Ny=4、phi=5°非零wrap。同80cells/物理Si/原配置及两cell三维notch，无重新变小几何。

1. 先hash核对pilot_report、provenance、independent_checker、ABI及每个使用的npy，逐项比较完整axes、material、period/angle/wavenumber、mode顺序/数量/manifest、native独立行顺序与Q/F/R_inverse。新的HEAD当然不同；只宣称列明原action/layout依赖的源码文件hash和ABI与旧oracle匹配，不假称整个HEAD相同。若不匹配，停止并解释，不能仅凭值近似绕过身份门。
2. 先从finalized public MPC coefficients/offsets/masters/slaves验证完整map，测量最大master展开width（含存储零系数，保守）；稀疏graph/workspace上界按cells×local_dimension²×width²+rows，宽度无法取得/核验则停止，不猜单master。p2公开dolfinx_mpc.assemble_matrix生成原volume稀疏矩阵；没有端口全局outer matrix和numericfactor。对保存A0_original mmap逐32列比较全部2048列：当前sparse volume panel加所有原carrier贡献，与旧dense独立原矩阵比较Frobenius相对差≤1e-11。载入旧oracle全部页可能驻留，额外保留其67,108,864B；不是只算当前小panel。
3. 建立准确凝聚及完整trace坐标。测量实际Bi/Di支持、Hhat、NNZ、矩阵/局部cache payload/RSS；核对全部off-q、primal/dual、端口别名。只有全部通过后，modal模块按新准入逐q因素化。
4. 原oracle的generic_rhs与physical_rhs、两个saved A0_direct解：新逆恢复后原FFCx/DtN true residual≤1e-10，完整slave零，原augmented FE/port/identity均≤1e-10，与saved direct solution相对差≤1e-9。generic load必须在每个内部row和每个q上有实际激励。重复/线性门、full恢复translation gate同时核验。
5. 同旧三维notch的outer原action，对旧notch_direct_generic/physical比较相同原空间残差/解差门；这部分由modalworker整合，不能用regular的离块审计替代notch耦合。
6. 将原rhs、恢复field、原action向量、volume/coupling、全部alpha、port投影及H、native/top/port residual数组绑定hash保存。checker从这些原字段重算范数和非Hermitian等式，并对p2重用saved dense矩阵重算完整原residual。p2新组件通过后才提交p4的单独准确命令；没有自动继续p4许可。

八个新小代数测试只检查nonunitary R、trace顺序、完整内部分割、极小非零mixing拒绝、Fourier极小非零mixing拒绝、先检查宽整数range再缩为PETSc.IntType、真实public MPC多master宽度/不一致拒绝、int32/int64实际itemsize载荷及必需allocation gate；它们不能代替上述真实p2。

## P4先验规模及resource gate（derived，尚未运行）

同80cells、全部532aliases：15,872完整独立FE，8,640内部，7,232active trace；四q trace各1,808，ports为76/152/152/152，增广块1,884/1,960/1,960/1,960。单个完整FE dense矩阵4,030,726,144B不准入；全p4 direct的fill未知，明确不运行。p4原physical accuracy和目标原尺寸解仍未资格化。

| 对象 | 先验数量/字节 | 条件与口径 |
|---|---:|---|
| 四q volume输入图上界 | 1,848,320 stored entries | 每q20个xz cell×至多152² canonical local channels；必须实际确认MPC support |
| 保守C/D+Hhat输入图 | 四q总≤2,417,104 entries，约48.4MB CSR | carrier实际支持不超已审计底/顶slab；包括可能非零Bi/Di，不假设bubble无耦合 |
| 更紧零interior-port图 | ≤1,985,044 entries，约39.7MB | 仅在实际Bi/Di确为零后才能引用 |
| 四q dense数值payload | 241,188,096B | 仅帮助说明维数；实现不创建这些dense块/矩阵 |
| 稀疏L/U全三角stored数值+int32界 | 301,702,544B | 非SuperLU工作区/超节点/RSS保证；不通过.L/.U物化副本采样 |
| 声明factor及工作区余量 | 536,870,912B | 政策budget，SuperLU无独立symbolic estimator，不能称预测/证明 |
| 证据/向量reserve | 134,217,728B | 保留给original恢复/核验/记录，不被setup占满 |

whole-tree simultaneous RSS硬上限min(1,610,612,736B,fresh dynamic cap)，wall600s、zero swap、serial/maththreads1、一次一个heavy。现有subreaper/watchdog能力必须先已资格，不用OOM作为停止。每步前调用fresh measured admission，初次因素化条件为当前树R0+512MiB额外factor/workspace+128MiBreserve小于有效cap（名义R0须<939,524,096B）。已经驻留的factor包含在实测RSS，后续再保留保守remaining请求，不双计整个初始余量，也不假设del之后allocator返还页。任何headroom不足、swap、NaN、身份/原residual失败、结构超预估、跨q非roundoff或时间超限立即受控停止整棵树，保存真实失败。

adapter本身在编译、实际kernel/MPC matrix预分配、localcache、真实port terms、CSR、trace restriction和p2 oracle panel前显式准入。预分配使用实际tagged slab，PETSc NEW_NONZERO_ALLOCATION_ERR保持开启；若carrier逃离slab直接停止重新估算。编译64MiB是声明allowance，非进程峰上界，编译子进程也计入watchdog。任何初始setup/JIT准入也由原runner的parent source/ABI/watchdog gate包住。

## Task040复用及不适用的旧假设

引用固定50897c0c62d1f35abed5b196ae17997b2e7521cc下S2c/S2d、block_transform/service；完整缓存blob清单见reuse_manifest.json。既有S2d准确离散all-harmonic逆的component证据有效，新包不重新发明其概念。当前完整YOrbitLayout已经复用共同hcurl_canonical_vector_dolfinx实体方向帮助器，不复制第二套方向/map代码。

不能直接调用旧Task040的3×2×4、两轴均匀、480trace/4aux、全部port在harmonic0、每块≤1024/dense LU封装。这里需y-only保留heterogeneous x-z和532aliases、p4≥1884行、逐q sparse抽取；不移植S3允许dropped_coupling的近似布局，不静默继承abs≤1e-14 orientation截断。不整体合并旧研究分支。复用manifest区分runtime import、shared inherited helper、历史证据与明确未采用模块。

原尺寸32,060 autochannels由portworker已实测；pilot532仅判断degree-growth架构，不能叫原尺寸mode truncation/连续精度/2TB/48h通过。完整三维外算子和未来notch能力保留。
