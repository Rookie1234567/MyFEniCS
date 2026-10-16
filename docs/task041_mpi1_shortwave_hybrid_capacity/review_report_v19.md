# Task041 Review V19：批准一次四次B作用的定向捕获，不恢复完整M400

## 0. 裁决、身份与额度

**接受V18离线分解的限定结论；批准一次新的诊断性构造额度，用存档S_B、冻结PC输入，捕获两侧y/q共四次固定B作用及其组合/投影。允许为此重建一套必要的两侧B/P4依赖，但不重新生成QEP、不构建任何新S_B列、不运行外层或完整物理场。V15判据及旧失败不变。**

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                = 2026-10-16 Asia/Singapore
reviewed_HEAD              = e287c367fd2d37c62a5d31230968c86fd3353b14
reviewed_response          = response_v19.md
previous_review            = review_report_v18.md
response_required          = response_v20.md
historical_runtime_source  = c662a70b4af4d742f7a8305d0efd63342423c775
historical_Invocation      = 6344a904b8df435a88a7466dd739da76
mathematical_PC_keep        = task041_v13_consistent_fixed_balh_modal_surrogate
row_contract_keep          = task041.v15.original_modal_row.terms_backward.v1
resource_policy_keep       = task041_v16_memavailable_phase_v1
new_experiment_scope       = task041_v19_frozen_rhs_four_B_capture
old_large_quota            = 2/2 consumed，永久保留
new_diagnostic_rebuild     = 1套依赖构造，非完整warm额度
new_full_M400_quota        = 0
QEP / new_S_B_columns      = 0 / 0
full_B_apply_budget        = 4 total，bottom2 + top2
outer / side / modal_KSP   = 0 / 0 / 0 次求解
archived_S_B_LU / solve    = 最多1次 / 1次
merge_approval             = NO
```

本报告覆盖V18“不得取得真实B或重建P4”的限制，**只覆盖下述单次诊断**。不恢复旧两场额度，不授权“捕获通过后顺便继续算”。当前最小blocker是e_K内部缺少同次y/q、投影和布局证据；本轮用一次有明确辨别能力的实验补齐它，而非再次修改误差门。

最终目标仍为0.7 nm、50×25 nm目标周期单胞、约2 TB物理内存及余量、48 h完整计算；本次既不是该目标资格，也不是任意非可分三维Full3D资格。W5弱显著级继续延期，W2、BIOS、GPU与node1维修不占本轮。

## 1. 审阅结论与来源边界

已读取当前ref、Response V19、中心outcome、machine record、summary及分析器的逐行HP路径，核对最新代码与历史runtime的compare。数值求解源码未变；新增的是离线分析器、review和结果文档。根AGENTS及repository_work_principles已回读；task、docs/AGENTS和前序review沿用此前已读且未改变的版本。当前任务目录没有新增补充任务书。[R1–R6]

`results/.../p0_analysis_closeout_index.json`经GitHub读取返回404。完整ignored数组未在本环境取得，本审阅不是第三次独立重算800行；结论依据版本化记录、可审阅分析代码和下述代数推导。执行者必须在工作站读原件并核hash，不能把summary当数组。[R1–R3]

| 本轮证据 | 接受的结论 | 不接受的推论 |
|---|---|---|
| 800行90位分解、四行120位复核、6类小代数校验 | 存档误差账目已闭合；e_K在800行及732失败行中均为最大项 | 不说明B错误、代码bug或V15应放宽 |
| 失败行最大abs(e_S)/abs(d)约5.37e-5；e_C亦非主导 | 优先增加小LU精度或只修Ca不是当前首要方向 | 不意味着每一操作都有已证明误差上界 |
| row259最后加减项为零 | 只提高最后求和精度不能解释该行差额 | 不排除上游axpy、projection或列/组合作用误差 |
| 行68/140的e_S超通用S-dot参考界 | 点积界不保证LU解残差，不能据此判LU失败 | 不把这两行另开LU修正主线 |
| L行、旧side split、y/q/Ly/Lq、原列反馈及原A独立C字节缺失 | 当前档案无法唯一辨识e_K | 不从C-S、r-g、local_size猜造缺项 |

行91的约2.5e-111分析余量属于已记录HP精度边界，不把它当生产binary64新增误差，也不为该极小项另开重算。原V16行失败及V14根因UNCONFIRMED保持。

## 2. 为什么值得一次捕获；“同一个a”必须怎样理解

固定B/S的理想定义为y=B r_s、g=r_m-Ly、S_B a=g、q=BGa、z=y-q。当前e_K混有三段：形成g、组合y-q并投影、以及存档逐列反馈与直接BGa路径差。四次B足以生成新的一组y/q；其余区分主要只需矩阵行读取和投影，不必再求800条响应。

但旧B/P4因子已销毁。**同源码、同配置、同矩阵定义不保证新因子的浮点作用与旧作用逐位相同。存档S_0也不是新B自动验证过的C-LBG。** 本实验的准确名称是“存档S_0＋重建同定义B_1的冻结输入诊断”，不能伪装成旧调用的位级恢复。

采用唯一的自然PC路径：

```math
y_1=B_1r_{s,0},\quad g_1=\mathrm{fl}(r_{m,0}-L_1y_1),\quad
\widehat a_1=\mathrm{solve}(S_0,g_1),\quad q_1=B_1G_1\widehat a_1.
```

**不强行把旧a_0塞回去。** 那会切断新g_1与owner求解的关系，不再是原PC，并可能伪造“同次owner通过”。核对新owner输出、G输入、原A输入及快照使用同一a_1；另记录a_1与a_0是否逐位相同、差向量/范数及S_0 a_0-g_1。a跨运行不相同只降低历史重现结论，不要求再做第五/第六次B来试旧a，不强设一个差值门后反复重建。

旧RHS指原失败PC的source，不是物理入射f，也不是旧PC target。保持其binary64值，不再次归一化，不作任意phase alignment。

### 2.1 启动前的身份检查分层

先做无需P4 numeric的工作：验证S_0/C_0、a_0/g_0、原rank source、原index/manifest及合格QEP；建立可复用的mesh/coupling/layout。尽量在numeric之前核对C、编号与取证接口，不能先分解两侧再发现旧矩阵无法载入。

必须匹配全部已有的物理/数值、MPI8、modal mode顺序/规范化/传播、组合ownership ranges、modal owner及旧layout hash。**旧hash若只覆盖总行数、每rank组合长度和modal indices，并不证明旧side边界或FE自由度映射。** 本次必须保存实际bottom/top ranges、local slices、FE/MPC/trace编号及其明确含义。

若可由既有独立mesh/编号指纹证明旧到新坐标对应，标`historical_coordinate_binding=verified`；否则，只有已存组合范围全部匹配、原packed source可逐位加载且当前坐标有完整记录时，才允许继续为`frozen_packed_source_new_layout_diagnostic`。后者是本报告明确批准的新诊断向量实验，不宣称同一物理RHS的历史重放。连组合范围、modal坐标或输入身份都不匹配则停止，禁止猜切一半、补零或擅自重排。

读取新原A实际持有的C_A、PC实际C及存档C_0；记录各自完整字节/输入修正/传播身份。新的C_A与PC C、存档C_0应一致；不一致时先保存差额与来源，停止于此，不为通过而替换C/S或修改mode相位。该项即使一致，也不能补证未保存的旧原A C字节。

## 3. 单次捕获的具体操作与必存数据

### 3.1 重建及入口

允许一套必要依赖的构造：原registered W0.7/p6h0.70/M400/MPI8的mesh、耦合、原A、H6/传递、两侧p4各一次正常symbolic/numeric及原有必要局部消元检查；若原耦合必需one-cell traction factor，沿原构造生命周期执行并单列成本。禁止全局p6/Hybrid直接factor。保持PORD、entity_closure、matched L20/N29、材料和全部数学参数。

从归档加载S_0，最多作一次800×800 owner LU及本次g_1的一次求解。这个小LU是新factor，不是恢复旧live factor。**不调用会自动构建S_B或执行B线性样本的普通builder。** 使用现有底层system/LDU类的显式诊断加载入口，生产默认不变；旧build audit只作为旧证据，不伪造为新B的一致性资格。

沿既有Task041准备/资源/监督链增加一个最薄的显式diagnostic dispatch，正式执行仍使用one-dat-one-run公共入口；它不是新的生产PC，也不得建立第二套runner或ledger。小型测试须证明该分支不会落入800列构造或outer。开始前冻结实际source和声明的工作计数。

### 3.2 仅一次apply，严格四次完整B

| 顺序 | 原路径动作 | 就地保存，不新增B |
|---|---|---|
| 1 | bottom B(r_b)→y_b | 实际B输入、y_b、同次Q/P4标量审计与序号 |
| 2 | top B(r_t)→y_t；原projection计算Ly | y_t；两侧Ly原值；形成前r_m与形成后g_1 |
| 3 | owner solve(S_0,g_1)→a_1；原traction形成G_b a_1、G_t a_1 | 原g/a、owner残差、G两侧实际输入及传播/列身份 |
| 4 | bottom B(G_b a_1)→q_b，top B(G_t a_1)→q_t | 两侧q；随后各一次只读projection得到Lq |
| 5 | 原axpy y-q→z；原A一次作用及原V15检查 | y必须在被覆盖前复制；z、原Lz/C_A a_1/w/d及全部800行指标 |

四次B限制针对本次M400诊断所有完整固定B apply，不能在setup、sample或验证中隐藏额外调用。两侧各2次，固定B中的每Q仍为原固定一次数学精化；实际p4回代/零分支及setup p4检查单列，不能用“4次B”掩盖这些成本。side/modal/outer KSP solve均为0。

Ly复用原路径两次projection；Lz复用原A行检查；只额外允许两次Lq projection。原A完整MatMult为一次原门所需动作，不再对y/q作完整A。所有额外写入与Lq使用自有scratch，原输出、g/a、算术顺序不变。若生产V15门再次拒绝，在抛错前保存；诊断可以成功取得证据而数值门仍FAIL，两种状态分列。不能吞掉拒绝后进入外层。

### 3.3 布局、矩阵与快照清单

每rank保存实际新Invocation/source、原A/B/PC对象身份与调用计数、combined/bottom/top ownership ranges、local slices、modal indices/owner、PETSc.IntType/complex128、MPC/trace/实体方向身份。旧raw及新r输入hash分别绑定；每个新中间量按相同apply token与阶段序号命名，不能再使用占位Invocation。

向量至少包括r_b/r_t/r_m、y_b/y_t、G_b a/G_t a、q_b/q_t、z_b/z_t，800维Ly/Lq/Lz、g/a、C_A a、w/d。保存同次B各自输入输出hash和Q/P4审计；不保存所有历史回代向量。每rank自有数据写私有文件，owner只汇总索引；不要每rank复制全局FE向量。

C_A、PC C、C_0和S_0可按去重引用保存，必须能区分来源。保存negative trace map、forward/backward factors、正负interior correction等实际C构造输入或其已存在且可访问的完整工件引用，不能仅说使用了同一函数。

**实际L先取六条既定模态行：259、631、707、105、68、140。** bottom/top本地行号按真实映射给出，不仅靠i<M推测；在当前注册布局下应分别对应bottom259、top231、top307、bottom105、bottom68、bottom140，仍以对象验证为准。全部800行的Ly/Lq/Lz照常保存，选六行只是限制原始稀疏行导出和HP成本，不是删去其余行门。

每条L行保存实际投影矩阵的global column IDs、complex128系数、owner、column vector布局及这些列到y/q/z的映射。现有coupling持有稀疏PETSc projection；通过其真实row accessor读取，不能用mode波形替代组装后的L，也不能调用B构造行。MatGetRow只能读所属rank的行，复制后按本机API正确restore；不得把本地编号当全局列号或重复计ghost。[R5][S1–S2]

取得六条行数据后，在各自输入上作离线高精度乘法即可；不物化全局A、完整B或全量FE×mode反馈。若实际矩阵类型不支持读取，应在小fixture/构造前检查发现；不得用对所有FE基向量逐一作用的方式补出L。

## 4. 新数据能拆什么，仍不能拆什么

以下全部量属于**新调用**；S_0/C_0仍是旧存档。HP对实际binary64输入作90位运算，六代表行120位交叉核对，不以打印后的十进制重建输入。

令ell_y、ell_q、ell_z为本次实际投影输出，按上下侧嵌入800维，定义：

```math
k_g=\widehat g-r_m+\widehat\ell_y,\quad
k_{zL}=\widehat\ell_z-\widehat\ell_y+\widehat\ell_q,\quad
k_F={\rm HP}(C_0a)-{m HP}(S_0a)-\widehat\ell_q.
```

```math
\boxed{e_K^{\rm new}=k_g+k_{zL}+k_F.}
```

这分别给出g形成误差、y-q/projection组合差、存档反馈与新直接作用差。原e_C/e_S/最后加减项继续保留，最终必须与新d完成复数闭合，不能只比较范数。

对已导出的实际L行进一步计算：

```math
\epsilon_z=\widehat z-(\widehat y-\widehat q),\quad
\delta_{Lx}=\widehat\ell_x-{\rm HP}(L\widehat x),\quad x=y,q,z,
```

```math
\boxed{k_{zL}=\delta_{Lz}-\delta_{Ly}+\delta_{Lq}+{\rm HP}(L\epsilon_z).}
```

epsilon_z应在高精度由保存的三个向量相减，不能先binary64相减再充当精确参考。报告epsilon_z本身、L对它的放大、各projection求值误差与方向。记录实际abs(L)abs(y)、abs(L)abs(q)、abs(L)abs(z)及abs(C_A)abs(a)等未相消乘积尺度；它们本轮仅作diagnostic，不代替V15。

C层分开记录`t_constraint-HP(C_A a)`与`HP((C_A-C_0)a)`，避免把C身份差归为纯乘法舍入。对于两次a的变化，可离线计算(C_0-S_0)(a_1-a_0)说明系数变化带来的已知部分，但不据此补造B作用或完整历史漂移。

**k_F仍不能唯一拆开：**它包含旧S列存储/构造误差、旧与新B/耦合浮点路径变化、以及逐列组合与直接作用差。原800列反馈缺失继续标`not_persisted`；C_0-S_0不是找回的原反馈，单次捕获不能证明B非线性或代码错误。不得未经授权再加若干基向量B调用。

## 5. 验证、判定与下一步分流

只补捕获相关的小型代数/已有真实PC作用fixture及一个MPI2边界；不重跑389/441步tiny、不重做全A/B/C、W5或生产资源框架。

| 必要验证 | 判定 |
|---|---|
| hook关闭/开启的同一tiny PC | 算术输出和输入不变；原owner/行门保持；完整B仍每侧2次，新增仅Lq投影及复制。协议完成不叫全场求解PASS |
| archive入口与计数 | S_0加载hash正确；new columns=0、QEP=0、outer/side/modal KSP=0；禁止隐藏重复B。坏hash、错modal次序/范围/相位应在大构造前拒绝 |
| a/g与布局错误注入 | 捕获的是owner实际返回并被G/原A消费的同一a；故意交换a/g或列号必须被协议检查发现。不要求a_1逐位等于旧a_0 |
| MPI2与生命周期 | 含非owner/局部空数据，分布式行只按owner读取；写入失败保留首因；失败/成功的中间量在destroy后仍可读取 |
| 分解校验 | 三项及细分复数闭合，90/120位归一差≤1e-30；使用实际输入项尺度，不加max(1,scale)。零尺度仅对应零差时通过分析检查 |

小fixture通过、可用旧工件已读、现有资源门与取证预算通过后，主控可在本授权内启动一次诊断构造，不必再逐项申请相同范围。主控—执行内部确认和普通commit规则保持。异常若只在准备阶段、未进入大装配/分解，可最小修复、定向测试后继续；同根因两次先小fixture解决。已开始大构造后失败则这一次额度已使用，不自动再次重建。

得到现场后按下列规则收口：

- k_g主导：检查本次r/Ly/g组合、字节身份和舍入流程；形成一个局部修复或合同提案。
- k_zL主导：用实际L行区分axpy误差经L放大与projection求值误差；允许对保存数组作补偿/HP运算的离线对照，但不改生产算术。
- k_F主导：交付新旧身份/系数差、已排除项和剩余列/直接作用混合项，不声称已唯一找到B根因；下一次需要什么最少方向必须另行裁决。
- 原门本次通过或a明显漂移：保存“不重现/部分重现”证据，不能因此修正旧FAIL，也不能重复调用至重现为止。

gamma预算须基于实际实/虚点积长度、归约路径和正常浮点前提；不把LU残差与点积界比较当solver定理，不用事后乘大系数包住观测。界内表示相容而非因果证明，界外表示当前预算解释不足。捕获完成也不自动批准更换判据、删弱行、增加精化、修改B或外层预算。

## 6. 资源和费用边界

| 项目 | 本次边界 |
|---|---|
| 大构造 | 新增1次诊断依赖构造；两侧各一套p4，必要原有local/traction构造单列；没有第二次自动重试 |
| 原系统运行 | 无外层、无完整解、无official EH/RTA；无新800列；无QEP |
| 固定B工作 | 整个M400诊断最多4次完整apply；非零完整路径通常至多8个Q请求，既有exact-zero短路、固定精化及实际回代如实计数，不硬凑回代次数；未完成的调用也计attempt |
| 小模态工作 | S_0新owner LU≤1、自然g_1求解≤1；不迭代修正owner解、不求全谱 |
| 作业内存 | 沿V16 hard80 GiB、warning72 GiB、W8 GiB及host reserve384 GiB；default/unbound、全部正常RAM节点与父cgroup检查不变；swap只观测 |
| 新取证内存 | 新增同时驻留payload预算256 MiB，计入上述80 GiB而非额外扩容；先按真实布局/六条L行算字节，必要时流式写出 |
| 工件与离线 | 捕获新增未压缩数据目标≤512 MiB；若按真实维度超预算，先保留必需小向量/元数据并给缺额，不删数学分量。HP分析沿2 GiB单进程/单数学线程预算 |
| 并行 | MPI8×1，fresh确认原请求map[1,2,3,5,6,7,8,15]及可用性；不干扰邻任务，不修改BIOS或启动监督提醒 |

旧49.6 GB峰只作同结构参考，不是新增取证后硬上界。对新分配按当前J、Delta和W检查；不把已驻留因子重复加算。实际L若导致明显额外对象超预算，不得偷建全矩阵或提高cap。

费用以“1套构造＋4次B＋一次原A＋必要投影和I/O”的有限工作量约束，不新增数千步或多次重启；沿既有watchdog，不另加一个为凑结果而任意调整的短elapsed强杀线。启动前从旧stage记录列出构造成本参考和本次新增字节，实测则分别登记dependency setup、archive LU、四次B、projection、捕获I/O、cleanup、离线分析。总service wall与其子阶段不重复相加，不按MPI数乘账。旧308项前缀和top651301.9334897036 s保留，新attempt唯一追加；历史2/2不改写。

## 7. 交付与授权终点

在同分支提交response_v20.md、一个中心outcome和轻量machine record，更新summary/test_summary。核心交付为：

1. 原输入/S_0及新坐标绑定级别、原A C身份、a_1/a_0与g_1/g_0对照；不能只列hash不说明覆盖范围。
2. 四次B计数和全部必存中间量；800行三项分解，六行的L/axpy/projection细分与数据尺度；分解闭合及误差方向。
3. 本次V15行门原结果、是否复现旧失败及其严格限定；仍不能辨识的历史列反馈/新旧作用差。
4. 一项有证据支撑的下一步修复或合同提案，所需最小额外计算；无自动完整M400授权。

允许诊断complete同时numeric gate FAIL；状态明确为`CAPTURE_COMPLETE_NUMERIC_REJECTED`或相应真实状态，不把捕获正常退出冒充solver pass。若执行额度在构造/取证错误中耗尽，保留已得现场与精确阻塞；下一次重建仍需审批。除本次专用捕获外，不扩大研究旁支。

**最终裁决：APPROVE_ONE_DIAGNOSTIC_DEPENDENCY_REBUILD_AND_FOUR_B_CAPTURE；KEEP_V15_GATE；NO_NEW_SCHUR_COLUMNS；NO_FULL_M400_RUN。** 这次投入的价值是把e_K变成可定位的操作差额，而不是再等待完整计算重复同一个失败。

## 8. 固定证据与接口参考

- [R1 Response V19](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/docs/task041_mpi1_shortwave_hybrid_capacity/response_v19.md)。
- [R2 中心outcome](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/v18_saved_modal_error_decomposition.md)与[机器记录](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v18_p0_saved_modal_error_decomposition_20261016.json)。
- [R3 已提交离线分析器](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/benchmarks/research/task041_v18_saved_modal_error_decomposition.py)。
- [R4 原PC](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/src/solvers/hybrid_fem_modal_block_ldu.py)：_apply_unwrapped的四次B、原g/owner解/axpy及V15门；诊断不得另写不同数学PC。
- [R5 实际projection与coupling](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/src/coupling/hybrid_internal_modes.py)、[原A](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/src/solvers/hybrid_fem_modal_iterative.py)、[布局/C定义](https://github.com/Rookie1234567/MyFEniCS/blob/e287c367fd2d37c62a5d31230968c86fd3353b14/src/solvers/hybrid_fem_modal_augmented_direct.py)。
- [R6 前序Review V18](review_report_v18.md)、[task](task.md)、[仓库原则](../repository_work_principles.md)；本轮仅增加专用诊断授权，旧数值与物理合同保持。
- [S1 PETSc MatGetRow](https://petsc.org/main/manualpages/Mat/MatGetRow/)、[MatRestoreRow](https://petsc.org/release/manualpages/Mat/MatRestoreRow/)：本机ABI下核验已有接口，不升级PETSc。
- [S2 PETSc矩阵/向量布局](https://petsc.org/main/manual/mat/)：行、列与向量的ownership不同；不能由长度相等推断坐标对应。

ChatGPT本次仅做远端审阅、代数推导与review提交，未执行工作站捕获、读取完整ignored数组或修改求解器。文档静态检查、远端blob校验和GitHub视觉渲染的可验证范围另行如实报告。
