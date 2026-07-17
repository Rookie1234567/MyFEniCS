# Factor lifecycle 与 MPI owner 报告

## Census

| 指标 | 结果 |
|---|---:|
| slabs | 16/16 |
| shape classes | 3,670 / 5,248 |
| census factor nnz | 45,724,195 |
| census factor storage | 915,625,532 B |
| formal G16 factor nnz | 45,747,719 |
| formal G16 factor storage | 916,096,012 B |
| test RHS rho max | `8.3014e-15` |
| factor destroy/reject apply | 16/16 |
| swap delta | 0 / 0 |

## Formal G16 per-rank

| owner rank | slabs | exact bytes | factorization sum s | exact apply count | exact solve accumulated s | mean per-slab apply ms | max slab p95 ms |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | 0,1,8,9 | 228,705,988 | 6.5770 | 13,584 | 141.594 | 10.424 | 14.766 |
| 1 | 2,3,10,11 | 229,346,288 | 6.5660 | 13,584 | 141.607 | 10.425 | 14.864 |
| 2 | 4,5,12,13 | 228,702,508 | 6.6008 | 13,584 | 142.176 | 10.466 | 14.922 |
| 3 | 6,7,14,15 | 229,341,228 | 6.5629 | 13,584 | 141.477 | 10.415 | 14.889 |

Full G16 的 exact-enabled ILU factor/apply、stored ILU nnz 和 hidden fallback 均为 0。运行结束 root record 汇集 16 个 destroyed=true diagnostics；重复 destroy由 unit/MPI2 test验证为幂等。

Census 与 formal G16 的少量 fill差异来自 SuperLU numeric pivot fill；operator fingerprints不变，formal residual和census test RHS均通过。两者存储差约0.05%，不会改变安全 Gate。
