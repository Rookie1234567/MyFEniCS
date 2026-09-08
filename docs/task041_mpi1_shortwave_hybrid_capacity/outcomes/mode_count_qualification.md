# Mode-count qualification

| case | 已完成 M | 结果 | 未完成阶梯 |
|---|---:|---|---|
| 3 nm p6/h3 fresh MPI8 | `800` | `IMPLEMENTATION_FAILURE` at `consumer_exit(solution_snapshot_destroyed)`；不构成 M qualification | M1200/M1600=`NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |
| 3 nm p6/h3 consumer retry MPI8 | `800` | candidate；solve/recovery mechanics通过，own physics closure失败 | M1200/M1600=`NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |
| 5 nm p6/h4 Task039 inherited MPI8 | `480` | full numerical/recovery/physics PASS | Task041 未新增 M 比较 |
| 5 nm p6/h4 Task041 local MPI8 | `480` | solve/recovery/physics PASS；独立本机 reproduction | Task041 未新增 M 比较 |
| 2 nm | `NA` | `not_run` | 全部 M 阶梯=`NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |

因此没有 Task041 的 M-convergence 或 3 nm 最小资格 M 结论。M800 是已执行 candidate，不是通过 physics qualification 的最小 M。
