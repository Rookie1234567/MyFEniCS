# Task41extra Review V9：同 LU 直接 RHS 缩减的条件生产验证

## 0. 裁决与冻结身份

**批准实现唯一显式候选 `same_lu_rhs_solve`：对每个内部 RHS 用已有局部 LU 求 z，再计算 −Jz，替代预存 T 乘 b_i。尚不批准无条件全域重建或生产采用。先在 V8 已保存的完整目标行局部包上，检查候选自身相对原 native RHS 的真实 d 是否改善；此廉价判别通过、实际资源通过且新固定窗口获准后，连续做至多一次全域重验，不再为同一范围逐阶段停审。**

V8 的 candidate/reference 投影差缩小足以支持检验这个具体候选，不足以证明它修好了原方程。下一轮不另开归因项目、不研究新 PC，也不同时改 S、R、张量算法、积分或 native。失败后不自动串联第二种数值方案。

| 冻结项 | 值 |
|---|---|
| repository / branch | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 本次结果 base | `a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f` |
| V8 最终 checker source | `3ce1a158e3e0b6556a2e094755adf9b5bd18ae08` |
| V8 selected-star producer | `35fd1bbf2bca13bd17e89cc79cf7cd825b94411c` |
| V6 全域张量 producer / donor | `210fbbf271faa14c62ac30153b80332d0e645982` / `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` |
| 上轮 review | `c3df1f4bc331d20e2f156cc7db0ad41ab749ef37`，本目录 `review_report_v8.md` |
| 本轮类别 | 局部消元的数值稳定性与生产接线；不是迭代收敛或网格精度研究 |
| 最终目标 | 原0.7 nm、50×50×140 nm计算域、居中17×20×120 nm Si、方位90°；完整三维场、十进制2 TB含余量、任务零swap、必要冷流程≤48 h |

已核对远端分支、response_v8、compact及证据索引、summary、run_index、test_summary、实际源码与V8增量；读取根AGENTS、docs/AGENTS、repository_work_principles、task.md，并核对本地V8全文对应远端。任务目录未出现新的独立补充任务书。本次Chat只新增review，不实现数值代码、不登录工作站或重读其大数组。下文工作站数值来自已发布证据，资源字节为另列推导；Chat仅做字节算术和独立微型复数块恒等式检查，不声称项目测试通过。[R1] [R2] [R3] [R4] [R5]

## 1. 接受 V8 的哪部分，不接受什么推论

V8已把active行4,766,937映射到原行15,440,235，找齐cells 23352与23493；前者tag2/permutation4680、后者tag1/permutation0。两个选中局部trace系数均为1；真实I/T分区、方向、candidate/reference角色分别核验。它不是全域候选重建。

| 对象 | 已接受的实测与边界 |
|---|---|
| RHS局部比较 | candidate/reference投影差top由2.433304760925843e-9到5.157211896343317e-10，bottom由4.976414600781769e-9到7.809377196826238e-10；不是候选自身对原native的全域误差 |
| 局部成本 | 4次新局部LU合计0.132975625 s、8次RHS反事实合计0.030730719 s；不能据此承诺全域每次PC成本 |
| V6原action | 冻结D为2225.481253487629、2225.4807123031883；两列1.7183209126709868e-10、3.6180522433957604e-10，门1e-11，仍FAIL |
| V6初始恢复 | forward约1.98e-11，门1e-11，仍FAIL；native volume residual通过，额外修正0次；旧donor三次PASS不转授 |
| checker | 第四次完成审计；前三次复数解码/字段/grouped-left与closure错误保留；审核完成不等于科学门通过 |
| 成本与资源 | 五个已记录service父段合计1005.333930810 s；最高tree RSS9,867,120,640 B；最终checker父157.833339050 s、tree RSS4,001,955,840 B；任务swap0、清场；不同cgroup口径不相加 |
| 保存成果 | V8局部张量、映射、24个LU/RHS数组与hash继续复用；累计证据14,789,864,384 B；工程准备未知费用保留UNKNOWN |

参考路径自己的d没有一致改善，所以不能把“candidate与reference更接近”改写成“更接近native”或“全域根因已找到”。宽算术只是诊断；E_S t在同trace的j0/j3差中抵消，原消元缺陷恒等式及Bα修复保持。[R1] [R2]

## 2. 首先做一个廉价而直接的判别，不再泛泛归因

### 2.1 要判别的是同一个 candidate 的 d，不是两种实现彼此的距离

对V8保存的两个完整incident cells、原两列known trace与原native RHS，固定candidate的S和全部数据身份，分别计算：

```math
\begin{aligned}
s_r&=\sum_{c\in\mathcal S_r}w_c^H S_c t_c,\\
g_{T,r}&=b_t[r]+\sum_c w_c^H T_cb_{i,c},\\
K_c z_c&=b_{i,c},\qquad
g_{LU,r}=b_t[r]-\sum_c w_c^H J_cz_c,\\
d_{T,r}&=s_r-g_{T,r},\qquad d_{LU,r}=s_r-g_{LU,r}.
\end{aligned}
```

其中b取原native_volume_rhs；完整式使用原f和原Bα，各项成套且全局b_t只计一次。复数E/MPC只按原约定投影一次。先独立重建s和g，再相减；不能用保存d减去一个拟合误差生成新答案。V8原行、两个cell、partition及全部所需局部块已经取得，不再扫描metadata或重新积分。

**这项判别可直接复用V8保存的z、K/J/T/S、b_i、两列输入和native trace值。**随后用将被生产reduce_rhs调用的同一小核心重放一次，以验证真实实现；优先重开V8已保存LU，pivots复制为可写int32，不重新做那4次分解。j0/j3的b_i相同，不重复求解同一列；状态只用于原生作用/归因配对。旧数据读回不等于重新运行其生产者。

分别报告candidate自身的旧/新d（实虚部、绝对值、冻结D尺度）、reference自身的旧/新d、candidate-reference差，以及普通与宽算术的最后组合差。局部S作用若为零，按保存值报告，不将此性质推广到全域。已有八键只补受影响RHS核心的小回归，张量/R/T/S资格不重跑。

**进入全域的局部筛选条件：**身份及原路径重放闭合；两列candidate自身d均有超出已测最后组合不确定度的改善，无非有限/约束或局部solve残差退化；新生产核心确实产生所声称的z与−Jz。它不是新的全域误差门，也不要求reference路径必然同幅改善。若只缩小candidate-reference距离、candidate自身不改善或结论被求和不确定度覆盖，本候选不进入昂贵全域构建，保存明确否决证据。通过则在同一获准执行包内继续，不再等待下一份review。

### 2.2 这个改动究竟改变哪一处误差

当前实际builder通过同一LU解伴随系统生成T，并不是必须显式存一个K逆；不要误报为“代码采用了显式全局逆”。候选避免的是先固化T再作T b_i的额外误差，不改变精确算术下的凝聚方程。[C2]

记E_T=J+TK，r_b=b_i−Kz，则对存储矩阵的精确算术有：

```math
T b_i+Jz=E_Tz+T r_b,\qquad
 d_{LU}-d_T=\sum_c E_c^H(E_{T,c}z_c+T_cr_{b,c}).
```

最后一式还需另列实际乘加/投影/相减的浮点余差。用保存z和局部块检查它，是解释RHS改变的有符号证据；不能把右侧当补丁加到生产答案上。该关系不证明E_S、R、native/local张量差或全域累加已经足够准确。小solve residual也不单独证明前向/完整action过门。

## 3. 唯一生产候选及完整接线

候选策略名 `same_lu_rhs_solve` 为本轮拟实现值，不是当前已有CLI。默认仍为既有预存T路径；新策略仅在明确的Task41 B0合同中opt-in。修改范围限定在现有condensation owner、P6 action及其当前调用/验收链，不另造PC、runner或版本框架。

### 3.1 J必须由生成该LU的同一实际张量拥有

在 `hcurl_assembly_time_condensation.py` 的实际块提取处，J就是方向变换后 `A_ti`。当前代码生成R/T/S/LU后释放A_ti；现有owner及 `_CellActionData` 都没有可借用的原J字段。[C1] [C2]

增加默认None的可选 `retained_trace_interior_by_class`（具体字段名可随现有风格），仅新策略保留。它按原exact-oriented key绑定与该K/LU同一次生成的J。保证保留的是独立紧凑432×450块，不是一个view把完整882×882 raw tensor留住；已有高级索引产生的独立块可直接转为只读所有权，不再复制一次。

P6 action、trace-only浅视图和真实target/reference消费者都借用同一backing；不按每个action或每个cell再复制J。T/R/S/LU本轮继续保留，T仍可能用于既有端口构造与对照，不同时开发删T优化。不能用−TK重构J、用G的转置代替J、合并actual键或重新积分每次RHS。

明确销毁顺序：先停止/释放借用action，再解除owner的J及其他数值缓存引用；`destroy()`仅标志或销毁PETSc对象不代表NumPy字典已释放。失败清理、重复destroy和浅视图共享均须有定向检查，不在仍有消费者时clear。新数组在实时资源与cap准入之后才分配。

### 3.2 reduce_rhs做一次solve，并复用于内部端口修正

当前 `P6CellCondensedAction.reduce_rhs` 对非零内部bi计算T@bi；若该cell有局部端口，随后还会lu_solve一次用于Di修正。[C1] 新分支应为：

```python
# Proposed core, not a claim that this option already exists.
z = lu_solve(cell.interior_lu, bi)  # K z = bi, no transpose/conjugation change
correction = -(cell.trace_interior @ z)
# Use the original trace/MPC scatter exactly once.
# Where the existing Di correction is required, reuse this same z.
```

零bi保留原跳过规则；非零bi每cell/RHS恰好一次GETRS，无新factor。保持 `rhs_is_mpc_dual` 的active/slave验证、原b_t只加一次、port_rhs一次相加和原−D/H符号。对于有Di的通用测试，复用z，不再解第二遍；Task41的Bi/Di零支持证书仍仅属于该物理/布局。真实内部projection/embedding若不是当前已资格的identity，须正确适配或显式拒绝，不静默套公式。

J、K、LU、几何/evaluator/方向及策略属于新的数值cache身份。shared helper应被生产方法和本次局部重放共同调用；checker使用独立保存矩阵/结果复核，不只调用同一个helper确认自己。

### 3.3 不能只改诊断构造器

P0必须列清实际调用链：新Task41配置/prepare → worker → B0 target owner → P6 action → full/native RHS验收与正式 RHS；后续reference PC处理任意内部残差的reducer、恢复和checker也明确读到该策略。定位所有本任务直接访问 `trace_from_interior_rhs_by_class` 的右RHS路径；例如 `condense_unconstrained_vector_to_active_trace(side='right')` 若在实际路径使用，必须委托同一数值核心或显式阻止旧路径混入，不能验证用新算法、求解仍用T。[C3]

不改无关adjoint/left-functional API，不全仓替换 `T @`，不替换S/R或既有B/D/H公式。本轮参考owner使用自己的J/LU，不能借target材料的块。旧A1/A2采用旧默认，历史资格不重跑。

## 4. 资源与成本：J不免费，solve也不免费

| 项目 | 推导或实测依据 | 边界 |
|---|---:|---|
| 每exact key的J | 432×450×16 = 3,110,400 B | complex128载荷，不含metadata/临时块 |
| 28,000份J | 87,091,200,000 B，约81.11 GiB | 新增retained载荷，不是实测RSS |
| 旧R/T/S/LU等推导＋J | 348,561,972,000＋87,091,200,000 = 435,653,172,000 B | 只是一部分numeric对象账，不是全场峰值 |
| 每次full nonzero内部RHS | 最多28,000次局部GETRS＋28,000次J作用 | 实际按非零bi计；两列最多56,000次；有Di时不重复solve |
| V6历史重建标尺 | evaluator19,641.25 s、owner24,777.35 s、service28,555.91 s | 不相加；新运行不得直接冒用旧时间 |

先记录同保存局部输入下新增GETRS、J乘法、MPC散射的分项成本，再把新owner的实际累计次数/时间记入完整PC成本。V8八次solve的毫秒结果不保证全域吞吐；factor的check_finite扫描、memory traffic及Python循环也属于真实费用。没有理由改math线程或MUMPS参数来隐藏这个代价。

保留1.5 TiB task cap、64 GiB host reserve、task reserve0及全部ancestor/host约束。全对象账还包括FE/maps、所有旧缓存、共享参考表、临时raw及J、端口实际页、两列/recovery输出、后续reference/q CSR/PETSc输入/因子、Krylov、输出及checker。共享backing只计一次，mmap页不算零。低RSS局部诊断不是完整内存准入。

## 5. 全域重验：列清真正需要重建的范围，最多一次

### 5.1 先承认现场owner已经销毁

已保存的141个donor、V6的174数组和V8局部块/24个LU-RHS数组，不等于28,000份完整可重开的LU/R/T/S/J缓存。先查实际inventory；只有完整身份与全部payload都存在才可重开。不能由哈希索引臆造checkpoint，不能把V8四个小LU称为全域owner。

若全域缓存确实不存在，**P0判别通过＋新窗授权＋资源/时间准入后，允许一次必要的actual-qmetric owner重建，顺便保留J。** 原因是新生产reducer和真实恢复需要全部局部LU/J，现场没有；不是为了重新证明旧张量优化。保持V6已资格evaluator、actual坐标、积分、方向、R/T/S构造及strict LU不变。旧八键oracle/慢FFCx资格直接按数学身份导入，不重算八份reference tensor；用已有块在实际首批键核对新接线，计算所得键继续用于全域。新source与旧evaluator/producer身份分开，不通过改名制造新积分。

仍须fresh FE/MPC/体积native及合法的元数据映射，但不能调用会先生成完整surface/carrier的旧高层前缀。carrier和两个B帧/稀疏Bα读原保存资格，禁止重新生成或做完整验证扫描；本次作用资格不需要重复64,120模式遍历。

### 5.2 先完整action，再必要候选恢复

在同一live owner内，使用原两列known和原native full/volume RHS：

1. 从生产P6体积核心重新计算S作用；端口数学未改时，继承原已核验输出并只读两个B帧/稀疏Bα。与旧V6保存S作用作交叉检查，以确认本候选没有夹带S/输入变化；不把旧结果向量当修补量。
2. 用生产 `same_lu_rhs_solve` 重新计算完整reduce_rhs，保存两个完整输出及身份。独立checker必须在原动态分母和冻结D0/D1下都≤1e-11，port/D继承一致性保持。失败立即保存原两列及分项，不放行200q，不换分母、不拟合误差、不再开始第二次全域构建。
3. action通过后，用同一新LU/R做候选自身恢复。初次状态及最多3次既有独立native残差驱动的同LU修正，原RHS、trace和alpha不变；forward≤1e-11、native volume residual≤1e-10，active trace精确保持、slave-zero。不增加第四次，不用known误差作修正。若某修正是合格所必需，真实恢复/输出路径也使用相同显式策略，不只在测试中修正。
4. saved checker分别输出文件完整性、action、candidate recovery和official状态；旧donor recovery PASS不转授。check失败先修工程读取错误，只审核已保存新输出，不重建owner或已通过数值阶段。

先算action能在RHS候选无效时避免额外恢复工作；这不是取消恢复门。V6原始候选恢复只做0次额外修正的事实仍保留。

### 5.3 证据空间在构建前规划，避免算完才被写盘门卡住

V8记录累计14,789,864,384 B，原16 GiB配额余2,390,004,800 B；启动时重新核验实际值。原全场数组和旧12个attribution累加向量不复制、不重新写。新两列action和reduced RHS各184,067,968 B（按128 B NPY头估计），两列终态恢复场及native residual共4×296,016,512 B：合计约1,552,201,984 B。若初始恢复不等于已保存的V6初态，另存两列初态约592,033,024 B，总计约2,144,235,008 B，尚有约245.77 MB供小型收据/局部失败证据；均是尺寸推导，实际headers/日志纳入准入。

每个修正步保留实际计数、范数、hash、trace/slave与native调用记录；本新紧凑资格路径只要求初态（可严格绑定旧相同数组）和终态/终态残差完整落盘，必要失败状态优先保存，不再无条件复制每步多份全域向量。明确这与旧V3逐步完整回放的范围不同；不伪称缺失中间向量可完整重放。独立终态forward/native门、次数上限和生产路径不能削弱。既有旧格式checker保持支持，新consumer显式识别本次紧凑证据。

若真实必要证据超额，先收窄冗余诊断输出；仍不足则在启动前报告准确差额，不自动抬配额、删除旧失败或静默省必需原件。本轮也不开发大型缓存持久化/压缩平台。生产J驻留字节与磁盘证据配额是不同口径，不混淆。

## 6. 通过后连续推进，但不因局部PASS越过全域门

P0完成前先核对现有worker是否在audit退出时无条件销毁owner。若要接续求解，补一个窄的“qualified owner交接”到当前target路径；同一FE/MPC、LU/R/S/J及独立native接口保持存活，不因通过一个门而销毁后再构建。实际调用路径和对象身份必须能证明复用，不能只写同进程口号。没有取得合格action/recovery/独立checker时，后续一律不启动。

全部门闭合且完整资源/余额许可后，可在同一获准包连续进入真实200q CSR/native、准确因子驻留、完整参考逆及原尺寸pilot。57个空端口q保留FE；新策略影响的reference RHS/recovery同样资格化，各q原native与两RHS门不省略；strict/V15区分。真实后续原生端口作用属于求解必要成本，禁止的是为重放旧检查而重复无关全模式遍历。

完整原A6≤1e-6、物理/体吸收≤1e-5及最终网格/mode精度要求不变。不用局部结果或q0×200估算整场实测。新24小时研究窗不把旧carrier等必要冷启动成本删除，最终48 h仍须完整账。

## 7. 新窗口、执行与失败出口

原V6数值截止 `2026-10-21T10:01:59.261754681Z`、总截止 `2026-10-21T10:21:59.261754681Z`（新加坡18:01:59/18:21:59）均已过。此次实际时钟核对为2026-10-21 19:42:03 Asia/Singapore。**不沿用旧余额、不刷新旧T0。**

本review批准代码候选和条件执行顺序；新的工作站受监督数值窗口仍为 `PENDING_USER_APPROVAL`。提案：总86,400 s，数值85,200 s，收口1,200 s；一次授权涵盖保存局部判别、至多一次全域重验及门通过后的条件接续。没有批准前完成本地窄实现、fixture和真实命令准备，不偷偷运行正式补算。主机/目录沿用 `fenics-ws:/home/fenics/Projects/laptop_share`，Codex项目名和对话不变；原complex128/int32、MPI1/math1、exact MUMPS、task swap0、1.5 TiB cap、64 GiB host reserve不改。

获准后T0从首项必要正式准备/加载前计，绑定父窗口/全部旧费用。启动全域前使用V6同机全域实测成本，加本轮J/求解/输出/收口的实际预算与现场负载检查余额；这些是计划而非完场保证。数值截止停止新增heavy，收口受总截止；service父段与内部子段不重复计费。普通接口bug定向修复、冻结新source后在同窗继续，不能热改运行科学代码或刷新时钟。

停止出口明确为：局部candidate自身不改善；完整身份或内存/证据/时间不准入；新完整action或受影响恢复仍FAIL；后续原数值门失败。分别保存 `LOCAL_CANDIDATE_REJECTED`、`NOT_ADMITTED`、`FULL_REQUALIFICATION_FAILED` 或实际阶段事实。原失败/unknown不改写，普通字段/导入/checker问题不作为重算科学数据的理由。不要为了“赶进度”用高精度诊断结果替代complex128生产输出。

## 8. 定向测试与交付

仅四类相关检查：①保存星区通过真正生产RHS核心重放，原b_t只加一次，两个列/state不混用；②复数非Hermitian小块、非零/零内部RHS、complex MPC、带Di时仅一次solve且符号正确；③新J只读共享、default旧路径不变、缺J不悄悄fallback、释放无悬空；④实际Task41配置→owner→新reducer→保存checker→条件owner交接/受监督收口。昂贵FE可以替身，但被改的配置/策略/状态传递不能全mock。

本轮不再扩大checker框架，不默认全仓pytest，不重装环境或重命名目录。主控只集中提交本分支：薄实现及定向回归冻结；数值证据与response_v9收口。更新已有summary/run_index/test_summary及项目总账。新response先答：局部自己的d是否改善；全域新reduced RHS及候选恢复是否过原门；J真实驻留与新增GETRS/时间；后续解锁到哪里。只有完成的阶段可写PASS。ChatGPT本次只提交此review，不修改master或其他分支。

## 9. 可直接交给 Codex 的执行文本

```text
继续Task41extra，先读review_report_v9.md。结果base=
a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f；V8 checker=3ce1a158e3e0b6556a2e094755adf9b5bd18ae08。

本轮唯一候选same_lu_rhs_solve：生产reduce_rhs由T@bi改为同一LU解Kz=bi后−Jz。
不是新PC，也不是已证明修复。先做保存数据上的必要判别，再条件全域，不另等一轮review。

用V8两个incident cells、原candidate S、原known/native RHS和保存LU/解，分别重建
候选自身的s、g_T、g_LU、d_T、d_LU；b_t只加一次，原E/MPC/复数符号不变。
不能只看candidate-reference gap。实际生产小核心必须重放该结论；pivot复制可写，
不重建metadata/张量或再做四次LU。两列自身d确实改善且身份/局部残差正常，才准入全域。
局部不改善则保存否决，不跑约8小时重建，不换第二种方案。

在现有condensation owner按exact key可选保留同一actual张量的A_ti=J；新策略显式opt-in，
default旧路径不变。P6及浅视图共享只读J，不每cell/每action复制，不从−TK或G转置重造J。
每个非零bi一次GETRS；有Di时复用同一个z。MPC-dual/port_rhs/零bi原语义保持。
完整接通Task41 prepare/worker、target和reference实际右RHS调用、验证/恢复/checker；
不能只改诊断。R/T/S/evaluator/native/RHS不改，T本轮仍保留。

J派生新增87,091,200,000 B；旧局部numeric账加J约435,653,172,000 B，非RSS保证。
先核真实缓存库存；旧进程的完整LU/J未保存则不能假称还能用。
局部判别、新窗授权及资源/余额通过后，允许一次必要28,000-key actual-qmetric owner重建，
顺便保留J。复用旧八键/原积分资格，不重跑慢FFCx、A1/A2、carrier生成或64,120模式验收遍历。

同一owner先通过原两列完整action：新生产体积作用、新reduce_rhs、原known/native RHS，
端口未改则继承旧输出仅读两个B帧。动态与冻结D0/D1均<=1e-11。
通过后验候选自身恢复，最多3次已有native残差驱动同LU修正；forward<=1e-11、
native volume residual<=1e-10、trace不变/slave-zero；旧donor PASS不转授。
独立checker全过才继续200q/准确因子驻留/完整参考/条件target，57空端口q保留FE。
重建前补好qualified owner窄交接，避免刚通过又销毁再建一次。

旧窗已过，不能复制余额。新24h窗口（86400/85200/1200秒）待用户一次明确批准，
范围含局部判别、至多一次全域重验及条件接续。批准前先完成本地必要实现/fixture/命令准备。
既有主机、1.5TiB cap、64GiB host reserve、task reserve0、ABI/MPI1/math1、任务swap0不变。
16GiB证据配额启动前规划，按review紧凑资格布局保存必要新两列和恢复终态/残差，
每步真实计数/norm/hash保留；不重写旧全场/全域归因数组，不削弱独立终态验收。

只做新核心、MPC/Di/零RHS、J所有权和正式调用链相关回归，不全仓测试或新框架。
普通bug定向修复后同窗继续，原数值/资源/截止门失败就保全成果停止依赖。
response_v9先报自身d改善、全域门、J峰值/GETRS/时间与新数值能力，再列测试；
保留全部旧失败和UNKNOWN，不合并master，不宣称完整场/最终精度/2TB/48h已经通过。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/docs/task41extra_phi90_p50x50_g17x20/response_v8.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v8_selected_trace_star_audit_20261021.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/src/solvers/p6_cell_condensed_action.py#L3000-L3270
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/src/solvers/hcurl_assembly_time_condensation.py#L3580-L3805
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f/src/solvers/hcurl_assembly_time_condensation.py
