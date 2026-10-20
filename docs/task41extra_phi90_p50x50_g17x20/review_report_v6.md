# Task41extra Review V6：actual 几何下的分块 Gram 张量生成与完整两列资格

## 0. 审阅决定

**接受 V5 的 exact-key 盘点、8 个真实前缀及 `CANDIDATE_NOT_ADMITTED` 分类；不批准原慢 kernel 的28,000键长跑。下一轮唯一数值候选为 `actual_geometry_blocked_gram`：保持 `mesh_actual_exact` 坐标与数值缓存身份，以原积分的参考表和逐单元实际几何系数，做有界分块矩阵乘积，替代逐项生成完整张量的慢路径。先通过完整局部张量/消元对照和实测成本准入，再一次完成原两列全域验证。**

这是局部装配的计算组织调整，不是新PC，不改变积分规则或native。不能用“先延长24小时”替代加速，也不能把前缀未准入写成新数学失败。旧完整action仍FAIL，原尺寸场仍未产生。

| 冻结项 | 值 |
|---|---|
| repository / branch | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 审阅结果 base | `dcc2737a9166e6c9185223ac084f811d5068ad4b` |
| V5 scientific source | `179cf7369e6bc5894fa87af6b74cf5c73938b6d4` |
| 上一 review / V4 结果 | `0560dbe95d9f568adc219fecd1ed835bbdfd65ea` / `f66857f2a6b0ebd0415165adce164dbc2f04cc04` |
| 当前模型 | 0.7 nm；50×50 nm周期、居中17×20×120 nm Si；方位90°、掠角1°、S；p6、10×200×14 |
| 保持的接口与物理 | complex128/int32、MPI1/math1、双Floquet、原64,120模式及H/B/D、200q、原exact MUMPS；57个无端口q保留FE |
| 唯一主交付 | 实际降低张量生成成本，并在原输入/RHS/分母上关闭完整两列1e-11门；不能以新函数或fixture PASS代替 |
| 角色和写入 | ChatGPT只新增本review；Codex实现、定向测试、获准运行及response_v6；只写本分支，不合并master |

已核对response_v5、compact、summary、test_summary、run_index及关键代码。task.md blob `5b669c109006fa91fdeebba2a81d97ba17b640b0` 未变；本地完整Review V5与blob `e7c5f4f3c74001753982f1d9725e7b70df414107`一致。根规则与工作原则继续适用。本审阅没有登录工作站、没有读取其大数组或执行新的FE/张量实验；以下实测引用冻结仓库，候选性能不预报为已实现。[R1–R5]

## 1. V5 的真实进展与代价

| 指标 | 实测 / 推导与边界 |
|---|---|
| exact-key清单 | raw/oriented均28,000；16,224,652 B；SHA `147ab6347e6b0059ea97627a48802a970e8450d20e832a716bcd60d95233c952` |
| 前缀 | 8次真实cache miss；cells 26762、26897、0、1、2、5、6、7505，按原清单核对材料/方向 |
| kernel | 合计419.1692760037258 s；均值52.39615950046573 s；范围51.93273649085313–52.97407950973138 s |
| LU/solve与Schur | 8次分别合计0.49611899768933654 s、0.0661380747333169 s；不是当前主要耗时 |
| 两cell actual原块 | 26762/26897坐标和K/G/J/L逐位对上旧actual；只证明局部重放 |
| 剩余预测 | 1,488,176.122617107 s（17.2242607天）；加原储备需1,490,279.122617107 s，当时只有712.8634632226167 s；不是全域实测 |
| 完整保留载荷 | 348,561,972,000 B为派生numeric上界；没有完成全量分配或证明全过程可驻留 |
| 最终服务 / 三服务 | 父518.842396 s / 合计622.824232 s；未采工程准备仍UNKNOWN，不能再加子计时 |
| 已运行前缀资源 | tree RSS 6,674,780,160 B；task cgroup 6,830,514,176 B；task swap0、host swap delta0、PSS null、后代清场 |
| 尚未资格化 | 新完整两列、200q、全参考、FGMRES、完整场、A6/物理、网格/mode精度及2TB/48h |

保留旧两列误差3.042118678294192e-10、6.391893878204816e-10和原1e-11门。前缀被预算拒绝不证明actual修复有效或无效。科学源码后的fixture-only修正不冒充新科学计算；已修复导入/计时字段不作为再次停审理由。[R1][R2][R5]

## 2. 已定位的代码边界：慢的是张量阶段，内部热点仍须有限确认

`mesh_actual_exact` 分支在每个cache miss直接调用 `_tabulate_raw_tensor_class`，其后才计orientation、LU/solve和Schur。因此V5的约52秒不应归给LU、SSH、完整模式遍历或本轮JIT。该计时包含一组适用kernel调用和局部张量清零/相加，尚无每个C kernel内部成本分项。[C1]

现有 `raw_tensor_evaluator` 钩子只经canonical分支的 `_global_raw_tensor_cache` 使用；actual分支忽略它。`build_task41_v4_volume_only_owner`也尚未向底层转交该对象。**必须把候选接进actual生产miss，而不是只新增一个benchmark函数或切一个无效开关。**[C1][C2]

先读取本次真正加载的FFCx生成C/编译元数据，在一个原始前缀key的必要对照中，记录：适用的default/tag kernel列表及次数、每个实际体积分规则的degree/点数/weights/点序、882×882局部张量循环结构、几何标量系数与基函数表来源、编译flags及实际库。体积分规则从原form/IR取得，**不能把端口积分的q值当作体积规则**。零default项只有编译结果明确消去时才按原逻辑省略。[C3]

这是随首个对照完成的有界核查，不开一轮profiling项目。已有生成C中的basis表通常已经预计算；不得无证据声称52秒是每次重新调用Basix。要测清是否主要为大量quadrature×test×trial收缩，并把候选的实际几何系数生成、BLAS收缩、scatter、hash/复制分别计时。无需安装perf或修改运行库；若现成采样工具可用，只对该小对照采样。

## 3. 唯一候选：共享参考表，保留每个actual几何系数

### 3.1 它改变哪一步

局部张量可以按原FFCx分项写成参考basis表与实际几何/材料系数的加权乘积。候选只将原本逐积分点累加大量矩阵项的工作，改为BLAS友好的块乘；同一参考表服务多个cell，但每个cell仍使用自己的原坐标、系数和28,000-key数值身份。

以一个原积分分项为例，I/J是原局部test/trial列映射，q是原积分点，f包含该分项的实际几何和材料系数：

```math
A_c[I,J]\mathrel{+}=U_I^{H}\,\operatorname{diag}(w_q f_c(q))\,V_J.
```

公式表示同一离散积分的重组，不假定非Hermitian材料矩阵可以对称化；对于FFCx已经处理共轭的表，按其约定不能再共轭一次。现有体积形式是逐tag的curl-curl加负复质量项，二者及所有适用积分都保留。[C3] Basix提供参考basis/导数表和方向/映射操作，FFCx将UFL形式变成局部tensor kernel；这些是可利用的现有能力，不是本候选的性能或正确性资格。[E1][E2]

### 3.2 具体实现合同

1. **参考表只建立一次。**在已有volume-only owner中保留原UFL form、compiled form、Basix element和实际quadrature身份。复用已存在的form分析/参考表工具及 `raw_tensor_evaluator` 合同；必要时增加一个局部数值evaluator，不写通用编译器、C文本解析平台或新runner。优先使用原FFCx分析/IR的表和block映射；若用Basix重新tabulate，必须核对点序、导数索引、basis编号及数值表与原kernel一致。不得重排正式FE自由度或改变element variant。
2. **几何系数每个cell实际计算。**输入原float64 coordinate dofs，禁止减lower/round/snap/用widths重造。按冻结FFCx几何标量表达式求每个所需积分点的Jacobian、逆/行列式及后续系数；保留实际出现的非零交叉项。不能因数学上是轴对齐affine就把所有metric换成单一widths矩阵，也不能平均积分点metric。若原生成代码在某组点共享一个系数，才沿原依赖共享。核对实际scalar graph的求值顺序/flags，避免用代数上等价的canonical公式重新引入V4问题。
3. **收缩统一采用分块Gram。**不展开形状`(Nq,882,882)`的所有outer products，也不保留所有cell的metric/张量。建议首实现固定quadrature块128、test/trial块64，按实际reference block映射使用`matmul`/BLAS；块大小是起始实现参数，不是全仓扫描任务。若原积分块较小直接消费，不填无用的大零矩阵。只精确跳过原表的结构零，不用阈值删small项。
4. **聚合和消元不另改算法。**每个key输出完整complex128 882×882 raw张量，沿原顺序汇总积分，使用现有方向变换后取得K/G/J/L。原strict LU、R=-solve(K,G)、T=-solve(K^H,J^H)^H、S=L+JR不变；不同时切换Schur公式或增加精化次数。BLAS带来的累加顺序差异必须通过下节门，不要求候选输出hash等于旧FFCx张量，但输入坐标与积分身份仍严格相等。
5. **真实钩子与生命周期。**actual分支显式调用该evaluator，验证其form/geometry能力与schema；未选择候选时原FFCx默认不变。参考表/plan的identity与新evaluator source进入新consumer记录，实际coords字节和28,000-key语义不变。旧canonical类、旧actual基准和新Gram数值缓存不能串用。每keyraw/oriented工作块消元后立即释放，保留现有的LU/R/T/S，不另留一套raw cache。容量gate须新增共享reference表、系数/BLAS scratch及任何输出复制；不能沿用零evaluator workspace。

一次性共享表、逐keymetric和Gram分别计时；不能把预计算隐藏成warm或历史。禁止用GPU、多线程/新MPI数、降低积分、rank-1替换oracle、几何近似合类或更改native来取得速度。本轮只实现这个候选；不同时开发完整sum-factorization和第二套tensor-contraction后端。

## 4. 精度前缀：少量真实key，完整张量而非几项元素

复用V5相同8-key集合和现有exact清单；两个已保存actual单元直接作为原FFCx基准。V5前缀的计时收据不等于8份完整矩阵都已落盘：先查实际manifest。缺失的原张量仅对这8键中尚无基准者各生成一次，最多6次原慢kernel，保存后复用；这是补独立数值对照，不是再跑全模型或重新计时全部慢前缀。

完整前缀通过以下检查，才产生全域准入请求：

| 层次 | 原对象 / 新要求 |
|---|---|
| 几何/积分/方向 | 原coordinate字节、材料、全部kernel、点/权重/编号身份一致；metric保留原actual路径，不按近似相等合类 |
| raw与K/G/J/L | 逐个完整块的绝对/Frobenius及最大项差，完整raw相对差和各非零块相对差均≤1e-13；这是新增前缀筛查，不能代替后面的更敏感全域门 |
| R/T/S | 原FFCx块各自消元得到基准；三块相对差≤1e-11，零基准另报绝对差和是否应精确为零；原strict LU门不变 |
| 作用敏感性 | 用已保存两列的实际local trace/interior/RHS，比较两种生成器的完整局部作用、RHS缩减及恢复；记录绝对差并除以冻结全域分母，不只看大矩阵Frobenius |
| 原生与全域 | 原两列full native RHS保持；前缀PASS不是native PASS，更不是0.7 nm场PASS |

浮点Gram不可能普遍保证与标量累加bitwise相同，因此V5“相同原kernel重放应逐位相等”的检查仍用于旧基准身份，而新evaluator使用上述显式数值对照。**不能仅删掉原bitwise断言就算完成资格适配。**若矩阵或R/T/S对照失败，先按同一分项定位几何系数、点序、复数符号、block scatter；允许修这同一实现的错误，不改变native、输入或门限来迎合它。

前缀要记录raw/metric差、局部消元缺陷E_T=J+TK、E_S=S-L-TG的作用及相减尺度。V5/V4已表明1e-15量级张量差也可能被消元放大，因此即使前缀上述范数门通过，仍不得直接放行200q。

## 5. 实测速度与容量准入：必须给全域留出验证时间

最初8个候选key同时测正确性和成本，不另跑一个小PDE。候选最终用于full build的前缀对象在同一owner内复用；若进程已退出，明确重建费用，不能假称LU还活着。独立慢基准的时间单列，不纳入“候选每key生成耗时”，但纳入本包父账。

为每key计入metric、加权/打包、Gram、scatter、orientation、tensor-copy/hash、LU/R/T/S、observer/释放。一次性IR/reference表/JIT、加载校验与映射另列；给CPU时间和实际线程库，用同机器同ABI比较，禁止把52秒直接与只计GEMM的一小段比较。

用当前实测前缀各排他阶段最大值形成保守剩余估计，持续用真实进度更新，不当作统计上界证明：

```math
T_{\mathrm{need}}=T_{\mathrm{shared,remaining}}
+N_{\mathrm{remaining}}t_{\mathrm{key,upper}}
+T_{\mathrm{two\ columns+affected\ recovery+checker}}
+T_{\mathrm{safety}}.
```

此量必须不超过当时实际数值余额。沿现有1803秒postbuild父储备、300秒终止储备作为**不得降低的起点**，但按新对象规模修正，不能认为旧3类后处理时间自动覆盖28,000类。postbuild若和后续累计父计时重叠只计一次。完整cold48h还要另加端口生成、200q/reference及求解等尚未测得费用。

24小时中的85,200数值秒即使全部用来构建，也只容许平均3.042857秒/key；实际必须更快，才能给其余步骤留空间。**工程目标是候选装配/消元整体约1秒/key或更低；这是设计目标，不是性能承诺，也不以任意固定加速倍数代替准入公式。**以1秒/key计算28,000键约7.78小时；2秒约15.56小时，均为算术情景，不是实测。

内存预计仍含约348.562 GB局部缓存；加速不等于该缓存消失。新共享表、scratch、FE/MPC/maps、完整输出、文件页及后续PC全部计入，原cap和host reserve不变。reference表可共享，actual数值类不近似合并。新增evaluator单工作块scratch规划≤256 MiB，共享表单独计入实际容量；不以“reference”名义隐藏常驻量。原16 GiB证据区只存前缀基准、轻量表身份、必要完整输出及checker，不写入约350 GB全部缓存；旧数据用指针/hash引用不复制。

## 6. 完整两列与生产接续

前缀精度、实测成本及全部对象准入通过后，沿V5 exact-key miss循环生成剩余局部缓存。每阶段有真实进度和产物；源码冻结后才能启动，不在运行中热改。复用V4的全域maps；必要fresh编号与保存身份逐项核对，不按cell号猜对应关系。

随后直接使用**同一候选owner**的真实P6体积作用、reduce_rhs、受影响恢复，消费原两列known/native RHS。旧carrier和64,120模式不重新生成、不重扫；仅读取两个B帧，端口输出与其资格按未改身份继承。已通过的旧恢复不重跑；新R/LU影响的恢复检查是候选必需新证据，仍用同一保存RHS，最多原3次同LU修正，没有第4次。必要原生volume新作用只限核验新恢复，提前计入预算。

完整5,752,120行、两列都必须过1e-11：原`max(norm(s),norm(g),tiny)`定义和冻结D0=2225.481253487629、D1=2225.4807123031883两个口径均检查，forward仍≤1e-11，独立native残差保持原门。全局b_t仅一次，局部E^H累加不重复MPC；不从保存差向量修答案。新输出在判门前保存，独立checker重算，端口平方和与trace分块闭合。

继续使用V5残差凝聚恒等式区分native/local几何差、E_T/E_S及大项相减。不能为了闭合恒等式重新制造native RHS。若新快速张量与原actual基准相符、但完整两列仍失败，说明“actual一致的这套局部装配/消元”尚不足，不将失败归给优化未够快，也不立刻追加新的积分/精化/PC方案。

两列、独立checker、真实生产路径与完整对象账闭合后，在获准窗口内连续推进200q、exact因子驻留、完整参考和条件target pilot。57个空端口q保留FE；reference新sector必须使用相容实际几何policy及独立native/跨q检查，不能假定绝对坐标不同而矩阵逐位平移等价。q0成本或一个cell成本不能乘q数冒充全场实测。

## 7. 清楚的停止条件与开发边界

| 条件 | 动作 |
|---|---|
| 前缀积分/张量/R/T/S不符 | 保存具体key、block、原基准和候选；同一实现的索引/符号/布局bug定向修复；不启动全域 |
| 前缀快但全域仍超预算 | `CANDIDATE_NOT_ADMITTED_PERFORMANCE`，给实际主要耗时及缺口；不批准17天运行或自动延长 |
| 新完整两列仍超门 | `FULL_ACTION_GATE_FAILED`，保存两列和缺陷分解；不进入200q/FGMRES，不降阈值 |
| 完整数值已通过，后续metadata/读取失败 | 保存成功产品，仅修受影响接线，不重建tensor/carrier |
| 数值、checker、容量与窗口均合格 | 连续进入已获准后续阶段，不为普通bug或每个阶段重复停审 |

只有三类相关回归：actual evaluator确实被生产miss调用且原key/坐标不变；独立FFCx对照与故意错误metric/复数符号应拒绝；正式volume-only→准入→两列checker路由及受监督收口。默认不全仓pytest、不大整理、不复制V6 runner/合同框架。共享基础接口变化只补直接受影响用例，保持A1/A2旧默认及资格。新模块仅放可复用局部数值核，不把算法藏在一次性benchmark。

## 8. 新固定窗口：明确待批准，不复活旧T0

旧T0=2026-10-19T05:23:07.094241922Z；数值截止2026-10-20T05:03:07.094241922Z、总截止05:23:07.094241922Z。审阅开始的时间查询为**2026-10-20 17:13:20，Asia/Singapore**，两项截止均已过去。不得复制V5的712秒余额，不把本轮工作写入已结束窗口。

新包提案：**24小时固定窗，总86,400秒、数值85,200秒、收口1,200秒，`PENDING_USER_APPROVAL`**。它授权一次候选前缀、条件全域两列和门通过后的连续推进，不授权原52秒/key长跑。P0实现、原生成代码只读审计及小fixture可以先准备；实际新重型运行需要用户一次明确批准。批准后从该包第一项运行准备/ABI/证据读入开始冻结T0，修复不刷新，旧窗口、父子关系和全部费用保留。若已在现有对话明确批准此新包，由主控登记真实授权后执行，不重复索要相同主机/cap。

沿现有`fenics-ws:/home/fenics/Projects/laptop_share`、原Codex项目/对话；task cap 1,649,267,441,664 B、host reserve 68,719,476,736 B、task reserve0、task swap0、MPI1/math1、原complex128/int32及MUMPS、16 GiB证据配额/2 GiB磁盘余量。实时host/ancestor/cgroup更紧条件优先。不得改系统库、线程、PSS采样口径、其他分支或master。完整冷流程48h仍未证明，warm复用不能抹掉必需首次计算费用。

## 9. 交付、继承身份与提交计划

先实现最小evaluator接线和针对性验证，主控冻结源码；再在同一明确执行包中完成前缀、准入及条件完整两列。代码与证据分清source，由主控集中提交本分支；不amend、强推或合并。response_v6先回答**新张量每key实际成本、基准精度、全域是否构建、两列门是否关闭、已进入哪个求解阶段**，再列测试；必要同步现有summary、test_summary、run_index和两级模型/进度账。

旧V3 141数组manifest：`f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465`；V4全maps/三类报告：`09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5`；两cell actual/canonical报告：`a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031`。V5 exact清单及raw prefix分别从本轮compact的`key_inventory`和`prefix_measurement.raw_receipt`读完整路径/hash，不根据相似attempt目录名猜位置。大数据只在ignored目录；本次Chat未逐文件重验工作站内容。

V5完整内存、性能估计和未准入类别保留；旧action两列FAIL、checker旧段错误/修复和无效b_t初版保留各自身份。缺失原始数据、JIT费用或工程准备不补造，不把service成功当作科学PASS。

## 10. 可直接交给Codex

```text
继续Task41extra，按review_report_v6.md执行；只写task41extra_phi90_p50x50_g17x20。
结果base=dcc2737a9166e6c9185223ac084f811d5068ad4b，科学base=179cf7369e6bc5894fa87af6b74cf5c73938b6d4。

接受V5的28000 exact keys/8前缀及NOT_ADMITTED，不批准52秒/key的17天长跑。
唯一候选actual_geometry_blocked_gram：原quadrature/reference basis表共享，
每cell按原actual坐标和FFCx几何标量语义求系数，分块Gram/BLAS生成完整张量。
不平移/round/snap，不把metric按widths或近似相等合类，不改native/RHS/模式。

先随一个必要基准确认真实C kernel/积分点/分项循环和编译flags，不开泛泛profile项目。
原参考表可能已预计算，不能把慢因归为未证实的重复Basix；测实际收缩成本。
在现有raw_tensor_evaluator接口接入actual分支：目前actual直接调用慢函数，
仅传开关无效。volume-only wrapper、identity与workspace gate一起最小接通。
保留原orientation、LU/R/T/S和28000-key数值身份，默认旧路径不变。

复用同8key前缀；两cell现成actual块作独立基准。其余完整基准缺失才各补一次
原kernel，最多6次；不重算旧carrier/64120扫描/A1/A2/已接受恢复。
比完整raw/K/G/J/L（<=1e-13）及R/T/S（<=1e-11），保存原局部输入的作用敏感性，
并核原坐标/积分/材料/方向。局部PASS不替代原全域1e-11。
候选可改变累加顺序，不要求它的hash等于原FFCx；旧基准身份仍严格核验。

每key分计metric、Gram、复制/scatter、方向、LU/Schur、hash和释放；
共享表/JIT/基准验证另计，不把单个GEMM与旧52秒总阶段比较。
以实测前缀、28000剩余数及完整后处理/checker储备作准入，不空口承诺倍数。
目标整体约1秒/key或更低，但是否启动全域以真实完整预算判定。
actual缓存仍约348.562GB，共享表/scratch/FE/maps/输出和未来PC另计，
raw逐key消元后释放，不再保留全raw或把350GB写入16GiB证据区。

前缀精度和成本合格才在同一owner继续全域。复用旧141数组、全域maps和原两列RHS，
只读两B帧、继承未改port，重新算受影响volume/reduce_rhs和必要新恢复。
原max范数与冻结约2225尺度下两列均<=1e-11；不换分母或输入，不拿候选自验，
全局b_t只处理一次，不加第四次同LU。输出判门前落盘，独立checker重算。
同一实现bug定向修复继续；精度或成本真实不过，保存具体缺口，不批准长跑、
不换PC或盲扫积分。全部门通过才连续200q/准确因子驻留/完整参考/条件原尺寸pilot，
57空端口q保留FE，不拿q0乘200冒充实测。

旧窗口已在2026-10-20 05:23:07.094241922Z完全结束，不能刷新旧T0。
先完成最小P0；新24h包（85200数值+1200收口）需用户一次明确批准。
原主机/目录、1.5TiB cap/64GiB reserve/task reserve0、task swap0、原ABI/
MPI1/math1/MUMPS及证据配额不变。用户已明确批准同包就登记后连续执行，
否则只交可执行准备包，不自动启动heavy。沿现有prepare/service/监督checker，
生成源码真正支持的命令，不复制V6框架。只跑受影响回归，不全仓测试。
主控集中提交response_v6及原始基准、时间、容量、两列checker和下一断点；
保留全部负结果/UNKNOWN，不合并master，不提前宣称最终精度或2TB/48h通过。
```

## 固定来源

R1–R5分别为最新回应、compact及三份汇总；C为冻结源码。外部参考仅用于算法结构，不据此升级现场库或承诺速度。

- [R1 response_v5](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/response_v5.md)
- [R2 V5 compact](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v5_mesh_actual_exact_not_admitted_20261020.json)
- [R3 summary](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md)
- [R4 run_index](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json)
- [R5 test_summary](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md)
- [C1 actual miss及LU/Schur](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/hcurl_assembly_time_condensation.py#L3040-L3200)
- [C2 volume-only调用入口](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/task41_v4_volume_only_audit.py#L743-L875)
- [C3 原volume形式](https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/common_3d_forms.py#L26-L57)
- [E1 FFCx官方说明](https://github.com/FEniCS/ffcx)
- [E2 Basix 0.10表格与变换接口](https://docs.fenicsproject.org/basix/v0.10.0.post0/python/_autosummary/basix.finite_element.html)
