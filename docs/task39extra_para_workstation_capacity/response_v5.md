# Review V5 执行交接：R13Q4 attempt 1 setup failure

**截至 2026-09-24（本地执行分支 WIP）。** R13Q4 attempt 1 已启动并在 setup 序列化处以 `WORKER_FAILED`/exit 4 结束；没有进入外层迭代，也没有数值、物理或 RTA 结果。旧失败、R2 未决、5 nm 监督缺口及 2 nm 历史终态均保留，不作覆盖。此失败对应的单次实现 bug replay 已登记，尚未启动，等待本次最小修复审核。

本次 run=`20260923T155313.871301Z`，source=`4ce7b31c5003580e70adf979f02e5ba36e76e749`，输入、阶段、监督及原始文件哈希见 [R13Q4 attempt 1 compact](outcomes/records/v5_r13_q4_attempt1_failure_v1.json)。最后持久阶段为 `retained_volume_quadrature_metadata_complete`；失败标记 `retained_sum_factorized_physical_action_complete` 时，worker 报 `Object of type mappingproxy is not JSON serializable`。这是 ledger 序列化实现错误，不是算子、数值 Gate 或资源 Gate 失败。原始 run/compact 未覆盖。

## H0/H1

H0 只证明拓扑，不代表空闲或性能：在线逻辑 CPU 为 0–47，CPU48 不存在；CPU24 属 socket1/node1、sysfs `core_id=0`、SMT siblings=`24`；CPU9 属 socket0、sysfs `core_id=11`、siblings=`9`。正式启动前仍须实时复核 CPU24 邻占用及资源准入。

H1 是合成负载，不是 FE 结果。CPU23/node0 与 CPU24/node1 的 60 秒算术吞吐分别约 `7.287e9`、`7.329e9 updates/s`；两组相同固定工作量中位数分别为 `7.3555e9`、`7.3686e9 updates/s`。三对 STREAM-like 名义值中位数为 node0 `8.270720`、node1 `9.086460 GB/s`，逻辑流量指标不等于实测内存控制器带宽。无 APERF/MPERF/MSR 忙频证据；TSC 与 sysfs 频率不冒充忙频。原始记录见 [`v5_h0_h1_m_a_profile_checks_v1.json`](outcomes/records/v5_h0_h1_m_a_profile_checks_v1.json)。

## M/C 组件资格边界

- V5 q3/q4 使用同一 retained-condensed workflow，粗阶 `q`、直接 `(6,q)` levels、A6/H6 sum-factorized 路径和 owner-transfer opt-in；保留 D2 的精化 ledger、raw geometry 身份、释放顺序及独立原算子核验。迁移来源按 4bf2/cad282 的冻结 blob 逐文件登记，未整体覆盖目标文件。
- 已验证实际 990-cell Aq 投影：80 modes；q3/q4 的 volume 与 DtN 投影各自均低于 `1e-10`。另有 18-cell q3/q4 workflow setup、实际材料局部组件、H6/A6 小 FE 对照、真实 Floquet 保存—恢复—canonical 往返，以及 PORD64 小 fixture。合并的 13 项轻回归通过；这些结果不等同于完整 990-cell 长场、全 80 模态端到端结果或持续资源资格。各测试名称、范围、库与来源 blob 见 [`v5_m_c_and_four_input_contract_v1.json`](outcomes/records/v5_m_c_and_four_input_contract_v1.json)。
- 私有 ABI 激活显式使用 base `tmp/task39extra_v5_abi_restore_20260923/base` 和 PORD64 overlay `.../base/prefix/pord64-overlay`；旧 int32/普通 int64 激活入口未替换。库、petsc4py cfg、MPC 包及激活脚本 hash 在上述 compact 中。PORD64 小 fixture 为组件资格，不是正式大图通过。

## R13Q4 唯一实现 bug replay 的原启动合同

输入固定为 [`v5_node1_13p5nm_p6h7p5_q4.dat`](../../input/task39extra_para_workstation_capacity/v5_node1_13p5nm_p6h7p5_q4.dat)，input SHA256=`f9e20874ed86e8697b307ca9d2539ec04be8dd77dc7211cc9e0be8dae30746b5`，physical SHA256=`255837330af27827d15ef43dfb01876187589a3b5e129f1d0882e24b955484c0`；冻结 V21 轴，990 cells、80 DtN modes、粗阶4。不得使用 h10 输入或短波输入。

父监督 CPU9；worker CPU24；MPI1、数学库线程1；`preferred_node1`，允许 node0/node1；PORD64 私有激活。实时启动准入要求 `effective_available_bytes >= 1437438953472`（1300000000000 B RSS Gate + 137438953472 B 本轮选定的启动余量），另核验当前 cgroup 和 CPU24 邻占用。运行期唯一自动资源停止为整个任务树 measured RSS 达到 `1300000000000 B`；1170000000000 B 为观察警戒值。没有时间截止；128 步只作进展观察，FGMRES restart32、zero retained start、max2048。swap、fault、预测值、温度、频率和吞吐均记录而不新增停止条件。

监督复用原 native parent/watchdog；另以 task-local 只读 `scripts/task39extra_event_observer.py`（SHA256=`aeded7a3f3447a186d223aec61502d0b54e60e8f1bf83d68b2cb28ac9c0f9757`）在 CPU9 每15秒读取该 run 与固定 root/worker PID+start_ticks，并将可读的 CPU24 hwmon/thermal-zone 温度、thermal-throttle 计数、`scaling_cur_freq`/`cpuinfo_cur_freq` 旁证写入 observer JSONL。helper 使用 `/home/fenics/Projects/Maxwell3D-Lab/task-control/codex-thread-notify-v2.py`。忙频保持 unknown（除非另有获准的 APERF/MPERF 证据）；缺失传感器不失败、不停止、不杀进程。观察器没有信号或重启能力，RSS 硬 Gate 仍由既有 watchdog 实施。observer 自测已覆盖 PID/tick 绑定、缺项仅记录和忙频不推断。

本交接记录不宣称 R13Q4 数值、物理、长期硬件或资源 PASS；唯一修复 replay 尚未启动。R13Q3、R13 pair release、F5/F2 均未运行。
