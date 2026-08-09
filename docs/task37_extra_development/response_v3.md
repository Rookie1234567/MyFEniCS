# Task037-extra Response V3：H1R action kernel diagnostic

本 response 是 Review V3 的 H1R.0/H1R.1 consolidated 记录。本轮在 clean `04030436b16050016d4b8ec37f30bf6bac56a144` 上运行了一次且仅一次 Review V3 fixed H1R.1 p2/p3/p4/p6 microbenchmark；checker 修复后没有重跑 measurement。没有运行的是 H1R.2、MPI2、PDE、H2-H4；raw measurement 未修改。

## 状态总表

| 范围 | 状态 | 边界 |
|---|---|---|
| G2 LOR-HX | `G2_FAIL` | 不重开、不扫描 |
| G3 additive LOR-HX | `prohibited` | 保持冻结 |
| 旧 G4 sweep | `prohibited` | 保持冻结 |
| H0 | `ACCEPTED_CAPABILITY_ONLY` | 不是数值资格 |
| H1.1 | `PASS` | p2/p3 tiny fixture |
| 旧 H1.2 | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED` | 1800 s raw 无 completed summary |
| H1R.0 | `PASS` | marker/flush focused contract |
| H1R.1 | `PASS` | 单元级 MPI.COMM_SELF diagnostic |
| H1R.2 | `NOT_RUN` | 需下一次 review 授权 |
| H2/H3/H4 | `LOCKED` | 不因 H1R.1 解锁 |

`H1R.1_PASS` 不是 H1 overall qualified，也不是进入 H2 的授权。它只说明固定单 cell/class Gate 通过。

## Review V3 六问

### 1. 旧 1800 s 运行的阶段分布能否被准确观测？

旧 1800s raw 不能被准确追溯拆分；H1R.0 只让未来运行可观测。它在 mesh、function space、Floquet MPC、form compile、candidate/reference build、每个 source 的 interpolation/reference apply/candidate apply 1/2/canonical export 以及 worker summary 前后写入立即 flush 的 JSONL marker。每条 marker 记录 schema、elapsed wall、rank、可用 RSS/PSS/USS、source label、apply count、cell count、local/global rows；未知字段为 `null`。

但本轮没有原样重跑旧 H1.2 的 1800 s worker，旧 raw 也没有这些阶段 marker，所以不能事后拆分旧 timeout 的 setup/reference/candidate/canonical 时间。

### 2. 当前 A 路径中 tabulation、orientation、GEMV 各占多少？

A 每次重建并定向完整 dense local tensor 后 GEMV。精确 raw median 如下：

| p | nloc | A setup(s) | A first(s) | A median(s) | tabulation(s) | orientation(s) | GEMV(s) | retained/touched(B) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 54 | 0.0000033369287848472595 | 0.00823377096094191 | 0.008251193503383547 | 0.008180072996765375 | 0.00004850846016779542 | 0.000016510486602783203 | 46656 / 281664 |
| 3 | 144 | 0.0000025909394025802612 | 0.11476325092371553 | 0.11626529000932351 | 0.11612569203134626 | 0.000093046051915735 | 0.00003393151564523578 | 331776 / 1995264 |
| 4 | 300 | 0.000003990018740296364 | 0.8226485629566014 | 0.8266520819743164 | 0.8261634309310466 | 0.00028098904294893146 | 0.00009491195669397712 | 1440000 / 8649600 |
| 6 | 882 | 0.00002297293394804001 | 19.933682644041255 | 20.05118844646495 | 20.045995232474525 | 0.004321829997934401 | 0.000869196024723351 | 12446784 / 74708928 |

p6 的 tabulation 约占 A median 的 `99.9741%`，说明 dense tensor 重建是主要成本。C 的 p4/p6 setup 含 form compile/setup 成本；A/C speedup Gate 只比较 repeated apply median，不隐藏 setup，也不把 setup 纳入 speedup。

### 3. B 改善多少，为什么不能作为 scalable path？

B setup 时缓存一次 exact-class dense tensor，重复 apply 只 GEMV：

| p | B setup(s) | B first(s) | B median(s) | retained(B) |
|---:|---:|---:|---:|---:|
| 2 | 0.008588992990553379 | 0.000027796020731329918 | 0.000004692526999861002 | 46656 |
| 3 | 0.10740622400771827 | 0.000018937978893518448 | 0.00001647550379857421 | 331776 |
| 4 | 0.8279413939453661 | 0.00007424294017255306 | 0.00007172551704570651 | 1440000 |
| 6 | 20.571481373975985 | 0.0009732820326462388 | 0.0007399940514005721 | 12446784 |

p6 A/B median 约 `27096` 倍，但 B 以 `diagnostic_only=true`、`h_refinement_scalability=not_claimed`、`eligible_for_H2=false` 为冻结边界。它只是分离 tabulation/orientation 与 GEMV 成本，不能掩盖 dense class tensor 的保留，也不能替代 direct partial action。

### 4. 是否成功实现 C？

是，在单 affine hexa cell/class 上实现并通过了 direct rank-one UFL action。它把输入写入 coefficient，fresh pack 当前系数，再直接用 `dolfinx.fem.assemble_vector(existing ndarray, rank-one form)` 产生 residual；不生成每次 apply 的 `nloc × nloc` tensor，也不组装 global matrix。

### 5. C 的误差、时间和 retained bytes 是什么？

| p | nloc | C setup(s) | C first(s) | C median(s) | error | retained payload(B) | packed temporary(B) | A/C |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 54 | 0.007889422005973756 | 0.00027473492082208395 | 0.00007066805846989155 | 1.0448732588064883e-15 | 1728 | 864 | 116.75987259362738x |
| 3 | 144 | 0.004713600035756826 | 0.00041074701584875584 | 0.00017496757209300995 | 6.510716434423364e-16 | 4608 | 2304 | 664.4962184622345x |
| 4 | 300 | 4.697555392980576 | 0.0009075960842892528 | 0.0005751060671173036 | 1.4617639397633573e-15 | 9600 | 4800 | 1437.3906471164132x |
| 6 | 882 | 48.40854476997629 | 0.007405082928016782 | 0.005264257488306612 | 1.3489283709986367e-15 | 28224 | 14112 | 3808.9300325837494x |

所有 C packed shapes 为 `[[1,nloc],[0,nloc]]`；`[0,nloc]` 是空积分域的 zero-extent packed array，元素数为 0，不是 dense tensor。p6 retained payload 为 `28224 B`，packed temporary 为 `14112 B`。

### 6. 是否具备进入 H1R.2 的资格？

最终 checker 在 b5796726 上从 raw 字段重算得到 `pass=true`、`problems=[]`、`eligible_for_H1R2=true`，且 p6 A/C 为 `3808.9300325837494x`。因此它具备提出 H1R.2 的单元诊断前置条件，但 H1R.2 本轮明确 `NOT_RUN`，不由 Codex 自动启动。仍须下一次 review 决定是否进行正式 p6/h10 单 source action-only Gate。

### Provenance

| 项目 | 值 |
|---|---|
| branch | `codex/20260806-task37-iterative-extra-development` |
| raw source start/end | `04030436b16050016d4b8ec37f30bf6bac56a144`，两端 clean |
| exact fixed command | `python -m benchmarks.run_task037_extra_h1r run --output benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_microbenchmark.json` |
| qualified Python | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |
| PETSc | ScalarType `complex128`，IntType `int32` |
| versions | DOLFINx `0.10.0.post2`；Basix `0.10.0`；FFCx `0.10.1.post0`；UFL `2025.2.1` |
| threads | `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`NUMEXPR_NUM_THREADS=1` |
| ordinary default / dependencies | ordinary default unchanged；未新增依赖 |

当前仓库 `.venv` 解析到记录中的 `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv` qualified target；qualified marker/complex ABI 已通过，因此不是 Windows/ABI 混用或异常。

## Gate 与 incident disposition

| Gate | 结果 |
|---|---|
| C error `<=1e-11` | PASS，最大 `1.4617639397633573e-15` |
| finite/deterministic | PASS，四阶均 true |
| no dense per apply/global matrix | PASS |
| p6 C `<0.25*A` | PASS |
| retained payload `<=16 MiB` | PASS，p6 `28224 B` |

首次 raw 由 source SHA `04030436b16050016d4b8ec37f30bf6bac56a144` 生成，raw evidence SHA 为 `0caf43c1b1f8b1fe6eb502b13ca0c22f59f76b81d09d11f33e4845f196c9bc6b`。raw 内嵌 `gate_failed` 和四个 `c_packed_shapes` 没有被改写；最终 checker SHA `b5796726e388d6a0be168ed19f93d4f0e8199b45` 修正了 zero-extent 的非负维度语义，requalification record 的 evidence SHA 为 `13417fc293a2ad3641b36e7e3bf05f4ae5e205d8a0947b8b42ed1f8b83b1d7ca`，fresh recomputation 为 `pass/problems=[]`。本次是 checker 假阴性修复，不是 measurement rerun。

## 代码、证据和测试索引

| 类别 | 索引 |
|---|---|
| H1R.0/H1R runner | [`run_task037_extra_candidate_h.py`](../../benchmarks/run_task037_extra_candidate_h.py) |
| H1R.1 runner | [`run_task037_extra_h1r.py`](../../benchmarks/run_task037_extra_h1r.py) |
| C backend | [`hcurl_rank_one_form_action.py`](../../src/solvers/hcurl_rank_one_form_action.py) |
| marker test | [`test277`](../../src/test/test_277_task037_extra_candidate_h_progress.py) |
| A/B/C contract test | [`test278`](../../src/test/test_278_task037_extra_p6_cell_action_microbenchmark_contract.py) |
| partial action test | [`test279`](../../src/test/test_279_task037_extra_partial_action.py) |
| raw measurement | [`h1r_cell_action_microbenchmark.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_microbenchmark.json) |
| compact requalification | [`h1r_cell_action_qualification_recheck.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_qualification_recheck.json) |

最终 focused suite 命令覆盖 test276–279，结果为 `32 passed in 1.60s`；两个 runner、C backend 和四个 tests 的 compileall 通过，git diff-check 通过；Ruff unavailable，未安装依赖。此前 implementation/checker 的历史证据分别为 test276–279 `32 passed`、test278+279 `27 passed`。C 的 p4/p6 setup 含 form compile/setup 成本，Gate 只比较 repeated apply。

## 未运行项与下一步

本轮没有 MPI2、正式 p6/h10 H1R.2、PDE/KSP、official field/RTA、H2/H3/H4，也没有 LOR/shift 扫描。字段 `MPI1_memory_target_evaluated=false` 的语义是 `NOT_EVALUATED`；用户提出的 MPI1 `<2 GB` 目标尚未测量/达成。Review V3 hard Gate 是 completed process-tree peak `<=1.25 GiB`，它是更严格的资格 authority。即使 H1R.1 通过，也不建议进入 H2 或 master merge；下一步必须等待 review 对 H1R.2 的明确授权。
