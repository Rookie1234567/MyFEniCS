# V15：局部配对与全局＋局部组合完成，多项式组合改善但未取得有限元资格

按[Review V12](../review_report_v12.md)实际完成L0→两条L1→两条条件L2→L3，六个one-run全部执行，无缺项。两库局部1544维、组合3098维，数值decoder与新制造见证全部合格；独立审核8状态严格通过0个，4个无标签物理候选均未过原方程。**UNION-POLY优于同容量UNION-NN，没有独立神经优势或hidden训练增量**；原0.7nm／48小时目标仍未合格。旧p4强逆路线关闭、历史负结果不变。

## 表示、方程与容量

把单胞的有限元边／面系数按几何位置分成八组，让各区独立组合空间函数。函数先经过完整边／面积分、坐标和方向变换，才变成合法的Nédélec有限元未知量；所有区域仍由同一个原Maxwell方程耦合。两库分别使用固定随机神经隐藏特征与确定多项式，并按每组实际秩匹配容量。每组方向正交化后直接输出trace，避免用巨大原始输出系数相消。这里trace是单元共享的电场积分系数，40个port是上下边界波模幅值；内部电场由原局部方程作包含非零特解的恢复。

本批hidden固定，网络只计算局部坐标的64个tanh函数；加常数后形成65个标量特征，每个配三个物理向量方向。最终组合系数由原方程薄最小二乘求得，完整40端口由原40×40凝聚Hhat闭合。Hhat不同于未凝聚Hp。两路线都有相同稳定解码及线性代数，不存在hidden训练增量。

```math
(B_b)_{j,(a,m)}=\ell_j[e_a e^{i k_{inc}\cdot x}\phi_m(\xi_b(x))],\quad
 t=\sum_b E_b Q_b c_b,\quad \alpha=H_{hat}^{-1}(b_p-Ft).
```

```math
\bar S=K-CH_{hat}^{-1}F,\quad A_Q=\bar S Q,\quad
 c=\operatorname{lstsq}(A_Q,\bar b),\quad
 \Phi=\frac{\lVert b-S[t;\alpha]\rVert_2^2}{2\lVert b\rVert_2^2}.
```

| 冻结身份／单位 | 本批实际情况／证据 |
|---|---|
| 原物理与网格 | 0.7 nm、真正三维缺口micro；384hex=8×6×8、h0.175 nm、Nédélec p3/q15、双Floquet/DtN；full34050、独立trace18144、内部13824、slave2082、reduced18184；top20+bottom20完整复端口 |
| 材料 | canonical `input/materials/si_optical_constants_v1.json`，USER V1；source0.699999988明确alias为nominal0.7；Si n=0.999885140474+4.32477054e-6i、epsilon=n*n，air与mu_r=1；材料/背景/入射/RHS不变 |
| 分组 | x=0、y=0、z=0.525分8盒；canonical master完整边／面实体中心及切面低侧规则，周期上边界只在归组时用等价位置，原积分坐标不变；2448实体、18144行无遗漏或重复 |
| 8组行数／共同秩 | 2913/2676/2289/2076/2439/2220/1863/1668；共同秩195/195/195/195/195/195/187/187，总1544。POLY最后两组秩187，NN各195；没有填零凑满1560 |
| 两库 | POLY是Legendre(0..3)^3+L4(x)，NN是seed420906的3×64 tanh隐藏64+常数；每组名义195列；extra L4是辅助函数。隐藏权重无训练、无NN7／s4／D1拟合初始化 |
| 载波 | 原入射k_inc=[8.97461192517716,0,-0.15665243385951635] nm^-1；两库均1载波。相对旧G0同时改变局部化和8→1载波，不能作纯单因素归因；40物理通道全保留 |
| 数值坐标 | 非零特征列单位范数；局部GESDD阈值sigma大于1e-12 sigma_max，取每组两库min rank。块乘法直接输出trace；组合按G0正交补，角度阈值1e-10、一次重正交、非pivoting QR稳定坐标；没有阈值／rank扫描 |
| 实际source | 全六个正式run为 **`db0e68e519767554412c960af14b3c185012f9de`**；C1 `78f547a86c21cf28920c8dc3f9e8132561497a46`的精确SHA见Git历史；checker source `8d6df6926fc6f5c1afc27491dc06255791fcc044`；最终文档HEAD不替代运行source |
| 数据provenance | [材料/physical/mode/action/矩与输入hash](records/plan_and_input_identity_v15.json)、[特征及权重](records/basis_inventory_v15.json)、[run index](records/run_index_v15.json)。REF7 a0610a…只在队列与状态冻结后读；已消费pilot，不称fresh blind或新几何泛化 |

完整实体延拓先作全部q15边／面矩、Piola及orientation，再选择该组行，没有跳变积分mask或点值PINN。原周期slave未增加未知量；新特征的完整逐行map与大数组在ignored artifact。[map概要](records/local_entity_map_v15.json)、[容量](records/matched_capacity_v15.json)。

## 数值资格与制造见证

独立DOLFINx q15全局延拓插值后取同样行，POLY／NN相对差2.92349e-15／1.87647e-15，MPC展开差0，5类方向变换全部覆盖，slave storage原0。块forward差0、adjoint运算差≤6.71e-18、正交缺陷≤2.09e-15，原barS每库3列+2个非零组合配对≤1e-10。Hhat条件13284.163＜1e10，所有端口solve≤1e-12。所有物理A数值列秩等于实际1544或3098，实际/thin差≤1.06e-12、range(A)驻点缺陷≤5.62e-12；固定GELSD/cond1e-12，未用修正或正规方程。数值满秩不称精确最优。

| 新LOCAL制造见证，原S生成完整rhs | known-z相对差；限1e-6 | 原残差；限1e-8 | 齐次恢复；限1e-10 |
|---|---:|---:|---:|
| POLY seed421501非零c及40非零port | 1.81741e-12 | 5.09211e-15 | 9.25456e-17；PASS |
| NN同seed与容量 | 2.61674e-13 | 4.37027e-15 | 8.64052e-17；PASS |

物理b未覆盖，制造问题使用自己的完整trace/port rhs。恢复包含非零内部特解；误差配对采用F(z_ref)-F(z)与F(e)-F(0)。新见证不改写旧V11-M2、旧头1e-8、V12 FD或V13负结果。[数值和制造raw](records/local_basis_checks_v15.json)。

## 原物理求解与有界组合

Schur残差检查凝聚后的trace+port方程，native在恢复内部后检查原方程；分母为冻结原RHS。散射E/curl以已保存同mesh/p3准确场为分母，不能由小total场误差或薄LS驻点代替。

| 同0.7nm模型／方法；measured，无量纲 | 实际复系数容量 | 原Phi | Schur／native；原限1e-6 | 散射E／scaled-curl；原限1e-4 | 严格资格 |
|---|---:|---:|---|---|---|
| G0 | 1560 | 0.318179987294 | 0.797721740／0.309359507 | 0.734256828／0.734361605 | FAIL |
| LOCAL-POLY | 1544 | 0.339574133266 | 0.824104524／0.319590851 | 0.578751074／0.578743743 | FAIL |
| LOCAL-NN | 1544 | 0.339239788767 | 0.823698718／0.319433478 | 0.628221107／0.628213879 | FAIL |
| UNION-POLY | 3098 | 0.134013809183 | 0.517713838／0.200771384 | 0.283235368／0.283293409 | FAIL |
| UNION-NN | 3098 | 0.168191759580 | 0.579985792／0.224920683 | 0.766070574／0.766240878 | FAIL |

两局部路线都数值可信且原方程失败，故按合同直接执行L2，没有以局部进展或收敛为准入条件。G0固定V14 ORIGIN Q，POLY/NN原始补空间秩1538/1544，取共同q=1538，组合各3098维。完整G0被保留，旧候选重建差0，组合正交与5项原作用配对通过；各从相同原b独立重求系数，无旧解相加、warm start或参考。两Phi均不劣于G0＋1e-8余量。[组合检查](records/union_checks_v15.json)。

局部化后的散射E比G0改善约21.18%／14.44%，Schur反而升高，且载波变化同时存在。组合POLY的rho下降**35.1009%**、散射E下降**61.4256%**；其空间维数约翻倍，不能归为神经增量。配对NN局部Schur仅略低而场更差；组合NN的Schur0.580和散射E0.766均差于POLY0.518/0.283，场还劣于G0。NN独有收益没有证据。

UNION-POLY已有可见场改善，仍未满足研究rho减半（需≤0.398860870）的条件；研究正信号四候选均FAIL。它仍距原1e-6残差和1e-4场门限很远，不能授予micro有限元或最终48小时资格。h/p、MPI、材料及网络规模均未扫描；旧p4逆未复活。

## 冻结后场、完整通道与功率

求解队列结束并冻结参数/系数/trace/port/z/hash后，唯一VERIFY一次FE环境处理历史G0/s4、4新候选及2表示诊断，共8去重状态。原REF7本次独立native **1.437444866e-12**，packet native3.017963044e-12，Schur6.424146503e-12；保留实际非零残差，参考身份与native通过，未重新LU。[参考审核](records/reference_audit_v15.json)。

UNION-POLY的total E／scaled-curl为0.0296391153／0.0296457515，scattered为0.283235368／0.283293409；selected复E／H为0.0258167294／0.0331777310，40复通道误差0.0118838170，最大通道功率差及完整原增广/独立native见[候选CSV](records/local_candidate_comparison_v15.csv)。上述均未达原场门限。mu_r=1和波长固定时，H_code=curl(E)/(i k0 mu_r)，全域H相对L2误差对应scaled-curl；selected复H另存。[selected复场](records/selected_fields_v15.json)、[完整40通道](records/channel_observables_v15.csv)。

| 实测无量纲，全部UNQUALIFIED_DIAGNOSTIC | R00_s／R00_p／R00_total | R_total／T_total | A_balance／A_volume | 能量闭合；限1e-5 |
|---|---|---|---|---:|
| LOCAL-POLY | 0.0835238612／1.75939662e-11／0.0835238612 | 0.0835261683／0.787065615 | 0.129408217／0.00477559473 | 0.124632622 |
| LOCAL-NN | 0.0820176413／3.13171152e-08／0.0820176727 | 0.082020565／0.780682892 | 0.137296543／0.0047384976 | 0.132558045 |
| UNION-POLY | 0.107758776／4.37751721e-07／0.107759214 | 0.107762913／0.856177879 | 0.036059208／0.00518517975 | 0.0308740282 |
| UNION-NN | 0.101495832／5.08402478e-07／0.101496341 | 0.101499785／0.837834135 | 0.0606660801／0.00510533807 | 0.055560742 |

每个通道保留原m/n、极化、上下侧、参考面和total/scattered复数；不校相位或重新归一化。原端口固定RHS相对残差最大约1.34e-16、恢复≤6.52e-13、identity≤7.00e-13、slave0，仅这些小项合格不能替代体方程与场。无新official R/T/A。

## 仅用于离线判断的表示投影

各局部库一次把REF7 trace正交投影到固定QL，再用原Hhat闭合port并作原仿射恢复。系数不进入训练/初值/选点；它最小化trace欧氏误差，非物理L2最优、非全部NN能力下界。

| offline参考辅助状态 | trace欧氏相对误差 | 散射E／curl误差 | 原Schur／native | 判断 |
|---|---:|---|---|---|
| PROJECTION-POLY | 0.00127666501 | 0.00113178129／0.0035047079 | 0.907830214／0.35205999 | FAIL；offline diagnostic |
| PROJECTION-NN | 0.00124788601 | 0.00113069576／0.0034895723 | 0.955868699／0.370689496 | FAIL；offline diagnostic |

两库投影的trace及场接近，原方程仍不合格；真实LS场远差于这些投影。这表明“近似可表达”与“当前原残差最小化选出的场”有明显差异，不能把全部失败仅归为全局tanh形状不足。投影残差仍约0.91/0.96，有限空间遗漏高响应方向、残差度量取舍及表示误差都可能并存，唯一根因仍`INCONCLUSIVE`。没有从投影权重重启求解或展开其他诊断campaign。[投影记录](records/representation_projection_diagnostic_v15.json)。

## 成本、资源与数据生命周期

| shared-workstation实测；含launcher/worker及所有后代 | 监督wall秒 | 同时采样整树峰bytes／GiB | 现场选核／清场 |
|---|---:|---|---|
| V15-SETUP | 37.607987 | 867385344（0.808 GiB） | 0；swap0，已清场 |
| V15-LOCAL_POLY | 236.083223 | 1797267456（1.674 GiB） | 0；swap0，已清场 |
| V15-LOCAL_NN | 237.381524 | 1798336512（1.675 GiB） | 0；swap0，已清场 |
| V15-UNION_POLY | 960.339373 | 4175888384（3.889 GiB） | 0；swap0，已清场 |
| V15-UNION_NN | 601.680765 | 4127686656（3.844 GiB） | 0；swap0，已清场 |
| V15-VERIFY | 33.074559 | 766357504（0.714 GiB） | 0；swap0，已清场 |

正式监督wall合计**2106.167431s**，含准入等launcher完整wall合计2114.586302s，最大采样树峰**4175888384B≈3.889GiB**；各阶段峰不能相加。UNION-POLY stage含两库共同补空间设置约351.631353s（各175.881787/175.749566s），NN stage没有重建该设置；公平方法lineage成本各应包含自己的设置，不能直接用两个stagewall宣称NN更快。LS／矩构建／A作用／QR／审核成本分别保存，嵌套时段不再次累加。[完整费用](records/resource_costs_v15.json)。

本批S/SH9345（其中新A列9284）、LS/RHS6/6、局部SVD16、补空间SVD2、原audit13、field8，全部在共同上限内，未重放正式数值。原数据已资格化的材料/ABI/矩链复用；没有重跑F0或旧campaign。局部decoder含索引56,302,464B/库，原作用A仍稠密；组合G0/U与LS workspace计入全过程，网络约8576个实hidden并不是全流程内存。本批不构造global Schur方阵、global p4因子、正规方程、Riesz/ILU或隐藏fallback；VERIFY原未凝聚native审核装配如实计入，流程不是零装配。

新artifact常规文件约1.020GB，整个Task042实际常规文件约7.739GB；此处按lstat统计不跟随符号链接，监督器的配额计数另外包括已存在的符号链接目标逻辑大小，两者都未触线。新results与辅助文件单独列入费用记录，独立缓存复用的新增占用未单列实测；此处按lstat统计不跟随符号链接，监督器的配额计数另外包括已存在的符号链接目标逻辑大小，两者都未触线。新results与辅助文件单独列入费用记录，独立缓存复用的新增占用未单列实测；A为内存可再生workspace不持久化，组合仅存补空间U并只读复用G0，历史负数组未删。独立cache/JIT/TMP/Python/Torch/模型路径全部在NN-Lab；FE/ML分环境，不改邻任务或系统。ownswap0、VRAM0、MPI1、数学/Torch1、Loader0、自有锁、nice10/I/O idle，实时核查物理核与SMT；当前硬件每逻辑核的siblings为自身。

无cgroup委派，实际独立watchdog是0.5s采样的整树12GiB预警／16GiB停止阈值，不称连续内核cap；常驻规划7.6e9B＜8GiB。所有正式stage PSI avg10峰0、最低MemAvailable943900930048B；保留系统10%余量与邻增长128GiB及本批16GiB。未见持续压力停止，邻任务可比吞吐unknown，性能`INCONCLUSIVE shared-workstation`，不宣称零干扰或无争用加速。

不可刷新窗口从2026-09-30 08:44:30 UTC开始，重负载截止12:29:30、总截止12:44:30；实现、测试、检查、推送与收尾全部计入。V6起formal可核下界**16776.579534s**，历史辅助unknown保持，不等于目标48小时能力。micro只跨少数波长，目标规模的单步费用、所需表示维数、收敛和离散误差仍unknown；本批没有新p4参考、最大模型、GPU或seed420620消费。

## 测试、偏差、发布与下一步

C1/C2小回归17/30通过，最终相关33项通过；compileall/diffcheck及6入口validate通过，独立checker从冻结raw残差/实际decoder/hash/门限重算为EVIDENCE_CONSISTENT，4个trace重建差0、严格通过0。Ruff不可用，未重装；不声称CI、full-repository或MPI2/4资格。[测试](test_summary.md)、[变更依赖组](changed_files.md)。

额外启动probe误用WSL marker断言；此前Task042原生ABI已经通过，shell当时未set-e，故合法native L0继续。已准确读取隔离activation并重核_NATIVE marker、complex128/int64/MPI1，后续命令全部set-e；没有变更ABI、源码、门限或重跑合格L0。原始失败输出及correct_native_preflight.json保留。正式实现修复/重放0。

Review V12精确OID的GitHub HTTP200、4表列宽一致、3math-renderer完整、不截断，服务端结构通过；浏览器实际字形NOT_OBSERVED。新文档本地合同和推送后页面结构分别记录，无法取得的视图不伪称通过。[发布检查](records/publication_checks_v15.json)。

唯一下一建议（本批未实施）：保持 LOCAL-POLY 的1544维空间及相同物理RHS，预登记一次由原FE测试函数的 H(curl) 能量范数确定的残差行尺度对照；尺度只由网格／算子决定，禁止用REF7选权重，最终仍按原未缩放残差和全部场／功率门限审核。这检验当前系数欧氏残差的衡量方式是否造成场误差取舍，不保证补足遗漏方向；需要下一份review授权，不自动执行或扫描尺度。

全部授权有限队列完成后只推送本执行分支，清场等待review；不merge，不回训，不追加profile。
