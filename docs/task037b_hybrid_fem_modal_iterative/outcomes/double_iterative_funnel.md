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

## Review V2 单侧 Gate 后的停止

V2-B bottom approximate 通过 20-step screen，V2-T top approximate 的
final/min true residual 为 0.3518371324843258。它虽从 0.428252 降到 0.351837，
仍严格高于 0.35，因此两侧不是都通过。按 Review V2 §6.3，唯一正式分类是
TOP_APPROXIMATE_SIDE_NEGATIVE。

| 后续 profile | 状态 | 原因 |
|---|---|---|
| double / max_it=20 | not_run_due_to_one_sided_gate | V2-T 严格 0.35 Gate 未通过 |
| double / max_it=100 | not_run_due_to_one_sided_gate | 同一前置停止点 |
| double / max_it=200 | not_run_due_to_one_sided_gate | 同一前置停止点 |
| full Hybrid solve、R/T/A、field、12+12、Full3D comparison | not_run | V2 bounded screen 不是 official physics |

V2-B/T 的 callback、modal Schur、factor identity、online apply count、lifecycle、no-swap
与 no-orphan 合同均通过；V2-T 的失败只属于 fixed top approximate side capacity。
因此结论是 exact matrix-free block operator pass、exact block-LDU pass、DtN Woodbury
algebra pass、bottom fixed approximate one-sided capacity pass、top fixed approximate
one-sided capacity negative；双端低内存近似逆资格未证明。

两侧 process-tree peak 都超过 6 GiB standalone resource-positive 参考线，故没有
resource-qualified candidate。T 的较高峰值包含一个 exact bottom direct factor，不能拿
它预测未来 double screen。LOR、AMS/HX、p2/p4、p-multigrid、full-space ILU 继续冻结，
不因本次 stop 重新开启。

V2-B/T 的完整 0–20 history、raw artifact 路径和 SHA 见
[V2 compact record](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v2_block_pc_screen_v1.json)。
