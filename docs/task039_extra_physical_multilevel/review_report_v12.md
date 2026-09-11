# Task39extra Review V12：一次性调整局部库存预算，完成现有宏块PC的真实三维验证

## 0. 仓库身份、审阅结论与执行权限

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-11
reviewed_HEAD              = 45c877a3b66516674dd68a799870549ec52d28b0
last_measured_source       = 7c936958451bc196f784ecc30db9278c4e5b402f
original_task_base         = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_materials         = review_report_v11.md / response_v12.md
new_profile                = physical_macro_dd4_v12
memory_allocation_policy   = SYMBOLIC_SIZED_LOCAL_MUMPS_V11
local_inventory_cap_bytes  = 2684354560
execution                  = O0 -> O1 -> O2 -> conditional O3 -> O4
response_required          = response_v13.md
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

**本轮消除的blocker：现有多单元物理局部逆仍未得到完整p4/p6数值检验，最近一次只因最后一个局部块的保守库存请求略超人为设置的2 GiB组件预算而停止。现在一次性将新profile的局部库存预算设为2.5 GiB，在整机安全线不变的前提下完成已有方法的真实检验，不继续为约29.3 MiB差额另开内存优化研究。**

首先纠正结论：V11通过的是代表块的新旧分配策略等价性和41个局部块的回代检查；不是“完整PC已证明可行”，也不是“子域法已经收敛”。这些块来自13.5 nm真实离散，但完整p4近似逆、p6外层、框架与restart对照均未运行。V5准确p4 LU支持的原始/notch成功继续保留；它与本轮候选资格分开。

用户本轮明确要求继续真实测试并写review。本文只对新profile覆盖V10/V11的2 GiB局部库存限制、终止后的执行许可及新批次预算；一次性提高到2.5 GiB，不追溯改判旧记录。局部矩阵、42块、2600行限制、MUMPS配额公式、四步I4、精度、整机安全、参考隔离、分支规则不变。原任务与V10/V11未被本文覆盖的条款仍生效。目录盘点未见额外补充task文件；不能把历史summary的“继续”当作额外授权。

最终目标仍为约2 TB整机物理内存内，0.7 nm、complex128、Nedelec H(curl)、双Floquet、Fourier-DtN、任意非可分三维周期单胞散射。本轮是13.5 nm笔记本研究，不是2 TB/0.7 nm资格；不等待、不重复、不修改同步进行的5 nm分支、目录、进程或预算。

## 1. 接受的V11证据与本轮调整依据

来源：[Response V12](response_v12.md)、[V11中心结果](outcomes/macro_memory_lifecycle_v11.md)、[V11 compact](outcomes/records/macro_memory_lifecycle_v11.json)、[独立N2审计](outcomes/records/v11_n2_supervisor_audit.json)。下表不是本review重新运行的结果。

| 内容 | 已有值 | 数据身份与边界 |
|---|---:|---|
| 完成局部块 | 41/42；index 41 numeric前停止 | measured构建进度，不是p4/p6收敛率 |
| 41块局部回代 | 82次，最大相对残差2.1772149386553977e-15 | measured局部检查，不是完整p4场误差 |
| N1同RHS旧/新解差 | 0.0；最大局部残差5.438606648780365e-13 | 两个代表块上的策略等价性 |
| block 0/1 allocated旧→新 | 262→53 MB；261→51 MB | 后端字段加取整余量，不是整机RSS |
| 41块allocated / CSR / base-shared | 1,643,000,000 / 443,371,460 / 45,710,148 B | 保守库存组成，不能换成used |
| 41块累计库存 | 2,132,081,608 B | derived inventory |
| 最后块当前矩阵 / Q请求 | 7,128,340 / 39,000,000 B | 矩阵与Q各只加入一次 |
| 最后块numeric前包络 | 2,178,209,948 B | derived请求，非42块完成后实测常驻 |
| 旧cap / 超额 | 2,147,483,648 / 30,726,300 B | 2 GiB / 约29.3 MiB；不是系统OOM |
| N2进程树RSS峰 | 1,918,558,208 B | measured watchdog；阶段采样1,918,562,304 B另列 |
| p4 I4/B4及p6外层 | 0次；未运行 | 不存在本轮残差迭代曲线 |

新cap为`5 * 2**29 = 2,684,354,560 B`，恰为2.5 GiB。与最后块请求的差为506,144,612 B，属于新授权的研究库存余量，不是保证实际运行还剩这么多内存，也不是所需内存的统计置信界。

2 GiB是组件工程预算而非用户16 GB机器的全部物理上限。V11已用41块数据消除了原先大额配额的主要疑点；此时继续压最后一点库存，不比尽快取得数学结果更优先。Codex按原合同停止正确，旧V11保持`LOCAL_INVENTORY_RESOURCE_BLOCKED`。不得用新cap将旧结果改成PASS，不宣称“内存减少/预算增加证明算法有效”。

## 2. 唯一资源变化：显式profile的2.5 GiB局部库存

### 2.1 必须逐层传递，而不是修改所有旧profile共用的常量

新增显式`physical_macro_dd4_v12`，通过dat/resolved config/contract向builder、pre-numeric、post-numeric、post-backsolve、complete-inventory、checker、manifest传入整数`local_inventory_cap_bytes=2684354560`。可用带旧默认值的参数或等价版本化配置实现；V10/V11默认仍为2147483648 B。禁止仅把某一处报错常量改大而遗漏其他门槛，或偷偷提高所有profile。

保留V11的`SYMBOLIC_SIZED_LOCAL_MUMPS_V11`配额策略及其E/Q公式、ICNTL(23)读回、ordering/scaling/pivot/refinement/full-rank/in-core设置。局部单实例的matrix/factor/转换/工作区预算仍为512 MiB；S/p2仍受8192总行及512 MiB约束。不升级PETSc/MUMPS，不再为已确认不支持的ICNTL(49)重新下载手册、探测私有地址或更换ABI。

默认继续累计allocated保守量、CSR与原有shared/index库存；保留used作为并列观测。禁止用used、min、factor_nnz乘16、单次RSS差或更小的E替代既定账/本次Q请求来放行。此前字段语义核验直接复用，当前加载库身份仍做轻量确认。

### 2.2 整机硬安全不放宽

| 资源层次 | 本轮规则 |
|---|---|
| 新macro局部库存 | 仅新profile2.5 GiB；numeric前、后、回代后和完整库存均检查 |
| 局部临时预留 | 仍1 GiB；进入整机检查，不能挪作额外常驻 |
| 单块行数、分块 | 总行数不超过2600；42块及原索引重叠不变 |
| 小型S/p2底层 | 总行数不超过8192；512 MiB预审不变 |
| 系统reserve | max(4 GiB, 15% effective_total)；有效内存按物理/cgroup可见限制取小者 |
| launch cap | 不高于min(12,000,000,000 B, effective_available - reserve)；沿现有合格实现计算有效available |
| 运行监控 | 全过程同期process-tree/cgroup、MemAvailable、job/global swap、磁盘、所有后代；一次一个heavy |
| 优先级 | 硬安全先于保存/审计；不能为完成第42块越整机线 |

先做一张完整生命周期表：局部全部矩阵/因子/缓存、C_U与S/p2、p6/p4空间与传递、DtN/H6、四维内部基、32/64外层基、构建临时量和恢复包。逐项标明同时存在阶段、measured/derived/predicted及来源，不把各阶段历史峰值相加，也不将当前1.919 GB当成完整外层峰值。

新cap不足或整机资源不足时按确切阶段停止；不自动再升到3/4 GiB，不删块、不缩模式、不切ILU/OOC、不增加swap。新授权解决的是已识别的组件预算边界，不预先保证后续所有门槛都能通过。

## 3. PC数学合同：不换方法，真正完成未检验的组合

### 3.1 全局物理与局部块

冻结原始13.5 nm、1度grazing、azimuth0度、s偏振，50×25 nm周期、z=-10到130 nm、原Si/air损耗、p6/h10、252六面体、80模式、complex128、MPI1/线程1。原physical SHA：`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`；ordered mode SHA：`dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。新input/source SHA另算，不硬填旧值。

p6独立维度N6=164592、存储行173802；p4独立维度N4=48960、存储行53084。P64为N6×N4的合法primal延拓，其共轭转置限制dual右端。真实A6/b、native/cached A4、体积分与DtN、约束、积分阶次和相容传递不变。

```math
A_6x=b_6,\qquad A_4=P_{64}^H A_6P_{64}.
```

保留V10固定2×2×2种子分组及边缘不足两格的分组，共42块；包含所触及的全部p4独立坐标，经Floquet主从映射去重。相邻块共享边/面坐标形成代数重叠；不是增加一整层几何重叠，也不是恢复全横截面slab。局部矩阵包括所选基函数在种子组之外的完整支撑贡献和适用的原DtN限制。

```math
R_i\in\mathbb C^{n_i\times N_4},\qquad
D_i=R_iA_4R_i^H,\qquad
M_D r=\sum_{i=1}^{42}R_i^H W_iD_i^{-1}R_ir.
```

W_i为原输出端1/multiplicity权重，输入端不再加权。局部LU在每场独立运行setup时构建一次，后续反复回代；不得每次PC重新分解42块。小块解准不代表加权和就是A4准确逆，块外耦合仍需整体处理。

### 3.2 p4两级PC与四步内部迭代

保留实际C_U：`complete_pq`、单元内部响应、相容W/P传递及S/p2底层组成的纠错作用。它不能被误换成“同shape的简单原生p2逆”。新局部M_D替代旧高阶实体逆，不再同时常驻旧1566实体/full252因子。

```math
\mathcal B_4^{DD}=C_U+(I-C_UA_4)M_D(I-A_4C_U).
```

一次作用按`a=C_U r; h=r-A4 a; d=M_D h; result=a+d-C_U(A4 d)`执行，所有中间量为p4向量。公式是作用关系，不形成任何N4×N4稠密矩阵。这个B4符号是预条件器，不是旧的正定B6辅助物理矩阵。

每个A4 c=g使用right FGMRES、零初值、至多4次新B4_DD作用、一个4维周期，无recycling/跨RHS热启动。1e-4只作内部提前返回目标；有限、合法、无breakdown但未达目标的近似可返回，记录native A4残差eps=g-A4 c。25秒请求安全返回、30秒费用线及原deadline/可见回调不变。不得加到8/16/200步凑内层通过。

### 3.3 p6外层与唯一框架对照

记I4为上述有限内部求解过程，可能因Krylov系数和提前返回而非线性，不能将它当作固定准确逆矩阵。对同一外层PC输入q：

```math
\begin{aligned}
g_1&=P_{64}^Hq, & c_1&=I_4(g_1), & z_c&=P_{64}c_1,\\
s&=H_6(q-A_6z_c), & g_2&=P_{64}^HA_6s, & c_2&=I_4(g_2),\\
z_{BAL}&=z_c+s-P_{64}c_2, && z_{ONE}=z_c+s.
\end{aligned}
```

H6保持已合格的正定辅助平滑；不恢复旧H6-p4-H6逐段MR。BAL_H每次两次I4，ONE_C一次I4，两者共享控制前缀。局部两级PC是局部/全局两种修正的固定组合，不是再增加两套必须收敛的循环。

```math
P_{64}^H(q-A_6z_{BAL})=\epsilon_1-\epsilon_2,\qquad
P_{64}^H(q-A_6z_{ONE})=\epsilon_1-g_2.
```

分别报告等式闭合误差与右侧实际范数；闭合小只说明实现一致，不能说明PC强。外层FGMRES组合多次PC方向以求原A6方程，不是每次机械执行x+=z。

## 4. O0–O1：复用已完成的检查，进入真实p4作用

### O0：短预检、profile与剩余接线

读取根/docs适用AGENTS、工作原则、task、本review及V10/V11，核对canonical worktree、branch/upstream、HEAD、clean、ABI、材料/mesh/map/mode、可见内存与watchdog。旧schema中已绑定的MUMPS版本/ICNTL49限制复用，不重做N0/N1校准、不重建p6/p4全局直接参考、不补跑旧账。

将新cap作为显式profile参数贯穿所有资源Gate及checker，保存旧/新阈值与来源。完成此前已授权但尚未运行的`build_w_transfer`、recursive map、cached/native A4、C_U、四步I4、BAL_H/ONE_C、真实FGMRES与正式输出的通用接线。现有`outer_execution_enabled=false`不能成为只交builder的理由；也不能只改成true就冒称实现全部完成。

先用现有计数和41块记录审阅完整工作集。新动作统一通过`python scripts/run_case.py input/path/to/case.dat`，一个dat只表示一场确定的控制/probe/正式计算，source与input身份均落盘。求解核心在`src/solvers/`，runner只编排、checker只独立核算，不新建一套庞大的task专用框架。

### O1：42块完成、少量同输入检查、一次框架选择

旧进程已经退出，41份在内存中的因子不再存在。没有已合格的持久化格式时，在新进程重建全部42块并记入fresh成本；不得把compact当作因子文件，也不为此开发新序列化/OOC系统。同身份的现有合法单元/映射数据可复用。

每块保留既有两个回代检查、代表native witness；这是新实例构建资格，不是重跑old/new内存策略校准。先完成全覆盖、局部/native、cached/native、C_U与传递检查，再执行完整PC；任一必要实现失配应修复并以新clean SHA重测受影响项，不降低门槛。

资源通过后连续执行V10第4.1–4.3节：至多六份已有g1/g2检查真实A4残差、匹配p4场误差及scaled-curl；至多三份已有合法q共享计算两种框架方向，共至多12次新增I4。已有reference只在评价端，不进入PC或初值。q与真实误差的关系及归一化需核对；缺匹配参考时标`REFERENCE_UNAVAILABLE`，不重建全局LU，不取消不依赖该参考的合法试跑。

框架选择继承V10：至少两个有效真实误差样本时，ONE/BAL的剩余场范数比几何平均不高于0.80、最大不高于1.10、scaled-curl几何平均不高于1.10、原A6残差比几何平均不高于1，且ONE/BAL完整作用时间不高于0.80，才选ONE_C；否则用BAL_H。近零共同输入尺度处理、阈值性质与V10一致；它是一次工程选择，不是一般最优性证明。

不要求裸PC单次残差小于1，不要求每个I4先达到1e-4。连续两次非零输入没有合法方向，或持续触及原30秒I4成本线，按原成本合同收口。不得在这一步因为只取得局部PASS而主动结束；必要正确性/安全/成本通过即进入O2。

## 5. O2–O3：直接在13.5 nm完整三维原始模型上裁决

### O2：同PC、同初值的restart32/64有限对照

保持O1所选框架、固定DD4、相同正交化、相同原A6/b，分别启动right FGMRES32和64，从零初值开始，无复用池。各最多64步、solve2400秒、workflow3600秒，顺序执行。前32步的解与真实残差在原数值容差内应一致；不一致先查状态/身份，不把它解释为restart差别。

每8步保存真实残差、每32步安全解和资源/操作计数。比较32/40/48/56/64共同节点及同一时间附近实际节点，缺失不插值；真实场误差使用已有同离散参考且只在评价端。restart64前64步不重启，不代表后续无限unrestarted。

两者都到64时，只有restart64/restart32的终点真实残差比不高于0.50、到64步时间比不高于1.25且资源合格，正式选64，否则选32。未到64时归因标`INCOMPLETE_AT_COST_CAP`、默认32；两probe都在2400秒内未到48步时按`WHOLE_PC_COST_NOT_VIABLE`收口，不追加长跑。这些是V10/V11既定投入规则，不因本轮结果修改。

如果某probe已经达到最终残差并完成全部合格输出，直接作为实际original成功进入notch，其余重复运行记`not_run_goal_met`。不得为了表格完整重跑已经完成的同一目标。

### O3：一次选定配置的正式original及条件notch

若O2未已成功且继续条件允许，按选定框架/restart及同一四步I4进行至多一次fresh original，从零初值开始。max2048，每8步及退出检查原A6真残差，每32步checkpoint。沿原时间投入线：首个约1800秒安全点rho>0.10停止；约5400秒rho>1e-3停止；否则最多solve10800秒/workflow14400秒。成本包括全部嵌套调用和诊断，硬安全优先。

original完成完整数值/物理检查后立即用同配置运行冻结的非可分缺口；重新构建实际材料相关对象、块因子、C_U和参考身份，不能套用原始结构专用packet。缺口仍为V5的8个cell keys与材料实体，不改变形状、块、模式、restart、I4设置。缺口失败保留范围限制并收口，不切另一个框架重新调参。

因此本批最多两个真实original短probe、一次选定配置fresh original、一次条件notch。重复前缀和各场fresh setup均计费，不包装成只跑了一场；不因诊断而无限增加测试数量。

## 6. 最终验收：组件构建通过不是终点

| Gate | 固定要求 |
|---|---|
| 每块限制/回代、代表native | 原1e-10门槛；42块新实例、完整覆盖与正确Floquet语义 |
| cached/native A4 | 原相对1e-11及输入不变、约束、相位要求 |
| 框架闭合 | BAL的eps1-eps2或ONE的eps1-g2按操作尺度1e-8；真实不平衡另报 |
| p6原方程 | norm(b-A6x)/norm(b)不超过1e-6 |
| 同结构匹配场 | L2/scaled-curl相对差不超过1e-4；复E/H及同坐标近场，不拟合整体相位 |
| R/T/A及体吸收 | 与各自同结构参考绝对差不超过1e-5 |
| 独立守恒 | R+T+A_volume与1之差、A与A_volume之差不超过1e-5 |
| 全部80模式 | 复幅值向量相对差不超过1e-4；逐通道功率最大绝对差1e-6 |
| 资源与复现 | 新2.5 GiB局部库存、原整机安全、完整process-tree与swap、时间、source/input/artifact SHA |

未达p6残差的解可作diagnostic场误差，不发布official R/T/A；不同结构不互作参考。V5两结构成功、旧参考448页global pswpout归因限制保持。小残差和守恒不替代h/p精度资格，本轮不声称0.7 nm或所有非可分几何通过。

成功后保存最小recovery packet，释放KSP/PC/局部及底层因子和无用矩阵，核对RSS再恢复输出，全过程计入资源。仅输出工程错误时可从同一已合格解恢复，不重求场来掩盖问题。

## 7. 预算、停止和交付

| 范围 | 新批次投入上限，非预计耗时 |
|---|---|
| O0/O1全部必要接线、测试、预审、构建、有限控制 | 7200秒；其中局部构建3600秒、有限数值控制1200秒为包含关系；不另开N1校准 |
| O2两个probe | 各solve2400秒/workflow3600秒 |
| O3 original与条件notch | 各solve10800秒/workflow14400秒 |
| 全批实际计算账 | 43200秒；小阶段或硬安全线先到先停 |

新账不继承V11名义剩余2342秒。父子包含关系、实际计算、实现活动、等待/文档、reserved与unknown分别登记；不靠补跑旧数据填账。必要provenance与raw日志完整保存，但不继续为秒级边界、已知库功能或表格措辞开启新数值调查。

允许修改新profile及cap参数接线、必要算子/框架/输出接线、focused tests与文档；不改变旧默认。禁止新数学PC、更多块/重叠/权重扫描、ILU/BLR/mixed precision/后端更换、全局p4/fine LU、全局稠密矩阵、扩rank/长内层、无限restart、5 nm/0.7 nm重型运行。已核实的ICNTL49不可用不是重开接口研究的理由。

安全不足为`RESOURCE_BLOCKED`，新局部库存超过2.5 GiB为`LOCAL_INVENTORY_RESOURCE_BLOCKED`；实现失配、MUMPS工作区错误、数值残差不达标、成本受控停止和证据缺口分开记录。不得因这些状态自动升cap或补一条新候选。正确性/安全/费用允许时O0–O4连续执行，不逐项停审；达到明确终止条件才集中收口。

O4提交`response_v13.md`及一个简明中心结果、compact、run index、test summary、development progress/model registry、handoff和selective manifest。至少列清：42块是否完成；p4误差/残差与费用；BAL/ONE差别；restart同节点/同时间证据；original/notch及各自参考；全流程峰值与构建/内层/外层/后处理成本。未运行写具体原因，不能只交PASS数量。

建议普通commit顺序：新profile/cap与剩余通用接线及测试；明确工程修复按需单独commit；数值结果与response收口。正式运行使用clean SHA；不amend、不强推、不合并master。旧push被拒的历史描述保留，但当前远程已可读45c877a；最终报告实际同步状态，不让用户为已存在的提交重复排错。

focused tests至少覆盖新profile精确2684354560 B、旧2 GiB默认不变、全部pre/post Gate接收同一cap、真实整机cap不变、预算例子重算、无重复计账/销毁、原配额策略不变、四次I4实际计数、ONE/BAL正确残差关系、restart前缀状态隔离、dat和official输出门槛。最后改动后重跑相关tests、静态及Markdown合同；保存raw stdout/stderr，不将历史Ruff差异审计写成全库Ruff/CI通过。

**这轮的交付问题是：在安全的2.5 GiB组件预算内，现有宏块PC能否以可接受总成本求解13.5 nm真实三维问题？不是再证明某个局部LU能解准，也不是维持最低RSS纪录。**

## 8. 依据与适用边界

仓库依据为[原task](task.md)、[V10](review_report_v10.md)、[V11](review_report_v11.md)、[Response V12](response_v12.md)、[V11中心结果](outcomes/macro_memory_lifecycle_v11.md)及其compact；算子与构建入口为`src/solvers/physical_macro_dd4.py`、`physical_bounded_runtime.py`、`physical_balanced_coupling.py`和`fullspace_bounded_mumps.py`。新算法不藏在benchmark中。

方法说明可核对PETSc官方[PCASM](https://petsc.org/release/manualpages/PC/PCASM/)与[KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：Schwarz允许局部求解器，FGMRES允许不精确/非线性内部预条件。在线文档只用于原理说明，不代表本机已具备最新接口；理论上的允许性不保证本候选收敛。

本轮即使成功，仍保留S/p2底层增长、更多子域的全局纠错、DtN/传递分布、局部因子总库存和h/波长鲁棒性的后续任务。局部因子可以是有界实现工具，但不能用本机固定案例或一次预算调整推导2 TB下0.7 nm任意三维已可行。
