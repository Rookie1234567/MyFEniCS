# Task41extra Review V14：有界同LU残差校正，先用保存包验证而不重建全域

## 0. 裁决、身份与范围

**接受V13的局部机制证据和保存数据复核；批准一个显式、有限的生产核心候选用于保存包试验：原LU初解后至多两次残差校正，残差采用明确的binary64实虚补偿求和，最终由真实核心返回z与−Jz。不是批准全域修复，更不是批准再次约19小时构建。先在cells360/446验证，改善后同窗完成既有保存块的跨材料/方向覆盖和生产接线检查；全域实验必须另有准入与明确授权。**

本轮消除的blocker：已有证据把一条真实trace行的大部分有符号偏差关联到内部RHS求解残差，但尚未做任何针对该残差的生产候选试验。继续只解释旧误差或重建FE都不是最小下一步。本包用既有K/J/LU与原RHS实际检验可否降低这一偏差，失败直接保留否决。

| 身份 | 冻结值 |
|---|---|
| 仓库／执行分支 | `Rookie1234567/MyFEniCS`／`task41extra_phi90_p50x50_g17x20` |
| 结果HEAD | `e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2`，审阅时远端一致 |
| 结果基线／前份review | `a6cde586698dc44d15b365ac8edd711768a229dd`／`f86e07b252eb8e9a046e5fc7588a8031b97017f1` |
| 最终V13 checker source | `af953ef38ba2f95a2e443e131dece20c17af8c1e` |
| 两cell producer | `196aedecbef5d129588c629fc091682d7a2900f4`；旧产品不重新署名 |
| 日期／审阅类别 | 2026-10-24，Asia/Singapore；代数一致性、数值稳定性与有限候选验收 |
| 最终目标 | 原0.7 nm、50×50×140 nm域、居中17×20×120 nm Si、方位90°；Full3D、十进制2 TB含余量、任务swap0、必要冷流程≤48 h |

核对response、compact及证据索引、当前生产核心与reduce/recovery调用、V13源码差异及既有task/review/根docs规则。任务物理与原数学门不变。ChatGPT只提交本review；没有访问工作站NPY、运行FE或项目测试，不把仓库记录称作本Chat重新实测。V13的序列化修复与真实科学结论分开。[R1] [R2] [R3] [R4] [C1] [C2] [C3]

## 1. V13接收结论及不得扩大之处

| 证据 | 接收范围 |
|---|---|
| 8组逐操作账、4组目标行分解 | 接收其保存数据复核；宽算术剩余约4.106e-13～1.476e-12，关键分量Decimal核验不覆盖所有分量 |
| A_rb=Σ(−λᴴr_b) | 两列约−4.9564304983e-9+4.3504314536e-12i、3.4478912707e-9−9.5434045200e-9i；扣除后剩余范数比5.13%／1.70%，不是贡献百分比，也不是GETRS程序错误证明 |
| J乘法／scatter诊断 | 相对原d约1.58%／2.43%；不能与前项百分比相加减，也不代表修正后误差下限 |
| 覆盖 | active87567/original250113、cells360/446；约占全域误差能量0.00627%／0.00664%，局部支持不等于全域通过 |
| 科学状态 | V9全域action仍为2.6749770637124364e-10、5.613598120039757e-10，对1e-11均FAIL；V9恢复NOT_RUN_ACTION_GATE_FAILED；旧donor PASS不转授 |
| 工程状态 | attempt10保存复核完成；旧tuple/array序列化缺陷及失败记录保留，不是全域数值失败原因 |

主分析23.331 s包含两次伴随回代0.0196566465 s；attempt07–10服务父段合计120.827731364 s，不再加子阶段。最大采样tree RSS714,338,304 B，cgroup另列，task swap0；工程等待、窗口外收口及无收据成本保持UNKNOWN。定向fixture报告缺完整source/log hash，不冒充绑定最终源码的科学资格；下一次仅重验实际修改相关节点。summary顶栏仍写V12属于轻量汇总滞后，随下一response修正，不为此重跑或阻挡候选。[R1] [R2] [R3]

## 2. 为什么反复卡“精度”：当前不是网格收敛失败

当前门比较同一离散系统的两条计算路径，而不是FE相对连续Maxwell真解或RCWA的物理误差。单元内部/trace分块为：

```math
\begin{bmatrix}K&G\\J&L\end{bmatrix}
\begin{bmatrix}u_i\\t\end{bmatrix}
=\begin{bmatrix}b_i\\b_t\end{bmatrix},\quad
S=L-JK^{-1}G,\quad g=b_t-JK^{-1}b_i.
```

实现使用原LU及R/T/S，消去内部未知量以节约全局内存。精确算术下这些关系等价；浮点计算中，局部积分、消元、matvec、RHS制造及相减分别产生误差。complex128是两个binary64分量，不是每个分量128位精度。少量局部误差还会通过J和K的逆方向放大。[N1] [N2]

令保存初解为z，原始矩阵残差r=b_i−Kz，则仅对这项求解误差有：

```math
g(z)-g(K^{-1}b_i)=JK^{-1}r,\qquad
\delta d=-JK^{-1}r\quad(d=y-g).
```

这说明负的伴随投影−λᴴr为何能解释当前局部d；它没有证明其他项为零。V6与V9两个已知输入的y完全相同，恶化只在g的trace，已经把本次跨run变化定位到缩减侧；这仍不是所有输入上的算子等价证明。[R4]

强相消是现实风险：V12该行局部/原生项约1e4～1e5，而最后差约1e-9；绝对误差不能只按最后的小数尺度估计。原完整比较分母约2225.48，1e-11允许绝对L2约2.2255e-8；V9实际约5.9531e-7、1.2493e-6，超限约26.75、56.14倍。局部原矩阵残差、恢复forward、完整action、真实散射A6以及网格/mode收敛是不同指标，不能互相转授。[R1] [R4]

“单个块通过”不保证“大向量通过”：若百万行各有约1e-10误差，其L2约1e-7，这是说明性的算术例子，不是本例测得误差分布。原最坏单行本身远不能代表全域L2。尚无完整场，不能将上述1e-10说成最终R/T误差，也不能假设网格加密可消除此一致性问题。

此前确有工程和诊断错误：Bα漏项、状态配对、只读pivot和窗口接线等；它们增加了轮次，但不是每轮都产生了一个新完整场失败。原同一action FAIL在多轮报告中持续保留。真实的局部/全域候选试验与保存分析应分别计数。更早的局部改善也不足以代表全域，审阅组织应吸取这一点：本轮先便宜验证并扩大现有保存覆盖，绝不凭单行再批准长跑。当前没有全域条件数证据，不把“病态”“高阶”“0.7 nm”当成未经测量的唯一原因。

## 3. 唯一候选：同LU、binary64补偿残差、最多两次校正

### 3.1 生产位置与不变项

修改目标是 `src/solvers/hcurl_assembly_time_condensation.py::project_internal_rhs_same_lu`，或它调用的一个同模块窄helper。现代码只做一次`lu_solve`随后`−J@z`，并未进行RHS残差校正。默认行为保持原样；以显式可选参数`refinement_max_steps=2`及冻结的残差策略绑定候选，默认0，不另造PC或V14框架。[C1]

输入必须包含与该LU来自同一actual/oriented张量的原始K。不能由LU乘积重造K作为残差oracle，不能混用reference K、旧canonical K或重新制造RHS。S/R/T/J、原b_i、native、积分、MPC、材料与precision均固定。原有最多三次全场内部恢复修正是另一层算法，次数不增加；本轮只新增一个有明确上限的RHS校正候选，不借用或冒写旧恢复计数。

### 3.2 明确的残差算法，不把宽算术诊断偷偷变为生产

本候选残差使用binary64乘法和标准库`math.fsum`式实虚补偿求和，对每个完整内部行计算：

```math
\begin{aligned}
\rho_{\Re,i}&=\operatorname{fsum}\left(b_{\Re,i},\{-K_{\Re,ij}z_{\Re,j}\}_j,\{+K_{\Im,ij}z_{\Im,j}\}_j\right),\\
\rho_{\Im,i}&=\operatorname{fsum}\left(b_{\Im,i},\{-K_{\Re,ij}z_{\Im,j}\}_j,\{-K_{\Im,ij}z_{\Re,j}\}_j\right).
\end{aligned}
```

把b项一起放入求和，不先产生低精度Kz再相减；每个实乘积仍为float64，fsum输入/输出为binary64，最终ρ及z均complex128。按固定j顺序、固定实虚符号实现，不使用共轭。可按行或有限小块暂存实乘积，禁止全域批量临时数组。该策略改善求和误差，但**不消除乘积舍入，也不保证r真实准确到任意位数**；必须由独立较宽残差复核。[N1]

本review显式批准这个局部求值组织变化，不允许自动改为longdouble/Decimal残差驱动、complex256求解、改native或切换第二残差算法。V13宽算术/Decimal只作为独立评估，不参与校正向量生成。若补偿残差仍不足，分类`RESIDUAL_EVALUATION_LIMITED`并交还事实，不静默升级精度。

### 3.3 迭代、返回和停止

```text
z0 = 原lu_solve(LU, b_i)
对k=0,1，至多两次：
    rho_k = 上述固定binary64补偿残差(K, z_k, b_i)
    delta_k = 原lu_solve(同一LU, rho_k)
    z_(k+1) = complex128(z_k + delta_k)
最终 correction = -(J @ z_final)  # 原完整矩阵乘法
返回真实z_final、correction及完整计数/成本
```

零RHS沿原路径返回精确零、GETRS=0。非零RHS初解一次、最多两次额外GETRS；中途非有限、shape/identity/pivot异常立即拒绝。ρ精确为零或更新逐位不改变z时提前停止并记录原因；不是自动scientific PASS。其余情况执行固定两次，不凭known误差、目标行d、λ或“哪个中间结果看起来最好”挑选步数/答案。最多次数耗尽后不追加第三次RHS修正，不重factor、不换排序/损耗。

第一阶段两cell×两列最多4次初解＋8次校正=12次GETRS。初解需通过真实新生产入口，并与保存z0/correction绑定；这是本次候选调用，不重复旧8个r_i诊断或两次伴随回代。j0/j3同b_i共享同一z，λ只读复用。每步在判门前保存z、ρ、delta、实际返回correction及计数。保持pivot可写owned int32的现有安全处理，不更改旧NPY。

## 4. 第一阶段验收：既要真残差改善，也要自身d改善

先复用V12中y9/g9精确重现的基线。只计算新算法影响的内部解和缩减；不要重新积分、factor、生成S或重跑184项旧审核。原known场仅用于验算，不能用于求校正。

### 4.1 三个独立层次同时记录

1. **核心返回量**：独立完整`−J@z_final`核对实际返回的correction；污染correction但z正确的反例必须被拒绝。不能丢弃返回量再重算一个正确答案冒充生产输出。
2. **全部450个内部行**：以原存储K和b_i独立计算每步真残差、绝对L2/∞范数、相对b_i范数及分量后向误差；不是只检查目标行投影。局部这些尺度不替代冻结的全域分母。使用已验证的宽算术读取器衡量补偿残差噪声；必要时仅对最差分量用原Decimal方法确认精度级别，不重做V13全部归因。
3. **原生产累加次序**：固定原y，先写全局b_t一次，再按cell、trace/MPC原顺序散射实际返回的correction；Bα/port各处理一次。分别保存y、g、candidate自身d，不只比较candidate/reference gap，不用新旧差向量直接补答案。

同一S与输入下，y必须保持绑定；g的实际变化与各cell返回correction变化投影相符，最后乘加余差单列。λ投影可用于解释变化方向，不能用于校正、停止或选结果。Di非零时必须消费同一个最终z，不能保留初解用于port；真实本B0内部Di=0资格继续继承，非零Di通过小fixture保护一般接口。[C2]

### 4.2 有限、可否决的筛选

两列目标行自身d均应有超过独立求值分辨率的改善，四个真实内部RHS的独立残差不恶化且有可信下降；每步原始结果全部保留，不把普通double残差下降当作独立真残差下降。若真实残差变好但d无改善，判该候选不足，不追加次数；若测量噪声覆盖改善，判INCONCLUSIVE，不写PASS。

一旦局部不改善、真残差恶化、输出状态不一致或成本明显不合理，保存`LOCAL_CANDIDATE_REJECTED`及准确原因，终止该候选的后续阶段。不自动回退stored_T作为成功，不串行尝试第二算法。这个出口不要求新全域运行。

## 5. 改善后同窗做最小保存覆盖，不再只看一条最坏行

第一阶段通过后无需停审，在同一获准小窗口内继续**已经存在且身份匹配的保存数据**：

- 必做新star的360/446与旧star的23352/23493；两条完整star均用两列原RHS及各自原MPC/输入重放candidate自身d。至少覆盖现存两种实际材料tag和两种方向；逐项读metadata，不把tag名字猜作材料。
- 用原八代表键的保存清单核对材料/尺寸类别/方向覆盖；对其中已有完整candidate K/J/LU、映射和原b_i的独立类别补同一候选。总上限为上述4cell与原8键的去重并集，最多12个key，不重新积分或分解。缺LU或原RHS映射时列精确缺项及用途，不能拿reference LU顶替。
- 两个star均需各自y/g绑定、残差与d改善；其他保存键核对完整局部残差和投影，不把含其他cell贡献的全局native trace当作某一cell的局部native trace。

这一覆盖仍不保证全域L2门。输出最多到`SAVED_COVERAGE_READY_NOT_GLOBAL`；未覆盖的类别和旧factor身份缺口逐项列明。本轮不为补覆盖建立新mesh或factor，更不把合成fixture替代真实缺失类别。

## 6. 生产接线、内存和完整验收的后续准入

### 6.1 不能只把诊断修好

候选核心必须位于共享求解模块，由现有P6 `_project_internal_rhs`／`reduce_rhs`真实调用。旧`stored_T`和不精化的`same_lu_rhs_solve`默认行为保持。统计中现有“每非零RHS计一次GETRS”需在新策略下改成真实initial＋correction次数，分别记录residual、GETRS、update、J及scatter成本，旧账不重写。[C1] [C2]

局部覆盖通过后才完成新策略的owner/target/reference配置传播和紧凑验收接线。采用新策略的真实恢复中，内部RHS解也须使用相同策略；R作用、B端口恢复和最多三次native内部恢复门保留，不能只改验收函数而漏掉正式恢复或Di。小型路由/借用释放测试通过后才可提出全域实验。

### 6.2 校正需要原始K；LU不是K的替代品

现在owner保留LU、R/T/S及J，不能假称原始K也已常驻。未来生产若采用本策略，按actual key可选保留同一张量的K，提供只读共享所有权及借用释放；避免让K/J切片继续持有整个882²原张量backing。不能每个RHS重新积分K，也不能用LU重构K来计算“真残差”。

按当前450内部行、complex128和28,000唯一key推导：每K=3,240,000 B，总K=**90,720,000,000 B**。加到旧约435,653,172,000 B局部库存后为**526,373,172,000 B派生载荷**；不是新RSS，不是准入已通过。真实共驻还包括FE/MPC、port页、工作区、全部q/因子、Krylov、恢复输出和系统余量。本轮只读小块，不分配此全量。

完整性能要测residual的全部行/实乘积/fsum、至多三次GETRS和J乘法；不能拿V13两次伴随0.02 s预测生产开销。fixed2校正意味着每个非零RHS最多额外两次回代及两次K残差作用。后续全域预算必须以实测活动成本和原19小时owner负担为依据，不用局部PASS承诺48小时。

### 6.3 全域启动仍需单独明确裁决

只有保存覆盖、真实生产接线、残差噪声评估、完整对象账和时间预算全部形成后，才提交一次必要全域两列验收的具体计划与新窗口请求；**本V14不自动授权该重建**。若得到授权，最多一次、同一owner内依次：原两列dynamic与冻结分母action≤1e-11；candidate自身恢复forward≤1e-11、native volume residual≤1e-10、trace/slave门及≤3次原恢复修正；独立checker。未改端口输出继承、仅读两B帧，不做64,120模式验收遍历。

这些门全部通过后，才由相应授权与完整资源账进入200q、准确因子两RHS、完整reference及真实target FGMRES。57个空端口q保留FE。真实target A6≤1e-6、物理门和最终网格/mode精度仍独立验收。不能把本地修正数量或窗口拆分隐藏为完整冷流程达标。

## 7. 时间、执行授权和开发成本

旧窗T0=`2026-10-23T23:12:47Z`，数值／总截止`2026-10-24T04:52:47Z`／`05:12:47Z`，即新加坡10月24日12:52:47／13:12:47；本次审阅核对时间已晚于总截止。禁止复活旧T0或复制旧余额。

提出新**6小时保存候选包**：21600 s总窗、20400 s数值、1200 s收口，状态`PENDING_USER_APPROVAL`。一次批准仅覆盖保存两cell试验、条件既存覆盖与独立审核，不包含全域构建或新factor。先完成窄实现、相关fixture、实际命令和身份接续准备，再在用户批准后登记新窗；正式准备从T0计费，同窗修复不刷新。旧source/window作为producer证据，新consumer另外绑定，不能每轮在源码中写死attempt号。

沿原工作站`fenics-ws:/home/fenics/Projects/laptop_share`、1.5 TiB cap、64 GiB host reserve、task reserve0、complex128/int32、MPI1/math1、task swap0。局部工作集沿6 GiB准入范围，新证据目标≤16 MiB且不超过既有512 MiB单包／16 GiB累计／2 GiB磁盘底线；旧矩阵不复制。已退出owner不称仍live，读取保存LU不等于新分解。旧失败、负审计和费用全部保留。

只做本次校正上限/零RHS、原K身份、实际返回correction、Di状态一致、补偿残差符号以及saved入口的必要回归；测试可含复数、强相消和污染输入，不能以选行宽算术替代生产。默认不跑全仓pytest、旧184项审核、V13完整归因、A1/A2、carrier、全模式或全域向量比较。普通接口bug修复后只读有效产品继续，不重新做矩阵。输入hash核验不属于重跑旧资格。

ChatGPT只新增本报告；Codex先提交共享核心的窄opt-in及定向回归，再提交正式保存候选/条件覆盖和`response_v14.md`，更新原summary/run_index/test_summary与两级账。首屏给每列自身d、全部局部残差、成本、覆盖及否决/待全域状态，不以测试数或审核退出0替代科学进展。不改master、Hybrid、Task39para或母Task40。

## 8. 可直接交给Codex的摘要

```text
读取同分支review_report_v14.md。结果base=e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2。
接受V13局部归因，不改原action FAIL。本轮由诊断进入唯一候选保存试验，
不重建FE/两cell/全域owner，不积分、factor、carrier或模式扫描。

在project_internal_rhs_same_lu增加默认关闭的有界RHS校正：原LU初解，
每步用原actual K和原bi按review的binary64实虚乘积＋fsum计算完整残差，
同LU解delta并complex128更新，最多两次。最后真实返回z和原完整−J@z。
不由known、lambda、目标d或保存差向量驱动；不改S/R/T/J/native/积分，
不把longdouble/Decimal诊断残差输入生产。零RHS零GETRS；非有限拒绝，
残差为零/更新不变记录停滞，限次后不追加。旧默认与三次恢复上限保持。

先cells360/446×原两列，由实际核心调用验证；最多4初解+8校正GETRS，
不重复旧ri/伴随求解。保存每步，独立核全部内部行真残差和实际correction，
按原b_t/MPC/cell次序分别重放y/g/自身d。Di用最终同一z。
普通double残差下降不替代独立复核，两列自身d需可信改善；不改善即否决。

改善后同窗用旧23352/23493完整star及现存八代表键中身份完整的数据，
做跨材料/方向的同一候选验证，最多12独立key、不新建factor或矩阵。
缺原K/J/LU/RHS就列具体缺项，不借reference代替。局部/覆盖PASS不是全域PASS。

仅在覆盖成立后完善actual owner策略、真实target/reference/recovery接线，
计入保留原K的90,720,000,000 B派生增量及residual/GETRS成本。
旧435,653,172,000 B加K约526,373,172,000 B仍非RSS或准入。
全域两列验收的重建与窗口另需明确批准，本轮不解锁200q/FGMRES。

旧窗已结束。新21600/20400/1200秒保存候选包待用户一次明确批准；
先窄准备后登记T0，不刷新旧钟。原主机/cap/reserve/ABI/线程/swap0不变。
现有service/readers复用，不新建V14框架或硬编码attempt号，不全仓测试。
普通bug定向修复继续、有效数组不重算；提交response_v14和真实覆盖/成本，
保留负结果与UNKNOWN，仅推当前分支，不合并master或宣称最终目标通过。
```

## 固定证据与方法来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2/docs/task41extra_phi90_p50x50_g17x20/response_v13.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v13_saved_diagnostic_closeout_20261024.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2/docs/task41extra_phi90_p50x50_g17x20/outcomes/v13_closeout/evidence_index.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2/src/solvers/hcurl_assembly_time_condensation.py
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2/src/solvers/p6_cell_condensed_action.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/commit/af953ef38ba2f95a2e443e131dece20c17af8c1e
[N1]: https://docs.python.org/3/tutorial/floatingpoint.html
[N2]: https://www.netlib.org/lapack/complex16/zgetrs.f
[N3]: https://www.netlib.org/lapack/explore-html/d5/da4/group__gerfs.html

同LU残差校正属于迭代精化的常见形式；LAPACK把GETRS的回代与GERFS的精化区分。这里的最多两次、补偿残差及所有准入是本任务的显式候选规则，不宣称照搬某库默认次数，也不保证它必然成功。[N2] [N3]
