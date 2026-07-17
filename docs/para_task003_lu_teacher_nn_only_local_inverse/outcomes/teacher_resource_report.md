# Sparse-LU teacher 资源与精度

| 指标 | slab 9 |
|---|---:|
| operator shape | 5,248 × 5,248 |
| matrix nnz | 526,696 |
| ordering / pivot threshold | COLAMD / 1.0 |
| factorization | 2.576 s |
| L / U nnz | 2,049,683 / 2,049,572 |
| total factor nnz | 4,099,255 |
| fill ratio | 7.783× |
| explicit L/U/permutation storage | 82,069,076 B |
| reused RHS | 704 |
| triangular solve mean / p95 / max | 13.263 / 14.500 / 18.528 ms |
| teacher rho median / p95 / max | `5.940e-15 / 7.503e-15 / 9.585e-15` |
| process RSS before / after factor | 211.06 / 382.49 MB |
| process peak after factor | 400.50 MB |
| process RSS after destroy | 362.07 MB |
| swap in/out pages | 0 / 0 |
| factor destroy confirmed | true |

RSS after destroy仍包含 704 个 RHS、teacher targets、压缩写入缓冲及 Python/SciPy allocator cache，不能把未完全回落解释为 factor 仍可调用；对象 lifecycle 已置空并通过 destroy test。WSL 当前没有可读的 cgroup v2 `memory.current/peak`，字段记录为 null，不伪造 cgroup 数据。
