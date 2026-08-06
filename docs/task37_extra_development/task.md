# Task037-extra：p6 静态凝聚 Full3D 低内存迭代法扩展研发

## 0. 任务身份与永久分支边界

```text
task                         = Task037-extra
task_kind                    = ISOLATED_RESEARCH_SOLVER_DEVELOPMENT
status                       = READY_FOR_CODEX_EXECUTION
repository                   = Rookie1234567/MyFEniCS
working_branch               = codex/20260806-task37-iterative-extra-development
working_directory            = docs/task37_extra_development
write_other_branch           = forbidden
create_child_branch          = forbidden
push_other_branch            = forbidden
pull_request                 = forbidden
merge_to_master              = permanently_not_planned
cherry_pick_to_master         = forbidden_without_new_user_instruction
rebase_onto_master            = forbidden_without_new_user_instruction
sync_from_original_task37     = forbidden_without_new_user_instruction
ordinary_default_change      = forbidden
production_qualification     = not_assumed
primary_target               = p6/h10 static-condensed Full3D iterative solver
primary_research_question    = replace or reduce p6 trace-slab ILU storage without losing convergence
frozen_physics               = 13.5 nm / theta 80 deg from normal / phi 0 / S polarization
frozen_discretization        = Case100/Task037 p6 Nedelec / h10 structured hexa / 252 cells
Hybrid_direct_or_iterative   = out_of_scope
0p7nm_PDE                    = out_of_scope
surrogate_or_inversion       = out_of_scope
new_external_dependency      = forbidden_by_default
```

本分支是一个**长期隔离的实验分支**。本任务的代码、测试、记录和文档只允许提交并推送到：

```text
codex/20260806-task37-iterative-extra-development
```

不得创建新的 Codex 子分支，不得创建 PR，不得合并或准备合并到 `master`，也不得把实验提交
cherry-pick 到其他分支。后续 ChatGPT 对话和另一台机器上的 Codex 开发均以本分支为唯一工作对象。

本任务允许产生失败候选和研究性代码。目标是把每条路线做到**可判定**，而不是强行得到正结果。
任何负结果都必须保留最小证据、明确停止，不得修改物理、降低精度、减少通道或放宽真残差来制造成功。

### 0.1 Codex 启动时必须执行的 Git 检查

开始编码前执行并记录：

```bash
git fetch origin
git checkout codex/20260806-task37-iterative-extra-development
git branch --show-current
git status --short
git rev-parse HEAD
git rev-parse @{upstream}
git rev-list --left-right --count HEAD...@{upstream}
git remote -v
```

要求：

- 当前分支必须精确等于本任务分支；
- upstream 必须是同名 `origin` 分支；
- 开始正式测试前 ahead/behind 必须为 `0/0`；
- 工作树必须 clean；
- 若发现其他机器已经推送新提交，先 `git pull --ff-only`，禁止 rebase 和 force push；
- 若存在不能 fast-forward 的分叉，停止并记录，不得自行改写远程历史。

### 0.2 Markdown 公式规则

GitHub 文档中的块公式统一使用：

~~~markdown
```math
A x=b
```
~~~

禁止新写 `\[ ... \]` 或 `$$ ... $$` 公式块。多行块公式同样放在以 `math` 标注的三反引号
fenced block 中。普通命令、路径和日志使用 `~~~text` 或三反引号文本块，避免与数学渲染冲突。

---

## 1. 继承事实：哪些已经成功，哪些已经被否定

本任务不是从零开始。Codex 必须先阅读以下文档，不得重复已经有充分负证据的路线：

```text
docs/task037_static_condensed_full3d_iterative/task.md
docs/task037_static_condensed_full3d_iterative/review_report_v1.md
docs/task037_static_condensed_full3d_iterative/review_report_v2.md
docs/task037_static_condensed_full3d_iterative/review_report_v3.md
docs/task037_static_condensed_full3d_iterative/review_report_v4.md
docs/task037_static_condensed_full3d_iterative/review_report_v5.md
docs/task037_static_condensed_full3d_iterative/review_report_v6.md
docs/task037_static_condensed_full3d_iterative/response_v6.md

docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/summary.md
docs/task030_multilevel_hcurl_low_memory_iterative_solver/review_report_v3.md
docs/task031_compact_physical_slab_memory_optimization/outcomes/summary.md

docs/task009_iterative_solver_profile_screening/review_report.md
docs/task011_low_memory_ams_hx_iterative_solver/review_report.md
docs/task013_real_split_ams_hx_qualification/review_report.md
docs/task014a_real_split_stage4_reduced_block_pc/review_report.md
docs/task015_boundary_aware_pc_diagnostic/review_report.md
docs/task016_zero_order_lifted_coarse_correction/review_report.md
docs/task017_petrov_adjoint_coarse_correction/review_report.md
docs/task018_true_fe_sampled_schur_krylov_integration/review_report.md
docs/task019_p2_h5_true_fe_sampled_schur_qualification/review_report.md
docs/task021_target_geometry_aux_residual_coarse_p2/review_report.md
docs/task022_p2_h2_schur_pc_preflight/review_report.md
docs/task023_petsc_mpi_fe_response_pc/review_report.md
docs/task024_engineering_iterative_solver_fast_track/review_report_v2.md
```

### 1.1 当前唯一完整通过的 Task37 迭代基线

当前完整数值和物理 Gate 通过的迭代方案仍是 M3a：

```text
exact p6 static-condensed matrix-free fine action
+ 16 overlapping physical trace slabs
+ owner-local p6 slab ILU(0) factors
+ fixed two-step fine smoother
+ fixed 75D Floquet/wave coarse correction
+ right FGMRES
```

冻结参考事实：

| 项目 | M3a 参考值 |
|---|---:|
| full FE DoFs | 173802 |
| active trace rows | 51192 |
| auxiliary rows | 80 |
| p6 slab factor NNZ | 91415952 |
| MPI1 full peak | 约 4.6005 GiB |
| MPI1 outer iterations | 约 352 |
| MPI4 full peak | 约 8.2658 GiB |
| full residual / RTA / channels | pass |

这些数值是历史权威；本任务若要比较内存百分比，仍必须在新机器上补一个同机 M3a 基线，不能把不同
机器、不同采样器的数字当作严格 A/B。

### 1.2 已确认的结构性事实

1. **Matrix-free fine action 已经成立。** 不形成全局 p6 fine matrix 不会改变方程；失败的不是
   matrix-free action，而是 factor-free PC 的近似逆能力不足。
2. **p6 factor-free storage 已经成立。** B2/B4 能做到 p6 slab matrix/factor/NNZ 为零，但 B2
   长跑 2500 步仍停在约 `0.1563`，B4 200 步约 `0.1406`。
3. **简单 p2/p4 additive correction 已被否定。** Candidate D 的局部 p2 inner PC 比 B4 更差；
   Candidate F 的 p4 correction 在 low/high/mixed source 上放大残差。
4. **普通黑盒 PC 已被充分筛选。** Jacobi、BJacobi、普通 ASM/ILU、local LU、GAMG、简单
   FieldSplit、BiCGStab/TFQMR 等没有形成可用 Stage4 求解器。
5. **普通能量谱粗空间已失败。** Task027 的 GenEO、interface harmonic、energy eigenmode、HPDDM
   Ritz 等没有捕获真实 Floquet/波传播慢误差；固定 75D wave coarse 反而有效。
6. **普通 p/h coarse 和 patch 已失败。** Task030 的 792D p/h coarse、layer/column/cell patch 等
   明显不如原 slab+wave 框架。
7. **AMS/HX 不能被简单写成“已失败”。** FE-only real-split same-H1 AMS 曾有正信号；但它单独
   预条件完整 FE+DtN coupled system 时不够强。当前尚未测试“p6 slab full-space LOR-HX”。
8. **FE response 质量决定 Schur/coupled correction 成败。** Task021–Task023 证明高质量
   $A_{FE}^{-1}$ 近似可以让 coupled Schur 成功，低质量 ASM/ILU response 甚至会给出错误方向。
9. **Candidate E 没有得到科学容量结论。** V6 在正式 80-mode Matrix-free DtN Gate 中因
   `MatPython.getInfo()` 遥测调用产生 PETSc Error 56，M120 coarse 未运行；不得把它写成科学失败。

### 1.3 本任务禁止原样重复的路线

以下路线不得重新做无边界参数扫描：

- Jacobi/BJacobi/普通 ASM/GAMG/普通 black-box AMG；
- 将 local GMRES 从 4 步盲目增加到 20、40、90；
- 当前 p2/p4 additive correction 的阶数扫描；
- 普通 energy GenEO/interface harmonic coarse；
- 继续扫描 slab 数、overlap、restart；
- aux-only/modal-only correction；
- 把 p6 ILU factors 写盘并在每次 PC apply 中反复读取；
- 通过减少 DtN modes、降低 fine operator 精度或放宽真残差改善结果；
- 在没有 one-slab contraction 正信号前直接启动 16-slab LOR-HX full solve。

---

## 2. 数学对象与扩展路线的准确含义

### 2.1 外层方程保持不变

Task37 静态凝聚后，外层仍求：

```math
A_t x_t=b_t,
```

其中 $x_t$ 是 51192 个 active p6 trace unknowns；80 个 DtN auxiliary unknowns按当前精确
condensed/augmented 代数处理。所有新 PC 都只能改变：

```math
r\longmapsto M^{-1}r,
```

不得改变 $A_t$、$b_t$、物理、网格、Floquet、DtN 或 official 后处理。

### 2.2 当前局部 trace-slab ILU

第 $j$ 个 slab 的局部 shifted trace operator 记为：

```math
S_j=R_j\left(A_t-i\sigma D_t\right)R_j^T.
```

M3a 保存：

```math
S_j\approx L_jU_j,
```

并反复使用：

```math
z_{t,j}=U_j^{-1}L_j^{-1}R_jr.
```

本任务的主要目标是减少或取消这 16 套 p6 trace ILU 的长期存储，同时保持足够强的
$S_j^{-1}$ 近似。

### 2.3 slab full-space 不是把外层改回 Full3D

对一个 slab，在静态凝聚前的局部 full-space unknowns 分为 interior 和 trace：

```math
\mathcal A_j=
\begin{bmatrix}
A_{ii}^{(j)} & A_{it}^{(j)}\\
A_{ti}^{(j)} & A_{tt}^{(j)}
\end{bmatrix}.
```

若需要求：

```math
S_jz_{t,j}=r_{t,j},
```

可以等价地求局部 full-space 问题：

```math
\mathcal A_j
\begin{bmatrix}
z_{i,j}\\z_{t,j}
\end{bmatrix}
=
\begin{bmatrix}
0\\r_{t,j}
\end{bmatrix},
```

最后只提取 trace correction。匹配同一局部边界、shift 和 constraint 时：

```math
S_j^{-1}=R_t\mathcal A_j^{-1}R_t^T.
```

因此：

- 外层仍只求 global trace；
- full-space 只在一个 slab 的 PC 内部临时使用；
- 不是“full-space ILU 减去 interior”；
- 不是把整个 140 nm Full3D 重新作为外层未知量；
- 一个 slab 保留完整 $x$-$y$ 横截面，但只覆盖约 $1/16$ 的 $z$ 高度加 overlap。

### 2.4 LOR-HX 替代对象

LOR（low-order refined）将一个 p6 hexa 单元内部表示为许多 lowest-order Nédélec 子单元。
它不一定显著减少最细层 DoFs，而是把高阶宽 stencil 转成低阶局部 stencil。

设：

```math
T_j:V_{LOR,j}\rightarrow V_{p6,full,j}
```

是 LOR 到 p6 slab full-space 的稳定映射，$B_{HX,j}^{-1}$ 是在 LOR 空间上的 H(curl)
辅助空间/V-cycle 近似逆。目标局部 PC 为：

```math
M_{j,LOR-HX}^{-1}
=
R_tT_jB_{HX,j}^{-1}T_j^HR_t^T.
```

理想数据流：

```text
trace residual
-> zero-interior/full-slab RHS
-> restrict/prolong to LOR space
-> H(curl) V-cycle
   -> cheap fine smoother
   -> gradient/H1 auxiliary correction
   -> vector-H1 auxiliary correction
   -> progressively coarser levels
   -> small coarsest-level exact solve only
-> map back to p6 slab full-space
-> extract trace correction
```

硬性要求：

```text
fine p6 trace factor count = 0
fine p6 full-space factor count = 0
fine LOR large ILU/LU factor count = 0
coarsest small factor = allowed and must be inventoried
```

### 2.5 G4 sweep 的含义

G4 不是“只求一个 slab 并把解插值成全场”。它是在一次 PC apply 中依次处理全部 slab：

```math
r^{(0)}=r,
```

```math
z_j=M_j^{-1}R_jr^{(j-1)},
```

```math
r^{(j)}=r^{(j-1)}-AR_j^Tz_j,
\qquad j=1,\ldots,16.
```

forward/back sweep 需要约 16 或 32 次局部 solve。其优势是每处理一个 slab 就立即传播误差，且在
流式实现中可能只同时保留一到少数 slab 的 workspace。它降低的是**峰值常驻资源**，不是把总工作量
变成 Full3D 的 $1/16$。

---

## 3. 成功标准与资源目标

### 3.1 数值与物理 Gate

任何最终候选都必须满足：

```text
KSP reason > 0
reported residual <= 1e-6
condensed true residual <= 1e-6
full augmented true residual <= 1e-6
full FE true residual <= 1e-6
finite complex128 solution
same 80 DtN mode identity
R/T/A and volume absorption closure pass
12/12 significant powers pass
12/12 significant boundary complex amplitudes pass
canonical active-trace and recovered-field comparison pass
no swap
```

screen 阶段未达到 $10^{-6}$ 时禁止输出或包装 official R/T/A。

### 3.2 内存目标

新机器必须先生成同机 M3a MPI1 baseline。以同机 baseline $M_{M3a}$ 为分母：

```text
minimum engineering signal       = peak <= 0.75 * M_M3a
primary target                   = peak <= 0.50 * M_M3a
stretch target                   = peak <= 2.0 GiB
```

按历史 4.6005 GiB 粗略对应：

```text
minimum signal                   ~ 3.45 GiB
primary half-memory target       ~ 2.30 GiB
stretch                          <= 2.0 GiB
```

跨机器历史数字只能作为背景，不得替代同机 A/B。

### 3.3 时间目标

本任务以低内存优先，但不接受无限时间。最终 full candidate：

```text
preferred wall                  <= 2.0 * same-machine M3a wall
maximum acceptable research wall <= 4.0 * same-machine M3a wall
```

超过 4 倍只能保留为 controlled resource negative，不得称为工程候选。

### 3.4 one-slab oracle Gate

对同一个真实 residual $r_j$，定义：

```math
\rho(M,r_j)=
\frac{\left\|r_j-S_jM^{-1}r_j\right\|_2}{\left\|r_j\right\|_2}.
```

以当前 trace ILU 为 authority、B4 为低内存负基线。LOR-HX 至少满足：

```text
minimum contraction signal:
    rho_LORHX <= (2/3) * rho_B4
    on real B4 long-tail-like residual and mixed/high source

strong contraction signal:
    rho_LORHX <= 2.0 * rho_ILU
    on at least two real residual snapshots

memory signal:
    retained one-slab hierarchy payload <= 0.60 * one-slab trace-ILU payload

apply-time signal:
    one or two V-cycles <= 10 * one-slab ILU apply time
```

G2 未达到 minimum contraction signal 时，禁止进入 G3。

---

## 4. 输出目录与证据规则

新增文档目录：

```text
docs/task37_extra_development/outcomes/
```

新增 benchmark 建议目录：

```text
benchmarks/cases/101_task37_extra_development/
```

若 `101` 已被占用，使用当前分支中下一个空闲编号，并在 outcomes 中记录原因。

重型文件必须保持 gitignored：

```text
residual vectors
mesh/VTU/XDMF/HDF5
PETSc binary matrices
factor files
large timelines
raw stdout/stderr
```

Git 中只保存：

- compact JSON/CSV；
- SHA256、shape、dtype、global index identity；
- source commit、完整命令、环境和 image digest；
- process-tree RSS/PSS/USS/swap；
- 阶段判定和失败原因；
- 小型 deterministic fixture；
- 必要的文档和测试。

每个正式运行前：

```text
HEAD == upstream
worktree clean
ahead/behind = 0/0
qualified activation = pass
PETSc ScalarType = complex128
PETSc IntType recorded
swap = 0 before run
```

每一阶段完成后提交并推送到本分支，不得积累大量未提交实验。

---

# 5. 执行路线 G0–G7

## G0：冻结真实残差、M3a 权威和 PC contraction authority

### G0.1 分支与继承审计

创建：

```text
docs/task37_extra_development/outcomes/g0_inherited_baseline_audit.md
```

至少记录：

- 本分支 HEAD/upstream/clean；
- 相对 `master` 和原 Task37 分支的 ahead/behind；
- 当前 Task37 tests、records 和 known negative candidates；
- V6 E0 是 implementation failure，不是 Candidate E scientific failure；
- ordinary defaults 未改变；
- 本分支永久不合并策略。

### G0.2 新机器同机 M3a baseline

执行顺序：

1. M3a MPI1 setup/20-step screen；
2. 若峰值低于机器安全 Gate且 residual/action identity 正常，运行一次 MPI1 full；
3. 记录 process-tree RSS/PSS/USS、factor NNZ、iterations、wall、full numerical/physics Gate；
4. 不重复 full run，除非首次因明确实现错误而非资源/科学 Gate 失败。

该结果是本任务所有内存百分比的同机 authority。

### G0.3 真实 residual snapshots

必须输出 ownership-independent 的 active-trace true residual snapshots：

```text
M3a: iteration 0, 20, 100, and one late/converged-cycle snapshot
B4:  iteration 20, 100, 200
B2:  historical i2500 vector only if an existing raw artifact can be hash-verified;
     do not rerun 2500 iterations solely to regenerate it
```

每个 snapshot 至少记录：

```text
global active row IDs
complex128 values
norm
iteration
profile
source SHA
SHA256
canonical ordering rule
```

若 B2 i2500 vector 不存在，明确标记 `not_available_without_prohibitive_rerun`，使用 B4 i200 和
B2/B4 bounded screen 的最慢 harmonic Ritz/residual direction 代替。

### G0.4 逐 slab authority

对每个真实 residual：

- 计算 16 个 slab 的局部 residual norm；
- 计算当前 trace ILU one-apply contraction；
- 计算 B4 local GMRES(4) one-apply contraction；
- 做逐 slab ILU ablation/sensitivity，判断哪些 slab 对全局 contraction 最关键；
- 记录 one-level、two-level 和 wave-coarse 前后的 contraction；
- 冻结“最困难 slab”和一个普通 control slab。

输出：

```text
docs/task37_extra_development/outcomes/g0_residual_and_contraction_authority.md
benchmarks/cases/101_task37_extra_development/records/g0_*.json
```

G0 不改变任何 solver 算法。

---

## G1：低风险工程收益——exact factor reuse 与 mixed-precision oracle

G1 不替代 G2，但先取得可能的低风险收益。

### G1.1 Exact factor reuse

重新测量当前分支和新机器上的 16 个 factor fingerprints。只有以下全部精确一致时才允许共享：

```text
row count
row global IDs and order
column structure
numeric values
shift
material/cell-class identity
factor ordering
factor values or deterministic factor fingerprint
```

禁止 approximate factor sharing。

若存在 exact duplicates：

- 只保存一份 factor object；
- 多个 slab 持有只读引用；
- 使用引用计数和幂等 destroy；
- action relative error `<=1e-12`；
- full M3a numerical/physics identity必须保持；
- 记录按实际字节加权的节省，不得简单按 `duplicate_count/16` 推断。

### G1.2 Mixed-precision factor 只做能力和 one-slab oracle

Fine operator、outer solution、true residual、R/T/A 必须继续 complex128。

仅允许把**局部 approximate PC factor values** 尝试存为 complex64。当前 PETSc build 的 scalar type 是
全局固定的；若不能安全创建/应用 complex64 local factor，记录 capability stop，不得通过复制到 Python
对象、反复 cast 或改变全局 PETSc ABI强行实现 full run。

one-slab Gate：

```text
action deterministic and finite
rho_mixed <= 1.25 * rho_complex128_ILU
factor payload reduction >= 30%
no change to fine operator or RHS
```

通过 one-slab 后最多运行一个 20/100-step global screen；未通过则关闭 mixed-precision lane。

输出：

```text
docs/task37_extra_development/outcomes/g1_factor_storage.md
```

---

## G2：一个 slab 的 full-space LOR-HX oracle

G2 是本任务主线。只在 G0 authority 完成后开始。

### G2.1 选择 slab

主 slab 必须来自 G0 的真实 B4/M3a residual sensitivity，而不是固定选 top/bottom：

```text
primary slab = largest persistent residual / largest ILU ablation damage
control slab = median residual / ordinary sensitivity
```

### G2.2 full-space slab 与 trace slab 的代数 identity

构造一个 slab 的 uncondensed p6 full-space operator，但不得形成整个 Full3D uncondensed global matrix。
必须一致处理：

- overlap 和 parent cells；
- interior/trace DoF maps；
- Basix entity orientation；
- Floquet slave/master phase；
- artificial slab boundary；
- current local shift；
- material和quadrature；
- MPI owner/local row identity。

在 tiny fixture 和真实 primary slab 上验证：

```math
S_jv
\approx
R_t\mathcal A_j
\begin{bmatrix}
-A_{ii}^{-1}A_{it}v\\v
\end{bmatrix}.
```

要求 3 个 deterministic vectors 和一个真实 residual direction 的 relative error `<=1e-10`。

### G2.3 full-space p6 ILU inventory oracle

仅作为结构对照，允许对 primary slab 构造一次 full-space p6 ILU/LU inventory：

- rows、matrix NNZ、factor NNZ、payload、setup peak；
- trace RHS `[0; r_t]` 后提取的 trace correction；
- contraction 与 current trace ILU 对比。

该因子不进入正式 16-slab candidate。若 full-space ILU 相对 trace ILU 的 retained bytes 没有至少 25%
下降，则明确关闭“仅换 full-space ILU”路线。

### G2.4 LOR mesh 与 transfer

先在 p2/p3 小型 hexa fixture建立 LOR，再扩展 p6 primary slab。要求：

- 每个高阶 parent hexa 的低阶细化拓扑可重建；
- parent material、cell orientation、periodic/Floquet entity identity保持；
- lowest-order Nédélec edge orientation正确；
- 构造 $T_j$ 和 $T_j^H$；
- 低阶/affine/curl-compatible manufactured fields transfer正确；
- adjoint identity relative error `<=1e-11`；
- no missing/duplicate active edge keys；
- transfer/cache repeated action deterministic。

LOR 不是 p2/p4 小维 coarse space，不得复用 Candidate D/F 的低维解释。

### G2.5 LOR-HX/V-cycle 实现边界

主目标是在 LOR 空间构造固定、低存储的 H(curl) V-cycle：

```text
fine LOR smoother              = cheap fixed linear smoother
scalar H1 auxiliary correction = required
vector H1 auxiliary correction = required or explicitly justified alternative
coarse hierarchy               = geometric/algebraic low-order hierarchy
coarsest solve                 = small exact LU/ILU allowed
fine/intermediate large factor = forbidden
```

原问题非 Hermitian、不定，因此 LOR-HX 可作用于一个物理一致的 shifted/coercive local proxy；
outer FGMRES 仍求 exact $A_t$。只允许两个冻结 shift 规则：

1. 继承当前 slab local diagonal shift 的等价 LOR 形式；
2. 基于 local mass/impedance 的 complex shift，参数由 $k_0$、局部材料和 slab 尺度自动计算。

禁止手工扫大量 shift。

历史 complex hypre AMS 曾有 crash 风险。规则：

- 不得直接把 current complex p6 operator挂到 hypre AMS；
- 若使用 real-split AMS service，先做独立 ABI/lifecycle/communicator smoke；
- 若 current environment 不支持安全 real-split AMS，使用 repository 内可维护的 HX composition 或记录
  capability stop；
- 不得安装或替换整个生产环境来隐藏 capability failure；
- one-slab oracle允许隔离 subprocess，但必须记录环境和内存。

### G2.6 one/two V-cycle Gate

只测试：

```text
1 V-cycle
2 V-cycles
```

禁止增加为 10、20、90 个 local Krylov steps来制造 contraction。

必须比较：

- current trace ILU；
- B4 local GMRES(4)；
- full-space p6 ILU oracle；
- LOR-HX 1V；
- LOR-HX 2V。

真实 residual 优先级高于 manufactured low/high/mixed source。

G2 判定：

```text
G2_PASS:
    minimum contraction signal pass
    memory signal pass
    deterministic/action/transfer Gates pass

G2_PARTIAL:
    contraction pass but memory fail
    or memory pass but contraction only weak-positive

G2_FAIL:
    contraction minimum fail
    action/transfer identity fail
    hierarchy unstable/nonfinite
```

只有 `G2_PASS` 才进入 G3。`G2_PARTIAL` 只允许一次有明确根因的局部修复，不得展开 profile sweep。

输出：

```text
docs/task37_extra_development/outcomes/g2_one_slab_fullspace_lor_hx.md
benchmarks/cases/101_task37_extra_development/records/g2_*.json
```

---

## G3：16-slab additive LOR-HX PC

仅在 G2_PASS 后执行。

### G3.1 架构

保持 M3a 的：

- 16 slabs；
- overlap；
- partition-of-unity；
- fixed 75D wave coarse；
- outer right FGMRES；
- exact matrix-free fine action。

唯一主要变化是：

```math
U_j^{-1}L_j^{-1}
\longrightarrow
M_{j,LOR-HX}^{-1}.
```

### G3.2 hierarchy reuse

对 16 个 slab 建立：

```text
topology class
material/coefficient class
orientation/Floquet class
numeric hierarchy fingerprint
```

允许 exact hierarchy/class reuse；禁止 approximate sharing。必须分别报告：

- unique hierarchy count；
- retained operator/transfer/coarse bytes；
- per-rank duplicates；
- setup workspace；
- coarse factor bytes。

若 16 套 hierarchy 全部独立常驻导致总内存没有优势，G3 不能伪装成成功。

### G3.3 漏斗

同机先运行 MPI1：

```text
20-step
100-step
200-step
```

最低 Gate：

```text
20-step true residual  <= 0.20
100-step true residual <= 0.05
200-step true residual <= 0.01
20-step peak           <= 0.75 * same-machine M3a peak
```

强 Gate：

```text
200-step residual <= 1e-3
predicted full iterations <= 1500
retained hierarchy + coarse payload <= 1.1 GiB
```

未达到最低 Gate，停止 G3 full，不进入 G4，除非 G2 局部 contraction很强且证据明确表明只缺跨 slab 传播；
此时允许进入 G4 的 one-apply sweep oracle，但不允许直接 full solve。

输出：

```text
docs/task37_extra_development/outcomes/g3_additive_lor_hx.md
```

---

## G4：forward/back z-sweep / multiplicative Schwarz

G4 只解决**跨 slab 传播**，不能补救一个 G2 已经很弱的局部 inverse。

### G4.1 第一阶段：multiplicative residual sweep

使用 G2/G3 的同一局部 solver，测试：

```text
forward bottom-to-top sweep
symmetric forward + backward sweep
```

禁止同时扫描大量 slab ordering。每处理一个 slab必须用 exact fine action更新 true residual。

比较：

```math
\rho_{additive},\quad
\rho_{forward},\quad
\rho_{forward/backward}.
```

进入 20/100-step screen 的 Gate：

```text
one-PC contraction improvement >= 2x vs additive
or 100-step predicted residual improvement >= 2x
memory no worse than additive
one-PC wall <= 4x additive PC wall
```

### G4.2 第二阶段：approximate block-LU / interface state

只有 multiplicative sweep有明显正信号才允许实现更强的 interface Schur/DtN 传播。禁止形成全局 dense
Schur。可保留的状态只包括：

- 相邻 slab interface vectors；
- small modal/impedance state；
- exact class-shared hierarchy；
- bounded Krylov/recycling state。

### G4.3 流式内存规则

若要声称“接近一个或少数 slab 的峰值”，必须证明：

```text
not all 16 large hierarchies/factors resident simultaneously
no hierarchy rebuild on every outer iteration unless wall Gate still passes
no disk-backed hot factor streaming
no hidden OS page-cache dependence
```

G4 的总工作量不是 Full3D 的 $1/16$；forward/back 需要处理全部 16/32 个局部问题。报告必须同时给出
peak 和总 local apply count/wall。

输出：

```text
docs/task37_extra_development/outcomes/g4_z_sweep.md
```

---

## G5：真实 Krylov recycling / M120 modal coarse，只处理剩余全局慢误差

只有 G3/G4 已经获得局部正信号、但仍存在全局平台时才进入 G5。

### G5.1 Matrix-free DtN E0 修复

V6 E0 的正式失败来自 action-only `MatPython` 被通用 `_petsc_matrix_stats()` 调用 `getInfo()`。
在本隔离分支允许修复该遥测路径，但必须：

- 区分 AIJ stats 与 MatPython action-only inventory；
- 不用假数值填充 unsupported stats；
- 完成 80-mode serial/MPI2/MPI4 action/recovery identity；
- explicit C/D materialized count在 primary matrix-free path 为零；
- ordinary default不变。

E0 未通过前禁止运行 M120 coarse。

### G5.2 Recycled Ritz / GCRO-DR 类 augmentation

优先从真实候选外层残差和 harmonic Ritz vectors 构造 augmentation，测试固定：

```text
16 vectors
32 vectors
```

禁止无界扫描。需要 ownership-independent canonical vector和 action basis。该路线主要服务未来角度/波长/几何
连续求解，也允许在当前 anchor 上测试。

### G5.3 M120 modal coarse

Candidate E 在原 Task37 中没有得到科学结论，因此本隔离分支可在 E0 通过后重新做一次。规则：

- 固定 M120 forward + M120 backward；
- 不扫 M40/M80/M160/M240；
- Full3D fine operator和Krylov空间保持完整；
- primary capacity使用 action-QR/SVD minimum-residual correction；
- 不恢复 direct Hybrid；
- basis generation offline peak和online peak分开报告；
- online additional peak `<=0.30 GiB`。

G5 进入 full screen 的最低 Gate：

```text
100/200-step residual improvement >= 2x vs same local-PC baseline
coarse/action rank stable
no nonfinite or severe conditioning failure
```

输出：

```text
docs/task37_extra_development/outcomes/g5_recycling_modal_coarse.md
```

---

## G6：selective 2/4/8-slab ILU hybrid

当完全 factor-free 或 LOR-HX 路线接近收敛但仍不足时，允许做一个有界折中：

```math
M^{-1}
=
\sum_{j\in\mathcal J_{strong}}
R_j^TW_jM_{j,ILU}^{-1}R_j
+
\sum_{j\notin\mathcal J_{strong}}
R_j^TW_jM_{j,cheap}^{-1}R_j
+Q_{wave}.
```

### G6.1 slab 选择

必须根据 G0 的真实 residual/ablation sensitivity 排序，不得按 boundary slab 或人工偏好选择。

只允许：

```text
2 strong ILU slabs
4 strong ILU slabs
8 strong ILU slabs
```

选中 slab的 factors可结合 G1 exact reuse；mixed precision只有其 one-slab Gate已通过时才允许。

### G6.2 Gate

```text
20/100/200-step residual clearly better than pure cheap-PC candidate
factor payload reduction >= 40% vs M3a
process-tree peak <= 0.75 * M3a
predicted full wall <= 4 * M3a
```

若 8-slab ILU 仍不收敛或内存无明显收益，停止 selective hybrid，不扩展 10/12/14-slab扫描。

输出：

```text
docs/task37_extra_development/outcomes/g6_selective_ilu_hybrid.md
```

---

## G7：最优候选的正式漏斗与唯一 full run

G7 只允许从 G1–G6 中选择一个 Pareto 最优候选。选择依据必须同时包含：

- true residual trend；
- one-apply contraction；
- retained bytes和process-tree peak；
- setup/apply/full wall；
- numerical stability；
- 可维护性；
- 是否仍保留大规模 p6 factors。

### G7.1 MPI8 漏斗

若新机器支持 MPI8且安全内存 Gate通过，运行：

```text
MPI8 20-step
MPI8 100-step
MPI8 200-step
```

若机器不支持 MPI8，明确记录 `not_run_by_host_capability`，不得用其他 MPI 数冒充 MPI8 authority。

### G7.2 MPI1 唯一 full

只有 MPI8 漏斗通过或有充分 MPI1-only研究理由时，运行一次 MPI1 full。要求：

- full true residual和物理 Gate全部通过；
- canonical vectors按实体/全局 key比较，不使用 raw ownership-order bytes作为唯一结论；
- process-tree RSS/PSS/USS/swap authority完整；
- 与同机 M3a比较 peak和wall；
- 最多一次正式 full；若因明确代码异常失败，可修复后再运行一次并保留首次失败记录。

### G7.3 最终分类

只允许以下分类之一：

```text
EXTRA_RESEARCH_FULL_PASS_HALF_MEMORY
EXTRA_RESEARCH_FULL_PASS_MEMORY_POSITIVE
EXTRA_RESEARCH_NUMERIC_PASS_RESOURCE_NEGATIVE
EXTRA_RESEARCH_PRECONDITIONER_INSUFFICIENT
EXTRA_RESEARCH_IMPLEMENTATION_STOP
EXTRA_RESEARCH_RESOURCE_STOP
```

无论结果如何：

```text
merge_to_master = no
ordinary_default_change = no
branch remains isolated
```

输出：

```text
docs/task37_extra_development/outcomes/summary.md
docs/task37_extra_development/response_v1.md
```

---

## 6. 推荐代码边界

新代码优先放在独立模块，不把实验逻辑塞回 ordinary case flow：

```text
src/solvers/static_slab_fullspace.py
src/solvers/static_lor_hcurl_transfer.py
src/solvers/static_lor_hx_pc.py
src/solvers/static_sweeping_pc.py
src/solvers/static_recycled_coarse.py
src/solvers/static_selective_slab_pc.py
```

实际文件名可根据现有结构调整，但必须遵守：

- 所有入口显式 `task037_extra` opt-in；
- ordinary solver profile和默认参数不变；
- 不在 import 时创建 PETSc/MPI对象；
- owner、borrowed、owned对象生命周期清楚；
- `destroy()` 幂等；
- MPI collective路径即使某 rank没有 slab也必须参与；
- 不在 MatMult/PC apply 中分配 FE-sized Python global arrays；
- 不在每次 PC apply 中重建 transfer、hierarchy或factor；
- 不把 raw artifacts加入 Git；
- 不新增长期依赖，除非用户另行授权。

建议测试：

```text
src/test/test_251_task037_extra_branch_contract.py
src/test/test_252_task037_extra_residual_snapshots.py
src/test/test_253_task037_extra_fullspace_slab_identity.py
src/test/test_254_task037_extra_lor_transfer.py
src/test/test_255_task037_extra_lor_hx_oracle.py
src/test/test_256_task037_extra_sweep.py
src/test/test_257_task037_extra_selective_ilu.py
```

测试编号若被占用，使用下一个空闲编号，并记录映射。

---

## 7. 硬停止规则

### 7.1 科学停止

- G2 minimum contraction失败：不进入 G3；
- G2 transfer/action identity失败：先修复代数，不跑 PDE；
- G3 200-step residual高于 `0.01` 且没有明确跨 slab传播证据：不进入 full；
- G4 sweep one-apply没有至少 2x 改善：关闭 sweep；
- G5 coarse没有 2x改善：关闭 coarse，不扩维；
- G6 8-slab仍失败：关闭 selective hybrid；
- 任一候选出现 nonfinite、false convergence或true/reported residual失配：立即停止。

### 7.2 资源停止

- swap非零并持续增长；
- process-tree RSS超过机器安全上限；
- 单一实验超出冻结 wall/timeout；
- 反复构建 hierarchy/factor造成明显 thrashing；
- 需要将 hot factors放硬盘才能运行；
- 需要 90-step inner Krylov才能获得局部 contraction。

### 7.3 代码治理停止

- 需要修改普通默认物理或求解器；
- 需要合并 master才能继续；
- 需要 force push/rebase远程历史；
- 需要减少 modes、改变材料、降低 fine precision；
- 需要把失败研究代码包装成生产 API。

触发停止后，写 compact outcome，提交并推送本分支，然后等待后续用户/ChatGPT审阅。

---

## 8. 每阶段提交与 Codex 工作纪律

建议提交粒度：

```text
docs(task37-extra): record G0 authorities
feat(task37-extra): add exact factor reuse oracle
feat(task37-extra): add full-space slab identity
feat(task37-extra): add LOR transfer oracle
feat(task37-extra): add one-slab LOR-HX oracle
feat(task37-extra): add additive LOR-HX screen
feat(task37-extra): add z-sweep prototype
feat(task37-extra): add recycling or modal coarse oracle
feat(task37-extra): add selective ILU hybrid
results(task37-extra): record final funnel
```

每次提交后：

```bash
git status --short
git log -1 --oneline
git push origin codex/20260806-task37-iterative-extra-development
```

禁止：

- `git push --force`；
- `git add -A` 未检查无关文件；
- 提交大体积 raw artifacts；
- 自动打开 PR；
- 修改 master；
- 把旧 Task37 文档改写成新结果；
- 删除历史负结果。

---

## 9. 第一次 Codex 执行边界

Codex 第一次收到本任务书后，只执行：

```text
G0.1 分支/继承审计
G0.2 M3a MPI1 setup/20-step安全 screen
G0.3 residual snapshot导出基础设施
G0.4 one-level contraction oracle的轻量测试
```

若上述全部通过，再继续同一分支上的 G0 full authority和 G1/G2。第一次执行不得直接实现完整 LOR-HX、
不得启动 G3/G4、不得运行新的 full candidate。

第一次 response 必须回答：

1. 新机器是否能复现 M3a 20-step identity和内存范围；
2. residual snapshot是否能按 canonical global row identity导出；
3. 真实最困难 slab是哪一个；
4. current trace ILU和B4在同一真实 residual上的 contraction差多少；
5. 是否具备进入 one-slab full-space identity实现的前置条件。

---

## 10. 最终目标的准确表述

本任务不是要证明 LOR-HX 或 sweep 一定成功。它要回答：

> 能否在保持 exact p6 static-condensed Full3D fine equation、80-mode DtN、完整 R/T/A和逐通道精度的前提下，用 full-space LOR-HX、多层传播或 selective factor结构，替代或显著减少 16 个 p6 trace-slab ILU factors，并将同机 MPI1 峰值降低至少 25%，优选降低 50%。

只有 full true residual、完整物理 Gate和同机资源 Gate同时通过，才能称为成功。即使达到成功，本分支仍保持
隔离，不合并 `master`，只作为后续研究和决策证据。