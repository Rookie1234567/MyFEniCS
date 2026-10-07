# Response V58：完整部署成本已测，成对相位表示仍未闭合跨p精度

本轮连续完成 Review V56 的 P→C6→G6→G7→保存场比较/独立 VERIFY。三份真实完整物理解均合法返回、原式与完整输出通过；C6 更严同离散再现通过，完整单次部署实测 **904.036401666秒**。新载波下跨p散射场分歧仍超过原门，完整准确性未闭合。没有NN训练、目标PDE、旧hp/M追加、邻支操作或merge。

改进把本case已独立计算的边界积分按完整身份保存，后续只重载；体审核采用实际基函数阶数证明足够的求积。它减少重复工作，仍保留完整 Maxwell 原式。不是神经收益。求解仍继承原局部内部消去、共享边/面和端口求解、全部内部恢复的凝聚链，没有再开发一套凝聚；有限全局 MUMPS 因子实际存在，完整解保存后、输出前释放。

## 身份与冻结窗口

| 项目 | 实际绑定 |
|---|---|
| canonical / branch | /home/fenics/Projects/NN-Lab / task42_neural_coarse_inverse；canonical登记不变 |
| review / intake / base | 721c2731da0ce02ef528345f7b6ffcea459b033c / 8091c9515fc4c2116b57481408f71d05b0c7eb9b / ccd357885f7f9be84efe3be07868cc94f13d93fc |
| P/S及3次完整solve source | c47799d1c2bb7109a071358f06500a905fc42c43；最终checker source b4898819b58fdfe8a282bc0321a5c12262cf342e；文档HEAD不冒充科学source |
| 物理/离散 | s=7/135，真实三维NOTCH，Z2/160hex，λ0.7nm，grazing1°/azimuth5°/s/幅值1，完整Cκ和双Floquet；m±11/n±4/上下×s,p=828，全部内部 |
| 材料 | canonical表hash55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2；Si n=0.999885140474+4.32477054e−6i，epsilon=n*n，mu=1，air1 |
| carrier | C6/R6/R7：κ=(8.94046081729244,0.7821889682108057,0)；G6/G7：κ′=(8.94046081729244,5.629217633749343,0)；物理cfg/incidence不变 |
| 时窗 | 首次2026-10-07T08:50:53.306561Z；heavy-stop15:50:53.306561Z；交付截止16:50:53.306561Z；UTC/monotonic/boot绑定，未刷新 |

相位表示将已知快速振荡放入解析载波g，数值场只表示包络u；物理E=g*u，H保留完整curl(u)+iκ×u。新入射包络含exp(−iGy*y)，物理mode key/参考面不变。连续等价不保证两个有限维空间相同，不预设新gauge更准。旧混含carrier/离散项的physical hash如实保留，新物理/数值身份另列，不伪造相同旧hash。

## 完整原式、场和828模式

| measured模型 | cells / p / 含端口行 | 独立true / augmented / port | R / T / A_volume | 能量缺陷 | 正式/direct门 |
|---|---|---|---|---|---|
| C6 | 160 / 6 / 33660 | 1.1491898856e-11 / 2.0593534498e-11 / 1.3903401686e-13 | 0.076218704147 / 0.9056651717 / 0.018116124158 | -5.2347015611e-13 | PASS / PASS |
| G6 | 160 / 6 / 33660 | 1.0710346759e-11 / 4.2413889433e-11 / 1.9531899644e-13 | 0.076218705307 / 0.90566517061 / 0.018116124081 | -1.3388179454e-12 | PASS / PASS |
| G7 | 160 / 7 / 46076 | 1.7714556983e-11 / 1.9470151879e-11 / 1.1568051769e-13 | 0.076205038744 / 0.90565924193 / 0.018135719327 | -6.5425442841e-13 | PASS / PASS |


| measured配对 | total E / H | scattered E / H(curl) | 240点最坏 | 828参考面复通道 | 单mode功率差 | RTA/A_volume最坏 | 完整增量 |
|---|---|---|---|---|---|---|---|
| B6_C6 | 2.9351856462e-13 / 2.9351136254e-13 | 2.0432746681e-12 / 2.0432522368e-12 | 2.0499346909e-12 | 1.4128950356e-12 | 5.6055160513e-13 | 7.1009864655e-13 | PASS |
| G6_G7 | 0.0049031288085 / 0.0048988750229 | 0.03408935887 / 0.034060278988 | 0.027114895977 | 0.00093612705274 | 3.1873298778e-05 | 1.9595246387e-05 | FAIL |
| R6_G6 | 6.1411139894e-06 / 5.8324355721e-06 | 4.2750220611e-05 / 4.0601964078e-05 | 4.8015084859e-05 | 3.9176997183e-07 | 1.1599060185e-09 | 1.1600361643e-09 | PASS |
| R7_G7 | 3.5997805594e-07 / 3.4057891547e-07 | 2.5027735581e-06 / 2.3679340306e-06 | 3.4536439487e-07 | 6.6402271484e-09 | 4.0430991888e-12 | 4.0341063823e-12 | PASS |


C6/B6更严门为field/240点/complex modes≤1e−6、RTA/A_volume≤1e−8、逐mode功率≤1e−9；最坏散射场2.04327e−12，PASS。空间/跨gauge门仍为1e−4、1e−5、1e−6；G6/G7不通过的量及真实数值见表，不以total或守恒覆盖。共同几何上分别评价原gVh，不投影、不校幅相、不换分母。H/scaled-curl相对差一致，绝对量也保存。

三个解各自经 PUBLIC_BASIX 未凝聚体向量＋完整q63端口独立审核，true/native/aug/port≤1e−6，direct内部目标≤1e−10单列，恢复/MPC/identity≤1e−10、slave存储零通过。完整/内部/trace三列、非零特解及复对偶保留。全部total/scattered E/H/curl、240点、828键/极化/侧/参考面/归一化/复振幅/逐mode功率、q23/q31体吸收均落盘。独立consumer从保存数组重算原式、吸收、功率与能量；mode坐标/功率最大差7.33e−15。极倏逝辅助坐标不用于物理误差或伪条件数。

## P资格与S跨空间缺陷

P读取实际 embedded_superdegree=6/7；q15/q17有512/729点，覆盖逐轴2d。保存B6/R7全cell三列低q与q31向量最大差2.642e−11，curl/mass操作差3.770e−14，过1e−10/1e−12。旧B6 q63重载位一致；新κ两固定实际cell/每p与q31操作差≤6.7385e−15。完整828/非零端口/4个连续FLAT试验平衡操作差3.7257e−16，两gauge差3.1816e−16，无新FLAT PDE。

每个新case自己的q47/q63各生成一次、各原子保存重开并后续消费。身份包含原几何/行/basis/orientation/MPC复对偶/κ/全mode与参考面/入射/q/source。q47没有替代q63，不跨p/gauge命中。Fourier、指数RHS、体吸收与跨gauge积分仍保留高q，低q体审核不读新15表/raw/Schur自证。三个case均实际消费资格路径，无数学降级或科学回退。

S消费同κ、同828的实际R6/R7，完整p6→p7映射，不是trace子块或编号后缀。保存defect=b7−A7*Pu6、δ=u7−Pu6、实际r7和A7δ，解差恢复没有内部特解。

| measured S量 | 实际值 | 含义/门 |
|---|---|---|
| 完整缺陷 / 原RHS | 0.0499943509758 | 欧氏系数尺度约5%，不是物理场误差界 |
| 完整 / 内部 / trace缺陷范数 | 0.108385069682 / 0.106176038032 / 0.0217709043845 | 原贡献组装后范数；内部高阶平衡占主量 |
| P^H缺陷范数 | 8.16265695079e−9 | 拉回p6很小，不证明完整高空间准确 |
| 实际R7残差范数 | 4.41775010186e−11 | 保留实际值，未强置零 |
| A7δ=defect−r7操作尺度 | 5.34772455302e−12 | ≤1e−10，PASS；独立保存数组checker复算一致 |

S包含物理DtN消去作用，保存原828增广port残差另列。完整用时291.464s≤1200s，无factor/solve。它表明p6未控制部分高阶平衡，但不能认定p7是真解、唯一根因是抵消，也不是inf-sup、condition number或完整Riesz误差证书。没有为诊断新建全局谱/大探针或把解差回传求解。

## 完整单次部署与全部费用

| measured完整进程 | T_N1/s | sampled树峰/GiB | 实际最大gap/s | symbolic MB / numeric额度MB | q47 / q63生成 |
|---|---|---|---|---|---|
| C6 | 904.03640167 | 7.4325942993 | 3.029459249 | 3685 / 7370 | 1 / 1 |
| G6 | 890.38443931 | 7.4082298279 | 3.47981384 | 3685 / 7370 | 1 / 1 |
| G7 | 1770.5065322 | 14.336380005 | 3.9483127419 | 7216 / 14432 | 1 / 1 |


T_N1从独立run_case进程启动，到原式/恢复/完整场/240点/828模式功率/体吸收/provenance/必要IO和后代清场结束。每case从物理零初值和空的本case数值缓存构造自己的参考表/raw/凝聚/边界/numeric因子；OS/JIT未清空，状态登记，不能称全系统冷启动。没有配平旧完整冷链，端到端速度比不授，不能把旧含研究的B6计时直接相除宣传加速。

| C6非重叠阶段 | measured seconds | 包含范围 |
|---|---|---|
| q47首次＋重载 | 69.982727557 | exclusive事件 |
| q63独立首次＋重载 | 299.22156359 | exclusive事件 |
| 15表/raw/save重开 | 22.161471586 | exclusive事件 |
| 内部消去与共享装配 | 135.72155383 | exclusive事件 |
| global symbolic/numeric | 50.048058328 | exclusive事件 |
| solve/recover/refine | 3.6334192571 | exclusive事件 |
| 独立体审核 | 42.514913633 | exclusive事件 |
| 吸收/完整field/mode/240输出 | 52.210388555 | exclusive事件 |
| 其余已分段mesh/JIT/RHS | 57.907549064 | exclusive事件 |
| 启动/解释/IO等未分段余额 | 170.63475626 | 实际总时间余额，未声称各子项精确份额 |


exclusive只分解T_N1，nested inclusive不另相加；未分段启动/解释/IO仍在总时间内，不填0。P/S/四组比较/最终checker/文档属于研究支出，单列T_research。已知新有载下界及历史176686.252374522s的累计见[最终费用](outcomes/records/resource_costs_final_v58.json)；未测旧费用、实现CPU及控制失败时长保留unknown。所有失败、probe、replay、外层超过launcher部分及最后文档/结算尾部计费，不刷新旧窗口。

numeric仍按live RSS+2×可靠INFOG16/17(decimal MB)+2GiB≤64GiB准入；C6/G6的symbolic为3685MB，G7为7216MB，固定两倍额度，ICNTL22=0，ownswap/OOC0。规划64GiB/warn80/sampled-stop96及100000行贯通。实际峰和gap见表，0.5s仅名义配置，文档生成前的全采样已知最大gap为9.59805448s，最终费用记录继续覆盖文档与结算尾部，不称连续硬峰。MPI1/CPU/math1、GPU/Loader0、空闲物理核/避忙SMT、PSI/cgroup/宿主和邻增长余量、自有锁/整树监督保持。全部标shared-workstation，不宣称零干扰。对象载荷、unique owner与同时RSS分别记录。

## 修复、关闭边界与下一步

原始失败、source、stderr及费用见[repair journal](outcomes/records/repair_journal_v58.json)。fixture缺Basix variant、连续相位dtype、资格入口label、保存output verdict、冻结source alias、modal checker漏v58均同轮最小修复并定点继续。首次VERIFY按532错误拒绝828，修为实际库存并覆盖未知库存拒绝，仅补保存消费；三个完整solve/numeric都未重放。文档准备的字符串接线及费用汇总把辅助任务误当PDE的错误也保留。辅助绑定现明确无PDE输入；正式缺输入/hash仍拒绝，最小回归和实际费用库存复算通过，未触碰科学数据。最终11项targeted回归、修改依赖compile/Ruff、六dat validate和一次15文档合同，本地通过，full pytest/CI NOT_RUN。

新gauge下散射E/H差为0.03408935887/0.034060278988，远超1e−4；同p跨gauge最大散射差4.2750220611e-05。固定gauge配对没有消除跨p分歧，不把新gauge称更准确，不把普通准确性FAIL称软件bug。原carrier/hp/M追加在此收口，完整场准确性仍INCONCLUSIVE。

唯一下一建议：在同一有限物理对象上，对保存Pu6与δ作一次物理H(curl)尺度的有界对偶缺陷/稳定性检验，区分高阶内部平衡遗漏与响应放大；不把5%欧氏量或有限低频弱函数当证书，不自动追加载波/p/h/M或原尺寸。此建议未实施，具体范围由后续review授权。本轮完整准确性仍INCONCLUSIVE，不授原尺寸0.7nm、2TB/48h或NN20。

目标按实际FGMRES V33+预条件方向Z32，共65条主库，另有solution/RHS/residual/workspace。V56假设极细cell情景p6/p7 trace+port=507608956/699775356：主库527.913/727.766GB；完整FE主库1.72571/2.74026TB，不含端口/其他对象。均derived非实测RSS，不是准确空间下界或2TB资格。目标factor/Schur/PC、iteration、operator/通信与完整T_N1仍unknown，不从C6线性外推48h。

本case即使免费消除有限全局symbolic/numeric/solve/refinement尾部，也只有5.9379774405%总时间的乐观空间；不能由此安排或宣称NN20。相对最佳同正确性非神经完整成本的必要式仍为fV−H≥0.2T_B，同时峰必须合规；未测所有冷数据/训练/加载/推理/清理费用，保留unknown。没有新学习对象或训练授权。

[完整专题](outcomes/deployment_cost_paired_gauge_v58.md) · [科学](outcomes/records/scientific_checks_v58.json) · [阶段/source](outcomes/records/run_index_v58.json) · [数组](outcomes/records/array_inventory_v58.json) · [source绑定](outcomes/records/source_bindings_v58.json) · [原始归档](outcomes/records/raw_archive_index_v58.json) · [非重叠费用](outcomes/records/resource_costs_v58.json) · [目标库口径](outcomes/records/target_gap_v58.json)。只存增量与父hash，旧task/review/response/raw不改。

GitHub精确review页未取得视觉证据，NOT_VERIFIED，本地公式/表格/链接另验。最后closed/active null、清场/锁释放、commit/push仅本分支，实时remote/完整SHA/clean/upstream由最终交付核实；不merge、不通知隔壁、不自动开下一窗口。
