# Task006 M3R0 failure telemetry

本文件由原 Case141 失败目录只读提取，未运行 FEM。

| tuple | relative residual | absolute residual norm | RHS denominator | KSP | peak PSS | swap |
|---|---:|---:|---:|---|---:|---:|
| `117.5,17.25/A07` | 1.5050283166105661e-09 | 3.2603068026197944e-09 | 2.1662760538368100e+00 | CONVERGED_ITS / 1 | 5.532 GiB | 0 B |
| `117.5,17.25/A09` | 1.4079544140587495e-09 | 6.7395453769312291e-09 | 4.7867639105608211e+00 | CONVERGED_ITS / 1 | 5.516 GiB | 0 B |

残差分子/分母和 full-operator residual method 均来自 run_summary；MUMPS INFOG/RINFOG 只按 raw index 保存，未推断字段含义。未记录的 PETSc/thread 环境变量明确标为 `not_recorded`。
