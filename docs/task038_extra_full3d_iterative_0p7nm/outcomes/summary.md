# Task038-extra Review V11 S6 closeout summary

## 一句话结论

S1 的全局结构审计、S2 的 p6/h10 foundation live-set 资格和 S4 的 p2/p3 LOR-edge 小 oracle 均在各自范围内通过；S5 的资源 Gate 通过，但唯一的 6→3 interlevel energy Gate 失败。因此 `lor_edge_geometric_mg_v1` 在 S5 关闭，不能写成 p6 solver pass，S6 之后及 p6 physical/PDE 均 `not_run_by_gate`。

这里的 **foundation live set** 是“完整计算所需的基础对象能否同时留在内存中”，不是 PDE 收敛或物理结果。S4 的 **oracle** 是小网格上的固定验证工具，也不是 ordinary default。

## 阶段总表

| 阶段 | 状态 | 事实 | 下一步边界 |
|---|---|---|---|
| V10 Q0 Reference E | `controlled_negative` | 500 步 true residual `4.2034233790900783e-4 > 1e-8` | 永久保留，不覆盖/重分类 |
| foundation-E | `pass` | p3/h50/MPI1/random，3020 步 `9.260562270838936e-9` | 只证明 exact LOR foundation 可收敛 |
| old global spectral audit | `controlled_negative` | GHEP smallest 固定 500 次 `reason=-1`, `converged=0` | spectrum 未建立 |
| HX/PCGAMG | `closed` | 旧 inverse 质量不足，V11 不再扫描 | production family 不重启 |
| S1 | `pass` | p2/p3 rank、SPD、Hermitian、endpoint residual 通过 | 授权 S2 |
| S2 | `pass` | p6/h10 foundation cold/retained/swap 通过 | 授权 S4 |
| S4 | `pass_at_small_oracle_scope` | 16/16 cases、8/8 MPI pairs 通过 | 授权 S5；不等于 p6 solver |
| S5 | `failed_algebra_gate` | 6→3 energy `0.04115402900674629 > 1e-9`；资源仍通过 | 关闭 LOR geometric MG，停止 |
| S6 | `docs_only_closeout` | outcome、compact、summary、response/progress 更新 | 不再运行 S4/S5/PDE |

## S1：全局 transfer/rank/spectral audit

| case | full/slave/independent | rank | singular min…max | lambda min…max | condition |
|---|---:|---:|---:|---:|---:|
| p2/h50/MPI1 | 988/220/768 | 768 | 0.25262199571308525…1.1728839979271446 | 0.07953013700040465…4.2447253801431595 | 53.37253952072989 |
| p3/h50/MPI1 | 3018/480/2538 | 2538 | 0.35955933841154997…3.7874131839018776 | 0.019970670477800642…283.0573385017638 | 14173.652247500142 |

Endpoint residuals were `1.1083766402470227e-13 / 2.7133854271858805e-15` for p2 and `2.0408235169191283e-11 / 6.039533107090146e-15` for p3; work, rank, Hermitian and SPD Gates passed. The S1 process-tree peak was `788,987,904 B`, swap `0 B`. As required, assembled high-order AIJ and temporary dense rank copies were audit-only; production high-order AIJ, global dense transfer and numeric allgather remain false.

Source/record identity: formal source `d19848e6f5484835a84186d13e349ae30fc8d56d`; compact record `outcomes/records/lor_global_spectral_audit_v2.json` SHA `8ffa8f1e74392bbd062314e0656d56c3bc464520c541d3a4668a52fad0a2ab09`; checker SHA `acec3b84f2e8001335bf362aa509e5a809657d5af11b33a847e51fd63cf1a5e3`.

## S2：p6/h10 foundation resource qualification

| item | measured |
|---|---:|
| source / physical | `12adebdf0e5e78de33818e97fd35cd870fef3a4e`; p6/h10/MPI1/13.5 nm |
| high/low rows | 173,802 / 173,802 |
| `B_L` NNZ | 5,825,468 |
| index / numeric | 23,997,084 / 93,207,488 B |
| known retained | 249,126,201 B |
| cold and external retained peak | 983,363,584 B |
| headroom to 2 GB / 1.55 GB | 1,016,636,416 / 566,636,416 B |
| repeated growth / swap | 0 B / 0 B |

Foundation objects were matrix-free high action, streaming DtN, fine LOR matrix/transfer metadata and restart20 reserve (21 basis + 4 auxiliary = 25 vectors). HX/PCGAMG, scalar node matrix, p6 factor, global high AIJ, global dense transfer, direct coarse and recovery arrays were not constructed. `/init.scope` shared swap was diagnostic only; formal process-tree/rank swap was zero. S2 record/checker remain immutable.

## S4：16-case oracle

The accepted aggregate is bound by [S4 outcome](lor_edge_geometric_mg_oracle_v1.md) and the two compact summaries. Aggregate checker SHA is `56b7eec1435abc69a38c38af056d8803e8f62a3ff6768b87faa594670c916c4e`. All 16 individual final true residuals were below `1e-8`, all process-tree peaks were below 500 MB, and all swaps were zero. The first four p2-MPI1 cases use `ca5171ac3bd6dd6ab333619cd76fd771524520e6`; the other 12 use `2b2df645418ee28c68681832661e58993897166d`.

## S5：p6/h10 capacity and algebra boundary

The fixed S5 record and independent checker are [record](records/lor_edge_geometric_mg_p6_capacity_v1.json) and [checker](records/lor_edge_geometric_mg_p6_capacity_v1_checker.json). The formal source was `2507a16d8f19df9b432319ae1625ea9b817d78f8`.

| level | rows | NNZ | index / numeric bytes |
|---:|---:|---:|---:|
| 1 | 1,067 | 37,253 | 153,284 / 596,048 |
| 3 | 23,073 | 783,083 | 3,224,628 / 12,529,328 |
| 6 | 173,802 | 5,825,468 | 23,997,084 / 93,207,488 |

| transfer | edge map | edge bytes | node map | node bytes |
|---|---:|---:|---:|---:|
| 6→3 | 882×144, 26,136 NNZ | 2,032,128 | 343×64, 21,952 NNZ | 351,232 |
| 3→1 | 144×12, 324 NNZ | 27,648 | 64×8, 512 NNZ | 8,192 |

The 3→1 energy relative was `2.7851655955739857e-15`, but 6→3 was `0.04115402900674629`. The external cold/retained peak was `1,207,476,224 B` and swap `0 B`; known combined ledger was `296,345,065 B`. The record's own retained ledger sample was `1,201,344,512 B` with `904,999,447 B` unattributed; these are different measurement fields and are not conflated. Fixed smoother facts were degree 3, power 10, one pre/one post; reserve was 25 vectors / `69,520,800 B`; p1 budget was derived `885,908 B` with no solver/factor.

The primary blocker is 6→3 interlevel energy consistency, not p1 distributed coarse size. Local diagnosis found non-nested p3/p6 GLL nodes; naive tiled composition defect was `0.23558864802518256`. No tiled repair, parameter scan or alternate operator was implemented.

## Historical negatives and evidence boundary

The old Q0 500-step negative, foundation-E pass, old spectral nonconvergence, HX/PCGAMG closure, S1/S2/S4 evidence, and the ba40358 probe-domain-invalid attempt are all retained. The ba40358 archived compact hashes are `ad8bbc3dfd81ba489efd6a4b2c24530c43f68484facc43020f9c5044f3be2a3f` (record) and `93423f917256edd40ac13727af2feac58e4dcc63dde29a229742e6b960f5aaa8` (checker); neither is reclassified.

No S4 repair, S5+ stage, p6 physical Maxwell, p6/h5, 0.7 nm PDE, official physics, or production coarse solver was run. The next blocker therefore has **not** converged to “p1 distributed coarse solver”; it is first the failed 6→3 transfer algebra Gate.

## Verification and integration boundary

| check | result |
|---|---|
| test312 | 20 passed / 350.31 s |
| test313 | 22 passed |
| related test294 | 3 passed / 91.97 s |
| compileall / AST / diff-check | passed |
| Ruff | unavailable in qualified environment; not installed |
| CI | not claimed |

The current work only updates docs and compact S6 summaries. Ordinary default, `master`, production numerical core and full 0.7 nm PDE remain unchanged.

## 冻结的 V9/V10 prior-phase authority（不覆盖 V11）

本附录恢复此前 summary 中仍具边界意义的阶段性事实。它们是 phase-local frozen facts：V11 的 S1/S2/S4/S5 结果不会删除、覆盖或重新裁决它们；foundation-E 的 3020 步 PASS 也不重分类旧的 500-step negative。

| prior 阶段/事实 | 冻结状态与数值 | 证据入口 |
|---|---|---|
| P0 checkpoint/restart | `PASS`，只归属于 `ba9016310d09c388a953fce93d9e71761343311f` fresh v2；roundtrip、restart-boundary residual、PC legality、provenance 通过 | [`memory_first_authority_contract.md`](memory_first_authority_contract.md)、`records/memory_first_authority_v1.json`、`records/memory_first_authority_checker_v1.json` |
| P1 v2 | 实际完成 9/16：8 个 p2 individual PASS；p3/h50 MPI1/random 在固定 `max_it=2000` 后 final explicit true residual `0.01027838962263555 > 1e-8`，分类 `FAILED_AT_FIXED_MEMORY_ITERATION_CAP` | [`memory_first_small_v2.md`](memory_first_small_v2.md)、`records/memory_first_small_v2.json`、`records/memory_first_small_v2_checker.json` |
| P1 资源口径 | cycle RSS 是 rank-root process-tree ledger；MPI2 不含 launcher；GNU time 不是完整 process-tree/cgroup authority；共享 `/init.scope` 的 `13,799,424 B` 仅 diagnostic，worker process-tree/rank swap 为 `0` | [`response_v9.md`](../response_v9.md)、上述 P1 compact records |
| P2–P7 | `not_run_by_gate`；没有 p6/h10 setup、physical Maxwell、MPI2 physical、h5 scaling、2 TiB workflow 或完整 0.7 nm PDE 结果 | [`lor_hx_p6h10_setup_v2.md`](lor_hx_p6h10_setup_v2.md)、[`lor_hx_p6h10_positive_longrun_v2.md`](lor_hx_p6h10_positive_longrun_v2.md)、[`lor_hx_p6h10_physical_longrun_v2.md`](lor_hx_p6h10_physical_longrun_v2.md)、[`lor_hx_p6h10_mpi2_v2.md`](lor_hx_p6h10_mpi2_v2.md)、[`lor_hx_h5_scaling_v2.md`](lor_hx_h5_scaling_v2.md)、[`feasibility_0p7nm_2tib_v3.md`](feasibility_0p7nm_2tib_v3.md) |
| old L2 one-apply | 永久 `FAIL`：`rho=1.7348663090876784 > 0.45`；不是 physical Maxwell 或 exact-A 结论 | [`lor_native_complex_hx_oracle.md`](lor_native_complex_hx_oracle.md)、[`lor_exact_contraction.md`](lor_exact_contraction.md)、old record SHA `0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3` |
| old v1 80-step performance | `FAIL`，保留为短迭代性能负结果；不能与后续长迭代正确性或 V11 S4 small oracle 混称 | [`response_v7_addendum.md`](../response_v7_addendum.md)、`records/memory_first_authority_v1.json` (`old_k1_v1_80_step`) |
| additive-v2 | formally `CLOSED`；不恢复、不扫描参数、不提升 ordinary default | [`response_v8.md`](../response_v8.md)、[`response_v9.md`](../response_v9.md)、`records/lor_native_complex_hx_krylov_pc_additive_v2_campaign_v1.json` |
| V10 Q0 Reference N | `diagnostic-only`；`rho=2.1958595524302254e-3`；`2.8019257502717445` 是 stored owner packet 与 trace-dual inferred re-encoded evidence 的坐标混用边界，不能证明 replay algebra PASS | [`p3_exact_reference_triage.md`](p3_exact_reference_triage.md)、[`response_v10.md`](../response_v10.md)、`records/p3_exact_reference_triage_v1_checker.json` |
| V10 Q1–Q5 | `not_run_by_Q0_hard_stop`；Q0 Reference E 的 500-step explicit rho=`4.2034233790900783e-4 > 1e-8`，foundation-E 后续 PASS 不覆盖该旧 negative | [`response_v10.md`](../response_v10.md)、[`lor_global_spectral_audit_v2.md`](lor_global_spectral_audit_v2.md) |

这些 prior 事实与 V11 的 S4 16/16 小 oracle、S5 6→3 algebra failure 是不同阶段、不同对象和不同 Gate；任何一个不能被另一个替代。
