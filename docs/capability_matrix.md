# 能力矩阵

状态只使用：`recommended`、`supported`、`experimental`、`research_only`、`diagnostic_only`、`deprecated`、`not_implemented`、`not_verified`。

## 2D

| 能力 | 状态 | MPI/入口 | 当前边界 |
|---|---|---|---|
| TM Nedelec | recommended | serial/MPI，`run_cases` | 主验证偏振 |
| TE scalar | supported | serial/MPI | 与 TM 形式不同 |
| real refractive index | supported | config/CLI | 零对比与 Fresnel 可验证 |
| complex refractive index | supported | complex PETSc | 支持体吸收 |
| x-Floquet | supported | manual 或 MPC | DtN 推荐 manual |
| PML | supported | scattered formulation | 与 port total-field 路径分开 |
| Robin port | supported | port workflow | 局部近似边界 |
| DtN port | recommended | manual + port_total | nonlocal DtN 不使用 mpc_official |
| explicit DtN | supported | `--port-dtn-assembly explicit` | 小阶数验证 |
| auxiliary DtN | recommended | `--port-dtn-assembly auxiliary` | 稀疏增广形式 |
| Fresnel reference | supported | flat interface | 用于界面基准 |
| multi-order R_m/T_m | supported | diffraction postprocess | 传播阶筛选 |
| total R/T/A | supported | postprocessing | official 来源取决于求解路径 |
| volume absorption | supported | complex material | 只在有损区域积分 |
| angle scan | supported | scan runner | 每点仍需 residual gate |
| wavelength scan | supported | scan runner | 材料色散由输入负责 |
| field output | supported | results/artifacts | VTU/PVD 不进 Git |
| mesh/order controls | supported | CLI/config | 新组合需网格收敛检查 |
| serial direct | recommended | ordinary default | 小中型案例 |
| MPI direct | supported | PETSc/MUMPS | 受因子内存限制 |
| production iterative | not_implemented | 无 2D production profile | 当前重点为 3D Stage4 |

## 3D

| 能力 | 状态 | MPI/入口 | 当前边界 |
|---|---|---|---|
| Stage1 airbox | recommended | serial/MPI | 快速 sanity |
| Stage2A double Floquet | supported | MPI | x/y 周期约束 |
| Stage2B PML | experimental | MPI | tensor/decay smoke 已有；尚无独立 canonical record 与生产精度资格 |
| Stage2C Fresnel | experimental | MPI | 解析参考/组合测试已有；旧 p2 精度限制尚未关闭 |
| Stage4 flat-layer sanity | recommended | MPI | 能量与参考解闭环 |
| Stage4 block grating | supported | MPI | 当前目标几何 |
| p1 Nedelec | supported | ordinary CLI | 低阶验证 |
| p2 Nedelec | recommended | ordinary/benchmark | workstation qualification 使用 p2 |
| p3 Nedelec + double Floquet | supported | Case090 + Case093，MPI1/2/4/8/16 | 解析 fixtures 已资格化；Task034 p3/h3 目标光栅 Full3D–Hybrid same-degree closure 通过，p3/h5 MPI identity 通过 |
| p4 Nedelec + double Floquet | experimental | Case090 + Case093，显式入口 | 解析 fixtures 通过；Task034 p4/h5 Full3D–Hybrid same-degree closure 通过；p4/h3 只有 Hybrid M160 shard，Full3D 在 assembly 后资源 stop |
| p3/p4 cross-section QEP | experimental | Task033 Phase A | p3/p4 组件与 selected MPI identity 已资格化；p4 只具有 compact Fourier subspace 证明；legacy p1–p4 aggregate 因 p1/p2 负结果未资格化 |
| p3/p4 matching-interface trace/projection | experimental | Task033 Phase B，p2 MPI1 + p3/p4 MPI1/MPI4 | 3D→2D 迹、右重构、左 Petrov、积分加阶、MPI compact identity、no-gather/no-dense 通过；p4 四模态块通过 |
| p3/h5 Hybrid modal funnel | experimental | Task033 Phase C，MPI4，M80/M120/M160 | Schur-minimal 漏斗、augmented/minimal 和同阶 full3D closure 通过；Hybrid 2.618 vs direct 7.781 GiB，未证明 wall-clock speedup 或 grid convergence |
| p3/h7.5 fixed-p equal accuracy | experimental | Task033 Review V6 accepted，MPI4，M120/M160 | `fixed_p_equal_accuracy_clear_success_with_qualifications`；相对 provisional p3/h5 reference 全部物理误差不劣，DoF/rows/factor-NNZ/memory/指示性时间全降；不是 continuum/grid-converged 证明 |
| native cellwise variable-p H(curl) | not_implemented | Task033 Phase D2 runtime audit | DOLFINx/Basix 公开 mixed/submesh API 不构成 unequal-p conformity/periodic/MPI 证据；bespoke exact-sequence research path 另列，不能写成 native capability |
| conforming graded-h mechanism | research_only | Task034 explicit research runner | mesh/Floquet/marker mechanism pass；三档 same-error compression controlled negative；未进入 production selective merge |
| Task035 field/goal-oriented h-adaptive / hp | experimental | Case094，Task035 stacked research branch | actual DtN adjoint、R/DWR、periodic tetra one-cycle local-h 与 fixed-mesh p-up 已有证据；最佳 adaptive 候选仍未通过全部 strict control，不是 ordinary default |
| Task035b assembly-time high-p condensation | experimental | `stage4_full3d_assembly_backend="assembly_time_static_condensed"` | fixed rectangular、first-order axis-aligned affine hexa、complex128 H(curl) direct 已资格化；包含cell-interior Schur、Floquet physical elimination、tensor dedup、exact preallocation、full recovery/true residual；ordinary default仍为`standard_full` |
| Task035b fixed p5-trace/p6-interior | research_only | Case095 MPI8 | h15 74,890 DoF、16,880 rows、5.803 GiB；scalar/vector/field/residual pass，但 12 通道只有 6/12 power、7/12 amplitude |
| Task035b Review V1 channel recovery | research_only | Case095 MPI8 + pure-postprocess | reference v1 与 16-goal adjoint通过；预算内最佳 z-only h13 为 89,740 DoF、10/12 power、10/12 amplitude，未达 same-error Gate |
| Task035e multilevel local-h / p4-p6 active-space infrastructure | research_only | Case098 explicit opt-in，MPI8 | component capability pass：level0/1/2、2:1、periodic/hanging、p4/p5/p6 inactive-mode elimination、current/p-shadow/h-shadow 均通过；没有 accepted cycle 或 production candidate |
| selective physical p6 trace restoration | research_only | Task035e Case098，MPI8 | `controlled_negative`：exact B/S/F hierarchy、774 periodic face orbits 和 signed DWR 已实现；16-orbit actual 对指定6目标有效，但完整结果49/59，direct lane已关闭 |
| Task035e reference-blind automatic hp controller | not_verified | Case098 closed historical research case | final status `incomplete`：reference certification通过；cellwise action predictor失败；无 accepted transition、cycle1、Path A/B freeze 或 hidden final audit |
| condensed trace factor-free iterative screen | not_verified | Case095 negative evidence | 三条MPI8 200步 terminal residual ratio=`0.861662/0.999661/0.996265`，均无official输出；不得通过public assembly backend选择，也不得把direct或NNZ proxy冒充迭代成功 |
| p2/p3/p4 fixed-geometry S sequence | experimental | Case093，MPI8 | 9 个 same-degree closure positive，p3/h10 Hybrid formal negative；不是 continuum/grid-converged 证明 |
| representative MPI-count identity | experimental | p3/h5 Full3D/Hybrid MPI1/8/16；MPI32 exploratory | identity 在阈值内；只关闭代表案例，不声明所有 p/h/M 对 MPI 数无关 |
| complex material | supported | complex PETSc | substrate/grating 可吸收 |
| auxiliary DtN | recommended | ordinary Stage4 | 稀疏增广系统 |
| explicit condensed DtN | supported | `condensed_dtn.py` | reference helper 仅支持 verified `H=I`；一般 H 用 matrix-free exact action |
| matrix-free condensed DtN | recommended | benchmark runner | `F-C H^-1 D` |
| MUMPS direct | recommended | ordinary default | h=2 内存超当前工作站 |
| Task29 direct-memory telemetry | recommended | Case050 runner | Review V2 技术通过并获准合并；RSS/cgroup/swap/stage/matrix/factor/CPU/thread 证据 |
| Task29 optimized direct profile | not_implemented | 无 | 所有候选均未通过 h3 工程 Gate |
| MUMPS MPI2 low-rank-count direct | diagnostic_only | Case050 显式 `--mpi-size 2` | h3 RSS 只降 15.119%，不是推荐 profile |
| MUMPS out-of-core | diagnostic_only | `mumps_ooc` profile | h5 只降 13.744%，时间 1.539×，需 scratch/I/O 证据 |
| MUMPS BLR | experimental | PETSc extra options | Task29 `1e-5` 数值 Gate 失败，不是当前候选 |
| SuperLU_DIST direct backend | supported | 显式 PETSc package | backend 有效；目标 h5 RSS +14.462%，不推荐该模型 |
| release-base lifecycle control | diagnostic_only | 显式 opt-in | h3 只降 5.462%，不是 low-memory profile |
| OpenBLAS-threaded direct | diagnostic_only | Case050 `--threads-per-rank` | 当前 image MPI1×4 KSPSetUp 仍约 1 核；capability unavailable |
| MPI4 workstation iterative | recommended | 显式 benchmark | 仅固定 p2/h5,h3,h2 profile |
| Task30 compact physical-slab low-memory profile | experimental | Case060 显式 flags | `workstation_memory_success_with_qualifications`；Review V3 通过并已合入 master；ordinary default 未改变 |
| Task31 assembled-F-free compact memory-first profile | experimental | Case070 显式 flags | clean h5/h3/h2 full pass；h2 external simultaneous 7.898 GiB、legacy internal 8.176 GiB；相对 Task030 历史值观察降幅约 15.8%/保守约 12.8%；solve 约 5.01x，非 ordinary default |
| Task31 simultaneous RSS/cgroup/swap/stage telemetry | recommended | `run_task031_memory_forensics.py` | 0.25 s live-rank sum，禁止 per-rank historical peak sum；h2 watchdog 9.5/11 GiB |
| public MPC form action + condensed fine lifecycle | experimental | `mpc_form_action.py` / Case070 | assembled-F-free public form-action path；h5/h3/h2 action error `<1e-15`；每次 apply 仍 assemble/通信，非低层缓存 kernel；跨参数/版本需复验 |
| Task32 generic 2D cross-section QEP / classification / propagation | experimental | Case080 显式 runner | 13.5 nm h5/h3 infrastructure validated；当前 all-modes MUMPS shift-invert、显式 right/left vectors 仅 current-scale，非 0.7 nm production |
| Task32 matched Hybrid FEM–Modal interface | experimental | Case080 explicit opt-in | p2/h5、p2/h3 M160 与同网格 full3D 的 R/T/A、E/H、吸收通过；M=每方向模式数，M160=320 internal amplitudes；p3/p4 无同阶 reference |
| Task32 augmented / Modal-Schur direct | experimental | Case080 explicit opt-in | `hybrid_direct_engineering_success` at 13.5 nm；h3 minimal 3.224 GiB；h2 `not_run_by_gate`；last-rank modal ownership、replicated M²、all-mode multi-RHS 和 local LU 不是 scalable service API |
| Task32 parameter interface | diagnostic_only | Case080 M4 smoke | 1–10° S/P 30/30 只证明接口/API/algebra；未证明全范围截断或物理资格 |
| Task036 compressed direct Hybrid | research_only | Task036 frozen branch | `controlled_negative / closed`；没有得到满足小掠射角、P 偏振、完整通道和显著内存优势的低维 direct 端口 |
| Task036 strong-trace Hybrid | research_only | explicit opt-in | 切向 E 连续达到 `4.588e-15`，但 energy `1.531666e-5 > 1e-5`、固定通道 `77/96`；不是 production Hybrid |
| Task036 exact FE trace-chain | research_only | one-cell/endpoint/full-chain oracle | 域分解 correctness oracle；可对照 Full3D，但不是可扩展生产 solver |
| Task036 M120/M240 complete port | not_verified | no production entry | 完整 joint-Cauchy/全通道合同未通过，not production-qualified；M120 selected-space 长程模态核心约 `2e-11` 对照仍保留 |
| 0.7 nm / 2 TiB solver | not_implemented | no solver entry | Task036 未解决；没有满足精度与整作业内存合同的实测或已资格化路线 |
| Task037 Full3D iterative research baseline | research_only | Task037 M3a explicit opt-in | p6/h10 Full3D matrix-free/static-condensed iterative baseline；不是 ordinary default，不是 0.7 nm qualification |
| Task037b frozen Hybrid iterative selective-merge-qualified research capability | research_only | `benchmarks/run_task037b_hybrid_iterative.py --frozen-m10` + dedicated watchdog/checker | p6/h10、13.5 nm、S、10°、M120/240、MPI8；五 residual、traction、recovery/physics/canonical 与 `12+12` 通过；ordinary direct/default unchanged |
| future complex-ends Hybrid route | research_only | scalable modal core → low-memory Hybrid iterative → wavelength continuation | exact complex 3D FEM ends required；generic epsilon(x,y) modal middle retained；1–2 TiB 为 conditional opportunity，尚未证明 |
| FGMRES outer port | recommended | `--ksp-type fgmres` | 与当前 variable/adaptive PC 合法配对；Task27/30/31 frozen target verified |
| ordinary GMRES outer port | research_only | `--ksp-type gmres` | port implemented；当前 PC linearity error `2.374308e-2`，certification fail closed，not target-qualified |
| TFQMR / BCGS outer ports | research_only | `--ksp-type tfqmr` / `--ksp-type bcgs` | interface exposed；非 FGMRES 自动 certification，当前 adaptive PC 不合法且无 full target qualification |
| fixed Richardson local smoother | research_only | `--smoother-ksp-type richardson` | 线性通过但 h5 200 步 residual 0.7703；numeric negative |
| nonmatching H(curl) transfer + condensed Galerkin | research_only | `hcurl_multilevel.py` / Case060 | validated infrastructure API 与失败 p/h/Woodbury research candidates 已隔离；当前 792D p1 coarse 的 solver 性能为负，不是可推荐 GMG |
| subdomain-local shift + factor-only storage | experimental | workstation runner 显式 opt-in | PETSc 3.24 complex action/lifecycle 等价通过；跨版本需回归；普通 Task27 profile 不变 |
| h=1.5 iterative | not_verified | 无 canonical record | 不得宣称 production |
| field/mesh output | supported | results/artifacts | rank-local + parallel PVD |
| residual telemetry | recommended | ordinary/benchmark | full true residual 是最终口径 |
| total MPI RSS telemetry | recommended | ordinary/benchmark | Task31 以同一采样时刻 live-rank RSS sum 为权威；各 rank 不同时刻 historical peak sum 只能单列 legacy/diagnostic |
| official modal R/T | recommended | DtN modal amplitudes | residual 通过后才有效 |
| A_volume | recommended | volume integral | 与 official port power 闭合 |
| probe-plane Fourier | diagnostic_only | postprocess | 不替代 official R/T |
| sampled net flux | diagnostic_only | postprocess | 用于定位能流问题 |
| spectral/GenEO coarse | research_only | 历史 Task27 分支 | 目标问题未成功 |
| HPDDM recycling | research_only | 历史研究分支 | 稳定 profile 不依赖 |
| AMS/HX FE-only | research_only | 历史研究分支 | 未形成 full Stage4 production PC |

## Qualification 范围

### Task027–Task031 canonical iterative profile qualification

| 参数 | 已验证值 |
|---|---|
| geometry | 50 x 25 nm period，17 x 25 x 120 nm block，130 nm air，10 nm substrate |
| incidence | theta=80 deg，phi=0 deg，s polarization |
| wavelength | 13.5 nm |
| element | p=2 Nedelec |
| mesh target | h=5/3/2 nm |
| MPI | 4 ranks |
| solver | canonical: fixed 75D coarse + 16 physical slabs + sm2 + FGMRES(100)；Task30 compact experimental: symmetric pre/post ILU0 + local shift + factor-only + FGMRES(90)；Task31 memory-first experimental: Task30 架构 + overlap0.125 + assembled-F-free public MPC form action + compact lifecycle |
| Task32 Hybrid direct | h5/h3、M160、13.5 nm 主点 only；h2 not run；30-point parameter set is smoke only |

该表只约束旧 iterative profile；偏离后必须重新取得相应参考、三残差、R/T/A、能量闭合和总 RSS 证据，不得把它解释为 Task034 fixed-geometry 的上限。

### Task034 Case093 fixed-geometry qualification

| 能力 | 已接受范围 | 边界 |
|---|---|---|
| S-polarization p/h sequence | p2: h5/h3/h2；p3: h10/h7.5/h5/h3；p4: h10/h7.5/h5；Full3D + Hybrid M160，MPI8 | 9 个 same-degree closure positive，p3/h10 Hybrid formal negative；不是 continuum convergence |
| higher-cost controlled outcomes | p2/h1、p3/h2、p4/h3 Full3D assembly/resource Gate；p2/h1 Hybrid field-recovery timeout；p3/h2、p4/h3 Hybrid M160 shard | stop/timeout 不得写成 solver pass；shard 不构成 M funnel 或 Full3D closure |
| representative MPI identity | p3/h5 S，Full3D + Hybrid M160，MPI1/8/16；MPI32 exploratory | 只关闭该代表案例的 MPI-count identity，不外推到全部 p/h/M |
| accepted M funnels | p3/h3 S MPI8 与 p4/h5 S MPI4，M80/M120/M160 | 不把 p4/h5 MPI4 funnel 宣称为 MPI8 production matrix |
| P-incidence capability | p2/h5 MPI8 单一 Full3D + Hybrid M160 sample | capability only，不重复整套 P 主矩阵 |

### Task035b Case095 fixed-geometry qualification

| 能力 | 已接受范围 | 边界 |
|---|---|---|
| same-mesh high-p | structured hexa h10 global p4/p5/p6，MPI8 | p6 是 best-available same-code high-p discrete reference，不是 continuum truth |
| high-p physical reduction | assembly-time cell Schur、Floquet slave elimination、tensor dedup、exact preallocation、factor release | exact opt-in engineering result；没有改变 ordinary direct default |
| significant-channel reference | 12 个 n=0 S 通道，power 与复振幅 numerical bands | reference v1 是 best-available convergence authority；冻结 Gate 不因弱功率放宽 |
| Review V1 recovery | fixed-trace h15/h14/h13/x、global-p5 y control、global-p6 h14、R5 slab、q31/buffer | 最佳 h13 仅 10/12 power + 10/12 amplitude；eligible candidate=0 |
| Hybrid continuation | 无 | selected Full3D candidate Gate 未通过，所以 Full3D–Hybrid、M/DtN funnel 与 resource model v3 均未运行 |

### Task035e Case098 qualification boundary

| 能力 | 已接受范围 | 边界 |
|---|---|---|
| reference certification | global p6 h10/h7.5/h5，MPI8，59-goal | 三点全部59/59；h5 peak 77.95 GiB；是离散 reference，不是生产配置 |
| multilevel local-h / variable-p | Path A current/p-shadow/h-shadow，MPI8 | component capability pass；没有 accepted action/cycle1 |
| goal-oriented selective trace | H10 p5-trace/p6-interior + 16 p6 face orbits | `research_only / controlled_negative`；指定6目标预测/actual pass，完整49/59 |
| reference-blind automatic hp | 无 | `incomplete`；hidden final audit、Path A/B freeze、Hybrid 均未运行 |
| Task035e final closure | Review V1 documentation authority | `PARTIAL_WITH_CONTROLLED_NEGATIVES_CLOSED`；production candidate none；ordinary default unchanged |

## 能力到使用、理论和证据的映射

| 能力 | Quick Start | Theory / Code Walkthrough | Benchmark case |
|---|---|---|---|
| 2D TM PML/Floquet | [`10_2d_pml_floquet.md`](../notes/quick_start/10_2d_pml_floquet.md) | [`maxwell_strong_weak_and_fem.md`](../notes/theory/maxwell_strong_weak_and_fem.md)、walkthrough 11 | [`001`](../benchmarks/cases/001_2d_tm_pml_floquet/README.md) |
| 2D TM DtN | [`11_2d_dtn_floquet.md`](../notes/quick_start/11_2d_dtn_floquet.md) | [`dtn_modal_ports_and_condensation.md`](../notes/theory/dtn_modal_ports_and_condensation.md)、walkthrough 12 | [`002`](../benchmarks/cases/002_2d_tm_dtn_equivalence/README.md) |
| 2D TE/TM/复材料 | [`12_2d_te_tm_and_complex_material.md`](../notes/quick_start/12_2d_te_tm_and_complex_material.md) | [`official_and_diagnostic_rta_methods.md`](../notes/theory/official_and_diagnostic_rta_methods.md) | [`003`](../benchmarks/cases/003_2d_te_tm_complex_absorption/README.md) |
| 3D Stage1 | [`20_3d_stage1_airbox.md`](../notes/quick_start/20_3d_stage1_airbox.md) | walkthrough 20 | [`010`](../benchmarks/cases/010_3d_stage1_airbox/README.md) |
| Stage2A/B/C | quick start [`21`](../notes/quick_start/21_3d_stage2a_floquet.md)/[`22`](../notes/quick_start/22_3d_stage2b_pml.md)/[`23`](../notes/quick_start/23_3d_stage2c_fresnel.md) | [`3d_stages_and_validation_ladder.md`](../notes/theory/3d_stages_and_validation_ladder.md) | cases [`011`](../benchmarks/cases/011_3d_stage2a_floquet/README.md)-[`013`](../benchmarks/cases/013_3d_stage2c_fresnel/README.md) |
| Stage4A flat | [`30_3d_stage4a_flat_layer.md`](../notes/quick_start/30_3d_stage4a_flat_layer.md) | walkthrough 22/23 | [`020`](../benchmarks/cases/020_3d_stage4a_flat_dtn/README.md) |
| Stage4B direct | [`31_3d_stage4b_grating_direct.md`](../notes/quick_start/31_3d_stage4b_grating_direct.md) | [`direct_solvers_and_factorization.md`](../notes/theory/direct_solvers_and_factorization.md) | [`021`](../benchmarks/cases/021_3d_stage4b_direct/README.md) |
| exact condensation | iterative quick start | walkthrough 31 | [`022`](../benchmarks/cases/022_dtn_condensation_equivalence/README.md) |
| OOC/BLR | [`32_3d_direct_ooc_blr.md`](../notes/quick_start/32_3d_direct_ooc_blr.md) | walkthrough 30 | [`030`](../benchmarks/cases/030_mumps_ooc_blr/README.md) |
| direct memory/thread forensics | solver guide Task029 | walkthrough 30 | [`050`](../benchmarks/cases/050_stage4_direct_memory_forensics/README.md) |
| MPI4 workstation iterative | [`40_3d_workstation_iterative.md`](../notes/quick_start/40_3d_workstation_iterative.md) | [`iterative_solver_ports.md`](iterative_solver_ports.md)、[`iterative_solver_and_preconditioner.md`](../notes/theory/iterative_solver_and_preconditioner.md)、walkthrough 32/33 | [`031`](../benchmarks/cases/031_workstation_iterative/README.md) |
| Task30 H(curl) infrastructure + physical-slab low-memory research | [`iterative_solver_ports.md`](iterative_solver_ports.md) / solver guide Task030 | iterative theory、walkthrough 32/33/50 | [`060`](../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md) |
| Task31 assembled-F-free compact memory-first research | [`iterative_solver_ports.md`](iterative_solver_ports.md) / solver guide Task031 | iterative theory、walkthrough 31/32/33/50 | [`070`](../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md) |
| Task32 Hybrid FEM–Modal direct reference | [`task032_hybrid_fem_modal_direct_baseline/README.md`](task032_hybrid_fem_modal_direct_baseline/README.md) | [`hybrid_fem_modal_domain_decomposition.md`](../notes/theory/hybrid_fem_modal_domain_decomposition.md)、walkthrough 41–51 | [`080`](../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/README.md) |
| Task036 Hybrid controlled-negative closeout | [`task036_forward_solver_bugfix_hardening/outcomes/final_summary.md`](task036_forward_solver_bugfix_hardening/outcomes/final_summary.md) | [`review_report_v8.md`](task036_forward_solver_bugfix_hardening/review_report_v8.md) | research evidence retained on frozen Task036 SHA |
| Task035 H(curl) goal-oriented adaptivity | [`task035_hcurl_goal_oriented_adaptivity/README.md`](task035_hcurl_goal_oriented_adaptivity/README.md) | [`hcurl_adaptive_error_estimators_and_hp_strategy.md`](../notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md) | [`094`](../benchmarks/cases/094_hcurl_goal_oriented_adaptivity/README.md) |
| Task035b high-p/local-hp resource envelope | [`task035b_high_order_local_hp_resource_envelope/README.md`](task035b_high_order_local_hp_resource_envelope/README.md) | Task035b outcomes、Review V1 与 response V2 | [`095`](../benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md) |
| Task035e reference-blind multilevel hp research | [`task035e_reference_blind_multilevel_hp_adaptivity/README.md`](task035e_reference_blind_multilevel_hp_adaptivity/README.md) | [`review_report_v1.md`](task035e_reference_blind_multilevel_hp_adaptivity/review_report_v1.md) | [Case098 historical index @ `cef2793`](https://github.com/Rookie1234567/MyFEniCS/blob/cef2793fbc3157f8b0f65a51a395954fe5cb38bb/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/README.md) |
| MPI/p/algebra regression | 环境/验证章节 | walkthrough 50 | [`040`](../benchmarks/cases/040_mpi_p_algebra_regression/README.md) |
