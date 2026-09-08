# 3 nm mesh convergence

| mesh | M | status | reason/evidence |
|---|---:|---|---|
| p6/h3 fresh attempt | 800 | `IMPLEMENTATION_FAILURE` | diagnostic marker only；consumer exit=`solution_snapshot_destroyed`；formal_result/gates/physics=null |
| p6/h3 consumer retry | 800 | `candidate_controlled_negative` | five residuals通过；closure=`1.9160032445286745e-5`>`1e-5` |
| p6/h2.5 | NA | `not_run` | `NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |
| p6/h2 | NA | `not_run` | `NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |

没有 3 nm mesh convergence 结论，也没有将 retry candidate 的 R/T/A 写成 official result。后续网格停止是前置 physics Gate，而非资源或技术能力判定。
