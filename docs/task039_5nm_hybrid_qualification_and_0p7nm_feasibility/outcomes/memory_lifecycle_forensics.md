# Review V1 E10：内存生命周期取证

## 1. 口径

“stage-aligned memory”表示每个固定生命周期节点都有同一进程树时间线上的 RSS、PSS
和 USS 样本。它能回答峰值发生在哪个阶段；单独的全程 peak 只能回答运行期间最高
占用是多少，不能把峰值归因给 QEP、耦合、因子或回收阶段。本次正式 M960 没有持久化
stage-event JSONL 或 E10 ledger，因此不补造分阶段数值。

## 2. M 系列 RSS measured series

| case | RSS | PSS / USS | stage snapshots | 来源 |
| --- | ---: | --- | --- | --- |
| M120 | `8.720 GiB` | not_available in E10 compact series | not_available | [T5 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json) |
| M240 | `10.742 GiB` | not_available in E10 compact series | not_available | [T5 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json) |
| M480 | `22.264 GiB` | not_available in E10 compact series | not_available | [T5 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json) |
| M960 prior trace / pre-solution | `22.008 GiB` | not_available | not_available | [T5 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json) |
| M960 formal direct | `71502.582 MiB` (`69.827 GiB`) | PSS `69746.089` / USS `69465.102 MiB`, measured | not_available | [E7 direct record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_result_v1.json) |

四项历史 RSS 取自 T5 compact record；正式 M960 direct 的外层
`run_summary.json` 记录 RSS/PSS/USS 和 swap。不同指标是独立峰值，不能拼成同一时刻
的内存向量。formal direct swap 为 `0 MiB`，smaps attempted/complete 为 `13165/13163`。

## 3. Formal M960 carrier 与阶段边界

| 项目 | 值 | 分类 |
| --- | ---: | --- |
| selected memory | `228.0657501220703 GiB` | measured |
| warning / configured hard | `180 / 220 GiB` | contract |
| effective hard stop | `205.2591751098633 GiB` | derived |
| global process-tree RSS/PSS/USS | `71502.582 / 69746.089 / 69465.102 MiB` | measured independent peaks |
| stage-aligned RSS/PSS/USS | not_available | no persisted stage snapshots |
| ordered cleanup proof | not_available | exit does not prove destruction order |

已有 E10 stage contract 的 18 个节点和顺序见 [resource ledger](resource_ledger.md)。
本次 carrier 只能证明全局 resource authority，不能证明节点级的 simultaneous peak。

formal record 还报告了 basis `245575680 B`、coupling `60218896 B`、projection estimate
约 `29867528/30351368 B`、augmented matrix estimate `1760047816 B`，modal Schur
未 materialize、factor resident bytes not_available。这些是对象容量或估计，不能相加
冒充 process-tree RSS；它们也不能单独解释 69.827 GiB 峰值。

## 4. 保守归因

| Review taxonomy | 结论 | 依据 |
| --- | --- | --- |
| `UNATTRIBUTED_RUNTIME_OR_ALLOCATOR_HIGH_WATER` | determined | 只有全局 peak measured，缺少阶段归因 |
| `LIFECYCLE_OVERLAP_DOMINANT` | hypothesis / not_established | 没有 stage-aligned snapshots，不能证明重叠主导 |
| `QEP_WORKSPACE_DOMINANT` | not_established | 无节点级 peak |
| `MODE_OBJECT_REPLICATION_DOMINANT` | not_established | 无节点级 peak |
| `COUPLING_ASSEMBLY_DOMINANT` | not_established | 无节点级 peak |
| `LOCAL_FE_FACTOR_DOMINANT` | not_established | factor resident bytes not_available |
| `MODAL_SCHUR_DOMINANT` | not_established | modal Schur 未 materialize |

因此不能因为某个 payload 或对象容量较小，就断言某一阶段主导。也没有开发新的
memory sampler、modal matrix-free、压缩或 owner-only 重构；不重跑 M960。

## 5. 证据入口与限制

- [E10 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e10_memory_lifecycle_v1.json)
- [E7 M960 direct compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_result_v1.json)
- [T5 resource ledger](resource_ledger.md)
- [E7 numerical audit](m960_trace_numerical_audit.md)

最终分类为 `E10_MEMORY_GLOBAL_PEAK_MEASURED_STAGE_ATTRIBUTION_NOT_AVAILABLE`。这是一项
证据边界，不是数值 solver failure，也不把 T4/T5 的历史负结果删除或覆盖。
