# Review V5 执行记录：R13_PAIR_RELEASE → F5 完成 → 105-cell 几何组件通过；setup-only 待审

**截至 2026-09-24。** R13 Q4/Q3 均以 source `6d989b4b9cbca12fcc35455d7ff381e66ef7ca6d` 完成；离线 checker source `515b0c653fc25bc1da2f319da9b7e658de049a2e` 的 attempt4 为 `NUMERICAL_PAIR_PASS`，结合共同路径、source-compact、连续 watchdog 与持续硬件证据记录 `R13_PAIR_RELEASE`。详见 [R13 release compact](outcomes/records/r13_pair_release_v1.json)。

性能差异主要落在 p6 凝聚 setup 的 raw tensor class 工作量：冻结源正式调用使用其 `rounded_12` 几何规则，当前已存 raw 几何按该规则派生为12组，而 V5 `raw_unrounded` 保留96组（8倍 distinct-kernel 工作单元；12是派生值，非源 run 实测）。Q4/Q3 p6 kernel 实测4721.61/4680.91 s，稳定；H1同工作量 node0/node1 与990-cell FE配对未见旧 node1 严重慢化，两次正式 observer 的 thermal-throttle 计数均为0。忙频 MSR/APerf/MPERF 仍 unknown；这不证明普遍硬件状态，也不授权改 raw identity policy。现有 A4/Aq 审计保留，额外成本按已记录操作范围描述，不做未测的精细拆账。

F5 正式场 `20260923T231207.264441Z` 已以 source `b468907cf54d04280b461cae5fc9078186302d54` 完成：121步，显式 A6 residual `8.60422e-7`，244/244 次 p4 返回通过 `1e-10`，checker 为 `BALANCED_OUTPUT_PASS`、旧5nm匹配比较为 `MATCHED_REFERENCE_PASS`；600通道及 R/T/A/体吸收 Gate 通过。整树 RSS 峰 `38,934,622,208 B`，swap0，watchdog `COMPLETED` 且清场。逐项身份、artifact hash及 Gate 指标见 [F5 compact](outcomes/records/f5_5nm_q4_terminal_compact_v1.json)。

F5 setup 实测 `11263.076 s`，其中 p6/p4 raw tensor kernel `8571.805/988.356 s`、Schur `29.46/2.23 s`。两者各175个 raw 几何类；按 `round(width,12)` 从已存几何派生为6组，但这只是类数推导，绝非时间提速或安全合并证明。H1/990-cell对照未见本次测试负载下旧 node1 严重慢化，observer throttle 计数为0；忙频 MSR/APerf/MPERF 仍 unknown。

### 105-cell 几何代表组件（不是 setup-only）

在源 `b468907cf54d04280b461cae5fc9078186302d54` 的未提交工作树上，使用原5 nm Si输入与物理身份、派生 `(5,3,7)` 即105-cell网格、`MPI.COMM_SELF`，从完整600-mode inventory中选4个真实零阶mode完成一次真实FE/MPC组件测试。每阶18个raw几何类合为9个tensor组；Schur/LU/recovery仍按raw float64宽度+orientation区分，MPC expansion仍逐cell。所有raw类逐一与组代表tensor对比，最大相对差 p4=`6.29475e-16`、p6=`4.34826e-16`；p6 condensed action差=`3.13911e-13`、独立原A6 residual/action差=`3.01989e-13`；原Aq体积/DtN投影差=`4.10e-15/1.08e-14`；原A4非零内部RHS返回rho raw/candidate=`2.38159e-11/1.65771e-11`。另有显式非零port RHS的增广矩阵解残差=`6.39e-14/8.56e-14`，这是独立检查，不是该RHS下的原A4恢复资格。

生产构建段计时 raw→candidate：p6 tensor `892.56→447.23 s`、p4 `43.45→21.26 s`；全raw类附加复算另耗p6 `1434.48 s`、p4 `64.51 s`。整项测试`1 passed/2986.99 s`。这里只能作为105-cell、四零阶mode的组件证据；不代表正式3780-cell setup、全600通道、资源资格或setup整体提速。逐文件hash、输入身份、命令、日志hash及边界见[compact](outcomes/records/v5_5nm_geometry_105_component_v1.json)。

与较早同5nm离散的698步结果对照：旧 solve/workflow=`206568.519/217665.164 s`，旧观测RSS峰=`50,161,172,480 B`；当前为121步、`10671.216/22680.912 s`、`38,934,622,208 B`。workflow墙钟约9.60倍，但旧CPU23与当前CPU24跨插槽，且source/runtime不同，不能把该比值全归因于算法提速；旧RSS记录有约8小时34分监督断档，不是连续资源PASS。旧run原记录不改写，当前 compact 只作对照。

下一门槛按最新指令为：CPU24上完成必要focused regression并clean提交/审核后，以同一input SHA单独运行一次5nm setup-only。setup-only须独立run身份、完整RSS-only监督，不进入外层迭代/RTA，不能冒充完整数值/物理PASS。只有该setup-only正常完成且实测提速明确、全部原Gate不变才评估条件F2；Q4 attempt1序列化错误的负记录继续保留，见[compact](outcomes/records/v5_r13_q4_attempt1_failure_v1.json)。

## H0/H1

H0 只证明拓扑，不代表空闲或性能：在线逻辑 CPU 为 0–47，CPU48 不存在；CPU24 属 socket1/node1、sysfs `core_id=0`、SMT siblings=`24`；CPU9 属 socket0、sysfs `core_id=11`、siblings=`9`。正式启动前仍须实时复核 CPU24 邻占用及资源准入。

H1 是合成负载，不是 FE 结果。CPU23/node0 与 CPU24/node1 的 60 秒算术吞吐分别约 `7.287e9`、`7.329e9 updates/s`；两组相同固定工作量中位数分别为 `7.3555e9`、`7.3686e9 updates/s`。三对 STREAM-like 名义值中位数为 node0 `8.270720`、node1 `9.086460 GB/s`，逻辑流量指标不等于实测内存控制器带宽。无 APERF/MPERF/MSR 忙频证据；TSC 与 sysfs 频率不冒充忙频。原始记录见 [`v5_h0_h1_m_a_profile_checks_v1.json`](outcomes/records/v5_h0_h1_m_a_profile_checks_v1.json)。

## M/C 组件资格边界

- V5 q3/q4 使用同一 retained-condensed workflow，粗阶 `q`、直接 `(6,q)` levels、A6/H6 sum-factorized 路径和 owner-transfer opt-in；保留 D2 的精化 ledger、raw geometry 身份、释放顺序及独立原算子核验。迁移来源按 4bf2/cad282 的冻结 blob 逐文件登记，未整体覆盖目标文件。
- 已验证实际 990-cell Aq 投影：80 modes；q3/q4 的 volume 与 DtN 投影各自均低于 `1e-10`。另有 18-cell q3/q4 workflow setup、实际材料局部组件、H6/A6 小 FE 对照、真实 Floquet 保存—恢复—canonical 往返，以及 PORD64 小 fixture。合并的 13 项轻回归通过；这些结果不等同于完整 990-cell 长场、全 80 模态端到端结果或持续资源资格。各测试名称、范围、库与来源 blob 见 [`v5_m_c_and_four_input_contract_v1.json`](outcomes/records/v5_m_c_and_four_input_contract_v1.json)。
- 私有 ABI 激活显式使用 base `tmp/task39extra_v5_abi_restore_20260923/base` 和 PORD64 overlay `.../base/prefix/pord64-overlay`；旧 int32/普通 int64 激活入口未替换。库、petsc4py cfg、MPC 包及激活脚本 hash 在上述 compact 中。PORD64 小 fixture 为组件资格，不是正式大图通过。

## 历史：R13Q4 attempt1 的实现错误与原 replay 合同

输入固定为 [`v5_node1_13p5nm_p6h7p5_q4.dat`](../../input/task39extra_para_workstation_capacity/v5_node1_13p5nm_p6h7p5_q4.dat)，input SHA256=`f9e20874ed86e8697b307ca9d2539ec04be8dd77dc7211cc9e0be8dae30746b5`，physical SHA256=`255837330af27827d15ef43dfb01876187589a3b5e129f1d0882e24b955484c0`；冻结 V21 轴，990 cells、80 DtN modes、粗阶4。不得使用 h10 输入或短波输入。

父监督 CPU9；worker CPU24；MPI1、数学库线程1；`preferred_node1`，允许 node0/node1；PORD64 私有激活。实时启动准入要求 `effective_available_bytes >= 1437438953472`（1300000000000 B RSS Gate + 137438953472 B 本轮选定的启动余量），另核验当前 cgroup 和 CPU24 邻占用。运行期唯一自动资源停止为整个任务树 measured RSS 达到 `1300000000000 B`；1170000000000 B 为观察警戒值。没有时间截止；128 步只作进展观察，FGMRES restart32、zero retained start、max2048。swap、fault、预测值、温度、频率和吞吐均记录而不新增停止条件。

监督复用原 native parent/watchdog；另以 task-local 只读 `scripts/task39extra_event_observer.py`（SHA256=`aeded7a3f3447a186d223aec61502d0b54e60e8f1bf83d68b2cb28ac9c0f9757`）在 CPU9 每15秒读取该 run 与固定 root/worker PID+start_ticks，并将可读的 CPU24 hwmon/thermal-zone 温度、thermal-throttle 计数、`scaling_cur_freq`/`cpuinfo_cur_freq` 旁证写入 observer JSONL。helper 使用 `/home/fenics/Projects/Maxwell3D-Lab/task-control/codex-thread-notify-v2.py`。忙频保持 unknown（除非另有获准的 APERF/MPERF 证据）；缺失传感器不失败、不停止、不杀进程。观察器没有信号或重启能力，RSS 硬 Gate 仍由既有 watchdog 实施。observer 自测已覆盖 PID/tick 绑定、缺项仅记录和忙频不推断。

该启动合同对应已完成的 R13Q4 replay，不能覆盖 attempt1 的原始负记录。当前 R13 pair 与 F5 均已完成；F2 未启动，须先经过上述独立 setup-only 决策门。
