# Task41extra Review V18：固定保存z，只验证完整Jz的稳定求值

## 0. 裁决与范围

**接受V17两cell包、y9/g9与y15/g15分别重放和最终只读审核。批准一个有界的保存数据候选：在 `project_internal_rhs_same_lu` 的J乘法位置，显式opt-in地使用binary64实虚乘积＋`math.fsum`生成完整 `−Jz`；固定保存z及其全部求解状态，不新增积分、LU或GETRS，不改 `reduce_rhs` 的散射累加次序。先检验当前star，再同包检验两组已有合格保存star。该批准仅为实现及局部实验设计，新科学执行窗口另获用户一次明确批准；不是生产默认、全域验收或下游解锁。**

本轮消除的blocker：已有有符号证据指向固定J/z后的乘法求值，但还不知道一个实际complex128实现能否改善完整correction与candidate自身d、是否在旧star上退化。用现有操作数直接回答，不再从归因结果跳到28,000键重建。

| 冻结身份 | 值 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 审阅结果HEAD | `3d3cb9f07104ce3993b1269480081e5388df99c4`，远端回读与用户一致 |
| V17 producer / checker | `56ff5a603d4ba17c8ba6c45974777e1abcbca35e` / `17df17b39379001cf2bd368f05ed1da9118762ac` |
| V16结果base / 上份review | `6399beadd62d610100ba3e2b8d55ce7f0d48200a` / `06cd1789c717face827476ad70f24ae8efb6b0f1` |
| 日期 / 类别 | 2026-10-28，Asia/Singapore / 局部消元数值一致性、最小核心候选 |
| 不变物理 | 0.7 nm；50×50×140 nm域，居中17×20×120 nm Si及原基底、无缺口；方位90°、掠角1°、S；p6、10×200×14、64,120 modes |

已核对当前response、compact、原始checker、索引、source差异、生产RHS核心及P6 reducer；task.md与V17 review的完整本地副本分别匹配远端blob `5b669c109006fa91fdeebba2a81d97ba17b640b0`、`9bc923903438708b4d3bf5a6e4da4bc34aa81b10`。根/目录规则及未改任务约束沿用。ChatGPT只提交本review；未读取工作站NPY、未运行项目或工作站计算。[R1][R2][R3][R4][R5][C1][C2][C3]

## 1. V17接收结论及不能外推的部分

V17实际只建立cells7873/8014，2份candidate张量、2次LU、6次矩阵RHS GETRS和12次向量GETRS。110个NPY、75,253,856 B已由最终checker核验；两个保存输入上的y/g各自精确重现，后续checker没有重新求解。此重放资格继续有效，不为review编号重跑。[R1][R2][R3]

原全域action约5.7625744836e-11、1.2123684644e-10，对1e-11均FAIL；candidate恢复、200q、完整参考、FGMRES、A6及官方R/T/A未资格化。原几何主体在高度区间规则挤出；本案成功也不等于任意非可分三维通过。最终十进制2 TB含余量、完整必要冷流程48 h及网格/mode精度目标保持。

V17证明的是**这条行在相同J上，从初解到最终z的误差变化**可由状态变化和J乘法舍入变化闭合；不能将变化的闭合解释成终态全部误差来自J。80位Decimal是对存储binary64输入的高精度诊断，约1e-75的闭合余差不是生产精度或全域残差。

原始checker还保存了终态而不只是变化量。以下数值由其复数分量取模推导：[R3]

| active1622464终态量 | 列0 | 列1 |
|---|---:|---:|
| 原binary64行差的模 | 8.3142193272e-10 | 1.6747717066e-9 |
| 固定J/z在Decimal中计算的行差模 | 3.6430141768e-10 | 7.6674243792e-10 |
| 原模 / 上述诊断模 | 2.2822 | 2.1843 |

第二行仍含local/native与固定z误差；它不包含候选输出最终舍入及原scatter重新执行的影响。**不是候选实测、严格误差下界或最大可改善倍数，更不能据此预计全域会过门。**

两个cell的实际t逐元素为0，故本star的 `S@t`、`R@t`项确实为0；原有输出的scatter与最终相减新增舍入也为0。换成新correction后scatter是否仍为0必须重新量出，不能继承为定理。local/native项不随本候选改变，但其来源尚未分离。新star约0.004%的全域能量及其所属71%类别都是已知覆盖边界，不再重复统计。

## 2. 唯一候选：完整矩阵乘法位置的binary64补偿求和

目前生产函数完成原LU/至多2次校正后直接执行 `correction = -(J @ solved)`；P6 reducer消费该返回量，先放入全局RHS，再按cell、trace和MPC条目次序累加，Di消费同一个solved。这些职责必须保持。[C1][C2]

候选只把一次局部矩阵向量乘法中容易相消的求和改成更准确的组织；不求更好的z、不改矩阵、不把已知答案用于校正。提出稳定策略名 `binary64_real_imag_fsum`，实际接到现有策略字段；原BLAS分支仍为默认。此名称表示本review要求实现的候选，不表示已有可调用参数。

对于J的每一行，a、b为其实部和虚部，x、y为z实部和虚部，fl64表示实际binary64乘法：

```math
c_{r,R}=-\operatorname{fsum}_{j}\{\mathrm{fl}_{64}(a_{rj}x_j),-\mathrm{fl}_{64}(b_{rj}y_j)\},\qquad
c_{r,I}=-\operatorname{fsum}_{j}\{\mathrm{fl}_{64}(a_{rj}y_j),\mathrm{fl}_{64}(b_{rj}x_j)\}.
```

每个实/虚分量的一次fsum接收全部2n个已舍入乘积，顺序固定。不能先形成复数乘积、把每对相消提前舍入后再sum；不使用共轭。不把b_t或其他cell一起放入局部fsum，也不把全局scatter改成fsum。

输出是完整m维complex128 correction，当前为432行，绝不能只算q选中的一行。J与保存z只读，z位模式不变。可用每行两条长度2n的float64缓冲、m维输出；n=450、m=432时这些显式数组约21,312 B，fsum内部对象、临时索引和解释器费用另测，不宣称此数就是RSS。

fsum改善求和但不恢复已经舍入的乘积；Python文档也提示平台求和可能有末位双重舍入。因此不宣传它“精确/始终更准”，不同时加入FMA、TwoProduct、longdouble、Decimal生产计算或另一候选。若乘积误差主导，本次如实失败或不足，不升级精度绕门。[P1]

## 3. 真实核心接线与零新求解的验证方式

在 `src/solvers/hcurl_assembly_time_condensation.py` 将Jz收尾抽为一个小的共享helper，由 `project_internal_rhs_same_lu` 的默认/opt-in两条收尾分支实际调用。saved实验直接将已绑定J与z交给**同一个helper**；不要在checker里另写一套candidate算法，不增加“给正式solver塞入saved z跳过求解”的特殊后门。

P6 `_project_internal_rhs`及直接策略调用者要传递该opt-in并记录身份；`reduce_rhs`的cell循环、MPC拉回、b_t/port_rhs次数和原加法次序不改。只做必要参数传播，不预建新的全域scope或整套runner。普通默认、旧schema/缓存读取和V17的“返回量等于原BLAS”历史校验保留；新candidate结果使用新策略身份，不能修改旧checker预期以覆盖新结果。

科学saved运行新增GETRS/LU/积分/native FE调用均为0。小型fixture可以用明确标记的微型LU验证调用链：同一输入、同一refinement策略下，策略切换只改变correction、不改变返回z、残差步骤及GETRS次数；Di从同一z得到完全相同的项。若尚未接通真实core/P6调用者，只能报 `HELPER_ONLY_NOT_CONNECTED`，不能报生产接线完成。

非有限、形状或身份不匹配拒绝；零RHS仍按既有零求解路径返回。持有者不复制整套J，不因helper引入新的释放/借用问题。新策略需要更新操作身份和计时，但不使原J、z、native、S的旧数值证据失效。

## 4. 保存数据矩阵：先主star，再直接覆盖两旧star

首次核验实际消费的文件、shape、dtype、数组布局及producer/source/window/hash；J必须是完整432×450矩阵，或由同身份完整oriented张量和真实I/T索引准确提取。只有一行J时不能宣称完整Jz检验。高级索引临时副本据实计内存，不把882维连续切成450/432。

| 保存对象 | 输入状态与新增工作 | 边界 |
|---|---|---|
| V17 cells7873/8014、两列 | 固定初解z0与最终zf：8个完整Jz输入，普通/候选成对比较 | 初解仅解释变化；正式候选筛查以zf为准，不能挑较优z作为新解 |
| V14 cells360/446、两列 | 只用已通过且在V16绑定V15的最终z：4个完整输入 | 不重跑V14求解、Decimal残差资格或旧j0/j3审核 |
| V14 cells23352/23493、两列 | 同上4个完整输入 | 相同RHS的j0/j3只算一次，不复制为额外覆盖 |

合计最多6个已有cell、16个不同J/z输入；12个最终态完整correction对应三个star×两列。没有完整同身份操作数则列精确文件缺项，先完成其余可用部分，不积分/分解补覆盖。用户要求的另外两star已有资格，是旧输入/终态的资格，不是新Jz候选的资格。

普通完整J@z必须按冻结调用方式再现旧correction，C/F布局、strides、BLAS/线程记录；没有再现就先标 `BASELINE_UNBOUND`，查身份和布局，不能换成选行点积迁就结果。两侧重放使用真实helper返回的新correction、原S及trace、原b_t/Balpha/E；按生产顺序分别计算y/g/d。新y应与同一保存y一致，不能只让d相近。

三star中只有7873/8014被证实t=0；另外两star必须读取自己的t/S，不能套用零trace公式。原Balpha、MPC、物理行值、原动态/冻结分母不改。只完成这些行的完整incident和局部432行乘法，不将两cell共享的其他行冒称已具备全部全域贡献。

## 5. 独立验证：把产品舍入、求和与剩余local/native分开

不重新运行V17的110数组全套checker；旧hash及重放资格继承，新增审核只检查本次实际依赖、新输出和新公式。候选不以自身实现作oracle。每个完整correction提供绝对L2/max及逐分量误差，原局部门/分母报告保留；近零分量报绝对误差，不能用1e5级Jz的相对误差掩盖1e-10级joint差。

独立参考区分两种对象：①用Decimal.from_float读取**已经binary64舍入的四种实乘积**并高精度求和，检查fsum这条明确定义的算法；②从原存储J/z分量直接做80位Decimal乘加，衡量产品舍入＋求和的总差。关键分量用100位复核；若分辨力不足，明确INCONCLUSIVE，不把80位当无条件精确。允许在有限16个完整输出上核验全部432行，不保存逐乘积大表。

对主star，用固定J/z的诊断p*、实际p_hat以及未改变的native行分解：

```math
d=\underbrace{\sum_c q_c^H J_cu_{i,c}-b_{t,volume}}_{D_{local/native}}
 +\underbrace{\sum_c q_c^H J_c(z_c-u_{i,c})}_{D_{fixed\ solve}}
 +\underbrace{\sum_c q_c^H(\widehat p_c-J_cz_c)}_{D_{J\ evaluation}}
 +\epsilon_{scatter/subtraction}+\epsilon_{B/RHS}.
```

该式仅用于已经证实t=0的主star；各项按有符号复数计算。新候选只改变第三项及由新操作数导致的末级舍入；前两项保持。乘积舍入与fsum求和余差分别报告，不能把所有差异都叫“累加”。不按各项模长百分比相加，不能利用p*或保存d生成新答案。

候选的全部correction先持久化，随后重放，再由独立checker核验。实验期间J/z/输入摘要前后不变；返回z、Di/port及计数不变由小fixture及冻结身份核对。保存初末candidate状态和每列原/新y/g/d，避免后续报表错误需要重新生成结果。

## 6. 明确的筛选、否决与后续边界

| 结果 | 当前裁决 |
|---|---|
| baseline无法绑定、J/z或输入污染、符号/共轭/输出维度错误 | 工程或身份失败；定向修复重读，不给数值PASS |
| fsum不符合独立的已舍入乘积求和参照，或全correction精度出现无法解释的恶化 | 拒绝实现/候选，保留真实数组；不放宽原门 |
| Jz本身更接近独立参照，但主star最终两列自身d没有可信改善 | `CONTRACTION_IMPROVED_JOINT_INSUFFICIENT`，不进入全域；保留local/native余项 |
| 主star两列改善、旧star最终两列出现可分辨退化 | `LOCAL_MIXED_NOT_QUALIFIED`；不只挑主star宣布通过 |
| 主star两列改善，三star最终态均无可分辨退化，完整Jz独立验证正常 | `LOCAL_CANDIDATE_SUPPORTED_GLOBAL_NOT_RUN`；仅支持进一步生产/覆盖评估，不解锁全域 |

“可信改善/退化”以保存复数差及独立oracle的实测分辨区间判别，不另造一个更松的action门；无法分辨则INCONCLUSIVE。初解结果不参与择优，保持最终z。局部不存在独立于全域覆盖的“整场通过”：原全域action 1e-11、candidate恢复forward 1e-11/native residual 1e-10、最多3次恢复修正及2次RHS校正均不改。

全域余差广泛分布，三个star只提供有限跨输入/类别检查。即使本轮全PASS，也必须报告剩余D_local/native，并提出下一最小生产验收依据及成本；不得自动建立全域owner、200q、factor、完整参考或FGMRES。

如果候选只是减少J求值误差而local/native仍主导，精确缺项是：**同一cells7873/8014、同一known输入和原kernel/积分/actual坐标下的独立native rank-1局部贡献及原scatter顺序/舍入**，用于将存储张量差与native RHS制造/组装差分开。已有全局native切片不能唯一反推出各cell项。本轮只列缺项，不新增该积分或native作用；不泛称继续研究舍入，也不串联第二数值算法。

## 7. 成本、窗口和证据

V17所有旧失败及费用保留：成功producer worker126.412692 s是128.293210 s服务父段内部；最终checker17.098682 s是37.743761 s父段内部；tree/cgroup及UNKNOWN分别报告。原110 NPY不复制，不为入口、JSON或checker错误再生成科学数据。[R1][R2][R3][R4]

本轮需要的科学工作是16个已保存输入的矩阵向量乘法和有限独立审核，无GETRS。每个输入普通/候选各一次保存即可；为测量完整Jz成本，可在同进程同操作数下额外各重复至多2次，只记计时，不复制产品。统计加载/hash、Jz核心、scatter、独立参考及保存父子时间；Decimal计时不能混入生产Jz成本。

不以单行点积时间推算完整432行成本；不以BLAS毫秒对比Python启动费用；未来若按28,000cell估算额外J成本，只列带假设的派生情景。它可能用很少scratch换取明显额外时间，本轮未测前不承诺48h收益。J原库存不因求和方法改变，不新增90 GB K或全域缓存。

**新证据上限16 MiB，累计上限16 GiB及磁盘2 GiB底线不变；计划工作集≤4 GiB，并服从现场更紧约束。** 新输出16×432 complex128纯载荷仅110,592 B，独立参考、报告、hash及暂存另计；不得保存全部逐乘积表或重复矩阵。沿用既有task cap1,649,267,441,664 B、host reserve68,719,476,736 B、task reserve0、complex128/int32、MPI1/math1、task swap0、PSS默认不采样。不得借大cap扩大范围。

V17数值截止为2026-10-28T14:57:39.097621720Z（新加坡22:57:39），总截止15:17:39.097621720Z（23:17:39）。本审阅时间查询快照为10月28日22:20:49，彼时旧窗尚未截止；这不是启动余额，也不代表旧scope已允许新算法。**不把剩余V17额度静默改成candidate试验许可，不刷新旧T0。**

提案：新的saved-Jz候选6小时包，总21600 / 数值20400 / 收口1200秒，`PENDING_USER_APPROVAL`。一次明确批准涵盖主star、两旧star、必要独立审核和不改变数值语义的普通工程修复；不含全域/新积分。先窄实现、实际service命令与最小fixture冻结，再登记新T0；正式加载核验起计时。若用户明确批准复用尚未结束旧窗的剩余范围，必须追加scope授权并取原截止，不延长或改写旧窗；否则使用新批准实例。

## 8. 实施与交付：不再让包装错误掩盖数值进度

只补共享Jz核心、直接策略传递、已有saved入口和新增输出读取；不复制V18 runner/监督器或大范围重构。预先用微型矩形非Hermitian复矩阵测试符号、非共轭、强相消、零/非有限、只读输入；用正确z/错误correction反例证明真实返回量被消费。P6小型fixture覆盖原散射顺序、非零Di及零RHS，实际saved调用链覆盖新consumer＋旧producer＋新输出＋失败审核。昂贵内核可替身化，正在验证的路径/摘要/状态不能全mock。不全仓测试。

原V17 accepted checker、旧数组、旧source/window不改写；新helper/evaluation/checker各绑新consumer。文件、shape/dtype artifact摘要、旧raw-state摘要各用已合格口径。candidate完成即落盘，之后checker/字段故障只能重读。数值否决生成完整报告不等于service崩溃；`audit_completed`、`candidate_supported`、`global_qualified`、`official_result`独立字段。

推荐两笔执行提交：①核心及窄调用链/定向测试；②response_v18、紧凑新输出/原文件引用/计数和成本、summary/run_index/test_summary及两级账。全部只写本分支，不amend、不强推、不合并master。response首先回答两列自身d和另外两star是否改善、完整Jz与独立参照差多少、local/native剩余是否仍主导、实际额外时间和最小下一缺项；测试数不是主结果。

## 9. 给Codex的接续文本

```text
继续Task41extra，读取review_report_v18.md；结果base=3d3cb9f07104ce3993b1269480081e5388df99c4。
接受V17两cell重放与110数组审核，不重算producer、旧归因或全域分布。
唯一候选是完整−Jz的binary64实虚乘积＋fsum；z/矩阵/原输入全部固定。

将Jz收尾抽为生产共享helper，由project_internal_rhs_same_lu实际调用，旧BLAS默认不变。
saved实验调用同一helper消费保存z，不调用LU，不给solver塞saved-z特殊后门。
完整432行求值；实部fsum(ar*zr,−ai*zi)，虚部fsum(ar*zi,ai*zr)，最后整体取负。
乘积binary64、输出complex128；不把复数逐项提前相减，不用长精度生产，不改K残差校正。
P6传策略且使用实际返回correction；b_t/MPC/cell/trace累加次序不变，Di仍用同一z。

先核完整J和原I/T、z初末状态、shape/strides/hash与原候选身份。
主star7873/8014两列初始/最终共8输入；旧360/446和23352/23493只用最终态共8输入。
共16完整Jz输入、0新积分/LU/GETRS/native。不能按j0/j3重复同一RHS或重新补八键。
普通路径需先绑定旧correction；新返回量先保存，再独立重放各star的y/g/自身d。
不只比candidate/reference gap，不挑z0替代zf，不用保存差向量补答案。

独立审核区分已舍入乘积求和与原存储J/z的Decimal乘加，检验全correction而非仅q行。
主star重新列local/native、固定z误差、J求值、scatter/最后相减各带符号项。
新scatter不保证仍为0。旧star各读真实t/S，不套用主star的t=0公式。
主两列不改善则保存否决；Jz更准而joint不足单列；旧star退化不能隐藏。
只有有限覆盖支持，不管结果如何均不解锁全域owner、200q、恢复或FGMRES。

同cell独立native rank-1/scatter仍缺时列精确输入、输出与用途，本包不新增取证。
普通接口bug定向修复并重读产品，不重跑已接受数据；只做核心/P6/真实saved路由相关fixture。
不复制V18框架、不全仓pytest。新输出≤16MiB，原累计16GiB、cap/reserve/ABI/线程/swap0不变。

V17原数值/总截止=2026-10-28T14:57:39.097621720Z / 15:17:39.097621720Z。
不复用历史余额、不自动扩大旧scope；提议新21600/20400/1200秒候选窗，待用户一次明确批准。
先完成窄准备并冻结；获准后连做主star、旧star和独立审核，不逐阶段停审。
提交response_v18、实际输出/哈希/计数/成本，保留负结果与UNKNOWN；只推本分支，不合并master。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/3d3cb9f07104ce3993b1269480081e5388df99c4/docs/task41extra_phi90_p50x50_g17x20/response_v17.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/3d3cb9f07104ce3993b1269480081e5388df99c4/docs/task41extra_phi90_p50x50_g17x20/outcomes/v17_closeout/v17_two_cell_compact.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/3d3cb9f07104ce3993b1269480081e5388df99c4/docs/task41extra_phi90_p50x50_g17x20/outcomes/v17_closeout/attempt07_checker_result.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/3d3cb9f07104ce3993b1269480081e5388df99c4/docs/task41extra_phi90_p50x50_g17x20/outcomes/v17_closeout/evidence_index.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/3d3cb9f07104ce3993b1269480081e5388df99c4/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/3d3cb9f07104ce3993b1269480081e5388df99c4/src/solvers/hcurl_assembly_time_condensation.py
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/3d3cb9f07104ce3993b1269480081e5388df99c4/src/solvers/p6_cell_condensed_action.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/commit/17df17b39379001cf2bd368f05ed1da9118762ac
[P1]: https://docs.python.org/3.11/library/math.html#math.fsum
