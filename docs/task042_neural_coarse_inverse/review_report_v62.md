# Review V62：保留四面体主线，以p6参照和一次局部h对照控制精度成本

## 0. 裁决、目标与唯一身份

**V63按有限实现与交付接受，`pass_with_qualifications`。A/B完整方程、场输出、精确边界支撑压缩和差分积分实现成立；细网格p4/p5的散射场和240点增量仍未通过，不能授连续准确性、同精度资源改善、NN收益或原尺寸2TB/48h资格。** 普通bug已同轮解决，获准队列已经结束；本轮不是重新补跑V63。

授权 **V64_P6_REFERENCE_AND_LOCAL_H_PILOT**。保留Codex建议的一次同网格p6完整参照，同时安排一次由已保存p4/p5场差指导的局部h细化p4完整对照。前者回答继续升阶有多大收益；后者回答能否不在全域增加阶数、而把自由度用在差异较大的区域。两者都是有限候选，不预设任一更准确，不保证本批达到1e-4。

要消除的blocker：**准确性还未闭合，而全域升阶的时间、因子与向量规模已经明显增长；目前缺少“精度改善与新增自由度/完整成本”的有界对照。** 不把新一轮变成一份定位报告，也不在本批开发新的PC、NN、矩阵自由求解器或自适应框架。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-08 Asia/Singapore
reviewed_HEAD          = 17e953f12502b0dfded7778e751d2274d12e5295
latest_commit_UTC      = 2026-10-08T12:24:56Z
latest_commit          = docs(task042): seal V63 final costs streams and closed cleanup
latest_response        = response_v63.md
previous_review        = review_report_v61.md
previous_review_commit = a3bbf90bf37810911bf1fa287cb77a30f2b50832
previous_review_sha256 = 7a36d595b8d5edd2bc181dee58feb93886b9ac671d203e6e904761f65795df30
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V64_P6_REFERENCE_AND_LOCAL_H_PILOT
required_response      = response_v64.md
ordinary_default       = UNCHANGED
NN_training_and_PC     = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

最终目标保持：真空0.7nm，原50×25nm周期、z=-10..130nm，周期单胞内任意非可分三维材料/几何，complex128 Nédélec H(curl)，x/y双Floquet、z完整Fourier-DtN，输出复E/H、衍射、R/T/A和独立体吸收；必要准备到独立验收不超过172800s。约2e12B是整机物理内存，必须保留系统余量。本批仍是s=7/135的有限Full3D参照，不是原尺寸或Hybrid生产资格。

本报告明确覆盖旧V61“不准p6”和“不得局部h”的本批限制，以及旧600000行限制；仅授权以下P6和L4。旧条件1188模式M不进入本批，不恢复废弃附件TC6，也不继续p7、全域h4、hex面扩充或gauge/M扫描。旧报告不改写，上一轮身份冲突已关闭，不再重新导入旧V61附件。

## 1. 实际审阅、结果与收益边界

读取了固定HEAD的根/文档规则、仓库原则、原task、最新README/response/summary、决策及差分区域记录；核对上份正式review之后8次提交，检查当前tetra装配/预算适配及继承的周期tetra细化代码。上一份正式报告通过完整本地副本读取，并核对远程Git blob `4a6048cfd4e01b5459e80f23d9d5666d84bbd182`；没有采用旧3eff附件。目录未发现新增独立supplement或同名新review。未SSH、未重演工作站大数组、未在审阅端运行PDE。以下measured均来自已发布记录，不冒充本端独立数组复算。

证据：[V63回应](response_v63.md)、[专题](outcomes/fine_tetra_accuracy_bounded_cost_v63.md)、[科学记录](outcomes/records/scientific_checks_v63.json)、[保存checker](outcomes/records/independent_saved_pair_checks_v63.json)、[差分区域](outcomes/records/physical_error_regions_v63.json)、[决策](outcomes/records/decision_and_not_run_v63.json)、[最终费用](outcomes/records/resource_costs_final_v63.json)、[run index](outcomes/records/run_index_v63.json)。

| recorded measured | A：7680tet/p4/828 | B：同网格p5/828 |
|---|---:|---:|
| 独立FE / 完整系统行 | 314624 / 315452 | 585920 / 586748 |
| 实际nnz | 59971384 | 156995068 |
| 独立true/native | 2.156588276e-10 | 2.162758944e-10 |
| 完整成功进程T_N1/s | 2270.285876 | 5645.946988 |
| sampled进程树峰/GiB | 18.120335 | 40.259663 |
| body准备/s | 902.3439 | 3775.6771 |
| numeric + 三角求解精化/s | 377.62155 | 503.80717 |
| R / T | 0.076218399264635 / 0.90566511182644 | 0.076218494578928 / 0.90566518681132 |
| A_volume | 0.018116488913546 | 0.018116318613210 |
| 独立能量绝对差 | 4.6214143623e-12 | 3.4570124541e-12 |

formal 1e-6通过，独立direct 1e-10未过，继续分列。没有证据表明约2e-10残差造成约5e-4场差，不能用加精化次数代替准确性研究。A之前91.234595s失败入口不含numeric，保留额外费用；成功进程与完整失败链不混称。OS/JIT缓存未清空，峰为采样值。

| 原完整配对 | scattered E / H | 240点六向量相对范数最大 | 原1e-4门 |
|---|---|---:|---|
| TH3/A | 1.115402136e-3 / 1.088650260e-3 | 3.338761742e-3 | FAIL |
| T5/A | 1.030465941e-3 / 1.018603849e-3 | 2.370138043e-3 | FAIL |
| A/B | 4.894867597e-4 / 5.085759517e-4 | 2.328823313e-3 | FAIL |
| T5/B | 9.085295555e-4 / 9.041092235e-4 | 1.503249768e-3 | FAIL |

A/B total场、复通道6.1088e-5及逐mode功率1.6645e-7通过，不能覆盖散射场和240点失败。240点指标不是“每点的最大误差”，而是六个完整向量相对范数的最大值。较高p不自动是真值。

V63明确取得两项工程收益：每侧实际可写行只占native的约2.67%/2.49%，对应边界临时数组不再包含大量从未写入的体行；新旧T5边界逐位相同。差分分子采用同实载波的精确多项式积分，旧配对再现约1.95e-14，研究VERIFY约509.5s。它们不是全流程同精度加速比，也不能使场误差自动消失。

B的body准备约占完整N1的66.87%，numeric与三角求解约8.92%；A对应约39.75%和16.63%。只在本有限例子中成立，不能外推目标因子占比。当前没有理由把NN-PC恢复成主线；准确空间和总自由度先明确。原始张量/边界/比较优化不应反复重做。

A实际source=`f6f9432904bd3efc1d4c534b3fb2f6bf3ffd07ba`，B=`62516c87b7ad35ffa15bff6413cb419bf35e686b`，VERIFY=`55a2e4f6d55571cf9e367889ce9a1e5c49c4208e`，最后checker=`7573da844f3b05e4cc002d057e7438eb8979e23e`。父解数组SHA：A=`8b62d15c074fe3c0c348630817ff54c9138121cf3664636a1b3164f33cca512e`；B=`68933f0bee9cc1382be2a7c3bf45321bb1ce2d7fac5d0a444ef1659793862862`。实际路径和成员hash从V63清单读取，不猜造。

## 2. 本批物理身份与两个互补的完整计算

固定V63的未舍入几何、真实NOTCH、材料、入射、背景、原κ和828物理mode键。s=7/135，λ0.7nm，grazing1°/azimuth5°/s/幅值1；κ=(8.94046081729244,0.7821889682108057,0)。Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；材料表hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。不再索要材料，不联网替换。

| planned角色 | 新空间 | 规模与权限 | 作用 |
|---|---|---|---|
| P6 | V63同7680tet网格，统一N1curl p6，828模式 | derived独立FE980352、完整981180行；限1000000行 | 一次更高阶完整参照候选 |
| L4 | 从该7680tet网格作一次相容局部h细化，统一p4，828模式 | 实际cell/FE由网格产生；限19200tet、800000完整行 | 检验差异指导的分辨率分配是否比全域升阶有用 |

P6使用现有周期实体E=9152、F=15488、C=7680和pE+p(p-1)F+p(p-1)(p-2)C/2计数；tet p6局部维数216。以上是derived，不是实际分配、factor或RSS。P6不改网格；L4只改变mesh，不改材料几何或统一p4。两路均求完整未凝聚UFL系统，仅消除周期冗余；保留全部内部未知量。不得把低阶PC称作本轮求解空间，不引入旧hex凝聚、15表或局部LU。

先冻结L4的标记规则及网格，再求P6；不得看P6结果后重新选择标记。新L4可使用旧A/B的差分来选网格，这是本报告对旧“旧场仅用于末端评分”的明确有限覆盖；旧系数不得用于RHS、物理初值或复制新解。P6不读A/B系数初始化。L4不是盲测，也不是无需前处理的单次方法。

## 3. S：一次有界的差分标记与相容网格，不另造自适应体系

### 3.1 从已保存真实差分取指标

优先读取V63 A/B公共cell差分平方积分、B的原散射范数和几何父键。不得重复全部q31积分，只为缺失的最小数据补消费。每cell指标固定为：

```math
\eta_K^2=\frac{D_{E,K}}{N_E}+\frac{D_{H,K}}{N_H},\quad
D_{E,K}=\int_K|E_A-E_B|^2,\quad
D_{H,K}=\int_K|H_A-H_B|^2.
```

N_E、N_H为旧B的对应全域散射平方范数，沿原单位与原floor的平方，不能改用cell自身范数或事后选分母。H也可用一贯的Hcode，但分子分母同单位；不再把scaled-curl重复计作第三个权重。两场背景相同，total/scattered差分分子相同。检查所有cell累计重现旧A/B分子至原操作门，只有这个复用检查，不重做V63全审核。

按eta平方降序、相同值按冻结几何键排序，选择最小前缀，使其覆盖总指标的50%。固定theta=0.5，不根据求解结果扫描theta、不按Ey份额选y、不围绕240点评分位置刻意加密。输出初始标记数、实际覆盖、最大前10%单元覆盖率和区域分布。若几乎全域都需标记，照实显示局部方法没有明显定位优势。

这是两个离散解之差驱动的一次h实验，不是经过可靠性/效率证明的Maxwell估计器；不假设p5是真值或满足saturation。Dörfler的集中标记思想可以使用，但其Poisson收敛定理不能直接转用本不定复数Maxwell。指标小也不证明未标记区域准确。

### 3.2 复用继承的周期tetra细化，保留真实父子身份

复用`src/adaptivity/periodic_tetra_refinement.py`中已有cell/edge周期闭合、相容细化及正定向重建，不启动Task035历史PDE、DWR或训练。源码的`full_boundary_synchronization=True`会额外标记整个周期边界；这不是零成本，必须列出额外边和最终cell数。

第一次固定使用已有的mate-only edge closure，即显式False；实际共享面和周期三角剖分审计不通过时，仅允许一次相同标记集合、True同步后备。两次都只建网格，不运行试探PDE，不为凑容量调theta或删周期配对。记录每种闭合的成本与真正新增单元。任一合法mesh必须不超过19200tet及800000行；超限则记L4_CAPACITY_NOT_ADMITTED，P6继续，不能把超限网格偷偷缩成另一实验。

`mesh.refine`父cell与后续正定向重建的排序必须组合成新cell到原7680cell的准确映射。通过父标签继承材料/NOTCH；若已有包装器重新按几何打标签，应与继承标签逐cell核对。相同材料总体积及缺口盒不变；新缺口tet数量不再硬编码192。坐标只用于身份/配对的容差键，不能把网格坐标舍入后改变物理边界。六外表面重标并审计周期配对、正体积和完整覆盖。

将实际mesh/tag/父关系作为`mesh_override`或等价显式输入传给已有tetra setup/加载器。不要让旧`physical_for`重新生成uniform mesh覆盖它。新保存场加载必须重建自己的真实连接与标签，不能只靠h_ratio或cell count猜网格。所有局部细化后的全场比较在各细子tet内直接评价双方原场，不能先投影一方。

S的工程适配目标90分钟、上限2小时；不能以旧父记录的策略性超时掩盖数值身份错误。新网格接口接不齐就隔离L4、保留网格/阻塞收据，并用原可信路径完成P6；P6容量否决但L4合法时反向继续。不要为证明“旧工具能用”重跑其完整测试套件。

## 4. 完整PDE、共同比较与可解释的裁决

P6复用V63标准UFL/FFCx完整相位弱式、精确可写边界支撑、Hermitian MPC拉回、原端口坐标、PUBLIC_BASIX独立作用和无JIT体吸收。L4同样复用，只显式注入合法的新mesh。三角q47/q63分别重新生成，改变p或mesh不能搬旧数值包；相同物理828 keys、C/D和非零载荷保持。body沿2p+3/2p+5并核对实际superdegree，P6为q15/q17，不将该多项式规则用于指数背景或表面Fourier积分。

连续执行：S与必要接线/容量 → P6完整解与保存 → L4完整解与保存 → 一次新增比较/收口。S部分诊断未完成不阻止P6；P6场FAIL不阻止L4。P6若确实资源/时间不准入，L4作为独立完整物理工作继续。没有合格mesh时不能强跑L4，不能以原uniform p4重复求解冒称局部结果。

每case物理零初值，原MUMPS、最多两次既有精化；不扫描ordering/shift/ILU/BLR/OOC，不换新PC或自动凝聚。每次numeric前核对scope中的实际row cap和预算，不能仍被600000硬门拦住，也不能直接修改admitted=True。返回完整向量立即保存，保留独立原作用；释放factor及无用矩阵后完成全部输出，后处理失败只补消费。

formal true/native/augmented/port各≤1e-6；direct目标≤1e-10继续独立列出；MPC/恢复/操作身份≤1e-10。两固定复作用见证覆盖新p/mesh和828端口。production与独立残差混称禁止；独立direct略超但formal通过时保留子FAIL并完成输出，不以无限精化拖住。

完整total/scattered E/H/scaled-curl、原240点六向量相对范数、参考面复振幅增量≤1e-4；R/T/A/A_volume及独立能量≤1e-5；逐mode功率增量≤1e-6。240点的一侧物理归属不因tet编号变化而变，不排除较难点，不用能量或total通过覆盖散射FAIL。

主比较仅B/P6、A/L4、B/L4、P6/L4（实际可得者）。保留原右侧场分母、左侧模式分母及近零floor；额外再输出一个固定P6共同分母的“效率对照列”供比较A/B/L4，不替代原Gate。P6 unavailable时不能编造共同reference效率。旧A/B、旧hex评分不重新全做。

| 新证据组合 | 本批允许的结论 | 禁止的结论 |
|---|---|---|
| B/P6全部增量通过 | 固定828、同fine mesh的p5/p6增量通过 | P6是真解、无限模式或所有h方向通过 |
| L4/P6通过，且B/P6也通过 | 对本有限题有两条空间一致性证据；按实际费用评估L4 | 自动成为2TB生产自适应或严格误差界 |
| L4对未参与选区的P6更接近且成本合适，但仍超门 | 有界局部分辨正信号，完整Gate仍FAIL | 用“下降百分比”替代最终1e-4 |
| P6仍变化、L4也不改善 | 如实关闭本批两候选，不继续原样p7或第二轮theta扫描 | 把真实精度差说成软件bug |

同一mesh的p5/p6并不提供空间独立性；L4来自A/B选区，P6虽未参与选区仍是候选参照。即使有限一致性通过，828模式截断还须以后独立资格，不将旧hex的M增量继承给新tet。当前不追加M是为了让两条空间路径和完整验收收口，不构造“空间不过永远不查模式”的永久规则。

## 5. 减少重复测试与持续排障

V63实际support压缩、同载波多项式差分和旧FLAT资格直接复用。不重开发边界压缩/比较器，不重跑旧A/B、旧Q0/FLAT、15表、宏面扩充、24弱函数、gauge/M或旧Task035 PDE。

只补p6角色/行预算、mesh_override与保存加载、父标签/周期相容、共同积分父关系的targeted回归；相关Ruff/compile/dat validate及一次紧凑文档检查。新增数学不可信不能跳过，但不要将全库pytest、全仓索引、全部历史hash或网页渲染变为数值总前置。

已返回解、已完成积分块优先补消费。普通API/shape/dtype/路径/schema/writer/collector错误在同一窗口定位、最小修复、受影响回归后继续，不按bug个数停工。同一根因两次无效后换诊断或隔离该路径，不第三次盲重跑；累计修复与受影响重放≤2.5小时。无关文档错误不触发PDE重解。原式、材料、ABI、映射或监督确有问题，先隔离其依赖；不能改变精度门、材料或分母“修成功”。

两项计划新全域solve，最多第三次仅用于确认后的科学修复重放；完整返回后的保存补审不占新solve，也不得暗藏factor。不得为失败统计/缓存计时另外开一个相同旧PDE。若某一路受阻，完成另一条可信路径及其全部物理输出；不把单一新接口的问题扩大到整条任务。

## 6. 时间、容量与现场隔离

新12小时总研发窗口，科学有载≤10小时，最后1小时交付；首次UTC/monotonic/boot绑定，所有身份核对、实现、修复、失败、等待、比较和IO计费，不重开V63。先做一次完整费用预测，不以最后solve几秒估算。P6完整case配额≤18000s、L4≤10800s，都受同一总窗约束；每次numeric前需为其原式/输出和全批收尾保留至少3000s，新增共同比较至少预留3600s。预算不容纳时提前保存not_run原因，不先耗尽准备再删验收。

| 本批独立profile | planning GiB | warning GiB | sampled tree stop GiB | 额外形状门 |
|---|---:|---:|---:|---|
| S和默认消费者 | 64 | 80 | 96 | 不暗藏全域solve |
| P6唯一同网格p6参照 | 192 | 224 | 256 | 完整行≤1000000 |
| L4唯一一次局部细化p4 | 128 | 160 | 192 | ≤19200tet，完整行≤800000 |

P6额度是一次有限accuracy参照许可，不是由2TB整机推出的自动准入；旧B的73.05GiB计划和40.26GiB采样峰只作校准，不证明P6资源。所有profile在plan/dat/resolved中冻结，贯通Journal、launcher/watchdog、assembly、factor和collector，旧默认不改、旧账不改、不同role不借额度。

numeric仍要求：实时树RSS + 2×可靠INFOG16/17估计（decimal MB）+ 2GiB ≤ 本role planning。先真实MPC图/所有CSR副本/三角包/临时乘积规划，再symbolic，未知fill不得按行数线性外推为准入。估计不可靠或超额就不numeric，不OOM探容量，不改排序/shift/BLR/OOC救场。局部mesh的周期闭合可能扩大图，计入实际而非只报初始标记。

MPI1、CPU/math1、GPU0、Loader0，complex128及原int64 ABI；ownswap/OOC=0、ICNTL22=0，原PSI/有效cgroup/宿主保留和384GiB邻增长余量不变。只使用合格空闲物理核并避忙SMT，一个自身heavy actor/一个global factor；不修改邻任务、系统库/驱动/全机swap或共享Git配置。实际sampling gap与sampled峰分列，不能由0.5s设置推定连续峰。

新增ignored≤40GiB，Task去重累计≤280GiB，free≥50GiB，证据余量≥512MiB。求解前计入完整原向量、微网格、独立作用、所有828mode与原子写双份，不复制旧场为新结果，不删除历史失败。只核对本批及直接引用父包，避免反复扫描全历史。

## 7. 2TB/48小时的实质交付与分支去重

本轮必须同时给出实际误差增量、FE/nnz/fill、完整N1和同时峰；不能只报告“又多了一阶”。局部h的收益比较不能免费使用A/B：分别列L4本次prepared-mesh N1、标记/网格成本、历史A/B必要生成成本及失败链。若部署每个新几何都需要先算A/B，完整adaptive lineage必须包含它们；没有同精度配平对照不授生产速度比。P6没有成为真值时只称“相对候选参照的成本—差异表”。

若少量单元承担多数差异且L4改善，可为后续有界局部分辨提供实测依据；若差异广泛、闭合引起大量细化或L4成本超过P6，也明确否决该配置，不把自适应名称当作收益。无论哪种结果，保持低存储局部作用/静态凝聚的历史成果，不直接将完整tetra LU放大到目标。

准确性参照足够后，下一阶段是把选择的空间接到凝聚trace上的matrix-free分布式作用、可扩展PC/有界粗问题、流式DtN和分块内部恢复，而不是把全FE向量放入每条FGMRES方向。当前原尺寸的合格网格、实际模式、迭代、PC/fill、全过程RSS及172800s均尚无证书。旧256GiB结论、当前有限资源停止与2TB可行性不能混同。

邻支只读冻结：Task42extra `7aa0df9b41ee1722e7a29cafbaa4e02314f063f0` 最新Review V32授权V33固定容量波动回拟合；本支不训练其网络、不做M5/teacher/VarPro。工程线 `33614413731d739d2c0f57106df180c359f4343f` 提交Review V18（提交说明为Ny8和容量推进），本次只核对ref/commit，不冒称重审其全部结果；不复制参考PC/通用CSR。dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`仅核对ref，不推断未推送本机状态。Task035只复用已继承的局部细化函数，不恢复历史campaign。

## 8. 提交、入口和一次交付

C1只接新scope、P6角色/资源及S父数据标记；C2接合法局部mesh及比较父映射。公共功能进入`src/`，复用`independent_tetra_reference/fields/study`和原runner/保存消费者，不为每个case复制大型runner。实现targeted回归后commit clean、validate，再正式运行；活跃数值期间不热改其受检源码。

以下是待创建的one-run入口，不提前声称可运行：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v64_resolution_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v64_tetra_same_mesh_p6.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v64_tetra_marked_h_p4.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v64_compare_verify_cost.dat
```

preflight/S没有全域solve；VERIFY不暗藏factor。每个dat绑定实际input_original、resolved_config、run_manifest、input/physical/source SHA、材料/mode/space/mesh/数组hash、ABI/MPI/线程和资源。新review只保留这一份最终正文；从同一commit读回核对blob后交付，不能再另写一个同编号附件版本。报告哈希不应作为数值父场哈希，两种身份分开。

交付`response_v64.md`、`outcomes/p6_reference_local_h_v64.md`及紧凑records，至少含S指标/标记/周期闭合/父标签、P6/L4完整场与全部门、原分子分母、NNZ/fill/N1/lineage/峰/gap、失败/补消费和唯一下一pilot。summary、README和两总账追加短而可解释的条目；旧task/review/response/raw逐字保留，不复制海量旧JSON为新证据。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

核对remote完整SHA、upstream/clean、closed/active null、后代清场与锁释放后交付暂停；不merge、不改master/邻支、不通知隔壁、不自动开新窗口。GitHub渲染无证据则记NOT_VERIFIED，不为网页重复数值计算。

## 方法依据与审阅端边界

[已继承的周期tetra细化](../../src/adaptivity/periodic_tetra_refinement.py)提供实际cell/edge配对与相容细化；[DOLFINx 0.10 mesh/refine及标签传递](https://docs.fenicsproject.org/dolfinx/v0.10.0.post3/python/generated/dolfinx.mesh.html)给出父子关系接口。使用现有ABI，不升级到文档中的其他版本。[Dörfler原论文](https://doi.org/10.1137/0733054)用于说明集中标记的出处，不能把其Poisson理论当成本Maxwell差分指标的可靠性证明。[Nédélec元素](https://defelement.org/elements/nedelec1.html)的阶数约定与Basix实测维数需区分。

审阅端只读远程结果、源码和已绑定报告，做了拓扑/比例和文档结构计算；没有运行FEniCS、细化真实工作站网格或重算大数组。新网格、p6、性能和精度均为planned/not_run，只有V64实测后才能给出结论。
