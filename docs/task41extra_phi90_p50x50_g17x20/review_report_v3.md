# Task41extra Review V3：先保存并关闭恢复偏差，再继续完整 B0

## 0. 决定与范围

**接收 V2 的分域资源修复、完整 donor 验收和低驻留消费路径；不接收尚未通过的完整 target action。当前 blocker 是第一组已知输入恢复误差 2.0454083899234283e-11 超过原 1e-11，以及关键向量没有保存。下一轮先做一次有证据的针对性恢复重放，不把已完成的约71分钟全模式作用作为该诊断的前置。利用现有原生残差与同 LU 修正接口，保持全部原门；通过后在同一 live owner 中补齐完整联合验收并继续200q/reference/target。**

| 冻结项 | 值 |
|---|---|
| 日期 / 分支 | 2026-10-19，Asia/Singapore / `task41extra_phi90_p50x50_g17x20` |
| repository / 结果 base | `Rookie1234567/MyFEniCS` / `f224b0ee4deebab7e60bed37d1139f22f1c92548` |
| 最终科学源码 | `53243cd6766b564fed17668753e9fdbb7cab1129` |
| 最后正式 attempt | `20261018T121210.548690Z` |
| 当前权威 | 本目录 task.md、Review V2、用户本轮指令；未发现独立补充任务书 |
| 本次职责 | ChatGPT 只新增本 review；Codex 实现、定向测试、获准计算及 response_v3 |
| 工作范围 | 证据持久化、恢复诊断/有限准确性修复、现有执行链接续；不换PC、不改物理、不升cap、不合并master |

已读远端 response、failure/adoption compact、run index、summary、相关源码及根/docs规则。task.md 和 Review V2 的远端 blob 分别为 `5b669c109006fa91fdeebba2a81d97ba17b640b0`、`e18ba3e01e3721d3134fd26b5b27b799f554bb5b`，与本地已提供全文一致。科学源码到结果HEAD只有一笔文档/证据提交。本审阅未登录工作站、未重读363 GB载荷、未运行FE或项目测试；引用的实测均为远端证据，推导单列。[R1][R2][R3][R4]

物理保持：50×50 nm周期、居中17×20×120 nm Si主体、无额外缺口、z=[-10,130] nm；0.7 nm、掠角1°、方位90°、S、p6、10×200×14。完整64,120模式、200q（57个无端口但保留FE）。最终目标仍为整机十进制2 TB含余量、任务零swap、必要完整单场冷流程≤172800 s及独立网格/模式精度。不是Task39para的p4 BAL_H任务。

## 1. 已完成与尚未关闭的资格

| 对象 | 接受范围 / 未完成边界 |
|---|---|
| 13.5 nm A1/A2 | 原直接场、6步迭代与保存场对照继续有效，不重跑。它不保证0.7 nm收敛。 |
| 资源分域修复 | 按原触发样本及定向回归接收；原1.5 TiB cap、64 GiB host reserve、task reserve0、swap与时间门不变。旧误停和后续清场记录保留。 |
| 完整carrier | 64,120模式、363,791,051,840 B前缀完整校验；64,121项只读offset，512,968 B；新生成模式0。旧producer与新consumer分列。 |
| 新B0支持证书 | B/D边界项分别9,094,725,000，cell-interior非零值0；只在匹配的当前数据/布局身份内有效，不借Task40旧证书。 |
| 最后全模式双输入作用 | 64,120/64,120处理完成；两代表模式消费检查PASS。这是执行覆盖，不是尚未执行的完整P6/native联合门PASS。 |
| 当前数值失败 | 第一组mode16030恢复前向相对误差2.0454083899234283e-11，门1e-11；约为门限2.0454倍。绝对误差、误差主导位置、原因未知。 |
| 第二组 / 凝聚一致性 | mode48090恢复及P6作用对凝聚RHS的最终判定未执行；不能写成一起失败或通过。 |
| 200q / 全参考 / FGMRES / 场 | 未运行；无独立A6和official R/T/A；原worker exit4/WORKER_FAILED保留。 |

最后workflow父段9364.070864045061 s（约2.601 h），全模式作用子段4257.863887676038 s（约70.964 min），读取/解析子计时93.11829357547686 s；它们不相加。tree RSS峰11,411,648,512 B、task cgroup峰11,872,563,200 B、task swap0、后代清场；PSS与逐backing峰值未知。宿主swapin/out的13/0页不归因给任务。旧1.58 TB生成阶段与当前11.87 GB消费阶段不同，不能报严格优化倍数；也不能由当前峰值证明全因子组能驻留。[R1][R2][R3][R4]

## 2. 源码结论：可以先检查恢复，无需先全模式扫描

`_task41_b0_full_size_two_input_identity_check` 当前先制造两组完整输入和复制原生volume RHS，再运行一次 `action.apply_multi_rhs` 全模式遍历，随后reduce/recover；第一组超门立即raise，完整向量和最终check尚未写出。[C1]

两组输入是确定性见证：沿用raw D probe的trace数据，每个cell内部以原始row号生成非零值；两列的端口向量分别只有mode16030、48090非零，alpha为0.7−0.4i。已完成的支持验收又证明本B0的Bi=Di=0。因此：

- 每组见证的 B·alpha 只需读取对应的一个已保存模式，不需要遍历其余零振幅模式。
- 内部恢复只取full_rhs内部行，不需要先得到所有 D·x 或端口RHS。当前内部行的 B·alpha 为零，原生体积RHS的内部行就是所需值。
- **先建立与原测试相同的完整known field、必要fresh volume/局部凝聚owner，保存RHS并做恢复；两组恢复闭合后才做剩下完整联合作用。** 这不是删掉最终全模式门，也不把选中两模式当完整场。

旧完整输入和RHS未保存，不能伪称可以离线重算原失败向量。先检查旧目录是否有独立产品；若仍缺失，允许一次按原源码配方的受监督重建，并标 `RECONSTRUCTED_WITNESS_FROM_FROZEN_RECIPE`。raw模式包、实际FE/MPC/方向、系数材料、积分和恢复布局均需核对；没有旧向量hash，不能声称新RHS与旧RHS逐字节相同。

`recover_storage` 当前计算的是“同一LU求内部RHS + 预存trace恢复项 − port恢复项”，本函数没有执行内部残差修正。已有 `correct_internal_storage` 可固定trace，仅用同一LU处理独立残差内部行；Task40 V25已有最多三次此类修正的实际调用先例。[C2][C3] 这只是可复用机制，不是新B0根因或通过证明。

## 3. 一次重放先取得可离线复算的失败包

在现有worker/helper内增加窄的恢复诊断顺序和artifact回调，不复制一套V3 runner或存储平台。输入/RHS返回即持久化，不能等全部门结束才保存。按每列分段，数值非有限立即保存可安全保存的部分并停止；有限超门先保存，不在另一独立列取证前无条件丢掉owner。

| 保存时点 | 最小必要内容 |
|---|---|
| 原生作用之前 | 两个known全场、reduced trace/port输入及实际alpha、raw probe指针/hash；active/slave/interior分类与cell/class/方向映射身份；字段shape/dtype/范数 |
| 每个原生作用返回后 | 原生volume RHS的独立拷贝、最终b_FE及其已选B·alpha构造记录；原生curl/负质量项能廉价取得时一并保存，否则在误差定位后只补受影响项 |
| 每次恢复之后、判门之前 | 原始恢复场、差向量或足以重算它的两向量、绝对误差、known范数、原相对比值、trace/slave误差、按cell内部误差平方和及最坏row/class |
| 独立残差之后 | 原生作用于恢复场的结果、b−A·u、内部/trace/slave分组范数；每次修正的输入残差/输出/计数/用时 |
| 全模式阶段返回后 | 两组P6输出、完整port RHS、reduce_rhs输出、两个原分母和相对差；无论后面PASS/FAIL先保存 |

借用PETSc输出必须复制后再下一次apply，不destroy owner的借用Vec；传入Vec/数组keepalive明确。保存采用已有NPY/manifest原子写与hash回读，不用大型压缩NPZ消耗时间；先做磁盘/额外数组工作集准入，一次处理一列或复用小缓冲。由真实full_rows计字节，不能按“只增加日志”记零内存。

所有局部原始矩阵不逐cell全量落盘。先用全域误差向量定位，选最多3个主导cell/class（必要时另取一个不同材料/方向对照），按同一编译积分、所有kernel、方向和原局部排序取得原始Vii/Vit及相关块，连同局部LU/pivots、trace expansion、b_i、known_i、recovered_i保存。相同class只存一份。**不能用LU重构矩阵或从recovery反推Vit充当独立raw张量。**[C2]

只读checker从数组重算误差、残差、trace不变和限值，不只相信status。前两次工程失败和第三次缺向量的负记录保留，新包不得补写成旧attempt当时已保存。

## 4. 如何区分根因，而不是猜“舍入误差”

令t为按真实MPC展开的局部trace，u_i为内部场，Vii/Vit为原始局部体矩阵。固定alpha和trace时：

```math
V_{ii}u_i+V_{it}t+B_i\alpha=b_i,\qquad
u_i^{(0)}=\operatorname{solve}_{LU}(b_i)+R_it-X_{iB}\alpha,
\quad R_i\simeq -V_{ii}^{-1}V_{it}.
```

当前B0在已证书范围内Bi=0。对新保存的known状态u_i^*，分别算：

```math
\Delta_i=b_i^{\mathrm{native}}-(V_{ii}u_i^*+V_{it}t+B_i\alpha),\qquad
r_i^{\mathrm{local}}=b_i^{\mathrm{native}}-(V_{ii}u_i^{(0)}+V_{it}t+B_i\alpha).
```

理想精确局部求解的误差也可能包含Vii逆作用于Delta；所以很小的局部残差不自动保证known前向误差。以下是诊断分支，不预判谁成立：

| 观察 | 需采取的最小动作 |
|---|---|
| trace/slave或映射先不一致、同输入重复作用不一致 | 先查表示、MPC单次回拉、借用buffer和状态；不靠LU精化绕过它。已有row分类/alpha修复不无证据重开。 |
| Delta明显主导，或native/local分量不一致 | 查原kernel累加、材料、积分、方向和native/local实现；先用相同输入逐分量定位，不换一个“更容易过”的oracle。 |
| RHS制造/大项相减产生可测精度损失 | 比较原complex128组装顺序、raw局部残差及有限高精度累加诊断。高精度只用于有界诊断，不把正式解偷偷换成complex256。 |
| 同算子一致而初始内部解残差明显 | 可使用下一节既有同LU修正；追踪原残差与前向误差，不以某项变小就宣布根因。 |
| residual很小而forward仍停滞 | 在最坏class用既有LU做有界条件/敏感性估计；不做全cell SVD，不升阶/换网格掩盖故障。不能仅以病态解释放行。 |

绝对误差、known全场范数及原相对量必须同时保存。保持原前向分母 `norm(known_full_field)`，不临时改为恢复场、入射幅度或某个更大尺度。局部零参考行报告绝对误差，分组范数和条件估计是诊断，不临时增加数千个逐cell硬门。

## 5. 有条件复用同 LU 修正，门限及真实生产语义不变

完成上述最小取证、确认无结构/身份错误后，允许对同一未修改RHS尝试现有 `correct_internal_storage`，**每列初次恢复后最多3次，与既有V25上限一致**；不加次数、不重新分解、不换PC、MUMPS参数或物理损耗。更新只能使用独立原生残差，不得使用known误差向量作校正：

```math
r_i^{(j)}=\left[b_{FE}-V_{\mathrm{native}}\widetilde u^{(j)}-B\alpha\right]_i,\qquad
\delta_i=\operatorname{solve}_{LU}(r_i^{(j)}),\qquad
\widetilde u_i^{(j+1)}=\widetilde u_i^{(j)}+\delta_i.
```

只修改内部行，trace/alpha不变，slave storage保持精确0。Bi=0且alpha固定时，这个内部残差不需再次遍历64,120模式；使用复制的原生volume输出及已验证的选中B项即可。同一次owner持有原LU，未保存/已销毁的factor不能假称还在；这里所需的是单元局部LU，不是200q全局factor。

逐次保存原始失败状态、native残差及forward。误差停滞、非有限、结构性差异或原门仍未过则停止依赖路径，不无限校正。若采用高精度raw局部残差累加，使用已存在的有界机制并记录平台真实精度，正式数组、LU和场保持complex128。

**若修正是通过所必需，必须把同一明确的opt-in恢复策略接到当前B0真实恢复/残差/输出消费者；不能只在测试里修好再让正式计算继续调用旧raw恢复。** 保留旧默认和A1/A2身份；对未改数学依赖的历史场不重跑。验收必须仍包含未替换的P6作用与凝聚RHS一致性；若局部修正只改善field而Schur/RHS门仍失败，不得授予完整target action资格。

本轮退出门：两列known恢复均≤1e-11、active/slave约束通过、独立原生残差按既有完整体积见证≤1e-10；完整P6/native reduced-RHS两列及original/active D一致性继续≤1e-11。前向、残差、凝聚三类状态分别记录。native残差检查复用已有机制，不调用全carrier反复计算诊断用内部残差。[C2][C3]

## 6. 最小重放范围与后续连续执行

1. 先做原有分支/ABI/资源/窗口及donor只读准入，建立必要fresh FE/MPC/volume/局部凝聚，复用已验证carrier、offset和raw代表模式。新进程根据原完整性规则核验文件；不取消必须的校验、不重新生成。若现有验证本身需要完整顺序读取，最多按既有准入执行一次并记录，不把它混称为全模式作用重跑。
2. 在旧全模式apply之前，通过直接读取对应两个frame构造每列B·alpha，先做第3–5节的两列恢复取证/修正。原native仍按相同输入和实际MPC计算；不能把同一condensed算子生成的RHS作为唯一oracle。保存失败包后可在同一scope对有依据的局部原因做诊断，不盲目重启完整模型。
3. 恢复闭合后，在同一live owner中做必要的完整双输入P6/D/B/H与reduce_rhs联合验收。旧run没有保存p6_result/reduced_rhs，不得假称能直接拿旧向量验算；因此允许**一次**本轮完整联合遍历并在返回时立即保存。未改变的donor/support及代表检查继续继承，不重新积分。按状态跳过已经持久PASS的阶段，下一次元数据失败不重放该遍历。
4. 全部适用门过后继续现有target assembly、各真实reference sector、200q CSR/native、原exact ALL_Q_RESIDENT与两RHS、完整参考逆，再在资源/余时许可下进入FGMRES32/zero/max2048。57个无端口q不删FE。目标原A6≤1e-6和物理/体吸收≤1e-5、最终网格/mode精度均保持；参考strict/V15按各自原合同报告。

当前约71分钟是两输入测试中全carrier/P6作用的实测父时间，**不是一次正式PC或FGMRES迭代时间**；其中解析93秒也不是完整磁盘I/O占比。正确性闭合后在实际target/reference调用中分别记录volume、端口、局部求解和replay次数；不要现在另开缓存/暖启动/新PC项目。若完整动作吞吐不足48h，用真实活动成本报告，不从单个局部测试或旧q0×200推断全场。

全局求解前保持完整共驻账：carrier实际页、FE/MPC、分类器/映射、local LU/Schur/recovery、所有q CSR/PETSc输入/转换/因子、Krylov、恢复/输出/checker及系统余量。诊断新增向量和文件页也计入，不借较小consumer峰值放松未来准入。新开进程的临时资源必须清场；普通bug只修受影响范围并冻结新source，不热改运行源码。

## 7. 时间与授权：原窗口目前尚未截止，不能用旧剩余值

| 固定合同 | 值 |
|---|---|
| 原T0 | 2026-10-17T05:43:44Z |
| 原数值截止 | 2026-10-19T05:23:44Z，即新加坡2026-10-19 13:23:44 |
| 原总截止 | 2026-10-19T05:43:44Z，即新加坡13:43:44 |
| window SHA | `87dd4ec560a208122e9959987a392bf878162793c61582877969206686d922e6` |
| 主机/目录 | 既有`fenics-ws:/home/fenics/Projects/laptop_share`；Codex项目与对话不变 |
| task cap / host reserve | 1,649,267,441,664 B / 68,719,476,736 B；task reserve0 |
| ABI/资源 | 原complex128/int32、MPI1/math1、exact MUMPS，task tree/cgroup swap0，PSS不采样记null |

审阅中查询的实际时间快照为**2026-10-19 07:02:48，Asia/Singapore**。距原数值截止为22,856 s（6小时20分56秒），距总截止24,056 s；这些只是该时间点的UTC上界，不是工作站账本读数，更不能重复使用最后run的约52,529 s余额。接收、冻结、启动和长步骤前均由现有合同读取实际UTC/monotonic/累计余额，取更紧限制。[W]

在原许可范围和实际余额内，本review允许上述一次针对性恢复重放及门通过后的连续计算，不为同一主机/cap重新停审。启动前先记录预计必要准备与安全收口是否能容纳；不以本报告估计保证完场。

若Codex接收或冻结时已到原数值截止：不启动新FE/全文件验证等heavy；只能按原总截止收口。若总截止也已过，旧窗完全关闭；本地小型代码/定向测试可准备，但不能把它记入已结束的运行窗或复活旧T0。**新执行窗备用提案为24小时（总86400、数值85200、收口1200），状态PENDING_USER_APPROVAL；须用户一次明确批准，新window父链引用旧window和全部费用，不改写旧T0。** 不是自动再给48小时，更不意味着完整冷流程48h已通过。

## 8. 有限测试、持久化出口与提交

只覆盖本轮三个真正风险：①在首列有限超门时raw输入/RHS/recovered/residual先保存，checker能重算，第二列状态不造假；②same-LU最多3次、不增加factor次数、只改内部、借用Vec不失效，且故意错误native/恢复必须仍失败；③真实Task41配置到同一worker的诊断顺序/require-existing/窗口和收口链，证明恢复诊断前不会自动调用完整P6 carrier sweep或producer。昂贵数值内核可在该集成测试用替身，正在验证的路由/状态/保存逻辑不能全部mock。

不跑全仓测试、不大整理、不创建新执行项目。V2整文件12PASS/3FAIL未做baseline，不能直接写“已证实原有失败”；相关reference路径真正要使用前，定向核对这几项与当前修改的关系，必要时最小修复，不用全仓pytest作为前置。不同源码/ABI/未提交diff的测试证据保持原绑定，本轮测试绑定最终冻结源码。

阶段产品各自保存状态：RAW_RECOVERY_CAPTURED、RECOVERY_GATE_FAILED、RECOVERY_QUALIFIED、FULL_ACTION_QUALIFIED，以及实际sector/q/reference/field状态。名称可沿现有schema字段表达，不为枚举再开发版本框架。required checker受监督核原始产品，数值失败不等于checker无法记录；缺footer保持真实负结果，同时保留独立完成产品。无需为补旧footer重跑PDE。

推荐提交①必要薄改动和定向测试；②新raw诊断、修正依据、实际继续计算和收口。只推本分支，主控集中冻结/提交，执行者不自行push，不改母Task40/Task39para/Hybrid/master。写response_v3，更新现有run_index/summary/test_summary和两级总账；先回答恢复为什么偏、原门是否关闭、实际解锁哪一步，再列测试。old producer→consumer→新见证/修正source依赖清楚，完整冷/warm/开发账与未知项分别保留。

## 9. 可直接交给 Codex 的文本

```text
继续 Task41extra，在 task41extra_phi90_p50x50_g17x20 读取 review_report_v3.md。
结果base=f224b0ee4deebab7e60bed37d1139f22f1c92548；失败科学source=53243cd6766b564fed17668753e9fdbb7cab1129。

接受V2分域修复、完整carrier/offset与当前B0支持证书；A1/A2不重跑。
当前第一组恢复2.0454083899234283e-11>1e-11是真实未闭合数值门，
不是已证明舍入或普通bug。旧完整输入/RHS/recovered没有保存，不伪称离线重算过。

先薄改现有helper：known输入先保存，native RHS复制后立即保存，
每次recovered、独立native残差、原范数/绝对与相对误差在判门前落盘。
按原mode16030/48090和原确定性内部配方重建一次真实见证，保持映射/材料/
积分/相位。不要为了到达这个门先重跑约71分钟全模式P6作用：每列alpha只有
一个非零模式，直接读对应B帧即可；已证Bi=Di=0，内部恢复不需完整D·x。
必要fresh FE/local LU可建，不建200q/global factor来诊断，不重新生成carrier。

同一实际owner先比较native/local内部残差和原始恢复，按误差选最多3个主导
cell/class保存raw局部块，区分kernel/映射差异、RHS制造/相减、LU误差。
不能由LU或recovery反推矩阵充当独立raw oracle；不做全cell密集矩阵归档。

无结构错误且有残差证据时，可用已有correct_internal_storage，固定trace/alpha，
按独立native残差每列最多3次同LU修正，不新建factor、不改门限或分母。
不能用known误差生成修正。逐次记录；forward与residual必须分别达标，
若修正是必需的，当前B0生产恢复也必须使用同一opt-in策略，不能只修测试。
原两列forward<=1e-11，原P6/native凝聚RHS和D映射<=1e-11；独立原生体积
残差按既有见证<=1e-10，slave精确零，active trace不变。没有通过就保留新raw
失败包和具体原因，不放行200q/FGMRES。

两列恢复闭合后，用同一live owner做一次必要完整联合验收，返回即保存全部
p6_result/port_rhs/reduced_rhs。旧全模式遍历完成不等于缺失向量可以复用，
但不重跑producer/旧模式资格。通过后在原资源和剩余时间内连续target→200q
CSR/native→ALL_Q_RESIDENT两RHS→完整参考→FGMRES/恢复/输出，57个空端口q保留FE。

接收/冻结/启动时读取真实余额。原T0=2026-10-17T05:43:44Z，数值截止
2026-10-19T05:23:44Z，总截止05:43:44Z；不使用旧52529秒余额、不刷新T0。
若已截止不启动heavy；新24h窗只是review内待用户一次批准提案，不能自动启动。
主机/目录、1.5TiB cap、64GiB host reserve、task reserve0、task swap0、原ABI/
MPI1/math1/MUMPS均不变；新source合同与旧producer身份分开，不取消donor完整性验证。

只做持久化、同LU/借用buffer、实际路由三类定向回归，不全仓测试或重构。
现有prepare/service输出真实continuation命令，最小集成检查后冻结source。
普通bug同窗修复继续，真实数值/资源/截止门停止受影响路径并保留成果。
response_v3先报恢复偏差原因、门是否关闭和实际新增计算能力；完整向量在ignored
artifacts，远端留精确路径/hash/独立checker。父子不重复计时，不推优化倍数或
未运行的2TB/48h/全q/场通过。只提交本分支，不合并master。
```

## 固定来源

[R1][R2][R3][R4] 指下列四份结果文件，所有代码链接均冻结在本次结果base：

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/docs/task41extra_phi90_p50x50_g17x20/response_v2.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_full_rhs_recovery_gate_failure_20261018.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/docs/task41extra_phi90_p50x50_g17x20/outcomes/p0_v2_adoption_action_performance_20261018.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/src/runners/task40_v10_worker.py#L260-L590
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/src/solvers/p6_cell_condensed_action.py#L3030-L3270
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/src/solvers/task40_v25_complete_volume.py#L530-L719
[W]: https://github.com/Rookie1234567/MyFEniCS/blob/f224b0ee4deebab7e60bed37d1139f22f1c92548/docs/task41extra_phi90_p50x50_g17x20/review_report_v2.md
