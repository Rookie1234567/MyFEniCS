# Task000-Task027 阶段总结

## 审计口径

本总结逐项核对了任务书、审查报告、审查回复、outcomes summary、gate、merge recommendation 与 next decision。成功类型严格区分为生产成功、工程成功、基础设施成功、诊断成功、负结果成功、文档成功和仅研究正信号。后续任务的证据优先于早期结论。

## 总体阶段

| 阶段 | 任务 | 可长期保留的结论 | 主线处理 |
|---|---|---|---|
| 功率与回归基础 | Task000-Task007 | official DtN modal R/T、A_volume、能量闭合、小单元 p/MPI 回归 | 已在 master，继续保留 |
| 目标直接法基准 | Task008-Task010 | p=2 h=2 direct reference；BLR 是显式备用而非低内存迭代法 | 保留 direct 默认与参考结果 |
| AMS/HX 与低秩诊断 | Task011-Task019 | FE-only 正信号、边界慢方向、p2 sampled-Schur 迁移失败 | 文档保留，失败代码不进入普通接口 |
| Schur/FE-response 研究 | Task020-Task025 | h5 Schur 机制、MPI 回填、complex-dot 与 CSR 可复现基础设施 | 仅抽取通用基础，不搬研究 runner |
| 凝聚与物理分片突破 | Task026-Task027 | exact auxiliary condensation；MPI4 owner-computes physical slabs + fixed 75D coarse | Task28 抽成稳定模块和显式 benchmark |

## 当前稳定能力

| 能力 | 状态 | 证据 |
|---|---|---|
| 2D Floquet/DtN 验证链 | 稳定 | master 既有回归 |
| 3D Stage1-Stage4 staged cases | 稳定 | Task004 全阶段 smoke |
| Stage4 official R/T/A | 稳定 | Task007 及后续目标案例 |
| p=2 h=2 direct reference | 稳定但内存较高 | Task008/Task010 |
| exact condensed DtN operator | 稳定模块 | Task026，Task28 重新抽取测试 |
| p=2 h=2 MPI4 workstation iterative | 显式 opt-in 生产候选 | Task027；Task28 独立复跑后最终确认 |
| h=1.5 或更细生产迭代 | 未完成 | 不作能力宣称 |
| spectral/GenEO coarse | 失败 | Task027 negative evidence |

## 关键纠偏

| 早期结论 | 后续纠偏 |
|---|---|
| Task009 的 KSP residual 可代表求解质量 | Task024 起统一使用显式 true residual；Task027 reported/condensed/full 三口径一致 |
| FE-only real-split AMS 可直接扩到 Stage4 | Task014a 证明最小 FE-AMS + aux identity 太弱 |
| p1 sampled-Schur 正信号可迁移 p2 | Task019 在 p2 h5 仅有 1.0018x/1.0804x |
| cached-Q/80 response 是必需架构 | Task026 exact static condensation 消除了辅助变量外迭代需求 |
| spectral/GenEO 是网格鲁棒突破来源 | Task027 spectral 假设失败；实际成功来自 fixed coarse + physical slabs + sm2 |
| Task027 可称 mesh-independent | h5/h3/h2 全通过，但迭代数 1201/993/1804 非单调；准确名称是 mesh-robust workstation candidate |

## Task026 与 Task027 的整合边界

Task026 进入稳定层的内容是 FE/aux block extraction、精确静态凝聚、matrix-free (F-C H^{-1}D)、转置/共轭转置作用、凝聚 RHS 和辅助变量回代。Task027 进入稳定层的内容是稀疏 fixed coarse、coarse rank/condition/true-action certification、完整物理 slab 的 MPI gathering、确定性 owner 平衡、owner-only local factorization、scatter/reverse-scatter 与两步 shifted-F smoothing。

以下内容不进入普通 API：SLEPc spectral basis、GenEO、interface harmonic、HPDDM recycling、sampled-Schur、cached-Q 以及任务编号研究 runner。它们的证据仍保留在对应任务分支与文档中。

## 阶段结论

Task000-Task027 已经从“能装配并用 direct 求解”推进到“在 14 GB 级工作站上用 MPI4 对 p=2 h=2 目标 Stage4 系统得到显式真残差小于 1e-6 的候选迭代方案”。该候选不是通用默认求解器：它依赖固定目标几何、固定 75D coarse 规则和经过验证的 workstation 参数，必须显式 opt-in。普通 direct 默认保持不变。
