# Task41extra Review V5：实际坐标一致的局部凝聚候选与全域两列验收

## 0. 决定、冻结身份与本轮唯一候选

**接受 V4 保存 checker 的修复和局部几何归因证据；完整作用仍 FAIL。本轮不再安排泛泛诊断，选择一个明确候选：局部 rank-2 FFCx 张量使用原 mesh 的 actual coordinate dofs，不再先平移到 canonical 坐标；由这同一张量及同一局部 LU 生成 R/T/S，供真实 P6 作用、RHS 缩减和恢复使用。独立 rank-1 native、原两列输入/RHS、端口与门限全部不改。**

候选名 `mesh_actual_exact` 是本 review 提出的 opt-in 数值策略，**不是已存在的 CLI 选项、已通过的修复或已经证明的全域根因**。先测真实 exact-key 库存及当前核的成本，严格准入后只做一次完整两列重验。不能通过时按第6节收口，不扩大为新的PC、积分参数扫描或缓存研究。

| 项目 | 固定身份 / 边界 |
|---|---|
| 仓库与分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| V4 结果 base | `f66857f2a6b0ebd0415165adce164dbc2f04cc04` |
| 最新科学 source | `02523b3d5a49d30d71caa8e7f8a9b9405a78fa33` |
| 上一 review / 原 V3 结果 | `bcc688ce542085cd00bc7f1531de0720cb2e6e24` / `f57b987ae62d50adeb0fa18295a296402dbf7acf` |
| 模型 | 0.7 nm，50×50 nm 周期，居中17×20×120 nm Si；方位90°/掠角1°/S，无缺口，p6，10×200×14 |
| 模式 / q | 原64,120模式、200q；57个空端口q保留FE |
| 当前解除的 blocker | 实际 native 与局部凝聚的几何计算输入及数值一致性；不是网格精度或最终收敛研究 |
| 角色 | ChatGPT只提交本review；Codex实现、相关测试、获准计算和response_v5；不改master/其他任务 |

依据为本轮用户指令、当前 task.md、Review V4、正式回应、compact、run index、summary、test summary和相关源码。任务书内容未变，blob仍为 `5b669c109006fa91fdeebba2a81d97ba17b640b0`。上传的完整Review V4已读，blob为 `6216b42d5e388e6c9ac2e422224faacad682fdf7`。未访问工作站、未重新核算其大数组；以下实测来自冻结证据，推导与方案分别标明。[R1][R2][R3][R4][R5]

## 1. 接受什么，不接受什么

| 项目 | V4事实与裁决 |
|---|---|
| 保存checker | 已受监督完成；data_integrity=true、recovery_passed=true、joint_action_passed=false、official=false。只读pivot复制、初始raw状态绑定、FAIL也重算三项修复继续沿用。 |
| 恢复 | 原两列三次同LU后forward约8.45e-14；原恢复门通过。原始失败、三次上限及状态文件全部保留，不重跑旧见证。 |
| 完整作用 | 两列相对差3.042118678294192e-10、6.391893878204816e-10，原门1e-11，仍FAIL。 |
| 差异分块 | trace L2为6.770178089430243e-7、1.4225036541037616e-6；port差为0。分母约2225.481253487629、2225.4807123031883。 |
| canonical重放 | 三类canonical块及全域映射已提取；选中两cell的canonical K/G/J/L、fresh T/S与旧缓存完全相等。 |
| actual证据 | cells26762/26897的actual块彼此并非bitwise相同，即使旧key相同；选中active row5458716的误差下降但不为零。只支持局部贡献来源，不支持“唯一根因已确定”。 |
| 无效诊断 | 重复扣全局b_t的初版必须排除；只使用SHA `27eb82d1e51fd62b2b80e74fe5129f7be0512c35f95d092c967aeca6f90216ae`的修正版输出及其原脚本身份。 |
| 后续能力 | 无200q/factor/完整参考/FGMRES/完整0.7 nm场；A1/A2原资格保持，最终精度、2TB/48h不通过。 |

两份正式诊断service父段为1638.8259056420065 s和305.99965768121183 s，合计1944.8255633232183 s；worker/checker子段不再叠加。另有70.426974745 s保存审核父段和三次离线诊断，工程准备缺项仍UNKNOWN。volume worker tree RSS峰13,237,129,216 B、service cgroup峰8,655,577,088 B分别报告，不相减解释节省；task swap0、宿主5页swap-in不归因任务。[R1][R2]

## 2. 为什么选择 actual 坐标，而不是继续改 checker

`_canonical_axis_aligned_coordinates` 即使 `preserve_exact_geometry=True`，仍执行 `coordinates-lower` 并规范化端点；该选项只阻止边长round到12位，**并没有让kernel接收原absolute coordinate dofs**。`build_unconstrained_assembly_time_condensation` 的 `("actual_space", tag, widths...)` 标签只是空间policy，不证明其坐标是mesh actual。[C1][C3]

V4 actual/canonical路径使用相同rank-2 FFCx kernel和方向变换，只改变坐标输入；native rank-1作用按实际mesh坐标计算。精确数学中的平移不变性，不保证两段浮点几何求值及随后局部消元的结果逐位一致。此处有具体局部数据，足以支持一次候选验证，但不能据此把全部偏差称作“可忽略舍入”。[C2][R2]

本轮保持独立native原实现与旧RHS不变，修改候选的局部装配去靠近该权威，**不把native也改成canonical以求两边一起通过**。也不只替换K、T或S中的一个：R、T、S必须都来自同一actual张量，旧canonical对象只作对照，不能混入新缓存。

## 3. 残差凝聚恒等式：先区分几何项与消元项

令每cell局部块为K/G/J/L，t_c=E_c t，T=-J K^{-1}，R=-K^{-1}G。生产当前用S=L+JR。对于已证Bi=Di=0的当前B0：

```math
s=\sum_c E_c^H S_c t_c+B\alpha,\qquad
g=b_t+\sum_c E_c^H T_c b_{i,c},\qquad d=s-g.
```

这里b_t是已组装的全局FE trace RHS，已含B alpha；**全局b_t只出现一次**。局部trace贡献通过E的共轭转置累加；不能将J擅自设为G的转置或共轭转置。现有用 `solve(K^H,J^H)^H` 得到右解的代码与T=-JK^{-1}一致，不因看到trans=2就错误改符号。[C4]

对同trace的保存态u（j0或j3），定义native残差r_i、r_t；定义局部raw相对native的差Delta_i和已全局累加的Delta_t，并显式保留消元缺陷E_T=J+TK、E_S=S-L-TG：

```math
d+r_t+\sum_c E_c^H T_c r_{i,c}
=\Delta_t+\sum_c E_c^H\left(T_c\Delta_{i,c}+E_{S,c}t_c-E_{T,c}u_{i,c}\right).
```

此式在精确算术中直接展开成立；实际计算另外记录其闭合差及累加尺度。它是归因工具，不取代原1e-11门。V4的K R+G、T K+J接近机器精度只说明**相同canonical张量内部**的消元一致，不代表乘以较大内部场后在约2225的原分母下可忽略。恢复修正也不会自动修正T或S。

无需重新生成旧见证。先用保存的三canonical类、全域maps及j0/j3重算所需分组；对已保存actual两cell，用同一个b_t和相同状态解释两条路径。不能把两个cell对一行的改善相加成全域资格，也不为了构造闭合而重新定义RHS。原native RHS约1e9的范数不得用作新比较分母。

## 4. 唯一候选的具体实现：`mesh_actual_exact`

### 4.1 只修改坐标输入与对应数值缓存身份

在现有hcurl装配模块增加一个显式opt-in几何求值policy，旧默认、旧文件和A1/A2不变。复用 `_tabulate_raw_tensor_class`、`_orient_cell_tensor`、既有strict local LU和R/T/S构造，保留相同rank-2 form、所有default/tag积分、顺序、局部DoF排列和complex128。[C2][C3][C4]

本candidate每个新raw张量必须从
`mesh.geometry.x[mesh.geometry.dofmap[cell]]`
的原float64坐标及原排列取得；不得减lower、round、snap，或根据widths重造坐标。校验axis-aligned等几何适用条件可以继续，但校验不能修改传给kernel的数组。编译一次，复用已有JIT/ABI；volume-only入口不能掉入surface/global physical builder。

数值消元仍严格沿原公式：一次原局部LU，R=-solve(K,G)，T=-solve(K^H,J^H)^H，S=L+J R。**本候选不同时切换S公式、精化次数、累加精度或积分算法**，以便完整失败时能够判断actual坐标单项修复是否足够。记录E_T/E_S，但不选择“误差更小”的另一路作为结果。

选中两cell已有actual/canonical块是首个集成对照：新kernel路径与保存actual输入/块对上，新R/T/S由新块产生；canonical对照仍复现旧输出。小测试不是重新启动这两cell正式service，更不替代全域。

### 4.2 旧共享key的合法范围

旧 `(tag,widths,permutation)` 仍可标识**旧canonical算法**的类，不能标识本候选actual矩阵类。新数值key至少绑定：几何policy、完整form/kernel和积分身份、材料/系数身份、原坐标shape/dtype/全部字节、有限元布局，以及方向变换。raw与oriented两层按实际依赖区分；hash相同还须验证对应完整输入字节，不以近似相等合并。

**禁止两种捷径：**一是把坐标round后重新并成三类；二是先给28,000 cell无条件分配28,000套缓存再查看内存。沿旧通用tuple键/metadata接口做有限适配，尤其V4 `_class_key`当前要求五字段，生产、容量计数、回读/audit必须同时识别新policy；旧canonical key与新exact key分列，不能改写旧manifest。[C5]

先只遍历几何/材料/方向metadata，测实际唯一raw/oriented key数、multiplicity、每key的kernel数量和代表cell，并保存轻量清单。不要为了数key先调用会构建全部canonical cache的高层入口。若fresh mesh编号与保存maps不一致，必须显式验证映射；不能只根据cell号或widths猜对应关系。

### 4.3 同一候选的容量与时间准入，禁止再次缓存两套全量张量

按实际key数更新现有容量公式，而不是继续传3。沿目前维数，一份R/T/S/LU/pivots的派生载荷为12,448,584 B；28,000份情景为348,560,352,000 B。**该情景不是实测class数、峰值或许可**，也不含FE/maps、临时raw/oriented张量、BLAS复制、native向量和后续reference。[R2][C0]

新policy下raw张量逐key生成、定向并完成消元，随后立即释放raw/oriented/K/G/J/L临时块；仅对已经联合准入的实际key保留所需R/T/S/LU，继续共享相同的identity backing。不调用现有 `_global_raw_tensor_cache` 先留一整套raw，再与全部消元缓存重叠。无需新建通用LRU、磁盘矩阵仓库或provider平台；可在现有构造循环中实现受限MPI1分支。

先在本轮实际构建的最初有代表性的至多8个cache miss上记录**排他的kernel、orientation、LU/solve、Schur、保存/释放**成本，再决定完整库存是否能在实际余额和原cap内完成。这些是本次完整构建的前缀，已算对象直接复用，不另开计时case，也不把306秒geometry service父段当单个kernel时间。按实际剩余key及类别覆盖给有不确定性的总成本；明确超余额时不盲跑到kill。

若完整保留缓存不能准入，本轮停止该candidate的完整生产构建，交真实key数、已测单key/累计成本与具体缺口；不悄悄改为每次matvec重新积分28,000格、也不开发磁盘换入替代方案。大raw/cache不纳入Git，也不把约350 GB临时数据写入只有16 GiB授权的证据区。证据只保存必要新全域结果、轻量key/index和少量原始块，旧141数组和1.299 GB映射不复制。

## 5. 全域验收：同一原始两列，端口继承，体积实际重算

只有上面的数据、容量和时间门通过，才继续全域。复用V4已保存的全域maps，必要fresh FE/compiled rank-2数据；建立的candidate owner由**真实P6体积作用与真实reduce_rhs**消费，不在benchmark里另写一套数值求解器。可复用V4 `audit_task41_v4_volume_identity` 的零append视图，但不能先强制新actual类与旧canonical类bitwise相等；改为分别验证旧donor身份和新policy身份，绝不取消布局/来源核验。[C5]

每列保持同一个known场、端口alpha、native_volume_rhs和native_rhs。初始恢复、j3及其native动作各按原时点读取；不重新制造输入/RHS，不重跑旧恢复校正，不加入第四次同LU。新局部R/LU改变后，必要的candidate恢复向量检查属于受影响路径核验：使用**保存RHS**并由当前owner生成，不重新运行旧V3的整套见证流程。确需native作用核新恢复时，仅补两次volume-only作用并预先列入预算，不调用端口遍历。

计算candidate体积trace输出及candidate reduced RHS；B alpha由两个保存B帧重建一次，port块继承经过校验的原数据。两列完整结果形状仍为(5,752,120,2)。完整向量和分项在判门前写入新consumer目录、hash后由修好的checker独立重算；新consumer引用旧donor/source/window，不改旧141文件或旧FAIL。

保留原比较定义 `max(norm(candidate_full_action),norm(candidate_reduced_rhs),tiny)`；同时使用原冻结尺度D0=2225.481253487629、D1=2225.4807123031883报告并验收，防止变化的尺度掩盖误差。**两个口径均≤1e-11**；冻结尺度下绝对差分别≤2.225481253487629e-8和2.2254807123031883e-8。trace/port平方和、B/H及一次MPC、完整行覆盖均要闭合。不会因为比旧值改善7倍或某单行通过而放行。

结合第3节，在actual完整结果上分别记录几何/native差、E_T/E_S作用和闭合余项的全域尺度；优先复用实际计算中已经得到的量，不为分解额外做66分钟全模式扫描。只用旧保存d直接补新输出、从known误差制造校正、改变原RHS或将checker oracle切为candidate，均禁止。

checker完整复核、两列完整门及受影响恢复/约束门全部通过，才能宣布本候选在当前离散的volume/RHS接线合格。端口资格是继承，不称新积分全通过。随后同一live owner优先继续target与200q；reference不得继续用旧几何cache假称与新策略同一算子。每个新sector应用相同policy、独立做原q/native/跨q泄漏检查。actual浮点路径并不保证所有平移sector逐位相同，不能强制把泄漏置零或复制q矩阵。

全局对象账允许时保留ALL_Q_RESIDENT准确因子，逐q两RHS真残差≤1e-10；完整参考strict/V15分列；之后才是条件FGMRES/原尺寸pilot。57个空端口q仍保留FE。后续求解必需的新算子作用正常计费，但本轮候选验证不再做carrier生成或完整端口遍历。

## 6. 清楚的失败出口与连续执行范围

| 触发条件 | 本轮动作，保留的产物 |
|---|---|
| hash/映射/旧actual小块重放不一致 | 在全域之前停止；给具体字段或数组差，局部接口错误可定向修复并继续，不重做donor。 |
| exact-key库存或实测前缀显示cap/磁盘/实际余额不够 | 记 `CANDIDATE_NOT_ADMITTED`，列实际N、工作集和剩余成本，不宣称数学失败；不升cap、不自动另开窗口。 |
| 首个actual局部LU/矩阵出现非有限或原strict门失败 | 保存该key原块、RHS、错误，停止依赖计算；不换pivot/材料损耗或增加精化次数。 |
| 完整actual两列任一仍>1e-11 | 记 `ACTUAL_COORDINATES_INSUFFICIENT`；保存两列完整结果和第3节缺陷分解，量出剩余绝对误差/尺度；不再原样跑完整模型，不串联第二个算法候选。 |
| 原门通过但checker/生产owner接线未闭合 | 数值成果独立保存；只修对应读取/调用链，不重新生成candidate张量或端口。 |
| 数值、checker与实际完整对象准入均闭合 | 不逐阶段停审；在本窗口内连续推进200q、全因子/参考与条件target，保持原门。 |

“actual不足”后如数据明确指向某一实现错误，可在同一候选、同一原始输入/积分内最小修复；若需要改变native定义、数值精度、消元算法或测试尺度，则超出本候选，保留定位后交审，不以“继续研究”无限试探。当前任务不研究替代PC、缓存暖启动、hp或材料扫描。

## 7. 原窗口与开发成本

| 合同项 | 保持值 |
|---|---|
| window SHA | `68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38` |
| 原T0 | `2026-10-19T05:23:07.094241922Z` |
| 数值截止 / 总截止 | `2026-10-20T05:03:07.094241922Z` / `2026-10-20T05:23:07.094241922Z` |
| 主机/目录 | `fenics-ws:/home/fenics/Projects/laptop_share`，现有Codex项目和对话不变 |
| cap / host reserve / task reserve | 1,649,267,441,664 B / 68,719,476,736 B / 0 B；现场更紧约束优先 |
| ABI、线程、其他限额 | 原complex128/int32、MPI1/math1、exact MUMPS、任务swap0；证据累计16 GiB、磁盘余量2 GiB；PSS未采样记null |

审阅时间工具快照为2026-10-20 09:41:27新加坡时间；当时距13:03:07数值截止约3小时21分40秒，只是UTC上界，非工作站账本余额。接收、源码冻结、试运行前缀和完整分配前必须重新读实际UTC/monotonic/连续费用，不能使用V4旧13,165秒余额。

已截止就不启动新的heavy；总截止内只做受监督收口。总截止以后，保全当前源码和数据并提交明确下一断点，**新24h窗口仅为PENDING_USER_APPROVAL提案**（数值85200、收口1200），不能自动续期。相同主机/cap不需要反复申请，新的固定时窗不能擅自创建。旧窗口和完整冷流程成本保留，不把warm复用成绩当172800秒冷流程PASS。

开发只做三组相关回归：actual/canonical及exact-key不混用；同一candidate块供P6/reduce/recover且全局b_t只处理一次；真实现有prepare/service/audit的零carrier调用及FAIL输出/收口。复用26项相关fixture中受影响项，不默认全仓pytest、重复21项无关文档检查或重装环境。旧A1/A2和已接受恢复/端口不因执行版本变化重跑。

正式源码冻结再运行，主控集中提交本分支；普通变量/路径/接线错误定向修复后继续，不热改live源码、不刷新T0。新数值产品写出后立即可回读；不建立新的V5脚本体系，优先扩展现有volume-only入口和数值内核。

## 8. 下一次交付与精确依赖

优先继承三个现成包：V3的141数组与manifest `f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465`；V4全域映射/三类报告 `09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5`；两cell actual/canonical报告 `a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031`。精确路径及各数组hash从V4 compact和原manifest读取，不能只验证这里列的短清单而跳过实际依赖。[R2]

提交response_v5、candidate策略/实际key清单、容量前缀和阶段时间、两列完整输出与checker、清场、run_index/summary/test_summary与模型总账增量。首屏必须回答：**候选是否完整执行；实际key数与峰值多少；两列原门是否通过；几何单项修复够不够；已解锁哪一步计算。**测试数量不作为主要成果。

至少分别给出COMPLETE/FAILED/NOT_ADMITTED/NOT_RUN及原因，不用service exit0代替数值资格。保留所有历史失败、无效b_t初版、旧SCI/ABI/消费身份和未知费用。不修改master、不合并；任意未闭合的原尺寸场、最终精度、2TB或48h均不写PASS。

## 9. 可直接交给 Codex 的文本

```text
继续Task41extra，按review_report_v5.md执行。
分支task41extra_phi90_p50x50_g17x20；结果base f66857f2a6b0ebd0415165adce164dbc2f04cc04；科学base 02523b3d5a49d30d71caa8e7f8a9b9405a78fa33。

V4 checker/recovery资格继承，完整action仍FAIL。只用修正版b_t诊断。
本轮唯一候选mesh_actual_exact：rank-2局部张量直接用原mesh coordinate
dofs，禁止平移/round/snap；native rank-1及原两列known/RHS不变。
沿原kernel、方向、strict局部LU和R/T/S公式，同时更新所有依赖块。
不只替换S或T，不把native改成canonical以求通过。

先在现有volume-only入口盘点实际exact geometry/kernel/material/orientation
key，旧(tag,widths,permutation)只作canonical标签。核对旧两cell actual块，
用最初至多8个实际cache miss计排他成本，先做全库存容量和余时准入。
不未经测量为28000格各留一套；不按tol重新并类。新policy raw张量逐key
生成消元后释放，不让完整raw cache和全部R/T/S/LU重叠。
既有容量/audit/key读取者同时适配，默认旧路径不变。

准入后只做一次全域两列重验。复用141数组、V4全maps/三canonical类、
两cell raw；读取两个B帧并继承未改port输出，不生成carrier、不扫描64120模式。
新体积及reduce_rhs必须走真实生产核心；原全局b_t只扣一次。
按review残差恒等式分别报告geometry/native差、T/S消元缺陷和相减余项。
原max范数定义及冻结约2225分母下均须<=1e-11，不换RHS/分母/输入，
不从保存差向量补答案，不加入第4次同LU。
改变后的R/LU只核必要受影响恢复，不重跑旧V3全套见证。

actual两列仍超门则保存全域FAIL和量化剩余缺陷，停止200q依赖；
库存/实测成本超资源或余额就给精确NOT_ADMITTED，不扩大cap或暗中逐步换算法。
同一候选内普通工程bug定向修复继续，不一处报错就停整轮。
两列及checker、生产接线与对象账通过后连续进入200q/准确因子驻留/
完整参考及条件原尺寸pilot。57个空端口q保留FE，各sector新native资格不省。

原T0=2026-10-19T05:23:07.094241922Z，数值截止=2026-10-20T05:03:07.094241922Z，
总截止=05:23:07.094241922Z。接收/冻结/分配前读实际余额，不刷新旧钟。
沿既有fenics-ws、1.5TiB cap/64GiB host reserve/task reserve0、任务swap0、
原ABI/MPI1/math1/MUMPS及16GiB证据配额。已截止不启动heavy，新窗须另获明确批准。

只跑本次geometry/key、共同消元和正式路由相关回归，不全仓测试、不另造PC或框架。
主控冻结/提交本分支，交response_v5、真实key/时间/峰值、两列误差和checker、
可接续产物与账本。保留负结果和UNKNOWN，不合并master、不预报最终精度/2TB/48h通过。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/docs/task41extra_phi90_p50x50_g17x20/response_v4.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v4_volume_only_attribution_20261020.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md
[C0]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/src/solvers/hcurl_assembly_time_condensation.py#L35-L131
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/src/solvers/hcurl_assembly_time_condensation.py#L1350-L1445
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/src/solvers/hcurl_assembly_time_condensation.py#L1825-L1990
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/src/solvers/hcurl_assembly_time_condensation.py#L2397-L2460
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/src/solvers/hcurl_assembly_time_condensation.py#L2553-L2755
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/f66857f2a6b0ebd0415165adce164dbc2f04cc04/src/solvers/task41_v4_volume_only_audit.py
