# Workstation FGMRES runtime：从 frozen config 到完整残差和 RTA

## 1. 文件与入口

| 文件 | 责任 |
|---|---|
| `src/common/config_3d.py` | `target_stage4_config`，唯一 target 物理配置来源 |
| `src/solvers/stage4_runtime.py` | 只装配 target augmented system |
| `benchmarks/run_workstation_iterative.py` | MPI4 显式 opt-in runner |
| `benchmarks/configs/workstation_p2.json` | 冻结 PC/KSP/物理模型合同 |

## 2. 关键签名

```text
config_3d::target_stage4_config(degree,h_nm) -> SimulationConfig3D
stage4_runtime::assemble_target_stage4_system(...) -> RuntimeStage4System
run_workstation_iterative::_complete_physical_slabs(...) -> list[np.ndarray]
run_workstation_iterative::_fixed_floquet_hat_basis(...) -> coarse vectors
run_workstation_iterative::_official_rta(...) -> official RTA dict
run_workstation_iterative::run(args) -> record dict
```

## 3. 调用者与被调用者

用户通过 Case031 `run.sh`、CLI 或 PyCharm External Tool 调用 module。runner 调用 Stage4 assembly、condensation、physical slab PC、PETSc KSP 和 3D postprocess；普通 `src/main.py` 不导入或静默启动它。

## 4. Frozen physical model

`target_stage4_config` 返回 50 x 25 x 140 nm domain、17 x 25 x 120 nm Si block、13.5 nm、theta=80°、phi=0°、s polarization、p=2、auxiliary DtN auto orders。workstation assembly 设置 `matrix_diagnostics_assemble_only=True`，表示普通 direct case flow 不先求解；runtime 自己接管 A/b。

## 5. h5 对象尺寸

| 对象 | 尺寸/数量 |
|---|---:|
| FE unknowns `n_fe` | 44,698 |
| auxiliary unknowns `n_aux` | 80 |
| augmented rows | 44,778 |
| condensed rows | 44,698 |
| coarse basis | 75 |
| physical slabs | 16 |
| MPI owners | 4，每 rank 4 slabs |
| outer iterations | 1,201 |

## 6. Runtime pipeline

```text
load JSON and CLI
-> _qualification_deviations
-> write parameters/progress
-> assemble_target_stage4_system
-> extract F/C/D/H and exact condensed RHS/operator
-> build shifted-F and 16 complete slabs
-> build/compress 75D fixed coarse basis
-> attach smoother-first SparseGalerkinTwoLevelPc
-> right FGMRES solve u
-> recover auxiliary a
-> compute three residuals
-> official RTA and RSS
-> write lightweight record
-> destroy PETSc objects
```

## 7. Outer 与 inner KSP 角色

outer KSP 是 flexible GMRES，因为 Python PC 中含 fixed inner GMRES/slab solves。right preconditioning 意味着 KSP residual 与原 condensed operator相关，但最终仍显式重算 true residual。inner sm2 只有固定两步，不作为独立收敛求解器。

外层方程与 right-preconditioned 形式为：

```math
A_c u=b_c,\qquad A_c M^{-1}y=b_c,\qquad u=M^{-1}y,
```

其中 `A_c=F-C H^{-1}D` 是 exact condensed operator，`M^{-1}` 是 smoother-first physical-slab two-level PC。FGMRES 允许每次 Python PC apply 的内部过程；资格化配置仍固定 sm2 和 coarse 定义，不能因此把任意变化都视为同一算子。

## 8. Monitor

monitor 每 50 步调用 `buildSolution`，用原 condensed operator 计算真残差，并写 elapsed/current/peak RSS。它有额外成本，但可以发现 PETSc reported norm 与真实 action 漂移。

## 9. 三种残差位置

| 字段 | 在哪里计算 | 对象 |
|---|---|---|
| `reported_relative_residual` | PETSc KSP | outer condensed solve |
| `condensed_true_residual` | `_linear_residual` | `A_c u-b_c` |
| `full_augmented_true_residual` | `_full_augmented_residual` | 原 `[F C;D H][u;a]-b` |

只有三者都小于 `1e-6`，才进入 official RTA。

## 10. Auxiliary 回代与 RTA

`recover_petsc_auxiliary` 生成 `a`，`_combined_augmented_vector` 用于 full residual。`_official_rta` 把 FE vector 恢复为 DOLFINx Function，并用 auxiliary modal amplitudes + volume absorption 生成 R/T/A；probe 不替代它。

## 11. Metadata 与 artifact

`_runtime_metadata` 记录 source commit/branch/dirty、真实命令、timestamp、image/digest 和 host。record 另存 resolved config、physical model、qualification deviations、DoF、PC、residual、RTA、time/RSS 与 artifact root。

Case031 脚本默认把候选 record 写到 `benchmarks/artifacts/cases/031/candidate_records`，防止参数扫描覆盖 canonical JSON。

## 12. PyCharm 调用

正式 PyCharm 流程是 External Tool：Docker + `mpiexec -n 4` + `-m benchmarks.run_workstation_iterative`。普通 Python Run 的 size=1 不具资格；完整配置见 [`../../quick_start/40_3d_workstation_iterative.md`](../../quick_start/40_3d_workstation_iterative.md)。

## 13. PETSc 生命周期

KSP/PC 持有 operator 和 context 引用；smoother 持有 local Mat/KSP/scatter；blocks 持有 submatrix。`run` 的 finally/末尾按依赖逆序 destroy，避免大矩阵在 RTA 后仍驻留或重复释放。

## 14. 测试、benchmark 与限制

- `test_22_condensed_dtn`：exact algebra。
- `test_23_physical_slab_two_level`：PC/MPI 生命周期。
- `test_25_benchmark_contract`：config/records/checker。
- Case031：h5/h3/h2 canonical evidence。

限制：只资格化固定 target、MPI4 和当前 PC 参数；h=1.5、角度/材料扫描、warm start、true multilevel H(curl) 未关闭。理论见 [`../../theory/iterative_solver_and_preconditioner.md`](../../theory/iterative_solver_and_preconditioner.md)。

## 15. Task030 explicit flags and record fields

runner 新增 `--post-smooth`、`--subdomain-local-shift` 和 `--factor-only-storage`，默认均为 false；与 `--ilu-levels 0 --restart 90` 共同构成 Case060 的 `compact_physical_slab_low_memory_experimental_opt_in` 候选。它仍是 Task27-derived physical-slab + 75D wave-coarse solver，不是 p/h multigrid solver。resolved config 和 record 同步写 `post_smooth`、`subdomain_local_shift`、`factor_only_storage`，smoother diagnostics 写 `subdomain_local_diagonal_shift`、`global_stored_factor_nnz` 与 factor-only identity。

这些 flags 触发 `qualification_deviations`，所以 Task027/Case031 ordinary canonical 不会被静默覆盖。失败的 Task030 Woodbury 和 x-harmonic coarse 没有保留在正式 workstation runner 参数表；它们只在 research runner、模块测试和负结果文档中出现。

Case060 best records 写入实际重型运行的 commit、tracked-source qualification、命令、时间、镜像 digest、host id、artifact root/SHA-256、80-mode identity 与 75D coarse identity。Review V2 后，h5/h3 来自 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 的 clean rerun：runner 接收 host 已验证的 exact full SHA，并要求它与容器 HEAD 完全一致，否则 fail closed；record 同时写 `git_dirty=false`、`tracked_source_dirty=false` 和 `host_git_clean_attestation`。h2 不重跑，仍保留原 dirty provenance，并以 `reviewed_historical_dirty_worktree_reference` 与 clean h5/h3 明确区分。factor-only 的 factor matrix lifetime 仅对 PETSc 3.24.0 complex build 验证；跨版本必须回归。

Case060 入口：[`../../../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md`](../../../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md)。

## 16. Task031 external sampler 与 matrix-free/compact pipeline

Task031 wrapper `benchmarks.run_task031_memory_forensics` 是 runner 的父进程。它先核对 host clean full SHA，再启动 `mpiexec -n 4` worker；每 0.25 s 读取 live rank RSS、process tree、cgroup、swap 与 `*_memory_stages.jsonl`，最后把 solver numeric pass 和 full-run memory summary合并。h2 默认锁定，并可在 9.5/11 GiB warning/termination 时受控结束。

新增 pipeline 为：

```text
assemble Stage4 form/F/C/D/H
-> certify public MPC form action against assembled F
-> build exact condensed shell with external fine action
-> build 75D coarse and 16 overlap0.125 slab factors
-> release assembled F when all require_f users finish
-> build FGMRES90 and write object ledger
-> solve with matrix-free fine action
-> recompute condensed/full true residual
-> destroy solver stack before official RTA
-> external sampler reports full-run simultaneous peak
```

`--matrix-free-fine`、`--compact-lifecycle`、`--ksp-type`、`--smoother-ksp-type`、`--certify-pc` 与 selective slab flags 默认都不改变 ordinary profile。最终 adaptive PC 非线性，所以 Case070 正式 run 用 FGMRES 并记录 certificate negative disposition，不用 `--certify-pc` 把已知非线性误判成运行失败。

`object_ledger_at_solve` 只做可解释 payload 模型；外部 RSS/cgroup 才是内存 authority。h2 ledger payload 3.383 GiB、legacy internal peak 8.176 GiB、external worker peak 7.898 GiB，三个数不能混写。matrix-free h2 调用 form action 13,960 次，解释了 solve 11982.581 s 的主要成本。

Case070 入口：[`../../../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md`](../../../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md)。
