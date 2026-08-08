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

## Review V2：单侧 block-PC screen 结项

V2 把已经通过代数审计的固定 Woodbury action 放进 exact matrix-free block operator，
只做最多 20 步的外层容量 screen。它不是 official Hybrid 求解：不恢复场，也不计算
R/T/A 或 Full3D physical comparison。两次单侧运行都绑定同一 p6/h10、modal p6/h10、
M120/candidate240、MPI8、10/110 nm、10° S、static-condensed 和两份 authority。

| 运行 | 近似侧 | exact 侧 | screen 结果 | 分类 |
|---|---|---|---|---|
| V2-B | bottom | top | final/min true=0.26797784324787316，阈值 0.35，last5 净下降 | BOTTOM_APPROXIMATE_SIDE_PASS |
| V2-T | top | bottom | final/min true=0.3518371324843258，last5 净下降；高于 0.35 正好 0.0018371324843258 | TOP_APPROXIMATE_SIDE_NEGATIVE |

V2-T 的 failure 是严格阈值负结果，不是四舍五入误差或 implementation failure。由于
一正一负，Review V2 §6.3 要求停止；double 20/100/200 全部 not_run_due_to_one_sided_gate。

### Review 采样点

下表直接来自两份 raw solver record；每行依次为 reported、global true、bottom true、
top true、modal true residual。完整 0–20 history 与 apply counters 保存在
[V2 compact record](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v2_block_pc_screen_v1.json)。

| 运行 / iter | 0 | 1 | 2 | 5 | 10 | 15 | 20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V2-B reported | 1.000000 | 0.809778 | 0.722333 | 0.634508 | 0.504982 | 0.358798 | 0.267978 |
| V2-B global true | 1.000000 | 0.809778 | 0.722333 | 0.634508 | 0.504982 | 0.358798 | 0.267978 |
| V2-B bottom true | 0 | 0.937467 | 0.884788 | 0.830776 | 0.762108 | 0.652331 | 0.541203 |
| V2-B top true | 1.000000 | 0.655741 | 0.521764 | 0.402601 | 0.255007 | 0.128736 | 0.068473 |
| V2-B modal true | 0 | 2.26e-13 | 1.57e-13 | 7.71e-14 | 4.53e-14 | 2.90e-14 | 1.64e-14 |
| V2-T reported | 1.000000 | 0.896505 | 0.819237 | 0.726754 | 0.612256 | 0.450678 | 0.351837 |
| V2-T global true | 1.000000 | 0.896505 | 0.819237 | 0.726754 | 0.612256 | 0.450678 | 0.351837 |
| V2-T bottom true | 0 | 6.74e-13 | 5.64e-13 | 5.12e-13 | 5.12e-13 | 3.16e-13 | 2.12e-13 |
| V2-T top true | 1.000000 | 0.896505 | 0.819237 | 0.726754 | 0.612256 | 0.450678 | 0.351837 |
| V2-T modal true | 0 | 1.83e-13 | 1.44e-13 | 1.09e-13 | 7.91e-14 | 4.41e-14 | 2.84e-14 |

### 代数与生命周期边界

两侧 callback 都满足 identity=0、determinism=0、repeat hash 一致、K rank=40、
arrays finite 和 no nested local KSP。V2-B/T 的近似侧 linearity error 分别为
1.9458251250889472e-15 与 1.9498727881145686e-15，K condition 分别为
3.033166890369435 与 4.162687539173754；两次 modal Schur 均为 240×240、rank 240，
且 build apply 为 bottom/top=480/480。B 的 factor identity 是 bottom direct/ILU=0/1、
top=1/0；T 反向为 1/0、0/1；online action increments 两侧均为 40。

两份运行的 exact/direct action、fixed base、components、outer context 均按记录释放，
borrowed action survivor=true，swap=0 且无 orphan。上述通过证明的是固定 action、block
operator 和生命周期合同；它不把 top approximate candidate 称为 production solver，也不
推断未经审查的其他 PC 家族。

| raw evidence | 相对路径与 SHA256 |
|---|---|
| V2-B solver / summary | ../../../benchmarks/artifacts/task037b/v2_b_bottom_approx_5b94060_mpi8/solver_record.json / 69c1688c0e6b024d0e0eb5fe95f10ad8d467ad88bde7053996a599eb0cb598b2；../../../benchmarks/artifacts/task037b/v2_b_bottom_approx_5b94060_mpi8.json / ed8cd8ced09d5964cbef12e6590fb6f126bc831ac7d3734c57dcea13b0cf8b78 |
| V2-T solver / summary | ../../../benchmarks/artifacts/task037b/v2_t_top_approx_5b94060_mpi8/solver_record.json / a5e19a1391462d093425a67d8d9cd7cfe72b431ebdaff9e57753ed99bae73956；../../../benchmarks/artifacts/task037b/v2_t_top_approx_5b94060_mpi8.json / c092aaa13f94af9a7a3c508dca64c343fc940872cfcf57838a3160374c4d6cea |
