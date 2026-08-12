# Task37 Extra Development V11 收口响应

## 授权与结论

用户已明确授权：针对具体执行问题持续研究、定位、做窄修并在监督边界内推进；本轮又明确授权忽略 Review V11 的“1 formal campaign + 1 execution-fix rerun”次数限制，继续进行本次版本化 M1 formal qualification。该授权只覆盖 formal-count 限制，不放宽任何数值、candidate-count、RSS、swap、physics 或 provenance Gate，不允许把容量或数值负结果包装成 execution-fix，也不允许越过 Review V11 的架构与阶段 Gate。

| 项目 | 当前结论 |
| --- | --- |
| working branch | `codex/20260806-task37-iterative-extra-development` |
| latest pushed source | `cc0573ba34cee13b1eb3b8dc8e51ac7e7cbe0dfc`（代码内容承接 `949494c...`，本提交含 V11 closeout docs） |
| M1 formal source 1 | `ad589ca1e7d473e6ed77827f8bb23410f21c38a9` |
| M1 execution-fix formal source | `caed4dea78e9d9a924e2ad06daba9dd635801e94` |
| M1 latest dual-fixture fix | `949494c73d1c6ece397471f0f0ccc96f78cc1d79`；已由当前 v2 formal/checker 资格化 |
| formal budget | 原 V11 次数限制由用户本轮明确授权忽略；其余 Gate 全部保留 |
| M1 最终状态 | `PASS / QUALIFIED`（v2 checker 15/15） |
| M2–M6 | 当前尚未运行；M1 evidence 提交后按 V11 进入 M2 |
| docs commit | `this_response_commit (exact SHA reported in final handoff)` |

历史 execution-fix raw 的 p4 canonical adjoint 曾失败；本轮用户授权只解除 formal-count 限制后，当前 source 使用已修复 dual fixture，v2 checker 独立重算全部 Gate 并通过。因此当前 M1 为正式 `PASS / QUALIFIED`；该结论不放宽任何数值、容量、RSS、swap 或 provenance Gate。

## 继承的冻结结论

以下结论沿用 V9/V10，不在本响应中重算或弱化：G2=`G2_FAIL`；G3 additive LOR-HX=`prohibited`；old G4=`prohibited`；H1R3 系列已通过；V8 fixed-unit H2B 为 numeric fail；V9 S0 direction 为 fail；P0 只资格化了代表性 representative；C1 canonical lane 曾因 candidate/capacity Gate 受控停止。ordinary default 未改变，research-only 路径不提升为 production。

## M1 正式运行与 checker

| 运行 | 实测结果 | 资源/身份 | 结论 |
| --- | --- | --- | --- |
| initial formal run1 | source `ad589ca...`；MPI1 image `0.31070811280298904`，adjoint `1.6018790302711856e-17`；MPI2 未运行 | MPI1 peak `510,328,832 B`，swap=0，进程退出；worker RC=1 | 旧 affine 本身低阶、可由 p4 表示，但不满足非平凡 Floquet 边界，因而不是合法 constrained-p4 manufactured fixture；归类为 fixture/execution construction failure，不把 image 值当 transfer 科学负结果 |
| execution-fix formal run1 | source `caed4dea...`；MPI1 image `5.468843900583829e-15`、adjoint `3.1471318267200023e-17`；MPI2 image `5.757606853614202e-15`、adjoint `1.521528936022671e-17`；两边 finite/deterministic | MPI1 peak `521,723,904 B`，MPI2 peak `974,729,216 B`，swap=0，RC=0，进程均退出；p4/p6 rows `53,084/173,802`，constraints `4,124/9,210` | worker 的 p6 image 和普通数值 Gate通过，但 checker 重算 p4 canonical adjoint relative L2=`0.9503885989179789`，故 M1 `gate_failed` |

历史 execution-fix checker 的冻结 record 为 `status=gate_failed`、`pass=false`，15 项 checks 中 14 项为 true；该负结果永久保留。当前 v2 checker 为 `status=pass`、`pass=true`、`problems=[]`，15/15 checks true；p6 canonical relative L2=`1.982326002916046e-15`，p4 canonical adjoint relative L2=`1.3580087229674401e-15`，missing/extra/duplicate 全部 `0/0/0`。

当前 v2 运行的资源为 MPI1 peak `521,449,472 B`、MPI2 peak `953,028,608 B`、swap=0、processes_gone=true；retained transfer payload 为 `18,244,384 / 15,574,480 B`，bounded workspace 为 `3,046,112 / 1,757,632 B`。raw source 与 checker source 均 clean、均为 `cc0573ba34cee13b1eb3b8dc8e51ac7e7cbe0dfc`。

## 两个 fixture/provenance 缺陷

### 1. source fixture

初始 formal 使用的 affine source 本身低阶、可由 p4 表示，但其 Floquet 边界不成立，因而不是合法 constrained-p4 manufactured fixture。诊断中旧 affine negative control 的边界 max abs 为 `33.76939473850167`、relative 为 `1.5286148007984073`。改用 cfg-bound 的 `qx*qy*c` 低阶多项式后，边界 max abs=`1.1102230246251565e-16`，raw p4→p6 relative=`5.102448959291011e-15`，transfer→独立 p6 expected relative=`5.466792763091917e-15`。这一窄修复落在 `caed4dea78e9d9a924e2ad06daba9dd635801e94`，没有放宽任何 Gate 或改变 transfer/MPC。

### 2. dual fixture

execution-fix 之前的 dual 使用 DOLFINx global dof id 生成值；global numbering 会随 MPI partition 改变。诊断中相同 canonical keys 的 global id 有 `72,840/164,592` 不同，即 `44.25488480606591%`；旧 dual input canonical relative=`0.9091583071292413`，旧 adjoint output relative=`0.9503885989179789`。改为 cfg-bound、固定的 `floquet_compatible_degree5_dual_v1` 后，manufactured dual input relative=`1.647661415080129e-15`，manufactured adjoint output relative=`1.3580087229674401e-15`，missing/extra/duplicate 均为 `0/0/0`。修复 commit 为 `949494c73d1c6ece397471f0f0ccc96f78cc1d79`；它尚未正式运行，不能取代已冻结的 negative formal evidence。

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

## 未运行项与硬停止

当前 M1 v2 已通过，下一阶段是 M2；M2 尚未启动，H2B-K、H2D、H4、PDE、official field/RTA、full true residual、direct-authority physics comparison 和 PDE process-tree RSS 仍为 `not_run_by_gate`/`not_measured`。因此尚不能声称达成 MPI1 full PDE RSS 严格小于 2,000,000,000 B、swap=0 且直接法物理对照通过的最终目标。

M2–M6 在各自 Gate 前不创建伪 PASS 记录；当前仅 M1 v2 已产生正式 compact。没有新分支、PR、master/default 修改。研究代码和历史负结果保留，ordinary default 不变。
