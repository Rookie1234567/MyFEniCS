# 合并建议

| 内容 | 建议 | 最新证据 |
|---|---|---|
| `src/solvers/condensed_dtn.py` 通用凝聚工具 | 可合并 | serial/MPI4 单测、h5/h2 actual action 通过 |
| matrix-free condensed operator | 可 opt-in 合并 | h2 MPI1/MPI4 最大 action error `1.001e-15` |
| auxiliary recovery/back-substitution | 可合并 | 非单位 H 与 PETSc block 回归通过 |
| 流式 monitor、粗矩阵 rank gate、内存生命周期修复 | 可合并到 research runner | 长任务中断可恢复证据，h5 smoke 通过 |
| topology/Floquet coarse PC | 仅 research-only | h2 最低 `7.051e-4`，未到 `1e-6` |
| custom explicit additive Schwarz | 仅研究保留 | h5 有效，h2 ILU2 速度失败 |
| adaptive enrichment/defect correction | 不进入 production | 没有可测收益 |
| ordinary auxiliary solver | 保留且不改默认 | 权威 reference/fallback |
| production default | 不修改 | h=2 residual、R/T/A、MPI PC gate 未通过 |

Task026 可以按“架构成功、求解器研究未完成”选择性合并；不得把整个 research runner 宣称为 production candidate。
