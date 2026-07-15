# Task032 滚动结果总结

## 1. local migration and branch identity

```text
task = Task032
status = phase0--phase10_implemented / h5_h3_physics_and_truncation_pass / h2_locked_by_memory_gate / clean_formal_record_pending
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

前置理论和 Task031 交接链已全部读取。Phase 0--5 与 Phase 6a--6e 的 clean 记录保持不变。本轮完成 `physical E/H + absorption -> wide M funnel -> augmented/Modal-Schur -> h5/h3 full-3D comparison -> angle/S-P smoke -> independent memory forensics`。h5/h3 的 M120--M160 均强收敛，h3 同网格 full-3D R/T/A、界面场和中间选面通过；三种 direct lifecycle 已独立测量。h2 因两种预测未过 4/5 GiB 强制 Gate 而按任务书保持锁定。

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
Phase 4 Gate 后为 `286/286 passed`。该句记录 Phase 4 的冻结边界；接口 coupling 现已按下节完成 clean Phase 5 record。

回归口径为完整 serial `196 tests / 10 skipped`、Phase 3+4 真实模式集成
`10/10`、Phase 4 单元合同 `6/6` 和正式 MPI4 runner `8/8` Gates。

## 7. interface projection

`clean_mpi4_formal_record_pass`。第一版使用匹配 3D hexa/2D quad 网格；canonical trace 为 `(E_x,E_y)`，bottom/top local FEM 外法向分别为 `+z/-z`，modal 外法向取相反号。分布式 3D 取迹只传接口插值点和两个复切向分量，空 source rank 合法，不聚集完整场或模态。

真实 Stage4 h10 两模 left/right Gram 投影得到 `N_Gamma=162`、`M=2`、Gram condition `30.4995`，系数 round trip 与重构 residual 分别为 `3.78e-16/4.69e-16`。affine complex 3D N1curl 场在 z=10/110 nm 的 2D trace coefficient error 为 `4.52e-15/6.61e-15`；air 两维近简并 basis 经 unitary rotation 后首向量相对差 `2.446`，但 mass-weighted projector error 仅 `2.11e-8`，因此 Gate 使用子空间而非逐向量 equality。完整 serial 回归为 `199 tests / 10 skipped`，Phase 5 MPI4 为每 rank `3/3`，正式 MPI4 runner 8/8 Gate 与 Case080 `290/290` checker 均通过。

```text
formal source commit = b565ac4610dee08a2d313060b7cb26b48145370d
clean formal record = benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/trace_phase5.json
record SHA-256 = 8b0eeff9e8666ed327f36e0ab243561e5cecbfc305cb353cab8f2108d6ac7aed
```

## 8. augmented direct result

`augmented_algebra_pass / physical_validation_pending`。Phase 6a 已建立 bottom/top 局部 p2 Nédélec/Floquet 网格，并完全移除中间 100 nm 三维体网格；Phase 6b 为每个局部系统只保留真实拥有的一侧外部 40 个 Fourier-DtN auxiliary unknown，bottom 无入射源、top 保留既有入射 traction/projection。Phase 6c 新增内部 `M x N` 投影、`N x M` 正/负向牵引、`M x M` 负迹映射和 O(M) 稳定传播对象，内部 unknown/equation 均为 `2M`，未构造 dense `N_interface^2`。

Phase 6c 的二维到三维提升只 allgather 小型结构化轴/cell-owner metadata，并用 alltoall 交换请求点和两个复切向分量；所有 collective 均在 DOLFINx interpolation callback 外执行，不聚集完整 field/mode。真实接口 surface Gram 取代 raw 2D Gram；bottom/top local FEM 法向为 `+z/-z`，traction 字段逐值变号。最终验证为 serial `4/4`、MPI2 每 rank `4/4`、MPI4 每 rank `4/4`。这些结果只资格化 block shape、projection round trip、normal sign、distributed ownership 和无 growing inverse；尚未声称 augmented residual、接口 E/H 连续、MUMPS 解或 Hybrid R/T/A 通过。

Phase 6d 把 unknown 冻结为 `[u_bottom,u_top,a_b+,a_t-]`，用 `a_b-=P-a_t-`、`a_t+=P+a_b+` 消去 outgoing amplitude。两个独立 local matrix 通过 rank-major 连续 ownership 复制到单个 MPI AIJ；每个 rank 依次拥有自身 bottom/top rows，最后一个 rank 再拥有 `2M` modal rows。h10 两条解析 Bloch mode 的 serial/MPI2/MPI4 均为每 rank `3/3`；MPI4 单体为 `2432 x 2432`、`251720` nnz，MUMPS 真相对残差 `3.732133e-13`，setup/solve 为 `0.046960/0.003048 s`。该结果分类为 `augmented_algebra_pass`，不是 `physical_augmented_direct_pass`；真实 Phase 3 basis、M 收敛、R/T/A 与 full-3D 比较仍待执行。

Phase 6e 已接入真实正/负 QEP basis，并在 h5 上执行 M=2/4/6 研究漏斗。研究 M6 单体为 `13744 x 13744`、`1470406` nnz，真残差 `4.6392e-12`；M4->M6 的 `|delta R/T/A|` 为 `8.33e-14/9.82e-13/1.07e-12`。target-cell Nédélec 路由把新增两列映射误差从最高 `1.24e-2` 降到约 `2e-14`，三组 block inverse 将正/负双正交误差降到约 `1e-11`。

随后从 clean source `5c1f12e610dd8c6040389c44c31584ab7fba66cd` 生成正式 MPI4 h5/M6 集成记录。该次精确交付正/负 `6/6` 模式，单体 `13744 x 13744`、`1470403` used nnz，真残差 `1.8590e-12`，接口 E 残差 `1.3090e-13`，bottom/top 变分 FE-modal traction residual 为 `2.6770e-12/1.5094e-12`；10 个 runner Gate 和 Case080 `294/294` checker 全过。记录分类仍是 `physical_integration_pass_mode_convergence_pending` 且 `official_record=false`；pointwise H jump、体吸收、中间选面和 h3 仍待完成。

```text
formal source commit = 5c1f12e610dd8c6040389c44c31584ab7fba66cd
clean integration record = benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/hybrid_phase6_m6.json
record SHA-256 = 43e46de0a7b82f9d0d0d1bb29474ddca08bc017dd5c436122fe6223561812011
```

Phase 6f 已用共享 scratch 模态重构器补齐物理 H、界面 E/H、局部+中间体吸收和五个选面。h5/M160 的体吸收闭合为 `1.74e-11`，相对 full-3D 的体吸收差 `2.07e-6`，选面 E/H 最大相对误差 `2.88e-4/8.79e-4`；h3/M160 对应为 `2.63e-6`、`4.35e-5/7.80e-4`。h3 local z 轴显式插入冻结的 10/110 nm，而不是把接口移动到 9/111 nm。

## 9. modal-Schur result

`implemented_and_numerically_passed`。fast 路径各局部 LU 只做一次 `MatMatSolve([f,C])`，形成 `2M x 2M` modal Schur 后恢复上下场；memory-minimal 路径按 bottom factor/contribution/release、top factor/contribution/release、modal solve、逐侧 refactor/recovery 执行。M160 的 h5/h3 modal coefficients、局部解、接口投影、R/T/A 和 full residual 均与 augmented 一致，未形成 dense `N_interface^2` 或完整 field/mode gather。内存结果见第13节。

## 10. truncation convergence

宽漏斗已完成 h5 `M=20/40/80/120/160`。M20->M40 的最大 total delta 为 `2.25e-5`，M40->M80 仅过 mandatory，M80->M120 和 M120->M160 才进入 strong 平台。最终一对最大 `|delta R/T/A|=7.71e-14`，显著衍射级复振幅最大相对变化 `2.22e-10`，界面投影 `3.91e-13`。h3 的 M120->M160 最大 total delta `3.55e-14`，显著复振幅变化 `9.86e-11`。两档均标记 `mode_truncation_converged`；clean formal record 尚待第一轮实现提交后重跑。

## 11. full-3D comparison

Phase 1 已从 clean commit `c468c728...` 完成 h5/h3 MPI4 direct reference。两档均生成 z=`10/30/60/90/110 nm`、40x20 周期单元中心网格上的 complex128 E/H；主数组 shape 为 `(5,20,40,3)`，接口显式保存 x/y tangential traces。z=10 从 +z 单元、z=110 从 -z 单元取迹，二者均来自中间模态区域。

h5 为 44,698 DoF，残差 `9.7340e-12`，`R/T/A=0.0890216029/0.4425882787/0.4683901184`；h3 为 198,438 DoF，残差 `9.9234e-12`，`R/T/A=0.0046130314/0.5836533572/0.4117336114`。两者闭合均优于 `1.3e-13`，NPZ/JSON/run-summary 哈希一致。h3 与历史 direct h3 的 R/T/A 绝对差约 `2.3e-14` 或更小。h5/h3 差异大，因此不宣称网格收敛：h5 用作快速开发，h3 是 Task032 主 full-3D 场/RTA reference。加入 Phase 2 formal QEP Gate 后，Case080 自动 checker 为 `277/277 passed`。

clean Phase 6e h5/M6 对同网格 full-3D h5 的 `Hybrid-full3D R/T/A` 为 `-4.8325e-6/-1.1162e-5/1.5994e-5`。full-3D h5 本身未网格收敛，且 Hybrid 尚未重建体吸收与点值 H，因此这些仍是同网格诊断，不能单独升级最终物理资格。

本轮 h3/M160 `Hybrid R/T/A=0.0046128199040/0.5836509402052/0.4117362398908`，相对冻结 full-3D h3 的差为 `-2.1150e-7/-2.4170e-6/+2.6285e-6`。界面 E/H 采样误差 `1.04e-7/4.82e-4`，中间选面 E/H `4.35e-5/7.80e-4`。这些同网格对照通过 `1e-5` 主阈值，但仍不把 h5--h3 差异解释为 full-3D 网格收敛。

## 12. angle/polarization smoke

研究批次 `30/30 pass`：h5 覆盖 1--10° 的 S/P，h3 覆盖 1/3/5/7/10° 的 S/P。每点验证参数 round trip、complex128、无 full gather、QEP 重算、被动方向分类、真实残差、界面投影、有限 R/T/A 与逐衍射级输出。较小 M=4 只用于 smoke；该批次明确不宣称整个角度范围 production qualification。

## 13. memory and timing

Phase 0 h5 full-3D direct 的 simultaneous total peak RSS 为 `2367.133 MB`，elapsed `23.849 s`。该数值用于环境迁移 sanity，不替代后续外部同时 sampler 的正式 Hybrid 内存结论。

Phase 1 冻结参考采样的 E/H 未压缩复制载荷仅 `384000 bytes`，并有 `64 MiB` fail-closed 上限；没有聚集完整 FE vector、matrix 或 volume mesh。

正式 h5/h3 的内部 historical-peak 上界分别为 `2360.723 MB` 和 `8707.480 MB`，elapsed 分别为 `21.178 s` 和 `79.541 s`。这些 peak 不是外部同时采样值，不作为 Task032 最终内存权威。

Phase 2 QEP formal record 的单 rank 进程生命周期 historical peak 最大为 `231.277 MB`。各 rank 高水位并非同一采样时刻，既不求和也不升级为 Task032 最终 Hybrid 内存结论；最终结论仍要求外部 simultaneous stage sampler。

Phase 3 formal record 的单 rank 进程生命周期 historical peak 最大为 `236.465 MB`，内部 elapsed 最大 rank `7.563 s`。前者同样不是 simultaneous total，后者不含宿主 Docker 启动/JIT 固定成本；二者都不作为最终 Hybrid 内存/性能权威。

Phase 4 lightweight coefficient runner 的单 rank historical peak 最大为
`86.926 MB`，内部 elapsed 最大 rank `0.0126 s`。它只处理小型复制的 mode-count
数组，因此既不是 full eigensolve 资源，也不是最终 Hybrid 内存/性能结论。

外部 0.25 s simultaneous sampler 的独立 M160 结果为：h5 augmented/Schur-fast/Schur-minimal `1.869/1.649/1.680 GiB`，h3 为 `3.869/3.974/3.215 GiB`；全部零 swap。h5 fast 有收益而 minimal 略差，h3 fast 反而比 augmented 高，只有 sequential-factor minimal 降约 `16.9%`。这说明因子填充和 allocator 高水位必须实测，不能仅按矩阵维数推断。

h2 最佳候选是 memory-minimal；网格尺度预测中心/上界 `5.380/6.188 GiB`，MUMPS factor-payload 预测为 `11.511/13.238 GiB`。两者均未满足中心 `<=4`、上界 `<=5`，故 `h2_unlock=false`，没有运行 h2。详见 `phase10_memory_and_h2_decision.md`。

## 14. negative results

首次最小 Stage4 preset 被继承的 `50 x 50 x 50 nm` 光栅块与 `10 x 10 nm` 平层周期冲突。通过显式零尺寸 A/B 定位后，在新库最小修复 preset 并新增合同测试；原始命令现已通过。失败过程和根因保存在 `old_vs_new_smoke.md`。

Phase 3 首次 block 双正交测试出现大 overlap 误差，根因是把 petsc4py `VecDot(x,y)=y^H x` 当成 NumPy 风格的 `x^H y`。交换 dot 参数顺序后，h5 air block 单位阵误差降到约 `4.9e-12`。完整 MPI4 测试最初还因在每个回归中重复负向和相邻参数 PEP 而两次触及 5 分钟上限；最终合同按职责拆分为 MPI4 正向分布式 basis 与 serial 负向/tracking，完整 research runner 仍在 MPI4 覆盖正反配对和角度 tracking。

本轮负结果包括：宽 target slice 混入反向候选、M120 per-mode Function 耗尽 MPI context、h3 缺少精确接口平面、M40 total delta 未过 mandatory、h5 minimal 不优于 fast、h3 fast 不优于 augmented，以及 h2 预测失败。均已保留根因与停止边界，详见 `negative_results.md`。

## 15. changed files

Phase 0/1 已提交；Phase 2/3/4/5 implementation 与 evidence 包括：

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
src/coupling/modal_trace_projection.py
src/test/test_35_task032_modal_trace_projection.py
benchmarks/run_task032_phase5_trace.py
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase5.sh
notes/reference/code_walkthrough/45_task032_modal_trace_projection.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/trace_phase5.json
src/geometry/hybrid_local_mesh.py
src/solvers/hybrid_local_dtn.py
src/coupling/hybrid_internal_modes.py
src/test/test_36_task032_hybrid_local_mesh.py
src/test/test_37_task032_hybrid_local_dtn.py
src/test/test_38_task032_hybrid_internal_modes.py
notes/reference/code_walkthrough/46_task032_hybrid_local_mesh.md
notes/reference/code_walkthrough/47_task032_hybrid_internal_modes.md
src/solvers/hybrid_fem_modal_augmented_direct.py
src/test/test_39_task032_hybrid_augmented_direct.py
notes/reference/code_walkthrough/48_task032_hybrid_augmented_direct.md
benchmarks/run_task032_phase6_augmented.py
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase6.sh
notes/reference/code_walkthrough/49_task032_hybrid_physical_runner.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/phase6e_research_diagnostic.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/hybrid_phase6_m6.json
src/postprocessing/hybrid_field_reconstruction.py
src/solvers/hybrid_fem_modal_schur_direct.py
benchmarks/run_task032_phase8_funnel.py
benchmarks/run_task032_phase9_smoke.py
benchmarks/run_task032_memory_forensics.py
benchmarks/run_task032_h2_prediction.py
src/test/test_40_task032_hybrid_field_reconstruction.py
notes/reference/code_walkthrough/51_task032_fields_schur_and_memory.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/phase6f_to_phase9_numerics.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/phase10_memory_and_h2_decision.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/negative_results.md
```

## 16. merge recommendation

```text
current recommendation = implementation_ready_for_clean_formal_rerun_and_review
reason = h5/h3 physical, Schur, truncation, parameter smoke and independent memory research pass; h2 correctly remains locked; clean records/checker still pending
```

## 17. next Task033 decision

`do_not_start_yet`。Task032 已证明 h5/h3 数值正确，并在 h3 memory-minimal 取得结构性下降，但 h2 未解锁。先完成 clean formal records、Case080 checker、review 和合并；Task033 只能在审阅接受 Task032 的“工程成功但非 h2 强成功”边界后开始。
