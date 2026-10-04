# Review V8：完成修复后的 W0 全链，复用 Task042 边界，推进真实 AUTO 内部成本

## 0. 本轮裁决

**明确批准主线一次新的 W0 续作窗口：核实旧作业终态，修通过期截止时间的传递后，直接完成完整 worker→科学 raw→独立原始张量 checker→持久读回。在固定累计预算内，依赖、表示、入口和写出错误由执行者局部修复、定向回归后继续，不因每个工程错误另开一轮报告。数学、身份、内存和 swap 门不放宽。**

| 审阅对象 | 最新远端 / 状态与决定 |
|---|---|
| 主线 | `task40extra_0p7nm_engineering`，`c0a36a3fc897ee66d07da1dc83cdecc78983a091`；[Response V7](response_v7.md)已经正式回应V7，本报告顺延V8 |
| dot | `task40extra_dot_parallel_cloud`，`077ec9c8386c976da232093779279fb9d1a93033`；本次读取未发现更新 |
| Task042 | `task42_neural_coarse_inverse`，`f3bf7942f62e725057c3ae44820bc1ca1794ee59`；读取V38/V39、消费包、独立checker及相关源码 |
| 主线修复后 W0 | **有条件 GO，授权已在本报告给出**；第2节一次新窗口及有限修复，不再另等文字批准 |
| 主线 W1 | **身份对齐/最小移交立即GO，实际FE须W0完整通过**；复用Task042已有边界，补原尺寸真实代表类、非零内部载荷、恢复与成本 |
| dot 768MiB新尝试 | **HELD，提交取消后的继续发布和运行许可须由人类单独确认**；本报告没有替它恢复许可，也不把本地测试算新FE |
| W2 | **HELD**；完整紧凑链、科学raw及独立checker通过后，才按既定小范围做完整p4-PC/p6参考逆对照 |
| 原尺寸正式求解 | **NO-GO / 未具备正式大规模运行资格**；原尺寸精度、全AUTO、全部q因子并存、完整恢复和冷流程成本尚未闭合 |

远端HEAD于2026-10-04 UTC最终复核；三条分支均仍为上表SHA。审阅日期2026-10-04 UTC。最终目标仍为 **50×25×140 nm、λ0.7 nm、完整三维并可扩展非可分缺口，整机十进制2,000,000,000,000 B、无swap、完整必要流程≤172,800 s**；冷JIT、求积、全部q分解/工作区、迭代、内部恢复、输出与独立检查均在内。

本报告基于远端文件、提交差异和本轮用户提供的最新dot回执。审阅端本地命令工具仍不能启动，没有运行新的FE/pytest，没有读取Library原始数组逐字节独立复算。dot新952文件归档及本地`aececd8`不在已发布077提交中，下面明确标为用户最新回执。只提交本报告到主线；不修改dot、Task042或master，不启动/干扰现有计算。

## 1. 真实进展与未完成边界

### 1.1 主线 W0：实际 FE 已开始，完整组件尚未结束

W0首先核对体单元和边界端口作用是否来自同一个有限元对象；随后才保存消元前原始张量、测试非零载荷下的内部恢复，并让独立程序从数组重新计算。这几个阶段不能用前一个的通过代替后一个。

| 项目 | 已发布实际证据 | 结论 |
|---|---|---|
| 实际源 / 修复源 | `4b89d7f922bda3859048d20714557ac0cf07ffc6` / `5f74e15fae6e01e4361325db162806a7319ba3f4` | 修复只规范JSON tuple/list身份表示，不改变数值门 |
| FE起点 | 2026-10-04T06:38:30.344517Z | 已达到旧10:07:14Z“进入FE”要求；无需为此再跑一个启动证明 |
| 实际模型 | p6-only、80单元4×4×5、532模式、φ5°、原生MPI1/数学线程1 | 缩小规则组件；输入文件的q4标签不代表已执行4q或p4空间 |
| same-live收据 | 8项命名门通过；2,410,188 B，SHA256 `858094d19ec9f7ea05eec85c94ecf003fa37ddbbe12cc7f1e62749de2fc6c037` | `PASS_COMPONENT_ONLY`，不能称完整C1a |
| 代表defect | C/D/H及原作用3.5931818e−14；逐模式全DoF界2.4672054e−13；五状态3.0996379e−14；物理FE RHS1.7324713e−14；非零端口方程1.8654148e−14 | 均过该same-live 1e−10门；transform ratio 3.4637922e−6≤1 |
| 失败 | tuple/list mode identity guard；06:41:46.252994Z exit1 | 实现表示错误；不是数值、内存或时间失败 |
| worker wall / 当时上限 | 196.76210885995533 / 199.49071288108826 s | 距旧06:41:49Z cutoff尚2.746386s；该窗口现已结束 |
| 同时任务树RSS / task swap | 1,408,434,176 B / 0 B；0.25s采样，PSS未采 | 不代表整机峰值或连续内核硬峰 |
| 宿主swap | 既有21,600 KiB；本次记录pswpin/out增量均0 | 不能称整机zero-swap qualified |
| 终态 | descendants_cleared=true，remaining_child_pids=[] | 发布终态已清场；续作前按PID/start_ticks核对当前无遗留 |
| 完整worker/raw/checker | 全部未到达；scientific raw member_count=0 | 不是已经导出后仅传输失败；没有完整恢复/原A6/official R/T/A |

[实际运行记录](outcomes/records/native_w0_actual_run_v1.json)与[增量账](outcomes/records/review_v7_incremental_workflow_ledger.json)是这次终态依据。36份、5,757,491 B支持文件及其fsync/readback是日志、ABI和same-live收据；不是原始张量/场数组。历史跨窗传输的自动审批拒绝另行保留，不把它与“科学raw尚未生成”混成一件事。

5f74离线list/tuple重验及 **40 passed / 10 skipped** 只证明修复的表示合同和有限测试；10项因保存数组fixture不可用而跳过。源码仍核对532项的数量、类型、顺序、完整Gauss、载荷和carrier身份，没有删掉这些数值要求；但完整worker和独立原始张量checker必须真跑后才合格。

三次worker分别2.026239892、2.090595266、196.762108860 s，**已知相互独立小计200.87894401792437 s**。6bbc shell blocker、整体准备起点与总费用仍unknown，不记零，不把4小时政策区间写成实测耗时。V6既有扣费 **5428.582333962078 s** 原样保留。

### 1.2 dot：科学 raw 保存已经前进，作用/恢复尚未完成

| 层级 | 状态 |
|---|---|
| [已发布077恢复收据](https://github.com/Rookie1234567/MyFEniCS/blob/077ec9c8386c976da232093779279fb9d1a93033/docs/task40extra_dot_parallel_cloud/outcomes/records/native_tensor_authority_recovery_20261004/historical_recovery_receipt.json) | 恢复原始native张量权威及checker源码；保留旧pyvista失败、旧方向算术字节不一致及原始资料丢失。不能把恢复提交当新FE通过 |
| 本轮用户最新实际回执 | 16类raw、29类方向张量重构及532模式子检查通过；完整C1a在512MiB导出上限受控停止 |
| 科学raw持久保存 | **952文件、942数组已完整存入Library、取回并核成员hash**；这比先前合成1.07MB传输试验更进一步 |
| 仍缺 | 完整action、任意内部/端口RHS、全部内部恢复、独立原始方程checker；已存部分数组不等于全套角色已闭合 |
| 768MiB候选 | 本地`aececd8`、122项测试通过；未发布，且提交取消后的继续许可未恢复 |
| 裁决 | 512MiB停止不是数学失败；768MiB测试不是下一次FE已运行。新窗口需单独人类确认，由dot本人执行 |

旧中断checker的UNKNOWN、丢失的旧raw和新952文件归档分别保留；不能用新归档补写旧运行的缺失结果。dot下一发布应带现有Library归档/成员manifest、实际run source/ABI、停止位置/成本，以及768MiB候选完整SHA和差异；无需重做已成功的传输试验。

## 2. 主线下一项交付：一次新窗口内完成 W0

### 2.1 先修明确的入口问题，然后直接运行

**当前c0a36a3还不能原样调用wrapper重启。**静态核对发现：

- `scripts/task40_fresh_c1/native_service_entry.sh`仍硬编码`2026-10-04T06:41:49Z`；`fresh_c1_p6_w0_dependencies.json`也绑定这个已结束时间。
- `scripts/run_fresh_c1_p6_native.sh`当前只收PREFIX、NEW_RUN_DIRECTORY两个参数；实际Python supervisor已经支持`--total-deadline-utc`。应在这条已有链上传入本轮一次冻结的截止线，不能只改文档或重用旧UTC。
- worker→checker已有监督链，checker从原始数组重建方向张量、局部消元及原方程，已包含私有可写int32 pivot复制，不能回退为对只读mmap pivot直接调用底层求解。
- checker核对当前源文件与worker的source manifest。若后面只修checker，要另绑checker SHA、原worker SHA和精确允许差异；不能把旧worker的source manifest改成新值冒充原始身份。数学输入或数值生成依赖改变则需新的worker。

只做这些与实际失败相连的最小接线：新窗口记录绑定本review提交、执行SHA、输入SHA、起点UTC/monotonic/boot ID、固定截止线、累计费用及attempt目录。通过真实shell/service→Python监督器的**一个无FE控制冒烟检查**，覆盖截止传递、资源回调父PID、worker结束后checker接续及失败写出；数值叶节点可用哨兵，预算/入口/清理本身不能替成恒定PASS。无需建立通用重试框架或重跑已通过的昂贵FE Gate。

启动前只做一次终态核实：旧worker `1649149/start_ticks102090439`、supervisor `1649133/start_ticks102090354`及原systemd unit已终止且无后代；PID重用不能误杀其他作业。确认当前工作树clean、自己的ABI/磁盘和实际空闲执行窗口。通过后**直接进入新worker，目标是完成全链，不能停在“修复已提交”**。

### 2.2 新窗口、旧账与可用额度

本报告**新增一次最多14,400 s的W0续作授权**，不是宣称旧窗口还有余额，也不抹掉旧费用。

| 账目 | 本轮处理 |
|---|---|
| 旧W0政策窗口 | 06:41:49Z已关闭，剩余许可为0；旧200.878944s实测小计、unknown准备费用和失败记录原样保留 |
| 旧窗口用于新准入的额度占用 | 保守保留全部14,400s政策份额，标`policy_allowance_consumed_not_measured_elapsed`；不回填旧`charged_seconds=null`，不再把200.878944s重复加收 |
| 新W0窗口 | 在本轮第一项执行准备前记录一次T0，截止T0+14,400s；同一窗口覆盖准备、定向测试、失败修复、全部worker/checker、写出、读回、清理 |
| V7/V8研究政策总额 | V7原43,200s加本次新增14,400s，明确为**57,600s**；旧W0政策占用后可分配43,200s，其中新W0≤14,400、W1≤7,200、条件W2≤21,600；不互借扩项 |
| 实测历史总成本 | 仍是已知项与unknown项分列；上述政策账不构成“历史总耗时已知”或原尺寸48h通过 |
| 每个worker/checker | 各≤4500s，且≤全窗口真实剩余；给结算/清场保留时间，终止宽限不能加在截止线之外 |

本次授权的增长只用于把同一W0完成到独立检查。旧10:07:14Z启动要求已由06:38:30真实FE满足，不作为本轮重新追逐的截止时间。新窗口一旦开始，重启进程、改commit或改attempt编号都不得刷新T0；未来重启按持久记录计算剩余，时钟/boot变化时保守结算或停止。只花有限时间核对既有收据，不以重建未知历史准备时间为新计算的前置无限任务。

**自主修复额度：新窗口内最多三轮明确工程根因的修复与定向回归，最多四次worker进入（首次+最多三次修复重放），checker单独失败优先复用相同raw。**同一根因连续两次修复仍失败、任何阶段达到累计截止，或出现真实数值/资源失败，停止对应数值升级并交真实证据。每次都用新attempt目录保留旧stderr/数组/费用，不靠重新编号获得更多时间。

允许修：不参与计算的可选依赖导入、tuple/list/标量序列化、模块路径、PID/资源回调绑定、过期时间参数、writer/fsync/原始成员路径、保持同一数学量的checker读取错误。禁止借修复改变材料、网格、p/模式、相位、分母、原方程/恢复门、RAM/raw限额、迭代法，或自动重装已合格整个环境。正常数值负结果不是工程重放理由。最终相关改动运行最小定向测试、冻结新SHA后继续；不强制每个小修复做全仓pytest。

### 2.3 输入、环境与执行命令

复用已经安装的原生独立prefix：Python3.12、PETSc3.25.6 complex128/int32、DOLFINx/Basix0.10.0、MPC0.10.5、MPICH5.0.1、MPI1及数学线程1。每个新run由tracked原生activation生成自己的ABI收据；WSL测试收据、云端收据都不替代它。禁止运行中热改该worktree。

冻结输入仍为`input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat`，SHA256 **6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e**。p6-only/80 cells/532 modes/φ5、原Si、同一carrier、同Gauss与boundary_plane保持；这一步不合入Task042材料/端口实现，不创建p4或全局q因子。

本轮应把已有shell入口最小扩展为第三个明确参数`TOTAL_DEADLINE_UTC`，逐级传给已有Python参数；依赖manifest更新为“读取本次冻结窗口”，保留旧运行凭据。**第三参是本轮待完成的小修复；不能宣称当前两参wrapper已经支持。**修复与冒烟通过后的准确调用为：

```bash
# 在主线canonical登记的原生Linux工作树根目录。
# PREFIX来自本机已通过ABI的独立环境；RUN为本轮全新ignored输出目录。
# DEADLINE只能读取本次持久window记录，不能每次重试重新生成“现在+4h”。
bash scripts/run_fresh_c1_p6_native.sh \
  "$T40_NATIVE_PREFIX" "$T40_NEW_RUN_DIR" "$T40_FIXED_DEADLINE_UTC"
```

service中的实际数值入口保持为以下已有CLI；必须由专用父监督运行，不能直接裸跑`--worker`：

```bash
python -m benchmarks.run_fresh_c1_p6_component \
  --supervised --output-dir "$T40_NEW_RUN_DIR" \
  --abi-receipt "$T40_NEW_RUN_DIR/abi_receipt.json" \
  --total-deadline-utc "$T40_FIXED_DEADLINE_UTC"
```

该supervisor已按worker→checker编排；本轮补齐整窗准备、持久读回和异常结算计时。独立checker若失败，保留原worker/source/raw身份，只在其读取错误修复后重验；不能因为checker错误重算正确FE或改原报告hash。

### 2.4 RAM、磁盘、swap和通过标准

| 门 | 主线 W0 固定要求 |
|---|---|
| 任务树RAM | 3,221,225,472 B=3GiB；分配前含借用对象/新workspace及128MiB证据余量；监督所有编译器和子进程 |
| raw磁盘 | **8,589,934,592 B=8GiB**；[主线budget manifest](../../benchmarks/fresh_c1_p6_w0_budget.json)给无去重、最多80 raw/orientation类的derived上界6,900,030,936 B。不是RSS |
| 其他磁盘 | control/log各128MiB、JIT2GiB、tmp1GiB、空闲reserve2GiB；启动所需各项总空闲至少14,227,079,168 B。未授权再造一个完整重复大归档 |
| 主机 | 实际整机/cgroup占用和正余量，整机≤2e12B；不终止其他任务、不擅自swapoff |
| swap | 任务树swap必须0，运行期间全局pswpin/out新增即停。已有21,600KiB宿主历史占用单独列出，不能认证整机zero-swap；这是旧Gate的继续执行，不是将其改判通过 |
| same-live | 现有八项、532有序keys、carrier前后身份、编译Gauss及内核来源全部保留 |
| 原始张量 / CSR | 按原native操作顺序重建消元前raw与方向张量的C-order字节hash；CSR完整支持/分块等价沿原1e−12，不能混成同一个byte-hash门 |
| action/RHS/恢复 | 原action/recovery≤1e−11、制造解完整原方程≤1e−10；覆盖非零内部及端口RHS、全部36,000内部自由度、MPC/slave和全部532输出；所有原分母/零尺度规则保留 |
| 独立checker | 从原始张量、方向与MPC映射、原耦合及载荷重算；不相信worker的PASS字段，不把40项测试和10项skip替代真实数组检查 |
| 持久证据 | 完整科学raw角色与成员hash闭合，写出/fsync、重新打开逐成员核验；支持JSON和scientific raw分别计数/计字节。新数组可留原生工作站canonical持久目录，在那里完成checker，不要求先搬回WSL |

如需空目录的额外完整取回副本，先单列目的盘容量与I/O预算，不把它藏进“final duplicate archive=0”；不绕过此前被拒绝的跨窗传输渠道。采用已有允许的本机持久读回及轻量hash索引即可推进数值检查。

**下一项必须交付的是一份完整W0结果：**worker报告、完整raw member/role manifest、独立checker报告、同机ABI/source/input、从T0起完整wall与互斥阶段费用、同时任务树/系统/cgroup峰值口径、task及host swap基线/增量、持久读回和清场证明。通过只写`W0_FULL_COMPONENT_AND_INDEPENDENT_CHECK_PASS`，不是原尺寸PDE或完整p6周期链。只完成same-live或导出一部分数组不能收为通过。

## 3. dot 下一项：补完当前 C1a，保持预算身份独立

主线8GiB不能移植为dot的额度；dot的约674MB上界依赖**实际16类raw/29类方向张量共享**。主线的约6.90GB是对全部80单元、不假设去重的保守上界，二者对象数量与共享假设不同。

| dot对象 | 决定 |
|---|---|
| 旧512MiB停止 | 保留旧source、停止时累计bytes及已存952文件/942数组；不能回写为768MiB运行 |
| 新768MiB候选 | 805,306,368 B的raw上限，仍是磁盘payload，不是3GiB RAM；需绑定实际类数/共享key/成员header和约674MB上界的精确公式 |
| 未发布aececd8 | 122项测试按其本地源码与测试范围记录；必须先取得提交取消后的明确继续许可，由dot发布完整SHA和预算/worker/checker一致性差异 |
| 实际续作 | 许可及源码核对后，执行同一个C1a完整worker、完整raw角色、作用/RHS/恢复、独立checker，再把新完整科学raw存Library并取回；原952文件归档不必重传来伪装新成果 |
| 失败出口 | 真实类别超过16/29、共享身份不成立、下一个完整成员超cap或RAM/wall/swap触发即停；不把类裁到16/29或继续加cap |

保持原C1每worker/checker **3GiB/4500s、MPI1/线程1、无task swap且全局新增swap即停**。未来续作同样允许固定新窗口内有限工程修复；**这里是技术方案，尚不是撤销取消状态的许可**。dot应在获得确认时一次冻结其自己的累计窗口、已有费用和最多三轮修复，而不是每次失败滚动重置。

完整C1a及持久raw/checker过后才C1b p4稠密端口参考链，再C1c显式启用`compact_projection_max_owned_bytes`的精确分片投影：同fixture全部4q、非零内部/端口RHS、内部恢复、regular/notch和全部532输出。**C1a、C1b、C1c分别裁决。**随后C2公共PETSc非Hermitian实际块、整数宽度、fill、全部q因子并存和回代成本；主线不重写这些dot已有实现，也不等待dot许可而停掉主线W0。

## 4. Task042 已解决的边界部分，移交而不重做

这里的“分方向边界作用”是利用平面面片上多项式与傅里叶相位的结构，共享一维积分和实体映射，避免每个通道反复遍历、保存大矩形边界矩阵。它仍可服务完整三维体积与三维缺口；它不负责体积求逆、内部恢复或外层收敛。

| 已读取的成果 | 可以复用 | 不能继承 |
|---|---|---|
| [Response V38](https://github.com/Rookie1234567/MyFEniCS/blob/f3bf7942f62e725057c3ae44820bc1ca1794ee59/docs/task042_neural_coarse_inverse/response_v38.md) | 上下各2628面、378432紧凑行、完整32060输出；q30/q60逐通道最差1.6066324e−12；独立12模式全表面差2.3997233e−14；H/功率参考检查 | 这是冻结材料、表面和q30的边界资格。原尺寸体积PDE、非零内部RHS恢复未通过；旧q15差1.3259472e−5失败、native q60存储停止保留 |
| V38成本 | 两个完整方向作用约0.0771/0.0760s，cache7,628,096B；采样整树峰1,047,965,696B；已结算监督/probe/bootstrap699.305166s，另5s保留 | 不能把单次作用毫秒数当冷流程或原尺寸求解成本；未监督准备仍unknown |
| [Response V39](https://github.com/Rookie1234567/MyFEniCS/blob/f3bf7942f62e725057c3ae44820bc1ca1794ee59/docs/task042_neural_coarse_inverse/response_v39.md) | 四类20唯一hex的native抽取/共轭散布与MPC见证，最大1.3623019e−12；原内部项保留；可调用接口 | 真实体积组合已尝试912.591881s，因MPC slave误作独立carrier失败；`owned_active_original_dofs`修复后未完整FE重放。不是“未尝试”，也不是已合格体积引擎 |
| V39成本/消费包 | 组件含失败992.281548s，采样整树峰2,073,407,488B；有真实局部内部LU | 消费演示使用zero-volume callback，不能代替Maxwell体积。旧未归一化内部输入失败仍保留，新unit-L2输入通过不覆盖旧结果 |

V38实际完整边界source为`5529cc22a9dcc208b84ce930be271fdc54fcbbd1`；V39最终接口/预算实现为`8efb82029829dcba3f133b0ab90a1f05d9aa6c60`。消费包与最终文档HEAD另有身份；移交应从本报告冻结的Task042 HEAD逐文件核对依赖，保留这些run source，不把文档提交冒充数值来源。

**发现三个必须在接入时解决的真实差异，不需要再做整套边界研究：**

1. **Si数值不同。**主线冻结n=`0.9998851703688496+4.3236152269189515e-6i`；Task042用户表n=`0.999885140474+4.32477054e-6i`。不是同一物理hash。复用参数化实现和测试，主线继续自己的材料、模式库存和物理输入，不继承Task042材料相关系数缓存或直接比较两线复数结果。两份数据的来源都保留，不重新联网找材料、不为接线改历史Gx/W0输入。
2. **表面不同。**Task042是73×36面片；主线272×4×14仍只是计数候选。按最大|n|=35，四段y面片中的模式相位跨度约`2π×35/4=54.98 rad`，Task042均匀36段对应约6.11rad，二者不是同一个积分问题。q30是积分degree，不是“30个周期q块”。因此保留V38完整通过，只对W1新的实际面片做一次q30/q60结构积分对照，不重复V38全表面、模式扫描或巨型native q60 JIT；若不通过，不能借V38资格绕过。这个推导提示新面片风险，不声称已测出误差。
3. **行与端口变量不同。**Task042紧凑378432行不是主线全native行号；需要真实cell方向、独立MPC master、slave精确零的计算存储及共轭散布。Task042的`D`已除projection denominator，增广块是`[V,B; -D,I]`。必须明确与主线C/D/H、相位、参考平面、极化和载荷的可逆变量/符号变换，不能按名字直接拼接。

优先移交[src/solvers/directional_boundary.py](https://github.com/Rookie1234567/MyFEniCS/blob/f3bf7942f62e725057c3ae44820bc1ca1794ee59/src/solvers/directional_boundary.py)及[src/solvers/native_boundary_adapter.py](https://github.com/Rookie1234567/MyFEniCS/blob/f3bf7942f62e725057c3ae44820bc1ca1794ee59/src/solvers/native_boundary_adapter.py)所需的最小依赖组、对应独立测试和接口说明；不整体merge/cherry-pick Task042，不复制其锁定物理配置的研究runner。后者的小型`independent_trace_port_terms`接收显式C/D，仅可用作有界见证，不能拿它物化全AUTO稠密矩阵。接口含extract/scatter、forward/adjoint、modal/RHS和volume callback；本轮应接真实非零体积/内部载荷，停止增加zero-volume演示。

特别是`Hp=I`只表示**未消元端口块**。按上述块符号，内部消元后
`Hhat = I + Di Vii^(-1) Bi`，端口RHS还含`Di Vii^(-1) fi`，内部恢复为`xi = Vii^(-1)(fi - Vit xt - Bi α)`。
projection denominator、Hp与Hhat不是同一量。V39的450内部列六面迹接近零，但原native C内部项最大约1.3012535e−11；不得直接截零，更不能据此删除非零内部载荷项。这正是W0之后值得实际计算的缺项。

## 5. W1：一组真实 AUTO 代表类，补内部修正及完整成本

### 5.1 冻结清单、范围与唯一新增对照

复用已有`benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json`及其字节相同副本：

| 身份 | 固定值 |
|---|---|
| 全部有序通道 | 32,060；原文件36,244,923 B |
| 文件SHA256 | `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d` |
| 有序keys digest | `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec` |
| 物理身份 | 原尺寸、λ0.7、θ89°、φ0；主线材料；上下端口/极化/出射基/参考面全部匹配 |
| 计数候选 | 272×4×14=15,232 cells，完整p6计数10,228,620、内部6,854,400；没有原尺寸精度资格 |

本次复核已发布hash/计数与Task042消费包，未读取ignored清单本体；执行方对**现有文件**重算hash并逐项核对键与系数即可，不再次生成库存。Task042也写32060不等于有序keys、介质、归一化和别名全部相同；若顺序不同但集合/物理相同，保存显式双射，不删补模式。材料相关字段不一致时只复用算法，在主线物理身份下重建这些系数并独立核验。

W0完整通过后，W1直接完成下面一组数值交付，不等dot：

- 原尺寸真实上/下介质各一个代表面、一个最大支持的内部修正类，p4/p6各处理必要对象；实际几何、材料、所有32,060有序keys可分批，禁止用随机modal stress或少量keys冒充全AUTO。
- 复用Task042边界/行映射，在新的实际面片上只做一次q30/q60结构积分对照，记录全keys最差项和原分母，沿边界1e−10门；不启动全表面重跑或native q60巨型JIT。不通过则停止该q30接线的向上资格，保留其余真实成本，不自动再扫q/p/M。
- 以同类有限小keys的显式旧表示作一次精确对照，再对全keys作作用/伴随/载荷与内部修正的分批检查。非零内部及port RHS、方向/MPC行映射、恢复≤1e−11及相关原方程≤1e−10沿V7不变；按独立原始数组重算。小keys只是见证，最终输出与费用必须覆盖完整keys。
- 同时保存真实raw/class/接口数据和创建/释放时间，供dot C2消费；不在主线重写dot的精确分片投影或再做一套完整4q p4链。

**W1整组≤7200s、任务树≤16GiB=17,179,869,184B、MPI1/线程1，swap与整机门同第2节；至多两轮局部接线修复，所有准备、冷JIT、失败、checker、写出均累计。**不建原尺寸全体积矩阵、不做目标规模LU、不增第二组几何，不自动扫描batch/tile参数。若新Task042参数化与主线ABI不兼容，有限修复仍无法接通则交精确缺口，不能以合成结果顶替。

这是对已有模块的最小接线任务，当前c0a36a3没有合格的全AUTO W1 CLI。执行者在授权内补齐后交真实`--help`、冻结输入和一次控制检查，随后直接执行；本报告不杜撰不存在的命令。

### 5.2 不先分配 Hhat；按真实对象和生命周期结算

32,060²个complex128的单个稠密方阵就是 **16,445,497,600 B**；在W1 16GiB中只剩734,371,584B给解释器、FE、投影、内部LU及所有工作区，连现有W0采样基线都不能容纳。**不得尝试先造它再观察OOM。**采用有界分批作用/已有精确结构，实际报告内部修正支持与临时量；未证明可压缩时保留unknown，不假设Hhat对角、不裁小元素。原H对角512,960B不能代替Hhat成本。

| 原尺寸费用项 | W1/互补验证必须补什么 | 当前边界 |
|---|---|---|
| 冷JIT、求积、缓存 | 从空任务缓存起计编译器子树、实际节点/weights、峰值与临时文件；复用V38算法降低重复积分，但记录新面片资格 | V7 nominal degree156/160只是旧公式成本，不能当必须重复的大JIT路线，也不能被q30历史值直接覆盖 |
| C/D、行映射、投影临时量 | 完整keys和真实参数、borrowed/owned、复制、CSR旧新重叠、一次batch及同时存活 | 主线W1测实际类；dot C1c检验分片投影。不能只统计最终CSR |
| 内部消元/恢复 | Vii因子、Vit/Bi/Di、内部特解、完整恢复映射、类别数/共享key、复用/重算次数 | 80单元W0完整恢复通过不代表原尺寸类别与费用已知 |
| H/Hhat | 原块、内部修正、RHS修正与matrix-free工作区；列出表示、支持与非Hermitian约定 | 有限见证与全keys作用不是全目标Hhat因子资格 |
| 全部q因子与fill | 各q rows/NNZ、L/U NNZ、排序/后端整数容量、setup/回代；全部因子及workspace实际并存 | dot C2补；单q×q数或缩小RSS线性外推不算实测 |
| 外层/完整PC | 原A6作用、完整PC的所有步骤、setup、外层步数及最大步数成本 | W2补有限完整对照；p4存储等价不自动减少p6步数 |
| 向量、输出与独立检查 | 真实同时Krylov/恢复/采样向量、raw、hash/fsync、独立checker重开、缓存和清理 | derived对象字节不相加冒充同时RSS |
| 系统 | 全局/cgroup其他占用、文件缓存、编译/BLAS后代、固定正余量、swap基线与增量 | 全机min(物理内存,cgroup,2e12B)扣除这些后才有solver额度 |

每项分类measured/derived/predicted/unknown，列出源、尺寸、同存区间和误差范围。Task042另一个容量scenario是530,856 cells，不能把它的向量/cache计数套到15,232 cells；两者均不是合格原尺寸离散。W1通过只得到真实对象和内部作用成本，不能从代表类推成全部q fill或原尺寸48h通过。

## 6. W2 与原尺寸资格：顺序不变，别把存储节省当收敛改进

**W2仍HELD：**W0完整raw/checker通过、dot C1c同fixture全部4q完整紧凑链通过、工作站ABI和真实入口接通后，才允许V7第6节那一个对照组。参数继续为80 cells、λ0.7、φ5、532模式、p6、regular及同一notch；同一原A6外层分别使用准确p4-based完整PC与全阶p6周期参考逆。后者改变参考问题所在的离散空间，可能减少外层步数，但增加投影、分解和恢复费用；必须以完整流程实测抵偿，不能继承p6组件资格。

整组≤21,600s、任务树≤64GiB、FGMRES32/零初值/最多128外层步；原A6显式残差≤1e−6、恢复/原方程identity≤1e−10、port≤1e−8、参考逆regular制造解≤1e−10、小对照action/恢复≤1e−11。两路线固定同坐标、同相位、同背景和原分母，总/散射E及scaled-curl≤1%、预冻结显著复模式≤1%、全532保留、功率差≤1e−3、能量≤1e−5。准备、完整PC、全部因子并存、恢复、输出及checker全部计费；任一不收敛不能声称全流程加速。两轮局部实现仍未接通则not_run，不开新网格或迭代上限升级。

既有[Review V7](review_report_v7.md)的历史比较继续有效：旧2nm p6/h1.5在185小时后OOM且未收敛；新版5nm F5约3.48小时、2nm H6单项约4.87小时，不重复这些优化。按F5分项，即便消除全部C步骤，总加速上限也仅约1.554倍；必须解决完整PC、步数及原尺寸规模增长。全阶p6参考逆是有条件的单一反证，不是自动成功的替代方案。

Gx784继续复用，不重跑：原A6=9.692115e−7、两组最大保存场差约0.0642%、`tested_x_agreement`成立；3431.623s、任务RSS约7.783GB/task swap0与系统151页swapout分开。四角/Gx结果不是原尺寸收敛；历史2.611883%/2.750374%场差和1.555605%显著复模式差不改写。原尺寸y4/z14及未来非可分缺口精度仍缺；规则φ0、y不变结构的对称性只能辅助诊断，不删除y自由度或q分支。本轮不重做背景归因、Gx/Gz、模式扫描或盲加密缺口。

原尺寸正式GO必须同时有：有依据的原尺寸离散精度、完整AUTO物理/行映射、完整原方程与p6内部恢复、合格公共后端/整数宽度、全部q因子及临时量并存的整机上界/实测锚点，以及冷JIT至输出独立检查的≤172800s完整成本。**目前没有证据证明现路线能满足这些条件；也不能据此宣布物理目标不可算。**

有界的下一方向只在对应证据失败后提出，不自动追加实验：若稠密端口是瓶颈，先完成现有结构化边界与精确内部修正作用的接线；若单q因子可装但全部q并存超限，另核有限批次/精确重算能否在48h内支付，不能偷换为swap/OOC；若单qfill或p6完整PC/步数已不支持目标，关闭该精确周期参考逆的当前参数路线，才另提改变规模增长的局部求解与递归物理粗纠错。不得重启已失败的宏块/近似p4扫描，也不得继续无止境优化边界测速。

## 7. 收口与可直接交给执行 Codex 的文本

通过、数值负结果、资源停止或有限修复耗尽，都需交真实完整命令、运行/修复SHA、输入/ABI/成员hash、最后阶段与数值/限值、互斥阶段wall及整窗wall、任务树/整机/cgroup口径、swap、清理证明和下一项not_run原因。准备成本仍unknown的历史不得被新的完整账覆盖。将本轮事实写入下一response、已有summary与run index，保留所有失败；不为每个工程错误新增review编号。

本报告的检查限于远端原文/源码差异、Markdown结构及单文件提交核对；本地pytest/文档测试没有运行，不能宣称CI通过。网页渲染结果在提交回执另报。

> 在canonical登记的主线工作树安全拉取，完整阅读docs/task40extra_0p7nm_engineering/review_report_v8.md。主线审阅基准c0a36a3fc897ee66d07da1dc83cdecc78983a091；dot只读077ec9c8386c976da232093779279fb9d1a93033；Task042只读f3bf7942f62e725057c3ae44820bc1ca1794ee59。不要reset、覆盖活动任务、改dot/Task042/master或合并；不重跑Gx784。
>
> 优先完成主线W0。核实旧06:41:49Z窗口已结束及旧PID/start_ticks无遗留，保留三worker200.87894401792437s、unknown准备费用和V6旧账。V8明确另批一次14400s新窗口：从本轮第一项准备冻结唯一T0/截止，所有修复、测试、worker、checker、raw读回、清理累计，不随重启刷新。先修native_service_entry.sh及dependencies中旧截止线，使wrapper第三参逐级传给已有--total-deadline-utc；通过一次真实入口无FE控制冒烟后，按第2.3节命令直接开新的ignored attempt目录运行，不停在修复/报告阶段。使用本机已合格原生prefix并生成本机ABI收据，禁止WSL wrapper或复制云收据；80cells/p6/532/φ5、输入6654ec…、数学及验收门保持。
>
> 新W0每worker/checker≤4500s、RAM3GiB、raw8GiB、启动空闲盘≥14227079168B；任务swap0且全局pswpin/out新增即停，宿主既有swap单列、不认证整机swap0、不擅自swapoff。允许最多三轮依赖/表示/入口/写出bug修复+定向回归，最多四次worker启动，checker bug优先复用raw；同一根因两次修复仍失败、数值失败或资源触发即止。交完整worker→科学raw全部角色→独立张量/原方程checker→持久读回，以及全部费用/峰值/清场；八项same-live和40passed/10skipped不代替它。
>
> W0执行期间可做W1只读身份/最小代码移交，重型FE仍一次一个。W0完整通过后按第4–5节复用Task042 V38/V39边界和native行映射，保留主线Si：两线Si数值与表面网格不相同，不能直接继承缓存/q30资格。核对现有32060清单及双hash，不重新生成；只补真实上下代表面、最大内部修正类、非零内部/port RHS与恢复，新增面片仅一次q30/q60结构对照。W1≤7200s/16GiB/两轮局部修复，全keys分批，不物化16.445GB稠密Hhat，不建目标体积/LU；交JIT、C/D、内部修正、投影临时量、H/Hhat、全q因子/后端、外层向量、输出checker与系统余量账，unknown保持unknown。
>
> dot的512MiB受控停止、952文件/942数组真实Library保存取回保留。aececd8/768MiB/122tests仍是未发布候选，提交取消后的发布与运行许可须人类单独确认；本指令不替dot恢复许可。确认后由dot完成C1a作用/RHS/恢复及独立checker和新科学raw保存，再C1b稠密链→C1c显式精确分片投影完整4q/532/内部恢复→C2公共PETSc/全部因子成本。不要把主线8GiB无去重预算套给dot的16/29共享预算。
>
> W2只有完整紧凑链及独立raw资格齐全后，才做第6节唯一p4完整PC/p6参考逆对照；≤21600s/64GiB、max128、原A6及固定场/模式/功率/恢复门不变。V7/V8研究政策额共57600s，旧W0政策保留14400，新W0/W1/W2上限分别14400/7200/21600，分项不互借；这些不是历史实测总成本，也不是原尺寸48h证明。整机十进制2TB、无swap、冷JIT至独立检查≤48h及原尺寸精度未同时闭合前，正式原尺寸始终NO-GO。停止时交可继续使用的真实证据和明确缺口，不自动追加扫描、编号重试或重跑旧失败路线。
