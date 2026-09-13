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
