# Task43 选择性合并清单（待外部审阅）

## V19 当前依赖组：保存数组研究诊断完成，无合并批准

| 依赖组 | 本轮变更及依赖 | 验证／建议审查顺序 |
|---|---|---|
| production numerical/core | 无改动；方程、离散、求解、默认writer不变 | 新增fresh PDE=0，不授予生产资格 |
| reusable runner/watchdog | 共享watchdog/activation/ABI不改；任务内短launch及snapshot归档 | 仅T1/D1/D2实际父链、CPU/资源/清理证据；不授予通用运行器资格 |
| checker/benchmark | 新`analyze_saved_hp_response.py`，stdlib/NumPy读旧数组；依赖固定V19合同及17项旧输入身份 | 先审输入/owner、两种独立恒等式，再审完整180/612表；T1初始12项+D2最终3项受影响验证，不是一次全套 |
| compact evidence/docs | response_v19、机器结果、三槽原件摘录、两阶完整CSV和逐项JSON、监督偏差与主控核算 | 研究证据可审，不等于merge approval；先核失败及超范围操作，再评价D2有限证据 |
| research-only | 新checker/小fixture/任务内launch、V19合同 | 不生成selector、DWR、transition10；未使用的通用resume路径仅fixture覆盖，不外推恢复资格 |
| do-not-merge | 大型NPZ/完整资源流、额外未监控数组操作的资格推断、未经批准整分支 | 原件ignored保留；不得把监督偏差隐去或以诊断完成提升科学/生产状态 |

D2固定运行源码`f066305d7e95b438a5ef8b223f2d5928bc6d79d9`，T1/D1为`8898f7e5fab82234786c51ffbd0cdeb167b379fe`。全域P8收益小、H8域外恶化占主导；所有旧精度失败保持。3次授权支持shell/105.266475099秒，另有两次未监控数组操作及一次shell127失败（NOT_MEASURED），正式新增0、账9/10末槽封存。不存在本轮合入顺序授权，只给审查依赖顺序。见[Response V19](../response_v19.md)、[机器结果](records/v19_saved_hp_response_results_v1.json)。

本轮收口另发现新合同残留D2未启用/无动态授权文案及一处旧launch hash；实际快照绑定一致，原合同字节保留，当前response明确订正。整体合同一致性与监督偏差仍待外审，不称工程全量验收通过。

## V18 历史状态：有限研究工程链完成，科学门未过，无合并批准

| 依赖组 | 变化与实证 | 合入顺序与边界 |
|---|---|---|
| production numerical/core | 未改共享数值核心、物理、容差、activation或ABI；新P8求解通过残差/A6 | 不据本次研究端点赋予production资格，本组无本轮变更 |
| reusable runner/watchdog | 通用watchdog默认不改；新增固定研究launch的分离会话与终态留证 | 只验证有限生命周期fixture及本次实跑；V17原信号来源仍UNKNOWN，不称修复了已知根因或通用资格 |
| checker/benchmark | 三个既有研究入口的恢复身份读取、唯一历史标签兼容、q8复用；定向fixture | T3 11项对应196571字节；C标签2项历史通过+最终3项实测。没有最终全仓/整套CI资格 |
| compact evidence/docs | response_v18、机器结果、轻量原文与主控独立复算、费用和失败索引 | 先审来源/失败与实际门值，再审代码；可审阅不等于允许合并 |
| research-only | round1_candidates、h100_anchor、compare_round1_candidate、v18_p8_stage_launch及fixture | 整轮绑定/恢复改动规模较大，维护复杂度须外审；保持opt-in，不提升默认，不建立自动后续运行权 |
| do-not-merge | ignored大数组/trace/resource原件、未经批准整分支及科学接受标志 | 保留原件和全部失败；不得生成transition10、更新accepted9或提升五项能力 |

实际P8 FE110722（+250）；q8/q10 J4.020864574738603>1，ΔJ.04419737048566574<εJ.12716416232413652。单位自由度收益区间跨零，p/h优劣未获资格。8次支持+1次正式恢复；formal9/10，旧末槽封存；没有merge approval。相关依赖必须绑定F源码196571、C源码75e1e05及各自实际测试，不把后续文档追认为运行字节。见[Response V18](../response_v18.md)、[机器结果](records/v18_r9_p8_scientific_results_v1.json)。

## V17 历史状态：F 未完成，无合并批准

| 依赖组 | V17 文件/证据与验证 | 建议顺序与边界 |
|---|---|---|
| production numerical/core | 本轮未改共享数值核心、方程、离散、约束、容差或默认行为；S只完成空间审计，F没有合格primary | 无fresh PDE数值端点资格；没有production merge项 |
| reusable runner/watchdog | 未修改原S/F/C launch或通用watchdog；F留下外层143/launcher文件0/watchdog终态缺失的矛盾 | 不据一次不完整链提升通用运行器资格；先查明外层信号/终态留证原因，再单独审查修复 |
| checker/benchmark | 未新增测试或通用checker；保留S joined、F失败摘录、资源与trace compact来源 | 空间审计仅支持本次P8空间计数；F没有可用于benchmark的official输出 |
| compact evidence/docs | `response_v17.md`、V17机器结果、来源索引及本manifest/summary/导航 | 供外审核查；无merge approval，不据此改accepted9/R9或五项能力 |
| research-only | 固定P8研究模式仍有真实空间实值，但求解端点未资格化 | 保持 opt-in/research-only，不提升生产默认；动态重试/恢复须另行授权。可继续静态定位；本轮没有确定性修复 |
| do-not-merge | ignored大型raw observation/resource streams、未资格化整分支以及不能证明的外层终止解释 | 保留失败与未知状态；不得将失败改写为通过或推断信号来源 |

V17 的 formal 8/9、P8/F槽1/1；S通过、F不完整、C未运行。见[Response V17](../response_v17.md)、[机器结果](records/v17_r9_p8_scientific_results_v1.json)和[轻量来源](records/v17_r9_p8_sources/README.md)。

## V16 历史补验：单节点通过，未新增正式计算

用户在原T两槽耗尽后授权一次单节点非PDE补验。末fixture已消除对前序测试创建phase的依赖，保留真实首次启动、ledger和同worker身份检查；生产门和数值源码未改。

| 项目 | 当前结果 |
|---|---|
| 补验 | 1 passed；运行HEAD `087ef600a4531c9e65643df787eb71e965f41b65`；其余17项只复用同字节历史证据 |
| 资源／费用 | whole12.767253825906664 s；树RSS采样峰256032768 B；CPU1、MPI1、六线程变量1、task swap0、退出0/0/0且清理完成 |
| 次数 | 原T2/2及两次失败不变；用户新增单节点1/1；三次whole94.8213470345363 s |
| 科学／资格 | S/F/C未运行；正式新增0、P8槽0/1、包络7/9、旧末槽封存；完整E CLI未资格化；无READY或合并许可 |

不是数值门失败，也不是新科学结果。17项历史复用＋1项本次实测不冒称一次最终18项批次；五项能力保持。依赖组仍为research-only与compact evidence/docs；不提升production默认。此次授权只补该节点，不据此启动正式求解。旧失败、合同和原结果v1保留；以下原交付段落中的“未补验”描述均属历史。

[单节点结果、字节身份与证据索引](records/v16_single_node_completion_v1.json)。

## V16 原交付历史：T 两槽用尽；没有科学或合并资格

| 依赖组 | 变化／验证 | 合入顺序与边界 |
|---|---|---|
| research-only | 三个既有研究入口的P8计划、primary/writer和旧三场复用比较；既有测试文件。T恢复17通过/1失败，末fixture静态修复未测 | 保持opt-in；真实S/F/C未运行，不提升生产默认；先审合同/绑定与失败，再审代码，不授权合并 |
| compact evidence/docs | response_v16、固定合同、机器结果、两次T终态/XML/日志、最终字节差异及当前导航 | 保存历史失败和NOT_RUN；可审文档不等于merge approval |
| production numerical/core | 无改动 | 无本轮fresh PDE资格 |
| reusable runner/watchdog | 仅新固定薄launch，通用watchdog/activation未改 | launch对应失败和未执行阶段分列，不称通用运行资格 |
| checker/benchmark | 有限研究模式与fixture；没有新通用算法 | 合成metric/owner测试不能替代真实P8结果 |
| do-not-merge | ignored大原件、未资格化研究路径和整分支 | 轻量失败证据可保留；不得重写原FAILED、accepted9或科学能力 |

S/F/C尚未进入；P8正式0/1、正式账7/9。T2/2耗尽不能借E补跑。末节点仅静态修正；E完整恢复链尚未实现或资格化。见[Response V16](../response_v16.md)及[结果](records/v16_r9_p8_results_v1.json)。

## V15 历史状态：P5诊断完成但不获接受，失败原件保留

| 依赖组 | V15 文件/证据与验证 | 建议合入顺序与边界 |
|---|---|---|
| research-only | benchmarks/task43_hp_adaptivity/round1_candidates.py、h100_anchor.py 与 compare_round1_candidate.py 的V15固定P2来源绑定、P4 ndarray summary reference writer、saved-primary P5 opt-in adapter；src/test/test_task43_v11_scientific_restart.py 现有入口fixture。P2空间/绑定已实际运行；A1和P4旧正式状态仍FAILED；P5为COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE，q8/q10均NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE | 不进入生产默认或通用数值核心。先按P5 root closeout独立审阅source/输入/q数值/资源；任何进一步使用都需单独授权 |
| compact evidence/docs | response_v15、机器结果JSON、P2 joined、A1 saved-primary joined gate、A1/P4失败closeout、测试XML/root closeout及summary/导航更新 | 先归档失败原件与root终态，再选择性合入必要文档；禁止把原FAILED端点覆盖成PASS |
| production numerical/core | V15无共享src数值内核、方程/离散/约束、容差或材料模型修改 | 无fresh numerical-core qualification，本组无V15合并项 |
| reusable runner/watchdog | 未改通用watchdog、资源采样、缓存或ABI策略 | V15执行证据不构成通用runner变更 |
| checker/benchmark | 未将V15恢复逻辑提升为通用checker；定向测试仅验证固定研究路径 | 不据saved-primary fixture授予benchmark资格 |
| do-not-merge | 所有 ignored 大原件及未资格化研究路径／整分支；禁止覆写或升级原 A1/H8 FAILED 端点 | 轻量失败 closeout 属于上列可保留证据，不能与大原件混列为禁止归档。P5 不改变 accepted9/R9 或 accuracy NOT_PASSED；V15 历史 formal7/8 保留，新 P8 专用槽仅由最新 review 前瞻授权，无 production/merge approval |

费用分账：本轮8次support whole累计2,240.4899401497096 s、formal whole 5,210.411748223938 s；V12/V14 recovery历史2,215.2188096446916 s、V11 support 853.8004706790671 s另列。P5比较/watchdog原件位于`benchmarks/artifacts/task43/v11_science/support/union_comparison_attempt1/`；root joined closeout位于`docs/task43_hp_adaptivity/outcomes/records/v15_bugfix_sources/P5/P5_joined_root_closeout.json`，SHA256为`5f2312d3bdf52a410a777e8e119ec8dbf6af992adb8bd575e12e0579e381165d`。后续动作及配额须由最新review明确；本manifest不授予新seed、计算、重试或合并。

详见[Response V15](../response_v15.md)与[V15机器结果](records/v15_bugfix_and_scientific_results_v1.json)。

## V14 历史状态：P2R一次已执行；实际FE取得，字段门失败

用户授权原P2R工作90分钟/含清理93分钟后，实际执行一次，whole **1596.6148925269954 s**；树RSS采样峰 **2210361344 B**、task swap0、CPU1/MPI1/单线程及清理符合记录。实际seed8及必要材料闭包得到194叶、**FE 116740，较R9增加6268**，满足110472与237600之间的数值区间；但研究入口误读periodic/floquet字段后抛错，worker/watchdog/launcher退出1/2/2，P2整体失败。已作键名和现有fixture的最小静态修复，AST通过、修复后pytest未运行。旧S1 12/12仅对应旧字节与覆盖范围。

旧A2保存数组raw/modal/q8/q10复算完整保存，q8/q10 G为6.043732933300416e-11 / 6.04373290835214e-11（限1e-5），无新A2求解。P3/P4/P5均未运行，h的J/G及输出收益未取得。P2R 1/1、recovery支持5/5用尽，支持whole累计2215.2188096446916 s；新正式0，正式5/8、历史封存槽及五项科学状态不变。无自动重试、READY或合并许可。

详见 [Response V14](../response_v14.md) 和 [V14机器记录](../outcomes/records/v14_p2r_budget_extension_results_v1.json)；原失败与旧字节保留，不把静态修正解释为P2成功。

| 依赖组 | 本轮变化与验证 | 合入边界 |
|---|---|---|
| research-only | round1键名/同文件fixture修复；AST通过，动态未验 | 不批准生产/default或合并 |
| compact evidence/docs | V14真实FE、失败、用户预算与终态证据 | 无fresh PDE，不授予merge approval |
| production core / reusable watchdog / checker | 未改数值核心、ABI、通用watchdog或通用checker | 历史资格缺口不变 |
| do-not-merge | 未资格化研究链及ignored原件、拒绝草稿 | 不合并整分支 |

## V13 历史状态：S1有限工程通过；D1受控停止；不授予合并许可

| 依赖组 | V13 文件与证据 | 合入边界 |
|---|---|---|
| research-only | `benchmarks/task43_hp_adaptivity/{h100_anchor.py,round1_candidates.py}`及`src/test/test_task43_v11_scientific_restart.py` | 修复 review §9.1–9.3 指定的 observer/raw checkpoint/真实读取测试问题；S1为12/12定向节点通过。D1在实际cell-map冷构造路径受控停止，未返回space authority或FE审计；这些代码仍是opt-in研究入口，不提升为默认/生产能力 |
| compact evidence/docs | `response_v13.md`、V13机器结果、S1/D1 closeout、P2R预算裁决和本轮summary/README/manifest/model registry/progress导航 | 保留S1有限通过、D1受控停止、旧数组诊断边界、未运行阶段、局部静态错误和费用。没有新正式PDE结果或merge approval |
| production numerical/core、reusable runner/watchdog、checker/benchmark | 无共享数值核心、默认行为、通用watchdog、profile/cache策略或通用checker改动；研究入口的raw reader修复归入上述research-only组 | S1 synthetic fixtures与D1支持剖析不构成科学、性能泛化或生产资格 |
| do-not-merge | 未资格化研究入口及整分支；ignored D1 raw run artifacts | recovery envelope累计4/5，P2R 0/1；D1已按540 s工作门受控停止，P2R所需1740 s工作界无法保守证明；P3/P4/P5未运行。旧正式额度5/6、末槽封存，扩展正式额度5/8，新formal 0；无READY、生产资格或merge approval |

下一步最小技术问题是给18个未完成冷degree keys及cell-map/audit尾段建立可审的费用界，或经另行审阅批准严格保持数学行为的窄成本修复。本manifest不授权进一步运行或合并。详见[Response V13](../response_v13.md)、[V13机器记录](records/v13_minimal_completion_and_scientific_results_v1.json)、[S1 closeout](records/v13_completion_sources/support/s1_completion_attempt1/root_closeout.json)、[D1 closeout](records/v13_completion_sources/support/authority_profile_attempt1/root_closeout.json)与[P2R预算裁决](records/v13_completion_sources/support/authority_profile_attempt1/p2r_budget_decision.json)。

## V12历史状态：两轮支持验证失败，最终两处断言当时未验证

| 依赖组 | V12 文件与证据 | 合入边界 |
|---|---|---|
| research-only | `benchmarks/task43_hp_adaptivity/{candidate_checkpoints.py,compare_round1_candidate.py,h100_anchor.py,round1_candidates.py}`及`src/test/test_task43_v11_scientific_restart.py` | V11 review §9 的研究入口修复；两轮支持运行分别10/24和12/14节点通过。最终两处断言只作静态修正、未运行；不得据此宣称回归通过或提升为默认/生产路径 |
| compact evidence/docs | `response_v12.md`、V12机器记录、两次root closeout、summary/README/本manifest/模型总账/开发进展导航 | 记录失败、局部准备错误、资源/trace和未运行边界；没有正式PDE证据或merge approval |
| production numerical/core、reusable runner/watchdog、checker/benchmark | 无共享数值核心、默认行为或通用watchdog改动 | V12支持执行不改变科学状态，不建立性能或数值资格 |
| do-not-merge | 未资格化研究入口及整分支 | S1主验证及局部恢复两槽已用；V12新支持总计2/4，D1/P2R各0/1但当前前门不合格；P3/P4/P5未运行；旧正式额度5/6、最后槽封存，V11两项新增正式槽均未消耗；无READY或生产资格 |

恢复测试最后有两个未通过节点，后续静态断言修正尚未运行。仅在新授权验证这两个selector后，才可考虑V11科学链；本manifest不构成重跑许可。详见[Response V12](../response_v12.md)、[V12机器记录](records/v12_recovery_and_scientific_results_v1.json)、[S1 root closeout](records/v12_recovery_sources/support/focused_attempt1/root_closeout.json)和[窄恢复 root closeout](records/v12_recovery_sources/support/focused_recovery1/root_closeout.json)。

## V11 历史状态：P2受控停止，不授予合并许可

| 依赖组 | V11文件与证据 | 合入边界 |
|---|---|---|
| research-only | `benchmarks/task43_hp_adaptivity/{candidate_checkpoints.py,compare_round1_candidate.py,h100_anchor.py,round1_candidates.py}`及`src/test/test_task43_v11_scientific_restart.py` | 仅V11 opt-in研究入口和定向测试；P1有限工程结果、P2受控停止；P2前门未完成，非生产资格 |
| compact evidence/docs | `response_v11.md`、`records/v11_scientific_results_v1.json`、P1/P2 closeout与sources archive及本轮导航/总账 | 记录真实终态、缺失科学字段、预算与实现/覆盖缺口；不把expected_forest作为FE/authority结果 |
| production numerical/core、reusable runner/watchdog | 无V11 `src/` 数值内核、共享watchdog或普通默认行为变更 | P2受控终止遵循现有watchdog；本轮没有数值或生产资格结论 |
| do-not-merge | P2 ignored运行原件、未资格化V11研究入口及整分支 | 正式旧额度5/6且末槽封存；V11新增正式槽0/2已用、P1支持2/2与P2支持1/1已用；无READY、生产资格或merge approval |

静态遗漏的必要闭包 gate 位于`round1_candidates.py:1688`，P2没有执行到该条件。P1还有一项fixture未覆盖真实非空闭包的缺口；两者均列为实现/审查问题，不是本次h科学失败。详细实际字段见[Response V11](../response_v11.md)、[机器结果记录](records/v11_scientific_results_v1.json)与[P2主控closeout](records/v11_p2_closeout.json)。

## V10 历史状态：静态证据更正，不授予合并许可

| 依赖组 | 本轮文件与依赖 | 核验与合入边界 |
|---|---|---|
| compact evidence/docs | `response_v10.md`、`records/v10_static_evidence_correction_v1.json`、`records/v10_static_evidence_sources/`及当前导航/总账 | 新纠正版必须连同原文行号、旧v1身份、逐字段diff、局部失败和UNKNOWN保留；静态核算61/18/48+13/24，fresh PDE为0；仍待正式审阅，未给docs merge approval |
| research-only | V10仅解析保存文本的stdlib脚本与历史采集脚本归档 | 仅供复核静态证据，不是controller、driver或生产入口；不执行归档采集脚本 |
| production numerical/core、reusable runner/watchdog、checker/benchmark | 无源码或数值行为变化 | 沿用既有依赖组限制；固定20项测试证据历史复用，不等于全仓或生产资格；没有新的建议合入顺序或许可 |
| do-not-merge | ignored原件、整分支、未资格化默认及所有锁定计算 | 正式5/6、A1 2/2、A2 3/3、最后槽封存；sanity1/1、D3 1/1不恢复；不合并 |

正式V9 review接受固定D3启动链及20项固定测试的有限工程证据，V10不否定也不扩大该结论。原782c57交付中三条派生错误由新文件纠正，原表不改。详见[Response V10](../response_v10.md)及[纠正记录](records/v10_static_evidence_correction_v1.json)。

## V9 历史交付：D3 有限工程复核完成；不改变生产合并资格

V8前瞻许可只恢复一次D3 support运行。Root对固定启动/import/ABI/affinity链与20个S2 fixture字节的审计为`PASS_LIMITED_ENGINEERING`，issues=[]；没有mesh、assembly、solver或PDE，也没有数值核心改动。watchdog whole wall `8.763570327777416 s`、进程树RSS采样峰`180887552 B`、task VmSwap峰0、global swap增量0/0页，后代清理完成。trace共1010行/44 getter，getter均为CPU `[1]`，0成功setter、0 signal；采样不等同连续观测，trace从taskset后开始。

| 合并组 | V9文件/作用 | 本轮证据 | 合并边界 |
|---|---|---|---|
| compact evidence/docs | `response_v9.md`、本manifest、Task43 README/summary、`docs/README.md`、模型总账、开发进展及`records/v9_d3_resume_closeout_v1.json` | D3原始阶段记录、19项synthetic sanity、20个target fixture、prelaunch/source hash和root终态审计副本归档在`records/v9_d3_sources/` | 仅支持固定启动链与fixture字节；不授予scientific/production/merge qualification |
| runner / numerical core / checker | 无V9源码、数值行为或测试源码改动 | 未构网格、装配、求解或运行PDE | 不新增合入文件或改变原建议 |
| research-only source/archive | `records/v9_d3_sources/{run_d3.sh,probe_import_affinity.py,sanity_once.py,root_terminal_audit.py}`与`preparation/`轻量原件 | driver和审计脚本按SHA逐字节绑定；preparation包含15 ELF/61 direct edges/3 bridge对象、prelaunch、sanity及root audit | 仅供审阅，不作为生产入口，不授权重跑或MPI扩展 |
| do-not-merge / locked work | 历史V8失败、V7 review、合同、PDE原件与资格锁 | 历史记录均保留；D3支持一次额度已消耗 | formal仍5/6、A1 2/2、A2 3/3、最后一槽封存；无READY、merge approval或下游解锁 |

## V8历史状态：D3准备门失败，停止且不合入

V7 review 的唯一D3支持许可要求先完成§9.2静态输入/ELF核查，再生成候选。候选过早生成，首次机械patch/copy失败；因此准备未通过，D3没有dispatch，候选仅是`/tmp/task43_v7_d3_proposal/`中的未资格化草稿。没有本轮源代码、测试、native导入或PDE改动；输入/ELF依赖闭包未完成。详见[Response V8](../response_v8.md)与[准备收口记录](records/v8_d3_preparation_closeout_v1.json)。

| 合并组 | V8文件/作用 | 本轮证据 | 合并边界 |
|---|---|---|---|
| compact evidence/docs | `response_v8.md`、本manifest、README、summary、`docs/README.md`、模型总账、开发进展及`records/v8_d3_preparation_closeout_v1.json` | 原命令、失败stdout/exit、部分activation/MCA与15个ELF静态原件；候选准确字节但准备顺序失败 | 仅保留受控停止和准备负结果；不是D3测试、ABI或运行资格 |
| research-only proposal | 唯一/tmp候选`run_d3.sh`及`probe_import_affinity.py` | 哈希与V7附录目标一致，但在§9.2步骤完成前生成；未运行sanity | 不纳入Git可执行入口，不授予支持、MPI、数值或生产资格 |
| production numerical/core、runner/watchdog、checker | 无V8源码或测试改动 | 无V8动态运行或fresh PDE | 不因V8新增任何合入文件或改变原建议 |
| do-not-merge / locked work | V7 review、V7 response、合同、READY与历史失败均保持不变 | 准备原件另记于V8 closeout；D3未启动 | formal预算仍5/6、A1 2/2、A2 3/3，最后1槽封存；无READY、merge approval或下游解锁 |

## V7 历史审阅快照：只读证据与未执行的worker假设

本轮新增仅为trace/ELF只读记录、历史启动器快照/diff及当前文档；没有源码行为改动、测试运行、driver、项目导入、PDE或READY。D1/D2停在首个显式`dolfinx`导入返回后的`native_import_complete`检查点；完整MPI/PETSc ABI为`NOT_REACHED`，S2的20个案例为`NOT_RUN`。12份完整raw trace留在ignored artifacts，Git仅保存204条事件表与代表栈摘录。完整入口见[Response V7](../response_v7.md)。

| 合并组 | V7文件/作用 | 本轮证据 | 合并边界 |
|---|---|---|---|
| compact evidence/docs | `records/v7_affinity_trace_event_inventory_v1.json`、`v7_affinity_source_loader_audit_v1.json`、4份保存shell/probe文本、2份diff及V7回应/状态文档 | 204条既有D1/D2成功setter、八个V5/V6 support根的文件映射、当前安装静态ELF身份和完整未执行D2→D3候选diff；12份完整raw trace仍在ignored artifacts | 只记历史支持负结果与静态假设；不改变历史记录、ABI、默认环境或数值结论 |
| research-only proposal (not code) | 候选在worker shell追加`OMPI_MCA_pml=ob1`，复用D2 probe并保留`HWLOC_COMPONENTS=-x86` | 仅有unified diff和当前调用栈上下文；候选目录未创建，运行、ABI预检与20个固定测试案例均未发生 | 不创建可执行runner，不授予新支持运行、MPI>1、数值或生产资格；须另有未来书面授权 |
| production numerical/core、runner/watchdog、checker | 无V7源码改动 | 无V7测试或fresh PDE evidence | 不因V7而新增合入文件或改变原有建议 |
| do-not-merge / locked work | 旧场、旧V6 trace/resources、合同、review与response历史文件 | 原件保持原路径/hash；V7只读索引不重写旧原件 | formal预算仍5/6，A1 2/2、A2 3/3，最后1槽封存；没有READY或production merge approval |

## V6历史支持结果：不授予新资格或合并批准

V6阶段按Review V5 §9仅新增一个test-only身份存在性修正与两次受限import/affinity诊断。没有数值源码、默认行为、旧合同或历史正式记录变化；新增正式PDE/dispatch/READY为0。S2的20个动态案例未运行。D1/D2在首个显式`dolfinx`导入返回后的`native_import_complete`检查点停止；完整MPI/PETSc ABI检查为`NOT_REACHED`，pytest、mesh、assembly和solver均未运行。

| V6依赖组 | 文件与作用 | 测试 / fresh PDE evidence | 合并建议 |
|---|---|---|---|
| test-only身份helper | `src/test/test_task43_v3_failure_safe_order.py`：测试中的联合读取约定要求source SHA为40位、contract/plan SHA各为64位且非空；新增共同缺字段反例 | 静态修改；20例`NOT_RUN`。D1/D2未进入pytest；无fresh PDE、无production consumer | 仅作为待动态验证的测试修正审阅，不把它描述为production数值改动 |
| V6 support evidence | `response_v6.md`、本页、summary/README/registry/progress、S1索引及[V6 affinity compact](records/v6_affinity_support_closeout_v1.json) | D1 200次、D2 4次成功affinity setter的有限trace；CPU1门`NOT_PASSED`，两次whole watchdog总计`20.736750496551394 s`；无模型计算 | 仅作为负向支持证据与状态说明，不授予任何求解/精度/生产资格 |
| do-not-merge资格边界 | 保持S2联合helper无自动消费者，未新增A2_R/controller或数值入口 | A1 2/2、A2 3/3、正式额度5/6，剩余1封存；V6不新增dispatch | 不得据此开启formal重试、其他下游工作或master合并；Task43仍未获production merge approval |

D2前的监督审查未分类D1当时已经存在的两类网络库setter（`libinfinipath`和`libpsm2`，合计4次）；D2仅屏蔽hwloc x86组件后仍观察到这两类调用。此审查遗漏已在response和compact中如实记录。V6因此没有证明strict CPU1导入链可用，也没有证实V5早期样本的历史根因。task VmSwap采样峰与global `pswpin/pswpout`页计数分开记录；未监控静态检查不并入watchdog费用。

## V5 历史整改范围：组件与文档证据，不授予合并资格

V5回应Review V4的F1–F4，只修改四个Python文件并更新收口文档/compact；无数值方程或默认native数值行为变化，无新正式dispatch/PDE。25项最小driver通过；31项focused首轮30 passed/1 failed，父子进程拓扑问题局部恢复后另两节点通过，未有单次31项全通过。六个受监控driver的strict CPU1全程门为`NOT_PASSED`，虽wall/RSS/swap/cleanup满足其支持限额；两次metadata检查未监控且失败。完整命令、source/test/driver hash、测试stdout、资源峰及静态检查结果见[V5 validation compact](records/v5_focused_validation_v1.json)及[独立资源复核](records/v5_root_resource_recheck.json)。

| V5依赖组 | 文件范围与作用 | 测试、fresh PDE evidence与资格 | 合并建议 |
|---|---|---|---|
| A1失败保护（research-only） | `benchmarks/task43_hp_adaptivity/h100_anchor.py`；`src/test/test_task43_v3_native_workflow_ledger.py`。只有本次成功建立空root后才允许failure wrapper写终态；已有非空root拒绝时保护所有旧文件 | 真实main边界/非空root/身份拒绝fixture；25项driver中相关节点通过；无网格、装配、求解或fresh PDE。A1_q2现场G2缺ledger的历史事实不变 | 只保留为research V3 opt-in；不提升为production default，不回填旧A1现场资格 |
| A2原件路径与联合故障读取（research/check fixture） | `benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py`；`src/test/test_task43_v3_failure_safe_order.py`；复用`candidate_checkpoints.py`原子writer | original path/hash字节绑定；合成完整文件控制与独立否决项；sidecar/comparison/summary写故障保留原异常和primary。联合约定只在测试中，无production消费者、无A2_R、无fresh PDE；fixture不授予科学资格 | 留在research-only；不增设consumer/controller，不用fixture代替端点验收 |
| V5 compact docs/evidence | `response_v5.md`、Task43 README/summary/manifest、`docs/development_model_registry.md`、`docs/development_progress.md`、validation compact及root resource recheck | 最小driver 25 passed；focused 30/1 failed；首次窄恢复在pytest前Ruff失败；第二窄恢复2 passed并完成四文件Ruff/compile/文档检查。CPU1全程门NOT_PASSED，metadata检查两次失败且not_measured | 作为有限审阅证据；不代表无条件F1–F4验收或merge approval |
| 禁止提升 | V3 observer、A2 adapter、测试内联合约定及V5 writer/failure path | 不提供production/default数值资格；formal quota remains 5/6，剩余1封存 | Do-not-merge为production；不得用旧READY、旧overlay或组件通过绕过剩余锁定 |

Q03旧Stage1 overlay只有59/66路径同字节、核心/共享路径23/27同字节；四个变化共享数值文件仍是`common_3d_case_flow.py`、`dtn_port_3d.py`、`hcurl_variable_p_reduction.py`、`solve_maxwell_3d_stage_4b_block_grating.py`。这份历史闭包没有资格化本轮四个修改Python字节，也不覆盖A1/A2最终共享依赖。V5没有重新宣称旧overlay或V1 PDE为新代码资格。正式预算仍为A1 2/2、A2 3/3、5/6；剩余槽封存，A1_R/A2_R/B/C与所有下游保持关闭。

## V4历史范围：整改代码仍为 research-only

V4按Review V3 §9仅做N1–N6整改，正式PDE/dispatch新增0、READY新增0。N1–N4涉及 `benchmarks/task43_hp_adaptivity/h100_anchor.py`、`a2_native_p6_diagnostic.py`、`candidate_checkpoints.py`、`src/runners/p6_condensed_direct.py`、`benchmarks/subreaper_watchdog.py`及相应failure-safe、native ledger和watchdog tests；改动为V3显式diagnostic路径的ledger/原子留证/失败权限/extra原向量时序，以及watchdog对停止原因的分类。默认 native runner数值路径不作为本次数值资格对象；新测试只覆盖隔离的CLI入口 sentinel、小数组和子进程。V4运行命令、日志、source/test hash与具体raw断言见[validation compact](records/v4_focused_validation_v1.json)。

| 新增依赖组 | 路径及作用 | 测试/新PDE证据 | 合并建议 |
|---|---|---|---|
| V4 A1 observer/ledger（research-only） | `benchmarks/task43_hp_adaptivity/h100_anchor.py`；复用现有 `WorkflowLedger`，仅在V3 opt-in的真实入口维护phase/stage并写失败终态 | mesh-boundary实际main sentinel；无装配/求解；缺phase和错误父身份构网前拒绝。此前A1_q2漏接账本仍是历史G2失败，主控放行责任已在response说明 | 不升为production default；不得把新fixture倒推为旧A1现场G2通过 |
| V4 A2 failure-safe 与 extra packet（research-only） | `a2_native_p6_diagnostic.py`、`candidate_checkpoints.py`、`src/runners/p6_condensed_direct.py`；原子summary/comparison降权、原比较副本/hash保留、extra原向量在后续物理输出/采样前落盘 | comparison异常、summary截断异常、extra恢复/transport/q10失败测试；从NPZ内嵌`__task43_record_json__`重算凝聚/A6/full-active并保留严格下降失败。没有新PDE；A2_q3旧primary/extra记录未被改写 | 不升为production default，不据组件fixture授予q/R或精度资格 |
| V4 watchdog分类 | `benchmarks/subreaper_watchdog.py`及`src/test/test_354_subreaper_watchdog.py` | 有残留后代和无后代cache等待两分支；历史A2 root affinity/lifecycle审计见[v4_root_audit](records/v4_root_audit/index.json) | 保留原有限清理标签；不改写旧A2 LIMITED |
| V4 compact docs/evidence | `response_v4.md`、summary、README、manifest、模型总账、progress与`v4_focused_validation_v1.json` | local focused/static/doc contracts按compact列出；无full suite、无新formal PDE | 只作审阅证据；仍未获merge approval |

仍为5/6 formal dispatch：A1 2/2、A2 3/3、剩余1封存；A1_R/A2_R/B/C、迭代、成本campaign和0.7nm均锁定。本轮组件整改不改变五项能力或V1 accepted9/R9状态。下方V1/V2/V3依赖清单及其历史测试范围继续有效，但不得被用于宣称V4新增native/observer路径获得production qualification。

V3-03生产合并门仍未关闭：旧Stage1 66路径依赖overlay复核为59/66同字节，27个核心/共享路径中23/27同字节。四个发生变化的共享数值文件是`src/solvers/common_3d_case_flow.py`、`src/solvers/dtn_port_3d.py`、`src/solvers/hcurl_variable_p_reduction.py`、`src/solvers/solve_maxwell_3d_stage_4b_block_grating.py`；旧overlay并未对这四个最终共享文件整体提供生产资格。本轮N1–N4局部focused不代替拟合入文件和共享依赖的干净production/full-suite qualification。

本清单描述依赖组和送审范围，不是 merge approval。基线为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`。V1数值/比较实现及正式模型测试以 `3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0` 为主要source HEAD；各历史PDE仍按其run内source snapshot解释。Stage1证据快照HEAD为`fad2df0fb5c15ab1e14fabddf262a772c126cda5`；V2诊断入口source snapshot为`a879554d7149bef1187b31bd731b09629f33fef3`；V3冻结组件/计划及A1/A2 dispatch source均以本页新增V3记录分别绑定。V2三次formal dispatch在完整资格前遇到工程/输入绑定失败；V3两次dispatch中A1_q2实际入口漏接WorkflowLedger、A2_q3则到达求解并在7200秒门后不完整停止，均无完整q/R端点结论。新增native A2 adapter、observer及V3留证接线为research-only，不因Stage1闭包、组件测试或V1 PDE取得production资格。R10拒绝与V1选择停止记录保持不变：accepted9最后状态R9（110,472独立FE，η_G=3.995683423e−5、J∞=4.065061945），最终精度未过；R10自然到180格全p6、118,800FE，G改善8.4129e−6未超过冻结噪声9.08816e−6，故拒绝且无transition10。以Y6_1为reference，R9的top/bottom `(0,0,s)`功率绝对差为4.065061945e−6与2.148245071e−6；R10对应top通道差2.837172688e−6，均超1e−6。h10独立内部DoF292,260超过控制FE237,600的目标，不是score剪枝。后验不反馈选择。

真实600叶局部h1已完成完整散射解、A6和公共全场比较，空间误差仍不达最终要求；不回写历史选择。R8原PDE supervisor终态缺失、outer143/sender未知，仅有采样窗资源；R9/R10完整资源通过不会修复它。完整六文件G3求解草稿仍/tmp且不应用。已实现最小三文件后验原场恢复/比较方案。Y5_1和两份6×10×6 p6控制已从冻结原场恢复，实际独立FE分别332640/237600/237600并由Floquet约束及周期实体公式复核；联合六场q8/q10九对比较已完成且由root从原数组、6mesh union、Gauss积分、R/T与612通道Poynting、原有A_volume记录差、E/H/G和四组幅值独立重算通过；本次未重新体积分A_volume；对Y5_1的R9/R10仍有2/1个零级s功率通道失败，对Y3只有R10单对通过，对Y3_2两者多项失败。Y6_1→Y5_1通过，Y6_1→Y3/Y3_2失败；全部结果及root raw/resource audit hash见[post-selection compact](records/post_selection_existing_fields_validation_v1.json)。后验角色不能进入accepted reader，无新PDE或选择反馈。

数值核心决定场如何表示、方程如何构造和解如何恢复；运行工具负责配置和记录，检查工具从保存的原始数据重算结论。拟选实现闭包的27个路径逐文件列在[机器依赖清单](records/selective_merge_dependency_closure_v2.json)中，按 `production_core_or_shared_runner_dependency` 角色筛选即可得到完整路径及SHA。它们包含A–D核心、A依赖的公共配置，以及mesh builder、Task43 axis plan和native capacity IO这些共同前置，组成第一原子组；表中A–D和共同前置只是审阅主题，不能按行独立合入。表外25个显式测试依赖、9个Task43研究runner/checker依赖、4个compact报告工具和独立watchdog也都在同一机器清单内。独立watchdog和忽略规则属于后续可单独纳入的工具组；Task43 profile/几何/IO文件不能放到后续顺序，因为第一原子组依赖它们。

| 依赖组／顺序 | 文件范围与作用 | 数值影响与依赖 | 对应测试、fresh PDE evidence与限制 | 建议 |
|---|---|---|---|---|
| production numerical/core · 第一原子组共同前置 | `src/geometry/mesh_builder_3d.py`、`src/geometry/task43_hp_adaptivity_axis_plan.py`、`src/io/native_capacity_profile.py` | Task43网格构造需要axis plan；求解和runner通过native capacity接口读取资源能力。这三项是A–D及Task43 runner的共享前置，不是runner/watchdog第二顺序。 | mesh/axis/resource-profile组件测试；overlay的66文件hash与25文件收集由Q03记录，新增正式模型PDE为0。 | 与A–D同批纳入第一原子组。 |
| production numerical/core · A子组（与B–D原子合入） | `src/adaptivity/exact_sequence_variable_p.py`、`hcurl_broken_cell_trace.py`、`hcurl_broken_trace_graph.py`、`hcurl_hanging_trace.py`、`hcurl_trace_constraint_graph.py`、`stage4_local_h.py`、`variable_p_degree_plan.py`、`variable_p_entity_map.py` | 扩展p3表示、实体共享阶次、真实局部h及周期/悬挂约束；p3秩判断用SVD，改变空间资格判定。参考空间缓存最终128只保留更多相同映射，不改变公式。 | test183/188/197/203、p-up closure、mixed hp9↔12；p3/4、p4/5已知场；36单元同阶MPI1/2；current与Round1–10 mixed-p真实PDE；600叶h1新几何真实PDE。旧p4 golden hash负项及未用level2缺口保留。cache128另有4项既有转移测试。 | 按实际已验路径送审，不将未验多层/悬挂组合升为默认。 |
| production numerical/core · B子组（同一原子组） | `src/common/config_3d.py`、`modes_3d.py`；`src/solvers/common_3d_forms.py`、`dtn_port_3d.py`、`hcurl_variable_p_assembly.py`、`hcurl_variable_p_reduction.py`、`independent_active_action.py`、`common_3d_case_flow.py`；`src/runners/run_3d_cases.py`、`src/postprocessing/rta_3d.py` | 显式q15/q28、相对cutoff与端口幅值尺度、BlockedGram接线、独立完整原方程A6、体吸收。依赖A和既有DtN模式/张量模块，保留普通默认。 | mode/test178/185/189、independent action、blocked Gram等价、真实36单元A6；current/Round1–10均保存完整612通道及A6。未缩放溢出负项保留。旧h1停在完整Task43A6之前并保留；h1重试已得到A6=8.7454e−10、condensed=3.8615e−13与完整612通道，不能以其空间误差未达标否定该数值资格。 | 与空间/后处理依赖一并审，不能用condensed残差代替A6。 |
| production numerical/core · C子组（同一原子组） | `src/solvers/petsc_residual_correction.py`、`solve_maxwell_3d_stage_4b_block_grating.py`及B中的接线；`src/adaptivity/variable_p_transfer.py`及A中的primal extractor | 同一LU因子额外回代仅在显式残差有限且严格下降时更新解，默认关闭/MPI1 preonly LU。同网格p转移核恢复与约束，不是直接解使用的初值。完整p6对偶载荷中仅严格全零单元跳过乘法，非零及1e−100保留原路径。依赖A/B。 | residual correction单元与27单元真实fixture、正式current求解扰动、Round2–10及h1重试同LU；test186串行/MPI2、primal测试、R2/R6父场转移；精确零跳过后36单元A6=8.7763e−13且模态/体吸收记录与旧anchor字节一致。 | 保持显式受限范围；跨网格h转移未资格化，不称warm start或可扩展迭代。 |
| production numerical/core · D子组（同一原子组） | `src/postprocessing/physical_field_sampling.py`、`physical_field_comparison.py`、`src/adaptivity/physical_g_error.py` | 在共同物理积分点比较E/curl/H并按实际单元积分G²作标记。固定入射尺度处理近零分母，G不是连续真误差界。依赖A恢复和固定几何/材料。 | comparison/sampling/physical G tests，MPI2集体采样修复及原失败保留；q8/q10初始校准，Round1–10及h1重试完整原数组独立复算。后验采用六场全部断点共同积分、每场每级q只采样一次、九对reference方向各自归一，q8/q10差仅是更严后处理积分观察，不替代PDE积分资格。当前精确双侧界面trace仍未实现，不从体采样推断侧壁通过。 | 可复用后处理送审，参考和最终空间精度另验。 |
| reusable runner/watchdog／第二组 | `benchmarks/subreaper_watchdog.py`、`.gitignore` | 通用进程树监管、资源采样与artifact忽略规则，无数值方程行为；作为独立工具组可在第一原子核心组之后纳入。 | subreaper/watchdog与资源合同测试及既有受监管运行；不新增PDE。Task43资源profile、mesh builder、axis plan和native capacity IO是第一原子组共同前置，已按27路径机器清单归入核心组，不列为第二组。 | 可独立于数值核心审阅；Task43 runner使用时依赖第一原子组的profile接口。 |
| checker/benchmark／第三组 | `benchmarks/task43_hp_adaptivity/{reference_restore,compare_initial_to_references,compare_round1_candidate,candidate_records,candidate_checkpoints}.py` | hash绑定保存场恢复、共同积分、原字段门槛重算、已接受父状态及pre-validation checkpoint。依赖A–D，不重新实现求解器。 | records/checkpoints tests、accepted-parent实际loader、参考恢复、q8/q10及逐轮612通道/全场审计。后验接线仅改reference_restore、compare_initial_to_references、compare_round1_candidate及已有test_task43_candidate_records；默认选择阶段仍拒绝holdout/control。12项保存真实场/角色/方向/弱量floor/全612物理重算/篡改拒绝fixture通过，无新PDE。旧initial缺新duplicate字段仅在明确初始父角色、精确schema/case及实际8640+6480/A6 rows匹配时兼容，现代candidate保持严格；h1首比较失败保留、局部修复后第二次比较通过。Root审核有完整J的field上界论证，不声称另算每个scattered精确范数。 | 保留为研究checker；冻结参考、尺度和阈值，不授予checkpoint official身份。 |
| compact evidence/docs／第四组 | `docs/task43_hp_adaptivity/`任务材料、outcomes/records、最终response和manifest；`docs/README.md`、模型总账、进展；报告工具`benchmarks/task43_hp_adaptivity/reporting/{build_cycle_index.py,build_unified_model_attempt_inventory.py,build_final_review_figures.py,watchdog_scope.py}` | 文档与轻量hash证据；四个报告/归属辅助工具只汇总原记录、绘制SVG或判定watchdog身份，不改变数值方程或默认行为。依赖各记录、已核原数组与run source/ABI身份；`watchdog_scope.py`是V2 inventory生成器的明确依赖。 | V2在当前代码身份下实际运行：保存场focused 40 passed/3 skipped（3项MPI2采样fixture另以MPI2两rank实测通过）；mixed p3/p4 exact-sequence、装配/内场恢复和独立action 3 passed；same-LU显式27-cell组件fixture 1 passed，watchdog156.695846s/树RSS峰1,054,969,856B/task swap0/后代清理。另有相同实现/测试hash的4项PETSc residual-correction单元旧记录可复用。上述都是组件/保存场检查，不是新正式候选。原全仓pytest在collection中1 skip、8 errors、test bodies 0执行，pytest报告91.42s；watchdog104.270419s/树RSS406,917,120B/swap0/exit2清理。错误细分为1个忽略Task43同名artifact module mismatch、1个test179 SLEPc key1211220 registration conflict、6个旧忽略tmp/task42extra缺模块。registry Markdown合同的两次原结果均保留，最新为5 passed/0.11s。Q03从干净的base405隔离worktree叠加66个hash-listed源码、runner及测试依赖，4个代表入口import通过，25个明确测试路径collect-only收集157项、0错误、0 skip且0测试体执行；这只证明依赖可导入/可收集，不是数值回归。报告生成器Ruff format/check与compileall、文档合同的最终日志和文件hash见[送审包验证compact](records/final_review_package_validation_v1.json)；这些局部检查不声称CI或全仓通过。h1辅助ABI原字节缺失保留，不能回填。各watchdog分账不等于全campaign。 | 不删负结果，历史source缺列及真实运行中补充保持原时间分类；reporting tools属compact/research reporting，不进入production default。 |
| research-only／第五组 | `benchmarks/task43_hp_adaptivity/{profile,h100_anchor,round1_candidates}.py`；三份reporting generator按compact-doc group提供输出，可仅作为研究工具保留 | 本次物理/资源/候选编排，依赖A–D与watchdog/checkers。固定MUMPS为显式参数，默认不变；skip-parent-transfer只省掉直接解未使用的资格转移，hash/actual authority/FE仍核对，默认保留旧转移；报告工具无数值行为变化。 | 36格mixed-p4/5/full612两后端相同CSR/RHS及完整场比较；原末尾JSON失败保留、仅bool包装修复后从原数组复核44门，不重跑PDE。skip真实36格空间+sentinel/默认/badhash/h未验状态测试，serial guard另提交；Round6–8 MUMPS实际A6（R8完整资源资格另缺）。最终reporting scripts各自Ruff/check/compile通过，inventory与SVG provenance绑定输入/生成器hash。 | 不根据不同p-map耗时或顺序JIT生命周期宣称后端加速，不将research runner或report generator升为production默认。 |
| research-only／V2 native diagnostic | `benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py`；`benchmarks/task43_hp_adaptivity/h100_anchor.py`中的V2 opt-in/observer transport接线；**`src/runners/p6_condensed_direct.py`的V2显式opt-in分支**；`src/test/test_task43_v2_native_p6_diagnostic_helpers.py`、`src/test/test_task40para_direct_residual_and_supervisor.py`、`src/test/test_task39extra_v7_p6_direct_pipeline.py` | A2 adapter读取冻结Y6_1并调用既有native runner。显式V2分支将q19 volume metadata同时送入native physical action与实际volume forms、将q32端口积分用于rhs；记录完整active-space残差，并为额外同因子回代保留factor直到before/after全输出。V1默认q、资源门、常规校正与原release-before-output生命周期保持不变。Y6 profile兼容仅在hash绑定的内存副本补唯一缺失display label后调用未改变的原生validator。 | V2两次A2_q均在构网前退出，V1和V2不授予该新native opt-in资格。之后V3 A2_q3到达576-cell网格、装配及extra校正，primary residual与q8/q10样本已保存；因7200秒门到期缺native summary/完整端点比较，且extra full-active explicit residual未严格下降。V3 A1 observer/WorkflowLedger实入口遗漏已作为独立工程负项记录。V3 regression与两次V3 formal终态、连同此前三次V2终态见V3 closeout compact；Q03旧66文件overlay闭包不覆盖新增native分支。 | 仅作为研究诊断入口保留；不升为production default，不据此宣称native P6与variable-p核心等价、q/R完整通过或空间精度通过。 |
| checker/benchmark · V2 endpoint comparison（research-only） | `benchmarks/task43_hp_adaptivity/compare_v2_endpoints.py`、`sample_v2_legacy_r10_fields.py`；`src/test/test_task43_v2_comparison.py`与上述native helper tests | 比较器从同一物理采样点的R13共同612与R14扩展tail通道重算幅值/功率差及联合门；legacy sampler从真实已存R10系数恢复旧端点的q8/q10字段。比较器不解方程，sampler不改解或补造R13缺失的tail系数。 | 12个比较器fixture通过，三次旧场后处理尝试费用及原件SHA见legacy resampling账；V2三次formal dispatch都没有得到完整可比端点，因此没有通过完整端点验收的fresh PDE evidence，也没有q/R结论。具体输入、测试命令与日志hash见V2 comparator validation及formal compact；不属于Q03的66文件overlay证明。 | 仅作研究对照和hash-bound checker/sampling工具；不能把旧场恢复或部分模态差提升为端点通过。 |
| do-not-merge／不合入 | ignored的场/网格/矩阵/因子/完整timeline日志，临时/tmp审计与草稿，旧NN/FTT输出，未验路线的默认开关 | 大数据以轻量hash入口保留，旧分支不整体merge/cherry-pick。未验level2/迭代不能冒充生产能力。 | 保留研究负结果、受控停止及已授权旧artifact清理provenance；无需把大型数据提交Git。 | 不纳入源码合并；相关轻量负证据归docs组。 |

## V3历史终态与新增依赖组（非合并批准）

V3总计两次正式dispatch，细节见[formal closeout compact](records/v3_formal_diagnostic_closeout_v1.json)。A1_q2实际构网并进入装配，随后因真实入口未接`WorkflowLedger`由主控停止；先前A1 READY保留作历史，不能视为本轮入口通过。A2_q3真实建立WorkflowLedger并运行到额外同因子校正，primary before-extra和q8/q10样本留存；7200秒门触发后任务不完整，且extra full-active explicit residual没有严格下降。A2 native summary/完整比较缺失。V2三次formal wall小计`4915.1723896381445 s`，V3两次小计`7372.49412643211 s`，五次总计`12287.666516070254 s`；此处只加whole-watchdog wall，RSS峰不相加，支持性检查另列于V3 pre-PDE index与closeout compact。

| 新增依赖组 | 实际变更文件与作用 | 测试/证据 | 合并边界 |
|---|---|---|---|
| V3 failure-safe/observer研究接线 | `benchmarks/task43_hp_adaptivity/h100_anchor.py`、`candidate_checkpoints.py`；`src/solvers/common_3d_case_flow.py`、`dtn_port_3d.py`、`hcurl_variable_p_reduction.py`、`solve_maxwell_3d_stage_4b_block_grating.py`；对应V3 failure-safe、residual、workflow-ledger测试 | V3组件冻结历史：HEAD `81c97e7c3357bbed1b29cab4ff40f2997e8bafdc` 上57 passed/1 skipped，唯一skip为明确opt-in的完整p6 FFCx矩阵见证；HEAD `fc260b1e204b8f8f3aeebf136e57de2165b4920b` 上另重跑最后改变的生命周期节点1 passed。历史Ruff为77项既有诊断，与`fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12`基线相同、无新增；均非V4最终字节检查。G1源码/组件审核见[`v3_root_final_source_review.json`](records/v3_root_final_source_review.json)。A1现场仍因真实入口缺ledger而停止，因此fixture/source审核没有证明该端点取得官方资格 | 诊断留证研究分支；不得通过V1历史PDE或组件测试推断新A1端点通过。ordinary/default行为受有限回归，但仍不进入production default |
| V3 native A2 research-only | `benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py`；`src/runners/p6_condensed_direct.py`及以上共同求解/observer接线；`src/test/test_task43_v3_native_workflow_ledger.py`与V3/V2 native helper节点 | A2_q3 实际建立native ledger、构造576格Y6_1网格、完成装配/求解及一次extra；保存的primary指标经root按raw vectors重算，审计在[post-PDE raw audit](records/v3_root_post_pde_audit/A2_q3_primary_raw_audit.json)。whole watchdog至性能门后`INCOMPLETE_NOT_OFFICIAL`；extra全显式残差未严格下降。计划/contract中q/R硬门没有被完整端点比较验证 | **Research-only，NOT QUALIFIED。** 新native opt-in不属于Q03旧66-file overlay闭包；不据此声称与variable-p核心等价、全端点q/R通过或精度通过 |
| V3 comparison/证据文档 | `docs/task43_hp_adaptivity/response_v3.md`、summary/README/registry/progress/本manifest及closeout compact；复用现有`compare_v2_endpoints.py` | 固定原件hash、V2/V3 five-dispatch表和实际缺项列于compact；A2完整`comparison_record.json`未生成 | 属compact docs/checker支持材料；当前变更集不授权生产合并 |

V1冻结inventory中的16次完整模型尝试是该V1表自身范围，不是V2/V3后全任务累计。五项能力保持：空间/选择`PARTIAL`，精度`NOT_PASSED`，同精度全过程成本`NOT_ESTABLISHED`，迭代`NOT_RUN/NOT_QUALIFIED`；0.7 nm未运行。正式预算5/6已耗用，A1=2/2、A2=3/3，剩余1个槽封存；A1_R、A2_R、B、C不运行，不跨组重分配。V1 immutable记录与历史负项保持；本manifest仍不是merge approval。

审阅重点：区分中间更新、离散求解资格与最终空间精度。R10的G噪声门失败不意味着PDE数值失败；它的完整原方程残差8.16407e−9、凝聚残差5.31294e−13、能量闭合差1.87028e−12均过门。不能因为它的118,800FE恰为对照预测的一半就授予同精度或成本优势，也不能把R9的九次中间接受视为独立参考验收。两种相同网格计数但不同轴分布的control已并列比较，未择有利分布；缺失自身q/R资格的历史参考仍只作有限离散诊断。

V1审计的56份终态workflow summary逐个保留原路径、SHA、分类和summary自带whole-watchdog elapsed；去重后合计63,340.73598930752s。`post_selection_restore_attempt1` 是包含Y5_1、Y3、Y3_2的完整恢复workflow，其实际summary记录166.96172243729234s（COMPLETED/exit0/后代清理），取实测原值，不从总数倒算；root独立核验56条、58个原件hash、原R3冻结18行和64份V1不可变文件通过，见 `benchmarks/artifacts/task43/v2_root_audit/cost_ledger_audit.json`（SHA `18cf21ea4da9ee6e173a6b4a12f24a01ef8cb0fd1d9d69cbe31fc57ab44f00d4`）。R8 PDE缺summary，另有3,109.3891972089186s采样窗下界，不能并入“完整wall”；完整R8终态、sender和全生命周期资源仍未知。两次最终测试watchdog wall共135.193513449747s另列。V2 root stored-field replay额外watchdog wall为46.21374210854992s（raw-array复核、非新PDE）；同一审计中的0.143265s轻量残差算术不属watchdog wall。各项合并只是已观测时长下界，不覆盖未监控工作/测试与导入参考生成，也不是全campaign成本。V1实际运行16次完整模型求解（12条lineage），accepted9；Q02–Q08仅组件/证据整理，没有新增正式模型PDE。候选和controls未经相同精度完整资格时，只列不同源码/缓存/生命周期下的实际数据，不能得出同精度加速或冷启动成本优势。

本清单覆盖R10拒绝、三文件后验接线、三份原场恢复、已完成的六场联合比较和最终两次测试。新增reporting脚本、模型表、cycle index、图与compact evidence属于review docs/reporting组；它们以脚本和输入hash绑定，不建立数值算法。历史PDE按各自run source snapshot/ABI/input manifest解释；HEAD `3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0`只标识本轮数值/比较代码及pytest，不追溯为所有历史解的源码。原/tmp六文件G3求解草稿不在送审diff。全仓pytest已真实尝试并在collection中止，按1+1+6错误分类保留，不假称测试体执行、CI通过或全仓通过；report生成器Ruff/format/compile与文档契约检查由compact绑定实际日志单独报告。


## V2阶段一门与附加原场复核（Stage2启动前的历史快照）

Q02–Q08的逐项身份、原始输出和sha256索引见[stage1 gate记录](records/stage1_gate_v2.json)及对应Q记录。主控已将Stage1直接诊断门判为PASS_WITH_LIMITATIONS：Q03的66文件闭包/hash、干净base405及实际overlay import/157项collection均独立核验；Q04的56份summary账只代表有summary的workflow记录，既含失败/停止/preview也含真实恢复时长，不代表56个数值成功，root逐行成本账核验已通过。生产与全仓门仍受real-SLEPc/complex PETSc ABI冲突及完整tracked collection错误阻塞。Q05只支持冻结contract hash出现在pre-run snapshot，不单独证明其严格早于首个candidate。Q06仅把p3纳入既有D4八变换及256个oriented-child组合测试；Q07只允许精确R8路径读取partial资源exception，V1 inventory不变；Q08两次registry markdown测试均通过，最新5 passed/0.11s。这个Stage1快照形成时尚无Stage2正式模型PDE；随后按已提交/审阅的有限计划启动三次诊断，实际终态见下节，不回写本段原时序记录。

新root replay与旧V1 raw audit、14项输入hash相符：复算的是原存储场样本数组的612通道Poynting和E/H/G，不从solution coefficients重新采样；R/T/A_volume使用已有记录，其中A_volume没有新体积分。残差复核是已有trace/interior/modal norm的算术重组和保存moments检查，没有新施加完整算子，因此不构成新的A6 qualification。对照/root审计索引见[post-selection replay V2记录](records/post_selection_old_field_replay_v2.json)。

## V2正式诊断终态与合入建议

本轮三个formal dispatch为A1_q attempt1、A2_q attempt1和A2_q attempt2，总whole-watchdog wall为4,915.1723896381445s；逐次worker/launcher退出码、resource samples、source/input前后hash、artifact SHA及root independent terminal audits见[formal attempts compact](records/v2_formal_attempts_and_profile_fix_v1.json)。A1在observer `MappingProxyType` broadcast序列化失败；A2第一次缺watchdog phase-path；A2第二次Y6_1旧profile缺一个display label并在网格前被原生validator拒绝。都不能解读为Maxwell解的物理/数值失败，也没有完整q/R端点结论。

A2后续profile修复仅对hash绑定Y6_1 resolved config作内存归一，随后以原生 `_validate_resolved_profile` 校验；真实只读helper/preflight和26个pure helper fixtures通过。profile兼容补丁后未再启动fresh PDE。A2额度2/2已耗尽，A1因缺完整A1_q endpoint/A6而关闭，A1_R前置不满足；一份A2_R额度在已审的retry冻结记录下仅重配给A2_q attempt2，之后没有跨组或额外重配。A2_R未运行；B和C被资格门锁定，未作独立求解。

V2 native-P6 A2入口、A1 observer transport分支与profile补丁均应列作research-only。新入口引用native Task40 runner与Task43核心，依赖范围和组件验证不属于Q03 66路径overlay闭包，不得作为production numerical/core资格。保留所有三次失败及原V1的64项immutable inventory。最终结论仍是V1 accepted9/R9、最终空间精度未达，V2因实现/接口问题没有得到q/R扰动结果；详见[response V2](../response_v2.md)。
