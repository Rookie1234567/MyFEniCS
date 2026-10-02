# Review V6 性能迁移：执行中记录

截至 2026-10-02，本批保留准确 p4 凝聚 MUMPS 因子。先在每个单元内部准确消元，再形成较小的全局矩阵；外层仍求原 p6 方程。低内存 p4 逆试验为 **0**，没有改变原 Aq≤1e-10、最多两次额外同因子精化的要求。

## 现场归因与监督

旧 F2 的 kernel 事件是 `CONSTRAINT_MEMORY_POLICY / nodemask=1 / global_oom`。当时被杀的是本任务 worker，触发分配的 PID 已消失，其项目、完整命令和 VMA 策略 unknown。旧 worker 为 preferred node1、允许 node0/1，不能把触发者的受限分配掩码当作被杀 worker 的策略。整树采样峰 1154381864960 B 未达到 1300000000000 B；这是 kernel OOM，不是 watchdog RSS 触线。保留旧失败与 224 步 solution-only 检查点，不称收敛参考，也不承诺免 setup 续算。

新 V6 profile 停用 parent/worker/JIT 监督的 PSS/USS 地址空间扫描，仍独立采样同时整树 RSS、身份、任务 swap 和全机 swap 计数，保持 1.3e12 B 硬线；node meminfo 只观察。用户已经协调独占 heavy 窗口，正式场仍须新鲜准入与锁、CPU、NUMA/ABI 核对。双 node interleave 的 4 MiB 启动探针通过，不能据此保证 TB 因子一定免 OOM。详见 [资源与 NUMA 记录](records/v6_resource_numa_policy.json)。

## 当前证据与未运行边界

| 项目 | 已执行证据 | 当前边界 |
|---|---|---|
| 监督控制流 | 最终 24 passed / 32.95 s | PSS provider 零调用、慢诊断不阻塞 RSS、触线清场；不重建 TB 旧工作集 |
| metric 对角、融合作用、原对角 | 最终 8 passed / 32.00 s | 包含真实 p3 Floquet 与复多主合并 fallback；尚非全 2 nm H6-only |
| 输入/profile/原入口合同 | 49 passed、1 skipped / 12.14 s | opt-in FE 项未在此命令运行 |
| 有限作用域、manifest 与严格粗返回合同 | 最终 48 passed / 5.06 s | 包含真实小 KSP 16 步计划停止；无完整 PDE 资格 |
| 5/2 nm 实际系数与全部模式组件 | 2 passed / 872.14 s | 有界 18-cell、全部 600/3904 模式；原 FFCx tensor、完整原作用、H6/Aq/恢复/C 检查通过；非完整 PDE |
| p3 共用优化路径 | 1 passed / 13.15 s | 真实 5 nm 系数与 600 模式；没有 q3 长场 |
| MPI2/MPI4 metric 对角 | 每 rank 1 passed / 6.51–6.52、5.04–5.05 s | 小 p3 Floquet FE，与原积分对角及装配矩阵比较 |
| 54332-cell H6-only | H6_ONLY_COMPLETED；流程 17521.132 s，整树 RSS 峰 11304841216 B | 仅 H6 setup；不建 p4 全局矩阵/因子；outer、完整 A6 recovery、RTA、checker 均 NOT_RUN；不是完整 PDE 资格 |
| 1/4 线程选择 | 4 场 bounded FE 对照均 `COMPLETED`；5/2 nm 两个 18-cell fixture 均 `COMPONENT_PASS`；同工作量 AB/BA 比较均 `BOUNDED_COMPARISON_PASS` | 2 nm warm 完整 PC 比值 math1/math4 为 1.047754、0.975515，未稳定受益；冻结 MPI1/math1、worker CPU24、parent CPU9、NUMA interleave 0/1。8 线程未运行 |
| 唯一新 5 nm 完整回归 | NOT_RUN | 组件与 H6-only、线程选择后 clean freeze |
| 唯一 2 nm setup＋16 步 | NOT_RUN | 5 nm 完整通过后执行，同一因子用于 QA 和 16 步 |
| 0.7 nm / 48 h 容量与精度账 | NOT_RUN | 不分配目标最大矩阵、不运行 PDE |

本次 worker 记录范围为 17516.854 s（包含 mesh/space）；H6 stage parent 为 17426.406 s。可归属子项 b6 shell 0.000216 s、metric 对角 15918.245 s、positive action 21.823 s、power10 1375.127 s，合计 17315.196 s；parent 减去这些子项后 111.209810 s 未归因，不命名为 Python 或装配时间。power10 中 20 次矩阵乘，嵌套 action timer 1335.038 s；power_history 的 10 条记录不是乘法次数。完整 workflow 为 17521.132 s。旧场 metric 对角 118597.093 s 与本次不同工作集/缓存条件，7.45 仅为非成对工程比，不作因果归因，也不外推 TB/P2 H6 时间。49,978 个 watchdog 样本均可读、最大间隔 0.685 s，整树 RSS 峰 11304841216 B（硬线 1300000000000 B）、任务 VmSwap 峰 0、后代已清场；全机 pswpin/pswpout 增量 83/0，归因未知。root CLI 实际退出码未知，源码推断 3 与 worker/watchdog 实测 exit 0 分列。监督 snapshot timer 合计 CPU 1878.914 s、wall 1878.978 s 仅代表进程树快照采样，不代表 watchdog 总开销。参见 [H6 终态记录](records/v6_component_and_h6_only.json)。

E3 的四场线程对照使用同一 clean source `41bd6afa0be4e6ff242025f3730a3e458d3717e7` 和 launcher `bfd8a4f236c5ba96524c37ef9c68c0a3cff6dfd9482ab2b40f72c2a0043ae68b`。PC 第一次调用独立报告；warm 比值只比较第 2、3 次调用均值。5 nm 小 fixture 的 math4 warm 收益在 AB/BA 均出现（1.384866/1.717097），但 2 nm 小 fixture 为 1.047754/0.975515，故不满足全范围稳定收益条件，正式配置冻结为 MPI1/math1、worker CPU24、parent CPU9、NUMA interleave 0/1；不运行 8 线程。p4 factor API 时间另列，不替代完整 PC 判断。math4 时线程环境设置为4、`openblas_get_num_threads()`报告4、worker实测OS线程数为6；报告字段`parallel_runtime=1`来自`openblas_get_parallel()`，按本机头文件表示`OPENBLAS_THREAD`类型，不是线程数量。PC实测墙钟与factor numeric API墙钟/进程CPU时间分别记录，未把API计时外推为PC CPU时间。MUMPS 共享内存并行能力仍为 unknown。该实验仅是固定工作量小 FE 组件证据，不是完整 F5/P2 PDE 资格。逐场 PID/start_ticks、RSS、任务 swap、原 JSON/NPZ/watchdog summary hashes及分开的首调用/warm 计时见[线程选择 compact](records/v6_thread_selection.json)。

真实组件测试时的源码为 review HEAD 上的 WIP，精确 patch 与文件 hash 留在 ignored `tmp/review_v6_components/actual_attempt3/source_identity.json`；它不能由后续提交 SHA 冒充。组件通过后的调整为 import/lint、边界库身份与 factory 元数据，不改变数值公式或 Gate。监督阶段提交为 `3bda76479f78fe775a30de63ad20789ae66d881a`，正式场尚未启动。后续 clean source 与运行身份分别进入 manifest；完整 C 分项和最终未达目标的量化缺口将在证据形成后更新。
