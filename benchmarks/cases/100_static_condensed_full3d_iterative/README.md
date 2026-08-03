# Case100：static-condensed Full3D iterative Task37 F0/F3/F5b

## 当前阶段

F0 direct authority、F3 assembled screen、F5a action oracle 已完成；F5b
assembled matrix-free full 已授权但未运行，唯一正式 p6/h10 MPI8 仍未执行。

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

## 冻结身份

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

## 证据规则

Case100 不复制 Case096 的 heavy raw evidence。raw vector 与大型 solver/
watchdog 输出必须写到 ignored benchmarks/artifacts/... run directory；
tracked record 只保留路径、hash、shape、来源和必要的 compact gate 结果。
active trace 与 recovered full FE vector 使用 ownership-range ascending 的
canonical global order、little-endian complex128；hash 输入包含 namespace、
shape、dtype 和 canonical bytes。

Direct F0 的资源上限沿用已资格化 Task035c p6/h10 口径：
warning 32 GiB、termination 48 GiB、timeout 7200 s、poll 0.25 s、swap=0，
并使用完整 process-group 的 TERM、5 秒 grace、KILL 语义。Task37 iterative
candidate 的 warning 10 GiB / termination 14 GiB 不适用于本 direct case。

F4、F5c、F6、Hybrid、hp、0.7 nm、Task037b 与任何新的
campaign/registry/framework 均不在当前授权范围。

两次 ignored serial smoke（p2/h50、p6/h50）均在 release/KSP 前因 5 层
z 网格上的固定 75 维 Floquet 粗基 singular；既不证实也不否定 F5b，
本阶段不修改粗基。
