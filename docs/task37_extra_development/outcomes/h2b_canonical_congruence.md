# H2B canonical congruence：C1 受控停止与 M0 轻量边界

本 outcome 记录 Review V10 的 C0/C1 实际证据，以及 C1 关闭后获准执行的 test-only M0 fixture。它不改写 [response_v9.md](../response_v9.md) 及更早历史，也不把研究代码或局部 fixture 解释成 PDE 资格。

## 先看结论

| 阶段 | 实际状态 | 通俗解释 |
|---|---|---|
| C0 canonical metadata carrier | `implemented / tested_only` | 代码能从有限元拓扑、orientation 和 phase metadata 生成可审计的局部 token/T；没有 PDE 结果。 |
| C1 formal run1 | `CONTROLLED_EXECUTION_FAILURE / NOT_QUALIFIED` | 运行到加载 R2 factor 后因一个缺失的 `numpy` 局部导入停止；没有形成 candidate、T 或数值结果。 |
| C1 execution-fix | `CONTROLLED_STOP_CANDIDATE_REPRESENTATIVE_LIMIT / NOT_QUALIFIED` | 84 个 candidate representatives 已超过固定上限32，因此按合同在任何 T、patch、probe、factor 前停止。 |
| C1 checker-only v3 | `gate_failed / pass=false / route=M0-review-only` | 19/19 项证据检查通过，唯一问题是 candidate count；这是可验的容量负结果，不是 C1 PASS。 |
| M0 fixture | `local feasibility PASS / no qualification` | 只验证一个 cell-local p4→p6 transfer 的 metadata、orientation、adjoint 和 phase-once；不验证全网格或 PDE。 |
| C2 / H2B-K / H2D / H4 / PDE | `not_run / locked` | C1 没有全通过，后续 block-factor lane 关闭。 |

用户于 2026-08-12 本轮再次明确授权针对具体执行问题持续分析、窄修和监督推进；该授权不放宽 candidate count、数值、RSS、swap、physics 或 provenance Gate，也不允许把容量或数值负结果包装成 execution-fix。

## 冻结历史结论

| 结论 | 冻结状态 |
|---|---|
| G2 LOR-HX | `G2_FAIL` |
| G3 additive LOR-HX | `prohibited` |
| old G4 sweep | `prohibited` |
| H1R3 | passed |
| V8 fixed-unit H2B | `FAIL_NUMERIC / NOT_QUALIFIED` |
| V9 S0 direction | evidence 可验，但 direction Gate fail |
| P0 | qualified，但只覆盖一个 representative central patch |
| P1 | `CONTROLLED_STOP_UNIQUE_FACTOR_LIMIT / NOT_QUALIFIED` |
| ordinary default | unchanged |

## C0 与 C1 的实际链路

C0 的作用是把“两个局部 patch 可能只是换了 row order 或 unit-modulus phase”变成可审计的 metadata 命题。它不能从 patch 数值反推变换，也不做 tolerance clustering。C1 原本应先形成 84 个 neighborhood candidate orbit，再决定是否有资格继续 patch-only audit；固定代表数上限为32。

| 代码阶段 | commit |
|---|---|
| C0 carrier 与 focused tests | `f094b6db11c8803882cc8825485d893ebc3c5f59` |
| bounded C1 runner/checker | `e58e14f3952b5adb9f57ca5d51dbf9b510cc3f7d` |
| C1 `numpy` scope execution fix | `aebc312f84b97418ba43a59d8b73cb403c53e8b4` |
| C1 cache/provenance checker fix | `aa71e1a63848715ad78591636a7e4c2dabe88438` |
| v3 evidence commit | `3bc541a5a77c02697ea2a34fca1abb5ab0f655a1` |
| M0 test-only fixture | `1c3038e57f0bc28cdd705354d9513c8eb8ce4816` |

这些 commit 只证明实现、测试或证据 checker contract；没有一个把 C1 或 PDE 变成 PASS。

### C1 formal run1：代码 execution failure

| 字段 | measured 值 |
|---|---:|
| source | `e58e14f3952b5adb9f57ca5d51dbf9b510cc3f7d` |
| raw | `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_e58e14f_run1` |
| stage | `24.786440406998736 s`，RC0，peak `1,291,288,576 B`，swap0 |
| C1 | `5.046119430990075 s`，RC1，peak `654,024,704 B`，swap0 |
| termination / cleanup | `termination=null`，`processes_gone_after_c1=true` |
| last progress marker | `r2_factor_load_ready` |

在 `r2_factor_load_ready` 之后，module-level `_c1_cell_metadata` 使用了未在该作用域导入的 `np`，产生 `NameError`。因此 candidate、T、patch、action、factor 均未形成。这是纯 execution failure，不是 numeric fail，也不是 candidate capacity evidence。

v1 compact 保留了当时的 generic `raw_unreadable:FileNotFoundError` 输出，不能被解释为 candidate limit：

| v1 evidence | SHA256 |
|---|---|
| file | `21378ee3d6b3adf200597b115fd6fb964f185606f3272eea06cecbf29de348a7` |
| embedded evidence | `ddc9e7182f0b1be71a52be34b2f96b8f99b3d2e440bf5eb65d84576e0456e2ee` |

### execution-fix formal：candidate count 的受控负结果

修复提交 `aebc312f84b97418ba43a59d8b73cb403c53e8b4` 只修正 `np` scope 并增加 focused coverage；没有改变 action、MPC、patch、numeric Gate 或资源 Gate。这是 Review V10 允许的唯一 C1 execution-fix，随后已耗尽。

| 字段 | measured 值 |
|---|---:|
| source | `aebc312f84b97418ba43a59d8b73cb403c53e8b4` |
| raw | `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_aebc312_execution_fix_run1` |
| stage | `24.819258175004506 s`，RC0，peak `1,281,986,560 B`，swap0 |
| C1 | `61.11731081700418 s`，RC1，peak `690,946,048 B`，swap0 |
| campaign total | `86.13728914600506 s` |
| termination / cleanup | `termination=null`，`processes_gone_after_c1=true` |
| topology closure | `252 cells / 24 classes / 84 neighborhoods / 173802 rows / 882 nloc / 9210 constraints` |
| candidate representatives | `84 > 32` |
| retained orbit metadata | `9,507,553 B <= 16,777,216 B` |
| max live patch matrix | `0` |

`candidate_representative_limit` 在 candidate 阶段立即触发。preflight/T/probe/patch/congruence/action/factorization/factor store 均为 `not_run` 或 `not_formed`；不能把它们写成 numeric fail。所有 materialization flags 均为 false；`fine_space=uncondensed_fullspace`、`condensation=false`，没有 global matrix、global constraint matrix、Schur、slab、KSP、DtN 或 PDE。

所以 C1 结论是 `CONTROLLED_STOP_CANDIDATE_REPRESENTATIVE_LIMIT / NOT_QUALIFIED`，route=`M0-review-only`。C2、H2B-K、H2D、H4、PDE 全部锁定。

## checker-only 收口

v2 是同一 frozen execution-fix raw 的旧 checker 输出。它已读到真实 candidate stop，但 checker 把 `measurement.cache` 错绑到 worker 顶层 cache，造成 `c1_measurement`、manifest、patch audit 和 numeric evidence 的 telemetry false negatives；这不是新的 C1 运行，也没有改变 raw。

`aa71e1a63848715ad78591636a7e4c2dabe88438` 只修正 cache/provenance binding，并保持 raw source 与 checker source 分开、各自 clean。之后在同一 raw 上只运行了一次 checker-only，生成 v3；没有再次启动 C1。

| compact | file SHA | embedded evidence | 结果 |
|---|---|---|---|
| `h2b_canonical_orbit_audit_v1.json` | `21378ee3d6b3adf200597b115fd6fb964f185606f3272eea06cecbf29de348a7` | `ddc9e7182f0b1be71a52be34b2f96b8f99b3d2e440bf5eb65d84576e0456e2ee` | generic raw-unreadable 历史输出 |
| `h2b_canonical_orbit_audit_v2.json` | `5a188b4c9f7cd2e3f6a950c4483bb75b1a54374d3e4c4079ca1dbbcbd236522d` | `e32f73afc69e76eb172aa29606a7fb168c5afb4ecf90541ed032c777e7469259` | candidate stop，但旧 telemetry checks false |
| `h2b_canonical_orbit_audit_v3.json` | `2acee2a15ab2f9921bc6c7df6d5b9091e768b30803ca726fd9bed9aab986f956` | `e21b001863471f5709485726423e41dd3a9020c7d6bbe5dd35465a4e526b6fdc` | RC1 预期；19/19 checks true；唯一 problem=`candidate_representative_limit` |

v3 的 raw source 是 clean `aebc312f84b97418ba43a59d8b73cb403c53e8b4`，checker source 是另一个 clean `aa71e1a63848715ad78591636a7e4c2dabe88438`。v3 是可审核的 C1 capacity negative，不是 C1 algorithm PASS。

## M0 第一边界：只做 local fixture

C1 失败后，Review V10 只允许静态/轻量 M0 fixture。提交 `1c3038e57f0bc28cdd705354d9513c8eb8ce4816` 新增一个 test 文件，没有 production solver/adaptivity 改动。

| fixture 项 | 实际结果 |
|---|---|
| p4→p6 cell-local interpolation | `I46` shape=`(882,300)`，`float64`，payload=`2,116,800 B` |
| structural locality | observed `1.725758366989246e-14`，fixed roundoff limit `128*eps=2.842170943040401e-14` |
| orientation/adjoint | full-space 882-row orientation、复数 Hermitian adjoint 通过 |
| Floquet entity transform | edge reverse、8 个 quadrilateral D4 permutation，共同 phase 只施加一次通过 |
| test evidence | test303 `3 passed`；301–303 `19 passed` |
| static checks | compileall、git diff-check 通过；Ruff unavailable |

fixture 只证明 local metadata/determinism、full-space orientation、Hermitian adjoint 和生产 edge/face Floquet transform 的 phase-once 关系。它没有构造 PETSc global AIJ、JIT、MPI transfer、GMG、coercive solve 或 PDE。

它也不能证明 full-mesh shared-entity conformity、MPI ownership/ghost、p6/h10 resource、global transfer 或 GMG/PDE。真实 full-space MPC owner-local transfer adapter 尚未实现；在没有新 review 前，不实现、不运行 GMG/PDE。

## 最终资格边界

| 目标/阶段 | 状态 |
|---|---|
| C2 representative factor/transformed solve | `not_run / locked_by_C1` |
| H2B-K normalized coercive solve | `not_run / locked_by_C1/C2` |
| H2D / full-space matrix-free DtN | `not_run / locked_by_H2B-K` |
| H4 time-harmonic PDE | `not_run / locked_by_H2D` |
| official field/RTA | `not_run / locked_by_H4` |
| MPI1 full PDE RSS `<2,000,000,000 B`、swap0、direct authority comparison | `not_measured / not achieved` |

PDE、full true residual、PDE process-tree RSS、direct-authority comparison、field/RTA 均未运行。因此不能用 stage 或 C1 peak 冒充 PDE peak。当前最多是 M0 local feasibility PASS，不是 full qualification。后续只能等待新 review 定义 actual owner-local full-space MPC transfer 及其小网格/MPI Gate；不得自行进入 GMG/PDE。

## Evidence index

| evidence | path / SHA256 |
|---|---|
| C1 run1 raw | `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_e58e14f_run1` |
| run1 watchdog | `c1_watchdog_summary.json` `eecc2c4442ef4e80349986c54b4cb3e36141d111b245957d98977e0f76d4fe22`；embedded `201ad3871165a58ae0e91dc5658391338e33406cb829ed5de5b04f15b52ba72f` |
| run1 stage | `stage_summary.json` `7cb20c878212c61955be9ad84c5c2aacbcca56d0ae040cd578e9d0a822a68aa6` |
| run1 progress | `c1_progress.jsonl` `4df3bbe2631b8baabf1a7625b72efe2719bf19ae06a4fc501ef4a7ef15173ba8` |
| run1 timeline | `c1_timeline.jsonl` `f5db4762b5f2667b097fd7144c5084d6e49a981c71bb234c742283453e59bbd1` |
| C1 execution-fix raw | `benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_aebc312_execution_fix_run1` |
| execution-fix watchdog | `c1_watchdog_summary.json` `f9bbc9b9f7a35ba8e2c510352b1b6daf9541b8d4329b3efe653bc728fbdc6753`；embedded `763b099af217107b1ea363cee886aeca3018a3d6dcab5904eae3216166a89947` |
| execution-fix summary | `c1_summary.json` `0c4c5d1faec065287508bd26141b276bedbe53d96c0c25e32b9611cf31bdec5d` |
| candidate stop | `c1_candidate_stop.json` `c6161f1ccd5650c91636dcd8a92624a288a125f7a4ffd12cc3a01008606b1ec6` |
| manifest | `c1_manifest.json` `c2588c05082fbc7c30c1c2a308f54befec6c563636ebca2a904c561469b8afd6` |
| execution-fix progress | `c1_progress.jsonl` `68ed36d4fd66b9cdf332af046c1a892b316a7fd3a576f1d1882af81c6ce251ac` |
| execution-fix timeline | `c1_timeline.jsonl` `ef615e60de2a963edf52f7f61fc553661c7308b9236b022fcb269c624e4e4f28` |
| C1 v1 compact | file `21378ee3d6b3adf200597b115fd6fb964f185606f3272eea06cecbf29de348a7`；embedded `ddc9e7182f0b1be71a52be34b2f96b8f99b3d2e440bf5eb65d84576e0456e2ee` |
| C1 v2 compact | file `5a188b4c9f7cd2e3f6a950c4483bb75b1a54374d3e4c4079ca1dbbcbd236522d`；embedded `e32f73afc69e76eb172aa29606a7fb168c5afb4ecf90541ed032c777e7469259` |
| C1 v3 compact | file `2acee2a15ab2f9921bc6c7df6d5b9091e768b30803ca726fd9bed9aab986f956`；embedded `e21b001863471f5709485726423e41dd3a9020c7d6bbe5dd35465a4e526b6fdc` |
| implementation/evidence commits | C0 `f094b6db11c8803882cc8825485d893ebc3c5f59`; runner `e58e14f3952b5adb9f57ca5d51dbf9b510cc3f7d`; fix `aebc312f84b97418ba43a59d8b73cb403c53e8b4`; checker `aa71e1a63848715ad78591636a7e4c2dabe88438`; evidence `3bc541a5a77c02697ea2a34fca1abb5ab0f655a1`; M0 `1c3038e57f0bc28cdd705354d9513c8eb8ce4816` |

## Selective boundary

| 分组 | 结论 |
|---|---|
| production numerical/core | 不提升；没有新的 PDE evidence，ordinary default unchanged |
| C0/C1 research code | research-only；不进入 ordinary default |
| M0 | test-only local fixture；不等于 transfer/GMG/PDE qualification |
| compact/docs | 保留正负 hash-bound evidence，旧 evidence 不覆盖 |
| do-not-merge | C1 candidate-limit negative、未形成的 C2/PDE 路径不得提升为 production |

本轮没有创建新 branch/PR，也没有修改 master/default。后续阶段必须由新的 review 定义 actual full-space owner-local MPC transfer 及其资源/小网格 Gate。
