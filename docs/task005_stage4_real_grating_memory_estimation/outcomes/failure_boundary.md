# 失败边界记录

## assemble-only

- 最后完成 h：2.0 nm。
- 第一个失败或 kill 的 h：本轮没有实测失败。
- 未继续运行 h=1.5/1.0/0.5 的原因：h=2.0 已耗时约 2984 s，估算 AIJ 矩阵 11.74 GB，保守 RSS 上界 39.38 GB。继续更细网格对当前 14 GB WSL 风险过高。
- 失败阶段：无。

## default MUMPS direct

- 最后完成 h：5.0 nm。
- 第一个失败或 kill 的 h：4.0 nm。
- 失败阶段：`stage4_dtn_augmented_ksp_setup`。
- 最后 progress：`stage4_dtn_augmented_ksp_setup` / `begin`。
- swap 使用：h=5 完成时 `swap_delta_GB=0.0591`；h=4 被 signal 9 kill，没有完整 `run_summary.json`。

最后 stdout 摘要：

```text
Stage-4 DtN prepared 450/708 auxiliary modes in 68.019 seconds; unique surface orders = 225
Stage-4 DtN prepared 500/708 auxiliary modes in 68.680 seconds; unique surface orders = 250
Stage-4 DtN prepared 550/708 auxiliary modes in 69.183 seconds; unique surface orders = 275
Stage-4 DtN prepared 600/708 auxiliary modes in 69.713 seconds; unique surface orders = 300
Stage-4 DtN prepared 650/708 auxiliary modes in 70.220 seconds; unique surface orders = 325
Stage-4 DtN prepared 700/708 auxiliary modes in 70.743 seconds; unique surface orders = 350
Stage-4 DtN modal cache summary: unique surface orders = 354, x/y component vector assemblies = 708, polarization cache hits = 354
Stage-4 DtN base matrix nnz = 73882316.0
Stage-4 DtN auxiliary coupling nnz estimate = 7325700
BAD TERMINATION OF ONE OF YOUR APPLICATION PROCESSES
EXIT CODE: 9
YOUR APPLICATION TERMINATED WITH THE EXIT STRING: Killed (signal 9)
```

## MUMPS OOC

- 默认 `mumps_ooc` 最后完成 h：5.0 nm。
- 默认 `mumps_ooc` 第一个失败 h：4.0 nm。
- 失败阶段：`stage4_dtn_augmented_ksp_setup`。
- PETSc/MUMPS：`petsc_error_code=76`，`mumps_infog_1=-90`。
- h=5 成功时 OOC disk：10.07 GB。
- h=4 默认 OOC 未留下有效 OOC 文件。
- h=4 调参 OOC `mat_mumps_icntl_14=200` 运行 90 分钟超时，保留 OOC 文件约 30.09 GB，最后停在 `stage4_dtn_augmented_ksp_setup`。

默认 OOC h=4 stdout 摘要：

```text
WARNING: direct LU failed at stage4_dtn_augmented_ksp_setup: PETSc direct LU failed during Stage-4 augmented DtN KSPSetUp/LU factorization.
PETSc error diagnostics = {'petsc_error_code': 76, 'mumps_infog_1': -90, 'mumps_info_2': 4}
MUMPS error in numerical factorization: INFOG(1)=-90, INFO(2)=4
case status = failed_direct_lu_exception
```
