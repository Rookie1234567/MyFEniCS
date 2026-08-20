# T2：Full3D full-space matrix-free action formal evidence

本阶段只验证体积分算子的 action（给定一个向量，计算算子乘该向量的结果）。它没有创建 KSP、没有求解 PDE，也没有使用 T3 Fourier-DtN。五个 compact record 均绑定到 formal source SHA `6d60bb5a9a59e88da98b027efeed8506d5dd7a82`；该 SHA 包含一次已记录的窄修复：把 Floquet phase audit 中的 NumPy `bool_` 转为可序列化的原生 `bool`。

## 1. Formal run matrix

下表的 reference setup time 是所有 MPI rank 的 `MPI.MAX`；RSS 是每个 rank 当前自身 RSS 的 rank-max 采样，不是 process-tree peak。数值和资源列均为 `measured`，h10→h5 exponent 为 `derived`。

| case | MPI | global rows | reference | reference relative error | setup seconds (`MPI.MAX`) | setup RSS bytes | runner wall seconds | 12-repeat max relative difference | warm RSS span bytes | swap max bytes |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| p2-h50 | 1 | 988 | assembled | `1.0623006934406839e-15` | 0.31732522300080745 | 118964224 | 1.48 | 0.0 | 8192 | 0 |
| p3-h50 | 1 | 3018 | assembled | `3.571370033045663e-15` | 8.088676141996984 | 159297536 | 10.47 | 0.0 | 0 | 0 |
| p6-h10 | 1 | 173802 | independent | `7.263059324300498e-17` | 47.20262084500064 | 951054336 | 90.20 | 0.0 | 0 | 0 |
| p6-h10 | 2 | 173802 | independent | `7.120392279402028e-17` | 1.1358982199999446 | 293732352 | 19.66 | 0.0 | 0 | 0 |
| p6-h5 | 1 | 1127502 | scaling-only | not applicable | `1.405001967214048e-06` | 489308160 | 97.79 | 0.0 | 0 | 0 |

All five records report exactly 12 applies, one unique output hash across the 12 repeats, unchanged source vectors before/after, and `swap_used_bytes = 0` for every repeat. The warm RSS span is recomputed by the checker from `repeats.rss_bytes[4:]`; the fixed limit is `67108864` bytes.

## 2. Gate results

| Gate | measured / derived value | limit | result |
|---|---:|---:|---|
| p2 assembled action identity | `1.0623006934406839e-15` | `<=1e-12` | pass |
| p3 assembled action identity | `3.571370033045663e-15` | `<=1e-12` | pass |
| p6/h10 MPI1 independent identity | `7.263059324300498e-17` | `<=1e-11` | pass |
| p6/h10 MPI2 independent identity | `7.120392279402028e-17` | `<=1e-11` | pass |
| p6/h10 physical canonical source peer | relative L2 `2.646028570711081e-16` | `<=1e-12` | pass |
| p6/h10 physical canonical action peer | relative L2 `1.1449579596647522e-13` | `<=1e-12` | pass |
| deterministic repeat identity | 12/12 hashes equal; max relative difference `0.0` | 12 applies; repeat limit `1e-13` | pass |
| warm rank-max current RSS | maximum span `8192` bytes | `<=67108864` bytes | pass |
| swap | maximum `0` bytes | `0` | pass |
| retained h10→h5 payload exponent | `0.9779306095631883` | `<=1.10` | pass |
| exact five-record aggregate | 5 expected case/MPI identities | exactly five | pass |

The MPI peer comparison found 173802 common physical packet keys for both source and action, with zero duplicate, missing, or extra keys. The action comparison's maximum absolute coefficient difference was `1.1545123085329561e-12`; its relative L2 value, rather than this absolute value, is the frozen Gate quantity.

## 3. Retained numeric payload

| case | local retained bytes | global sum bytes | global max bytes |
|---|---:|---:|---:|
| p2-h50 MPI1 | 45696 | 45696 | 45696 |
| p3-h50 MPI1 | 127296 | 127296 | 127296 |
| p6-h10 MPI1 | 6151104 | 6151104 | 6151104 |
| p6-h10 MPI2 | 3492456 | 6988752 | 3496296 |
| p6-h5 MPI1 | 38290752 | 38290752 | 38290752 |

The checker derives the exponent from global rows and the `global max` retained payload: p6/h10 MPI1 has 173802 rows and 6151104 bytes; p6/h5 MPI1 has 1127502 rows and 38290752 bytes. No process-tree memory claim is made at T2; `resource.process_tree_evidence` remains `not_measured_t2`.

## 4. No-materialization audit

The five records all carry the same required action architecture audit: PETSc matrix type `python`, owner-local storage, finalized Floquet/MPC application once, DOLFINx N1curl orientation, no numeric allgather, no replicated global numeric vector, no global matrix/constraint matrix/condensed Schur/cell Schur/slab matrix, no dense cell tensor per apply, no KSP, no DtN, zero factors and zero forbidden matrix NNZ. `ordinary_default_changed` is false. The checker independently recomputes these fields from each raw record.

## 5. Failure evidence retained

The first p2-h50 MPI1 attempt at implementation SHA `5ce75540ff97089f74021660876ab2022ffad1f9` reached raw mesh and vector artifacts but failed while serializing the compact record with `Object of type bool_ is not JSON serializable` (wall `6.17 s`). Its raw directory remains ignored at:

```text
benchmarks/artifacts/task038_extra_full3d_iterative_t2/p2-h50-mpi1/raw
```

The only fix was the explicit `bool(...)` conversion in the Floquet audit. The frozen p2-h50 case was then rerun once under the fix SHA in `p2-h50-mpi1-rerun`; no other case or parameter was retried.

## 6. Evidence boundary

The tracked compact records are under `outcomes/records/`. Full vectors, canonical shards and manifests, mesh files, JIT artifacts, and console/raw artifacts remain under the ignored `benchmarks/artifacts/task038_extra_full3d_iterative_t2/` directory. T2 is complete for this action-only scope; T3 dynamic DtN, KSP/PDE, process-tree measurement, T7, T8, and T9 were not run.
