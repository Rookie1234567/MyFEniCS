# Task39extra 阶段总账

| 范围 | 当前状态 |
|---|---|
| 研究对象 | 原始 13.5 nm、Full3D p6/h10、MPI1、80 个 DtN 模式；不是 0.7 nm 已通过模型 |
| 主候选 A2 | 用较低阶 p4 解辅助 p6 迭代；两次实际运行均由用户受控停止，未取得最终场 |
| 诊断参考 A2R | 用原 p4 物理矩阵的一次直接分解替换中间迭代逆，检查中间逆的影响；增加矩阵和分解内存，生产默认不变；实现/小型测试通过，原尺寸 `not_run` |
| 证据边界 | 当前为阶段同步，非 A5 结项；后续阶段尚未完成 |

下表时间单位为秒，内存为 B；峰值指 watchdog 同期进程树 RSS 采样峰值，不是各进程历史峰值之和。

| 正式模型 / 方法 | 状态与原因 | 完整 workflow | S6 / 至 solve 开始 | RSS peak / swap | 最终物理结果 |
|---|---|---:|---|---|---|
| 原 p6/h10，旧 S6，A2 主候选 | `USER_AUTHORIZED_CONTROLLED_STOP_DURING_SETUP`；setup 成本过高，尚未开始 outer | 5946.465141321009 | 5916.818793114 / 未开始 solve | 1582481408 / 0 | outer final `not_available` |
| 原 p6/h10，精确对角优化 S6，A2 主候选 | `USER_AUTHORIZED_COST_CONTROLLED_STOP`；完成 7 次 PC，第 8 次 partial | 3015.3758775380556 | 143.69 / 553.52 | 1849683968 / 0 | outer final `not_available` |
| 原 p6/h10，A2R 诊断参考 | `not_run`；等待实际容量 Gate | — | — | — | `not_run` |

S6 是给迭代提供较便宜修正的辅助计算。精确对角优化省掉计算对角项时不需要的单元耦合，保持原积分及约束；原模型完整 S6 从约 98.6 分钟降至 143.69 秒。后一次至 solve 开始约 553.52 秒还包括其他 setup，不能与 S6 单段混用。早期组件文档中的“优化后尚未运行”描述的是当时状态，后续实测以本表为准，旧证据不改写。

PC 是每次外层迭代调用的辅助修正。后一次 7 个完整 PC 各运行 36 个中间迭代步，其各自 RHS 对应的 A4 真残差依次为 0.846787、0.815692、0.720637、0.794347、0.817342、0.635752、0.803464；中间逆目标 1e-2 未达到，记录为 `INEXACT_INTERMEDIATE`。这些是不同 RHS 的结果，不能串成收敛曲线。第 8 个 PC 未完成；checkpoint 0 的残差 1 只代表初始零解，不能代替最终残差。此次停止说明已观察到较高成本，不能推出方法必然不收敛。

| 数据 / 比较维度 | 已知值与未运行项 |
|---|---|
| rows / independent rows，p6、p4 | 173802 / 164592；53084 / 48960 |
| NNZ、A2R 分解内存 | A2R 原尺寸尚未装配/分解，`not_run` |
| official R/T/A、A_volume、R00_s / R00_p / R00_total、重要衍射级 | 未产生通过最终 residual Gate 的场，全部 `not_run` |
| p/h、Hybrid、M、MPI 扫描 | 原尺寸当前仅 p6/h10、Full3D、80 modes、MPI1；其他比较 `not_run`，不宣称连续极限收敛 |
| 身份 / 资源 | 两次停止的源码、物理/模式 hash、原始路径、内存口径和清场状态见结构化索引 |

证据：[运行索引](records/run_index.json)、[测试摘要](test_summary.md)、[S6 组件证据](setup_diagonal_optimization.md)、[新 A2 停止核验](../../../benchmarks/artifacts/task39extra/original_2bed3d4_v1/stop_verification.json)、[A2R 实现 manifest](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_manifest.json)。大型 raw 保持 ignored，索引以 hash 绑定。

| 后续依赖组 | 当前建议与边界 |
|---|---|
| numerical/core → runner → checker/tests | A2R 作为显式诊断 profile；正式容量及残差证据未取得，不提升为生产默认 |
| compact evidence/docs | 本次独立同步提交；不是最终 selective merge manifest |
| research-only / do-not-merge | A2R 诊断结论保留研究属性；大型 raw/cache 不入 Git |

下一步是在获批的同一父工作流内完成实际装配、一次 symbolic 和资源预测 Gate；只有容量允许才继续 numeric 和唯一 A2R 外层求解。2×符号估计加 1 GiB 缓冲是工程预测，不是实测峰值或严格上界。
