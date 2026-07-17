# Case092：LU-teacher NN-only local inverse feasibility

本 Case 对应 PARA-Task003，最终状态为 `exact_lu_oracle_global_signal_insufficient`。

| 编号 | 冻结合同 |
|---|---|
| 1. | task = PARA-Task003 |
| 2. | predecessor = PARA-Task002 Review V1 |
| 3. | mesh = h5 only |
| 4. | wavelength = 13.5 nm |
| 5. | geometry = validated full-3D Si grating |
| 6. | element = p2 Nédélec hexahedral |
| 7. | FE DoF = 44,698 |
| 8. | periodicity = double Floquet |
| 9. | ports = 80 Fourier-DtN unknowns |
| 10. | outer = right FGMRES90 |
| 11. | coarse = 75D true-action Galerkin |
| 12. | physical slabs = 16 |
| 13. | formal parallelism = MPI4 |
| 14. | first target = slab 9 |
| 15. | conditional targets = slab 0/10 |
| 16. | teacher = sparse LU COLAMD |
| 17. | input = raw local residual only |
| 18. | label = exact local LU solution |
| 19. | online training = false |
| 20. | P3-P7 = not run by oracle Gate |
| 21. | ordinary default changed = false |
| 22. | heavy root = benchmarks/artifacts/cases/092 |

## 物理问题

物理模型与 Task001/002 相同：13.5 nm complex-Si periodic block grating、S polarization、80 个 Fourier-DtN auxiliary unknowns。Task003 只改变 selected local slab 的 oracle 研究后端。

## 参数说明

P0 使用当前 16-slab ILU0 two-step baseline。Capture A/B/C 只保存 slab 9 的 512/128/64 个 raw RHS，不保存 ILU output 或 ILU residual。P1 对同一 operator factorize 一次并复用 704 个 RHS。

P2 先运行 slab-9 exact LU oracle；因为迭代未下降 2%，再运行唯一允许的 slab 0/9/10 conditional oracle。三-slab 只下降 2.33%，未达到 5%。

## PyCharm

Windows PyCharm 应使用 WSL 解释器 `/home/fenics/.local/bin/myfenics-python-complex`，working directory 指向 WSL 仓库路径。Task003 没有进入 GPU 模型训练阶段。

## CLI 或测试

正式入口仍为 `python -m benchmarks.run_workstation_iterative`。Oracle 通过显式 `--exact-lu-enabled-slabs` 启用。Teacher dataset 由 `python -m benchmarks.neural_pc.build_lu_teacher_dataset` 生成。

运行测试：`python -m pytest -q src/test`。`run.sh` 只给出阶段顺序，避免越过 Gate 自动启动后续阶段。

## 代码路径与理论

`src.solvers.lu_teacher_local_solver` 实现 one-factor/many-RHS sparse LU。`petsc_capture` 提供 slab filter 与 raw-only capture。`run_workstation_iterative` 只在 explicit oracle flag 下替换 selected local action。

## 当前证据

slab-9 teacher residual median/p95/max 为 `5.94e-15 / 7.50e-15 / 9.59e-15`。Factorization 为 2.924 s，L+U fill 为 7.783×，显式存储估算 82.07 MB。

P0 baseline 为 860 iterations。slab-9 exact LU 为 862；slab 0/9/10 exact LU 为 840，只下降 2.33%。所有 formal run 的 full residual、R/T/A 和 closure 通过。

## 结果解释

单 slab 理想局部逆没有改善外层迭代，三个代表 slab 的理想上限也没有达到任务书 5% Gate。近似 exact LU 的 learned model 不可能突破该固定 selected-slab oracle 上限，因此继续训练不能建立 global acceleration 因果链。

## 限制

结论只覆盖一个 h5 physical RHS、当前 MPI4 partition 与当前 16-slab/two-step/coarse 架构。它不证明所有 NN local inverse 在其他 slab 集合、全 16 slabs、其他 coarse space 或其他物理参数下都无效。

未运行 P3 learned linear、nonlinear NN、P4 shadow、P5 active、P6 factor removal、P7 slab-specific models、h3 或 h2；这些均是 Gate 要求，不是遗漏。
