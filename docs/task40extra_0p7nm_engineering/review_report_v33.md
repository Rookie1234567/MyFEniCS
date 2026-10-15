# Task40extra Review V33：继承 q4 PASS，先完成其余 sector，再贯通完整参考与原尺寸场

## 0. 决策与冻结快照

**本轮主目标是取得尚缺的六个 q 的完整矩阵与资格，并在同一获准运行中继续准确因子驻留、完整参考逆和条件原尺寸 pilot。禁止原样重放“先完整 global physical builder、后生产其余 q”的昂贵前缀；不把加日志、整理代码或全仓测试作为主要交付。**

| 项目 | 本次依据与决定 |
|---|---|
| 审阅日期 | 2026-10-15，Asia/Singapore |
| 仓库 / 分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| V32 结果 HEAD | `a8fe7b597333619c19ad3ae301c9bf96d0c381e8` |
| 最新提交 | 2026-10-15T02:04:22Z，V32 q4 native 与截止证据收口 |
| 已回应 review | V32，`e2737b4049045a1824f5a1c49bb7bfac85e6e929` |
| q4 native source | `767323bbee161a6163fec01d27c96723f52b5f97` |
| 最后正式运行 source / attempt | `9ba8f0aa2750d020533321860d653dbbc44b885f` / `20261014T121113.504617Z` |
| 裁决 | 接受 q4 COMPLETE CSR/native；接受真实受控停止与监督执行事实；完整 reference/target 未资格 |
| 当前写入范围 | 仅本 review；不改程序、旧数据、原结果或 master |

最终目标仍是 50×25×140 nm、0.7 nm、真实非可分三维 Maxwell，complex128 Nédélec H(curl)、双 Floquet、Fourier-DtN，整机十进制 2 TB 含系统余量、任务零 swap，必要完整冷流程不超过 172800 s。当前 p6、272×8×14、30464-cell 配置是原尺寸工程 pilot，最终 h/p 与 mode 精度仍需单独验收。reference 的规则结构仅用于预条件器，不能替换真实 target。

本轮是现有执行路径的有限顺序修正，不是重新设计预条件器或通用框架。用户最新要求优先：先完整计算，后系统整理；只运行受影响测试，不在启动、修复和收口时默认各跑全仓。根规则和旧 Task AGENTS 中的本机/P0描述不能覆盖后续已批准的主控工作站通道；执行者仍不得据此自行迁移或扩大权限。[R1][R5][G1][G2]

## 1. V32 的实质成果与未完成项

q4 已从 NUMERIC_COMPLETE_NATIVE_PENDING 前进到 COMPLETE_CSR_NATIVE_PASS。本次接受依据是逐 q compact 内的原 native 收据、四作用误差、分量重组、双向配对泄漏、保存向量索引及最后运行的只读消费记录；不是仅凭文件 hash 或顶层 PASS 字符串。本 Chat 未登录工作站、重读大数组或重算数值。下次按旧资格严格导入，不要求重做四次 native。[R1][R2]

| q4 指标 | 已记录值 |
|---|---:|
| 形状 / 全结构槽 | 777424×777424 / 581086528 |
| 纯 CSR 载荷 | 11624840260 B |
| 四次完整作用的最大相对误差 | 2.6835748652861403e-14，门限 1e-11 |
| 分量重组相对误差 | 2.304769489707805e-14 |
| q0→q4 / q4→q0 scaled leakage | 2.646436357798361e-16 / 2.5936531846871953e-16 |
| COMPLETE manifest SHA256 | `c7c5a627c9685849d4bca109b030b6dd853f6b64ff3d719048b89278bddf8868` |
| native qualification SHA256 | `9d4ccd8f1b4b8b0119d4b62fc1c2fea3849e8cf80a6e4442bfd8016248778892` |

原始 native 向量根为 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_767323bbee161a6163fec01d27c96723f52b5f97/factor_bank/selected_q/q4_twist0/`；精确 manifest、数组与资格文件路径以现有 selector 和 [R2] 的原收据为准，不根据文件名猜新路径。V31 数值数组与其来源继续只读。小型收口副本不是全部大文件已经转移的证明。

q0、q4 合计已有 **2/8 份完整 CSR/native 资格**；这不等于新增两份，也不等于八 q 的25%总工作量。V29只证明过 q0 的分解生命周期，因子早已销毁；本轮没有新的 live factor bank。其余六 q、六类完整参考检查、原尺寸 KSP、official E/H/R/T/A 和完整冷账均未闭合。旧 target-volume 等已接受证据不因本轮截止失效。[R1][R2][R7]

### 1.1 时间、资源和停止原因

| 量 | 记录值与口径 |
|---|---|
| 最后一次 twist0 owner/reuse/handoff 父段 | 2064.048938861 s，约34.40 min；不冒充首次 q4 native 总成本 |
| global_reference_builder 开始至 SIGTERM | 46863.032342846 s，约13.0175 h；未完成的外层阶段跨度，内部归因 UNKNOWN |
| run_case / watchdog 父段 | 49072.819633 / 49072.059610 s，相互嵌套，不相加 |
| 含 required checker 等相邻父段合计 | 49077.043639834614 s，约13.63 h；不是整个 campaign 或完整冷流程 |
| required checker 父段 | 2.896090 s，已包含于上述合计 |
| 同时 tree RSS / job cgroup 峰 | 50996031488 / 33537933312 B；保留两个口径，不相加、不用差额猜对象 |
| task swap / PSS | 0 B / null；宿主 swap-in +82页、swap-out +0页只是全局诊断 |
| 末次已落账 / 后续只读投影累计 | 85235.54772132506 / 85793.12263780605 s；不能再叠加运行子时间 |

T0=2026-10-14T02:08:33.255938807Z；数值截止=2026-10-15T01:48:33.255938807Z；总截止=02:08:33.255938807Z，均已过去。TERM 后30秒KILL、后代清场，分类保持 PERFORMANCE_CONTROLLED_STOP，不改称内存失败、factor失败或不收敛。[R1][R3][R4]

本轮 required checker 已真实经过监督链，输出 NO_PARTIAL_FOOTER；监督执行事实与科学/收口结果通过是两回事。保留该负结果，不为补 footer 重跑 PDE；不重新把已修复的旧监督入口当成待开发项目。已完成 q4 产品由独立收据成立。[R4][R5]

## 2. 当前阻塞的源码依据与最小修复

### 2.1 确定的是依赖顺序，不是尚未测出的热点

`build_task40_v10_p6_reference_inverse` 在任何剩余 sector 生产之前，依次创建 global levels、完整 `build_same_mesh_physical_action(... verify_dtn_quadrature=True)`、global entities/layout、global H，随后才遍历 contexts 并调用 missing-q preparer。完整 physical factory 又先创建 surface assemblers、gauge context、全模式 carrier，再建立 volume action。[C1][C2]

这证明其余 q 被完整全局准备前置阻挡。日志没有内部边界，不能证明13小时全部属于 JIT、carrier 或哪一次 hash。低于 cap 也不能证明所有未来对象可容纳。

**本轮选择：在现有 builder 内将 sector 数据生产移到完整 global physical 构建之前；迟建真正只被全局参考检查/传输消费的对象。** 加日志与这个有限控制流改动一起实施，不再单独启动一遍原样13小时流程“先看热点”。

### 2.2 sector 先生产的准确边界

在现有入口内，先从冻结的模式表、profile、轴坐标和 regular cfg 计算真实 contexts/global H。V31 已在 twist0预构建中使用 `assembly_projection_denominator(..., BOUNDARY_PLANE)` 做过这种拆分，应复用同一数值定义并在 global carrier 实际建立后核对 H/模式身份。[C3]

每个 sector 的局部 FE/MPC、local volume/recovery、q maps、端口模式和两份矩阵使用真实本 sector 数据。`TwoCellNativeTransport` 依赖 global entities，但 local native 与 sector CSR 不应因此依赖完整 global carrier；把 transport 构造延后到 global entities 可用时。全局身份暂由明确的 frozen-mode/H descriptor提供，不能伪造带 physical_action 的全局 bundle，更不能提前标 global Gate通过。

现有 prebuilt owner 接口只允许 twist0，需窄扩展为实际 profile 的0、1、2、3，并校验 context、tau/eta、axes、mode/H、map、同一 transform bank与唯一清理责任。不得据此跨 twist复用不相同的端口/矩阵或复制q0。局部 owner 在同一服务内留给后续参考逆；跨进程只复用真实保存数组/收据，不能声称 Python/PETSc owner仍live。[C1]

### 2.3 预先关闭必经循环中的遗留变量，避免算完再报错

冻结源码的 sector 循环在移入 local-owner helper 后，仍出现 `trace=trace`、`list(actual_inventory)` 和 `del compiled`；这些值的构建已在 helper 内，而该 builder 的当前循环未从 pending_sector重新绑定它们。应取 `pending_sector['trace']`、从真实 condensed 对象派生 inventory，并去掉本作用域不持有的 compiled 清理。不要用空占位值蒙混。[C1]

这是静态查到的后续执行风险，不是本次13小时停止的已证实原因。一个真实 sector callback→结果合并→事件→清理的小型集成测试应覆盖它，不能只测 callback helper返回值。昂贵FE/factor可以替身化，被修改的调度和字段传递不能全被mock掉。

### 2.4 迟建不等于消除成本：global 和 local 同时获得可测进度

在下一次必要运行中，于实际函数边界记录 mesh/space/MPC、surface form/JIT、carrier逐side/mode进度、volume form、凝聚class/cell、map、pattern、fill/native及释放。使用现有 event/runtime能力；每个长循环按固定节流间隔报告 completed/total和CPU/内存/I/O已有观测。长原生调用无回调时写清当前调用和存活状态，不能虚报完成比例。

优先复用当前已经证明适用的保存原始B/D/H和紧凑模式生成路径；新twist没有合格donor时正常生产一次。不得把旧cached factory换个名字就称为有界，也不能从saved-only字样推定全部carrier/JIT已省去。若新计时暴露明确热点，在同一范围修复重复生成/逐行Python操作或重复准备，保留原phase、积分、两级筛选和B/D定义。不得降 quadrature、删模式、临时换PC/ABI/线程来制造提速。

q1/q5必须先产出可保存的完整成果；全局剩余必要工作随后继续，并按实测成本更新48小时账。若全局工作仍过慢，报告明确调用、进度、限速项及已保全的六q，不得再仅交global STARTED和一个UNKNOWN。

## 3. 连续执行顺序与不变的数值门

| 步骤 | 交付及放行条件 |
|---|---|
| P0：窄接线 | sectors-first、既有q0/q4严格导入、上述循环变量、同一owner交接及实际服务参数通过定向集成；不做全仓整理 |
| P1：第一对新sector | twist1的真实共同生产，q1、q5各自pattern/数值/native；完成即原子保存，不等global/reference结束 |
| P2：剩余两对 | 按(q2,q6)、(q3,q7)连续生产；已有COMPLETE严格加载、pending只补缺失验证；不重跑q0/q4 |
| P3：global/reference组装 | 必要global FE/layout/physical action与传输建立一次，核验实际全局mode/H及所有sector身份，保留局部owner |
| P4：ALL_Q_RESIDENT | 八q CSR/native齐全；所有symbolic完成后按真实INFOG和完整共驻账准入numeric；各q两组非零RHS真残差≤1e-10，合格因子留存 |
| P5：完整参考与target | 同一live owner做原六类全空间检查，strict与原V15 PC状态分别报告；PC准入及target资源/时间门成立，立即进入原尺寸工程pilot |
| P6：监督收口 | 原始成果、事件、完整父账、checkpoint、required checker和清理；缺footer仍负，不丢弃已验收产品 |

新六q仍须四次完整 CSR/native、分量与重组和适用pair leakage，原门≤1e-11；真实复twist和H不可省略。原已资格q0/q4无需重积分或重做native；当前新加载仍核验源数据与数学身份，单纯新source/window不撤销旧资格。reference与target不相同，reference中的block diagonal性质不得用来删除target的真实q耦合。

ALL_Q优先复用现有 `AllQExactMumps`。V29因子已销毁，本次live bank正常新建q0；q4从未有factor PASS，不能标成旧因子复用。各q完成两RHS后不先evict再为reference重建；真实numeric-live集合与后续numeric计数必须证明驻留。全bank无法准入则保存实际symbolic/缺口，不改cap，不临时退回单槽循环并冒称全驻留通过。

完整reference六类RHS与原strict/V15分账沿V32合同，不另加一套更严格的运行前门。全target独立A6与释放后残差≤1e-6，能量/吸收绝对闭合≤1e-5，沿原每8步A6、每32步checkpoint、完整E/H/衍射/R/T/A/A_volume输出。求解后的物理验收不能循环成为首次pilot运行前提。最终网格/mode精度尚未通过，本包不加精度或PC参数扫描。[R8]

## 4. 已完成资格的接续与防重复

用V32已经成立的COMPLETE provider和cross-window consumer机制同时登记q0/q4。q4新COMPLETE与native的上述两份hash是起点；只读加载旧manifest/数组/保存输出按现有映射，不把本机小型收口副本当原运行路径。consumer source/window单列，旧contribution/numeric/native身份不重署。

新sector逐q保存原始贡献/必要恢复信息、完整pattern、NUMERIC_COMPLETE_NATIVE_PENDING、native向量与COMPLETE selector entry。复用现有持久化格式；半数值+=无可靠游标时，按已有精确清零语义恢复，不伪造数值完成。资格已经写出后，后续global/factor/checker失败不能撤销它。

不先重建一个完整twist0 owner才能启动twist1。q0/q4的大CSR可按需求受控加载，旧局部恢复owner若已随进程结束消失，需要时新建并计费；只读复用旧数组不等于owner或factor仍存活。

同一q失败后保留原attempt，定向修复并补缺失步骤。实际独立性、材料、模式、映射或数值门失败只停止依赖阶段；不以“普通bug可继续”为由放宽数值门。新的全局reference不能通过“由同一q矩阵重组再与自己比较”冒充独立全空间资格。

## 5. 资源、24小时新窗与48小时目标

沿用已指定工作站 `fenics-ws:/home/fenics/Projects/laptop_share`，task cap=1649267441664 B，host reserve=68719476736 B，task swap=0，原complex128/int32、MPI1、数学线程1和exact MUMPS；一次一个heavy。现有执行者仍按主控已批准通道工作，本review不扩大个人SSH权限或改变目录/其他任务。

**V32窗口已结束。建议一次新的24小时固定执行窗，总86400 s、数值85200 s、收口1200 s；本报告不是已取得的运行批准。** P0先准备，主控取得本轮真实一次批准后，在第一项必要部署/激活/ABI/读取前冻结T0。已有本轮明确批准不重复询问；未批准只交可运行准备。修复/重启不刷新T0，不自动续窗。24h是工作包限额，不承诺全部完成，也不改变最终48h标准。

保持一个正式 `run_case`/service链，沿V32已经可用的合同加载、数据格式、监督和same-window resume实现，用有边界的配置登记新review/window。**不因V33这个编号复制新的大runner、solver、schema或全套contract模块。** 若既有常量拒绝新窗口，只对review元数据/许可值做最小显式参数化及一项真实参数传播测试，旧历史合同原样可查，资源/身份拒绝语义不删除。生成器输出实际可执行命令；不能在交接中虚构当前CLI没有的开关。

完整共驻账覆盖各q CSR唯一backing、PETSc输入/转换副本、全部因子和symbolic/numeric工作区、两方FE/MPC/实体映射、local LU/Schur/recovery、B/D/H/carrier/cache、transform bank、Krylov与临时向量、JIT/compiler、恢复/输出/checker和系统余量。相同backing只计一次，同时存活对象累加，确实互斥的工作区才取max。reference-only、target-build、target-ready分别准入；未知target不阻止已具完整账的reference，亦不能视作0放行target。

RSS与cgroup的V32峰值不同，保留原scope和shared-page语义，不通过二者差额推断某一owner。下一次正常资源采样核对成员与祖先cgroup即可，不为该诊断追加大计算或修改PSS策略。

48h账要包含必要首次网格/JIT/端口/各q构建、全bank、target算子、全部PC/Krylov、恢复输出与checker；warm continuation不等于冷流程。13.0175h是未完成global跨度，不能直接乘sector数；q0 factor×8也只是情景。实际以global/sector父段、T_bank、排他各q构建、真实PC与A6调用次数计费，父子不重复相加。失败开发费用保留在工程账，不伪装成必要单场算法成本；历史冷账缺项继续UNKNOWN。

必须优先测完整PC中因子复用，而不是追求小例外层步数。只有实际八q因子和全部owner同时存在，且后续PC不增加numeric次数，才能称全驻留收益成立。无法证明2TB共驻或48h时报告具体最大owner/阶段和可行改动，不以最新review版本数代替进展。

## 6. 测试与运行纪律：直接服务本次计算

不进行全仓pytest、旧小模型全场、目录重命名、旧分支合并或全局框架整理。只做修改点的失败回归和一条小型集成调用链：真实调度、selector/load/native-preparer和sector结束事件不mock；昂贵FE/factor可以替身化。覆盖q0/q4 require-existing不调用producer/native/fill、twist1→twist2的实际字段与owner交接、global physical在sector产品之后调用、异常清理、既有监督checker仍能执行。公共数值核心真有变化时补直接受影响的数值验证，不以这个原则跳过科学验收。

代码冻结后尽快进入首个真实新sector；不要测试开始/修复/收口各自再跑全仓。相同昂贵资格与输入无关改动不重复。只记录少量必要阶段与节流进度，避免逐标量日志或重复大文件扫描成为新热点。

现有required checker真实监督路径在V32已执行，继续复用。NO_PARTIAL_FOOTER是未完成运行的负结果，不再单开checker重写任务。只在真实产品完成时用已有阶段收据/索引落盘；TERM/KILL之后controller可引用已存在产物，但不能替worker伪造footer。旧失败和历史缺项不改写。

## 7. 交付、提交与下一步判据

源码改动集中在现有reference builder/直接调用者及最小相关测试；主控冻结、提交、部署，执行者按既有分工运行，不热改科学source。普通bug同窗最小修复后继续，真实安全或截止门停止受影响工作。无新增cap、ABI、排序/主元/BLR/OOC、线程或模式许可，不合并master。

`response_v33.md` 首先给真实的逐q完成表、完整reference/target状态，再给耗时与内存，最后列修复和测试。沿用既有operator/resource/reference/pilot/run_index/handoff结构；不新增平行的权威说明体系。每个新矩阵/资格/阶段有原路径/hash和下一条实际命令；没有保存数据就不能声称可从该阶段恢复。

主要验收是：q1/q5实际完整资格并继续余下两对，最终争取全部q及reference/pilot；不是增加一个有限panel或只交P0 PASS。窗口不足时给已完成q、最后内部调用、实际进度与可接续文件，不原样重复13小时未知前缀。未跑target不能称原尺寸场通过；有pilot场也不能自动称最终精度及完整冷流程达标。

发布计划：ChatGPT仅新增本review，一次同分支提交并回读；执行方先提交窄代码/必要测试，获准运行后集中发布轻量数值结果。正式大数组留ignored artifacts，负结果保留。本Chat读取远程固定源码和轻量证据，做算术与文档静态检查；没有运行项目pytest、工作站任务或大数组审计。

## 8. 给现有 Codex 主控的接续文本

> 按 Review V33 继续当前 Task40extra 分支。V32 q4 COMPLETE/native已接受，最大误差2.6835748652861403e-14；q0/q4均严格复用，不重新producer/pattern/fill/native。先在现有builder内把(q1,q5)、(q2,q6)、(q3,q7)的真实sector生产提前到完整global physical/carrier之前，逐q持久化；contexts和H由冻结模式/profile定义，global transport/layout/physical在真正需要时补齐并核对身份。复用现有局部owner与CSR/native preparer，不新造预条件器或另一套runner。修正sector循环中trace/actual_inventory/compiled的作用域遗留，用一个真实调用链fixture覆盖结果合并和清理。实际长函数内部补节流阶段/进度，不能再原样执行13小时未知前缀。
>
> 不把延后global等同于省掉它：继续完成必要全局原生参考、准确因子驻留和同owner target接线。八q资格齐全且共驻账成立后直接ALL_Q_RESIDENT，每q两RHS真残差≤1e-10；六类reference按原strict/V15分列，获准则连续进入非可分原尺寸pilot，完整A6和物理门不降。只做修改相关测试，不跑无关全仓，不重构目录或重新统一所有历史版本。
>
> V32窗口已截止。沿用现有工作站、1.5TiB cap、64GiB reserve、task swap0、原ABI/MUMPS/MPI1/线程1。P0先准备；建议新86400/85200/1200秒窗口，须主控记录用户一次明确批准，不自动刷新。复用现有合同与service，用配置绑定本轮review/source/window，不复制全套V33基础设施。获准后同窗连续推进，普通bug定向修复，旧成果保留；真实门失败或截止才停止依赖阶段。交response_v33、逐q/owner/reference/target成本和可执行handoff，不以测试数、提交数代替数值进展，不合并master。

## 9. 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/docs/task40extra_0p7nm_engineering/response_v32.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/docs/task40extra_0p7nm_engineering/outcomes/records/review_v32_per_q_operator.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/docs/task40extra_0p7nm_engineering/outcomes/records/review_v32_owner_phase_audit.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/docs/task40extra_0p7nm_engineering/outcomes/records/review_v32_terminal_closeout.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/docs/task40extra_0p7nm_engineering/outcomes/records/review_v32_closeout_evidence_index.json
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/docs/task40extra_0p7nm_engineering/outcomes/summary.md
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/e2737b4049045a1824f5a1c49bb7bfac85e6e929/docs/task40extra_0p7nm_engineering/review_report_v32.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/9ba8f0aa2750d020533321860d653dbbc44b885f/src/solvers/task40_v10_p6_yorbit.py#L5575-L6400
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/9ba8f0aa2750d020533321860d653dbbc44b885f/src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py#L107-L240
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/9ba8f0aa2750d020533321860d653dbbc44b885f/src/runners/task40_v10_worker.py
[G1]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/AGENTS.md
[G2]: https://github.com/Rookie1234567/MyFEniCS/blob/a8fe7b597333619c19ad3ae301c9bf96d0c381e8/docs/repository_work_principles.md
