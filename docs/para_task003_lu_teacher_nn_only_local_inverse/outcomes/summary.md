# PARA-Task003 阶段结果总结

## 1. 最终状态

| 项目 | 结果 |
|---|---|
| classification | `exact_lu_oracle_global_signal_insufficient` |
| teacher resource/accuracy | pass / pass |
| single-slab exact-LU oracle | numeric pass；global signal fail |
| conditional three-slab oracle | numeric pass；global signal fail |
| P3-P7 | `not_run_by_gate` |
| h3/h2 | `not_run_by_gate` |
| ordinary default | unchanged |
| production claim | prohibited |

Task003 先问“理想 exact local inverse 是否有足够全局价值”，再决定是否训练。结果是 slab-9 exact LU 没有降低 outer iterations；slab 0/9/10 同时 exact LU 也只降低 2.33%，低于 5% Gate。因此继续训练近似这些 LU 的 learned/NN-only models 缺少全局因果上限，任务按规定在 P2 停止。

## 2. 目标与边界

模型路线若被解锁，只允许 raw residual `r_s -> A_s^{-1}r_s`，不得使用 ILU output/residual/teacher。全局 exact condensed operator、right FGMRES90、75D coarse、16 slabs、true residual 和 official R/T/A 均冻结。第一阶段只研究 slab 9；slab 0/10 只用于 conditional oracle。

## 3. 环境与 P0 baseline

| 环境 | 值 |
|---|---|
| WSL | Ubuntu 24.04 |
| FE stack | Python 3.12.3；DOLFINx 0.10.0.post2；PETSc 3.19.6 complex；MPC 0.10.1 |
| sparse/ML | SciPy 1.11.4；PyTorch 2.7.1+cu118（本 Task 未训练） |
| hardware | 48 visible CPU cores；2× Quadro RTX 8000 |
| formal run | MPI4；OMP/BLAS threads=1；h5 only |

| P0 | iterations | solve / total | full residual | peak |
|---|---:|---:|---:|---:|
| current ILU baseline | 860 | 104.725 / 197.205 s | `9.930033e-7` | 1.595139 GiB |

## 4. Raw capture 独立性

| capture | role | samples | run iterations | full residual | ILU data saved? |
|---|---|---:|---:|---:|---|
| A | train | 512 | 852 | `9.980248e-7` | no |
| B | validation | 128 | 861 | `9.992481e-7` | no |
| C | holdout | 64 | 849 | `9.988413e-7` | no |

三次独立 run 的 slab-9 exact fingerprint 一致。每个 raw sample 只有 `rhs` 和 `apply_index`；capture wall time 只用于数据生成，不进入 baseline/candidate 性能比较。

## 5. P1 sparse-LU teacher

| 指标 | 实测 | Gate | 结果 |
|---|---:|---:|---|
| factorization | 2.576 s | resource feasible | pass |
| factor fill | 4,099,255 nnz / 7.783× | 无 swap/OOM | pass |
| factor storage estimate | 82.07 MB | 当前机器安全 | pass |
| teacher solves | 704 RHS；13.263 ms mean | one factor reused | pass |
| rho median | `5.940e-15` | `<=1e-11` | pass |
| rho p95 | `7.503e-15` | `<=1e-10` | pass |
| rho max | `9.585e-15` | `<=1e-9` | pass |
| swap in/out | 0 / 0 pages | zero | pass |
| factor destroy | confirmed | required | pass |

P1 证明 LU teacher 数据在当前机器上可行且准确，但 teacher 可行本身不解锁训练；必须先看 P2 global oracle。

## 6. P2 exact-LU oracle

| run | exact slabs | iterations | reduction vs 860 | solve | full residual | peak | Gate |
|---|---|---:|---:|---:|---:|---:|---|
| baseline | none | 860 | reference | 104.725 s | `9.930033e-7` | 1.595139 GiB | pass |
| single oracle | 9 | 862 | -0.23%（worse） | 180.402 s | `9.890735e-7` | 1.778637 GiB | fail `<2%` |
| conditional oracle | 0,9,10 | 840 | +2.33% | 206.001 s | `9.974997e-7` | 2.002991 GiB | fail `<5%` |

Oracle wall time 只反映 SciPy LU upper-bound implementation，不用于判断未来 NN inference。关键量是 iterations：单 slab 理想逆没有正信号，三个代表 slab 的理想逆也只减少 20 steps。

## 7. 数值可信性

| run | R | T | A_volume | closure |
|---|---:|---:|---:|---:|
| P0 baseline | 0.0890216033 | 0.4425882730 | 0.4683901227 | `-9.689e-10` |
| slab9 oracle | 0.0890216041 | 0.4425882732 | 0.4683901183 | `-4.370e-9` |
| three-slab oracle | 0.0890216046 | 0.4425882733 | 0.4683901182 | `-3.890e-9` |

reported、condensed true 与 full augmented true residual 全部一致并低于 `1e-6`。Oracle 不替代 final residual/RTA 验证。

## 8. 根因与研究含义

Task001/002 已证明 local residual 可以改善；Task003 进一步证明，即使 selected slabs 使用 exact inverse，当前 16-slab two-step + 75D coarse 架构的 outer spectrum 也只发生小变化。瓶颈不是模型没学好，而是少量 selected slabs 的理论全局杠杆不足。

这不证明所有 NN local PC 都无效。它只排除了当前冻结架构下“先训练 slab9，再扩展到 0/10 的少量 slab-specific replacement”路线。全 16-slab exact oracle、不同 coarse/smoother 或跨参数 operator learning 不属于本任务，也不能由本结果直接否定。

## 9. 停机决策

| 阶段 | 状态 | 原因 |
|---|---|---|
| P3 learned linear inverse | not run | three-slab ideal oracle `<5%` |
| nonlinear NN-only | not run | 没有必要逼近无全局信号的 oracle |
| P4 shadow | not run | 无正式模型 |
| P5 active fallback | not run | P4 未进入 |
| P6 factor removal | not run | active Gate 未进入 |
| P7 slab models | not run | P6 未进入 |
| 16 models / shared model | prohibited | Task003 明确非目标 |
| h3/h2 | not run | h5 Gate failed |

## 10. 性能与内存限定

Oracle 仍保留原 ILU factor并额外构造 LU，故 peak 增加 11.50%/25.57%；这不是 factor-removal memory test。没有模型 checkpoint、online candidate 或 training amortization，因为训练未被 Gate 解锁。成本摊销只能报告 teacher 数据生成：2.576 s factor + 9.260 s triangular solves，不得虚构 NN solve 成本。

## 11. Provenance 与限制

重型 evidence 位于 Git-ignored `benchmarks/artifacts/cases/092/`。所有 formal records 写入 `commit_sha=7e52ebac416463e1e90bd93050ea148a155a025e` 和正确分支；WSL Git 因跨 Windows worktree/行尾及后续未提交实现记录 `git_dirty=true`、`tracked_source_dirty=true`。P0 启动前 Windows Git status 为 clean；oracle 则确实运行于 Task003 实现尚未提交的工作树。因此这些记录足以支持 research negative Gate，但不是 clean-final-HEAD canonical performance evidence。

本 Task 结论覆盖一个 physical RHS、h5、当前 MPI4 partition、当前 PETSc complex ABI 和 selected slabs 0/9/10。三-slab root record 没有汇集 non-root slab10 的 local timing；global iteration/residual/RTA Gate 完整，局部 timing 缺口已在 runtime breakdown 明示。

## 12. 最终决定

保留 raw-only capture、LU teacher dataset schema、one-factor/many-RHS lifecycle、exact-LU oracle port 和测试。停止当前少量 selected-slab NN-only 路线，不进入 P3-P7，不改变 ordinary default，不做任何远程/分支管理动作。

## 13. 验证

| 检查 | 结果 |
|---|---|
| teacher/capture/Case targeted tests | 17 passed |
| exact-LU owner backend MPI2 | rank 0/1 均 pass |
| complete pytest suite | 185 passed，11 skipped |
| Ruff | pass |
| compileall | pass |
| `git diff --check` | pass |
| heavy artifact ignore audit | pass；全部命中 `benchmarks/artifacts/` 规则 |

## 14. 证据入口

- Task：`../task.md`
- Task002 Review：`../../para_task002_batched_neural_smoother_acceleration/review_report_v1.md`
- Case092：`../../../benchmarks/cases/092_lu_teacher_nn_only_local_inverse/README.md`
- teacher resources：`teacher_resource_report.md`
- experiment matrix：`experiment_matrix.csv`
- heavy artifacts：`../../../benchmarks/artifacts/cases/092/`（ignored）
