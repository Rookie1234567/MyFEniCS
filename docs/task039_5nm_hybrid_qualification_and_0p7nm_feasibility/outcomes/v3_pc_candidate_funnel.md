# V3 side-PC candidate funnel

本页记录 Task39 V3 中 side preconditioner 的受控筛选。这里的 contraction rho 是
side action 对固定探针残差的收缩比；越接近 0，说明一次 side 预条件应用越能降低
残差。它只是为后续全局 Hybrid iterative 候选筛选 side PC，不等于全局物理资格。

## Candidate B 与 C1

| candidate | side setup | measured outcome | classification | next decision |
| --- | --- | --- | --- | --- |
| B | whole-endcap ILU(0) + one-pass dynamic DtN Woodbury | 8/16/32 均未满足 median `<=0.1`、worst `<=0.3`；side-online peak `17666.33203125 MiB` | `USER_AUTHORIZED_CANDIDATE_B_NUMERICAL_NEGATIVE` | 不进入 global outer |
| C1 | whole-endcap ILU(1) + 同一 one-pass dynamic DtN Woodbury | bottom median/worst `26018.790046350907 / 34401.291596737974`；top `1307.8809666185202 / 1921.6148166351625` | `USER_AUTHORIZED_CANDIDATE_C1_NUMERICAL_NEGATIVE` | 不运行 C2/ILUT 或同类 global candidate |

C1 的每侧 `pass` 只表示该 side 的向量测量有限且完成；最终裁决使用
`rho_summary.candidate_C_pass=false`。bottom 的 physical side RHS 是零向量，因此被标记为
`degenerate_uninformative`，不参加 median/worst；其余 direct residual、四个固定 seed
和两个 early-Krylov residual 均被逐项保留在 ignored checkpoint 中。

## C1 资源与因子证据

- run root：`results/task039_v3_8_candidate_c1_ilu1_formal_mpi8_after_lifecycle_fix`
- source SHA：`5f924c896f5dd6715cba2d3d269f7c98aac7b54d`
- producer SHA：`5bfab734a9ca053b69fa1f3f20d907aacbf8b07f`
- 5 nm / 1 degree grazing / phi=0 / S / p6-h5 / M480 / MPI8；external keys `600`，verified shards `32`
- 每侧 factor rows `51840`，source NNZ `40154400`，factor NNZ `85706136`，估算 CSR payload `1714330144 bytes`
- 两侧 base factor simultaneous total `2`；每侧 direct/global factor `0/0`；cleanup 后 factor `0`，`factors_released=true`
- C1 total process-tree RSS peak `82360.7890625 MiB`，其峰值位于 research direct-payload transient；swap `0`
- C1 side-online 区间重算 peak `18627.58984375 MiB`；总峰值和 side-online 峰值不可混称
- B checkpoint 没有 source/factor NNZ 或 bytes 字段，因此 C1 对 B 的 factor NNZ/bytes 比值为 `not_recorded`

C1 不是 implementation failure，也不是资源 hard-stop；它是用户授权的数值负结果。首轮
C1 的 cleanup schema 接线失败仍作为独立历史 raw 保留。

ILU(1) 的 factor NNZ 相比 source NNZ 已约为 `2.13x`，但 contraction 仍严重恶化；当前
PETSc/SLEPc 环境未提供本任务所需的受控 ILUT/drop 配置。基于这一实测证据，本轮不运行
C2/ILUT，也不运行任何同类 global candidate。下一步若继续，只能由主审另行批准新的、
有数学依据的 side-PC 设计；本页不把 C1 提升为 production qualification。

## Evidence

完整逐 probe、factor timing、lifecycle、checkpoint 和三份 telemetry 保存在 ignored
run root；tracked compact record 为
[`task039_v3_8_candidate_c1_ilu1_formal_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_8_candidate_c1_ilu1_formal_v1.json)。
