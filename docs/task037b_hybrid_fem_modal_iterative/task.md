# Task037b：p6/h10 静态凝聚 Hybrid FEM–Modal 迭代求解器

## 0. 任务身份

```text
task                         = Task037b
task_kind                    = SOLVER_DEVELOPMENT
status                       = READY_FOR_CODEX_EXECUTION
base_master_sha              = 454df04358bd4e1670ec14c5b0276b430249cd37
working_branch               = codex/20260807-task37b-hybrid-iterative-development
remote_upstream              = origin/codex/20260807-task37b-hybrid-iterative-development
direct_master_write          = forbidden
merge_to_master              = not_authorized
ordinary_default_change      = forbidden
primary_scope                = original static Hybrid FEM-modal iterative solver
frozen_physics               = 13.5 nm / 10 deg grazing / phi=0 / S polarization
frozen_discretization        = p6 Nedelec / h10 / Case096 exact configuration
frozen_internal_modes        = M120 forward + M120 backward
external_port                = formal Matrix-free Fourier-DtN
outer_solver                 = right FGMRES
preconditioner_family        = approximate block-LDU
Full3D_iterative_research    = closed in Task037; reuse infrastructure only
strong_trace_Hybrid          = out_of_scope
exact_trace_chain_solver     = out_of_scope; correctness oracle only
new_modal_basis              = forbidden
M_sweep                      = forbidden
actual_h_or_p_adaptivity     = out_of_scope
0p7nm_PDE                    = out_of_scope
RCWA                         = out_of_scope
surrogate_or_inversion       = out_of_scope
new_external_dependency      = forbidden
```

Task037b 只研究**原始 static Hybrid FEM–Modal 系统的迭代求解**。它不是把 M120
再次当作 Full3D coarse space，也不是继续 Task036 的 compressed-port、strong-trace
或 exact-trace 研究。

本任务的核心目标是建立：

```text
exact monolithic Hybrid block operator
+ formal Matrix-free external DtN
+ right FGMRES
+ approximate block-LDU preconditioner
+ iterative bottom/top FEM endcap inverses
```

最终 Hybrid 方程必须保持与当前 direct Hybrid 完全相同；近似只允许进入
preconditioner，不能进入 exact operator、接口耦合、M120 propagation、外部 DtN
或 official R/T/A 定义。

---

# 1. 为什么 Task037 的负结果不关闭 Task037b

Task037 Candidate E 使用的是：

```text
Full3D unknowns
+ M120 仅作为 coarse / deflation directions
```

其 E2 证明 M120 action space 几乎不包含 B4 的后期停滞残差，因此该 coarse 路线关闭。

Task037b 使用的是：

```text
bottom FEM unknowns
+ top FEM unknowns
+ M120 modal amplitudes 作为真实系统未知量
```

M120 不再负责近似 Full3D late residual，而是直接承担中间规则区域的物理传播。
在冻结的 10° 掠射、S 偏振、p6/h10 案例中，static Hybrid M120 已经通过
Full3D 的 12/12 功率、12/12 复振幅、接口场和中间场 Gate。因此：

```text
M120 Full3D coarse negative
!=
M120 Hybrid block-system negative
```

Task037b 必须独立验证 Hybrid block iterative，不能沿用 Candidate E 的结论代替运行。

---

# 2. 开始前必须读取的文件

Codex 编码前必须完整读取并在继承审计中概括：

```text
docs/repository_work_principles.md
docs/markdown_rendering_standard.md
docs/task_retrospective_standard.md
docs/iterative_solver_ports.md
docs/project_service_requirements_phase1_scope.md

docs/task037_static_condensed_full3d_iterative/task.md
docs/task037_static_condensed_full3d_iterative/review_report_v7.md
docs/task037_static_condensed_full3d_iterative/review_report_v7_1_task37b_remote_handoff.md
docs/task037_static_condensed_full3d_iterative/response_v7.md
docs/task037_static_condensed_full3d_iterative/outcomes/summary.md
docs/task037_static_condensed_full3d_iterative/outcomes/test_summary.md

docs/task035c_hybrid_channel_memory_closure/task.md
docs/task035c_hybrid_channel_memory_closure/outcomes/p6_h10_channel_closure.md
docs/task035c_hybrid_channel_memory_closure/outcomes/summary.md

docs/task032_hybrid_fem_modal_direct_baseline/task.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
docs/task032_hybrid_fem_modal_direct_baseline/review_report_v2.md

docs/task036_forward_solver_bugfix_hardening/outcomes/final_summary.md
docs/task036_forward_solver_bugfix_hardening/review_report_v8.md

notes/theory/hybrid_fem_modal_domain_decomposition.md
notes/theory/dtn_modal_ports_and_condensation.md
notes/theory/iterative_solver_and_preconditioner.md
notes/theory/maxwell_strong_weak_and_fem.md
```

编码前还必须阅读下列源码，不能只根据本任务书重新实现一套平行系统：

```text
src/solvers/hybrid_local_dtn.py
src/solvers/hybrid_fem_modal_augmented_direct.py
src/solvers/hybrid_fem_modal_schur_direct.py
src/solvers/hybrid_static_field_recovery.py
src/coupling/hybrid_internal_modes.py
src/modes/mode_classification.py
src/modes/stable_propagation.py

src/solvers/condensed_dtn.py
src/solvers/static_local_schur_action.py
src/solvers/static_condensed_iterative.py
src/solvers/physical_slab_two_level.py
src/solvers/hcurl_canonical_vector.py
src/solvers/hcurl_canonical_vector_dolfinx.py
```

任务结果必须维护：

```text
docs/task037b_hybrid_fem_modal_iterative/outcomes/summary.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/test_summary.md
docs/development_progress.md
```

只有第一个完整 Hybrid iterative full pass 产生后，才允许创建：

```text
benchmarks/cases/101_hybrid_iterative_block_solver/
```

在此之前，重型 artifact 只保存在：

```text
benchmarks/artifacts/task037b/
```

不得提交 Git。

---

# 3. Git、文档与继承 Gate

## 3.1 分支身份

任务书提交前，远程分支满足：

```text
branch SHA        = 454df04358bd4e1670ec14c5b0276b430249cd37
origin/master SHA = 454df04358bd4e1670ec14c5b0276b430249cd37
ahead / behind    = 0 / 0
```

Codex 开始时必须确认：

```text
current branch = codex/20260807-task37b-hybrid-iterative-development
upstream       = origin/codex/20260807-task37b-hybrid-iterative-development
worktree       = clean
ordinary default = unchanged
```

所有实现、测试、outcomes 和 response 只能提交到本分支。未经最终 review 和用户授权，
不得 merge 或 push `master`。

## 3.2 文档公式新标准

从本任务开始，所有新建或修改的 Markdown 文档必须遵守：

```text
inline math  = $...$
display math = fenced math block beginning with ```math and ending with ```
```

不得在新文档中使用多行 `$$ ... $$`、`\[ ... \]` 或 `\( ... \)` 作为正式公式格式。
原因是 GitHub GFM 会把数学块内部独占一行的 `=` 或 `-` 抢先解释为 Setext 标题，
导致公式被拆坏。

Codex 的第一个 docs-only commit 必须：

1. 读取最新版 `docs/markdown_rendering_standard.md`；
2. 同步 `README.md`、`docs/README.md` 与 `docs/repository_work_principles.md` 中仍残留的旧 `$$` 默认表述；
3. 更新或增加文档合同测试，使新/修改文档的 display math 使用 fenced `math`；
4. 不批量改写未触碰的历史文档；历史文档在后续被修改时再迁移；
5. 人工检查 GitHub rendered view。

该 docs-only commit 不得夹带 solver 代码。

## 3.3 继承基线审计

开始 solver 修改前创建：

```text
docs/task037b_hybrid_fem_modal_iterative/outcomes/inherited_baseline_audit.md
```

至少记录：

- branch、HEAD、upstream、clean status；
- PETSc `complex128/int32`、DOLFINx、Basix、SLEPc 和 MPI 版本；
- Task037 选择性合入的 11 个 master commits；
- formal Matrix-free DtN 与 M3a 仍为 explicit opt-in；
- Task037 Candidate A–F/E research-only modules未进入 master；
- Task036 strong-trace/exact-trace 仍为 research-only；
- ordinary direct/Hybrid default 未改变；
- focused baseline tests 的命令、exit code 和结果；
- Task037 full pytest 的真实历史为 `849 passed / 48 skipped / 3 failed`，随后三项 targeted closure通过，但没有第二次 full pytest；不得写成继承 full-suite PASS。

最低继承测试：

```text
src/test/test_24_repository_work_principles.py
src/test/test_26_documentation_contract.py
src/test/test_28_direct_memory_telemetry.py
src/test/test_179_task035b_hybrid_static_condensation.py
src/test/test_217_task037_f0_direct_authority.py
src/test/test_218_task037_static_iterative_port.py
src/test/test_219_task037_external_solver_runtime.py
src/test/test_224_task037_static_local_schur_action.py
src/test/test_230_task037_dtn_direct_blocks.py
src/test/test_231_task037_dtn_action_only_port.py
src/test/test_53_task033_high_order_hybrid_components.py
src/test/test_hybrid_interface_audits.py
```

继承 Gate 失败时先停止并分类，不得在已知回归上继续开发。

---

# 4. 冻结物理、离散与直接法权威

## 4.1 冻结模型

所有正式 heavy run 必须精确复用 Case096 的成功 Hybrid M120 配置：

```text
geometry / material       = Case096 frozen p6/h10 rectangular block grating
wavelength                = 13.5 nm
incident theta from normal= 80 deg
incident grazing          = 10 deg
incident phi              = 0 deg
polarization              = S
periodic boundary         = double Floquet
external ports            = top/bottom Fourier-DtN, 40+40 modes
FE degree                 = first-family Nedelec p6
mesh                      = structured h10 / 252 cells
Hybrid middle interval    = frozen Task032/035c 100 nm z-invariant region
internal modes            = M120 forward + M120 backward
local FE backend          = assembly_time_static_condensed
scalar / index            = complex128 / int32
development MPI           = 8
```

不得修改：

- M120 数量、selection、ordering、branch 或 normalization；
- propagation beta、traction beta 或 reference plane；
- external DtN mode set；
- geometry、material、angle、polarization 或 mesh；
- interface位置；
- quadrature、Floquet phase 或 official channel定义；
- static-condensation approximation space。

## 4.2 历史 direct authority

冻结历史结果：

| 路径 | rows | matrix NNZ | factor NNZ | peak GiB | total s | physics |
|---|---:|---:|---:|---:|---:|---|
| Full3D static | 51,272 | 41,989,040 | 212,343,992 | 14.7218 | 260.74 | 12/12 + 12/12 pass |
| Hybrid static M120 | 17,168 | 12,313,232 | 45,293,792 | 7.5443 | 322.78 | 12/12 + 12/12 pass |

Hybrid static M120 还通过：

```text
bottom/top interface tangential E
bottom/top interface tangential H
selected middle-plane E/H
R/T/A and A_volume closure
full explicit true residual
```

逐通道 authority：

```text
benchmarks/cases/096_hybrid_channel_memory_closure/
    records/p6_h10_mpi8_six_path_v1.json
```

complex-amplitude field 固定为：

```text
outgoing_amplitude_at_boundary
```

## 4.3 当前源码 direct Hybrid authority

Stage H1 必须在当前 clean Task037b SHA 上只运行一次：

```text
p6/h10 static Hybrid M120 augmented direct / MPI8
```

其用途是建立当前源码的 direct Hybrid solver authority。必须记录：

- bottom/top FE、external auxiliary、modal和 monolithic rows；
- 各块 shape、matrix NNZ、factor NNZ；
- exact true residual；
- bottom/top local residual；
- modal equation residual；
- modal amplitude vector hash；
- bottom/top condensed vector与恢复后的 full FE vector hash；
- interface E/H 与 selected middle-plane E/H；
- 12/12 powers、12/12 boundary amplitudes、R/T/A；
- setup、factor、solve、recovery、RTA wall；
- process-tree RSS/PSS/USS/swap；
- source SHA、exact command、image/ABI和clean status。

若当前 direct Hybrid 不能通过历史 Case096 合同，停止 Task037b，不得用旧 vector 继续。

不运行 M160，不重跑 p6 standard Hybrid，也不重跑 34 GiB Full3D standard。

---

# 5. 数学求解对象

## 5.1 外部 DtN 先在算子层隐式凝聚

bottom 和 top endcap 各自包含外部 Fourier-DtN auxiliary。对 side
$s\in\{b,t\}$，局部增广系统写成：

```math
\begin{bmatrix}
F_s & C_s^{\mathrm{ext}}\\
D_s^{\mathrm{ext}} & H_s^{\mathrm{ext}}
\end{bmatrix}
\begin{bmatrix}
u_s\\q_s
\end{bmatrix}
=
\begin{bmatrix}
f_s\\g_s
\end{bmatrix}.
```

Task037b 的 exact local operator必须使用 Matrix-free Schur action：

```math
A_s
=
F_s-C_s^{\mathrm{ext}}
\left(H_s^{\mathrm{ext}}\right)^{-1}
D_s^{\mathrm{ext}},
```

```math
b_s
=
f_s-C_s^{\mathrm{ext}}
\left(H_s^{\mathrm{ext}}\right)^{-1}g_s.
```

不显式形成外部 DtN Schur 矩阵，但每次 MatMult必须精确执行：

```math
y=D_s^{\mathrm{ext}}x,
\qquad
z=\left(H_s^{\mathrm{ext}}\right)^{-1}y,
\qquad
A_sx=F_sx-C_s^{\mathrm{ext}}z.
```

收敛后恢复：

```math
q_s
=
\left(H_s^{\mathrm{ext}}\right)^{-1}
\left(g_s-D_s^{\mathrm{ext}}u_s\right).
```

外部 DtN unknowns 不进入 Task037b 的 monolithic Krylov unknown layout。

## 5.2 内部 Hybrid modal unknowns 必须保留

记：

```text
u_b = bottom static-condensed FE trace unknowns
u_t = top static-condensed FE trace unknowns
a   = [a+ ; a-]，240 个内部 modal amplitudes
```

为避免与外部 DtN 的 $C/D/H$ 混淆，本任务统一使用：

```text
T_b, T_t = modal traction -> local FE equation
P_b, P_t = local FE interface trace -> modal equation
G        = internal propagation / E-trace constraint block
```

exact Hybrid block system 为：

```math
\begin{bmatrix}
A_b & 0   & T_b\\
0   & A_t & T_t\\
P_b & P_t & G
\end{bmatrix}
\begin{bmatrix}
u_b\\u_t\\a
\end{bmatrix}
=
\begin{bmatrix}
b_b\\b_t\\g_m
\end{bmatrix}.
```

exact block action 为：

```math
y_b=A_bu_b+T_ba,
```

```math
y_t=A_tu_t+T_ta,
```

```math
y_m=P_bu_b+P_tu_t+Ga.
```

最终 action-only path 不得形成 global monolithic Hybrid AIJ matrix。
允许保留：

- distributed rectangular $T_b,T_t,P_b,P_t$；
- 240×240 dense $G$；
- 240 维 modal vector 当前 last-rank ownership。

不得形成 full-dimensional interface square projector、multiplier或 penalty。

## 5.3 True residual

对候选解 $x=(u_b,u_t,a)$，必须同时计算：

```math
r_b=b_b-A_bu_b-T_ba,
```

```math
r_t=b_t-A_tu_t-T_ta,
```

```math
r_m=g_m-P_bu_b-P_tu_t-Ga.
```

全局 Hybrid true residual：

```math
\rho_{\mathrm{Hybrid}}
=
\frac{
\sqrt{\lVert r_b\rVert_2^2+\lVert r_t\rVert_2^2+\lVert r_m\rVert_2^2}
}{
\sqrt{\lVert b_b\rVert_2^2+\lVert b_t\rVert_2^2+\lVert g_m\rVert_2^2}
}.
```

还必须报告三个 block residual各自的相对值。不得只报告 KSP monitor residual。

---

# 6. Exact operator 与 approximate PC 的强制边界

Task037b 的最重要架构规则是：

```text
exact operator = 固定、线性、与 direct Hybrid 同一离散
approximation  = 只存在于 preconditioner
```

禁止把低精度 local solve藏进 exact modal-Schur MatMult。否则每次算子作用可能变化，
最终不再明确求解同一个 Hybrid 方程。

外层固定为：

```text
right-preconditioned FGMRES
restart = 90 initially
rtol    = 1e-6 for formal full solve
atol    = 0
```

普通 GMRES、TFQMR、BCGS 不作为主路线；若 local PC具有可变性，必须继续使用 FGMRES。

---

# 7. Block-LDU 预条件器

定义：

```math
A
=
\begin{bmatrix}
A_b&0\\
0&A_t
\end{bmatrix},
\qquad
T
=
\begin{bmatrix}
T_b\\T_t
\end{bmatrix},
\qquad
P
=
\begin{bmatrix}
P_b&P_t
\end{bmatrix}.
```

精确 modal Schur 为：

```math
S_m
=
G-PA^{-1}T
=
G-P_bA_b^{-1}T_b-P_tA_t^{-1}T_t.
```

对残差 $(r_b,r_t,r_m)$，approximate block-LDU PC 施加顺序为：

```math
z_b=\widetilde A_b^{-1}r_b,
\qquad
z_t=\widetilde A_t^{-1}r_t,
```

```math
\widehat r_m
=
r_m-P_bz_b-P_tz_t,
```

```math
z_m
=
\widetilde S_m^{-1}\widehat r_m,
```

```math
z_b
\leftarrow
z_b-\widetilde A_b^{-1}T_bz_m,
```

```math
z_t
\leftarrow
z_t-\widetilde A_t^{-1}T_tz_m.
```

若所有近似逆均为精确逆，该 PC 等于 exact block inverse。Task037b 应先用精确版本建立
oracle，再逐步替换 bottom/top inverse。

最终实际 modal approximation冻结为：

```math
\widetilde S_m
=
G-P_b\widetilde A_b^{-1}T_b-P_t\widetilde A_t^{-1}T_t.
```

它只在 setup 中构造一次，使用与在线 PC完全相同的 fixed approximate local inverse。
最终仍是小型 240×240 dense matrix，可用 complex128 LU精确求解。

---

# 8. 软件架构

建议提取职责单一的组件，名称可以调整，但不得创建通用 plugin framework：

```text
HybridIterativeLayout
    复用或抽取 HybridAugmentedLayout 的 pack/split/ownership，不依赖 assembled global A

HybridBlockOperator
    exact MatPython action for [bottom, top, modal]

HybridBlockResidual
    blockwise true residual 和全局 true residual

HybridLocalCondensedAction
    one endcap exact static local-Schur + Matrix-free external DtN action

HybridLocalInverse
    direct oracle 或 iterative approximate inverse 的统一 apply contract

HybridModalSchurApproximation
    构造并求解 240×240 exact/approx modal Schur

HybridBlockLduPc
    施加 approximate block-LDU

HybridIterativeSolution
    bottom/top/modal、DtN auxiliary recovery、field recovery、residual和lifecycle
```

优先复用：

```text
HybridAugmentedLayout
internal_modal_constraint_matrix
internal_modal_rhs_correction
HybridInternalModeCoupling
recover_hybrid_static_local_field
Matrix-free DtN block action
static local-Schur action
canonical vector comparator
Task037 FGMRES lifecycle/telemetry
```

不得复制整份 Task037 runner或 direct Hybrid模块。公共 direct API必须保持不变。

---

# 9. 分阶段执行计划

## H0：继承审计与文档合同同步

完成第 3 节全部要求。不得在 H0 同时修改 solver。

H0 输出：

```text
outcomes/inherited_baseline_audit.md
outcomes/document_rendering_gate.md
```

## H1：当前源码 direct Hybrid M120 authority

按第 4.3 节运行一次 MPI8 direct Hybrid static M120。

H1 Gate：

```text
full explicit true residual <= 1e-9
12/12 powers               = pass
12/12 complex amplitudes   = pass
interface E/H              = pass
middle-plane E/H           = pass
R/T/A and A_volume closure = pass
swap                       = 0
```

失败即停止。

## H2：Exact monolithic Hybrid action

### H2a：assembled-block oracle

先允许使用现有 `bottom_system.A` 和 `top_system.A`，构造不装配 global AIJ 的
Hybrid MatPython action。与 `build_hybrid_augmented_direct_system(...).A` 比较：

- 3 个 deterministic random vectors；
- physical packed RHS；
- 单独 bottom、top、modal block probes；
- pack/split round trip；
- MPI1、MPI2、MPI4 identity。

Gate：

```text
action relative error <= 1e-11
block action errors    <= 1e-11
pack/split error       <= 1e-13
missing/extra rows     = 0/0
```

### H2b：Matrix-free local endcap action

把 $A_b,A_t$ 替换成：

```text
static local-Schur fine action
- Matrix-free external DtN Schur action
```

与 H2a assembled local block 比较，Gate仍为 `<=1e-11`。

H2b通过后，正式 exact Hybrid operator必须满足：

```text
global monolithic A materialized = false
global bottom/top F materialized = false
external explicit C/D            = 0/0
p6 direct factor count           = 0
```

## H3：Exact block-LDU iterative oracle

H3 允许临时保留 bottom/top MUMPS direct factors，仅用于验证 block iterative代数：

1. 构造 exact $S_m$；
2. exact block-LDU作为右 PC；
3. exact Hybrid block operator作为外层 operator；
4. outer FGMRES求解同一 H1 RHS。

Gate：

```text
outer iterations                  <= 3
Hybrid true residual              <= 1e-10
bottom/top/modal block residuals  <= 1e-10
solution vs direct Hybrid         <= 1e-10
modal amplitudes vs direct        <= 1e-10
12/12 powers and amplitudes       = pass
R/T/A                             = pass
```

H3结束后必须释放 direct factors。H3 内存不是最终目标，但必须单独记录。

若 H3失败，分类为 `HYBRID_BLOCK_ITERATIVE_ALGEBRA_FAILED`，停止；不得继续调PC。

## H4：Modal block 的有界诊断

在 bottom/top exact local direct inverse保持不变时，只比较两种 modal block：

```text
H4a = exact S_m
H4b = G-only
```

用途是测量端部反馈对 modal block 的重要性，不作为最终低内存候选扫描。

禁止增加 diagonal、low-rank、M80/M160 或参数化 modal候选。

若 G-only差，不关闭任务；最终仍使用由 approximate local inverse构造的
$\widetilde S_m$。

## H5：bottom/top endcap iterative inverse 资格化

H5 必须先把两个 local inverse作为独立问题测试，不能直接在全系统中盲调。

### H5a：local direct reference

分别对 bottom/top建立 direct reference，但只用于 local solve comparison。

测试 RHS 固定为：

```text
physical local RHS
4 deterministic random RHS
6 fixed modal traction RHS
    - forward low-index propagating
    - backward low-index propagating
    - representative evanescent
    - representative high-index retained mode
```

具体 mode indices须从 M120 frozen ordering确定并写入 record，不得根据结果重选。

### H5b：主要 local iterative candidate

第一候选固定为：

```text
exact matrix-free local operator
+ right FGMRES
+ distributed ASM/RAS with ILU(0) approximate factors
```

允许 assembled sparse matrix仅作为 preconditioner matrix；fine operator仍须
matrix-free。不得使用 MUMPS/SuperLU local direct factor作为最终 candidate。

只允许一个冻结配置：

```text
ASM or RAS choice = 由最小代数测试确定一次
ILU levels        = 0
complex shift     = 继承 Task037 validated sign/convention
inner restart     = 30
inner max_it      = 300 for standalone qualification
```

不得扫描大量 overlap、shift、ILU levels或subdomain count。

H5b Gate，对 bottom/top 和全部冻结 RHS：

```text
finite / deterministic       = true
standalone true residual     <= 1e-8
iterations                   <= 300
no direct fallback           = true
swap                         = 0
```

同时报告：

```text
local rows / matrix NNZ
local factor NNZ / payload
setup and apply wall
RSS/PSS/USS
contraction after 1, 2, 4, 8 fixed applies
```

### H5c：可选 factor-free local refinement

只有 H5b 数值通过、但预计 MPI1 whole-job peak仍高于 2 GiB 时，才允许一个
factor-free refinement：

```text
fixed four-step local FGMRES
+ one already-qualified cheap local PC
```

不得重开 Task037 B2/B4/p2/p4 candidate family，也不得扫描 2/4/6/8 步。
H5c失败不影响 H5b数值基线。

## H6：单侧 iterative replacement

依次运行：

```text
H6b: bottom iterative / top direct
H6t: bottom direct / top iterative
```

两条均使用 exact Hybrid operator、right FGMRES和block-LDU PC。

每条先执行 20/100/200-step funnel：

| stage | Hybrid true residual Gate |
|---|---:|
| 20 | < 0.35 |
| 100 | <= 0.12 |
| 200 | <= 0.05 |

还要求最后 40 步净下降，且预测总迭代不超过 3000。

H6用于定位哪一侧更难。若仅一侧失败，必须记录 side-specific negative，不能把问题
模糊写成“Hybrid iterative整体失败”。

## H7：双侧 iterative + approximate modal Schur

使用 H5 最佳 local inverse，构造：

```math
\widetilde S_m
=
G-P_b\widetilde A_b^{-1}T_b-P_t\widetilde A_t^{-1}T_t.
```

构造时必须：

- 使用与 online PC相同的 fixed approximate inverse；
- 只构造一次 240×240 matrix；
- complex128 dense LU；
- 报告 480 个 local apply 的时间与内存；
- 不使用 direct local factor；
- 不根据 direct solution或当前 residual修改列。

然后执行唯一的双侧 H7 candidate，仍采用 20/100/200 funnel。

通过 200-step后才允许运行完整 MPI8 solve。

## H8：MPI8 full numerical qualification

正式 full solve要求：

```text
outer = right FGMRES restart90
rtol  = 1e-6
max_it= 3000
```

数值 Gate：

```text
reported residual             <= 1e-6
Hybrid true residual          <= 1e-6
bottom local residual         <= 1e-6
top local residual            <= 1e-6
modal equation residual       <= 1e-6
external auxiliary recovery   <= 1e-10 action identity
full FE recovery residual     <= 1e-6
```

与 direct Hybrid比较：

```text
modal amplitude relative L2   <= 1e-5
bottom canonical active/full  <= 1e-5
top canonical active/full     <= 1e-5
interface E/H                 = frozen Gate pass
middle-plane E/H              = frozen Gate pass
12/12 powers                  = pass
12/12 complex amplitudes      = pass
R/T/A and A_volume closure    = pass
```

再与 Full3D static authority比较同一 12+12 和场 Gate。

任何 residual未通过时：

```text
official R/T/A = not_run
```

禁止 global direct fallback后仍写 iterative success。

## H9：Restart 与 MPI 资源资格化

只有 H8 完整通过后，才测试：

```text
restart 90 -> 60 -> 40 -> 20
```

每一档必须复用同一 PC，不改其他参数。迭代次数增加可以接受，但必须完整收敛并通过
所有物理 Gate。选择最小通过的 restart。

随后运行：

```text
MPI4 full
MPI1 full
```

比较必须同 MPI 口径，同时记录绝对峰值。

资源层级：

| 等级 | 目标 |
|---|---:|
| numerical pass | 不以资源阈值否定正确解 |
| MPI8 resource-positive | peak <= 6.0 GiB |
| MPI8 engineering | peak <= 5.0 GiB |
| MPI8 50% stretch vs direct Hybrid | peak <= 3.77 GiB |
| MPI1 primary low-memory target | peak <= 2.0 GiB |
| MPI1 preferred | peak <= 1.5 GiB |

最终 online solve必须满足：

```text
global direct factor count = 0
bottom/top MUMPS factor     = 0/0
ordinary default            = unchanged
swap                        = 0
```

允许 local approximate ILU factors，但必须完整报告 aggregate factor NNZ、payload和重复率。
离线 direct oracle peak与在线 iterative peak必须分开，不得混写。

## H10：solver error 与 Hybrid model error 分离

只有 H8通过后，才从 Task036 已冻结的失败案例中选择**一个**已存在的
small-grazing/P配置，不进行新角度扫描。

运行：

```text
direct Hybrid authority
iterative Hybrid
已有 Full3D authority或最小必要对照
```

分类：

```text
iterative Hybrid ~= direct Hybrid
but Hybrid != Full3D
    -> iterative solver PASS / Hybrid model FAIL

iterative Hybrid != direct Hybrid
    -> iterative solver FAIL
```

不得在 Task037b 中修复原 Hybrid joint-Cauchy不完备，也不得切换 strong-trace或exact-trace。

---

# 10. 停止规则

Task037b 不允许无限扩展候选。

| 停止点 | 分类 | 后续 |
|---|---|---|
| H1 direct authority失败 | inherited correctness regression | 停止 |
| H2 action identity失败 | block operator implementation failure | 修复同一实现，不改算法 |
| H3 exact block-LDU失败 | block iterative algebra failure | 停止，不调PC |
| H5 bottom/top均无法资格化 | local inverse family negative | 停止，不发明新PC家族 |
| H6仅一侧失败 | side-specific local inverse negative | 记录并只允许一次证据驱动修复 |
| H7 200-step失败 | double-iterative block PC negative | 停止重型 full |
| H8 residual失败 | iterative solver negative | official R/T/A not_run |
| H8通过但资源未达标 | numerical success / resource qualification negative | 保留资格边界 |
| H10 Hybrid/Full3D失败但iterative/direct一致 | model error | 不归因迭代法 |

禁止自动增加：

```text
M160/M240
new p2/p4 hierarchy
new modal coarse
new port basis
new Schwarz family
new Krylov family
new overlap/shift sweep
new angle sweep
```

需要新增算法家族时必须等待新的 review，而不是在 response 中自行扩 scope。

---

# 11. 内存与对象生命周期审计

每个正式阶段必须记录同时存活对象，而不是只列 `.nbytes`：

```text
bottom/top static Schur class cache
external DtN action state
T/P rectangular coupling blocks
G and modal Schur
local approximate matrices/factors
FGMRES bases
field recovery cache
canonical export/postprocess
MPI/PETSc runtime
```

必须分别报告：

```text
process-tree RSS
simultaneous worker RSS/PSS/USS
rank historical peak
cgroup current/peak if available
swap
factor NNZ and payload
stage peaks
```

H3 direct oracle、H5 local reference与最终 online solve 的峰值必须分开。

最终候选若在 setup中暂时形成 assembled preconditioner matrix，必须在 outer solve前释放；
但 whole-job peak仍按已经发生的高水位计算，不能用释放后的 current RSS代替峰值。

---

# 12. 测试要求

## 12.1 单元与代数测试

至少新增覆盖：

- Hybrid layout pack/split round trip；
- exact block action vs assembled monolithic AIJ；
- Matrix-free endcap action vs assembled local A；
- blockwise true residual；
- exact block-LDU inverse identity；
- approximate modal Schur construction identity；
- local inverse determinism/finite；
- no global matrix/direct fallback inventory；
- auxiliary recovery；
- canonical bottom/top recovery；
- ordinary defaults unchanged。

## 12.2 MPI tests

至少：

```text
MPI2 block action identity
MPI4 block action identity
MPI2 Matrix-free local DtN
MPI2 layout/modal ownership
MPI2 local inverse
MPI2 canonical comparison
```

## 12.3 PDE tests

按阶段运行：

1. tiny p2 Hybrid block operator smoke；
2. tiny static Hybrid exact block-LDU smoke；
3. p6/h10 H1 direct authority；
4. p6/h10 H6 funnels；
5. p6/h10 H7/H8 full only after Gate。

不得提前运行 H8重型 full。

## 12.4 静态检查

所有 touched Python files：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

## 12.5 Full repository pytest

最终 targeted Gate通过后运行一次无 deselect full pytest。

- 完整通过则记录 PASS；
- timeout则记录 completed count与边界；
- touched-code failure必须修复后停止等待review；
- 不得删除测试、增加新 xfail或放宽数值阈值。

---

# 13. Outcomes 与证据格式

Task进行中持续维护：

```text
outcomes/inherited_baseline_audit.md
outcomes/direct_hybrid_authority.md
outcomes/block_operator_identity.md
outcomes/exact_block_ldu_oracle.md
outcomes/local_endcap_inverse_matrix.md
outcomes/one_sided_replacement.md
outcomes/double_iterative_funnel.md
outcomes/resource_ledger.md
outcomes/test_summary.md
outcomes/changed_files.md
outcomes/summary.md
```

`outcomes/summary.md` 必须表格优先，至少包含：

- 最终状态与范围；
- H0–H10实施矩阵；
- direct/iterative数值表；
- bottom/top/modal residual表；
- channel与field Gate；
- local inverse矩阵；
- MPI/restart/内存表；
- 失败与未运行项；
- merge与下一步决策。

所有数据必须标明：

```text
unit
baseline
data identity = measured / derived / predicted / not_run
evidence path
source SHA
MPI
```

完整场、矩阵、factor和长 residual history留在 ignored artifact目录。

---

# 14. Commit 纪律

建议提交顺序：

```text
docs(task037b): adopt fenced-math documentation standard

test(task037b): freeze inherited Hybrid iterative baseline

feat(task037b): add exact Hybrid block operator and residual

feat(task037b): add exact block-LDU iterative oracle

feat(task037b): add iterative endcap inverse and approximate modal Schur

bench(task037b): qualify Hybrid iterative numerical and resource gates

docs(task037b): record outcomes and response v1
```

每个提交职责单一。不得把任务书、数值实现、重型结果和最终文档压在一个commit中。

---

# 15. 最终验收

Task037b 至少分成三种可能结论：

## 15.1 完整成功

```text
exact Hybrid block operator          = pass
iterative Hybrid vs direct Hybrid    = pass
Hybrid vs Full3D anchor              = pass
12/12 powers + 12/12 amplitudes      = pass
MPI8 full                            = pass
MPI1 peak                            <= 2.0 GiB
ordinary default                     = unchanged
```

## 15.2 数值成功、资源有限

```text
all numerical/physical Gates         = pass
MPI1 peak                            > 2.0 GiB
resource scalability                 = not qualified
```

这是可接受的 `PASS_WITH_RESOURCE_QUALIFICATIONS`，不得包装成0.7 nm能力。

## 15.3 受控负结果

```text
exact block operator                 = pass
exact block-LDU oracle               = pass
iterative local inverses or H7       = fail
```

必须保存为何失败、哪个side失败、残差平台和内存事实，不能只写“不收敛”。

---

# 16. Codex 最终响应

完成本轮授权工作后创建：

```text
docs/task037b_hybrid_fem_modal_iterative/response_v1.md
```

并报告：

```text
branch / tested SHA / upstream / clean status
H0-H10 status matrix
current-source direct Hybrid authority
exact block-action errors
exact block-LDU iteration count
bottom/top local inverse results
one-sided and double-iterative funnels
full residuals and modal residual
modal amplitudes / canonical fields / 12+12 channels
R/T/A and closure
MPI/restart/memory results
all negative and not_run items
serial/MPI/PDE/full-pytest results
changed files and commit list
ordinary defaults unchanged
merge recommendation
```

完成后停止等待 ChatGPT 审阅。不得自行 merge `master`，不得创建 Task037c，
不得启动 0.7 nm PDE。
