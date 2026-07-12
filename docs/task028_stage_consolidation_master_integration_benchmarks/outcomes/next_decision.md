# 下一步决策

## 当前建议

暂停新算法任务，先由 ChatGPT 进行 Task28 Review V2。审查重点：

| 优先级 | 项目 |
|---|---|
| P0 | h2 record的reported/condensed/full residual一致性 |
| P0 | ordinary default未改变 |
| P0 | stable module没有Task编号研究依赖 |
| P0 | benchmark目录与results目录实际边界及direct/iterative新record |
| P0 | automatic checker失败退出与commit relation语义 |
| P0 | 环境`qualified_local_image`限定是否诚实充分 |
| P1 | total RSS字段定义与文档一致 |
| P1 | Task000-027分类/替代关系 |
| P2 | README和capability matrix可读性 |

V2审查通过并经用户同意后，才将该分支合并到 master。Task029 不在本轮启动。

## 后续研究候选

未来若继续求解器研究，优先做固定profile的角度/波长/材料小范围鲁棒性矩阵，再讨论h=1.5；不恢复已关闭的spectral/GenEO盲扫。
