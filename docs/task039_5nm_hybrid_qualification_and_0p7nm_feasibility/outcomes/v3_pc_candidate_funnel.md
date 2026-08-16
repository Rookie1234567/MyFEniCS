# V3 side-PC candidate funnel

本页记录 Task39 V3 中 side preconditioner 的受控筛选。这里的 contraction rho 是
side action 对固定探针残差的收缩比；越接近 0，说明一次 side 预条件应用越能降低
残差。它只是为后续全局 Hybrid iterative 候选筛选 side PC，不等于全局物理资格。

## Candidate B、C1 与 E

| candidate | side setup | measured outcome | classification | next decision |
| --- | --- | --- | --- | --- |
| B | whole-endcap ILU(0) + one-pass dynamic DtN Woodbury | 8/16/32 均未满足 median `<=0.1`、worst `<=0.3`；side-online peak `17666.33203125 MiB` | `USER_AUTHORIZED_CANDIDATE_B_NUMERICAL_NEGATIVE` | 不进入 global outer |
| C1 | whole-endcap ILU(1) + 同一 one-pass dynamic DtN Woodbury | bottom median/worst `26018.790046350907 / 34401.291596737974`；top `1307.8809666185202 / 1921.6148166351625` | `USER_AUTHORIZED_CANDIDATE_C1_NUMERICAL_NEGATIVE` | 不运行 C2/ILUT 或同类 global candidate |
| E | ILU(0)+动态 DtN Woodbury 上的固定残差误差子空间校正 | bottom `6.767346265947249 / 7.752279149310453`；top `9.429046770914342 / 10.4485053168248` | `USER_AUTHORIZED_CANDIDATE_E_NUMERICAL_NEGATIVE` | 不进入 global outer；不扫描 seed/rank/depth |

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

## Candidate D：exact-side 研究 oracle（V3-11）

Candidate D 不是普通生产 PC，而是用户授权的实验性 hybridized direct-side block-LDU
oracle。它对 bottom/top 各保留一个 exact sparse factor，配合同一动态 DtN Woodbury
动作；全局 Hybrid direct factor 为 `0`，outer 在零初值 FGMRES 下 1 次迭代达到五项
残差限值。这个结果证明局部 side inverse 的数值强度，但 exact factor 的构造成本、
生命周期和通用 production 接线仍需另行资格化，所以不能改写为 production success。

| 指标 | V3-11 measured |
| --- | ---: |
| reported/global/bottom/top/modal residual | `2.10121e-10 / 2.10122e-10 / 9.06975e-12 / 1.95048e-10 / 4.33722e-11` |
| process-tree peak | `51149.70703125 MiB = 49.95088577270508 GiB`，swap `0` |
| 相对 Hybrid direct / Full3D direct 节省 | `41.250535704287% / 46.802822979879%` |
| cleanup 后 factors | bottom/top/global `0/0/0`；explicit components released，collective cleanup completed |

峰值发生在 coupling 尾部的 `post_coupling_heap_cleanup` 之前。Full3D strict channel
comparison 仍为 diagnostic-only；Hybrid-direct integrated checker 与 selected E/H
通过。Candidate E 的 side-capacity 结果见下文。

## Candidate E：固定残差误差子空间校正

Candidate E 尝试从固定的、与验证探针不重叠的 8 个 global-index seed 中学习
ILU(0)+动态 DtN Woodbury 一次应用后反复出现的误差方向。通俗地说，它先用 16 层
固定的 block-Arnoldi/MGS 过程建立一个小的误差子空间，再用固定的线性校正动作修正
验证残差；它不使用 physical RHS、direct residual 或验证探针训练，也不引入 exact LU。
两侧最终 retained rank 都是 `32`（上限 `128`），不是通过补 seed 或扫描 rank 得到的。

| 项目 | bottom | top |
| --- | ---: | ---: |
| informative probes | `7`（physical zero，excluded） | `8` |
| median / worst rho | `6.767346265947249 / 7.752279149310453` | `9.429046770914342 / 10.4485053168248` |
| Gate `median<=0.1, worst<=0.3` | fail | fail |
| retained rank / layers | `32 / 16` | `32 / 16` |
| R condition | `12.404244482859818` | `11.33900546651523` |
| QR reconstruction / Q orthogonality | `3.4844e-16 / 3.9968e-15` | `3.5224e-16 / 2.8866e-15` |

Candidate E 的 side report `pass=true` 只表示向量测量 finite 且完成；正式裁决使用
两侧的 median/worst，因此分类为
`USER_AUTHORIZED_CANDIDATE_E_NUMERICAL_NEGATIVE`。它明显优于 C1 的 contraction 数值，
但远差于 Candidate B 的 32-step 结果（bottom 约 `0.9486/0.9618`，top 约
`0.9699/0.9792`），所以不能支持 global outer，也不能通过增加 seed、rank 或 depth
扫描来追逐结果。

Candidate E 两侧各有一个 base ILU(0) factor，同时 live base factors 为 `2`；local
direct factor 和 global Hybrid direct factor 均为 `0`，清理后两侧 factor count 均为
`0` 且 `factors_released=true`。全过程 peak 为 `51101.28515625 MiB`、swap `0`，
低于 `69651.3 MiB`；但这是 side-capacity 运行的资源子Gate，不是 Hybrid iterative
production qualification。峰值发生在 post-coupling cleanup 之前的 setup transient，
而 Candidate-E side-online 区间 peak 仅 `17618.02734375 MiB`，两种口径不可混称。

Candidate E 为验证 `x*` 的 side residual 按合同读取了 hash-bound direct payload；这不等于
加载 independent reference，也没有运行 identity reference、global KSP、recovery 或
field/RTA。完整 compact evidence 见
[`task039_v3_8_candidate_e_side_capacity_formal_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_8_candidate_e_side_capacity_formal_v1.json)。
