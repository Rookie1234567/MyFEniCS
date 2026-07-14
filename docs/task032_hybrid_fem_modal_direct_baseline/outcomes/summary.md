# Task032 滚动结果总结

## 1. local migration and branch identity

```text
task = Task032
status = phase0_complete / phase1_full3d_reference_complete / phase2_cross_section_qep_complete / phase3_mode_basis_complete / phase4_stable_propagation_complete / task_in_progress
base and Task031 merge = dae03170b0cdd87f2d72769aea7ce04e32acce2b
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
old directory = read-only historical baseline
new directory = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
origin = Rookie1234567/MyFEniCS
ordinary default changed = false
```

详细证据见 `local_migration_record.md`。新库从 Task031 clean merge 后的远程 `master` 克隆，Task032 分支已推送；旧目录未修改。

## 2. frozen physical model

已按任务书冻结：13.5 nm、当前验证 Si、规则双周期结构、主点 10° 掠角/phi=0/S、局部 3D p2 Nédélec、MPI4、direct only。材料扰动、多波长、h/p、自适应迭代法、实验噪声与反演不在 Task032 范围。

## 3. theory-to-code mapping

前置理论和 Task031 交接链已全部读取。Phase 0 完成环境与旧能力迁移；Phase 1 已加入显式、默认关闭的 full-3D 参考面导出，并建立 Case080 配置、命令、records 和 checker。Phase 2 已实现 `matching cross-section -> mixed QEP -> distributed PEP`；Phase 3 已实现 `Poynting classification -> adjoint QEP -> biorthogonal blocks -> overlap tracking`；Phase 4 已完成稳定 two-port propagation 和 clean MPI4 formal record。接口 coupling 与 Hybrid solvers 尚未开始。

## 4. eigenproblem implementation and validation

```text
implementation = passed in serial/MPI4 tests and clean formal benchmark
space = transverse N1curl(p2) x longitudinal Lagrange(p2)
polynomial = K0 + beta*K1 + beta^2*K2
solver = SLEPc 3.24 PEP/TOAR + shift-invert MUMPS
ownership = distributed reduced/full vectors; no rank0 full gather
clean formal record = benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/qep_phase2.json
formal source commit = 33211a4ac6d4f6717351197a93c506e1adec609f
record SHA-256 = 8743ab4bfe95b1e532069f6eb643996ea60d2009ad267c3f0e78cbc430003cd1
```

二维截面复用 Stage4 三维 hexa 网格的 x/y 轴，并支持 homogeneous air、homogeneous lossy Si 和当前 air/Si `epsilon(x,y)`。双 Floquet 约束只复制周期边界规模元数据，显式构造分布式 `u=Cq`，矩阵通过 `C^H K C` 稀疏约化。MPI4 测试覆盖 Bloch phase、Nedelec orientation、无 slave-chain、解析复 beta、正反向配对、残差、归一化和 ownership。

clean formal MPI4 记录包含 air h5/h3/h2/h1.5、homogeneous lossy h2 与当前 `epsilon(x,y)` h3 六个 case。air 正向基模 beta 依次为 `0.0569516267`、`0.0763028564`、`0.0799092656`、`0.0804520941 1/nm`，相对解析误差严格下降为 `29.5323%`、`5.58859%`、`1.12629%`、`0.454640%`。h5 的大误差来自 10° 掠入射下 `beta^2=k^2-k_t^2` 对横向色散高度敏感，不能拿 h5 单点否定 QEP 符号。

lossy h2 得到 `beta=0.0773232064+0.00511171935j 1/nm`，相对解析误差 `1.19656%`；当前 Stage4 x/y 材料 h3 得到 `0.0753551902+0.00178364869j 1/nm`。所有选中模态最大多项式相对残差 `1.8177e-15`，最大 electric-L2 范数误差 `4.44e-16`，最大 `+/- beta` 配对误差 `7.50e-16`，orientation probe 与周期配对坐标 Gate 均通过。Case080 checker 为 `277/277 passed`。

## 5. mode classification/normalization

```text
implementation = serial/MPI4 tests and clean formal benchmark passed
direction = cross-section Poynting flux first; Im(beta) decay branch fallback
left modes = explicit distributed adjoint QEP at lambda approximately conj(beta)
normalization = unit-absolute-Poynting right mode + Q'(beta) left/right basis
near degeneracy = small block inverse with condition fail-closed
tracking = maximum left/right overlap + principal-angle subspace report
clean formal record = benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/modes_phase3.json
formal source commit = 72dca66b70515bcf6ccef239005afa43028df72b
record SHA-256 = 10f2737c51a9506f2cbb73d98c5b0d6ec2747e180ceb8ccef4680ad1e46fdea8
```

SLEPc 3.24 PEP 的 Python API 不提供 two-sided left vectors，因此 Phase 3 显式求解 `K0^H + lambda K1^H + lambda^2 K2^H`，不把普通右模 Euclidean 正交冒充双正交。研究 MPI4 h10 runner 对 air、homogeneous lossy 和当前 Stage4 `epsilon(x,y)` 均通过；air/有损双正交单位阵误差约 `1e-15`，patterned 为 `2.51e-10`，左右 beta 配对约 `1e-14`，右/左 QEP 残差均远小于 `1e-8`。air 正反 beta 配对误差约 `5e-16`，所有选中分支通过被动性方向规则。

回归结果为全量 serial `190 tests / 10 skipped`、Phase 3 serial `4/4`，以及 MPI4 Phase 3 每 rank `4 tests / 2 skipped`；MPI skip 仅用于避免重复负向和相邻参数 factor setup，完整 MPI4 runner 仍覆盖这些路径。

80° 到 79.8° 的 tracking 对两维近简并子空间得到 singular values `0.9999929/0.9999825`，最大 principal angle `0.005918 rad`，无未匹配旧模；serial 合同另覆盖模式数增加时的 unmatched 新模。当前 h10 是分类/归一化合同，不替代 Phase 2 beta 精度或最终 h3 Hybrid 对比。clean formal record 固定在 `72dca66...`，Case080 checker 加入五类 Phase 3 Gate 后为 `282/282 passed`。

## 6. stable propagation

`clean_mpi4_formal_record_pass`。新增 two-port
scattering 表示，正向用 `exp(+i beta+ L)` 从 bottom 到 top，反向用
`exp(-i beta- L)` 从 top 到 bottom；不保存 growing inverse，也不形成普通
transfer matrix。100 nm air/lossy/current-patterned 模式、37+63 nm composition、
无界面反射、reciprocity/passivity、强衰减安全下溢和增长/ambiguous 负对照的
8 个 runner Gate 全通过，MPI4 四个 rank 的记录签名一致。

```text
formal source commit = 9206e9c964db387448551cdefdc88081ef705441
clean formal record = benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/propagation_phase4.json
record SHA-256 = 808fd6991de0ace38f1e582d09d7d1f3b20d131fc5a9cc4cf96708719caf37f9
Phase 3 record SHA-256 = 10f2737c51a9506f2cbb73d98c5b0d6ec2747e180ceb8ccef4680ad1e46fdea8
```

air 的 independently solved 正反 basis 得到 reciprocity beta/factor 最大误差
`3.63e-16/2.78e-15`；三个 case 的 reflection norm 均为 0，composition 最大误差
`9.42e-16`。air/lossy/current-patterned 最大 factor magnitude 分别约
`1.000/0.620/0.853`；强衰减 `exp(-1000)` 安全下溢为 0。Case080 新增四类
Phase 4 Gate 后为 `286/286 passed`。接口 coupling 尚未加入。

回归口径为完整 serial `196 tests / 10 skipped`、Phase 3+4 真实模式集成
`10/10`、Phase 4 单元合同 `6/6` 和正式 MPI4 runner `8/8` Gates。

## 7. interface projection

`not_started`。第一版使用匹配网格，并要求 trace round trip、orientation 与 projection residual。

## 8. augmented direct result

`not_started`。

## 9. modal-Schur result

`not_started`；必须在 augmented direct 通过后开始。

## 10. truncation convergence

`not_started`。

## 11. full-3D comparison

Phase 1 已从 clean commit `c468c728...` 完成 h5/h3 MPI4 direct reference。两档均生成 z=`10/30/60/90/110 nm`、40x20 周期单元中心网格上的 complex128 E/H；主数组 shape 为 `(5,20,40,3)`，接口显式保存 x/y tangential traces。z=10 从 +z 单元、z=110 从 -z 单元取迹，二者均来自中间模态区域。

h5 为 44,698 DoF，残差 `9.7340e-12`，`R/T/A=0.0890216029/0.4425882787/0.4683901184`；h3 为 198,438 DoF，残差 `9.9234e-12`，`R/T/A=0.0046130314/0.5836533572/0.4117336114`。两者闭合均优于 `1.3e-13`，NPZ/JSON/run-summary 哈希一致。h3 与历史 direct h3 的 R/T/A 绝对差约 `2.3e-14` 或更小。h5/h3 差异大，因此不宣称网格收敛：h5 用作快速开发，h3 是 Task032 主 full-3D 场/RTA reference。加入 Phase 2 formal QEP Gate 后，Case080 自动 checker 为 `277/277 passed`。

## 12. angle/polarization smoke

`not_started`。

## 13. memory and timing

Phase 0 h5 full-3D direct 的 simultaneous total peak RSS 为 `2367.133 MB`，elapsed `23.849 s`。该数值用于环境迁移 sanity，不替代后续外部同时 sampler 的正式 Hybrid 内存结论。

Phase 1 冻结参考采样的 E/H 未压缩复制载荷仅 `384000 bytes`，并有 `64 MiB` fail-closed 上限；没有聚集完整 FE vector、matrix 或 volume mesh。

正式 h5/h3 的内部 historical-peak 上界分别为 `2360.723 MB` 和 `8707.480 MB`，elapsed 分别为 `21.178 s` 和 `79.541 s`。这些 peak 不是外部同时采样值，不作为 Task032 最终内存权威。

Phase 2 QEP formal record 的单 rank 进程生命周期 historical peak 最大为 `231.277 MB`。各 rank 高水位并非同一采样时刻，既不求和也不升级为 Task032 最终 Hybrid 内存结论；最终结论仍要求外部 simultaneous stage sampler。

Phase 3 formal record 的单 rank 进程生命周期 historical peak 最大为 `236.465 MB`，内部 elapsed 最大 rank `7.563 s`。前者同样不是 simultaneous total，后者不含宿主 Docker 启动/JIT 固定成本；二者都不作为最终 Hybrid 内存/性能权威。

Phase 4 lightweight coefficient runner 的单 rank historical peak 最大为
`86.926 MB`，内部 elapsed 最大 rank `0.0126 s`。它只处理小型复制的 mode-count
数组，因此既不是 full eigensolve 资源，也不是最终 Hybrid 内存/性能结论。

## 14. negative results

首次最小 Stage4 preset 被继承的 `50 x 50 x 50 nm` 光栅块与 `10 x 10 nm` 平层周期冲突。通过显式零尺寸 A/B 定位后，在新库最小修复 preset 并新增合同测试；原始命令现已通过。失败过程和根因保存在 `old_vs_new_smoke.md`。

Phase 3 首次 block 双正交测试出现大 overlap 误差，根因是把 petsc4py `VecDot(x,y)=y^H x` 当成 NumPy 风格的 `x^H y`。交换 dot 参数顺序后，h5 air block 单位阵误差降到约 `4.9e-12`。完整 MPI4 测试最初还因在每个回归中重复负向和相邻参数 PEP 而两次触及 5 分钟上限；最终合同按职责拆分为 MPI4 正向分布式 basis 与 serial 负向/tracking，完整 research runner 仍在 MPI4 覆盖正反配对和角度 tracking。

## 15. changed files

Phase 0/1 已提交；Phase 2/3 evidence 与 Phase 4 implementation 包括：

```text
src/modes/cross_section_spaces.py
src/modes/quadratic_beta_eigenproblem.py
src/constraints/cross_section_floquet.py
src/geometry/mesh_builder_3d.py
src/test/test_32_task032_cross_section_qep.py
benchmarks/run_task032_phase2_qep.py
notes/reference/code_walkthrough/42_task032_cross_section_qep.md
notes/theory/hybrid_fem_modal_domain_decomposition.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/qep_phase2.json
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/expected/gates.json
benchmarks/check_benchmarks.py
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
docs/development_progress.md
src/modes/mode_classification.py
src/test/test_33_task032_mode_classification.py
benchmarks/run_task032_phase3_modes.py
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase3.sh
notes/reference/code_walkthrough/43_task032_mode_classification.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/modes_phase3.json
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/expected/gates.json
benchmarks/check_benchmarks.py
src/modes/stable_propagation.py
src/test/test_34_task032_stable_propagation.py
benchmarks/run_task032_phase4_propagation.py
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase4.sh
notes/reference/code_walkthrough/44_task032_stable_propagation.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/propagation_phase4.json
```

## 16. merge recommendation

```text
current recommendation = do_not_merge_yet
reason = Phase 1/2/3/4 are complete, but interface coupling and Hybrid direct solvers are pending
```

## 17. next Task033 decision

`not_applicable_yet`。只有 Task032 证明 Hybrid 正确且内存结构性下降后才评估 Task033。当前下一步是 Phase 5 matching-interface trace coupling。
