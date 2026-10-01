# Phase 2 范围补充：真实 G0 的有界 p4 因子诊断

本补充只适用于 dot 独占云端分支。协调方已核准这里明确列出的研究范围补充。它不接管父任务，也不修改父 review 或生产默认。每个数值阶段必须分别核准准确命令、源码内容和环境资格。当前命名小系统的装配/导出已完成，未执行全局分解或完整求解；真实失败与结果见 [Response V2](response_v2.md)。

最新最终目标仍是完整三维求解器：原尺寸50×25×140 nm、无缺口规则基线、0.7 nm、约2 TB/单次≤48小时，研究窗口截至2026-10-04 10:07:14 UTC；不接受二维/2.5D替代交付，未来三维缺口能力必须保留。本补充的小缺口G0只作真实三维算子研究，不是目标能力证明。

## 范围补充

原 task.md 排除了完整 G0/G1 PDE 和全域生产因子。本阶段增加一个明确的、小规模 research 例外：只生成现有 336-cell G0 几何上的 p4 凝聚矩阵、80 个真实 Fourier-DtN 端口及一个真实入射 Maxwell RHS；在后续独立获准的固定资源条件下，顺序比较 complex128 和 complex64 全局研究因子。这里的 p4 覆盖整个 G0，因此不能继续称为局部组件。未限定/目标尺度的全域生产因子仍被排除。

- 不生成 p6 场，不运行 p6 外层 KSP，不建立 p6 全局因子
- 不生成 official R/T/A，不授予生产、通道截断、连续极限、BAL_H 或目标规模资格
- 一个真实物理 RHS 不是原运行保存的 BAL_H 初/中/后期 RHS；该缺口必须保留
- 使用真实双 Floquet、原 DtN 生成器和既有完整局部恢复路径；不以随机矩阵、人工 Laplacian 或单单元代理代替
- 新组装明确采用 exact geometry cache，和历史 legacy-rounded p4 的 CSR 字节身份可能不同；不得宣称复现了原 CSR hash
- ordinary default、其他分支、用户电脑和父任务执行会话都不修改

## 运行入口与分级 Gate

| 阶段 | 可执行工作 | 停止条件 |
|---|---|---|
| Q0 | ABI、分支、源码/输入内容、线程、可用内存/磁盘、watchdog资格 | 任何缺失或不匹配即停；没有资格回执不得运行 |
| Q1 | p4-only mesh/space/MPC、真实端口与独立 p4 原算子；p6 仅 UFL 符号积分规则分析 | cell/mode/row不符、内存/时间越界、端口身份不符即停 |
| Q2 | FFCx p4 单元凝聚、原端口插入、CSR/RHS/recovery导出 | 预分配 projected Gate、非有限值、维度或结构不符即停 |
| Q3 | complex128 reference；恢复完整p4，直接计算原 A4 真残差 | 分解前容量估计不合格、因子资源停止、原A4大于1e-10即停，不放宽 |
| Q4 | 释放128因子后建立64因子；原 A4 complex128 残差最多2次修正 | 非有限值、2次修正仍失败、资源停止即记负结果 |
| Q5 | 内容身份复核、因子数组载荷/实际NNZ、分阶段时间及外部同时树RSS | 缺失独立资源authority或源码漂移不得称通过 |

独立 subreaper watchdog 使用现有实现。并发 heavy case 数量为1，MPI1，OMP/BLAS线程1。显式 simultaneous process-tree 上限为 6 GiB，实际限值再取既有动态内存 envelope 的较小值；零 swap；采样0.25秒；资源违规立即终止完整后代树。当前已实现的入口只执行 Q0–Q2：从独立监督启动到清理的总预算900秒，包含所有新JIT、真实端口和导出。这是诊断停止预算，不是性能通过线。

Q3/Q4 factor入口尚未实现，也未被本次assembly命令启用。必须先审阅实际矩阵、全树RSS和余量，再单独核准factor命令与时间预算；候选预算为每个numeric factor300秒、单次解/原A4检查120秒，但当前监督代码未实施这些未来阶段Gate，不能声称已经具备或执行。

## 容量估计和限制

历史 Task39 p4凝聚 exact 的 MUMPS allocated上界为1,463,000,000 B，21,824 rows；其全过程 RSS为1,785,585,664 B。当前 G0计划29,072 rows、10,912,592 NNZ，CSR complex128/int64原始载荷262,134,792 B。这些数据不能直接保证 SuperLU fill。

SuperLU 的公开 SciPy splu 没有独立 symbolic-only/fill-estimate API。分解前采用声明的保守政策估计（最大4 GiB新增因子及workspace，包含CSC转换）；加当前 resident基线和128 MiB证据余量不得超过实际tree cap，否则不开始numeric。该4 GiB是policy upper estimate，不是数学上界、SuperLU测量或MUMPS symbolic预测。若要求准确的SuperLU symbolic预测作为硬前提，本入口必须停在Q2。

128/64使用同一 ordering/pivot设置，精度引起的实际pivot/fill变化另报。L/U值、索引、indptr和排列字节分别记录；索引与原矩阵没有减半，所以总RSS不能以2倍节省作保证。两个因子不同时持有，释放128后实际resident Gate不过则停止64。

## 为什么需要新的窄入口

现有 V18 runner 的 _build_common 总是建立p6动作、transfer和metric；cell_condensed_stack 立即建立MUMPS factor。它没有p4-only assembly/export或SciPy complex64选项。新入口只调用既有数值内核，在 src 中放研究factor适配，在 benchmarks 中编排与监督；不复制Floquet、DtN、凝聚或恢复算法。

原A4不用装配一份全空间大矩阵。build_same_mesh_physical_action 提供complex128原p4 form-action，P4CellCondensedInverse提供原slave-zero坐标中的完整恢复。后续factor阶段的每一次修正都应直接形成 g-A4c，再经过同一凝聚/恢复和64因子。最终原A4≤1e-10才算本物理RHS的严格研究通过；仅凝聚残差小不能替代它。当前assembly阶段只保存该映射和身份，没有原A4残差结果。完整BAL_H资格仍需真实粗修正RHS及相应对照。

## 环境与证据

新的官方 DOLFINx 0.10 complex栈须单独资格，不调用硬编码WSL3.19的旧activation。资格化至少包括PETSc complex128/整数位宽、Python/MPI/PETSc/DOLFINx/MPC ABI来源、所用src的最小真实FFCx/port/recovery fixture及实际环境manifest hash。运行前冻结源码文件SHA256、git HEAD、dirty状态、输入完整hash、physical/discrete identities和有序模式hash。结果只能称为新云端research实测，不能沿用父运行的source/environment身份。

大型CSR、RHS、recovery映射和局部LU均位于ignored benchmarks/artifacts；Git只收compact记录和准确的正/负/controlled-stop分类。全流程不承诺约2 TB或48小时，也不重跑已有MUMPS-BLR扫描。
