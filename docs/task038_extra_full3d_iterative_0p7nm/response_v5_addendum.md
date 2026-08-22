# Task038-extra Review V5 v2 补充响应

本文件补充 `response_v5.md`，不覆盖原 response。用户明确授权了一次 fresh v2 LA0/LA1 attempt；第一次 lifecycle stop、旧 N2 v1 negative、`response_v5.md` 和 v1 evidence 均保持不变。

## V5 §12 补充矩阵

| # | Review 要求 | v2 实际回答 |
|---:|---|---|
| 1 | 身份 | branch `codex/20260820-task38-extra-full3d-iterative-0p7nm`；source `ae599854d08fcd16e3f1d204017bc4bc04482bbf`；upstream `9b7e0b4d6190957e2d40ca9650e0151383cbe1b9`；formal source clean；closure pre-commit: v2 checker compact + v2 outcome + response addendum，无代码修改。 |
| 2 | old N2 v1 | 保持 `CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE`；compact SHA `d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40`，未修改。 |
| 3 | failed class | digest `0c6b9830423f8baf83b6714ac178c724b63af1359d01b3ca5badd1d40c070a67`；slot `1`；rows `882`；class-order SHA `a7b649d25c7f843a160816a3c4fe3836243e9639eb7c0ba43dd2901955511028`。 |
| 4 | Hermitian/eigen/condition | defect `9.757433025229162e-17`；λmin `0.00045043462322559666`；λmax `25934.54102501312`；κ₂ `57576704.11589122`。 |
| 5 | factorization | `8.158904706122267e-16`；packed roundtrip exact，relative `0`。 |
| 6 | S0–S3 | S0 `1.0426245523812324e-11` / back `9.01854818500637e-19`；S1 `9.316208748538303e-12` / `8.058382790658791e-19`；S2 `2.544882468429781e-11` / `2.2012856990841358e-18`；S3 `6.672944399115928e-12` / `5.771998219478778e-19`。 |
| 7 | Path | 独立数值诊断为 `Path T` candidate；不是 formal Gate PASS。 |
| 8 | production solve | 未修改 `_PackedCholesky.solve`、B0、patch、mode、coarse 或 Gate。 |
| 9 | original Gate | `<=1.0e-11` 完全未变；S0 与旧 v1 residual 相对一致性为 `0`。 |
| 10 | resource/lifecycle | peak `1,487,814,656 B`；swap `0`；145 samples；约145.004 s；already_exited/no orphan/no SIGKILL。worker/checker rc=`1/1`，因此 overall `CONTROLLED_STOP_LA1_MARKER_REGISTRATION / NOT_QUALIFIED`。 |
| 11 | N2 MPI1 setup | 未完成；没有完整 252 patch inventory、mode/coarse/Z/AZ/E 或 post-setup retained qualification。 |
| 12 | MPI2 | 未运行；cross-MPI identity/factor ownership not_run。 |
| 13 | N3 | 五类 source、coarse-only/full PC rho 和资源均 not_run。 |
| 14 | N4 | 20/100/150/200 true residual、contraction、KSP/PDE 和资源均 not_run。 |
| 15 | 分类 | measured：LA0/LA1 facts与资源；independently_recomputed：checker metrics；controlled stop：marker registration；not_run：LA2及后续。不能把 Path T candidate 写成 PASS。 |
| 16 | T6/physics/后续 | T6-F、official physics、T7–T9、full 0.7 nm PDE 全部 not_run。 |
| 17 | selective merge | watchdog ownership fix + 真实 subprocess E2E 可审阅；LA0 marker runner/LA1 diagnostic research-only/not-qualified；不提升 production triangular 修复。 |
| 18 | evidence | raw root 为 `benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/`；tracked checker compact 为 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/n2_local_factor_la_v2.json`，`3933 B`，SHA `9610f69826092a31a69d6c3a7cbcb8cefd69ada0954c767b11953abafed47d44`。完整 raw/marker/mesh/hash/bytes 见 `local_factor_linear_algebra_diagnostic_v2.md`。 |

## 关键停止事实

worker 的实际 marker 为：

```text
preflight → mesh_space_mpc → subdomain_inventory → local_factor_build → failure
```

在 LA0 已捕获 exact class、完成 LA1 计算后，marker 注册调用报：

```text
ValueError: unknown N2 marker: linear_algebra_diagnostic
```

因此 checker 正确返回 `passed=false`。这次 failure 不代表 S1/S3 数值失败，也不代表资源 hard stop；它意味着 formal worker 没有满足 rc0/lifecycle contract。按一次 formal attempt 规则，禁止修 marker或重跑。

## 保留与停止边界

旧 N2 v1 compact/raw、第一次 LA0 lifecycle compact（SHA `e0d161d2827b2bed390fe4ab6ef7238891606edc094adb0513a3e0ba4c10a739`）、本次 v2 raw/record/watchdog/worker.log 和当前 checker compact 均保留。LA2、fresh N2、MPI2、N3、N4 及所有禁止阶段不启动。本 addendum 不修改 `response_v5.md`，也不构成 production solver 或 formal qualification。
