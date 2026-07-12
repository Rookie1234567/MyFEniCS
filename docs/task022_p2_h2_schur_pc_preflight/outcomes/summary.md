# Outcome Summary

## 任务

Task022 用目标物理模型巩固 task021 的 Schur/FE-response 预条件器突破，重点检查 h=5 production-like residual 是否可重复、h=2 是否能进入工程 preflight、每个 case 的总 RSS 是否清楚、matrix-free FE action 是否能作为 h=2/h<2 的内存支撑。

## 分支

`codex/20260709-task20-wave-solver-search`

## 模型确认

继续使用 task008 目标模型：`50 x 25 x 140 nm` domain、`50 x 25 nm` period、`17 x 25 x 120 nm` grating、`theta_from_z=80 deg`、`phi=0`、s polarization、复折射率 `0.999002304859 + 0.00182649365j`、double Floquet x/y + auxiliary DtN port。没有回到 default100。

## RSS 总表

| case | stage | status | current total RSS GB | peak total RSS GB | 说明 |
|---|---|---|---:|---:|---|
| matrix-free p2 h10 FE action | completed | completed | 0.199 | 0.207 | FE weak-form action 对照 |
| h5 resource/CSR | completed | completed | 0.472 | 0.676 | p=2 h=5 装配与 CSR |
| h5 SPILU m=1 | converged | production-like | 2.194 | 2.281 | fill nnz 44835659 |
| h5 SPILU block Schur | converged | production-like | 2.264 | 2.354 | fill nnz 44835659 |
| h5 exact Schur upper bound | converged | production-like | 4.104 | 4.194 | SPLU fill nnz 47793239 |
| h2 resource/CSR | completed | completed | 3.285 | 6.277 | rows 615188, nnz 65448472 |
| h2 baseline history | not converged | residual 0.163120 | 3.609-4.502 | 6.277 | 20 history points |
| h2 SPILU fill=12 | blocked | memory guard | 4.502 | 6.277 | estimated total RSS 27.79 GB |
| h2 SPILU fill=1.05 | timed out | factorization timeout | 4.502 last recorded | 6.277 last recorded | estimated total RSS 6.54 GB，但 7200 s 无 factor 返回 |

说明：timed-out case 的精确 factorization 期间峰值 RSS 没有被 Python 收尾记录到，因为外部 Docker 命令在 7200 s 被终止；CSV 中保留的是 factorization 前最后一次记录的 total RSS 与估算值。

## h=5 Reproducibility

| profile | true residual | gate | history points | peak total RSS GB |
|---|---:|---|---:|---:|
| baseline GCROT + Jacobi | 2.109624e-1 | fail | 40 | 0.676 |
| SPILU coupled PC m=1 | 9.865457e-7 | production-like | 6 | 2.281 |
| SPILU block Schur PC | 2.430285e-7 | production-like | 2 | 2.354 |
| exact FE-block Schur PC | 8.183739e-12 | production-like | 2 | 4.194 |
| exact FE-block Schur one apply | 8.155352e-12 | production-like | 0 | 4.194 |

结论：task021 的 h=5 突破可重复。虽然本轮 baseline 只跑 40 个 history points，所以 baseline residual 是 `0.210962` 而不是 task021 80 points 的 `0.202577`，但三个成功 profile 的 production-like residual 完全复现。

## h=2 Resource Preflight

| p | h_nm | rows | nnz | n_fe | n_aux | estimated AIJ MB | CSR delta RSS GB | assembly s | CSR s | peak total RSS GB |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2.0 | 615188 | 65448472 | 615108 | 80 | 1250.68 | 1.219 | 297.81 | 2.36 | 6.277 |

h=2 matrix/CSR 本身可以在当前机器上完成；真正卡住的是 FE block SPILU factorization。

## h=2 Mode Mapping

| rank | local aux index | global row | side | order | polarization | aux residual abs | aux norm fraction | total fraction |
|---:|---:|---:|---|---|---|---:|---:|---:|
| 1 | 38 | 615146 | top | (0, 0) | s | 1.781991e-1 | 0.999792 | 0.140165 |
| 2 | 34 | 615142 | top | (-1, 0) | s | 3.088361e-3 | 0.017327 | 0.002429 |
| 3 | 28 | 615136 | top | (-2, 0) | s | 1.681462e-3 | 0.009434 | 0.001323 |

结论：h=2 下主导 auxiliary mode 仍然是 top `(0,0)` s，local aux index `38`。因此 task021 的物理 selector 具有网格鲁棒性。

## h=2 Candidate Results

| candidate | FE response | status | residual | gate | memory / time conclusion |
|---|---|---|---:|---|---|
| A coupled m=1 | SPILU drop=1e-3 fill=12 | blocked |  | blocked | estimated total RSS 27.79 GB，超过 12 GB guard |
| B block Schur | SPILU drop=1e-3 fill=12 | blocked |  | blocked | 同上 |
| A coupled m=1 | SPILU drop=1e-1 fill=1.05 | timed out |  | timeout | 7200 s 未完成 FE factorization |
| B block Schur | SPILU drop=1e-1 fill=1.05 | timed out |  | timeout | 没有进入 Schur setup |

结论：h=2 的失败不属于 mode selector，也不是 matrix/CSR 装配失败；失败集中在 serial SciPy SPILU FE factorization。task021 的数学方向仍成立，但 task022 证明它不能以当前 serial SciPy SPILU 形式直接工程化到 h=2。

## Matrix-Free Support

| case | relative action error | status | peak total RSS GB | 结论 |
|---|---:|---|---:|---|
| target box FE action p=2 h=10 | 6.034580e-16 | completed | 0.207 | FE weak-form matrix-free action 与 assembled matvec 一致 |

matrix-free 的定位保持不变：它能减少显式 FE matrix/matvec 存储压力，为 PETSc MatShell 和内层 FE solve 提供基础；但它不能自动替代 `A_FE^{-1}`，所以不能直接把 exact Schur 或 SPILU factorization 变便宜。

## Official R/T/A

本轮没有输出 h=5 iterative official R/T/A。原因是当前 research runner 在 SciPy reduced vector 上验证 linear residual，但还没有把 converged reduced solution 回填到现有 Stage4 后处理管线，缺少 field reconstruction / `Function` update / official `dtn_port_modal_amplitudes + A_volume` 接口。

## Gate Decision

| 问题 | 结论 |
|---|---|
| h=5 是否稳定复现 production-like？ | 是 |
| h=2 是否达到 minimum / strong / production-like？ | 否，未进入 outer solve；卡在 FE SPILU factorization |
| Candidate A/B 谁更适合生产化？ | A 的物理 selector 更轻；B 的结构更强。但二者都不能用 serial SciPy SPILU 直接生产化到 h=2 |
| h=2 失败原因 | FE response / factorization 工程实现，不是 mode selector |
| 是否允许 h=1.5 preflight？ | 不允许 |
| 是否可以开始 PETSc/MPI implementation task？ | 可以，而且应当开始 |
| matrix-free 是否进入主线？ | 应作为 PETSc/MPI PC 的基础设施进入主线，不是独立求解器 |

## 最终目标句回答

Task021 的 DtN auxiliary FE-response / Schur 预条件器可以稳定复现目标模型 p=2 h=5 production-like residual，并且 h=2 mode selector 保持物理一致；但当前 serial SciPy SPILU 实现无法鲁棒推进到 p=2 h=2 outer solve。matrix-free FE action 已验证为正确的内存支撑层，下一步应转向 PETSc/MPI-safe PCShell/MatShell、分布式 FE response 或 PETSc native ASM/ILU/AMS-HX/BLR 混合实现。
