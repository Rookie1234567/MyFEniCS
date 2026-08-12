# M1 full-space p4→p6 owner-local transfer收口

## 结论先行

这里的 transfer 是把四阶 N1curl 空间中的一个场表示转换为六阶空间中的表示；adjoint 是在复数内积下按相反方向作用的伴随映射。canonical identity 则不直接比较 MPI 分区中的本地编号，而是按实体、方向和基函数身份生成可跨分区比较的 packet。这样做的目的是区分“同一个物理量只是换了分区”与“数值映射真的不同”。

| 项目 | 记录 |
| --- | --- |
| M1 最终状态 | `NOT_QUALIFIED_FORMAL_BUDGET_EXHAUSTED` |
| 资格结论 | `not_formal_pass`；不是正式 M1 PASS |
| 已用正式预算 | 1 次 initial formal + 1 次 execution-fix formal；余额 0 |
| 最新代码 SHA | `949494c73d1c6ece397471f0f0ccc96f78cc1d79`；该 SHA 尚未正式运行 |
| 运行范围 | p6/h10、MPI1→MPI2、uncondensed full-space |
| 后续阶段 | M2–M6 均 `not_run_by_gate`；不创建伪 PASS outcome/record |
| PDE 目标 | full PDE true residual、direct-authority comparison、process-tree PDE RSS 和 RTA 均未测量；“PDE RSS <2 GB 且物理对照通过”未达成 |

## 固定范围与 Gate

| Gate | 固定合同 | 实际记录 |
| --- | --- | --- |
| MPI1 process-tree RSS | 严格 `<900,000,000 B` | execution-fix `521,723,904 B`，通过；initial `510,328,832 B`，资源值通过但数值路径先停止 |
| MPI2 process-tree RSS | 严格 `<1,300,000,000 B` | execution-fix `974,729,216 B`，通过 |
| swap | `0 B` | 两次 execution-fix phase 均为 `0 B` |
| phase timeout | `1800 s` | 两次正式运行均远低于上限 |
| retained transfer numeric payload（Gate量，含 lazy p6 work Vec） | `<=128,000,000 B` | execution-fix MPI1 `18,244,384 B`、MPI2 `15,574,480 B`，通过；其中基础 retained numeric payload 为 `15,463,552 / 13,976,176 B`，lazy p6 work Vec 为 `2,780,832 / 1,598,304 B` |
| bounded apply workspace | `<=64,000,000 B` | execution-fix MPI1 `3,046,112 B`、MPI2 `1,757,632 B`，通过 |
| scope identity | p4/p6、252 cells、uncondensed full-space、无 global matrix/AIJ、无 KSP/PDE | 两次 raw 均记录为通过/未使用 |
| rows/constraints | p4 `53,084` / `4,124`；p6 `173,802` / `9,210` | 两次正式路径一致；missing/extra/duplicate rows 均为 `0` |

资源 Gate 通过只说明这两次运行没有超过资源上限，不能替代 transfer 数值 Gate，也不能外推为 PDE 峰值。

## 两次正式运行

| 运行 | source / raw | watchdog 与阶段 | 数值与分类 |
| --- | --- | --- | --- |
| initial formal run1 | `ad589ca1e7d473e6ed77827f8bb23410f21c38a9` / `benchmarks/artifacts/task037_extra_development/m1_ad589ca_run1` | watchdog `gate_failed`；MPI1 RC=1；peak `510,328,832 B`；swap=0；进程已退出；MPI2 `not_run_by_gate` | image error `0.31070811280298904`，adjoint error `1.6018790302711856e-17`；旧 affine 本身是低阶、可由 p4 表示，但不满足非平凡 Floquet 边界，因而不是合法 constrained-p4 manufactured fixture；归为 fixture/execution construction failure，不把它当 transfer 科学负结果 |
| execution-fix formal run1 | `caed4dea78e9d9a924e2ad06daba9dd635801e94` / `benchmarks/artifacts/task037_extra_development/m1_caed4dea_execution_fix_run1` | watchdog `pass`；MPI1 RC=0，15.366251135012135 s，peak `521,723,904 B`；MPI2 RC=0，13.284939228993608 s，peak `974,729,216 B`；两阶段 swap=0、进程均退出 | MPI1 image `5.468843900583829e-15`、adjoint `3.1471318267200023e-17`；MPI2 image `5.757606853614202e-15`、adjoint `1.521528936022671e-17`；worker 数值项 finite/deterministic，p6/p4 canonical packet 均形成 |

Execution-fix raw 的独立 checker 结果为 `gate_failed`、`pass=false`、`route=M1-review-only`，15 个 checks 中 14 个为 true，唯一失败是 `canonical_p4_adjoint`。checker 重算的 p6 image canonical relative L2 为 `1.982326002916046e-15`，missing/extra/duplicate 为 `0/0/0`；p4 adjoint canonical relative L2 为 `0.9503885989179789`，max abs 为 `16.50305548580111`，missing/extra/duplicate 仍为 `0/0/0`。因此 M1 没有资格化，且正式预算已耗尽。

## 两处 fixture 缺陷与最小修复

| 缺陷 | 证据 | 修复与边界 |
| --- | --- | --- |
| 初始 source 是旧 affine 场；它低阶、可由 p4 表示，但不满足 required Floquet 边界，因而不是合法 constrained-p4 manufactured fixture | `/tmp/task037_m1_floquet_polynomial_probe.json` 的旧 affine negative control：边界 max abs `33.76939473850167`、relative `1.5286148007984073`；同一 probe 的 qx·qy·c polynomial 边界 max abs `1.1102230246251565e-16`，raw p4→p6 relative `5.102448959291011e-15`，transfer→独立 p6 expected `5.466792763091917e-15` | `caed4dea78e9d9a924e2ad06daba9dd635801e94` 使用 cfg-bound `floquet_compatible_bilinear_p4_v1`；execution-fix image 两个 MPI 均约 `5.5e-15`。这只修正测试对象，不放宽 Gate、不改变 transfer/MPC |
| 初始 dual 由 DOLFINx partition-dependent global dof id 生成，不能作为 MPI1/MPI2 相同物理 dual | `/tmp/task037_m1_dual_partition_diagnostic.json`：global-id dual input relative `0.9091583071292413`，adjoint output relative `0.9503885989179789`；canonical key 映射中 `72,840/164,592 = 44.25488480606591%` 的 global id 不同；cfg-bound manufactured dual input `1.647661415080129e-15`，adjoint output `1.3580087229674401e-15` | `949494c73d1c6ece397471f0f0ccc96f78cc1d79` 删除 global-id dual 路径，改用固定的 `floquet_compatible_degree5_dual_v1` callback。该修复尚未重新 formal，不能写成 M1 PASS，也不消耗或重新获得正式预算 |

这些结果把 execution-fix checker 的 p4 canonical negative 归因到 fixture/provenance 构造，而不是已证实的 transfer/MPC 数值算法失败。独立 MPC diagnostic 还显示 carrier 与 DOLFINx backsubstitution 的 p4/p6 系数误差均为 `0`、master binding mismatch 为 `0`；完整 transfer 与 `C6 P0 C4` 一致，relative error 为 `0`。orientation 假设也没有证据支持：252 个 cell 中 nonzero `cell_info` 为 82，但 current-vs-prescribed max abs 仅 `8.616549110757854e-15`。

## 形式化证据与诊断证据的边界

* **formal measured**：上述两次 raw 中的 rows、constraints、RSS、swap、elapsed、worker image/adjoint、canonical checker 结果；它们分别绑定各自 source SHA 和冻结 raw。
* **diagnostic measured**：四个 `/tmp` diagnostic 中的 source-fixture、MPC commutation、orientation 和 dual partition 结果。它们用于解释正式负结果，不能把未重跑的 `949494c` 结果提升为 formal evidence。
* `m1_fullspace_p4_p6_transfer.json` 保留为真实 checker negative，原字节不变；其 SHA 为 `ad4184d82743a3063d426ad2bd2c2e582c5c3f6f5d8999548cf2d81d704422b0`。新的诊断 compact 状态为 `diagnostic_complete`，qualification 为 `not_formal_pass`，不会覆盖旧 negative。

## 证据索引

| 对象 | 路径 | SHA / 身份 |
| --- | --- | --- |
| initial raw watchdog | `benchmarks/artifacts/task037_extra_development/m1_ad589ca_run1/m1_watchdog_summary.json` | `d9fc27103c8fe4fd3668e0d64e1d46c19235d1ee5b4b4767218e98be42798cb4` |
| initial raw worker | `benchmarks/artifacts/task037_extra_development/m1_ad589ca_run1/mpi1_worker_summary.json` | `b113b7fee27eecdad178fe5d2bd45792def3a621f757e34b032db829f3af203a` |
| execution-fix raw watchdog | `benchmarks/artifacts/task037_extra_development/m1_caed4dea_execution_fix_run1/m1_watchdog_summary.json` | `d9a094debc89e37df93a2b4bbc7a1209aa0d07b96d879907673b7d82dd38a9c0` |
| execution-fix MPI1 worker | `benchmarks/artifacts/task037_extra_development/m1_caed4dea_execution_fix_run1/mpi1_worker_summary.json` | `34905b4ac0985f7815e8adf8e4ccb53aeecf0402ccfe04d8b9b89982b7c6d449` |
| execution-fix MPI2 worker | `benchmarks/artifacts/task037_extra_development/m1_caed4dea_execution_fix_run1/mpi2_worker_summary.json` | `6356337f4fbad871743f781a53a553353da1085a6f534df822637ee73986150c` |
| frozen checker negative | `benchmarks/cases/101_task37_extra_development/records/m1_fullspace_p4_p6_transfer.json` | file SHA `ad4184d82743a3063d426ad2bd2c2e582c5c3f6f5d8999548cf2d81d704422b0`; embedded evidence SHA `a6aebc97116ff7d4baf3280d6d705a5fc420ce4f6be15eb9c2bb7582a921774f` |
| new fixture diagnostics | `benchmarks/cases/101_task37_extra_development/records/m1_fixture_diagnostics.json` | self-bound by its `evidence_sha256` field |
| orientation diagnostic | `/tmp/task037_m1_orientation_diagnostic.json` | `53e7bf5f60faf01657c8fd88626d510adb24c8b8ab6db7534e8ff897eedf1f76` |
| MPC diagnostic | `/tmp/task037_m1_mpc_commutation_diagnostic.json` | `3522def9cf00c532b8fc1a2a3839a7837d0a60f01903da7295ef5bccf6e519e0`; script `1bcb35d36717398aa415009462a0de79ec2474ed0b684de630fb8195b60dbeb1` |
| Floquet polynomial diagnostic | `/tmp/task037_m1_floquet_polynomial_probe.json` | `7cc3f26392b3f485fc2d9d9971db97b609c0cf0ceff113f7d47ab5e7acf7c09d`; script `44025eeee04644e365a6126643b1f8b95ba39e8e6528d8194b1eff2ceb2582a0` |
| dual partition diagnostic | `/tmp/task037_m1_dual_partition_diagnostic.json` | `954d22b4b40a45afc969af59b28cb3da5d170ddd8c74cd254e91f86a0a045af5`; script `ba8900b97ae869001c7e3a05fd09bf6c626b995433f384a3688e0ee14ebb4ca5` |

## 阶段边界

M1 在正式预算耗尽后关闭，不能以 fixture 修复名义第三次运行。M2–M6 均保持 `not_run_by_gate`，没有创建空的 PASS 记录；因此没有 H2B-K、H2D、H4、PDE、field 或 RTA 结果，也没有 full PDE process-tree RSS 与 true residual。当前材料只保留 M1 的真实负证据、诊断解释和未资格化的最新代码状态；不得提升到 ordinary default，也不改变普通路径的数值结论。
