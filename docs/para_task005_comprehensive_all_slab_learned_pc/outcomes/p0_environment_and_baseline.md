# P0 环境与初始基线

## Provenance

| 项目 | 值 |
|---|---|
| branch | `ChatGPT/20260715-para-task-neural-local-pc` |
| clean source | `f4c0600f352dd940b48e7bdd9b9494d5ebe9e4b0` |
| WSL | Ubuntu-24.04, Linux 6.18.33.2-microsoft-standard-WSL2 |
| complex Python | 3.12.3 |
| DOLFINx | 0.10.0.post2 |
| PETSc | 3.19.6, complex128 |
| NumPy / SciPy | 1.26.4 / 1.11.4 |
| ML Python | 3.12.13 |
| PyTorch / CUDA | 2.7.1+cu118 / 11.8 |
| GPU | 2 x Quadro RTX 8000; training fixed to GPU 0 |
| threads | MPI4; OMP/BLAS/MKL/NumExpr = 1 |

任务书中的 `notes/reference/physical_slab_two_level_pc.md` 在当前分支实际为
`notes/reference/code_walkthrough/32_physical_slab_two_level_pc.md`，已按要求读取。

## Clean h5/MPI4 baseline

| 指标 | 结果 |
|---|---:|
| KSP reason | 2 |
| iterations | 852 |
| solve | 97.252974 s |
| condensed operator applies | 2,584 |
| one-level applies | 5,112 |
| reported residual | 9.99509346e-7 |
| condensed true residual | 9.99509348e-7 |
| full augmented residual | 9.99509348e-7 |
| R | 0.089021603824 |
| T | 0.442588273937 |
| A_volume | 0.468390120999 |
| closure | -1.23937705e-9 |
| external simultaneous worker peak | 1.612289 GiB |
| swap in/out delta | 0 / 0 pages |

P0 numeric、R/T/A、memory 和 no-swap Gate 通过。最终速度 Gate 不使用本次单点
替代 finalist HEAD 的三轮 paired baseline。
