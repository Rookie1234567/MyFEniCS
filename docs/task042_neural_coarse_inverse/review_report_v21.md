# Review V21：V23收口与固定局部块—粗空间配对

## 0. 决定、快照与要消除的障碍

**接受V23同空间最小残差性质、薄QR与独立场证据；不授予完整有限元、神经加速或合并资格。停止继续替换同一p1空间的左测试、调整tau或延长旧标量细层配置。下一批固定一套几何实体分区，在原p3方程上构造局部块解，配对比较“局部块”与“相同局部块＋现有作用像粗校正”，两者分别做暖起点和零trace试验。**

本批针对的blocker是：原方程剩余误差既不能由单次p1校正有效消去，当前fine部分又只是标量乘法。局部块解让每次修正实际考虑一组相邻有限元未知量之间的耦合，而不只将每个残差乘同一个数。它可能改善方向，也可能因跨块波传播、局部不定性或粗细耦合仍然无效；收益未知。代价是八个有界局部LU、局部装配及反复三角解，不是免费或无因子的方案。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42_neural_coarse_inverse
worktree                  = /home/fenics/Projects/NN-Lab
review_date               = 2026-10-02
reviewed_HEAD             = dfaf983c2f6de28f59ee3271fb071c5b97210d2d
reviewed_commit_UTC       = 2026-10-02T11:34:51Z
reviewed_commit_Singapore = 2026-10-02T19:34:51+08:00
original_base_SHA         = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review           = review_report_v20.md
previous_review_commit    = 5c91a8101644f09d6e6e1b45043ae5581394c0e9
latest_response_reviewed  = response_v23.md
V23_all_formal_source     = 0d64407e9ec8c5d0b1da947a17f7bc390b8ccd52
next_batch                = V24_FIXED_LOCAL_BLOCK_AND_COARSE_PAIR
response_required         = response_v24.md
decision                  = ACCEPT_EVIDENCE_CONTINUE_BOUNDED_RESEARCH
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

最终目标仍为约2 TB整机内存内、端到端48小时完成新的0.7 nm任意非可分三维周期单胞有限元计算。本批是384-cell micro的求解器机制试验；不是完整2 TB容量模型、生产预条件器、p/h资格或目标规模通过。ChatGPT实际审查远程合同、回应、紧凑记录和相关实现，未SSH运行工作站、读取其全部ignored数组或测量实时资源。历史为recorded/measured，公式与载荷为derived，新队列为planned/not_run。

## 1. V23结果与解释

依据：[Response V23](response_v23.md)、[完整结果](outcomes/p1_image_minres_comparison_v23.md)、[候选CSV](outcomes/records/candidate_comparison_v23.csv)、[QR](outcomes/records/setup_QR_v23.json)、[粗比较](outcomes/records/coarse_compare_v23.json)、[费用](outcomes/records/resource_costs_v23.json)。

| 原0.7nm/384hex/p3/q15/40端口；无量纲measured | 暖起点V21-C | 单次Galerkin D-G | 单次MR D-MR | MR全空间暖M | MR零trace Z |
|---|---:|---:|---:|---:|---:|
| Schur；限1e-6 | 2.528117033e-6 | 5.789586833e-5 | 2.527812964e-6 | 2.507714365e-6 | 6.811317716e-2 |
| native；限1e-6 | 9.804133464e-7 | 2.245223668e-5 | 9.802954277e-7 | 9.725011139e-7 | 2.641454768e-2 |
| 散射E误差；限1e-4 | 7.816080389e-5 | 7.782445912e-5 | 7.816079665e-5 | 7.805935381e-5 | 9.891432988e-1 |
| 单通道功率最大差；限1e-6 | 1.719644651e-6 | 1.618374779e-6 | 1.719649314e-6 | 1.699731464e-6 | 9.105690357e-3 |

六个冻结状态完整0/6，M/Z原方程0/2。暖M四周期1024内步只降原rho约0.807%；零Z八周期2048内步后散射误差仍约98.9%。Z第二个四周期仅下降约1.397%，按原规则停止，不是资源停止或零起点永久不可解的证明。D-G原残差放大约22.90倍；D-MR满足最小残差不等式，却只降暖残差范数0.0120275%。其可移除平方范数约0.0240535%，不是历史参考误差的98.99%系数投影覆盖率。

这已经回答了上一轮的问题：同空间改变测试目标可以防止单次粗校正放大残差，但仍不能有效处理当前尾部。T/QR/R三角解均通过，不能默认是这些接口错误；也不能仅凭这一结果认定fine局部修正一定有效。保留class64及旧oracle独立审核。

V23正式监督wall1061.43058951秒，历史formal研发下界75124.917593秒，旧辅助/单解上游拆账unknown。采样同时树峰2061123584 B、自身swap/VRAM0；它们不是目标规模资源或单个成功解的时间。MR暖路线和旧Galerkin在相同四周期都无实质突破；不重跑它们来换标签。

## 2. 本轮为何不是重复ILU或局部神经基

旧V20是全局自然排序ILU(0)，在一个固定稀疏填充模式中近似整个体块；本批是在固定的八个不重叠局部主块内做完整LU，跨块耦合仍由原全局作用和外层Krylov处理。它属于块Jacobi机制，不是ILU排序/填充扫描。块求解的通用定义见[PETSc PCBJACOBI](https://petsc.org/main/manualpages/PC/PCBJACOBI/)，本批实际用已有SciPy/LAPACK数组接口，不要求把PETSc对象接入ML进程。

V15虽然也有八个分区，但当时每区只组合约195个辅助函数；本批每区处理该区全部p3独立trace未知量，没有局部神经表示限制。只复用V15的几何实体map，不读取其神经特征、权重、解或参考。局部块不是八个独立的完整散射问题，人工块界面也不是新物理边界；局部解只是预条件作用。

本报告只授权这一套局部规格及同规格的粗组合，覆盖V23的“不得新建PC”批次限制；不改长期治理。旧首轮task的13.5nm/p4与独占安排按后续micro/受控共享合同解释，不倒退回跑。当前任务目录未见另命名supplement；根/目录AGENTS、原task、历次正式覆盖及最新合同继续适用。

## 3. 冻结身份与数据权限

| 项目 | 固定值或SHA256 |
|---|---|
| fine物理 | Full3D complex128，0.7nm，grazing1度/azimuth0/s，三维缺口，原背景/RHS，双Floquet/Fourier-DtN |
| 离散 | 384hex/p3/h0.175nm/q15；full34050、trace18144、interior13824、slave2082；40端口，z18184 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；离线ready，不再索要 |
| Si | n=0.999885140474+4.32477054e-6i，epsilon=n*n、mu=1；0.699999988仅明确alias到nominal0.7 |
| physical | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| material | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| modes | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| warm V21-C-FINAL NPZ | 680f58e5e58704fc69f0b539c8c411131ce697b7811445eb9643bbf92a736072 |
| warm z array | 3751e1cacb2b160a7425cdb8f0bbe58ffbfdcafdb533504f392686ca5840f6d1 |
| V15 geometric map NPZ | bd40a9cc9d9040cf1efdd17d2e3682a7cad84ff10402b2110d8945e74e9b32a9 |
| V22 T NPZ | 22e21cd840efb51d2dc66e556d85587088f406dce3221f564109a27b7b096fd8 |
| V23 U NPY | 1e7624c2531739cafefb500906514f1da7e5b0649064899a957ef6d937822fd1 |
| V23 R NPY | 8acdec1077a1259d71ad0ef3386a8680ec79aff9047d0f7e3d89e77597f6e8bc |
| REF7 NPZ，仅最终VERIFY | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

路径及成员hash从[几何map](outcomes/records/local_entity_map_v15.json)、[现有QR](outcomes/records/setup_QR_v23.json)及原run/checkpoint解析。warm保持V21-C，不选V23略好的M-FINAL，以便复用历史同起点控制。W不重新构造，T不重新插值，U/R不重新QR。

SETUP只读物理packet、几何map及T/U/R，不能读暖解或参考；WARM只解压trace/port/z/residual；ZERO只读原物理、几何/局部因子及所需T/U/R，不能解压任何warm、x/CU/旧方向或神经数据；VERIFY只在全队列冻结后读取REF7。参考历史已参与研究设计，不称全新blind test，求解过程仍无参考反馈。

map缺失但原mesh/moment身份完整时，只允许复用canonical_entity_map做一次相同规则的几何重建、核对全部原成员hash并记录新容器hash；不得重跑V15基构造。T/U/R缺失仅阻塞组合路线，局部路线仍可做；不自动重建旧QR。新artifact/ledger/cache独立，旧目录只读。

## 4. L8：固定几何主块与局部完整求解

采用V15已记录的x=0、y=0、z=0.525八盒。按canonical master完整边/面实体中心分组，切面归低侧、周期上边界只在分组时用等价代表位置。保持原行序、相位及所有高阶矩；不按row编号等分，不增加slave，不改变积分坐标。

分区行数必须为2913/2676/2289/2076/2439/2220/1863/1668，总18144、2448个完整实体。布尔限制矩阵记为E_b，各行恰归一块。分区定义从已存map核验，不调块数、重叠、排序或方向。任一缺行/重复/实体分裂必须先修数据问题。

原闭合算子记为A，体块K仅作代数记号，本批不物化全局K。原40端口消元给出：

```math
A=\bar S=K-C H^{-1}F,\qquad H=H_{hat},\qquad
A_b=E_b A E_b^H=K_b-C_b H^{-1}F_b.
```

C_b=E_b C，F_b=F E_b^H，完整40列/行均保留，F不能假定为C的共轭转置。K_b通过原cell Schur和Floquet展开的局部子贡献累加；先正确处理共享贡献，不按owner cell截断装配，不分别凝聚curl/mass。可复用fixed_p3_ilu0.expansions/direct_C/direct_F的数学助手，但不调用旧全局assemble_K或ILU。

每块是原A的主子矩阵，不是只组装块内单元的另一物理PDE；跨块耦合只在PC中忽略，外层与验算始终保留。禁止18144次单位向量重构完整A。用每块两个固定复向量（seed422401+2b起）核对A_b w=E_b A(E_b^H w)，最大运算尺度差<=1e-10，包含全部端口闭合。

已有complex128 LAPACK部分选主元LU，每块一次固定直接三角解，无shift/drop/ILU/经验阻尼或自适应精化。局部rcond1由gecon估计并明确是估计，要求>=1e-12；每块两个见证局部相对残差<=1e-8、运算尺度缺陷<=1e-12。零RHS返回零，重复/复线性<=1e-10。这里要求局部方程可靠，不要求一次局部PC成为整个fine的准确逆。

```math
\mathcal L r=\sum_{b=1}^{8}E_b^H A_b^{-1}E_b r,\qquad
\mathcal D=\mathcal L^{-1}=\sum_{b=1}^{8}E_b^H A_b E_b.
```

所有局部块可逆时，分区覆盖保证L8是全秩块对角作用，不是低秩代理。D只按块乘，不显式构造全局逆/矩阵。局部块不安全时保存负结果，不自动加shift、扩大块、删变量或用tau填补坏块。

容量先于分配：各块<=4096行；实际sum(n_b^2)=42,325,956，一套稠密A_b载荷677,215,296 B，两套A_b+LU为1,354,430,592 B，约1.261 GiB，pivots另计。矩阵+LU显式载荷上限2 GiB，连同U/R、最大单块副本、BLAS、D_L构造、Krylov及原packet规划同时<=8 GiB，原12/16 GiB与swap0不变。这个数组计算不是实测RSS。只保留一套分区与同规格因子；至多5个独立进程各载入同一8块因子，不序列化不可恢复对象。数组LU/pivot可按ABI/hash只读复用，先做独立进程重载求解测试；不能每周期重新分解。

声明LOCAL8_DENSE_LU_PRESENT；组合另声明GLOBAL_TALL_IMAGE_QR_PRESENT。不把局部因子、40维H或粗R隐藏为factor-free。固定八块随目标规模增长会变大，本批不证明生产可扩展性；将来必须限制每块规模并处理分布式耦合和粗空间增长。

## 5. LC8：同一局部作用与原作用像粗校正组合

保留V23的J，构造新组合而不修改旧ImageMinresPC的tau语义：

```math
AT=UR,\qquad J r=T R^{-1}U^Hr,\qquad
B_{LC}r=\mathcal Lr+J(r-A\mathcal Lr).
```

先由局部方程给出修正，再用同一个1248维空间处理局部修正后可消去的残差分量。与旧tau方案相比，只替换fine作用；不用旧tau再乘一次L，不加入网络权重或新方向。局部解本身改善多少、粗层在其上额外改善多少，必须用L8/LC8实际配对区分。

**旧Dsmall=U^H T的安全性不能直接用于新组合。** 精确运算下定义新的1248阶块：

```math
D_L=U^H\mathcal D T,\qquad
\det B_{LC}=\det\mathcal L\,\det(R^{-1}D_L).
```

因此各A_b及R可逆时，还须D_L可逆才能排除组合PC的非零核。D_L按至多32个T列分块，通过局部A_b乘法和U的BLAS共轭转置累加，不存完整D或新的n×n投影；新增一份D_L小矩阵即可。固定一次svdvals，sigma_min/sigma_max>=1e-12；不截列、伪逆、加shift或扫描阈值。D_L不安全只隔离LC8，已经可信的L8暖/零路线继续。

小型复数非Hermitian、非互伴C/F及非零40-port模型验证以下关系和完整右侧求解：

```math
U^H A B_{LC}=U^H,\qquad
B_{LC}\mathcal D T=T R^{-1}D_L.
```

必须有反例A=[[1,-3],[1,1]]、T=(1,1)^T/sqrt(2)、两个一阶局部块。A和局部块都可逆、AT满列秩，但L=I、D_L=0且组合奇异；不能以“局部都能解”跳过这个检查。真实使用三个固定复粗见证/随机fine向量核对组合恒等式运算尺度<=1e-8及重复/复线性<=1e-10，不要求fine逆残差1e-10。精确关系不是收敛率保证，浮点资格单独记录。

## 6. 固定四路线：先得到有效对照，再有界继续

外层复用已验证的GMRES256与返回后事务，候选B分别为L8或LC8：

```math
r_k=\bar b-A t_k,\qquad (AB)y=r_k,\qquad y_0=0,\qquad
 t_{k+1}=t_k+B y.
```

使用LinearOperator(y -> A(B(y)))，SciPy的M=None，明确右预条件。[SciPy GMRES](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.gmres.html)的M接口是左预条件，不混用。restart256/maxiter1/callback_type=pr_norm，现场tol/rtol适配且相对容差0，atol=1e-8*norm(原完整物理b)。原方程正式门限仍1e-6；info和内部残差不代替原审核。

| 路径 | 起点/内容 | 首块与继续上限 |
|---|---|---|
| S | 分区/局部装配/LU、已有U/R复核、D_L与端到端资格 | 设置/数值资格<=2400秒，不重建p1/QR |
| LW | 原V21-C-FINAL，只有L8 | 首4周期；每4周期原rho降>=10%才续4；最多16周期/1200秒 |
| LCW | 同一暖点，LC8，独立于LW | 同LW；不使用LW末态warm start |
| LZ | 新进程零trace，只有L8 | 首4周期独立准入；每4周期降>=20%才续4；最多32周期/1800秒 |
| LCZ | 新进程零trace，LC8 | 同LZ；不继承LZ/M/Z的解或循环方向 |
| V | 全队列冻结后唯一FE审核 | <=12个去重状态/600秒 |

先按LW4→LCW4→LZ4→LCZ4完成各数值可信路径首块，再按每4周期轮转和预登记进展扩展，避免第一条耗尽窗口。某暖路线负结果不阻止零初值，粗组合Gate失败不取消局部路线。S缺T/U/R时仍可完成L8资格和LW/LZ；物理packet或分区/局部块本身不可信时停止其全部依赖，不绕过。

Z是ZERO_TRACE_FROM_FROZEN_OPERATOR，端口与内部特解按原b闭合/恢复，不强置零；不是从几何开始的完整fresh run。暖点继续承担旧神经基/LSQR/循环的全部上游成本，不能只报本批末端校正时间。

每周期先保存y，再By/实际trace，再由旧bar.close取得完整z并切出40port，最后旧ActionPacket审核和commit；已返回但审核失败只补审，不重算内周期。原/新作用差/norm(b)<=1e-11、恢复/identity<=1e-10、slave storage=0始终保留。连续两个周期原rho显著上升（绝对余量1e-10）只独立复核一次，确认则停止该路线。FIRST_EQUATION_PASS单独冻结且不可覆盖；同路线预算内至多再2周期追求可选1e-8余量，不提高强制成功门限。

历史V22/V23相同暖/零起点、同外层设置的记录按hash复用，不重跑旧PC。新L8一次PC不调用fine A，LC8额外调用一次；比较共同迭代、原作用前缀及完整wall，明确不是同代价每步。局部factor/setup及上游T/U/R成本不得排除。没有资格通过就不谈同严格精度加速。

## 7. 数值验证与本批终点

S及所有求解/分流/hash冻结并退出后，唯一VERIFY才读REF7。预登记审核旧warm、四条最终点、各FIRST_PASS、各零路线第4周期，去重<=12；超过时依次保留FIRST_PASS/最终/旧warm/零4周期，不按参考选择。局部单次随机资格不是参考训练数据，本批无监督投影、参考误差新分解或求解后回训。

原Schur/native/增广/规定端口<=1e-6，恢复/identity<=1e-10、slave-zero；total/scattered E/H/curl、selected复场、40复振幅<=1e-4；R/T/A/A_volume绝对差<=1e-5、逐通道功率差<=1e-6、能量<=1e-5。native与独立total-native分列，不用一个通过替代另一个。功率由原批准函数从完整复振幅导出，标derived并保留通道键/极化/reference plane；未合格状态只给UNQUALIFIED_DIAGNOSTIC。

若LW/LZ改善而LCW/LCZ不改善，说明粗组合没有显示额外收益；若组合明显优于局部-only，才有局部—粗层协同证据。若只降残差却场/功率不过，仍未完整通过。若四路径均无实质收益，收口这一固定八块规格，不自动调块数/重叠/shift或再延长同配置；只提交一个下一最小建议。任何成功最多称当前micro同离散资格，没有神经训练增量、p/h精度或目标规模证明。

神经研究定位必须如实：这轮没有训练NN，测试的是通用有限元求解所需的局部—全局耦合机制。不能把确定性局部解收益归给神经网络；也不以本批负结果否定学习局部校正、学习粗方向等全部路线。当前优先完成一个可信的micro求解，再决定学习模块是否存在可量化的独立价值。

## 8. 预算、安全、自行修复与时钟

新start从首次真实UTC/monotonic/boot_id检查冻结，全批最多4小时，3.5小时停重负载，最后30分钟交付；实现/测试/setup/修复/等待/求解/验证全部计入。每次上下文恢复、新stage、commit/push和交付前读真实钟与持久ledger，不从摘要推算剩余时间，不扣除未知间隔。数值队列退出即写minimum_result/cost/response骨架，不能等到超时才组织证据。

全批原/新S+SH<=45000，L8整套apply<=25000，局部LU solve<=210000（每次solve的L/U两个三角pass另计，上限420000），J/R三角解<=14000，原audit<=160，field_states<=12。一次8块装配/数值factor构建和一次D_L小SVD；相同因子只读重载，不每路线重新分解。至多一个受损块的原规格修复重建且计费，不据数值负结果换配置。gecon内部动作记录估计/保守上界，不伪造实测次数。新持久artifact<=2GiB，原数组不复制；外部actor队列的子预算同时受总截止限制。

setup前按实际行数、两套局部矩阵、最大单块临时副本、U/R、32列缓冲、Krylov、Python/BLAS/原packet给出同时规划<=8GiB。RSS warning12GiB/hard16GiB为0.5秒整树采样停止阈值；无delegated cgroup就不称kernel连续硬限额。ownswap0、无OOC/GPU；MPI1、数学/Torch1、DataLoader0，实时选空闲物理核并避开忙SMT，旧核编号不固化。

继续用户已授权的受控共享CPU：其他heavy存在不自动阻塞，但系统max(128GiB,10%effective total)、邻增长128GiB及本任务16GiB余量、diskfree>=50GiB、自有锁、独立缓存和原PSI保护不能放宽。PSI full avg10>=0.1百分数连续三次5秒停止自身；只杀自身后代，不改邻任务、共享Git配置、系统swap/ABI/BLAS/CUDA、锁或监督器。资源停止至少冷却120秒、最多观察600秒；full<0.05持续60秒且所有Gate通过才重入，全批最多2次、累计等待<=1200秒，计入总窗口。

最多4个已定位意外根因最小修复，每次<=900秒、累计<=2400秒、同根因最多2次；计划内实现计时但不占修复根因。局部零主元、D_L不安全、普通不收敛不是实现bug，不能靠改精度或配置“修过”。一条路线阻塞只隔离依赖项，合格独立路径继续，不逐小阶段等待确认；总截止后仅必要清场/保存/交付，延期如实保留。

## 9. 实现、证据与正式入口

复用local_trace_geometry/既有map、fixed_p3_ilu0的局部数学助手、ImageMinres、class64、原ActionPacket/BarAction、cycle_commit和窄reader。新局部与组合核心进入src/solvers；普通默认、旧ImageMinresPC和原audit数学实现保持不变。新driver只加参数化接线，不复制大runner或数千行旧JSON。

小测试必须覆盖：复数非互伴40端口、局部主块完整装配、共享cell/Floquet重复贡献、局部solve独立读盘、D_L反例、旧tau等价特例L=tau I、真实右PC更新、dat→worker→close→保存→原审核、坏hash/半写/返回后补审、warm/zero角色白名单与截止清场。先focused回归并提交clean源码，正式PDE绑定实际source，而非review或最后文档HEAD。

以下为本轮待创建入口，不得提前声称已实现；按资格和轮转调度执行，不盲跑条件组合：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v24_local_block_setup.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v24_local_warm.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v24_local_coarse_warm.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v24_local_zero.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v24_local_coarse_zero.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v24_verify.dat
```

每个slice一项明确one-run，继承同campaign预算，保存input_original/resolved_config/run_manifest/input/physical/material/modes/action/backend/map/block/LU/pivots/T/U/R/D_L/parent/state成员hash、ABI/MPI/线程/source/run_summary与全过程资源。没有完整递推状态的物理快照不叫无损续算checkpoint，未知费用保留下界/上界。

提交计划：C1局部核/复数及奇异反例测试；C2端到端接线与clean输入；C3冻结求解和独立验证；C4紧凑结果/response/总账。交付response_v24.md、outcomes/local_block_coarse_pair_v24.md；records至少含partition/local_capacity/block_action/local_factor_safety/local_reload、composite_overlap/linearity、cycle_history/candidate、field_channels/per_channel_power、lineage/access/checkpoint、run/cost/deadline/repair/not_run。引用上游hash，不重嵌套旧recipe。

同步summary/tests/changed_files/README导航、development_progress和development_model_registry，旧task/review/response/raw及所有负结果不改。Review由ChatGPT维护；Codex发现问题在response提出，不改写review。Markdown遵循fenced math和列数一致表格；没有精确GitHub视觉证据如实标NOT_VERIFIED，源码检查不是视觉通过，不为渲染启动额外数值负载。

仅推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse。截止、安全/修复上限或全部可执行队列结束后清场，报告精确HEAD/base/upstream/worktree、实际source、局部/组合因子与容量、暖冷完整资格/费用、停止原因、未运行项和唯一下一建议。不得merge master、其他分支或自动启动更大模型/新p4参考。
