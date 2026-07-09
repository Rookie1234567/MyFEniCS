# Outcome Summary

## Task

task010：Stage 4 3D Maxwell 物理预条件器与 MUMPS-BLR 压缩直接预条件器原型验证。

## Branch

`codex/20260707-maxwell-physics-blr-preconditioner-prototype`

## 结论先行

本轮找到一个短期可用候选：`FGMRES + MUMPS-BLR`。在 p=2、h=2 nm、8 MPI ranks 下，`eps=1e-5` 和 `eps=1e-4` 都能达到 `rtol=1e-6`，并且 official R/T/A 与 task008 direct LU 对照一致到约 1e-9 量级。`eps=1e-5` 迭代最少，h=2 用 4 次迭代，`true_relative_residual_norm = 2.085e-08`。

但它还没有突破本机 h=1.5：`eps=1e-5` 在 p=2、h=1.5 的 KSP setup 阶段被 signal 9 kill，失败前 `RSS_upper_GB = 13.81`。因此当前本机 production 上限应写为 p=2/h=2，而不是 h=1.5。

shifted/positive Maxwell minimal P 路线已经验证了 `KSP.setOperators(A, P)` 和 P 矩阵装配，但所有 h=5/h=4 初筛均 1000 步未收敛，没有 official R/T/A。它不能作为当前 production solver。

## Changed Files

见 `changed_files.md`。

## Run Commands

完整运行记录见 `run_log.txt`。核心命令均通过 Docker complex-mode 执行：

```bash
. dolfinx-complex-mode && python3 -m src.studies.run_3d_matrix_scale ...
```

## Physical Model

| item | value |
|---|---|
| geometry | 50 x 25 x 140 nm, grating 17 x 25 x 120 nm |
| material | substrate/grating n = 0.999002304859 + 0.00182649365j |
| wavelength | 13.5 nm |
| incidence | theta_from_z=80 deg, phi=0 deg, s polarization |
| boundary | Stage 4 DtN port, auxiliary assembly, auto propagating orders |
| official power | `R_total/T_total` from DtN modal amplitudes, `A_volume_total` from volume absorption |

## Numerical Settings

| item | value |
|---|---|
| FE | Nedelec p=2 |
| MPI | 8 ranks |
| mesh spacing | boundary_fitted |
| BLR KSP | FGMRES, right preconditioning, unpreconditioned norm |
| BLR tolerance | rtol=1e-6, atol=1e-12, max_it=1000, restart=80 |
| BLR options | `mat_mumps_icntl_35=1`, `mat_mumps_cntl_7=epsilon` |
| shifted/positive P | original `A` solve with separate `P`, FE block physics P + auxiliary identity |

## Key Results

| profile | h | status | iterations | true relative residual | R | T | A_volume | closure error | RSS upper GB | wall s |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| iter_fgmres_mumps_blr_eps1e-5 | 1.5 | failed | - | - | - | - | - | - | 13.81 | 1762 |
| iter_fgmres_mumps_blr_eps1e-3 | 2.0 | timeout | - | - | - | - | - | - | 16.27 | 1801 |
| iter_fgmres_mumps_blr_eps1e-4 | 2.0 | completed | 7 | 1.883e-07 | 0.0013429337 | 0.59921323 | 0.39944384 | 1.657e-09 | 18.09 | 1234 |
| iter_fgmres_mumps_blr_eps1e-5 | 2.0 | completed | 4 | 2.085e-08 | 0.0013429328 | 0.59921323 | 0.39944384 | -6.701e-10 | 17.85 | 1358 |
| iter_fgmres_mumps_blr_eps1e-3 | 2.5 | completed | 15 | 4.310e-07 | 0.0027121888 | 0.59282379 | 0.404464 | -1.217e-08 | 14.42 | 83.49 |
| iter_fgmres_mumps_blr_eps1e-5 | 2.5 | completed | 4 | 6.212e-09 | 0.0027121893 | 0.5928238 | 0.40446401 | 3.452e-10 | 14.6 | 164.9 |
| iter_fgmres_mumps_blr_eps1e-3 | 3.0 | completed | 15 | 8.130e-07 | 0.0046130278 | 0.58365337 | 0.41173362 | 1.314e-08 | 10.29 | 64.01 |
| iter_fgmres_mumps_blr_eps1e-5 | 3.0 | completed | 3 | 1.464e-07 | 0.0046130308 | 0.58365336 | 0.41173361 | -3.233e-09 | 10.5 | 73 |
| iter_fgmres_mumps_blr_eps1e-3 | 4.0 | completed | 11 | 3.974e-07 | 0.0035540305 | 0.56191709 | 0.43452886 | -2.271e-08 | 6.354 | 19.99 |
| iter_fgmres_mumps_blr_eps1e-5 | 4.0 | completed | 3 | 1.963e-08 | 0.0035540315 | 0.5619171 | 0.43452887 | -6.852e-10 | 6.387 | 19.96 |
| iter_fgmres_mumps_blr_eps1e-3 | 5.0 | completed | 8 | 2.121e-07 | 0.089021608 | 0.44258828 | 0.46839013 | 1.667e-08 | 4.027 | 26.78 |
| iter_fgmres_mumps_blr_eps1e-5 | 5.0 | completed | 3 | 3.139e-09 | 0.089021603 | 0.44258828 | 0.46839012 | 9.202e-11 | 3.843 | 11.3 |

## Direct LU 对照

| h | profile | abs error R | abs error T | abs error A | BLR RSS GB | direct RSS GB | BLR wall s | direct wall s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2.0 | iter_fgmres_mumps_blr_eps1e-4 | 8.400e-10 | 2.539e-10 | 5.634e-10 | 18.09 | 20.53 | 1234 | 1666 |
| 2.0 | iter_fgmres_mumps_blr_eps1e-5 | 7.053e-12 | 5.042e-10 | 1.588e-10 | 17.85 | 20.53 | 1358 | 1666 |
| 2.5 | iter_fgmres_mumps_blr_eps1e-3 | 5.513e-10 | 8.310e-09 | 3.309e-09 | 14.42 | 14.81 | 83.49 | 327.9 |
| 2.5 | iter_fgmres_mumps_blr_eps1e-5 | 3.029e-12 | 2.315e-10 | 1.167e-10 | 14.6 | 14.81 | 164.9 | 327.9 |
| 3.0 | iter_fgmres_mumps_blr_eps1e-3 | 3.651e-09 | 1.095e-08 | 5.844e-09 | 10.29 | 11.9 | 64.01 | 194.8 |
| 3.0 | iter_fgmres_mumps_blr_eps1e-5 | 5.714e-10 | 1.331e-09 | 1.330e-09 | 10.5 | 11.9 | 73 | 194.8 |
| 4.0 | iter_fgmres_mumps_blr_eps1e-3 | 9.472e-10 | 1.258e-08 | 9.185e-09 | 6.354 | 6.328 | 19.99 | 142.2 |
| 4.0 | iter_fgmres_mumps_blr_eps1e-5 | 1.054e-10 | 5.671e-10 | 2.235e-10 | 6.387 | 6.328 | 19.96 | 142.2 |
| 5.0 | iter_fgmres_mumps_blr_eps1e-3 | 4.991e-09 | 1.732e-09 | 9.945e-09 | 4.027 | 3.817 | 26.78 | 145.9 |
| 5.0 | iter_fgmres_mumps_blr_eps1e-5 | 2.501e-10 | 2.281e-10 | 1.141e-10 | 3.843 | 3.817 | 11.3 | 145.9 |

## Energy Check

所有已收敛 BLR runs 的 `R_total + T_total + A_volume_total` 都在 1 附近，h=2/eps=1e-5 的能量闭合误差为 `-6.701e-10`。未收敛的 shifted/positive runs 不生成 official R/T/A，因此不纳入能量判据。

## Mesh / DoF / Solver Cost

- h=2/eps=1e-5：system rows ``，nnz `-`，RSS upper `17.85 GB`，wall `1358 s`。
- h=2/direct LU：RSS upper `20.53 GB`，wall `1666 s`。
- h=1.5/eps=1e-5：base matrix nnz `1.421e+08`，KSP setup 被 signal 9 kill，尚未进入 official solve。

## Known Issues

1. `MUMPS-BLR compression ratio` 暂未从当前 PETSc/petsc4py summary 稳定取出，本轮以 epsilon、迭代数、RSS 和 direct 对照评估可行性。
2. `RSS_upper_GB` 是 rank max RSS 乘以 ranks 的保守上界，不是严格总 RSS；但它对同一机器、同一 MPI ranks 的横向比较仍有用。
3. shifted/positive minimal P 没有 DtN Schur 近似，也没有 AMS/HX auxiliary-space，因此负结果不能否定完整 HX/AMS 路线。
4. h=1.5 被 kill 时未返回 PETSc/MUMPS error code，说明更像系统/容器内存边界或 factor workspace 峰值问题。

## Next Questions for Review

1. 是否接受 `iter_fgmres_mumps_blr_eps1e-5` 作为当前第一 production candidate，并在工作站优先跑 h=1.5？
2. 是否需要下一轮专门实现 MUMPS-BLR compression ratio 采集？
3. shifted/positive minimal P 是否作为基础设施保留，但不继续投入调参，转向 HX/AMS 完整实现？
