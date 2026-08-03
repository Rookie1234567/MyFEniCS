# Case100：static-condensed Full3D iterative Task37 F0

## 当前阶段

Case100 先冻结 Task37 的 current-source direct authority。它只验证
Case096 已经使用过的 p6/h10 Full3D static-condensed 模型在 Task37 执行
分支上的完整身份、物理结果、残差、矩阵规模、向量身份和资源遥测。
本次 Stage 0 只提交 contract；F0 direct 尚未运行。

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

F1--F6、Hybrid、hp、0.7 nm、Task037b 与任何新的 campaign/registry/
framework 均不在 Case100。
