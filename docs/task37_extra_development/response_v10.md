# Task037-extra Review V10 consolidated response

用户于 2026-08-12 本轮再次明确授权：针对具体执行问题持续分析、窄修、监督推进，目标仍为 MPI1 full PDE process-tree RSS 严格 `<2,000,000,000 B`、swap=0，并取得可与直接法权威对照的物理结果。这是用户明确授权。相邻边界同样明确：授权不放宽数值、candidate count、RSS、swap、physics 或 provenance Gate，不允许把容量/数值负结果包装成 execution-fix。

本文件是 V10 收口，不改写 [response_v9.md](response_v9.md) 或 [review_report_v10.md](review_report_v10.md)。

## 一页结论

| 项目 | 最终状态 | 含义 |
|---|---|---|
| G2 / G3 / old G4 | `G2_FAIL / prohibited / prohibited` | 历史失败路线不重开、不扫描。 |
| H1R3 | passed | 保留历史 action/identity evidence。 |
| V8 H2B fixed-unit | `FAIL_NUMERIC / NOT_QUALIFIED` | 不因后续 execution fix 改写。 |
| V9 S0 | direction Gate fail | evidence 可验，但三组合无一取得方向资格。 |
| V9 P0 | qualified | 只资格化一个 central representative row-complete patch。 |
| V10 C1 | `CONTROLLED_STOP_CANDIDATE_REPRESENTATIVE_LIMIT / NOT_QUALIFIED` | 84 representatives 超过固定32；这是 capacity negative。 |
| M0 | local feasibility PASS / no qualification | 只有 test-only p4→p6 cell-local fixture。 |
| ordinary default | unchanged | 没有 production numerical promotion。 |
| C2 / H2B-K / H2D / H4 / PDE | not_run / locked | C1 未全通过，后续路线关闭。 |

## 1. C1 的真实结果

### 1.1 第一次 C1 formal：execution failure

这次 formal 使用 source `e58e14f3952b5adb9f57ca5d51dbf9b510cc3f7d`，raw 为 `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_e58e14f_run1`。

| 阶段 | RC / wall / process-tree peak / swap | 结果 |
|---|---:|---|
| stage | RC0 / `24.786440406998736 s` / `1,291,288,576 B` / 0 | 正常完成 |
| C1 | RC1 / `5.046119430990075 s` / `654,024,704 B` / 0 | `termination=null`，cleanup=true |

progress 最后到 `r2_factor_load_ready`。随后 module-level `_c1_cell_metadata` 缺少 `numpy` 作用域导入，产生 `NameError`。candidate、T、patch、action、factor 均未形成；这是 execution failure，不是 numeric fail。

当时的 v1 compact 是 generic `raw_unreadable` 历史输出：file SHA `21378ee3d6b3adf200597b115fd6fb964f185606f3272eea06cecbf29de348a7`，embedded evidence `ddc9e7182f0b1be71a52be34b2f96b8f99b3d2e440bf5eb65d84576e0456e2ee`。它不能被当作 capacity evidence。

### 1.2 唯一 execution-fix formal：candidate capacity stop

`aebc312f84b97418ba43a59d8b73cb403c53e8b4` 只修复 `np` scope 并增加 focused test，没有改变 action、MPC、patch、numeric 或 resource Gate。它是 Review V10 允许的唯一 C1 execution-fix，预算已经耗尽。

raw 为 `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_aebc312_execution_fix_run1`。

| 阶段/字段 | measured 值 |
|---|---:|
| stage | `24.819258175004506 s`，RC0，peak `1,281,986,560 B`，swap0 |
| C1 | `61.11731081700418 s`，RC1，peak `690,946,048 B`，swap0 |
| campaign total | `86.13728914600506 s` |
| termination / cleanup | `termination=null` / `processes_gone_after_c1=true` |
| topology | `252 cells / 24 classes / 84 neighborhoods / 173802 rows / 882 nloc / 9210 constraints` |
| candidate representatives | `84 > 32` |
| retained orbit metadata | `9,507,553 B <= 16,777,216 B` |
| max live patch matrix | `0` |

`candidate_representative_limit` 在 candidate 形成后立即受控停止。因此 preflight/T/probe/patch/congruence/action/factorization/factor store 均是 `not_run` 或 `not_formed`；不能把它们写成 congruence/action numeric fail。materialization 全部为 false，`fine_space=uncondensed_fullspace`、`condensation=false`，没有 global matrix、global constraint matrix、Schur、slab、KSP、DtN 或 PDE。

最终 C1 状态为 `CONTROLLED_STOP_CANDIDATE_REPRESENTATIVE_LIMIT / NOT_QUALIFIED`，route=`M0-review-only`。

## 2. checker provenance 与 v3 evidence

v2 在同一 frozen raw 上读到了真实 stop，但旧 checker 将 `measurement.cache` 与 worker 顶层 cache 错绑，造成 `c1_measurement`、manifest、patch audit、numeric evidence 的 telemetry false negatives。它不是新的 formal。

`aa71e1a63848715ad78591636a7e4c2dabe88438` 只修 checker cache/provenance binding，保持 raw 不变，并要求 raw source 与 checker source 分开、各自 clean。之后只运行了一次 checker-only，生成 v3；没有重启 C1。

| compact | file SHA | embedded evidence | checker/结果 |
|---|---|---|---|
| C1 v1 | `21378ee3d6b3adf200597b115fd6fb964f185606f3272eea06cecbf29de348a7` | `ddc9e7182f0b1be71a52be34b2f96b8f99b3d2e440bf5eb65d84576e0456e2ee` | generic raw-unreadable |
| C1 v2 | `5a188b4c9f7cd2e3f6a950c4483bb75b1a54374d3e4c4079ca1dbbcbd236522d` | `e32f73afc69e76eb172aa29606a7fb168c5afb4ecf90541ed032c777e7469259` | telemetry false negatives |
| C1 v3 | `2acee2a15ab2f9921bc6c7df6d5b9091e768b30803ca726fd9bed9aab986f956` | `e21b001863471f5709485726423e41dd3a9020c7d6bbe5dd35465a4e526b6fdc` | RC1 预期；`gate_failed`、`pass=false`、route=`M0-review-only`；19/19 checks true；唯一 problem=`candidate_representative_limit` |

v3 raw source 是 clean `aebc312f84b97418ba43a59d8b73cb403c53e8b4`，checker source 是另一个 clean `aa71e1a63848715ad78591636a7e4c2dabe88438`。v3 是 candidate capacity negative 的证据，不是 C1 PASS。

## 3. C0/C1 实现身份与冻结边界

| 内容 | commit / 判断 |
|---|---|
| C0 carrier | `f094b6db11c8803882cc8825485d893ebc3c5f59`；metadata/tests implemented，不是 PDE PASS |
| bounded C1 runner | `e58e14f3952b5adb9f57ca5d51dbf9b510cc3f7d`；runner/checker implemented，不是 PDE PASS |
| C1 `np` execution fix | `aebc312f84b97418ba43a59d8b73cb403c53e8b4` |
| checker binding fix | `aa71e1a63848715ad78591636a7e4c2dabe88438` |
| C1 evidence | `3bc541a5a77c02697ea2a34fca1abb5ab0f655a1` |
| M0 test-only fixture | `1c3038e57f0bc28cdd705354d9513c8eb8ce4816` |

C1 的 candidate count Gate 是固定合同；没有因为 C1 失败而放宽为 tolerance merge，也没有原样重跑旧 P1。C1/C2 负结果和 raw/compact 永久保留。

## 4. C1 失败后唯一执行边界：M0 local fixture

Review V10 只允许静态/轻量 M0 设计与 fixture。本轮新增 `test_303_task037_extra_m0_p4_p6_transfer_fixture.py`，没有 production solver/adaptivity 改动。

| 验证项 | 实际结果 |
|---|---|
| production p4→p6 I46 | shape `(882,300)`，`float64`，payload `2,116,800 B` |
| structural interior→trace | observed `1.725758366989246e-14`，fixed `128*np.finfo(float64).eps = 2.842170943040401e-14` |
| orientation/adjoint | full-space 882-row orientation 与 Hermitian adjoint 通过 |
| Floquet phase | edge reverse 与8个 quadrilateral D4 permutation 的 common phase-once 通过 |
| tests | test303 `3 passed`；301–303 `19 passed` |
| static checks | compileall、git diff-check 通过；Ruff unavailable |

这个 fixture 证明的是 cell-local metadata/determinism、full-space orientation、Hermitian adjoint 和生产 edge/face Floquet transform 的 phase-once 关系。它不构造 PETSc global AIJ，不运行 JIT、MPI、GMG、coercive solve 或 PDE。

它不能证明 full-mesh shared-entity conformity、MPI ownership/ghost、p6/h10 resource、global transfer、GMG 或 PDE。真实 full-space MPC owner-local transfer adapter 仍未实现；没有新 review 前不得实现或运行 GMG/PDE。

## 5. 最终目标与依赖链

| 目标/阶段 | 状态 |
|---|---|
| C2 representative factor/transformed solve | `not_run / locked_by_C1` |
| H2B-K normalized two-level coercive solve | `not_run / locked_by_C1/C2` |
| H2D / full-space matrix-free DtN | `not_run / locked_by_H2B-K` |
| H4 time-harmonic PDE | `not_run / locked_by_H2D` |
| official field/RTA | `not_run / locked_by_H4` |
| full PDE RSS/direct authority | `not_measured / not_achieved` |

PDE、full true residual、PDE process-tree RSS、direct-authority physics comparison、field/RTA 均未运行；因此不能把 stage/C1 peak 冒充 PDE peak。当前最多是 M0 local feasibility PASS/no qualification，用户的完整 MPI1 full PDE 目标尚未达成。

后续只能由新 review 定义 actual owner-local full-space MPC transfer 及小网格/MPI Gate。不得自行进入 C2、GMG、H2B-K、H2D 或 PDE。

## 6. Evidence index

### 6.1 C1 raw 与 compact

| evidence | path / SHA256 |
|---|---|
| C1 run1 raw | `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_e58e14f_run1` |
| run1 watchdog | `c1_watchdog_summary.json` `eecc2c4442ef4e80349986c54b4cb3e36141d111b245957d98977e0f76d4fe22`；embedded `201ad3871165a58ae0e91dc5658391338e33406cb829ed5de5b04f15b52ba72f` |
| run1 stage | `stage_summary.json` `7cb20c878212c61955be9ad84c5c2aacbcca56d0ae040cd578e9d0a822a68aa6` |
| run1 progress | `c1_progress.jsonl` `4df3bbe2631b8baabf1a7625b72efe2719bf19ae06a4fc501ef4a7ef15173ba8` |
| run1 timeline | `c1_timeline.jsonl` `f5db4762b5f2667b097fd7144c5084d6e49a981c71bb234c742283453e59bbd1` |
| execution-fix raw | `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_aebc312_execution_fix_run1` |
| execution-fix watchdog | `c1_watchdog_summary.json` `f9bbc9b9f7a35ba8e2c510352b1b6daf9541b8d4329b3efe653bc728fbdc6753`；embedded `763b099af217107b1ea363cee886aeca3018a3d6dcab5904eae3216166a89947` |
| execution-fix summary | `c1_summary.json` `0c4c5d1faec065287508bd26141b276bedbe53d96c0c25e32b9611cf31bdec5d` |
| candidate stop | `c1_candidate_stop.json` `c6161f1ccd5650c91636dcd8a92624a288a125f7a4ffd12cc3a01008606b1ec6` |
| manifest | `c1_manifest.json` `c2588c05082fbc7c30c1c2a308f54befec6c563636ebca2a904c561469b8afd6` |
| execution-fix progress | `c1_progress.jsonl` `68ed36d4fd66b9cdf332af046c1a892b316a7fd3a576f1d1882af81c6ce251ac` |
| execution-fix timeline | `c1_timeline.jsonl` `ef615e60de2a963edf52f7f61fc553661c7308b9236b022fcb269c624e4e4f28` |
| C1 v1 compact | file `21378ee3d6b3adf200597b115fd6fb964f185606f3272eea06cecbf29de348a7`；embedded `ddc9e7182f0b1be71a52be34b2f96b8f99b3d2e440bf5eb65d84576e0456e2ee` |
| C1 v2 compact | file `5a188b4c9f7cd2e3f6a950c4483bb75b1a54374d3e4c4079ca1dbbcbd236522d`；embedded `e32f73afc69e76eb172aa29606a7fb168c5afb4ecf90541ed032c777e7469259` |
| C1 v3 compact | file `2acee2a15ab2f9921bc6c7df6d5b9091e768b30803ca726fd9bed9aab986f956`；embedded `e21b001863471f5709485726423e41dd3a9020c7d6bbe5dd35465a4e526b6fdc` |

### 6.2 其他冻结 authority

| evidence | path / identity |
|---|---|
| V9 history | [response_v9.md](response_v9.md) |
| V10 contract | [review_report_v10.md](review_report_v10.md) |
| S0/P0/P1 old records | 原 records/raw 保持不变，不由本文件重写 |

## 7. Selective boundary

| 组别 | merge 判断 |
|---|---|
| production numerical/core | 不提升；没有新的 PDE evidence，ordinary default unchanged |
| C0/C1 research implementation | research-only；不提升为 production numerical candidate |
| M0 | test-only fixture；不等于 full-space transfer、GMG 或 PDE qualification |
| compact/docs | 可保留为 hash-bound 正负 evidence |
| do-not-merge | candidate-limit negative、未形成的 C2/PDE 路径不得提升为 ordinary default |

本轮没有新 branch、PR 或 master/default 修改。P1 数值/容量负结果不再以 execution-fix 名义重跑；C2 及之后阶段保持锁定。
