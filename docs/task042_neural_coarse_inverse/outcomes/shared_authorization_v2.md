# Task042 用户授权：受控共享运行

2026-09-28 用户在本任务中明确授权继续 `task42_neural_coarse_inverse`，原文授权核心为：

> Task042 可以在已有 heavy 程序仍运行时受控并行，不再仅因 heavy_present=true 就停在 F0 或等待整台工作站空闲。

> 本次授权覆盖 Task042 task.md §2.3 中与此冲突的“已有 heavy 则禁止 FE/JIT、teacher、训练和 PDE”及必须独占全机 heavy lock 的要求；只适用于 Task042，不修改其他任务的运行合同。

允许为 Task042 新增显式受控共享 profile 和本任务准入/锁策略；不得删除、强占、修改邻任务锁。Task042 使用自己的 nonblocking flock，内部仅一个前台数值阶段；不建立后台自动等待器。用户明确指出这不是精度/资源/provenance/停止条件豁免，也不是 F0 正式 review 已通过。本次是用户授权下继续关闭原 F1–F4 Gate，保留 `task.md`、既有 review、`response_v1.md` 与 F0 原始记录。

CPU 路线现场选择不与忙碌物理核心/SMT同胞冲突的核心；MPI1，BLAS/OpenMP/MKL/NumExpr、编译等线程1。只对 Task042 自身设置 nice10、idle I/O。训练使用现有独立 CPU-only Torch，显式 float64 实虚通道、torch intra/inter-op=1、DataLoader workers=0；原训练预算和候选规模不变。两卡持续训练时直接 CPU，不安装 CUDA，不修改 MPS/MIG、compute mode、功率/驱动或 reset。

固定整树 RSS hard16GiB/warning12GiB，包含 launcher、worker、compiler 和全部后代；own swap 必须0、禁止OOC，原 reserve=max(128GiB,effective_total的10%)、磁盘自由>=50GiB、artifact<=20GiB。新增保守的邻任务增长 allowance128GiB，作为额外启动与运行余量，属于明确的规划保护量，不是邻任务增长预测。cgroup只读检查真实权限；没有独立委派就只声明采样进程树强制停止，不能冒充内核 cgroup 限制。监督失效、容量触线或持续压力只清理 Task042 后代。

启动前保存短资源基线；观察可读邻阶段与低开销 status/CPU/PSI，不能扫描邻任务大日志或反复 smaps。不能保证数学意义零影响；不能把邻任务自然阶段变化直接判为干扰。所有时间/RSS/teacher/训练/线性/NN成本标为 shared-workstation；负载变化或条件不可比时性能结论 inconclusive，仍可评估数值正确性。

仍按 F1→F2→F3→F4→条件F5：真实原 A4/A6、primal/dual、非零内部与端口 RHS 先通过；teacher/参考、训练、候选部署独立进程顺序释放；候选从构建起没有 global p4 LU，不放宽1e-10粗返回或1e-6原A6，不隐藏LU fallback、不减少验算、不扩大到5/2/0.7nm或无界扫描。每个 dat 对应一个明确阶段，正式 FE 前 commit clean 实现，实际 source SHA 与后续文档HEAD分开。

完成授权阶段或触发真实停止条件后，交付实际数值、负结果、资源/影响/provenance和未运行项到 outcomes，新增 `response_v2.md`，同步项目总账，仅推送本执行分支，然后等待 review；master 合并仍未授权。
