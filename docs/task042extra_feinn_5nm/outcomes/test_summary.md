<!-- TASK42EXTRA_V38_CURRENT_BEGIN -->
# 当前V38：新FTT完整接口资格与独立数值失败分列

本支只做神经。Review V37 授权的新FTTNN已实际完成两条从零无标签训练、独立新模型q30/q60重建、完整FE compare-only和保存数组checker；M5联合门均FAIL。没有在接口、commit或普通bug处停止。FTTNN以三个小网络的复矩阵连乘生成三维场，避免旧全局波库/重复QR，但仍需完整矩、原A/A*和逐点反传。本次没有同精度神经资源收益。

| measured；原M5/5nm/384hex/p3/31968复FE/40端口 | 无标签FTTNN | 同秩Chebyshev控制 | 原门/解释 |
|---|---:|---:|---|
| 实参数 / 实际完整调用 / Adam / L-BFGS | 9072 / 46 / 46 / 0 | 9120 / 68 / 68 / 0 | 每条3600s先到；未达Adam500 |
| native / augmented | 0.998818668222 / 0.998818668222 | 3.39713275365 / 3.39713275365 | 各1e-6，FAIL |
| 独立total原残差 | 0.473142162262 | 1.60922776845 | 1e-6，FAIL |
| 总E / 散射E L2相对差 | 0.685720474906 / 0.999950913962 | 0.685749540923 / 0.999993299439 | 各1e-4；同p3原参考完整分母 |
| 总H / 散射H、scaled-curl相对差 | 0.683758070006 / 0.999951999695 | 0.68384279279 / 1.00007590129 | 各1e-4，FAIL |
| R / T / A_balance / A_volume | 0.837465686644 / 0.113250263846 / 0.0492840495103 / 0.463379025542 | 0.837444396846 / 0.113278457882 / 0.0492771452711 / 0.463355617548 | 原残差未过，仅diagnostic |
| 独立能量闭合 / 最大逐级功率绝对差 | 0.414094976032 / 0.0809182401449 | 0.414078472276 / 0.0809442210956 | 1e-5 / 1e-6，FAIL |
| 实际模型重建 / MPC / q30-q60作用 | 0 / 0 / 1.86670425752e-15 | 0 / 0 / 8.64289041436e-14 | 1e-10 / 1e-10 / 1e-8，PASS |
| 本阶段attempt秒 / 同时树RSS采样峰B | 3502.51148525 / 463720448 | 3385.22676557 / 463044608 | loaded-packet实测；swap0，冷N=1 UNKNOWN |
| 条件隔离拟合G误差 / 调用 | 0.992359773046 / 40 | 0.924916613637 / 33 | 原零初态；参考暴露、非PDE-only；非最优空间oracle |
| actual / producer联合Gate | FAIL / FAIL | FAIL / FAIL | 不挑有利版本；全部四类40复通道/六点/区域已验 |

[测试与原失败](records/tests_v38.json)、[真实M5完整矩/非零FD](records/implementation_qualification_v38.json)、[完整场Gate](records/full_numerical_gates_v38.json)、[修复](records/repair_log_v38.json)。现有22个小型case按受影响依赖分批资格，17项旧未改依赖复用，最终5项受影响测试通过；不把分批次数相加当唯一总数。Ruff/compile通过，未full pytest/重装/CI。文档、JSON/CSV/原绑定有限检查和GitHub有限实际呈现另记，不冒称全页视觉闭合。

NUMERICAL_GATE_NOT_REACHED / FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED。接口与梯度资格、完整参数真实更新、完整场失败和成本收益分别判定：模型小不等于求解成功。全局Gram因子/Gsolve/Maxwell因子均0；孤立拟合仅G乘法。研究信号未达，0.7nm缩小pilot未准入、未注册、NOT_RUN；不自动新rank/seed/loss/架构或继续训练。

FTTNN首轮旧raw stop_reason错误及训练软截止越界下界25.6411715581s永久保留，总硬3600s、内存和swap门未超；150s收口未合格，120s完整保存窗口没有独立资格记录，因此不追认整条时间协议PASS；硬总时限、内存和零swap与该流程缺口分列。后续最小计时/用途修复没有重放健康训练。全过程冷N=1、项目精确历史累计仍UNKNOWN；旧波库10186.178641493432s不是新FTT必要前缀，但旧费用全部保留。

原50×25×140nm、Si17/120nm、λ0.7完整三维FE、双Floquet/全部内部/完整端口、decimal2e12B整机、ownswap/OOC0、172800s完整冷流程及原精度门仍未达到。M3600较好态、最终退化、D0成本否决/D1未运行及所有负结果/UNKNOWN保持；下方历史全文不改，旧“当前/下一步”不是新授权。旧稠密波库继续关闭，本支不转去W0/W1、全口面、传统PC、存储或主线接入。

<!-- TASK42EXTRA_V38_CURRENT_END -->

# 当前V36：分块投影核、保全和checker恢复资格

正式S0新核资格完成；本地targeted_3为8项通过，checker补丁targeted_5为2项通过。各批有重复case，不能相加宣称唯一测试总数；targeted_2未用导入Ruff失败、targeted_4监督内存契约漏项测试失败及费用保留。源文件最终受影响测试/Ruff/compile均通过，未full pytest、重装或声称CI。两份真实1377列投影及独立保存物理checker完成，联合数值门FAIL，不能用测试数替代物理成功。

最终轻量元数据检查见[封存检查](records/final_metadata_checks_v36.json)；GitHub实际呈现为PARTIAL_VISIBLE_RANGE_CHECK_WITH_FORMULA_CAPTURE_FAILURE，范围与限制见[render记录](records/render_check_v36.json)。数值source和已资格化数据未改变，没有重跑昂贵数值测试。

[实际JUnit/source/峰值](records/tests_v36.json)、[保全/后备资格](records/fallback_recovery_v36.json)、[完整物理Gate](records/joint_gates_v36.json)。

# 当前V35测试与验收

最小相关fixture、复数/秩亏/不同尺度独立白化配对、标签隔离、实际writer/seal/reopen及用途损坏测试完成。初次mock/API/脚本路径/lint失败保留，最小修复后affected targeted suite 51 passed、Ruff/compileall通过；随后预算writer/元数据恢复的5项最小测试、损坏反例和Ruff/compileall另行通过；无full pytest、环境重装或CI声明。A六个真实完整矩/A复组合健康见证复用，B无保存新场，C只核对旧场身份/绑定并复用原完整Gate；新FE/q15-q30/保存数组数值checker NOT_RUN。

[实际测试与失败](records/tests_v35.json)、[修复](records/repair_journal_v35.json)、[run/source/资源](records/run_index_v35.json)、[完整Gate](records/joint_gates_v35.json)。本地Markdown/链接/compact字段和有限GitHub视觉另记，旧失败不冒称通过；数值source与后续文档HEAD分开。下方旧测试原文保留。

# V32：最小fixture、真实完整矩和最终保存数组Gate

最小测试分次运行，JUnit原失败与重复case名称保留，不把次数相加冒充唯一测试数。最终多尺度/global/Piola/MPC/复导数/batch/轮转/标签隔离资格，QR强相消回滚与真实1377列修复，随后实际两路线与原数组独立审核均已完成；测试通过不等于M5联合通过。未full pytest/重装/CI；健康旧FE/材料/参考资格按同hash复用，不重跑V30/V31完整验收。

[全部JUnit/source](records/tests_v32.json)、[真实12列资格](records/multiscale_checks_v32.json)、[完整数组指标](records/full_numerical_gates_v32.json)、[原失败/修复](records/repair_journal_v32.json)。


V32分次本地JUnit实测如下。各行共享部分case，不能相加作为唯一测试总数；首次失败的原JUnit和费用继续保存。

| 范围 / 原JUnit目录（均在tmp/task42extra/v32） | 实际结果 | 具体边界 |
| --- | --- | --- |
| targeted_tests_1 | 27通过 | 新多尺度调度、完整块、标签和事务fixture |
| targeted_tests_final | 31通过 | 冻结实现前最终定向资格；后续改动只重验受影响项 |
| socket_repair_tests | 14通过 | stage绑定的短socket、恢复与原窗口保护 |
| qr_refresh_tests | 27通过 / 1失败 | 强相关fixture的真实作用配对须拒绝；修正预期而不放宽门 |
| qr_refresh_tests_final | 28通过 / 1失败 | toy fixture遗漏route_seconds；补齐同一计时契约 |
| qr_refresh_tests_qualified | 29通过 | 最终复数、强相消、回滚、原子重开和原AU配对 |
| qr_resource_classification_tests | 1通过 / 7未选 | 只重验真实QR资格的numerical角色分类，不重跑无关旧测试 |
| 真实M5完整矩资格 / 1377列原作用QR资格 | 均实际通过 | 非fixture；原1e-10作用/重建门、全部自由度族及MPC |
| 最终独立FE与保存数组checker | 完成，联合FAIL | 136项指标、640复通道值、160逐级功率；不以实现测试替代数值门 |


有限GitHub实际目视：Review V31和Response V32可见首屏通过；专题旧宏失败保留，同义宏修正后唯一复查的首屏两公式通过。全页/全表未覆盖，保持NOT_VERIFIED；[原截图与范围](records/render_check_v32.json)。最终metadata复核原CSV分子/分母、完整数量、所有旧正文hash及未改变数值source，不再次运行producer或旧FE Gate。
# V31最终：完整保存场检查已完成，测试资格与求解失败分列

writer、块代数、JSON事务、标签/预算、数值秩、诊断opt-in及严格新块guard的定向fixture通过；真实完整矩/非零方向FD和长缓存 qualification已执行。初始18项中的1个预期原因断言失败及其最小更正保留，不能抹成全程无失败。最终数学source c32723a6c176a75e69174bd7a9570b8c981c4160与文档HEAD分开，健康旧昂贵Gate未重复。

独立FE重建与pure保存checker实际完成，参考合格但两新候选M5联合门FAIL；固定重建3.92857e-10及读出2.35272e-9亦FAIL。小fixture/FD PASS不能代替原方程与物理Gate。最后affected lint/compile/Markdown/链接/records合同单列；无full pytest、CI或环境重装。GitHub有限新页检查失败不得称视觉通过。

[JUnit及失败](records/tests_v31.json)、[真实资格](records/block_checks_v31.json)、[完整数组门](records/full_numerical_gates_v31.json)、[费用](records/resource_costs_v31.json)、[呈现](records/render_check_v31.json)。下方旧测试原文保留。

# 当前V30最终：实现资格与未完成物理验收分列

新网络确实学了连续波动方向；测试只验证实现链，不能替代真正的散射解。最终native残差仍为神经0.3308837562、控制0.4237611235，均高于1e-6。独立完整矩重建后，神经模型与保存系数相对差1.71986e-10超过1e-10；全场、功率及区域验收未运行，保持负结果和UNKNOWN。

| 本地实测或复用 / source | 结果与范围 |
| --- | --- |
| 原S0/真实全矩/梯度/局部作用/投影/候选分批 | 按原hash复用已接受配对；各历史失败和负性能保留，不重跑昂贵旧Gate |
| 复数事件writer→JSONL重开、封存重建消费与损坏输入 | 7bd72c7e81a9983addeff4032e9feacde6088a27；8项最终pytest通过，Ruff/compile通过；[源码/JUnit/费用](records/recovery_qualification_v30.json) |
| 首次修复检查 | 8项pytest通过，但Ruff发现重复Path导入；最小修正后重验通过，原失败未删除 |
| 独立两路线q30/q60完整矩重建 | 已保存四次完整重建；控制映射1.59643e-11通过，神经1.71986e-10失败；系数求积漂移子项通过，[原量](records/rebuild_recovery_v30.json) |
| 原FE compare-only / 79f363981765876e7020ac09cec326e8ba7e656e | 复数事件写出在完整场后处理前失败，2713.072832s保留；不是完整FE数值验收或求解通过 |
| 修复后的真实恢复入口 / 7bd72c7e… | 已实际尝试；worker前被资源观察预算拒绝，启动FE/训练/参考求解0；不重跑健康四次重建 |
| 最终新文档/compact字段检查 | 只检新页及当前导航，围栏/公式/表格/链接/状态与hash另存[最终局部检查](records/local_delivery_checks_v30.json)；不扩为历史全量数值或CI |
| GitHub实际视觉 | 有限访问与无法取得视觉证据单列[呈现](records/render_check_v30.json)；本地结构不冒充浏览器PASS |

最终代码修改后已重验受影响的8项pure测试；后续仅文档和compact记录。新9页/14张表的局部Markdown、链接及状态检查通过，独立保存向量检查从原数组重算系数映射、求积漂移和保存r范数；不是新的A作用或完整场checker。首次最终轻检查2.051332s/树峰94715904B/ownswap0，全部费用保留。没有full pytest、环境重装或昂贵旧资格重放。轻检查单核/线程1、树2GiB；峰与完整多根范围分列。以下所有历史测试、失败、费用和开发时“进行中”原文保留，收口后不授新运行。

# V30追加：实际网络重建与计时保全

新增12纯fixture通过，全宽度1/2/4/8、完整边/面/内部及方向/owner、严格零与任意小非零、模型重建、损坏状态/覆盖、真实复数writer重开；另1条受影响原窗口计时回归、Ruff/compile通过。实际冻结两候选q30/q60各3cell点值新/原配对差为0，但多项成本更差，原独立重建仍选择。科学Gate尚待全域独立进程，未将小fixture或抽样当完整场通过。2GiB监督峰201,424,896B/40.836549s、自身swap0；轻计时跟进峰70,987,776B/2.299511s，复用本准备阶段PSI收据而不声称新增60s观察。[原绑定及全部范围](records/frozen_field_qualification_v30.json)。

# V30追加：有界独立候选分批资格进行中

20项受影响pure测试实际通过、零跳过，包含1/2/4/8宽度、重复/相关列、完整native接受场、无效投影、原复数梯度/QR/schema/标签隔离；实际独立60s PSI、树峰114233344B、自身swap0。健康旧35项及昂贵FE资格不重跑。新真实M5完整proposal配对随后运行，不以fixture代替物理或求解Gate。[绑定源/JUnit](records/screening_targeted_tests_v30.json)。Ruff初始F401已最小修正；Ruff/compileall/diff最终通过。后续正式source与本文件HEAD分列。

# 当前V30：新增波动函数/完整原方程实现资格

S0原M5完整映射、方向、MPC与非零梯度见证实际通过，属于实现资格。新增输入支持作用六见证也已实测；512列完整保存后，投影缓存及受影响保存checker的35项fixture通过，真实保存态配对尚未运行。[新定向测试](records/projection_targeted_tests_v30.json)、[局部作用](records/local_action_qualification_v30.json)、[完整保存与监督](records/engineering_pause_2_v30.json)。没有full pytest、重装或CI；原测试失败与全部旧资格保留。后续仅重验实际改动的计时项。

# 当前 V29：最终17项定向资格与全口面独立原门

最终实现source为c94fe051752ab1576bc8b00548eb12109f18280a；17项pytest/Ruff/compileall全部通过，JUnit SHA a704fabb0b5701fa1eb6df76dda30f1f5630fe6d467325f00e11cd1b42e974b5。测试覆盖新鲜CPU/身份/cpuset/最后24份/拒绝25份、显式opt-in、完整API路由、周期映射、更新hash后的损坏数组、实际writer→seal→重开→消费者、失败监督/陈旧资源拒绝、D共轭、原清单参考面、原生原向量分母及固定根因计数。fixture中的Basix替身不是原生物理证据。

| 实测资格 / source | 结果与边界 |
| --- | --- |
| final P0 / c94fe051… | 17/0，Ruff/compile exit0；轻树峰121204736B、swap0；[测试/hash](records/targeted_tests_v29.json) |
| actual p4/p6 / ef9f9f39…/91023bdc… | 原生300/882列及全部2176口面/32060模式真实API，非stub；各一次健康producer |
| separate saved checker / c94fe051… | 每p原门513630/0；额外1360/4947逐列失败保留，无体内资格；[全部保存结果](records/independent_checker_v29.json) |
| actual package ready consumer / c94fe051… | 默认ready重开37文件/251699594B，不新增FE生命周期；[调用/消费](records/main_api_handoff_v29.json) |
| 历史/失败与重用 | 开发序列化/格式、c29字段错误、c129分母分类失败、a329 worker前拒绝都保留；旧92A/39/V28受影响37按依赖复用，无全套重跑 |
| 文档与网页 | 新页/新增前缀本地结构与链接另记；新页浏览器视觉NOT_RUN，有限GitHub访问Cache miss；不是全页或CI PASS |

[运行source](records/run_index_v29.json)、[修复](records/repair_log_v29.json)、[费用](records/resource_costs_v29.json)、[呈现](records/render_check_v29.json)。最后代码修改后已重验相关资格，后续仅文档/compact记录；无full pytest、环境重装、无关MPI或CI。下方全部旧测试、失败和费用原文保留。

# Targeted tests 与文档复核

本页保留首次失败与修复后结果。完整suite与CI没有运行；检查限定于新增full-FE数学/事务/Riesz及本任务文档，不重跑旧heavy。

| 检查/尝试 | 监督状态/exit | wall / s | 同时树RSS / MiB | own swap / B | 子树清场 |
| --- | --- | --- | --- | --- | --- |
| algebra_and_lint_20260929T104946920206Z | WORKER_FAILED/1 | 1.998625 | 59.152 | 0 | True |
| c3_reference_static_20260929T180338558573Z | COMPLETED/0 | 1.519846 | 38.395 | 0 | True |
| cholmod_dependency_20260929T102823494524Z | WORKER_FAILED/1 | 7.300278 | 146.961 | 0 | True |
| e5_analytic_target_capacity_20260929T182053680758Z | COMPLETED/0 | 1.515314 | 41.074 | 0 | True |
| e5_compact_evidence_20260929T182110831272Z | COMPLETED/0 | 1.519980 | 40.312 | 0 | True |
| e5_independent_raw_check_20260929T182126238712Z | COMPLETED/0 | 2.024982 | 60.969 | 0 | True |
| fe_abi_20260929T102600471321Z | COMPLETED/0 | 3.311251 | 175.434 | 0 | True |
| implementation_checks_20260929T105219053119Z | COMPLETED/0 | 1.974255 | 59.156 | 0 | True |
| ml_abi_20260929T102713264800Z | COMPLETED/0 | 6.851944 | 265.969 | 0 | True |
| optimizer_transaction_20260929T111245150321Z | COMPLETED/0 | 5.494056 | 269.293 | 0 | True |
| pure_algebra_20260929T104743142102Z | WORKER_FAILED/1 | 2.664926 | 83.258 | 0 | True |
| sparse_gram_binding_20260929T104918118890Z | COMPLETED/0 | 2.657193 | 93.379 | 0 | True |
| task_local_ruff_20260929T105023806802Z | COMPLETED/0 | 9.171619 | 114.961 | 0 | True |

相关测试文件为 `src/test/test_feinn_full_algebra.py`（4项）、`test_feinn_riesz_ml.py`（2项）、`test_feinn_transaction_ml.py`（2项）和 `test_optical_material_table.py`（7项）。分别覆盖完整保留内部量的A/Aᴴ/原增广关系、复SPD解及symbolic拒绝numeric、优化外层异常恢复与accepted状态、材料离线hash/插值/边界；不会把纯测试称为物理5nm通过。

首次纯代数检查的fixture键名 `dofs` 与实现 `cell_dofs` 不一致，在C1提交前最小修复，原失败日志保留。scikit-sparse打包缺少Cython，改用系统已有CHOLMOD薄C ABI；没有在旧环境安装。后续source、Ruff/compile、输入解析和相关pytest以实际light记录为准，费用全部计入[研究成本](records/resource_costs_v1.json)。

E1真实制造解/384cell完整矩/原action/Gram、3方向FD与batch1/8、q15/30属于正式one-run接口资格，另见[interface](records/interface_gates_v1.json)。它们不是本页纯测试的替代，也不是候选原方程/场/功率通过。

独立stdlib checker从compact原数值重算方程、字段/复杂幅值、功率、能量和资源；大artifact hashes可在本机加 `--verify-raw`：

```bash
python benchmarks/check_feinn_pilot.py --evidence docs/task042extra_feinn_5nm/outcomes/records --output /tmp/task42extra_gate_recheck.json --verify-raw
```

结果见[Gate](records/gate_decisions_v1.json)，而非仅复述status字符串。FE体积分差由原独立积分保留absolute/denominator；complex E/H与ordered通道从compact复值重新算范数；功率差与闭合由原R/T/A_volume重新计算。

本任务Markdown逐页检查closed fences、math fence、表格列数、UTF-8 replacement及本地相对链接；summary按回顾标准16节且至少8张表。总账只运行相关3项Markdown检查，不宣称历史模型/COMSOL数值重验。解析、实际GitHub rendered view、raw blob一致性、浏览器DOM/截图和明确blocked原因分别见[render记录](records/render_check_v1.json)，本地解析不替代浏览器视图。

实际 GitHub Firefox 首轮检查 11 页（任务书、8页本任务文档、两份总账新节），每张表的浏览器 DOM 列数一致。它发现发布任务书 §5.4 的 `\operatorname{Re}` 和本任务方法映射原式的 `\operatorname{solve}` 均被 GitHub 数学渲染器拒绝。任务书由发布方维护，记录为 `RENDERED_VIEW_FAIL_TASK_MATH`；方法映射已改成 `\mathrm{solve}`，其复核随最终 render 记录提交。截图和完整 DOM 留在本任务 ignored 目录，compact 文件保留 hash，不称该失败检查为通过。

实际数值source是E1 C1、E2 C2及E3/E4各run index；之后证据提交HEAD不会冒充运行源码。运行中的HEAD未移动，提交前与推送后clean核验。

## Review V1 后续 V2 定向测试和保留失败

V2 复用原生FE/ML资格环境及V1 native/Gram/历史/checkpoint，不重新安装或重跑旧E0/E1与full pytest。先运行 `src/test/test_feinn_scaling_ml.py` 的9项定向测试、Ruff/编译/FE环境缩放导入检查，再通过正式one-run的D1资格：合成复数非Hermitian A/Hermitian正定G，固定M5上3个非零复向量、3个非零实参数方向，h=1e-4/1e-5/1e-6中心差分，AD共轭转置、`c=Dy`往返、真实Gsolve、预算/线搜索事务及冻结checkpoint一致性。D1全部通过；原始误差与费用见[scaling checks](records/scaling_checks_v2.json)。D0仅评价4个实存状态，未造Adam500中间状态。

首次compare-only因FE进程顶层导入Torch失败于物理前；最小延迟导入修复提交后，默认沙箱在MPI_Init本地socket处失败；在任务自身监督下完成第三次compare-only。两次失败均保留于[run index](records/run_index_v2.json)与[资源账](records/resource_costs_v2.json)，不是数值失败或参考重算。第三次compare-only复用V1准确同p3参考，MUMPS symbolic/numeric/solve=0。独立checker逐字段复算原40级复通道、参考分母、功率、energy、原方程及`D`来源、冻结物理`c`，结果[严格/研究 Gate](records/gate_decisions_v2.json)均未通过。这是固定优化设置的真实负结果，不能被9项接口测试的通过覆盖。

Markdown局部检查范围扩展到新review、获授权修正的task、Response V2、V2诊断、summary和两份总账新增节；检查fence、表格列数、相对链接、UTF-8及解析结果。GitHub渲染只复查review与修正task，浏览器DOM/截图与失败原因见[render记录](records/render_check_v2.json)。本地解析不等于浏览器PASS，也不宣称CI或全仓测试。

实际GitHub预览在首轮Firefox完整页面加载策略下导航60秒超时，无DOM可判；改用 `pageLoadStrategy=eager` 后只对同两页复核成功。Review V1 的6表/3公式和修正task的6表/7公式均无列错或数学报错，全部24张截图hash一致，抽看review首页/公式和task修正公式/表格。[render记录](records/render_check_v2.json)区分失败与成功两次监督，不能用首次失败代替最终结果，也不声称逐张截图人工精读。

## Review V2 后续 V3 定向资格与保留失败

本批没有重装 FE/ML ABI、BLAS/CUDA，也不重跑整套 E0/E1 或 full pytest。实现源 `d9e5a7d00a1cac82390b058384e0cd9193b472d4` 的轻量 `src/test/test_feinn_reference_fit_ml.py`、事务和完整非 Hermitian 代数共 8 项通过；Ruff、compileall及Git diff空白检查通过。首次 `ruff` 在ML环境因可执行文件不在该环境而于启动前失败，改用原资格化FE环境的Ruff检查通过，没有安装或修改环境。FE import/ABI预检在默认执行沙箱被 MPI 本机 socket 拒绝；依既有最小执行权限重试后，PETSc complex128/int64、FE进程未导入Torch及本任务单核/树RSS/zero swap通过。两次费用保留在[V3资源账](records/resource_costs_v3.json)，不把默认沙箱拒绝记为 ABI 或物理失败。

正式 one-run `v3_fit_checks` 实测合成复数目标相对差`3.01e-11`，真实固定 M5 的 batch1/8 c/loss/梯度差`4.22e-16/0/7.96e-16`；三非零实方向、h=`1e-4/1e-5/1e-6`的全部误差均≤`1e-5`，异常事务参数逐位恢复，训练标签hash与master/背景/port身份锁定。P0 `A(c-c_ref)=r-r_ref` 四态差≤`3.45e-13`、真实Gsolve最大相对`2.15e-13`，不重放未保存的旧状态。[资格原始记录](records/reference_fit_checks_v3.json)、[P0记录](records/error_residual_geometry_v3.json)。

P1 唯一训练被执行会话意外中断；最后完整观察825 closure，第817次已提交参数审核只有指标没有checkpoint，最后保留参数为Adam500。原运行没有`run_summary`/final/last_trial，按[中断记录](records/fit_interruption_v3.json)保守计费，不伪造正常停止。恢复接线的轻量8项pytest、Ruff、compileall及新one-run输入解析通过；P2留存态q30与独立FE审核完成，`q30/q15=2.85841e-12`，MUMPS0、整树峰647409664B/own swap0。独立checker从保存参数/完整c、原Gram、原复E/H样本、40级复通道及独立R/T/A_volume重算，所得场/方程/功率检查均false，并断言监督路线的`pde_only_solver_qualified=false`与`official_candidate_results=false`。[V3 Gate](records/gate_decisions_v3.json)、[资源账](records/resource_costs_v3.json)。首次局部Markdown检查因渲染记录链接尚未落盘而失败；创建明确待发布记录后，Review V2与本轮7页新增/修改文档共8页、38张表的链接/围栏/数学/表列检查通过。精确已发布commit的GitHub实际浏览器渲染8页、11表、7公式，26截图hash一致，抽看Review公式、诊断公式与summary结果表；浏览器树峰2042216448B、own swap0，低于2GiB轻预算。[实际渲染记录](records/render_check_v3.json)保存发布blob与URL，旧task/V1不重复全套检查。没有CI或全仓测试通过的声明。

## Review V3 后续 V4 定向资格

| 检查 / 本地实测 | 结果 | 范围 |
| --- | --- | --- |
| C1 optimizer checkpoint＋fit目标/政策 | 9 passed | 小复数loss、完整state加载等价、Adam→fresh L-BFGS、原子写入中断、真实非零strong-Wolfe异常及接受更新量 |
| 自身进程故障 | 4类通过 | 明确停止、监督报告失效、监督SIGKILL清场、启动端退出/关闭输出管道；未测平台回收路径不声称通过 |
| M5阶段边界资格 | 2次完整loss/gradient，配对差0 | E_G0.20082113406866917、native14.263463207213235；不重跑原Adam500/P0/旧FE Gate |
| C2计时修正与fit政策 | 11 passed、0失败/错误/skip | 包含9项复测及2项launch时钟测试；不是20个独立新测试 |
| FE preflight | complex128/int64、MPI1、Torch未导入 | 复用资格化ABI、task-local activation，无安装 |
| final q15/q30独立重建 | 参数→c=0；q30/q15=8.5141e-13 | 完整边/面/内部矩；固定网络buffers与8966参数匹配 |
| independent FE compare-only | 审核完成；严格方程/场/功率失败 | 负结果如实保留，参考复用，新MUMPS0；不把审核完成称solver PASS |
| compact checker | 冻结state/hash/optimizer与原始复场/功率重算通过 | G matvec仅证据验算，无训练、Gsolve或新因子 |
| Ruff / compile / Markdown / GitHub | 按本轮实际记录收口 | 本地与远端渲染分列，不推断CI |

初始小测试快照见[durability checks](records/durability_checks_v4.json)，后续边界与11项复测见[post-fit checks](records/post_fit_checks_v4.json)，完整检查点见[checkpoint index](records/checkpoint_index_v4.json)。R0小问题同时树≤2GiB、自身swap0；数值阶段逐个监督并清场。原始Ruff/compile/测试/浏览器尝试及所有失败费用在[资源账](records/resource_costs_v4.json)，不full pytest、不重验整套E0/E1，不宣称GitHub Actions通过。

C1正式段的保存留白有计时偏差，作为规则未满足记录；C2已用launcher时钟和150s cutoff修正，并有定向测试，未再次正式执行。旧V3后段状态未恢复，失联原因仍unknown。[新review及V4页渲染记录](records/render_check_v4.json)分别绑定真实GitHub DOM、published blob和截图，不能用本地Markdown代替。

## Review V4 后续 V5 定向资格

本轮复用已资格化的原生FE/ML与V1–V4完整矩/算子证据，没有安装、full pytest或旧heavy重跑。新路径的11项定向tests两次均通过（最终修改后重跑）：小复SPD满秩/重复/近相关/尺度/纯虚配对独立白化SVD、G列计数/预算/负范数拒绝、实际实虚末层/bias和完整矩映射、标签输入与FE顶层Torch隔离、launcher时钟。Ruff和compileall通过，首次静态检查有两个unused import，在正式运行前移除；费用由直接120s保守计费覆盖，失败不记为数值失败。

| 检查 / measured | 实测 | 判定范围 |
| --- | --- | --- |
| 持久clock dummy | importdelay0.663786s，退出147.705s，过期数值工作0，watchdog清场 | 150/120s协议通过；不追认旧V4偏差或所有平台断连路径 |
| S0 M5 | 原a0差3.077e-15，3非零复/纯虚/bias/内部/edge/face/batch1/8≤1e-10 | 新线性接口资格；c0/E_G/native与V4相同 |
| 独立投影checker | 591次列G复算，orth2.324e-13、实际最优性1.394e-13、回写通过 | 不重求投影或训练；不是strict physics PASS |
| 独立ML q15/q30 | 参数→c差0，q30差7.893e-13 | 一次最终求积复核，无改q15后重训 |
| 独立FE compare-only | complex128/int64/MPI1、Torch未导入，原方程/场/功率未通过 | 原参考只读，新MUMPS0；监督官方资格固定false |
| 新Markdown / GitHub实际view | 以本地解析及render JSON为准 | 不批量重渲染历史，不声明CI |

原始资格：[readout checks](records/readout_checks_v5.json)，独立Gate：[gate](records/gate_decisions_v5.json)，完整费用：[resource](records/resource_costs_v5.json)。run source `a6ac769027384525e406537f3069607043bc4a67`；checker字节hash与light日志独立绑定，不把后来文档HEAD当运行源码。GitHub实际新review及必要新节检查见[render](records/render_check_v5.json)，状态由真实DOM/截图决定。

## Review V5 后续 V6 定向资格

| 新检查 / local | 结果 | 范围 |
| --- | --- | --- |
| 纯数值targeted pytest | 8 passed；最后版本0.20s | 复非Hermitian、满秩/重复/近秩亏/尺度、独立SVD、两置换与标签白名单 |
| ML targeted pytest | 2 passed，1.95s | 新坐标反变换→原实虚bias/三分量；FE顶层Torch隔离 |
| M5 T0 | PASS；3方向A3/A*3/G6 | seed421601，不重建Phi/GQR |
| 唯一主阶段 | FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED | 不是物理合格 |
| 独立ML/FE/checker | 完成；q30 7.26e-13；总A206/A*3/audit4/G16 | 新MUMPS/Gsolve/因子0 |
| Ruff/compileall/diff | PASS（两处unused import局部修复后） | 受改文件，无full pytest/CI声明 |
| 本地Markdown/GitHub view | 记录分别核查 | 不以结构PASS替代视觉审核 |

定向文件、ABI、日志hash见[tests](records/targeted_tests_v6.json)和[真实T0](records/residual_readout_checks_v6.json)。旧资格复用；数值核心与测试文件在C1后无数学改动，后续checker仅去掉无用import，不重复昂贵原算子审核。费用、一次状态探针index大小写错误及纠正保留在V6直接/辅助账；主阶段实际先收尾再启动ML，没有重复主阶段。

[本地文档/实际浏览器证据](records/render_check_v6.json)只覆盖Review V5和新V6小节。

## Review V6 后续 V7 定向资格

提高一次有限元阶次只改变每个单元表达场细节的能力。本轮测试先确认两个阶次描述同一物理场时仍得到相同的电场、旋度和周期恢复，再允许唯一准确参考尝试；接口通过不等于参考求解完成。

| 本地检查 / 实测 | 结果 | 证据和限制 |
| --- | --- | --- |
| C1 数组/跨阶 FE targeted tests | 10 passed，1.47s | 非零复场、方向/MPC、体和DtN q15、数组容量、原子packet、显式stage；Ruff/compileall通过 |
| 正式 U0 公共场/curl/MPC及原action | 全部≤1e-10 | 两种规模、完整边面内部和三非零复方向；实测75264独立复FE/40端口，symbolic容量未取得 |
| C2 停止后入口/checker targeted tests | 10 passed，0.18s | 原字段故意损坏不能通过；近零分母、导入延迟截止和启动前p4身份；Ruff/compileall通过。没有正式重放修正后的入口 |
| 独立原记录 checker | U0通过，p4时间阻塞，U2未运行 | 核对唯一启动、原hash、请求时钟、清场摘要、原样本与旧not_run；不求解或造新参考 |
| p4原残差/物理/U2 q30差值 | NOT_RUN | 唯一参考在数值截止前未取得恢复packet；不是精度超限、OOM或数值通过 |

C1资格对应实际源码76d863e43d2fc1b5bed8b1c835aa6f43bb2c93d2；C2资格对应c2bfd3ce2ae5d499b6d8afe6a0b3fc3cf743a2a9。轻测试在提交前完成，最终相关文件字节与指定commit逐项一致，见[targeted tests/source/log hashes](records/targeted_tests_v7.json)。U0第一次FE fixture degree错误、之后Ruff E741、C2 Ruff E731都保留日志与费用，修正后最小定向复测通过；没有full pytest、环境重装、CI或其他项目资格声明。

复用已有Linux complex128/int64 ABI及环境证据；FE未顶层import Torch。已测跨阶配对不代替一次阶次变化的物理差异。本地只解析新Review V6和本轮9页/新节的围栏、表列及链接；[真实GitHub rendered view](records/render_check_v7.json)单独绑定已发布blob、DOM和抽看的截图，无法取得则记录blocked。本地解析结果和最终费用后续写入[tests](records/targeted_tests_v7.json)与[resource](records/resource_costs_v7.json)。

## Review V7 后续 V8 定向资格

| 新定向测试 / 本地 | 实际结果和范围 | 证据 |
| --- | --- | --- |
| A装配/独立核/复JSON小tests | 最终8 passed；非零复场、非Hermitian/伴随、内部/port/准确展开CSR与独立Basix核 | 原日志/source在targeted_tests_v8 |
| B/阶段/预算/标签与事务 | 最终9 pure＋6 ML passed；k=0/固定buffer、数据读审计、真实非零strong-Wolfe异常回滚、完整state和launcher时钟 | 同最终bc052a3文件字节绑定；不同suite不重复加独立数 |
| B正式M5 | k=0、独立相位、非单位Floquet、3非零实方向VJP、batch1/8、q15→30→60通过 | phase_checks_v8原值/稳定区与hash |
| C/D实际 | 匹配持久模型/optimizer保存，四条无故障恢复；C各4000/D各1500计费closure | 负结果不是接口PASS或求解通过 |
| 冻结后独立ML/FE | 参数→完整c、q30、G/L2/curl恒等式、6点复E/H与完整40级通道/功率 | compare-only；无新MUMPS或Gram factor |
| E原记录checker tests | 10 passed；伪造status、复通道/分母、监督official边界、缺40级、G能量、零方向、共同wall、逐级功率和总R/T配对、当前/其他未完监督隔离 | 最终完整record checker从原字段重算 |
| Ruff/compileall/Markdown/GitHub | 按本轮source/日志/DOM记录分别核对 | 只改文件/新页，不full pytest或CI声明 |

首次profile JSON复数、Ruff环境位置/unused import/format错误都保留失败成本，定位后最小修复及定向重试，非物理或ABI失败。FE复杂scalar complex128/int64与未导入Torch复用并轻量确认；无重装。所有轻测试/浏览器受自身监督≤2GiB、swap0，长数值MPI1/数学Torch1/CPU-only/单空闲物理核/树warn12-hard16GiB。实际测试文件/bytes/log/summary hash见[tests](records/targeted_tests_v8.json)，[Gate](records/gate_decisions_v8.json)，[资源账](records/resource_costs_v8.json)。本地Markdown与[GitHub实际DOM/抽样截图](records/render_check_v8.json)不互相冒充。

## Review V8 后续 V9 定向资格

复用已资格化环境与原完整矩/资源保全证据，只检验新增部分；未full pytest或重装。

| 检查 | 结果/具体范围 | 证据 |
|---|---|---|
| FE/ABI与p5新增 | complex128/int64/MPI1；20个目标测试；小凝聚/full、MPC、独立能量及真实p5A/AH | records/targeted_tests_v9.json；p5_authority_v9.json |
| GN小模型 | 12个独立合成/事务测试；复非Hermitian显式J/K、非线性曲率、PC/SPD、保存加载 | 同上 |
| 真实B资格 | 两C500完整c/原loss/native、3非零JVP方向/伴随/K、batch1/8/固定buffer | records/gn_checks_v9.json |
| E派发及共同时间 | 5个FE/metadata/PC检查；FE阻止Torch导入；1个ML持久runner fixture | records/targeted_tests_v9.json |
| 最终checker修改 | 2个原字段checker测试、Ruff/compileall；全部V9原字段checker成功 | records/targeted_tests_v9.json；gate_decisions_v9.json |
| 独立最终复验 | 四条q15从参数重建相同；q30≤1.85e-12；全域/区域G范数恒等式≤6.17e-14 | PDE/FIT比较记录 |
| 文档与浏览器 | 新页结构检查与GitHub实际渲染分开；实际状态以记录为准 | records/render_check_v9.json |

lint失败两个未使用名称已局部修复，成本保留。以上是本地证据，不声称CI；数值负结果不改成测试失败或PDE通过。

## Review V9 后续 V10 定向资格

本批测试检验同一完整参数导数能否少做重复前向，并保证预算/恢复只提交已验证的完整状态；接口通过不等于原方程或表示门限通过。复用qualified FE/ML环境和旧完整矩/相位证据，未full pytest、未重装、未宣称CI。

| 定向资格 / 本地实测 | 结果、失败边界 | 原证据 |
|---|---|---|
| 缓存切线/匹配伴随与小复链 | 最终19 ML＋1纯FE-dispatch；非零方向、所有边/面/内部、batch1/8、失效/恢复和实伴随 | targeted_tests_v10.json及hash绑定日志；重复测试不加为独立数量 |
| 四个真实V9固定态 | c/JVP/VJP/伴随≤1e-10，K/梯度≤1e-9；最终两C完整s/pred/ared逐位一致 | cache_checks_v10.json；初版/第一canonical方向超限保留 |
| 预算末端与事务 | PC不足/中断、有限CG真残差、方向验证、拒绝回滚、原子提交、缓存键和spent PC quota通过 | 8项相关ML及阶段/白名单原日志，未重演旧长训练 |
| 本轮完整状态恢复 / 导出 | 12项相关资格；保存/失联边界、参数/buffers/GN/RNG/hash/标签与spent计数；导出9 pure＋1 ML | 真phase第60/75边界完整c逐位一致；原PT不改；两次PSI中断成本保留 |
| 最终compact checker | 5 passed；损坏label/counters/完整proposal/timer/compact大小不能通过 | 606ad775源码；先lint失败一次、修正后通过，原字段checker已完成 |
| 冻结后独立ML/FE | 四个新终态参数→c相对差0；q30≤1.103e-12；全场/6点/四类各40级复通道/功率/区域及G范数恒等式 | compare-only仅复用原p3参考，未新MUMPS或Gram factor |
| Ruff/compileall与新页结构 | 最终相关文件检查；Review V9与8个新页/追加节，不全量重渲染历史 | 本地结构与render_check_v10.json实际浏览器记录分开 |

两次phase系统压力停止是执行安全原因；自身swap0/树内存合规，不写OOM、正常预算不收敛或网络不可表达。所有测试失败、保存fixture/metadata问题和对应局部修复见[repair log](records/repair_log_v10.json)，全部费用见[资源](records/resource_costs_v10.json)。[测试原日志/source/hash](records/targeted_tests_v10.json)、[原字段Gate](records/gate_decisions_v10.json)与[实际GitHub渲染](records/render_check_v10.json)均单列。
# Review V10 后续 V11 定向资格

最后成功的新页检查是15:31 UTC的8页26表；最终费用数字更新后的额外table-only检查因无空闲物理核未启动worker，记NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE，不重试，费用从已有尾段预留计入。

本节只记录本批新增路径，不重跑旧四态缓存 benchmark、参考求解或 full pytest。最终本地8页26表解析、Ruff/compileall与原字段checker通过；GitHub视觉为已目视确认的Unicorn服务错误页，记BLOCKED。小型模型测试证明接口和状态保全；实际 M5 的独立审核另见 [Gate](records/gate_decisions_v11.json)，不能用测试通过代替物理精度。

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 固定度量的两种代数关系、S=I、组顺序 | 10 targeted passed | `tmp/task42extra/checks/v11_B_metric_unit_corrected_20261002T104310046901Z` |
| 原 GN 接受/回滚、缓存和持久事务 | 17 targeted passed | `tmp/task42extra/checks/v11_B_transactions_20261002T104543790954Z` |
| 复用 runner 的度量 fork/完整状态 | 8 targeted passed；后续相关边界 15 passed | `v11_B_metric_runner_20261002T104736215729Z`、`v11_B_commit_boundary_20261002T110532265889Z` |
| 真实 A | 26 K、4 真实试探；恢复 theta0/cache；启动信号成立 | [尺度记录](records/parameter_scale_v11.json) |
| 真实 B 链式作用和 S=I proposal | g/K/proposal 配对相对差 0；3 方向均有两步稳定 FD 见证；累计16 K | [接口记录](records/metric_checks_v11.json) |
| FD 修复小测试 | 两次各9 passed；最初真实 FD 和第一修复失败保留 | [修复记录](records/repair_log_v11.json) |
| 共同时间/工作量选择及未来恢复次数元数据 | 4 passed；未到时点不生成，禁止按误差挑状态 | `tmp/task42extra/checks/v11_E_frozen_views_tests_20261002T143356060820Z` |
| 独立 ML q15/q30 | 实际参数→保存系数相对差0；终态 q 漂移约1.6e-15 | [字段诊断](records/metric_field_diagnostics_v11.json) |
| 独立 FE compare-only | 9个实际冻结状态完成；没有新参考 solve/factor | [比较](records/metric_comparison_v11.csv) |
| 纯记录 checker | 重算复场、通道分母、功率、G范数、接受/CG及资源；完成 | `tmp/task42extra/checks/v11_E_compact_json_repair_20261002T150136052008Z` |
| Ruff / compileall | 新增及相关修改模块通过；最终文档合同另核 | [文件范围](changed_files.md) |

首次误选不存在的测试文件得到 exit4，随后改为存在的 targeted selector；不重装环境。两次轻量 checker 启动前 CPU Gate 拒绝，worker 未启动；带只读诊断的原 Gate 通过后，checker 定位并修复 compact JSON 排版体积问题。所有失败/准入/修复成本保留。仅本地测试，不声称 CI。


# Review V11 后续 V12 定向资格

本批新数学先过非Hermitian复数二次型交叉、实参数加权QR/SVD、重复/近相关/尺度列和损坏输入；两个保存态另以原torch.func JVP/AD VJP和两步有限差分配对。没有新训练、四态缓存benchmark、参考求解或full pytest。

| 范围 | 实际结果 | 口径 |
| --- | --- | --- |
| 原代数+阶段/预算白名单 | 13通过 | source521b9，未变逻辑资格复用；首次取消余项错误及费用保留 |
| 保存场接口+8-cell FE新接线 | 4+1通过 | sourcebc4c；独立常复场积分、固定区域/顺序、计数与损坏hash |
| p4散射参考schema修复 | 5通过 | source6c844；明确c_scattered，拒绝错字段/端口代替master |
| 原字段checker+损坏记录fixture | 真实B/C1/C2重算通过；6fixture通过 | 无训练/G逆/FE新求解；错误loss、identity、cap、spectrum均拒绝 |
| 合并24项最后invocation | worker未启动，RESOURCE_WINDOW_UNAVAILABLE | 不称24/24通过；分组件资格及最终schema/checker测试分别绑定 |
| 新E/curl交叉/邻层积分 | 资源未运行 | 不以旧区域或C2嵌入配对替代该新增积分 |
| 两态局部导数/8个恢复见证 | JVP/VJP差0，实伴随≤7.87e-18，FD≤2.40e-9；参数/buffers恢复 | fixed real directions，reference exposed diagnostic only |
| p4测试空间 | 6 A4，旧参考4.29e-12，映射≤7.92e-15 | c字段错误首尝试保留；无G4/装配/新solve |

最终Ruff/compileall只覆盖本批改动源码，新Review/三新页与追加节的parser和实际GitHub视觉分列。原始source/日志与Junit见[tests](records/targeted_tests_v12.json)，真实vector重算见[checker](records/independent_checker_v12.json)，[资源](records/resource_costs_v12.json)和[render](records/render_check_v12.json)不合成PDE PASS；无CI声明。

V12收口实测：16个本批Python源文件Ruff和compileall均通过；9个选定新页/新增节本地parser通过（30表格）。GitHub真实DOM/截图资格另以render记录为准。

V12实际GitHub检查：发布cad9fe635199d5c22e83a0698b7412e349449aaf的Review V11与Response V12取得DOM/截图，18表列数一致，review三组公式及关键结果/宽表左右/Gram成本截图实际可读，`GITHUB_VISUAL_SPOTCHECK_PASS`。单次42.048241s/1800376320B树峰/swap0/清场；没有重渲染历史，也没有把本地parser当视觉证据。后续只改费用/hash/此条文本，最终本地parser另绑定。

# Review V12 后续 V13 定向资格

本批只测试新增C1自动分类、背景仿射加法/累计计数及最小FE接线，不重复旧8见证、训练/参考/缓存benchmark或full pytest。

| 检查 | 实际结果 | 范围 / 证据 |
| --- | --- | --- |
| C1小复非Hermitian实参数正/损坏fixture | 54通过 | 独立白化小例；两类比例、before/after及所有cross字段损坏、8类非有限原向量均拒绝 |
| 最终pure+FE定向资格 | 73通过（包含前54，不相加） | 新背景复杂数加法、分母/相位损坏、失败预算保全、新dat政策及一个8-cell完整P34/MPC/公共积分fixture |
| ABI | complex128/int64/MPI1，FE未import Torch | 同一已资格化stack，未重装；abi_v13.json及测试记录绑定 |
| 真保存B/C1向量checker | 通过；新增算子/网络0 | 八个范数直接复用review核验，不重生成见证 |
| 唯一真实背景B / 冻结后独立checker | 2 A4，公共E/curl/MPC、加法/能量/差分恒等式过原门 | 新source8000ee893a42e2f3cef288fe4652ee1052d511e7；原p3负结果不变 |
| Ruff/compileall | 实现8个Python文件通过；新文档checker另外检查 | 本地证据，无CI声明 |
| 新页parser / GitHub实际视觉 | 独立有限检查记录 | 不重渲染全部历史，不把发布端结构检查当视觉通过 |

一次轻测试调用因无空闲物理核未启动；原Gate的新只读窗口准入一次后，73测试通过。数值修复0次，文档修复2次（转义及GitHub拒绝公式宏），B数值重试0次，所有费用计入完整墙钟账。[定向原日志/JUnit](records/targeted_tests_v13.json)、[独立checker](records/independent_checker_v13.json)、[失败/准入](records/repair_log_v13.json)、[渲染](records/render_check_v13.json)。旧V12合并24项未启动及新增FE邻层积分未运行不改标。

首次本地parser为8页26表通过；GitHub发布bebd08f24d50f9791e03e7ca5ea5d0c2dcc7d4d9的回执公式/结果表目视通过，专题公式报实部宏不允许，25.759025916s/1810116608B树峰/swap0/清场。专题宏已改为 `\mathrm{Re}`，数学不变；修正后的parser与浏览器复查资源未运行，不冒称最终视觉通过，也不在唯一资源重新准入用完后继续等待或重启。仅追加文档、记录与Git收口，未再运行数值测试或算子。

# Review V13 后续 V14 文档核验

本轮只运行改变页面的现有Markdown parser/链接检查和有限实际GitHub渲染；真实结果与source/hash/资源见[归档收据](records/archive_receipt_v14.json)。V13的73项数值资格直接复用，54项包含在73项内，未新增或重复数值测试；不声称CI通过，不full pytest、不FE/矩阵作用、不安装环境。

未变专题最终公式的本地parser及实际GitHub视觉PASS复用[Review V13收据](records/review_v13_evidence_audit.json)，绑定专题SHA256 b1a7541ee4b7a4d746f4d80b6ddc6e7e9a703dcbae86369c1630a5eb65965dd1；旧首次失败及资源未复验原记录均不覆盖。新/改变页的结构检查、实际视觉和未验证状态分别记账。

## V15：保存数组诊断定向资格

87项pure定向测试通过，改动Python Ruff/compileall通过；新增共同可行/真实冲突、复数白化、近相关与标签隔离/损坏记录/先fsync候选后参考读取的端到端fixture。首次近相关拉回失稳25通过/1失败保留；QR后小R-SVD修复26通过，再最终组合87通过。独立实际数组checker复算8配置通过，M3600保守界宽目标UNKNOWN不冒充数学全资格。未运行FE/MPI/full pytest/旧73项或CI。[测试hash](records/targeted_tests_v15.json)、[checker](records/independent_checker_v15.json)、[repair](records/repair_log_v15.json)。

V15浏览器补查：原实际截图的回执核心表仍停留页首，保留该失败；修复当前DOM重取后compileall/Ruff与唯一核心表定向视觉复验通过。数值核与浏览器合计2/2局部修复；四review公式、四专题公式/四表及回执身份/核心表通过，非全量旧历史或最终新增说明段视觉验收。

## V16：完整记录checker与冻结方向归因

最终受影响75项pure checker测试通过；相关143组合通过，未变代数组件按相同文件hash复用；Ruff/compileall通过。八配置/32点fixture覆盖本review漏检、合法PARTIAL/UNKNOWN、真实ledger/hash/事件、用途、阈值余量及不调用优化器。测试钩子生命周期1次意外修复，首轮8失败/67通过保留；V15原历史数值1+浏览器1=2。唯一原数组复验通过，M3600界宽UNKNOWN和无标签NOT_ADMITTED保留；只核验两条方向端点。[测试](records/targeted_tests_v16.json)、[checker](records/independent_checker_v16.json)、[GitHub实际视图](records/render_check_v16.json)。无full pytest/MPI/旧FE/重装或CI声明。

## V17：暂停交接的静态与文档检查

只做源码文本/AST/相对import小fixture、源码资格hash复用、改变页Markdown/链接/JSON检查及有限新页实际渲染；已有75/143相关资格不重跑。静态脚本首次遗漏src.io包相对导入，一次有依据修复通过，原失败与费用保留。新数值/FE/producer/优化/前向/完成器及full pytest未运行，Ruff/compileall旧资格按未变source复用，不称CI。实际范围/资源/渲染见[交接收据](records/handoff_receipt_v17.json)，[依赖与原测试入口](records/diagnostic_dependencies_v17.json)。

## V18：受约束方向、区域积分及持久真实网络见证

只做受影响pure fixture与真实父监督接线，没有full pytest、无关MPI或旧数值全量复验。最终A/B/C组合、Ruff/compileall、改动文档合同及原记录hash检查见[测试收据](records/targeted_tests_v18.json)。开发时lint、近零分母损坏fixture、语法/作用域错误，以及正式C重复不可覆盖记录错误的失败证据和费用均留[修复账](records/repair_log_v18.json)。

A独立从原数组重算四配置、冻结顺序、实PID、N/R/F及保守证书，不调用优化器；B检查原能量/四区域/体积/近零分母/G恒等式，不执行FE或算子；C独立2A/4G检查实际场和原保存向量，后独立FE恢复两个c。全部真实性通过；实际R不增门两態FAIL，不因checker通过声称solver通过。新页结构与有限GitHub实际渲染分开，[render](records/render_check_v18.json)保留未测尾段及旧失败。

## V19：Review V18停止落实的受影响文档检查

实际仅完成pure身份/hash检查：原task/Response V18及16份相关源码、发布文档、4669个tracked路径与数值交付后的两文件差量通过；3.00519637496s、同时树峰57,675,776B、自身swap0、已清场。改变页Markdown parser/本地链接/compact JSON及自动历史正文保留检查两次在worker前被CPU门拒绝；唯一再准入前有实测新窗口，但启动时窗口消失，NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE。不直接裸跑绕过保护，Git差量人工核对/`git diff --check`不是parser通过，具体见[一次P0收据](records/closeout_receipt_v19.json)。未重复全库hash/AST或V17静态清单；原ca7ad5d的52 targeted/Ruff/compileall按未变hash复用，无新pytest、full pytest、FE/前向/算子或CI声明。

Review V18最终公式及旧专题两张区域表右侧的实际浏览器资格复用[审阅收据](records/review_v18_evidence_audit.json)，旧失败及原执行端部分视图不覆盖。新改变页视觉为NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE：资源链停止后未启动浏览器，不假称截图/DOM或视觉PASS。没有实际复用需求，A checker半径及原始列来源绑定限制保留，不加无关fixture或重跑A/B/C。

## V20：相位进入FE基函数的联合资格与独立保存场检查

最终受影响pure fixtures41 passed、Ruff/compileall通过；κ=0对真实旧build_physical_rhs回归差0；8-cell双向空气独立Poynting及全部36模式/逐级/能量通过。原A20门通过，原air_plane_power为振幅平方proxy，物理通量由独立补验收据给出而不追改含义。最早A残差超门及CSC修复、O3坐标修复仍超门、p6内部端口支撑拒绝都保留；测试通过不表示B候选解通过。

唯一最终纯数组checker source0ede17f482d6370ce84bf8bbf0c638e7f95193ab，5.184892364s/224890880B采样树峰/swap0、已清场；逐模式/物理key/参考面与坏输入fixtures不调用FE/solver。C source d9f1b50ee9b7be66d610fbbb78449bc9f6a3dc2f，q15/q30积分漂移3.39275e-12，仅两未合格空间争议，O6/E4缺失为PARTIAL/UNKNOWN。所有开发失败和最终fixture配置KeyError修复日志均hash绑定，旧昂贵测试不重跑，无full pytest/CI声明。

[测试/原日志](records/targeted_tests_v20.json)、[原资格和补验](records/qualification_v20.json)、[checker](records/independent_checker_v20.json)、[修复](records/repair_log_v20.json)。文档parser/实际GitHub关键页目视与完整费用另行封存，不把DOM检查冒称视觉。

本批改变的8处文档parser/链接/表格/公式检查、716行原CSV逐值配对及旧正文保留已通过，另20项仓库原则/总账Markdown/回顾合同pure测试通过。旧全库总账测试仍按40任务限定并引用历史缺失文件，修改前后两项错误完全相同，记PREEXISTING_FAILURE_NOT_FIXED_OUT_OF_SCOPE；不改其他任务历史或声称全库测试通过。原失败与基线核对见测试收据。

## V21：准确端口/拓扑资格与保存物理独立复验

以原资源单核/2GiB运行受影响pure fixtures、真实E4保存MPC及损坏负控；新正式资格prefix/两轮修复、P2/E4与独立compare/checker逐项source绑定。纯测试/解析/CI口径区分，full pytest、无关MPI及昂贵旧资格不重跑。P2前legacy mock未及时检查的流程失败保留，修正后E4前通过；普通p6 q15/30负结果不当bug再次启动。详细测试/初始失败/本地文档和视觉见[tests](records/targeted_tests_v21.json)、[repair](records/repair_log_v21.json)、[render](records/render_check_v21.json)。

## V22：可靠总场/解析面/条件修正的定向与独立核验

求解前47项pure资格已冻结；最终checker的54项pure fixtures、Ruff/compileall通过，old/new比较alias禁止同角色控制授予准确参考，并显式保留guard digits。独立raw surface从CSR重算36/340模式及三个非零作用后才启动修正。真实p3/p4/p6面与两次新的双向空气Poynting通过，E3/E4完整未凝聚/独立弱式/存储D/H准确回代/MPC复验通过；实际c的独立物理面积分原点投影另列敏感性与未过项。最终compare-only/pure checker从保存场重算，不复求参考。实际source和数值负项见[测试](records/targeted_tests_v22.json)、[checker](records/independent_checker_v22.json)。没有full pytest、旧昂贵Gate、无关MPI、CI或环境重装。

初始phase轴/JSON/lint/mock失败及三正式失败/受控停止均保留[repair](records/repair_log_v22.json)；早期42-test XML被复用输出路径覆盖，原日志/预期hash标NOT_RETAINED，未重放补历史，47项准入及最终54项XML各自独立冻结。文档parser、全CSV/raw/historical正文及局部实际GitHub视觉单列，不把结构通过当视觉；未变Review V21呈现按已验收收据复用。原registry两失败在输入与当前同样保留，不改其他任务。


## V23：实际入口拒绝、局部面组件与独立保存数组

47项最终pure fixture通过，包含真实load/workflow分派、campaign/direct求解哨兵前拒绝、schema/错caller/file/hash、独立Decimal80/110固定Gauss64、区间中心相位/1/2换元、局部复数法向/共轭伴随及损坏数组。Ruff/compileall局部通过，无full pytest/CI/安装。当前native complex128/int64/MPI1预检及60s窗口通过，Basix局部p4/p6方向/独立点值、上下s/p/三非零方向/原H完整消费已正式运行。两种实现仅各一次冷生命周期；后续独立checker只读保存数组，不重跑producer。

P0最初workflow接线和compact负控字段失败保留，修复测试后最多两次重试；初期CPU拒绝及两次新窗口再准入、mpmath缺失和格式失败保留。资格化面组件没有重放；43-test早期XML被47-test覆盖，原XML NOT_RETAINED但日志/费用保留，最终47-test XML唯一保存。旧Review V22已视觉封存证据复用；新页视觉只记实际浏览器结果，不以本地parser替代。

[测试](records/targeted_tests_v23.json)、[修复/限制](records/repair_log_v23.json)、[独立checker](records/independent_checker_v23.json)、[视觉](records/render_check_v23.json)、[完整费用](records/resource_costs_v23.json)。两实现局部都过，但解析成本无20%优势，推荐q60；不提升旧投影FAIL为严格解或NN收益。

## V24：W0实际科学raw与独立checker闭环

最终28项pure定向fixtures覆盖固定源码、公共one-run识别、单调截止、自身终端PID/start/UID/锁、观察器自耗及邻任务保留、EMFILE子进程/自身hard FD不变、5000别名复用、数组损坏/缺件/额外字节/逃逸/关闭；Ruff/compileall通过。最终Junit见[测试索引](records/targeted_tests_v24.json)，最初9项Ruff错误、fixture NameError与入口首行错误均保留，不标full pytest或CI。

实际原数学worker一次，独立checker总三次数值尝试（两次EMFILE/末次955门及4负控通过）与一次数值前CPU拒绝独立计费；原raw不覆盖。纯数组逐成员readback通过，6.97152s/105771008B/own swap0；没有新FE/factor/solve。stage原采样及source/hash见[运行](records/run_index_v24.json)、[原门](records/independent_checker_v24.json)、[readback](records/durable_readback_v24.json)。

初始优先级/IO/终端亲和性缺口限定保留；W0同80组件不能替原尺寸散射有效解。新关键页[GitHub呈现记录](records/render_check_v24.json)独立记录实际范围/失败，旧V23已验收视觉按原收据复用，不重复批量渲染。

## V26：R接线增量资格与资源拒绝

新src/test/test_w1_input_recovery.py的16个独立fixture最后全部通过，Ruff/compileall及公开run_case --validate-only通过；source9ec41386完整SHA见[索引](records/run_index_v26.json)。旧A的92项JUnit、受测source和receipt按hash复用，不重执行。新fixture只核schema/来源/正文/失败监督/窗口与全频率枚举，执行frozen zvalue不构造库存，不导入FE跑积分，不能当跨ABI输入重现或物理资格。

初始JSON整数资源键、输出目录、缺冻结模块/Mapping及未使用导入lint失败均保留；四个受监督增量资格2.533773/2.688902/2.259993/2.656706s，最后16/16且Ruff通过；最大采样同时树峰93,003,776B、hard2GiB/ownswap0/清场。重新准入dat曾复用output_root，重复保护拒绝后仅修dat根并定向断言全部路径同根，另列严格修复轮限定；没有因此重复worker或生成器。

两次R内层资源拒绝使ABI、native方向/MPC、完整q60/Decimal覆盖及数值保存checker全部未运行。关闭后只核saved receipt/JUnit/current source和43个Git原blob，不重producer、A/full pytest、昂贵FE、参考或NN。新页本地parser与旧正文保留检查另记；实际GitHub两新页发布6a698306…标题及4表、6图目视通过，浏览器21.901543s/树峰1,775,185,920B/ownswap0且清场；其他导航/最终seal尾段不授视觉PASS，旧review有限范围按原审计复用。[测试](records/targeted_tests_v26.json)、[metadata checker](records/independent_checker_v26.json)、[修复](records/repair_log_v26.json)、[呈现](records/render_check_v26.json)。

## Review V26 后续 V27：39项增量资格、一次真实R及保存拒绝

新资源范围、失败观察、typed Git blob/磁盘封存、marker-last、实际writer/seal/reopen/消费者和窗口限额共23项新增，与16项受影响旧增量共39项通过；Ruff/compileall及四份v27dat validate-only通过。旧A92由原source/hash绑定复用，没有重跑。最初两次fixture各33pass/1fail及一次旧A路径资格失败保留；修好后扩充相关测试，最终39pass。clean实现904131e19396c4b6896d42056df2e27387908c1f之后无正式工程重放。[原日志](records/targeted_tests_v27.json)。

唯一真实R得到BITWISE_REPRODUCTION_FAILED：文件36,263,033B，原36,244,923B，完整SHA不同；32060keys和物理hash一致不能替代原件。运行COMPLETED/exit0不等于科学PASS。实际43Git blobs与manifest封存成功，独立只读checker重算完整hash/keys/身份并用实际commit/消费者验证拒绝；checker4.873763s/341,622,784B/ownswap0、2GiB、子树清场。B0/B1和B1物理checker未运行，原字段差NOT_RETAINED；未full pytest/CI/旧昂贵回归，未调整ABI。[保存checker](records/independent_checker_v27.json)、[完整费用](records/resource_costs_v27.json)。


## V28定向资格与真实数值验证

最终36项pure delta通过；新增1项局部import/provider回归独立受监督通过，旧92A和39V27根据受影响依赖复用。正式input_contract阶段29项已通过；后续局部修复只补相关测试，所有precommit lint/fixture及资源拒绝保留，不full pytest、不重装、不声明CI。普通fixture中的Basix/积分替身不当作FE证据。

实际科学资格另列：32060模式/416780字段检查；真实Basix p4/p6全列/非单位Floquet控制；1004完整chunk的全模式q60；独立pure保存checker1218328数值门；另一个新目录1043文件的模式物理与同一数值门重新核验，全部实际通过。原q60最大9.595725209727146e-11≤1e-10、一维矩9.082805012334877e-14≤1e-12，未放宽分母。健康producer不重跑；软件接线失败不是新的数学失败。消费最后复用同一已批准样本/PSI/clock，未重新采CPU，其流程限定如实单列。

[测试与原JUnit](records/targeted_tests_v28.json)、[真实source/run](records/run_index_v28.json)、[独立数组checker](records/independent_checker_v28.json)、[实际consumer](records/consumer_receipt_v28.json)、[失败/修复](records/repair_log_v28.json)、[资源](records/resource_costs_v28.json)。最后Markdown/JSON/链接和历史保留结构检查单列，不冒称GitHub视觉PASS。

## V30有限准入与独立验收依赖接线

27项pure串行/身份/父进程/时效/PSI/swap/间断负控＋最终1项外层拒绝保存通过，Ruff/compile通过；初次24项通过但28处测试格式错误仍保留。仅是纯开发fixture，无FE/参考加载或新60s数值稳定资格。实际2GiB整树、fresh CPU、当前PSI及Health监督，最后树峰152231936B/ownswap0。新数值启动仍必须单独60s PSI；后续FE/pure只能复用同一活监督树的实际最近完整60s，再现场复核CPU，阈值未变。[source/费用](records/dependency_qualification_v30.json)。
