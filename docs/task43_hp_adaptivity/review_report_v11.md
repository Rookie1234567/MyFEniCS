# Task43 正式审阅 V11：修复实际执行路径，有限诊断后续接科学实验

## 1. 审阅身份、结论与执行效力

| 项目 | 本次审阅固定身份 |
|---|---|
| 仓库／唯一执行分支 | `Rookie1234567/MyFEniCS`／`task43_hp_adaptivity` |
| 被审提交 | `6755cf4ace94c6d06b50c98f13489d8726de67be` |
| V11 任务书提交 | `70e2cfdcc3e5a7c3be5e8b714076420e3eac1129` |
| 长期代码基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 审阅对象 | 上述固定提交的代码、测试、机器合同、Git 内运行摘录与当前文档；不是未来修复字节 |
| 审阅日期 | 2026-10-26 |

审阅开始时远端分支确为 `6755cf4…`，没有后续提交。执行方在工作站的 clean／ahead-behind 陈述与当时远端相容，但本审阅环境没有读取其 canonical worktree，不能独立认证工作站工作树。报告仅新增到同一执行分支；不修改代码、历史任务书、合同、失败记录或既有 review，不执行测试、支持 driver、采样或 PDE，不合并。

**裁决：V11 交付部分接受。真实失败及停止的记录基本成立，科学前门尚未完成，当前实现不能直接启动 P3。下一轮明确批准第9节的有限修复、定向支持验证和一次原因诊断；有实测预算依据时允许一次 P2 恢复。P2 合格后，原来未消耗的 P3 A1_q3、P4 R9_H8、P5 三场比较条件授权继续有效，主控核门后可以连续执行，无需逐阶段再次等待 review。**

这不是增加正式 PDE 槽位，也不是把当前未运行路径判为通过。第9节是下一轮唯一新增执行章节；物理、参考、数值阈值和科学判别沿用 [V11 任务书](supplement_v11_scientific_restart.md) 与 [原机器合同](outcomes/records/v11_scientific_restart_contract.json)。本报告只前瞻修正实现要求、支持额度及恢复路径，不追认旧失败或不充分放行。

| 裁决维度 | 结论 |
|---|---|
| 文档与受控停止证据 | 部分接受；计划／实测、支持／正式及失败账大体区分正确，仍需第3、8节所列小范围勘误、摘录补充 |
| 工程实现 | 部分接受；存在三个确定性执行阻塞，以及原数组、采样场和输入不变性绑定缺口 |
| 当前运行资格 | 固定被审字节不具备 P3–P5 放行条件；第9节修复与前门通过后按条件恢复 |
| 科学资格 | 未新增 q 响应或小 h 收益结果，不能将 P2 超时称为 h/p 方法负结果 |
| 实际合并许可 | **没有 merge approval** ；本报告不授权合并任何依赖组或整分支 |

## 2. 实际审阅范围与证据可见性

完整阅读三层 `AGENTS.md`、任务书、V11 补充任务书、回应、机器结果与合同；检查 P1/P2 closeout、交付静态检查、提交的 launch 文本、source/input manifest、终态、阶段记录、trace 摘录及保存计划；对照当前 README、summary、selective merge manifest、模型总账和开发进展。直接比较任务书提交至送审提交的全部差异，并沿引用检查相关未变的空间、求解、恢复和物理比较代码。没有将 response 的 PASS 或数量当作实现正确性的替代。

实际提交链为：

| 提交 | 用途与字节边界 |
|---|---|
| `c976dda2076ea7ce802c279bb56b3189fa10dced` | V11 实现、合同与初始测试；P1 首次运行 HEAD |
| `cfe1adae3805c432b0a58349853a70ac47ceed2a` | 修复测试桩位置参数；P1 局部恢复 HEAD |
| `2d01bfae15a3831683a859673e69f0c992186b85` | P1 记录收口；P2 实际运行 HEAD |
| `6755cf4ace94c6d06b50c98f13489d8726de67be` | P2 停止证据与文档交付；不是历史运行 HEAD |

任务书至送审的四个研究 Python 文件合计新增约4014行、删除85行，另新增1388行测试。`2d01bfa…` 至送审为文档／证据变化。没有修改 `src/` 数值核心、共享 watchdog 或 activation，没有改写历史 review、冻结合同、正式失败记录。代码规模本身不是拒绝依据，但应逐条检查真实路径；本次确实发现了仅审阅摘要不能发现的问题。

| 证据层级 | 本审阅实际做了什么／没有做什么 |
|---|---|
| Git 原文件 | 直接读取固定提交代码、测试、JSON、shell、计划与逐行摘录；核对下载文件的 Git blob 身份、关键 SHA、提交差异和算术关系 |
| Git 中的运行摘录 | 读取 P1 两次提交的资源小流、P2 资源汇总／关键行、阶段 JSONL、退出和清理记录、affinity 事件／帧索引；这些是可外审的摘录，不能替代未提交原件 |
| 工作站 ignored 原件 | **未亲读** 完整 P2 `resources.jsonl`、三次完整 trace、全部 source/input snapshot 原文件、旧 A2/Y6/R9/R10 NPZ 或系数、完整 stdout/stderr；不声称重新运行或重算这些原件 |
| 历史复用 | 原 D3、V10、R9/R10/A2 资格按既有边界保留；本轮没有重做其动态验证，没有重开 V10 静态归档问题 |
| 推断／UNKNOWN | 根据代码可确定未来异常；根据单个停止栈只能判断终止瞬间的位置。空间 authority 的完整耗时分解、实际最终 FE、未返回阶段的执行结果仍未知 |

下文代码行号均对应 `6755cf4…`。记录以文件路径及 JSON 字段／事件名定位；完整原件 hash 是身份声明，不是本审阅已读原件的证明。

## 3. 按严重程度排列的问题

这里的“高／中／低”是审阅严重性，与 P1–P5 阶段编号无关。全部阻塞都要求局部修复；不据此重建控制平台、改数值方法或要求全仓重跑。

### V11-01｜高：共享 `_audit_plan` 新增未绑定的 `Mapping`，authority 返回后仍会失败

**位置：** [round1_candidates.py][src-round] 顶部导入及第780–803行，尤其783、800、803行。

文件只导入 `Any`，没有定义或导入 `Mapping`，却在运行表达式 `isinstance(seed, Mapping)` 中使用它。这不是延迟求值的类型注解。即使旧计划没有 `v11_seed`，首个 `isinstance(None, Mapping)` 也要解析该名字，因此会影响旧 `_audit_plan` 调用，不仅是 V11 opt-in。

**影响：** 当前 P2 在更早的 authority 构造中停止，尚未触发此异常；不能将它写成本次超时原因。但只修闭包条件后直接重跑，完成重计算仍会遇到 `NameError`。manifest 第9行“无普通默认行为变更”的绝对陈述不成立。

**最小整改／验收：** 补正确导入；以重边界替身进入真实 `_audit_plan` 的后半段，分别覆盖旧无 seed 计划与固定 seed8 计划。保留真实元数据、计数与继承代码，不能把 `_audit_plan` 整体替换。对本轮改动文件做未定义名字静态检查，记录实际范围；不以 compileall 代替名字可达性检查。

### V11-02｜高：把必要闭包为空列为门，且 P1 未覆盖实际计划和后置门

**位置：** [round1_candidates.py][src-round] 第1668–1696行，尤其1688；[V11 测试][src-test] 第417行起的 seed fixture、第1009–1325行真实 main sentinel。

`or space_detail["forced_closure_root_ids"]` 要求被迫闭包为空，违反任务书“保留必要材料／周期／2:1／阶次闭包”。提交的计划 SHA 为 `0f5885976b000a24e2f21b5aa5f4d0ea97fdd142cac9208e25d4c6e615d1ac23`；其中 expected forest 是180根、194叶、user closure 1、material closure 1、hanging patches 9。该构造信息不能证明最终空间，但已足以否定“必要闭包必须空”的预设。

seed fixture 替换 `_build_next_round_plan`；真实 main sentinel 在 `_audit_plan` 前终止。两者验证了部分输入拒绝和启动链，**没有验证真实 builder 产生非空必要闭包后能通过真实后置门** 。主控 P2 放行缺少该项任务书要求的证据；fixture 参数恢复通过也没有补上这一点。责任属于实现和放行审查，不能只归咎运行时长。

**最小整改／验收：** 删除“非空即拒绝”，同时保留并核对闭包的来源与集合：用户唯一 seed 为 mesh global cell 8，几何盒为 `[16.5,5,-10]–[33.5,10,0]`，不要把该编号混成 forest root index；forced roots 必须恰为原 builder 对该计划产生的必要闭包。所有叶，包括 forced roots 的叶，继承各自父 p；不得额外改 seed、p 或 level。用真实计划构造器覆盖合法材料闭包、伪造额外 root、错误继承三类情形，实际后置门分别接受／拒绝。实际 FE 必须仍满足 `110472 < FE_h < 237600`，expected forest 不参与冒充 FE 验收。

### V11-03｜高：primary-only observer 在保存 primary 前读取尚未生成的模态键

**位置：** [h100_anchor.py][src-anchor] 第4941–4990、5120–5129、5295–5296、5481–5503、5534–5537行。

`captured["ordered_mode_keys"]`、`captured["mode_count"]` 由 `capture_primary_fields()` 填入；V11 为先存 primary 而跳过此前 capture，却在第5481–5482行构造 packet identity 时先读这两个键。首次 V11 capture 在第5537行。P4 提前存入空间审计也不会补这两个键。因此 P3/P4 在 observer 到达此处时会先发生 `KeyError`，完整 primary packet 写入尚未开始。此前的 pre-validation checkpoint 不能冒充完整原向量 primary。

**最小整改／验收：** 使用第5121行起已有的、已校验的 `view.goal_context["modes"]`／`ordered_mode_keys` 绑定身份。取得现有 live view 所需的正常恢复、full-active与A6数据后，在 observer 内后续 field export、采样后处理及其运输风险之前落盘 primary；不能为填键而把高风险采样移到保存之前，也不要求重排共享核心进入 observer 前已经完成的恢复／端口计算。调用真实 `_run_impl` 所注册的 observer，以小型 view／原数组替代昂贵 solver 边界，分别走 A1_q3、R9_H8。验证一次 normal、零 extra，原向量门失败后保留包并停止后处理，A1 q10 故障保留 primary 与 q8，P4 将体采样留给 P5。现有“先调用 writer 再人工抛采样异常”fixture 不足以验证这一顺序。

### V11-04｜高：残差数组可来自不同状态，P5 采样场也未完全绑定到 primary

**位置：** [h100_anchor.py][src-anchor] 第2487–2737行；[compare_round1_candidate.py][src-compare] 第339–417、507–556行；[V11 测试][src-test] 第45–70、123–347、387–395行。

当前 raw checker 已检查 full-active 与 recovered active-full、normal_after 与 returned condensed 的部分关系，但没有强制以下同一状态关系：

- full-active 保存的 reduced RHS 与 returned RHS 一致；reduced solution 与 returned solution 一致，前者甚至未列为必需数组。
- full-active 的 reduced `Ax-b` 与 returned 的 `b-Ax` 是同一个残差的相反数。
- 对本次非零激励模型，用于相对范数的 RHS 范数必须有限且严格正；不能用极小分母替代把零 RHS／零残差错误包装成合格物理端点。

这不是臆测坐标系：未改的 `src/solvers/dtn_port_3d.py` 第8000–8019、8498、8560–8565、8989–8991行显示，本路线使用同一 `A_aug/b_aug/x_aug`。当前正例第55行 full reduced RHS 为零，第62行 returned RHS 为一，仍被当作有效 pending 包，直接暴露了缺口。应保持现有 Gram dual norm 的数学定义，不能改为随意拼接的 Euclidean 范数。

此外，P5 分别核 primary NPZ 与恢复 storage 的 hash，却没有把实际用于采样的 `recovered_p6_local_coefficients` 与 primary 中的 `recovered_recovered_p6_local_coefficients` 逐项绑定。两个文件各自 hash 正确，不能证明残差合格的场就是比较的场。完整 source／candidate／plan 身份也应在 primary、storage、endpoint、terminal 间一致。

**最小整改／验收：** 补相同坐标系、shape、顺序、符号及系数／必要恢复索引绑定；修正正例，增加 RHS、solution、残差符号、缺数组、零 RHS、换系数和错身份反例。反例重新绑定合法文件 hash，避免只是撞上外层 hash 拒绝；不得预先把 `raw_audit.pass` 设 false 冒充独立原数组核验。仍只算保存数组范数与恒等关系，不新施加 PDE 算子。

### V11-05｜中，执行前必须修：P5 新生成输入未完整进入前后不变性检查

**位置：** [compare_round1_candidate.py][src-compare] 第65–86、1504–1505、1812–1818、1839–1850行；`v11_scientific_sources/launch/union_comparison_attempt1.sh` 第62–76行。

内外清单主要列原合同旧输入。实际读取的 P2 plan/audit 与 P4 endpoint、terminal、primary、storage、modal、launch/watchdog/exit 等新产物没有完整进入读取前冻结、读取后对照的集合。结束时再 hash 新输入，不能证明计算始终消费这些结束时字节。

外层50项源码清单及主控审计已含内部清单遗漏的比较／恢复依赖，所以不将其误写为整个流程完全漏核源码。应统一已有完整清单，并补齐真正消费的新输入。

**最小整改／验收：** P5 读取前保存全部实际输入映射，结束逐项比较，不用末态 SHA 替换开始 SHA；中途漂移必须退出非零，保留已存 q8，不授完整诊断。第1820–1831、1966–2003行的数据记录可能先于后续 ledger 异常写出，必须由 worker 外主控在 watchdog 退出后形成 joined 结果，任何 failure 文件、非零／未知退出、绑定错误或清理失败均否决。当前 official／continuation 已保持 false；本问题是完整诊断资格与同一数据身份，不是已证实的 production 权限泄漏。

### V11-06｜中，执行前必须补：P1 的比较／失败 fixture 没有穿过关键真实路径

**位置：** [V11 测试][src-test] 第619–718、975–1006行及上文各处；[compare_round1_candidate.py][src-compare] 第1467–2003行。

common-points fixture 把三个相同单箱 axes 送入原 quadrature builder，再检查 FE 增长边界，没有调用新的 `compare_v11_union`。它不覆盖不同 h 断点、三场六次采样、612模式、参考方向、完整分类、q10异常和写入顺序。pending 正例传入内存 dict，磁盘 endpoint 文件只是占位文本，不能证明真实 reader 联合读取成立。

**最小整改／验收：** 新增一组穿过真实 `compare_v11_union` 的小型合成流程，只替换 native mesh／field 恢复等重边界；保留真实 metrics、J、classification 和文件读写。三组不同 axes 含 h 新断点，q8/q10 每阶三场同点同权；验证 Y6→R9、Y6→h 方向、固定 floor、带符号输出、完整模式、正 Delta_FE 及分类冲突。注入 q10、终态 marker 和输入漂移失败，核 primary/q8 不变、非零退出、无完整 joined 资格或 selection transition。不要再增加一批镜像实现的 PASS 计数。

### V11-07｜中：空间构造缺少可归因计时，独立旧 A2 工作及部分结果被后置

**位置：** [round1_candidates.py][src-round] 第687–696、1663–1710、1900–1955行；`P2_space_and_saved_primary_attempt1/stages.jsonl`；[P2 closeout](outcomes/records/v11_p2_closeout.json)。

`mesh_authority_begin` 后只有大阶段包围，进程在内部停止时没有返回实际空间审计；旧 A2 保存数组核验排在其后，也完全未到达。该顺序使独立、可能较轻的工作和已完成的阶段结果一并缺失。

直接读调用链发现：`stage4_local_h.py:789–842` 构造物理 broken trace、阶次、全局实体和 cell trace 约束；`hcurl_broken_cell_trace.py:1605–1611` 逐 owned cell 请求 variable-p reference space；`exact_sequence_variable_p.py:510–617,1048起` 涉及已有缓存、custom element、插值、SVD／QR及精确序列检查。这些是待区分的成本来源，不是本次已经测出的瓶颈分解。P4 第2967行的预装配 authority 与后续旧 reduction 第1208行也可能重复构造，应记入真实生命周期；尚不能断言时间翻倍或擅自删审计。

**最小整改／验收：** 将旧 A2 原数组只读复算先行、独立原子保存；逐实际阶段 BEGIN／END 留证，保存已完成 mesh／计划／authority 结果后再判后续门，失败时明确 incomplete。使用第9节一次诊断取得真正调用／缓存键／阶段／CPU秒信息。只增加观察和持久化，不改变数学、闭包、缓存策略、线程或监督频率；不新建 controller。

### V11-08｜低：文案与轻量证据还需精确收口

**位置：** `docs/README.md:3`、`outcomes/selective_merge_manifest.md:9`；`v11_p1_closeout.json` 的 getter 摘要；`P2_space_and_saved_primary_attempt1/trace_events_and_frames.json`。

docs 总入口仍写 V10／V9 权威，应更新为本次 review 与后续回应；manifest 应承认 V11-01 的旧调用回归风险。P1 恢复记录中“all returned CPU [1]”缺逐事件原行；P2 的帧集合做过 sorted-unique，不能由其独立恢复某个事件与其完整栈的关系。

**最小整改／验收：** 从既存原 trace 静态追加 P1 恢复的全部 affinity 事件原行、行号、时间戳、返回值及各文件结束尾；追加旧 `sched.2036715` 第713–736行连续原块，绑定原 trace SHA，核实 SIGTERM→Basix帧→终止尾。原件读不到就记未核验，不重跑支持或 PDE。此补证不是 V10 归档任务重开，也不是新运行的替代。

## 4. P1、P2 证据及费用裁决

### 4.1 测试身份与可复用范围

P1 首次为7 passed、1 failed，恢复仅1 passed。初始与最终测试文件差异确为 `stop_at_p2_audit(*, plan_path, …)` 改成 `stop_at_p2_audit(_cfg, *, plan_path, …)`，只影响该测试函数。初始 SHA256 为 `14e1d73daecba2e762935b340ba4635afedd43faec1d8e9f67f9f475376cb209`，最终为 `ce9ad7fdd8b07a8b33f55fc26c721dd17eb546315b60f03449cba8fe49d5fd2b`。

因此，未改七项可以按原字节／原断言范围复用，恢复证明实际参数签名已修正；**没有一次最终同字节整套8项通过** 。更不能将原八个 selectors 的数量视为 V11-01～06 风险已覆盖。源码新增约四千行时，仅 sentinel、mock 和 count 不足以完成放行审查。

P1 的 `strace -D` 证据支持本次 direct-watchdog worker 父链组织；恢复的 worker／tracer 均被 watchdog 覆盖。fixture 的故障子进程不是实际 direct worker，不能将其退出7外推为任意 worker 故障清理。P2 的实际 TERM 与清理提供另一条有限实测。后续每个 worker 的身份、ABI、affinity 和终态仍要现场核验，历史证据不替代本次。

### 4.2 成本与终态

| 工作流 | worker／watchdog／launcher exit | whole-watchdog，s | 同时进程树 RSS 采样峰，B | 结果与范围 |
|---|---|---:|---:|---|
| P1 首次 | 1／2／2 | 5.6703435350209475 | 265396224 | 7通过1失败；失败保留 |
| P1 局部恢复 | 0／0／0 | 5.841137452982366 | 253300736 | 仅原失败 selector 通过 |
| P2 唯一尝试 | -15／2／2 | 842.2889896910638 | 1156853760 | 840秒工作门后 `PERFORMANCE_CONTROLLED_STOP`；不是完成空间或 PDE |
| 三次互斥合计 | 不汇总退出码 | **853.8004706790671** | 不将峰值相加 | whole求和正确；不是完整研究或人工墙钟 |

依据：[首次 closeout](outcomes/records/v11_p1_attempt1_closeout.json)、[恢复 closeout](outcomes/records/v11_p1_closeout.json)、[P2 closeout](outcomes/records/v11_p2_closeout.json) 与各自归档 summary/exit/resource 摘录。三次 task VmSwap 采样为0，所报全局换页增量0，终态记录相关后代清除。P1 小型资源流在 Git 内可直接读；P2 的1148条完整流在 ignored 原件，本审阅只核提交的关键行、汇总和引用的一致性，**没有亲自逐条重算其全流峰值或清理观察** 。RSS/VmSwap 均为采样量，PSS未启用；空 cache stamp 不是实际 JIT/global cache 稳定证明。

P2 阶段 marker 从 `2946609.154686336` 到停止 `2947432.850145779`，差约823.695459443秒；最后活进程样本约840.600秒。whole842.289包含停止后清理，没有获准延长工作。Git 摘录有19个 affinity getter 返回 `[1]`、两条来自 watchdog PID 的 SIGTERM及终止尾，未显示非CPU1 setter；这不能将未读全 trace 写成独立全量认证。

**超时归因裁决：** 能确认在 `_audit_plan` 的空间构造路径内达到工作阈值，最终 authority 未返回；可以报告“执行方记录终止栈含 Basix 插值构造”，在连续原块补齐前须注明此审阅仅看到拆分帧。即使该栈绑定补齐，仍不能判定823.7秒全部耗于同一函数。采样间隔也不等于指定0.25秒：按提交计数与窗口推导平均约0.734秒；worker、tracer、watchdog共享CPU的实际成本需要测量，不能直接归因监督器。

P0 静态检查、未计时编辑、失败读取／git辅助命令与上述运行成本分列；不把内层 pytest、阶段计时再次加到 whole。没有发现提交材料中隐藏额外 dispatch 的证据，但未访问工作站全局运行历史，不能以此证明不存在任何未记录命令。

## 5. 科学意义与未完成事项

| 能力 | 本次正式裁决 | 原因 |
|---|---|---|
| 空间 | `PARTIAL` | 有固定 seed8 计划构造，最终实际空间、约束和 FE 未返回；旧有限 local h／mixed-p 资格边界不变 |
| 选择 | `PARTIAL` | accepted9/R9 与 R10拒绝保留；本轮固定动作不是新自适应选择更新，没有第10次接受 |
| 精度 | `NOT_PASSED` | A1 q响应、旧 A2 保存数据复核及三场共同比较均未产生新完整结果；历史独立精度失败保留 |
| 同精度全过程成本 | `NOT_ESTABLISHED` | 本轮仅支持费用，无同精度端点；失败、参考、恢复、监督成本不能删除或拼成加速比 |
| 迭代 | `NOT_RUN / NOT_QUALIFIED` | 未执行，也不因支持整改解锁 |

P2 超时发生在 PDE 之前，既不能证明 seed8 无收益，也不能证明 h/p 不适用。低 RSS 不等于构造成本可接受；expected194叶也不能给出实际 FE通过。必须取得实际 independent trace＋interior、Floquet从属、carrier与凝聚 rows 的分账，且 `110472 < FE_h < 237600`；端口612行与 carrier存储不能反代 FE。

对未运行 P5 的静态审查确认：共同分区、Y6_1→R9／h方向、q8/q10、完整612模式、总／散射场固定 floor、无 phase fit、固定 epsilon_J/G、正 Delta_FE 与分类冲突处理的总体设计符合任务。相应运行和数据绑定仍待修复验证。一次固定 seed 的正响应只能回答该动作的输出收益及自由度代价；不能直接证明独立精度或普遍自适应选择成功，也不能据同空间 q稳定性宣布空间精度通过。

## 6. 哪些证据复用，哪些必须重新验证

| 对象 | 允许复用 | 新增必需验证 |
|---|---|---|
| 历史科学负结果与 V10 关闭项 | 原样保留；不再重做 V10 ELF／派生关联归档、不重做 D3 20项 | 仅核本次实际消费输入仍匹配冻结身份 |
| P1 七个未变测试及局部恢复 | 按原字节、原 selector 和原断言范围引用 | 新改实际路径必须按第9节 S1 验证；不得累计为最终完整绿套 |
| seed8计划 | 固定几何、parent、degree和预声明动作；提交计划可作身份基准 | 真实闭包门、所有叶继承、最终实际authority和FE；不能复用 expected forest 当空间结果 |
| P1 父链／清理观察 | 已观察的启动组织作为复用设计依据 | 后续各worker实测父PID/start_ticks/TracerPid、ABI、CPU、资源、终态 |
| 旧 A2 原数组 | 只读、身份匹配时复算保存数据；不另解、不重积分或新采样 | 真正到达并保存 raw范数、612及q8/q10比较；旧端点仍不合格 |
| P3–P5未执行代码 | 保留明确 opt-in研究实现 | V11-03～06真实路径fixture、随后经授权的实际端点及joined核门 |
| 性能／缓存 | 旧成本分账作为历史观察 | D1取得阶段／调用／CPU分解；不由一个停止栈或温缓存次数推出时长 |

## 7. 依赖组与合并资格

| 分组 | 本次评价 | 依赖、阻塞与合并裁决 |
|---|---|---|
| 文档／轻量证据 | 具有研究档案保留与独立审阅价值；需V11-08小勘误 | 保留失败和可见性；**没有实际 merge approval** ，本次仅提交本报告 |
| V11 test-only | 部分历史测试有用，新分支覆盖不足 | 依赖四个研究入口及既有数值环境；新增真实路径fixture通过前不称完整资格 |
| `candidate_checkpoints.py` | 原子单文件保存、身份记录可复用设计 | 依赖真实observer调用顺序及reader联合绑定；组件正确不等于新端点合格，不单独升级生产 |
| `h100_anchor.py`、`round1_candidates.py`、`compare_round1_candidate.py` | 仅保留为研究代码 | V11-01～07阻塞；最小修复后可按第9节执行，仍无生产默认资格 |
| 共享启动／watchdog | 本轮未改共享实现；已有实测只覆盖指定组织与窗口 | 不将研究shell作为通用启动默认，不扩大ABI／全仓CI资格 |
| 原 manifest A–D 数值核心及依赖组 | 本轮没有新核心字节或新增数值资格 | 原依赖闭包、历史overlay／ABI／完整数值验收限制继续有效；不能用本轮fixture替代 |
| 整分支 | 不具备整体生产合并资格 | 不执行merge；未来仍需明确按组review approval和用户授权，由Codex执行 |

下一轮限制在四个研究 Python 文件、现有 V11 测试、薄launch、一个执行恢复manifest和结果文档。不得借上述问题重写数值核心、复制第二套比较算法或大范围抽象重构。

## 8. 当前交付验收与责任

本轮正确做到了：保留 P1 失败与局部恢复身份、P2达到阈值后停止、未启动后续正式模型、没有把计划计数写成 actual FE、没有用 scalar PASS 代替缺失科学结果。停止发生后没有自动借用正式余额；这一点接受。

不充分之处也必须记入下一份回应：闭包测试没有穿过真实构造及后置门，静态未定义名和primary键顺序未检出，P5关键真实入口未受测。主控批准P2时的测试覆盖判断不足；V11-01／03未在P2现场触发，不追溯写成已发生故障。审阅补发现这些缺陷，不构成否定全部历史支持观察，也不应再只做一轮归档。

**本轮结束状态是“有限工程进展、空间准备资源停止、科学链尚未执行”。下一轮立即按第9节推进；完成整条授权链或触发明确硬停止后再交付，不为普通局部修复、文档更正或每个成功阶段另等审阅。**

## 9. 下一轮唯一执行授权：V12有限修复与V11科学链恢复

### 9.1 授权目标、文件范围及不变项

**批准执行。** 目标是取得可用的实际空间前门，再完成原定 q响应与 seed8真实小h实验；不是重新开启V10归档，也不是直接绕过前门启动PDE。

首先修复V11-01～06并实现V11-07的轻量观察／及时留证。允许修改仅限：

- `benchmarks/task43_hp_adaptivity/{round1_candidates.py,h100_anchor.py,compare_round1_candidate.py,candidate_checkpoints.py}`；已有逻辑能复用时不另写并行实现。
- `src/test/test_task43_v11_scientific_restart.py`；只新增或修改与本报告风险直接对应的fixture。
- Task43新回应／新记录、当前导航／summary／manifest／模型总账／进展，及下述ignored薄launch和源码输入快照。

不改 `src/adaptivity/`、`src/solvers/` 数学代码、共享activation、ABI、watchdog默认策略、native profile或旧合同。无新p候选、第二seed、level2、R14、extra correction、参数盲扫、缓存清除／预热campaign、环境重建。原A1_R、A2_R、其他B/C模型、fresh baseline、成本campaign、迭代、0.7nm、NN/FTT及合并继续锁定。这里仅续接V11已指定的R9_H8，不解锁一般B组扫描。

普通静态路径／lint／JSON／文档错误可就地修复；记录实际做过的检查，不为它们消耗新driver或补造耗时。旧P1恢复trace与P2连续停止栈从已有原件补摘录即可。

### 9.2 前瞻执行绑定：旧合同不改，新路径不冒充旧失败

保留原合同文件及其SHA `6aadbf82a9c816e1e272b087aa2189435bb0163df1ed1b55a363295a773dadf1`。新增唯一小型 `outcomes/records/v12_execution_recovery_manifest.json`，绑定本review完整提交、原合同SHA、修复源码身份、下表四个支持root／预算、两个允许的P2产物路径；它只实现本节执行绑定，不具有自行授权或改阈值的能力。

在首次支持启动前冻结manifest和实现；各launch再记录实际HEAD及文件SHA，保持合同／manifest与实际源码身份分开，不制造“提交包含自身SHA”的循环。manifest中的源码是初始冻结身份；本节允许的后续局部修复以新的不可变launch快照记录实际source、相对初始字节的允许范围diff和受影响测试，不回写旧manifest或伪称同字节。允许通过一个显式 `--execution-recovery-manifest` 参数，在现有V11 opt-in入口共用一个小resolver读取该manifest。**原 `_load_v11_primary_contract` 仍返回原合同及原SHA；不得修改其内存物理／路径内容后仍称原合同字节。** resolver另行返回有效P2路径和recovery manifest SHA，不接受任意路径、数值或容差覆盖。

需要覆盖的路径校验点为 `round1_candidates.py:1571–1585,1657`、`h100_anchor.py:2434–2441,2944`、`compare_round1_candidate.py:320,1615`。D1或P2R中哪一次取得完整实际P2，由主控在其终态及P4 launch manifest中显式绑定实际plan/audit/原数组结果SHA；P5沿用P4保存的绑定。只允许下表D1、P2R两个目录，禁止扫目录挑“最新／第一个成功”，禁止复制完成标记到旧失败root。D1若完整通过，直接用其产物，不为改目录名重跑。

primary、terminal、P5 joined记录同时保留base contract SHA、recovery manifest SHA和实际来源。新增绑定须由S1覆盖：未知root、改阈值、错合同／错review、产物未完成及错plan全部拒绝。正式P3/P4/P5的模型、root和次数不变。

### 9.3 唯一命令、额度与资源

canonical仍为 `/home/fenics/Projects/NN-Lab-V2`。新增支持前缀唯一为 `/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v11_science/recovery_v12/`。表中支持root和脚本相对此前缀；启动命令严格为 `bash <此前缀>/launch/<所列文件>`。薄shell完整argv须在dispatch前写入该次不可变launch manifest；恢复manifest事前声明唯一命令形状及P4的两个P2路径变体，实际选定项在P4 launch中绑定，不补改冻结manifest。不得从聊天另取平行指令、更换编号或删除失败目录。

| 槽位 | 唯一root | 唯一launch文件 | 次数上限 | 工作停止／whole含清理，s | 树RSS上限 |
|---|---|---|---:|---:|---|
| S1定向主验证 | `support/focused_attempt1/` | `focused_attempt1.sh` | 1 | 270／300 | 8GiB与原动态门取严 |
| S1局部恢复 | `support/focused_recovery1/` | `focused_recovery1.sh` | 1，条件使用 | 270／300 | 同上 |
| D1实际authority诊断 | `support/authority_profile_attempt1/` | `authority_profile_attempt1.sh` | 1 | 540／600 | 同上 |
| P2R有依据的恢复 | `support/space_and_saved_primary_attempt2/` | `space_and_saved_primary_attempt2.sh` | 1，条件使用 | 1740／1800 | 同上 |

**上述为新授权，最多4次支持launch、whole最多3000秒；不是恢复已耗尽的旧P1/P2额度。** D1只诊断与空间／旧数组工作，P2R同样不装PDE矩阵、不factor、不solve。调用唯一launch即消耗其槽，包括watchdog前失败；剩余秒数不换次数。D1已完整完成P2则P2R不调用，剩余额度作废，不改作其他目的。

延续原未消耗槽如下，前缀仍为原 `…/v11_science/`；命令仍为其 `launch/` 下同名shell，只允许增加上述绑定参数和实际新P2输入身份，不改科学设置：

| 阶段 | 唯一root／launch文件 | 剩余次数 | 工作／whole，s | 树RSS上限 |
|---|---|---:|---:|---|
| P3 A1_q3 | `formal/A1_q_attempt3/`／`A1_q_attempt3.sh` | 1 | 6900／7200 | 32GiB与原动态门取严 |
| P4 R9_H8 | `formal/R9_H8_attempt1/`／`R9_H8_attempt1.sh` | 1 | 6900／7200 | 同上 |
| P5共同点比较 | `support/union_comparison_attempt1/`／`union_comparison_attempt1.sh` | 1，支持 | 1740／1800 | 8GiB与原动态门取严 |

历史正式5/6、原末槽封存不变；扩展包络当前5/8。执行P3/P4最多再用2个原V11槽，到7/8；本review新增正式PDE额度为0。下一轮新支持上限3000秒加原未用P5的1800秒，合计最多4800秒支持；原两次正式whole上限仍14400秒。所有最大允许后续whole合计19200秒，**历史853.8004706790671秒另保留** ，不是人工总wall或加速证据。

每次继续采用原activation，仅worker内 `HWLOC_COMPONENTS=-x86`、`OMPI_MCA_pml=ob1`；CPU1、MPI1、六线程变量1，complex128/int64和MUMPS前置实测。只用已验证组织 `exec taskset -c 1 strace -D -ff -ttt -k -e trace=sched_setaffinity,sched_getaffinity … python -u …`，保持watchdog直接父链。支持node cap为8589934592B，正式为34359738368B，原reserve／available／动态包络取更严者。task-tree VmSwap必须0；global换页另报，不把全局变化自动归因本任务。

任何非CPU1成功setter、活worker非CPU1采样、未解释setter、父链／tracer替换、资源超限或原件身份漂移立即停止受影响链。停止只针对已绑定PID；工作阈值之后仅TERM/KILL/reap和保存已得记录，不继续计算。whole超限、退出码未知、相关worker／tracer后代未清除都不能合格。一次只运行一个本任务workflow，不干扰其他任务。

### 9.4 S1：把测试用在真实风险上

全部已知修复、观察插桩与manifest接线先完成静态审查、提交／冻结，再一次定向执行以下实际路径；selector名称由实现登记，禁止用选择整个测试目录扩大范围：

1. 真实计划builder及真实audit后置门：合法非空闭包、全叶继承；额外requested seed/root、错误p和FE边界拒绝，必要forced closure允许且逐项核对，并含旧无V11 seed调用。
2. 真实observer：两phase的primary身份及保存顺序、normal一次／extra零、raw门失败、q10失败保留证据。
3. 真实磁盘联合读取与raw恒等关系：V11-04各混包反例即使外层hash重绑仍拒绝。
4. 真实P5合成主路径：不同axes共同点、六次采样、参考方向／612／固定分类、q10／输入漂移／末态故障与joined拒绝。
5. 新恢复manifest的白名单、原合同语义及实际路径绑定；保留真实main到mesh前sentinel，核本次direct parent／tracer与未执行mesh。

只替换昂贵依赖边界，不mock受验函数或预设它的PASS。先运行必要静态未定义名字／语法检查；不跑全仓pytest、collect-only、完整p6 witness、旧D3二十项或独立ABI探针。ABI和CPU门在同一受监控worker内完成。

S1第二槽只用于已定位fixture／接线／留证错误的受影响节点，保留首次失败和两次字节；若第一次已通过，不为“最终同字节整套”再跑。它也可保留给D1揭示的纯观察接线小修复，但仅限D1正常结束或单纯到时、未触发下一节身份／资源／trace／写入／清理硬失败的情形；仍仅跑受影响节点，不允许数值算法／缓存优化。触发这些硬失败后只允许静态修复与交付，不借剩余S1槽再次启动。若没有剩余验证槽却需要改变受测实现，不启动P2R／正式模型；交付确切改动和未验证范围。D1自身不可补跑。

### 9.5 D1：先得到可解释观察，再决定是否花恢复额度

S1必要节点通过后，调用D1一次。使用与原P2相同的固定seed8、parent和数值空间，先完成并原子保存旧A2保存数组复算，再进入实际空间authority。旧A2原件缺失、身份冲突或原q门超限即停止，不另解A2。各phase已有结果即时保存；标明未完成authority，不能抢写FE通过。

诊断允许在现有runner中以薄wrapper／计时记录调用原函数，返回原结果；不替换数学实现。至少记录：

- plan／mesh、broken trace、实际degree／reference space、插值或restriction、实体及cell约束、FE核验的BEGIN／END与单调时钟；未返回调用明确 `IN_PROGRESS_AT_STOP`。
- 原函数实际参数、已有cache key、独特工作量与重复次数、原cache hit/miss信息；区分首次构造和同进程复用，不造新的数值缓存。
- worker／tracer／watchdog的PID/start_ticks和阶段CPU秒，实际资源采样间隔；区分数值计算与监督消耗，不无证据移除追踪或改采样频率。
- 已完成和剩余工作，部分可读产物及SHA；原异常、退出、全部affinity事件、停止尾和清理。

540秒工作阈值到达即停止。**本节明确将“诊断到时、有序停止、观测完整”授权为可用于评估P2R的诊断结果** ，不机械套用旧“一次支持非零即永久阻断整包”；它本身仍不是P2通过。身份、数值门、CPU/RSS/swap、trace、写入或清理异常不享受该例外，禁止后续动态工作。

若D1在额度内完成全部实际空间、FE、旧A2数组门，且退出零、输入／源码／资源／清理完整，由主控读原件核实后直接作为P2前门；不再跑P2R。否则只有同时满足以下条件才可调用P2R一次：实际工作量和阶段／调用耗时足以解释慢段；剩余主要类别有已测依据，未返回的慢调用不能按0秒或一次温缓存速度估算；包含冷启动、全部必要闭包／验证、持久化、监督成本的保守估计支持1740秒内结束，并明确余量与不确定性。不能只因“原840翻倍”、RSS低或终止栈有Basix就放行。

没有这种依据就不启动P2R，提交阶段实值、主要未完成工作和需要改变的具体实现问题，不能只写“原因未知，申请再跑”。不要求精确预知总耗时，不要求重建环境。D1后只允许本节明示的小型接线／留证修复及相应S1局部验证；需要改变数值算法、缓存策略或空间实现时停止并提出具体方案，不在本额度内试错。

### 9.6 P2完成后，主控直接续接P3→P4→P5

**允许按顺序连续执行，不再另等一轮授权。** 但主控必须亲读阶段原件与实值，不能只看子代理summary或PASS：

| 放行点 | 必须核验 | 任一不满足的行动 |
|---|---|---|
| P2→P3 | 实际requested／forced闭包和全叶p；实际空间trace/interior/FE及由其推导的矩阵rows预算，已装配rows/NNZ留正式运行实测；`110472 < FE_h < 237600`；旧A2保存数据q8/q10全门；原R9与本次数值核变化仅属允许观察接线；source/input、ABI、CPU、资源和终态完整 | 不启动A1凑次数，不换seed，不用expected值放行 |
| P3→P4 | 固定R10空间180cells／118800FE，q19/q32/R13；完整primary原数组／A6／normal计数、612与Av、q8/q10；旧R10→新A1每个原冻结q门通过；退出／资源／清理零缺口 | A1不重试，不extra，不以一阶采样通过替代另一阶 |
| P4→P5 | 固定R9_H8，q15/q28/R13；装配前实际空间与选定P2逐项一致；完整primary、raw恒等关系、独立A6和物理门；`SOLVED_PENDING_POSTPROCESS`与零退出／身份／资源／清理完整 | h不重解，不另选动作；pending不能冒充完整诊断 |
| P5→完整诊断 | 三场共同q8/q10均完整，完整612与总／散射指标；实际输入前后不变；分类冲突按冻结规则报告；P4/P5联合终态、退出、资源、清理与所有原件绑定 | 数据、身份或资源门失败则未资格化；仅q8/q10分类不同则数据完备但科学响应未解决。保留primary和已存q8，不额外采样或重试 |

保持原共同硬门：独立A6≤1e-8、full-active≤1e-8、condensed≤1e-9、normal一次且同RHS／正收敛原因／严格下降、extra零、体吸收能量闭合≤1e-5。数值核心已有更严格门则继续遵守，不能为本报告放宽。A1与旧A2的aggregate／单通道／归一场q门仍为原1e-6／1e-7／1e-5；q8与q10均须完整。P5 epsilon_J=`0.12716416232413652`、epsilon_G=`9.088158796603444e-6`不改。

P5报告同一Y6目标下新算的R9和h的J、eta、全部输出、Delta_FE及单位新增FE收益，按原三类响应及采样冲突规则判别；不写第10次selection transition，不改accepted9，不将Y6当已证明的连续真解或独立holdout通过。无论正、负或无明显收益，都完成这一固定实验的报告，不再盲扫参数。

### 9.7 必须持久化的证据与本轮收口

每次launch前保存完整shell/argv/env、真实HEAD、源文件与输入hash、合同和recovery manifest；保存worker/watchdog/launcher退出、PID/PPID/start_ticks/TracerPid、逐事件affinity、资源流、阶段BEGIN/END、末态和清理。FE审计、旧A2算术结果、primary原向量／系数／normal、q8、q10、modal和比较每完成一项即保存；后续失败不得丢掉已完成项，单文件原子写不宣称多文件事务。

主控joined记录在watchdog退出后生成，读取实际数据与退出结果；数据里的true、complete或散列不能单独放行。Git至少留足以复算关键算术与门判定的轻量实值、最差项、连续异常片段和原件索引，大原数组留ignored。费用按互斥whole计，失败、局部恢复、诊断及P2R全计入；阶段时间不重复加，未计时静态动作另列。

交付 `response_v12.md`、`outcomes/records/v12_recovery_and_scientific_results_v1.json` 及必要轻量记录，更新当前导航、summary、manifest、模型总账和进展。对应本报告V11-01～08逐项说明最终代码／测试字节、关闭依据和仍未执行范围。成功时交付完整q响应及固定h收益；硬停止时交付具体实值、剩余工作与最小技术改动需求，不再以单纯档案复核替代科学推进。

## 10. 最终审阅声明

本报告对固定提交给出有限工程审阅和明确的后续执行授权，没有完成或声称完成工作站原件重算。当前五项科学状态不变。既有D3／历史测试、旧P2资源停止和本次静态修复要求分别保留，不合并为一个PASS。

本次提交内容仅为本文件。正式review完整提交SHA由Git提交产生后在交付消息中提供，不在文件内制造自引用SHA。Codex接收本报告后应执行第9节，不把“等待新任务”作为本次收口动作；也不得越过其中具体前门、次数与停止条件。

[src-round]: https://github.com/Rookie1234567/MyFEniCS/blob/6755cf4ace94c6d06b50c98f13489d8726de67be/benchmarks/task43_hp_adaptivity/round1_candidates.py
[src-anchor]: https://github.com/Rookie1234567/MyFEniCS/blob/6755cf4ace94c6d06b50c98f13489d8726de67be/benchmarks/task43_hp_adaptivity/h100_anchor.py
[src-compare]: https://github.com/Rookie1234567/MyFEniCS/blob/6755cf4ace94c6d06b50c98f13489d8726de67be/benchmarks/task43_hp_adaptivity/compare_round1_candidate.py
[src-test]: https://github.com/Rookie1234567/MyFEniCS/blob/6755cf4ace94c6d06b50c98f13489d8726de67be/src/test/test_task43_v11_scientific_restart.py
