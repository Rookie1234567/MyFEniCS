# V39变化：原生抽取／对偶散布、独立checker与部分体积接线

数值核进入src/solvers，五个one-run入口复用runner／watchdog；新输入生命周期／callback检查、实体映射、费用及保存数组checker是opt-in。旧ActionPacket和native oracle保持独立，普通默认、其他任务及dot不改。体积接线修复未获得完整native重放资格。精确清单见[changed_files](records/changed_files_v39.json)，依赖分组见[manifest](records/selective_merge_manifest_v39.json)。旧task/review/response/raw及以下历史正文逐字保留。

<!-- V39-LATEST-END -->

# V38变化：opt-in分方向边界核、完整库存checker和接口修复

新数值核在src/solvers，六个明确stage复用同一个runner及监督。改变的是边界数据布局／相同q计算顺序，ordinary默认和原native oracle不改；无体积求解或NN训练。覆盖、MPI共同错误、预算reader与原子无损writer修复均附定点测试。旧task/review/response/raw保持。[精确列表](records/changed_files_v38.json) · [依赖分组及production边界](records/selective_merge_manifest_v38.json)。以下历史逐字保留。

<!-- V38-LATEST-END -->

# V37变更：通用分面片端口作用与独立原数组审核

数值核心在src/solvers，按mode内双遍历生成／散射未裁剪面片，原oracle／体积solver默认不变；provider补H/source身份绑定。复用既有runner、窗、watchdog、事务writer，并加本批新存储live门与无损JIT归档。checker只重算保存数组，不搭建FE或solve。

五个one-run dat对应IDENTITY／PATCH／CAPACITY／CHECK／DEPLOY，PATCH失败没有被伪造为完成；大数组、JIT、timeline保持ignored。compact证据、README／总账只增加V37内容，原task／review／response／raw不改。[实际清单](records/changed_files_v37.json) · [依赖分组与资格](records/selective_merge_manifest_v37.json)。无merge approval，不把research-only组件升为production default。

<!-- V37-LATEST-END -->

# V36变更：准备接口、按需全端口与独立证据

新增通用bounded provider／surface适配、目标物理／计数／mode准备核；runner只编排新scope的四个opt-in stage，复用既有监督，不复制体积求解。仅在run_case加explicit dispatch、修闭账fixture；原ActionPacket/recover/uncondensed/audit、默认物理solver及其他分支不变。

[source/hash](records/run_index_v36.json)、[依赖分组](records/selective_merge_v36.json)、[实际变更清单](records/changed_files_v36.json)。本轮不授production目标求解或merge approval。

<!-- V36-LATEST-END -->

# V35依赖分组：opt-in在线核、守卫、独立checker与紧凑证据

本轮首次真实冷启动，用七区局部解处理任意新残差，并由GMRES选择修正组合。代价是每个非零输入八次局部solve和两次传播作用；这是传统块方法，没有神经训练。

| 模型／结果身份 | measured或not_run结果 | 解释／边界 |
|---|---|---|
| .7nm／384hex／p3／q15／18144trace＋40port | 首256步Schur0.20524886351900365>0.01 | ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT，关闭固定七／八块追加预算 |
| 原完整方程 | native/augmented0.07959628543991103、total augmented0.027619862207395922>1e-6 | port/恢复/MPC通过不足以授完整解资格 |
| 费用／同时采样树峰 | actor188.162088667s／2108018688B／ownswap0；834次S/SH、264次PC | shared-workstation，全部aux/探针/旧费用另列，不双加嵌套计时 |
| 原因／范围 | 保存残差平方99.19%在外域；第二周期与FE/REF7 NOT_RUN | 无official R/T/A、NN20%或原尺寸2TB/48h资格 |

[完整源码与hash](records/source_inventory_v35.json)／[分组](records/selective_manifest_v35.json)。新FullInputPC只在显式V35入口使用；原oracle与普通default保持。公共finish增加opt-in总作用hook，小Hp缓存也为显式opt-in，历史raw未改写。没有fresh FE／merge approval，不提升失败候选为production。

唯一下一建议是匹配外域Schur的周期／层次全局逆接口与容量资格；本轮不实现。历史后缀逐字保留。

<!-- V35-LATEST-END -->

# V34依赖分组与本轮改动

| 依赖组 | 内容／行为改变 | 验证及建议顺序 |
|---|---|---|
| production numerical/core | 无生产默认改动；原ActionPacket/recover/uncondensed保持独立 | 无fresh PDE，不提升为production |
| reusable runner/watchdog | V34显式schema/dat、统一storage、收费probe/修复重入/退避、两层账及原始结算receipt | final13定点及真实one-run；旧V33默认/closed保持；先审核公共资格helper与runner |
| checker/benchmark | 新旧残差原限值后统一使用保存新r，累计与单run独立消费审核；保存八区norm/复交叉项 | 合成阈值/来源/库存反例＋实际cached CHECKED，0新A/factor；其次审核checker |
| compact evidence/docs | response34、result/cost/source/raw/consume/repairs/test/dot/NN/gate/run/integrity/storage/render；导航及总账前缀 | 绑定numeric fbc5c578…和checker a4cf9c0…；保护旧材料字节及closed；只新增版本记录 |
| research-only | full_input_block_v34_window薄扩展、唯一fixed B_full dat及收费授权 | 数学内核未换；两态负结果，仅显式opt-in，不新增PC/迭代/训练 |
| do-not-merge | ignored真实NPZ/因子/TMP、失败合成archive、未资格化研究执行路径 | 无merge approval；大对象不进Git，不把负求解代码升为默认 |

源码阶段分别79f3d5a…、最小fixture修后fbc5c578…、独立保存分析a4cf9c0…，没有amend/重写历史。新批复用既有study/fixture/checker而非另复制求解器；[source列表](records/source_inventory_v34.json)、[repairs](records/repairs_v34.json)、[最终run index](records/run_index_v34.json)给出实际hash与依赖。P1/P2不改变loss、原方程或阈值。以下历史文件清单及分组逐字保留。

# V33变更／依赖组：外域直接入口与完整交付

只新增opt-in研究路径，不修改旧task/review/response/raw或默认V32数学。准入source45d34165…；静态防护后的最终实现a874498a…未运行资格化，不作production default。

| selective merge依赖组 | 文件／用途 | 数值行为与验证／建议顺序 |
|---|---|---|
| research-only numerical/core | src/solvers/full_input_block_correction.py、full_input_block_study.py、full_input_block_v33_window.py | 新固定B_full缓存诊断；无11方向LS、迭代或训练；新测试NOT_RUN，仅编译，暂不提升production |
| reusable runner/watchdog | diagnostic_storage、原return runner、task042_shared、diagnostic_auxiliary | 显式batch33、统一库存／资源停止标记／计费；沿用原监督，没有本轮有效worker，需新定点资格 |
| checker/benchmark | task042_full_input_checker、return_certificates共享见证、v31_checks、实际workflow fixture／新6函数 | 原数组独立重算与计数／资格；NOT_RUN，不信status自证；依赖新core和runner |
| input／thin入口 | io/full_input_block_v33、io/profile/dat-loader、run_case、full_input_block_v33.json及v33 dat | 当前单阶段输入已创建；未dynamic validate，旧默认保留 |
| compact evidence/docs | response_v33、full_input_block_correction_v33、records、README/summary/tests/changed_files、两总账 | 原资源拒绝、static／not_run、费用与dot/NN边界；原始gzip可还原；可独立审阅 |
| do-not-merge | tmp窗口／ledger／失败stderr、历史及真实大数组／factor（ignored） | 仅原索引引用；不复制或删除，无merge approval |

新数值接口先资格化core／writer／checker，再由新合同判断真实准入；静态16 compile不替代fresh PDE或数组证据。本轮没有production numerical/core可升级项。完整清单和hash见[源码库存](records/source_inventory_v33.json)、[测试](records/tests_v33.json)，历史后缀逐字保留。

# V32：显式路由／资格收费／统一存储及真实负结果

复用V31数值study、fixture和watchdog，新增薄V32 IO/window／单dat/plan、collector后缀及最小dispatcher注册；辅助按独立attempt记账，当前文件hash证明通过覆盖，失败不覆盖。一个stat-only库存模块同时供pre/live/final使用，修复review/records/results漏计；原数学、EXPECTED、门限、普通默认不变。

12 focused、一次真实actor和独立checker绑定source1fe058e3…；无大runner复制、新LU/PDE或训练。后checker的存储预留停止与允许cache清理独立保存。新compact records绑定hash和费用，不重复嵌套旧JSON；大数组ignored。分组及完整文件见[源码库存](records/source_inventory_v32.json)，[回应](../response_v32.md)。旧task/review/response/raw与closed文件保持，以下历史逐字保留。

# V31改动与证据边界

源99739709…添加relative显式导入、V31 IO/window/profile/run_case/worker/父监督/结算、collector显式后缀、固定aux summary计费及合成workflow fixture；普通默认和数学阈值不变。后续4734b22d…仅补拒绝fixture三个接口。数值核心复用原模块，没有新全局矩阵、LU、训练、迭代或大型runner复制。

真实study接线与checker合成通过，前测整体109/1；修后runtime未再测，正式运行未启动。[完整文件／hash与分组](records/source_inventory_v31.json)、[测试](records/tests_v31.json)、[response](../response_v31.md)。新增records绑定原始日志和真实费用；旧task/review/response/raw与closed文件不改。以下历史保持。

# V30变化：入口修复与精准合成验收

数值方程、真实action/PC/恢复和actor未改。本轮依赖组如下；source `1a18f520dae3ecd702a1369b0d9241ec3e81802a`已在clean提交后通过7/162回归，无production提升或merge approval。

| 依赖组 | 文件／职责 | 数值行为与资格／合入边界 |
|---|---|---|
| production numerical/core | 无新增或改动 | fresh PDE无，禁止据此提升真实PC |
| reusable runner/watchdog | task042_diagnostic_auxiliary.py；共享监督不改，只加v30 namespace | 复用原准入／deadline／树监督，1次实测通过；research opt-in |
| checker/benchmark | collect_task042_return_direction.py、task042_v29_cached_analysis.py、task042_v29_light_checks.py | 创建输出目录、schema、批次／日志、完整入口；合成资格已过，真实验收未运行 |
| tests/research-only | task042_return_fixture.py、test_task042_v29_checker.py、test_task042_v30_entry.py | 正控制及32准确错误Gate、7精准回归；小矩阵算法保持 |
| compact evidence/docs | response_v30、light_entry_acceptance_v30、V30 raw/hash/资源／导航和总账 | 只提交轻量证据；历史原文保留，不重复复制nested旧JSON |
| do-not-merge | 所有未资格化真实回流／全空间PC和大数组 | ignored scratch合成包不入Git；旧research路径不提升默认 |

[原始source／run索引](records/run_index_v30.json)及[测试](records/tests_v30.json)。建议顺序是先单独审查审核／入口修复，再compact证据；不自动实施选择性合并。以下历史逐字保留。

# V29变化与依赖分组

| 依赖组 | 改动、证据与审阅边界 |
|---|---|
| production numerical/core | 原算子／物理／网格／MPC／恢复／普通默认未改变；不提升生产资格 |
| checker/benchmark | 完整七bundle／消费／durable ledger-manifest-result检查；回流向量、支持、实际范数／状态／尺度一致性；参数化collector和临时合成包，未运行验收 |
| research-only | 现有return读取已经算出的norm／state／action证书并保存，无额外原作用／solve／分解；B隔离n≤8纸面fixture，不注册真实PC/dat |
| reusable runner/watchdog | 仅辅助wrapper新增V29显式profile，复用原准入和监督；一attempt marker／自有锁／旧窗口不读取；2GiB/1GiB监督因CPU早拒绝未创建 |
| compact evidence/docs | response_v29、A/B/C静态记录、冻结逐核原因表、raw gzip／stderr、完整成本／NOT_RUN、导航和总账；旧task/review/response/raw不改 |
| do-not-merge | 所有未验收checker／research路径、ignored缓存／因子／原始大数组；无merge approval |

依赖审阅顺序：资格证书→独立checker→完整合成与既有回归→轻量资源证据→文档。source bea514e6与交付HEAD及null worker source分开；当前不是合入建议。以下历史逐字保留。

# V28变化与依赖分组

| 组 | 改动、资格与依赖 |
|---|---|
| production numerical/core | 原物理/材料/MPC/恢复/普通默认不变，无production资格提升 |
| research-only | return数学核同一薄QR新增p9/QR/原作用证书；未分辨列只考核合格九列驻点，原门限不变；真实两态NOT_RUN |
| reusable runner/watchdog | 原audit默认关闭receipt，仅V28显式出口；成功/失败CPU及未查Gate均保存；原0.5s监督/资源策略保留；独立V28薄接线与V27累计carry |
| checker/benchmark | 独立cached-array数值checker、parent映射、准入receipt重算；33新fixture＋67旧scope100通过；不新调用原A/LU/分解 |
| compact evidence/docs | 新response/outcomes、原始stderr及gzip快照、parent纠正、账/索引/源码/导航；旧task/review/response/raw不改 |
| do-not-merge | ignored因素/raw/cache/TMP及尚无真实资格的研究路径；无merge approval |

依赖顺序为checker/fixture→显式io/window/audit→research证书→证据文档；不是合并授权。source4808fcab…与最终文档HEAD及空数值source分开。以下历史保留。

# V27变化与依赖分组

| 依赖组 | 行为／证据／审阅边界 |
|---|---|
| production numerical/core | 无原方程/材料/MPC/恢复/普通默认变化；不提升任何生产求解资格 |
| research-only数值 | return_block_direction/study：七bundle只读流式、固定J-O-J、一次十列QR/LS；21项小fixture，实际两态NOT_RUN，不能部署为全空间PC |
| reusable runner/watchdog | DiagnosticWindow／V27薄io/adapter，原runner增显式profile；0.5s整树/自有锁/PSI原语义保持，新stage累计/reader/port-RHS计费；真实launch被CPU Gate拒绝 |
| tests | 两旧V26测试临时时钟ledger fixture，4拒绝case；不改生产V26准入或真实window；67最终focused通过 |
| compact evidence/docs | response_v27与输入/source/零消费/费用/失败/run索引；导航/summary/总账仅前缀，旧字节后缀保留 |
| do-not-merge | ignored factor/raw/cache/TMP、未资格化研究实现；无新LU、无新FE证据；无merge approval |

未来审查依赖顺序为隔离fixture→显式schema/监督→research核→紧凑证据；这是依赖索引，不是合并授权。最终文档HEAD与未执行actor/source分开。以下历史保留。

# V26变化与依赖分组

| 组 | 实际变化／资格／边界 |
|---|---|
| production numerical/core | 无原物理/材料/方程/恢复/普通默认改变；新诊断不升级production |
| research-only数值 | joint_block_direction/study：选定主子块全cell pullback、唯一LU、独立正反作用、两冷残差新增方向；8个纯复数fixture与真实两态资格，非部署PC |
| reusable runner/watchdog | DirectionStage参数化，新joint io/window与28行adapter、显式one-run注册；默认V25保留，原0.5s整树/deadline/PSI/自有锁复用 |
| checker/benchmark | 固定三状态库存与decision命名保护；新两态cached checker重算eta/正交创新/驻点，不读factor、不调用S、不重新分解 |
| compact evidence/docs | response_v26、结果/CSV/JSON、输入/source/matrix/LU/状态hash与全成本；6项导航/总账只前缀更新 |
| do-not-merge | ignored3888矩阵/LU/pivot、方向/raw/缓存/tmp、旧所有factor；不复制上游大结果；无merge approval |

未来审查依赖顺序：库存checker/测试→opt-in schema/监督→research诊断核→compact证据；不是合并授权。运行source独立，旧task/review/response/raw逐字保持。以下原历史保留。

# V25变化与依赖组

| selective merge组 | 变化／证据／边界 |
|---|---|
| production numerical/core | 无原方程／材料／恢复／普通默认改变；没有新的production求解资格 |
| research-only数值 | block_residual_direction.py、block_direction_study.py：同残差8方向上限及原作用见证；复数focused与真实三状态；非PC部署 |
| reusable runner/watchdog | block_direction_window、薄adapter、schema/dat、shared显式V25注册；原整树监督复用；16/12GiB及deadline未放宽 |
| 原reader兼容 | load_local仅增加显式factor_root关键字；旧默认相同，独立只读重载/坏hash及V24准入回归通过 |
| checker/benchmark | 必需six/four和40mode库存；collector从cached数组重算并导出compact records，无新S或求解 |
| compact evidence/docs | response_v25、outcomes及CSV/JSON；source/input/physical/mode/state/factor/hash与费用绑定；旧task/review/response/raw不改 |
| do-not-merge | ignored旧因子／三组方向响应／缓存／tmp工具／raw监督；仅有hash-bound历史引用，不迁移大型payload |

实际run source bc88fe5a81d086059dec705db333b9cf9bf2921e；最终文档HEAD独立。源码commit只包含Task04214文件；collector与证据收口另提交。普通路径不提升，merge NOT_APPROVED。建议未来审查顺序：checker及测试→opt-in读取／监督→research诊断核→compact证据；不是合并授权。以下原历史保留。

# Task042 V24最新收口：对称首块与唯一审核完成

四条首块及唯一冻结审核已完成，完整同离散资格0/5。资格由原方程、场、端口及逐通道功率共同决定；单项native通过或残差降低不能替代完整资格。神经20%增量独立记NOT_DEMONSTRATED：本批无隐藏层训练，也没有最佳合格非神经同精度／完整端到端成本的配对性能证据。

本批用八个固定几何区域中的完整局部解来修正残差，再比较追加既有低阶作用像校正的效果。局部解考虑同组未知量的耦合；组合解在局部修正后再处理粗空间能够消除的部分。原有限元方程、跨块耦合、内部恢复和全部40端口保持，代价是八块稠密LU、每次八个局部解及组合路线额外的原作用和全局薄矩阵乘法。

| 路线／起点 | 周期 | Schur（≤1e-6） | native（≤1e-6） | 散射E差（≤1e-4） | 最大通道功率差（≤1e-6） | 完整资格 |
|---|---:|---:|---:|---:|---:|---|
| V21-C-FINAL | 历史暖点 | 2.528117033e-06 | 9.804133464e-07 | 7.816080389e-05 | 1.719644651e-06 | FAIL |
| LW-FINAL | 4 | 2.502117907e-06 | 9.703307865e-07 | 7.778607315e-05 | 1.666968717e-06 | FAIL |
| LCW-FINAL | 4 | 2.524169303e-06 | 9.788824018e-07 | 7.808877891e-05 | 1.708820964e-06 | FAIL |
| LZ-FINAL | 4 | 0.0813766679 | 0.03155817955 | 0.5688882779 | 0.007245973616 | FAIL |
| LCZ-FINAL | 4 | 0.3252622227 | 0.12613792 | 0.8368884535 | 0.007757579435 | FAIL |

| 状态；全部为未资格诊断 | R00_s | R00_p | R_total | T_total | A_balance | A_volume | 能量误差 |
|---|---:|---:|---:|---:|---:|---:|---:|
| LW-FINAL | 0.1176449645 | 6.952925802e-13 | 0.1176460215 | 0.8770494499 | 0.005304528605 | 0.005306406598 | 1.877993788e-06 |
| LCW-FINAL | 0.1176449706 | 7.011877452e-13 | 0.1176460275 | 0.8770494918 | 0.005304480711 | 0.005306406825 | 1.92611376e-06 |
| LZ-FINAL | 0.1104079944 | 3.889963505e-12 | 0.1104090388 | 0.8698018277 | 0.01978913352 | 0.005272352662 | 0.01451678086 |
| LCZ-FINAL | 0.109887183 | 1.728616029e-09 | 0.109900937 | 0.8797669468 | 0.01033211621 | 0.005293212092 | 0.005038904117 |

固定Full3D/p3/h0.175nm/q15/MPI1：384hex、storage34050、trace18144、internal13824、slave2082、40通道；fine全局NNZ未构造。正式wall1977.711696s、整树采样峰2782064640B、自身swap/VRAM0；分阶段成本与hash均见本轮回应及records。

依赖组：research-only数值local_block_coarse/study/readiness；IO/薄runner/监督/有限queue；6dat唯一计划；focused tests；compact evidence。普通默认及production未批准。ignored因子/数组/缓存do-not-merge。运行source03fd7874190c33a837879d76312d9911223314e0，docs HEAD独立。

收口新增checker/benchmark组：`benchmarks/check_task042_local_block_records.py` 从原始资格、参考残差、场和逐通道功率复算Gate；`src/test/test_task042_v24_compact_qualification.py` 覆盖native不能替代Schur、总功率不能替代单通道、参考必须合格及非有限数据否决。最终5 passed；不改变数值算子或重跑FE。新增紧凑前缀、历史控制、残差像覆盖、逐通道功率复核和旧总账检查索引均属compact evidence/docs；大型map／矩阵／因子保持ignored。

唯一下一建议：以本批已保存的零初值残差为输入，预登记一次有界的块内／跨块耦合作用分账，判断下一种局部通信机制需要补足的方向及容量；不立即改变块数、重叠、粗空间或追加求解。

[本轮回应](../response_v24.md)。以下历史原文逐字保留；其中“当前”仅指记录当时。

# V24变更／research-only，正式数值未准入

| 依赖组 | 内容／资格／建议顺序 |
|---|---|
| production numerical/core | 本批无production或merge批准；普通默认不变 |
| research-only numerical | local_block_coarse/local_block_study：固定L8/LC、全cell主块、D_L和原作用审核；仅pure小模型资格 |
| reusable runner/watchdog | local_block_pair IO/薄adapter/有限queue/window；既有driver仅追加显式v24参数；先依赖原事务/监督 |
| checker/benchmark/tests | test_task042_v24_local_coarse及既有相关pure fixture，28通过；无真实FE替代证据 |
| compact evidence/docs | 6dat、唯一计划、V24停止/费用/权限/原身份/新导航；按任务授权本地保存、待提交 |
| do-not-merge | ignored TMP、失败日志、环境与draft；未来局部矩阵/LU不进Git；未经正式资格的配置不升默认 |

已提交实现精确文件清单见[source_inventory](records/source_inventory_v24.json)。源码HEAD370b7bbe2455448b320ca4272eb62950e4715ecc，formal run source不存在。旧task/review/response/raw逐字保留，无p4强逆/参考重建或大模型。
以下历史正文逐字保留；旧“当前”只指其当时阶段。

# V23变更／显式research opt-in

| 依赖组 | 内容与资格 |
|---|---|
| research numerical core | src/solvers/p1_image_minres.py、p1_image_study.py：J/B_M、同r比较、实际右GMRES和费用；new only，没有普通默认提升 |
| reusable IO/runner/watchdog | 新io/薄adapter/queue/window、五dat和注册；共用旧Stage/reader增加参数，原默认保留；线程/事务/监督回归 |
| checker/benchmark/tests | raw-field资格/不等式/资源复算和篡改反例；只读records，不重新实现求解器 |
| compact evidence/docs | V23来源/QR/场/通道/周期/费用/负结果；旧authority/response/raw byte保护 |
| do-not-merge | ignored W/U/R/field/run/cache/日志；无production或master merge批准 |


本轮变更入口：

- `benchmarks/check_task042_p1_image_records.py`
- `docs/development_model_registry.md`
- `docs/development_progress.md`
- `docs/task042_neural_coarse_inverse/README.md`
- `docs/task042_neural_coarse_inverse/outcomes/changed_files.md`
- `docs/task042_neural_coarse_inverse/outcomes/p1_image_minres_comparison_v23.md`
- `docs/task042_neural_coarse_inverse/outcomes/records/candidate_comparison_v23.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/checkpoint_inventory_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/coarse_compare_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/cycle_history_v23.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/deadline_repair_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/environment_identity_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/field_channels_v23.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/field_checks_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/historical_control_identity_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/historical_control_prefix_v23.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/legacy_registry_check_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/not_run_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/per_channel_power_check_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/per_channel_power_v23.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/progress_journal_v23.jsonl`
- `docs/task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/resource_costs_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/review_render_check_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/run_index_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/setup_QR_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/small_overlap_Gate_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/source_inventory_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/static_checks_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/test_results_v23.json`
- `docs/task042_neural_coarse_inverse/outcomes/summary.md`
- `docs/task042_neural_coarse_inverse/outcomes/test_summary.md`
- `docs/task042_neural_coarse_inverse/response_v23.md`
- `input/task042_neural_coarse_inverse/p1_image_minres_v23.json`
- `input/task042_neural_coarse_inverse/v23_p1_coarse_compare.dat`
- `input/task042_neural_coarse_inverse/v23_p1_image_mr_warm.dat`
- `input/task042_neural_coarse_inverse/v23_p1_image_mr_zero.dat`
- `input/task042_neural_coarse_inverse/v23_p1_image_setup.dat`
- `input/task042_neural_coarse_inverse/v23_verify.dat`
- `scripts/run_case.py`
- `scripts/task042_v17_campaign.py`
- `scripts/task042_v17_queue_watchdog.py`
- `src/io/p1_image_minres.py`
- `src/io/p1_trace_galerkin.py`
- `src/io/task042_profile.py`
- `src/runners/p1_image_minres.py`
- `src/runners/p1_image_queue.py`
- `src/runners/p1_trace_galerkin.py`
- `src/runners/p1_trace_queue.py`
- `src/runners/task042_shared.py`
- `src/solvers/p1_image_minres.py`
- `src/solvers/p1_image_study.py`
- `src/solvers/p1_image_window.py`
- `src/test/test_task042_v23_image_minres.py`
- `src/test/test_task042_v23_records.py`

当前研究路径不提升production default；所有既有权威和历史结果保留。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# V22改动／selective-merge分组（未获合并许可）

| 依赖组 | 文件／变化 | 数值行为／资格与顺序 |
|---|---|---|
| research-only numerical/core | src/solvers/p1_trace_galerkin.py、p1_trace_transfer.py、p1_trace_study.py、p1_trace_error_diagnostic.py、p1_trace_window.py | 新显式opt-in P1_TRACE_GALERKIN及固定全空间右PC/离线诊断；真实mapping/PC合格，物理解负结果，不提升production default |
| reusable transaction/validator | gmres_cycle_commit.py、gmres_residual_completion.py、neural_fe_blind_reference.py | 原默认不变；optional旧oracle残差action、role loader及一次冻结诊断callback；事务及仿射恢复小回归通过 |
| runner/watchdog/io | src/io/p1_trace_galerkin.py、p1_trace_galerkin/queue runners、run_case/profile/shared/v17 queue注册 | 六个独立dat、真实deadline/整树监督/角色白名单；依赖numerical/core；不复制每route巨大runner |
| checker/test/benchmark | benchmarks/check_trace_galerkin_evidence.py、两个相关test模块 | 原字段独立重判与反例；无新求解器/FE重建 |
| input/config | input/task042_neural_coarse_inverse/p1_trace_galerkin_v22.json与六dat | 冻结物理/材料及warm hash；普通默认不变 |
| compact evidence/docs | response22/outcome22/records与6份导航/总账前缀 | 负结果、成本、source和历史依赖保留；可独立审阅 |
| do-not-merge | ignored T/Ac/LU/Gram投影/field/state/cache/results | 大对象不进Git；不从研究结果提升生产PC或宣称可扩展 |

不存在master merge。旧task/review/response/raw不改；实际源提交与文档提交分开。[逐路径source](records/source_inventory_v22.json)、[测试](records/tests_v22.json)、[旧blob保护](records/static_checks_v22.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# V21最小改动与依赖顺序

| 组 | 实际改变、依赖与资格 |
|---|---|
| research-only numerical | 独立ClassBatchAction按精确class/64cell作用；SciPy边界GCROT保留None及33库存；原oracle数学与普通默认不变 |
| reusable runner/watchdog | 参数化V21 stage、不可刷新UTC/monotonic/boot窗口及conservative计费；成熟0.5秒整树监督复用 |
| checker/schema/test | 六个显式opt-in dat；raw/hash/Gate反例；R04只收窄物理parent reader，B原no-read FAIL保留 |
| compact evidence/docs | 实际source、失败/恢复/未运行、同工作量、独立场与40通道、RSS/预算和旧成本；不冒称NN训练 |
| production numerical/core | 无资格晋升、无ordinary default改变 |
| do-not-merge | ignored CU/向量/日志/缓存/环境、不批准merge master |

[完整依赖manifest](records/selective_merge_v21.json)给出文件、数值行为、测试与fresh证据。建议只按研究核心→runner→reader/schema→compact证据审阅；原task/review/response/raw保持。实际数值source与最终文档HEAD分开，B读取缺口不可追溯标PASS。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# V20 最小变更与依赖

| 组 | 改变及依赖 | Gate／合入定位 |
|---|---|---|
| research-only numerical | src/solvers/fixed_p3_ilu0*：原cell K装配、唯一native ILU0、40端口修正；依赖原packet/BarAction | 小fixture＋formal配对；数值负结果，不晋升production |
| reusable return protocol | gmres_cycle_commit可选right-PC，旧默认不变 | V18/V19与全部返回/失败/补审回归 |
| opt-in runner/watchdog/io | V20参数化共享driver、不可刷新计数/监督、7dat/plan | schema与实际one-run；仅Task042研究入口 |
| compact evidence/docs | 原hash/数组/残差/资源重新判Gate，response/summary/总账 | 无新求解；截止延期如实保留 |
| do-not-merge | ignored大K/向量/日志/缓存、未执行新reader mutation代码 | 不提交大数组、不启用production或merge |

建议审阅顺序：数值研究核心→return协议→opt-in runner/schema→compact证据。没有production默认修改；全部formal source与文档HEAD分开。旧task/review/response/raw字节保护。[完整source/run](records/run_index_v20.json)。

以下历史正文保留，旧“当前”仅指其当时阶段。

# V19 最小依赖分组与变更

| 依赖组 | 改变行为／目的 | 验证与建议 |
|---|---|---|
| research-only numerical | 固定R原点的P/L；新增独立事务类型；不改旧close/schema | C0真实审核+物理队列+事务小测试；不得晋升普通默认 |
| runner/watchdog/io | 显式V19入口/预算/缓存；成熟driver参数化 | 6dat实际注册/validation、原V18回归、whole-tree超时清场 |
| checker/tests | 只读原数组与数字重新判Gate | reader反例与原artifact hash；不重实现求解器 |
| compact evidence/docs | 真实source、逐周期、方向、资源、字段和未运行项 | 原历史正文逐字保留；最终HEAD不同于run source |
| do-not-merge | NPZ/方向/大日志/缓存/环境 | 继续ignored，无raw复制或production merge授权 |


数值核心进入src/solvers，成熟runner只显式选择V19。没有更改原task/review/response/raw、材料、方程、MPC或普通默认；不会将研究负结果称为production资格。依赖顺序和完整清单见[selective manifest](records/selective_merge_v19.json)。当前不merge master或其他任务分支。

本批相关文件（后置publication记录另按Git清单）：

- `docs/development_model_registry.md`
- `docs/development_progress.md`
- `docs/task042_neural_coarse_inverse/README.md`
- `docs/task042_neural_coarse_inverse/outcomes/changed_files.md`
- `docs/task042_neural_coarse_inverse/outcomes/post_lsqr_residual_polish_v19.md`
- `docs/task042_neural_coarse_inverse/outcomes/records/candidate_comparison_v19.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/channel_observables_v19.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/checkpoint_inventory_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/close_end_to_end_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/compile_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/csv_publication_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/delivery_cleanup_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/direction_fault_tests_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/field_channel_checks_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/input_lineage_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/paired_same_work_v19.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/plot_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/polish_cycles_v19.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/protected_history_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/quota_dispatch_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/repair_reentry_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/resource_costs_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/run_index_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/same_work_curves_v19.csv`
- `docs/task042_neural_coarse_inverse/outcomes/records/selective_merge_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/static_checks_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/records/tests_v19.json`
- `docs/task042_neural_coarse_inverse/outcomes/summary.md`
- `docs/task042_neural_coarse_inverse/outcomes/test_summary.md`
- `docs/task042_neural_coarse_inverse/response_v19.md`
- `input/task042_neural_coarse_inverse/post_lsqr_polish_v19.json`
- `input/task042_neural_coarse_inverse/v19_post_lsqr_g256_gnn.dat`
- `input/task042_neural_coarse_inverse/v19_post_lsqr_g256_gpoly.dat`
- `input/task042_neural_coarse_inverse/v19_post_lsqr_lgmres_gnn.dat`
- `input/task042_neural_coarse_inverse/v19_post_lsqr_lgmres_gpoly.dat`
- `input/task042_neural_coarse_inverse/v19_post_lsqr_preflight.dat`
- `input/task042_neural_coarse_inverse/v19_post_lsqr_verify.dat`
- `scripts/activate_task042.sh`
- `scripts/run_case.py`
- `scripts/task042_v17_campaign.py`
- `scripts/task042_v17_queue_watchdog.py`
- `src/io/post_lsqr_polish.py`
- `src/io/post_lsqr_polish_check.py`
- `src/io/task042_profile.py`
- `src/runners/gmres_residual_completion.py`
- `src/runners/post_lsqr_polish.py`
- `src/runners/post_lsqr_queue.py`
- `src/runners/task042_shared.py`
- `src/solvers/gmres_residual_completion.py`
- `src/solvers/lgmres_boundary.py`
- `src/solvers/post_lsqr_polish.py`
- `src/solvers/post_lsqr_window.py`
- `src/test/test_task042_v18_completion.py`
- `src/test/test_task042_v19_evidence.py`
- `src/test/test_task042_v19_polish.py`

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# V18改动与依赖

仅Task042必要文件。close caller修复与既有restart64默认保留；新G256/R/V18 schema及窗口显式opt-in。新src/solvers/gmres_cycle_commit.py负责GMRES返回即保存/补审；residual_completion_window.py继承不可刷新预算；gmres_residual_completion.py在原数值模块上完成F0/G/R/VERIFY。src/io、src/runners是薄入口/reader/队列，既有runner/watchdog参数化batch，不另复制大型算法。

8个input v18*.dat及冻结json、两套测试、后置raw checker、response/outcomes与compact records。导航/summary/tests/changed_files及两总账只前缀新增，旧body byte exact；旧task/review/response/raw/records不改。

[依赖组](records/selective_merge_manifest_v18.json)、[source/hash](records/run_index_v18.json)、[历史保护](records/protected_history_v18.json)。research-only不改production default；无merge approval。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# V17：按依赖组列本批变化（research-only）

| 依赖组 | 实际文件／行为 | 对应证据及建议顺序 |
|---|---|---|
| production numerical/core候选 | `src/solvers/bounded_complex_lsqr.py`增加initialize/step/export/restore，原generator沿同一recurrence | 旧20步bit-identical、小80对32+48、真实32恢复；只是可复用接口，无新production Maxwell资格；先审纯core |
| reusable runner/watchdog | `resumable_lsqr_checkpoint.py`两代原子NPZ/hash/commit；`resumable_trace_window.py`不可刷新窗口与保守账；`scripts/task042_v17_queue_watchdog.py`复用subreaper | kill/半写/错identity/计数与.5s整树监督，先core再持久化和监督；不改变全机策略 |
| research-only数值 | `resumable_trace_study.py`复用原ProjectedTraceOperator/BarAction/原audit；`resumable_trace_gmres.py`已安装SciPy固定64周期 | LSQR真实R1和6347/6119；G算法pure测试PASS、正式消费close接线FAIL，不能合入production default；下一review才修 |
| research-only接线 | `src/io/resumable_trace_campaign.py`、`src/runners/resumable_trace_campaign.py`、六one-run dat/frozen plan、有限foreground milestone queue | 一dat一stage、slice继承预算、不自动永久等机；每库B9000/G900、ref barrier；只显式opt-in |
| inherited opt-in seams | `scripts/run_case.py`、`src/io/task042_profile.py`、`src/runners/task042_shared.py`仅登记V17、自己的准入／持久计数 | 普通默认/其他Task合同不变，不改原方程/材料/MPC/modes；旧测试覆盖默认行为 |
| checker/benchmark | 新`resumable_trace_evidence_check.py`和两V17 test文件 | 最终35PASS及原数组Gate/hash重算，拒绝status伪成功；不新求解 |
| compact evidence/docs | Response17、V17结果/JSON/CSV、README/summary/test_summary/changed_files与两项目总账的新前缀 | 旧正文及旧task/review/response/records blob逐字保护；只当前分支，不merge |
| do-not-merge | `benchmarks/artifacts/task042/v17`滚动递推／完整状态、`results/task042/task042_v17_*`与`tmp/task042/v17`监督／资源／草稿 | ignored；大Q/U/R只读原目录、不复制Git；失败向量不存在时unknown，不猜造 |

实现源顺序7defb5…→8350647…→86c7efa…→50a8e9…→bd3ab93…（真实加载失败）→59feb657…（续算/VERIFY及真实G失败）；独立checker源74a3f264…，最终文档HEAD另列。完整源码/hash文件清单见[本批manifest](records/changed_manifest_v17.json)；正式source与leaf费用见[run index](records/run_index_v17.json)。未改旧Task/review/response/raw、原材料表、相邻任务或共享环境；没有获准master merge。

以下历史正文逐字保留；旧版本的“当前”只指其当时阶段。

# V16 变更与selective merge依赖组

| 依赖组 | 文件／数值影响／资格与顺序 |
|---|---|
| production numerical/core | bounded_complex_lsqr仅新增可选完成步callback，旧默认递推bit一致；不把V16研究路径提升默认 |
| reusable runner/watchdog | 复用Stage与既有Task042监督；V16 opt-in dispatch、deadline/counter、source Mapping结构化；独立缓存／锁／整树停止小回归；先审核边界 |
| checker/benchmark | 新V16 raw checker从保存数组/norm/hash重算；不重实现求解、不读参考反馈；依赖冻结schema与相关小测试 |
| compact evidence/docs | response/outcomes/records、README导航、summary/test/changed与两总账；保留旧正文／失败；后于冻结数值证据 |
| research-only | augmented_trace_lsqr/study/window、五dat与冻结plan；Q/U双投影和完整补空间数值核心；仅原micro与本批Gate，未获生产或目标资格 |
| do-not-merge | ignored大基／U/R／完整resources／迭代快照／本地缓存，普通默认改动、旧p4路线、GPU或最大模型均无授权 |

新增算法在src/solvers，runner保持薄入口；普通默认未改变。新source/test/hash见run_index与final_checks。实际依赖文件按git diff相对Review V13列入最终记录；master merge未批准，顺序建议不是合并授权。以下为旧变更记录。

# V15变更与selective merge依赖

| 组 | 数值/文件变化与依赖 | 验证/顺序与边界 |
|---|---|---|
| production numerical/core | 原Maxwell/FE/材料/MPC/DtN/恢复及普通default保持 | 无新生产求解资格，不提升失败研究路径 |
| research-only core | local_trace_features/geometry/decoder/head/study/window：完整矩的8组、匹配SVD块decoder、固定原LS与一次配对组合 | features/metadata→decoder→head→study；33相关测试、L0-L3 fresh evidence，物理FAIL |
| reusable runner/watchdog | 既有V14 Stage仅可注入IO/window/limits，旧默认与门限保持；task042_shared只加V15显式profile，复用原整树监督 | writer/subreaper原子与清场回归；不改邻任务策略 |
| research IO/runner | local_trace_representation IO与薄runner、run_case/profile显式分派、固定JSON和6dat | 核心之后；验证输入/source/hash/冻结参考屏障，one-run |
| checker/benchmark | local_trace_evidence_check、check_task042_v15、小证据反例 | 从raw/哈希/残差/真实decoder重算，无新求解；之后审阅compact records |
| compact evidence/docs | response_v15、outcome/records/journal、最新README/summary/tests/changes及两总账条目 | 保留历史原文，等待review，merge未批准 |
| do-not-merge | 完整map、raw库/块Q/补U/旧G0/action/moment/REF7、results/venv/cache/JIT/TMP | ignored NN-Lab；A是可再生内存workspace，未删除旧负证据 |

以下历史变更原文保留。

# V14变化与selective merge依赖

| 依赖组 | 变化／数值行为 | 验证／推荐顺序与边界 |
|---|---|---|
| production numerical/core | 原Maxwell/材料/MPC/Floquet/DtN/恢复/普通默认无改变 | 没有新生产求解资格，不能提升研究decoder为default |
| reusable runner/writer | task042_shared原子小元数据边界，V14显式分支与独立deadline/tree监督 | C1及22 focused tests；先审writer，再opt-in窗口；不改邻任务合同 |
| research-only numerical | orthonormal_trace_reprofile/study/window：直接Qc、固定薄LS、有限profile | core→study→入口；source8794089…的O1–O4；场FAIL，不是精确VarPro |
| research IO/runner | orthonormal_trace_reprofile IO/薄runner，run_case/profile最小dispatcher，固定plan与3dat | 显式新family/schema/source/hash；一套workspace，6+2固定库存，无隐式参数扫描 |
| checker/tests | orthonormal_trace_evidence_check、薄check_task042_v14、两组pure反例 | C3只从raw/哈希/Qc重算，无PDE；22 tests，EVIDENCE_CONSISTENT不是solver PASS |
| compact evidence/docs | response_v14、outcome、records/journal、README/summary/tests以及Task042两总账新条目 | 旧正文/历史原文保留；审批后仅按依赖选择，当前merge未批准 |
| do-not-merge | P/Q/A/workspace/action/moment/REF7、results/artifacts、env/JIT/TMP/cache | 全ignored NN-Lab；保留origin/selected Q，历史负结果不删除，不提交大数组 |


# V13 变化与selective merge依赖边界

| 分组 | 本批变化／数值行为 | 依赖、测试及fresh证据 | 建议合入顺序／边界 |
|---|---|---|---|
| production numerical/core | 无生产方程／默认改变，原材料、Maxwell、MPC、DtN及恢复不改 | 所有新入口显式V13 opt-in | 不提升失败研究为production |
| research-only numerical | `src/solvers/neural_trace_tangent.py`、`tangent_head_model.py`、`tangent_head_study.py`：手推JVP、实小LS、补偿／实际试探、有限记录恢复 | 原batch8/action/Hhat/stable_head；小型复数与真实A/B/C/D资格 | 核心→局部模型→study；极小J下降，非精确VarPro或solver资格 |
| reusable runner/watchdog | `tangent_head_window.py`不可刷新deadline／journal，复用既有tree/subreaper，无永久后台等待器 | 超时、setsid清场、sibling保护；六run清场 | 先审窗口／ownership；无cgroup连续限额声明 |
| research入口／接线 | `src/io/tangent_head_compensation.py`、薄runner及run_case/profile/shared的最小显式分支，六独立dat | identity／预算／参考屏障；四基础validate及有限复核／恢复 | 核心之后；普通default不变，不复制每方向脚本 |
| checker／benchmark／tests | `src/io/tangent_head_evidence_check.py`、`benchmarks/check_task042_v13.py`、三组V13测试 | raw与NPZ状态hash重算，反例、25pytest＋4ML小断言 | 证据一致性可单独审阅；不等于solver PASS |
| compact evidence/docs | Response V13／outcome／JSON/CSV/journal、README导航及summary/test_summary、Task042两总账追加 | 初始／失败／接受／恢复／审核source与measured/derived/unknown分开 | 可保留负证据，master merge未批准 |
| do-not-merge | results/artifacts、P/Z/R/A、参数／moment/action/REF7、venv与JIT/TMP/cache | ignored只在NN-Lab；Git只有轻量指标／hash | 不提交大数组或环境，历史失败不删除 |

实际接受source `33f7d613b1341fa585f0324ead6039bf28211fff`；writer最小修复及记录恢复／D source `7615baae2f0d75fbc47c05be392b35ef2878c431`，没有重新优化。[Run index](records/run_index_v13.json)、[完整研究](tangent_scale_head_compensation_v13.md)。以下旧分组与失败历史正文保留。

# Task042 实际变化与依赖分组

| Selective merge组 | 变化与数值行为 | 依赖/验证/fresh证据 | 建议顺序和边界 |
|---|---|---|---|
| production numerical/core | 没有把研究逆提升生产默认；旧p6 action/runtime仅显式`borrowed_p4_witness`/`retain_coarse_schur` opt-in | paired默认拒绝/ownership测试、noncommuting原p4测试、真实F1 A4/A6/恢复 | 先审查opt-in与所有权；本轮无合格F5，不能宣布production逆替换 |
| research-only numerical | `coarse_inverse_protocol.py`、`learned_coarse_inverse.py`、`learned_coarse_runtime.py`、`learned_coarse_data.py`、`learned_coarse_packets.py`、`learned_reduced_correction.py`、`learned_training.py` | 原方程/有界局部PC/strict return→p4同身份→teacher packet/POD→线性/NN；pure tests与F1/F2/F3/F4实际记录 | 协议→原p4 witness/容量→离线数据/表示→候选；严格逆失败，维持research opt-in |
| reusable runner/watchdog | `benchmarks/subreaper_watchdog.py`新增可选memory_envelope/health/include_pss；原默认不变 | 既有subreaper语义，资源触线orphan/setsid清理且sibling不受信号；可读健康资源检查 | 先验证own descendants范围和cgroup权限声明；不合并其他任务共享规则 |
| research orchestration | `src/runners/task042_shared.py`、`task042_experiment.py`、`task042_coarse_stages.py`、`task042_training.py`及`src/io/task042_profile.py` | 自有flock、clean source、隔离ABI、逐阶段退出；src承载算法，runner仅装配/记录 | 所有numerical/data模块之后；普通runner新增显式dispatcher，不复制每case solver |
| checker/benchmark/tests | `src/test/test_task042_*`、解析研究profile枚举和input validation opt-in | tiny complex arrays/真实80mode元数据/borrowed witness/资源监督；同组16 RHS及独立raw Gate重算 | 核心接口/枚举变化的focused验证，不运行邻heavy下full pytest或MPI2/4 |
| local activation/config | `scripts/activate_task042.sh`、`task042_preflight.py`、`task042_bounded_check.py`、Task042 dat/profile/依赖lock/尺度模型 | 单核/线程/缓存realpath、FE/ML分环境、CPU-only FP64、每dat一次明确阶段 | 配置→ABI/probe→数值；不得把本机readonly prefix路径当普遍部署配置 |
| compact evidence/docs | 本outcomes/v2 JSON/CSV、`response_v2.md`、本分支progress/registry Task042段 | 所有实际source/input/dataset/model hash、误差与failed/not_run、过程时间/RSS | 可独立审阅负结果；原task/review/response_v1/F0数值records保留 |
| do-not-merge | `.venv/.venv-ml`、results/artifacts、raw logs/time lines、JIT/bytecode/cache、Q/模型/checkpoint/teacher包 | ignored仅NN-Lab；不包含旧大结果/factor，也不向Git提交大矩阵/权重 | 本地复現artifact，Git只提交必要轻量hash记录 |

所有代码路径与data provenance见[架构](architecture_and_oracle.md)、[数据模型](dataset_and_model_provenance.md)。研究模块名字带Task042的部分承担固定范围入口/记录，不把新的p4数学只实现于benchmark脚本；通用core函数参数化。已有A4/A6物理、传递、DtN库存、材料/几何、BAL_H方程和最终门限保留；既有task/review及其他任务源码、环境、watchdog、锁未修改。仅两个原solver/runtime opt-in点与明确research dispatcher/schema分支改变现有文件。

## 真实实现提交及失败修复

| 完整SHA | 阶段/实际作用 |
|---|---|
| `ae5b7d2b79dec38056e4a8b9bd986429989455dd` | 共享CPU profile、F1原方程与有界PC；首次缺pyvista导入失败，无JIT |
| `23cb4710e3ed2c8f7c51fd2b3f4e4dd952bea716` | NN-Lab graphics依赖固定后一次重试；CFFI缺setuptools，保留失败 |
| `f194e455cf904d255fbb30151f21d12be19bc56b` | 独立setuptools与complex CFFI资格；真实p6/p4构建后默认action拒绝材料化p4，非数值失败 |
| `7188564f1a284049ddac3eb32a77ccbda84c5c6b` | 明确借用p4 witness接口，paired旧行为测试；实际mode complex JSON serialization失败 |
| `cca180f875bd22146f2d30fa4d004e372135dfbb` | complex元数据和数组形状最小修复；F1接口实际通过、B0非零失败保存 |
| `b72448bb2117a0221f041f1b47ac41049750a3c7` | 真实teacher、batch packet/native检查；384对实际生成 |
| `d9de8ad69bfeeac4860e5187e1738c902a3d808e` | teacher资格绑定、表示容量、F1失败state完整audit；oracle实际四rank |
| `28a814d1c740c5c23916fe8053c0de7435608a80` | FP64 CPU MLP/冻结推理与F4候选；静态发现F4-B0手写schema enum漏登记，此source无正式数值负载 |
| `a221d881bae9405c98e351df2b0b9533582e6d50` | enum最小修复/all-phase input test；CPU实际训练300epoch |
| `7216efa605bae155ee383fd716c0fae422448b52` | model/dataset/basis资格绑定、真实训练摘要；三条F4均在此同一clean源码运行 |

这是局部实现/元数据修复顺序，原失败资源与错误保留，未以参数扫描反复求数值成功。最终交付另修正零RHS报告不携带前一个native audit缓存；返回/迭代算法及冻结F4结果不变、不重放、不冒充新文档source。最终测试、静态检查和后续文档HEAD另记录。[run index](records/run_index_v2.json)是每次实际clean运行的身份权威，非最新HEAD回填。


## V3 最新有限诊断（原V2正文保留）

V3新增research-only `learned_geometry_overlap.py`、几何/预算/phase测试和`task042_diagnostics.py`；旧backend只可选observer，默认不变。两独立dat/diagnostic_v3.json显式opt-in、V3活动样本准入、CPU纠正和compact CSV/JSON/response/两总账新增段。numeric SHA与文件hash见[运行账](records/run_index_v3.json)。原task/review/response_v1/v2、原v2JSON/CSV和raw保护，未修改邻任务或共享配置；未获production/merge资格。

最终仅修正Task042 watchdog测试从原始整树样本断言后代；未改变监督器/数值源码，原失败记录保留。冻结numeric source仍7fc3f1434cf4f38f43e5244ebfed3a19d0780a26。


## V6：关闭旧路线，材料独立神经trace接口

| 依赖组 | Task042实际变化／数值行为 | 测试与边界 |
|---|---|---|
| research-only geometry/core | 新`neural_micro_pilot.py`参数化box/notch标签＋居中坐标载体；`neural_trace*.py`完整moment/Piola/orientation packet、复数loss/VJP、固定FP64 MLP／局部checker | 23相关pytest、两ML断言、真实FE／ML接口；无目标S、物理恢复或solver资格 |
| reusable runner/watchdog | 新薄`neural_fe_interface.py`接线，原run_case／profile／shared仅两个显式material-blocked入口、实时V6准入；原subreaper复用 | 普通PDE仍要求材料，默认不变；source clean／一dat一stage／独立artifact，唯一坐标修复保留失败 |
| compact evidence/docs | 新V6 design／2dat、material blocker、原字段聚合／source与资源／response和两总账新增段 | 原task/review/response/records保护，旧augmentation不实施，seed420620不消费 |
| production numerical/core | 无新增资格化路径；原A4/A6/S/Floquet与默认不改 | 不提升新表示为production |
| do-not-merge | FE packets／零初始与非零接口witness checkpoint、mesh／日志／缓存／临时helper | ignored只在NN-Lab，无旧大型结果复制 |

C1 `64c128c3541887e22788343692cc4f7832a45696`；唯一正式坐标修复／成功接口C2 `2a2cb4af78ba869a26a1254b4b4b76c9ac158366`。模型11696参数并非合格解，未建真实S/Sᴴ／物理port／内部恢复，三求解路线尚未运行。新材料独立loader是必要显式研究例外，普通schema的Si材料要求保留。所有权威／历史及原结果不改，不merge。


## V7：四波长材料与真实单次FE求解对照

| Selective merge依赖组 | 必要Task042改动／数值行为 | 对应测试／边界／顺序 |
|---|---|---|
| material/core独立组 | input/materials/si_optical_constants_v1.json、optical_material_table.py及离线回归；唯一来源/精确alias/complex square | 7材料回归，先审材料/loader；不自动改变普通case输入 |
| research numerical/core | hcurl_assembly_time_condensation仅可选保留原局部张量审计；neural_fe_action_packet/pilot/gradient_check/optimization/bounded_complex_lsqr | 默认False不改旧求解；真实N1/三路线源绑定，未资格化research-only，不能默认部署 |
| reference-only组 | neural_fe_blind_reference.py，单次p3 symbolicGate/LU，原FE/EH/power；一个范数Form修复后只验证重放 | complex CSR/valid UFL 4 targeted、实际参考；依赖三状态先冻结，不进入候选/loss，不回旧p4 |
| runner/watchdog组 | 原run_case/profile/shared与薄neural_fe_continuation opt-in、独立one-run dat、cumulative V6+V7预算 | 复用原监督器/own lock，MPI1、整树16/12GiB/swap0；无复制watchdog、无ABI/邻任务修改 |
| checker/benchmark组 | neural_fe_gate_check.py与两个反例；复E/H和完整40channel重算、不相信status | 最终32相关pytest，checker无solver/FE重放 |
| compact evidence/docs组 | material/geometry/gradient/三路线/全channels/226audit/source/model/budget/response_v7及summary/两个项目总账新增 | 先数值依赖再轻证据；历史byte/prefix/suffix保护，Review V4不改 |
| do-not-merge | 209MB packet、model/checkpoints、accurate reference、global p3 reference临时CSR/LU、JIT/cache/大日志与临时helper | ignored NN-Lab，不把global参考逆放候选、不上传大型数组 |

正式source完整表在[response_v7](../response_v7.md)／[run index](records/run_index_v7.json)：N1 70f5f543…、三路线7c4037a2…、参考19adac7e…、后处理1ff6f8ba…。后续compact checker/docs HEAD不替代这些source；普通default/原方程/MPC/材料旧输入/旧80通道模型/Task与Review及V1–V6负结果保持。不amend/强推/merge，只原执行分支待review。


## V8：有界尺度与等价计算校准

| 依赖组 | 必要Task042变化／行为 | 验证／边界 |
|---|---|---|
| research numerical/core | optimizer_step_transaction、neural_fe_column_scaling及原optimization显式包装 | 事务/稳定列范数/非Hermitian adjoint/原LSQR递推；严格负结果，非production默认 |
| research neural execution | neural_trace_batched、neural_fe_batch_calibration | 原3×64/8载波/FP64/完整矩，batch8＋固定缓存；真实等价与三对micro，无训练 |
| runner/profile/input | calibration_v8 plan＋独立dat、neural_fe_calibration IO/薄stage、原run_case/shared dispatcher | clean source/自有锁/原watchdog/预算；C2未用moment读入最小修复后边界回归，原运行保留 |
| checker/tests | neural_fe_calibration_gate_check复用原物理checker，新增raw损坏反例、C1/C2/C3/输入边界tests | 不含FE求解；从raw标量/复observable重算，不信PASS标签 |
| compact docs/records | response_v8、scaling_and_execution_v8、所需CSV/JSON、summary及两总账新段 | source/hash/真实负结果/全过程费用及not_run；旧历史逐字保护 |
| do-not-merge | D/state/packet/网络参数、raw日志/监控/缓存/环境和临时helper | ignored NN-Lab；无global p4部署，setup小CSR释放，参考只验证 |

建议合入顺序：事务→列尺度/包装→batch数学核→研究profile/runner→checker/compact证据，全部依赖组待review，不提升默认、不merge。原action、LSQR递推、原FE／A4/A6/MPC、material和旧task/review/response/records不改。正式source仅1a2984a44ca48573bbe18ffe8a7f8c5d6bdacc05和52d47d35656c5a763bed07e07f827fb6fb285bb7，后续所有权及checker/docs source另列。


## V9：只读固定误差定位的依赖组

| Selective merge组 | 必要变化／数值行为 | 测试／边界 |
|---|---|---|
| research numerical/core | 新frozen_fe_error和frozen_fe_field_localization；齐次误差helper、缓存原作用、一次FE积分；原生产S/F/MPC不改 | 复数非零特解/port、原方程身份和实际区域积分；不生成新解 |
| research runner/profile/input | 新frozen_fe_diagnostic IO/薄stage、固定六状态plan和one-run dat；run_case/profile/continuation/shared仅显式V9 dispatch | clean source、原自有lock/watchdog、128调用/3600及累计预算；ordinary default不改 |
| checker/tests | 新frozen_fe_error_check与两个focused test；单次修复交叉平方身份运算尺度 | 23相关最终pytest、真实raw checker，不求解、不信status |
| compact evidence/docs | response_v9、frozen_error_localization_v9、九必需records及显示/静态/环境；summary新前缀，两总账及测试/变化追加 | 历史按字节保护，首次失败和负结果不改写，完整source/hash/成本 |
| production numerical/core | 无新资格路径，V8事务和batch8实现保留 | 不改loss/network/PC、不重开p4、不提升默认 |
| do-not-merge | raw_fixed_error_vectors、原状态/packet、FE积分JIT、日志、环境、tmp helper | ignored NN-Lab；Git只有小CSV/JSON/文档 |

建议依赖顺序为helper→FE积分→研究IO/stage→显式dispatch→checker/tests→compact证据，均待review，不merge。正式FE source a1dc3466294c30b6de292468d6dd1aa9b685b193；最小checker修复source e21af767d3522af531ad83c45eacc1df252566c9，不替代运行source。原task/review/response、旧records和所有负结果保留，不修改邻任务。


## V10：自主输出头／端口研究依赖组

| Selective merge组 | 必要文件／行为与依赖 | 测试、fresh证据及建议顺序 |
|---|---|---|
| production numerical/core | 无新增合格production路线；原S/A4/A6/MPC/材料/trace矩/恢复/优化事务/batch8按字节不改 | 四候选负结果，不提升默认，不merge |
| reusable runner/watchdog | autonomous_batch_window、自有journal/父监督保护；task042_shared最小deadline/dispatch，沿原subreaper | 原start不重置、超时及整树触线/独立兄弟存活测试；先于研究stage接入 |
| research-only numerical/core | neural_linear_head、neural_linear_head_torch、neural_port_closed_head、neural_volume_balance | 复代数/薄容量/原矩与真实回写/Hhat真梯度/保存分项；原action依赖，有限pilot实测，不生产部署 |
| research runner/profile/input | autonomous_neural_head IO及统一参数化stage、run_case/profile最小显式V10入口；冻结plan与one-run dat | clean实际source/hash/自有锁；E/P入口预登记但不准入、不启动，普通default不改 |
| checker/benchmark/tests | neural_head_gate_check、薄LS/矩/窗口/Hhat/元数据及watchdog tests | 25最终pytest、ML三见证、真实pilot补核与原raw false-PASS反例；数值核后接入 |
| compact evidence/docs | response_v10、autonomous_neural_head_v10及必需11compact记录、通道/身份/静态/发布；summary新前缀及两总账/README/tests/changed追加 | 旧历史逐字保护，D2失败与Gate时序偏差披露，费用source完整；依赖最后归档 |
| do-not-merge | P/W/参数/field/action/raw分项、环境/JIT/监控/tmp helper及大日志 | ignored NN-Lab，保留hash-bound数据，不入Git；无global p4部署/hidden fallback |

建议审阅依赖顺序：窗口/监督→薄LS→原矩输出映射→Hhat精确端口与原V诊断→研究IO/stage/显式dispatch→checker/tests→compact证据。全部待review，不merge；E/P/最大模型未运行，不提升普通默认。最初B一见证、三个见证后补，原时序偏差及首次D2失败保留；后续文档source不冒充正式1fb8/6e56/6cba运行source。


## V11：稳定头与变量投影研究依赖组

| Selective merge组 | 本批必要文件、行为与依赖 | 验证／边界／建议顺序 |
|---|---|---|
| production numerical/core | 无新增合格production路径；原A4/A6、S、MPC、材料、40端口、普通默认与旧p4负结果不改 | M2内部门限与原物理场失败，禁止提升默认或合并master |
| research numerical/core | `src/solvers/stable_head_varpro.py`、`stable_head_varpro_torch.py`、`stable_head_window.py`：P=ZR、原S对Z重算A、Hhat40闭合、原方程loss及有界变量投影导数／接受状态 | 依赖原action/q15/batch8/port helpers；合成复数梯度与事务测试通过，但真实FD因S1/S2失败未运行；仅research-only |
| reusable runner/watchdog | `src/runners/task042_shared.py` 的V11窗口/整树监督沿用与最小字段；`src/runners/stable_head_varpro.py` 薄阶段编排（仍较长，后续审查应关注） | 单独one-run MAIN/REPLAY/VERIFY、own lock/CPU0/MPI1/math1/16GiB树监督，真实后代清场；不改邻任务 |
| research input/dispatch | `input/task042_neural_coarse_inverse/stable_head_varpro_v11.json`及三个`v11_*.dat`；`src/io/stable_head_varpro.py`、`task042_profile.py`、`scripts/run_case.py`仅显式V11入口 | 预登记seed/预算/物理hash/参考屏障；干净实际source a2cba715…、036e36ec…；旧默认不受影响 |
| checker/tests | `src/io/stable_head_varpro_check.py`、`src/test/test_task042_v11_checker.py`、`test_task042_v11_stable_varpro.py`；从raw重算S1/S2/场门限，拒绝坏saved status | 最终12 pure pytest＋3 ML小断言、compileall、真实S1/S2/FE；checker源码c6c650ad…是后置审计，不冒充正式计算源码 |
| compact evidence/docs | `response_v11.md`、`outcomes/stable_head_varpro_v11.md`、Review要求的9项compact记录，另加40复通道CSV及Review／静态／发布显示；README最新导航、summary新前缀、tests/changed及两项目总账 | 保留历史原字节与失败源／MAIN序列化缺陷，文档只说明真实结果；最后归档审阅 |
| do-not-merge | ignored P/Z/R/A、trial/workspace、参数/场/action packet、FE JIT/cache、原raw stage和tmp collect helper | 只在NN-Lab ignored目录，hash绑定不入Git；无在线global p4 factor、完整S/CSR、ILU/Riesz、正规方程或隐藏fallback |

建议审阅依赖次序：已有action／q15／Hhat→研究solver→窗口／stage／显式输入→独立checker/tests→compact负结果。真实 S3 FD、S4 hidden update、p4 enrichment 与目标大模型未运行，不能把已写的研究代码视为经过这些阶段的数值资格。原 task/review/response 及 V1–V10 raw 保留；无master合并授权。

## V12：固定头真实损失研究路径的依赖与合入边界

| Selective merge组 | Task042 本批变化／实际行为 | 验证、依赖及审阅建议 |
|---|---|---|
| production numerical/core | 无新增合格路径；原A4/A6、S、MPC、Si表、q15、40端口和普通默认未修改 | 原Schur0.7977/native0.3094、散射误差0.734均失败，不提升默认、不合并master |
| research-only numerical/core | 新 `src/solvers/actual_loss_block_descent.py`：固定γ真实原loss、40维Hhat闭合、共轭转置VJP、分辨率和Armijo规则；`actual_loss_window.py`不刷新四小时钟 | 依赖原action、batch8原矩、V11端口；真实 FD 未资格化，T3代码尚无真实接受更新证据，需保持research-only |
| runner/watchdog | 新 `src/runners/actual_loss_block_descent.py` 三stage编排，`task042_shared.py`只增加显式V12分流、own supervisor和原16/12GiB采样门 | T1最小两次接线修复及失败记录均保留；第二次后源码`d9df7068…`三正式stage成功；不改变邻任务或共享父cgroup |
| input/dispatcher | `src/io/actual_loss_block_descent.py`、`task042_profile.py`、`scripts/run_case.py`和三个独立`v12_*.dat` | 同物理hash、材料、输入及one-run身份；旧V1–V11输入／入口不变 |
| checker/tests | 新`src/io/actual_loss_block_descent_check.py`及两份V12 focused tests，从raw重算T1、FD、state、场及通道，5类坏证据反例 | checker在正式数值后提交`559846ee…`，不冒充run source；ML环境无pytest，纯环境最终26项通过／1排除，ML直接断言通过 |
| compact evidence/docs | `response_v12.md`、`actual_loss_block_descent_v12.md`、9项规定compact记录、README最新导航、summary/test/changed及两个项目总账 | 旧task/review/response/raw字节保留；所有负结果、未运行项、历史有载下界与source分开记 |
| do-not-merge | ignored V11/V12 P/Z/R/A、参数NPZ、原packet/REF7、FE JIT/cache、supervision/完整日志 | 只在NN-Lab，hash绑定不入Git；无global p4 LU、global S/CSR、ILU/Riesz或隐藏fallback |

建议审阅顺序：冻结原action和V11状态→研究数学核→自有窗口／one-run分流→独立checker／损坏证据测试→紧凑负结果。T3有界隐藏优化和块末头提议虽已实现，但本批由真实T2门限阻止，不能据未运行代码授予数值资格。若下一轮需要改变该Gate，应另行正式授权；本轮不做变相阈值放宽。
