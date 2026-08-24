# Review V10 最终 LOR foundation addendum

本 addendum 只汇总两条已经完成的正式证据：先前唯一一次 foundation-E formal 的通过结果，以及随后唯一一次 global transfer/rank/spectral audit 的受控负结果。它不重新运行求解器，也不把未生成的 worker record 或 checker 结果补写成通过。

## 1. 已冻结的结论

| 路径 | 结果 | 含义 |
|---|---|---|
| V10 Q0 Reference E | 永久 negative：`rho=4.2034233790900783e-4 > 1e-8` | 旧的 500 步 Q0 结果保留，未覆盖、未重分类 |
| foundation-E | PASS | p3/h50、MPI1、random、exact LOR edge inverse 在 3020 步达到 `9.260562270838936e-9` |
| global transfer/rank/spectral audit | `CONTROLLED_NEGATIVE_GHEP_NONCONVERGENCE` | smallest 端点在固定 SLEPc 500 次内 `reason=-1, converged=0`，全局谱等价性尚未建立 |

“真残差”是用完整算子重新计算 `b-Ax` 得到的误差；它不是 PETSc 内部报告的近似残差。foundation 的 `9.26e-9` 因而满足该 formal Gate，而 global audit 没有得到可审阅的特征值、秩或条件数。

## 2. foundation-E formal（唯一 numerical foundation run）

foundation-E 使用 exact LOR edge inverse 作为 Reference E，p3/h50、MPI1、random，right GMRES/restart20，最大 10000 步，每 500 步保存 solution-only checkpoint。本轮没有运行 Reference N。

| iteration | explicit true residual |
|---:|---:|
| 500 | `4.2034233790900783e-4` |
| 1000 | `4.401332743770308e-5` |
| 1500 | `3.282602742213605e-6` |
| 2000 | `5.321845410207366e-7` |
| 2500 | `7.438106631138348e-8` |
| 3000 | `1.005098887039319e-8` |
| 3020 | `9.260562270838936e-9`，PASS |

关键事实：`matvec=3170`、`PC apply=3171`、`KSP destroy=151`、outer wall `613.287 s`、process-tree peak `253284352 B`、process-tree swap `0`。finite、repeat、input unchanged 和 high-primal constraint 均通过；single-apply direct residual 为 `9.13154427545479e-16`。

此前 foundation 前的两次启动问题分别是 watchdog argparse 启动缺陷和 shell 路径笔误。它们没有创建或进入 numerical worker；正式 numerical foundation 因而恰好只运行了一次。两次失败事实没有覆盖任何旧证据，也不改变 foundation 的 PASS。

## 3. global transfer/rank/spectral audit

这个审计检查能否把低阶边空间的矩阵与高阶正定算子的“拉回”结果放到同一个独立自由度坐标中。full raw rows 为 3018，其中 480 个是 slave identity rows，真正独立的 owner rows 为 2538。目标比较是 sparse `B_L` 与 matrix-free pullback `L^H B_H L`；只有 owner 维数、双射、Hermitian/work identity 和两端谱端点都成立，才可考虑直接 LOR-edge geometric multigrid。

本次唯一 audit 的固定 smallest GHEP 端点在 `max_it=500` 内以 `reason=-1, converged=0` 结束。没有生成 worker record，因此没有 checker；`lambda_min`、`lambda_max`、numerical rank 和 condition 均为 `spectral_not_established`。这是真正的数值资格未闭合，不是 RSS、swap 或进程生命周期失败：watchdog 观察到 process-tree peak `176119808 B < 500000000 B`、process-tree swap `0`、all status readable，且无 orphan。

这次停止不能被解释为“所有 LOR/HX foundation 都失败”：foundation-E 已 PASS；同样，也不能把 global audit 未完成改写成谱等价性通过。当前 geometric-MG consideration 仍为 `NOT_QUALIFIED/locked`，需等待审阅，不自行提高 max_it、扫描参数或改变谱求解设置。

## 4. 证据索引

| 证据 | 相对路径 | SHA256 |
|---|---|---|
| global watchdog raw | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v1/4bd610954da0d6aa01fbc6440f67f6604381e6a2/p3-mpi1/watchdog.raw.jsonl` | `f06ccf3a825bd2ecc4b2446a069209b2222227d676f551743e42099c05963450` |
| global worker log | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v1/4bd610954da0d6aa01fbc6440f67f6604381e6a2/p3-mpi1/worker.log` | `2a54020d2d91a0053c14209b91155972f83c6352369c29f5799866a2357f7dd0` |
| global marker | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v1/4bd610954da0d6aa01fbc6440f67f6604381e6a2/p3-mpi1/worker_raw/stage-rank0.jsonl` | `d519fd38a03adb9320c21f178d8597ff49b58024705be8c29ec3c82298dff100` |
| global watchdog compact | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_global_lor_spectral_audit_v1_watchdog.json` | `55e2ae1299eace079aaf943422acd912052b869d5eaaaa147a88c9ad3142b9c3` |
| foundation worker record | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_edge_foundation_10000_v1.json` | `ab98d01a99d22e69fd2ed9132bf64d8703e30ff4589a3120e17ed31a6d7beac0` |
| foundation checker v2 | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_edge_foundation_10000_v1_checker_v2.json` | `b42675cc9b3d6729f18c1ae744742fefbfe312ded30b5db2ada098664db98525` |

旧 Q0 record/checker 的 SHA 分别为 `2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82` 与 `be70e0e559fea32023dfde58e4ede11009574c18f51e4b914d9b5034832a35ea`，均保持不变。没有运行 Reference N、p6、PDE 或 official physics。
