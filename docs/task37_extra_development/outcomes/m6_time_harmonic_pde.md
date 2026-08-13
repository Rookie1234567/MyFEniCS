# M6A 全空间无矩阵 DtN 与后续时谐/PDE边界

## 当前状态

M6A 的作用是验证冻结的 80 模式端口 DtN（Dirichlet-to-Neumann，给定端口场后计算端口通量）在真实 p6/h10 全空间上可执行，并与独立的流式 direct modal-sum 对照一致。它只验证端口 action/恢复的数值和架构合同，不等于时谐 PDE 求解或最终物理结果。

| 路线 | 状态 | 边界 |
| --- | --- | --- |
| M6A matrix-free full-space DtN | `PASS / QUALIFIED` | 仅 action/DtN authority；checker 15/15，通过 MPI1/MPI2 对照 |
| M6B/time-harmonic screen | `not_run_yet` | 未运行 |
| full time-harmonic PDE / RTA / field recovery | `not_run_yet` | 未运行 |
| 最终 PDE `<2,000,000,000 B` process-tree 目标 | `not_run_yet` | 未测量，不能由 M6A peak 代替 |

## 固定模型与数值结果

| 项目 | 实测/合同 |
| --- | --- |
| source | `2a9dabaa13365373864814d7146ee9399395ed51` |
| mesh/space | p6、h=10.0、252 cells、173,802 global rows、9,210 constraints、local nloc=882 |
| port modes | 80；mode manifest SHA `8d7c396b5251365c6865b2fafefd37e1559794fe39f445ef8bccc3b8ff29cac5` |
| physical layout | `fine_space=uncondensed_fullspace` |

MPI1 与 MPI2 的 candidate action、独立 direct action、physical RHS、recovery 和 repeat 五项误差均为 `0.0`，且 finite。checker 的 cross-MPI source/action/RHS/recovery 与 mode-manifest checks 全部为 `true`；cross-MPI recovery relative error 为 `0.0`。

| 阶段 | peak RSS | swap | elapsed | compiler descendants | cleanup |
| --- | ---: | ---: | ---: | --- | --- |
| isolated stage | `527,859,712 B` | `0` | `13.230624606 s` | 有，属于隔离 JIT stage | `true` |
| MPI1 online | `388,956,160 B` | `0` | `21.308124773 s` | `[]` | `true` |
| MPI2 online | `693,411,840 B` | `0` | `14.421220687 s` | `[]` | `true` |

retained+work 为 MPI1 `16,673,350 B`，MPI2 每 rank `8,378,950 B`、global sum `16,757,900 B`，均低于 `150,000,000 B`。在线 cache 的 20 个文件满足 `stage == before == after == final`；online 未产生 compiler descendant。

## 架构边界

candidate 与 direct oracle 都不物化 PETSc C/D、global、augmented 或 Schur/trace matrix；explicit C/D count 均为 0，采用两个流式 direct assembly pass 和每次一个 80-complex modal Allreduce。无 static condensation、trace-slab PC、DtN retained matrix、FE-sized numeric allgather；输出/载荷使用 owner-local dual 语义，source 保持 primal 语义。M6A 仍不是 PDE、RTA 或 official physics qualification。

## 早期负证据

M6A run1 的 online-JIT/cache lifecycle negative 与 run2 的 watchdog JSON serialization negative 都是 execution failures，分别保留在原 raw/check 路径中；不把它们改写为算法 FAIL，也不把它们当作 PASS。run3 是修复后的唯一 positive authority，本 outcome 不覆盖 run1/run2/run3 raw 或外部 checker。

## 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| run3 raw | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3`；raw tree digest `665f3a02a13f73c0a949e817c3b2bc7fc915166c10f61dc844c09a242f7cff52`（82 files） |
| watchdog summary | `.../m6a_watchdog_summary.json`；`2a275b43f756a54e8285d0bc16d57947e6731d1615d91ecc37d2295182ffccd6` |
| stage summary | `.../m6a_stage_summary.json`；`a1f157314a5b3651090e61d9bc58523c15aaf6ace9f77fa1c15e992bb11046bd` |
| MPI1 worker summary | `.../mpi1_worker_summary.json`；`65bcb6cad5bf6cc856867f474fbeb8114f7da4509b58df667a728ba470f31341` |
| MPI2 worker summary | `.../mpi2_worker_summary.json`；`ad92cb53a6256b6a3c5081bccabd9c8d9a0d663a53aad2daca963cb48c3c1646` |
| external checker | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3_check.json`；`d121f19553576e1fcce947325edc35c1ef16ecbf370cab9b7ad1477fe16b0c2a` |
| checker embedded evidence | `9a412106a6428c1555b58945eeda6a5b1294bd0e1e85bc763c6c46a7314f30a4` |
| tracked compact | `benchmarks/cases/101_task37_extra_development/records/m6a_fullspace_matrix_free_dtn.json`；byte-for-byte copy of external checker |

M6B、time-harmonic operator、field/RTA、direct-authority physics comparison 和最终 PDE RSS 仍等待后续阶段；不能把 M6A 的 action peak 当作 PDE peak。
