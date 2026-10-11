# Review V72：停止重启与反馈续扫，用局部Maxwell-harmonic粗基完成一次完整对照

## 0. 裁决、blocker与唯一身份

**接受V73的实际执行、完整诊断场和负结果记录；R128完整256步没有解出原方程。B128在195步触发错误的旧600次实例门，只能评价已保存的192步候选，不能声称完成256步。该接线已修复，但现有趋势不支持专门重建39个因子补跑旧尾部。批准V74_LOCAL_MAXWELL_HARMONIC_COARSE：保持细层、38块RAS、粗空间维数和restart128不变，以一次局部齐次Maxwell延拓替换粗基函数的内部形状，完成一个新预条件器的真实完整求解。**

本轮消除的blocker是：简单p2多项式粗插值与现有局部修正没有形成有效的全局求解，增大restart或补粗反馈也没有取得合格场。现在检验粗基是否需要包含局部波动响应，而非继续增加内存、p/h、迭代步或网络。**粗空间不足仍是待检验假设，不是已证唯一根因。** 本任务属于求解器/粗空间研究；不改变物理方程或细层离散，不提高历史空间准确性资格。

```text
repository              = Rookie1234567/MyFEniCS
execution_branch        = task42_neural_coarse_inverse
canonical_worktree      = /home/fenics/Projects/NN-Lab
review_date             = 2026-10-11 Asia/Singapore
reviewed_HEAD           = b393ec0c2be86270a72ebaac8a02a73d05cf7a83
commit_timestamp_UTC    = 2026-10-11T11:10:59Z
commit_timestamp_local  = 2026-10-11 19:10:59 +08:00
reviewed_response       = response_v73.md
previous_review         = review_report_v71.md
previous_review_commit  = f1504cffd4bdcd7bfe025c0ff8e544298e1b7995
previous_review_blob    = f33bfb1da4c034131c4d9a0a02d5e7916de709cc
original_base           = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign                = V74_LOCAL_MAXWELL_HARMONIC_COARSE
required_response       = response_v74.md
ordinary_default        = UNCHANGED
NN_training_PC          = NOT_AUTHORIZED
merge                   = NOT_APPROVED
```

目标仍是原50×25nm周期、z=-10..130nm、真空0.7nm、任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN、复E/H、完整衍射及独立体吸收；必要构建到验收≤172800s。十进制2e12B是整机内存，须留系统余量、ownswap/OOC=0。当前s=7/135、MPI1有限问题不是原尺寸或48小时资格。

本报告明确覆盖上版“不换粗空间”的阶段限制，只批准本文一个候选。V73的两条旧曲线、600次错误、未完成尾部及费用原样保留。新V74窗口从真实首项工作计时；不刷新V73、不重复发放额度。

## 1. 已审事实、收益与未决项

本次读取最新ref/commit、response全文及summary、repair记录、变化文件清单、hot作用源码、现有粗映射/局部PC与FGMRES调用链、根规则和仓库原则；task/docs规则未变内容沿此前已读原文及blob核对衔接。前版完整review从本会话挂载原件读取，SHA256为3269e49b6004ccee1882de13db58e2fb01aa2ccf595c483d79ddf76c287a8243。任务目录未见独立supplement或同名V72。未SSH，未检查工作站此刻PID，未在审阅端重跑大型数组/PDE。measured均指仓库执行记录，不是ChatGPT自行实测。

依据：[Response V73](response_v73.md)、[summary](outcomes/summary.md)、[残差](outcomes/records/residual_history_v73.json)、[PC](outcomes/records/PC_qualification_v73.json)、[修复](outcomes/records/repair_journal_v73.json)、[费用](outcomes/records/resource_costs_final_v73.json)、[源码](outcomes/records/source_bindings_v73.json)。R128/B128实际数值source均为5e35ab9b1fac5e9e7101616db29a8fb7e4af39f2，修复/补消费/文档source分别保留。

| recorded measured | R128 | B128 |
|---|---:|---:|
| 实际KSP步 / 可评价候选步 | 256 / 256 | 195 / 192 |
| retained显式true | 0.994418150467 | 0.995072797554 |
| 独立原true/native | 0.992693268155 | 0.995072797554 |
| 独立port | 0.00228909658346 | 4.03994303604e-13 |
| 128步原true | 0.992675296094 | 0.995072799520 |
| 192步原true | 0.992675827113 | 0.995072797554 |
| 全域total E差/V70范数 | 0.988887497881 | 0.990238282756 |
| 全域scattered E差/V70范数 | 6.88391647442 | 6.89331965757 |
| prepared诊断进程链秒 | 6009.00250631 | 6396.80511518 |
| 新numeric因子 | 39 | 39 |

本批采样整树峰43.598033905GiB、最大gap2.56955s、自身swap0；较低内存对应的是失败候选，不是同精度收益。R128总场相对参考误差仍约98.9%；不能只看通道或“已恢复全部内部”称成功。B128的193–195步没有合法完整返回，其后61步未执行；记录192步原式与六场FAIL，不外推未跑尾部。

旧热算子约1.2–1.3s/作用、无fine K/S构建与内部恢复仍是有效组件成果。V73没有因为writer重求解；但旧600次实例门在全批1150次、尚未达到1600总门时触发，确实暴露配置没有贯通所有层。后续只消费现有修复并检查新调用合同，不另开历史故障追查。

固定physical_RHS上，粗修正后残差/原RHS为0.487639686028；再作旧局部组合为60.7130442268，两侧反馈后为77.9655797366。反馈后的粗约束运算尺度仅1.37422e-11。**粗约束被满足不等于全残差下降；单次PC也不必是收缩映射。** 不能仅据这张表定罪RAS或指定某个唯一根因；完整迭代平台才是拒绝原样续跑的依据。

时钟另列：commit时间11:10:59Z与response自称的费用快照12:11:15.599935Z有不一致。下一次收口只读核对各时钟来源，记录CLOCK_PROVENANCE_UNRESOLVED或真实解释，不改旧原文、不用这两个UTC差值拼计算时间。优先沿有来源的monotonic区间/原回执计费；此项不要求重跑数学，也不成为健康新计算的总前置。

## 2. 唯一候选：相同粗维数，让粗基在区域内部满足局部原方程

普通粗插值把p2多项式直接延入细网格。新方法仍由同样的p2边界系数控制区域之间的连接，但在每个原960四面体区域内部，用原p5算子解一次齐次局部方程，得到会响应波长、材料与几何的基函数。**改变的是PC粗基函数形状，不是待求物理场空间；不是NN，不是增加全局粗阶数，也不是把内部材料假设为可分离。**

离散Maxwell-harmonic空间已用于波动Schwarz粗空间研究，例如Li–Hu的[原始论文](https://arxiv.org/abs/2501.18305)。该论文使用特定谱选择/阻抗子问题及条件；本文只做固定骨架迹的局部Dirichlet延拓，不做其谱算法、不继承波数无关收敛结论。风险包括局部近共振、p2宏骨架仍不足，以及旧RAS在补空间中仍无效。保留全部风险，不预告收敛或加速倍数。

冻结：25576tet/1000个NOTCH tet、p5、828模式、全部原内部自由度；κ=(8.94046081729244,0.7821889682108057,0)，0.7nm，1度grazing/5度azimuth/s；Si n=0.999885140474+4.32477054e-6i、epsilon=n*n、mu=1。

```text
mesh_sha256     = c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c
material_sha256 = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
physical_sha256 = df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44
fine_FE         = 1943745
cell_internal   = 767280
retained_FE     = 1176465
retained_total  = 1177293
coarse_FE       = 6240
coarse_plus_port= 7068  (hard cap 8192)
```

只读V70 local_packet/q47/q63及V71的38块、真实p2映射Z0和parent_cells。实际路径与成员hash从健康manifest解析，不猜文件名。V70物理参考场仅在新候选冻结后评分；V73失败残差不用于训练/选基/初值。旧E0只作历史标识，不能拿来替代新粗矩阵E_H。

## 3. H：局部延拓与真正的共轭限制

### 3.1 使用真实父关系，不另造宏网格

原960tet粗空间及fine-to-parent关系已由V71的实际矩/Piola/MPC检查取得。复用它们，不重建一张新网格。对细层retained FE分成宏骨架B及各宏内部J_j：J_j包含某一个父宏内的细边/面未知量，不是已经被消去的单元内部30维。

按真实实体闭包和父单元面识别骨架；物理外边界、跨宏面及周期对应骨架全部在B。同一个周期master的全部贡献先合并。只统计incident-parent数量不足以识别外边界，必须检查实体是否位于父tet的任一面。每个J_j唯一所属；核对B与所有J_j无重无漏、实际单元贡献不存在J_j与J_k(j≠k)连接。几何容差沿已有定位资格，不能按矩阵小值决定拓扑。

宏内每块≤20000行，超过则保存明确容量失败，不重分宏域、扩大p或扫描划分。空J_j合法，直接保留骨架映射。原p2为6240个独立FE系数；B上的P_B为旧Z0对应行，真实边/面矩、方向、Piola和MPC不变。按p2实体DOF覆盖及既有完整矩嵌入核对P_B没有失去粗方向，不构造全局稠密Gram/SVD，也不截秩补救。

### 3.2 完整缩放算子、端口及延拓公式

记当前缩放接口算子为Ahat，其FE–FE块K只由单元Schur贡献求得；C/D/H是HotTracePacket已聚合的实际有符号端口块，再按原行/列尺度处理。D的符号不能再翻一次，C和D不假定互为共轭。全部828端口仍是粗变量的一部分。

对每个宏，构造：

```math
F_j=\widehat A_{J_jJ_j},\qquad
U_j=-F_j^{-1}\widehat A_{J_jB}P_B,\qquad
V_j=-F_j^{-1}\widehat A_{J_jp}.
```

新粗延拓定义为：

```math
(Z_H(c,\alpha))_B=P_Bc,\qquad
(Z_H(c,\alpha))_{J_j}=U_jc+V_j\alpha,\qquad
(Z_H(c,\alpha))_p=\alpha.
```

这里的alpha是原缩放port坐标，物理场恢复仍按原column_scales还原。基生成使用齐次原方程，不读取物理解或物理RHS选列。所有实际非零J–port项必须保留；理论迹为零不能用来删除旧数值实现已存在的项。U_j只存实际支撑的粗列，V_j只存实际非零的端口列，不分配每宏或每cell的828平方库。

反向限制必须为真实Z_H的共轭转置：

```math
Z_H^H r=
\begin{bmatrix}
P_B^H r_B+\sum_j U_j^H r_{J_j}\\
r_p+\sum_j V_j^H r_{J_j}
\end{bmatrix}.
```

不能把它简化成旧的“Z_FE^H r_FE，再原样接r_port”，除非已证明所有V_j为零。允许block-sparse矩阵或局部lift接口，禁止全局稠密N×7068数组。primal/dual、port坐标和forward/adjoint都写进新transfer contract。

### 3.3 无fine K/S构建新粗矩阵

构造E_H=Z_H^H Ahat Z_H。优先先在每个宏内部消去J_j，再以Q=diag(P_B,I_port)投影，仅装配7068行E_H。对q=(B,p)：

```math
\widehat S_{qq}=\widehat A_{qq}
-\sum_j\widehat A_{qJ_j}F_j^{-1}\widehat A_{J_jq},\qquad
E_H=Q^H\widehat S_{qq}Q.
```

上式与Z_H^H Ahat Z_H等价的原因是Ahat Z_H的J行被局部解消为零；对非Hermitian矩阵仍须使用真实A_qJ而非A_Jq^H。用合成复数非互伴系统证明实现，而不是以对称矩阵掩盖错误。

**公式不授权形成全局fine骨架Schur。** 按fine-parent分桶，局部体贡献及J消元修正直接累加到E_H；全局C/D/H基础项恰好一次，宏修正各一次。或者使用等价逐cell Galerkin累加，但必须支持含V_j的完整Z_H。旧coarse_galerkin/prolong/restrict不能只改变量名后静默沿用端口identity假设。禁止7068次全域action逐列形成E_H，禁止常驻Ahat Z_H全列库。

每宏F_j稀疏LU串行形成；先真实symbolic，双倍预测≤8GiB且live共驻规划通过才numeric。最多16列一批解U/V，保存后释放该宏F_j与因子，不把960个宏因子带入每次PC。一次主构建、无旧full-K/全局fine-S读取；健康38块保持不变。局部原解残差目标≤1e-10，运算尺度≤1e-10并记录放大；不能自动shift、增吸收、伪逆或改排序。局部近共振导致不可信时报告实测，不把它当成普通接口bug。

新增lift及映射显式常驻≤8GiB，额外临时块≤2GiB；容量先查实际稀疏列/行，不因粗维数没增长就隐去存储成本。已生成健康宏packet原子封存，中断从未完成宏继续；数学身份变化只作受影响失效，不覆盖旧包。

### 3.4 必要资格之后必须进入真实求解

只补：新增B/J拓扑和周期owner；小复数非互伴且非零port模型的延拓/粗矩阵恒等式；实际宏局部残差；两个固定复粗向量的Z_H/Z_H^H对偶、全域Galerkin和J齐次行见证。误差按绝对与运算尺度分别列，门1e-10；局部比较不能以过小RHS掩盖放大。宏J是retained行，未凝聚原cell内部仍按现有packet恢复。

新E_H必须重新symbolic/numeric；绝不重用旧E0因子。这一变化只在新粗矩阵，38个局部CSR直接复用。构造/qualified不等于solver PASS，也不要求测试向量上的PC必须收缩才能运行物理问题。旧15表、FLAT、相位/M、240点语义、8cell或全网格资格不重做。

## 4. I：一个完整求解，只有粗基改变

固定C_H=Z_H E_H^{-1} Z_H^H，沿R128的coarse-first组合：

```math
z_c=C_H r,\qquad
z=z_c+B_{\rm RAS}(r-\widehat A z_c).
```

保持原38块、一层halo、唯一core写回、局部矩阵、norm和正交化；RIGHT FGMRES/restart128/max256，初始retained为零。细层operator/RHS不变，不加B128末尾反馈，才能与旧R128区分粗表示的作用。不再次运行旧R128控制、不接旧B128尾部；历史对照未配平，不能授严格速度比。

在本次39个实际PC因子形成后，用原物理RHS记录一次新coarse-only的转移分账，旧值直接引用V73同RHS记录，不另建旧E0因子或重跑旧PC。该项与实际PC资格同批、最多300秒，不以其下降比例选参数、决定基或取消可信KSP。新完整PC做两个固定非零复向量的有限性/对偶接线与齐次见证；测时间，不要求它是收缩映射。

每32步、候选收敛及末态计算显式retained true，并恢复检查完整原式；同状态同路线缓存不得跨source/RHS/尺度串用。retained≤1e-11，独立true/native/augmented/port各≤1e-6，恢复/MPC/Schur-original≤1e-10；独立direct1e-10继续单列。局部齐次粗基通过不能代替完整原方程。

最多256步/3小时迭代；本批全域列作用≤800，资格、PC内、外层、true、独立PUBLIC审核按列计数。全部层显式接收同一个预算，不再叠加HotTracePacket默认600；只复验“实例能越过600但在本批800处正确拒绝”的轻量计数逻辑，不用真实PDE跑800次做测试。资格全域作用≤12，不能在循环里偷偷逐列调用数千次。

一个计划KSP.solve。只有已定位实现错误且没有合法终态，允许一次本批retained续算；总有效迭代、作用、3小时及固定窗口不清零。不重启科学停滞，不换restart、粗p、halo、shift或PC组合。真实时间/资源停止保存最后合法候选，未执行步数明确NOT_RUN；异常必须先保存调用分账和factor释放收据。

## 5. 完整场、成本与决策标准

retained/RHS/尺度/新旧packet/source先持久保存，释放KSP、38局部及1新粗因子并记录RSS，再完整恢复全部767280内部系数。完整total/scattered E/H/curl、原240点、828个物理复通道、逐mode功率、R/T/A及独立体吸收与能量必须交付。writer/JSON/补消费错误不触发重factor。原式未过则功率diagnostic only。

候选冻结后才读取V70场；沿已验证同基差系数积分和原q23/q31分母/floor。一次分子给候选和V70两个固定分母，均报告，不择优。严格同离散六场/240点/复通道≤1e-6；RTA/A_volume差≤1e-8、逐mode功率差≤1e-9、独立能量≤1e-5。历史P6/L5约1.14e-4/1.23e-4散射差及240点9.56e-4仍FAIL，不因迭代成功升级连续资格。

| 本轮可能结果 | 正确解释与下一步边界 |
|---|---|
| H构造合格、完整原式及严格场通过 | 固定有限case的无fine-LU迭代资格；核算包含新粗基准备的全费用，再设计packet-only冷构建/中间尺度或MPI所有权试验 |
| H合格但原式/场不通过 | 否决这个固定p2骨架、局部齐次延拓+旧RAS组合；保存残差/费用，不能自动增粗p、重启长度或跑另一组模式 |
| 局部F_j近奇异或coarse映射/容量不合格 | 记录具体宏/方程/数值/对象，保留健康构建；未运行KSP不称不收敛 |
| 普通接口错误 | 同窗最小修复、受影响回归，从健康宏/场资产继续；不是整批自动结束 |

完整成本包含父V70局部包构建前缀、V71局部准备前缀、新宏LU与lift、粗组装、39个PC numeric、每步coarse/RAS/action/正交化、原式恢复、输出和审核。父资产按依赖计一次，不把全部研究历史摊成单场必要成本，也不把新多尺度基当免费。prepared-start和真正几何起点cold分开；当前父V70曾形成全局S，故不能宣称整个cold历史无S。

## 6. 资源、持续执行与Git

新14小时总研发窗口；科学有载≤11小时、最后1小时收尾。H适配与构建预计工作量先盘点，给H阶段至多4小时累计；I含numeric与完整输出至多6小时，其中KSP至多3小时；所有修复/失败/等待/IO服从总窗口。每次进入PC numeric前至少预留实际numeric预测加4500秒完整输出审核。普通修复累计≤2.5小时；同根因两次无效换正确等价实现/隔离，不第三次盲跑。不是给每个dat单独刷新额度。

保持PC因子双倍symbolic总门80GiB，整树规划/警戒/采样停止96/112/128GiB；默认轻消费者64/80/96GiB。新粗E_H代替旧E0重新估计，旧38块估计可作依据、实际numeric仍回读确认。每factor前live RSS+全部未分解双倍symbolic+future≤96GiB；future≥12GiB并枚举257条主Krylov向量、临时PC、原式/恢复等。新增lift在live RSS中，不能借“局部因子已释放”隐藏它。宏局部因子逐个构建/释放，H阶段同样受96GiB规划和单宏双倍8GiB门。允许一次不改数学的owner释放/分块调整，不提高总额、不借用旧256GiB额度。

MPI1/math1/CPU1/GPU0/Loader0、complex128/int64、ownswap/OOC0、原宿主/cgroup/PSI/384GiB邻增长、空闲物理核/避忙SMT和机器heavy-lock策略不变。未确认旧actor清场前不启动；不改邻任务/系统，不忽略TERM、不关闭watchdog、不靠OOM探路。只读一次核验当前parent清单，不扫历史全盘hash。

新增ignored≤32GiB，Task去重许可696GiB，free≥50GiB；至少512MiB收据余量。新宏packet、lift、稀疏E_H与完整场原子写入空间事前计入。旧失败不删除。大数组留ignored，轻量记录只引用hash，不复制数万行父manifest。

复用hot_tetra_trace、bounded_trace_pc、bounded_trace_study、physical_retained_fgmres及共享scope/保存消费者；新局部延拓公共数学放src/solvers，粗transfer使用显式protocol，不复制另一个大型runner。只跑新增数学、完整port dual、计数贯通、parent身份及异常释放的targeted tests，相关Ruff/compile/dat validate；不full pytest/CI、FLAT、旧控制PDE或全仓索引。文档收口一次，不为网页或JSON重新跑PDE。

commit计划：C1新H/transfer/预算协议与targeted资格；C2冻结实现/参数并clean运行；C3只补已确认的定点错误，健康资产沿source复用；C4结果/response/两总账。活跃actor不改受检HEAD；本任务只在NN-Lab、本执行分支工作，不reset/stash/clean/amend/强推/merge，不向邻支派活。

## 7. 正式入口与交付

实现、targeted回归、commit clean与validate之后，通过资格化activation/现有监督运行以下待创建入口。它们目前是合同要求，不声称已经存在。

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v74_harmonic_coarse_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v74_harmonic_coarse_prepare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v74_harmonic_trace_fgmres.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v74_compare_verify_cost.dat
```

PREFLIGHT不暗藏PDE；H_PREPARE允许已声明宏局部factor，不能暗藏全域KSP；VERIFY不暗藏factor。一个dat一项明确计算，实际input/resolved/manifest/physics/source/ABI/MPI/资源/asset hash绑定。普通阶段PASS后继续后续可信工作，不停在“新粗基生成完成”交棒。

交付response_v74.md、outcomes/local_maxwell_harmonic_coarse_v74.md及紧凑records：macro_partition、harmonic_lift_qualification、new_coarse_Galerkin、local_coarse_factor_inventory、residual_history、complete_physics、paired_results、resource_costs_final、repair/source/run/closure；更新retained_iterative_contract_v74.json、summary/README及两总账短入口。必须回答新空间维数是否仍7068、局部成本多了多少、是否进入完整KSP、原方程/场是否通过、不能通过的具体原因和唯一下一项。

邻支已实际回读：Task42extra @e0508555ffec6d13fad68b7516971c5899a09901为Review V44→V45神经特征坐标实验；工程线@399787abc991e0e30975bc694bd18a9a30c5470e为V26完整q消费者/全行结构及资源停止。本支不复制其NN、规则reference-q、CSR任务或dot边界工作。本地宏齐次延拓来自非可分真实target原矩阵，不是把target替成可分reference。

仅推送本分支：

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

核对remote完整SHA/upstream/clean、closed/active null、后代清场与锁释放后交付暂停。不merge、不改master/邻worktree、不自动开下一窗口。新review授予的是一次研究试验，不是2TB/48小时保证。
