# Task032 Phase 6e 真实 QEP h5/M6 研究诊断

## 状态

```text
classification = physical_integration_pass_mode_convergence_pending
official_record = false
source = dirty research worktree
mpi_size = 4
image = myfenics-stage4:task28
h_nm = 5
requested_modes_per_direction = 6
```

该记录说明真实 QEP 到 MUMPS/RTA 的链路和 M4->M6 截断变化通过；它不是 clean formal record，
也不是完整 `physical_augmented_direct_pass`。

后续已在 clean source `5c1f12e610dd8c6040389c44c31584ab7fba66cd` 生成
`records/hybrid_phase6_m6.json`。该正式集成记录通过 Case080 `294/294` checker，
但仍保持 `official_record=false`，不会反向把本页的 dirty-research 漏斗冒充 clean funnel。

## 关键修复证据

- 正负共享一个已编译 `PoyntingFluxEvaluator`，消除第二次 evaluator 的 MPI/JIT 长等待；
- dirty-research 不再在 Linux 容器扫描 Windows CRLF worktree；
- SLEPc 原始 `nconv=8/8`，下游精确交付 `6/6` 并释放超额向量；
- 三个近简并组均用 `near_degenerate_block_inverse`；
- target-cell Nédélec 路由把新增两列映射误差从最高 `1.24e-2` 降到约 `2e-14`。

## M6 数值

```text
matrix_size = 13744 x 13744
matrix_nnz = 1470406
true_relative_residual = 4.63917660324918e-12
interface_E_projection_relative_residual = 6.8808621277907e-14
bottom_FE_modal_traction_relative_residual = 3.20348116580249e-12
top_FE_modal_traction_relative_residual = 4.15965481760633e-12
positive_biorthogonality_error = 1.81609001989064e-11
negative_biorthogonality_error = 6.86946763023221e-11
R = 0.08901677045141917
T = 0.44257711681153356
A_balance = 0.46840611273704724
M4_to_M6_abs_delta_R = 8.33e-14
M4_to_M6_abs_delta_T = 9.82e-13
M4_to_M6_abs_delta_A = 1.07e-12
MUMPS_setup_seconds = 0.34743706800509244
MUMPS_solve_seconds = 0.011195671002496965
runner_total_seconds_max_rank = 14.958937502997287
```

## 与 full-3D h5

```text
hybrid_minus_full3d_R = -4.83248501946532e-6
hybrid_minus_full3d_T = -1.11618455934104e-5
hybrid_minus_full3d_A = 1.59943306128896e-5
```

full-3D h5 只是 fast-development reference，未通过 h5--h3 网格收敛，因此这里不以该差值单独
判定最终物理正确性。

## 尚未完成

- pointwise interface H jump；
- lossy volume absorption reconstruction；
- z=30/60/90 nm selected-plane E/H reconstruction；
- h3 Hybrid 和 h3 full-3D 对比；
- 外部 simultaneous RSS 内存资格。
