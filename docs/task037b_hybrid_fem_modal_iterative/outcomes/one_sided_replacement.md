# Task037b H6：单侧 replacement 边界

## 当前状态

H6 未运行。任务书要求 H5 双侧 local inverse 在冻结 RHS 集合上先完成资格化；本次 H5b bottom/top 均未通过，因此按顺序停止，不把单侧 replacement 另写成已经验证的候选。

| 阶段 | 状态 | 原因 |
|---|---|---|
| H5a exact local reference | pass | bottom/top 各 11/11，通过显式 oracle 与 action residual |
| H5b bottom local inverse | controlled negative | 11 项中仅零 physical RHS 通过；其余 reason=-3、max_it=300 |
| H5b top local inverse | controlled negative | 11/11 均 reason=-3、max_it=300 |
| H5c | not_run | H5b 前置数值 Gate 未通过 |
| H6 one-sided replacement | not_run | H5 双侧失败触发任务停止 |

## 不应作出的推断

H5a 的 exact/direct reference 通过，且 H3/H4 exact authority 已通过；因此本停止点不是原始/direct Hybrid 物理失败，也不是 action、ownership、资源或 telemetry 接线失败。H6 若未来重新开启，必须有新的 review 明确授权，不得在本文件范围内自行更换 PC、放宽 `1e-8`、缩减 RHS 或改用未审查算法。

结论：`LOCAL_INVERSE_FAMILY_NEGATIVE` 只适用于本轮冻结的双侧 local inverse family；H6 保持 `not_run`。

参见 [H5 local matrix evidence](local_endcap_inverse_matrix.md) 与 [总览](summary.md)。
