# Task37 Extra Development V11 收口响应

## 授权与结论

用户明确授权原文为：“我允许你继续正式运行，不用管v11里的限制，继续执行任务”。据此，用户授权越过 V11 的正式运行次数限制、M2→M3 阶段锁和 84 个完整 882D packed factor 限制，并现已明确授权继续 M4–M6 正式研究。该授权不放宽 full-space、数值、RSS `<2,000,000,000 B`、swap=0、true residual `<=1e-6`、physics 或 provenance Gate，也不允许把容量或数值负结果包装成 execution-fix。

| 项目 | 当前结论 |
| --- | --- |
| working branch | `codex/20260806-task37-iterative-extra-development` |
| latest code/source before this response | `404f6c6a5326219bcf6aca098b332b68214781a3`（M3Y formal source；本次文档提交前的 clean code SHA） |
| previous M1 closeout source | `cc0573ba34cee13b1eb3b8dc8e51ac7e7cbe0dfc`（承接 `949494c...` 的历史文档/代码提交） |
| M1 formal source 1 | `ad589ca1e7d473e6ed77827f8bb23410f21c38a9` |
| M1 execution-fix formal source | `caed4dea78e9d9a924e2ad06daba9dd635801e94` |
| M1 latest dual-fixture fix | `949494c73d1c6ece397471f0f0ccc96f78cc1d79`；已由当前 v2 formal/checker 资格化 |
| M3Y code chain | `12777a724...` → `b8afa94...` → `404f6c6a...` |
| formal budget | 原 V11 次数限制由用户本轮明确授权忽略；其余 Gate 全部保留 |
| M1 最终状态 | `PASS / QUALIFIED`（v2 checker 15/15） |
| M2 最终状态 | `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`；checkerboard source 超过 `0.70` |
| M3Y packed full-store | `PASS / QUALIFIED`（明确授权的 research-only lane） |
| M4–M6 | `not_run_yet`；已获用户授权继续正式研究 |
| docs commit | `this_response_commit (exact SHA reported in final handoff)` |

历史 execution-fix raw 的 p4 canonical adjoint 曾失败；随后用户授权继续 formal-count 范围内的正式研究。M1 v2 仍是正式 `PASS / QUALIFIED`，M2 high-complement oracle 的 checkerboard source 触发正式数值 Gate 失败，因此 M2 为 `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`。在该失败之后，用户又明确授权执行独立的 M3Y packed-store research lane；M3Y checker 正式通过，但不改变 M2 结论，也不代表 PDE 目标通过。所有结论均不放宽数值、容量、RSS、swap 或 provenance Gate。

## 继承的冻结结论

以下结论沿用 V9/V10，不在本响应中重算或弱化：G2=`G2_FAIL`；G3 additive LOR-HX=`prohibited`；old G4=`prohibited`；H1R3 系列已通过；V8 fixed-unit H2B 为 numeric fail；V9 S0 direction 为 fail；P0 只资格化了代表性 representative；C1 canonical lane 曾因 candidate/capacity Gate 受控停止。ordinary default 未改变，research-only 路径不提升为 production。

## M1 正式运行与 checker

| 运行 | 实测结果 | 资源/身份 | 结论 |
| --- | --- | --- | --- |
| initial formal run1 | source `ad589ca...`；MPI1 image `0.31070811280298904`，adjoint `1.6018790302711856e-17`；MPI2 未运行 | MPI1 peak `510,328,832 B`，swap=0，进程退出；worker RC=1 | 旧 affine 本身低阶、可由 p4 表示，但不满足非平凡 Floquet 边界，因而不是合法 constrained-p4 manufactured fixture；归类为 fixture/execution construction failure，不把 image 值当 transfer 科学负结果 |
| execution-fix formal run1 | source `caed4dea...`；MPI1 image `5.468843900583829e-15`、adjoint `3.1471318267200023e-17`；MPI2 image `5.757606853614202e-15`、adjoint `1.521528936022671e-17`；两边 finite/deterministic | MPI1 peak `521,723,904 B`，MPI2 peak `974,729,216 B`，swap=0，RC=0，进程均退出；p4/p6 rows `53,084/173,802`，constraints `4,124/9,210` | worker 的 p6 image 和普通数值 Gate通过，但 checker 重算 p4 canonical adjoint relative L2=`0.9503885989179789`，故 M1 `gate_failed` |

历史 execution-fix checker 的冻结 record 为 `status=gate_failed`、`pass=false`，15 项 checks 中 14 项为 true；该负结果永久保留。当前 v2 checker 为 `status=pass`、`pass=true`、`problems=[]`，15/15 checks true；p6 canonical relative L2=`1.982326002916046e-15`，p4 canonical adjoint relative L2=`1.3580087229674401e-15`，missing/extra/duplicate 全部 `0/0/0`。

当前 v2 运行的资源为 MPI1 peak `521,449,472 B`、MPI2 peak `953,028,608 B`、swap=0、processes_gone=true；retained transfer payload 为 `18,244,384 / 15,574,480 B`，bounded workspace 为 `3,046,112 / 1,757,632 B`。raw source 与 checker source 均 clean、均为 `cc0573ba34cee13b1eb3b8dc8e51ac7e7cbe0dfc`。

## M2 正式运行、checker 与数值边界

M2 的通俗含义是：把一个完整的 882 维局部 patch 分成低阶 300 维部分和高阶 582 维补空间，只对高阶补空间保存一个 factor，检查它能否把五类固定 source 的 patch residual 降到要求。它不是全局 PDE solve，也没有物化 global matrix、Schur、slab factor 或 KSP。

| 项目 | 实测结果 |
| --- | --- |
| formal source | `b4c1c6c76d667dac78e5dc384b302026379cb8d2` |
| raw | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1` |
| watchdog | `PASS`；stage/online worker `RC=0` |
| checker | `RC=1`；`status=gate_failed`；`problems=["source_gate"]` |
| stage | peak `1,296,175,104 B`，swap `0`，RC0 |
| online | peak `848,654,336 B`，swap `0`，RC0 |
| scope | 252 cells、173,802 rows、9,210 constraints、central `3`/class `3`/touching `19` |
| split | `rank(QL)=300`、`rank(QH)=582`；Q orthogonality `9.257892486599041e-16`；split reconstruction `9.637068547580966e-16` |
| factor | values+pivots `5,421,912 B`；factor residual `5.725553567915199e-16`；solve residual `6.773813153765502e-13` |
| retained transform | `12,446,784 B` |

| source | low/high energy | formal rho | action closure | 结论 |
| --- | ---: | ---: | ---: | --- |
| gradient-dominated | `0.7476937969517845 / 0.25230620304821527` | `0.6501331033379294` | `3.731727295429185e-14` | PASS |
| curl-dominated | `0.6568811348518978 / 0.34311886514810186` | `0.5370997972508667` | `4.765947835467422e-14` | PASS |
| mixed | `0.7350021241367845 / 0.26499787586321516` | `0.6350618866926864` | `3.9933950843220025e-14` | PASS |
| checkerboard/high-frequency | `0.6666666666666659 / 0.3333333333333332` | **`0.7319752447810908`** | `1.1012012738647016e-13` | **FAIL，超过 `0.70`** |
| physical-RHS-like | `0.6338129814899229 / 0.3661870185100772` | `0.5038880312320936` | `4.8627220733002086e-14` | PASS |

因此 M2 的正式分类是 `FORMAL_NUMERIC_FAIL`，不是 timeout、JIT、API、RSS、swap 或 resource failure。compact 的机器字段仍保留 `status=gate_failed`、`pass=false`、`problems=["source_gate"]`；这里的 source Gate 失败由 checkerboard 的实际 `rho` 触发，不能改写为 PASS。

## M2 固定离线诊断边界

两份 `/tmp` 诊断均为 `BEST_CASE_DIAGNOSTIC_ONLY / not_formal_pass`，没有改变正式 M2 FAIL：

| 固定结构 | checkerboard 结果 |
| --- | ---: |
| row-complete low→high | `0.7365588632365486` |
| fixed A directions 的 joint2 least-squares | `0.7314868062038236` |
| fixed three-action symmetric LHL | `0.7318570005704766` |
| exact patch inverse sanity | `2.1656111107723205e-12` |

这些结果排除了“只补 low 阶段即可恢复 M2”的解释；这些旧离线诊断本身不构成 M3Y 资格，资格来自本轮正式 raw/checker。M3Y 已由用户越过阶段锁后正式通过；M4–M6 已获授权继续但当前仍为 `not_run_yet`，H2B-K、H2D、H4、PDE、RTA 和 full PDE process-tree RSS 仍为 `not_run_yet`/`not_measured`。

## 两个 fixture/provenance 缺陷

### 1. source fixture

初始 formal 使用的 affine source 本身低阶、可由 p4 表示，但其 Floquet 边界不成立，因而不是合法 constrained-p4 manufactured fixture。诊断中旧 affine negative control 的边界 max abs 为 `33.76939473850167`、relative 为 `1.5286148007984073`。改用 cfg-bound 的 `qx*qy*c` 低阶多项式后，边界 max abs=`1.1102230246251565e-16`，raw p4→p6 relative=`5.102448959291011e-15`，transfer→独立 p6 expected relative=`5.466792763091917e-15`。这一窄修复落在 `caed4dea78e9d9a924e2ad06daba9dd635801e94`，没有放宽任何 Gate 或改变 transfer/MPC。

### 2. dual fixture

execution-fix 之前的 dual 使用 DOLFINx global dof id 生成值；global numbering 会随 MPI partition 改变。诊断中相同 canonical keys 的 global id 有 `72,840/164,592` 不同，即 `44.25488480606591%`；旧 dual input canonical relative=`0.9091583071292413`，旧 adjoint output relative=`0.9503885989179789`。改为 cfg-bound、固定的 `floquet_compatible_degree5_dual_v1` 后，manufactured dual input relative=`1.647661415080129e-15`，manufactured adjoint output relative=`1.3580087229674401e-15`，missing/extra/duplicate 均为 `0/0/0`。修复 commit 为 `949494c73d1c6ece397471f0f0ccc96f78cc1d79`；该修复已在 `cc0573b` clean source 的 M1 v2 formal/checker 中正式通过并资格化，同时保留旧 negative formal evidence。

### 诊断边界

orientation diagnostic 中 252 个 cell 有 82 个 nonzero `cell_info`，但 current-vs-prescribed max abs=`8.616549110757854e-15`，因此没有证据支持 orientation 是根因。MPC commutation diagnostic 显示 carrier 与 DOLFINx lift 的 p4/p6 系数误差均为 `0`、master binding mismatch 为 `0`，且完整 transfer 与 `C6 P0 C4` 的 relative error 为 `0`。这些诊断解释了已观测的失败路径，但不能把未正式运行的最新 code 变成资格化结果。

## 实现与测试收口

本次收口文档阶段未再改代码、不改旧 checker、不启动任何 formal/checker/MPI/PDE。本轮代码修复提交明确为：`caed4dea78e9d9a924e2ad06daba9dd635801e94`（source fixture）和 `949494c73d1c6ece397471f0f0ccc96f78cc1d79`（dual fixture）。最终代码变化后运行的 focused 验证如下；这些是实现回归，不构成 M1 qualification。

| 验证 | 实际命令 | 结果 |
| --- | --- | --- |
| `test305` | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_305_task037_extra_m1_harness.py` | `12 passed` |
| `test304` MPI1 | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_304_task037_extra_p_split_owner_transfer.py` | `6 passed, 1 skipped` |
| `test304` MPI2 | `source scripts/activate_myfenics_wsl.sh && mpiexec -n 2 python -m pytest -q src/test/test_304_task037_extra_p_split_owner_transfer.py` | 每个 rank `6 passed, 1 skipped` |
| `test303 + test227` | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_303_task037_extra_m0_p4_p6_transfer_fixture.py src/test/test_227_task037_canonical_vector_artifacts.py` | `6 passed, 2 skipped` |
| `compileall` | `source scripts/activate_myfenics_wsl.sh && python -m compileall -q benchmarks/canonical_vector_artifacts.py benchmarks/run_task037_extra_m.py src/solvers/hcurl_canonical_vector_dolfinx.py src/solvers/hcurl_p_split_owner_transfer.py src/test/test_304_task037_extra_p_split_owner_transfer.py src/test/test_305_task037_extra_m1_harness.py` | pass |
| `git diff --check` | `git --git-dir=.git-codex --work-tree=. diff --check` | pass |
| full repository pytest | 未运行 | `not_run` |

`949494c...` 的边界是“dual fixture 已改为 partition-independent”，不是“formal M1 已通过”。

旧 formal raw 目录和旧 negative record 永久保留；`m1_fullspace_p4_p6_transfer.json` 原字节保留，file SHA 为 `ad4184d82743a3063d426ad2bd2c2e582c5c3f6f5d8999548cf2d81d704422b0`，其 status 仍为 `gate_failed`，不能改写为 pass。当前新增 v2 compact file SHA 为 `6ed2c394fc0e04ed1222024bb1cc89281d6c77ac9be28e07451312906107cf72`，embedded evidence SHA 为 `2820715b3d30d54ee7af9169884b4cf562fbb969c0be31bb2238304366cf56ba`。

## M3Y packed row-complete factor store

M3Y 的通俗含义是：对每个 882 行完整局部 patch，不长期保存一个 882×882 方阵 factor，而只保存其 lower packed complex128 Cholesky 三角因子；fresh loader 用 mmap 和三角 solve 读取它，packed action 由 checker 独立重算。它解决的是 84 个局部 factor 的存储问题，不是把局部证据变成全局 PDE 结果。

| 项目 | 正式结果 |
| --- | --- |
| 授权与边界 | 用户明确授权越过 V11 的 M2→M3 锁和 84-factor 研究禁令；M2 `FORMAL_NUMERIC_FAIL` 保持不变，其他 Gate 未放宽 |
| fixed scope | degree=6、`h_nm=10.0`、MPI1、252 cells、24 classes、84 neighborhoods、173802 global rows、882 local rows、9210 constraints |
| source / checker | `404f6c6a5326219bcf6aca098b332b68214781a3` / 同一 clean SHA |
| formal raw / compact | `benchmarks/artifacts/task037_extra_development/m3y_404f6c6_run1` / `benchmarks/cases/101_task37_extra_development/records/m3y_full_packed_patch_store.json` |
| final status | `M3Y PASS / QUALIFIED`，仅指本 research-only packed-store lane |

| Gate | 限值 | 实测 |
| --- | ---: | ---: |
| isolated JIT stage RSS | `<1,800,000,000 B` | `1,280,749,568 B` |
| builder RSS | `<1,800,000,000 B` | `1,068,343,296 B` |
| fresh loader RSS | `<1,050,000,000 B` | `575,459,328 B` |
| swap / cleanup | `0 B` / process gone | `0 B` / `true` |
| factors / packed bytes | `<=96` / formula `882*883/2*16` | `84` / `523,357,632 B` |
| metadata/mapping / retained total | retained `<=560,000,000 B` | `1,838,930 B` / `525,196,562 B`，PASS |
| max action closure / solve residual | `<=1e-11` | `8.402445013054496e-12` / `8.402445013054496e-12`，PASS |
| predicted builder/online live set | `<=1,750,000,000 B` | `1,346,005,004 B`，`predicted`，不是实测 |

builder 对 84 个 row-complete patch 流式生成 packed factor，抽样 neighborhood `0/41/83` 的重复 matrix/factor SHA 一致；全部 84 个 factor 的 solve/action 均记录为 finite、deterministic。loader 对 factor 文件做 read-only mmap 和 solve，checker 独立重算 packed action。`full_dense_factor_count=0`、`pivots=false`、patch/global matrix、global constraint matrix、Schur、static condensation、trace slab、QL/QH transform 和 per-cell factor 均为 `false`。独立 `m3y-check` 返回 RC0，compact 的 20/20 checks 为 `true`，`problems=[]`。

M3Y 代码提交链为 `12777a72497a98576bcb8caa15d58b13a0c837c0`（初始实现）、`b8afa94dd93fca3336660c1e78c52021843acf92`（checker/resource 收紧）和 `404f6c6a5326219bcf6aca098b332b68214781a3`（最终 packed BLAS action 修正）。正式前轻量验证为 `39 passed`，compileall、AST duplicate-key 和 diff-check 均通过；Ruff 不可用。该 PASS 不等价于 PDE qualification，也不改变 ordinary default。

## 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| initial raw | `benchmarks/artifacts/task037_extra_development/m1_ad589ca_run1`；watchdog `d9fc27103c8fe4fd3668e0d64e1d46c19235d1ee5b4b4767218e98be42798cb4` |
| execution-fix raw | `benchmarks/artifacts/task037_extra_development/m1_caed4dea_execution_fix_run1`；watchdog `d9a094debc89e37df93a2b4bbc7a1209aa0d07b96d879907673b7d82dd38a9c0` |
| frozen checker negative | `benchmarks/cases/101_task37_extra_development/records/m1_fullspace_p4_p6_transfer.json`；file SHA `ad4184d82743a3063d426ad2bd2c2e582c5c3f6f5d8999548cf2d81d704422b0`；embedded evidence SHA `a6aebc97116ff7d4baf3280d6d705a5fc420ce4f6be15eb9c2bb7582a921774f` |
| current v2 checker | `benchmarks/cases/101_task37_extra_development/records/m1_fullspace_p4_p6_transfer_v2.json`；file SHA `6ed2c394fc0e04ed1222024bb1cc89281d6c77ac9be28e07451312906107cf72`；embedded evidence SHA `2820715b3d30d54ee7af9169884b4cf562fbb969c0be31bb2238304366cf56ba` |
| current v2 raw watchdog | `benchmarks/artifacts/task037_extra_development/m1_cc0573b_qualification_run1/m1_watchdog_summary.json`；SHA `7ffa3c129a7938d4a9a34787b6709c62ba6fec950a236df2a46dfb25b3725389` |
| fixture diagnostics compact | `benchmarks/cases/101_task37_extra_development/records/m1_fixture_diagnostics.json`；由 `evidence_sha256` 自绑定 |
| source fixture diagnostic | `/tmp/task037_m1_floquet_polynomial_probe.json` SHA `7cc3f26392b3f485fc2d9d9971db97b609c0cf0ceff113f7d47ab5e7acf7c09d`；script SHA `44025eeee04644e365a6126643b1f8b95ba39e8e6528d8194b1eff2ceb2582a0` |
| MPC diagnostic | `/tmp/task037_m1_mpc_commutation_diagnostic.json` SHA `3522def9cf00c532b8fc1a2a3839a7837d0a60f01903da7295ef5bccf6e519e0`；script SHA `1bcb35d36717398aa415009462a0de79ec2474ed0b684de630fb8195b60dbeb1` |
| orientation diagnostic | `/tmp/task037_m1_orientation_diagnostic.json` SHA `53e7bf5f60faf01657c8fd88626d510adb24c8b8ab6db7534e8ff897eedf1f76`；临时 JSON 未嵌入 source/script SHA，compact 已标明该 provenance 限制 |
| dual partition diagnostic | `/tmp/task037_m1_dual_partition_diagnostic.json` SHA `954d22b4b40a45afc969af59b28cb3da5d170ddd8c74cd254e91f86a0a045af5`；script SHA `ba8900b97ae869001c7e3a05fd09bf6c626b995433f384a3688e0ee14ebb4ca5` |
| M3Y raw / watchdog | `benchmarks/artifacts/task037_extra_development/m3y_404f6c6_run1`；`m3y_watchdog_summary.json` SHA `bd364d928a45fda15f49c8890c76ea6a59029b6320221cc7ec546b73f32fdeb8` |
| M3Y stage / builder / loader summaries | `stage_summary.json` `250e61783bf97ceb9a74fde8bf52910ad7d4f7d609fdfff852f098a6f814204c`；`m3y_builder_summary.json` `d0d7d3a80384994b3415dc41ac3e1b816c35b6ff0682fd3ad8384bb3a8fcb652`；`m3y_loader_summary.json` `eece84bb7250a80967665a0d63aef91dc9a0bd34366f69e2f506200a1e30ab82` |
| M3Y progress / timeline | builder `5676e6074bdb0a219cc7f96c26ea03071d74b2885e7481cb3633743f8d7aa2af` / `213d8dc29598b3487f2278b684a09eb4174f2f8791dcfe00acaa339f59714512`；loader `da0a2c7aeb10f406357d486af76c6dbc9f89b266dea712044b7f70c732cca2f1` / `80c29993fe52821ec2711c6b1d52e45027289a81f6f8b4b656fc02713410c1a6` |
| M3Y stage progress / timeline / manifest | `1648701c75611f180a0c7d7444584ff25f63f815742f21cbc4a45ed19fe8a60d` / `3d79487825b847a7fd23f67d485c995c0874ff5b1389b1909577913bbcdc0b0a` / manifest `949c04da123ccf1e0014a301f617e3a9509b9aaed365793948c469e12feade17` |
| M3Y compact | `benchmarks/cases/101_task37_extra_development/records/m3y_full_packed_patch_store.json`；file SHA `f40d6e27c628b946f9ff735027e966cd192748322aa29f752f27ebc4daeab979`；embedded evidence SHA `605cb0c19e4e7c49d0304474b1e6844d2047f78abca8d20e7692ba524de5b241` |
| M2 final raw worker | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1/m2_worker_summary.json`；SHA `3db16f4d2709c9839bbdec88366c0f740da1f7cd871981992c71c758adc74f73` |
| M2 final raw watchdog | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1/m2_watchdog_summary.json`；SHA `bad3879a32d11434caf2bb5d4c235b05a91ffd7c210a4add496be958fd6d7425` |
| M2 final raw form reuse | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1/m2_form_reuse.json`；SHA `7f90385c16534e79c81df8b36103c2ddfe52c6afcc7759ef9ec493e2fd1c27e9` |
| M2 v2 compact | `benchmarks/cases/101_task37_extra_development/records/m2_high_complement_patch_oracle_v2.json`；file SHA `ebd512aa0e4b6823d5d95c5f816cc6e898c9fd97392af4f7346c83ba3ac4e31f`；embedded evidence SHA `59e0af2e187be4bc593db25a81b5c685fdbbeac5d45633687ae35863a12843a5` |
| M2 initial negative compact | `benchmarks/cases/101_task37_extra_development/records/m2_high_complement_patch_oracle.json`；SHA `bfb59f5b2f0c75e1863a78cd58bb951f2b3dbd30a7f3b2bd4526f8c77ae57023` |
| M2 BEST_CASE diagnostics | first JSON SHA `7d5e511377801efd4473ae795a6a09ab9394adcf39527d4f799d5dfd6afcde52`；coupled JSON SHA `ad900db41005e3540e4c3088b59145e5991290a71f3e8ca76667c267f9f3485e`；coupled script SHA `e74f8528c25eda0e86acb8754c7705fffb1c7bcb103d59f117fbfa52713ef5fc` |

## 未运行项与硬停止

M1 v2 已通过；M2 已完成正式运行但因 checkerboard 数值 Gate 失败而 `NOT_QUALIFIED`。用户随后明确越过 M2→M3 阶段锁并授权 M3Y，因此 M3Y 已正式通过；H2B-K、H2D、H4、M4–M6、PDE、official field/RTA、full true residual、direct-authority physics comparison 和 PDE process-tree RSS 仍为 `not_run_yet`/`not_measured`。尚不能声称达成 MPI1 full PDE RSS 严格小于 2,000,000,000 B、swap=0 且直接法物理对照通过的最终目标。

M2 数值 Gate 失败仍保持原始负结论；用户之后的明确授权已开启 M3Y 以及后续 M4–M6 正式研究，但这些后续阶段当前仍未运行，不改变 M2。M1/M2 compact、所有早期执行失败 raw、M2 BEST_CASE 诊断和 M3Y raw/compact 均保留；没有新分支、PR、master/default 修改。研究代码和历史负结果保留，ordinary default 不变。
