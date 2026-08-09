# Candidate H H0：全空间 matrix-free 与 MG 能力审计

本文件只记录 Candidate H 的 H0 能力审计，不实现 H1/H2，不运行新的 PDE，也不把
任何 API 存在写成数值或物理通过。Candidate H 与已经关闭的 G2 LOR-HX 路线是不同
对象：它面向未静态凝聚的完整 p6 Nédélec 全空间 action。

## 1. 审计身份与冻结边界

| 项目 | H0 结论 |
|---|---|
| 执行分支 | `codex/20260806-task37-iterative-extra-development` |
| HEAD | `a203794089cd8615206cfb8a0a2b7b9311348206` |
| upstream | `origin/codex/20260806-task37-iterative-extra-development`，同 SHA |
| ahead/behind | `0/0` |
| 启动 Gate 工作树 | clean |
| 当前审阅前状态 | 仅本文件 untracked；没有其他本地修改 |
| Review V1 | [review_report_v1.md](../review_report_v1.md)，接受 G2 负结果与停止边界 |
| 当前 consolidated 身份 | [response_v1.md](../response_v1.md)，`G2_final_classification=G2_FAIL` |
| G2 | `G2_FAIL`，不得改写为 partial/pass |
| G3 | `not_started_and_prohibited_by_G2_FAIL` |
| 旧 G4 | failed LOR-HX 上的 sweep、shift/cycle/smoother 调参均 prohibited |
| ordinary default | unchanged；Candidate H 只能是显式、隔离的研究路径 |
| H0 判定 | `H0_PASS`，仅表示 capability-only；不表示 H1/H2 数值通过 |
| H1.1 | unlocked；必须先通过 H1.1 才能讨论 H1.2 |

Review V2 的最高优先级合同为
[review_report_v2.md](../review_report_v2.md)。它只授权 bounded Candidate H component/oracle
development；第一轮不授权 full p6 PDE、H3、H4、G3 或任何 G2/LOR-HX 重开。

## 2. 本轮 measured capability probe

所有 probe 均在同一 shell 中执行：`source scripts/activate_myfenics_wsl.sh`；没有真实
mesh、FE form、PDE、KSP solve 或 heavy MPI run。

| 项目 | measured 结果 | 解释 |
|---|---|---|
| qualified marker | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` | activation contract 满足 |
| Python | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` | 当前仓库 `.venv` 解析到该 qualified target |
| PETSc scalar/int | `complex128` / `int32` | 与 Candidate H complex ABI 要求一致 |
| Linux ABI | petsc4py、slepc4py、dolfinx、mpi4py、Basix 均来自 `/usr/...` Linux 栈 | 未发现 Windows Python/MPI 混入 |
| MatPython/Vec | `COMM_SELF` 创建 2x2 MatPython，`y=2x` 得到 `[(2+0j),(4+0j)]`，随后 Mat/Vec destroy | tiny lifecycle/action capability；不是 FE action 证明 |
| PCMG type | `PETSc.PC.Type.MG` 成功设置，`getType()` 为 `mg` | PCMG binding 可用 |
| PCMG controls | `setMGLevels`、`setMGType`、`setMGCycleType`、`setMGInterpolation`、`setMGRestriction`、`getMGSmoother`、`getMGCoarseSolve` 均存在 | custom interpolation/restriction 的 API 入口存在 |
| MPI communicator | `mpi4py.COMM_SELF.Split` 得到 size/rank=`1/0`；PETSc communicator 有 `tompi4py()` | communicator split 与 PETSc/mpi4py 互操作可用 |
| coarse communicator 限制 | 当前 petsc4py `PC` 未暴露 `setMGCoarseSolveMat` 或直接 coarse-communicator setter | 不能假称 coarse-rank MG 已可用；后续先采用同 communicator 或做窄 capability 设计 |

默认沙箱第一次启动 PETSc 时 PMIx listener 被权限拒绝；没有进入 FE/PDE。按环境规则在
qualified WSL 权限下重做上述 tiny `COMM_SELF` probe 后全部结果如表，故这不是数值
blocker，也不是一次 PDE retry。

## 3. 既有实现边界

| 既有路径 | 状态 | 可复用内容 | 不能冒充的内容 |
|---|---|---|---|
| `src/solvers/hcurl_assembly_time_condensation.py` | inherited capability | FFCx complex128 cell tensor、cell dof map、Basix/DOLFINx orientation、`_tabulate_cell_tensor`/raw class tabulation 的实现事实 | 当前路径形成 `Aii/Ait/Ati/Att` 并做 static condensation；不是未凝聚全空间 matrix-free action |
| `src/solvers/hcurl_canonical_vector_dolfinx.py` | inherited capability | full-FE canonical packet、cell permutation、Basix `T_apply`/`Tt_apply`、物理 entity identity | packet extraction/reconstruction 不是 MatMult 内的 element-local action，也不证明 H1 |
| `src/constraints/floquet_3d_high_order.py` | qualified identity | 统一 geometry tolerance、p6 physical entity/translation identity | 不提供 full p6 operator action |
| `src/constraints/high_order_floquet_trace.py` | qualified identity | `PhaseIndependentConstraintBlock`、edge/face/corner physical identity 与 phase convention | TraceConstraintMap 或 active row ID 不能被用来猜 Candidate H 的 full DoF action |
| `src/constraints/floquet_3d.py` | qualified lower-order identity | hexa edge orientation、periodic phase、entity map 的现有约束机制 | 低阶 periodic builder 不是 p6 full-space action |
| `src/solvers/condensed_dtn.py`；[Task037 E0 closeout](../../task037_static_condensed_full3d_iterative/response_v6.md) | inherited component capability | MatPython/lifecycle 与 synthetic/component action 可复用 | Task037 E0 formal 80-mode Gate 因 `MatPython.getInfo()` telemetry implementation failure 未闭合；不能写成 formal 80-mode qualification，但不阻塞当前 H1 full-space volume-action fixture |
| `src/solvers/static_condensed_iterative.py`、`src/solvers/hcurl_p4_core_global_partial_condensation.py`、`src/test/test_222_task037_assembled_fgmres_core.py` | inherited MatPython/PC hooks | 现有 MatPython operator、PC context 与 coarse-action wiring 的实现样本 | 它们仍属于 condensed/partial-condensed solver；未证明 Candidate H 的 full p6 action 或 PCMG coarse communicator |
| `src/solvers/static_fullspace_slab_factor_oracle.py` | inherited audit reference | owner-local row order、局部 full block products、factor object lifetime | 它是单 slab assembled SeqAIJ/factor oracle，不是 global full-space matrix-free action |
| `src/solvers/mpc_form_action.py` | inherited form action | UFL/MPC action 的公共装配入口 | `assemble_vector(action(a,x))` 仍不是 Candidate H 要求的低层 element-local partial action |
| `src/solvers/static_lor_hcurl_transfer.py`、`static_lor_hcurl_hx.py`、`static_lor_h1_*` | G2 closed / prohibited for H | 仅保留为历史身份和负结果参考 | LOR edge space、slab trace lift、scalar/vector H1 hierarchy、LOR-HX 不得复用为 Candidate H |
| `src/solvers/hcurl_multilevel.py`、`static_trace_auxiliary.py`、`static_p2_slab_pc.py` | research/old candidate boundary | 可参考已有 review 中的失败模式 | 同网格 p2 coarse、trace Galerkin、旧 multilevel prototype 不是 H full-space smoother/MG 证据 |

Candidate H 的第一步必须直接面向完整 p6 Nédélec unknowns：不静态凝聚、不构造 global
p6 matrix、不保存 FE-sized Python global vector，不使用 G2 的 LOR-HX hierarchy。

## 4. 历史内存基线：inherited，不是 Candidate H 结果

这些数字用于 H0 的风险背景和后续 payload 对照；它们没有被本轮重新测量，也不构成
Candidate H action 通过。

| 历史 authority | record/source | process-tree memory | 本轮语义 |
|---|---|---:|---|
| Full3D standard | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json`；source `244b62e1fb4f299a468363cf90a2dd548dc34ff6` | 约 `34.041 GiB`（record 精确值 `34.04121017456055 GiB`） | inherited historical full standard reference |
| static direct v2 | `benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v2.json`；source `2631a4c47258c9def919530787e409774b8ce029` | `15.059223175048828 GiB` | inherited static-direct authority；不是 H action evidence |
| ordinary M3a MPI1 | [g0_residual_and_contraction_authority.md](g0_residual_and_contraction_authority.md) 的 ordinary full baseline 段；source `77d39cbe461204f9e095fb6596ad5b617279d302`；raw run `g0_m3a_mpi1_full_77d39cbe`；12+12 compact checker 为 `benchmarks/cases/101_task37_extra_development/records/g0_m3a_mpi1_full_channels.json`，不承载内存 authority | `4.767307281494141 GiB` | inherited same-machine M3a denominator；不是 Candidate H smoother evidence |

Full standard/static direct/M3a 的 static condensation、ILU 或 ordinary solve 成功均不能
推出 Candidate H 的 element-local action 或 MG 稳定性。

## 5. Candidate H H0 之后的最小依赖链

| 阶段 | 必须先满足 | 允许内容 | 明确不做 |
|---|---|---|---|
| H0 | 本审计、ABI/API capability 与生命周期边界清楚 | 文档审计；无新 PDE | 不实现 action/MG |
| H1.1 | H0；p2/p3 structured hexa fixture | 独立 assembled tiny reference 对照 matrix-free action；orientation、Floquet、material、serial/MPI2 | 不跑正式 p6，不做 KSP/official RTA |
| H1.2 | H1.1 全部通过 | p6/h10 action-only；3 个 deterministic vector + 1 个 physical-RHS-like vector；MPI1/MPI2 identity | 不求解、不生成 official field/RTA、不保留 global/cell dense matrix |
| H2 | H1.1 与 H1.2 全部通过 | 只对 coercive proxy 做 exact class-reused block smoother；固定一 pre/一 post | 不接原 time-harmonic FGMRES，不做 H3/H4 |

H1.1 的核心 algebraic Gate 是 assembled 与 matrix-free action 的相对误差不超过
`1e-11`，并且 finite、deterministic、orientation/Floquet identity 与 MPI 分区一致。
H1.2 还要求 global full/condensed matrix 均不物化、无 cell dense 882x882、无 slab
factor，retained numeric payload `<=0.50 GiB`，action-only process-tree peak
`<=1.25 GiB`。

H2 使用 task.md 冻结的正质量 coercive proxy：

```math
B_h = K_{curl,h} + k_0^2 M_{|\epsilon|,h}.
```

它不是原始 time-harmonic DtN 方程。H2 只允许 exact class-reused element-block
smoother、确定性 coloring、固定一次 pre/post；source 至少包括 gradient-dominated、
curl-dominated、mixed 与 checkerboard/high-frequency。Gate 为 high-frequency
`rho<=0.70`、mixed `rho<=0.85`、class 数不随重复/细化增长、block-factor payload
`<=0.25 GiB`，且一次 smoother apply 不超过一次 matrix-free action 的 20 倍。

## 6. H0 判定与 hard stop

| 判定项 | 结果 |
|---|---|
| element-local p6 action 可实现性 | `capability-only: 可实现；待 H1.1/H1.2 证明`。现有 cell kernel、orientation、Floquet identity、MatPython 生命周期和无新依赖路径足以进入 tiny fixture；没有把它写成已实现或已通过 |
| coarse communicator | `constraint`。generic MPI split 可用，但当前 petsc4py 没有直接 PCMG coarse-rank setter；未假称该能力，通过同 communicator 的最小路径继续审查 |
| 新依赖/ordinary default | 无新依赖；ordinary default unchanged |
| H0 | `H0_PASS`，仅能力审计范围 |
| H1.1 | `unlocked` |
| H1.2/H2 | `not_yet_qualified`，必须等待前序 Gate |
| G2/G3/G4 | G2_FAIL 冻结；G3 与旧 G4 sweep 均 prohibited |

下列任一项出现即关闭 Candidate H 当前阶段，不得通过调参掩盖：H1 action error
`>1e-11`、非有限或不确定、orientation/Floquet/transfer 不一致、payload/峰值超限、
global/cell/slab dense object 被长期保留、per-cell factor、class 数随规模增长、
H2 rho 超限、需要 20--90 步 local Krylov、或要求修改 ordinary default/安装新依赖。

本轮没有执行 H1.1；`H1.1 unlocked` 只表示 H0 的能力和治理前置条件已满足，不表示
任何 numerical/physics Gate 已通过。
