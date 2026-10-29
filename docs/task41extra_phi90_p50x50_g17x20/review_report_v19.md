# Task41extra Review V19：只补独立 native rank-1 与原组装顺序

## 0. 裁决、目标与固定身份

**接收 V18 的实现一致性、保存重放及 `LOCAL_MIXED_NOT_QUALIFIED` 结论。fsum Jz 不提升为默认，不再试另一种求和、增加 RHS 校正或重建全域。本轮唯一包：复用 cells7873/8014 的完整候选数据，在同一原 known 输入上补独立 native rank-1 的 curl、mass 单元向量及原 scatter/MPC/分量合并过程；先绑定原 native RHS，再拆开 local/native 差。技术范围在本报告内限定，新执行窗口仍需用户一次明确批准。**

rank-1 指固定输入后、只含一个测试函数的线性形式，直接产生单元向量；不是“矩阵秩为1”或低秩近似。它提供独立于已保存局部矩阵乘法的计算路径。本包解决的 blocker 是：已有局部矩阵、解与最终投影，却没有原 native 这一侧的单元级来源，无法区分局部算子求值差和装配求值差。

| 项目 | 固定身份 / 边界 |
|---|---|
| repository / branch | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 结果 base | `bd943b6f15163d2a3dfc790d2feeffd336c69c57`；开始回读与用户一致 |
| V18科学 source | `ff22c0a78099e7e48e0c11127ce01e06ae1ac8cf`；到结果HEAD只有文档/证据提交 |
| 上份 review | `042538b7ea8f0b0cae7ee59684d6badaefaa36e1` / `review_report_v18.md` |
| 日期 / 本轮角色 | 2026-10-29，Asia/Singapore；ChatGPT审阅和任务，Codex实现/获准取证/response_v19 |
| 唯一科学对象 | active `1622464` → original full-storage `5218672`；cells `[7873,8014]`；原known两列 |
| 原物理 | 0.7 nm，50×50×140 nm域、居中17×20×120 nm Si及原基底，无缺口；方位90°、掠角1°、S；p6、10×200×14、64,120 modes |

根/目录规则、task及未改数学门沿用。此次读取了远端response、compact、index、summary、相关源码及提交差异；12.87 MB完整checker原件与NPY只在工作站ignored目录，本Chat未重新读取或执行它们，远端审核结果按绑定记录审阅。不将本报告的代数推导称为工作站实测。[R1][R2][R3][R4]

## 1. V18接收结论：运算改善与方程一致性必须分开

| 项目 | 接受的事实 / 不能外推的结论 |
|---|---|
| 16个完整Jz输入 | 原BLAS基线已重放，候选完整432行符合规定的binary64乘积＋fsum语义；新增积分/LU/GETRS/native FE作用均0 |
| final 12输入 | 对原存储J/z的80位诊断参考，聚合L2 `2.546673384084861e-9 → 2.0057324742353132e-10`；不能推出每个分量或joint d都改善 |
| 局部退化 | cells23352/23493列0的d模 `8.745466676409231e-11 → 1.0008161688044719e-10`，约14.44%；j0/j3是同一RHS，不重复计数 |
| 当前候选 | `LOCAL_MIXED_NOT_QUALIFIED`保持。helper可以保留为显式研究路径，不默认为生产策略；数值实现正确不等于本场修复合格 |
| 全域 | 原两列约 `5.7625744836e-11`、`1.2123684644e-10` 对 `1e-11` 仍FAIL；没有新全域action、candidate恢复、200q、FGMRES或物理场 |

更准确的局部乘法可能减弱另一项误差的偶然抵消；这是可能机制，不是已经证明退化必然来自抵消，也不是保留较不准确乘法就获得物理正确性的理由。本轮不因为局部退化去拟合混合系数、逐行择优或恢复旧误差。[R1][R2]

主star固定z后的剩余项仍有非零local/native和solve贡献。V18重放的scatter与最终相减余项为0，只约束这次RHS reducer的操作数；不约束生成旧native RHS时的原始装配。[R2]

成本继承：service父段62.540324 s，worker5.924485 s、checker55.059161 s为内部阶段；16次fsum1.291472651 s、BLAS0.003146933 s，约410.4倍仅适用于本小批，不预测全域。tree worker/checker峰326,643,712/263,819,264 B与cgroup207,638,528 B分列；task swap0。窗口累计2887.994186 s含准备/失败/等待/收口，不再加service；发布后费用及无独立收据失败成本UNKNOWN保留。[R1][R3]

## 2. 源码依据：这次必须取得哪条独立路径

`project_internal_rhs_same_lu` 的Jz新helper按规定实现实虚binary64乘积与fsum，旧BLAS默认保留。只修改它不能回答原native RHS从何而来，不继续变更此核心或 `P6CellCondensedAction.reduce_rhs` 的循环、MPC和Di语义。[C1]

仓库的 `FullspaceMpcFormAction` 通过 `ufl.action(bilinear_form, coefficient)` 建立rank-1形式；默认分支调用 `fem.pack_coefficients` 和 `fem.assemble_vector`。输入先按原MPC homogenize/backsubstitution，输出装配后再做带共轭系数的限制转置、slave处理及ghost操作。它也支持显式local_kernel分支，故**实际donor的backend/audit必须先核对，不能仅从类名推断其当时使用了哪个分支**。[C2]

`FullspaceSplitVolumeAction.apply` 分别完成curl与material_mass作用，然后 `curl_result.axpy(1, mass_result)`；合并前，两分量已经分别完成各自装配/MPC。combined bilinear form用于局部凝聚，却不代表native先把curl/mass单元项相加再scatter。[C3]

原known/native RHS见证在worker内将 `volume_action.apply(field_vec)` 返回的借用Vec复制为volume RHS，之后才加入Bα。应绑定真正制造该RHS的旧donor manifest/source/kernel/ABI，而不是把V15或V18消费者SHA冒作原native producer。[C4]

**关键取证要求：保持原分量和原阶段顺序。** 不用已保存J乘known、candidate Gram evaluator或新编写的矩阵乘法当“native”。不把rank-2核的coefficients=NULL调用接口套到rank-1核；rank-1必须传原始常量和实际packed coefficient。不得把新两cell子网格的方向/编号当作旧网格的方向/编号。

## 3. P0最小准备：冻结原生取证manifest，不建立全域owner

先读取V17/V18索引、已接受的V16 metadata以及原donor身份。固定下列内容后再启动数值：

- 原known两列的文件/数组hash、shape/dtype、full-storage/active编号、所需882项切片；使用known，而不是z_final、j0/j3或重造解析输入。旧z/correction只用于已有solve项，不作为新native系数。
- 两cell有序actual坐标及hash、material/tag、真实I/T、permutation、E与完整incident覆盖。复用已有metadata；不重做全域分组或incident搜索。当前目标行的两个贡献为+1且无非平凡MPC，但必须由记录核实，不在代码里替所有行假定如此。
- 原native component backend、UFL/form/kernel签名、每个default/tag integral ID及执行次序、积分点/权重或其身份、常量、系数packing/变换规则、C/JIT/编译选项和原ABI。curl与mass各用原规则，不凭端口degree推定体积积分。
- 原native体积RHS目标行及两cell的全部内部行；完整RHS与Bα另列，保留 `b_full−b_volume−Bα`，不能预设为0再替换原数据。

只增加一个参数化的selected-native证据入口或回调，复用现有selected service、scope和持久化工具；不要复制新监督框架、版本分支大表或独立求解器。普通算法默认不改。旧producer source/window/hash不变；新取证消费者绑定新source/window。

若原生接口确需fresh mesh/space/form，允许一次必要轻量准备以恢复相同原mesh身份；禁止建立28,000-key数值缓存、condensed owner或surface/carrier。优先仅pack选中cells；若原ABI只能全表pack，先列实际字节与生命周期，最多一个组件/一个输入的临时表存活，记录其真实开销，不积分其他cell。

先做一个微型调用链回归，覆盖旧donor＋新窗口、两cell/两列/分量限制、真实loader、逐项保存及只读checker；只替换昂贵数值核，不mock全部路径/字段/摘要。编译前即可拒绝错误坐标顺序、坏hash、重复MPC、未知积分范围和非法扩展。无全仓pytest或环境重装。

## 4. 唯一新增数值：选定cell的原rank-1贡献

在已核实的默认split-native路径下，逻辑工作为 **2 cells × 2 known列 × 2分量 = 8份完整882行单元输出**。实际UFCx调用数为“两列 × 两cell各自合法curl/mass kernel数量之和”，可能有多个default/tag核；P0将准确清单冻结并逐次计数，不能为凑8次删去实际核。若donor实际backend不同，先把原backend及等价的最小组件清单写明；不得静默切换来追求吻合。

每个cell/列/组件保存：实际packed coefficient及offset/方向语义、常量引用、raw kernel输出、原native测试侧方向变换后输出、kernel及cell次序、目标原行与内部行索引。rank-1输入系数变换和输出测试变换各只执行原规定次数；不可套用rank-2的双边变换。

**本轮新增rank-2矩阵、candidate张量、LU、GETRS、伴随、恢复与全域native作用均为0。** 已保存K/G/J/L、S/R/T、z、correction及MPC映射直接读取；没有完整同身份输入就给精确缺项，不额外建立其他cell。不运行carrier、模式扫描、A1/A2或旧资格测试。

复用/窄抽取冻结DOLFINx原生装配的局部kernel调用与方向处理；保留原integration entity列表中的相对顺序和累加规则。仅把不可能贡献于目标行/相关内部行的积分实体排除，不改tag或重编一个不同积分定义冒充原路径。原核若不能受此限制调用，报告具体接口缺项；不回退到全域assemble_vector。

每份输出及其摘要立即原子保存并用独立loader试读。已完成产品作为接续断点：后续checker、JSON或授权字段错误只读重开，不能因改attempt号重新积分。新核取证标 `RECONSTRUCTED_SELECTED_NATIVE_ACTION`，不是旧run当时保存的逐cell日志。

## 5. 首道绑定：重建原native输出，不重新算散射场

对每列，保持curl的所有合法单元/核贡献先在其原输出空间装配，完成原约束/ghost语义；mass亦同；最后按原split `axpy` 合并。不能改成“每cell先curl+mass，再两cell相加”。使用实际原kernel/积分列表顺序，不假定它等于排序cell ID；即使目标行恰好无非平凡MPC，也保存这一证据。

目标索引是原行5218672，进入active域时才是1622464。核对所有可能经slave限制转置贡献到该行的原行均被metadata覆盖；原slaves的identity项按组件所有权处理一次。不得用active行号直接索引full-storage native RHS。

将新重放的目标行volume值与旧donor保存值分别比较实/虚与bitwise结果，并验证两cell全部450内部行的volume RHS（内部行只属于该cell，先验证其无额外MPC或facet贡献）。这里只对完整支持的目标行和内部行宣称绑定，不把其余local trace向量说成已有全局贡献。

预期同身份、同顺序精确重放。不能绑定时标 `NATIVE_REPLAY_UNBOUND`，保留每个分量和差；不能把行差除以全域分母后通过就称重放相同。检查旧ABI/kernel/packing/方向/积分顺序、原输出借用状态及相加次序；普通接线bug定向修复重读。若原kernel/JIT字节缺失，只能如实标重新编译及其证据边界，不先声称历史操作逐位复现。

绑定成功证明这两组native产品在所覆盖行上被复现，不证明native自身是精确算术真值或全域正确，也不重新验收已有y/g、旧checker或三个star候选。

## 6. 有判别力的分解：把local/native拆成三段

对当前主star两列，保存的局部trace均为0；取证时核对此事实。设q_c为目标行的真实E列，a_c是由旧候选存储矩阵和原known得到的局部作用，n_{c,k}为本轮取到的各native分量/积分核输出（已完成测试侧方向变换）：

```math
a_c=J_cu_{i,c}+L_ct_c,\qquad
A=\sum_c q_c^Ha_c,\qquad
Q=\sum_{c,k}q_c^Hn_{c,k}.
```

令b_replay为按原native计算顺序得到的binary64目标行，b_saved为原volume RHS，使用以下有符号恒等式：

```math
D_{\mathrm{local/native}}=A-b_{\mathrm{saved}}
=\underbrace{(A-Q)}_{D_{\mathrm{local/rank1}}}
+\underbrace{(Q-b_{\mathrm{replay}})}_{D_{\mathrm{native\ assembly}}}
+\underbrace{(b_{\mathrm{replay}}-b_{\mathrm{saved}})}_{D_{\mathrm{binding}}}.
```

这里A、Q的“精确存储值语义”用既有80位Decimal作独立诊断，关键标量以100位复核分辨力；不称绝对精确，不把高精度值输入生产算法。逐cell、逐组件记录实际binary64中间值，以带符号误差账将 `Q−b_replay` 分解为核输出合并、cell scatter、MPC/ghost（若有）和最终curl/mass合并。不能只比较各项norm，更不能把范数占比相加作原因百分比。

`A−Q` 仍包含候选存储张量/其作用与原rank-1求值之间的差，**不能据其非零单独判定native错误或矩阵错误**。同样不能把“V18 reducer scatter误差为0”沿用给新的native装配段。算式应把实际新数组与原有两列local/native复值绑定，不能直接把总差命名为一个新分项。

附加必要而便宜的内部核对：用原K/G/known计算内部存储矩阵作用，与同一新rank-1内部输出及旧b_i比较。无需GETRS。这样可以判断trace侧差与RHS制造侧差是否同时存在；原最终z、solve项、Jz普通/候选项保持旧数据身份，不重复其求解或全套归因。

本轮必须同时报告两列A−Q、Q−b_replay、binding、闭合剩余，以及curl/mass和每cell的有符号贡献。补偿/较宽求和若用来对照顺序，只是固定新原始输出上的诊断，不另立数值候选。

## 7. 明确出口，不再以“审核完成”代替原因

| 实际结果 | 本轮结论与唯一下一项所需证据 |
|---|---|
| 无法绑定原native输出或coefficients | `NATIVE_REPLAY_UNBOUND`；定位具体source/kernel/packing/映射/顺序缺项，不能将新值用于解释旧全域FAIL |
| 已绑定，native装配/分量合并项主导且两列方向一致 | 将问题指向 `FullspaceMpcFormAction.apply` 或 `FullspaceSplitVolumeAction.apply` 的具体操作；给固定操作数上的量化依据，但本包不修改它、不换原RHS |
| 已绑定，local/rank-1差主导 | 确认问题在组装之前。指向 `actual_qmetric_blocked_gram` 与原rank-1核的局部求值差；不能仅据此确定哪方更准 |
| local/rank-1差仍无法进一步区分 | 精确下一缺项是同一两cell、同一known的原始FFCx rank-2作用/必要积分分量与rank-1对照（不含LU），或已定位的rank-1关键积分累加中间量；先给其数量和用途，本包不自动新增它 |
| 所取来源差较小，原fixed-z项仍重要 | 保留各项复数方向，明确仅修native不足；不追加第三次校正或再试Jz算法 |

这是一项机制取证，不是修复验收。局部绑定或分解闭合不解锁全域owner、恢复、200q、准确因子、完整参考、FGMRES或target。不得修改原known、矩阵、积分、生产精度、原分母/门限；不按行择优，不拟合系数，不用保存差向量补答案。

独立checker只读取新raw向量、操作次序和旧绑定数据，重算原行/内部行输出及上述三段，不再次调用native核、Jz候选、LU或GETRS。候选不合格、取证完成、数据完整、重放绑定和原全域FAIL分别表达。若诊断分辨率不足，列明确项和可分辨尺度，不把1e-75等高精度闭合当作生产精度。

## 8. 授权、资源、成本和防止再重复

V18固定T0为2026-10-29T00:50:15Z；数值/总截止为2026-10-29T06:30:15Z / 06:50:15Z，即新加坡10月29日14:30:15 / 14:50:15。其scope只允许saved-Jz候选。无论接收本review时是否还有墙钟余额，不能用该余额许可本轮新增native核，也不能复活旧T0。

**建议新6小时有限取证包：21600秒总窗、20400秒数值、1200秒收口，PENDING_USER_APPROVAL。** 一次批准仅覆盖两cell/原两列的必要native分量取证、原scatter重放、保存分解及独立checker，不包括新rank-2、LU、GETRS或全域。先完成窄接线、fixture、实际命令核验和源码冻结，再登记新T0；正式准备/JIT/读取进入新窗，前期工程成本另列。持续检查真实余额、资源和清场，不复制旧序61快照。

原主机 `fenics-ws:/home/fenics/Projects/laptop_share`、Codex项目/对话、task cap1,649,267,441,664 B、host reserve68,719,476,736 B、task reserve0、complex128/int32、MPI1/math1、任务swap0和磁盘底线2 GiB不变。计划工作集按必要mesh/form/packing实际盘点，预留不超过既有两cell诊断的16 GiB计划预算；该计划不是实测保证，也不是升高task cap。

8份882行complex128输出的纯载荷仅112,896 B；若保存raw和变换后两套则225,792 B，coefficients/映射/计时另计。**新证据上限16 MiB，累计仍≤16 GiB**；编译缓存、临时表、实际文件页另记资源，新的必要JIT产物也计实成本，不靠不归档藏时间/空间。引用旧矩阵和checker，不复制75 MB旧包或12.87 MB旧审核JSON。

新native kernel成本未测，不能把V17的126秒当本包时间保证。按P0 kernel/JIT库存登记有限工作估计与终止预留；准入不能靠删除原积分、减少分量、提高cap或修改截止。每个cell/组件/列完成即落盘并可重开。普通路径、摘要、输出或checker bug在同一范围定向修复继续，不为后端审核重复已有native取证；失败成本保留，父子不重复加，未知项不填0。

## 9. 提交、验收和Codex接续文本

本轮只安排三个相关回归：旧donor/新consumer和kernel参数的真实路由；非Hermitian复数/MPC/分量先散射再相加的顺序反例；已保存单元输出在checker失败后重开且不再调核。微型fixture与科学调用数分列。不扩大全仓测试、不复制V19框架、不重做已通过审核、carrier、模式扫描、A1/A2或全域分布。

主控集中冻结、commit/push本分支，执行者实现和获准运行。推荐两笔提交：必要提取接口与定向测试；实际证据、`response_v19.md`及现有summary/run_index/test_summary/两级账。原负结果和混合候选保留，不改master，不合并。

```text
继续Task41extra，读取review_report_v19.md；结果base=bd943b6f15163d2a3dfc790d2feeffd336c69c57。
接受V18 LOCAL_MIXED_NOT_QUALIFIED，不推广fsum，不再试求和/精化候选。
唯一包是cells7873/8014、原known两列的独立native rank-1＋原scatter来源。
新6h有限取证窗待用户一次明确批准；V18余额不扩展scope、不刷新旧T0。

复用V17/V18矩阵、z、correction、maps和V16完整incident；active1622464/original5218672。
先冻结真正制造native RHS的donor backend/kernel/JIT/积分/coeff packing/方向/ABI，
不是把消费者SHA当producer。用原known，不用final z或重造输入。

复用原FullspaceMpcFormAction/FullspaceSplitVolumeAction的实际rank-1核及装配规则；
核实是否有local_kernel override。禁止用J@known或Gram张量乘法冒充native。
保留curl和mass独立装配、各自MPC/ghost后再axpy的原次序，
不能先每cell合并再散射，不假设核/单元顺序是cell排序。

只对两个cell产生完整rank-1向量：通常2cell×2列×2分量=8份，
多default/tag核按原清单计数。无新rank-2、LU、GETRS、native全域作用。
必要mesh/space/form仅作接口准备，不建数值owner、surface或carrier。
每个原核输出及方向变换后向量、packed系数和scatter中间值即时保存。

先分别绑定目标原行及所有有完整支持的内部行到保存native volume RHS；
Balpha/full RHS另列，不重复MPC。不能绑定就保留UNBOUND，不用新分母放行。
绑定后用原存储矩阵作用A、捕获分量贡献精确和Q、新原序b_replay、旧b_saved，
拆解Dlocal/native=(A−Q)+(Q−b_replay)+(b_replay−b_saved)。
独立Decimal只诊断，保留两列/每cell/每分量有符号项及闭合余差。
候选/原native谁更准不能仅据差非零判断；固定z项仍按旧证据保持。

若local/rank1仍分不开，列同cell原FFCx rank-2作用或关键rank-1积分中间量的
精确缺项和用途，本包不自动生成它。局部完成不解锁全域、200q或FGMRES。
checker只读新产品，无新核/solve；普通工程bug定向修复，不重复完成取证。

新窗21600/20400/1200秒；原主机/cap/reserve/ABI/线程/swap0不变；
新增证据≤16MiB且累计≤16GiB。只做真实路由/分量次序/接续相关小测试，
不全仓测试、不复制新框架。response_v19先给native绑定、三段原因和具体函数，
再列测试。保留负结果及UNKNOWN，只推当前分支，不合并master或预报最终通过。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/docs/task41extra_phi90_p50x50_g17x20/response_v18.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/docs/task41extra_phi90_p50x50_g17x20/outcomes/v18_closeout/v18_saved_jz_compact.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/docs/task41extra_phi90_p50x50_g17x20/outcomes/v18_closeout/evidence_index.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/docs/task41extra_phi90_p50x50_g17x20/review_report_v18.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/src/solvers/hcurl_assembly_time_condensation.py
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/src/solvers/fullspace_mpc_action.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/src/solvers/fullspace_physical_action.py
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/bd943b6f15163d2a3dfc790d2feeffd336c69c57/src/runners/task40_v10_worker.py
