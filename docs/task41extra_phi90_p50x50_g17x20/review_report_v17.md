# Task41extra Review V17：只补主导签名中的7873/8014完整star

## 0. 裁决、目标及固定身份

**接受V16的保存全域分布、互斥分组、两旧star终态绑定及新行metadata。技术上批准仅补cells7873/8014这一完整star的缺失candidate数值块和原RHS终态链；新固定窗口须用户一次明确批准。本轮不是第二数值候选，不修改生产算法，不重建28,000键，也不重复已完成的分布或旧star审核。**

本轮消除的blocker：此前有精确重放能力的旧star属于低总能量类别；当前主导签名中的机制尚无局部数值包。用两个单元分别重现保存的y15/g15，再区分内部求解、R/S形成、local/native及求值次序，才能给出可证伪的最小生产修复依据。单行重放不证明整个签名，更不证明全域门通过。

| 项目 | 冻结身份 |
|---|---|
| repository / branch | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 审阅结果base | `6399beadd62d610100ba3e2b8d55ce7f0d48200a`；开始回读与用户一致 |
| V16最终分析source | `086c884121575c8a9662cd0f500a5287a36a79b8`；Stage A source另保留 |
| 原科学source / run | `3b8e7f5327ce1905deae658bd0bbb0fa94dba5ad` / `20261026T081134.584306Z` |
| 上份review | `3205450c390d86e574187b833593de2bffe1ff76` / `review_report_v16.md` |
| 当前日期 / 类别 | 2026-10-28，Asia/Singapore / 局部消元一致性、有限补证 |
| 原物理与数值身份 | 0.7 nm；50×50×140 nm域，居中17×20×120 nm Si及原基底，无缺口；方位90°、掠角1°、S；p6、10×200×14、64,120 modes |

根/目录规则、task及未改补充约束继续有效。本审阅核对固定提交下的response、compact、A/B结果的关键字段、分组、metadata、checker、索引、尝试记录与相关源码；V16源码差异没有改变本轮所用生产RHS算法。大NPY仍在工作站，本Chat未读取它们、未执行项目测试。这里的算术推导不冒充新实测。[R1] [R2] [R3] [R4] [R5] [R6] [R7] [R8] [C1] [C2] [C3]

## 1. V16接收结果，以及两项不能遗漏的解释

原全域两列仍为约5.7625744836e-11、1.2123684644e-10，限值1e-11。恢复、200q、完整参考、FGMRES、原始A6/物理场及最终精度均未资格化。y在两已知输入上逐元素相同，只说明这次输出变化位于g侧；不证明S或native已经正确。[R1][R2]

V16已完成的三个产品直接继承：全域分布及57个互斥签名；旧87567/4766937的y/g分别绑定V15；新1622464→5218672的完整incident metadata。不得为新review编号重新运行它们。

**主导组不是少数异常行。** group1有3,646,632/5,688,000＝64.111%的trace行，能量占71.0718%/71.1085%；每行均方误差约为全域均值的1.109倍（由保存数据推导）。它值得优先补机制证据，但不能直接断言tag1或perm0实现错误。即使假设整个group1误差完全归零且其余不变，全域相对差仍约3.10e-11/6.52e-11，仍不过门。此反事实仅说明覆盖边界，不是允许改写差向量。[R3]

**新探针在校正后反而变差。** 从保存复数d9/d15直接取模，active1622464两列分别约扩大1.790/1.841倍；这与全域改善4.6倍并不矛盾。下一步要解释同一行从初解到终态的带符号变化，而不是先假定再增加精化就有效。[R6]

已知9次service父段合计511.6682869841 s；最后父/子段28.9388948972/21.6609200719 s嵌套不相加。三次preworker计时/峰值UNKNOWN保留；tree/cgroup最大值来自不同attempt，不作同一时点归因。提交前6441.524033062 s是窗口账快照，包含等待、修复等，不再加service。元数据确实生成两次，后续只读复用；不能删除第一次失败成本。[R2][R7]

## 2. 唯一对象与已有数据的复用

对象仅为active1622464、original5218672、cells `[7873,8014]`，按原生产cell顺序；两cell tag1/perm0，目标行各一项+1投影，无非平凡MPC。不得沿用旧360/446或旧original编号。

metadata文件：`outcomes/v16_closeout/max_row_probe_metadata.json`，SHA256 `35720a498334c463f660f9179315eb20d5dbed5d6111fcf7201f7de0c9344665`。

| cell | 坐标范围，仅作阅读标注 | actual-coordinate SHA256 |
|---|---|---|
| 7873 | x33.5–39、y13.75–14、z40–50 | `de118e5efd5a260cd4f362a9acb5c9444531371d7bbc7da3d9f9b8a4eecf5378` |
| 8014 | x33.5–39、y13.75–14、z50–60 | `ff063f2c63bd6c7e3255827d9be399920bdaf1a5c6e9b2780c27784730f749ab` |

**按metadata的有序 `coordinates/coordinate_hex` 读取，不能用已排序的 `actual_keys` 集合重造顶点顺序。** 两者在保存文件中顺序不同。local_position、local_trace_position也由真实I/T分区和E核对，不把882行连续切成450/432。[R5]

复用V15四列y/g、V9旧y/g、原known/native/full-volume RHS、Bα、maps、V16 metadata和旧evaluator/kernel资格。只校验本次消费的文件，不重跑全套accepted checker、分组、metadata全域扫描、两旧star、A1/A2或模式验收。原carrier只作为身份来源；取Bα用已有稀疏数组/对应两个B帧，不遍历carrier。

先查精确库存；若已有完整同数学身份局部包则读取。确缺时只允许本报告列明的两个candidate单元。原进程已退出，不假称旧LU存活；新块统一标 `RECONSTRUCTED_SELECTED_CELL`，分别记录旧producer、此次重建source/窗口/环境及数组hash，不重署名旧V15。没有原局部hash，只能通过元数据和输出重放建立绑定，不能声称是旧内存逐位拷贝。

## 3. P0：窄接线一次完成，正式窗口内先产出数值包

复用既有selected-cell和saved service/loader；将选行、cell列表、metadata及V15列布局以严格manifest传递，不复制V17求解器、监督器或数千行checker。旧helper的固定V11/V14入口保持可读，新scope不得误用旧行、旧窗口或旧候选未校正状态。

一次小型真实调用链回归覆盖：新有效consumer窗口＋旧冻结metadata/donor→仅两个cell构建回调→即时保存→saved checker；只替换昂贵kernel，不能把新的身份、路径、摘要、复数解码、状态及输出名都mock。坏hash/错误coverage拒绝，已保存单元在后续失败后可重开，禁止到达global owner/surface/carrier/q回调。测试限本次直接修改，不全仓pytest。

执行前冻结源码、实际命令、expected-file清单和预算。新scope显式允许最多2个candidate张量/2次LU及本报告回代；不继续标成纯saved-only。metadata来自旧窗口，不要求旧窗口现在有效；运行权限来自新批准窗口。普通接口bug定向修复后续作；不要每个字段错误都重新取矩阵或要求再次review。

## 4. 最少数值构建与调用账

复用同一冻结 `mesh_actual_exact + actual_qmetric_blocked_gram` evaluator、积分/C/kernel、材料、方向和原strict LU。若接口需要fresh mesh/space/form，允许一次必要的轻量准备并核对这两个cell；不重扫incident集合，不构造全域condensed owner或surface。优先传入已有metadata，而不是从高层流程进入。

每个cell只生成一次raw及oriented张量，调用现有 `condense_selected_volume_tensor`，从同一个oriented张量获得K/G/J/L及同一LU/R/T/S；不能为获取LU再调用第二遍分解。保留原strict局部检查，不把T反推的K/J当作原矩阵。[C1]

| 正常缺块重建的上限/账目 | 数量与含义 |
|---|---|
| actual candidate evaluator / LU factorization | 2个键 / 2次；不加FFCx reference、不重做八键prefix |
| 原strict稳定性检查 | 每cell 1次GETRS、450个RHS列，共2次；这是原检查，不移除 |
| R及T构建 | 每cell各1次、各432个RHS列，共4次GETRS；S为原 `L+J@R` |
| 原两列内部RHS | 2cell×2列＝4个唯一RHS；最多4次初解＋8次校正＝12次GETRS |
| 新诊断伴随/残差RHS/恢复求解 | 0；使用第6节的T中已有伴随信息，不重复旧j0/j3求解 |
| 正常完整调用合计 | 最多18次GETRS调用，矩阵RHS与向量RHS分列；若全用满，为2640个RHS列当量，不可只报12次而隐藏构建求解 |

已有局部包可减少上述工作，不为凑计数重算。strict失败则保全失败并停止该数值路径，不换主元、损耗、精度或门。所有LU复用原资格化ABI/MPI1/math1；saved pivot传GETRS前按既有安全规则复制为可写int32，旧文件只读。

对每个原b_i，直接调用生产 `project_internal_rhs_same_lu`，冻结 `refinement_max_steps=2`、binary64乘积＋fsum残差、complex128更新。初解及每步residual/delta/z、最终真实z与correction先保存再判定。保留实际提前停止、GETRS和残差评估计数；不得做第3次RHS校正。初始z已在同次调用中取得，用它计算未校正的−Jz0作V9对照，不为该对照再解一次。

## 5. 第一出口必须是分别重放y15、g15，不是d相近

用原known的真实局部trace t、内部u及native b_i；全局full/volume trace RHS和Bα分别绑定。按原生产完整 `S@t`、完整 `−J@z`、cell/trace/MPC散射顺序重放：y由cell贡献后加入Bα，g先写全局b_t，再加两个实际返回correction。b_t、Bα及MPC各一次，不对已MPC-dual RHS再回拉。

两列分别报告y、g的复数值、与保存V15值的实/虚差和逐元素是否一致。预期精确重放；若不精确，保留两侧差，不放宽为新的1e-11单行绑定门。先查kernel/cache/局部分区/存储布局/BLAS与累加次序，无法绑定就标 `REPLAY_UNBOUND`，不把该新局部结果用于解释旧run。

同时用已保存的初解z0形成g0，并与V9同一行比较；只改变z阶段，其余量完全相同。y/S/input不改，可直接解释新探针为何校正后反而变差。检查每cell每列t是否逐元素为0：只有真实t=0时，R/Schur与t相乘的项才确实为零；不能从全局y=0反推局部t=0。

真正返回的correction必须被重放使用，另独立核其等于原完整−Jz。原full-vector动态/冻结分母和1e-11门保持，只作历史参照；单行除以全域分母很小并不是全域PASS。没有本轮candidate恢复/全域A6结果，均不得生成。

## 6. 同一局部包的有符号原因分解：不用新增伴随解

第一步先在每个初始/最终z上核原K真残差，使用已有独立宽算术/必要Decimal读取器；生产校正仍只消费binary64+fsum。诊断更高精度不参与求解更新。以**原known场**u和t作本节状态，不混入donor j0/j3恢复态；u只用于解释差异，不用于构造校正。

令q_c为该active行在cell局部trace上的实际E列（本包为单个+1），b_i为保存native内部RHS，b_t^V为保存native volume的全局目标行。所有下式按存储值的精确代数含义定义，再另计求值误差：

```math
w_c=R_ct_c+z_c-u_c,\quad r_c=b_{i,c}-K_cz_c,\quad
E_{R,c}=K_cR_c+G_c,\quad C_{S,c}=S_c-L_c-J_cR_c,
\quad \delta_{i,c}=K_cu_c+G_ct_c-b_{i,c}.
```

```math
\delta_t=\sum_c q_c^H(J_cu_c+L_ct_c)-b_t^V,\quad
\epsilon_t=b_t^{\mathrm{full}}-b_t^V-(B\alpha)_t,\quad
K_cw_c=E_{R,c}t_c-\delta_{i,c}-r_c,
\quad d=\delta_t-\epsilon_t+\sum_c q_c^H(C_{S,c}t_c+J_cw_c).
```

上述delta_t已扣全局native一次，与旧字段仅存局部Ju+Lt的含义不同；命名必须明确。完整生产d还需加matvec/scatter/末级相减的带符号求值余差。`C_S=S−(L+JR)`重复同一浮点表达式得到0，不等于精确存储数缺陷为0；禁止照搬只基于相消后输出的gamma估计。

**无需新伴随GETRS：** 本轮正常T构建已经解过 `K^H X=J^H`。取 `lambda0=−T^H q`；对本包单个+1的q，等同直接取负共轭T行，没有新的线性求解。它仅是已有近似伴随，不是独立真值，必须同时保存其缺陷：

```math
\lambda_{0,c}=-T_c^Hq_c,\qquad
 e_{\lambda,c}=J_c^Hq_c-K_c^H\lambda_{0,c},\qquad
 q_c^HJ_cw_c=\lambda_{0,c}^H(E_{R,c}t_c-\delta_{i,c}-r_c)+e_{\lambda,c}^Hw_c.
```

输出每cell及两cell汇总的复数项：delta_t、−epsilon_t、q^H C_S t、lambda0^H E_R t、−lambda0^H delta_i、−lambda0^H r、e_lambda^H w；再加各实际求值余差，与保存d独立核对。伴随缺陷项必须保留，不能因为lambda来自T而认定它准确；也不能把各项范数百分比相加当误差贡献比例。

独立核验用两条表达：直接 `q^H Jw` 和包含e_lambda的展开。较宽求值分辨力不足时，仅在本包已有小矩阵/所需标量上用已有Decimal实现核查，并记录精度与分辨边界；不重做V13八组账、不新建全域高精度算法。每项区分“局部存储矩阵/原native数据差”与“本次diagnostic算式自己的误差”。

## 7. 独立checker、具体因果出口与停止条件

checker只读取新包及原绑定数组，新增积分/LU/GETRS均为0。复算I/T、q与两侧y/g、回调状态链、返回correction、全部内部行残差和第6节有符号闭合。读取指向旧产品的引用，不复制旧完整矩阵/场；摘要按既有file、shape/dtype+payload或raw-state各自语义。首次保存即用同一真实loader试读，不等producer退出后才发现字段或复数编码不兼容。

| 获得的证据 | 本轮可以提出的具体下一步，非自动执行许可 |
|---|---|
| 两侧重放失败或K/LU/输入身份不一致 | 修选行/布局/状态接口；只重读或修必要输出，不改数学算法迁就结果 |
| −lambda0^H r确实主导剩余d，且其测量/伴随缺陷已分辨 | 指向 `project_internal_rhs_same_lu` 的残差求值/求解精度；不能仅据残差范数建议第3次校正或升级精度 |
| E_R t或C_S t主导、RHS项已小 | 指向 `condense_selected_volume_tensor` 及生产对应的R/S构造；否决“只继续改善b_i解即可” |
| delta_i/delta_t主导 | 指向actual evaluator与原native/RHS路径的差异。若还分不开矩阵与native制造误差，精确缺项是同一两个cell、同一known的独立native局部rank-1作用及其原scatter过程，而不是更多全域RHS；本包不默认新跑它 |
| 固定矩阵/z后J乘法或scatter相消主导 | 指向核心J乘法或 `P6CellCondensedAction.reduce_rhs` 的实际累加；只建议一个有实虚方向依据的最小改动 |
| 求值分辨力/多个相消项仍不足 | 列具体尚未分辨的项、需要的量和预计范围；不泛称舍入，也不选第二数值算法试运气 |

支持生产修复提案至少需要：y/g分别绑定；两列同一假设的带符号变化可核算；归因余差/伴随缺陷足以区分竞争解释；能指向一个具体函数。可在固定保存值上作“该项被更准确评估时应改变多少”的反事实量化，但不把它当新生产答案。当前不授权改变S/R/T/J、积分、输入、RHS、分母、复杂精度或校正次数。

重建和checker完成、局部d变小均只授予本star的重放/诊断状态。原全域FAIL保持，禁止自动进入28,000键、恢复、200q、factor、完整参考、FGMRES或target。后续全域试验必须另以机制跨类别适用性和成本重新裁决。

若strict LU、身份、非有限或资源真失败则保全并停止相应数值路径。普通接口、JSON/摘要/输出故障允许同一包修复继续；每cell的raw/oriented/LU/R/T/S、每个RHS步骤完成就原子保存及hash。后续故障只重开已完成部分，不把新attempt等同重新积分/分解额度。终态审核不要求成功物理输出目录。

## 8. 时间、资源和一次性授权

V16旧T0=2026-10-27T09:26:25.501825940Z；数值/总截止=2026-10-27T15:06:25.501825940Z / 15:26:25.501825940Z，即新加坡10月27日23:06:25 / 23:26:25。本次审阅日期已为10月28日，旧窗已过，不使用序405的历史余额。

**提案：新6小时完整two-cell补证包，总21600 / 数值20400 / 收口1200秒，PENDING_USER_APPROVAL。** 一次明确批准覆盖最多2个新candidate张量/2次LU、上列构建与4个RHS的两步校正、只读原因分解/独立checker；不含FFCx reference、全域或下游。先完成窄实现、fixture、真实命令及源码冻结，再登记新T0；正式准备、所需库加载和输入核验进入本窗，工程准备另记账。各长步骤前读实时余额，不自动续窗。

V12同类两cellproducer曾实测148.449 s（含51.777 s准备、3.445 s构建），但新路径/缓存可能不同，仅作校准。本包可沿900 s工作预算＋120 s终止预留作启动估算，并完整计入必要checker/IO；它不是新的900 s硬kill或完成时间承诺。无法准入给出具体缺口，不降低余量重启。

沿既有主机 `fenics-ws:/home/fenics/Projects/laptop_share`，项目名/对话不变；task cap1,649,267,441,664 B、host reserve68,719,476,736 B、task reserve0，complex128/int32、MPI1/math1、原MUMPS设置（本包不调用全局MUMPS）、task swap0、磁盘底线2 GiB均不变。计划新增工作集≤16 GiB，仍按实际对象准入，不能因沿用大cap扩大范围。

两个cell保存raw+oriented及R/T/S/LU/pivots，shape-only载荷为74,684,304 B；K/G/J/L按oriented与真实I/T重开，不再重复落盘。NumPy高级索引会产生临时副本，不能把它们都说成零内存view。状态、maps、报告和scratch另计。

**新增落盘上限128 MiB，并继续受累计16 GiB限制。** 先列expected files与确切bytes，旧数组只引用；旧快照15.603 GB与窗口37.17 MB可能有重复或尚未并账，必须按实际路径/文件身份去重核算，不能直接当实时剩余。普通重试保留全部失败并计入额度；无配额则先停，不删除旧负结果、不自动提高配额。tree/cgroup/PSS/host swap口径与未知项分别保持，父子时间不重复相加。

## 9. 提交与Codex接续摘要

主控负责冻结、集中commit/push；执行者只实现、定向测试和获准运行。推荐提交：①参数化两cell scope/持久化与直接相关回归；②真实补证、独立checker、response_v17及现有summary/run_index/test_summary和两级账。不改master或其他任务，不整体重构，不修改旧review/负结果。

```text
继续Task41extra，读取review_report_v17.md；结果base=6399beadd62d610100ba3e2b8d55ce7f0d48200a。
接受V16 A/B/metadata，不重跑分布、旧star或accepted checker。
唯一包：active1622464/original5218672的cells7873/8014。
新6h窗口及有限积分/分解待用户一次明确批准，旧窗已过。

先窄接现有selected service/manifest：新consumer与旧metadata/donor身份分开，
只允许两个cell；ordered coordinates/hex而非sorted actual_keys决定几何顺序。
真实I/T/E核对，不连续切882矩阵、不硬套旧360/446/旧窗。
实际调用链小fixture通过再冻结；不复制V17框架、不全仓测试。

缺数值块时各生成一次原actual-qmetric candidate，使用现有
condense_selected_volume_tensor，共2次LU；原strict、R/T构建另计GETRS。
原2列×2cell共4个RHS，生产core初解＋最多2次原fsum同LU校正，最多12次向量GETRS。
正常构建6次矩阵RHS GETRS也如实记账；不额外求旧ri/j0/j3或恢复。
每cell/每步即时保存，后续bug只重开已有数据。

使用真实返回correction，完整S@t和−Jz，保持cell/trace/MPC累加与b_t/Balpha各一次。
先分别重现保存y15、g15；再用同次初解z0对照g9，不重新解未校正候选。
两侧不能绑定则保留UNBOUND，不用差向量或换次序补答案。

用原known状态和已保存native RHS检查局部残差与R/Schur/local-native项。
T构建已有伴随信息：lambda0=−T^Hq，并保留e_lambda=J^Hq−K^Hlambda0，
无需新伴随GETRS。按review有符号恒等式连接到d，完整保留e_lambda^Hw和求值余差。
先检查真实t是否为0；只有t真零才能排除R/S乘t项。宽算术/Decimal仅独立诊断，
不驱动生产、不修改原门或精化次数。

checker只读新包，无新积分/分解/GETRS。输出一项具体生产修复依据或精确缺项，
不能只有审核完成；统计71%类别不是单行因果证明。
局部结果不解锁全域owner、200q、FGMRES或物理场；不新增第二候选。

新窗21600/20400/1200秒，明确批准后从正式准备计时，不刷新旧T0。
原主机/cap/reserve/ABI/线程/task swap0不变；新增≤128MiB且累计≤16GiB。
不重跑carrier、模式扫描、A1/A2、八键资格或全域比较；普通工程bug定向修复继续。
提交response_v17、精确路径/hash、独立审核与父子成本到当前分支，保留负结果，不合并master。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/response_v16.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/outcomes/v16_closeout/operator_resource_compact.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/outcomes/v16_closeout/group_summary.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/outcomes/v16_closeout/stage_b_terminal_replay.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/outcomes/v16_closeout/max_row_probe_metadata.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/outcomes/v16_closeout/next_probe_missing_evidence.md
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/outcomes/v16_closeout/attempt_index.json
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/docs/task41extra_phi90_p50x50_g17x20/outcomes/v16_closeout/evidence_index.json
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/src/solvers/hcurl_assembly_time_condensation.py#L3290-L3384
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/src/runners/task41_p0_v4_volume_only_audit.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/6399beadd62d610100ba3e2b8d55ce7f0d48200a/src/solvers/p6_cell_condensed_action.py

文档静态结构及单文件提交范围须核验；若GitHub只能返回原文，线上渲染记未核验。本Chat仅做独立小型代数核验，不声称重新计算工作站数据。
