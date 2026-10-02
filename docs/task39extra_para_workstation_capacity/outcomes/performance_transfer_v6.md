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
| 54332-cell H6-only | NOT_RUN | 不建 p4 全局矩阵或因子 |
| 1/4 线程选择 | NOT_RUN | 当前候选 math1；不以环境变量冒充实际库并行 |
| 唯一新 5 nm 完整回归 | NOT_RUN | 组件与 H6-only、线程选择后 clean freeze |
| 唯一 2 nm setup＋16 步 | NOT_RUN | 5 nm 完整通过后执行，同一因子用于 QA 和 16 步 |
| 0.7 nm / 48 h 容量与精度账 | NOT_RUN | 不分配目标最大矩阵、不运行 PDE |

此前 32.94 h H6 对角和 12.25 h numeric 是旧场实测。PSS 干扰是有证据的性能疑点，但不能把关掉 PSS 的未配对收益写成“33 h 必降为 5 h”。局部 tensor 已有 6 组复用，其约 326 s 份额不能解释或独自消除 51.22 h setup。

真实组件测试时的源码为 review HEAD 上的 WIP，精确 patch 与文件 hash 留在 ignored `tmp/review_v6_components/actual_attempt3/source_identity.json`；它不能由后续提交 SHA 冒充。组件通过后的调整为 import/lint、边界库身份与 factory 元数据，不改变数值公式或 Gate。监督阶段提交为 `3bda76479f78fe775a30de63ad20789ae66d881a`，正式场尚未启动。后续 clean source 与运行身份分别进入 manifest；完整 C 分项和最终未达目标的量化缺口将在证据形成后更新。
