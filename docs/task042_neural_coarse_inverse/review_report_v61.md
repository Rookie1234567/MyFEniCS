# Review V61：完成细网格四面体参照，压缩边界支撑与重复场积分

## 0. 裁决与本轮必须推进的主线

**V62以`pass_with_qualifications`接受：四份完整四面体方程及物理输出已经取得，新FLAT解析校准通过；NOTCH的空间增量未通过，不能指定T5、TH3或旧R7为真值。** 新四面体路线已经具备实际可运行性和较低的有限参考成本，不应马上再换一个方法族。下一轮继续这条独立参照，补齐同一细网格的p4/p5，同时解决源码中会使大一点参考被过宽容量估计拦住的边界存储，并降低重复场比较费用。

授权 **V63_FINE_TETRA_ACCURACY_AND_BOUNDED_COST**：A=7680tet/p4/828；B=同网格p5/828；两者的完整增量通过后，条件M=同网格p4/1188。不是只做预检，不重跑旧FLAT，不训练NN，不恢复NN预条件器，也不继续旧hex的面/内部/gauge扫描。

这项工作消除的blocker是：**目前独立tetra参照同时改变h和p，缺少较细网格上的阶次证据；可接受的准确空间、真实稀疏容量及完整单次成本还无法连接到2TB/48h。** 同时明确：边界数组压缩和比较器优化只改善实现，不能冒充物理准确性。

```text
repository          = Rookie1234567/MyFEniCS
execution_branch    = task42_neural_coarse_inverse
canonical_worktree  = /home/fenics/Projects/NN-Lab
review_date         = 2026-10-08 (Asia/Singapore)
reviewed_HEAD       = 76f02f5ea7227462948777b10168cd2ebcf565f8
latest_commit_UTC   = 2026-10-08T07:32:40Z
latest_commit       = docs(task042): seal V62 final streams costs and closed cleanup
latest_response     = response_v62.md
previous_review     = review_report_v60.md
previous_review_SHA = b39df0051e6a0501528de54bf02987021188702e
original_base       = ccd357885f7f9be84efe3be07868cc94f13d93fc
next_batch          = V63_FINE_TETRA_ACCURACY_AND_BOUNDED_COST
required_response   = response_v63.md
ordinary_default    = UNCHANGED
merge               = NOT_APPROVED
```

目标仍为真空0.7nm、原50×25nm周期/z=−10..130nm、任意非可分三维周期结构、complex128 Nédélec H(curl)、双Floquet、完整Fourier-DtN及E/H/衍射/吸收；必要准备至独立验收≤172800s。十进制约2e12B是整机物理内存，不是单任务RSS额度。当前s=7/135只是有限authority候选；生产仍需分布式/matrix-free、凝聚接口迭代、有界粗问题、流式DtN和按块恢复。

本报告明确替换V60的已完成队列，覆盖其200000完整矩阵行上限，允许本批列明的最多600000行参考；A/M保持64GiB规划，仅B明确允许128GiB有限研究规划，均需现场资源及symbolic准入。没有放宽精度、修改系统策略或授权原尺寸直接分解。

## 1. 审阅范围与实际结果

实际读取固定HEAD的最新README/response、规则/仓库原则、原task及原blob身份、最新review、决策和存储费用记录，核对上份review以后8次提交；深读`independent_tetra_reference.py`、`independent_tetra_fields.py`、`independent_tetra_study.py`和scope。上一份review本地完整副本的Git blob与远程`2f31dd8e5a44785f99975a9d2bb5f52b2b03ee54`一致，已完整读取。目录未发现新的独立supplement或更晚review。没有SSH、完整工作站数组重演或审阅端新PDE；下面measured来自仓库，并非审阅端重测。

主要证据：[Response V62](response_v62.md)、[专题](outcomes/independent_tetra_reference_v62.md)、[科学记录](outcomes/records/scientific_checks_v62.json)、[保存场checker](outcomes/records/independent_saved_pair_checks_v62.json)、[存储/部署](outcomes/records/storage_lifecycle_deployment_v62.json)、[最终费用](outcomes/records/resource_costs_final_v62.json)、[决策](outcomes/records/decision_and_not_run_v62.json)。

| recorded measured | T4：960tet/p4 | T5：960tet/p5 | TH3：7680tet/p3 |
|---|---:|---:|---:|
| 独立FE / 含828端口行 | 39616 / 40444 | 73680 / 74508 | 143424 / 144252 |
| 实际nnz | 9307708 | 22757388 | 19517436 |
| 独立true/native | 1.511499009e−10 | 8.259781881e−11 | 2.189487576e−11 |
| 完整T_N1/s | 357.761297 | 985.805547 | 744.207395 |
| sampled树峰/GiB | 2.426861 | 4.847828 | 6.813831 |
| R | 0.0762191847290 | 0.0762186641826 | 0.0762189084148 |
| T | 0.9056657239404 | 0.9056651260259 | 0.9056651887408 |
| A_volume | 0.0181150913315 | 0.0181162097958 | 0.0181159028462 |

F4独立true=1.747489041e−10，解析total E/H/curl最大约9.2822e−8、240点约1.1061e−7，解析功率通过。F4/T4的formal1e−6通过而独立direct1e−10未过，继续分列；不为补这一个内部标签重解旧PDE，也不在无证据下把约千分级场差归咎于它。F4有保存后补审核链，不能称一次无故障fresh进程。

| 物理比较 | scattered E / H | 240点六向量相对范数最大 | 原1e−4门 |
|---|---|---:|---|
| T4/T5 | 3.860795783e−3 / 3.846640785e−3 | 6.595829506e−3 | FAIL |
| T5/TH3 | 8.816147058e−4 / 8.993733236e−4 | 2.152344167e−3 | FAIL |
| FXY/T5 | 9.20210359448e−4 / 9.11457862705e−4 | 9.09532692962e−4 | FAIL |
| R7/T5 | 3.40367805544e−2 / 3.4007623682e−2 | 2.71593270223e−2 | FAIL |

T5更接近FXY而不是R7，是有价值的方向性证据，但新tet自身的变化仍与FXY/T5同量级，不能投票选择真值。T5/TH3同时改变h和p，不能据这一对拟合收敛阶或宣称细网格更差。四份原式通过也不替代连续准确性。

四PDE必要进程合计2520.622384s，独立研究VERIFY为4538.095313s，约为前者1.80倍（derived）；这不代表物理检查可以删掉，说明应复用同一场的范数/几何和相同分子，不反复支付相同积分。V62普通API/字段/早求值问题均已同轮修复，四numeric、四完整解，无科学重解；停止是获准队列完成，不称“仍卡在bug”。

科学source：F4=`8027ac9e680b2ba04c20f9977442d11f0f9daa12`；F4补审/T4/T5=`40af0ff568ab6a5d221142a659a09c6b15fc026b`；TH3/VERIFY=`2c9fa66e9c320329bb630d3c28fdab1d01574915`；末次纯数组checker=`fc5855eed95ae4298fadb6dc6646c8c83246ef8d`。不以文档HEAD替代运行source。

## 2. 冻结问题、主计算与合理的比较逻辑

保持V62真实未舍入物理descriptor、相同Freudenthal取向和材料边界；s=7/135、0.7nm、掠入射1°/方位5°/s/幅值1，κ=(8.94046081729244,0.7821889682108057,0)。Si n=0.999885140474+4.32477054e−6i，epsilon=n*n、mu=1；材料表hash`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。材料ready，不再索要，不联网替换。

A/B准确复用TH3的7680tet几何/材料：原Z2盒各向二分、8×8×20小盒×6tet，192个NOTCH tet，双周期，原背景/入射/完整Cκ不变。p是Basix N1curl阶数，不是从0起的subdegree。独立周期实体计数为edge9152、face15488、cell7680；用p×edge+p(p−1)×face+p(p−1)(p−2)/2×cell导出下面数字，实际MPC仍须核对。

| planned角色 | 完整空间 | 独立FE | 含端口行 | 内存规划 |
|---|---|---:|---:|---|
| A / TH4 | 7680tet/p4，828模式 | 314624 | 315452 | 64GiB |
| B / TH5 | 相同7680tet/p5，828模式 | 585920 | 586748 | 仅此有限case上限128GiB |
| M，条件 | A相同网格/p4，1188模式 | 314624 | 315812 | 64GiB |

先A，再B，不因A与旧粗解的增量FAIL而取消B。两者均从物理零初值求完整未凝聚系统；不使用旧场作初值、RHS或挑基，不调用旧hex15表/宏Schur/内部LU。标准UFL/FFCx体装配、复杂MPC的Hermitian拉回、独立PUBLIC_BASIX、完整三角DtN与通用MUMPS保留。不重新开发求解器或加入新PC。

A后实际比较TH3/A（同h升p）和T5/A（交叉h/p）；B后比较A/B（同h升p）及T5/B（同p细化）。旧T4、TH3或T5较粗导致的FAIL不需要被新解“修成PASS”。尤其不得要求旧TH3与T5都贴近同一个新场才允许继续：它们已经相差约9e−4，粗端点间不一致不能成为永远锁住细解的门。

A/B全部场、240点、物理通道与功率通过时，仅授`FINE_TETRA_P_INCREMENT_PASS`；不是连续误差上界。T5/B的旧粗→细h差较大可与此并存，必须如实保留。B尚未运行或自身原式不合法时，不授此资格。TH3/A、A/B的变化率只作有限趋势，不拟合未经证实的渐近阶。

只有A/B联合增量通过且剩余预算充足，直接进入M：m=−13..13、n=−5..5、上下×s,p，共1188模式，保留全部原828。M检验新tet参考的有限DtN增量，而非继承旧hex模式结果。旧A在新增360模式上的投影实际计算，不设零、不改原A端口数组；M独立零初值，新边界/载荷/因子完整收费。比较A/M通过仅增加一个有限模式证据，不授无限模态收敛或目标尺寸。

通常两项主solve加一项条件M；**最多三次新全域numeric/solve，包含确认后的科学修复重放**。发生一项科学修复时优先A/B、取消M。后处理/JSON失败不占新solve，应补消费。不得再加p6、h4、FXYZ、新载波或新的物理尺寸。

## 3. 必做的窄工程修正：边界只存实际可访问支撑

### 3.1 源码事实，不把保守估计叫物理bug

`TriangleComponents`目前为每侧分配`out=(nkeys,n_native,2)`；但循环只访问该侧边界三角所属的tet，再通过`dual_maps`写入相应master行。`assembly_capacity`却以`4*n*828`估计全部耦合、以`6*n_native*828*16`估计边界副本，并硬编码200000行。对于A/B，这会把数学上不可能被该循环访问的大批体行计入预算。它是过宽的数据布局/估计，不是已证明的场误差根因。

### 3.2 精确压缩，不删小项

每侧先建立集合Γ_s：**该侧所有边界三角owner tet的全部局部DOF，经实际MPC展开后所有可能被写入的master**。故意保留整owner单元的行，而非仅保留理论面DOF；这样连旧实现的微小浮点残留也能保存。不要按绝对值drop，不因为理论零切向就删尚未核验的数值项。

建立固定global-row↔compressed-row索引，仍按旧triangle/cell/DOF顺序累加完整x/y分量。`out`只分配`(nkeys,|Γ_s|,2)`，输出时映回同一全局行号。未在Γ_s中的行必须由循环访问证明从未被写入，而不是只测随机向量后猜零。非零小值、C/D符号、trial/test共轭、入射牵引、所有mode/beta/参考面保持。q47与q63仍各自独立生成一次，复用只发生在本case已保存的对应包上。

容量按真实Γ_s、真实side模式数、body局部连接及对象生命周期重算：体保守贡献可用Σ dim(cell)^2，耦合存储可用Σ_s 2*M_s*|Γ_s|；计入MPC展开、native/压缩CSR、augmented/scaled矩阵、PETSc副本和临时乘积。尚未释放的对象必须同时计；不能只改`admitted=True`，不能在旧full-native分配仍存在时用新压缩估计准入。可用真实稀疏图收紧重复贡献上界，但不开发通用CSR/staging框架。

一次在已保存T5的相同几何/p/828上重建边界包并对照旧q47/q63/incident，门沿原作用尺度1e−10和载荷1e−11；不重解T5。检查实际Γ外写入拒绝、phase/key/parent和一个非零小项保留反例。资格通过后用于A/B；90分钟内优化接不齐时允许旧正确构造器继续，但必须以其真实内存重新规划，不能用优化估计掩盖旧分配。本项不是重做dot流式积分或邻支CSR研究。

## 4. 比较器只做必要工作：同载波差分的精确多项式积分

V62每次比较重复计算相同背景、六类场和父场范数，研究VERIFY反而比四份PDE总用时更长。本轮允许一个窄、显式opt-in的`SAME_REAL_CARRIER_POLYNOMIAL_DIFFERENCE`路径。它不修改生产方程，也不降低物理门。

当两场在同一真实κ、仿射tet、分片常mu和同一背景下，公共子tet上有：

```math
\Delta E=e^{i\kappa\cdot x}(u_b-u_a),\qquad
\Delta H_{code}=\frac{e^{i\kappa\cdot x}}{i k_0\mu_r}C_\kappa(u_b-u_a).
```

κ为实数时，模因子绝对值为1，total与scattered的**差分分子完全相同**。若实际tet基最高多项式度为s，三种平方差的度不超过2*max(s_a,s_b)。可采用`qdiff=2*max(actual embedded_superdegree)+3`，p5最高时建议q13，最终以实际Basix/polyset证书为准。在共同包含的真实tet上直接分别评价两原函数，不插值或投影一方，不构造全局mass/Gram。

**只简化分子。** total/scattered分母各自不同，散射分母含解析背景的指数项，继续保留原q23/q31资格及原floor/单位。原complete_output已经保存`per_cell_analytic_squared`，可复用对应场的散射范数；总场范数可在本case一次输出中顺带保存。旧数据缺失只补该场范数，不重解。复模式仍用原左侧固定范数，场仍用原右侧范数；不能借重构统一改分母。240点一侧归属和全部六个向量范数保持。

一次用已保存T4/T5完整配对的q31积分作对照，新分子按新规则重算；检查误差积分操作尺度≤1e−10，并要求非近零差分范数的相对再现≤1e−6，原六场/240点/模式Gate结论不变。无需重跑旧q31；已有原记录是对照。再以少量实际TH3子tet核对公共包含/真实J和变换。新两主场中至少一组配对保留一次独立q31抽核及证据；发现差异则该配对回退完整旧q23/q31，不调门救成功。

不同κ、曲几何、不同物理背景、非分片常mu、未包含的公共子tet均拒绝这个快路径。Fourier边界、指数RHS、解析FLAT、独立原式不因此降q。相同fine网格的A/B只使用已有same-mesh几何与亲属表，不每个点遍历全部单元找父。缓存按真实identity有界共享，workspace≤2GiB。不得把进度日志当作可恢复积分块；若声明可续算，必须原子保存已完成块及其hash，避免最后writer失败后重做全部积分。

本项实现预算≤60分钟；失败或尚未资格时原比较器继续。不把优化成败作为A/B求解前置。最终只汇总一次必要比较，旧R7/FXY最多各与B作一组预算允许的诊断，不重做四组旧比较或24弱试验。

## 5. 数值资格、分流和不中断

新后端p4/p5、真实tet映射和F4解析已通过。体数学未变时不重跑FLAT、旧preflight全套或Task035。只补新role/行预算、support压缩、比较器和1188条件接线的targeted测试、相关Ruff/compile/dat validate；不例行full pytest/CI、全仓索引或全历史hash扫描。

每新case生产UFL完整body与独立PUBLIC_BASIX作用沿原q=2p+3/2p+5，保留两个固定复作用见证；三角q47/q63，M若实际不足只允许一次63/79并绑定真实q。不复用旧hex数值包，不回退凝聚或新PC以伪造独立参照。

formal true/native/augmented/port各≤1e−6；direct内部目标≤1e−10单列，MPC/身份/恢复操作≤1e−10。最多两次原有精化。生产残差过目标而独立direct略超，仍保留该子标签，不隐瞒、不增加精化次数；全部formal门安全时继续完整输出。每份解返回立即原子保存完整x/u/port/mesh/tag/MPC/κ/source/hash，保留独立原作用，释放全局factor和无用矩阵后再后处理。

全部total/scattered E/H/scaled-curl、固定240点六向量相对范数和物理参考面复通道≤1e−4；R/T/A/A_volume增量及独立能量≤1e−5；逐mode功率差≤1e−6。不调幅相、不用能量闭合覆盖场FAIL、不将0.0001附近结果四舍五入过门。

A原式/输出合法而比较FAIL，B继续；B真实容量不足，保留A完整结果、真实symbolic和已完成比较，不伪造B或改成toy。不因某一研究比较或一个collector字段而暂停其他数学可信的工作。已返回解的API/dtype/路径/写出/checker问题，只做最小修复、受影响回归和补消费；不再factor。确认数学、材料或映射改变时才动用科学修复槽，旧原结果和费用不改写。

**不按bug个数停工。** 同根因两次无效后换诊断或已授权正确回退，不能第三次盲跑；累计修复/重放≤2.5h且受总窗。真正ABI/原式/监督不可信先隔离依赖项。科学差异不是bug，不能直到“算成预期”才停止。

## 6. 时间、内存、磁盘与现场隔离

新10h总研发窗口，科学有载≤8h，最后1h交付；首次UTC/monotonic/boot绑定，包含实现、测试、修复、所有失败/等待/比较/IO，不刷新V62。每项numeric前保留至少3000s用于完整输出、必要比较及收尾；单case预估必须包含完整N1，不以最后solve几秒作为预估。先保证A/B及验收，预算紧先取消M和可选旧场诊断。

| 本批明确profile | planning | warning | sampled tree stop |
|---|---:|---:|---:|
| P/A/M/消费者默认 | 64GiB | 80GiB | 96GiB |
| B：唯一7680tet/p5完整参考 | 128GiB | 160GiB | 192GiB |

B的增加是一次有限accuracy authority许可，不是2TB可用的假设，也不是新生产默认。所有profile在dat/plan中事前冻结并传到Journal、launcher、watchdog、assembly、AnalyzedDirectFactor和collector；不运行中改旧window或把旧64GiB账改成128。A或消费者不得借B额度超限。

完整矩阵行上限600000只对本批列明case有效，不授任意600000行任务。numeric须满足实时树RSS+2×可靠INFOG16/17(decimal MB)+2GiB≤本role规划；实际fill未知，不线性外推已有factor授权，不赌OOM，不扫描ordering/shift/BLR/OOC。各类实际矩阵、局部表、三角缓存和PETSc副本入账；只增加行数许可不会自动增加资源许可。

继续MPI1/math1/CPU1/GPU0/Loader0，ownswap/OOC0、ICNTL22=0、原PSI/有效cgroup/宿主保留和384GiB邻增长余量。受控共享的原合格物理核与避忙SMT条件不放宽，一个自身heavy actor/一个global factor；只停止自身后代，不修改邻任务或系统ABI/BLAS/CUDA/全机swap。现场余量不够就不启动该case，不能因整机标称2TB绕过。

新ignored≤32GiB、Task去重累计≤240GiB、free≥50GiB、证据余量≥512MiB，求解前计入原子写入双份、全部场/独立向量/边界包；旧失败不删除。只stat本批与引用父包，不反复hash全树。实际采样gap与已观察峰分列，不将名义0.5s称连续硬峰。

## 7. 与邻支去重及2TB/48h的实质交付

最新只读范围：Task42extra `d85532461b04f486a86c678c3eadaf745a442126` 已交付V32多尺度神经，native约0.111824、散射E约0.042322，联合门未过；工程线`57f20cc66b3de65c696def2b9bf783ddcbfce55e`已交付V17构建/Ny组件，E1/原尺寸仍未资格。本支不重复M5/teacher/NN-PC、工程参考逆/通用CSR或dot流式模式算法。dot只核对ref`15713d3e09b63f65511c7b7f61fa043fdb23dca5`，NN-V3只核对`1f01ae46bbe21f17200350a46513ef5f33e5cf6a`；不推断未推送本机状态，不通知/改写邻工作树。

部署N1从本case启动到必要mesh/MPC、JIT/body/triangle、factor/solve、全部场/240点/模式/吸收、独立原式、provenance/IO及清场。版本比较和一次性资格另列T_research，但必要物理审核不能挪走以降低N1。数值缓存新构建与只读准备复用分别注明；OS/JIT未清空如实写，不要求破坏系统缓存。缺配平同精度旧对照不授生产加速比，却必须测新case自己的完整N1。

本轮新增实际FE/nnz/fill、边界活跃行/缓冲尺寸、峰、释放生命周期、A/B同h阶次变化及M决定。不要再复制旧亿级DOF情景表当进展。若A/B稳定，可形成可供后续求解器使用的有限参照包：精确descriptor、完整physical field、原作用/残差契约、真实所需精度与费用；仍不是完整原尺寸资格。若不稳定，保存公共细网格上的差分区域/方向信息与实际分子，给出一个明确下一步，不自动再开启第4份PDE、另一载波或另一有限元家族。

即使tetra有限直接法更便宜，也不宣布global LU适合目标规模。准确性基线确定后，后续生产优先保留已验证局部消元/类共享，发展分布式trace作用、可扩展PC/有界粗空间与流式DtN；完整内部场不进入所有Krylov向量。当前全矩阵独立参照的内存与未来凝聚接口库存不同，二者分开。2TB须留系统余量；目标48h须包括必要构建和验收，仍有目标模式/accuracy-qualified网格/迭代/fill/同时RSS等未知项。

## 8. 实现、正式入口与一次交付

复用`independent_tetra_reference/fields/study`数值核，只作薄参数化scope，不为A/B/M复制一套大runner。新代码进`src/`；旧默认和历史source不改写。阶段C1接真实support与按role资源/schema；C2接比较复用及条件模式；targeted回归后commit clean并validate，再启动正式actor。活跃科学期间不改其受检HEAD。

以下是**本轮待创建**one-run入口，均通过既有资格activation和监督运行：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v63_tetra_fine_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v63_tetra_notch_h2_p4.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v63_tetra_notch_h2_p5.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v63_tetra_notch_h2_p4_m1188.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v63_compare_verify_cost.dat
```

preflight不暗藏全域solve，M未准入不得盲跑，VERIFY不暗藏factor。1188必须沿configuration/boundary/output/loader/checker传递真实期望库存；旧`==828`、硬编码数组长和隐式回退必须拒绝或显式改为冻结库存，不允许静默降回828。体矩阵相同不意味着M的边界/RHS/全局factor可复用。

交付`response_v63.md`、`outcomes/fine_tetra_accuracy_bounded_cost_v63.md`及紧凑records：source/run/physical identity；support容量与新旧边界配对；实际A/B/条件M完整原式/物理场；比较分子/各自分母/资格；nnz/fill/T_N1/T_research/峰和真实gap；全部修复/未运行原因及唯一下一pilot。完整数组留ignored，Git只交本批必要摘要与父hash，不再拷贝数千条基缓存成员为“新物理场”。summary、README和两总账追加简明条目，旧task/review/response/raw逐字保留。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

最终核对完整remote SHA/upstream/clean、closed/active null、后代清场和锁释放后交付用户暂停；不merge、不改master/邻支、不通知隔壁、不自动新窗口。GitHub视觉未取得就标NOT_VERIFIED，不为网页重跑PDE。

## 方法依据与审阅端边界

[Basix 0.10求积定义](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.quadrature.html)规定degree是精确积分的多项式最高次数；本报告的差分恒等式及适用限制必须由实际元素/公共子tet资格补全，不能对含指数的分母或表面积分套用。[Nédélec元素定义](https://defelement.org/elements/nedelec1.html)说明tetra空间、实体矩及阶数约定；[DOLFINx标准PETSc装配](https://docs.fenicsproject.org/dolfinx/v0.10.0.post3/python/generated/dolfinx.fem.petsc.html)为本轮继续复用的公开路径，不要求升级当前ABI。

审阅端只进行了周期6-tet实体/自由度组合计数、公式检查与文档结构/身份检查，没有运行新FEniCS或PDE，未重算工作站大数组。所有新性能、准确性及资源结果必须由V63实测取得。
