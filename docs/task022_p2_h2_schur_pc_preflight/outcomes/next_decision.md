# Next Decision

下一任务应从“继续跑 SciPy SPILU 参数”转为“PETSc/MPI-safe Schur/FE-response PC implementation + h=5 official R/T/A reconstruction”。

| 优先级 | 任务 | 目标 |
|---:|---|---|
| 1 | Reduced solution reconstruction | 把 converged reduced vector 回填到 Stage4 field，输出 h=5 official R/T/A |
| 2 | PETSc MatShell action | 用 matrix-free FE action + explicit aux coupling 复现 assembled residual |
| 3 | PETSc PCShell m=1 | 用 top `(0,0)` s mode 实现 h=5 production-like |
| 4 | PETSc FE inner solver | 测试 ASM+ILU、MUMPS/BLR、real-split AMS/HX |
| 5 | h=2 rerun | 在 PETSc/MPI PC 下重做 h=2 Candidate A/B |

不建议继续 serial SciPy SPILU h=2 参数扫描；不进入 h=1.5；不把 matrix-free 单独当 solver；不把 exact Schur 当低内存 production。
