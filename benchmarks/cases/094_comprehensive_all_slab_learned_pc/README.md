# Case094：Comprehensive All-Slab Learned Local Inverse

本 Case 对应 PARA-Task005，只在当前 research branch 上验证固定 h5 operator 的
16 个 slab-specific learned local inverses。它不改变 ordinary default，也不自动运行
h3/h2。

| 编号 | 冻结合同 |
|---|---|
| 1. | task = PARA-Task005 |
| 2. | predecessor = PARA-Task004 positive oracle signal |
| 3. | mesh = h5 only |
| 4. | wavelength = 13.5 nm |
| 5. | material = current complex Si |
| 6. | element = p2 Nédélec hexahedral |
| 7. | FE DoF = 44,698 |
| 8. | periodicity = double Floquet |
| 9. | ports = 80 Fourier-DtN unknowns |
| 10. | outer = right FGMRES90 |
| 11. | coarse = fixed 75D true-action Galerkin |
| 12. | physical slabs = 16 |
| 13. | overlap = 0.25 layers |
| 14. | formal parallelism = MPI4 |
| 15. | representative slabs = 0,5,9,15 |
| 16. | train/validation/screening = 1024/256/256 per slab |
| 17. | primary GPU = Quadro RTX 8000 |
| 18. | persistent CUDA process required = true |
| 19. | private exact-audit CSR exceeded memory budget |
| 20. | P3 through P10 = stopped by P2 Gate |
| 21. | ordinary default changed = false |
| 22. | production claim allowed = false |

## 物理问题

物理问题固定为 13.5 nm complex-Si periodic block grating、S polarization、
p2 Nédélec、double Floquet 和 80 个 Fourier-DtN unknowns。Task005 只研究
当前 h5 operator 上的 slab-specific learned local inverse，不外推到 h3/h2。

## 参数说明

| 项目 | 值 |
|---|---:|
| 物理 | 13.5 nm、当前 complex Si、theta 80°、phi 0°、S polarization |
| 离散 | p2 Nédélec hexahedral，h5，44,698 FE DoF |
| 并行 | MPI4，每 rank/BLAS 1 thread |
| GPU | 单进程 persistent CUDA，GPU 0 Quadro RTX 8000 |
| 外层 | right FGMRES90，rtol 1e-6，max_it 1200 |
| PC | 16 slabs、overlap 0.25、75D coarse、two-step + post-smooth |
| 数据 | 每 slab 1024 train + 256 validation + 256 holdout |
| artifacts | `benchmarks/artifacts/cases/094/`，Git ignored |

T1/T2/V/H 使用独立执行产生的 capture 文件，但来自相同确定性 RHS 和 Krylov
轨迹分布；这不构成跨物理、跨随机种子或跨轨迹的统计独立性。当前 V 未用于
模型选择；H 已被用于候选 screening，身份应为 consumed screening split。

## PyCharm

Windows PyCharm 的 FEniCS 运行解释器为
`/home/fenics/.local/bin/myfenics-python-complex`，working directory 为
`/mnt/c/Users/Administrator/Desktop/MyProject`。GPU 训练使用 WSL
`fenics-ml` 环境；正式 FEniCS/MPI 求解仍使用 complex wrapper。

## CLI 或测试

正式 worker 入口为 `python -m benchmarks.run_workstation_iterative`。capture、
teacher、linear/nonlinear screen 和 owner batch 分别由
`benchmarks/neural_pc/` 下的 Task005 脚本驱动。完整 CPU/FEniCS 套件和
`fenics-ml` 中的 PyTorch 导出测试分开执行。

## 代码路径与理论

raw capture hook 位于 `src/solvers/physical_slab_two_level.py`；有界 multi-RHS
SuperLU teacher 位于 `src/solvers/lu_teacher_local_solver.py`。linear ridge、
structured synthetic probe、nonlinear MLP 和 owner-batch benchmark 位于
`benchmarks/neural_pc/`。Task005 以 exact local inverse 为 teacher，但 learned
候选必须独立满足质量、runtime、memory 和 no-hidden-ILU Gate。

## 强制顺序

```text
P0 clean baseline
-> P1 T1/T2/V/H raw capture + sequential LU teacher
-> P2 R4 data/model/backend screen
-> P3 16 independent models
-> P4 shadow
-> P5 diagnostic fallback
-> P6 true no-hidden-ILU replacement
-> P7 three paired A/B
-> conditional P8/P9
-> P10 decision
```

任一 Gate 失败即按任务书停止后续条件阶段并保留负结果。特别是不能用 shadow 或
fallback profile 声称 factor removal，不能在 16-independent 工程 Gate 通过前训练
shared/expert 模型。

## 当前证据

clean source `f4c0600...` 的初始 baseline 为 852 iterations、97.253 s，
三种 residual 约 `9.9951e-7`，外部 simultaneous worker peak 1.612 GiB，
swap in/out 为 0。该数字是初始 sanity；最终性能声明仍使用 finalist HEAD 上三组
paired A/B。

P1 的 16-slab teacher 数据和 leakage/fingerprint 审计通过。P2 仅在 R4
执行：linear D0/D1 与 nonlinear 候选都未同时满足 local quality、runtime 和
memory Gate。D1 负结果只覆盖当前 index-space structured synthetic recipe，
不能解释为所有物理结构化增强均无效。

## 结果解释

Task005 最终分类为 `learned_pc_memory_budget_failure`。主因不是 checkpoint
本身，而是 exact-audit 路径为每个 slab 持久复制 private CSR operator，导致
owner storage 超过预算。由于 P2 工程 Gate 已失败，P3 至 P10 均按任务书停止，
没有形成 all-16、global shadow、active replacement 或端到端性能声明。

## 限制

结论只覆盖 R4、当前 h5 operator、单一物理/RHS 和确定性 capture 轨迹。capture
仅记录 stride/offset，没有 phase、norm bucket 或 outer-iteration metadata；
H 已消耗，V 未使用。Task005 不证明 learned local inverse 理论上不可行，也不
证明显式 private CSR 是唯一 audit 实现。

后续只能通过独立 Task006 研究 borrowed assembled action、低存储 proxy 和
periodic exact audit。Task005 的 heavy evidence 不重复运行，ordinary default
保持不变。
