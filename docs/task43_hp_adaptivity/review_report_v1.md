# Task43 自适应 h/p 网格研究：正式审阅 V1

| 审阅事项 | 结论 |
|---|---|
| 总体裁决 | **维持 PARTIAL / CONTROLLED_NEGATIVE。可作为有边界的研究阶段结果归档；用户的最终精度与更少自由度联合目标尚未达成。** |
| 空间能力 | p3–p6 mixed-p 与单层局部 h 有真实实现及组件/实解记录；h1 的代数资格与空间精度必须分开。level2、跨 h 转移及一般分布式组合未资格化。 |
| 选择能力 | 九次 p 更新的接受不等式与 h 剪枝界可由提交的轻量数值复算；R10 拒绝符合原规则。属于人工编排的受控自适应实验，尚无完整自动 selector。 |
| 精度 | R9、R10 对独立 holdout 均未通过；R10 对 Y3 的单对通过不能替代独立精度。参考自身、端点 PDE 积分/端口及双侧壁资格仍开放。 |
| 成本 | FE 计数与规模减少可信；同精度全过程成本尚不能比较。56 份 watchdog 的最终逐项轻量账不完整，已公布总额仍只能按其限定解释。 |
| 迭代能力 | 本轮没有完成 adaptive direct/iterative 等价与可扩展性资格；0.7 nm 条件试验不应解锁。 |
| 工程交付 | 有可复用核心，但当前不能给 production core 合并通过。须先修正依赖分组、补回归与有限组件覆盖、完善证据清单。 |
| 本次变更 | 只新增本审阅报告到 task43_hp_adaptivity；不修改历史证据、接受链或源码，不向 master 提交，不执行合并。 |

审阅日期：2026-10-24。本文评价指定送审版本，不把后续修正追溯成该版本已经通过。这里的“P1”包括阻塞任务验收或生产合并的资格缺口，不表示每一项都是已证实的代码错误；“P2”为有限修复或证据补充；“P3”为报告工具与表述问题。

## 1. 身份、方法与独立核验范围

### 1.1 分支与提交身份

| 对象 | 已核对的固定身份 |
|---|---|
| 仓库／执行分支 | Rookie1234567/MyFEniCS ／ task43_hp_adaptivity |
| 送审 HEAD | 5f89dd2ba35f067593983d1a68f845de965dfb6b |
| HEAD tree | 85d1af196c0fe06b5d5bfbbd75dca7856290e601 |
| HEAD 父提交 | 3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0 |
| 初始 Task43 提交 | 0a625d770e1d3638bf53016a72facecfc8c81407 |
| 初始提交的父提交／代码基线 | 405e3aff42ac421a4c99315df1ed9b96941ecbe4 |
| 祖先关系 | HEAD 相对初始提交 ahead 34、behind 0；相对代码基线 ahead 35、behind 0，merge base 正是上述代码基线 |
| 本次审阅 diff | 初始 Task43 提交至送审 HEAD，共 129 个变更路径 |
| 选择停止检查点 | 6210b552f7476a22c2d5aefa96b3a4b9b9883cc3；后验恢复/比较接线随后在 3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0 提交 |

审阅开始时，远端执行分支确实指向送审 HEAD。初始提交只有任务准备的身份与其后执行工作没有混淆。数值/比较代码与最终 focused/full pytest 的记录绑定 3da2fa6；送审 HEAD 另加入报告生成器和最终文档。**历史 PDE 仍须按各自运行的源码快照、dirty map、ABI 和输入解释，不能统一追认成在送审 HEAD 重跑。** [提交历史][H1]、[送审提交][H2]、[最终测试记录][Rtest]支持以上身份区分。

### 1.2 实际审阅的方法

已阅读根 AGENTS.md、docs/AGENTS.md、Task43 AGENTS.md，以及用户指定的 task、[baseline_audit][A]、codex_handoff、response、summary、selective_merge_manifest；检查了模型总账和开发进展的最终段落及历史检查点。基于固定 HEAD 下载并核对源码、测试和全部 **52 份 outcomes/records 文件**，对关键修改与 405e3aff 基线逐段比较。审阅缓存的文件字节用 Git blob SHA 校验，避免把文本读取/换行变化误当源码变化。

本次直接做了以下核对：

- 阅读实际空间、约束、组装、恢复、原方程 action、体吸收、采样、比较器、候选 reader、runner 和报告生成器，不能仅凭 response 的“通过”作结论。
- 从提交的 compact 数值重算九轮接受条件、FE 增量、p 分数下界与 h 上界；核对父 selection 和冻结合同 SHA 链。
- 从后验 compact 的组范数、参考分母、容差和分量值重算九组 J；复算独立 FE、h10 内部行下界与成本加法。
- 在当前审阅环境实际运行原文件的纯数值测试：  
  `python -m unittest src.test.test_task43_physical_g_error -v`  
  Python 3.12.14、NumPy 2.3.5，**6 tests / 0.043 s / OK，exit 0**。覆盖公共微区归属、G 局部贡献闭合、Dörfler 截断并列/舍入、零参考地板；这不是工作站 focused suite 或 PDE 复跑。

**未独立核验的范围必须保留：** 当前没有工作站 ignored artifacts 中的大型原始场、完整 612 行原始 modal 数组、矩阵、完整 source archives、watchdog 采样与 worker 日志；当前环境也没有 PETSc、DOLFINx、MPI 和工作站 pytest。因而没有从这些原始场重新积分、重新施加原算子或复跑 PDE/MPI。源码结构与 compact 算术一致，不等于这些原始运行已被本次亲自重算。材料中的“root raw audit”“原数组独审通过”指执行阶段审计声明，**不是本次外部审阅的复现结论**。hash 能绑定对象，不能代替取得并重算对象。

## 2. 按严重程度排列的问题与验收条件

### Q01 — P1：最终精度与更少 FE 的联合目标尚未达成

**性质：已记录的方法负结果及科学资格缺口，不是新发现的计算造假或已证实的核心错误。**

R9 的 FE 为 110472，但对 Y5_1 的 J 为 4.014410424；R10 为 118800 FE，对 Y5_1 的 J 仍为 2.786521166。两者主要受零级 s 功率通道的绝对 1e-6 门限制。R10 对 Y3 的 J=0.126453607 为真，但 Y3 本身对 Y6_1 的 J=2.710719081，没有最终精度资格。不能选 Y3 这一有利比较替代 holdout，也不能以 G、能量闭合或 A6 通过抵消功率失败。完整九对结果见第 5 节与[后验 compact][Rpost]。

此外，q8/q10 是已保存场的后处理积分检查；它没有解决 PDE q15/q28 加严、R13/R14、最终端点求解扰动和参考自身资格，也没有完成四个垂直界面的双材料侧 trace 检查。[任务合同][T]第 6 节已明确要求这些资格，[比较合同][Rcontract]也明确侧壁尚未运行。

**验收条件：** 先把终点与参考的代数/积分/端口不确定性分别限制到各最终物理容差的 10% 内，再对未参与新设计的独立丰富见证验证完整输出向量和双侧壁要求；同时独立 FE 小于 237600。未完成前保留 PARTIAL。这里不要求成本一定获胜，但要求在同一精度资格下作完整成本比较。

**最小行动：** 保持 V1 结果不变；按第 9 节先做有限原因诊断，不为取得 PASS 自动追加大批候选，更不降低既有门限重写 R10。

### Q02 — P1（生产合并门）：全仓回归没有执行测试体，尚不能排除共享路径回归

**位置：** [final_test_attempts_v1.json][Rtest]；[test179 导入][Ctest179]；[SLEPc 导入点][Cslepc]。

实际全仓命令在 collection 中发生 1 skip、8 errors，测试体执行数为 0。最终 40 passed/3 skipped 只覆盖指定模块和一个 CLI node，不覆盖全部修改过的数值核心；3 个 skips 是 MPI2-only 的 physical sampling 测试。较早组件证据有价值，但不能把它们与最终 focused 数量合并成“所有核心在最终 HEAD 全回归通过”。

轻量记录给出 1 个 Task43 同名 artifact 模块冲突、1 个 SLEPc 注册冲突、6 个旧 scratch 缺模块的分类，但未在已提交的轻量记录中列出八项确切路径及关键 traceback；原 worker.log 有 path/hash，当前未取得原日志。本次不能独立核实全部归因。test179 的实际模块导入链确实进入 slepc4py；而 direct 环境记录明确 SLEPc 为 NOT_LOADED_NOT_REQUIRED_BY_DIRECT_PATH。**direct 成功不能资格化 Hybrid/SLEPc 导入，现有材料也不能判定该错误一定由 Task43 引入或一定无害。**

**验收条件与最小行动：**

1. 从现有日志补轻量错误索引：逐项路径/node、异常、关键 traceback、原日志 hash，保留原失败。
2. 在相同送审代码的干净 checkout、可核对的原生环境中先定位 PETSc/SLEPc 解析路径、版本和 import-only 行为；再完成 tracked suite 的收集及变更依赖组回归。若采用限定收集范围，准确命名，不称原来的全仓命令通过。
3. 不通过删旧负证据、改 golden 或扩大忽略规则来改写原结果。这些工程检查不需要新的正式科学模型 PDE。

本项不阻止研究负结果归档，但阻止给共享 production core 无条件合并通过。

### Q03 — P2（明确交付缺陷）：选择性合并清单的 A→B→C 不是可执行的独立合入顺序

**位置：** [manifest][M]第 7–18 行；[stage4_local_h 导入][CimportsA]第 21–24 行；[dtn_port_3d 导入][CimportsB]第 84–86 行。

A 组的 stage4_local_h 无条件导入 B 组新增的 config 常量/函数，在基线中不存在；B 组的 dtn_port_3d 又无条件导入 C 组新增的 petsc_residual_correction。即使 same-LU 默认关闭，该导入仍发生。因此直接拿 A，或者拿 A+B 而不拿相应 C 依赖，会在导入阶段失败。

**影响边界：** 完整 Task43 分支包含全部文件，不因此失效；问题是选择性合并说明无法按所列顺序直接执行。

**验收条件与最小行动：** 将共享配置/API、辅助模块及相关几何入口放到完整前置依赖闭包，或明确 A+B+C 必须原子纳入、内部只按概念分层审查。对拟选择的实际文件集合做最小 import/collection 检查，并随组纳入相应测试；不需要重跑正式 PDE。本次报告不实际执行任何合并。

### Q04 — P2：最终 56 份 watchdog 总额缺少完整逐项轻量账，最后恢复费用不可直接外审

**位置：** [旧成本清单][Rcost]、[R10 拒绝记录][R10]、[后验验证][Rpost]、summary 第 167–176 行。

名为 completed_watchdog_cost_inventory 的文件仍是 R3 时的 18 条历史冻结账。后续有增量/累计记录，但没有一份最终 56 条的完整逐项表。可见数值为：

| 已提交口径 | 秒 |
|---|---:|
| 截至 R10 的 54 份完整 watchdog 累计 | 61517.39555825014 |
| 后验六场 joint comparison watchdog | 1656.37870862009 |
| 两项相加 | 63173.77426687023 |
| 最终报告的 56 份小计 | 63340.73598930752 |
| 两者差额 | 166.96172243729234 |

差额按上下文应属后验 restore 的整树 wall，但提交材料没有该实测单项及其 watchdog summary 的 path/hash。root_restore_audit 的 hash/PASS 和三场内部恢复时间合计 147.3610370797105 s，均不能代替这个整树计时。**本次不能把倒算出的 166.961722 s 当成已经独立核验的实测。** 这不是证明最终加法算错，而是最终证据账未闭合。

**验收条件与最小行动：** 新增一份最终成本 compact，逐条列 56 个互不重复的 path、SHA、classification、whole wall、类别；补真实 restore summary，并自动核 count/sum/路径唯一性。保留 R3 原清单，不覆盖历史。R8 partial、最终测试、未监控工作和导入参考生成分别列账。无需新 PDE。

### Q05 — P2（证据边界）：远端 Git 不能单独证明首轮接受规则的运行前冻结时序

[acceptance 合同][Raccept]与 transition1 首次同时出现在 2e35567e909f71bf3a428456c59a113dc1fb0228（2026-10-22 21:50:49 UTC）；合同自述冻结时 HEAD 为其父提交 6389b9f5e0a2151014021ad25618637cfd948c72。Git 证明二者在该提交共同存在，不能独自证明更早的工作站写入顺序。

另一方面，comparison/control 合同早于该提交入库；九轮绑定的 acceptance SHA256 始终为 e589d7c980b4467fc21e13445c4af19202ea662cae9f7277f61e98a3e7702647，父记录链也吻合。本次**没有发现后续改阈值或后验反向修改 V1 选择的证据**，不能由同批提交推断作者事后造规则。

**验收条件与最小行动：** 若要加强“严格事前冻结”的可审阅证明，补原 pre-run 输入快照/启动记录中合同 bytes/hash 与候选启动的时间顺序摘录。没有原件就明确保留“hash 一致，时序依赖未独立核验的工作站记录”。不重跑、不回填过去时间戳。

### Q06 — P2（组件覆盖）：新增 p3 尚未进入完整方向组合回归参数

**位置：** [test_197_task035d_hanging_trace.py][Corient]第 111–170 行。

p3 已有 canonical restriction 和六个 hexa face chart 测试，但完整 8 个 D4 变换、256 个 oriented-child 组合的两项参数仍是 p4/p5/p6（第 138、160 行）。当前 h1 与既有 mixed authority 有实际证据，此缺口不能被解释成已证明 h1 错误；它限制“通用 p3 hanging 全方向已资格化”的说法。

**验收条件与最小行动：** 将这两项补入 p3，在已资格环境跑该有限组件集，记录 commuting/方向一致性结果。若失败，定位具体映射，不改旧 golden 抹平。无需正式新模型 PDE。

### Q07 — P3（明确实现问题）：报告生成器把任意缺失 watchdog 都归为 R8

**位置：** [build_unified_model_attempt_inventory.py][Cinventory]第 186–224、246–251 行。

代码只要 wd 为 None，就写 R8 缺失分类并填固定的 3109.3891972089186 s、6844891136 B。当前 16 条模型记录只有 R8 缺 summary，故没有发现已提交 inventory 的实际误标；但未来任一其他 attempt 缺文件时，会复制 R8 资源数字到错误对象。

**验收条件与最小行动：** 只对明确的 round8_p 身份允许这个特例；其他缺失应报错或保持 null/missing。R8 窗记录应来自其固定证据并核身份。用一次非 R8 缺 summary 的小输入检查即可；不需 PDE。

### Q08 — P3：最终文档测试耗时的“最后一次”表述不一致

response/summary 写 5 passed / 0.08 s；[final_review_package_validation_v1.json][Rpackage]注明最后 wording-refresh attempt2 为 5 passed / 0.11 s。通过数量一致，影响很小。

**最小行动：** 后续响应写明两次 attempt 或采用最后一次 0.11 s，不需重跑；本次不修改原送审材料。

## 3. 自适应闭环是否真实

### 3.1 有真实场驱动、空间闭包与候选求解

[physical_g_error.py][Cg]用复电场及 curl/k0 的共同体积分差构造正定 G，按真实 leaf boxes 累加；粗叶跨越多个公共微区时，贡献仍归回同一真实单元。Dörfler 使用 theta=0.5，按贡献排序并完整纳入截断并列项。

[round1_candidates.py][Cplan]第 275–306 行从已接受父场保存的完整非负逐叶贡献重新标记，并核对实际 trace+interior FE。p-up 使用当前 p-map，保留 p6 饱和标记，经过邻接/周期闭包；没有删除 p6 单元后重排以制造可提升区域。h 候选为同一区域根单元的一分八细化，继承父 p；maximum_level=1，遇到需要 level2 的完整标记集合直接拒绝，未悄悄漏掉已细化叶。

[实体阶次与 p 闭包][Cclosure]取 incident-cell minimum，并完成 periodic/hanging 固定点闭包，检查 edge≤face≤cell、邻接 p-jump 等条件。实际自由度来自这些约束后的空间，不能从彩色 cell-p 图直接相加。

正式 h1 为 600 个 p3 叶，FE47235，A6=8.745351252e-10；不是空 h anchor。其 eta=0.245641161、J=300895.081，故“真 h 解过且代数合格”和“h1 空间精度很差”同时成立。[h1 记录][Rh1]保留原中断及后续资格重试，不能把后来的实解回填成 R1 当时已经完成。

### 3.2 九次接受与 R10 拒绝的复算

冻结 epsilon_G=9.088158796603444e-6，epsilon_J=0.12716416232413652；epsilon_G 来自参考差、后处理积分差、初始求解加严差之和的两倍。它是实测不确定性策略，不是统计置信区间或连续误差上界。接受要求 eta 下降严格超过 epsilon_G、J 不超过父 J+epsilon_J，并先通过空间、完整输出和代数硬门。[接受合同][Raccept]与[比较器][Ccompare]一致。

下表由提交数值复算；“h 上界”不表示 h 已求解：

| 轮次 | 独立 FE | 新增 FE | eta_G | J | p 分数保守下界 | h 含噪上界 |
|---|---:|---:|---:|---:|---:|---:|
| R1 | 19679 | 4559 | 2.927588310e-1 | 367685.6637 | 2.967839667e-5 | 1.332962222e-5 |
| R2 | 32358 | 12679 | 1.245868489e-1 | 134007.8296 | 1.326310387e-5 | 4.851247231e-6 |
| R3 | 43208 | 10850 | 4.833604970e-2 | 42271.5272 | 7.026885810e-6 | 1.747635664e-6 |
| R4 | 53659 | 10451 | 9.542819712e-3 | 7475.0800 | 3.711046008e-6 | 5.742453036e-7 |
| R5 | 70212 | 16553 | 3.411538344e-3 | 3407.0428 | 3.698539968e-7 | 5.916948747e-8 |
| R6 | 83959 | 13747 | 4.096986620e-4 | 182.9059 | 2.177021549e-7 | 3.389779509e-8 |
| R7 | 97557 | 13598 | 1.945911432e-4 | 54.8750 | 1.515071040e-8 | 2.206824196e-9 |
| R8 | 106725 | 9168 | 1.258884882e-4 | 10.6024 | 6.502453778e-9 | 1.321091630e-9 |
| R9 | 110472 | 3747 | 3.995683423e-5 | 4.0651 | 2.050800511e-8 | 6.670949019e-10 |

九轮均满足两条数值接受不等式。R8 的数值父状态与其资源终态不完整必须分别评价，不能从此表恢复资源 PASS。逐轮入口及实际闭包见[cycle index][Rcycles]与各 transition/audit。

剪枝在冻结的单位新增 FE 目标下成立。因为 eta_h 非负：

```math
s_p^-=(\eta_{parent}-\eta_p-\epsilon_G)/\Delta N_p,
\qquad
s_h^+\leq(\eta_{parent}+\epsilon_G)/\Delta N_h.
```

每轮 p 的保守下界严格高于 h 上界，因此没有用到 wall-time 平局规则；未运行的 h 费用没有被当成实测便宜值。R9 的 h 内部行下界 309060 给出 Delta N_h≥202335，用较小的正分母计算上界更保守，方向正确。

R10 的 eta 改善为 8.41290070174027e-6，小于 epsilon_G；p 下界为负。即使 J 从 4.065 降至 2.837，也不能通过既有双门。记录没有 transition10，拒绝正确。h10 另因 FE 目标不可行停止，**不是**被同一分数规则剪枝，也不是已求解后失败。[R10][R10]对此区分正确。

### 3.3 科学结论的范围

候选集合是“同一标记区的组合 p-up”与“继承父 p 的单层各向同性 h”。九次 p 获胜支持这个候选集合与冻结 G/FE 目标下的选择，不支持任意局部 h/p 组合最优、方向性 h 无效或墙钟成本获胜。G 不直接最小化最坏的零级功率差；终点 G 已小于 1e-4 而功率仍失败，提示后续需要区分标记目标与输出目标的失配、参考误差及 q/R 扰动，不能直接归罪于 hanging 实现。

代码会重算本轮共同采样、G/J、eligibility 和 score，但 accepted-reader 本身只核身份、hash 与保存状态；人工决定跨候选胜负、h 界剪枝、写 transition、推进计数。[reader][Creader]第 37–113 行与[比较器][Ccompare]第 737–970 行职责不同。称其为“人工受控自适应实验”准确；称“全自动 h/p 控制器”或“reader 独立重验全部历史数值门”不准确。无需为这轮审阅重建控制框架。

## 4. 更少自由度的结论

### 4.1 计数口径可交叉核对

对本次均匀张量 N1E(p)、x/y 周期、z 开边界拓扑，独立 FE 与内部维数分别为：

```math
N_{FE}=N_xN_y p^2(3N_zp+2),
\qquad N_{int}=N_xN_yN_z\,3p(p-1)^2.
```

| 对象 | trace | interior | 独立 FE | 与求解矩阵/存储的区别 |
|---|---:|---:|---:|---|
| 初始 3×10×6、p3 | 8640 | 6480 | 15120 | 612 端口行另计 |
| R9：28 个 p5、152 个 p6 | 35352 | 75120 | 110472 | 增广求解行 35964=35352+612 |
| R10：180 个 p6 | 37800 | 81000 | 118800 | 增广求解行 38412=37800+612 |
| 真 h1：600 个 p3 叶 | 25635 | 21600 | 47235 | 增广求解行 26247 |
| Y3／Y3_2：6×10×6、p6 | 75600 | 162000 | 237600 | 恢复 storage244644−7044 Floquet 从属行 |
| Y5_1：504 格 p6 | 105840 | 226800 | 332640 | storage341436−8796 Floquet 从属行 |
| Y6_1／Y6_2：576 格 p6 | 120960 | 259200 | 380160 | 是更丰富的有限离散参考 |

R9 的边行数为 148×5+452×6=3452；面行数为 115×40+455×60=31900；内部为 28×240+152×450=75120，总和110472。结合原恢复/authority 的已提交计数与周期实体公式，未发现把 carrier、从属行、trace 或矩阵行混成独立 FE 的算术错误。[统一模型账][Rmodels]、[自由度估计][Rdof]支持这些口径；原 p-map/authority 大文件仍属未独立重建范围。

因此 R9 比 237600 少 **53.5050505%**，R10 少 **50%**，作为空间规模描述可信。R10 尚未接受，两者也未通过独立精度，故不能省略“同精度尚未证明”。

### 4.2 h10 的停止证明成立，但只针对冻结动作

R9 有 28 个 p5、152 个 p6。冻结 h10 的 46 个标记含全部 28 个 p5 和 18 个 p6；闭包后分裂82个根，其中54个p6。得到224个p5子叶及530个p6叶，共754。内部 bubble 不被 trace/Floquet 从属消元去掉，故：

```math
N_{FE,h10}\geq N_{int,h10}
=224\times240+530\times450
=292260>237600.
```

未知 trace 是非负额外维数；不必为证明这项 DoF 不可行构造完整 authority 或 factor。记录把 actual trace/total FE 保持 null 是正确的。[h10 计划][Rh10plan]支持该推导。

它没有否定更小标记集合、不同初始划分、其他合法 h/p 组合或未来方向性细化；也没有给出 h10 的误差、运行时间或所有 h/p 方法的负结论。无需补跑全部被严格支配的 h 候选来“证明 h 失败”。

## 5. 角色隔离、后验比较与循环自证

### 5.1 代码与提交顺序的检查

选择使用 Y6_1，Y6_2 只用于参考不确定性校准；Y5_1 和两份控制在 stop 后才进入专用后验入口。该入口要求停止决定、accepted selection SHA、资产清单和原合同，输出 selection_eligible=false，不能直接被 accepted-parent reader 使用。[reference_restore][Crestore]与[后验准备][Rpostprep]提供代码/身份边界。

Git 顺序为先停止选择、再加入后验恢复比较路径。没有发现后验结果反向改变 V1 的 marks、阈值或 accepted9。此判断仍受第 1 节及 Q05 的原始运行时序访问限制，不能用提交日期证明所有工作站知识均被隔离。

Y6_1/Y6_2/Y5_1 都是 p6、主要改变 y 分布，保留相同 x/z 的参考族。它们的接近不覆盖所有空间方向和 PDE/端口误差。两份 6×10×6 控制的轴分布不同，不能只按格数将它们合并成一个“真值”；最终比较并列报告两者是正确选择。[控制合同][Rcontrol]

### 5.2 比较器的量、方向和弱量规范

源码检查支持如下限定结论：

- 公共积分使用所有参与网格的断点并集；affine、轴对齐 N1E p≤6 的 E/curl 由 cell-local DGQ6 导出，且检查每个点的全局唯一 owner。这比低阶 VTU 固定点采样更充分。[公共积分/范数][Cfield]、[采样][Csampling]
- reference 始终是范数函数的第一个参数，分母用该参考范数与固定入射尺度的较大者。E 地板为 sqrt(350000)，G 地板为 sqrt(700000)，H 使用对应物理单位。没有拟合全局相位。
- 总场与散射场分别记录；散射场减去同一解析层状背景。绝对差可相同，原始相对差可不同；地板归一通过不能宣称极弱散射量的原始相对差通过。
- J 包含全部有序 612 通道功率、R/T/A_volume、R00_s/p/total、四组完整复边界幅、总/散射 E/H 和 G。功率逐通道 1e-6、聚合功率 1e-5、场及复幅地板归一 1e-4，未见删去弱/倏逝模式或只比 R/T/A 的代码路径。[完整输出比较][Cmodal]、[J 计算][Ccompare]
- 后验 A_volume 的差来自各原正式记录，**本轮后验比较未重新体积分六场的吸收**。这一点在 manifest 已限定；不能称本次重验了所有原吸收积分。

### 5.3 九组后验结果的独立算术复算

六场并集1008子盒；q8为516096点、q10为1008000点。以下 q10 J 及归一分母可由 compact 复算，q8的判断一致；通道数量是已提交摘要内的核对，本次没有取得并逐行重算原612数组。[后验 compact][Rpost]

| reference → 比较场 | G 地板归一差 | J | 超限功率通道数/612 | 该有限离散对 |
|---|---:|---:|---:|---|
| Y5_1 → R9 | 3.977742372e-5 | 4.014410424 | 2 | FAIL |
| Y5_1 → R10 | 3.129339464e-5 | 2.786521166 | 1 | FAIL |
| Y3 → R9 | 2.617954805e-5 | 1.769487985 | 2 | FAIL |
| Y3 → R10 | 9.501742743e-6 | 0.126453607 | 0 | PASS，仅这一对 |
| Y3_2 → R9 | 3.019235967e-4 | 182.556012693 | 2 | FAIL |
| Y3_2 → R10 | 3.021068962e-4 | 183.783901951 | 2 | FAIL |
| Y6_1 → Y5_1 | 4.222078795e-6 | 0.059167900 | 0 | PASS，仅参考间一致 |
| Y6_1 → Y3 | 3.007437284e-5 | 2.710719081 | 1 | FAIL |
| Y6_1 → Y3_2 | 3.034015351e-4 | 186.621074639 | 2 | FAIL |

q8/q10 归一指标变化最大为最终容差的4.09006162e-13倍，支持本次后处理积分稳定。它不等于 PDE quadrature 收敛、full DtN 收敛或连续真解精度。R10 与 Y3 的相近尤其不能转化为用户要求的独立精度通过。

## 6. 数值核心：可以认可什么，尚不能外推什么

### 6.1 空间、恢复与原方程残差

p3 扩展进入实际 exact-sequence active 空间，并非取 p6 系数前缀；rank 检查改用 SVD 是资格判断层修改。p4–p6 的原空间构造主要保留。当前单层 h 的硬限制、cell-driven trace 与 legacy selected-face 互斥，以及真实 leaf degree catalog 校验都有源码支撑。[局部 h 接线][Clocalh]、[组件记录][Rg1]

新的 A6 也不只是给 Schur 残差换名称：

| 源码路径 | 实际操作 | 支持的判断 |
|---|---|---|
| dtn_port_3d 第4836–4891行 | 对恢复场重组原 UFL volume action−RHS | 可检查对原体积离散方程的一致性 |
| hcurl_variable_p_reduction 第180–254行 | p6 dual 投到 active dual，trace 再用实际 C 的复共轭转置；interior保留 | 不是只检查凝聚 trace，且没有要求 inactive carrier 行全归零 |
| dtn_port_3d 第4906–5104行 | fresh incident/port 向量，独立 lower-modal scalar integral | 不是直接复用求解时保存的 Schur residual |
| dtn_port_3d 第5111–5217行 | trace、interior、modal共同组成残差；raw modal与solver gauge分别记录 | 检查当前约束离散的完整原方程口径 |
| dtn_port_3d 第8295–8388行及恢复路径 | 先完成受限 same-LU 修正，再恢复场、A6及物理输出 | 未把修改前场与修改后残差混作正式结果 |

固定源码：[独立 action][Caction]、[dual 投影/恢复][Creduction]、[修正 helper][Ccorrection]。A6 仍共享合法的物理 forms、几何和规定 cutoff，这是检查同一个离散问题所必需；它不能证明这些离散选择已接近连续问题。

same-LU 默认关闭，生产接线限 MPI1、内置 preonly+lu、有 live observer、无 external solver；只有显式残差有限且严格下降才更新解，否则在 recovery/RTA 前失败。原 KSP telemetry 单列。严格全零投影跳过没有把1e-100等非零载荷裁掉；对应组件记录保留了失败、修复与串行/MPI见证。[same-LU 组件][Rlu]、[零载荷组件][Rzero]

R9/R10 的 A6 分别约8.1537e-9/8.1641e-9，均达到任务 small-direct 1e-8目标；其凝聚残差及能量闭合也过门。这支持代数求解资格，不能从这些数字直接估计物理输出误差，因为两者不是同一量纲或误差范数。

### 6.2 体吸收与局部 h 资格

[rta_3d.py][Cabsorb]按材料区域积分 Im(epsilon_r)乘完整电场模平方并除入射功率；[case flow][Cflow]传入恢复的 E_total。A_volume 不是1−R−T的回填。新增的是显式体积分阶数接线，未配置时保留旧行为；能量闭合另行判断。

h100 triplet 检查同阶 native/empty-h MPI1/MPI2；mixed 9↔12 fixture 检查真实 hanging 的 p3/p4、p4/p5 manufactured 解，但不含完整周期/端口组合。test203 有非平凡 Floquet mixed authority 检查，正式h1再提供新模型的真实单层h实解。这些证据互补，不能各自被扩大成所有空间组合已验。[h100][Rh100]、[mixed-hp][Rmixed]、[h1][Rh1]

建议在既有小 fixture 上分别扰动一个 interior、独立 trace 和 modal coefficient，再重算 A6以确认对应组能捕捉错误；这属于未来重构的有限防护，不是本次已经发现 action 漏行，也不需要新正式 PDE。

### 6.3 转移、迭代和默认行为

父场 p-transfer 的共享行与上层 whole-p6 roundtrip 使用 max(1, coefficient scale) 地板；它不是任意小幅值场的严格齐次相对误差。当前限定 serial、same mesh，R7起明确 skip，因为 fresh direct 不使用这个初值。**当前解恢复的资格与父子 warm-start 转移资格是两件事。** 后续用于迭代或跨h前，须补绝对/无地板相对误差、尺度重缩放、物理E/curl/G roundtrip、非零Floquet及MPI测试。[转移入口][Ctransfer]

共享配置的 ordinary solver/mesh/旧90k gate、quadrature缺省及same-LU开关未见静默改成Task43默认；Task43 profile和新DoF策略是显式选择。缓存上限扩大到128会改变保留内存/性能，不能把“数值默认不变”扩大成所有负载资源不变。[配置][Cconfig]、[manifest][M]

主要数学操作已位于src；benchmark负责本任务配置、候选组合、比较合同与留证，未见另写一套Maxwell求解器。h100_anchor较重，仍应维持research runner边界，不能因这轮成功读取记录就变成production adaptive入口。暂不要求为报告进行大范围重构。

## 7. 成本与缺失证据的评价

[统一模型账][Rmodels]保留16次完整模型尝试、12条科学谱系；“谱系数”不能用来抵扣失败重试的真实尝试和费用。15次有完整watchdog的模型尝试累计33194.906630876474s；R8另列partial。原18条成本账逐项和为12784.686087460723s，与其声明吻合。

失败/重试没有被简单删去：原h1中断2430.828569s、R2 preflight失败1283.605441s、R5性能停止2230.240470s、backend末尾JSON失败及恢复、h1比较623.858588s失败和712.540753s成功均在相应账中。transfer、计划/authority、比较也有费用记录；例如R6 transfer在其计划watchdog内，后续skip并不删掉那笔历史费用。阶段时间是嵌套计时，不应再叠加到whole wall。

| 缺口/口径 | 本次判断 |
|---|---|
| R8 supervisor终态 | 2491样本、3109.389197s观察窗及窗峰6844891136B可以按原记录保留；全程wall/peak/零swap/exit/清理均未完整资格化。shell143、sender未知，不能猜成用户停止或成功退出。 |
| h1辅助ABI文件覆盖 | 原独立ABI JSON旧字节不可恢复；worker前置断言、数值/资源记录是另一组证据。保持unconditional provenance PASS=false，不伪造补档。 |
| R5源码清单漏transfer | 原40文件清单与运行中补充的真实时间分类应保留，不改成pre-run完整快照。 |
| “56份”总额 | 给定63340.73598930752s小计，再加R8观察窗及最终测试135.193513449747s，66585.31869996618s的加法正确；Q04仍阻止把这个小计称已逐项外审闭合。 |
| 同精度全过程成本 | 参考生成、未监控工作/测试与完整R8尚缺，且候选/控制本身没有统一精度资格，不能给出同精度加速或冷启动成本优势。 |
| 不同阶段/后端耗时 | p-map、源码、JIT缓存和生命周期不同，不能用R5/R6/R9/R10的wall差直接证明后端或算法加速。factor对象字节也不能代替同时进程树RSS峰。 |

[R8审计][R8audit]、[h1记录][Rh1]与现有response/summary对这些缺口总体诚实。补档案应使用原件，不能靠重跑一个更漂亮的后续case修补历史终态。

## 8. 选择性合并与工程验收边界

| 组别 | 当前可接受的定位 | 合并前条件 |
|---|---|---|
| 空间、组装、恢复、A6、体吸收 | 可复用数值核心候选 | 修正完整依赖闭包；补p3方向覆盖和受影响核心最终回归；保持单层及默认范围 |
| 公共积分、物理G、采样 | 可复用后处理核心候选 | 保持affine/p≤6/owner限制；MPI2资格按实际证据引用，不由串行40+3代替 |
| same-LU与转移 | 受限组件 | same-LU继续显式关闭为默认；转移不提升为通用warm-start/跨h能力 |
| watchdog/profile/轴规划 | 可复用运行支持 | 显式Task43 identity与旧默认回归，按实际依赖一起纳入；历史R8缺口不追认 |
| reader/checker/候选runner | 研究工具 | 正确说明identity reader与数值comparator区别；不包装为自动生产自适应控制器 |
| 文档、轻量记录、报告生成器 | 可归档的研究材料 | 修Q03/Q04/Q07/Q08并补Q02/Q05可取得的原证据；旧负结果保留 |
| level2、cross-h transfer、adaptive BAL_H/迭代、0.7nm默认开关 | 未资格化 | 暂不能合并成受支持生产能力 |
| 大型ignored场/矩阵/原始timeline、临时草稿、NN/FTT输出 | 不纳入本次源码交付 | 仅保留必要轻量入口；不整体合并旧研究分支 |

本轮对“归档一个诚实的受控负结果”给出认可；对“将全分支或上述core组合入production”不给通过。后续修复可做小的依赖明确提交，本报告不授予master合并授权。

## 9. 当前停止与最小后续实验

### 9.1 停止是合理的

九次已接受更新保留为中间进展；R10未超过冻结epsilon_G，h10冻结动作又不可能满足DoF目标，完整模型尝试已达原规划16次。此时停止比为了多一个accepted而改阈值更有证据依据。当前结论只关闭V1的这组候选/规则，不关闭所有h/p研究，也不提供重启NN/FTT、预条件器盲扫或旧大型控制框架的理由。[任务预算][T]、[停止记录][R10]

### 9.2 先完成零新增正式PDE的收口

优先顺序为Q03依赖表、Q04最终成本账、Q02错误索引及import定位、Q07缺失值归属、Q06有限p3组件；同时补能取得的Q05原冻结摘录。原始场若可访问，用原脚本复核R9/R10/Y6_1关键残差、零级s复幅/功率及原场身份，明确这是重放旧证据。若缺原件，保留未独立核验，不编造替代证明。

这一包新增正式模型PDE预算为**0**。可以跑必要组件/import/已有场checker，真实费用单列；不重算全部九轮或补跑已严格支配的h候选。对当前代码修改前，保留送审版本的原记录。

### 9.3 若继续研究：最多6次新增完整尝试，分阶段放行

这是建议的新研究预算，**本次审阅没有执行这些实验，也不是补写V1的通过结果**。失败与重试同样占用6次，不按谱系抵扣；若基线重建占用名额，就减少后面的动作。保持Task43的192GiB上限及系统余量、单重型队列、task swap为零。运行时限按相同规模实测阶段重新估计并事前登记，不套600秒或为过门任意延长。

启动A阶段前需一个有限的V2诊断入口preflight：R14为836通道，而现有比较器明确要求同序612通道，不能直接拿旧checker运行R14。按(side,m,n,pol)核对共同612，并单列新增224通道的功率与复幅；预先写清完整inventory、聚合功率和复幅组的比较规范，不截回612伪装相同inventory。R13/R14保持同一FE空间但改变端口离散算子，不称same-discrete direct/iterative等价。该入口只服务这组诊断，不放宽V1 reader。[任务第2.2节][T]、[modal比较器][Cmodal]提供这一依赖依据。

| 阶段 | 最多新增完整PDE尝试 | 冻结设计与判别目的 | 继续条件 |
|---|---:|---|---|
| A1：终点资格诊断 | 2 | 固定R10空间和当前数值核心，先仅加严PDE体/面积分，例如q19/q32、保留R13；再在该积分下仅改R14。每次完整输出都与同源码/同FE空间的有效基线比较，并单列端口算子差异，分别判断积分与端口是否解释当前零级s差。 | 每项扰动≤对应最终容差10%；否则停在该原因，不进入空间搜索。 |
| A2：参考资格诊断 | 2 | 对冻结的Y6_1参考空间做同样两个分离的q/R检查。它只作选择参考；对reference误差保持独立记录。若原基线的数值核身份/等价性不能确认，一次名额先用于重建基线，不能把源码差归因q/R。 | 参考不确定性受控；四个名额不够就保留未资格化并停止，不自动加跑。 |
| B：一个区分原因的空间动作 | 1 | 仅在A通过后，从R9与Y6_1的已冻结逐叶贡献选一个最高贡献根单元种子，连同必需周期/2:1/实体闭包做一次现有单层h；先按实际authority筛选FE<237600。明确这是新的小patch规则，不能假称仍执行V1完整theta=.5动作。 | 同一参考重算G及完整J；判断小h动作是否能改善剩余功率误差/单位FE收益。若closure已超预算或FE目标，不启动求解，不改换多个种子盲扫。 |
| C：新的独立验证见证 | 1 | B候选完全冻结后，对事前选定、未参与该候选设计的h-rich方向/组合见证作独立比较；若已有未揭盲且有完整资格的原场，可复用以省此名额。 | 完整输出、参考自身资格与侧壁要求都满足才讨论最终精度；该见证仍缺q/R等资格时如实停止，6次预算不是完成所有验收的保证。 |

A阶段还应在同一已因子化系统上安排一次事前限定的更严回代诊断，比较修正前后完整物理输出；最多再一次同因子修正、显式残差必须有限且严格下降，成本计入对应尝试。若不能安全复用已因子化状态，把重跑算入预算。**不能仅因A6数值小，就推定其对1e-6功率门的影响已低于10%。** 这个诊断不改变旧正式场或旧接受决定。

B不是承诺新h会成功。它只用一个小patch检查原整批h动作是否因闭包过大失去单位FE收益；失败也只说明**这个种子及其闭包的h动作**未能有效减少剩余误差。R9叶均为level0根，现有单层核心可以构造此计划，但现有CLI强制重算theta=.5并写V1合同，不能只替换marked list为一格。应使用很小的V2计划入口与新provenance，保留R9的p-map、fresh direct及明确的单seed规则；不修改V1 reader，也不把未资格化的跨h transfer作为前置。[候选入口][Cplan]

B必须固定与R9父场一致的数值源码、q/R和物理设置。若改用A阶段加严设置，先取得同设置R9基线并占用6次预算，必要时取消后续名额；不能把q/R变化和h变化一起归因于空间动作。A对R10/参考的资格也不能自动赋予R9或B最终资格。如果seed闭包本身不满足真实空间约束，应停为不合格候选，不为凑一个h胜出新增多层/方向网格框架。本文不建议同时加入p-down、多个theta值或多个方向扫描。

### 9.4 新规则只能前瞻生效，旧holdout不能继续假装未揭盲

若改epsilon、输出目标、标记集合或候选族，必须先写V2合同，解释其与所测参考/积分/求解不确定性的关系，并冻结后再运行。epsilon_G目前主要由有限参考族的差贡献；不能因R10只差约6.75e-7就把门改小。即使新规则接受同一个场，也只能形成新epoch的结论，V1的R10仍是拒绝。

Y5_1/Y3/Y3_2的后验结果已经看到；若据此设计V2，它们可以继续作为已知诊断或控制，不能再次称未参与设计的盲holdout。C必须事前声明新的独立见证；两个6×10×6控制仍只用于最终比较，不能反向指导标记、排名或选择更有利的参考。

仅当新候选独立精度合格后，才排一个同源码、同ABI、同核数、明确冷/共享缓存生命周期的最终候选与合格控制全过程成本比较。分别记录最终单场必要路径和整个adaptive开发费用；成本可以不胜出。再之后才在完全相同离散上做小规模direct/iterative action、transfer、恢复和A6等价资格。当前不解锁0.7nm，也不以global LU作PC的小试验声称可扩展迭代。

## 10. 最终裁决

本次直接源码、测试与轻量数值审查，没有确认足以推翻已运行p链或h1的P0/P1数值实现错误；发现了明确的合并依赖、报告生成器缺失值处理和有限测试/证据完整性问题。九次中间接受、R10按原规则拒绝、h10针对冻结动作的DoF不可行判断，在可取得记录的范围内成立。

**认可 PARTIAL / CONTROLLED_NEGATIVE 作为V1的准确状态；不授予最终空间精度、同精度更省、完整成本或迭代能力通过，也不授予生产合并通过。** 当前最有价值的后续是先用已有材料补齐工程证据，再用受限q/R与单个空间动作区分原因；保持所有历史负证据、R8/h1缺口与V1停止决定不变。

## 固定源码与证据入口

以下源码链接固定到送审HEAD；相对文档/records链接的评价对象同样是该HEAD，后续响应不得替换本文所审历史结论。

[T]: task.md
[A]: baseline_audit.md
[M]: outcomes/selective_merge_manifest.md
[H1]: https://github.com/Rookie1234567/MyFEniCS/compare/0a625d770e1d3638bf53016a72facecfc8c81407...5f89dd2ba35f067593983d1a68f845de965dfb6b
[H2]: https://github.com/Rookie1234567/MyFEniCS/commit/5f89dd2ba35f067593983d1a68f845de965dfb6b
[Rtest]: outcomes/records/final_test_attempts_v1.json
[Rpackage]: outcomes/records/final_review_package_validation_v1.json
[Rcontract]: outcomes/records/comparison_contract_v1.json
[Rcontrol]: outcomes/records/final_control_contract_v1.json
[Raccept]: outcomes/records/round1_acceptance_contract_v1.json
[Rcycles]: outcomes/records/cycle_index_v1.json
[R10]: outcomes/records/round10_rejected_candidate_v1.json
[Rh10plan]: outcomes/records/round10_p_only_plan_preparation_v1.json
[Rpost]: outcomes/records/post_selection_existing_fields_validation_v1.json
[Rpostprep]: outcomes/records/post_selection_existing_fields_preparation_v1.json
[Rcost]: outcomes/records/completed_watchdog_cost_inventory_v1.json
[Rmodels]: outcomes/records/unified_model_attempt_inventory_v1.json
[Rdof]: outcomes/records/uniform_dof_estimates_v1.json
[Rg1]: outcomes/records/g1_components_v1.json
[Rlu]: outcomes/records/same_lu_residual_correction_component_v1.json
[Rzero]: outcomes/records/sparse_zero_skip_component_v1.json
[Rh100]: outcomes/records/h100_anchor_triplet_v1.json
[Rmixed]: outcomes/records/mixed_hp_9_to_12_component_v1.json
[Rh1]: outcomes/records/h1_real_action_qualification_v1.json
[R8audit]: outcomes/records/round8_independent_audit_v1.json
[CimportsA]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/adaptivity/stage4_local_h.py#L21-L26
[CimportsB]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/solvers/dtn_port_3d.py#L77-L86
[Ctest179]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/test/test_179_task035b_hybrid_static_condensation.py#L8-L34
[Cslepc]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/modes/quadratic_beta_eigenproblem.py#L12-L17
[Corient]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/test/test_197_task035d_hanging_trace.py#L111-L170
[Cinventory]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/benchmarks/task43_hp_adaptivity/reporting/build_unified_model_attempt_inventory.py#L185-L251
[Cg]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/adaptivity/physical_g_error.py
[Cplan]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/benchmarks/task43_hp_adaptivity/round1_candidates.py#L275-L464
[Cclosure]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/adaptivity/hcurl_broken_trace_graph.py#L521
[Ccompare]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/benchmarks/task43_hp_adaptivity/compare_round1_candidate.py#L563
[Creader]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/benchmarks/task43_hp_adaptivity/candidate_records.py#L31-L113
[Crestore]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/benchmarks/task43_hp_adaptivity/reference_restore.py#L112-L190
[Cfield]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/postprocessing/physical_field_comparison.py
[Csampling]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/postprocessing/physical_field_sampling.py#L94
[Cmodal]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/benchmarks/task43_hp_adaptivity/compare_initial_to_references.py#L347-L399
[Clocalh]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/adaptivity/stage4_local_h.py#L345
[Caction]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/solvers/dtn_port_3d.py#L4780-L5316
[Creduction]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/solvers/hcurl_variable_p_reduction.py#L180
[Ccorrection]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/solvers/petsc_residual_correction.py#L104-L202
[Cabsorb]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/postprocessing/rta_3d.py#L50-L215
[Cflow]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/solvers/common_3d_case_flow.py#L2450-L2496
[Ctransfer]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/benchmarks/task43_hp_adaptivity/round1_candidates.py#L645-L728
[Cconfig]: https://github.com/Rookie1234567/MyFEniCS/blob/5f89dd2ba35f067593983d1a68f845de965dfb6b/src/common/config_3d.py
