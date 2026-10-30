# Task43 正式审阅 V21：保留 H67 独立 A6 失败，批准保存数组原因诊断

审阅日期：2026-10-30。唯一执行分支：`task43_hp_adaptivity`。

## 1. 正式裁决

**本轮研究入口、测试修正及实际空间证据有限接受；接受 F1 独立 A6 数值门失败与随后的停止裁决。H67 没有合格 primary 或科学比较端点。下一轮明确执行第9节 V22：只用既有保存数组，分解并交叉核对三类残差，定位主要差异块及可可靠归属的单元/模态。新增正式 PDE、算子作用、correction、有限元场恢复、采样和 C 比较全部为0。新增支持最多4次，whole累计1800秒。**

这里的诊断不是再求一次解，而是检查已经存下来的“方程左右不平衡量”：它主要出现在单元内部、共享切向未知量，还是端口模态；两种计算路径是否使用了同一状态、符号和范数。这样能把下一次可能昂贵的改动定位到具体环节。代价是：没有保存的矩阵、约束展开或局部消元块不能由这些向量凭空恢复，诊断完成也不自动证明连续真解正确。

| 审阅对象 | 裁决 | 不能扩大的边界 |
|---|---|---|
| T1正则修正、T2补验 | 接受有限节点/字节证据 | 14项未改历史证据与3项T2实测，不是最终同字节17项单批次通过 |
| H67请求、必要闭包和空间 | 接受实际空间计数及固定动作身份 | 不授多层/任意MPI/自动选择资格 |
| F1原向量保存与失败留证 | 有限接受 | 42个数据数组存在不等于primary合格；未访问的大原件不称外审亲验 |
| F1数值状态 | **FAILED_OR_INCOMPLETE，official=false** | A6约为门限的2.1004倍；不能切换到较松的任务通用门或用其他残差覆盖 |
| 不运行C/F2/E | **符合V20授权** | 此次是数值硬门失败，不是可借工程恢复槽绕过的异常 |
| H67输出收益 | **UNKNOWN / NOT_RUN** | Av、q8/q10、J/G、收益/FE均未取得；不能评价此位置的h收益正负 |
| 下一轮 | 第9节的保存数组诊断获明确授权 | 不恢复旧未用槽；不调用旧正式/后处理入口 |
| 合并 | 无任何具体依赖组或整分支的merge approval | 保留研究档案不等于生产合并许可 |

## 2. 固定身份、审阅方法与可见性

| 角色 | 完整SHA |
|---|---|
| 本轮固定被审交付 | `a4fa1f536fbed152bc0bd4746cbdd545895018a6` |
| 原执行权威V20 review | `0dd5555f8795a68c7c9b1dc58387337d98fd76a5` |
| T1前实现提交 | `535b23d6274b750ab8a8ffd55faf4048d93c1b2e` |
| 正则修复及T2/S/F1实际源码 | `5796d78b642b58c0963ef47d181f70b96b728786` |
| 长期代码基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |

审阅开始与写入前的远端HEAD均为固定被审提交，没有发现后续提交。V20 review之后是实现、单行测试正则修复、交付三步；运行HEAD到交付HEAD只有文档与证据变化，没有把交付SHA追认为运行身份。远端核查不等于进入了工作站canonical worktree，现场工作树及本地ahead/behind仍来自执行方记录。

本审读取三层AGENTS、仓库工作原则、任务物理/残差约定、V20第9节、V21 response/results、现行汇总/manifest/总账/进展，并沿研究入口追到独立A6、变量阶次消元恢复和实体编号源码。直接检查了T1/T2 XML、正则提交差异、S实际空间记录、F1 raw audit摘录、42数组字节目录、primary写出与检查顺序、资源退出窗口及trace事件原行。只用另写的标准库算术复核标量商、计数和费用；**没有执行仓库模块、项目测试、工作站支持driver或PDE。**

| 证据层级 | 本审亲读/复核 | 访问限制 |
|---|---|---|
| 固定Git源码与测试 | opt-in接线、实际observer/reader、A6/Gram公式、实体内部行编号、T1/T2异常及通过节点 | fixture中的模拟空间、解和A6不等于真实方程验证 |
| Git轻量记录及摘录 | S独立FE、F1 scalar审计、42成员dtype/shape/hash目录、prevalidation绑定、相邻退出窗口、trace事件、计费 | 摘录/目录不是全部原件的替代品 |
| 工作站ignored原件 | 已定位其固定路径/hash | **未亲读**primary NPZ、prevalidation NPZ、完整6904行资源流、完整1859行trace、全体原始源码快照及约1.9MB原raw审计/terminal |
| 模态中间文件 | 检查实际字段、标度约定及部分原行，与primary模态顺序和612计数的绑定路径 | 没有重新装配物理功率或枚举重算全部612行；本轮不以中间R/T作精度结论 |

下一轮实际消费原件时必须在受监控worker里核对它们；不得为了扩大本次审阅措辞而重跑F或C。[固定差异][diff]、[来源索引][index]。

## 3. 按严重程度排列的问题与处理

| 编号/严重性 | 代码或证据定位 | 结论、影响 | 最小处理/验收 |
|---|---|---|---|
| **V21-01／高，数值准入阻塞** | F1 `primary_raw_audit_excerpt.json`；`h100_anchor.py:5480–5790,8940–9360` | A6=2.1004005221911206e-8，冻结门1e-8；其他门通过不能替代。未发现能够据此直接定位根因的证据 | 保留FAILED；第9节从固定原包重算并定位。不得改阈值、重解、额外correction或用F2/C续接 |
| **V21-02／中，原因可识别性缺口** | `dtn_port_3d.py:4800–5290`；`hcurl_variable_p_reduction.py:590–850`；42成员目录 | A6与full-active采用不同算子求值路径、消元坐标及范数。相对残差约相差3.26万倍，不等于已证明某一计算错误 | 区分原式、变换后式和保存矩阵残差；先分块。没有A_ti/A_ii/C/Gram矩阵时不得声称完整Schur关系已数值闭合 |
| **V21-03／中，诊断映射限制** | `variable_p_entity_map.py:1–40,130–170,225–325`；`primary_byte_inventory.json` | all-p6内部行可由固定源码及现有global/box数据归属；独立trace行不能直接套p6 dofmap。42成员不含完整trace展开与局部消元映射 | 第9节构造并验算215格内部行归属；trace只报独立行索引，除非已有同身份显式映射。缺失映射标NOT_IDENTIFIABLE，不新构造约束补证 |
| **V21-04／低，测试与监督** | `test_task43_v21_r10_h67.py:1131–1140`；T1/T2 XML；正则提交 | reader确实提前拒绝混包，错误是期待旧文字。主控未发现该断言不匹配，造成一次可避免失败；修复不改变产品门 | 接受14+3逐项复用；不要求重跑旧17项。新checker测试必须验证原数组关联与真实失败值，不用mock PASS代替 |
| **V21-05／中，生产边界** | 新`r10_h67_diagnostic.py`；三个历史研究runner；F1失败留证路径 | 实现保持显式研究入口，未修改共享数值核心；但继续增加历史任务/固定路径绑定，不是通用生产runner | 本轮固定研究链有限接受，正常成功C/工程恢复路径未实跑。下一任务独立只读分析，不再向旧求解runner叠恢复框架 |
| **V21-06／低，证据范围** | F1 `root_numerical_stop.json`、`root_lifecycle_readback.json`、`artifact_index.json` | 原字节复核、退出后源码检查和连续运行中检查不是同一证据；空cache清单也不是共享cache稳定证明 | 保留当前限制。新diagnostic逐阶段保存自己的产物；不得回填旧worker成功end快照或给中间模态数据官方资格 |

上述高/中项是具体的数值与资格阻塞，不是宣布已查明求解器bug。本审没有发现足以把本次A6失败直接归咎于某一索引、符号、材料或MPI问题的确定性证据。也没有依据将它直接称为“舍入误差，可以忽略”。

## 4. 实现、T覆盖和H67空间

### 4.1 T修复与实际调用路径

`5796d78…`只把混包用例的期待正则由`saved raw-vector gates`改为`do not match the returned system`。T1 XML保留真实ValueError：full-active reduced RHS/solution/residual不匹配returned系统。T2 XML为runtime节点及同reader合法/混包两例3 passed。最终测试文件的执行方绑定SHA为`456d2c31f0b8b99d634bed2d0a05c6127b0f56d4d06aa4f2518a13e5c63bec5c`；运行提交到交付提交没有再改测试或源码。

`test_06`使用真实forest/plan与后置audit逻辑，明确交换global ID以避免把plan行号当global67；昂贵mesh/reduction authority被合成对象替代，因此真实FE仍以S为准。`test_12[False/True]`进入实际main/observer、原数组gate、共享writer与成功/失败terminal；实际A6计算及求解器被fixture替代，所以它验证接线而非原弱式精度。其A6/interior示例也不是证明两条真实装配路径逐项相同的证据。

F1实际先从同一live view提取恢复storage，写prevalidation；再调用独立A6；将同pass full-active、returned、normal前后及恢复数组写成primary；随后从原数组核门，写raw audit，再因A6失败抛异常。因此保存primary早于失败成立，Av和正式field capture的on-pass分支没有被绕过。[测试][tests]、[raw gate及observer][anchor]。

### 4.2 空间计数与闭包

| 量 | 核对值 | 解释 |
|---|---:|---|
| requested root | 127，对应原global67 | 唯一请求，box为[16.5,10,90]至[33.5,15,120]nm |
| forced roots | 129、130、131、160 | aggregate material closure=4，balance=periodic=0；没有逐事件原因轨迹，不细编因果顺序 |
| 叶数 | 180+7×5=215 | 8个请求子叶、32个闭包子叶、175个未分裂叶 |
| active interior | 215×450=96750 | p6单元内部模式数3×6×5²=450 |
| 独立trace | 42804 | 已含实际hanging/Floquet约束 |
| 独立FE | 42804+96750=139554 | 对R10增加20754，即17.46969697% |
| raw active/carrier | 151032=54282+96750 | inactive p6 rows=0；不等于独立FE |
| trace从属行差 | 54282−42804=11478=5544+5934 | 不能混用carrier端另记的5982 periodic行 |
| returned矩阵 | 42804+612=43416 | S是预测维数，F实测43416²；NNZ used/allocated=37660296/45453492 |

S的实际计数与F预装配、primary scope、矩阵实测相容；FE低于237600，只证明空间规模，不证明同精度。S以历史四个案例预测峰值/时限的工程包络，没有被当作H67实测。[S实际审计][space]。

## 5. 三类残差：已经确定与仍未知的内容

### 5.1 数值商与冻结门

| 量 | residual norm | RHS norm | 相对值/门 |
|---|---:|---:|---|
| 独立A6 | 2.2197718044678094e-8 | 1.0568326283561202 | 2.1004005221911206e-8 > 1e-8，FAIL |
| full-active变换范数 | 6.812408124146155e-13 | 1.0568326281891791 | 6.446061507221647e-13 ≤ 1e-8 |
| returned-condensed | 7.295067464183063e-13 | 1.0568326283561202 | 6.902765176289437e-13 ≤ 1e-9 |

本审用独立十进制算术核对商。A6与full-active分母相对差仅约1.57964e-10，不能用这一分母差解释约32584倍的相对残差差异；但这也不排除分子坐标/范数、独立求值与舍入传播的影响。normal从1.5364631556420623e-10降至6.902765176289437e-13，约缩小222.59倍，确为一次正常修正；extra为0。

### 5.2 原方程A6与变换后方程不是同一个数组公式

A6重新组装原弱式在恢复p6场上的作用，通过实际active实体及复Floquet/hanging约束的共轭转置投影，保留内部方程，并独立积分模态下行。记保存的体作用减体RHS为V，入射牵引为I，含负辅助幅度的端口作用为P_alpha，入射投影端口作用为P_inc，则：

```math
r^{A6}_t=V_t-I_t+P_{\alpha,t}+P_{\mathrm{inc},t},\qquad
r^{A6}_i=V_i-I_i.
```

A6 norm是独立trace、active interior、规范化modal gauge残差的Euclidean组合。raw modal原方程也保存，但不能拿它代替规范化modal行拼入冻结范数。A6 modal RHS为零，producer明确写入零数组，reader也明确拒绝非零。[A6源码][a6]。

full-active通过已组装的凝聚矩阵计算A_s x−b_s，trace部分使用保存的Gram逆作用；内部部分用同一局部LU及interior-from-trace关系计算。它是精确块消元结构下的残差检查，却不是独立重组装原弱式。returned保存b_s−A_s x，因此与full-active reduced residual必须相反号。内存中同一pass的Gram action保留在包内，不能将所有full数组直接Euclidean拼接。[恢复残差源码][reduction]。

若原系统分块为trace/interior，采用r=Au−b且所有量已处于相同约束/规范后，理论上有：

```math
r_S=r_t-A_{ti}A_{ii}^{-1}r_i.
```

这是解释坐标关系的恒等式，不是本次已由42数组验证的结果。包内没有A_ti、A_ii因子、完整C或Gram矩阵；只有各自作用后的若干向量。不能倒推矩阵或把A6 trace直接减Schur trace后称为实现误差。也不能把full-active中用于其自身残差的Gram action拿来当A6的Gram action。

### 5.3 已有绑定及下一步能排查什么

源码明确要求returned/full的RHS与solution相同、residual反号；normal后状态与returned相同；active-full解/RHS与恢复storage相同。primary内嵌record绑定源、plan、空间、模式和各数组，主控字节清单也报告prevalidation的11数组匹配primary。但本审没有访问原NPZ，数值重算须在第9节执行。

现有数据足以：重算所有范数与符号；重建A6已保存四项的代数组合；区分trace/interior/modal平方贡献；以真实global ID和all-p6编号定位215格内部残差；比较同坐标内部行的独立重组装结果与LU路径结果；量化相消；定位612个modal行及异常幅度。尚不能独立重验p6恢复系数到active系数的完整传递算子、所有实体约束C或局部Schur恒等式。

“数值门失败”成立；“究竟是独立路径舍入/相消、局部恢复、约束/规范、切断规则、实现不一致或实际代数误差”仍UNKNOWN。即使后续保存数组恒等式全闭合，也只能说原包内部一致、差异定位到某块；不自动排除未重做的装配/恢复算法问题。

## 6. 资源、退出、费用与权限

| 调用 | whole秒 | 原状态 |
|---|---:|---|
| T1 | 95.217966388 | 16 passed/1 failed |
| T2 | 9.091490977 | 3 passed，局部恢复 |
| S | 207.789824667 | 实际空间审计完成 |
| F1 | 4813.658310916 | 数值门失败 |
| 支持合计 | 312.099282032 | 3次，旧上限7次 |
| 全部合计 | 5125.757592948 | 4次实际调用 |

watchdog elapsed4811.279815596秒已包含于F1 whole，二者差2.378495320秒不是额外求解费用。采样RSS峰7900602368B约7.358GiB，低于32GiB；不是连续高水位。未计时静态检查/打包保持NOT_MEASURED，普通打包失败未变成新动态调用，旧失败不退款。

直接父关系的可见记录为worker3766301/start_ticks318082594→watchdog3766298/start_ticks318082517；strace3766305归该watchdog，外层supervisor3766204。采样/阶段的CPU1及线程配置与trace摘录一致。trace保存了3次成功设置CPU1的调用及匹配的SIGCHLD，不能称“没有setter/没有任何signal”。

退出窗口6900记录worker vanished；trace有worker `1793260640.532312 exited with 1`，MPI daemon随后退出0；6901起退出码1、后代为空，后续四行与host消失记录支持退出采样竞态，而不是活跃求解期间长期监控失联。接受这一限定解释，不声称本审亲读了全部资源/trace或连续所有时刻。F失败的原因是保存的raw gate异常，不是watchdog时限/内存杀停。[生命周期原行摘录][life]、[数值停止及连续窗口][stop]。

worker成功结束快照未到达，主控退出后的56项源码与20项输入核对单列，不能追填为worker正常end。共享cache监测为空，不赋cache资格。F1之后不启动C/F2/E符合V20数值硬停止规则：本轮正式累计10/12，历史末槽和未用F2均不因新诊断恢复。

## 7. 科学能力状态

| 能力 | V21审后状态 | 实际新增事实 |
|---|---|---|
| 空间 | PARTIAL | 固定H67的5根闭包、215叶与独立FE已实际构造 |
| 选择 | PARTIAL | H67没有合格场，收益未评价；accepted9与R10拒绝不变 |
| 精度 | NOT_PASSED | 独立A6失败；Av、J/G、q8/q10、独立参考/侧壁资格未补齐 |
| 同精度全过程成本 | NOT_ESTABLISHED | 失败费用完整记账不是同精度速度或内存优势 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 本轮direct研究不能授迭代资格 |

不得因FE比237600少41.2651515%、中间R/T有限或凝聚残差很小，宣称成功的自适应解。此次停止也不证明h方法或global67位置永远无效。

## 8. 各依赖组与合并资格

| 依赖组 | 文件/依赖 | 本次意见 |
|---|---|---|
| production numerical/core | 本轮未改共享数值内核；A6与消元实现为历史依赖 | 不因fixture或S/F局部实测新增生产资格 |
| reusable runner/watchdog | 共享watchdog/activation未改；研究launch及生命周期记录 | 具体调用有限接受，不授通用runner资格 |
| checker/benchmark | `r10_h67_diagnostic.py`、三个研究入口及固定合同/原件 | 显式research-only；成功C及各种恢复路径未在此轮实跑，不能迁成默认 |
| test-only | `test_task43_v21_r10_h67.py`及被调用fixture | 对应节点/字节接受；依赖环境、研究入口和原输入，不是孤立production包 |
| compact evidence/docs | V21正负证据、费用、原件索引及当前说明 | 可保留/供未来选择性审查；保留UNKNOWN及可见性限制 |
| do-not-merge | 大NPZ、未经验证恢复/选择器、整研究分支 | 禁止提升或整合 |

**无任何具体依赖组的实际merge approval。本次不合并；未来仍须明确审阅批准及用户授权。**

## 9. 下一轮唯一执行授权：V22 保存原数组残差原因诊断

### 9.1 明确批准的科学问题与边界

**批准现在开始最小实现、定向测试、一次实际保存数组诊断及有界普通bug恢复。目标是给出H67 A6超限的主要残差块、可解释的空间/模态归属、三种范数和同状态绑定的逐项结果，以及哪些Schur/约束关系因缺少原矩阵不能识别。**

固定对象只有本次失败H67，不换模型/位置/参考，不再分析R9/H8/P8/R10场收益。新工作是数值后验诊断，不混称纯静态文件读取。允许在编号driver中进行NumPy向量运算、范数、内积、保存几何分组及CSV/JSON写出。

**新增PDE、装配、矩阵/算子作用、LU/Gram逆/约束重建或应用、correction、native ABI探针、FE场恢复、采样、Av积分、q/R扫描、J/G或C比较全部为0。** 不导入dolfinx、Basix、UFL、PETSc、SLEPc、MPI或旧求解runner；保存Gram-action与其向量做内积属于读取既有作用结果，不是新施加Gram算子。不能通过旧FAILED-primary恢复入口打开C。

原F1始终失败；新诊断的“完成/算术复现通过”和“原A6通过”分别编码，绝不自动改后者。此次授权是从数值失败转入原因分析，不是允许数值失败后的正式重试。

### 9.2 静态准备、固定输入与允许文件

canonical worktree为`/home/fenics/Projects/NN-Lab-V2`。先安全fetch本review、核branch/upstream/HEAD/status及后续差异。保护其他任务，不reset、clean、强推。槽外只允许源码、既有JSON/XML/CSV、文件字节hash及路径/格式核查；实际NPZ数值读取进入D1/D2，不再出现槽外数组试算。

F1唯一原目录：`benchmarks/artifacts/task43/v21_r10_h67/formal/R10_H67_attempt1/`。至少冻结下列原件，原外层SHA是准入锚，不用新副本覆盖旧文件：

| 原件，相对F1目录 | 原SHA256 |
|---|---|
| `run/primary_state.npz` | `0ed1eada0a7d575ede4fdc8401371ffb2571a15c3b15c139ab5eabfda936beb5` |
| `run/pre_validation_checkpoint.npz` | `123132585c72d5a77ec5d510581173bf65af1a439db2f815a85de1c46abb9287` |
| `run/primary_raw_vector_audit.json` | `a3bb3216efd9c94c30970214ba04fd5738e13558c53a4bf2db5111408006e112` |
| `run/v21_f1_terminal.json` | `d2f86090d41857422e91fc7b4c71b2af1a20f136bde80a2ed81e3d7a7b3f84db` |
| `run/candidate_plan.json` | `38739c012870e3a878aafb764951d771293285fa45d46f535aa078bc5c295fc3` |
| `run/solve/dtn_port_diffraction_orders_3d.json` | `632d1a1dcf1f8aa96f8c03e9885c91777ffb8d918a7f589e112a15eaea338cfe` |

S审计及其180根继承/闭包JSON、F实际空间审计、上述字节清单/终态与固定源码作为额外身份和映射输入，从本次已提交索引逐一绑定，不扫描选择“最新”版本。原V21合同SHA为`4340377a1c96edd3f5ebb0605e647b3569b026f7d8a9c0527902ef0b6c093f6b`。只读取H67包；其他历史PDE数组不在本授权内。

允许新增：

- `benchmarks/task43_hp_adaptivity/analyze_saved_h67_residual.py`：仅stdlib/NumPy的只读checker；
- `src/test/test_task43_saved_h67_residual.py`：小型合成fixture；
- `outcomes/records/v22_saved_h67_residual_contract.json`及本轮results/sources/response；
- 第9.7节目录中的薄launch/快照及tracked文本副本；
- 必要当前README、summary、manifest、模型总账与进展更新。

不修改旧三个runner、`r10_h67_diagnostic.py`、共享数值核心/监控/activation/ABI、历史测试/合同/失败记录。可复用不导入native的原子写出和纯身份函数，不复制整套历史controller。新合同只冻结规则/输入/预算；每槽manifest另绑定实际HEAD和文件hash，避免自包含自身commit/hash循环。

### 9.3 第一产物：原包一致性与三个范数的独立重算

D1先验证42个数值数组及一个`__task43_record_json__`元数据成员的精确inventory、dtype/shape/内外hash、finite和范围；禁pickle/object、重复ZIP成员、无关额外数组。核primary中的11个恢复数组与prevalidation逐字节相同；核F1源HEAD、plan、contract、FE、模式顺序、normal/extra身份。原包非official与失败状态必须保留。

不调用旧`_v11_raw_vector_gates`冒充独立复算；新checker按第5节明确公式，重算A6、Gram full-active和returned范数/分母/比值，逐项对照旧raw audit。范数/商复现用`abs(new-old) <= max(1e-22, 5e-10*abs(old))`，只是本次复算一致性门，不改变1e-8/1e-9求解门。保留未裁剪的复内积实/虚部；若需要复现旧Gram微小负数处理，单列旧规则与原值，不用新裁剪掩盖异常。

必须逐数组验证：returned/full RHS与solution相同、residual反号；normal前后RHS相同，after状态与returned相同，normal一次严格下降、extra0；active-full解/RHS与recovered相同；modal RHS为零；full interior数组前54282行为零。将旧gate的false复现出来是诊断正确结果，不是再次启动恢复的理由。

另算同一full residual在不加Gram时的Euclidean值及其与Gram值的比例，只用来说明该向量的范数效应；不得据此计算不存在的A6 Gram范数。三个分母与分子分别列出，不把分母差、量纲差和原算子误差混成一个解释。

### 9.4 第二产物：A6分块、相消与可比较行的差异

按原producer括号顺序从保存V/I/P_alpha/P_inc重建trace、interior组合，并与保存A6 residual比较；同时用独立的实/虚`math.fsum`或等价补偿求和核查逐行组合。报告原顺序逐位是否相同、绝对差、相对于各加数绝对值总和的差；组合误差界取`64*eps64*max(sum(abs(terms)),tiny)`逐行。原顺序若不相同，必须解释具体最大行和量级，不能仅通过放大atol消掉。

交付trace、interior、normalized-modal三个块的norm²、占A6总norm²比例、最大行、top1/5/10/20及正负实/虚分量。对trace四项列各自norm、完整Hermitian内积交叉项和相消比；对interior两项作同样检查。交叉项求和与合成残差平方的校验必须使用对加数规模敏感的浮点误差界，不能用很大的固定绝对容差制造微小残差的通过；这项恒等式不证明原组装舍入误差就是原因。

可以数值比较的同坐标内部行是：A6 interior的96750项与full interior数组去掉54282个raw trace前缀后的96750项。输出它们的差、相对规模、每单元分布。只有在源码/记录明确两者均为同一active interior、同一Au-b符号后才比较；不得错取42804作为full interior起点。

端口交付全部612行，使用primary的实际有序mode keys与中间modal JSON的auxiliary_index交叉绑定；列raw modal、normalized A6 gauge、full reduced modal尾612项及returned反号关系。规范确实相同时才把独立积分与矩阵modal残差之差称为跨求值路径差。原记录若保存D及surface moment，可只读核`D*alpha-moment`与gauge；若没有，明确`D_OR_MOMENT_NOT_SAVED`，不得通过raw/gauge相除制造“独立”D，也不调用模态函数重算。

V_t已经减过体RHS，且包内没有独立linear-vector副本。允许从保存rhs和端口/incident量导出一个隐含体RHS，但必须标`DERIVED_NOT_INDEPENDENT`，不能将定义回代称为独立RHS闭合。没有A_ti/A_ii/C/Gram原矩阵时，完整Schur/恢复等价性标`NOT_IDENTIFIABLE_FROM_SAVED_PACKET`。这些缺项不能触发擅自重装配、求解或新算子作用。

### 9.5 第三产物：215单元及约束归属的可靠范围

本次all-p6每格内部450行。固定源码按拓扑维度及global entity ID连续编号，故在核实MPI1、global cell IDs为0..214的双射、215格均p6、raw trace前缀54282后，可使用：

```math
\text{A6 interior rows of cell }g=[450g,450(g+1)),\qquad
\text{full interior rows}=[54282+450g,54282+450(g+1)).
```

用保存的`mesh_owned_cell_global_ids`关联geometry dofmap行，依实际8顶点坐标得box，再与冻结S根/叶JSON做唯一包含核对。global ID、数组slot和forest root分别记录，不拿plan行号当global ID；不调用native几何搜索。核8请求子叶、32闭包子叶、175未分裂叶及体积覆盖。

输出完整215行：当前global/slot、box、parent root、p、内部行区间、A6内部norm²、LU路径内部norm²、两者差norm²及各自占比。汇总请求root127、四个closure root分别及其总和、其他175格；完整加和应复现第9.4节块norm。该表是方程残差归属，不是场误差估计、R00局部误差或h收益。

独立trace42804行并非p6 carrier trace54282行；禁止按p6 dofmap或几何排序直接给其贴边/面标签。仅当已有同身份的显式trace-row/实体/约束映射存在于冻结原件中，才可读取并分组；其覆盖、无重复/无缺失和共轭方向必须核实。没有映射时交付独立行索引top表与缺少的具体映射名称，保留`TRACE_ENTITY_MAPPING_UNAVAILABLE`，不重建C。这不阻止完成其他已授权分析。

### 9.6 定向测试与诊断分类

T1最多12个展开节点，只覆盖新checker，禁止重跑旧17项或native测试。至少覆盖：真实NPZ读取与内外身份；错RHS/解/符号的合法重绑反例；Gram范数与Euclidean差异；modal零RHS；小型4项/2项组合与相消；all-p6内部编号及打乱global/slot；trace错当carrier的拒绝；完整main写出与后段失败保留已完成块；原数值gate=false但诊断可以完成。输入身份反例不能仅靠未重绑的坏hash碰巧拒绝。

合成测试允许小尺寸scope，正式CLI只接受固定生产尺寸/合同；测试不得整体mock受验loader、范数或分组函数。不执行任何原模型阵列读取来准备fixture。T1通过后可直接D1，无需再等待review。

最终分类分开保存：

- 原件/状态/符号关联存在真实不一致：保存具体数组和索引，标`SAVED_PACKET_INCONSISTENCY`，停止受影响推断，不改原件；
- 复算一致且原A6失败：标`A6_FAILURE_REPRODUCED`，继续完成主要残差块及可信映射分析；
- 主要跨路径差位于interior/trace/modal：列全部块比例，不强行只有一个原因；
- 仅能定位而缺矩阵/映射：标`CAUSE_LOCALIZED_OPERATOR_PROOF_UNAVAILABLE`，具体列出缺失对象；
- 不得从相消大直接宣布舍入根因，也不得从恒等式闭合直接宣布求解器/独立A6实现全部正确。

必须给出一个按证据优先级排序的技术结论和最小待查对象；下一轮只交该诊断，不在其末尾自动启动验证PDE。科学上未能唯一归因是有效结果，不是使用恢复槽换输入或放大容差的理由。

### 9.7 唯一命令、root、次数与资源预算

唯一新前缀：

`/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v22_saved_h67_residual/`

外层命令只能为`bash <上述绝对前缀>/launch/stage_launch.sh <STAGE>`，STAGE只能取下表之一。冻结后调用；root排他创建，拒绝已存在非空目录/符号链接，不删除失败目录、不加attempt3。新checker的唯一科学入口为：

```text
python -u -m benchmarks.task43_hp_adaptivity.analyze_saved_h67_residual
  --manifest docs/task43_hp_adaptivity/outcomes/records/v22_saved_h67_residual_contract.json
  --output-root <本槽root>/data
```

| 新槽 | 前缀下唯一root | 次数/条件 | 工作停止/whole含清理 | RSS |
|---|---|---|---:|---:|
| T1 | `support/targeted_attempt1/` | 1，最多12节点 | 270/300秒 | 8GiB |
| T2 | `support/targeted_recovery1/` | 至多1，仅T1已定位普通bug，最多6受影响节点 | 270/300秒 | 8GiB |
| D1 | `support/residual_diagnosis_attempt1/` | 1，T门通过后的固定原包分析 | 540/600秒 | 8GiB |
| D2 | `support/residual_diagnosis_recovery1/` | 至多1，仅D1普通checker错误；同worker最多6节点验证后续接 | 540/600秒 | 8GiB |

**新增支持最多4次、whole累计1800秒；新增正式槽0、正式调用0。** 18.7MB原primary和小型向量运算不需要旧F的小时级预算；本上限含首次读取、校验、记录和监督，不是保证完成时间。T2/D2不互换，旧V21未用T3/F2/C/E不能挪用；外层shell开始执行即计数，包括watchdog前失败，失败不退款，剩余秒数不换次数。

CPU affinity严格[1]，单worker，不调用mpiexec；六个数值线程变量均1，`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`仅worker-local。使用已有资格化activation绑定的解释器/NumPy，不改共享环境，不跑native ABI。RSS取8GiB与既有dynamic available/reserve门的较严值，保持至少64GiB/15%系统余量规则；task VmSwap=0，全局swap另记。禁止heavy并跑。

复用已验证watchdog/strace-D组织，记录实际直接父PID/start_ticks、TracerPid归属、可见TID affinity、原资源流和全部trace。已解释的CPU1 setter、与子进程退出匹配的SIGCHLD不自动失败；非CPU1 setter、活进程/TID偏离、未知信号/解析遗漏是硬门。whole末尾仅用于TERM/KILL/reap和留证，不延长科学工作。异步launcher返回0不代表完成，必须读worker/watchdog/supervisor最终退出及清理。

### 9.8 普通bug恢复、硬停止与逐阶段持久化

**静态准备→T1/必要T2→D1/必要D2→主控复核→整体交付可连续执行，不逐阶段等待新review。** 槽外普通文本路径/字段/JSON错误可局部修复留痕；不借此打开原数组试算。

T1若是新增fixture/字段/索引/序列化普通错误，允许修复、提交新字节后用T2只补相关节点；未变节点逐项复用。T2仍不通过则不启动D1。D1若是新增checker普通实现错误且原件身份、资源、清理完整，允许D2：同一受监控worker先运行最多6个受影响测试，再运行同输入分析，不另起未计数pytest。算法变化则从同一原包重算受影响派生部分，D1已完成且未受影响的产物可显式hash绑定复用；全部写到D2新目录。

按顺序原子保存：输入/数组目录→三个范数→A6块/相消→215格及612模态→缺失映射与结论。后段失败保留前段字节与原异常，完整状态为INCOMPLETE且无原F资格提升。不得因为原A6仍大于1e-8退出到一半而不做已授权原因诊断。

外层hash/源/输入漂移、非有限或错布局原数据、未知退出、CPU/RSS/swap/时限、父链/tracer异常、必需原件不可信、无法清理，立即停止受影响链，不能用D2绕过。若已绑定原包内真实RHS/解/符号关系矛盾，保存最小证据并停止依赖该关系的推断，不通过重绑原件或放宽比较修复。新checker自身的公式自检失败只有被源码和小fixture明确定位为普通实现错误、且输入/资源硬门均完整时，才可使用剩余对应恢复槽；实际数据的不可解释闭合失败不能默认为软件bug无限重试。

原F1保存的数值gate=false、无法取得完整C/Schur矩阵、无法唯一判定舍入来源，都不是新资源/身份失败；按限定范围完成诊断并交付未知即可。任何诊断成功不解锁F2、C、Av、额外correction或正式重试。

### 9.9 交付、主控复核及仍锁定的工作

新增`response_v22.md`、`outcomes/records/v22_saved_h67_residual_results_v1.json`和sources，包含完整三范数表、块norm/交叉项、215格内部行表、trace行top表、612模态表、同状态/符号/编号核对、原始假设与缺失对象、每段产物hash及失败。所有表须能从保存实值独立加和，不只交PASS和hash。

主控在启动前审新合同/脚本与实际源码差异；完成后亲读完整CSV/JSON、原trace/逐行资源/清理，并用标准库复核落盘表的加和、商和分组。槽外不得二次打开NPZ或调用原checker产生“独立重算”；若需原数组运算，只能在已有编号D槽内。记录精确运行HEAD与最终交付HEAD，混合历史节点不称最终全套；所有失败和whole互斥计费，内层时间不重复加，未计时静态工作保持NOT_MEASURED。

只更新当前导航、summary、selective merge manifest、模型总账和进展，不重写历史review、合同、accepted9/R9、R10拒绝、F1 FAILED或中间612输出身份。正式账仍10/12，历史末槽封存，原V21未用正式与支持槽在本授权中均锁定。无新PDE、correction、FE恢复/采样/积分、矩阵或算子作用、q/R扫描、其他seed/模型、迭代、0.7nm、NN/FTT、环境重建或合并权限。

## 10. 提交声明

本次仅新增`docs/task43_hp_adaptivity/review_report_v21.md`。完整review SHA由提交产生后回读给出，不在文件中自包含自身SHA。远端API写入和内容回读与GitHub页面视觉渲染分开陈述；未完成视觉检查时明确NOT_VERIFIED。本审没有运行项目测试、支持driver或PDE。

[diff]: https://github.com/Rookie1234567/MyFEniCS/compare/0dd5555f8795a68c7c9b1dc58387337d98fd76a5...a4fa1f536fbed152bc0bd4746cbdd545895018a6
[index]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_sources/F1/artifact_index.json
[tests]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/src/test/test_task43_v21_r10_h67.py
[anchor]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/benchmarks/task43_hp_adaptivity/h100_anchor.py
[a6]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/src/solvers/dtn_port_3d.py
[reduction]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/src/solvers/hcurl_variable_p_reduction.py
[space]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_sources/S/root_independent_audit.json
[life]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_sources/F1/root_lifecycle_readback.json
[stop]: https://github.com/Rookie1234567/MyFEniCS/blob/a4fa1f536fbed152bc0bd4746cbdd545895018a6/docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_sources/F1/root_numerical_stop.json
