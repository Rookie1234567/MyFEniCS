# Outcome Summary

## Task

Task023：PETSc/MPI-safe FE-response PC for DtN auxiliary Schur correction。

## Branch

`codex/20260709-task20-wave-solver-search`

## Physical Model

| 项目 | 值 |
|---|---|
| domain | 50 x 25 x 140 nm |
| grating | 17 x 25 x 120 nm |
| substrate / top air | 10 nm / 10 nm |
| incidence | theta=80 deg, phi=0, s polarization |
| material n | 0.999002304859 + 0.00182649365j |
| boundary | double Floquet x/y + auxiliary DtN port |
| power source | dtn_port_modal_amplitudes + A_volume |

## Key Results

| case | route | status | true residual | RSS peak |
|---|---|---|---:|---:|
| h=5 | PETSc FE-response `ASM+local LU`, selected mode PC | production-like | 9.326e-7 | 1.557 GB |
| h=5 | PETSc FE-response `ASM+local LU`, full 80-aux Schur one apply | production-like | 2.493e-10 | 1.701 GB |
| h=5 | PETSc FieldSplit/Schur + FE LU | production-like | 3.797e-9 | 1.351 GB |
| h=2 | PETSc FieldSplit/Schur + ASM/ILU | failed | 9.896e-1 | 8.948 GB |
| h=2 | selected dominant-mode FE response + ASM/ILU | failed | 1.540e0 | 8.326 GB |
| h=2 | ASM+local LU / LU-MUMPS fallback | resource boundary | not available | timeout |

## h=5 R/T/A Closure

| source | residual | R | T | A_volume | R+T+A_volume |
|---|---:|---:|---:|---:|---:|
| direct reference | 2.764e-11 | 0.089021602936 | 0.442588278657 | 0.468390118406 | 0.999999999999 |
| best PETSc FE-response | 2.493e-10 | 0.089021602936 | 0.442588278658 | 0.468390118407 | 1.000000000001 |
| FieldSplit FE-LU | 3.797e-9 | 0.089021602935 | 0.442588278668 | 0.468390118400 | 1.000000000003 |

结论：h=5 的 reduced/augmented vector 已能回填到 H(curl) Function，并调用 official `dtn_port_modal_amplitudes + A_volume` 后处理。R/T/A 与 direct reference 的差异在约 `1e-12` 量级。

## Mode Mapping

| rank | local aux index | side | order | pol | aux residual fraction |
|---:|---:|---|---|---|---:|
| 1 | 38 | top | (0,0) | s | 0.999956 |
| 2 | 34 | top | (-1,0) | s | 0.008867 |
| 3 | 28 | top | (-2,0) | s | 0.002822 |

dominant slow mode 仍然是 Task021/022 确认的 top `(0,0)` s、local aux index `38`。

## h=2 Diagnosis

| 测试 | 结果 | 判断 |
|---|---:|---|
| assembly, 4 MPI ranks | rows=615188, nnz=65448472, peak RSS=7.37 GB | 装配可承受 |
| FieldSplit ASM/ILU, 40 outer steps | residual=0.9896, peak RSS=8.95 GB | local ILU 太弱 |
| selected response ASM/ILU, 80 inner steps | inner residual=1.1267, one-shot residual=1.540 | FE response 方向错误/太弱 |
| FieldSplit ASM+local LU | >7200 s / no residual row | local LU setup 过慢 |
| selected response ASM+local LU | >3600 s / no residual row | 单 RHS local LU 也过慢 |
| LU/MUMPS fallback | >7200 s after ASM/ILU run | fallback 接近直接法成本 |

这说明 h=2 的失败点不是 mode selector，也不是 MPC ownership。修正 FieldSplit IS 后，MPI ownership 问题已排除；真正瓶颈是低内存 FE-response 质量。ASM/ILU 给不出有效 `A_FE^{-1} C_j`，ASM/LU 和 LU/MUMPS 在当前 14 GB WSL 配额下进入时间/资源边界。

## h=1.5 Projection

未实际运行 h=1.5，因为 h=2 assembly 已 peak 7.37 GB，FieldSplit ASM/ILU 已 peak 8.95 GB。按三维网格近似比例 `(2/1.5)^3 = 2.37` 外推，h=1.5 显式矩阵 assembly 可能超过 17 GB，FieldSplit/Schur setup 可能超过 21 GB。当前 14 GB WSL 配额下不建议直接跑 h=1.5 显式 AIJ。

## Answer

目前最有希望替代 SciPy SPILU 的 PETSc/MPI-safe 方向不是 plain ASM/ILU，而是：

| 优先级 | 方向 | 原因 |
|---:|---|---|
| 1 | real-split same-H1 AMS/HX FE-response service + auxiliary Schur | task013 已证明 FE-only 正信号；task023 证明 Schur/RTA 回填闭环 |
| 2 | PETSc FieldSplit/Schur + stronger FE inner solver | h=5 已闭环；h=2 需要比 ASM/ILU 更强的 FE inverse |
| 3 | MUMPS/BLR selected-response fallback | 可做 reference，但不应包装成低内存 production |
| 4 | matrix-free FE action + inner PC | 只降低显式矩阵压力，仍需要有效 inner PC |

下一步应进入 real-split AMS/HX FE-response service 工程化，而不是继续调 SciPy SPILU 或 plain ASM/ILU。

## Run Commands

```text
. /usr/local/bin/dolfinx-complex-mode; python3 -m src.studies.run_task023_petsc_mpi_fe_response_pc --h-values 5 --baseline-maxiter 5 --outer-maxiter 5 --fieldsplit-maxiter 20 --fe-inner-maxiter 20
. /usr/local/bin/dolfinx-complex-mode; mpiexec -n 4 python3 -m src.studies.run_task023_petsc_mpi_fe_response_pc --stage refinement --h-values 2 --refinement-maxiter 40 --rta-residual-gate 1e-5
. /usr/local/bin/dolfinx-complex-mode; mpiexec -n 4 python3 -m src.studies.run_task023_petsc_mpi_fe_response_pc --stage refinement --h-values 2 --run-selected-response --selected-response-profiles asm_ilu --fe-inner-maxiter 80 --skip-fieldsplit-refinement
```
