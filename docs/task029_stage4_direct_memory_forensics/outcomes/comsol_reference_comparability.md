# COMSOL 内存参考可比性边界

## 1. 来源

参考文件为 [`../references/comsol_3d_direct_iterative_memory_report.md`](../references/comsol_3d_direct_iterative_memory_report.md)，整理日期 2026-07-13。它汇总另一台 Windows 工作站上的 COMSOL 6.4 已保存模型与日志。

## 2. 机器与内存口径

COMSOL 机器记录 32.38 GB 可用内存、10 核；FEniCS 当前运行在 16 GB 级 Windows 主机的 Docker/WSL2 中，WSL 可见约 13.65 GiB。COMSOL 使用日志进程高水位；Task29 将区分同时总 RSS、各 rank 历史峰值和、cgroup current/peak 与 swap。两者的 GB 数只能作量级参考。

## 3. 网格、DoF 与单元

COMSOL 使用 182,393 个自由四面体、1,178,238 DoF、默认二阶 curl/Nédélec 电场单元和二次几何映射。FEniCS target 使用 boundary-fitted/matched hexahedral 路线，h5/h3/h2 的 FE DoF 约为 44,698/198,438/615,108。缺少可比 matrix nnz/fill 时禁止每 DoF 效率结论。

## 4. 物理差异

COMSOL 为 16 nm block、P 偏振；FEniCS 为 17 nm block、s 偏振。两者都使用 50 x 25 nm 周期、13.5 nm 波长和 80 度入射，但不能据此把 R/T/A 视为同一问题。

## 5. 端口与衍射级

COMSOL 报告关闭附加衍射级，只保留 `(0,0)`。FEniCS Task29 必须保留 `auto_propagating` 的全部传播级、auxiliary unknowns、per-order official R/T、A_volume 与能量闭合。减少模式不是允许的内存优化。

## 6. MUMPS 调查线索

COMSOL 记录的 nested-dissection、内存 relaxation、in-core/OOC 自动策略、BLR off、pattern/reorder reuse 和 iterative refinement 只作为假设来源。Task29 只使用当前 PETSc/MUMPS 构建真实支持并能确认生效的选项；无法映射的字段写 `not_directly_mappable`。

## 7. GMG 后续启示

COMSOL 的 GMRES/TFQMR + 完整 GMG 层次把约 117.8 万 DoF 内存降至约 9–13 GB，说明后续真正 multilevel H(curl) 路线仍有研究价值。但 Task29 不实现 GMG、不修改 Task27 iterative profile，也不以 COMSOL 迭代数或时间作为 direct Gate。

## 8. 允许与禁止的比较

允许：成熟实现的内存量级、MUMPS 配置调查方向、后续多层架构启示。

禁止：跨机器时间排名、RTA reference、无 matrix/fill 数据的每 DoF 效率、要求 FEniCS 达到 COMSOL 的绝对 GB 数、用零级端口替换完整传播衍射级。
