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

---

## 10. 2026-10-02 独立复核与未完成 V24 合同澄清

本节由用户指定的独立审阅者完成；不使用 subagent，不修改求解源码、不启动 PDE／训练／大型实验。**接受 V23 的实现检查与负结果，完整资格仍为 0/6；V24 值得一次有界、对称的首块对照，但必须先处理下述两个准入／调度问题。当前没有可核验的神经增量、原尺寸 0.7 nm 解或 2 TB／48 小时资格，也不批准 merge。**

本节澄清正在进行而未闭环的 V24：原 §0–9 原文保留，本节明确修正的执行项以本节为准，其他物理、安全、预算、来源与验收约束继续有效。不是另开一轮，也不创建平行 addendum。`response_v24.md` 已有本地阶段提交，但声明继续原窗口，尚无冻结求解／VERIFY 的正式结果；故按 AGENTS §15 更新本 review，不提前编号 v22。若执行者之后发布新结果，应先核对实际 source／时间／状态，再审下一轮，不把本节的时间快照当作永久状态。

### 10.1 远端、现场与审阅范围

| 核对对象 | 事实与证据边界 |
|---|---|
| 远端权威 | 非交互 `git ls-remote origin refs/heads/task42_neural_coarse_inverse` 核实为 `c3370061c6693eab70e20c34965ec7d640b978bd`；2026-10-02 14:14 UTC 再查仍相同。没有把相似分支或本地 tracking 缓存当作最新远端 |
| 本地实现 | 开始检查时已有未发布实现 `370b7bbe2455448b320ca4272eb62950e4715ecc`；审阅期间出现文档提交 `3741ed0679e975b89f16b1ecf613076e8d93828e`，parent 链为 c337→370b7→3741。它们是既有执行工作，非本审阅者编写 |
| 仓库身份 | `/home/fenics/Projects/NN-Lab`，canonical common Git 为 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；分支名逐字符核对。未 checkout、修改、合并 dot 或 master |
| 是否运行 V24 | 主机级只读进程检查在 14:15 UTC 未发现 Task042 数值 actor。14:19:57 UTC 本地 journal 最新为 14:08:39 的续行声明，`benchmarks/artifacts/task042/v24` 尚不存在；不能把“准备继续”写成已经执行。未重复启动、终止或接管任何队列 |
| 本地 V24 分类 | 首次准入无空闲物理核，actor 未创建；其后审批服务认证失败，命令未执行。14:07 后恢复声明保留历史，不能把早先认证错误继续当作当前永久 blocker。阶段文档、测试、容量算术已存在；真实八块装配／LU／D_L／四路线／VERIFY 在上述快照均 `NOT_RUN` |
| 权威阅读 | 核对根／docs AGENTS、仓库工作原则与导航、task／README、共享授权、23 份 response、21 份 review、最新及历史 summary；按轮追到原始 records、相关凝聚／DtN／测试说明和实际源码，不只依据最新摘要 |
| 可复查索引 | [独立审阅记录](outcomes/records/independent_review_v21_20261002.json) 对 c337 的任务目录 **547 个 tracked 文件、16,900,423 B** 逐项登记内容 SHA256；384 JSON、12 JSONL、72 CSV 完成结构解析。明确另外列出 3741 的新增／变更文件，不混用工作树新文档冒充 c337 内容 |
| 审计深度 | 重点语义检查 action／恢复、神经 FE 矩、固定头、全空间校正、右 PC／事务、class64、p1 传递、image-QR、八块 LU／组合／reader／queue 及相关测试。**索引和结构解析不是全仓每个文件的逐行语义审计**；大型 ignored artifact 未全部重算 hash，未重新恢复 FE 场 |
| 本审阅实际复核 | qualified `activate_task042.sh pure` 下重跑 V23 轻量 checker；独立从 240 行功率记录计算绝对差；隔离 queue 的 AST，仅用惰性替身复现两项控制流问题。无 FE/MPI／完整 pytest／训练／新正式数值运行。V23 的 27 passed 和本地 V24 的 28 passed 是历史测试记录，不冒充本次重跑 |

原始进度中的 `dependent_not_run: local block numerical Gate` 是过宽的分流文案；[V24 分流](outcomes/records/qualification_and_dispatch_v24.json)及 [response_v24](response_v24.md) 已说明真正未进入数学 Gate。外层 `COMPLETED`／退出 0 只表示监督流程结束。空 CSV 不是零误差场，规划中的因子大小不是已经分配的 RSS。余额可按用户授权使用；本审阅未使用重置卡，也不要求重置配额。

### 10.2 历史去重：什么已经尝试，什么仍没有运行

下表中的数值均为绑定原记录的**历史测量**，不是本次新求解。V1–V5 是 13.5 nm、252-cell、80 端口的旧 p4 严格粗逆；V6 起是 0.7 nm、384-cell、p3、40 端口的微型三维缺口模型。两者的物理对象及门限不同，不能拼接成一条原尺寸成功轨迹。Schur／native 衡量不同原方程表示下的不平衡；散射场误差衡量扣去背景后的实际信号是否恢复。

| 轮次与证据入口 | 已尝试／实际结果 | 已否定的有限命题、未运行或仍未知 |
|---|---|---|
| [V1](response_v1.md) | F0 环境／协议准备，当时共享资源阻塞 | F1–F5 当时未运行；不能把当时等待当作今日 blocker |
| [V2](response_v2.md)、[逐 RHS](outcomes/records/strict_rhs_metrics_v2.csv) | B0／线性／NN 均仅零 RHS 通过，非零各 0/15；物理 A4 残差约 0.998655／0.998262／0.998456，对应门限 1e-10；实际训练 300 epochs | rank128 表示 oracle 有部分覆盖，不等于严格逆；F5／p6 物理解未准入 |
| [V3](response_v3.md)、[历史](outcomes/records/full_residual_history_v3.csv) | 几何重叠单元块＋80port，物理 native 0.891958，另两项 0.935862／0.932011；仍 0/3 | 这个局部规格不够；不是所有局部预条件均无效。新 seed420620 池未消费 |
| [V4](response_v4.md)、[六项](outcomes/records/two_level_comparison_v4.csv) | 固定局部＋OLDPOD／ERROR 两个 rank128 空间，各 256 步仍 0/6；物理 A4 0.998588／0.999864 | 未取得严格粗返回；新的 fresh 终测未解锁，无新 NN 训练 |
| [V5](response_v5.md)、[覆盖](outcomes/records/coverage_v5.csv) | 12 状态、192 单次修正审计；物理 OLDPOD 剩余残差比例 0.9990665，误差比例 0.2216303 | 误差表示≠残差消除；端口单项小 LS 改善仍不够。[review v3](review_report_v3.md)关闭旧 p4 路线，port-only augmentation 未执行；不重开固定 Q 系数网络 |
| [V6](response_v6.md) | 新神经 FE trace 接口／几何矩验证 | 真实三路线受当时 0.7 nm 材料缺失阻塞；该 blocker 已在 V7 解除 |
| [V7](response_v7.md)、[比较](outcomes/records/neural_fe_comparison_v7.csv) | 真正网络训练 Schur 0.913263、散射误差 0.66125；自由 FE 优化 0.797339／1.00826；LSQR 0.0716026／0.999953；三者全失败 | 梯度接口可用不等于网络能合格求解；REF7 是同离散参考，非连续收敛。旧 NN 末态是否为 optimizer 接受点不能事后猜造 |
| [V8](response_v8.md)、[缩放](outcomes/records/scaled_lsqr_comparison_v8.csv) | 列尺度 LSQR Schur 0.0682833、散射 0.998598；batch8 等价闭包微基准约降时 48.55% | 缩放未恢复场；batch 是同函数实现加速，无新增训练／完整求解加速，不再扫 D |
| [V9](response_v9.md)、[场分量](outcomes/records/field_error_components_v9.csv) | NN7 散射形状相关约 0.999809，但幅值比 0.457259；LSQR8 幅值比约 0.003671 | 冻结诊断，无新候选；仿射恢复误差必须扣掉特解，不可凭低 loss 称场准确 |
| [V10](response_v10.md)、[四候选](outcomes/records/candidate_comparison_v10.csv) | 幅相／训练 hidden 固定头／随机 hidden 固定头／精确40port闭合均失败；B1/B0 Schur 0.797694／0.797324；C 散射 0.697842 | 同固定空间线性头不等于学习 hidden；参考拟合约 1e-3 仍非资格且不能用于在线求解。curl／mass 抵消不是全谱或唯一根因证明 |
| [V11](response_v11.md)、[制造回收](outcomes/records/manufactured_recovery_v11.json) | QR 稳定头，小系数回收通过；大系数一次修正后 2.8952e-8 仍超过 1e-8；真实回写差 3.9598e-8 | 真正 VarPro FD／隐藏更新 **未运行**，不能记作训练数值失败 |
| [V12](response_v12.md)、[梯度](outcomes/records/fixed_head_gradient_checks_v12.json) | 固定头真实 FD 差 0.0635／0.0760／0.1742，大于 1e-5；8 个函数值试探无接受 | 优化未准入／有限试探为负；不是合格梯度下长训练失败 |
| [V13](response_v13.md) | JVP/VJP 与线性化修复后，1 次 hidden＋head 联合接受，loss 相对降约 7.15e-7；散射约 0.734256 | 存在真实学习更新，但没有有用求解增量；不把“接受一步”当成功 |
| [V14](response_v14.md) | 正交 trace 坐标降低大系数回写问题，10 状态 0/10；loss 降约 0.088922%，Schur 0.797367 | 坐标稳定化没有扩大空间，未证明完整 hidden 优化有效；不再只换同空间坐标 |
| [V15](response_v15.md) | 等维 local NN／poly 与联合空间：联合 poly Schur／散射 0.517714／0.283235，联合 NN 0.579986／0.766071，8 状态全失败 | 固定特征非训练；GPOLY/GNN 共用 G0 神经随机特征，GPOLY 不是完整非神经基线。有限比较偏向 poly，不否定全部学习空间 |
| [V16](response_v16.md) | 真正全空间 LSQR：plain 4096 步 Schur 0.069419；两增强库发生 PSI 受控停止 | scalar 进度 816／85 不能替代保存向量 256／0；资源停止不是同预算数值失败，未训练网络 |
| [V17](response_v17.md) | 持久递推恢复：GP/GN 6347／6119 步 Schur 0.00049022／0.00059448，散射 0.00026516／0.00024920 | GMRES 完整 z／port 重复拼接导致 0 完整周期，是实现失败，不能否定 GMRES |
| [V18](response_v18.md) | 修复后 G64/G256 与继续 LSQR 真正执行；GP-R 散射 8.07999e-5 已小，但 Schur 1.46308e-4、功率差 1.58806e-6 仍失败；0/8 | 场单项通过不授予完整资格；GN-R 散射约 1.00199e-4 也不能四舍五入为通过 |
| [V19](response_v19.md) | plain／保留3方向 LGMRES 各64调用；GP-L Schur 9.67833e-6，功率差 1.78553e-6；0/8 | 更多校正改善原方程，但功率未合格，无新神经训练，不无限延长旧预算 |
| [V20](response_v20.md) | 固定 p3 ILU0／40port，4周期降幅 0.262%／0.430%，低于无PC 2.956%；0/5 | 该不完全因子规格缺少收益；冷起点／迁移未运行。明确存在全局 p3 incomplete factor；交付窗口超时历史保留 |
| [V21](response_v21.md) | class64 等价完整作用 44.5365→23.4719 s；GCROT C 112调用 Schur 2.52812e-6、native 9.80413e-7，功率 1.71964e-6；0/5 | 工程降时约47.3%不是同精度求解加速；共同16调用 C 不优于 B。B 读入多余旧方向的边界失败仍保留，不能归为网络收益 |
| [V22](response_v22.md)、[投影](outcomes/records/offline_warm_error_v22.json) | 真正 p1→p3 FE 传递，Galerkin 原 p3 粗矩阵；warm PC4 Schur 2.5143e-6，zero32 0.00411726；0/4 | 误差平方能量覆盖约98.99%不代表残差可消除；存在全局粗 LU。不是重新离散一个 p1 Maxwell 解 |
| [V23](response_v23.md)、[候选](outcomes/records/candidate_comparison_v23.csv) | 固定同 T 的 image-QR 数学资格通过；warm4 Schur 2.507714e-6，zero8 0.0681132；0/6 | 精确最小残差单次修正仍几乎不动 warm；不重做同 p1 空间测试函数、scalar-tau 或延长旧周期 |
| 本地 [V24 阶段记录](response_v24.md) | 八块原主子块 LU＋可选 image-coarse 已实现、小测试有记录；正式四路在本节快照未运行 | 新信息尚不存在；必须区别 `NOT_RUN`、数值负结果与准入／服务失败；以下是对未完成合同的澄清 |

旧 p4 闭环、后来的神经 FE trace、固定特征／直接线性头、Galerkin／image-QR、全空间迭代是五类不同路线。已有证据不支持神经收益，但也没有完成“所有网络都无效”的实验。历史未运行还包括 seed420620 fresh pool、原 F5／p6 物理解、新 p4 enrichment、原尺寸 0.7 nm 的精度与规模资格；本轮不把这些补成自动执行清单。

### 10.3 V23 独立重算：通过的是构造，不是完整解

本审阅实际重跑 [原始字段 checker](../../benchmarks/check_task042_p1_image_records.py)，结果为 image/PC qualification true、6 states、0 passed。另独立遍历 [240 行逐通道功率](outcomes/records/per_channel_power_v23.csv)，重算 `abs(power-reference_power)` 并与候选最大值核对，六状态一致。这里重算的是记录的差值与 Gate，未重新由 FE 场积分功率；源场的可信度仍依赖其绑定的历史 FE 验证链。

| 状态／起点 | Schur，限1e-6 | native，限1e-6 | 散射E相对差，限1e-4 | 最大逐通道功率绝对差，限1e-6 | 失败通道 |
|---|---:|---:|---:|---:|---|
| V21-C-FINAL，warm父点 | 2.5281170328e-6 | 9.8041334638e-7 | 7.8160803891e-5 | 1.7196446511e-6 | bottom (0,0,s) |
| D-G，单次Galerkin | 5.7895868335e-5 | 2.2452236677e-5 | 7.7824459122e-5 | 1.6183747791e-6 | bottom (0,0,s) |
| D-MR，单次像最小残差 | 2.5278129643e-6 | 9.8029542773e-7 | 7.8160796654e-5 | 1.7196493144e-6 | bottom (0,0,s) |
| M-FINAL，warm4 | 2.5077143653e-6 | 9.7250111386e-7 | 7.8059353814e-5 | 1.6997314644e-6 | bottom (0,0,s) |
| Z-CYCLE4，zero4 | 0.06907817137 | 0.02678877608 | 0.9985383903 | 0.009406737813 | top (0,0,s) |
| Z-FINAL，zero8 | 0.06811317716 | 0.02641454768 | 0.9891432988 | 0.009105690357 | top (0,0,s) |

其余 augmented、独立 total-native、恢复、selected E/H、curl、40 个复振幅、R/T/A/A_volume 和能量 Gate 继续分别核对；表格突出足以否决完整资格的真实超限项，没有用 native 单项替代 Schur。以上功率全部 `UNQUALIFIED_DIAGNOSTIC`。

误差能否写进某个空间，与那个空间能否纠正当前方程，是两个问题。令 A 为原闭合 trace 算子，T 为已有低阶 trace 方向，`AT=UR` 且 U 列正交，`J=T R^{-1}U^H`。理想算术中固定该空间一次能够去掉的残差平方比例为：

```math
\eta_{AT}=\frac{\|U^H r\|^2}{\|r\|^2},\qquad
r_{MR}=(I-UU^H)r.
```

V22 的 98.99% 是**误差在 T 中的平方范数表示量**；原方程作用后的两部分约各 5.12e-4，强烈相消才得到约 2.09e-7 残差。不能把它解释为 J 可消除 98.99% 的当前残差。由 [V23 同向量记录](outcomes/records/coarse_compare_v23.json) 重算：warm 残差范数 2.090203601963259e-7→2.0899522031671444e-7，仅减少 **0.0120275%**；平方比例约 **0.0240535%**。同空间 Galerkin 反而把范数放大约 **22.9008 倍**。zero 单次 MR 减少约5.21%只是单步结果，zero8 仍失败。以上不构成 fine 条件数或全谱结论。

### 10.4 V24 为什么仍有新信息，以及它不能证明什么

局部完整解让每次修正先照顾一组相互耦合的有限元未知量；粗校正再处理残留中已有全局方向能看见的部分。它改变的是**全空间修正 L**，而非再次更换同 T 的测试范数，因此与 V22／V23 有区别，也不同于 V3 的旧物理、单元重叠小块及 V20 的全局自然顺序 ILU0。

```math
A_b=E_b A E_b^H,\quad L=\sum_bE_b^H A_b^{-1}E_b,\quad
B=L+J(I-AL),\quad D=L^{-1}=\operatorname{blockdiag}(A_b).
```

组合路线单次残差满足 `r_L=(I-AL)r`、`r_B=(I-UU^H)r_L`。在已验的浮点误差范围内，粗校正不能增加**同一次局部修正后的二范数残差**；但这既不保证整个右 PC 可逆，也不保证 GMRES 多步更快、场／功率更准确。原 §5 的 `D_L=U^H D T` 及其相对最小奇异值资格仍必需，不能用旧 `U^H T` 替代；二维奇异反例继续保留。

四路可分别回答：L 能否纠正 warm 的尾部困难；L 能否从 zero-trace 恢复散射；J 对 **L 之后**的残差是否额外有用；额外原作用、投影与三角解是否值得。可以在已有 PC 调用中记录 `||U^H r_L||²/||r_L||²`，只作该次残差可消除量的解释（r_L=0 单列），不额外新建全局谱／参考投影实验、不增加预算。这比重测 `P_T` 的误差覆盖更有信息。

LW/LCW 必须独立取同一 V21-C-FINAL；LZ/LCZ 必须独立 zero-trace。端口／内部特解依原 b 恢复，zero-trace 不等于所有未知量强置零，也不等于从网格开始的 fresh 端到端求解。暖解依赖的旧特征、LSQR、循环和准备成本不能消失。**V24 没有训练网络，局部 LU／p1 空间／QR／Krylov 收益均不能登记为 NN 增量。**

### 10.5 两项必须先处理的执行缺口

**P1-A：五个因子读取进程与多轮轮转不相容，会产生偏置预算。** [queue](../../src/runners/local_block_queue.py) `solve()` 首轮 LW4→LCW4→LZ4→LCZ4 每次启动独立进程；[load_local](../../src/solvers/local_block_study.py) 每次增加 `factor_readers`；[window](../../src/solvers/local_block_window.py) 上限为5。四路均达到续行门限时，本审阅用 AST 隔离该函数、惰性替身替代运行，实际调度为 **LW4、LCW4、LZ4、LCZ4、LW8**，随后其余全部因5次上限停止。复现输入、输出和脚本全文在独立审阅记录中；没有数值执行。

这首先是原合同“进程上限”和“多轮轮转上限”之间未解决的冲突；实现确实执行了上限，不能简单斥为擅自少跑。**澄清为：本次未完成 V24 只做四路各首4周期；取消自动第5次 LW8 和后续16／32周期扩展。** 5个 reader 的总上限保持，第5个只供已定位、原合同允许且实际必要的恢复／修复，不能当作单一路线加预算。若需更多对称周期，必须先审首块证据，不能用增加 reader 数或刷新窗口静默扩展本轮。warm10%／zero20%保留为研究进展指标，不再作为本轮继续授权。

**P1-B：失败 SETUP 的早置位标志可绕过公共准入。** [setup](../../src/solvers/local_block_study.py) 在 `old_new_S_SH_pairs` 配对前就写 `local_qualified=True`；后续 original/class64 不一致会抛异常。[stage wrapper](../../src/runners/local_block_pair.py) 把 partial result 以 `status=FAILED` 保存，父类 `finish()` 仍发布索引；reader 核对 hash／plan 但不检查这些公共 Gate。下次 `solve()` 直接复用已有 SETUP，仅检查这个布尔值；独立 route 入口同样如此。本审阅的惰性复现给定 `FAILED + local_qualified=True + composite_qualified=False`，得到 **LW4、LZ4 被 dispatch**。这证明失败记录可进入下游调度，不声称真实坏场已经运行或被接受；后续周期审计不能替代前置准入。

执行者须使队列和独立 dat 两个入口均验证一个明确的 **local-ready 证据集合**：分区与成员身份、局部原主块配对、因子安全、局部 solve／线性资格、原 S/Sᴴ 与 class64 配对均完成且可信；重复读取不能仅信旧布尔值。失败原因和原 partial artifact 原样保留。可用明确阶段证书或推迟置位实现，具体代码选择由执行者负责。粗层文件缺失／D_L不安全只取消 LC，**不能误伤已完整通过公共 Gate 的 L**；因此不能粗暴地把任何 composite 失败都当作 local 失败。

新增最小控制流回归应覆盖：四路首块均可行时完全对称且不再 LW8；带 true 标志的公共 SETUP 失败在 queue 和 standalone route 均拒绝；只有粗层失败时 L 仍可行；旧失败记录的重入保持原计数／时间，不重建已消费对象或改坏证据。小测试通过后提交 clean 实现再进入既有正式入口。本审阅不修改这些源码。既有28项测试覆盖了算子与短接线，并未排除这两条调度／重入路径。

### 10.6 给执行者的唯一有界下一任务

**先修上述准入／调度缺口并做最小回归，然后只在原窗口尚有效、现场确认没有另一个 Task042 actor 时，完成 SETUP→LW4→LCW4→LZ4→LCZ4→冻结→唯一 VERIFY。** 不因本报告、余额恢复、服务中断或新 commit 重置 campaign。已有 source 若在运行中，先只读观察与保全，不改变其 HEAD、重启或重复启动；在安全阶段边界应用澄清。已经真实执行的周期和费用全部保留，不为凑齐对称表重复前缀。

| Gate／阶段 | 验收及停止条件 |
|---|---|
| 时间 | start固定 `2026-10-02T12:04:23.502588Z`；heavy-stop `15:34:23.502588Z`；交付截止 `16:04:23.502588Z`。每次读真实 UTC／monotonic／boot_id。若已到期，仅收口记录、清场、提交，**不启动新窗口**。晚交付明确标注，不隐去 elapsed |
| 修复 | 仅两个已定位控制流缺口；仍受原全批4根因、每次900 s、累计2400 s及原窗口约束。已有 R01/R02 及费用继续计入，不通过改 review 编号清零。未完成修复则依赖数值路线不准入 |
| 容量／安全 | 固定8块／complex128，不加块、不重叠、不shift／drop／改精度；A+LU载荷1,354,430,592 B≤2 GiB，实际同时规划≤8 GiB；整树warn12/hard16 GiB、ownswap0和全部共享余量／PSI／清场规则沿原§8。规划不代替现场树峰 |
| Local资格 | 每块原作用≤1e-10、solve相对≤1e-8／operation≤1e-12、rcond1估计≥1e-12；重复／复线性≤1e-10、完整非互伴端口／共享cell／Floquet贡献、只读reload及原/新S/Sᴴ配对合格。公共错误停止全部依赖，不借 local flag 绕过 |
| Composite资格 | 已有T/U/R身份与原像配对、D_L一次固定SVD比值≥1e-12、已有整块分辨率检查；3个固定复见证恒等式≤1e-8及复线性≤1e-10。失败则LC两路NOT_RUN，L两路仍按自身资格进行；不删秩／伪逆／调tau救场 |
| 四路工作量 | 每路最多4个GMRES256周期；第一原方程通过点单独保存，最多额外2周期仍包含在4周期内；不因warm失败取消zero。历史V22/V23对照按hash复用，不重跑旧PC。时间不足时报告缺项，不把顺序更早路线多算的终点当公平胜出 |
| 原方程／恢复 | Schur、native、augmented及规定端口各≤1e-6；独立total-native另验；恢复／identity≤1e-10、slave=0。重复作用差与连续两次原rho上升按原§6停止。禁止仅callback或info授予成功 |
| 场／物理 | 冻结后唯一VERIFY读取REF7；total/scattered E/H/curl、selected复场与40复通道≤1e-4；R/T/A/A_volume差≤1e-5；每通道功率差≤1e-6；能量≤1e-5。任何必需项缺失即NOT_QUALIFIED；功率保留通道、极化、reference plane，不只报总R/T |
| 总计数 | 原§8 S+Sᴴ45000、L8 25000、LU solve210000、三角pass420000、R14000、audit160、field12、1次8块装配与因子／1次D_L SVD上限不增加；不能以首4更短为由增加其他试验 |
| 收口 | setup／四路／VERIFY 已结束或触任何上限即提交response_v24及原约定证据；缺失写清NOT_RUN原因，无需填满预算。没有全部严格资格则无official结果；即使全部通过也仅micro同离散资格 |

这种缩窄是为了得到可解释的首轮对照，不是声称4周期足以证伪所有局部方法。研究正信号可按首4周期 warm≥10%／zero≥20%的原rho降幅报告；达到该信号仍不是物理通过，更不是 NN 的20%增量门限。比较至少给出共同周期、累计原S/Sᴴ前缀与完整wall：LC每次PC比L多一次fine A，不能按相同迭代次数直接宣称效率更高。

### 10.7 所有因子、全局 QR 与完整费用必须显式入账

| 对象 | 实际／推导成本与必须披露的边界 |
|---|---|
| 既有小块凝聚／40port | action packet 的局部消元与端口小分解已经是求解链的一部分；“未使用全局p4 LU”不等于没有精确逆或因子。包括建立、作用、恢复、条件估计和释放 |
| V22粗层 | T为18144×1248、217296非零；粗矩阵／LU／pivot约49,845,120 B。原FE传递构建历史约495.33 s，不能从V23/V24部署fresh总账中免费略去 |
| V23全局薄QR | W与U各362,299,392 B，R24,920,064 B；至少U+R387,219,456 B常驻。W构建61.1547 s、QR24.9366 s只是setup子项，不替代完整131.5988 s；含全局薄QR，不能叫factor-free |
| V23本批正式账 | 五个正式阶段合计1061.43058951 s，最大采样同时树峰2,061,123,584 B；M约299.147 s、Z约563.193 s、VERIFY约55.062 s。它不是某一warm方法从零得到解的总时间 |
| V24八块 | 行数2913/2676/2289/2076/2439/2220/1863/1668，单套A或LU677,215,296 B；A+LU约1.261 GiB，pivot另计。规划同时5,709,615,024 B仍是derived。真实factor／reload／gecon费用未测，不填写零成本 |
| V24每次修正 | L8为8个LU solve＝16个三角pass；LC另加fine A、Uᴴ乘法、R三角解与T乘法；hash扫描／mmap缺页／只读重载／私有pivot工作区／缓存／Krylov／输出全计。嵌套inclusive计时不可重复相加 |
| 全链费用 | V6起formal累计75,124.917593 s是历史研究账下界，不是一遍合格求解成本；暖点所有上游构造／训练／迭代与IO须列依赖。缺少per-solution拆账就写unknown，不拿本批尾部校正秒数声称48h达标 |

原尺寸放大尤其不能沿用微型低内存印象。以 n 为trace行数、r为粗维数，固定8个稠密块的A+LU存储为 `32*sum(n_b²)` B，均衡时约 `4*n²` B；factor工作量随 `sum(n_b³)` 增长。全局U需 `16*n*r` B、R需 `16*r²` B，薄QR工作量量级 `n*r²`。若固定网格阶次和全域p1空间使r随n增长，仍会出现平方存储／立方setup，不能假定r永远1248。增加块数虽能限制局部规模，却改变方法及跨块收敛，属于另一个尚未资格化设计，不由本轮自动授权。

这些是算术规模模型，不是实测目标资源预测；还需端口数、单元内部、Krylov256、完整场恢复和分布式通信／共享存储生命周期。完整峰取同一时刻进程树／适用cgroup聚合，不能把各阶段峰相加或只报网络权重。2 TB应显式记录实际字节口径，不能与2 TiB混用；48h=172800 s必须覆盖一遍必要的准备、训练／推理、精确校正、审核和IO。现有数据不足以证明这些上限。

### 10.8 失败后的有效替代分析，以及神经路线的下一道门

| 首块结局 | 可支持的结论／有效下一分析 | 不应自动执行 |
|---|---|---|
| 公共局部Gate失败 | 定位是原主块装配／Floquet贡献／因子安全／class64还是重载身份错误；保留失败输入与已有见证。真实小rcond是该规格的数值限制，不是任意shift的许可证 | 换精度、加重叠、增块、回全局p4；以不同算法掩盖错误 |
| 只有D_L失败 | L仍可评价；表明当前粗与局部组合缺乏可逆安全性，与“空间能表示误差”不同；用已有D_L数值和反例作代数解释 | 调tau、截秩／伪逆、再做同p1测试空间扫描 |
| L改善且LC无额外收益 | 此固定image空间对局部剩余残差不够有效，或额外成本抵消收益；用已有r_L投影量和每作用／wall分账区分 | 把原T再换测试方式当新路线，继续延长LC旧预算 |
| LC优于L但均不合格 | 只证明当前微型例上存在局部—粗层协同；分析未过的是哪条原方程、具体场分量或通道 | 用一次修正、native通过或降幅足够授予完整成功 |
| warm有效、zero无效 | 这是尾部修正器，不能替代从头求解；检查warm依赖和zero残差／场轨迹，不混计起点 | 把warm速度推广成cold部署能力，免除上游成本 |
| 四路无实质进展 | 收口固定八块＋既有image组合；只读已有残差／块界耦合、成本和尺度模型，给出缺失机制与下一方案所需的最小证据 | 无限周期、再扫scalar-tau，或让NN在已失败固定空间中只猜系数 |
| 有完整micro通过 | 才能讨论该路线能否成为有效非神经基线，以及放大后的局部因子／全局投影成本是否可承受 | 直接升级production、启动原尺寸、宣称连续精度或神经成功 |

若需要真正不同的后续研究，优先从已保存残差与费用判断应改变**局部与跨块通信能力**还是**实际可消除残差的方向集合**，给出数学接口和容量论证，再申请单一有界实验。学习局部修正映射、学习新的粗方向都是尚未证明的候选；当前证据不能保证它们能修复失败。可分析目标是能否减少精确局部解／全局方向构建或迭代总成本，同时保留完整原FE校正与审核；不能仅因输出来自MLP就把传统线性组合包装成新收益。

**后续神经合同固定为20%，覆盖早期 task §5 的10%条款，并与 review v3 §7一致。** 在相同正确性前提下，与**最佳合格非神经路线**比较，完整端到端耗时或完整同时峰值内存至少改善20%，另一项仍合规；才可声明NN增量。只有神经路线通过而对照未通过，可以说资格不同，但不能绕过同正确性比较直接授予这个性能增量。共享负载不可比、完整账缺失或误差不同则结论为未证实／inconclusive。

未来若申请学习实验，至少需要：明确实际训练参数和学习数据；按完整problem／轨迹分离训练与终测；同容量随机特征／确定性poly或其他最佳传统路线；学习模块移除／替换消融；相同硬件线程与匹配输入；含数据生成、训练、模型加载、推理、全部精确校正／setup／审核的N=1成本。多RHS摊销只在实际需求和break-even证据存在时另列，不能掩盖N=1。可比条件下预登记至少3组配对测量及噪声范围；共享干扰不可控就不报20%胜出。此处是**下一轮立项门槛，不授权本次训练或性能campaign**。

### 10.9 原尺寸资格与 dot 分工

最终对象仍是**原尺寸、0.7 nm、完整三维有限元**。旧尺寸锚点为50×25 nm周期、z=-10..130 nm、块高120 nm；后续真正非可分几何的精确输入、材料、入射、通道与精度要求仍须绑定同一目标记录，不能静默拿微型缺口替代。当前micro计算域仅1.4×1.05×1.4 nm；同为0.7 nm并不代表原尺寸问题已经解决。

| 必需原尺寸资格 | 当前状态 |
|---|---|
| 全三维物理、双周期约束、完整DtN通道及原方程 | micro有接口／参考证据；目标尺寸未资格化，40通道不能直接外推 |
| 独立离散精度／p-h及端口截断误差 | REF7仅best available discrete reference；没有目标精度收敛，不能凭micro p3或一次同离散通过替代 |
| 从头完整解与全部observable vector | V23候选0/6；V24尚待真实证据；原尺寸NOT_QUALIFIED |
| 完整峰≤2 TB、端到端≤48 h | 缺目标n／通道／factor／QR／作用和迭代实测校准；NOT_QUALIFIED |
| 神经20%额外收益与泛化 | 未建立最佳合格非神经同精度对照及完整成本；NOT_DEMONSTRATED |

dot 继续自己的 `task40extra_dot_parallel_cloud`，负责完整三维参考逆、周期分块、共享存储和规模验证。本任务只使用经过双方身份／hash匹配的算子、参考和成本证据接口，研究特定局部／粗校正及学习模块的独立价值；不复制 dot 的完整参考逆／MPI规模campaign，不修改或合并其分支。报告也不预先宣称 dot 已交付尚未读取的能力。未来原尺寸论证要组合可信证据，不能把两任务各自的局部成功拼成一遍未经执行的完整成功。

本审阅交付仅本报告更新和轻量证据索引；保留全部旧 review／response／原始失败。文档链接、公式围栏、表格和diff做本地检查；GitHub精确页面视觉为 `NOT_VERIFIED`（网页读取未取得渲染证据），不声称CI或新PDE通过。执行者拉取后先检查最新现场状态与本节缺口，按原窗口收口；仅推送本任务分支，完成后等待正式结果审阅，不合并master。
