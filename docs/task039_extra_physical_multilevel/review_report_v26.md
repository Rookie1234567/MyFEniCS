# Task39extra Review V26：A6融合与H6共同收缩优先，阶段线程最后试、失败即回退

## 0. 本轮裁决、目标与权限

**先实现并测试p4版本的A6体积作用融合、A6/H6共同张量收缩；用户提出的“setup并行、迭代单线程”放到最后，只作一次有界的两线程候选。该项不正确、不更快、不能证明峰值中性，或需要大幅重构时，立即退回合格单线程组合，不拖住主线。最后仍以同一original p6/h7.5完整计算检验实际收益。**

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task39extra
review_date            = 2026-09-23
reviewed_base_SHA       = bc475f6bc0e1ffbb366983f20b38e060abb71b36
latest_review_response = review_report_v25.md / response_v28.md
speed_baseline_source  = 4bf2bba56cc2e568d56ff3096aeb4a108744f28d
batch_identity         = review_v26_fused_A6_H6_optional_setup_threads
suggested_profile      = physical_p6_trace_fused_kernel_v28
response_required      = response_v29.md
execution              = N0 -> N1 -> N2 -> N3 -> N4(optional) -> N5 -> N6
normal_full_PDE_count  = 1
environment            = qualified personal-laptop WSL/Linux; MPI1
numeric_cache_mode     = build
ordinary_default       = unchanged
master_merge           = NOT_APPROVED
```

要消除的blocker是：**Full3D有效预条件器的细层作用仍然昂贵，造成更多单元或更短波长下单步成本过高。** 本轮不寻找新PC，不改变p4粗空间；优化后的公共细层内核将来可服务p3，但不在本批重跑p3/p2。0.7 nm任意非可分三维与约2 TB仍是最终目标，不把本机固定案例优化当作目标规模资格。

本review把[研究备忘](performance_followup_notes_20260923.md)中的A/B转为明确实现任务，阶段线程仅为最后的条件选项。它替代Review V25本批“仅低风险准备优化、固定全程单线程”的范围限制；旧结果、旧权限和历史负分类不改。**允许必要的局部kernel重组及融合接口，不能只增加计时器，再因“需要新实现”而不尝试N1/N2。** 不授权升级ABI、重写整个求解器或操作工作站。

这是新授权批次，不消费V26/V27已经用完的旧replay额度，也不清零旧账本。正常只新增一场完整PDE；小组件检查集中执行，后续不逐项等用户确认。真实实现bug按现有hash-bound流程修复必要受影响项，最多一次必要正式重放；性能不及预期不算bug。只因可选线程失败不停止整批。

执行前读取根/目录AGENTS、[工作原则](../repository_work_principles.md)、[task](task.md)、两份既有用户补充授权、[Review V25](review_report_v25.md)、[Response V28](response_v28.md)、[summary](outcomes/summary.md)及研究备忘。当前用户要求与本review决定本批范围，不恢复旧的粗阶筛选或诊断任务。

## 1. 实测基线与本轮收益对象

主分母来自[r2完整结果](outcomes/records/v25_q4_ac_swap_observe_r2_result.json)及[明确setup边界](outcomes/records/setup_efficiency_v26_compact.json)。全部为13.5 nm、original、p6/h7.5、990单元、80通道、q4、MPI1/thread1；时间单位s，GB为十进制。

| 对象 | r2实测 | 用途与边界 |
|---|---:|---|
| 完整workflow | 3114.283619607013 | 51.90分钟，端到端主分母 |
| 纯KSP | 2284.681783819 | 38.08分钟，不是monitor.solve_seconds |
| 明确setup | 781.971881371981 | 13.03分钟，由阶段边界取得 |
| 迭代次数 | 126 | 比较基线，不是停止线 |
| 同时进程树RSS峰值 | 7390937088 B | 约7.391 GB，比较量而非新固定硬上限 |
| PC内部live A6 | 263次，823.1639212121663 | 其中volume 822.071849550819，DtN 0.7940302900387906 |
| H6 apply | 131次，484.89414036102244 | 含内部B6工作，不再叠加其子计时 |
| 独立native A6 | 29次，148.35112204798497 | 保留独立见证，不通过删检查提速 |
| 原A6最终残差 | 9.283165086752956e-7 | 原目标1e-6，authority limited |

这些累计动作与父阶段可能重叠，不能相加拼成总时间。[V27配对](outcomes/records/workingset_p6_setup_v27_pair.json)未复现明显在线退化，六组旧/新输出差为0；本轮不重复该历史归因。V27只有工程结果，没有新完整解。[V26](outcomes/records/setup_efficiency_v26_compact.json)的3595.9571450339936 s保留为历史对照，不能用更慢的分母夸大本轮收益。

最新工程定位中，p6 raw tensor生成228.84196730799158 s、局部Schur 11.954928313018172 s；12类raw/26类定向Schur已共享。这里不是大量重复LU，且是工程场，不填入r2作为实测分项。本轮不再把hash、4秒对角或局部LU当主要热点；完整局部矩阵的新积分后端留作后续，不与N1/N2和线程同时重写。

## 2. 冻结最终问题，不更换成功的PC

从[r2输入](../../input/task39extra/v25_q4_ac_swap_observe_r2_h7p5.dat)继承，新的dat只增加run_id、profile和经选择的实现/阶段线程字段。输入、resolved、源码hash重算，物理身份逐字段核对，不重定义历史hash。

| 对象 | 本批冻结 |
|---|---|
| 物理和几何 | 13.5 nm、1°掠入射、azimuth0、s偏振、原Si/air复材料及mu_r；原单胞和original结构 |
| 网格 | 原9×5×22=990单元轴坐标、连接、tag；h7.5不是波长 |
| 细层 | p6 Nédélec H(curl)、原Basix变体、complex128、原积分规则、双Floquet与全部80个DtN key/相位/归一化 |
| 外层 | p6独立trace＋端口199340行，right FGMRES32、max2048、零初值 |
| PC | 原增广逆桥、BAL_H、一次H6与两次逻辑p4修正；不加H4或inner Krylov |
| 粗层 | 同网格p4单元凝聚、84680行、唯一准确全局LU；原矩阵/排序/主元/额度控制 |
| 精化 | 原A4返回<=1e-10；按需最多2次额外同因子修正，累计FE/端口；ICNTL(10)=0 |
| H6定义 | 同一正定B6、正确对角、Chebyshev规则、power10步数和seed规则；不改谱窗倍数 |
| 输出与核验 | 每8步原A6、每32步场；完整E/H、curl、界面量、R/T/A/A_volume、80复模式与逐模式功率 |
| 生命周期 | 必要JIT在大factor前；共享局部数据；factor活跃时保留借用矩阵；最终场核验后释放再后处理 |

保留已资格化的owner传递、有界精化、对角复用及无用参考表删除；同场只读共享按真实身份复用。不强制全盘回滚V26，也不因文件更新就把未测组合称为最快。禁用BLR、降精度、fast-math、积分降阶、删通道、改restart和新粗层；不装配全局A6/B6或保存逐单元稠密库。p3/p2、notch、工作站与其他波长均不运行。

## 3. N1：实现A6的公共步骤融合，优先减少重复工作

### 3.1 为什么做、具体改哪里

当前[FullspaceSplitVolumeAction](../../src/solvers/fullspace_physical_action.py)分别调用curl和mass，再相加；[物理后端](../../src/solvers/physical_equivalent_fast.py)建立两个局部作用。每个作用各自进行gather、方向/MPC处理、Nédélec到多项式系数转换、反向转换与scatter。**共享几何数据只省准备/存储，不等于这些在线操作已经共享。**

新增显式opt-in的融合volume作用。对同一批单元，先取得一次局部系数并转换一次；curl和mass分别按各自原积分规则计算，尽可能合并到共同系数表示后反向转换一次、回写一次。目标是改变实际计算组织，不是仅将两个旧apply包进一个新函数。

以列向量记局部Nédélec到共同多项式系数的映射为T，两个积分分支的结果为s_c、s_m。允许的代数合并是：

```math
T^H s_c+T^H s_m=T^H(s_c+s_m).
```

T必须确实相同，包括系数顺序、嵌入维数与方向约定。复介电系数属于积分分支，不因上式而错误共轭。这里是局部体积代数，不包括另有定义的端口块和slave identity行。

```text
一次gather/MPC展开/方向处理
→ 一次Nédélec到共同多项式系数转换
→ curl按原积分规则计算 + mass按其原积分规则计算
→ 在相同多项式系数空间合并贡献
→ 一次反向系数转换/方向拉回/约束scatter
→ 按原规则加DtN；slave identity总共一次
```

### 3.2 必须保留的语义

curl/mass积分点、权重、点顺序可能不同：分别保留，不用公共低阶积分或点插值凑成同一网格。可共享不依赖积分规则的T和外围操作；若规则相同才共享对应中间表。若不能安全合并反向转换，先实现合格的gather/前向转换复用并报告实际收益，不改数学定义。

新作用保持原返回buffer所有权、alias语义和完整向量覆盖；不得原位修改输入或让两项覆盖同一未消费输出。MPC相位与共轭、方向拉回、ghost处理、strict slave-zero及非零slave的identity合同都保持。最终A6只加一次DtN，不把物理A6与正定B6混用。

旧split路径与独立native A6保留作对照。新volume继续提供完整原bilinear form供单元凝聚借用，不能因component接口变化破坏p4/p6局部矩阵生成；两物理项相加后再凝聚，绝不分别凝聚再相加。正式场不同时常驻两套候选volume工作集。

新增最小计数：gather/constraint、forward coefficient、各积分分支、backward coefficient、scatter的次数/时间与workspace。标明哪些由两次变一次，不要求全场所有逻辑A6调用数变化。先测完整A6 volume/full作用，不只计某个BLAS子段。

## 4. N2：A6/H6共用的张量收缩减少重复算术

H6的B6本来可以一起处理正curl与正mass，不能把已经存在的组合重新当成果。重点是[张量积内核](../../src/solvers/fullspace_n1e_sum_factor.py)中的六个交叉导数、值和反向投影：现在多次从头进行三方向收缩；同一分量的若干分支具有相同前缀或可合并的线性反向工作。

实现一份明确的共同子表达式调度。例如同一分量的y导数与z导数均先做相同的x方向值收缩，可先算一次，再分别走y/z分支；值与z导数还可能共享前两级。选择由实际表身份证明相同的分支，复用只限同一次输入、同一批单元，不缓存上次向量的计算结果。

优先减少前向重复收缩；仅在代数与数据布局清楚时再合并反向投影。保持六个交叉导数的符号与curl分量、原积分点排列、metric和复材料乘法。不要按阈值截断Basix系数，不更换有限元基，不将全三维材料假设成可分离结构。

固定合理batch和有界scratch，使用后立即复用中间buffer；不能为全部单元保留全部导数张量。记录前后收缩次数、实际计时和唯一/临时数组载荷。**仅启用旧projection-reuse开关，或只把einsum换一种写法而没有新算法/收益，不算完成本项。**

先固定同一个对角与谱窗比较B6/H6 apply，避免setup变化混入；资格通过后新B6可用于原power10，步数/seed/对角定义不变，窗口舍入差异记录。H6处理次数不减少，不用弱化PC换取单次更快。可采用“融合A6＋原H6”或“原A6＋改进H6”等合格部分组合，不要求两个候选同时成功。

## 5. N0/N3：少而必要的验证，不再开展一轮历史退化诊断

N0用既有mock先核对入口、stage、返回向量接口、资源策略及checker能识别新profile；不得在大factor建好后才发现apply(source)被误调成apply(source,target)。修正上一轮combined pair里i112旧NOT_RUN字段的scope歧义即可，不重跑旧探针或重写其负历史。

N1/N2先做局部与真实990网格的算子配对，无需p4全局factor。复用已保存早期/后期合法向量，另覆盖零、复数、多次不同输入与非整batch尾部；保持输入hash和原积分/材料身份。测试包括周期映射、方向、复损耗、slave语义、repeat/linearity以及B6能量/等价。当前A6有损，不能误设A6为Hermitian来验收。

每项有实际实现后，与既有合格sum-factorized旧路径短配对：一次预热、通常三次交错调用，保留全部值与中位数、wall/CPU、RSS/PSS及原子项计数。native用于独立正确性，不用更慢的native替代性能分母。时间差被波动覆盖时不宣布收益；不重新解释V26那次18.9%的历史差异。

两项分别量化后选择唯一单线程组合。完整BAL_H兼容检查放入随后需要的唯一p4工作集，最多一次短组合检查，不为每个开关/向量反复numeric。工程因子若必须单独建立应明确成本；正式场必须fresh numeric build，不能称工程setup免费。正式源冻结前完成选择，不在KSP中自动调参或热改代码。

“实现尝试后不更快/不合格”与“未实现”分开写。主候选不合格可做针对性修复后再测，仍不合格则回退该项并继续另一项；不漫无目的扫描batch/编译参数。N1/N2不能用“没有低风险优化”一行文字代替具体实现或明确的技术阻断证据。

## 6. N4：阶段多线程放到最后，仅两线程，失败立即退回

**只有N1/N2的单线程结果与选择已写清，才进入本节。** 用户要求的回退只撤出线程/相应前移，不撤销前面已合格的内核优化。不开展4/8线程扫描、不并行MUMPS numeric、不多核迭代、不复制求解进程。

候选只处理不同p6 raw tensor类型的独立C核；先由主线程串行完成必要JIT、输入和函数指针准备。核可重入性、独立输出、异常回收和真实并行入口有依据才试2个worker；每个worker内BLAS保持1。MPI、PETSc/MUMPS、cache登记和全局装配仍由主线程执行。

优先将仅依赖网格/材料/积分的raw生成前移至p4大factor之前，生成后join线程，释放临时数据，后续只借用一份结果。若前移需重构整个setup、复制大缓存或无法闭合factor阶段峰值，**不前移、不强开线程，直接保留单线程流程**。本节不重写FFCx积分核，不开发持久化缓存。

```text
可选局部准备2线程（内部BLAS1）
→ join/关闭局部线程池，确认结果完整且无共享写入
→ 主线程确认原线程上限及CPU affinity已恢复
→ p4分解、其余setup、FGMRES和后处理均按合格单线程
```

两线程先用同一组类型做一次短的1/2线程对照，计入join、工作区与保留数据，不建p4全局因子只为测试并发。使用实际不同类型数量，不把12硬编码进通用实现；不能把所有worker绑在同一核。运行时库控制需实际支持并读回，不能只修改已初始化库的环境变量便声称切换完成。没有控制能力则回退，不升级ABI或安装监控平台强行实现。

峰值中性判断覆盖整个生命周期，而非只看并行区间：

```math
M_{\mathrm{peak,new}}=\max\{M_{\mathrm{local,2}},M_{\mathrm{factor,new}},M_{\mathrm{iter,1,new}},M_{\mathrm{post,new}}\}.
```

前移保留的raw矩阵、线程栈、BLAS/allocator残留和采样范围全部计入；切回1线程不等于这些内存已经释放。比较对象首先是**本轮相同单线程内核组合**，不能用融合节省的空间掩盖线程额外长期驻留；整场还需与r2的7390937088 B比较。临时阶段可使用后续阶段的真实余量，但不能自行设允许增长百分比，或仅凭派生bytes宣称实测峰值不变。没有足够依据就不采用线程。

任一项出现无明确加速、数值差、峰值风险/残留、切换不可靠，立即选N3单线程组合，不再修第二套线程方案。线程失败产生的部分结果仅在完整身份/数值检查通过后才能复用，否则丢弃该项并串行重建；有数据损坏或无法清理的线程时停止worker，不能假装已安全回退。

正式前尽量完成这个可选项的裁决。若正式setup首次暴露可安全回退的问题，按已冻结的fallback在进入KSP前回退，保留原始全过程峰值和成本；不得清零峰值、改标签冒充纯单线程运行。无法证明峰值中性则线程资格失败，已有有效内核结果仍保留；不为此自动追加第二场完整PDE。

## 7. N5：一次完整p6/h7.5（q4）回归，不能只交组件加速

选择和必要测试完成后提交clean source，使用既有`python scripts/run_case.py input/path/to/case.dat`与独立service/watchdog直接运行。新batch授权覆盖本轮，旧replay额度不得误挡；复用现有参数化runner，不为每个阶段复制脚本。源码冻结后不热改数值实现。

正式场保持第2节全部身份；合格JIT可复用，**所有局部数值数据与全局因子本场build，numeric_cache_loads=0**。只建一份准确p4因子，跨全部回代复用；setup合格后直接完成KSP与输出，不停在准备阶段等待用户再授权。组件oracle的重复buffer在正式迭代前清除，独立native A6保留。

只要有经过正确性/组件测试选中的实际改进，正常完成这一场以验证端到端收益，不要求先承诺节省多少百分比。若N1/N2和可选线程经实际尝试均未采用任何变化，则明确NO_ADOPTED_CHANGE，不无意义重跑r2。当前126步、51.90分钟都不是终止上限。

| Gate | 沿用要求 |
|---|---|
| A6/B6/H6等价 | 操作尺度relative<=1e-10；已有更严伴随/局部合同保留；near-zero按原绝对规则 |
| H6对角 | 同一定义、正实finite、relative<=1e-12；约束交叉项不能省 |
| 原A4每次逻辑返回 | <=1e-10，最多2次同factor精化，累计总FE/端口；零输入不除零 |
| 凝聚、端口与恢复 | 原局部/桥接检查与<=1e-8闭合；非零内部RHS和非Hermitian左右耦合保留 |
| 原A6最终 | 完整p6场恢复后，释放前后独立true residual<=1e-6 |
| 同离散场回归 | 相对r2的FE L2/scaled-curl、同坐标E/H/界面与80复模式relative<=1e-4 |
| 功率和守恒 | R/T/A/A_volume绝对差<=1e-5，逐模式功率最大绝对差<=1e-6；两项能量闭合<=1e-5 |

不拟合相位、不重归一化、不减少检查或输出。允许等价浮点重排，不要求所有hash或迭代数机械相同；显著收敛改变需解释。逻辑A6/B6/PC计数与融合后的底层计数分开，不能硬编码旧split的两次wrapper调用作为物理正确性标准；仍核对每次BAL_H的两次逻辑粗修正和实际精化。

全部通过仍为DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED；r2没有独立h7.5高精度参考，回归一致不等于连续真解、网格收敛或短波鲁棒。

## 8. 安全、内存与计时：让最终能看清每一步省了什么

本机一次一个heavy，全程接电并固定现有电源模式；不改散热保护、不触碰工作站。短preflight检查branch/HEAD/worktree、合格complex128/int32 ABI、MPI/线程、输入/物理/网格/80通道、有效RAM/cgroup、实时余量、磁盘及独立watchdog。现成可读的AC、CPU time/频率和线程状态随阶段保存，缺失写unknown；线程选项所必需的状态不明则回退，不能拖住单线程主线。

新profile延续最近明确授权的time/swap observe_only，并在wrapper、worker、watchdog与resolved中读回一致；实测zero-swap仍是性能比较目标。真实物理内存压力、系统余量、数值breakdown、非finite、未修复质量错误、写盘/监督异常仍安全终止，OS OOM不是正常终态。不恢复旧6/8 GiB库存或固定2倍symbolic作为唯一阻断，不擅自提高p4 ICNTL(23)额度。实际发生作业swap就限制资源/性能结论，不用交换支撑更大缓存。

N1/N2原则上复用和减少原工作区；新增固定scratch必须计入同一进程树RSS/PSS和唯一数组账。对线程的不增峰值要求不能以“切回单线程”替代证据。各阶段峰值不相加，factor原生allocated/used不冒充RSS；工程两候选共存的内存不称正式单候选峰值。

复用已有计时字段，不建新profiling平台。最终至少给出以下一张逐步表：

| 计时组 | 必须报告 |
|---|---|
| setup | JIT hit/miss、细/粗空间与约束/端口准备、H6对角/power10、p6 raw kernel/局部Schur、p4装配/symbolic/numeric、桥/必要检查 |
| 在线A6 | gather/约束、正向系数转换、curl与mass积分分支、反向转换、scatter、DtN；逻辑次数/累计/每次均值 |
| 在线H6 | apply与B6、共同收缩次数及耗时、工作区；子项不可重复相加 |
| 其他迭代 | P/PH、粗RHS缩减/回代/恢复、原A4核验与精化、外层Schur、正交化及已能独立取得的包装开销 |
| 收尾 | 最终原A6、释放、保存场和物理后处理 |
| 可选线程 | 串/并行局部准备、join/切换、前移后保留bytes、factor/迭代/全过程峰值与回退原因 |

每行说明inclusive/exclusive、原始起止或累计count。无法分离的旧项写unknown，不以差值命名成某个未测热点。full/setup/KSP使用同一时钟和边界闭合；UTC、monotonic、process CPU不同口径并列，不挑更短的时钟。component warm-up、编译、独立测试和工程重建成本另列，不从批次成本删除。

```math
S_{\mathrm{full}}=\frac{3114.283619607013}{T_{\mathrm{new,full}}},\qquad
S_{\mathrm{KSP}}=\frac{2284.681783819}{T_{\mathrm{new,KSP}}}.
```

主要分母是r2；V26只作历史附列。组件更快但整场没快就分别判读，不自动反复重跑。线程若采用，setup收益与单线程在线内核收益分开；没有全流程对照不能宣称纯线程因果加速。

## 9. 提交与交付

建议提交：D1局部融合/共同收缩及针对性测试；D2唯一profile/dat、线程选择/回退和clean source；D3正式结果、轻量证据及response。数值实现进入可复用src；只做必要runner/schema接线，不整体merge旧分支、不改ordinary default、不amend/强推、不合并master。

相关fixture集中覆盖Nédélec方向、不同积分、复材料、约束、buffer生命周期、H6与bridge；线程只增加必要的可重入与回退mock。复用已有测试框架，不每改一行跑全库。lint/compile/文档合同与本地/远程渲染按仓库要求核对，未执行CI或全库测试如实not_run。

可合并轻量文件，但至少覆盖：

```text
outcomes/fused_operator_speed_v28.md
outcomes/records/fused_operator_speed_v28_components.json
outcomes/records/fused_operator_speed_v28_selection.json
outcomes/records/fused_operator_speed_v28_setup_threads.json
outcomes/records/fused_operator_speed_v28_compact.json
outcomes/records/fused_operator_speed_v28_decision.json
response_v29.md
```

正式证据仍绑定input_original.dat、resolved_config、run_manifest、input/physical/source SHA、run_summary、环境/MPI/线程、mesh/mode/数组身份、原残差、资源与输出hash。大型field/matrix/timeline留ignored artifacts。同步summary、test_summary、run_index、development_progress和模型总账，保留旧负结果。

response必须直接回答：A6实际减少哪些重复步骤；H6少做哪些收缩；各组件和完整p4运行分别快了多少；每步和setup分别用了多久；峰值是否增加；阶段线程有没有尝试/采用/回退及依据；最终场与功率是否保持；下一最大热点是什么。若没有收益，给出已实现候选和具体负证据，不用“任务完成”替代性能结论。

执行完推送同一task39extra分支并报告完整HEAD/工作树/上游状态，统一待审。**线程不成功就收回这一项，前面的合格内核继续交付；本轮不转为新的线程调参或历史慢场原因调查。**
