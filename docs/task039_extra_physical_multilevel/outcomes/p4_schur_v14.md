# Task39extra Review V15 增量：R0 宿主存储 Gate

本次增量的最终状态为 **`INFRASTRUCTURE_BLOCKED`**，不是算法失败。R0 在受限 sandbox 视图中完成了两个父目录、四轮共 `16777216 B` 的原子写入/重开哈希/目录 `fsync`/自身清理探针；但宿主范围核验确认承载 Ubuntu-24.04 WSL VHD 的 Windows `C:` NTFS 卷只剩 `827174912 B`。健康状态 `Healthy/OK` 不消除这个持续性空间风险，因此没有进行 R1 账本迁移、恢复 Q0 或任何正式 PDE。

| V15 项目 | 结果 | 解释 |
|---|---|---|
| 宿主身份 | Ubuntu-24.04 → `C:\Users\admin\AppData\Local\wsl\{bb298883-9031-4854-a46f-fe067cfd0cb8}\ext4.vhdx` | 路径是 VHD 身份；`407550365696/827174912 B` 是承载它的 C: 宿主卷容量/余量，不是 VHD 文件大小 |
| 当前旧 Q0 进程 | `old_q0_matches=[]`；33 个数值进程条目 | 当前未发现旧 Q0 活跃匹配；`historical_cleanup_proven=false`，不证明历史清场 |
| ledger | SHA `b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0`，前后不变 | snapshot 为 `old_ledger_snapshot.json`、mode `0444`；`RESERVED/active_attempt=0` 仍是未结算状态 |
| R1 / new Q0 | `not_run` / `0` | 没有正式政策扣账、没有新的 Q0、没有新的 PDE |
| 已知基础设施收集时间 | `2.387310507 s` | sandbox UTC 区间 `0.497441 s` 加宿主只读 UTC 区间 `1.889869507 s`；不是正式 PDE 费用 |
| 历史日志边界 | `incomplete` | 旧窗口命令没有明确 UTC 基准，不能证明覆盖 `2026-09-12T12:35Z` 故障窗口；journal/orphan 行不证明 EIO 根因 |

Review V15 规定的旧 `600 s` 只作为不返还的政策预算责任，本轮未写入真实 ledger；旧实际耗时仍 `unknown`。因此已知最低责任为 `602.387310507 s`，剩余只能写成 `42597.612689493 s` 上界，不能作为启动许可。Q0–Q6 均为 `not_run_by_infrastructure_gate`；V14 的 partial setup、parent `EIO`、缺失终态和 Q1/Q2 不可用记录保持原判定。

完整状态、原始报告和所有 hash 见 [response_v16](../response_v16.md) 与 [V15 I/O compact](records/v14_io_recovery_v15.json)。本页以下的 V14 内容是历史证据，不被本增量覆盖。

# Task39extra Review V14：Q0–Q2阶段证据

本页只登记现有运行目录和审计结果，不把未完成的 Q0 变成通过，也不把 Q1/Q2 缺失写成数值失败。Q0–Q2 的机器记录见 [compact](records/p4_schur_v14_compact.json) 和 [comparison](records/p4_schur_v14_comparison.json)。Q3–Q6 仍是待继续的工作，不在本页提前结项。

## 当前结论

准确 Schur 对照要求把体内未知量消元，再保留接口体积 Schur、原 80 个端口和所有内部/接口因子；它只有在 Q1 全局直接法和 Q2 准确 Schur 都完成、精度门槛相同且经历同一清理流程后，才能回答是否省内存。本次没有得到这组配对数据，因此当前答案是 `COMPARISON_INCONCLUSIVE`。

| 阶段 | 实际状态 | 运行到哪里 | RHS / 原 A4 残差 / 场 L2 / scaled-curl | 资源与时间 | 原因和边界 |
|---|---|---|---|---|---|
| Q0 `Q0_CORE` | `partial_observation` | preflight、公共预分配门、fine quadrature、P64 transfer；最后可靠 phase 为 `setup` | 均为 `not_available`；尚未准备 reviewed RHS，也没有 Q0 完成 marker | watchdog 有效前缀 373 行；树 RSS/PSS 峰值 `1,417,695,232 / 1,385,432,064 B`；job swap 峰值 `0 B`；common setup 到最后事件 `97.819706335 s`，不是完整 setup 时间 | 已知直接错误是 parent launcher 的 `EIO`；有效前缀未触发 watchdog Gate，但 worker 终态缺失，最终数值/资源分类为 `not_available` |
| Q1 `Q1_FULL_DIRECT` | `not_available` | 没有当前工作区运行目录或终态记录 | `not_available` | `not_available` | 不用 V5/V13 历史数据填充本轮 Q1 |
| Q2 `Q2_SCHUR_DIRECT` | `not_available` | 没有当前工作区运行目录或终态记录 | `not_available` | `not_available` | 不用 V5/V13 历史数据填充本轮 Q2 |

## Q0 可核对的时间线

Q0 运行目录为 `results/euv_grazing1_phi0/task39extra_v14_q0_core__full3d_iterative__mpi1__Mna/20260912T123558.964217Z`。manifest 的启动时间是 `2026-09-12T12:35:58.976504Z`。可见事件依次为：

- common preallocation gate：`12:35:59.892856Z` / `12:35:59.894340Z`；
- common setup started：`12:36:00.043279Z`；
- fine quadrature complete：`12:36:05.654845Z`；
- P64 transfer complete：`12:37:37.862986Z`。

P64 transfer 的 raw facts 包含 fine/coarse storage rows `173802/53084`、base polynomial cache `21,168,000 B` 和本地 82 个非平凡 cell permutation。它是接线/公共准备证据，不是 p4 Schur solve 或物理场结果。`workflow_phase.json` 和 watchdog 尾部都仍为 `setup`，未出现 `q0_core_complete` 或 `physical_p4_schur_v14_summary.json`。

watchdog 的 373 个有效采样覆盖到 `2026-09-12T12:37:43.112614Z`；第 374 行是 3,276 字节的 NUL/非 JSON 残留，故完整清场和终态没有证据。有效前缀的 RSS/PSS 峰值分别为 `1,417,695,232 / 1,385,432,064 B`，峰值时仍为 `setup`。5 行由 worker 触发的进程树快照（root、mpiexec、worker）的峰值为 `726,052,864 / 697,837,568 B`；这是稀疏的另一采样口径，不能代替完整树峰值。

`v14_inventory.json` 只有启动时的空清单（字段为 0）；这不表示整个 setup 期间 live inventory 为 0，故 resident inventory、workspace 峰值和 apply 时间均登记为 `not_available`。同理，watchdog 观察到 job `VmSwap=0`；全局累计计数为 `pswpin=18`、`pswpout=2039`，有效前缀内增量为 `0/0`。这里不把累计全局计数改写成 job swap，也不把前缀内增量改写成整个 workflow 的 zero-swap 证明。

## I/O 故障与 ledger 身份

可见工具记录在 `2026-09-12T12:38:19.308Z` 报告 outer `exit_code=135`。原始 traceback 的第一处故障是 `task038_launcher.py` 写 `run_manifest.json` 的 `OSError: [Errno 5] Input/output error`；异常处理随后在 `_settle_v14_shared_budget` 读取 `benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json` 时再次得到同一 EIO。该记录只足以确认 parent I/O 故障；有效前缀没有触发 watchdog Gate，但缺少 worker 终态，最终数值/资源分类仍为 `not_available`，不能硬排除未知终态。

ledger 保持原样：`review_v14`、Q0 attempt 1、`status=RESERVED`、`active_attempt=0`、reserved `600 s`、`elapsed_seconds=0.0`、`unique_bug_replay_count=0`。由于 settlement 没有完成，`0.0 s` 不是实际消耗为零的结论，formal charged/settled seconds 只能写 `not_available`；本次没有手工修改预算或重放。

## 身份和证据入口

本次 Q0 绑定 source `efea244159d63a7c9db67ca091e29a9c19f9ce88`、input SHA `76e5ce396f064d7e1e7db3d0d283c7260c07cf7f0d9275783c3a10037a1afd29`、physical model SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` 和 resolved-config SHA `8c6590a404ef518bfc6f9db05ed8a6386aa152574df2d6b0ccfa1f6ac27a290d`。完整 raw 文件 hash、审计 hash 和缺失字段原因见 compact；原始大型 timeline 仍留在 ignored artifact root。

Q1/Q2 尚没有本轮 source、残差、场误差、curl、矩阵/因子 NNZ、常驻 inventory、setup/apply/cleanup 时间，也没有 memory ratio；三份冻结 RHS 名称已列入 compact，但每项数据均为 `not_available`。当前缺少共同核心的正式资格，Q3 工程实现仍需继续；后续准入按 Review V14 的共同正确性和资源条件决定，不以准确 Schur 内存节省为条件。

## 后续工程进展（不改变上述正式证据）

工程代码已提交为 `5d239140d3931364bc16d35c45458189cd957808`，固定接口候选与条件式 p6 接线的联合测试 104 passed，输入/旧 watchdog/文档另有 30 passed。没有新增正式 worker，Q0–Q2 数值字段和原 ledger 未变。实现细节、测试原始输出及已核实的推送状态见 [阶段 response_v15](../response_v15.md) 和 [工程证据](records/p4_schur_v14_engineering.json)；本次阶段记录不是 Q6 最终结项。
