# 3 nm 网格与 p/h 结论

本任务只完成 p6/h3 的 M800 与 M1200 candidate runs。两次 residual solve 均通过，但 own physics 均失败，故不能宣称 3 nm accuracy-qualified 或 grid convergence：

| case | result | reason |
|---|---|---|
| p6/h3 M800 | candidate negative | abs(A_balance-A_volume)=1.9160032445286745e-5 > 1e-5 |
| p6/h3 M1200 | candidate negative | abs(A_balance-A_volume)=1.8704745773062692e-5 > 1e-5 |
| h2.5/h2 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |

因此最终状态为 3NM_COMPLETED_NOT_GRID_CONVERGED。h3 已完成是运行事实，不是合格性通过；不得用 M800→M1200 的接近 scalar 取代 own Gate。
