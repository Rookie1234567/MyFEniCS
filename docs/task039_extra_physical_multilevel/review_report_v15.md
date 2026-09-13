# Task39extra Review V15：一次I/O中断恢复，继续完成V14 Schur对照

## 0. 决定与执行身份

**选择新增这份恢复review，不另开算法任务。它解除的是Q0文件读写中断和未结算账本造成的执行阻断；V14的数学方案、数值门槛、内存限制及最终目标均不改变。恢复检查通过后，Codex直接继续，不逐阶段等待新指令。**

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task39extra
review_date            = 2026-09-13
reviewed_HEAD          = fe1b3fd20f7595d49645c558cc43bf3a942360e6
latest_engineering_SHA = 5d239140d3931364bc16d35c45458189cd957808
interrupted_Q0_source  = efea244159d63a7c9db67ca091e29a9c19f9ce88
numerical_contract     = review_report_v14.md
execution              = R0 -> R1 -> one recovered Q0 -> Q1/Q2 -> conditional Q3/Q4/Q5 -> Q6
response_required      = response_v16.md
infrastructure_recovery_allowance = 1, only for the identified interrupted Q0
ordinary_default       = unchanged
master_merge           = NOT_APPROVED
```

本轮用户已明确授权由ChatGPT直接决定并落实后续指令。本文据此授权一次**基础设施中断后的受控恢复**，不是把EIO改称实现bug，也不是授权数学失败重试。它优先补充V14的中断恢复和回应文件要求；其余继续服从[Review V14](review_report_v14.md)。同一执行分支普通提交并推送，不改旧review，不合并master，不影响同步5 nm任务。

最终目标仍为单节点约2 TB内的0.7 nm任意非可分三维Maxwell散射。本批仅恢复16 GB笔记本上13.5 nm的既定实验；不声称通过这次恢复即可消除求解器或容量瓶颈。

## 1. 已审阅事实：只接受记录能够支持的结论

依据：[response_v15](response_v15.md)、[V14阶段结果](outcomes/p4_schur_v14.md)、[compact](outcomes/records/p4_schur_v14_compact.json)、[工程证据](outcomes/records/p4_schur_v14_engineering.json)。这些是远程既有记录，不是本review重新测得。

| 项目 | 已知数值或状态 | 口径与边界 |
|---|---|---|
| Q0最后可靠阶段 | setup；P64 transfer已生成 | 没有Q0完成摘要、准确p4求解或终态资源资格 |
| 直接异常 | 写manifest和读ledger先后出现EIO；outer exit 135 | 已知parent I/O故障；worker最终原因仍缺失，不推定硬盘坏或OOM |
| 进程树RSS/PSS | 1,417,695,232 / 1,385,432,064 B | 373行有效前缀的采样峰值，不是完整workflow峰值 |
| zero-swap与清场 | 前缀内job swap为0；最终终态缺失 | 不追溯认证整个旧运行 |
| Q1/Q2配对 | 未找到合格完成记录 | 不拿V5/V13填充，不无限寻找假定存在的结果 |
| 新工程实现 | 104项联合测试及另30项检查通过 | 尚无新正式p4/p6资格，不重写已实现的接口PC |
| 推送状态 | 最新提交已确认推送 | 不再要求解决旧的推送审批或认证问题 |

旧Q0路径为：

```text
results/euv_grazing1_phi0/task39extra_v14_q0_core__full3d_iterative__mpi1__Mna/20260912T123558.964217Z
```

旧共享账本为：

```text
benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json
SHA256 = b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0
Q0 attempt 1: RESERVED; reservation=600 s; elapsed_seconds=0.0
observed elapsed lower bound = 104.12926405597166 s
```

`elapsed_seconds=0.0`是未结算字段，不是零成本。600秒也是原预留额度，**既不是实测耗时，也不是失联期间实际运行时长的已证上界**。本节身份若与实际原件不符，先核对是否存在有据可查的后续记录；不能强行覆盖成上述hash。

## 2. R0：一次有限环境准入，不开展存储系统研究

先在已登记的canonical worktree确认branch/HEAD、工作树、qualified Linux ABI、complex128/int32、MPI1和线程1。沿用原有合格环境，不安装新求解库、不重做未受影响的MUMPS/metric资格。

**确认旧任务当前已不存在活跃进程。** 用命令行、实际运行目录、进程启动时间及可用的boot身份判定；不得只凭旧PID发信号。若仍有确切归属于本次旧Q0的进程，只按现有watchdog范围清理并回读确认；禁止全局`pkill python/mpiexec`、重启全部WSL或影响其他任务。不把“当前无旧进程”写成已证明历史清场成功。

环境检查集中一批，采集过程预算最多300秒，并计入本次总账；历史日志不可读时记录权限/缺件，不无限追查。检查实际源码、ledger、results/artifact所在挂载点的可写性、空间、inode和可取得的故障时段内核/文件系统日志；WSL下也检查承载其虚拟磁盘的宿主卷余量。若无法取得关键存储状态且因此不能排除持续风险，停止，不假装已检查。

在ledger和results父目录分别使用**本次新建临时文件**，各顺序执行两次不超过8 MiB的写入、文件fsync、关闭重开、hash核验、同目录原子重命名与目录fsync。每轮回读后仅删除自己创建的探针文件。两位置总写入载荷最多32 MiB，不做压力测试、全盘扫描、cache清空或文件系统修复。file fsync与directory fsync含义见[Linux接口说明](https://man7.org/linux/man-pages/man2/fsync.2.html)；WSL两层存储背景见[Microsoft说明](https://learn.microsoft.com/en-us/windows/wsl/disk-space)。这些操作不构成介质健康或断电耐久性的完整证明。

| R0结果 | 行动 |
|---|---|
| 当前读写核验通过、空间满足既有预检、无持续存储错误、旧进程已不存在 | 进入R1；不要求先证明历史瞬时EIO的唯一根因 |
| 再次EIO、只读挂载、hash不符、空间不足或清场无法确认 | `INFRASTRUCTURE_BLOCKED`，停止正式worker，保存可取得证据 |
| 需要fsck、VHD修改、强制重新挂载、系统重启或数据迁移 | 本文不授权这些操作；停止并交付具体阻碍，不能为继续PDE冒险 |

本轮不把旧记录末尾的NUL截掉后当成完整日志，也不删除旧manifest、ledger或负结果。已有已查目录没有Q1/Q2结果时，直接承认缺口；只有出现新的具体路径线索才定向核验和复用，不全面重搜磁盘。

## 3. R1：保留证据的账本恢复与唯一补跑授权

### 3.1 恢复必须可审计、幂等，不靠手工清零

当前`task038_launcher.py`会拒绝任何未结算active attempt，并将普通重放要求绑定到`IMPLEMENTATION_BUG`。允许最小的**显式V15恢复入口**处理本节唯一事件；默认行为及其他profile不变。复用现有parent ledger/worker/Q6，不建设新的调度或审计平台。

先将旧ledger原始字节及hash保存为不可变快照，旧Q0产物不修改。再产生一个包含`predecessor_ledger_sha256`和恢复记录hash的后继工作账本；可经同目录临时写、fsync、rename、目录fsync原子发布到原工作路径。父启动器独占迁移，禁止与活跃worker并发改账。

后继账本完整保留旧attempt的原字段和终态缺口，另加恢复事件，至少记录：

```text
recovery_id = V15_Q0_EIO_ONCE
failed_source_sha / old_run_directory / original_ledger_sha256
observed_elapsed_lower_bound_seconds = 104.12926405597166
actual_elapsed_seconds = null
accounting_policy_debit_seconds = 600.0
accounting_basis = ORIGINAL_RESERVATION_NOT_REFUNDED
historical_terminal_coverage = incomplete
current_no_live_attempt_evidence / io_probe_evidence
administrative_closure = INFRASTRUCTURE_INTERRUPTED_UNFINALIZED
infrastructure_recovery_count = 1
```

**解除active控制指针只表示可以开始新任务，不代表旧worker正常退出、数值通过或资源终态已知。** 相同恢复事件再次调用必须无变化或明确拒绝；不得重复扣600秒、重复释放active、再给一次额度。若发布过程中又中断，先按前驱/后继hash判断已提交状态，不猜测或清空文件。

### 3.2 预算仍是原43,200秒，未知成本与实测成本分开

旧600秒预留本批不返还，作为一次明确的**政策预算占用**；旧真实耗时继续`unknown`。新增R0检查、正式worker、checker和保存开销按原父流程计费，嵌套不重复相加。工程编辑/测试时间另列，不冒充PDE成本。

```text
budget_used = verified_measured_charges + 600 s policy_debit
remaining   = 43,200 s - budget_used - currently_active_reservations
```

这里只对这一次缺失终态的旧Q0使用政策扣款；它不是实际总耗时的完整测量。若另发现可靠的旧终态，须经同一幂等恢复记录调整为至少600秒且不低于可核实费用，不双重计费、不将新证据悄悄覆盖旧证据。预算检查、worker剩余时间、stage额度及Q6必须读取同一有效账，不能某处只读旧`elapsed_seconds=0`而漏掉扣款。

**授权且只授权一次新的Q0完整尝试，上限仍为600秒。** 新attempt使用新的运行目录及clean source SHA，明确绑定本文。旧600秒占用加新Q0的至多600秒预留，是本文唯一的Q0累计额度例外；不增加整批43,200秒，不改变Q1–Q5阶段额度。R0在同一总预算内单列。旧失败不算新PASS，新的Q0必须真正完成共同核心资格。

此恢复不消耗、也不重置V14原有`unique_bug_replay_count`；使用单独基础设施计数。Q0完成这次恢复尝试后不得因EIO、数学/费用停止或本地自动重试再获得第三次Q0。后续其他阶段的真实实现bug仍只能按V14原有一次、需证据的全批规则处理；数学失败不重试。再次基础设施故障则保存证据并收口，不循环恢复。

### 3.3 允许的最小实现与测试

允许修改现有launcher的恢复/预算读写、worker预算读取及Q6恢复记录识别，补必要的原子发布与异常清理。新状态通过显式recovery metadata启用，不改变物理hash或旧默认策略；变动源码要先普通提交再启动正式worker。不要因代码已经测试通过就跳过新的干净源码身份。

集中测试：非匹配hash/活跃旧任务拒绝；重复恢复不重复扣款；未知耗时不变成600秒实测；恢复额度与bug额度独立；总账/worker/Q6一致；旧默认路径不变。复用已保存且仍适用的104/30项工程结果；仅对本次修改所影响的集合重跑，保存原始输出。缺少Ruff等工具如实记录，不为此升级ABI。

EIO异常路径必须优先停止新阶段并执行现有、可确认归属的进程清理；保存失败时可将紧凑异常输出到仍可用的stderr。不能无限重试同一坏路径，也不能捕获EIO后继续装作成功。若硬件故障使持久化仍不可能，报告终态缺失，不制造完整证据。

## 4. 恢复后连续执行V14，不改算法、不再逐步停审

共同物理和数值身份完全继承V14：13.5 nm、1度、p6/h10、252 hex、42宏块种子、80个原DtN条目、MPI1/线程1、complex128/int32；原A6/b、材料、quadrature、Floquet及P64不变。原physical SHA为`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`，ordered mode SHA为`dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。已有参考仅用于评价。

| 执行顺序 | 按既有合同交付什么 |
|---|---|
| 恢复Q0 | 原公共核心、映射、作用与资源资格；不将旧部分setup当成完成 |
| Q1 → Q2 | 同三份RHS的原p4准确LU和准确Schur；两套大因子顺序运行，报告原A4精度、全部内部/接口库存、完整RSS及setup/调用/恢复时间 |
| 条件Q3 | 唯一接口候选：一次内部消元—固定接口两级修正—恢复，直接替换整个旧I4 |
| 条件Q4 → Q5 | 同一FGMRES32通过有限进展线后继续original；完整通过才用同配置验证notch |
| Q6 | 依据真实已完成数据统一收口；缺失阶段明确分类，不以占位状态或工程测试当求解成功 |

Q1/Q2必须维持原A4残差不大于1e-10、匹配场/旋度差不大于1e-8。**准确Schur没有省内存，不禁止Q3。** 仅全局接口分解因费用/资源被挡住时，若共同内部求解、作用/伴随及恢复按V14已资格化，也可继续Q3；共同正确性失败则停止，不能用近似隐藏问题。

Q3的三输入准入、每次F_int费用、局部SVD/左右P/Q及小粗矩阵限制，全部按V14第5节；不降低门槛，不恢复旧C_U/S-p2、四步I4、recycling、额外内层或新PC。Q4同一步数/同时间比较及1800/5400秒进展规则照旧；最终原A6残差不大于1e-6，并完成V14原有E/H、L2/curl、R/T/A、A_volume、全部80模式、守恒及provenance要求。

资源不放宽：树RSS上限仍受8 GiB和动态整机余量共同限制，reserve为max(4 GiB,15% effective_total)；Q1/Q2常驻库存6 GiB，Q3–Q5常驻库存3 GiB，所有并存临时工作区合计1 GiB；零作业swap、无新增全局交换、一次一个heavy。不把partial RSS、后端used或factor数值载荷替代全过程RSS和allocated库存。

正式计算继续通过`python scripts/run_case.py input/path/to/case.dat`。Q1/Q2没有合格旧结果时按合同fresh执行，是完成未完成的计算，不是“仅为上传重跑”。不得再次回到无限寻找旧结果、重写接口算法或旧诊断优化。

## 5. 停止、证据与提交

恢复前置通过就连续完成可执行阶段，最后统一审阅；无需为普通阶段切换、已批准的预算恢复或既定Q3准入再次询问。硬资源/存储错误、真实正确性失败、数学或性能停止均保留分类与实值；没有证据就写`unknown/not_available/not_run`。本次不以工程完成声称Schur省内存，也不声称新PC已有效。

仅新增一份紧凑恢复记录`outcomes/records/v14_io_recovery_v15.json`，包含R0结果、旧/新账本hash、旧600秒政策扣款与新实测费用、一次恢复计数、source/input/运行路径和终态入口。原始日志、原账本快照及数组继续放ignored目录。无需建立第二套数值结果目录结构或监控平台。

最终新增`response_v16.md`，按V14现有文件增量更新`outcomes/p4_schur_v14.md`、compact/comparison、run_index、summary/test_summary及项目总账，保留response_v15和旧Q0历史。Q6及response首屏分别回答：**准确Schur省内存了吗；唯一接口近似是否有效；完整original/notch是否通过；若未完成，实际在哪个Gate停止。** 同时分列已知实测费用、600秒政策占用和历史未知耗时。

普通commit顺序：最小恢复逻辑及定向测试；真实Q0/Q1/Q2证据；Q3和条件完整求解证据；统一回应。每个正式worker绑定clean source。用户已授权向`Rookie1234567/MyFEniCS`的`task39extra`推送本任务代码和轻量证据；仅此目标，不导出大型数组、凭据或无关数据，不绕过实际审批拒绝。推送后用远端ref核对，并回读关键结果；本次已解决的旧推送问题不再作为前置任务。不amend、不强推、不merge master。

**本review的新增内容只有：可核查的环境准入、一次Q0基础设施恢复、未知费用的诚实预算处理。其终点仍是完成V14已经要求的真实对照，而不是再交一份“恢复工具已通过”的结果。**
