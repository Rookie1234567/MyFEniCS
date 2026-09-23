# Task39extra Review V25：正式工作集配对与p6准备热点优化

## 0. 结论、目标与新增执行授权

**保留r2的51.90分钟作为速度基线；接受V26的离散正确性及H6对角局部加速，不接受“V26已经整场提速”。本轮先在同一正式规模工作集下，区分A6/H6/PC的实现开销与跨运行波动；随后只优化p6准备中实测占主导的一项，保留已证实的局部收益。选定组合后，正常只做一场新的original p6/h7.5完整回归。**

```text
repository                = Rookie1234567/MyFEniCS
branch                    = task39extra
review_date               = 2026-09-23
reviewed_base_SHA         = 73d1f1f4ee3e13b85ceac6c37b667857f6d0576a
base_latest_commit        = Record V26 setup efficiency closeout
latest_review_response    = review_report_v24.md / response_v27.md
speed_baseline_source     = 4bf2bba56cc2e568d56ff3096aeb4a108744f28d
V26_formal_source         = c27c07e305739b2dcf02c18dde44a0bc8bc70642
batch_identity            = review_v25_workingset_and_p6_setup
suggested_profile         = physical_p6_trace_workingset_efficiency_v27
response_required         = response_v28.md
execution                 = R0 -> R1 -> R2 -> R3 -> R4 -> R5
normal_new_full_PDE_count = 1
environment               = qualified laptop WSL/Linux; MPI1/thread1
primary_entry             = python scripts/run_case.py input/path/to/case.dat
ordinary_default          = unchanged
master_merge              = NOT_APPROVED
```

本轮消除的是面向“0.7 nm、任意非可分三维周期单胞、约2 TB”的工程blocker： **有效PC的实际执行成本不清，以及p6局部凝聚准备的重复工作** 。不是新PC筛选，不授权工作站、5 nm或2 nm运行，不将笔记本结果外推为全局p4因子的目标规模资格。

本review是用户明确授权的新批次，不是V26的再次bug replay。新batch/run_id与账本登记必须关联本review，旧V26的“2个fresh worker、1次replay”及所有失败成本原样保留； **不得沿用耗尽的旧批次额度阻止本次授权，也不得清零或篡改旧账本。** 新profile优先复用现有编排与schema，不复制一整套求解脚本。

完成必要检查后连续执行，不在每个小测试或setup后停审。正常一场正式PDE；真正实现bug可沿现有hash-bound机制作一次必要重放。性能不及预期不是bug，不自动追加完整复跑。预启动拒绝与实际worker失败分别记账，不伪造数值结果。

先读根/目录AGENTS、[工作原则](../repository_work_principles.md)、[任务书](task.md)、[Review V24](review_report_v24.md)、已有补充授权、[Response V27](response_v27.md)及[summary](outcomes/summary.md)。本review只改变新批次的范围；旧证据、旧checker与普通默认不追溯改写。

## 1. 审阅事实：这次应该优化哪一段

证据：[V26 compact](outcomes/records/setup_efficiency_v26_compact.json)、[components](outcomes/records/setup_efficiency_v26_components.json)、[cold build](outcomes/records/setup_efficiency_v26_cold_build.json)、[r2](outcomes/records/v25_q4_ac_swap_observe_r2_result.json)。秒均为monotonic实测；GB=10^9 B。

| 同一original p6/h7.5、990单元、q4 | r2速度基线 | V26 | 判读 |
|---|---:|---:|---|
| 完整workflow / s | 3114.283619607013 | 3595.9571450339936 | V26多481.6735 s |
| 纯KSP / s | 2284.681783819 | 2716.518828 | 多431.8370 s，约占总增加量89.65% |
| 明确setup / s | 781.971881371981 | 823.0868099959989 | 多41.1149 s；不是full减KSP |
| 外层步数 | 126 | 126 | 没有由步数增加解释变慢 |
| 同时进程树RSS / B | 7390937088 | 7381557248 | 仅减少9379840 B |
| 原A6最终残差 | 9.283165086752956e-7 | 9.283164976754267e-7 | 都达到1e-6 |

V26组件配对中，H6对角45.0798 -> 4.1694 s，完整H6 setup 84.6834 -> 43.2881 s。后者节省约41.4 s，仅相当于r2全流程1.33%；两个嵌套收益不能相加。V26中p6 retained build为259.0239490659951 s，MUMPS numeric为232.61775177499658 s，p4凝聚装配为29.55984354500106 s。p6 build包含局部数值、映射、端口、身份/hash和右端项准备， **不是259秒全在局部LU** 。

保留V26四项已通过的优化作为待选择组件：无用参考表删除、H6直接选后端、只读bundle共享、准确对角类型复用。projection reuse未采用，端口预分配未取得收益，局部磁盘缓存DEFERRED；本轮不把它们冒充现成成功。V26温度/频率证据不完整，不能预判“必定拔电”或“必定新代码慢”。

V26正式场的worker/wrapper swap policy不一致；后续launcher修复只做过mock，不算新PDE资格。新批次用最新源中的修复并核实整条链，不改旧分类。旧checkpoint表可能在同iteration混有检查前/后时间；先按原event/phase选同一边界，不能仅凭iteration拼表，也不覆盖raw数据。

## 2. 冻结问题与不可改变项

从[r2输入](../../input/task39extra/v25_q4_ac_swap_observe_r2_h7p5.dat)和[V26输入](../../input/task39extra/v26_q4_setup_efficiency_original_h7p5.dat)核对相同物理字段；新dat只改变run_id、profile及经配对选定的实现开关。新source/input/resolved hash重新计算，历史physical hash若含执行字段，以明确的逐字段物理等价桥解释，不重定义旧hash。

| 对象 | 冻结合同 |
|---|---|
| 物理 | 波长13.5 nm，1°掠入射、azimuth0、s偏振；原复数Si/air及mu_r |
| 几何与网格 | 同一original实体、冻结9×5×22=990单元轴坐标/tag；p6/h7.5不是7.5 nm波长 |
| 有限元与边界 | complex128，原Basix Nédélec变体、原积分、双Floquet、全部80个DtN通道及相位/归一化 |
| 外层 | p6独立trace+端口199340行，right FGMRES32，max2048，零初值 |
| PC | 原增广逆桥、BAL_H、一份H6、每次PC两次逻辑p4修正；不加H4/inner KSP |
| 粗层 | 同网格准确p4凝聚，84680行；一个全局LU，一次建立反复回代 |
| 内部质量 | 原A4<=1e-10；按需最多2次额外同factor精化，累计FE及端口；ICNTL(10)=0，BLR关闭 |
| H6 | 同一B6、对角定义、Chebyshev规则、power10步数与seed；不调谱窗倍数 |
| 输出/核验 | 每8步原A6、每32步场；完整E/H、curl、界面量、R/T/A/A_volume、80模式与独立native见证 |
| 生命周期 | JIT在大factor前；因子活跃时安全保留矩阵；完整场/最终残差后释放PC再后处理 |

本轮不做p3/p2、DD/PML、BLR、GPU、低精度、fast-math、减少积分或通道、restart扫描、MUMPS排序/主元/ABI实验、LU detach、局部磁盘缓存平台。 **固定MPI1/thread1，不将多核再混入这次归因。** 用户“多核不能增加内存”的条件保留，但本批线程试验为NOT_RUN。

## 3. R0：先把运行链和计时口径一次对齐

在已授权的新batch下做一个轻量的入口/策略dry-run或mock：覆盖dat解析、profile派发、original retained-space guard、独立service、worker、watchdog及checker。核对最终传入的profile、stage和资源策略，不再等构建完网格才发现original-only guard不认识新stage。不得通过删除所有guard来绕过问题。

wrapper、worker、watchdog和resolved config一致记录本批time/swap的observe_only，真实物理内存压力与监督清场仍有效。只改新profile的接线，旧profile不得因新授权被放宽。复用现有接口记录AC在线、固定电源模式、实际线程库/绑核、可得CPU频率及进程CPU time；读不到写unknown，不装监控平台、不改散热保护。

以现有marker补必要的monotonic起止：p6局部张量、局部消元、trace/MPC/端口映射、身份/hash/序列化、RHS/bridge；A6 volume/DtN、B6/H6、P/PH、粗求解/精化/native A4、PC外层包装。父子inclusive与可得exclusive分开， **不把计时器之和当wall，不把monitor.solve_seconds当纯KSP** 。UTC与monotonic偏差另记，不能挑较小的时钟制造收益。

## 4. R1：同一个正式工作集中的短配对，先判断在线是否真的退化

### 4.1 测量方式

使用990单元实际网格、唯一p4因子、p6凝聚缓存、原约束/端口和常规工作向量，模拟正式常驻状态。工程阶段允许旧/新action短暂共存，但 **只建一份p4因子，不为每个向量或候选重新numeric** ；正式运行不能带着重复oracle工作集。

旧对照是r2的已验证sum-factorized执行路径，不是更早、明显更慢的native路径。优先使用已有兼容开关；核对实际源码、开关和调用路径与r2的差异。不能把最新对象贴上“r2”标签就视为旧实现，也不整体merge/cherry-pick旧分支。必要的最小适配进入可复用src，工程证据保存source/patch身份。

输入优先取已存真实PC/残差向量，至少覆盖一个早期、一个后期；缺少对应向量时用固定合法fixture并标明范围，不重新跑完整前缀收集。输入准备不计入单次作用计时，两边使用同一数据与hash。

先比较A6作用；再固定相同对角、逆平方根和谱窗比较H6 apply；最后用同一p4因子、同一传递与同一输入比较完整BAL_H。H6 setup可产生舍入级差异，单独验证其对角/窗口和最终H6等价，不能把setup差异偷偷混进apply配对。

每组先各一次warm-up，随后交错AB/BA、最多3轮配对；计时采用返回结果已完成的完整调用。记录wall和进程CPU time、实际调用计数、额外精化数、RSS/PSS及现成可得供电/频率。warm-up和准备成本单列，不选最快一次代替全部记录。相同输入也必须区分cold首次与warm重复。

若需要两套Krylov基来模拟内存，禁止复制；保留一套既有实际工作区或说明未复现的占用差异，不分配无用途巨型数组“压内存”。工程配对RSS包含两个候选，不冒充单候选生产内存。

### 4.2 按测量分流，不要求编出唯一历史根因

| 配对观察 | 允许的下一步 |
|---|---|
| V26持续比r2慢，wall/CPU及动作细分支持同一热点 | 只替换/撤出导致退化的共享、布局、调用或包装项；保留对角等不受影响收益 |
| A6/H6本体不慢，但完整PC慢 | 优先检查P/PH、native A4核验、状态复制、资源/日志包装；不继续重写快内核 |
| 配对差异小于或交错于重复波动 | 记NO_REPRODUCED_IMPLEMENTATION_REGRESSION；不强行归因供电或代码，不以未归因阻止后续setup优化 |
| 输入/约束/算子不等价 | 先修真实实现错误，不能用性能数据选取数学错误的候选 |

只对复现的最大问题做一次有针对性的修正与配对复核，不进行全开关组合扫描。无在线退化时，保留现有合格apply，不为了写“新优化”增加改变。该阶段不产生新物理解，不宣称历史59.93分钟的原因已被唯一证明。

## 5. R2：只优化p6准备中实测最大的一个子阶段

### 5.1 先拆开259秒，而不是把整个区间称为Schur计算

以[RetainedOuterAdapter.build](../../src/runners/physical_retained_outer_adapter.py)、[凝聚builder](../../src/solvers/hcurl_assembly_time_condensation.py)、[P6CellCondensedAction](../../src/solvers/p6_cell_condensed_action.py)为入口，读取已有raw_tensor/local_schur/preallocation等计时，补齐缺口。使用R1已需要的准备过程获得基线，不能为每个marker重新构建全栈。

| 子阶段 | 允许优先核查的真实工作 |
|---|---|
| raw局部张量与方向处理 | 每类FFCx tabulation次数、同类型重复转换、临时布局；当前已按类型共享，不重新宣称“从逐cell LU改成共享” |
| 局部LU、Schur与恢复 | 是否重复求同一个已知响应、是否有不必要复制；原strict数值检查保留 |
| trace/MPC及端口映射 | 已有映射是否被重复生成，是否对无内部端口支撑的cell执行空操作 |
| 共享数据校验和身份 | 只读同一class数组是否逐cell重复finite扫描；同一快照是否反复hash/序列化相同内容 |
| RHS/bridge及其余 | 数值工作和证据包装分开，不删除返回质量与最终检查 |

例如当前`_build_cells()`逐cell调用`_borrow_matrix()`并再次对共享Schur/恢复数组作finite扫描。它是可核查的重复工作， **不是已证实占据259秒的大头** 。`cache_identity`已有部分按类去重，不能不测量就重复开发。按绝对秒数选择主导项，不能因为某个4秒函数能快十倍就再次优先投入。

### 5.2 允许的最小优化与正确性条件

若主要成本是重复校验/身份：在数组最终建立并冻结后，对唯一只读class payload做一次内容扫描与hash，cell记录保留映射、shape、role和内容引用。去重键应分辨base、offset、shape、strides、dtype及语义；不同视图不能仅按base指针共用hash。 **每个必要快照仍重新验证内容；不得将setup缓存hash直接当作运行结束时未改动的证明。** mutable数组不跨调用盲目复用校验。

若主要成本是局部数值或映射：复用确实相同的类型数据、约束展开和已有中间结果，采用有界批处理或连续工作区，保持同一FFCx积分、方向和MPC语义。材料/几何相近不等于相同，不用放宽几何容差、系数截断或减少局部检查换速度。仅当空端口维度被严格证明时跳过零列求解，非零Bi/Di及其消元影响完整保留。

若最大项不适合本批低风险改动，明确保留它并记录下一对象；不扩大为通用缓存平台、新JIT后端或全局直接法重写。p4 MUMPS约233秒作为独立成本记录，本轮不改其排序、线程、额度或数值策略。

用相同局部类型/映射或同一live mesh进行针对性旧/新比较；需要重建p6动作时串行清理旧工作区，不同时保留两套大cache。 **允许一份工程因子服务R1/R2检查，最终正式进程仍重新build一次；工程成本另列，不冒充正式免费setup。**

已通过的H6对角复用和无用参考表删除优先保留，不再做第二轮同类优化。持久化局部cache仍DEFERRED，本轮不实施加载方案；正式numeric_cache_mode=build。

## 6. R3/R4：选定唯一组合，再完成一场p6/h7.5

R3集中运行实际受影响的最小测试，验证r2/V26/所选组合的原算子与数据一致性；保存implementation selection、实际对象身份、backend/thread、source和输入hash。选定后清理工程oracle与因子，提交干净源码，正式执行不热修改。

所选组合可以是“r2在线作用 + V26准确对角/必要setup精简 + 一项p6准备优化”，不要求全盘使用V26或全盘回退。选择依据是完整PC配对、准备的绝对成本和正确性，不只看函数名称或版本号。

| 阶段 | 操作 | 收口 |
|---|---|---|
| R0 | 新批次接线、环境/策略检查、历史计时对齐 | 旧额度与旧失败不影响新授权，也不被擦除 |
| R1 | 唯一因子/正式工作集下的A6/H6/PC短配对 | 复现/未复现退化均可形成明确结论 |
| R2 | 分解p6准备计时，优化一个主导子项 | 合格项入选；无收益项退出，不持续加候选 |
| R3 | 合并必要测试、选择并冻结源/输入 | 不逐小项停审 |
| R4 | 一场original p6/h7.5，fresh numeric build，零初值 | setup后直接用同factor完成KSP及完整输出 |
| R5 | 同口径报告/审计/推送 | response_v28；统一待审，不合并master |

正式比较仍以r2为主要分母，同时列V26，不用较慢的59.93分钟替代51.90分钟来夸大加速。每项工程探针/构建的耗时与峰值单列；不为每个开关、输入或阶段跑一场PDE。若无任何新采用的数值/布局/准备组合，只完成归因并记NO_ADOPTED_CHANGE，不为凑表重复旧完整计算。若已有合格改变，正式回归不能因未预先达到某个百分比而被跳过。

## 7. 数值、物理、安全与性能裁决

### 7.1 保持同一解与同一检查强度

| Gate | 要求 |
|---|---|
| 原A4每次逻辑返回 | 原始g分母relative<=1e-10，按需最多2次显式同factor修正，累计FE/端口；不得用错误映射的精化掩盖bug |
| A6/B6/H6/bridge等价 | 操作尺度relative<=1e-10，H6对角<=1e-12；保留原更严的伴随/重复/线性/finite与slave规则 |
| 局部凝聚 | 完整物理项相加后消元、非零内部RHS及非Hermitian左右耦合；局部原检查与端口闭合<=1e-8 |
| 原A6最终 | 完整场恢复后、释放前后均独立true residual<=1e-6 |
| 同离散最终场 | 与r2的FE L2/scaled-curl、同坐标E/H/界面及全部复模式relative<=1e-4 |
| 功率 | R/T/A/A_volume绝对差<=1e-5，逐模式功率最大绝对差<=1e-6；两项能量闭合<=1e-5 |
| 输出/计数 | 全部80模式及原输出；动态统计setup/iteration/check角色、粗逻辑/实际回代与精化，不硬编码126/262/267 |

近零量沿已有绝对规则，不拟合相位、不重归一化。原A6独立native实现保留，不能用候选缓存作为唯一oracle。不同浮点求和顺序允许合格数值差异，不要求bitwise一致；迭代显著变化要解释，不能只交功率结果。全部通过仍为AUTHORITY_LIMITED，没有独立h7.5连续精度资格，不外推短波鲁棒性。

### 7.2 性能与资源

全程插电、固定电源模式、避免其他heavy；MPI1/BLAS1/OMP1及绑核合同固定。供电/宿主频率或时钟异常发生时保存证据，性能标记受干扰，不擅自循环重跑。现成接口不可用写unknown，不为取得传感器读数阻塞一轮开发。

本review仅对新profile明确继承r2的time_policy=observe_only、swap_policy=observe_only；新授权ID绑定本review，wrapper/worker/watchdog读回一致。目标仍为实测zero-swap，任何作业交换都必须限制资源/性能结论，不能靠swap换速度。全局小量页活动与作业VmSwap分列，不将未知归因直接等同OOM。真实有效RAM/cgroup/宿主压力、系统余量、写盘及监督异常仍触发原安全机制，OS OOM不是正常终态。

不恢复旧6/8 GiB库存或固定2倍symbolic预测阻断。7.391 GB是比较量，不是新硬停止线；保留已资格化p4额度与真实内存保护。对共享buffer、哈希去重或批处理新增的scratch计入峰值。原矩阵不能在MUMPS借用期提前销毁，不复制factor，不通过删检查或少输出换性能。

126步、51.90分钟不是终止上限；仍为FGMRES32/max2048。数值breakdown、非finite、输入/缓存身份错误、原A4经允许修正仍不合格、实际资源/监督异常或用户停止才受控退出。性能慢本身不触发bug replay。

## 8. 最终必须交代的结果

用如下定义比较，时间分母均有既有实测支持：

```math
S_{\mathrm{full}}=\frac{3114.283619607013}{T_{\mathrm{new,full}}},\qquad
S_{\mathrm{KSP}}=\frac{2284.681783819}{T_{\mathrm{new,KSP}}},\qquad
\Delta T_{\mathrm{setup}}=T_{\mathrm{new,setup}}-781.971881371981.
```

**setup、KSP和后处理必须由同一流程的明确起止闭合。** 最终表同时列r2、V26和新正式场的完整时间、setup分项、纯KSP/每步、迭代、A6/H6/P/PH/native A4计数与时间、实际粗回代/精化、RSS/PSS、后端used/allocated、swap、供电/时钟边界及场/模式/功率回归。嵌套action时间不重复相加，未知exclusive保持unknown。

R1配对给出所有重复值和次序，而非只有最佳值；R2给出基线子项、采用修改、实际构建次数/唯一数组校验次数/bytes及秒数。减少统计工作需保持证据覆盖，不将删除追溯信息当作内核性能改进。工程与正式成本分列，不跨场加载数值cache，合格JIT可正常复用并记录hit/miss。

最终裁决应能回答：

1. 单步变慢是否在同状态下被复现？依据指向哪一项，哪些原因仍未知？
2. p6准备259秒实际主要花在哪里？这轮改变了哪一项、节省多少绝对时间？
3. 哪些V26收益保留、哪些可选项撤出？完整流程是否真正快于51.90分钟，内存是否增加？
4. 下一步是否已有更大热点值得研究，还是应保留基线并转向工作站规模？不得把本轮扩大成该工作站运行。

若配对无退化、setup有收益但单次全场仍慢，应保留局部证据并承认跨次波动未闭合；不自动判定所有改动失败，也不宣布整个新profile更快。若没有总体收益，r2继续作为已测速度基线，不因版本更新而替换。

## 9. 交付与提交

实现放入适当的可复用src；runner只做最小选择与阶段记录。建议提交顺序：D1接线/计时与针对性实现测试；D2冻结唯一正式dat、implementation选择及source；D3运行后证据与收口。工程若存在dirty worktree，保存直接源码hash/patch；正式必须clean。不要在源码冻结后修改数值路径再复用旧source声明。

轻量文件可以合理合并，但需覆盖：

```text
outcomes/workingset_p6_setup_v27.md
outcomes/records/workingset_p6_setup_v27_pair.json
outcomes/records/workingset_p6_setup_v27_selection.json
outcomes/records/workingset_p6_setup_v27_compact.json
outcomes/records/workingset_p6_setup_v27_decision.json
response_v28.md
```

raw数据保存于既有ignored results/artifact，保留input_original.dat、resolved_config、run_manifest、input/physical/source SHA、run_summary、环境/MPI/线程、原残差和资源/输出hash。复用既有checker并最小扩展新backend/schema的显式允许值；状态仅由动态计数检查通过不能替代原A6与保存场回归。同步summary、test_summary、run_index、项目进展与模型总账，保留Q3低内存成功、Q2未完成及全部中断/拒绝历史。

文档采用GitHub fenced math，检查本地渲染、表格和链接；远程视觉不可用时明确范围，不声称已完成。未运行的全库测试、CI、频率/温度测量如实not_run/unknown。提交推送task39extra后统一待审，不改master、不amend/强推、不整体合并研究分支。
