# V5 h4 Hybrid iterative 最终边界

本页把 h4 的“能算出数值”和“能在内存目标内完成”分开。前者要求完整 residual/physics，后者要求同口径的 process-tree RSS；任何一项缺失都不能写成完整资格。

## 结论总表

| 路径 | 数值/物理 | 内存证据 | 最终分类 |
| --- | --- | --- | --- |
| Hybrid direct h4 | own residual、projection、traction、R/T/A/A_volume、canonical 与 external identity 通过 | matched reference process-tree peak `93.377006531 GiB` | `HYBRID_DIRECT_H4_OWN_PASS` |
| V4 exact-side iterative h4 | 1 outer iteration；五残差均 `<=5e-9`；recovery/physics 与 direct checker 通过 | `104.334560394 GiB`，相对 direct 为 resource regression | `HYBRID_ITERATIVE_H4_EXACT_SIDE_NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL` |
| V5-2 exact-side setup-only | setup peak `85.376991272 GiB`；对象/marker 归因完成 | 相对 advancement line `84.039305878 GiB` 未满足 | baseline positive，非完整 qualification |
| V5-3/4/5 compaction | factor-only、single modal Schur、固定 GMRES、streaming-W component evidence | h4 fresh full-solve RSS 未重新测量 | research evidence only |
| BLR factor family | 两个冻结 profile 均超过 `59.7638938904 GiB` resource limit | 1e-5: `75.89627456665039 GiB`；1e-3: `95.39834594726562 GiB` | family closed, resource negative |
| fixed-budget side Krylov | modal traction +/− true residual `0.748109402736452`/`0.737754681505050`，limit `0.01` | setup interval `21.677326202393 GiB`，但 run 因数值 Gate 受控停止 | controlled numerical negative |

固定预算 raw 的 manifest/run summary 仍是 `status=launching`、`exit_status=null`，ledger 为 `in_progress`；没有 final cleanup marker，所以 cleanup count 是 `not_available`，不是零。

## V5 的正式边界

- `V5-8` full formal、top、outer solve、recovery、field、canonical、R/T/A 均 `not_run`。
- 当前没有“数值合格且节省内存”的 h4 Hybrid iterative。20% meaningful target `74.701605225 GiB` 没有建立。
- `Full3D` 新 heavy、0.7 nm PDE 和 arbitrary-3D qualification 均未执行。
- ordinary defaults、既有 exact mathematics 和历史 BLR/iterative raw 均不改写。

## 证据入口

- [h4 exact-side memory attribution](v5_h4_exact_side_memory_attribution.md)
- [exact-side compaction](v5_exact_side_compaction.md)
- [streaming-W evidence](v5_streaming_woodbury.md)
- [BLR compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_factor_light_side_inverse_v1.json)
- [fixed-budget compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_fixed_budget_side_krylov_component_v1.json)
