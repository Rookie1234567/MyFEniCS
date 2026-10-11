# Review V69：进入一次有界接口迭代，停止继续依赖全局细层LU

## 0. 裁决、目标和唯一身份

**V70按pass_with_qualifications接受：无全局K装配、独立无全局S作用、完整场严格再现均通过；没有获得连续精度、端到端加速或原尺寸2TB/48h资格。** 授权 **V71_BOUNDED_TRACE_ITERATIVE_PILOT**：只读复用V70局部包，在完全相同的p5/828离散上，完成一次无全局细层K/S/因子的两层预条件FGMRES试验。局部因子和固定上限的小粗因子允许且全部收费。不是再做一份全局直接解，也不等待连续精度闭合才检验同离散求解成本。

要消除的blocker：全局细层LU仍主导求解时间和峰值；已有无S作用尚未被完整迭代求解消费。先保证反复调用的原作用可承受，再检验一个固定、可失败的PC，不扫描低阶粗逆/ILU，不把测试条数当进展。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-11 Asia/Singapore
reviewed_HEAD          = bc8decc7b30b4e9b30e089c98300d4526bab6028
latest_result_UTC      = 2026-10-11T01:28:16Z
latest_result_local    = 2026-10-11 09:28:16 +08:00
latest_response        = response_v70.md
previous_review        = review_report_v68.md
previous_review_commit = 7eb964ce194748d5c3510a4dc1798e312282aa57
previous_review_blob   = 997db3c9238437ec632bc66ebdb711843e279165
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V71_BOUNDED_TRACE_ITERATIVE_PILOT
required_response      = response_v71.md
ordinary_default       = UNCHANGED
NN_training            = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

明确覆盖上版“只做两次ACTION、不研发PC/迭代”的阶段限制，只批准下述一个候选。原目标仍为真空0.7nm、原50×25nm周期/z=-10..130nm、任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN、复E/H/衍射/R/T/A/独立体吸收；完整必要流程≤172800s。十进制2e12B是整机内存，须留系统余量。本批s=7/135有限问题和串行实现不是目标规模或波长鲁棒性资格。

## 1. 已审事实与本次取舍

已读取冻结HEAD的root/docs规则、仓库原则、task身份、最新response/summary、V70改动和实际局部包/迭代/费用源码；任务目录未发现独立supplement或同名V69。上一完整review读取会话原件并核对远程同blob。检索只用于定位旧文件，技术判断采用当前分支文件，不以默认分支搜索结果代替执行HEAD。未SSH、未重跑工作站PDE或大型场数组。

依据：[回应](response_v70.md)、[汇总](outcomes/summary.md)、[完整费用](outcomes/records/resource_costs_final_v70.json)、[部署口径](outcomes/records/deployment_cost_boundary_v70.json)、[局部包](outcomes/records/assembly_time_checkpoint_v70.json)、[ACTION](outcomes/records/trace_action_qualification_v70.json)、[完整比较](outcomes/records/paired_results_v70.json)。实际数值source为0490af3085f32940787f0a02f0d801578ab87b73，不以文档HEAD代替。

| recorded measured | V70结果 | 裁决 |
|---|---:|---|
| 独立FE / retained含828端口 | 1943745 / 1177293 | 767280内部全部恢复 |
| 新S stored / exact nonzero | 266599917 / 266599916 | 与C5同存储项，无新增nnz收益 |
| 独立原式true / port | 3.35623167109e-10 / 5.87622187275e-16 | formal1e-6 PASS，direct1e-10 FAIL单列 |
| 新解/C5散射E/H | 7.40937013119e-12 / 7.4048021928e-12 | 严格同离散PASS |
| BUILD / SOLVE sampled峰 | 18.4390258789 / 111.277801514GiB | 构建低峰不等于全流程低峰 |
| BUILD+SOLVE必要成功分段 | 22313.3740884s | 约6.20h，不是目标原尺寸 |
| prepared-start SOLVE / numeric | 12666.5476045 / 8857.6219858s | numeric约占SOLVE70%，计时嵌套不重复相加 |
| 体核+局部LU+ADD+块IO | 8560.4155957s | 内部细分计时UNKNOWN，不猜JIT或LU占比 |
| 完整体积分输出 | 2963.41044207s | 仍计入必要流程 |
| 无S首次 / 第二次作用 | 101.378834659 / 34.456206552s | 首次含实际类读取；不能拿第二次冒充冷成本 |
| ACTION误差 / 局部类实际读取 | 1.64775892845e-15 / 3513173560B | 已可用的原作用，不是迭代已通过 |

当前约10660个精确类、25576个映射；已保存类内Schur和局部LU。热作用不能再默认“每cell还在重新构造Schur”。类数据约3.51GB低于4GiB缓存限，**没有证据把34.46s归罪于容量不足或LRU颠簸**。应计量实际metadata、gather/scatter、稀疏E重建和边界局部三角调用，不先指定根因。

历史P6/L5全域散射E/H为1.14449e-4/1.23013e-4，240点约9.56042e-4，仍FAIL1e-4；p5的828→1188有限增量已通过。这些物理资格不变，不重跑模式、点值/界面诊断或p/h扫描。V70普通故障已修复并完成主队列，不再追查历史SIGTERM。

## 2. 冻结科学问题及数据权限

仍为25576tet/1000个NOTCH tet、p5、828模式(m±11/n±4、上下侧×s,p)，完整Cκ、原入射/载波/材料/网格。κ=(8.94046081729244,0.7821889682108057,0)，λ=0.7nm，grazing1度/azimuth5度/s，幅值1；Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1。材料SHA256为55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2；网格为c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c。

生产只读V70实际sealed local_packet及q47/q63边界，指针从assembly_time_checkpoint/retained_operator_contract读取并一次核对COMMIT、schema与成员身份。不得重建体核、加载旧global K/S、使用V70解作初值/RHS/选区，或加载global fine factor。compare-only消费者只读旧固定作用向量；完整参考场在新候选冻结后才评分。无全局K/S约束同时覆盖PC构建，不能在PC里偷偷装配完整矩阵再切块。

本批是prepared-start求解器试验。父BUILD费用保留，不能将复用包称为从几何开始的免费生产计算。安全缺失的父资产如实ASSET_BLOCKED，不重新做数小时已资格构建来补一个文件。

## 3. O：把原作用变成可反复调用的热路径，不另开优化campaign

复用[tetra_assembly_packet.LocalTracePacket](../../src/solvers/tetra_assembly_packet.py)，其现有class中已经存Schur。只允许等价的数据组织优化：初始化一次解析cell/class、retained ids和稀疏E；冻结后缓存映射、共轭映射和实际非零内部port cell清单，避免每次重开map压缩文件、重新构建稀疏E或对无port单元重复切CSR。按精确class分组，用矩阵多列乘法/gather/scatter-add；同一global id的重复贡献必须相加。一次受控读取后的只读数组可复用，不能每次matvec全量重哈希；文件/身份改变则立即失效。

热态数值cache和映射合计≤12GiB，额外临时块≤2GiB。允许一次聚合完整tilde-C/tilde-D/tilde-H及其精确局部修正，以避免反复解同一Ci块；所有实际非零项保留，Ct/Dt/H仅加一次。该稀疏边界块不是global FE Schur，仍须单列字节和初始化成本；不得分配每cell的828×828库。局部Schur已有，不再预计算第二套同对象。

新旧作用在两固定complex128向量上分别按FE和port运算尺度≤1e-10；再保留一个非零内部RHS的recover/condense原式见证。只读旧ACTION向量作参照，不加载global S。记录首次读取、初始化、连续三次热作用、各cache命中、局部LU调用和scatter费用，全部调用计费。不重跑旧8cell/完整原式资格。优化目标90分钟；若新快路径不可靠，原V70正确作用可回退并据其真实速度执行有界迭代，不能只交微基准或放宽原作用。

## 4. P：唯一固定两层PC，不扫描“便宜的强粗逆”

### 4.1 为什么采用这个候选

预条件器先解一些相互重叠的小区域，再用一个有上限的低维全局空间传递跨区域信息。它不是原p4巨大精确逆的廉价替身，也不是已证明波长鲁棒的生产PC。本次是**当前相位四面体trace系统**的首个固定规模可行性试验，旧Task39低阶粗逆失败保留；不能因此承诺p2粗修正一定有效，也不能借“可能不够”永远不做一次完整试验。

参考[Maxwell两层Schwarz原文摘要](https://arxiv.org/abs/1711.03789)、[PETSc PCASM](https://petsc.org/release/manualpages/PC/PCASM/)及[KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)。文献的吸收、网格、粗空间条件不等于本案弱损耗/Floquet/DtN条件，以下不是继承其波数独立收敛定理。保留当前原算子，PC不改变物理材料或目标方程。

### 4.2 32个几何核区和有界局部因子

在当前物理包围盒按x/y/z的4×2×4等分构造32核区。独立边/面自由度用其实际几何实体中心、半开区间和固定几何键唯一归属；周期等价实体先按canonical代表计一次。每个核区向外取一层实际tet邻接的halo，x/y距离和邻接按周期处理。记录核区、halo和重叠比例；不根据参考场或迭代结果重分区。

每个patch的I_j是其halo内trace索引，R_j为取子向量，W_j只把核区owner的修正写回，保证所有FE trace恰好有一个写回owner。端口不复制到每个patch，全部由粗块处理；B_RAS返回的FE向量嵌入全retained向量时端口分量为零。局部矩阵B_j=R_j Ahat_tt R_j^T必须从**所有对这些行列有贡献的局部Schur**累加，包含halo外单元对主子块的贡献；不能仅把patch中心单元相加冒称原主子块。保留所有方向、MPC系数和实际非零，不阈值drop。

单patch≤80000行；超过时仅作事前几何二分最长物理轴(平手x,y,z)，至多64patch。此规则只控制资源，不重试重叠/参数；64仍超额则CAPACITY_BLOCKED。局部稀疏LU用现有合格后端，全部局部numeric/三角调用和总驻留内存分别计数。精确主子块理论上可能难解；不得自动shift、加吸收、伪逆或改变原排序来扫参数。实际数值不可解先区别实现故障与数学失败。

所有局部因子和粗因子的可靠symbolic估计双倍和须≤64GiB，并与全进程96GiB规划同时成立。可逐patch形成/分析、释放矩阵，冻结图和预算后再建所有因子；不能先建完再查总量。PC每次按固定顺序加性求解并restricted写回，不能因一个patch失败就把它替换为identity而称同方法。

### 4.3 固定p2粗空间及828端口，最多8192行

使用已继承的原960tet相容粗网格，仅构造周期N1curl p2空间与fine trace插值。预期独立edge/face实体1168/1952，p2自由度6240，含全部828端口后7068；这些是derived，实际MPC/mesh核对，不得凭数字补列。粗网格不做PDE或teacher求解，不读取旧p2场。

以真实Nédélec矩、方向/Piola、周期和父cell关系构造稀疏Z_gamma；不得按编号截断、用点插值代替边/面矩或对齐不同材料。Z=diag(Z_gamma,I_828)在**当前缩放后的数值坐标**中定义。使用原port_coordinate_scales的Ahat=L S R、bhat=L b；FE缩放为1、port列为identity时，先验证细/粗相同端口缩放与Z可交换。不能混用未缩放coarse与已缩放fine。

```math
E_0=Z^*\widehat S Z,\qquad Qr=Z E_0^{-1}Z^*r,
\qquad B_{\rm RAS}r=\sum_j R_j^T W_j B_j^{-1}R_j r_t.
```

E0从实际局部Schur和全部凝聚端口项做Galerkin累加；不是另一张独立p2体矩阵，不假定p传递与凝聚交换。无需对7068个列逐一调用全域action；禁止稠密N×7068的Z或S Z库。粗矩阵、因子、pivot和工作区允许但≤8192行，全部纳入局部/粗因子总预算。不能为提高收敛自动改p3/p4或增加coarse列。若以后目标模式数超过此上限，需要新的端口/粗空间设计，本批不放宽上限外推。

固定preconditioner为一次先粗后局部的乘法组合：

```math
z_0=Qr,\quad r_1=r-\widehat S z_0,\quad
M^{-1}r=z_0+B_{\rm RAS}r_1.
```

因此每次PC通常额外包含一次原作用，不能只按outer matvec计时。保留两组实际全域调用及一个小复数非Hermitian块回归：核区写回闭合、coarse Galerkin作用、Z复对偶、PC输入输出和非零port/RHS。低残差或参考场不参与选PC。这个PC没有已测的波长鲁棒性；本轮只测固定候选的收敛/成本，不宣称新发明了Schwarz。

## 5. I：一次真正的无细层全局因子FGMRES求解

复用[physical_retained_fgmres.py](../../src/solvers/physical_retained_fgmres.py)的PETSc MatPython/PCPython与retained向量生命周期，不复制求解器。原实现硬编码A6名字、2048步、8步恢复和物理停止门；只增加显式参数/evaluation-policy，旧默认不变。不要把当前tetra指标假填到旧A6字段，也不为满足旧controller重跑历史profile。

固定RIGHT FGMRES、restart32、max256；端口缩放与V70相同，retained系数从零开始，不使用旧解或旧global因子；恢复含固定内部特解，不将其说成全FE系数都为零。最多一次正式KSP.solve；确认为实现错误且尚无合格返回场时，可从最近合法retained状态续算同一方法，累计迭代/调用/时间不清零。不得因科学停滞再从零开第二PC或追加全局LU收尾。

每步只记录KSP估计残差/时间/实际A及PC计数；每32步、达到预设候选收敛和退出时，计算独立retained true residual并完整恢复原式。保存retained向量后再消费。固定停止目标为retained true≤1e-11且原true/native/augmented/port各≤1e-6，恢复/MPC/恒等式≤1e-10；独立direct1e-10继续单列，不借旧formal门提前宣布严格同离散PASS。

最多600次实际全域接口action调用，包括PC内、显式true、资格和续算；其中资格/计时目标≤12次。迭代数不是总成本。256步或6h迭代预算先到就保存最终候选并独立审核；不按第16/32步必须降低某倍的研究筛选过早停。若非有限、真实breakdown或安全门失败则停止依赖计算。最终残差未过，场/功率可保存diagnostic但不称official。

最终retained、full RHS和恢复packet先保存；退出KSP并销毁全部local/coarse因子及无用cache，记录RSS下降，再作最终全场恢复与输出，避免PC和后处理重叠驻留。候选冻结后才读取V70完整场。合格场须复现六场/原240点/物理参考面复通道≤1e-6；R/T/A/A_volume差≤1e-8、单mode功率差≤1e-9，每场独立能量≤1e-5。沿已合格同基系数先相减的差场算法，不校幅相、不换分母、不删点。若代数门过而同离散场门失败，保留不同资格，不按参考误差驱动再求解。

失败也必须交最终显式残差、完整候选、各阶段资源、可复现状态和原因。一次固定PC失败不证明所有迭代或NN不可能；但也不自动授权继续ILU/shift/coarse扫描。软件普通错误同轮修复，数学不收敛不当bug修到通过。

## 6. 实现顺序、继续路径和预算

顺序：身份/父packet → O热作用必要适配 → P局部及粗空间构造/资格 → I完整迭代 → 恢复/独立场和费用。O目标90分钟，P实现/资格目标2小时；成熟gather/稀疏矩阵/局部LU可复用[spectral_schwarz.py](../../src/solvers/spectral_schwarz.py)，但旧模块依赖完整edge矩阵及谱粗空间，禁止整体套用或运行其旧scan。新增数值核进src，runner保持薄配置。

若O快路径有bug，回退旧V70原作用，更新真实forecast后继续P/I；正确的cache/PC已形成时不要为了微优化重做。若coarse插值或局部PC真实不合格，只隔离依赖步骤，完成健康O和明确blocked证据，不能用identity PC或旧global factor伪装完成。P数学资格通过后必须执行I，不以“没有事先收敛证书”为由停在小测试。只允许固定候选，不扩大成多路径research campaign。

新14h总研发窗，科学有载≤12h，最后1h收尾。I累计≤6h，numeric建PC前用实测热作用和局部solve建立成本预测；为完整恢复/原式/六场积分输出预留≥4500s，当前输出约2963s不能按几秒估算。实现、读取、失败、重放、等待、IO全部计费，不刷新旧窗口；600次调用/256步只是上限，不保证能用完。

| 内存范围 | planning / warning / sampled stop | 约束 |
|---|---|---|
| O/预检/普通consumer | 64 / 80 / 96GiB | 不暗藏细层factor |
| P/I与同进程最终原式 | 96 / 112 / 128GiB | 局部+coarse双倍symbolic合计≤64GiB，cache≤12GiB，额外workspace≤2GiB |

96GiB是新研究规划上限，不是预计RSS。每个factor前用已驻留RSS、该factor双倍可靠symbolic、未建必要对象和2GiB工作区再准入；旧256GiB不得作为隐式后备。全细层global LU count=0，local/coarse LU count真实非零。局部pattern、稀疏Z、coarse、全部Krylov与恢复scratch都计入同时内存，不能只报最大的一个patch。

保持complex128/int64、原ABI、MPI1/math1/CPU1、GPU/Loader0、ownswap/OOC0，原PSI/cgroup/宿主/384GiB邻增长余量和物理核-SMT隔离、机器heavy锁；不得改邻任务或系统配置。一次自身数值actor，现有durable会话/停止先落盘复用。采样11.84s等历史实际gap保持；新实际gap另列，不把0.5s配置称连续硬峰。

新ignored≤32GiB、Task去重≤632GiB、free≥50GiB并留512MiB证据余量；父局部包不复制，不能删除旧失败/场腾空间。PC cache/可恢复状态原子保存，持久块身份变了才失效；不要将所有分段小matrix都装成全局S再保存。

普通API/shape/dtype/路径/写出故障累计修复重放≤2.5h；同根因两次无效换诊断或已授权正确路径，不第三次盲跑。不以bug个数交棒，不在代码commit或targeted测试通过后停等review。合法retained/全场已经保存，JSON/checker/文档只补消费；不因文档重跑I。原方程、ABI、数据身份或监督真实不可信先隔离，不绕Gate。

## 7. 向2TB/48h推进的验收与去重

本批最重要的分界线是：**没有全局细层K/S及其LU，是否仍能在可接受成本内得到同一份完整FE解。** 只完成热作用、只让残差下降、只完成局部因子都不是该完整资格。若正式门失败，仍可接受有用组件，但“迭代完成同离散解”必须标FAIL/NOT_RUN，不改成pass_with_qualifications掩盖。

成本分为父V70局部包构造、新O/P准备、新I、完整恢复/输出/独立审核、研究比较及失败。父BUILD包括旧S装配，当前没有单独packet-only冷成本，须保留这个成本边界，不能从父时间中猜扣掉S后给出完整cold速度比。与V70 SOLVE的12666.5476045s、111.277801514GiB只做有说明的历史观察；没有配平同精度对照不授生产加速比。

当前65条complex128 retained主向量按1177293维约1224384720B，尚不含其他workspace；这只是derived，不是PETSc实测RSS。原尺寸coarse/ports/patch数不能照搬当前7068/32并宣称robust。下一步若本候选通过，应选受内存与精度约束的中间尺度及分布式验证；若停滞，则根据最终残差及PC代价确定一次具体的Maxwell粗空间/局部传输改进，不自动多轮扫参数。全局直接coarse必须继续有界，不允许通过不断扩大粗问题回到旧瓶颈。

当前p/h连续准确性缺口另列，PC严格再现不使之通过。对任意三维生产需要可扩展coarse、分布式数据、流式DtN及可验证精度；本串行有限试验没有自动达到这些目标。

相邻分工已核对：task42extra_feinn_5nm@34ccdfa87b6682812570ef23e12dc22a02542e9b最新Review V42授权V43从同一Bloch-FTT状态续算，仍为NN；task40extra_0p7nm_engineering@c1a77d362d852d864668dcf5d43957880a6788df最新V24为q0 tile/32模式复用和体积行panel，尚无完整8-q/目标场；dot@15713d3e09b63f65511c7b7f61fa043fdb23dca5只读。Task42本批不训练、不开NN-V3，不移植邻支参考PC/CSR/端口构造，不发跨worktree命令。旧p2/p3/p4粗逆研究是经验边界，不将本候选称为新发现的通用强逆。

## 8. 入口、提交和一次交付

先核对branch/HEAD/upstream/origin/canonical/worktree及活跃actor，安全fetch/ff-only本分支；不reset/stash/clean、不回退、不改共享配置。实现和定点测试后提交clean source，validate，再运行。旧ordinary行为不变。只做新增热映射、patch/粗映射、复数PC与retained停止策略的targeted回归；不full pytest/CI、全仓索引/历史hash扫描，不重解FLAT/L5/C5/M5或重跑区域诊断。文档只一次紧凑检查；视觉未取得如实NOT_VERIFIED，不影响已可信数值继续。

下列入口须本轮创建，一个dat只表示一项明确工作：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v71_trace_operator_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v71_bounded_pc_setup.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v71_trace_fgmres_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v71_compare_verify_cost.dat
```

预检不暗藏PDE，PC_SETUP允许且必须记录local/coarse factor，但fine global factor为0；VERIFY不新增KSP.solve或factor。身份和每阶段预算绑定input_original/resolved/manifest/input-physical-source hash、环境/MPI/全部新artifact，不伪装成旧namespace通过Gate。

交付response_v71.md、outcomes/bounded_trace_iterative_v71.md及紧凑records：O逐项成本/正确性、实际patch/粗空间/因子库存、完整残差历史与每类调用、最终完整候选及原式/场/功率、费用/同时峰/实际gap、修复和未运行原因、retained_iterative_contract_v71.json及唯一下一pilot。全部失败保留；流水线“做完”与数值“通过”分开，不能只交微基准或预检报告。

只推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse；旧task/review/response/raw不改，summary/README/两总账短追加。核对remote完整SHA、clean/upstream、closed/active null、自身后代清场和锁释放后交付用户暂停。不merge、不改master/邻支、不自动开新窗口。
