# Task007 response v1

## 结论

Task007 M0–M2 已完成并通过 Case146 独立完整性 checker。本轮是纯 stored-response replay：没有运行新 FEM，没有重试 Task006 的两个 residual 失败点，没有访问 Task006 frozen validation，没有修改 Task006 model lock，也没有开始正式反演。

J1/N1 的 objective identity 和 trained37 P2 离散查询 Gate 通过：11/11 external targets 唯一最小，P2 全部在 1 次在线 query 命中隐藏 tuple。B0 最近离线点没有一次 exact hit；P2 相比固定随机回放的查询中位数明显降低。

连续 P3 posterior-mean MAP 没有通过主 Gate：J1/N1 仅 2/11 满足 `|dh|≤0.25 nm` 且 `|dw|≤0.05 nm`。该负结果已保留，未放宽容差、改变 seeds/target set、删除点或重新调参。因此 Task007 本轮输出不能被解释为已资格化的连续正式代理。

## 实现与合同

- `src/surrogate/task007/objective.py`：J1/J0 标量 objective、N1/N2 权重、固定域缩放、deterministic initial sets、Matérn-5/2 ARD exact GP、expected improvement 和连续 MAP。
- `benchmarks/cases/146_task007_schneider_objective_gp_benchmark/run.py`：M0–M2 deterministic replay runner；目标值只在对应 replay query 后进入 observed set。
- `finalize.py`：只修正在线 query 统计口径（首个 query=1）并从原始轨迹重建 aggregate summaries；没有重新拟合 GP。
- `checker.py`：不调用 runner，从 train37 数组和 Case141 原始 sample JSON 独立重建 J1/J0 与 objective/hash，并验证 leakage、query trace、GP metadata、P3 误差和 identity。

固定身份为 forward SHA `fdf961545f217d620e22800f2704ae9913a6d270`、`S_PROD_FULL3D_STATIC_P5_H10_NY4`、`task002.fixed-n0-orders.v3`；replay universe 为 37+11=48，`(117.5,17.25)` 明确排除。
Task007 clean implementation SHA 为 `75e5cdb`；所有 compact/replay/audit records 均绑定该 SHA。

## Gate 与审计证据

| Gate | 结果 |
|---|---|
| J1/N1 unique replay minimizer | 11/11 pass |
| P2 J1/N1 exact target ≤5 queries | 11/11 pass |
| P2 J1/N1 all ≤11 queries | 11/11 pass |
| P3 J1/N1 continuous tolerance | 2/11；controlled negative |
| Case146 integrity checker | pass |
| 新 FEM / frozen validation / formal inversion | 0 / 未访问 / 未运行 |

GP 审计共 2022 fits，8 个优化初值，jitter 仅按 training LML 选择；所有 LML 有限，1626 个 optimizer warnings 与 1558 个 boundary collisions 均保存到 metadata。详见 `outcomes/OBJECTIVE_GP_MODEL_AUDIT.json`。

## 证据入口

- 总结：[outcomes/summary.md](outcomes/summary.md)
- 独立 checker：[../../benchmarks/cases/146_task007_schneider_objective_gp_benchmark/records/case146_check.json](../../benchmarks/cases/146_task007_schneider_objective_gp_benchmark/records/case146_check.json)
- 方法比较：`outcomes/METHOD_COMPARISON.md`
- 离散轨迹：`outcomes/BAYESIAN_OPTIMIZATION_REPLAY.json`
- 连续 MAP：`outcomes/MAP_RECOVERY_SUMMARY.json`

本轮完成后按任务书停止，等待下一轮审阅；不得据此自动开始新的 FEM、主动学习或 inversion。
