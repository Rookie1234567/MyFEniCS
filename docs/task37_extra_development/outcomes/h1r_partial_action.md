# H1R partial action：C 路径的局部资格结论

本文件聚焦 H1R.1 的 C 路径。它回答的是“单个 affine hexa cell 上，能否直接产生局部 residual 而不在每次作用中生成 `nloc × nloc` dense tensor”，不是正式 p6/h10 求解器资格，也不是 H2 解锁。本轮在 clean `04030436b16050016d4b8ec37f30bf6bac56a144` 上运行了一次且仅一次 Review V3 fixed H1R.1 p2/p3/p4/p6 microbenchmark；checker 修复后没有重跑 measurement。

## 结论

| 项目 | 结果 |
|---|---|
| fixture | `MPI.COMM_SELF`，单 affine hexa，p2/p3/p4/p6 |
| C backend | `dolfinx.fem.assemble_vector(existing ndarray, rank-one form)` |
| relative error | 全部 `<=1.4617639397633573e-15` |
| finite/deterministic | 四阶均 PASS |
| dense tensor per apply | `false` |
| global matrix | `false` |
| 最大 retained exact-class payload | `28224 B` |
| p6 A/C speedup | `3808.9300325837494x` |
| H1R.1 | `PASS` |
| H1R.2 | `NOT_RUN` |

## 计算路径

rank-one UFL action 可以通俗理解为：把输入系数写入一个有限元 coefficient，重新 pack 当前系数，然后直接由线性形式产生输出向量。C 的 repeated apply 每次都更新并 pack coefficient，再调用 rank-one kernel；它不调用 global PETSc matrix，不保留 `nloc × nloc` cell tensor。

| 步骤 | C 路径 |
|---|---|
| 输入 | 当前 local coefficient values |
| 更新 | 写入 coefficient Function，并按现有 local action 约定准备输出 |
| pack | 每次 apply fresh pack，固定 `apply_count=5` |
| action | `dolfinx.fem.assemble_vector(existing ndarray, rank-one form)` |
| 输出 | 预分配 local residual ndarray |
| retained inventory | coefficient local array、output buffer、constants；不计 Python header 和 borrowed form/mesh |

每个阶次的 packed shapes 都是 `[[1,nloc],[0,nloc]]`。`[0,nloc]` 表示空积分域中的 zero-extent packed array，元素数为 0；它不是一个稠密二维 cell matrix。对应的 entries/bytes closure 如下：

| p | nloc | packed entries | packed bytes | per-apply temporary bytes | retained payload |
|---:|---:|---:|---:|---:|---:|
| 2 | 54 | 54 | 864 | 864 | 1728 |
| 3 | 144 | 144 | 2304 | 2304 | 4608 |
| 4 | 300 | 300 | 4800 | 4800 | 9600 |
| 6 | 882 | 882 | 14112 | 14112 | 28224 |

## 精确 raw 结果

| p | setup(s) | first apply(s) | median(s) | relative error | A/C speedup |
|---:|---:|---:|---:|---:|---:|
| 2 | 0.007889422005973756 | 0.00027473492082208395 | 0.00007066805846989155 | 1.0448732588064883e-15 | 116.75987259362738x |
| 3 | 0.004713600035756826 | 0.00041074701584875584 | 0.00017496757209300995 | 6.510716434423364e-16 | 664.4962184622345x |
| 4 | 4.697555392980576 | 0.0009075960842892528 | 0.0005751060671173036 | 1.4617639397633573e-15 | 1437.3906471164132x |
| 6 | 48.40854476997629 | 0.007405082928016782 | 0.005264257488306612 | 1.3489283709986367e-15 | 3808.9300325837494x |

C 的 raw inventory 在四阶均为 `form_rank=1`、`coefficient_count=1`、`finite=true`、`deterministic=true`、`dense_cell_tensor_materialized_per_apply=false`、`retained_dense_cell_tensor_count=0`、`cell_tensor_scratch_count=0`、`global_matrix_materialized=false`。

## A/B 的边界

A 的 p6 median apply 是 `20.05118844646495 s`；tabulation、orientation、GEMV 分别是 `20.045995232474525 s`、`0.004321829997934401 s`、`0.000869196024723351 s`。B 的 p6 median 是 `0.0007399940514005721 s`，但 B 预先保留了 `12446784 B` 的 exact-class dense tensor。因此 B 必须保持 `diagnostic_only=true`、`h_refinement_scalability=not_claimed`、`eligible_for_H2=false`；B 的改善不能替代 C，也不能被外推为 scalable action。

## Evidence 与资格边界

| 项目 | 路径/值 |
|---|---|
| raw | [`h1r_cell_action_microbenchmark.json`](../../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_microbenchmark.json) |
| raw evidence SHA256 | `0caf43c1b1f8b1fe6eb502b13ca0c22f59f76b81d09d11f33e4845f196c9bc6b` |
| compact requalification | [`h1r_cell_action_qualification_recheck.json`](../../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_qualification_recheck.json) |
| compact evidence SHA256 | `13417fc293a2ad3641b36e7e3bf05f4ae5e205d8a0947b8b42ed1f8b83b1d7ca` |
| measurement source | `04030436b16050016d4b8ec37f30bf6bac56a144` |
| final checker | `b5796726e388d6a0be168ed19f93d4f0e8199b45` |

### Provenance

| 项目 | 值 |
|---|---|
| branch | `codex/20260806-task37-iterative-extra-development` |
| exact fixed command | `python -m benchmarks.run_task037_extra_h1r run --output benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_microbenchmark.json` |
| qualified Python | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |
| environment | PETSc complex128/int32；DOLFINx 0.10.0.post2；Basix 0.10.0；FFCx 0.10.1.post0；UFL 2025.2.1 |
| threads | `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`NUMEXPR_NUM_THREADS=1` |
| source / defaults | raw start/end 同为 `04030436b16050016d4b8ec37f30bf6bac56a144` 且 clean；ordinary default unchanged；未新增依赖 |

当前仓库 `.venv` 解析到记录中的 `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv` qualified target；qualified marker/complex ABI 已通过，因此不是 Windows/ABI 混用或异常。

raw 内嵌的旧 `gate_failed` 和四个 `c_packed_shapes` 没有被修改；requalification 只用最终 checker 重新解释 zero-extent shape，得到 `pass/problems=[]`。本证据不包含 MPI2、正式 p6/h10 H1R.2、PDE/KSP、official field/RTA、H2-H4 或 LOR/shift 扫描；`MPI1_memory_target_evaluated=false` 的语义是 `NOT_EVALUATED`，用户提出的 MPI1 `<2 GB` 目标尚未测量/达成。Review V3 hard Gate 是 completed process-tree peak `<=1.25 GiB`，为更严格的资格 authority。

## 测试状态

最终 focused suite 覆盖 test276–279，结果为 `32 passed in 1.60s`；两个 runner、C backend 和四个 tests 的 compileall 通过，git diff-check 通过；Ruff unavailable，未安装依赖。C 的 p4/p6 setup 含 form compile/setup 成本，Gate 仍只比较 repeated apply。
