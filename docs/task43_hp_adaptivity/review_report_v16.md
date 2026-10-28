# Task43 正式审阅 V16：关闭正常路径的 T 前门，继续固定 P8 科学实验

## 1. 固定身份与裁决

审阅日期：2026-10-28（Asia/Singapore）。唯一执行分支为 `task43_hp_adaptivity`。

| 身份 | 完整值 |
|---|---|
| 仓库 | `Rookie1234567/MyFEniCS` |
| 固定被审交付 | `1294527a0ccb6ab6e52c5e3aded2551567fb9256` |
| 执行依据／本轮差异基点 | V15 review `f72e1c8d031de7acc374f0806ddac06099c461c4` |
| 首次 T 实际 HEAD | `c620c96ef98adac4e1caf05e28dae7744e73a328` |
| T 恢复实际 HEAD | `3b9d5e0adb43f69a1fdf339691b26d7eec506686` |
| 用户单节点补验实际 HEAD | `087ef600a4531c9e65643df787eb71e965f41b65` |
| 任务数值基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |

审阅开始时远端正好位于固定被审提交，无后续提交。V15 review→交付为5个线性提交、61个变更文件；补验运行HEAD→交付仅一个提交，修改文档／证据，未改研究源码或测试。不能将交付HEAD追认为运行HEAD。本审阅未访问工作站canonical worktree，远端身份核对不等于独立证明其本地clean/upstream状态。

**总裁决：接受本轮正常 P8 路径的有限工程实现、两次失败的诚实归档和用户授权单节点补验。17项同字节历史通过＋1项新实测，足以关闭正常 S_MAIN→F→C 所需的 T 前门。完整 E 恢复链仍未实现／未资格化，本次明确禁止使用；不要求为了一个尚未发生的恢复场景先建设完整 E。**

**下一动作已经明确授权：主控只读核对并生成第9.2节的新 T 资格记录，随后直接执行原未消耗的 S；S 合格后直接执行唯一正式 P8 求解 F；F 合格后直接执行四场比较 C。无需逐阶段等待新 review，不重跑18项，不新增正式槽或支持槽。**

| 维度 | 本次裁决 |
|---|---|
| 工程验收 | `PASS_WITH_QUALIFICATIONS_NORMAL_PATH`；正常路径有限接受，E未交付部分不接受为可用功能 |
| T资格 | `T_NORMAL_CLOSED`；原两次失败不改，补验不冒充一次最终18项批次 |
| 资源资格 | Git可见实值范围内接受三次支持终态；真实S/F/C环境与资源仍须逐次现场核 |
| 科学资格 | 没有P8实际FE、primary或J/G结果；五项能力均不升级 |
| 下一步运行 | 原S1次、F1次、C1次继续有效；新剩余正常链whole上限10800秒 |
| 合并资格 | 无merge approval；不合并master，不整体合并研究分支 |

本报告第9节是下一轮唯一执行授权。它前瞻收窄V15中尚未实施的E许可，不追认原V15完整E要求已满足；其他冻结数值规则保持。

## 2. 实际审阅范围与证据边界

已阅读三层AGENTS、仓库工作原则、任务书、V11科学补充任务书、V15 review第9节及相关结论、V16回应／合同／两份结果记录、全部本轮差异、sources目录和当前summary／manifest／模型总账／开发进展中的相关内容。三个独立子审阅分别检查工程覆盖、科学正常调用链和证据；主审再次核对关键代码、实值及建议，并作出本报告裁决。

本次取得全部61个变更文件及必要权威文件，共69份固定HEAD文件，按Git blob算法核对一致；另取得恢复运行HEAD的完整测试文件。下载过程对本地复制产生的末尾换行作了精确修正，不把本地序列化差异误报为仓库变化。对代码只作静态调用追踪、差异及AST文本比较；对Git JSON/XML作标准库算术，未执行项目导入、pytest、collect-only、ABI探针、构网、旧场采样、积分或PDE。

| 层级 | 本审阅亲自核对的范围 | 不能由此声称 |
|---|---|---|
| 固定Git代码 | 三个研究入口、测试增量、合同、launch及正常S/F/C字段衔接 | 真实P8空间或求解已成功 |
| 测试实值 | 三份JUnit XML、stdout、运行HEAD、最终测试字节、41个未变定义及完整文件diff | 一次最终同字节18项全通过或全仓CI通过 |
| 单节点trace摘录 | 全部35条已提交getter原行、6个退出尾段及原件索引 | 已亲读工作站1918行完整trace及栈 |
| 单节点资源 | 21条已提交聚合资源行、两个Z态原进程摘录、四个终态PID检查 | 已访问完整每PID资源流，或采样峰等于连续高水位 |
| 身份记录 | 51组source expected/current/snapshot、80组input expected/current的一致性；可用Git源码字节交叉核对 | 已读取工作站全部原快照和80份原件 |
| 工作站原件 | **未亲验**：全部完整trace/resources、原source/input快照、fixture目录及旧P5/primary NPZ | hash引用不等于原件访问或独立重算 |

原件索引见[补验raw_index](outcomes/records/v16_r9_p8_sources/T_user_completion/raw_index.json)、[主控终态](outcomes/records/v16_r9_p8_sources/T_user_completion/terminal_review.json)和[sources导航](outcomes/records/v16_r9_p8_sources/README.md)。工作站本轮原件位于 `benchmarks/artifacts/task43/v16_p8/support/{focused_attempt1,focused_recovery1,resume_phase_completion_attempt1}/`；旧P5数组仍位于V15声明的 `v11_science/support/union_comparison_attempt1/comparison/`，没有在本审阅重新打开。

## 3. 按严重性排列的问题及最小处置

### V16-01｜中：E未实现，不能把helper通过扩写为完整恢复资格

**位置：** [h100入口][h100] `4327–4363`；[测试][tests] `6813–6900`；[当前回应](response_v16.md) `25,50–59`；三个入口的CLI分派。

`_v16_p8_resume_output_binding`只检查互斥用途、固定输出位置和当前worker身份。三个入口没有完整的 `--resume-paired-p8-stage` 实施；没有同一worker中先运行受影响测试、再真实续接S/F_POSTPROCESS/C的动态证据。原V15第9.8节完整E要求没有完成，单节点1 passed不能替代。

**影响与裁决：** E、E_S和FAILED-primary续接不具备运行资格；正常S_MAIN→F→C没有调用E的必需依赖。当前回应如实披露，未发现把E冒写可用。

**最小处置／验收：** 本轮禁止E及其三个resume用途，不为此新增controller、CLI或测试。第9节仅放行正常链；正常代码不得改source_id指向E_S，也不得把失败F伪造成成功terminal交给C。今后若确有恢复需要，应根据实际失败单独限定需要的那一条路径，不预建三套恢复。

### V16-02｜中，有限覆盖边界：没有一个动态正例贯通完整成功F→C

**位置：** [测试][tests] `5722–6248,6344–6753`；[成功terminal writer][h100] `1145–1193`；[C端点reader][compare] `3161–3601`。

main fixture确实经过真实main、observer、primary/raw门和共享JSON writer；writer返回后故意抛 `_WriterReached`，动态贯通的是失败terminal。成功terminal通过独立helper调用检查。四场循环测试使用合成frozen-endpoint、恢复对象和metrics替身，不是完整F成功收口→真实C reader的正向集成证明。

**影响：** 这些证据支持正常路径的组件准入，不支持真实F端点、真实C大样本已经完成。不能说“关键函数全mock”，也不能说“完整端到端已通过”。

**裁决／验收：** 静态交叉检查未发现正常S→F→C字段、路径或成功状态不相容；没有足以要求整套重跑的具体实现错误。接受有限T前门，首次真实S/F/C分别依现场原件完成资格，不额外授权为覆盖标签补测。F成功terminal、endpoint、primary/raw及root joined必须真实相互绑定；C必须实际消费这些原件，任何真实失败不得靠手填PASS补齐。

### V16-03｜中，已修复的测试及监督问题：两次失败不是数值失败

**位置：** [首次XML](outcomes/records/v16_r9_p8_sources/T_main/pytest_results.xml)、[恢复XML](outcomes/records/v16_r9_p8_sources/T_recovery/pytest_results.xml)、[历史修复diff](outcomes/records/v16_r9_p8_sources/focused_recovery1_resume_fixture_fix.diff)、[补验测试][tests] `6813–6900`。

首次以 `degree-plan` 充当合法身份摘要，被真实reader拒绝；恢复批次最后一项错误地要求共享phase尚不存在。主控冻结前均漏识别，责任记录成立。一次用户明确新增的单节点授权独立于原T2/2，不属于擅自第三次T或挪用E。

最终fixture在phase不存在时通过真实首次启动门，再由真实WorkflowLedger创建；之后绑定当前worker/PID/start_ticks/tracer/绝对路径，原phase hash保持不变。实际补验走 `phase_preexisted=false`，结果支持该具体路径。

**重要限定：** runtime reader核当前进程身份和phase路径，不读取已有phase内容来证明旧创建者。未单独执行的preexisting分支，不能外推为“任意外来phase必定被拒绝”或完整E身份安全已验证。正常S/F/C仍保留严格unused-phase默认，故此限定不阻塞当前正常链。

**验收：** 本地fixture修复和用户补验接受；两次失败、各自字节与费用原样保留。测试不得再删除phase模拟首次启动，不再重复18项。

### V16-04｜低，执行前必须完成的静态接线：T资格派生记录尚待生成

**位置：** [S launch][s-launch] `91–94`；[F launch][f-launch] `108–111`；[C launch][c-launch] `97–100`。

三个launch读取 `preparation/T_root_qualification.json`，核固定合同hash及当前51项source map。原T失败记录、补验通过和本review不能自动生成这个文件。

**最小处置：** 按第9.2节一次只读生成新的、前瞻的正常路径资格记录；明确17历史＋1新，不改名原失败、不声称18项批次全绿。这是实际科学启动需要的元数据工作，不是再开一轮历史归档或新支持driver。

### V16-05｜低，维护限制：研究入口增量偏大

**位置：** 本轮diff中 `round1_candidates.py` +1132/−1、`h100_anchor.py` +1728/−134、`compare_round1_candidate.py` +1280/−3，测试+1497行。

约四千行新增研究接线与身份检查，是显著维护成本；没有发现新增共享数学算法、修改shared writer默认或改变activation/ABI。当前不以大重构阻塞一次已经明确的科学实验，也不因为这些代码位于既有文件便认为架构已适合production。

**验收边界：** 保持显式opt-in和research-only；下一轮不再扩建恢复框架。生产迁移应另按最小依赖组审查，本报告不给整分支或这些研究入口merge approval。

## 4. 测试覆盖、身份与T关闭范围

### 4.1 真实覆盖及替身边界

| 测试范围 | 实际验证 | 明确未验证 |
|---|---|---|
| p计划／后置门，测试6251–6337 | 真实既有p-up builder和闭包；固定seed/box/p；无h、180叶及FE门的实际判定函数 | 昂贵authority采用小fixture；110682不是P8实测FE |
| main／writer，5722–6248 | 真实环境、父链、main、observer、NPZ/raw门、共享writer、异常terminal、finally恢复 | 昂贵mesh/solver替身；完整正常main成功收口 |
| 9项raw/身份参数，5406–5720 | 保存原数组检查；系数与mesh索引混包重绑外层hash后仍被拒绝；残差同状态门 | `missing_source`实际测试UNKNOWN_SOURCE枚举，不是所有source-SHA污染形态 |
| 5项四场循环，6344–6753 | 真实循环、旧样本读取、新P8每阶一次、q10失败保q8、binding/输入漂移与joined拒绝 | 合成endpoint、native restore、metric替身不构成科学数值正确性实测 |
| owner/分区，6756–6810 | 真实磁盘/点权/owner-box/轴断点checker，特定负例到达目标门 | 重复合成点不是旧P5或新P8物理解 |
| 单节点，6813–6900 | 真实首次启动及ledger、当前worker绑定、非法用途/改PID拒绝、phase hash不变 | preexisting分支单独实测、完整E CLI和测试后真实resume |

这不是以通过数量替代覆盖评估。关键数值比较仍复用既有 `_field_metrics`、`_modal_comparison`、`_j_infinity` 和冻结分类；没有新增一套计算J/G的数学实现。

### 4.2 17项历史复用成立，不能拼成一个新批次

独立比较 `3b9d5e0…` 的完整测试文件与固定交付：只改最后一个fixture；41个其他顶层定义逐文本相同，完整diff也未改变其他模块常量、装饰器或共同helper。三个研究入口在这几次测试之间同字节。最终测试SHA256为：

`c7ae026e40ac782652b17e87e7399eef541c139ff62900b20caf7ea59e34a236`。

[字节范围记录](outcomes/records/v16_r9_p8_sources/T_user_completion/test_byte_scope.json)与原XML相容；原静态修正版 `80a80fc8…` 和恢复实测 `29b3d134…` 的历史身份也保留。

**T关闭的精确定义：** 本报告从现在接受指定最终研究字节进入正常S_MAIN→F→C；不追认原失败批次成功，不授予E、完整P8端点、全仓CI、生产ABI或科学精度资格。为未使用E补全测试并非本轮S的前置任务。

## 5. 实现与科学口径检查

### 5.1 P8动作与S→F

[计划代码][round] `1328–1448` 核原R9、180根/叶、28个p5/152个p6、global8/root4及box、父p5，仅请求该单元p5→p6，再调用原 `_build_next_round_plan(action="p_up")`。额外实际变化与原 `p_up_closure.forced_increments` 相等；未要求强制闭包为空，未把H8材料root34另加为用户请求。

`1451–1505` 核实际180叶、无h、合法degree/entity及 `110472 < FE_P8 < 237600`。`1508–1644` 的S先读旧P5输入，再建计划和真实authority，及时保存计划及审计；不装PDE矩阵、不factor、不solve。F的 `_load_v16_p8_context` 和 `_v16_p8_actual_space_audit` 继续核实际mesh、degree、约束、trace/interior/carrier和S计数，旧P2错误字段已使用正确键。

未发现将p预测值填入实际门、遗漏必要闭包或偷偷改h动作。**但S尚未运行，实际FE仍未知。** 若只有该cell的cell-p变化，interior增加210只是预测，不是总FE。

### 5.2 F→C

[h100][h100] `954–1051,8180–8362,9413–9602,9740–9774` 保留q15/q28/R13、normal1/extra0、primary/raw先保存、严格残差、实际S空间匹配和Av form记录。NPZ summary策略已显式覆盖R9_P8，不改变共享默认writer。

成功terminal的schema、状态、plan、packet、raw及endpoint字段与[C reader][compare] `3161–3601` 相容。C要求正常F的完整零退出、清理、root joined和原件绑定，不能用旧H8的FAILED适配器直接代替新P8成功端点。

Av观察器记录实际积分form后恢复原函数；不是把q标签写进JSON便视为积分已测。真实F仍要取得所用form metadata、独立吸收及能量闭合。

### 5.3 四场比较

[C循环][compare] `3740–4271` 对固定Y6_1为reference，读取旧P5三场样本，只采新P8；保留612通道、四复幅组、总／散射场和既有地板归一化，Δ方向为R9减动作场。两阶分类、收益/FE和冻结尺度区间与V15第9.6节一致。

S新增owner-box几何包含核对比单纯slot自洽更强，但它仍不是新native场采样或独立全域几何搜索。旧NPZ的点权、背景、mesh和原件身份若不匹配必须拒绝，不能重采旧三场拼补。

当前科学问题未改变：H8未带来超过冻结尺度的输出收益，尚缺同一位置p动作的实测响应。T失败与补验不能回答p是否有效。Y6_1是固定离散目标，不是本轮独立精度已成立的保证；237600 FE只作上界，不反向指导选择。

## 6. 资源、trace、失败与费用

| 批次 | XML实测 | whole含清理，秒 | 树RSS采样峰，B | launcher/watchdog/worker |
|---|---|---:|---:|---|
| T_main | 1 failed；其余17未运行 | 20.264135509729385 | 304947200 | 2/2/1 |
| T_recovery | 17 passed、1 failed | 61.78995769890025 | 519254016 | 2/2/1 |
| 用户单节点 | 1 passed；其余17不重跑 | 12.767253825906664 | 256032768 | 0/0/0 |

原两次合计 **82.05409320862964秒**；三次合计 **94.8213470345363秒**，独立求和与记录相符。pytest 5.59秒等内层时间已含在whole内。初始只读输入核对1.8255486912094057秒另列；其他静态、人工、编辑和Git时间为not_measured。以上不是整轮人工wall或同精度成本。

本审阅重新枚举Git中的单节点35条 `sched_getaffinity` 原行，均返回[1]；6个退出尾段均exit0，原件索引行数合计1918。0 setter／0 signal与已提交摘录和终态相容，但不能由摘录独立证明未提交原文没有遗漏。完整原trace未亲读。原两次T分别有41/91条getter原行、0 setter、各一个正常SIGCHLD；不能把正常SIGCHLD当作异常终止。

21条聚合资源行可重算RSS峰256032768、task VmSwap峰0，末行后代为空；采样间隔实值约0.385–0.785秒，名义0.25秒不是连续监测保证。两个空cmdline是已知worker/orted的Z态，PID/start_ticks及后续清除相容。四个相关终态PID检查均不存在；三份退出码与watchdog相符。

51组source字段和80组input字段内部一致；源码/测试历史范围另由Git字节核实。完整工作站快照／每PID流未亲验。trace从taskset之后开始、TID无独立start_ticks、PSS禁用、未指定cache-path均是已披露边界，不否决这次有界支持fixture；不授共享JIT/global cache或生产运行资格。

读错日志路径后改读已有worker.log没有新增运行；原argv尾空格触发格式检查后保留原字节并单列例外，处理合理。不能把全量diff-check曾报错写成无例外全绿，也不必为原始argv空格重新跑测试。

## 7. 五项能力与验收归属

| 能力 | 状态 | 本轮贡献／仍缺什么 |
|---|---|---|
| 空间 | PARTIAL | P8计划及实际审计入口有限组件验证；尚无P8真实FE/authority结果 |
| 选择 | PARTIAL | 固定同位置p动作尚未求解，无法比较h/p实际收益 |
| 精度 | NOT_PASSED | 没有新科学结果；旧零级s超限和独立精度失败保留 |
| 同精度全过程成本 | NOT_ESTABLISHED | 支持费用准确，但没有新的合格同精度端点或成本对照 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 本轮仍未接线或验证 |

工程成果分项接受，不把E未完成写成完成；单节点资源证据有限接受；科学资格不升级。accepted9/R9、R10拒绝、旧H8无明确收益、旧A1/P4 FAILED均原样保留。

## 8. 依赖组与实际合并资格

| 依赖组 | 本轮文件及依赖 | 裁决 |
|---|---|---|
| compact evidence/docs | V16合同、回应、三次T轻量证据、当前summary/manifest/总账/进展及本review | 接受研究档案与可审阅性；没有实际merge approval |
| test-only | `src/test/test_task43_v11_scientific_restart.py`，依赖三个研究入口、checkpoint及native环境 | 指定节点和字节范围有限有效；不能作为独立生产测试包或最终全文件通过 |
| research-only | 三个研究入口、固定P8合同、其checkpoint/恢复依赖 | 正常用途可继续受控科学实验；E禁用；不提升production默认 |
| checker/benchmark | 保存数组/owner/比较路径、主控终态记录 | 复用设计可审阅；真实P8输入和科学结果尚待S/F/C |
| reusable runner/watchdog | 固定薄launch；通用watchdog/activation本轮未改 | 三次T现场资格限定其调用；未执行S/F/C不是已验证launch成功 |
| production numerical/core | 本轮无共享数学核心变更；既有overlay、全仓和ABI缺口保留 | 无新的生产合并资格 |
| 整分支／do-not-merge | 未资格化恢复路径、大ignored数据及整体研究历史 | 不整体合并；失败轻量档案可保留，原件不入Git，不改master |

任何实际合并仍需后续明确的逐组merge approval及用户授权，由Codex执行。本报告不批准或执行合并。

## 9. 下一轮唯一执行授权：立即完成正常 S→F→C

### 9.1 授权决定与范围

**批准直接推进固定R9_P8科学实验。** 本节前瞻关闭正常路径T，保留原未消耗的S1、F1、C1；**不新增支持次数或正式次数，不重新跑T，不使用E。** 本节与V15冲突之处仅为：完整E不再是当前正常科学链的前置任务，且E及E_S/F_POSTPROCESS/C恢复现明确禁止。其他冻结模型、物理、数值与资源门沿用V15。

下一轮不需要新增数值实现或重构。开始动作是第9.2节的有限静态准入记录，然后运行S。此处没有要求再完成一轮ELF、历史trace、全仓pytest、20项旧测试、native探针或归档campaign。

### 9.2 唯一必要的静态准入记录

canonical仍为 `/home/fenics/Projects/NN-Lab-V2`，artifact前缀仍为：

`/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v16_p8/`。

安全fetch/fast-forward本review，保护未提交和后续工作。核固定交付到当前只增加本review或可解释文档，三个研究入口及最终测试字节与本次接受范围相同；核S/F/C各唯一root从未调用且不存在，输入原件可读、无邻近任务冲突。

允许用标准库只读原T证据及当前文件，生成唯一：

`<前缀>/preparation/T_root_qualification.json`。

该文件必须包含：

1. 现有launch需要的 `status="PASS_LIMITED_V16_SUPPORT"`、固定 `contract_sha256` 和完整当前51项 `source_sha256` map。合同hash保持 `8305bc7bbef3dfc33145a9032a9ce7628b3648f43b4900a982c4b0528f38bc1b`。
2. 原两次FAILED、三份XML/terminal、补验用户授权及各实际HEAD/原件hash；17个具体历史通过节点与新1节点的覆盖对应，不能填一个虚构的18项成功批次。
3. 当前测试SHA `c7ae026e40ac782652b17e87e7399eef541c139ff62900b20caf7ea59e34a236`，历史定义/依赖同字节依据、实际当前源码身份及核验者。
4. 本V16 review的路径、完整提交和文件hash，作为额外的 `authorization_review` 绑定；明确 `allowed_route=S_MAIN_to_F_to_C`、`E_qualified=false`、`E_allowed=false`，科学/生产资格不由此授予。

新资格记录是本review裁决后的派生对象，不是覆写原T失败。若该唯一路径已存在，先检查来源和字节；有效同内容复用，冲突或未知记录不得覆盖或换名绕过。

**保留原V15合同和reader字段的原义。** 现有机器合同、launch manifest以及S/F joined中的 `review_commit` 仍表示其冻结协议来源V15，按现有reader保留 `f72e1c8d031de7acc374f0806ddac06099c461c4`；不要把该字段直接替换为V16导致确定性拒绝。`authorization_review` 只添加到本次新建T资格记录及主控新生成的S/F joined。保持同字节launch自动生成的manifest原样，由其中 `T_qualification` 的路径/hash传递当前授权；不得事后编辑manifest补写V16字段。不改旧合同hash、不放松reader、不向严格的gates/products集合添加额外键。

本步骤不导入项目、不跑ABI/pytest/driver，不消耗动态槽；费用实测或not_measured如实列。只核实际需要的身份及已有结果，不重做完整原trace审计。

### 9.3 唯一模型、动作与科学交付

| 项目 | 唯一允许范围 |
|---|---|
| 父状态 | accepted9/R9，180根/叶、28个p5/152个p6、110472独立FE |
| 请求 | global cell8／forest root4，box `[16.5,5,-10]→[33.5,10,0]`nm，p5→p6 |
| 闭包／几何 | 保留实际p/entity/Floquet闭包；无h分裂、180叶；不增加第二seed/p7/h+p |
| 物理 | 新phi90、50×50×140nm、13.5nm，原材料/Floquet/入射/端口 |
| q／R | operator q15、incident/port q28、R13完整612、原cutoff；Av实际form规则单列 |
| 求解 | MUMPS direct，complex128/int64，normal一次、extra零 |
| 参考 | 固定原Y6_1；两份6×10×6控制及holdout不用于选动作或换参考 |
| 实际FE门 | `110472 < FE_P8 < 237600`；独立trace/interior、carrier、从属行和矩阵rows分别记 |
| 比较 | 复用原P5三场/点权/背景，仅新P8每阶采样一次，q10主、q8稳健 |
| 阈值 | εJ=0.12716416232413652，εG=9.088158796603444e−6，保持原归一化及分类 |
| 结果用途 | 完整612、总/散射E/H/G、J、ΔFE、ΔJ/ΔFE、ΔG/ΔFE；不写transition10、不改变accepted9 |

P5两原NPZ继续按合同绑定：q8 `7286c09d6b3f3bb3a7ece1cd46284a9a5faafd6ebbcb213e2568b6a32ed1119e`；q10 `82d7bc676e23bea0794caf5e16b3d6c28ee02cb18c57cb59e4bfc08a55759f99`。它们分别565248与1104000点、1104共同盒、体积350000nm³。原件不匹配不能重采旧三场补齐。

### 9.4 唯一launch、root、额度与预算

下表路径均相对第9.2节唯一前缀。外层命令只能为 `bash <绝对前缀>/launch/<表中脚本>`，使用本次交付的同字节脚本；不得改名获得新次数。各root由脚本排他创建，不能预先创建成非空后再清理。

| 阶段 | 唯一launch | 唯一root | 剩余次数 | 工作停止／whole含清理 | RSS上限 |
|---|---|---|---:|---:|---|
| S实际空间及旧样本核验 | `space_attempt1.sh` | `support/space_attempt1/` | 1支持 | 1740／1800秒 | 8GiB |
| F正式R9_P8 | `R9_P8_attempt1.sh` | `formal/R9_P8_attempt1/` | 1正式 | 6900／7200秒 | 32GiB |
| C共同点四场比较 | `paired_comparison_attempt1.sh` | `support/paired_comparison_attempt1/` | 1支持 | 1740／1800秒 | 8GiB |

这三次正常链新增whole上限 **10800秒（3小时）**，其中支持3600秒、正式7200秒。原review支持已用2/5，完成S/C后最多4/5；E仍0/1但被冻结，不可转换为测试、重跑或其他用途。用户补验1/1独立记账，不能合并成原T第三槽。

原两次82.05409320862964秒、用户补验12.767253825906664秒均保留；若正常链用满，上述三次T加本链合计最多10894.821347034536秒。这是三次已测支持费用加后续正常链预算上限，不是未来已发生费用，也不是任务历史总费用。静态/人工及更早费用另列。

正式包络仍 **7/9**，P8调用0/1；F调用后最多 **8/9**，历史最后一槽继续封存。没有新正式额度。调用唯一shell即计数，包括preflight或watchdog前失败；没取得watchdog计时则not_measured，不填0，剩余秒数不换次数。

CPU1、MPI1、六线程变量1、task VmSwap=0；support cap8589934592B、formal34359738368B，与原动态available/reserve取更严者，保留 `max(64GiB,15%有效总内存)` reserve。使用原 `activate_task40_phi90_pord64.sh`，worker-local `HWLOC_COMPONENTS=-x86`、`OMPI_MCA_pml=ob1`、既有taskset/strace -D/watchdog父链；不得改共享activation、ABI、缓存策略或安装环境。一次一个Task43 workflow。

启动前核现时资源，worker现场核complex128/int64、MUMPS、MPI1、六线程和父链/tracer；旧补验不能替代这些本次门。正常SIGCHLD等应分类，不能泛化“零signal”为PDE要求。非CPU1成功setter、活worker非CPU1或未解释setter仍否决。

### 9.5 S通过后直接进入F

S只执行原 `round1_candidates --paired-p8-contract <固定合同>`，不装PDE矩阵／factor／solve。完成真实P8计划、必要闭包、完整authority与旧P5样本几何/身份门，及时保存原实值。

主控核完整plan/audit/bundle、真实FE/约束/degree、source/input首尾、资源/trace、退出0/0/0和后代清理，生成：

`support/space_attempt1/v16_p8_space_joined_terminal.json`。

沿用现有schema `task43.v16.p8-space-root-joined-terminal.v1`，`space_source_id=S_MAIN`，仅在真实合格时 `status=S_COMPLETE_ROOT_VERIFIED`。产品键恰为plan/audit/bundle，六个gate为source/input/resource/trace/space/old_samples，均绑定主控亲读的实值和证据文件，不能只手填true。当前授权另记顶层字段，不改冻结协议来源。

S/F两个joined还必须显式写入固定 `contract_sha256`、各自实际 `source_head`、`launcher_exit_code/watchdog_exit_code/worker_exit_code=0`、`descendants_cleared=true`、`remaining_child_pids=[]`，以及 `root_observation_record={path,sha256}`。每个product有真实绝对路径和hash，每个gate为 `pass` 加 `evidence={path,sha256}`；所有引用文件必须已真实持久化、可读、身份匹配，字段/路径遵照现有reader。主控观察记录保存判定用实值及范围，不以单个状态字符串替代证据。不得先制造joined成功再补原件。

**S合格即直接F。** F只使用S_MAIN的 `support/space_attempt1/plan_output/plans/v16_r9_p8.json`，不得选E_S、latest或手工重造计划。S原件或source集合不相容时不启动F。

### 9.6 F通过后直接进入C

F使用交付的唯一launch，实际重建空间在装配前与S逐项一致。保留完整primary、normal前后原向量、独立A6、full-active、condensed、计数、恢复布局、612及Av，primary先于高风险后处理。

严格门：

- 独立完整active A6≤1e−8、full-active≤1e−8、condensed≤1e−9，保留更严格原门；
- normal恰一次、同RHS、正收敛原因及残差严格下降，extra=0；
- 能量闭合绝对值≤1e−5，Av真实体积分；全部必要实值有限；
- FE/trace/interior/carrier/约束与S一致；实际MUMPS、q/R/恢复身份匹配；
- source/input、资源、退出、持久化、清理均合格。

主控亲读成功terminal、endpoint、primary/raw、watchdog和实值，生成：

`formal/R9_P8_attempt1/v16_p8_endpoint_joined_terminal.json`。

沿用schema `task43.v16.p8-endpoint-root-joined-terminal.v1`，`status=F_COMPLETE_ROOT_VERIFIED`，产品键恰为terminal/endpoint/primary_packet/raw_gate_checkpoint，七个gate为source/input/resource/trace/raw/space/numerical_endpoint。保留原V15协议来源，另加本review授权身份。

**F合格即直接C。** 此处只取得 `SOLVED_PRIMARY_PENDING_PAIRED_COMPARISON` 的非official诊断端点，不提前宣告科学PASS。F若FAILED或缺完整成功收口，当前C reader没有已资格化的恢复例外，禁止伪造terminal或借旧H8适配器续接。

### 9.7 C完成科学问题，不因结果不理想截断证据

C只消费正常F及原P5三场数组。每阶仅采新P8一次，核P8真实owner、点权、背景、612与参考方向；每阶完成立即保存，q10故障保q8。完成后主控核完整结果、前后输入、资源/trace、退出和清理，再给最终诊断。

分类保持V15第9.6节：

- ΔJ>εJ、G不超过R9+εG且两阶一致，才是固定参考输出正响应；
- J或G超过其冻结恶化尺度，报告负响应／权衡；
- 其余完整结果为无明确收益；两阶分类不同为采样敏感性未决，不加第三阶；
- 硬门/身份/资源/证据失败为端点未资格化，不当作p方法负结果。

收益/FE同时报告点值及原冻结尺度区间；未分辨微小收益不能除以小ΔFE后宣布优越。只有P8自身正响应、G门成立，且两阶区间下端都高于H8上端，才称这两个固定动作的收益/FE辨优；该区间不是统计置信区间。

J>1或ΔJ未超过门槛不构成提前停止预定两阶比较的理由。在硬门合格时完成两阶并收口，无论正、负或未分辨，不追加seed或模型。即使固定参考J≤1，独立精度也不自动升级。

### 9.8 普通错误、源码冻结和停止权限

**当前没有必须先改代码的确定性阻塞。** 允许直接修复只读准备中的路径引用、派生资格记录的键名/来源、当前导航或格式错误，保存错误与修正；这种修正不得改变冻结合同、研究源码、测试或任何原运行记录，不额外启动native/测试/driver。在唯一stage shell尚未调用且其实际源码/input仍合格时，修正静态准备后继续，不需再等review。

已调用某stage就消耗其槽，不因“普通bug”退款。若真实S/F/C失败，允许立即静态定位并提交最小修复与确切剩余任务，保留已完成产物；**本轮没有可用的动态重试或E恢复权限**。不把未实现的恢复功能临时投入现场，也不借E补跑测试。若发现必须改变受验研究源码或测试，原T资格需按受影响范围重建，现有三次T不自动覆盖新字节；本报告未给第四次T。此限制针对实际新缺陷，不要求在无缺陷时预先再做一次验证。

特别是F/C把current source与S快照比较。S之后修改源码，不能只更新T资格map、修改旧S快照或手填兼容标签继续；不得通过补写hash把新字节追认为旧S所测对象。只改非source清单中的新回应/文档，可记录不同实际HEAD并继续，不能混同为运行时HEAD变化。

数值门失败、FE/几何不符、normal/extra不符、非有限值、资源/时间/CPU异常、身份漂移、父链/tracer异常、必需原件缺失/不可读/哈希不可信、未知退出或清理失败，立即停止受影响动态链；不放宽门、不换参考、不延长、不重解。

达到工作阈值后的whole余量只用于TERM/KILL/reap及保存终态，不继续数值工作。只处理已核本任务PID，不干扰邻近任务。完整合格primary即使已经保存，当前E仍禁用；保存并报告可恢复范围，不能私自恢复或伪造成功收口。

### 9.9 交付及其余禁止项

下一交付应为 `response_v17.md`、`outcomes/records/v17_r9_p8_scientific_results_v1.json` 和必要轻量证据，沿用原v16_p8实际运行root与原合同，不另建一份平行科学协议。更新当前summary/manifest/模型总账/进展，不覆写V16回应、原结果v1、单节点completion、review或失败。

至少交付P8实际FE/trace/interior/约束和ΔFE，F原方程残差/normal/612/R/T/Av，q8/q10完整四场输出、J/G与ΔJ/ΔG、收益/FE和判别范围，以及逐次原始费用、身份、资源、退出和清理。实际启动前可保存T资格轻量副本和引用，不能以这份元数据作为整轮完成。

如果S/F/C触发硬停止，交付已完成的实值、具体失败位置、最小修复和所缺的精确动态节点；不是笼统“等待新任务”。正常阶段通过则主控直接连续执行，**无需为S或F成功另等审阅**。

本节外的E、E_S、FAILED恢复、A1/A2 q重试、A1_R/A2_R、其他B/C、第二seed、p7/h+p、fresh baseline、q/R扫描、成本campaign、迭代、0.7nm、NN/FTT、共享activation/ABI修改及任何合并继续禁止。

## 10. 提交声明

本次只新增本报告；不修改master，不执行合并，不改历史review、合同、失败、负结果及运行身份。未运行本轮项目测试或计算。review完整提交SHA在提交产生后由交付消息提供，避免文件自引用自身SHA。

[round]: https://github.com/Rookie1234567/MyFEniCS/blob/1294527a0ccb6ab6e52c5e3aded2551567fb9256/benchmarks/task43_hp_adaptivity/round1_candidates.py
[h100]: https://github.com/Rookie1234567/MyFEniCS/blob/1294527a0ccb6ab6e52c5e3aded2551567fb9256/benchmarks/task43_hp_adaptivity/h100_anchor.py
[compare]: https://github.com/Rookie1234567/MyFEniCS/blob/1294527a0ccb6ab6e52c5e3aded2551567fb9256/benchmarks/task43_hp_adaptivity/compare_round1_candidate.py
[tests]: https://github.com/Rookie1234567/MyFEniCS/blob/1294527a0ccb6ab6e52c5e3aded2551567fb9256/src/test/test_task43_v11_scientific_restart.py
[s-launch]: outcomes/records/v16_r9_p8_sources/launch/space_attempt1.sh
[f-launch]: outcomes/records/v16_r9_p8_sources/launch/R9_P8_attempt1.sh
[c-launch]: outcomes/records/v16_r9_p8_sources/launch/paired_comparison_attempt1.sh
