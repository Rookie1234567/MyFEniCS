# Case100：static-condensed Full3D iterative Task37 F0/F3/F5b

## 当前 M3a MPI scaling 证据索引

- [M3a MPI1/2/4/8 compact record](records/task37_m3a_mpi_scaling_v1.json)：四组
  full solve 的 residual、R/T/A、process-tree memory、wall、factor inventory、
  raw artifact hash 与 canonical comparison；
- [M3a MPI scaling report](../../../docs/task037_static_condensed_full3d_iterative/outcomes/m3a_mpi_scaling_comparison.md)：
  统一表格和通俗结论。

四组 numerical/physical/canonical identity 均通过；MPI1/2/4 通过
`<=10.30 GiB`，MPI8 仅该内存 Gate 失败。MPI1/2/8 carrier 为 `a51c5457`，
MPI4 numerical anchor 为 `2631a4c4`；carrier 只改变 runner eligibility/tests，
没有改变 `src/` 数值内核或 ordinary defaults。

## 前序源码 v2 证据索引（由上节扩展）

当前 closeout source 为 `2631a4c47258c9def919530787e409774b8ce029`。最新 compact evidence：

- [Direct v2 authority record](records/task37_direct_authority_v2.json)：MPI8、return 0、official=true、canonical export 完成；
- [M3a overlap .125 partition full record](records/task37_m3a_overlap0125_partition_full_v1.json)：MPI4、no-global A/F、16 slabs、partition weights、official=true；
- [M3a full outcome](../../../docs/task037_static_condensed_full3d_iterative/outcomes/m3a_overlap0125_partition_full.md)：canonical/physical/norm、12+12 channels、nested timing 和资源口径。

`60402` active canonical packets 是由 `51192` 个 independent active coordinates 展开/约束还原后的完整 original-trace packets；full FE 为 `173802`。M3a full 只在 MPI4 完成，历史 MPI8 M3a 只有 screen20 resource-negative，因此不能宣称 same-candidate MPI4/8 formal identity。ordinary defaults、历史 M2c/M3a negative 和 M4d negative 均保留。

## 历史 response_v0 阶段快照（已由上节 v2 索引取代）

F0 direct authority、F3 assembled screen、F5a action oracle 已完成；F5b
assembled matrix-free full 的 solver residual、物理 observables 和 12+12
channel Gate 通过；raw vector indexwise Gate 与资源 Gate 为 controlled
negative，最终分类为 `PARTIAL_WITH_CONTROLLED_NEGATIVES`。记录与报告见
`records/task37_f5b_matrix_free_full_v1.json`、
`docs/task037_static_condensed_full3d_iterative/outcomes/matrix_free_report.md`
和
`docs/task037_static_condensed_full3d_iterative/outcomes/resource_and_mpi_report.md`。

F5b 在 setup 形成 fine F、完成局部因子/粗基后，于 outer KSP 前释放 F，
再由 cell-local Schur action 施加 fine action；因此不是 never materialized。

Stage 0 contract 已冻结；F0 direct 已在 current-source clean SHA
`03f4fa02aece62bb2f193c01616177bffff0aa51` 上完成并通过。compact tracked
record 为 `records/task37_direct_authority_v1.json`，审阅说明为
`docs/task037_static_condensed_full3d_iterative/outcomes/direct_authority.md`。

静态凝聚的直观含义是：在每个单元内先消去只属于该单元的未知量，全球
系统只保留界面/trace 与 DtN auxiliary 行，求解后再恢复完整有限元场。
这样通常会降低全局矩阵规模，但可能增加界面稠密度、局部消元和恢复
时间，所以本 case 同时要求 numerical 与 resource evidence。

### 冻结身份

- geometry/source: Task034 fixed rectangular block grating；
- wavelength: 13.5 nm；
- incidence: normal angle 80°，等价 grazing angle 10°；phi=0；
- polarization: S；
- finite element: p6 Nédélec；
- mesh: Case096 exact h10 topology，boundary-fitted conforming hexahedron；
- MPI: 8；
- backend: assembly_time_static_condensed；
- direct entry: existing benchmarks/run_task033_full3d_watchdog.py；
- historical acceptance source: benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json；
- historical raw authority is reference only; F0 must run current source once.

### 证据规则

Case100 不复制 Case096 的 heavy raw evidence。raw vector 与大型 solver/
watchdog 输出必须写到 ignored benchmarks/artifacts/... run directory；
tracked record 只保留路径、hash、shape、来源和必要的 compact gate 结果。
active trace 与 recovered full FE vector 使用当前运行的 ownership-range
ascending order、little-endian complex128；hash 输入包含 namespace、shape、
dtype 和 ownership-order bytes。该顺序不是已证明的跨 partition physical
canonical identity。

Direct F0 的资源上限沿用已资格化 Task035c p6/h10 口径：
warning 32 GiB、termination 48 GiB、timeout 7200 s、poll 0.25 s、swap=0，
并使用完整 process-group 的 TERM、5 秒 grace、KILL 语义。Task37 iterative
candidate 的 warning 10 GiB / termination 14 GiB 不适用于本 direct case。

F4、F5c、F6、Hybrid、hp、0.7 nm、Task037b 与任何新的
campaign/registry/framework 均不在当前授权范围。

两次 ignored serial smoke（p2/h50、p6/h50）均在 release/KSP 前因 5 层
z 网格上的固定 75 维 Floquet 粗基 singular；既不证实也不否定 F5b，
本阶段不修改粗基。
