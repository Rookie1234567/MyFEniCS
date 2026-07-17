# Case091：Batched linear reduced smoother

本 case 对应 PARA-Task002，最终状态为 `local_microkernel_success_global_signal_insufficient`。

| 编号 | 冻结合同 |
|---|---|
| 1. | task = PARA-Task002 |
| 2. | predecessor = PARA-Task001 |
| 3. | mesh = h5 only |
| 4. | wavelength = 13.5 nm |
| 5. | geometry = validated full-3D Si grating |
| 6. | element = p2 Nédélec hexahedral |
| 7. | periodicity = double Floquet |
| 8. | ports = 80 Fourier-DtN unknowns |
| 9. | outer solver = right FGMRES |
| 10. | coarse basis = 75D true-action Galerkin |
| 11. | physical slabs = 16 |
| 12. | formal parallelism = MPI4 |
| 13. | selected experimental slab = 9 |
| 14. | selected reduced rank = 32 |
| 15. | offline construction = CUDA complex128 POD/ridge |
| 16. | runtime = frozen fixed linear CPU BLAS |
| 17. | local action = persistent SciPy CSR |
| 18. | shadow audit = every call exact |
| 19. | active acceptance = non-degradation |
| 20. | ordinary default changed = false |
| 21. | all-slab/h3/h2 = not run |
| 22. | heavy root = benchmarks/artifacts/cases/091 |

## 物理问题

物理模型、材料、几何、偏振、入射角、DtN 模式和 official R/T/A 路径均与 PARA-Task001 冻结目标一致。本任务只改变 owner-local slab correction 的研究实现。

## 参数说明

P1 使用 boundary slab 0、grating/interior slab 9 和 second interior slab 10。P2 在独立 validation 上选择 rank 32。P3/P4 只启用 slab 9，其余 15 个 slab 保持原 ILU。

## PyCharm

在 Windows PyCharm 中使用 WSL 解释器 `/home/fenics/.local/bin/myfenics-python-complex`，工作目录指向仓库的 WSL 路径。GPU 离线构造改用 `/home/fenics/miniforge3/envs/fenics-ml/bin/python`。

## CLI 或测试

微基准入口是 `python -m benchmarks.neural_pc.benchmark_local_action`。CUDA 构造与验证入口分别是 `fit_linear_reduced_map` 和 `evaluate_batched_reduced_smoother`。正式 h5 通过 `benchmarks.run_workstation_iterative` 的显式 `--linear-reduced-*` 参数启用。

完整测试运行 `python -m pytest -q src/test`。重型命令与结果 JSON 不提交。

## 代码路径与理论

`src.solvers.local_slab_solver` 提供 portable 与持久 compiled CSR action。`src.solvers.batched_reduced_smoother` 实现固定线性 map、batch API、checkpoint、融合 audit 和 local adapter。全局可信框架仍由 physical slab two-level 和 exact condensed DtN 路径提供。

## 当前证据

P1 的 SciPy mean 为 Python row loop 的 7.13%-7.49%，complex128 error 为 0。rank-32 validation `rho median/p95=0.593884/0.745695`，线性误差 `3.894e-15`，batch 差异为 0。

P3 shadow 的 5166 次候选全部通过非退化 audit。P4 active 的 full true residual 为 `9.985467e-7`，official energy closure 通过，peak 为 1.618153 GiB。

## 结果解释

P4 迭代从 849 到 847，仅下降 0.24%；solve 从 151.343 s 到 137.261 s，下降 9.30%。两者均未达到任务书的独立 signal gate。因此局部微核成功不能升级为全局加速成功。

## 限制

只验证一个物理 RHS、一个 MPI4 partition、当前 WSL/PETSc 3.19.6 ABI 和 slab 9。墙钟存在运行间波动，P3 的较低 solve 时间不作为性能声明。没有运行 P5、factor removal、all-slab、h3 或 h2，也没有改变 ordinary default。
