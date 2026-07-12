# 3D 工作站 MPI4 迭代生产档

该路径不在普通单进程 `main.py` preset 中。它必须显式启动 MPI4：

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --config benchmarks/configs/workstation_p2.json \
  --h-nm 2 \
  --results-dir benchmarks/artifacts/iterative \
  --record benchmarks/records/workstation_p2_h2_mpi4.json
```

推荐统一运行：

```bash
sh benchmarks/scripts/run_level3_iterative.sh
python benchmarks/check_benchmarks.py --no-write
```

## 限定配置

| 部件 | 固定选择 |
|---|---|
| 外层 | right-preconditioned FGMRES，restart 100，rtol `1e-6` |
| 算子 | auxiliary DtN 精确凝聚后的 matrix-free `F-C H^-1 D` |
| coarse | 24 个 z 节点 x 3 分量，正交后 75 维 |
| smoother | shifted-F，16 个物理 z slab，owner-computes Schwarz |
| 局部解 | GMRES(1) + ILU(1)，两次 smoother action |
| MPI | 4 ranks；p=2；h=5/3/2 nm |

## 已记录结果

| h (nm) | DoF FE | 迭代 | full true residual | 总峰值 RSS (GB) | R | T | A_volume |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | `9.84e-7` | 1.991 | 0.08902 | 0.44259 | 0.46839 |
| 3 | 198,438 | 993 | `9.93e-7` | 5.082 | 0.004613 | 0.583653 | 0.411734 |
| 2 | 615,108 | 1,804 | `9.997e-7` | 13.080 | 0.001343 | 0.599213 | 0.399444 |

表中数字只对 benchmark 记录的 50 x 25 x 140 nm、Si、13.5 nm、80 度 s 偏振 target case 成立。h=5 迭代 RTA 与同 h direct 一致；h=3 同样有 direct 交叉检查。记录身份和 Gate 由 `check_benchmarks.py` 判定。

## 成功条件

`qualified_profile=true`、`ksp_reason>0`、reported/condensed/full 三种残差均合格、coarse rank=75、condition 低于阈值、official RTA 闭合、总 RSS 未越界。只看到 `KSP converged` 不够。

理论与代码分别见 [`../theory/iterative_solver_and_preconditioner.md`](../theory/iterative_solver_and_preconditioner.md) 和 [`../reference/code_walkthrough/33_workstation_fgmres_runtime.md`](../reference/code_walkthrough/33_workstation_fgmres_runtime.md)。PETSc FGMRES 参考：<https://petsc.org/release/manualpages/KSP/KSPFGMRES/>。
