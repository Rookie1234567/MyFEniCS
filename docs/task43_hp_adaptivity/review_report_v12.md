# Task43 正式审阅 V12：补齐一次最小验证，条件续接固定 q／小 h 实验

## 1. 身份、总裁决与执行效力

审阅日期：2026-10-27（Asia/Singapore；提交操作按 UTC 记录）。

| 对象 | 固定身份 |
|---|---|
| 仓库／唯一分支 | `Rookie1234567/MyFEniCS`／`task43_hp_adaptivity` |
| 本次被审提交 | `30333c5705d6a9ef64ba22d0d7030dd63a9c763d` |
| 本轮执行依据、比较基点 | 正式 V11 review：`cd4112a0079aba28e9ce1513b58a1b9a51fd6938`，第9节 |
| V11 科学任务书 | `70e2cfdcc3e5a7c3be5e8b714076420e3eac1129` 中的 `supplement_v11_scientific_restart.md` |
| 长期代码基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 实际 S1 运行 HEAD | `4ab4e4e8a80fb13f4c4dde63decfe282b897567e` |
| 实际 S1 局部恢复 HEAD | `14f94a7491c6545c6280ac2a67629e9941a38317` |

审阅开始时远端正好指向被审提交。相对 V11 review 为线性新增3个提交、60个文件变化；未见后续提交。两次运行后的最终交付不能追认为运行时 HEAD。本次审阅仅提交本文件，提交前再次核对远端并以预期父提交保护更新；不覆盖其他工作，不修改 master、不合并、不运行项目或数值计算。

**总裁决：本轮工程整改部分接受，失败与资源档案接受其已披露范围；S1 尚未通过。明确批准第9节的一次新最小支持验证，随后在原前置门满足时连续执行 D1、必要时 P2R，以及原有 P3→P4→P5。** 这不是要求再做一轮纯归档，也不是立即放行正式求解。

不能只补验回应列出的两个断言：本审阅另发现 D1 观察器会错误读取真实约束返回对象的字段，以及原数组校验、旧 A2 子阶段留证的小缺口。修复范围可以限制在两个研究脚本和同一测试文件，无需改数值核心或建立控制框架。新增正式 PDE 槽为0；现有两个未用的 V11 正式槽仍按条件续接。

| 裁决维度 | 本次结论 |
|---|---|
| 工程验收 | 部分接受；V12-01～04按第9节修复／验证 |
| 已执行支持的资源资格 | Git 内实值一致，有限接受；完整 ignored 原流未亲读 |
| 下一步执行 | 明确新增1次支持验证；通过后续接原未用条件链，无须仅为阶段通过再等 review |
| 科学资格 | 五项能力不升级，没有新的 FE、q 响应或 h 收益实测 |
| 合并资格 | 无实际 merge approval；研究档案保留、组件测试和生产合并分别判断 |

## 2. 实际核验范围与可见性

完整阅读三层 AGENTS、仓库原则、Task43任务材料、V11任务书及正式review、本轮response、恢复manifest、结果／静态记录；逐项检查四个研究脚本与测试的全部本轮差异，并追踪所依赖的真实空间返回类型、原向量与读取链。当前README、summary、manifest、模型总账、进展及docs导航的新增状态也已对照。

独立读取 Git 中两份原 JUnit XML、两份launch manifest、launch脚本、runtime identity、watchdog summary、退出码、全部55／16条资源摘录、trace非栈原行和原件索引；重算计数、RSS成员求和、swap、事件分类、费用和文件身份。下载的60个变更文件及三层AGENTS共63项内容，均按Git blob算法与固定提交返回身份核对一致。该核对证明读审字节与Git对应，不证明工作站原件全部真实完整。

| 可见性类别 | 本次实际范围 |
|---|---|
| 亲读并核算的Git内容 | 代码／diff／JSON／XML／shell、资源逐样本摘录及trace事件原行；可按其中实值重新判断门 |
| 历史复用 | V11及更早已审结论；两次支持各自已到达的断言和当时源码；不拼成最终整套通过 |
| 工作站原件未亲读 | 两次完整 `watchdog/resources.jsonl`、`worker.log`、完整 `strace/sched.*`及逐事件完整栈；51项源码现场快照与38项输入原件的完整集合；主控完整观察JSON、fixture磁盘原件、历史A2/R9/Y6大NPZ |
| 本轮不存在的证据 | D1、P2R、P3、P4、P5现场产物；实际h FE／约束完成结果；正式q或h响应 |
| 本审阅没有做 | pytest、collect-only、native导入、归档driver执行、旧场重采样／积分／重算或PDE |

工作站待核原件具体路径已列在 `outcomes/records/v12_recovery_sources/support/{focused_attempt1,focused_recovery1}/root_closeout.json` 的 `raw_index`、`trace_events.json` 的 `raw_trace_index` 和两份 `launch_manifest.json`。无需为外审可见性重跑旧测试；后续主控仍应按实际原件核新门，不能只复述本报告或PASS标签。

## 3. V11-01～08 整改验收

| 原问题 | 固定提交中的检查结果 | 验收 |
|---|---|---|
| V11-01：未导入 Mapping | `round1_candidates.py:14`补导入；真实main／audit fixture包含旧no-seed调用，已通过；未改共享数值核 | 有限工程关闭 |
| V11-02：错误拒绝必要闭包 | `:913–945,999–1039,1725–1777`核所有叶继承父p、实际requested/forced集合，保留必要闭包；测试`:2880–2915,3057–3183`走真实builder与audit后置门 | 逻辑／fixture关闭；实际authority与FE仍未取得 |
| V11-03：primary保存前缺模态键 | `h100_anchor.py:3209–3254,5701–5706,6146–6172`先从live modes取身份，持久化primary/raw门后才采样；恢复的4个真实observer用例通过 | 对该缺陷有限关闭；正式端点未运行 |
| V11-04：原数组及恢复场不完全同状态 | `h100_anchor.py:3007–3149`补RHS／solution／反号残差、正分母；`compare_round1_candidate.py:452–511,660–725`补真实primary/恢复系数与索引绑定，4个reader场景通过 | 部分关闭；见V12-02的齐次RHS与既定反例缺口 |
| V11-05：P5输入未完整冻结 | `compare_round1_candidate.py:96–138,1665–1702,2027–2044`补P2/P4输入首读及首尾一致性；漂移／q10／ledger故障4例通过 | 部分关闭；成功例尾部断言未运行 |
| V11-06：比较fixture没有真实穿过主路径 | 现有fixture确已调用真实比较器，核共同点、方向、分类和失败留证；不能以合成输出代替模型 | 部分关闭；成功与joined负例最终断言待验 |
| V11-07：慢段观察及旧A2后置 | 旧A2移到authority之前；加入委托原函数的观察；缓存委托／alias恢复用例通过 | 部分关闭；观察器真实返回类型错误及子阶段持久化见V12-01／03 |
| V11-08：导航／历史轻证据边界 | 当前导航与失败账基本一致；历史trace补摘录；未知及NOT_RUN保留 | 有限关闭；下一份当前说明须纳入本报告新增风险 |

此处“关闭”指具体旧缺陷及对应有限工程范围，不指整条研究路径、全部ABI、空间或生产资格。实际main fixture中的authority/FE为合成边界，`FE=110473`不是本轮模型结果。依据见[真实测试代码][test]和[本轮结果记录](outcomes/records/v12_recovery_and_scientific_results_v1.json)。

## 4. 按严重性排列的问题与最小验收要求

### V12-01｜高：D1观察器在真实约束函数成功返回后仍会抛错

观察器用于记录“时间花在哪里”，应保持被观察函数的返回值和数学行为。当前[round1:755–759][round-owned]对所有带 `owned_cells` 的对象读取 `cell.degree_map`。但[BrokenHexCellTraceMap:67–85][cell-map]没有该字段；它含cell身份、独立行及trace映射。只有另一类实体映射的cell才有degree map。

真实authority在[stage4:828–839][stage4-call]必经 `build_broken_hexa_cell_trace_constraint_map`，其模块与已导入别名均在观察名单 `round1:770–797` 中。因此该函数返回非空owned cells后，新增摘要代码会抛 `AttributeError`。错误发生在原函数的异常捕获区之后，内层BEGIN还可能没有对应END/ERROR。**这是静态确定的接线缺陷；D1未运行，不能写成已发生的现场失败或hp方法负结果。**

已有 `test_v12_observer_delegates_cache_and_restores_alias_after_errors`（测试`:1921–1996`）只返回整数42或抛原异常，未进入上述结果分支；main fixture替换了整个实际authority，也覆盖不到该问题。

**最小修复／验收：** 仅修改观察返回值摘要，区分实体映射和cell约束真实结构；原函数只委托一次，原结果对象原样返回，不重算degree、不增缓存。以实际返回数据类和临时小数组构造fixture，分别验证两类结果、BEGIN/END、原异常和alias恢复；观察留证自身出错必须明确失败，不伪装成数值函数错误或成功。不得修改 `src/adaptivity/` 的返回结构迎合观察器。

### V12-02｜中，正式链前必须关闭：齐次modal RHS未守住，原数组反例仍缺

“同状态校验”要证明方程右端、解和残差属于同一次计算；仅各文件hash正确并不足够。本轮主要关系已经补上，但[raw checker:2968–2996][raw-modal]允许任意非零modal RHS进入独立A6残差的归一化分母。对应[producer:6036–6045][producer-modal]明确写的是齐次约束，实际保存612个零；这类方程右端应固定为零。

正常producer当前正确，没有证据表明本轮产生了错误数值包。但reader如果接收一个重新绑定hash的非零modal RHS包，会人为放大分母，使相同残差看起来更小。最小修复是拒绝该冻结齐次项的任何非零值，保持原分母语义与容差；不改物理或数值核心。

V11 review要求的full/returned RHS、solution、残差符号、缺solution、零RHS反例未全部落实。[测试:556–580][raw-test]只验证Gram范数公式及一个shape错误；已通过真实reader4例是source、系数和索引身份，不能替代这些原数组反例。

**验收：** 在小型合法primary包正例上逐一制造上述5类错误及非零modal RHS；需要保留一致关系时同步更新相应数组，避免被无关shape错误先拦下。重绑NPZ内数组身份及外层文件hash，走真实raw checker和真实pending reader，确认仍拒绝；不得预写 `audit.pass=false`冒充独立重算。正例保持通过，Gram范数定义、原阈值与正常producer零RHS不变。

### V12-03｜中：旧A2复算虽已前移，完成的子结果仍可能随q10失败丢失

[round1:1396–1453,1555–1722][round]先算raw／modal／q8／q10，最后才整体返回；[main:1925–1955][a2-main]随后一次写出。若q10读取、身份或场检查出错，捕获分支只保存错误与false，已完成raw/modal/q8实值仍在内存中。D1未运行，因此这是未执行路径的留证缺口，不能宣称本轮已经丢失科学数据。

**最小修复／验收：** 在同一helper上增加可选的子阶段checkpoint，raw、modal、q8、q10各完成即原子保存到本次唯一root；绑定原合同、recovery manifest及输入身份。保持旧算术、读取顺序、整体门和旧A2失败身份。未完成项标NOT_REACHED，已完成子门实值照录，部分记录不得把整体pass/official/continuation设为true；失败主记录引用已保存子项，不覆盖其字节。成功与q10故障小fixture验证已完成实值、hash和原异常均保留，后者不进入空间构造。可替换昂贵数据读取／物理依赖边界，但不得mock受验checkpoint及失败处理为PASS。同步修正main测试`:3047–3055`的helper桩签名，避免新增keyword再次造成fixture失败。

### V12-04｜中：最终两处断言合理，但S1未完成；主控覆盖判断仍有遗漏

恢复后的[最终diff](outcomes/records/v12_recovery_sources/preparation/final_unrun_test_assertions.diff)仅把不同shape数组的 `!=` 改为 `not np.array_equal`，并使拒绝regex匹配真实 `root-verified successful attempt`。没有放宽产品门，静态可接受；最终字节未运行，仍不能通过。

P5成功例在旧数组断言后尚未到达joined输入键、首尾快照、核验调用次数及q8/q10文件断言；主控只读看见文件不能替代这些断言。joined负例虽已实际拒绝，最终selector也须通过。

S1恢复仅跑首次受影响的4个selector、展开14例，符合原窄恢复许可；没有发现额外driver或换名抵扣。用尽后停止正确，不是应擅自挪用D1预算继续测试。主控遗漏包括fixture复制方向／缺文件、第二轮断言及真实返回结构审查不足；这些不应归因ABI或数值方法。

**验收：** 第9节把两处遗留断言与本报告确切风险合入一次支持验证；更新当前状态时不得再把“只剩两个selector”当作整条链的完整风险清单。保留旧response与失败原字节，在新回应解释新增审阅发现。

## 5. 两次支持运行、资源与费用裁决

| 项目 | S1首次 | S1唯一局部恢复 |
|---|---:|---:|
| JUnit节点／结果 | 24：10通过、14失败 | 14：12通过、2失败 |
| 测试文件SHA256 | `bc3d1f01fa246d6a79a2faa2bb57a5270d20c1df375780b8ecccd6049900532e` | `5dcfcddb3253266bc3eff5c93172c9e84af553252166ea574db92765a5bdaf2d` |
| whole-watchdog／s | 42.5156832835637 | 7.066758690867573 |
| 同时树RSS采样峰／B | 284934144 | 265719808 |
| 资源摘录行数 | 55 | 16 |
| worker/watchdog/launcher退出 | 1/2/2 | 1/2/2 |
| getter／setter／signal | 57／0／4 SIGCHLD | 19／0／0 |
| task VmSwap、global换入／换出 | 0；0/0页 | 0；0/0页 |
| 末行与清理 | worker exit1、children=[]；已绑定进程不存在 | 同左 |

原始XML计数与相应closeout、退出文件一致。两份launch各51个源码条目，仅测试文件不同；38个输入路径／hash一致。四个研究脚本最终字节均等于两次运行记录；测试最终SHA为 `451f0a71d84b5bc7df28e79124d2f4e9022c7d69b541d03517538ca7e6e743ae`。按两份diff逆向重建的旧测试字节分别命中上述SHA，不能将不同版本的通过节点拼成最终24项全绿。

资源逐成员RSS/swap求和吻合，活成员观察均为CPU1，峰值与summary一致。S1第51条的worker消失发生在退出邻域，下一条已经exit1且空树，不是未解释的活worker affinity缺测。四个SIGCHLD中预设exit7有fixture身份和reaped记录；不能把它扩大成watchdog所有信号故障路径已验证。运行前后身份实值与worker直接父链、tracer、start_ticks一致，支持有限资源接受。[S1证据](outcomes/records/v12_recovery_sources/support/focused_attempt1/root_closeout.json)与[恢复证据](outcomes/records/v12_recovery_sources/support/focused_recovery1/root_closeout.json)给出了具体路径。

保留限制：trace从taskset之后开始，TID无独立start_ticks，RSS/VmSwap是采样，PSS未启用，未指定cache-path，空cache SHA不能证明JIT/global cache稳定；完整ignored原流未亲读。首次真实main、恢复首个observer正例中的真实环境门支持当次worker记录，不能代替未来worker门或全仓ABI资格。

两次whole合计 **49.582441974431276秒**，失败和恢复均计费／计次数。静态明确计时4项合计 **7.670738293323666秒**，编辑、读审和部分收尾NOT_MEASURED；旧V11 **853.8004706790671秒**另列。嵌套阶段时间不加到whole，以上不是整轮人工wall或同精度成本。初始DNS／并行fetch、裸python127、错误读取路径、Ruff定位等准备失败均有记录，未伪称动态通过；初始非clean快照没有冒充后两次干净dispatch。

## 6. 科学意义与未完成结果

| 能力 | 本次状态 | 理由 |
|---|---|---|
| 空间 | PARTIAL | 实际R9_H8 authority、独立trace/interior/FE尚未返回；计划180根／194叶不能替代实际审计 |
| 选择 | PARTIAL | 固定seed8实验尚未求解；不新增接受更新，accepted9/R9与R10拒绝保留 |
| 精度 | NOT_PASSED | 没有新A1完整q响应或独立精度通过；合成P5分类不是模型结果 |
| 同精度全过程成本 | NOT_ESTABLISHED | 当前是支持测试费用；没有等精度完整端点及生命周期比较 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 未接入或验证迭代 |

下一阶段要得到的是：积分阶数变化是否足够小，以及一个固定局部h动作带来多少输出改善、增加多少独立自由度。即使这些诊断成功，也不能自动证明连续真误差、独立holdout达标或一般多层hp有效。参考角色、两份237600 FE控制的后验限制、既有独立精度失败及extra负结果均不改变。

## 7. 依赖组与合并资格

| 依赖组 | 文件／依赖与证据 | 本次资格 |
|---|---|---|
| compact evidence/docs | V12 response／机器记录／sources及当前导航、总账；连同不可改写的历史失败和本review | 接受研究档案价值；无实际merge approval |
| test-only | `src/test/test_task43_v11_scientific_restart.py`，依赖四研究脚本及真实native导入环境 | 部分具体节点有效；最终两断言及新增缺口待验，不独立宣称生产测试包通过 |
| research-only入口／checker | `round1_candidates.py`、`h100_anchor.py`、`compare_round1_candidate.py`、`candidate_checkpoints.py` | 保留显式opt-in研究实现；第4节阻塞未清，尚无完整真实新端点 |
| reusable runner/watchdog | 本轮没有共享watchdog或activation改动 | 不新增生产资格，不以测试shell成功作共享启动的全面验证 |
| production numerical/core | 本轮没有 `src/adaptivity/`、`src/solvers/`数学代码变更 | 旧overlay／共享依赖生产资格缺口未被本轮修复；不批准合入 |
| 整分支／do-not-merge | 含未资格化研究路径和历史负结果 | 不批准整体合并，不执行任何merge |

本轮四研究文件新增1374行、删除121行，测试新增1937行、删除42行。新增主要是身份、读取、留证和显式恢复接线，未发现本轮另写PDE数学算法或开启普通默认路径；仍应保持研究范围，下一轮不再为这几个问题增加通用平台或重复数值实现。既有全仓collection／ABI限制没有解除。

## 8. 本轮验收与责任

接受：失败真实保留、两次支持费用和次数、最终NOT_RUN、必要闭包修正、primary顺序及已实测reader边界。停止符合耗尽额度后的要求，没有依据把它定性为未经授权中断或数值方法失败。

部分接受：S1和后续研究入口的工程资格。最后两断言不是唯一剩余问题；观察器字段假设和原数组／子阶段留证缺口必须在下一次支持启动前修好。主控应把审查从“有没有对应测试名称”转为“实际返回类型、原数组关系、异常发生后哪些字节仍在”。不要求为无关历史或归档错误重跑已通过全套，也不再次处理已关闭的V10静态问题。

## 9. 下一轮唯一执行授权：V13最小收口后续接原科学链

### 9.1 立即可做的具体修复

**批准执行，不需另等任务书。** 仅完成V12-01～04：

- `benchmarks/task43_hp_adaptivity/round1_candidates.py`：观察器返回摘要兼容真实结构；旧A2子阶段checkpoint和失败引用。
- `benchmarks/task43_hp_adaptivity/h100_anchor.py`：只补齐次modal RHS为零的reader约束；不改正常producer、数学门、容差或数值算法。
- `src/test/test_task43_v11_scientific_restart.py`：保留最终两断言修正，补相关原数组／返回类型／checkpoint反例，更新受新参数影响的fixture签名。
- 新回应／结果记录、当前导航／summary／manifest／总账／进展，以及下述ignored薄launch、快照与证据。

`compare_round1_candidate.py`和`candidate_checkpoints.py`本次不需实现改动；优先复用现有真实reader与atomic writer。不得扩大为共享核心、controller、cache算法、环境／ABI重建或无关重构。

先只读核全部真实返回数据类、RHS定义、调用签名和fixture构造顺序，完成静态语法／未定义名／路径检查，主控审查实际diff后提交并冻结。只要还存在这些明确静态问题，就不要花唯一新driver“看看会不会失败”。

### 9.2 执行绑定和唯一新增槽

保留旧合同SHA `6aadbf82a9c816e1e272b087aa2189435bb0163df1ed1b55a363295a773dadf1` 及恢复manifest SHA `fd42af62c989e9b8886c1fb1458a7aa904907d2c241da2f88f6888d1d7340734`。不改旧manifest的四槽列表／review字段，不将新支持槽伪装成旧槽；本节直接追加一次支持许可，无需新增平行manifest或controller。

唯一canonical为 `/home/fenics/Projects/NN-Lab-V2`。支持前缀仍为 `/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v11_science/recovery_v12/`。唯一新增：

- root：`support/s1_completion_attempt1/`；
- shell：`launch/s1_completion_attempt1.sh`；
- 唯一launch命令：`bash /home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v11_science/recovery_v12/launch/s1_completion_attempt1.sh`；
- 次数 **1**；工作停止 **270秒**，whole含清理 **300秒**；树RSS **8589934592 B**与原动态门取严。

shell沿用已验证组织，仅改唯一root、selector清单和本次绑定；dispatch前保存完整argv/env、实际HEAD／源码／输入hash、相对30333的允许diff、本review完整SHA及不可变shell。新review身份可作launch附加字段，不破坏现有P2/P4源码集合比较，不回写旧snapshot。整个支持测试在本次root内创建fixture，绝不写真实formal root。

旧S1=2/2仍耗尽；原V12支持2/4已用不清零。追加后该恢复包络为 **已用2／最多5次、名义whole总上限3300秒**，其中D1/P2R仍各最多一次。任何调用唯一shell即用槽，包括pre-watchdog失败；剩余秒数不能换次数。新槽失败后没有自动恢复槽，不挪用D1或P2R重跑测试。

### 9.3 一次支持验证的精确范围

在同一个受监控pytest worker中仅执行下列6个selector范围；可参数化所列小反例，启动前静态登记完整展开节点，**最多16个节点**，不执行collect-only。命令使用 `python -u -m pytest -q -s --tb=short --maxfail=1`，JUnit与basetemp均在新root；不选择整个文件或目录。

| 顺序／selector（均位于现有测试文件） | 必须实际验证 |
|---|---|
| 1. `test_main_reaches_v11_mesh_sentinel_with_watchdog_identity` | 复用真实main／真实runtime门，核新worker ABI、CPU、父链、tracer及ledger；只替换mesh/authority昂贵边界。更新A2 helper桩签名并核checkpoint调用，不做真实构网／PDE |
| 2. `test_compare_v11_union_reads_bound_p2_p4_inputs_and_preserves_q8[None]` | 两断言之一及此前未到达的全部成功尾断言 |
| 3. `test_v12_p2_joined_source_binding_rejects_root_terminal_failure` | 真实拒绝与最终regex |
| 4. `test_v12_observer_delegates_cache_and_restores_alias_after_errors` | 扩充为真实entity-map和cell-constraint数据类返回，原对象／委托次数、缓存及alias恢复；原异常与观察留证错误分类 |
| 5. 新 `test_v13_raw_packet_same_state_and_zero_modal_rhs` | 1个合法包及第4节六类原数组反例；实际checker／reader重算，不靠预填false或无关hash错误 |
| 6. 新 `test_v13_saved_a2_partial_checkpoint` | 成功与q10故障两种小fixture；完成子项及时保存，错误不覆盖旧字节／原异常，部分项不变成整体通过 |

第一项中的身份／环境函数必须委托真实函数，不mock为PASS；把实际返回持久化。该项失败即结束此次验证，不执行后面的fixture，更不启动D1。其余节点的异常注入只能在临时小fixture内，预期异常须被断言捕获，不属于另一次driver。

旧observer4例、原reader4例及P5负向4例可按原字节和覆盖范围复用；不要求旧24项、D3二十项、全仓pytest或p6 witness重跑。若最小修复改变了本节未覆盖的产品行为，不能以“历史通过”掩盖，应先缩回本节允许范围；不能静默扩大测试／运行额度。最后一次源码或测试修改后，相关新节点必须实际通过；静态AST/lint不替代。

### 9.4 共同资源、身份与失败规则

所有后续工作继续使用 `scripts/activate_task40_phi90_pord64.sh`；仅worker内 `HWLOC_COMPONENTS=-x86`、`OMPI_MCA_pml=ob1`。CPU1、MPI1、OMP/OpenBLAS/MKL/BLIS/NumExpr/VECLIB六线程变量1；同一实际worker确认complex128/int64、MUMPS可用及父链，不另开ABI探针。

继续 `taskset -c 1`、`strace -D -ff -ttt -k -e trace=sched_setaffinity,sched_getaffinity`、watchdog直接父链与原0.25秒采样设置。task-tree VmSwap必须0；global换页单列，RSS及available/reserve按原更严门。PSS和cache未测的边界如实保留，不清缓存、不预热、不扫描参数。

非CPU1成功setter、活worker非CPU1、未解释setter、源码／输入／父链漂移、资源超限、写入或清理失败立即停止受影响动态链。工作阈值后只允许停止、reap和保存已得记录；不利用whole余量继续计算。whole超限、退出未知或相关后代残留不能合格。所有停止只针对已核PID，不干扰其他任务；同时仅一个Task43 workflow。

新S1的任何真实测试失败或上述硬失败均不得重试。允许静态定位和最小修正后交付确切未验范围，但不借其他槽补测。没有新的证据错误时，不要求重复既有大原件全集审计。

### 9.5 S1通过后直接执行D1，P2R沿用原条件

**S1所需节点全部通过、源码绑定完整且主控亲读新终态后，明确允许立即执行原D1，无需再请一次review。** D1/P2R不新增次数或时限：

| 阶段 | recovery_v12下唯一root／launch | 剩余次数 | 工作／whole，秒 |
|---|---|---:|---:|
| D1 | `support/authority_profile_attempt1/`／`launch/authority_profile_attempt1.sh` | 1 | 540／600 |
| P2R | `support/space_and_saved_primary_attempt2/`／`launch/space_and_saved_primary_attempt2.sh` | 1，条件使用 | 1740／1800 |

两者树RSS上限均8GiB与动态门取严；唯一命令均为 `bash <recovery_v12绝对前缀>/<表中launch>`。先复算并保存旧A2已存数组，再构固定seed8的真实空间authority。允许构网／约束和保存数组算术，不装PDE矩阵、不factor、不solve、不重新采样或积分旧A2。

D1只回答慢段的实际工作量、重复／缓存委托及耗时，并取得能完成的P2产物。保留每类调用BEGIN/END、单调时间、CPU、参数／key、原cache信息和未返回状态；嵌套耗时不能相加成workflow。若D1完成全部真实P2门，直接使用其产物，**不跑P2R**。

D1只有单纯到时且有序清理、观察完整，才适用V11 review §9.5的诊断例外：主控根据实际工作分解、未完成类别和冷启动／闭包／监督／持久化费用，形成支持1740秒内完成的保守估计，才可执行P2R一次。未返回慢调用不得按零耗时或单个温缓存命中估算。没有依据、数值门失败或任何身份／资源／trace／写入／清理硬失败则不运行P2R。D1不重试，不因RSS低或旧终止栈含Basix便延时。

本轮新S1槽用尽后，D1若又揭示需要改代码的问题，仅允许静态定位／修正并记录未验证范围；没有剩余动态验证权，不能改完直接P2R。禁止借诊断新增缓存算法、改变空间、seed、p/q或重新建环境。

### 9.6 P2合格后，原P3→P4→P5条件授权继续有效

**明确允许主控逐门核实后连续执行，不再为“阶段通过”等待新授权。** 原 `v11_science/` 前缀下的唯一root和launch保持：

| 阶段 | root／launch文件 | 剩余次数 | 工作／whole，秒 | RSS |
|---|---|---:|---:|---|
| P3 A1_q3 | `formal/A1_q_attempt3/`／`launch/A1_q_attempt3.sh` | 1正式 | 6900／7200 | 32GiB与动态门取严 |
| P4 R9_H8 | `formal/R9_H8_attempt1/`／`launch/R9_H8_attempt1.sh` | 1正式 | 6900／7200 | 同上 |
| P5共同点比较 | `support/union_comparison_attempt1/`／`launch/union_comparison_attempt1.sh` | 1支持 | 1740／1800 | 8GiB与动态门取严 |

launch命令均为 `bash /home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v11_science/<表中launch>`；实际argv只允许原模式及已批准恢复绑定。模型保持新phi90、50×50×140 nm、13.5 nm；P3为原R10空间180cells／118800 FE、q19/q32/R13；P4为R9父空间只请求seed8一层h、必要闭包、每叶继承父p、q15/q28/R13。normal一次、extra零。

| 放行点 | 主控必须从实际原件核实 |
|---|---|
| P2→P3 | 合法requested/forced闭包与全叶p，实际独立trace/interior/FE及约束；`110472 < FE_h < 237600`，carrier／Floquet／矩阵rows各自口径；旧A2 q8/q10全门；所选D1或P2R四产品、joined、输入／源码／ABI／资源／清理完整。计划194叶不是通过依据 |
| P3→P4 | 完整primary原向量／独立A6／full-active／normal计数、612通道、Av、q8/q10；新A1对旧R10的所有冻结q门通过，退出／资源／清理合格；A1失败不重试 |
| P4→P5 | 装配前真实空间与选定P2一致，实际rows/NNZ另实测；完整primary及同状态原数组门；`SOLVED_PENDING_POSTPROCESS`和零退出／完整清理。pending不冒充完整结果 |
| P5→完成固定诊断 | R9、h、Y6三场同一公共分区q8/q10、全612、总／散射指标及物理输出，输入前后不变，P4/P5联合终态与原件绑定。q8/q10分类不同保留科学未解决，不再采样或重跑 |

冻结门保持：A6≤1e-8、full-active≤1e-8、condensed≤1e-9，normal同RHS、正收敛原因、严格下降一次，extra=0，体吸收能量闭合≤1e-5；原更严格门照旧。A1／旧A2 aggregate、单通道、归一场门仍为1e-6／1e-7／1e-5；P5 epsilon_J=`0.12716416232413652`、epsilon_G=`9.088158796603444e-6`不改。

P5交付两个采样阶次的J、eta、全部关键输出、Delta_FE及单位新增FE收益；参考始终Y6固定数值目标，正／负／无明显收益或采样敏感均如实报告。不写transition10，不改accepted9，不用后验control指导seed或选择。

### 9.7 总额度、证据与交付

本报告新增正式额度为0。历史正式5/6及封存末槽保留；扩展当前5/8，仅原P3/P4最多再用2槽至7/8，A1最多累计3次、A2仍3次、R9_H8最多1次。sanity、D3及原S1均不复活。

下一轮未用支持whole上限为 **300+600+1800+1800=4500秒**（新S1、D1、条件P2R、原P5）；原两个正式whole共14400秒，后续总上限 **18900秒**。已发生49.582441974431276秒及更早费用单列。跳过P2R或提前失败不释放可改用途次数。全部失败、预检失败和清理计费，未测静态时间不补造。

每次保存launch／source/input快照、真实退出、PID/PPID/start_ticks/TracerPid、trace与资源原流、阶段和partial；每项科学实值完成即落盘。主控joined在进程退出后从实值生成，不预填通过。Git保留可复算的关键实值、失败原行和索引，大NPZ与完整流仍放ignored。

交付 `response_v13.md`、`outcomes/records/v13_minimal_completion_and_scientific_results_v1.json` 及必要轻证据，更新当前导航／summary／manifest／总账／进展；不修改旧response、review、合同、manifest或失败记录。成功则交付固定q与h实验结果；受控停止则交付具体阻塞、已完成实值和最小剩余技术任务。**本次执行的起点是9.1的修复与9.3的唯一支持验证，不是再次等待一个新任务。**

A1_R、A2_R、一般B/C扫描、fresh baseline、同精度成本campaign、迭代、0.7nm、NN/FTT及所有合并继续禁止；仅本节点名的固定R9_H8例外按原V11许可执行。

## 10. 最终声明

工程整改、有限支持资源资格、实际科学结论和merge approval是四件不同的事。本轮保留所有历史负结果，不把静态修复、合成测试或hash变成科学通过。正式review提交完整SHA在提交后交付，不在文件内制造自引用SHA。

[round]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/benchmarks/task43_hp_adaptivity/round1_candidates.py
[round-owned]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/benchmarks/task43_hp_adaptivity/round1_candidates.py#L748-L797
[cell-map]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/src/adaptivity/hcurl_broken_cell_trace.py#L67-L88
[stage4-call]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/src/adaptivity/stage4_local_h.py#L828-L839
[raw-modal]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/benchmarks/task43_hp_adaptivity/h100_anchor.py#L2968-L2996
[producer-modal]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/benchmarks/task43_hp_adaptivity/h100_anchor.py#L6036-L6045
[a2-main]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/benchmarks/task43_hp_adaptivity/round1_candidates.py#L1925-L1955
[test]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/src/test/test_task43_v11_scientific_restart.py
[raw-test]: https://github.com/Rookie1234567/MyFEniCS/blob/30333c5705d6a9ef64ba22d0d7030dd63a9c763d/src/test/test_task43_v11_scientific_restart.py#L556-L580
