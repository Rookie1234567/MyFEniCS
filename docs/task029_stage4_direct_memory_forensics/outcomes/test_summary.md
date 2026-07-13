# Task029 test summary

## Stage A telemetry

| 检查 | 结果 |
|---|---|
| ruff | pass |
| `compileall benchmarks src` | pass |
| Docker full unit discovery | 128 passed, 10 skipped |
| focused factor/history aggregation | 12 passed |
| documentation contract | 11/11 |
| benchmark checker | 149/149 |
| `git diff --check` | pass |

镜像固定为 `myfenics-stage4:task28@sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`。

## Stage B full-solve validation

| 检查 | h5 MPI4 | h3 MPI4 |
|---|---|---|
| clean source SHA | `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc` | `fba69d88ea8590ea01537b7561edff1684f25135` |
| source-code equivalence | baseline implementation | only tracked docs/evidence changed since h5 SHA |
| full solve | pass | pass |
| assemble-only | false | false |
| true residual | `5.225e-12` | `1.382e-11` |
| max Task28 R/T/A abs delta | `0` | `1.865e-14` |
| energy closure | `1.219e-13` | `7.305e-14` |
| factor inventory | 33,862,428 nnz | 266,127,836 nnz |
| peak stage | KSPSetUp | KSPSetUp |
| swap-in/out | 0 / 0 pages | 0 / 0 pages |

## h5 rank diagnostics

MPI1 PETSc LU、MPI1 forced MUMPS、MPI2 MUMPS 和 MPI4 MUMPS 都完成 full solve，true residual/RTA Gate 全通过且无 swap。所有运行固定每 rank 1 个线程；同后端 MUMPS 的总线程数分别为 1、2、4，并已在 `rank_scaling.csv` 明确记录。MPI2/MUMPS 是后续 h3 候选，MPI1 ordinary default 因后端不同只作诊断。

重型 timeline、solver log 和场输出保留在 gitignored `benchmarks/artifacts/cases/050/`；tracked summary 只引用通过 Gate 的轻量证据。用户未跟踪的 `papers/` 与 Task023 raw runs 未修改、未暂存。
