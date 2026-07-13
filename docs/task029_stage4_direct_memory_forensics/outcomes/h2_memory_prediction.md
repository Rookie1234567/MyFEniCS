# h=2 直接法内存预测

## 决策

当前工作站不适合运行 Task29 h=2 optimized direct。两种独立的两点外推分别得到约 22.2–22.3 GiB，明确的敏感性区间为 **18.882–27.913 GiB**；上界显著超过冻结的 13.5 GiB 限值。

## 输入

拟合使用 h=5 与 h=3 的同一最终诊断候选：default in-core MUMPS、MPI2、每 rank 一线程、完整求解、零 swap，source 为 `6babe4700328be2b3b93aad7e3e6c212b6dbad10`。

| 量 | h=5 实测 | h=3 实测 | h=2 目标/输入 |
|---|---:|---:|---:|
| FE DoF | 44,698 | 198,438 | 615,108 |
| augmented nnz | 4,896,156 | 21,317,860 | 65,448,472 |
| factor nnz | 33,940,948 | 266,564,172 | predicted below |
| simultaneous worker RSS | 1,655.484 MiB | 7,343.137 MiB | 下文预测 |

h=2 FE DoF 与 augmented nnz 来自只读的 Task28 reviewed reference（`615,188` augmented rows，包含 80 个 auxiliary unknown）。该历史运行是 MPI8，且报告不同的历史上界口径，因此不混入拟合。

## 模型 1：DoF 幂律

对 `RSS = c * n_fe^p`，两点实测给出：

```text
p = 0.9994126366
h2 prediction = 22,746.761 MiB = 22.214 GiB
```

这个接近线性的指数只是在 h=5 到 h=3 区间的经验拟合，不是一般 FEM 复杂度结论。

## 模型 2：factor-nnz / fill 路径

先由 augmented nnz 外推 factor nnz，再由 factor nnz 外推 RSS：

```text
factor_nnz ~ augmented_nnz^1.4009925144
predicted h2 factor nnz = 1,283,227,194
RSS ~ factor_nnz^0.7227936186
h2 prediction = 22,865.965 MiB = 22.330 GiB
```

factor 数值使用同一套 PETSc nnz inventory。PETSc 返回的 raw factor memory 为 0，因此不虚构 allocator-accounted MUMPS memory。

## 预测区间与不确定性

只有两个网格点，因此该区间是透明的工程敏感性范围，不是统计置信区间：

```text
lower = min(two central predictions) * 0.85 = 18.882 GiB
upper = max(two central predictions) * 1.25 = 27.913 GiB
```

不确定性包括 ordering/fill 波动、MPI metadata、采样波动，以及 h=2 factor fill 可能比两点模型增长更快的风险。Task28 历史 MPI8 上界 20.533 GiB 属于不同口径和环境，只作交叉佐证，但同样说明 13.5 GiB 不可信。

## 资源建议

阻塞阶段是 `KSPSetUp` / MUMPS analysis 与 numeric factorization。未来 guarded h=2 reference 至少应有 40 GiB cgroup-visible memory 和 48 GB 主机物理内存；更推荐 64 GB 主机，使预测上界之外仍保留 OS、Docker 与安全终止余量。该运行应属于另行授权、具备真实 watchdog 的任务。
