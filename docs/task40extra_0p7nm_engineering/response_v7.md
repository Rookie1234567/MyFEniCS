# Task40 Review V7 执行回应（进行中）

**状态：W0 本次尝试已在 FE 前受控阻塞收口；Task40 Review V7 整体仍在进行中。** 原生独立 ABI 与身份审计原始收据已核对通过；固定在已审阅 source `5be1210aa79f25c13a7677cc291a4a766a548650` 的实际导入闭包因缺少 `pyvista` 失败，FE 未开始。没有 worker/checker、PDE、残差或 raw 场。这是 FE 前入口阻塞，不是数值失败，也不构成任何数值阶段通过。W1/W2 保持 `not_run`，原尺寸完整求解继续 **NO-GO**。

## 当前执行状态

| 阶段 | 状态 | 已有证据与边界 |
|---|---|---|
| 原生 ABI 与 prefix 身份 | `PASS; no FE action` | 原始 `workstation_abi.json` 与 `abi_identity_audit.json` 均在 packet 中逐成员核验；ABI receipt SHA256 `4ef26bf3d4ea0b3c16170b030694e7de7a303108e5fd78b3309835d0c4aa5102`。它证明隔离 native prefix 的 ABI 身份，不代表 FE/求解通过。 |
| 宿主资源/空闲窗口 | `HELD; NOT_ATTEMPTED` | 03:35:29Z 快照 `MemAvailable=2,089,370,224 KiB`（约 `2.1395e12 B`），没有显示容量不足；Task42 进程组在 03:34:11Z 前后已不见，Metrology 训练仍活动，因此本次没有完成合同要求的空闲重型作业窗口资格。此状态是窗口未准入，不是已测容量失败。宿主 SwapUsed 基线/末次观测均为 21,600 KiB；基线时间缺失，相等读数的 0 KiB 差值只是 derived，不能归因给 Task40。`pswpin/pswpout` 初始计数未采集，增量为 `null`。 |
| W0 λ0.7/p6 导入闭包 | `BLOCKED_BEFORE_FE` | 三个浅导入预检通过后，实际命令 `python -c 'import src.solvers.dtn_port_3d'` 于 2026-10-04T03:24:37–38Z 在 source `5be1210…` 上沿 `dtn_port_3d → common_3d_utils → solve_vector_maxwell → postprocess → pyvista` 因 `ModuleNotFoundError`、exit 1 停止。FE start event 为 `NOT_REACHED`；W0 component、dry admission、worker、checker、physics、raw archive 均为 `NOT_RUN`。控制端在 FE 启动截止时间 2026-10-04 10:07:14 UTC 前已报告未能启动 FE。trace SHA256 `343939c7bec310f03c05134763e4aef504d9997abb40f06956bdb08dcf2af01a`，closure receipt SHA256 `64f65b92b8379c432cf87c6f6d97b62108236e67512eade1699b22cdde9c20b7`。 |
| W1 原尺寸 AUTO 端口/局部修正成本 | `not_run`（有条件） | 必须先有 W0 数值通过；主线目前没有可运行的完整 W1 入口。只准备最小接口和缺口，不提前实现或运行。 |
| W2 全阶 p6 周期参考对照 | `not_run`（有条件） | 还需 W0 本机资格、dot C1c raw 和新的完整 p6 链入口；p6 component probe 不等于完整求解链。 |
| 50×25×140 nm 原尺寸完整求解 | `NO-GO` | 完整 AUTO 接线、全部 q 因子及并存、完整 p6 恢复、原尺寸精度与端到端成本均未闭合。 |

原生 packet 的 packet SHA256 为 `4c98a859a265bb942cc2eb3e37cead21f0fafd2251574bbe742f1cef61cf4d3d`、113,898 B，19 个成员的 UTF-8 字节数和 SHA256 均已独立核验。控制端报告的持久副本路径为 `/home/fenics/.local/share/mamba/task40extra_w0_root/evidence/native_w0_handoff_4c98a859/handoff_packet.json`，其回读 stdout 已单独保存并标明来源；本地又从 `/tmp/task40_native_handoff_4c98a859.b64` 解码、核 hash 后写入 ignored artifact。完整包和全部成员在 `benchmarks/artifacts/task40extra_0p7nm_engineering/native_w0_handoff_4c98a859/`；13 份轻量原始 ABI/audit/import/resource/host 身份收据在 [W0 收据索引](outcomes/records/native_w0_handoff_4c98a859/handoff_index.json)。较长安装日志、包清单和辅助脚本只保留在 ignored artifacts，由索引列出各自 SHA，不复制 timeline。

W0 的实际入口阻塞和 resource-window 状态是两个不同结论：主要复现阻塞是冻结 source 的 `pyvista` import 闭包失败；资源窗口则因 Metrology 训练仍活动而保持 `HELD/NOT_ATTEMPTED`。大约 `2.1395e12 B` 的 MemAvailable 快照不支持“内存容量不足”结论；宿主 SwapUsed 快照也不是 Task40 进程树 swap。Task42 已不在末次观察中，不能继续写成仍活动。没有 W0 worker/FE/checker PID，因此没有本任务进程子树需要终止或清理。

本次完成到 native ABI/identity audit 和固定 source 的导入闭包检查，仍有三个缺口：固定 source 的入口闭包未通过；本轮没有完成空闲重型作业窗口资格；W0 FE component 因此前两项没有运行，故无数值结果。新 source `077ec9c8386c976da232093779279fb9d1a93033` 还包含方向字节 authority/checker 变化，超出窄导入修复；其授权仍待人类答复，主控的静态审阅不作为新授权。本轮没有安装 PyVista、修改 solver source、重跑或换 source。

可证的时钟字段只支持局部边界：prefix transaction UTC 起止为 `03:11:47Z–03:12:22.313564304Z`，receipt 给出的 `34.489 s` 是 derived 子区间；从 transaction 开始至 import blocker 的 `771 s` 也由 UTC 边界推导。完整准备起点无耐久时间戳，整体准备时长、W0 monotonic/boottime 用时及预算扣款均为 `unknown/null`，不得记零或用秒级 UTC 窗口替代。V7 总上限 43,200 s，W0/W1/W2 上限 14,400/7,200/21,600 s；V6 历史 settled debit 5,428.582334 s 未改。

## AUTO 清单与离散成本账

没有重新运行清单生成器。复用已有 original/repair 两份 36,244,923 B 清单；两份文件此前已核验字节一致。身份为：32,060 个有序模式 key，全部 classified propagating，最大 `|m|=142`、`|n|=35`；manifest SHA256 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`，ordered-key digest `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec`。它只证明原尺寸端口模式库存身份，不证明体网格、离散精度或完整求解可行。

主线唯一计数候选沿用 0.7 nm 电尺寸与 Gx784 的 x 分段：x 各段 78/58/58/78，共 272；y=4、z=14，合计 15,232 个六面体。候选几何为周期 50×25 nm、z∈[-10,130] nm。它是计数与成本候选，尚未生成或资格化为 FE 网格。

| 对象 | 数值 | 分类与限制 |
|---|---:|---|
| p6 full / periodic independent / interior DoF | 10,228,620 / 9,948,672 / 6,854,400 | `derived`，来自现有单元基维数及 32,060 模式数；不是已组装矩阵行数 |
| p6 trace + 实际 AUTO ports；p4 interface + ports | 3,126,332；1,346,364 | `derived` 候选行数；不含分解填充 |
| 单个 p6 full / retained complex128 vector | 163,657,920 / 50,021,312 B | `derived` payload |
| FGMRES(32) 74 个 retained vectors；retained/full scratch | 3,701,577,088；4,428,003,200 B | `derived` payload；生命周期和相互重叠未知，不能相加称作 RSS |
| 一个原 H 对角 / 稠密 H | 512,960 / 16,445,497,600 B | `derived` 单对象字节数；Hhat 修正和共存未测 |
| p6 单元局部张量；内部 LU 的 dense shape | 12,446,784；3,240,000 B | `derived` 单实例 shape；并非实际稀疏因子或工作区 |
| trace Schur；每份 450×432 耦合/恢复 shape | 2,985,984；3,110,400 B | `derived` 单实例 payload；局部类别数、共享和生命周期未知 |
| p4/p6 面求积 | max_order=142；公式阶数 156/160，名义 79²/81² 点 | `derived`；实际 compiled points/weights、冷 JIT 时间和峰值未知 |
| `Di/XiB`、Hhat、完整端口支持、全部 q 因子及 backend workspace | — | `unknown`；没有对应构建/分解实测，未知值不记为零 |

旧 AUTO 账本中的 WSL 系统快照时间为 2026-10-03 07:27:20 UTC（总内存 14,654,988,288 B、当时可用 13,156,769,792 B）；它是 `measured` 的历史 WSL 快照，不代表当前 WSL，更不代表工作站。原尺寸资源准入必须使用工作站当次整机/cgroup/进程树收据。

## W1 最小接口方案与缺口

只在 W0 真正通过后，考虑用通用 `src` 的现有端口/局部凝聚 API 加一个薄 runner；不复制数值算法、不造全体积矩阵或目标 LU。实际入口第一步必须读取已保存的 original-size manifest 字节与有序行，核对其 SHA、32,060 keys 和 ordered-key digest；不得调用 `build_dynamic_mode_inventory` 或任何清单生成器重生成库存。当前没有把已保存 manifest 直接读成运行时 `PortMode3D` 的薄适配器，这是待补的最小接线。现有 `build_ordered_mode_manifest` / carrier API 只可用于核对由存档行解析出的 key 顺序和身份，不能代替读取清单。p4、p6 分别在原尺寸上下边界使用 `_ReusableSurfaceComponentAssembler`，以完整 32,060 keys 构造真实稀疏耦合/投影项，记录每个 key 的支持、数值摘要、字节、构建时间和别名/参考平面身份；完整集合可以分批处理，但不得抽取小 M 冒充完整 AUTO。

先固定一个对两侧介质、两种偏振及 alias/gamma 伙伴闭合的小完整 key 组，与现有显式表示做精确 action/恢复对照（≤1e-11）和相关原方程对照（≤1e-10）；完成后才进入全 keys 成本测量。再选实际 p6 中支持最大的一个局部修正类，记录真实局部张量、`Bi/Di`、`XiB`、`Di @ XiB`、任意内部 RHS 恢复、数组借用/复制及释放时刻。必要时将 `P6CellCondensedAction` 或 `condense_physical_cell_blocks` 接入该单一对象，p4/p6 使用相同冻结物理对象。

当前可复用代码有 `fullspace_dtn_action.py` 的 carrier/action、`dtn_port_3d.py` 的 surface assembler，以及 `p6_cell_condensed_action.py` / `hcurl_assembly_time_condensation.py` 的局部消元 API；但仓库没有符合本合同的 W1 runner、真实 `--help`、无 FE 控制链检查或完整 keys 对照收据。现有 carrier builder 会累计分量缓存和模式级 entries，carrier 再校验、排序并保留各模式稀疏项；action 的批量处理不能证明构建峰值有界。更关键的是，单个完整 32,060×32,060 complex128 的 `Di @ XiB`/`Hhat` 结果需要 16,445,497,600 B；W1 总限额只有 17,179,869,184 B，留下 734,371,584 B 容纳其余所有输入、借用数组、BLAS 暂存、输出和 checker，因此不得直接物化该完整方阵。分配前必须把这些同时存活对象整体纳入 Gate；只有已存在的受限作用/因子表示能在预算内产生完整 keys 的真实成本证据时才使用，否则如实 `controlled_stop`，不得新增投影器或第三条数值路线。局部最大支持类从 production compiled form 到真实 W1 数据的接线也尚未闭合。

W1 整组（准备、冷 JIT、p4/p6 对象、checker、写出）累计 ≤7,200 s、任务树 ≤16 GiB（17,179,869,184 B）、MPI1、单数学线程、swap=0；最多两轮局部接线/定向测试。每次全 keys 构造前须有实际 workspace/其他作业余量的分配 Gate。缺少容量证据、超过边界或索引宽度不安全均受控停止；不得扩成第二个面、网格或参数扫描。

## 验证与后续

本地资格化 WSL preflight 最终通过：原始 `sys.executable` 位于仓库 `.venv`、`sys.prefix` 与该环境一致；PETSc complex128/int32，PETSc/SLEPc/DOLFINx/Basix/mpi4py 均为 Linux ABI 路径（PETSc/SLEPc complex3.19、Open MPI 4.1.6、MPI1）。此前两次 preflight 都因我写的断言口径错误在 pytest 启动前停止：第一次错误要求解释器符号链接的最终目标仍位于 `.venv`，第二次错误要求 SLEPc 使用 PETSc 的安装根目录；实际为标准 venv symlink 和独立 `/usr/lib/slepcdir` 前缀。它们不是仓库环境失败，耗时没有 monotonic 收据，记为 unknown。修正后文档合同测试 24 passed（pytest 报告 0.06 s）。这只是本地文档检查，不是工作站 W0 资格。没有运行 FE、MPI 多进程、全仓 pytest 或昂贵 Gate，也未改写 V6 账本。原生完整 packet 已以 4c98a859… SHA、113,898 B 和 19 个逐成员 SHA 核验，native ABI/identity、导入链与末次资源快照原始收据见 [W0 收据索引](outcomes/records/native_w0_handoff_4c98a859/handoff_index.json)。控制端回读路径的完整 packet 位于 ignored artifacts；轻量 raw receipt 在本目录；长安装日志和 package inventory 留在 artifact 并有 hash index。Task42 process group 在末次快照前已不见，Metrology 仍活动；空闲重型工作窗口保持 `HELD/NOT_ATTEMPTED`，并非内存容量失败。W0 固定 source 的导入闭包仍缺 `pyvista`，本次没有启动 FE 或清理任何 W0 进程子树。source `077ec9c…` 的人类授权仍未解决；本轮停止，不自动换 source、不等待训练结束，也不重放。W0 总耗时/预算扣款仍为 `unknown/null`；V7 的 W1/W2 保持 `not_run`，全尺寸仍 **NO-GO**。Gx784 身份已作为独立 x-refinement 对照接入四角接口包旁的 V7 link 记录，原四角签名和四角结果保持不变；run index、outcomes summary 和 V7 增量账已同步。当前回应是 FE 前受控阻塞记录，不是 V7 数值通过、最终审批或 merge 请求。
