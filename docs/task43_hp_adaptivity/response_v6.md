# Task43 Review V5 执行回应：affinity 取证与身份 helper 静态修复

本回应覆盖正式 review 提交 `b5a4b69c25c6be92faf0116e119904c438cbe297` 的 §9；任务基线仍为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`。本轮没有新增正式计算、dispatch、PDE 或 READY；本地 S2 测试改动尚未运行。执行分支仍为 `task43_hp_adaptivity`，科学状态仍是 `PARTIAL / CONTROLLED_NEGATIVE`，等待外部审阅。

CPU affinity 是进程或线程被允许运行的核心集合。要求 `[1]` 时，观测到成功设置为 `[0]` 或其他集合就不能算严格 CPU1 通过；短时采样或导入结束后恢复成 `[1]` 也不能抵消期间的偏离。D1/D2 用 `strace` 记录了成功的 affinity 设置及调用栈，但只覆盖这两次导入过程，不能连续证明所有线程的状态，也不能倒推 V5 历史样本由何种机制触发。

## S1/S2 结果

S1 只读整理六个已有 V5 support driver 的记录、身份和 affinity 异常邻域，没有启动支持 driver 或测试。索引是 [S1 只读上下文记录](outcomes/records/v6_s1_v5_support_affinity_context_v1.json)，SHA256 为 `098332476031eb14b1ee03aa52f0950e24e4d682b42fb043b1694cd39ad475ab`。其中 launcher exit code 来自 V5 compact 的独立历史记录，因为六份 watchdog summary 本身未存该字段；它的 null 不能解释为 worker 未知或清理失败。

S2 只改了测试内 `_synthetic_joint_read_has_no_engineering_veto`：比较身份前要求 source 为非空40位十六进制字符串，contract 和 plan 各为非空64位十六进制字符串；保留原一致包、独立否决和 writer 故障场景，新增共同缺 source、contract、plan 及三者全缺四例。当前文件 SHA256 为 `52f94e28306d2d7f83f602c5e654c8953e544f00091ae3013378d52d040b7a43`。这是测试 helper 修正，不改 production consumer、A1/A2 数值入口或冻结合同；该 helper 及其20个直接测试案例均未运行，不能称为动态通过。

## D1/D2 affinity 结果

两次均在 `dolfinx` 导入阶段发现成功的 affinity 设置偏离 `[1]`，立即退出，未进入 pytest、mesh builder、装配或 solver。D2 是本轮最后一次允许的 support driver，不再重试。

| Driver | 观察到的成功 `sched_setaffinity` 设置 | 终态与资源 | 判定 |
|---|---|---|---|
| D1 `run_d1.sh` | 共200次：196次直接调用栈落在 `libhwloc`，2次为 `libinfinipath`，2次为 `libpsm2`；请求集合 `[0]` 6次、`[1]` 10次、其他集合184次 | 导入探针 exit 23、watchdog leader 23、外层launcher 2；16个采样、51条成员观察；whole-watchdog 10.266887816600502秒；最大同时采样树RSS 161,480,704 B；task VmSwap采样峰0 B，global `pswpin/pswpout`增量0/0页；后代已清理 | CPU1 `NOT_PASSED`；停止原因为探针观察到设置集合不是 `[1]` |
| D2 `HWLOC_COMPONENTS=-x86` | 共4次：没有 `libhwloc` 直接调用，`libinfinipath` 与 `libpsm2` 各2次；`[0]` 与恢复的 `[1]` 各2次 | 导入探针 exit 23、watchdog leader 23、外层launcher 2；13个采样、40条成员观察；whole-watchdog 10.469862679950893秒；最大同时采样树RSS 160,063,488 B；task VmSwap采样峰0 B，global `pswpin/pswpout`增量0/0页；后代已清理 | CPU1 `NOT_PASSED`；网络库调用仍出现，pytest未运行 |

D1 的 `dolfinx` 导入阶段 PID/start_ticks 为 `4071459/284920539`，PPID `4071446`；启动时 TID `4071459` 的采样 affinity 为 `[1]`。导入后快照看到 TID `4071459/4071491/4071492` 均为 `[1]`，`trace_sync=true`；但同一同步 trace 已记录 hwloc 成功设置到 `[30]` 和 `[33]`，所以阶段末恢复到 `[1]` 不能抵消偏离。D2 对应 PID/start_ticks `4076967/284948743`、PPID `4076949`；导入后快照的三个 TID 均为 `[1]` 且 `trace_sync=true`，但 trace 有两次 `[0]` setter 与两次 `[1]` 恢复。每个阶段快照只说明取样时刻，不代表连续线程监测。D1/D2 均在第一个显式 `dolfinx` 导入后停止：MPI/PETSc 完整 ABI 检查为 `NOT_REACHED`，pytest 入口也未到达。`launch_context.txt` 中的 marker、解释器路径和线程设置只是激活后的 shell 记录，不是已完成的 ABI 实测。

两个 driver 合计 whole-watchdog 20.736750496551394 秒，总预算和每次时限均未超；8 GiB动态节点上限、RSS、task VmSwap采样和清理记录满足支持 driver 门，CPU1 门未通过。两次 global `pswpin/pswpout` 增量均为0/0页，和进程树 `VmSwap` 分开记录。compact 逐次绑定了artifact与driver快照路径、实际watchdog/worker命令片段、逐文件源码及快照哈希、阶段PID/TID与trace同步状态、全部trace文件、资源流、终态和代表性完整栈段；另列D1原resources中的两个CPU偏离成员样本及D2的13/40样本均为CPU1：[V6 affinity support closeout](outcomes/records/v6_affinity_support_closeout_v1.json)。S2 计划的20项——1个一致包正例、4个共同缺身份例、12个独立否决例和3个 writer 故障例——均为 `NOT_RUN`；没有把“未到pytest入口”记作通过。未监控的shell语法检查与JSON解析仅按已有报告列为静态检查；没有可留存命令/输出核实S2 test module bytecode compilation，因此不作该项通过声明。未监控检查耗时/RSS为 `not_measured`，不计入watchdog wall。

D1 的完整trace包含200次 setter。D2 前的复核只识别了 `hwloc`，没有把 D1 已经出现的两类网络库 setter（`libinfinipath`和`libpsm2`，合计4次）分类；D2因此只尝试在本次 worker shell 内禁用 hwloc 的 x86 组件，未处理已经存在的网络库调用。D2 后全量重读 D1 trace才发现这一遗漏。这是主控对D2前证据审查不完整，不是S2问题，也不是数值方法结果。D2中 `HWLOC_COMPONENTS=-x86` 仅对该次worker shell生效，不改系统、共享ABI或项目默认配置；该变量会减少hwloc x86补充拓扑发现的信息，但这次设置仍出现网络库affinity调用，因此不能作为修复。hwloc 2.10文档描述以 `-` 前缀禁用组件，[固定版本文档](https://github.com/open-mpi/hwloc/blob/hwloc-2.10.0/doc/hwloc.doxy)；[x86拓扑实现](https://github.com/open-mpi/hwloc/blob/hwloc-2.10.0/hwloc/topology-x86.c)展示该组件涉及CPU绑定调用。新trace的调用栈说明这些调用发生于本次MPI初始化相关导入路径，但对V5更早的离散affinity样本只能说机制相符，不能声称已证实其历史根因。

## 状态与范围

| 项目 | 当前结论 |
|---|---|
| S1 | 六份 V5 support 原件索引与异常上下文已只读保存；没有重算或重写旧记录 |
| S2 | 测试 helper 的身份存在性已静态修复；20项动态案例未运行 |
| D1/D2 | 两次支持额度已用完；均在导入期退出，CPU1 NOT_PASSED；不再执行第三次driver |
| 新正式计算 / READY | 0；formal仍5/6，A1 2/2、A2 3/3，最后1槽封存 |
| 五项能力 | 空间 `PARTIAL`；选择 `PARTIAL`；精度 `NOT_PASSED`；同精度全过程成本 `NOT_ESTABLISHED`；迭代 `NOT_RUN / NOT_QUALIFIED`；0.7 nm未运行 |
| 科学与合并 | R9仍为最后接受状态，最终精度未达；本轮没有科学正负结论，未获生产合并批准 |

没有运行full suite、p6 FFCx witness、PDE、网格、装配、求解、旧场回放、采样或积分。已有A1/A2历史失败、extra严格下降负项、V5 CPU1受限结果均不改写。本轮只完成有限support取证与测试 helper 静态修复；它们不授予新模型、重试或下游研究资格。

本轮支持次数已用2/2，每次whole-watchdog均小于120秒，合计小于240秒；剩余时间不授予第三次运行。A1/A2 q重试、A1_R、A2_R、B/C、fresh baseline、同精度成本campaign、迭代、0.7 nm、NN/FTT全部继续锁定，未签发READY，也不执行合并。
