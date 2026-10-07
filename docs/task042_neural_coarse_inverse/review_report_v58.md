# Review V58：先在单元内消元再装配，配合独立子网格响应推进准确性和内存

## 0. 裁决与这轮实际要交付什么

**V59按有限实现与交付范围接受（`pass_with_qualifications`），不授精度、内存或时间收益。两份混阶方程确实解出；接口p6、内部p7/p8并没有闭合场准确性，最终行数减少也没有兑现为更小的实际峰值。停止继续内部p9或相同全局稀疏三乘积路线。**

授权 **V60_LOCAL_ASSEMBLY_AND_SUBCELL_RESPONSE**：①以实体数学支撑建立局部迹映射，将消元后的单元矩阵直接装到原p6接口；②用同一M67空间做一次完整再现和成本实测；③对一个预登记真实单元作独立局部h响应对照，并把固定2×2×2子网格响应部署为一份完整NOTCH解。不是只写一个局部诊断，也不再仅增加全局自由度。

本轮消除两个blocker：**全局投影把微小插值支撑扩成大稀疏图；内部升p仍变化，缺少与之独立的局部空间分辨依据。** 两项分别验收。局部装配正确/更省内存不等于场更准；局部h响应稳定也不等于整个三维问题收敛。

```text
repository          = Rookie1234567/MyFEniCS
execution_branch    = task42_neural_coarse_inverse
canonical_worktree  = /home/fenics/Projects/NN-Lab
review_date         = 2026-10-08 (Asia/Singapore)
reviewed_HEAD       = 7e31cf67a23917b137e0867e1320919d6a951cb1
latest_commit_UTC   = 2026-10-07T15:22:51Z
latest_commit       = docs(task042): settle V59 final validation and closed resource ledger
latest_response     = response_v59.md
previous_review     = review_report_v57.md
previous_review_SHA = e75eb2c6b4d3319e9ccb109ef5fa9debc1f60287
original_base       = ccd357885f7f9be84efe3be07868cc94f13d93fc
next_batch          = V60_LOCAL_ASSEMBLY_AND_SUBCELL_RESPONSE
required_response   = response_v60.md
new_global_solves   = two_planned; at_most_three_including_scientific_repair_replays
NN_training_PC      = NOT_AUTHORIZED_THIS_BATCH
merge               = NOT_APPROVED
```

最终目标仍是原50×25nm周期、z=−10..130nm、真空0.7nm、任意非可分三维周期材料/几何；完整必要准备至场/模式/功率/原式验收≤172800s，十进制约2e12B是整机物理内存而非本任务RSS许可。生产路线仍需分布式、matrix-free、流式DtN、凝聚接口迭代及有界粗问题。本轮是有限Full3D authority，不是Hybrid或原尺寸资格。

本报告明确覆盖V57“先建立全局高阶Schur再投影”的原型许可，以及仅内部升p的范围，改为下述局部形成与有界内部h分辨；不改变物理方程、原精度门、ordinary default或任何历史失败。新10h研发窗口不是重开V59，也不等于目标已在48h内通过。

## 1. 审阅事实、收益与负结果

读取了根/目录规则、仓库原则、原task（同blob历史继承）、V57执行合同、V59 response/summary/原门/费用和最新7次提交差异，深读`trace_interior_restriction.py`、`trace_interior_study.py`及原凝聚/恢复接口。没有SSH、没有读取工作站大数组或在审阅端运行新PDE。下表measured为仓库记录，不是审阅端重测；本报告新方案均为planned/not_run。

依据：[回应](response_v59.md)、[完整专题](outcomes/trace_fixed_interior_enrichment_v59.md)、[原门](outcomes/records/gate_verdict_v59.json)、[阶段费用](outcomes/records/deployment_stage_costs_v59.json)、[生命周期](outcomes/records/object_lifetimes_and_capacity_v59.json)、[最终费用](outcomes/records/resource_costs_final_v59.json)。

| recorded measured | M67：迹6/内部7 | M68：迹6/内部8 | 判断 |
|---|---:|---:|---|
| 最终含828端口行数 | 33660 | 33660 | 拓扑控制实现；不能据此推断资源 |
| 独立mixed true | 1.7479659606e−11 | 3.5312547547e−11 | 原1e−6和direct1e−10通过 |
| ambient高空间缺陷/RHS | 0.041420104358 | 0.010063815177 | 不同测试空间的诊断；不是完整高p解 |
| 完整T_N1 / s | 1693.2687995 | 3717.9348898 | 含必要准备、输出、审核、IO；OS/JIT状态保留 |
| sampled tree peak / GiB | 26.997310638 | 32.819904327 | 无自身swap/OOC；没有实测内存改善资格 |
| 临时高Schur存储项数 | 59693384 | 98051848 | 未factor，但实际占用内存 |
| 全局中间乘积存储项数 | 97323900 | 126155880 | 不应带入目标架构 |
| 最终低迹矩阵存储项数 | 141754824 | 141754824 | 少行不等于便宜矩阵 |
| 局部唯一载荷 / GiB | 1.377144 | 2.882517 | 不与各阶段峰值相加 |

| recorded measured完整场比较 | scattered E / H | 复通道差 | mode功率差 | 原门 |
|---|---|---|---|---|
| R6→M67 | 0.00269123555 / 0.00272375924 | 1.25051846e−4 | 1.38486870e−6 | 均有FAIL |
| R7→M67 | 0.0365737340 / 0.0365440976 | 1.00318790e−3 | 3.32570097e−5 | 仍相差约3.66% |
| M67→M68 | 0.00350686583 / 0.00347462021 | 1.45191325e−4 | 1.83060014e−6 | 内部增量未过1e−4 |

M67并未复现完整p7响应，不能把内部缺陷的旧95.97%系数平方占比当作“内部富集应解决95.97%误差”的证明。M68的ambient数值较小也不能用作不同空间之间的物理误差下降率。所有原mixed残差、完整场、功率和ambient量分列。

V59普通错误已经修复，完整科学solve没有因writer、容量估算或API问题重放。停止原因是队列完成及科学负结果，不是程序一直卡住。**应改变下一实验，而不是要求继续同一方法直到PASS。**

### 1.1 支撑膨胀的源码事实

`TraceRestriction`通过整个局部插值矩阵形成高迹行，然后按唯一owner从该cell的全部低迹列取值；代码只跳过恰为零的项。`projection_pattern_envelope`明确记录：插值矩阵在理想实体支撑之外有微小存储项，所以低p6 stencil不能界定当前全局乘积。随后`sparse_projection`形成高Schur×Q及Q^H×中间矩阵，额外邻接连接进入最终图。

这足以解释一个具体的存储代价，**并未证明该现象造成旧uniform p6/p7的场差异**。不能通过对已装配矩阵做幅值drop来“修复精度”或宣称相同数学身份。本轮按实体函数的解析支撑重新定义算子形成方式，并另立数值身份/再现证据。

### 1.2 邻支去重

只读ref：`task42extra_feinn_5nm@a96f7775c9d2f33c85a61535e5512e5e511eae95`仍是V31块波动神经求解合同；NN-V3为`1f01ae46bbe21f17200350a46513ef5f33e5cf6a`。本支不训练、不做M5、teacher或神经字典。

工程线`f59884b1a98b329cfce2a3de8307dd3db8560520`已发布V15：Gx560三步完整target通过，但workflow比旧路线慢约25%；E1在symbolic后资源停止。其下一候选是全局CSR bounded-staging。本支不重写该CSR策略/参考逆；这里改变的是受限单元矩阵的形成位置与数学支撑，不是另一轮通用稀疏累加优化。dot ref`15713d3e09b63f65511c7b7f61fa043fdb23dca5`不变，不重复其流式边界。上述结果不授当前不同相位/空间的PC资格，也不代表邻工作树此刻闲置。

## 2. 冻结物理与三种工作角色

继续同一Z2宏网格160hex、真实三维NOTCH、s=7/135、原κ=(8.94046081729244,0.7821889682108057,0)，不是G6/G7的κ′。物理轴/NOTCH盒从原descriptor精确读取；波长0.7nm、掠入射1°、方位5°、s、幅值1；Si n=0.999885140474+4.32477054e−6i、epsilon=n*n、mu=1；原材料表hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。完整Cκ、双Floquet、原RHS、828模式m±11/n±4/上下×s,p、参考面和归一化不变。

| planned角色 | 空间/作用 | 最终全局行 | 是否新完整物理解 |
|---|---|---:|---|
| K / C67 | 新局部形成，重现V59的trace6/interior7空间 | 33660 | C67一次，K不暗藏solve |
| L | 一个预登记宏单元，同迹/源的p6/p7/p8与子网格p6响应 | 无全域矩阵 | 局部边值问题，单列成本 |
| H2 | 每个原宏单元内2×2×2个p6子单元，宏边界迹仍p6 | 33660 | 一次，非旧uniform hp扫描 |

没有新增物理尺寸、p9、第三个载波、更多DtN模式、全局uniform p8或新的NN。最多两项计划全域solve，第三项只用于确认后的科学修复重放。局部L有明确有限清单，不能把它算作“没有数值工作”，也不能冒充全域解。

## 3. K→C67：局部消元/受限形成，再直接装配低迹系统

### 3.1 先定义正确实体支撑，不用数值阈值裁剪

建立实体化迹插值L_e：高阶edge矩仅依赖同一低阶edge；高阶face矩依赖该face闭包内的低阶edge/face，不能错误地只保留face内部列。低阶内部函数的整个切向边界迹在数学上为零。DOF方向、Piola和MPC复对偶仅应用一次，每个共享实体有唯一几何定义。

从原Basix插值/实体矩接口构造这些块，**支撑掩码由拓扑与迹泛函定义，不由abs(value)<tol产生**。记录被判为结构零的原插值残差最大值、运算尺度及实体清单，禁止对已有R、Schur或C/D作一般drop。错误mask应由一个非零合法edge→face反例检出。真实所有出现的方向做一次切向场/共享及复对偶核验，门1e−10/1e−12；同一资格不每case重跑全套。

独立实体矩抽查与旧稠密局部插值的物理切向评价配对。两者若超门，先区分新支撑实现错误和旧浮点映射敏感性；不能直接把结构零之外的合法项删掉。Basix依据见附录，不能套用标量Lagrange节点规则。

### 3.2 局部公式及全局图

将一个完整局部问题分为内部i与边界b，令高阶边界系数b=L_e t_e。先形成完整raw（含全部相位cross/mass），再计算：

```math
S_e=L_e^H(A_{bb}-A_{bi}A_{ii}^{-1}A_{ib})L_e,\qquad
f_e=L_e^H(f_b-A_{bi}A_{ii}^{-1}f_i).
```

全域体部分只装配：

```math
S_{\mathrm{macro}}=\sum_e E_e^H S_e E_e,\qquad
f_{\mathrm{macro}}=\sum_e E_e^H f_e.
```

E_e是原p6共享迹和Floquet展开。完整828端口另按原耦合/闭合装配；物理外边界的高内部零切向迹只能在数学资格后作为结构零，不能剪掉实际非零端口项。若采用一般Bi/Di接口，完整按原凝聚式保留。边界接收点/模式构造可直接在宏p6迹上进行，须用真实切向等价关系配对，不搬旧native行号。

复用已有单元LU、局部Schur/恢复和低p6装配映射，增加窄的local-block provider或受限局部系统接口。**不得先建全局高Schur或全局Q^H S Q；不得为此再写通用CSR/staging框架。** 高阶局部LU/恢复对象和宏p6全局MUMPS因子实际存在，明确登记。

本几何每宏单元432个局部p6迹坐标。保守体存储贡献上界160×432²=29859840；两物理端面p6独立支撑行共2304。连同保守2×2304×828耦合和828²端口块，存储图上界为**34360848项**。这是基于已证实体支撑的derived上界，不是实测nnz。实际装配前由真实拓扑/MPC数出并校验；若超界，先检查支撑/重复组装，不能恢复V59的全局三乘积来假称完成K。低矩阵CSR载荷与后端副本/因子仍分别计入资源。

### 3.3 C67完整再现及可消费作用

从物理零初值运行C67；不读取M67作初值或造RHS。先用小型非Hermitian、非互伴端口、非零内部载荷的局部形成/一次性受限系统作代数检查；再用至多两个实际单元与V59局部形成配对。不得重新生成/分解一份全球旧M67作控制。

C67返回后保存完整高p7场，独立原式按新实体化J^H拉回，ambient缺陷单列。与V59保存M67进行完整同空间再现：total/scattered E/H/curl、240点、物理复通道≤1e−6；RTA/A_volume≤1e−8；逐mode功率≤1e−9。比值分母沿既有规则。旧数值泄漏意味着新/旧矩阵不必逐位相等，不能伪造同一hash。

若新映射和完整原式可信，但旧场再现超门，保存`STRUCTURAL_MAP_SENSITIVITY`及完整数值，不自动称新场更准确；旧再现FAIL不取消独立可信的L/H2，新的原方程/映射错误则必须先隔离。C67的用途是检验资源与算子实现，不授空间准确性。

局部S_e既然已生成，可顺带以两个固定复向量核对ΣE_e^H S_e E_e作用与已装配体矩阵≤1e−10，并报告单次耗时/独立workspace；不复制新全局矩阵，不做迭代/PC扫描，不重写DtN流式算法。这个可消费的局部作用接口是通往后续trace matrix-free的交付之一，而不是生产资格。

## 4. L：一个局部h参照，不继续全域内部升p

选定一个与NOTCH共享面的Si宏单元，按几何最长宽比最大、再按中心坐标字典序取一。在读取场系数前保存cell/tag/未舍入J及选择理由；不得跑多个类后挑有利结果。它只是代表性局部见证，不覆盖任意材料/几何。

第一组边界数据使用保存C6的真实p6切向迹，内部载荷使用相同物理total方程在该单元的实际源，零就如实为零，不从参考高p解反造f。另加一份事前固定、零切向迹的多项式制造场及其非零体源，检验内部特解/恢复；这是局部恢复控制，不冒充真实散射。

同一边界迹/体源计算局部p6、p7、p8和固定p6子网格r=2、r=4响应。一个r表示三个坐标各等分r段。旧有匹配raw可复用但LU若已释放须实际新建并收费；不得称免费恢复。已保存同几何健康局部响应可直接消费。最多这五种空间、两组载荷；同根因修复不扩大为阶数/频率扫描。

在共同几何积分上比较物理E与完整Cκ/k0；边界反馈为原反力泛函q=L^H(A_bi u_i+A_bb L t−f_b)，不得把f消掉。用同一432维正的边界切向mass Gram给反馈差的对偶尺度，或明确标记原固定坐标诊断，不能把不同高p欧氏系数范数当物理量。此小Gram不是全局Riesz逆或Maxwell粗PC。

r2→r4的E/H及反馈差≤1e−4只标`ONE_CELL_RESPONSE_INCREMENT_PASS`；否则记录实际差。r4也不自动当真解，不定局部Dirichlet问题不保证误差单调。局部LU的backward error、尺度和有限性必须报告；零主元或数值不安全不加吸收/shift救场。不估计全域inf-sup/谱，也不再扩展24弱函数。

r4只解这一个宏单元、只求上述载荷，不构建它对全部432个迹列的响应库。它的空间增量FAIL不是H2全域实验的禁入条件，代数/映射不可信才停止相关依赖。L目标45分钟，最晚60分钟转交已保存partial并继续可做主线，不能耗完整夜且不交全域结果。

## 5. H2：子网格在宏单元内，全球仍只连原p6迹

**它与此前x/y/z全局加密不同：原宏网格及其p6接口不变，内部用8个p6小单元表示场；小单元之间的新边/面未知量只在宏单元内消去。** 没有把整个小单元全局迹暴露给大系统。属于有约束迹的相容H(curl)空间，不是删除内部未知量或把每个宏单元当独立散射问题。

一个宏单元r2/p6的derived库存：完整局部6084，宏边界1728，宏内部4356；第一次消去8×450=3600个子单元内部后，第二次需消去756个宏内部小接口，留下1728宏边界，再按真实迹矩映射到432个宏p6迹。可先限制边界再消去内部，按完整局部代数资格证明等价。

r4局部库存为45000/6912/38088；先消去28800个子单元内部后，第二级9288个内部小接口用稀疏factor，不得构造45000²或9288²稠密矩阵。只作为§4一个局部参考，不扩到全域。

H2全域仍160个宏单元，1280个子单元；mixed独立数为32832+160×4356=729792，最终含port仍33660。未约束的全局子网格p6 independent FE为834048，仅作重建/审核载体，不能拿它的全部方程残差作为新空间正式求解门。

每个宏单元的内部响应S_e/f_e及恢复用§3公式形成，局部两级矩阵/因子按精确几何、材料、p、κ和方向类只读共享；不按坐标round合类，也不为每cell复制全部响应表。16列或更小批次构造432个宏迹响应列，控制峰值；不把r4响应库误用于全域。局部D的实例可供函数回归，部署N1的冷/暖缓存和重构费用单列。

宏边界子迹必须由原p6切向函数的真实矩得到，不能仅对几个端点采样或把新增边界DOF设零。只约束宏外边界，所有宏内部微界面和子单元内部场都由Maxwell方程求出。子单元继承原材料，不移动/平滑NOTCH；非齐次内部项、原κ、完整端口保留。

C67和L的数学接口合格后，在预算内直接启动H2；不要求C67先取得速度/精度收益，也不要求局部r2/r4已收敛。只做一个新H2全域解，不启动全域r4、提高trace p或换模式。

H2独立审核用全部子单元的PUBLIC_BASIX未凝聚原式，再按同一J^H汇入宏p6迹与全部宏内部。J/J^H可以逐块作用，不需全局稠密映射。独立原式不能读生产S_e自证，细网格ambient残差保持诊断。完整细子单元场恢复并输出，不能投影回单个宏p6多项式；共享和周期接缝检查切向E，不强迫法向E连续。

只新增H2/R6、H2/M68两组完整比较；H2/R7仅在剩余预算足以完整验算时加一次诊断，不要求新场贴近两个互不一致的旧解。局部r4一个类的稳定性不替代全域h收敛；完整功率或1e−11代数残差也不能授真实场准确性。

## 6. 数值门、退出逻辑与后续决策

正式restricted/macro true、native、augmented、port各≤1e−6，direct目标≤1e−10另列；恢复/MPC/primal-dual及身份≤1e−10。最多两次继承的精化；即使达到formal但未达到direct内部目标也分别保留。不得因ambient缺陷大而无限精化mixed解。

物理空间增量门不变：total/scattered E/H/scaled-curl、原240点、物理参考面复通道≤1e−4；R/T/A/A_volume增量和独立能量≤1e−5；逐mode功率≤1e−6。共同积分沿q23/q31与运算尺度1e−10，必要一次q39；不同子网格先建立共同物理划分再分别求值，不先投影，不拟合幅相，不换分母。p6子单元body复用已资格q15，p7沿q17；Fourier/指数载荷和跨空间比较不能据此降q。

- C67再现通过且nnz/同时峰下降：授同空间实现收益，报告包括新setup的T_N1，不推断整体精度或全流程同比速度。
- 局部h响应与p6/p7/p8显著不同：定位到本类的响应敏感性，不能指定某p为真解；H2完整结果给出实际全局反馈。
- 局部r2/r4稳定且H2仍与高p簇不同：不能以一个局部类断定全域接口错误；下一步仅选择有证据的接口/独立表示核验，不自动再提高内部p/h。
- H2原式合格但精度比较FAIL：保存完整结果和区域分解，标科学负结果，完成成本与可复用局部作用交付，不把它当writer bug。

本轮不以“某个新诊断PASS”代替实质运行。可安全执行的C67与H2应连续推进；如果H2确因构造/容量未能实现，至少交出完整C67、局部h响应和明确缺口，不能只有计划或无关测试。不能为了跑满窗口重复一个已否决配置。

## 7. 时间、资源及不中断策略

新总研发窗口**10h**，科学有载≤8h，最后1h收尾；从第一次实际工作UTC/monotonic/boot绑定，包含实现、所有修复/失败/等待/资格/部署/研究比较/文档。恢复上下文重新读真实钟，不重开V59或清零累计成本。C67及H2各自启动前预留完整输出/审核和最终结算；预留不足先取消额外诊断，不降低物理门。

继续64GiB同时规划、80GiB警戒、96GiB采样树停止；100000行适用于全域凝聚矩阵（本批固定33660），**834048是H2可用的场/审核载体行数，不可误套该凝聚行门或创建其全球矩阵**。H2局部第二级最多756行，L的唯一r4局部稀疏第二级最多9288行。先数实际图、factor symbolic/工作区再分配；numeric仍按live树RSS+2×可信INFOG16/17(decimal MB)+2GiB≤64GiB。局部非MUMPS后端也需明确有界存储计划及峰值，不能填0。

不因最终行数固定就免除所有局部LU、子单元原表、432列响应、恢复、trace映射、边界包与审核工作区。r2全域类缓存计划≤8GiB，单独r4局部工作区计划≤16GiB，均包含在64GiB而非另加额度；容量不合格不分解、不赌OOM，不删历史失败腾盘。新增ignored≤16GiB、Task去重累计≤140GiB、free≥50GiB，按现场实际统计准入，禁止历史全树反复hash。

MPI1/math1/GPU0/Loader0、ownswap/OOC0、ICNTL22=0及原ordering/shift/BLR策略不变；一个自身heavy actor/一个全局factor，原物理核/SMT、PSI、有效cgroup、宿主余量与384GiB邻增长预留保持。只动NN-Lab，不改邻任务、系统库/BLAS/驱动、swap和共享Git设置。记录真实采样gap；名义0.5s不是连续硬峰。

**不按bug个数停工。** 意外修复与受影响重放累计≤2.5h并受总窗限制；同根因两次无效后换诊断、缩小验证到局部或使用已授权正确实现，不能第三次盲重跑。K的局部装配不能回退全局高Schur三乘积冒称完成；若K尚未可信，L仍可作为独立局部工作推进。H2依赖新的数学正确性，不能绕过原式/映射失败。

所有返回向量、local Schur/恢复包和积分块先原子保存，collector/JSON/文档错误只补消费。新解已返回不为写一份报告再factor；只有数学输入改变才使用第三个全域修复槽。后处理失败保留AUDIT_PENDING且尽早补审，不在总预算末尾才尝试全部checker。

不例行full pytest/CI、全仓索引、旧FLAT/gauge/24弱函数/15表重建、旧高p全部随机映射资格。只做新增实体支撑/局部两级消元/非零载荷/输出接线targeted测试、相关Ruff/compile/dat validate和一次紧凑文档检查。测试是保护新增数学，不是本轮主要产出。

## 8. 对2TB/48h必须新增的证据

不再复制旧宏观容量表。以C67/H2真实数据追加：实际nnz与图上界；每类局部setup/LU/恢复载荷；全局factor/原作用/完整输出费用；目标内部子网格副本如何限制；凝聚接口向量与内部恢复的同时生命周期。FGMRES仍须按实际V/Z库计数，不能把固定65条乘一个方便的N代替完整内存。

若H2响应可用，它改善的是局部场与可流式恢复能力，**不证明目标每个宏单元都要r2，更不能将总细场向量全部放进Krylov**。若新全域局部cache按cell复制会超2TB，必须明确class共享与逐块重算的时间/内存代价。C67/H2仍有全局直接factor，本批不继承工程线“三步”资格或开启新的PC研究。

未来生产最低路线仍是局部消元/作用→分布式trace+port迭代→有界全局纠错→流式DtN→按块恢复全E/H；独立精度锚点、目标fill、迭代数和172800s实测缺一项就不得写通过。本轮没有NN训练，所有收益为确定性表示/装配/执行收益。

## 9. 执行入口、提交与交付

先实现公共数值小核到`src/solvers/`，复用`trace_interior_*`、原低迹装配、15表、局部恢复、PUBLIC_BASIX、无JIT吸收、边界包与runner/监督/事务writer。不要为每case复制大runner。薄V60参数可显式选择local p7或subcell p6，不改变旧默认。

实现、targeted回归、commit clean、validate后经资格activation和监督执行以下**待创建**one-run入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v60_local_assembly_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v60_local_trace6_interior7.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v60_one_cell_h_response.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v60_subcell2_macro_trace6.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v60_compare_verify_cost.dat
```

顺序K→C67→L→H2→VERIFY；C67费用/旧场再现负结果不自动取消独立可信L/H2。各dat固定一个计算及清单，L明确其五局部空间/两RHS，不暗藏全域PDE；最终consumer不暗藏factor。入口未创建不能声称可运行。

C1提交实体局部形成与最小回归；C2提交局部子网格/恢复与one-run接线；活跃数值期间不改变受检HEAD。阶段完成、实现commit或一次局部负结果不是停等review的理由。先保存科学输出，再做一次紧凑结算。

交付`response_v60.md`、`outcomes/local_assembly_subcell_response_v60.md`；records至少有source/run/物理与空间身份、实体映射/结构零、局部响应、C67再现、H2原式与ambient/完整场、图/容量/全部T_N1与T_research、repair/未运行及唯一下一pilot。完整数组和per-cell清单留ignored，Git只交增量索引与必要摘要，不再嵌套数万行父manifest。summary、README、development_progress与development_model_registry追加短入口，旧task/review/response/raw不改。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

最终核对完整remote SHA/upstream/clean、closed/active null、后代清场和锁释放后交付用户暂停；不merge、不改master/邻支、不通知隔壁、不自动开新窗口。GitHub渲染没有视觉证据则明确NOT_VERIFIED，不为网页重跑科学计算。

## 附录：方法依据与审阅端边界

静态凝聚的局部块条件与恢复公式参照[MFEM公开文档](https://docs.mfem.org/4.8/classmfem_1_1StaticCondensation.html)；这不授本Maxwell子网格的收敛资格。真实矩插值与方向变换参照[Basix0.10插值接口](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.interpolation.html)；实体closure包含边界低维实体，不能按编号后缀代替。

本审阅端只检查了小型复数两级消元/非零内部与端口载荷的代数恒等式、实体图上界和DOF计数，以及Markdown结构；它们不是新的FEniCS或PDE资格。源和结果依据冻结到上述SHA；工作站现场资源、ignored完整数组和未来运行仍由Codex实测。真实准确性未知时不宣称成功，也不以历史负结果证明0.7nm问题本身不可解。
