# Review V60：停止盲目扩充接口，用独立四面体完整场判别准确性

## 0. 裁决、目标与执行身份

**V61按有限实施和交付范围接受（`pass_with_qualifications`）：FX/FXY完整原式、恢复和物理输出成立；x面增量通过，加入y面后的散射场与240点增量仍失败，跨表示差异约3.37%没有消除。没有新NN收益，也没有原尺寸0.7nm、2TB/48h资格。** 本次不把更多接口自由度当作默认答案，不授权FXYZ、宏边扩充或继续增加内部p/r。

授权 **V62_INDEPENDENT_TETRA_FULL_FIELD_REFERENCE**：在同一缩尺0.7nm/828模式/真实NOTCH物理问题上，用相容四面体Nédélec空间和标准完整弱式装配，绕开当前六面体15表、宏单元局部消元和受限迹算法，直接求完整有限系统。先一个新后端的解析FLAT校准，再两份NOTCH完整解，资源允许时增加一个事前固定的细网格交叉解。这里的reference是候选参照，不预先指定为真解。

这项工作消除的blocker是：**两簇完整物理场长期不一致，而多数新结果仍继承相同的六面体张量、相位空间和凝聚链，尚无足够独立的离散证据说明该保留哪种精度/规模方案。** 它不是重写生产求解器，也不是再次只做局部残差诊断。有限直接法在本轮专用于准确性authority候选；大规模主线仍须走可扩展Full3D迭代。

```text
repository           = Rookie1234567/MyFEniCS
execution_branch     = task42_neural_coarse_inverse
canonical_worktree   = /home/fenics/Projects/NN-Lab
review_date          = 2026-10-08 (Asia/Singapore)
reviewed_HEAD        = 400acdc53944e9da6cbca931da6e31cdf7d76dd6
latest_commit_UTC    = 2026-10-08T03:08:08Z
latest_commit        = docs(task042): seal V61 final bytes costs and closed cleanup
latest_response      = response_v61.md
previous_review      = review_report_v59.md
previous_review_SHA  = 9077e392a367afd7b90b61a85c1e0952f256b4ee
original_base        = ccd357885f7f9be84efe3be07868cc94f13d93fc
new_campaign         = V62_INDEPENDENT_TETRA_FULL_FIELD_REFERENCE
response_required    = response_v62.md
ordinary_default     = UNCHANGED
NN_training_PC       = NOT_AUTHORIZED_THIS_BATCH
merge                = NOT_APPROVED
```

最终目标不变：真空0.7nm，原50×25nm周期、z=−10..130nm，周期单胞内任意非可分三维材料/几何，complex128、Nédélec H(curl)、双Floquet、完整Fourier-DtN、E/H/衍射/吸收；单场必要构建至输出和独立验收≤172800s，十进制约2e12B是整机物理内存，须保留系统和邻任务余量。当前s=7/135有限模型不是原尺寸，也不是允许该任务用满2TB。

本报告明确替换V59的面扩充队列，允许下述有限四面体参考路径及完整未凝聚矩阵，覆盖原只允许宏迹/100000行的限制；仅条件TH3的本批矩阵行许可提高到200000，**内存许可不提高**。旧task、review、失败、窗口及费用保持；不修改治理原则或其他分支。

## 1. 已审阅事实与本轮取舍

实际读取了固定HEAD的response/summary、原task、根/文档规则与仓库原则、上一份完整review、V61结果/存储/决策记录，比较上份review后5次提交，检查新增面响应和相关现有四面体/MPC基础接口。目录未发现新的独立supplement或更晚review；旧task和规则同blob部分继承。没有SSH、工作站大数组重演或审阅端新PDE；下文measured来自仓库，计划数字单列derived/planned。

证据：[V61回应](response_v61.md)、[完整专题](outcomes/face_trace_enrichment_v61.md)、[科学记录](outcomes/records/scientific_checks_v61.json)、[存储/因子](outcomes/records/storage_lifecycle_deployment_v61.json)、[决策](outcomes/records/decision_and_not_run_v61.json)、[最终费用](outcomes/records/resource_costs_final_v61.json)。科学source为`0881cb94ad8fb84915c9a1f5f1589c2124d73396`，最后保存consumer为`2681258fe60745bb06d30dea9f88d60fbebf751c`，不能以文档HEAD替代。

| recorded measured | FX | FXY | 裁决 |
|---|---:|---:|---|
| 最终行数/实际nnz | 66300 / 99404541 | 98940 / 223567101 | 合法完整新空间；更大图不是免费的准确性 |
| 独立true/native | 3.074891604e-11 | 3.064346084e-11 | 原1e-6和direct1e-10分别通过 |
| 完整prepared-start T_N1/s | 2300.785113 | 3201.971758 | 复用旧内部因子，不能称完整fresh冷启动 |
| sampled树峰/GiB | 21.66981506 | 41.24351120 | 有限实测；采样间隙峰值未知 |
| numeric同时规划/GiB | 30.43509924 | 62.98122048 | FXY已接近64GiB规划门，不能默认再扩面 |
| factor存储项 | 220879368 | 746525304 | 与矩阵nnz、后端allocation、RSS分开 |

| 完整物理配对 | scattered E / H | 240点最坏 | 原1e-4门 |
|---|---|---:|---|
| H2→FX | 4.742945734e-5 / 4.946710161e-5 | 4.598158028e-5 | 完整增量PASS |
| FX→FXY | 1.886431146e-4 / 1.866523070e-4 | 1.715245780e-4 | FAIL，功率通过不能覆盖 |
| H2→FXY | 1.954583313e-4 / 1.940162448e-4 | 1.798841299e-4 | FAIL |
| R7→FXY | 0.03365849935 / 0.03369817781 | 0.02685884949 | 跨表示FAIL；R7不是真值 |

释放的x/y面方向缺陷确实降至约3e-12；FXY剩余z面和宏边缺陷/RHS约0.00693168、0.000587823。这证明新增方程被满足，但这个系数尺度分账不是物理能量，也不足以断言继续释放z面就能得到准确场。之前按某方向h变化推选同法向宏面，只是启发式，不能继续当因果证明。

V60的C67同M67再现及存储收益继续保留：nnz由141754824降到28510524，sampled峰由26.9973降到8.8550GiB；V61没有将其推翻。但现在扩大空间后nnz和因子又增长，不能将早先约67%峰值改善直接套到FXY或目标网格。

V61两个完整solve和两个numeric均完成，没有科学重解，停止原因是固定队列结束，不是一个普通bug。审阅不把科学差异说成软件错误。名义0.5s监督在FX/FXY实际最大gap7.21/10.35s，研究VERIFY/归档又有30.93/42.49s；只报告sampled峰，不声称连续硬峰或间隙内绝对零swap。

## 2. 独立程度、已有基础和分支分工

**不从零再造一套FEM软件。** 本分支已继承Task035的周期四面体能力；已核对`src/constraints/floquet_3d.py`对tetra的p3/p4/p5支持、`src/geometry/tetra_mesh_audit.py`及`src/adaptivity/target_uniform_tetra_control.py`的原入口。复用网格质量/周期实体核验、现有高阶方向与MPC、通用MUMPS/监督/保存格式。不要启动Task035旧13.5nm案例、DWR、角度或自适应campaign。

本轮的独立性必须真实发生在：①四面体基而非旧六面体基；②标准UFL/FFCx的完整矩阵装配，而非15参考表或旧raw；③不静态凝聚、不限制宏迹、不复用子/宏LU；④新三角端口积分和完整物理场求值。**仍共享DOLFINx/Basix、材料和模式物理约定，故不是完全不同软件的独立验证；相位变量代换也保留。** 共同系统误差仍可能存在，不以“独立”二字授真值。

邻支冻结范围：

| 分支快照 | 最新范围 | 本轮避免重复 |
|---|---|---|
| task42extra_feinn_5nm @ 2b841cb6910be14fcaf9fea98ea59b7f458a5c94 | Review V31→V32，多尺度神经支持/方向学习 | 不训练NN、不做M5/teacher/神经空间审计 |
| task40extra_0p7nm_engineering @ 220f416f2917011b823e383bd308a5337b1ce0cf | Review V17，恢复、稀疏构建、Ny=8及条件E1 | 不重写其PC/CSR/目标端口组件 |
| task40extra_dot_parallel_cloud @ 15713d3e09b63f65511c7b7f61fa043fdb23dca5 | 只核对ref | 不接管或重复其组件开发 |
| task42extra_NN-V3-learned-iteration @ 1f01ae46bbe21f17200350a46513ef5f33e5cf6a | 只核对ref | 不推断未推送本机状态 |

本次未改/通知/启动邻工作树，不merge/cherry-pick研究整分支。

## 3. 冻结物理与有限计算队列

NOTCH直接读取V61的真实宏几何轴、材料与几何盒，不按Markdown小数重建低位。s=7/135，Z2宏布局4×4×10、160个矩形盒，原κ=(8.94046081729244,0.7821889682108057,0)，λ0.7nm、掠入射1°/方位5°/s/幅值1。Si n=0.999885140474+4.32477054e−6i、epsilon=n*n、mu=1，材料hash`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。原828物理模式m±11/n±4/上下×s,p、导纳/beta分支、参考面、背景及RHS保持。

每个盒用同一个全局坐标顺序的6-tet Freudenthal剖分，得到960tet。共享面与x/y周期面三角划分必须平移相容；每个tet继承所属原盒材料，不能按“缺口必须还是2个cell”误判新的tet计数。原材料体积、界面与NOTCH边界不改变。使用既有构造器能保证这些条件则复用；否则只增加这个确定性6-tet薄适配，不引入外部网格依赖或重写自适应框架。

| planned角色 | 网格/阶数 | derived独立FE | 加828端口 | 用途 |
|---|---|---:|---:|---|
| F4 | 同盒960tet/p4，原解析FLAT几何/材料 | 39616 | 40444 | 新后端完整解析校准，不是复跑旧hex FLAT |
| T4 | 960tet/p4，真实NOTCH | 39616 | 40444 | 第一份独立离散完整场 |
| T5 | 同960tet/p5，真实NOTCH | 73680 | 74508 | 同几何更丰富tet空间，不指定为真值 |
| TH3，条件 | 每盒各向二分再6-tet，7680tet/p3 | 143424 | 144252 | 不同h/p路径交叉参照，不是嵌套p增量 |

这里的p是Basix `N1curl`阶数；tet局部p3/p4/p5维数45/84/140，不得套hex维数或DefElement从0起的subdegree。上述周期拓扑由纯组合计数导出，实际DOLFINx/MPC编号须核验，不以derived冒充运行。

顺序：一次窄接线→F4完整求解/解析审核→T4→T5→条件TH3→统一比较/结算。TH3在两主NOTCH解代数合法、真实容量和剩余时间可容纳完整输出时执行；**不要求T4/T5先接近旧场或先通过准确性增量**。T4/T5变化小也不自动取消这个可执行的独立h检查。默认四个完整求解上限，另一个保留槽仅用于确认后的科学修复或F4分辨不足时的同网格F5解析校准；总数≤5，包括失败后重解。没有更多阶数/网格/模式扫描。

F4必须验证新tet管线的解析total/scattered E/H、固定点、物理通道及功率。若输出API错误，补消费；若确为F4离散不足而原式可信，允许F5一次。若两者仍不能解释解析差，优先修原式/边界/映射，不以错误flat链给NOTCH授authority，也不改物理/阈值救场。

## 4. 完整独立装配：明确保留与禁止项

继续解析相位表示，而不改变物理或采用单向/傍轴近似：

```math
E=g u,\quad g=e^{i\kappa\cdot x},\quad
C_\kappa u=\nabla\times u+i\kappa\times u,
\qquad H_{code}=\frac{g C_\kappa u}{i k_0\mu_r}.
```

体弱式由新简洁UFL表达式经标准FFCx装配：

```math
 a_\Omega(u,v)=\int_\Omega \mu_r^{-1}C_\kappa u\cdot\overline{C_\kappa v}
 -k_0^2\epsilon_r u\cdot\overline v\,dx.
```

所有trial/test交叉项、真实DG0材料和非零载荷保留。`fem.petsc`或`dolfinx_mpc`标准装配均可，沿已有tetra拓扑MPC施加复对偶。用P表示真实周期primal展开，则完整方程形式为：

```math
\begin{pmatrix}P^H K P&P^H C\\-D P&H_M\end{pmatrix}
\begin{pmatrix}\widehat u\\\alpha\end{pmatrix}
=\begin{pmatrix}P^H f\\f_M\end{pmatrix}.
```

C/D不假定互为共轭，H_M及符号沿原物理定义；port等价坐标只施加一次。只压缩周期冗余，不消去内部自由度；所有tet内部、边/面与828端口都在这一全局系统内。正式标签为`FULL_UNCONDENSED_TETRA_N1CURL_PHASE_UFL`，global finite LU存在，不称factor-free或生产架构。

禁止导入15表、`ChildBlock`/`MacroResponse`、旧raw/Schur/内部LU、`TraceRestriction`、`FaceMacroResponse`来形成新矩阵。通用物理载荷/模式常数/后处理定义可以复用，旧hex边界数值包不能当tetra矩阵。新三角面上重新计算完整C/D/H和入射，生产q47与独立q63各建一次；不能按旧节点/行号搬运或仅保留532/340/40模式。若47/63未过原积分门，按既有规则一次63/79，不剪微小项。

body生产建议degree=2p+3，独立直接Basix作用采用2p+5；须按实际tet元素superdegree核实足够。这里仅限仿射、单元常材料和实κ；Fourier表面、背景指数与跨空间比较不因此降q。独立作用不读生产矩阵/raw，完整body向量与独立端口组合后计算原残差。

代码已支持tetra高阶MPC，优先调用；不要误走旧hex-only p2私有入口。Tet的坐标回拉须使用真实3×3仿射J、covariant Piola与正确DOF变换，**不能复制hex的逐轴除宽度/包围盒公式**。用一正一不同方向tet的实际点值/curl和共享周期切向E核对新求值链；不要求法向E连续。旧解析公式可复用，不使用旧FE场构造入射或初值。

## 5. 最小必要资格、完整验收与判别规则

### 5.1 资格与运行连成一个包

只验证新增的6-tet共享/周期拓扑、材料体积/NOTCH继承、tetra Piola/方向、complex MPC、非互伴端口/非零RHS接线、保存读回。标准装配与独立作用用两个固定复向量核对，操作门1e−10、复对偶1e−12。优先复用Task035对应同blob资格，不能重新跑其整套adaptive/DWR；新物理边界与新场验收不可省略。

不例行full pytest/CI、全仓索引、全历史hash扫描、旧15表、旧H2/FX/FXY求解、24弱函数或新的谱/Riesz/NN诊断。必要单元/接线测试与静态检查目标60分钟以内，API适配本身计实现/修复，不伪造测试预算通过。数学仍不可信时不能强行跳过，但不要仅因文档字段或可修复writer停工。

### 5.2 一次完整求解的门

每个case独立物理零初值，标准已资格MUMPS，最多两次既有精化；不扫ordering/shift/ILU/BLR/OOC。解返回立即保存完整u/port/mesh/tag/MPC/κ/source/hash，再审核、释放因子与不再使用矩阵，保留独立作用能力并完成输出。没有凝聚恢复不等于不用恢复MPC物理场。

formal原true/native/augmented/port各≤1e−6，direct内部目标≤1e−10单列，MPC/作用身份≤1e−10。完整total/scattered E/H/scaled-curl、原240点、828物理复振幅/逐mode功率、R/T/A/A_volume及能量全部输出。独立能量≤1e−5；只有残差合格的场可发布对应离散official功率。

新FLAT对解析场沿原场/复通道1e−4、RTA/吸收1e−5、逐mode功率1e−6；不以能量平衡代替解析场。NOTCH新旧比较仍用相同门，但旧R7或FXY不是reference truth，不要求新解同时贴近两个已不一致的端点。

### 5.3 跨网格比较必须真的比较物理场

固定主比较T4/T5；TH3完成后追加T5/TH3。对旧场只做T5/FXY、T5/R7两组，若TH3是最佳新参照，可在同一积分批次补它对应两组，不重新算旧场。所有候选求解/选择冻结后才读旧系数用于评分，mesh/tag/模式元数据可提前读取。

同macro盒内按共同子盒与一致6-tet分割产生积分域，确认每个积分子tet均位于双方各自的一个真实单元内；不先投影任一场，不用粗单元一个中心代替积分。共同q23/q31、运算尺度≤1e−10，必要一次q39；真实J和相位、相同背景/分母保持。选点在材料面上的归属沿既有一侧规则，不因tet编号换物理侧。

T4/T5通过只能标`TETRA_P_INCREMENT_PASS`。若TH3同样与较丰富解在完整门内一致，授有限交叉参照`BOUNDED_INDEPENDENT_REFERENCE_AGREEMENT`，仍非连续误差上界/无限模式收敛。若T4较粗而T5/TH3通过，不再要求新解反过来修好旧T4；保留其FAIL。相反，TH3不同意时不能只挑T4/T5这组好结果发布收敛。

新tet稳定且接近FXY/R6簇，只说明证据倾向该簇；稳定且接近R7簇则反向，旧结果原式资格均不回写。若新tet仍不稳定或两簇都不接近，保存实际独立场和差异，明确当前仍缺准确性参照，**不默认追加第六个PDE或宣布现有某种方法必错**。

## 6. 资源、持续排障和交付预算

10h总研发窗口、科学有载≤8h、最后1h收尾；从首次真实UTC/monotonic/boot绑定，包含实现、失败、修复、等待、完整求解、比较、IO及文档。旧V61closed不刷新。优先F4/T4/T5及完整输出，TH3用真实剩余预算准入，启动numeric前至少为该case及结算保留1800s。

64GiB同时规划、80GiB警戒、96GiB采样树停止保持。本批完整未凝聚矩阵行上限200000仅为有限参考授权；实际N/图、所有body/边界/矩阵副本、factor和工作区先计算。不能把旧100000“凝聚行”硬套在TH3后被迫停工，也不能因为行数允许而直接factor。numeric仍须live树RSS+2×可靠INFOG16/17(decimal MB)+2GiB≤64GiB。估计不可靠或容量超门则不numeric，不靠OOM探路，不更改ordering/shift/BLR/OOC救场。TH3阻塞不取消已完成T4/T5和比较。

MPI1/math1/GPU0/Loader0、自身swap/OOC0、ICNTL22=0，原物理核/SMT/PSI/cgroup/宿主与384GiB邻增长余量保持；一个自身heavy actor/一个factor，不修改邻任务或系统库/ABI/共享Git。新三角表和求值缓存优先按p/参考点/真实J有界复用，额外临时workspace≤2GiB并计总规划。

新增ignored≤20GiB、Task去重累计≤200GiB、自由盘≥50GiB、证据余量≥512MiB；求解前包含原子写入双份及独立向量存储。只检查本批和所引用父包，不反复哈希旧全树，不删除失败。数值包先保存，JSON与collector失败只补写/补审，**不重算已返回场**。材料、输入、mode或数学改变才允许受影响重解，计入≤5次上限。

普通API/shape/dtype/路径/stage/writer问题同轮修复；不按bug个数停工，累计修复与重放≤2.5h且受总窗约束。同根因两次无效就换诊断或同一数学的正确实现，不第三次盲重跑。新tet构造器不可用可采用上述固定6-tet；标准MPC装配接口冲突可改用完整P的稀疏共轭拉回（不做静态凝聚），不回退旧宏单元PDE冒充独立参照。

安全停止后只在同一预算内重查实际资源，原门恢复方可续作；不能为“不中断”关闭监督。为减少已有长sampling gap，数值前做一次轻量采样活性核验，保留独立监控进程；若仍有长间隔，单列真实最大gap、已观察峰和未知间隙，不能补造历史。无需为优化collector开另一条监控研究线。

## 7. 2TB/48h的下一真实里程碑

本轮不运行原尺寸，不重新复制旧几亿自由度情景表。新增证据应是：①同物理的独立完整场和不一致区域；②tetra空间真正的FE/图/fill、T_N1、RSS与边界库存；③哪一个现有准确性假设得到支持或被否定。N1从本case启动到必要构建/求解/完整输出/独立审核/IO清场，研究比较另列T_research；编译或OS缓存如实标，旧父准备不免费。

较少tetra行数本身不证明同精度更省；同精度未成立时不计算“生产加速比”。若有限参照闭合，下一步才选择精度合格表示并把既有低存储局部作用接向matrix-free的凝聚接口迭代/流式DtN。必须有有界PC/粗问题、全量内部恢复生命周期、真实MPI复制和Krylov V/Z库；无全局矩阵不等于总内存合规。NN只在实测准确链的明确昂贵环节证明净收益，当前不重新启用NN-PC。

独立参照无法在本预算内达到1e−4时，也要交付已取得的全场和准确性限制，不将“新后端跑通”升级为目标pass。原尺寸的accuracy-qualified网格、实际模式库存、factor/PC增长、迭代次数及≤172800s仍逐项unknown，不以256GiB旧no-go或本次64GiB资源停止推断2TB不可行。

## 8. 提交和一次性交付

只在本分支增加显式opt-in、可复用的tetra参考小核（建议`src/solvers/independent_tetra_reference.py`及相应窄geometry/output适配），复用`run_case`、原监督/Journal/事务保存与metadata，不复制每case大runner。C1提交薄tet网格/标准完整装配和针对性回归；C2提交解析校准、独立作用、共同场比较及dat；活跃科学actor期间不改变受检源码。

实现、targeted回归、commit clean、validate后，按上述Gate经资格activation执行以下**待创建**one-run入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v62_tetra_reference_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v62_tetra_flat_p4.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v62_tetra_notch_p4.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v62_tetra_notch_p5.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v62_tetra_notch_h2_p3.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v62_compare_verify_cost.dat
```

条件F5和修复重解须另有明确dat/run_id，不在preflight或VERIFY里暗藏solve。每dat只表示一个明确计算；完整绑定`input_original.dat`、`resolved_config.json`、`run_manifest.json`、input/physical/discretization/source/数组hash、ABI/MPI/线程、资源和run_summary。入口未实现不能提前声称可运行。

交付`response_v62.md`、`outcomes/independent_tetra_reference_v62.md`与紧凑records：实际新旧依赖分工、几何/基/材料/模式身份、F解析结果、T4/T5/条件TH3完整场及原式、共同积分/比较、nnz/fill/生命周期/T_N1/T_research/采样、修复和未运行原因、一个唯一下一pilot。summary、README与两总账追加短入口；旧task/review/response/raw不改。无需为一次发布再复制上万条父数组索引或重建全部历史导航。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

核对remote完整SHA/upstream/clean、closed/active null、清场和锁释放后交付用户暂停；不merge、不改master/邻支、不通知隔壁、不自动开新窗口。GitHub网页视觉未取得就记NOT_VERIFIED，不能为网页或Markdown问题重跑PDE。

## 方法来源与审阅验证边界

标准完整形式装配依据[DOLFINx 0.10 API](https://docs.fenicsproject.org/dolfinx/v0.10.0.post3/python/generated/dolfinx.fem.petsc.html)；complex约束须使用Hermitian对偶见[DOLFINx-MPC](https://jsdokken.com/dolfinx_mpc/)；Nédélec tetra与hex属于不同多项式空间及阶数约定见[DefElement定义](https://defelement.org/elements/nedelec1.html)。这些文档不证明本次tetra方案一定达到0.7nm准确性，更不要求升级当前资格化ABI。

审阅端完成确定性周期6-tet拓扑/自由度组合计数、文档结构检查；没有新FEniCS、PDE或工作站测量。所有新空间、时间和精度结果必须由V62实际取得。公开网页引用和历史Task035资格不能替代此次完整物理校准。
