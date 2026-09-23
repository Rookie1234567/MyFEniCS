# Task041 Response V9：13.5 nm Hybrid 与 5 nm fixed-eight 配对收口

## 结论

13.5 nm 显式 `cell_condensed` Hybrid 回归的五项 true-residual 与物理 Gate 通过；完整 H2 可比观测量的数值比较通过，但旧 H2 总 checker 因 V6 资源合同口径而失败。Full3D secondary checker 未运行。5 nm 本轮只完成固定八 RHS 的 full→释放→cell_condensed 组件配对，不是完整 5 nm consumer：8 对中 bottom 4/4 通过，top 2/4 通过，正式配对门失败。

| 5 nm top RHS | 响应差 `e_x` | action 差 `e_A` | 原门 | 结果 |
|---|---:|---:|---:|---|
| formal column 12 | `2.361490171146484e-8` | `6.410084067690454e-8` | 两项均 `<=1e-8` | 失败 |
| formal column 493 | `2.584982558163933e-8` | `7.016739340072887e-8` | 两项均 `<=1e-8` | 失败 |

两项 side residual 约 `0.00938705`，满足 `0.01`，但不能替代失败的配对门。两侧同 mesh/MPC/layout 与 RHS 身份、full 因子先销毁及释放门均通过。Full 八响应 `1185.079661994 s`、condensed `1173.609554288 s`，约降时 `0.97%`，仅为未通过数值门的组件计时，不构成性能资格。用户授权的本场专用 cap 为 `68,719,476,736 B`；authority/tree 峰 `65,674,952,704 B`，warning 已越过、hard cap 未越过，swap/pswp delta 为零。

Finalizer 实际执行并写账，但以 `service_boundary_failure` 结束：public result 未完成、service 非正常退出；ledger 检查和清场检查通过。V5 ledger 唯一新增本场 `5069.064609306 s`，总额 `23836.239034977996 s`；本报告不重复计费。

完整 5 nm consumer、RTA、EH 与 24 小时完成均为 `not_run`/`not_assessed`。不要把本固定八 RHS 组件探针写成完整 5 nm 计算通过。

## 历史阶段入口

| 阶段 | 简要结果 | 证据 |
|---|---|---|
| F1 | `b518fb33dbff523bee8c13d31345025f183d40d5` 在 transfer 加入 `entity_closure` 与 `reference_entity_trace_v1`，按 Basix 实体支撑构造边/面传递；这是改传递构造，不是抬高一致性阈值。修复前 F1c 历史负结果为 `1.3116919128020489e-11 > 1e-11`；该历史失败与本次 top 配对失败的原因未作关联，后者根因仍未定位 | [Basix 支撑分析](../../results/task041_review_v6_transfer_and_5nm_24h/f1a_mpi8_transfer_diagnostic_20260922/run_20260922T005426.371809368Z/f1d_basix_support_compact_v3.json) · [F1c/F1d 离线摘要](../../results/task041_review_v6_transfer_and_5nm_24h/f1a_mpi8_transfer_diagnostic_20260922/run_20260922T005426.371809368Z/f1c_f1d_offline_compact.json) |
| F2 | MPI8 tiny-FE full→释放→cell-condensed backend equivalence 通过；不等于 5 nm 物理求解通过 | [V6 中心 outcome](outcomes/transfer_fix_5nm_24h_v6.md) |
| F3a | 13.5 nm 五项 residual/物理 Gate 与 H2 数值向量通过；Full3D secondary 未运行，旧 H2 资源合同使总 checker fail | [V6 中心 outcome](outcomes/transfer_fix_5nm_24h_v6.md) |
| F3c 5 nm | 两次实现错误、一场旧 cap 资源停止、一场 cap64 配对数值失败；细节见中心表 | [尝试记录与 compact v2](outcomes/transfer_fix_5nm_24h_v6.md) · [compact v2](../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/preparation/f3c3_cap64_r1_20260923/cap64_r1_postmortem_compact_v2.json) |

详细逐 RHS 数值、manifest 哈希、资源、finalizer 与费用见[中心 outcome](outcomes/transfer_fix_5nm_24h_v6.md)及[机器可读记录](outcomes/records/task041_v6_transfer_5nm_24h.json)。
