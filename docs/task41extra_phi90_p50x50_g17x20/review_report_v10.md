# Task41extra Review V10：V9 准备实现审查与首次局部筛选接续

## 0. 裁决：接受准备进展，修三处小缺口后先筛选，不直接重建

**本次是 V9 准备代码审查，不是 V9 数值结果审查。`same_lu_rhs_solve` 的数学定义、显式 opt-in、J 同源保留和一次 GETRS/Di 复用方向正确；真实局部筛选、完整 action/recovery、200q 与场仍为 NOT_RUN。先修复“实际返回 correction 未被筛选消费”“筛选与生产的全局累加次序不同”两项，在新窗口获准后运行保存局部判别。J 异常释放的可重试性在全域重建前关闭。局部通过才补齐真实全域接线并准入至多一次重建。**

本文件只是 V9 的准备审阅补充，编号不代表新求解方案或新科学结果；不复制 V10 runner/schema/window。V9 的候选、旧输入、原分母、数学门、最多三次同 LU 恢复修正及旧负结果均不变。本轮不要求编造 `response_v9.md`；准备继续记入现有 `v9_preparation.*`，首次正式数值后再写 `response_v9.md` 并同时引用 V9 与本文件。

| 身份 / 范围 | 冻结事实 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 准备代码 base / HEAD | `84644ca67d4e49c15ff8f609bb0781576d3bd72c`，远端回读一致 |
| V9 review | `b24b6ce6577225af7fb03e4a62bef80126efc9b8` |
| 最新科学结果 | `a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f`，V8；不是本次准备提交 |
| 审阅日期 | 2026-10-22，Asia/Singapore |
| 当前类别 | 局部消元稳定性候选的代码/接口/生命周期审查 |
| 目标 | 0.7 nm、50×50×140 nm计算域、居中17×20×120 nm Si、方位90°；完整三维场，十进制2 TB含余量，任务零swap，必要冷流程≤48 h |
| 写入范围 | ChatGPT仅新增本review；Codex窄修、相关测试、获准执行；不动master、其他任务或旧结果 |

已读取 V9 全文、准备 MD/JSON、测试记录、该提交差异和以下引用的关键源码。V9本地全文与当前远端blob `2b094bbf0d7527a4efbd40145f8c181f5ceadb13`一致；比较范围内根/docs治理、task.md、V9及旧科学结果未改变，没有新的独立补充任务书。沿用既有根AGENTS、docs规则与task.md，不再把历史正文复制成新执行框架。本次没有访问工作站或读取其大数组，没有运行项目测试/FE；仅在Chat容器做了明确标记的简化控制流与浮点累加反例，不构成数值资格。[R1][R2][R3][R4]

## 1. 已实现部分与资格边界

| 对象 | 源码/证据支持的结论 | 不能提升为的结论 |
|---|---|---|
| 局部 RHS 核心 | 解原 Kz=b_i 后完整计算 −Jz；零 RHS 跳过；Di需要时复用z | 新候选确实改善了真实输入 |
| J与旧默认 | 同一方向变换后的 A_ti 按键保留、只读借用；旧 stored_T cache v1保持 | 全域J库存已经分配或资源准入 |
| 保存筛选 | 固定V8报告/数组身份；不重新积分或factor；candidate/reference各自s/g/d分列；candidate两列与j0/j3决定局部状态 | 实际工作站保存数据已跑通 |
| 诊断隔离 | 用完整 T@b_i、S@t、J@z 产生当前筛选向量；选行恒等式/宽算术不替换这三项 | 整条累加流程已完全等同生产 |
| 兼容性 | 旧V8 helper保留；旧B0 authority/v1不强迫新增字段；V9/v2缺策略仍拒绝 | 所有旧模型重验或CI通过 |
| 测试 | 准备回执记录最终10 passed/0.51 s，本机qualified complex128/int32 | 工作站ABI/service或科学门PASS |
| 未完成 | actual volume-only策略/J绑定、紧凑终态checker、同进程owner交接 | “批准后直接启动全域即可” |

准备成本仍有UNKNOWN；无本轮正式GETRS耗时、RSS峰值、局部改善或全域资格。三个历史过期窗口fixture失败与Ruff不可用保留，不为消除历史负记录刷新窗口或重跑全仓。旧action误差1.7183209126709868e-10/3.6180522433957604e-10与候选初次恢复约1.98e-11仍FAIL；历史donor恢复PASS不转授。[R1][R2][R3]

## 2. 真实局部筛选前的两项必修，以及一项释放边界

### A. 筛选必须消费生产核心返回的 correction

`task41_p0_v9_saved_star_screen`调用 `project_internal_rhs_same_lu` 得到 `solved, correction, timing`，核验并保存solved，但随后只缓存z，重新计算 `new_vector=-(J@z)`。实际生产 `_project_internal_rhs` / `reduce_rhs` 消费的是返回的correction。[C1][C2]

**现有helper公式本身没有被发现写错；缺陷是筛选不能拦住“z正确、返回correction错误”的回归。** 不能报告这条路径已经核验了被生产实际使用的两个返回值。

最小修改：按cell/role/column同时保存并复用返回的z与correction；j3复用j0的同一RHS结果，不再求解。门所使用的新局部trace向量取返回correction；另以独立完整 `-(J@z)` 对照它的shape、dtype、finite、符号与数值，保存差。故意只污染返回correction、保持z不变的fixture必须拒绝；不能被后续重算覆盖。仍保留完整矩阵乘法，不改为只乘选中一行以改变浮点答案。

### B. 保留V8分组重放，另外明确复现生产散射顺序

当前筛选先 `sum(local_terms)` 再加b_t；生产 `reduce_rhs` 先向result写入原b_t，再按 `_cells`、`original_trace`、MPC项次序逐项 `+=`。精确算术相同，强相消的有限精度结果可能不同。每个局部向量已经完整matvec，并不能保证最后的累加次序相同。[C1][C2]

分开保存而不更改旧V8 helper：

```text
V8_GROUPED_REPLAY：b_t + sum(各局部贡献)，用于对照旧保存反事实。
PRODUCTION_ORDER：先写b_t，再逐cell/局部trace/MPC项累加，供V9新筛选。
```

对当前两个cell按实际顺序23352、23493，只向目标active行累加非零贡献，包含保存的复MPC系数；若同一cell内多条原行汇入该active行，保持逐项顺序，不能先vdot归并再假称逐行散射。s也明确绑定正式体积作用的顺序和投影语义。使用现有两个局部包做窄的生产方法重放或等价的精确顺序回放，不建全域owner；原b_t仍只计一次。

旧V8分组d仍应与旧报告比较；新生产序d不强求与旧分组d逐位相同。两者差与宽算术最后组合差单列。**不通过改生产的累加策略来迎合筛选**，本次候选仍只替换内部RHS求值。判门基于生产序candidate自身d，两列均改善且超过已测最后组合不确定度；candidate/reference gap只作诊断。宽算术只提供诊断比较，不是严格误差上界，不替换complex128答案；记录longdouble实际mantissa，平台不更宽时不得假称不确定度为零。[C3]

另做几项廉价身份/尺度核验：j0/j3的t_c和b_i分别一致；b_t列/原行一致；原分母及D0/D1不变。现有筛选保存backward-scaled residual并允许其加1e-13，不能把这个尺度直接叫作原RHS相对残差无退化；同时报告 `norm(Kz-b_i)/norm(b_i)`、绝对残差和backward尺度，沿用原冻结局部要求，不因换尺度放松资格。真实z与原保存z、残差的匹配仍必须成立。

### C. J的错误顺序销毁需要可重试，不重新设计所有权系统

owner有借用计数，禁止借用者尚在时释放J，这一点正确。但action当前 `destroy()`先设 `_destroyed=True`，释放自己的借用，再调用其拥有的owner.destroy。若同一owner还被另一action借用，后者抛错；待另一action释放后，再调用前一action.destroy会因其已标destroyed立即返回，owner释放不再被重试。[C4][C5]

这是由当前控制流可构造的边界，不是已发生的工作站内存泄漏。Chat简化探针确认：两借用者中拥有owner的一方先释放，第一次报错；另一方退出后重试，仍残留owner引用。正常正确顺序没有因此被否定。

最小修复可选择在改变action状态前检查拥有的owner是否仍被其他action借用，明确拒绝且保留可重试状态；或将action自身释放与owned-owner释放完成状态分开记录，使后者可重试。不要把失败标成完整DESTROYED。保留默认stored_T生命周期，借用视图不拥有J，不能在另一个消费者活着时clear共享字典。增加一个错误顺序→拒绝→正确顺序→重试成功的小fixture即可；不扩建缓存框架。此项最晚在全域重建前通过，不要求为它重算任何科学数据。

## 3. 数学身份与诊断：哪些已正确，哪些不要过度解读

当前有符号诊断实际形成选中行的 `J+T@K`，并区别于重组的 `Jz+T(Kz)`；符号及共轭投影符合 V9：

```math
r_b=b_i-Kz,\qquad T b_i+Jz=(J+TK)z+Tr_b.
```

这套诊断没有替代candidate自身s/g/d的构造，方向正确。修正A、B时继续隔离。把实际完整matvec投影与选行投影的差、局部恒等式余差、最后全局加减余差分列；不要把三者混称为单一“舍入已解释”。可用有符号关系检验报告字段，但不能从恒等式右侧给生产答案补一个保存误差。[C1][C3]

`stored_T`的cache v1和旧B0 authority/v1兼容继续保留；新同LU身份携带策略、J和pivot。新代码source可以变化，但producer数学身份、旧数组hash与旧负记录不可重署。已有旧V8重放字段是兼容对照，不因为文档编号变成V10就升级所有格式。

## 4. 先筛选；只有通过才完成以下全域接线

当前准备回执主动承认三处缺项，这个边界应保留。[R1][R2] 局部否决就保存 `LOCAL_CANDIDATE_REJECTED`，不为一个尚无效候选实现更多昂贵路径。若局部通过，按同一获准包连续完成以下工作并冻结新source，无须再等一轮review。

| 接线 | 最小实际要求 | 重建前证明 |
|---|---|---|
| Task41 actual owner | 从V9配置/合同把策略传入 `build_task41_v4_volume_only_owner` 的真实actual-qmetric调用，使构造器保留同张量J；错误/缺失绑定在昂贵分配前拒绝 | 小fixture穿过真实选路/参数/构造调用，不只验证通用adapter；old默认不变 |
| 全两列和恢复checker | 生产新reducer产生完整结果，原输入/RHS/native/端口和冻结尺度不变；使用V9紧凑输出格式，独立读取初/终态及残差，不依赖旧逐步全量存储假设 | 能保存数值FAIL、区分action/recovery/checker完成和official；坏source/列/终态不能通过 |
| owner同进程交接 | 验收阶段持有FE/MPC、体积native、LU/R/S/J；成功交给target/reference实际调用者，失败释放 | 正确owner被移交且不经过无条件finally销毁；未通过不能进入200q；带异常的清理可重试 |

按V9范围检查真实右RHS路径，包括 `condense_unconstrained_vector_to_active_trace(side='right')` 与reference PC任意内部残差缩减；不同时修改left/adjoint接口或端口数学。target和reference各自拥有相应材料/几何的J/LU，不能混用同名对象。必要引用是Python对象共享，不是重复一份87GB载荷。

正式验收先action：原两列动态与冻结分母均≤1e-11，端口继承一致；随后同一owner验证candidate自身恢复：原forward≤1e-11、独立native volume residual≤1e-10、trace不变/slave-zero，至多三次已有同LU修正。旧candidate初次FAIL和donor PASS均保留。若修正是合格所必需，真实恢复/输出路径使用同一显式策略，不能只修测试。

action/recovery和独立checker均通过、全对象账与时间允许后，才进入原200q、准确因子驻留、完整参考与条件target；57个无端口q不删FE。局部筛选只是首个依赖，不是生产资格。完整A6/物理与最终网格/mode精度继续按task.md/V9。

## 5. 减少重复工作、资源与固定窗口

原V6总截止为 **2026-10-21T10:21:59.261754681Z，即10月21日新加坡18:21:59**；本次查询实际时钟为2026-10-22 07:11:07 Asia/Singapore，旧窗口已结束。当前仍是 `PENDING_USER_APPROVAL`，本review不代替用户批准或生成T0。

新提案仍沿V9：总86,400 s、数值85,200 s、收口1,200 s；同一授权覆盖保存局部筛选、通过后的必要接线与至多一次全域重验、门通过后的条件继续。T0从首项必要正式准备/加载前开始，后续补接线和修bug不重置。局部筛选source与后续全域source可以分别冻结；读取旧producer与当前consumer分开，二者引用同一新窗口和连续账本。不要因为补接线得到新SHA就开第二个24小时。

主机和目录沿既有 `fenics-ws:/home/fenics/Projects/laptop_share`，Codex项目不变；task cap1.5 TiB、host reserve64 GiB、task reserve0，complex128/int32、MPI1/math1、exact MUMPS和task swap0不变。现场ABI、MemAvailable/ancestor-cgroup、磁盘和单heavy检查仍须通过。

J增加87,091,200,000 B，旧numeric加J约435,653,172,000 B均是派生载荷，不是已测RSS。构造中按key保留紧凑独立J、所有action只借用一次；raw临时张量释放、实际缓存backing、参考表/maps、checker和后续q对象都入账。记录GETRS/非零bi次数、J乘法、散射及父时间，不用fixture耗时预测全域速度。[C2][C4][C6]

继续复用V8局部LU/z、真实maps、141/174数组、两份B帧/稀疏Bα和未改变的端口输出；不生成carrier、不做64,120模式重验遍历、不重跑A1/A2或旧积分资格。没有全域可重开LU/J时，在局部、代码、容量和剩余时间门均通过后才允许一次必要actual-qmetric构建；不能假称已退出的owner仍live。

原16 GiB证据配额、2 GiB磁盘余量保持。先按V9紧凑布局核算实际旧证据＋新两列/初终态/残差/小报告，避免全域完成后才发现没地方保存；不重复写大归因数组，不删负结果、不借换目录绕配额。任务swap、宿主swap和tree/cgroup峰值分列。旧carrier必要费用纳入最终冷账，研究窗口不是完整48小时PASS。

## 6. 验证、停止与交付要求

本包只补当前修改能漏掉的少量fixture：返回correction污染、强相消/复MPC生产顺序、paired trace/RHS、错误顺序销毁后重试；局部通过后再补actual owner策略与终态/交接的最小集成。复用已通过的相关10节点，不要求每次改一行就跑全仓。沿用原环境，Ruff不可用记录NOT_RUN，不为此重装依赖。测试必须绑定实际冻结文件/工作树差异，不能把本机fixture当工作站结果。

准备阶段先更新 `v9_preparation.*` 的缺项/命令及精确source。原准备模板已有selector，不杜撰裸worker命令；由现有prepare/service生成实际授权路径/attempt，在薄修fixture里穿过修改的路由。无正式运行时保持NOT_RUN，不编写虚假的科学response。

获准后的出口：局部筛选否决就结束昂贵依赖；真实身份/资源/证据/时间不准入则NOT_ADMITTED；全域原门失败则保全原向量并停止200q，不串联第二种数值算法。普通路径/字段/checker错误在同范围内定向修复，重读已保存产物，不重建已完成数值阶段。首次正式工作后写response_v9，先给candidate自身d、实际action/recovery、J/GETRS成本与解锁阶段，再列测试；所有旧失败/UNKNOWN保留。主控集中提交本分支，不merge master。

## 7. 给 Codex 的连续执行文本

```text
继续 Task41extra 的 V9 候选，读取 review_report_v10.md（V9准备实现审查）。
准备base=84644ca67d4e49c15ff8f609bb0781576d3bd72c；V9 review=b24b6ce6577225af7fb03e4a62bef80126efc9b8。
不是新的数值结果或新PC，不另造V10合同/runner，不要求现在写response_v9。

先在现有saved-star screen做两个窄修：
1. 门用project_internal_rhs_same_lu实际返回的correction；按cell/role/column与z
一起缓存，j3不重复求解。独立完整−J@z核对返回量；污染correction而保持z正确必须拒绝。
2. V8的b_t+sum局部项留作历史兼容重放；新判门按生产reduce_rhs先写b_t、
再按实际cell/trace/MPC项顺序累加。完整T@bi、S@t、J@z不换成选行乘法。
生产序candidate自身两列d都改善且超出已测最后组合不确定度才READY。
选行恒等式、宽算术、candidate/reference gap都不替代答案或门。
核paired t_c/b_i与原行；同时报RHS尺度和backward残差，不混称尺度。

补同一owner有两个借用action时的异常释放重试：拥有owner的一方提前destroy
被拒后，后续正确顺序仍能完成owner释放；不因已置destroyed标志永远跳过清理。
保留旧stored_T默认/cache v1、V8 helper和旧B0 authority/v1语义，V9缺字段仍拒绝。
只做相应小回归，不全仓测试，不重装环境。

新24h窗口仍待用户明确批准，旧V6窗口已结束；批准前只做上述准备/fixture。
获准后用现有prepare/service运行保存局部判别，不积分、不factor、不扫描carrier。
局部否决保存LOCAL_CANDIDATE_REJECTED，不启动昂贵重建。

局部通过后同包补齐真实Task41 actual volume-only owner的策略/J传递、紧凑两列/
恢复初终态输出及独立checker、qualified owner到target/reference同进程交接。
通用adapter传参不算这三项已完成。小fixture和完整对象/证据/余额准入后，
冻结新source，至多一次必要全域owner重建；同一窗口不刷新T0。
先原action两列动态/冻结尺度<=1e-11，再candidate自身恢复forward<=1e-11、
native volume residual<=1e-10、trace/slave检查，最多三次既有同LU修正。
独立checker通过才继续200q/准确因子驻留/完整参考/条件原尺寸pilot；57空端口q保留FE。

输入/RHS/native/S/R/evaluator/积分/资源/精度门不改。不重跑carrier、64120模式
验收遍历、A1/A2或旧积分资格，不把旧donor PASS转授candidate。
沿现有主机/目录、1.5TiB cap、64GiB host reserve、task reserve0、task swap0、
complex128/int32、MPI1/math1与16GiB证据边界；J载荷不是RSS/准入结果。
新窗86400/85200/1200秒一次批准，范围与V9相同；启动读现场时钟和资源，
代码补接线与普通修复不刷新窗口，不热改运行源码。

准备继续记v9_preparation；首次正式数值后写response_v9，引用V9和本准备review。
先报告真实自身d和新增数值能力，后列测试。保留失败和未知费用，不合并master。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/docs/task41extra_phi90_p50x50_g17x20/outcomes/v9_preparation.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/docs/task41extra_phi90_p50x50_g17x20/outcomes/v9_preparation.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md#L308-L313
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/docs/task41extra_phi90_p50x50_g17x20/review_report_v9.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/src/runners/task41_p0_checker.py#L4300-L4760
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/src/solvers/p6_cell_condensed_action.py#L3112-L3223
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/src/runners/task41_p0_checker.py#L3845-L3930
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/src/solvers/hcurl_assembly_time_condensation.py#L475-L581
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/src/solvers/p6_cell_condensed_action.py#L3826-L3844
[C6]: https://github.com/Rookie1234567/MyFEniCS/blob/84644ca67d4e49c15ff8f609bb0781576d3bd72c/src/solvers/hcurl_assembly_time_condensation.py#L3910-L3950
