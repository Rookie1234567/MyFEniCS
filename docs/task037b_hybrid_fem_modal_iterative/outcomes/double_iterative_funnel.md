# Task037b H7-H10：双侧 iterative funnel 边界

## 停止矩阵

H7-H10 依赖 H5 双侧 local inverse 先通过。本次 bottom 与 top 在同一冻结 p6/h10、M120、MPI8 配置下均未资格化，因此后续 funnel 不启动。

| 阶段 | 状态 | 直接原因 |
|---|---|---|
| H5b | `LOCAL_INVERSE_FAMILY_NEGATIVE` | bottom 1/11、top 0/11；非零 RHS 在 300 iterations 后仍为 reason=-3 |
| H5c | not_run | H5b numerical Gate 未通过 |
| H6 | not_run | H5 双侧失败触发停止 |
| H7 | not_run | 同一前置停止点 |
| H8 | not_run | 同一前置停止点 |
| H9 | not_run | 同一前置停止点 |
| H10 | not_run | 同一前置停止点 |

这里的 funnel 是任务书规定的后续逐级验证，不是已经存在的失败算法结果。不得用 H5 candidate 的内存记录或重复解一致性替代后续数值 Gate。

## 边界

H5 candidate 使用的是唯一冻结的 partition ASM + shifted ILU(0) family；本负结论不否定 Hybrid 模型、exact block action、exact block-LDU，也不证明任何未经授权的 PC 家族不可能。若后续需要恢复 H7-H10，必须新建 review，重新指定算法与 Gate；本 docs closeout 不扩大范围。

参见 [H5 local matrix evidence](local_endcap_inverse_matrix.md)、[总览](summary.md) 与 [测试汇总](test_summary.md)。
