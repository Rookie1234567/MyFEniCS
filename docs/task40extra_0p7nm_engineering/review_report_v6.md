# Review V6：打通一次 Gx784 执行，复用 AUTO 清单，分开裁决云端资格

## 0. 本轮决定

**批准一次新的、附明确启动条件的同一 Gx784 执行。先修通真实旧账本续作与后处理入口，在不加载 FE 的完整启动契约检查通过后，直接执行并完成两组比较，不再等一轮文字审批。当前 b8bd7c2 不能直接重启；本授权不是恢复已耗尽的 V5 故障重放额度。**

本轮回应 [Response V5](response_v5.md)及[执行收口记录](outcomes/records/review_v5_execution_closeout_v1.json)。只有一个新增精度点，仍是 V5 的 14×4×14 Gx784；不新增第二张网格，不重复 Gx/Gz、背景归因或 AUTO 清单生成。通过或失败均完成有界交付，然后停止自动追加实验。

| 身份 / 对象 | 核实与裁决 |
|---|---|
| 审阅日期 | 2026-10-03 |
| 主线最新远程 HEAD | task40extra_0p7nm_engineering：b8bd7c2f23726142161b58a7d7ff52275ea677ba |
| dot 最新远程 HEAD | task40extra_dot_parallel_cloud：eb5b0ecc1afe593f626b44a6038f7f26651b3317；未发现更新 |
| 本轮权威 | 本 V6 替代 V5 中已耗尽的执行/重放许可和“生成 AUTO 清单”任务；V5 数学案例、分母及验收不变，其他未冲突合同继续适用 |
| 主线启动接续修复、无 FE 契约检查 | **立即 GO**；最多两轮局部修补与定向检查 |
| 主线新 Gx784 正式执行 | **一次有条件 GO**；第 2 节全部通过、旧场可读、机器准入后自动执行；不是当前源码已就绪 |
| dot C1a / C1b / C1c | **数值计划有条件 GO，当前 HELD**；持久保存决定阻塞云端实际运行，不阻塞主线 |
| AUTO 资源账 | **立即 GO：读取已存在清单，补生命周期与缺项**；不再生成库存 |
| AUTO 实际成本探针 | **有条件 GO**；按 C1→C2 顺序，在完整模式接线及小预算内做有界探针；当前 NOT_RUN |
| 原尺寸完整求解 | **NO-GO**；精度、AUTO 接线、因子填充与并存、后端、完整时间均未闭合；不称工作站大规模验证就绪 |

最终目标仍为 **50×25×140 nm、λ=0.7 nm、完整三维、保留未来三维缺口能力，整机十进制 2,000,000,000,000 B、swap=0，完整必要流程 ≤172,800 s**。包括冷编译/求积、构造装配、全部分解、迭代、内部场恢复、必要输出和独立校验。缩小模型、组件、残差通过均不能替代该目标。

本次读取远程源码、提交差异、V5 测试/收口记录，以及 dot V15、恢复合同与新候选检查点。审阅端本地命令工具无法启动；**本报告未实际执行新的启动契约测试、pytest 或 FE，也未取得 ignored 原始场/36 MB 清单逐字节重算**。下文严格区分已发布证据、静态核对、derived 数值与待执行检查。条件授权允许执行 Codex 在本轮补齐实际启动证据后直接推进，不把静态审查写成动态 PASS。

## 1. 接受 V5 的真实进展与停止，不继承不存在的精度结果

| 事项 | 已发布事实及其边界 |
|---|---|
| pre-ledger 启动失败 | CONSERVATIVE_REALTIME 未定义，发生在 watchdog/worker/FE 之前。systemd 微秒时间戳推得服务主进程寿命上界 0.189045 s；原错误单位收据和更正收据都保留 |
| Gx784 worker 失败 | 源码 24a56962c733b9ae5454000cdae224dae6dda8f0 拒绝 enforce，报 V20 requires observe_only throughout the worker；尚未到数值预检查/FE。没有新场、残差、R/T/A，不是残差失败 |
| 后处理 attempt1 | POSTPROCESS_PARENT_FAILED：监督器要求专用且无已有子进程的父进程；没有启动比较 worker/checker |
| 969b4086320b844d44fb0b67092ffe5af2d760b1 | 修正 Gx784 的 worker 时间合同、后处理先检查求解/恢复状态再启动；35 项相关测试、12 项生命周期测试、13 项文档测试及记录中的 ABI/compileall/diff 检查通过 |
| 修复后 held 记录 | 由直接 preflight/写记录 helper 生成，未运行完整 service 入口、预算预留、watchdog 或场比较。不能当作成功后处理路径的运行证据 |
| V5 执行额度 | unique_bug_replay_count=1，已耗尽。修复已提交不自动授予再跑一次 |
| 旧精度负结果 | F3/F5 散射 E 2.611883%、scaled-curl 2.750374%、冻结显著复模式 1.555605%，均继续保留为超过 1% |
| 四角结果 | Gx/F5 E 与 scaled-curl 差约 1.376e−6 / 8.788e−7；Gz/F5 仍约 2.612% / 2.750%。支持当前误差主要对 x 敏感，未证明 x=10 收敛 |

已记录工程账为：

| 已发生工程阶段 | 预算扣费 s | 不能解释为 |
|---|---:|---|
| pre-ledger 服务寿命上界 | 0.189045 | PDE 或完整准备时间 |
| 失败的 Gx784 尝试 | 3.939768298688392 | setup/KSP 时间；其实际父流程 monotonic 为 3.939483341993764 s，watchdog 为 3.9084257329814136 s，范围不同 |
| 失败的后处理父进程 | 0.4904406969435513 | 已执行场积分或独立 checker |
| 合计 | **4.619253995631944** | 数值求解耗时或整个项目累计耗时 |

共享账本现存 SHA256 为 **67c086c9fa975c97a3a6980bfa5ac4fa9cb60c59e2fa2f5ea60f477e86c72c8d**，active_attempt=null，剩余 172795.38074600438 s。两次 AUTO 生成时间没有保存，仍标 unknown，不计为零。133,492,736 B 是 pre-FE 失败期间的进程树 RSS 峰值；不是 Gx784 计算内存。

## 2. 先解决可定位的启动接续问题，再用一次执行得到新场

### 2.1 计时与后处理源码审查

这里的“启动契约”指同一输入、源码、旧账本和剩余时间真正穿过启动器、worker、求解器及后处理；它要排除的是已经发生的入口冲突，不是再做一套物理验证。

| 环节 | 静态核对与处理 |
|---|---|
| launcher → worker | launcher 对精确 Gx784 run_id 选择 enforce / 172800 s，并传入父账本、attempt 与剩余量。V20 的 _resolve_v20_worker_time_contract 只对该案例复制并覆盖旧 profile；历史其他案例仍保留原 observe_only。这个局部修复方向正确 |
| worker → Q4 求解器 / PC | _V14Runtime 读取同一父账本、源码和策略；Q4 对已标记 Gx784 接受新时间合同，workflow_limit 取父预留与总上限的较小值，停止回调使用 enforce。旧 10800/43200 s 和 PC 25/30 s 限制不能重新成为本案例隐藏终止条件；p4 数学参数不变 |
| **真实旧账本续作仍有阻塞** | launcher 的 _load_task40_v5_preledger_bug_replay 要求旧凭据 fixed_source_sha 等于当前 source_sha；旧凭据绑定当时的 24a5696，新的修复/审阅提交必然不同。随后还核对旧历史对象完全相等，并按 V5 已用额度拒绝重放。不能删旧凭据、改其 fixed_source_sha、清零计数或换 run_id 绕过 |
| **成功场的后处理接续仍有阻塞** | _reserve_task40_v5_postprocess_budget 的旧重放只接受 POSTPROCESS_WORKER_FAILED_OR_CONTROLLED_STOP + WORKER_FAILED + 非零 worker exit；实际历史是 POSTPROCESS_PARENT_FAILED 且没有 watchdog。这种真实失败不能伪装为 worker 失败以取得许可 |
| **完整时间需贯穿后处理启动间隙与清理** | 后处理预留扣除了前置检查，但 supervise 直接收到预留时的 reserved_seconds；预留到实际启动之间的耗时及结束写出/清理需纳入同一剩余截止线。当前源码不足以证明 48 h 边界无遗漏；这不是已实测超时 |
| 后处理数学门 | 当前实现保留三场精确轴并集、同材料公共体积、归档 F5 场分母、两对各自首场模式分母及冻结 11 keys；入射归一化仅作诊断。这部分不需改算法 |
| 完成与精度通过 | service 返回成功只代表监督工作完成。独立 checker 的原始量及最终分类才裁决精度；负结果可正常完成流程，不能因为 exit0 就改为通过 |

定位入口（均为审阅基准源码）：[历史凭据与预留](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/src/runners/task038_launcher.py#L3613)、[后处理重放](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/src/runners/task038_launcher.py#L4630)、[后处理完整入口](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/benchmarks/run_task40_v5_postprocess_service.py#L297)、[worker 策略](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/src/runners/physical_dual_cell_condensed_lowmem_v20.py#L1189)、[Q4 预算选择](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/src/runners/physical_p4_schur_v14.py#L7194)。

已有测试有实际首次预留/结算和 pre-ledger 单次扣费测试，应复用；但名为 full_launcher_chain 的测试替换了真实 reservation，worker 测试使用新建账本，后处理 ready-path 测试没有运行完整 ready service。**它们尚未覆盖“真实历史账本 + 新源码 + 本轮授权 + 成功场后处理”的接续。**不要求把这些已通过单测重新包装成一批新成果。

### 2.2 一次新的授权怎样落地

在既有账本中追加一项有界授权记录，例如 review_v6_gx784_once，绑定本报告提交、最终执行源码 SHA、原输入 SHA、旧账本 SHA 和新输出目录。这是授权元数据，不是新物理案例；保留原 run_id：

task40extra_0p7nm_nonseparable_gx784_review_v5_v1

旧 V5 两次启动失败、后处理父失败、凭据 hash、历史 fixed_source_sha、unique_bug_replay_count=1、4.619253995631944 s 累计扣费全部保留。历史凭据按其历史修复源码验真，新授权按新的执行源码验真；两者不可混写。沿用已有预算读写与监督器，做最小扩展，不复制求解 runner，也不建设通用重试框架。

本 V6 的正式额度是 **一次 Gx784 launcher/worker 执行**；即使再次在 FE 前失败也消耗本轮额度，不能再发一个编号重启。可以配套执行一次完整保存场后处理；若后处理自身出现明确局部实现错误，另明确允许 **最多一次仅后处理修复重放**，不能重跑 PDE、换场或因精度不合格重算。后处理旧父失败保留并由本次新授权接续，不借用 V5 已耗尽额度。所有新尝试均使用新目录并计入共享剩余时间。

### 2.3 必须补齐的一份无 FE 启动契约证据

在真实旧账本及凭据的隔离副本上运行；不得消耗正式授权或写入活动作业。复用原测试文件和入口，最多两轮局部修补/定向测试，覆盖以下一条链及其必要分支：

1. **真实输入与历史续作：**读冻结 .dat，经实际配置解析、真实预算预留/结算及新授权消费逻辑；保留历史扣费和原 fixed_source_sha。使用新的 source SHA，证明首次可以进入，第二次消费同一正式授权会拒绝，错误案例/旧 observe_only 也不能冒充本次授权。
2. **统一策略和真实剩余：**实际 launcher 命令/环境进入 _V14Runtime、V20 resolver 与 Q4 预算选择/停止回调；验证总合同 172800 s、已有扣费后的剩余量、启动准备时间及零边界终止一致。PC 超过旧 30 s 不会单独误停；超过本轮实际剩余截止线必须停。其他历史 profile 行为不变。
3. **两条后处理路径：**缺少合格残差/完整场时，实际 service 的 held 路径不预留重型预算、不导入 FE、不启动比较；有合格元数据与保存文件时，经过真实 ready preflight、历史 POSTPROCESS_PARENT_FAILED 接续、预留、专用父进程监督、比较/独立 checker 命令编排及结算。用非 FE 哨兵代替数值叶节点，验证实际 supervisor 不因已有子进程再次失败。
4. **整段时间与裁决：**用可控非零准备延迟检查预留到启动的剩余更新和结束余量，避免遗漏或重复扣费；资源终止和异常也结算。让 checker 返回一次完成的负结果，确认主控不会将 supervisor/exit0 当精度 PASS。

只替换 FE/ABI 数值边界与必要外部系统 I/O，不把受审的 reservation、settlement、策略 resolver 或后处理准入替成恒定 PASS。fresh 进程设置导入守卫，实际不加载 dolfinx、basix、petsc4py、mpi4py，不创建网格、张量或矩阵；若入口当前不能到达可测试边界，允许最小提取纯控制函数，数值算法不动。单纯 --help、模块导入或函数名检查不足以称“完整启动契约通过”。

交付一个绑定最终源码/输入/旧账本 hash 的轻量收据，列出上述实走节点和替身边界。另按任务 activation 做正式 ABI preflight，不能把无 FE 测试当 ABI 资格。现有相关测试及改动触及的生命周期/文档检查在最终改动后运行；不因报告更新重跑昂贵 PDE。

**以上通过，执行方在同一轮直接进入第 3 节。**如果两轮局部修复仍无法穿过控制链，交付准确失败点并停止，不运行 PDE 来试启动，不追加第三轮、不只换报告编号继续。

## 3. Gx784：固定物理合同、固定验收、一次执行后收口

### 3.1 数学身份全部沿用 V5

| 项目 | 冻结值 |
|---|---|
| 输入 | input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_q4_review_v5.dat |
| 输入 SHA256 | 12f2e0dbed831f56c6e41133cdad292d0b70bea828087348ca8ede13142da422 |
| physical_model_sha256 | 2d9fa71c8781d96a75e07d0ef1636bbba05e38e50891cd0bcb6661e4059555d8 |
| mesh_plan_sha256 | 00760c10b132911a40c84ae5950742dcbd0086af2b26732be628ea08346b88d1 |
| 网格 | 14×4×14；原 x 界面 [0,16.5,25,33.5,50] 各段 4/3/3/4 等分后乘 7/135，y/z 精确复用 Gx |
| 物理 | 同一个缩小的非可分三维缺口；λ0.7、θ89°/掠角1°、φ0、s/E0=1、原 Si 材料/μ、Fresnel 背景、参考平面与周期/出射相位 |
| 离散 / 求解 | p6 / 原准确 p4 预条件，FGMRES32、max2048、零初值、原 p4 分解与精化规则、全 340 模式、MPI1/单线程 |
| 原始场复用 | Gx 与 F5 的既有保存场及 hash；不重跑基准，不读 F3/Gz 冒充两基准 |
| 输出隔离 | 同一 run_id 下新时间戳目录，执行前确认未占用；不得覆盖 20261003T074956.168518Z 的失败记录 |

这仍不是原尺寸网格。Gx784 维数低于已成功 F5 只是选择它的成本依据，不保证 LU 内存更小。V5 mesh 实现保留了材料界面，当前无需重新设计网格。

### 3.2 正式量及分母

| Gate | 不得改变的标准 |
|---|---|
| 求解 / 恢复 | 完整原 A6 显式真残差，包括释放后重验 ≤1e−6；原有 native/interior/Schur identity ≤1e−10、端口残差 ≤1e−8、有限数、MPC/slave 与全部内部恢复条件不变。p4 原 A4 目标 1e−10及原最多两次同因子精化规则不变，不额外改变旧 best-finite 处理 |
| 两组场 | Gx→Gx784、F5→Gx784；总/散射 E、H、直接 curl、scaled-curl 每项 ≤1%，用三场精确轴并集、每轴 7 点与相同公共材料体积 |
| 场分母 | 两组均为 V4 已归档 F5 同量范数，不能随新积分结果刷新。散射 E=0.8964588762723267，scaled-curl=0.8963653695824167；其他量从冻结接口取 |
| 11 个显著复模式 | 原冻结 keys 不变；Gx→Gx784 分母为 Gx 的首场幅值，F5→Gx784 为 F5；各最大复幅值相对差 ≤1% |
| 完整输出与功率 | 全 340 模式 real/imag/功率均保留；两对 R、T、A_balance、A_volume 绝对差 ≤1e−3；每个官方场能量闭合及两种吸收差 ≤1e−5；R00_s/p/total 分列 |
| 诊断 | 入射归一化绝对误差、统一 F5 模式分母诊断、材料分区贡献可输出，均不能替换正式门槛 |

保存场、比较结果和独立 checker 三者 hash 绑定。主控读取 checker 原始标量重算结果，区分 completed、solver_gate_pass、accuracy_pass；不换背景、不拟合相位、不删模式、不用功率闭合改判。源代码已有这一比较接线，优先复用。

### 3.3 时间、内存与结果分支

本例明确使用 enforce，覆盖旧 task/profile 中仅适用于历史运行的 observe_only；不将该覆盖推广到其他案例。**本轮不是再赠送一整段 48 h**：从同一共享账本剩余量中扣除新启动、求解、恢复、后处理、checker、必要清理成本；已知旧扣费不抹掉。本轮新增可测工程准备成本另列并纳入保守预算，不把历史未知清单时间声称已补齐。人工等待/审阅时间与实际执行阶段计时分列，不冒充 PDE 时间。

父监督从重型导入/JIT 前开始，所有后代受控；为终止、写出与结算预留时间，终止宽限不能外加到 172800 s 之外。一次完整新执行的 monotonic 时间及共享累计扣费分别记录，均不得越界；在实际剩余耗尽前停止完整进程组。无资源停止后的自动放宽时限/迭代数。

内存沿现有 physical-memory-pressure 政策。启动前冻结实际 RAM、cgroup 上限、其他常驻占用与正的系统/监督余量；允许的同时任务驻留必须使整机占用低于 min(实机物理容量、有效 cgroup 容量、2e12 B)。执行与后处理使用相同实际准入与零 swap 条件，不把 .dat 中旧 8/10 GiB 当本轮停止权威。记录 simultaneous process-tree/cgroup 峰值、系统基线/余量与 swap；进程树 RSS 不能冒称整机峰值。若主机已有无关 swap，不能宣称整机 swap=0，也不擅自关闭或清空它。一次只启动一个 heavy case，不干扰现有任务。

| 结果 | 本轮必须做完，然后停止什么 |
|---|---|
| 两对全部 Gate 通过 | tested_x_agreement_pass：只证明当前缩小三维模型、固定 y/z/p/M 下新增 x 分辨率一致；仍称 best available discrete reference。完成接口/成本收口，不追加 x/y/z/direct |
| 任一场或 11 模式 >1% | accuracy_not_closed；列最坏量、具体复模式/分母/限值及分区，保留旧 F3/F5 失败；不追加 x18/x20、p/M 或缺口扫描 |
| A6/恢复未通过或 max2048 | 没有正式物理精度结果，记录 solver_not_qualified；数值不收敛不是 bug 重试理由 |
| 再次入口失败、超内存/时间或中断 | 本轮正式额度结束。保存阶段、输入/源码、预算扣费、树清理和已有尺寸数据；未知结果保持 unknown，不再换编号启动 |
| 已有 Gx/F5 原始场不可读 | 按现有索引定位一次；找回失败则停配对精度 Gate，不重跑两基准。启动前已知缺失时不消耗唯一正式额度；保留已可独立完成的资源账 |

独立 direct 或 y 加密都不在本轮自动范围。只有新结果出现求解误差影响 1% 裁决的证据，才另选同离散参考；规则原尺寸在 φ0、沿 y 不变材料与均匀入射下的对称性可帮助决定是否需要 y 检查，当前缺口破坏该对称性，不能宣布缺口 y 收敛。生产算子继续保留完整三维、全部 q 与内部恢复。

## 4. AUTO 的新事实已经成立；接下来补成本，不再生成库存

### 4.1 接受并复用现有清单

V5 收口记录、生成源码与两份清单记录一致：**32,060 个完整有序通道**，最大 |m|/|n| 为 142/35，文件 36,244,923 B。原版和修复版 manifest SHA256 均为：

52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d

有序 [side,m,n,polarization] 键 digest 为：

03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec

文件分别位于 benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/ 与 target_ledger_v5_repair/ 的 original_size_auto_mode_manifest.json；完整路径/源码及配套账本 hash 见[收口记录](outcomes/records/review_v5_execution_closeout_v1.json)。此身份是原尺寸外部材料、入射及端口库存；不证明内部缺口模型或网格已资格化。旧 dot 库存没有有序 digest，只能作计数一致性对照。

本审阅核对了已提交记录与生成器的序列化方式，未重读 ignored 原始字节。执行方直接读已有文件一次，核验 SHA、32,060 行及顺序键 digest：JSON 的键列表按 ensure_ascii=False、separators=(",",":") 编码后取 SHA256。随后原样复用/移交；**不要调用 run_task40_v5_target_ledger.build/main 再生成一份**。路径失效先依索引查找，丢失则报告丢失，不默默再造后改写身份。

### 4.2 已知载荷与剩余实测

这里的“载荷”只是数组本身的字节数；求解器的临时数组、稀疏填充、共享/复制和并存会改变峰值。

| 已知 derived 量 | 字节 / 数量 | 限制 |
|---|---:|---|
| 单个 AUTO 原 H 对角 / 稠密 H | 512,960 / 16,445,497,600 B | 只说明一个矩阵的表示节省；Hhat 的内部修正和并存未计清 |
| 一个 p6 单元原张量 / 内部 LU 形状 | 12,446,784 / 3,240,000 B | 882² / 450² complex128，不含 LU 额外工作区及类数量 |
| trace Schur / 单份耦合或恢复项 | 2,985,984 / 3,110,400 B | 432² / 450×432；共享、方向类、twist 实例数量未知 |
| 272×4×14 计数候选 | 15,232 单元；p6 full=10,228,620，interior=6,854,400 | 仅计数候选，不是原尺寸合格网格 |
| 该候选的 p6 retained / p4 interface（含 AUTO） | 3,126,332 / 1,346,364 | 不含分解填充 |
| 该候选 74 个 outer 向量 | 3,701,577,088 B | 33+33+8；source-formula 估计，不是 RSS |
| retained/full scratch | 4,428,003,200 B | 与前项生命周期重叠未知，不直接相加当同时峰值 |

原尺寸成本账继续写入现有 TARGET_LEDGER 体系，不再建立一套平行账本。主线立即将已有公式/对象登记与缺项关联；本次 Gx784 顺带保存既有资源采样和实际对象生命周期，不能按其 RSS 线性外推原尺寸。dot 填下表的专属实测：

| 尚缺项 | 下一项可验收交付 / 负责人 |
|---|---|
| 求积与冷 JIT | dot C2：实际 compiled nodes/weights、kernel/cache 大小、编译子进程峰值及冷时间；order142 对 p4/p6 的名义 degree156/160、79²/81²点只是公式预测 |
| C/D、Di/XiB 与 H/Hhat | dot C1/C2：真实支持类维数、NNZ、共享/借用/复制、原 H 与内部修正全部生命周期，不把小耦合裁零 |
| 内部恢复缓存 | 双方各自已有实现：唯一几何/材料/方向类、每 twist 实例、450维内部因子与恢复工作区，完整 RHS 和恢复批次 |
| 投影临时矩阵 | dot C2：最大 lp×rq、16lp·rq B、中间乘积、COO→CSR 与累加的同时驻留；源码仍有 projected = dual_di @ xib_primal |
| 全部 q 因子 | dot C1c/C2：每块输入 NNZ、真实 L/U fill、backend/order/pivot、workspace、所有因子同时驻留；512 MiB 策略额度不是测量值 |
| 外层与完整原方程 | 主线总账：FGMRES 两组基向量、完整 action/RHS/残差、PC 应用耗时与迭代数，不能只算一个 H 或一个 q |
| 输出 / 校验 / 系统 | 主线汇总双方收据：恢复写出、原始数据缓冲、checker 与缓存重叠、OS/监督余量；完整必要时间，未知项不填 0 |

已知数组规模无法回答“2 TB 是否够”。准入需在同一生命周期上计算最大同时占用，再以实际进程树/cgroup和系统记录校准；不能相加独立阶段峰值，也不能遗漏常驻因子。当前网格精度、AUTO 截断/接线、整数范围、填充、外层迭代和完整时间不足以给原尺寸运行许可。

## 5. dot 的互补任务：已有候选直接进入有保存条件的真实资格

dot [V15](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/response_v15.md)的 X/XZ/Y 是已发布旧环境小尺度 p4/532 历史证据，120/168/120 单元不代表原尺寸；Y 缺口有周期移位，也不是主线 y 精度对照。旧低内存组件/532分解前对照与只读 pivot 崩溃、修复后中断分别保留，旧最终 checker 仍 UNKNOWN。

[新检查点](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/records/fresh_c1_source_v1/source_checkpoint.json)明确 raw_artifacts_durable=false、storage_approval_pending=true、FE_JIT_p6_component_p4_chain_NOT_RUN=true。79 项是新非 FE 测试；不再沿用旧合同“官方源不可达、没有环境”的过时状态，也不把安装成功写成 FE 数学通过。新环境为 Python3.12.13、DOLFINx/Basix0.10.0、MPC0.10.5、PETSc3.25.6 complex128/int32、MPICH5.0.1 的 MPI1 资格。

恢复合同 [portable_retained_h_qualification_contract_v1_zh.md](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/portable_retained_h_qualification_contract_v1_zh.md)和[remaining gaps](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/original_target_remaining_gaps_recovery_v1_zh.md)的数学/容量要求继续使用；运行时和 AUTO 库存状态以上述新事实更新。精确恢复的 H 源码、重新构造的 candidate、旧已发布标量证据与缺失 raw 分开标记，不能相互继承 PASS。

| 顺序 | 具体任务与通过标准 | 不代表什么 |
|---|---|---|
| C0 保存验证 | 用户确认持久 raw 目的地/方式；用小归档完成保存、取回到空目录及成员 hash 验证，再开始昂贵 FE。每个正式阶段的 raw、输入/源码/环境/worker/checker 收据也必须保存并取回验证 | 当前报告不代替用户确认，也不要求主线等待 |
| C1a p6 组件 | 已有入口在同一实际 full3D 80 单元/532端口载体比较 dense 与 compact H/Hhat，全部36,000内部自由度、任意非零内部及端口 RHS、完整恢复/MPC；独立原始张量 checker。action/recovery≤1e−11、制造解原方程残差≤1e−10、纯代数≤1e−12；近零补充门不替代原门 | 制造解及组件通过不是物理 p6 全局迭代解或原尺寸精度 |
| C1b p4 稠密端口参考链 | 绑定同一新环境/依赖源码的 C1a 收据；同一80单元fixture、全部4个q、532模式、8,640内部 RHS、四种载荷，regular/notch 完整原方程、恢复和全输出，沿用原数值门 | 稠密的是端口参考表示；FE/q 使用既有稀疏路径，不是全局稠密 FE direct，也不是紧凑链资格 |
| C1c 紧凑分块完整链 | 在同一 fresh p4/532 fixture 接入两单元紧凑参考构造，全部 q、内部恢复、regular/notch 与 C1b 完整向量/模式对照。当前 CLI 只有 p6-component/p4-chain，允许最小接线后做这一项，不假装已有现成 PASS | 不能把 C1a 或 C1b 的通过代替 C1c；不新增 p6 全局全链试验 |
| C2a 公共后端 | 先实际 complex 非 Hermitian 小块，再同一已合格 q 块与参考比较；记录因子填充、全部驻留、setup/回代和整数宽度 | 公共 API 可导入、MUMPS enabled 不代表实矩阵通过 |
| C2b AUTO 成本探针 | 使用主线已存完整32,060清单及其精确物理身份；完整模式映射参数化通过后，至多上下介质各一个代表面和一个最大支持内部修正类，p4/p6各需的求积/投影成本。全 keys 覆盖，可分批，不删模式；覆盖不足则不给全局上界 | 不构造原尺寸全体积、不做目标规模 LU，不把532扩展断言简单删除 |

每 worker/checker 仍 **≤3 GiB=3,221,225,472 B、≤4500 s、MPI1/threads1、swap0**；不足实机余量时收紧。另留128 MiB证据余量，未压缩 raw≤512 MiB、可用磁盘≥2 GiB；p4四因子512 MiB仍只是策略上限。每阶段 worker、独立 checker、持久取回都通过后才前进；本轮每阶段最多一次明确实现 bug 的修复重放，最多两轮局部修补/测试，不因数值失败、预算耗尽或环境中断自动重试。既有同依赖 hash 的资格不因文档改动重跑。

公共 PETSc setup 的 symbolic/numeric 可组合发生，应按实际公共 API 的可控边界记录，不伪造独立 analysis PASS、不使用私有 ctypes 绕行。int32 的 rows/NNZ/indptr/offset 要在分配、narrowing 和后端转换前核验，不能仅凭 PETSc 类型推断后端容量。

主线继续拥有精度与统一接口，dot 继续拥有紧凑端口、周期参考构造、存储与后端校准；不移植重写已有 dot 实现。沿用[四角接口包](outcomes/records/review_v4_four_corner_interface_v1.json)，主线 φ0/340 与 dot φ5/532 不直接比复数值；映射完整模式顺序、Bloch/出射基、参考平面、背景、相位、H单位和内部/端口排列。C2 原尺寸 φ0 清单另绑其物理身份，不能偷偷塞进 φ5 的旧fixture。

## 6. 最短路线、失败出口与交付

最短可检验路径是：**主线一次启动接续修复 → 一次 Gx784 新解及两对比较；独立复用 AUTO 补账。dot 保存获准后按 C1a→C1b→C1c→C2 取得互补证据。**不再生成同一库存，不在等待期间重复79测试、安装环境或重做旧小尺度扫描。

[Review V5 第6节](review_report_v5.md#6-历史路线核对复用成果保留失败)的历史路线台账继续有效：task035 的 residual 自适应不优，DWR 有过收益但不是当前最优；task035b 分区阶次/轴向路线有未过门记录；task39extra 宏块精确 Schur 内存与近似粗逆负结果保留；主线背景归因、M扩展、四角已完成。不得重做这些路线来回避当前1%失败。两单元参考逆与紧凑存储改变求解成本，不改善离散精度。

**目前主线全局准确 p4 加云端稠密端口参考链，没有足够证据支撑原尺寸目标。**紧凑路线确有减少原 H 和重复参考构造成本的依据，仍缺实际投影、fill、全部q驻留和时间证据；不能宣判必败，也不能称已可上工作站。只有对应瓶颈出现才选以下一个出口，不是自动追加许可：

| 实测瓶颈 | 有依据且不重复旧失败的后续方向 |
|---|---|
| 投影稠密临时矩形先超限，而完整稀疏输出可容纳 | 精确分片生成同一完整投影矩阵，保留全部模式/内部修正，以 C1b/C1c 原方程和全输出反证；不做裁零或低秩改物理 |
| 每个 q 可容纳、全部因子并存超限 | 先只核算受限因子批次/精确重算的存活时间与重复分解总成本；48 h不成立就否决，不直接运行 |
| 单个 q fill 或完整时间已经不成立 | 明确该参数下当前精确参考逆路线不支持目标；后续从已登记但未实测的局部加递归物理粗纠错中另冻结一个反证实验，不能重开旧宏块/BLR/低阶扫描 |
| Gx784精度仍未闭合 | 根据本次最坏场/模式及求解误差证据提出一个下一选择，需另定范围；本轮不自动新增网格或独立参考 |

执行交付不应再只有报告：主线优先交 **真实启动契约收据、一次新执行（或明确受控停止）、两对比较/独立 checker、复用清单后的成本账增量**。将成功、超限和失败写入下一 response、既有 summary/run_index/模型总账，保留原始失败文件和 source/input/environment/raw hash；给出本轮新成本、旧累计成本与仍未知成本。dot 各阶段独立交 worker/checker/持久证据，不由主线写 dot 分支。

正式执行前若存在活动任务或未提交更改，先核对接续，使用 canonical clone 已登记工作树安全拉取报告，不 reset、不覆盖、不重启相同 case、不干扰其他作业。报告提交仅含本文；无 master 合并、无 merge approval。本次未运行本地测试；网页渲染尝试及远程提交核验在提交回执单列，文本结构核对不替代这些 Gate。

待确认事项只有各自依赖项：dot 持久 raw 方案由用户确认；本机 Gx/F5/账本可读性与实际资源由执行方核实；原尺寸合格网格、完整AUTO资格、因子/后端/时间仍需后续实证。前两项的阻塞不应扩散为整条项目停摆。

## 7. 可直接交给主控 Codex 的执行文本

> 在 canonical clone 已登记的 task40extra_0p7nm_engineering 工作树安全取得并完整读取 docs/task40extra_0p7nm_engineering/review_report_v6.md。主线审阅基准 b8bd7c2f23726142161b58a7d7ff52275ea677ba，dot只读基准 eb5b0ecc1afe593f626b44a6038f7f26651b3317。保留活动任务、旧失败、原输入及旧账本，不修改dot/master、不merge、不重跑Gx/Gz/背景归因，不再生成AUTO清单。
>
> 先按报告第2节修通历史fixed_source_sha与新授权分离、POSTPROCESS_PARENT_FAILED续作和完整截止时间；复用真实旧账本副本，以不加载FE的实际launcher→worker→Q4控制链和ready/held后处理集成检查验证。最多两轮局部修补/定向测试；不得stub预算/策略/结算来宣称全链通过。通过后提交冻结源码及收据，按activation做ABI和实际内存准入，直接使用V6新增的一次授权执行同一Gx784，不必再等审阅。输入SHA=12f2e0dbed831f56c6e41133cdad292d0b70bea828087348ca8ede13142da422；14×4×14、p6/原准确p4、340模式、材料/背景/相位全部不变；同run_id新时间戳输出，不新增第二网格。再次启动失败也耗尽本轮正式额度。
>
> 复用Gx/F5保存场完成两对比较。完整A6显式残差≤1e−6，恢复/identity沿原合同；场每项≤1%，分母用冻结F5；11个显著复模式≤1%，分母分别为首场Gx/F5；功率差≤1e−3、能量≤1e−5。诊断归一化不能替门，保留原2.611883%/2.750374%场差及1.555605%模式差。通过只报tested_x_agreement_pass；数值失败、max2048、资源停止或新入口失败均收口，不自动补网格/direct/y/p/M。仅后处理实现bug最多一次独立修复重放，不重跑PDE。
>
> 共享172800s预算保留已扣4.619253995631944s，计入新增准备、JIT、装配、分解、求解、恢复、输出/checker及清理，旧AUTO生成耗时仍unknown；本机按实际physical-memory-pressure与系统余量、整机≤2e12B、swap0执行，时间/内存耗尽前清理整个进程组，一次一个heavy case。直接读已有AUTO32,060清单，核对报告中的manifest/key SHA，补C/D、恢复、投影、H/Hhat、全部q填充并存、外层/输出/系统成本，禁止RSS线性外推。
>
> dot由其执行方在用户确认持久保存并完成取回验证后，依次C1a真实p6组件→C1b p4全q稠密端口参考链→C1c紧凑分块完整链→C2公共PETSc及有界AUTO成本；每worker/checker≤3GiB/4500s、MPI1单线程swap0。失败停下游，旧checker UNKNOWN与新FE NOT_RUN不得继承PASS。主线不等待保存决定。原尺寸大规模求解继续NO-GO。完成或达到停止条件后提交下一response、既有summary/索引和真实证据，推送同一主线分支，返回完整执行SHA及结果，不自动开始下一轮。
