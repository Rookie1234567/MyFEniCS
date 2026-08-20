# Task038-extra：面向 0.7 nm 与 2 TiB 的通用 Full3D 迭代求解器

## 0. 任务身份

```text
task                                  = Task038-extra
task_kind                             = LONG_HORIZON_FULL3D_ITERATIVE_PC_REDESIGN
status                                = READY_FOR_CODEX_EXECUTION
repository                            = Rookie1234567/MyFEniCS
base_branch                           = master
base_master_sha                       = 438caf150439343ee7c4c58ad7e02a3da812a23c
working_branch                        = codex/20260820-task38-extra-full3d-iterative-0p7nm
remote_upstream                       = origin/codex/20260820-task38-extra-full3d-iterative-0p7nm
ordinary_default_change               = forbidden
master_write_or_merge                 = forbidden without final review and user authorization
primary_user_entry                    = python scripts/run_case.py input/path/to/case.dat
formal_development_wavelength         = 13.5 nm
formal_development_machine            = approximately 16 GB physical memory, single workstation
future_target_wavelength              = 0.7 nm
future_target_memory                  = approximately 2 TiB physical memory, single node
future_target_geometry                = arbitrary non-separable 3D material/geometry distribution inside one periodic cell
physics                               = complex128 frequency-domain Maxwell, dual Floquet x/y, open z with Fourier-DtN
finite_element                        = Nedelec H(curl)
primary_research_line                 = full-space matrix-free Full3D iterative
Hybrid_role                           = separate structure-exploiting accelerator, not this task's replacement
static_condensation_role              = authority/control only, not the production fine-space architecture
full_0p7nm_PDE_in_this_task           = forbidden
whole_task37_extra_merge              = forbidden
whole_task39_merge                    = forbidden
unbounded_PC_search                   = forbidden
response_required                     = response_v1.md
```

本任务使用仓库实际默认分支 `master`。用户口中的 `main` 在本仓库对应 `master`。

Task038-extra 不是对已合入 `master` 的 Task038 输入模块进行替代；它在 Task038 的单一 `.dat` 入口和 provenance 框架上，开发新的 Full3D iterative 方法。

最终目标不是只让当前 p6/h10 小案例低内存运行，而是形成一条满足以下结构要求的长期路线：

```text
arbitrary 3D inside periodic cell
+ full-space Nedelec H(curl)
+ exact matrix-free fine operator
+ distributed Floquet/DtN/interface data
+ scalable domain-decomposition or multilevel PC
+ no growing global direct factor
+ near-linear memory with h refinement
+ wave-number-aware global error treatment
```

---

# 1. 新分支决定与旧研究分支处置

## 1.1 为什么从当前 master 重新开始

当前 `master` 已经包含 Task038 的输入驱动框架：

```bash
python scripts/run_case.py input/path/to/case.dat
```

并包含：

- strict `.dat` schema、validation、resolved config 和 manifest；
- Full3D direct、Hybrid direct、Hybrid iterative adapter；
- 统一结果目录和 input/physical/source hash；
- 当前 production 数值核心与 ordinary default。

`codex/20260806-task37-iterative-extra-development` 与当前 `master` 已明显分叉。该 research branch 相对 `master` 具有大量 task-numbered runner、负结果 PC、重复 checker 和旧接口假设，且落后于 Task038 输入迁移。不得把该分支整体 merge、rebase 或 cherry-pick 到本任务。

## 1.2 Task37-extra 不删除，但冻结

Task37-extra 不应物理删除或改写历史。它保留为：

```text
full-space matrix-free action positive evidence
matrix-free full-space DtN positive evidence
low-memory lifecycle evidence
failed shifted-patch/range/nested-PC research archive
```

本任务只能按文件、按依赖、按测试进行选择性迁移；所有迁移必须在当前 `master` 基础上重新验证。

## 1.3 与 Task039 的关系

`codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` 是 Hybrid direct/iterative 与 5 nm/0.7 nm 容量研究主线。Task038-extra 不整体继承 Task039，也不与其竞争。

两条长期路线保持：

| 路线 | 适用范围 | 本任务定位 |
|---|---|---|
| Full3D iterative | 任意非可分离三维结构 | 本任务主线 |
| Hybrid | 存在可模态传播内部区域的结构 | 平行加速路线，不替代 Full3D |

---

# 2. 开始编码前必须读取的权威材料

Codex 开始前必须完整读取：

```text
AGENTS.md
docs/AGENTS.md（若存在并适用）
docs/repository_work_principles.md
docs/markdown_rendering_standard.md
docs/task_retrospective_standard.md
docs/README.md
```

必须读取当前 `master` 的 Task038 闭环：

```text
docs/task038_input_driven_configuration/task.md
docs/task038_input_driven_configuration/review_report_v1.md
docs/task038_input_driven_configuration/response_v1.md
docs/task038_input_driven_configuration/outcomes/summary.md
src/io/input_schema.py
src/io/input_validation.py
src/io/execution_plan.py
src/runners/task038_input_worker.py
src/runners/task038_full3d_direct.py
scripts/run_case.py
```

必须只读审计 Task37-extra 的下列权威和正/负证据：

```text
docs/task37_extra_development/response_v1.md
docs/task37_extra_development/response_v15.md
docs/task37_extra_development/review_report_v11.md
docs/task37_extra_development/outcomes/h1r3_warm_repeat_v2.md
docs/task37_extra_development/outcomes/h1r3_mpi2_partition_identity.md
docs/task37_extra_development/outcomes/h1r3_h5_scaling.md
docs/task37_extra_development/outcomes/m6_time_harmonic_pde.md
benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat_v2.json
benchmarks/cases/101_task37_extra_development/records/h1r3_mpi2_partition_identity.json
benchmarks/cases/101_task37_extra_development/records/h1r3_h5_scaling.json
benchmarks/cases/101_task37_extra_development/records/m6a_fullspace_matrix_free_dtn.json
benchmarks/cases/101_task37_extra_development/records/m6b_w5_disk_fgmres_screen.json
benchmarks/cases/101_task37_extra_development/records/m6b_w7_s1_restart_disk_fgmres_screen.json
```

必须只读审计 Task039 的长期边界：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/task.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/review_report_v7.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v7.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/summary.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/feasibility_0p7nm.md
```

如果某一远端文件不存在或路径已变化，必须在 inherited audit 中记录，不得猜测。

---

# 3. 第一提交：只读继承审计与选择性迁移清单

第一项提交必须是 docs-only：

```text
docs(task038-extra): audit master and reusable research components
```

必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/inherited_master_audit.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/task37_extra_selective_migration.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/task39_boundary_audit.md
```

第一提交不得修改 Python、输入 schema、runner 或 solver。

## 3.1 初始迁移分类

下表是审阅起点，不是允许盲拷贝的清单。

| Task37-extra 组件 | 初始分类 | 迁移条件 |
|---|---|---|
| `hcurl_rank_one_form_action.py` | reusable candidate | 去除 task-specific 命名；在当前 master 上重建测试 |
| `hcurl_rank_one_mpc_action.py` | reusable candidate | 重新验证 Floquet/MPC、MPI1/MPI2、complex128、ownership |
| `hcurl_fullspace_dtn.py` | reusable architecture candidate | 去除固定 80-mode/identity-H 假设；支持动态 mode inventory 与 streaming |
| canonical-vector utilities | reusable candidate | 与当前 Task038 provenance/canonical schema 对齐 |
| JIT staging、cache identity、process-tree watchdog 模式 | reusable pattern | 迁移通用模式，不复制 task-numbered orchestration |
| `disk_backed_flexible_gmres.py` | diagnostic-only candidate | 仅作有界 oracle；不得成为 0.7 nm production 基础 |
| p4→p6 owner-local transfer | deferred candidate | 只有进入 p/h multilevel lane 时才迁移 |
| `fullspace_matrix_free_hcurl.py` 旧 dense-cell 路径 | do not migrate | 每次生成 dense cell tensor，不具 h/p 可扩展性 |
| `hcurl_h2b_*`、`hcurl_m6b_*`、W8–W18 | do not migrate as PC | 当前 PC 家族已充分负资格化 |
| 84 个 882D patch factor store | do not promote | p6/h1 下不满足近线性可扩展设计 |
| fixed 75/390/530D range | do not promote | 固定维数不适用于 0.7 nm 电尺寸增长 |
| LOR-HX slab hierarchy | do not migrate | 已有内存与数值负证据 |
| `benchmarks/run_task037_extra_*.py` | do not migrate | 巨型 task runner；数值核心必须进入通用 `src/` |
| 历史 compact records/docs | archive/reference only | 只迁移最小 authority summary，不复制全部历史 |

任何 reusable candidate 必须：

1. 逐文件列出依赖；
2. 在新分支重新命名为通用模块；
3. 添加当前 master 下的 focused tests；
4. 证明未引入旧 task runner 或旧输入路径；
5. 不以旧 branch PASS 代替本分支 fresh evidence。

---

# 4. 冻结物理、离散与开发案例

## 4.1 正式开发物理

本任务所有正式 PDE 开发运行固定为：

```text
wavelength          = 13.5 nm
problem             = 3D frequency-domain Maxwell scattering
scalar type         = complex128
finite element      = Nedelec H(curl)
periodicity         = dual Floquet in x and y
open boundary       = Fourier-DtN in z
material            = complex/lossy permitted
geometry            = rectangular block grating anchor, then one non-separable 3D fixture
formal fine space   = uncondensed full-space
```

禁止用 0.7 nm full PDE 试错。0.7 nm 在本任务中只做容量、通道与复杂度审计。

## 4.2 开发网格层级

至少维护：

| 层级 | 用途 | 允许的求解 |
|---|---|---|
| p2/p3 小 fixture | 代数、MPI、transfer、interface identity | direct 与 iterative |
| p6/h10 | 正式 13.5 nm anchor | 完整 iterative；direct 使用冻结 authority 或条件运行 |
| p6/h5 | scaling oracle | action/PC apply 优先；完整 PDE 需 preflight 通过 |
| p6/h2.5 或最近可承受点 | scaling extension | 只在前序 Gate 通过后 |
| 0.7 nm target inventory | capacity only | 不运行 full PDE |

## 4.3 任意三维的含义

本任务的“任意三维”指周期单胞内任意三维材料与几何分布。新的 PC 可以沿 z 做 domain decomposition，但不得要求内部材料沿 z 可分离、均匀挤出或可用有限模态精确表示。

当人工接口穿过非均匀截面时，必须使用一般的 impedance/optimized transmission 或局部谱空间；只有处于均匀区域的接口才允许使用解析 Floquet modal transmission。

---

# 5. 精确算子与预条件器目标

精确物理方程保持：

```math
A u = b,
\qquad
A = K_{\mathrm{curl}} - k_0^2 M_{\epsilon} + T_{\mathrm{DtN}}.
```

fine operator 必须：

```text
full-space
matrix-free / action-only
no global AIJ A
no global condensed Schur
no per-cell dense matrix cache
no growing slab LU as production requirement
no FE-sized global numeric allgather
```

真正需要解决的是：

```math
M^{-1}r \approx A^{-1}r
```

并同时满足：

```text
memory approximately O(N)
iteration count bounded or slowly growing with h refinement
global wave propagation represented explicitly
coarse/interface data distributed
```

---

# 6. 主 PC 架构：z-sweeping optimized Schwarz

## 6.1 它解决什么问题

Task37-extra 的局部 patch PC 对 coercive Maxwell 很强，但对真实不定时谐问题的剩余误差缺乏跨区域传播能力。成功的 M3a trace-slab PC 则保留了较大 z-slab 内的长程耦合，但其 factors 不能扩展到 0.7 nm。

本任务主线用“前向/后向波传播 sweep”替代常驻大型 slab factor：

```text
residual enters slab 0
→ local slab solve with artificial transmission
→ outgoing interface data sent to slab 1
→ continue to top
→ reverse sweep back to bottom
```

它改变的是 PC apply，不改变精确物理方程。

## 6.2 局部 slab 方程

第 j 个 slab 的辅助问题写为：

```math
\left(A_j + \mathcal T_j^- + \mathcal T_j^+\right) u_j
=
f_j + g_j^- + g_j^+.
```

其中 `T_j^-`、`T_j^+` 是人工界面传输算子。

允许的固定候选最多三类：

| 顺序 | transmission | 适用范围 |
|---:|---|---|
| A | first-order impedance/Robin | 一般非均匀截面，最低存储基线 |
| B | propagating + near-cutoff Floquet modal transmission | 仅均匀接口或经 identity 资格化的接口 |
| C | bounded second-order/rational or local spectral impedance | A/B 有正信号但未通过时的唯一 fallback |

禁止连续扫描 Robin 参数、Padé 阶数、mode 数量或 overlap。

## 6.3 全局 coarse/deflation

不得再次使用固定 75D coarse 作为长期设计。

允许两种自适应策略之一：

```text
1. all propagating + near-cutoff interface modes selected by a frozen physical tolerance;
2. local Maxwell-harmonic generalized eigenvectors selected by a frozen eigenvalue tolerance.
```

coarse dimension必须由波数、电尺寸和误差容限决定，并在结果中报告增长规律。

production 设计禁止：

```text
replicated dense FE-to-mode matrix
replicated global coarse factor
coarse dimension proportional to volume DoFs
```

## 6.4 slab 内部求解

slab 内部可以复用本任务资格化的 matrix-free action，并使用：

- fixed small-restart Krylov；
- bounded local patch/low-order multilevel；
- class-reused local factors；
- distributed coarse level。

不得要求每个 slab 保存随横截面或 h refinement 超线性增长的 LU/ILU factor。

---

# 7. 资源合同

## 7.1 当前 16 GB 开发机

正式 heavy 前必须记录：

```text
MemAvailable
swap total/used
disk free
MPI/thread identity
process-tree watchdog
```

运行规则：

```text
one heavy job at a time
swap = 0
warning at process-tree RSS 10,000,000,000 B
controlled stop at process-tree RSS 12,000,000,000 B
no OOM kill accepted
```

超过 2 GB 但低于 12 GB 的结果只能称为 diagnostic/development，不得称为 0.7 nm-scalable qualification。

## 7.2 p6/h10 战略资格线

最终 13.5 nm p6/h10 anchor 必须满足：

```text
completed full workflow process-tree peak < 2,000,000,000 B
swap = 0
true residual <= 1e-6
official field/R/T/A enabled only after residual pass
```

推荐内部预算：

| 组件 | 建议上限 |
|---|---:|
| exact action + mesh/MPC | 450 MB |
| PC retained data | 700 MB |
| Krylov and work vectors | 300 MB |
| DtN/interface/coarse | 250 MB |
| telemetry/runtime margin | 300 MB |
| total | 2,000 MB |

这是规划预算，不是将对象 bytes 相加冒充 RSS；最终只认 simultaneous process-tree measured peak。

## 7.3 h-refinement scaling

对至少 h10、h5 和一个更细可承受点拟合：

```math
M(N)=M_0+cN^{\alpha}.
```

要求：

```text
retained numeric payload exponent alpha <= 1.10
process-tree incremental bytes/DoF stable within stated uncertainty
iteration-count ratio across qualified meshes <= 2.0
```

## 7.4 0.7 nm / 2 TiB 规划线

2 TiB 是整机物理内存，不允许程序占满。容量审计采用：

```text
preferred full-workflow prediction <= 1.6 TiB
conditional feasibility ceiling    < 1.8 TiB
reserved system/uncertainty margin >= 0.2 TiB
swap                               = 0
```

该预测必须拆分：

```text
mesh/DoF/maps
fine action
Krylov vectors
slab/interface work
coarse/deflation
DtN modes
MPI duplication/ghosts
recovery/postprocess
lifecycle overlap
```

任何 `derived` 或 `predicted` 字节不得写成 measured RSS。

---

# 8. 分阶段执行

## T0：继承审计与选择性迁移清单

只做 §2–§3 的文档审计。

Gate：

```text
master SHA exact
branch/upstream exact
worktree clean
Task37-extra and Task39 boundaries explicit
no Python changes
```

## T1：`.dat` 方法合同与 opt-in adapter

在当前 Task038 schema 中增加通用方法：

```text
method.kind = "full3d_iterative"
```

要求：

- 仍是一 dat 一 run；
- adapter identity稳定且 fail closed；
- 研究 PC profile 必须显式 opt-in；
- ordinary default 不变；
- validate-only/dry-run先通过；
- 不在 schema 中公开大量临时研究参数。

建议第一版只公开：

```text
solver.linear_solver = "iterative"
solver.preconditioner = "full3d_scalable_v1"
solver.ksp_type
solver.restart
solver.max_iterations
execution.mpi_size
execution.memory_limit_gb
```

传输、slab、coarse的研究细节通过版本化 profile 固定，资格化后再决定是否公开。

## T2：generic full-space matrix-free volume action

从 Task37-extra 选择性重构 rank-one action，不复制旧 dense-cell实现。

必须验证：

```text
p2/p3 assembled identity <= 1e-12
p6/h10 reference action identity <= 1e-11
MPI1/MPI2 canonical identity <= 1e-12
12-repeat deterministic
RSS does not climb
no global matrix / Schur / slab matrix / factor
h10→h5 retained payload exponent <= 1.10
```

正式模块必须使用通用名称，不得保留 `task037_extra` 作为生产 API。

## T3：dynamic full-space matrix-free DtN

选择性重构 Task37-extra 的 owner-local sparse carrier，但必须：

- mode 数由 `.dat` 与 physical inventory解析；
- 不固定为 80；
- 支持 streaming/batched modal action；
- MPI1/MPI2一致；
- 不显式形成 C/D；
- mode identity、normalization、propagating/evanescent/near-cutoff分类可审计。

Gate：

```text
action/direct modal-sum relative error <= 1e-11
recovery relative error <= 1e-11
cross-MPI relative error <= 1e-12
retained+bounded work reported by mode count
no FE-sized allgather
```

80-mode 只作为 13.5 nm authority anchor，不是长期固定参数。

## T4：slab/interface topology 与 transmission oracle

先不运行 full KSP。

必须建立：

```text
z-slab partition
owner-local interface trace maps
forward/backward communication plan
material/interface classification
homogeneous vs nonhomogeneous interface identity
```

对 p2/p3 两 slab fixture验证：

```text
interface restriction/prolongation adjoint
Floquet phase once
MPI ownership/ghost closure
artificial transmission action identity
```

禁止形成 dense interface Schur matrix。

## T5：两 slab与少 slab sweep contraction

固定 source：

```text
gradient-dominated
curl-dominated
checkerboard/high-frequency
physical RHS
fresh p6/h10 iterative long-tail residual snapshot
```

按 A→B→C 顺序测试，每种只允许一次实现修复后的正式 rerun。

一次 forward+backward sweep 的主 Gate：

| source | required rho |
|---|---:|
| physical RHS | `<=0.60` |
| long-tail residual | `<=0.70` |
| checkerboard/high-frequency | `<=0.75` |
| gradient/curl | `<=0.90` |

同时要求：

```text
finite and deterministic
true action closure <= 1e-11
peak < 6 GB diagnostic ceiling
retained memory approximately interface/volume linear
```

若 A/B/C 全部不能使 long-tail residual `rho<=0.70`，停止主 sweep 路线，不得启动完整 PDE。

## T6：13.5 nm p6/h10 Full3D iterative anchor

只有 T5 通过才运行。

外层优先：

```text
right FGMRES
restart = 20
```

只有 measured live set 和数值证据支持时允许固定 restart=30；禁止无界 restart/KSP扫描。

分级 screen：

| checkpoint | true residual Gate |
|---:|---:|
| 20 | `<=0.40` |
| 100 | `<=0.05` |
| 200 | `<=0.005` |
| final | `<=1e-6` |

200 步后若残差高于 `0.005` 或 150→200改善不足 20%，不得靠数万步长跑掩盖 PC失败。

最终数值/物理 Gate：

```text
true residual <= 1e-6
reported/true residual agree
R/T/A and A_volume finite
energy closure within frozen direct-authority tolerance
selected complex E/H and diffraction channels match authority
completed workflow RSS < 2,000,000,000 B
swap = 0
```

若本机无法重跑 p6/h10 direct authority，允许使用已冻结 authority，但必须证明：

```text
physical_model_sha256 exact
mesh/discretization identity exact
mode/order inventory exact
observable definitions exact
```

否则只能标记 numerical pass，不能标记 complete physics qualification。

## T7：h-refinement scaling

按顺序：

```text
p6/h10 full solve authority
→ p6/h5 action + PC apply
→ p6/h5 full solve only if preflight passes
→ one finer action/PC scaling point
```

必须报告：

```text
DoF/cells/constraints/modes
retained bytes/DoF
process-tree peak
one action wall
one PC apply wall
iterations
alpha fit
```

禁止从单一 h10 数字外推 0.7 nm。

## T8：0.7 nm capacity audit，禁止 full PDE

使用正式 0.7 nm 材料与几何身份，完成：

```text
external channel inventory
propagating/near-cutoff/evanescent count
accuracy-qualified h/p envelope
full-space DoF envelope
interface/coarse dimension envelope
Krylov vector memory
DtN streaming memory
MPI duplication/ghost estimate
recovery/postprocess overlap
```

必须区分：

```text
measured at 13.5 nm
derived scaling
predicted 0.7 nm
not_run 0.7 nm PDE
```

输出至少三个场景：

```text
optimistic
central
conservative
```

并明确是否满足 1.6/1.8 TiB规划线。

## T9：结项与 selective merge 决策

必须完成：

```text
outcomes/summary.md
docs/development_progress.md update
selective_merge_manifest.md
response_v1.md
```

没有最终 review 与用户授权，不得 merge `master`。

---

# 9. 硬停止条件

任一条件发生，停止受影响 lane：

1. full-space action 或 DtN identity 不能达到 Gate；
2. 需要 global AIJ、global Schur、dense interface matrix或 growing global factor才能继续；
3. PC retained memory随 fine DoF呈明显超线性增长；
4. A/B/C 三种 transmission均不能处理 fresh long-tail residual；
5. p6/h10 200步 residual高于0.005或形成明确平台；
6. h-refinement iteration ratio超过2且无单一明确实现错误；
7. 需要无限增加 coarse维数、inner steps、restart或参数扫描；
8. process-tree达到12GB开发机 hard stop、出现swap或OOM kill；
9. 0.7 nm central预测超过1.8TiB且没有已测量的结构性压缩路径；
10. 任务开始演变为 Hybrid、RCWA或结构可分离专用算法。

硬停止不等于整个 Full3D iterative目标永远不可行；必须记录具体 blocker和下一个真正不同的候选架构。

---

# 10. 允许与禁止修改

## 10.1 允许

- 扩展 Task038 `.dat` schema与adapter以支持显式 `full3d_iterative`；
- 新建通用 full-space matrix-free action/DtN模块；
- 新建通用 slab/interface/sweep/optimized-Schwarz模块；
- 新建通用资源与checker工具；
- 从旧研究分支按文件重构已资格化组件；
- 添加 p2/p3/p6、MPI1/MPI2、action、PC、PDE测试；
- 增加官方13.5nm输入与0.7nm capacity-only输入。

## 10.2 禁止

- whole-branch merge/cherry-pick Task37-extra或Task39；
- 复制 `run_task037_extra_m6b.py` 一类巨型runner；
- 重新开放 W8–W18 shifted/range/nested PC搜索；
- 用固定75D coarse宣称0.7nm可扩展；
- 将大factor写入硬盘后在每次PC apply中热读取；
- 改Maxwell弱式、Floquet相位、DtN normalization或物理材料来促使收敛；
- 降低p/h、mode数、残差或物理Gate后宣称原目标通过；
- full 0.7nm PDE；
- 修改ordinary default；
- 删除旧负结果分支或重写历史。

---

# 11. 测试与证据

每次阶段代码完成后至少运行：

```text
focused unit tests
MPI1 fixture
MPI2 fixture where applicable
compileall
git diff --check
Markdown fenced-math/table rendering checks
benchmark compact JSON parse/checker
```

T6/T7正式运行必须绑定：

```text
input_original.dat
resolved_config.json
run_manifest.json
input_sha256.txt
physical_model_sha256.txt
source_sha.txt
run_summary.json
environment and ABI
MPI/threads
process-tree resource record
artifact hashes
explicit true residual checkpoints
official observable identity
```

重型 raw 放在 ignored artifact目录，不提交Git。

---

# 12. 提交计划

建议提交顺序：

```text
1. docs(task038-extra): audit master and reusable research components
2. feat(io): add opt-in full3d iterative dat contract
3. feat(maxwell): add generic full-space matrix-free Hcurl action
4. feat(maxwell): add dynamic matrix-free full-space DtN
5. feat(dd): add owner-local slab and interface maps
6. feat(dd): add bounded optimized-Schwarz transmission oracle
7. feat(dd): add forward-backward sweep PC
8. feat(runner): connect full3d iterative adapter and watchdog
9. evidence(task038-extra): record p6h10 and scaling results
10. docs(task038-extra): close out scalable Full3D iterative study
```

每个提交只包含一个可解释阶段。禁止 amend、force push和混入无关重构。

---

# 13. outcomes 与 response 要求

必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/matrix_free_action.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/dynamic_dtn.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/sweep_oracle.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/full3d_iterative_anchor.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/h_scaling.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/feasibility_0p7nm.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/selective_merge_manifest.md
docs/task038_extra_full3d_iterative_0p7nm/response_v1.md
```

`response_v1.md` 必须说明：

- branch/base/final HEAD与ahead/behind；
- 实际迁移了哪些Task37-extra组件，哪些明确未迁移；
- 每个PC候选的数值、内存、时间与停止原因；
- p6/h10是否同时通过 residual、physics和2GB；
- h-scaling exponent与迭代数趋势；
- 0.7nm容量结果的 measured/derived/predicted边界；
- 未运行项；
- selective merge建议；
- 下一步消除哪个0.7nm blocker。

---

# 14. 开始与停止格式

Codex 开始时必须报告：

```text
branch
HEAD
upstream
ahead/behind
master base SHA
worktree cleanliness
Python/MPI/PETSc/DOLFINx/Basix ABI
PETSc ScalarType/IntType
MemAvailable/swap/disk
```

随后只执行 T0 docs-only audit并提交、push，然后停止等待首次 review。

在首次 review 前禁止开始 T1或迁移任何Python代码。