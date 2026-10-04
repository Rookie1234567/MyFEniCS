# Task40 Review V7 执行回应（进行中）

**状态：本轮尚未收口。** 已复用原尺寸 AUTO 清单并复核计数候选和已有对象账；原生执行窗口仍在做只读宿主/环境核验。W0 的实际 FE 尚未启动，W1/W2 均为条件性 `not_run`。这些状态不表示数值失败，也不构成任何阶段通过。原尺寸完整求解继续 **NO-GO**。

## 当前执行状态

| 阶段 | 状态 | 已有证据与边界 |
|---|---|---|
| 原生工作站准入 | `in_progress` | 控制窗口报告 CPU 完整 x86-64-v4 特征核验通过；宿主最终资源、隔离 prefix 和 ABI 收据仍待执行窗口提交。已有其他重型作业在运行，故不启动 W0 FE。 |
| W0 λ0.7/p6 组件 | `not_run`（准入等待） | 专用原生窗口正在检查环境和活动作业；没有 worker/checker、FE residual 或 fresh raw 结果。截止实际 FE 启动时间为 2026-10-04 10:07:14 UTC；没有把导入或 dry-admission 当 FE。 |
| W1 原尺寸 AUTO 端口/局部修正成本 | `not_run`（有条件） | 必须先有 W0 数值通过；主线目前没有可运行的完整 W1 入口。只准备最小接口和缺口，不提前实现或运行。 |
| W2 全阶 p6 周期参考对照 | `not_run`（有条件） | 还需 W0 本机资格、dot C1c raw 和新的完整 p6 链入口；p6 component probe 不等于完整求解链。 |
| 50×25×140 nm 原尺寸完整求解 | `NO-GO` | 完整 AUTO 接线、全部 q 因子及并存、完整 p6 恢复、原尺寸精度与端到端成本均未闭合。 |

控制窗口报告的宿主 CPU 核验和活动作业状态尚未由本机最终收据闭环；原生 ABI、实时内存/cgroup/swap、可用余量及实际进程树均记为 `unknown`。当前 W0 仍固定在已审阅的 dot source `5be1210aa79f25c13a7677cc291a4a766a548650`。控制窗口发现新 source `077ec9c8386c976da232093779279fb9d1a93033` 不止修复 PyVista 导入，还改变原生方向字节 authority/checker；历史 raw 与云端测试日志已丢失，不能继承 C1 通过。该改动超出窄修复范围，source 升级授权尚待主控/用户明确决定，因此不使用新 source，也不把它当成 FE 资格。此前本地 WSL 的 PETSc3.19/OpenMPI4.1.6 和旧内存快照不代替工作站证据，也不用于 W0 准入。Task41 的 dirty 工作树保持不动。

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

本地资格化 WSL preflight 最终通过：原始 `sys.executable` 位于仓库 `.venv`、`sys.prefix` 与该环境一致；PETSc complex128/int32，PETSc/SLEPc/DOLFINx/Basix/mpi4py 均为 Linux ABI 路径（PETSc/SLEPc complex3.19、Open MPI 4.1.6、MPI1）。此前两次 preflight 都因我写的断言口径错误在 pytest 启动前停止：第一次错误要求解释器符号链接的最终目标仍位于 `.venv`，第二次错误要求 SLEPc 使用 PETSc 的安装根目录；实际为标准 venv symlink 和独立 `/usr/lib/slepcdir` 前缀。它们不是仓库环境失败，耗时没有 monotonic 收据，记为 unknown。修正后文档合同测试 24 passed（pytest 报告 0.06 s）。这只是本地文档检查，不是工作站 W0 资格。没有运行 FE、MPI 多进程、全仓 pytest 或昂贵 Gate，也未改写 V6 账本。下一步等待原生窗口给出 host、活动任务、隔离 ABI 和 W0 实际 FE 收据；只有 W0 通过后才开启 W1。若 W0 在期限前不能安全启动，后续 response 更新为精确 blocker 与 `not_run` 证据，不把资源等待说成数值失败。Gx784 身份已作为独立 x-refinement 对照接入四角接口包旁的 V7 link 记录，原四角签名和四角结果保持不变；现有 run index、outcomes summary 与 V7 增量账已登记本轮状态。工作站收据到达后仍须更新同一 response 和索引再收口；本文件当前为进度记录，不是最终审批或 merge 请求。
