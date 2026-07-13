# Task029 test summary

## Stage A

| 检查 | 结果 |
|---|---|
| ruff | pass |
| `compileall benchmarks src` | pass |
| Docker focused telemetry + documentation | 18 passed |
| Docker focused source/full-solve Gate regression | 9 passed |
| Docker focused factor/history aggregation regression | 12 passed |
| Docker full unit discovery | 128 passed, 10 skipped |
| Benchmark checker | 149/149 |
| `git diff --check` | pass |

镜像固定为 `myfenics-stage4:task28@sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`。这里仅验证遥测和既有轻量回归；h5/h3 数值等价必须由后续完整 baseline solve 证明。

## Stage B h5

| 检查 | 结果 |
|---|---|
| clean source SHA | `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc` |
| Docker focused factor/history aggregation | 12 passed |
| Documentation contract after h5 evidence update | 11 passed |
| h5 full solve | pass |
| assemble-only | false |
| true residual Gate | `5.224671064148491e-12 <= 1e-8` |
| Task28 R/T/A absolute delta Gate | `0 / 0 / 0 <= 1e-8` |
| energy closure Gate | `1.219024881038422e-13 <= 1e-8` |
| factor inventory | available；33,862,428 nnz |
| external peak stage | `during_ksp_setup_peak` |
| swap delta | `0 / 0` pages |

完整运行目录为 ignored artifact `benchmarks/artifacts/cases/050/h5_default_mpi4_20260713T050814Z`；tracked summary 为 `benchmarks/cases/050_stage4_direct_memory_forensics/records/h5_baseline.json`。

收尾全量 Docker discovery 为 128 passed / 10 skipped，Benchmark checker 为 149/149；ruff、compileall、JSON/CSV 解析和 `git diff --check` 均通过。
