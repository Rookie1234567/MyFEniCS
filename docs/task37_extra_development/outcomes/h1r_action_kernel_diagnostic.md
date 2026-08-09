# H1R action kernel diagnostic：单元 action 微基准

本记录只描述 Review V3 授权的 H1R.0/H1R.1 单元诊断。这里的“action”是把一个有限元输入向量送入局部 Maxwell 双线性形式并得到局部输出向量；它不是求解器、预条件器或 PDE 结果。本轮在 clean `04030436b16050016d4b8ec37f30bf6bac56a144` 上运行了一次且仅一次 Review V3 fixed H1R.1 p2/p3/p4/p6 microbenchmark；checker 修复后没有重跑 measurement。

## 结论与冻结边界

| 范围 | 当前结论 | 说明 |
|---|---|---|
| G2 LOR-HX | `G2_FAIL` | 不重开、不扫描 |
| G3 additive LOR-HX | `prohibited` | 保持 Review V1/V2 决定 |
| 旧 G4 sweep | `prohibited` | 不因 H1R 改变 |
| H0 | `ACCEPTED_CAPABILITY_ONLY` | 仅 capability/API 审计 |
| H1.1 | `PASS` | p2/p3 tiny full-space action 与 dual identity |
| 旧 H1.2 | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED` | 1800 s 正式 action-only 运行未写出 summary |
| H1R.0 | `PASS` | marker/flush focused contract 已通过 |
| H1R.1 | `PASS` | 仅为 MPI.COMM_SELF 单 affine hexa 单元诊断 |
| H1R.2 | `NOT_RUN` | 仍需下一次 review 明确授权 |
| H2/H3/H4 | `LOCKED` | 未运行、不可由本记录解锁 |

H1R.1 的 `eligible_for_H1R2=true` 只表示这个固定单元 Gate 的 evaluator 通过；它不表示 H1 overall qualified，也不表示已经批准 p6/h10、MPI2 或 H2。

## 1. H1R.0：阶段 marker 与可观测性

阶段 marker 在耗时调用前写出 `started` 并立即 flush，在调用正常返回后写出 `ready` 并立即 flush。当前实现覆盖以下边界：

| 阶段 | 事件 |
|---|---|
| 构建 | `mesh_build_started/ready`、`function_space_started/ready`、`floquet_mpc_started/ready`、`form_compile_started/ready`、`candidate_build_started/ready`、`reference_build_started/ready` |
| 每个 source | `source_interpolation_started/ready`、`reference_apply_started/ready`、`candidate_apply_1_started/ready`、`candidate_apply_2_started/ready`、`canonical_export_started/ready` |
| 收尾 | `worker_summary_started/ready` |

每条 JSONL event 固定记录窄 schema、worker 起点后的 elapsed wall seconds、rank、可取得的 RSS/PSS/USS、source label、apply count、cell count、local rows 和 global rows；未知量写 `null`，不伪造为零。事件由 `benchmarks/run_task037_extra_candidate_h.py` 发出，focused 合同由 [`test277`](../../../src/test/test_277_task037_extra_candidate_h_progress.py) 覆盖。

本轮没有原样重跑旧的 1800 s H1.2 worker，因此不能从旧 timeout raw 追溯拆出各阶段耗时。未来正式运行可利用这些立即 flush marker 区分 setup、reference apply、candidate 两次 apply 和 canonical export。

## 2. 数据身份与 evidence

| 项目 | 值 |
|---|---|
| measurement source SHA | `04030436b16050016d4b8ec37f30bf6bac56a144` |
| raw measurement | [`h1r_cell_action_microbenchmark.json`](../../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_microbenchmark.json) |
| raw evidence SHA256 | `0caf43c1b1f8b1fe6eb502b13ca0c22f59f76b81d09d11f33e4845f196c9bc6b` |
| requalification record | [`h1r_cell_action_qualification_recheck.json`](../../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_qualification_recheck.json) |
| requalification evidence SHA256 | `13417fc293a2ad3641b36e7e3bf05f4ae5e205d8a0947b8b42ed1f8b83b1d7ca` |
| final checker SHA | `b5796726e388d6a0be168ed19f93d4f0e8199b45` |
| measurement reused | `true` |
| measurement fields modified | `false` |
| communicator | `MPI.COMM_SELF`, MPI size 1 |
| degrees/repeats | p2/p3/p4/p6，`REPEATS=4` |

raw 内嵌 qualification 保留了原始 `gate_failed` 及四个 `c_packed_shapes` 问题；它没有被静默改写。最终 checker 在 b5796726 上按 zero-extent packed array 语义重新计算为 `pass`、`problems=[]`。

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

## 3. A/B dense-cell diagnostic

A 是当前路径的诊断：每次 apply 都重新 tabulate 一个完整 dense `nloc × nloc` cell tensor，重新做 orientation，再执行 dense GEMV；只复用一个 scratch，不长期按 cell 保存矩阵。B 在 setup 时对同一 exact class 生成并定向一次 dense tensor，重复 apply 只做 GEMV。

### A：每次重建 tensor

时间单位为秒；retained/touched 为 raw 中的字节口径。

| p | nloc | setup | first apply | median apply | median tabulation | median orientation | median GEMV | retained B | touched B |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 54 | 0.0000033369287848472595 | 0.00823377096094191 | 0.008251193503383547 | 0.008180072996765375 | 0.00004850846016779542 | 0.000016510486602783203 | 46656 | 281664 |
| 3 | 144 | 0.0000025909394025802612 | 0.11476325092371553 | 0.11626529000932351 | 0.11612569203134626 | 0.000093046051915735 | 0.00003393151564523578 | 331776 | 1995264 |
| 4 | 300 | 0.000003990018740296364 | 0.8226485629566014 | 0.8266520819743164 | 0.8261634309310466 | 0.00028098904294893146 | 0.00009491195669397712 | 1440000 | 8649600 |
| 6 | 882 | 0.00002297293394804001 | 19.933682644041255 | 20.05118844646495 | 20.045995232474525 | 0.004321829997934401 | 0.000869196024723351 | 12446784 | 74708928 |

p6 的 A median 为 `20.05118844646495 s`，其中 tabulation 为 `20.045995232474525 s`，约占 `99.9741%`；orientation 为 `0.004321829997934401 s`，GEMV 为 `0.000869196024723351 s`。这直接显示当前瓶颈是每次完整 tensor 生成，而不是 GEMV。

### B：exact-class cached dense diagnostic

| p | setup | first apply | median apply | retained B | diagnostic flags |
|---:|---:|---:|---:|---:|---|
| 2 | 0.008588992990553379 | 0.000027796020731329918 | 0.000004692526999861002 | 46656 | `diagnostic_only=true` |
| 3 | 0.10740622400771827 | 0.000018937978893518448 | 0.00001647550379857421 | 331776 | `diagnostic_only=true` |
| 4 | 0.8279413939453661 | 0.00007424294017255306 | 0.00007172551704570651 | 1440000 | `diagnostic_only=true` |
| 6 | 20.571481373975985 | 0.0009732820326462388 | 0.0007399940514005721 | 12446784 | `diagnostic_only=true` |

B 的全部 raw 标记为 `diagnostic_only=true`、`h_refinement_scalability=not_claimed`、`eligible_for_H2=false`。p6 A/B median 约 `27096` 倍，但这是把一个 12.45 MB dense class tensor 预先保留后的时间分解，不能作为 scalable candidate，也不能补偿 C 的资格。

## 4. C：direct rank-one UFL action

rank-one action 的通俗含义是：把当前输入写进一个 coefficient，重新 pack 当前 coefficient，然后直接调用 rank-one UFL linear form 生成局部 residual vector；它不生成 `nloc × nloc` dense tensor，也不组装 global matrix。

| p | nloc | setup | first apply | median apply | relative error | retained payload B | packed temporary B | A/C speedup |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 54 | 0.007889422005973756 | 0.00027473492082208395 | 0.00007066805846989155 | 1.0448732588064883e-15 | 1728 | 864 | 116.75987259362738x |
| 3 | 144 | 0.004713600035756826 | 0.00041074701584875584 | 0.00017496757209300995 | 6.510716434423364e-16 | 4608 | 2304 | 664.4962184622345x |
| 4 | 300 | 4.697555392980576 | 0.0009075960842892528 | 0.0005751060671173036 | 1.4617639397633573e-15 | 9600 | 4800 | 1437.3906471164132x |
| 6 | 882 | 48.40854476997629 | 0.007405082928016782 | 0.005264257488306612 | 1.3489283709986367e-15 | 28224 | 14112 | 3808.9300325837494x |

每阶 C 的 packed shapes 都是 `[[1,nloc],[0,nloc]]`。第二个 block 是没有本地 cell 的空积分域，元素数为 0，不是 dense tensor。每阶 `packed_entries=nloc`，且 `entries × 16 = packed_bytes = per_apply_bounded_temporary_bytes`。

C raw 的结构字段为 `form_rank=1`、`coefficient_count=1`、`apply_count=5`、`global_matrix_materialized=false`、`dense_cell_tensor_materialized_per_apply=false`、`retained_dense_cell_tensor_count=0`、`cell_tensor_scratch_count=0`；四阶均 finite/deterministic。

C 的 p4/p6 `setup_seconds` 包含 form compile/setup 成本；H1R.1 的 A/C speedup Gate 只比较 repeated apply median，不隐藏 setup，也不把 setup 纳入 speedup。

## 5. H1R.1 Gate disposition

| Gate | raw/recomputed evidence | 结论 |
|---|---|---|
| C relative error `<=1e-11` | 四阶最大值为 `1.4617639397633573e-15` | PASS |
| C finite and deterministic | 四阶均为 `true` | PASS |
| per-apply 不生成 dense cell tensor | dense per apply=false，retained dense=0，scratch=0，global matrix=false | PASS |
| p6 C median `<0.25*A median` | `0.005264257488306612 < 0.25 × 20.05118844646495` | PASS |
| exact-class retained payload `<=16 MiB` | p6 最大为 `28224 B` | PASS |

因此本单元诊断分类为 `H1R.1_PASS`，最终 evaluator 为 `pass=true`、`eligible_for_H1R2=true`。这不是正式 p6/h10 或 H1 overall qualification；H1R.2 本轮 `NOT_RUN`，必须等待下一次 review 授权。

## 6. 测试与不可外推项

最终 focused suite：`source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_276_task037_extra_candidate_h_runner.py src/test/test_277_task037_extra_candidate_h_progress.py src/test/test_278_task037_extra_p6_cell_action_microbenchmark_contract.py src/test/test_279_task037_extra_partial_action.py`，结果为 `32 passed in 1.60s`。两个 runner、C backend 和四个 tests 的 compileall 通过，git diff-check 通过；Ruff unavailable，未安装依赖。implementation/checker 的历史证据分别为 test276–279 `32 passed`、test278+279 `27 passed`。

本证据只覆盖 MPI.COMM_SELF 单 affine hexa 单 cell/class。没有 MPI2、正式 p6/h10 H1R.2、PDE/KSP、official field/RTA、H2/H3/H4，也没有 LOR/shift 参数扫描。字段 `MPI1_memory_target_evaluated=false` 的语义是 `NOT_EVALUATED`；用户提出的 MPI1 `<2 GB` 目标尚未测量/达成。若后续授权 H1R.2，Review V3 的更严格资格 authority 是 completed process-tree peak `<=1.25 GiB`，二者不能混称。
