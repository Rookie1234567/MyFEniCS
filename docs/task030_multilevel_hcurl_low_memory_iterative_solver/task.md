# Task030：3D H(curl) 多层低内存迭代求解器探索

## 0. 任务身份

```text
task_id = Task030
name_zh = 3D H(curl) 多层低内存迭代求解器探索
name_en = Multilevel H(curl) Low-Memory Iterative Solver Exploration
status = planned
execution_branch_creator = Codex
ordinary_default_change = forbidden_without_final_review
```

建议执行分支：

```text
codex/20260713-task30-multilevel-hcurl-low-memory-iterative
```

本任务书先随 Task029 审查分支进入仓库；**Task030 不得在 Task029 分支执行**。启动顺序必须是：

```text
1. Task029 response_v2 完成；
2. Task029 最终审查通过；
3. 用户明确同意 Task029 合并；
4. Task029 合并 master；
5. master 运行轻量 release checks；
6. Codex 从更新后的 clean master 创建 Task030 独立执行分支；
7. 读取本任务书和前序证据后开始实现。
```

---

# 1. 背景

## 1.1 当前直接法边界

目标 3D EUV 周期光栅的冻结物理模型使用：

```text
50 x 25 x 140 nm unit cell
17 x 25 x 120 nm grating
lambda = 13.5 nm
theta = 80 deg from z
phi = 0 deg
s polarization
complex Si
p = 2 Nedelec
matched hexahedral mesh
double Floquet
auxiliary Fourier-DtN
auto_propagating propagation-order policy
80 propagating modal unknowns before exact condensation
```

Task008/028/029 已建立直接法参考。h=2 约 615,108 FE DoF 的直接法在不同记录口径下约需要 18–20.5 GB；Task029 证明主峰来自 MUMPS `KSPSetUp` 中的 analysis 与 numerical LU factorization，而不是 KSPSolve、R/T/A、field output 或 80 个 auxiliary modes。

Task029 进一步证明：

```text
release A_base/b_base after augmentation:
  h3 peak reduction ≈ 5.46%

MUMPS MPI2 instead of MPI4:
  h3 peak reduction ≈ 15.12%

MUMPS OOC:
  h5 has moderate RAM reduction but scratch/time cost

BLR 1e-5:
  true residual and R/T/A fail

SuperLU_DIST:
  memory worse

alternative ordering:
  factor nnz and RSS worse

MPI1 x 4 OpenBLAS threads:
  KSPSetUp still uses about one CPU core
  threaded direct unavailable in current image
```

因此 Task030 不继续直接法微调。

## 1.2 Task027 的成功与局限

Task027 首次得到可在 14 GB 工作站内完成 h=5/3/2 的迭代法闭环：

```text
exact matrix-free condensed operator A = F - C H^-1 D
right FGMRES restart=100
16 complete physical z-slabs
owner-computes distributed Schwarz
shifted-F local ILU1
two fixed shifted-F global GMRES smoothing steps
fixed 75D no-RHS Floquet z-hat coarse space
true Galerkin coarse operator
explicit condensed/full true residual
auxiliary back-substitution
official per-order/total R/T + A_volume
```

正式结果：

| h (nm) | FE DoF | iterations | full true residual | peak total RSS |
|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | `9.839e-7` | about 1.96–1.99 GB |
| 3 | 198,438 | 993 | `9.933e-7` | about 5.07–5.08 GB |
| 2 | 615,108 | 1,804 | `9.997e-7` | about 12.96–13.08 GB |

迭代比：

```text
1804 / 993 = 1.8167 < 2
```

但 Task027 不是几何多重网格。其主要内存仍包括：

```text
assembled global F
16 overlapping slab submatrices
16 distributed local ILU1 factors
about 95.6M global slab-factor nnz at h2
fixed coarse basis and coarse operator
FGMRES basis vectors
scatter/index/work vectors
```

Task027 的意义是“第一个可信工作站迭代基线”，不是最终面向千万 DoF 的低内存架构。

## 1.3 COMSOL 参考的作用

用户提供的 COMSOL 报告显示，在另一台机器、自由四面体、P 偏振、16 nm block、零级周期端口的约 1,178,238 DoF 问题中：

```text
MUMPS direct ≈ 22.99 GB
GMRES + 5-level GMG ≈ 10.55–13.38 GB
TFQMR + GMG ≈ 8.99–9.01 GB
```

COMSOL 的成功结构包含完整 GMG hierarchy、SOR、Vanka、vector smoother 和 coarse MUMPS。

本任务**不以复刻 COMSOL 为目标**。COMSOL 只证明：

```text
- 百万级 H(curl) 问题存在显著低于 direct 的内存架构；
- 真正多层方法可能比单一大子域 Schwarz 节省更多内存；
- 成功关键是完整层次与合适 smoother，而不是仅更换 Krylov 名称。
```

禁止使用 COMSOL 数据作为：

```text
- FEniCS R/T/A reference；
- 跨机器时间排名；
- 每 DoF 内存效率硬指标；
- 减少 FEniCS 传播衍射级的理由。
```

---

# 2. 任务目标

Task030 的核心问题：

> 能否在保留完整 3D p=2 Nedelec、双 Floquet、exact condensed DtN 和全部传播衍射级的前提下，用真正的多层 H(curl) 预条件架构替代 Task027 中内存昂贵的大 slab ILU，从而同时降低每 DoF 内存与迭代数？

## 2.1 最低目标

```text
1. 建立可复核的 3D H(curl) 层次、transfer 和 level operator 基础设施；
2. 至少系统筛选 5 类不同机制的预条件路线；
3. 对每条路线使用统一 h5 低成本筛选和显式真残差；
4. 对正反馈路线持续深化，不在出现正信号后过早停止；
5. 至少一条路线完成 h5 full solve；
6. 只有强正信号路线进入 h3；
7. h2 必须条件解锁；
8. 保持 80 个传播 modes、official R/T/A 和 A_volume；
9. 明确哪些基础设施可合并、哪些 solver 仅留研究分支。
```

## 2.2 工程目标

相对 Task027：

```text
minimum engineering target:
  predicted/observed h2 peak RSS <= 10 GB
  h2 full true residual <= 1e-6
  h2 iterations <= 1200
  tested mesh iteration ratio <= 2

preferred target:
  h2 peak RSS <= 8 GB
  h2 iterations <= 800
```

h3 代理 Gate：

```text
Task027 h3 baseline ≈ 5.07–5.08 GB
strong h3 memory target <= 3.8 GB
preferred h3 memory target <= 3.5 GB
```

若最终没有达到工程目标，但可靠定位了下一代架构瓶颈，仍可分类为 `diagnostic_success` 或 `research_positive`。

---

# 3. 非目标

本任务不做：

```text
- 自适应网格或误差估计循环；
- 改变目标物理模型；
- 减少 auto_propagating 传播 modes；
- 以零级端口代替完整 DtN；
- 新的材料/波长/角度参数扫描；
- 物理网格收敛最终资格化；
- 重新优化直接法；
- 重跑已失败的 spectral tau/cap 参数海洋；
- 将任何正信号静默设为 ordinary default；
- 无 Gate 地运行多个 h2 重型算例。
```

Task030 可以为后续自适应网格建立嵌套/分级网格基础，但不完成真正 adaptivity。

---

# 4. 必须读取的前序证据

开始前必须读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md

docs/task026_auxiliary_free_3d_modal_port/outcomes/summary.md
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/summary.md
docs/task028_stage_consolidation_master_integration_benchmarks/review_report_v4.md
docs/task028_stage_consolidation_master_integration_benchmarks/response_v4.md

docs/task029_stage4_direct_memory_forensics/task.md
docs/task029_stage4_direct_memory_forensics/task_comsol_reference_addendum.md
docs/task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md
docs/task029_stage4_direct_memory_forensics/outcomes/summary.md
docs/task029_stage4_direct_memory_forensics/review_report_v2.md
docs/task029_stage4_direct_memory_forensics/response_v2.md  # merged前必须存在

docs/development_progress.md
docs/solver_guide.md
notes/theory/
notes/reference/code_walkthrough/
```

运行日志首段必须确认已读取。

---

# 5. 冻结物理与数值口径

所有主候选必须保持：

```text
geometry = Task28/Task27 target grating
period = 50 x 25 nm
cell height = 140 nm
block = 17 x 25 x 120 nm
lambda = 13.5 nm
theta = 80 deg
phi = 0 deg
polarization = s
complex Si
p = 2 fine Nedelec
double Floquet
stage4 boundary = dtn_port
order policy = auto_propagating
stage4 assembly = auxiliary for reference / exact condensation for outer solve
propagating modal identity = same as Task27/28
n_aux before condensation = 80
official power = modal port power
absorption = material volume integral
success residual = explicit full true residual
```

允许改变：

```text
- multilevel mesh hierarchy；
- coarse element order；
- transfer operators；
- level operator construction；
- smoother/preconditioner；
- Krylov method after PC is fixed；
- matrix-free/assembled split；
- coarse direct package on sufficiently small level；
- explicit opt-in solver profile。
```

禁止改变：

```text
- physical dimensions/material/incidence；
- number or identity of propagating modes；
- R/T/A definition；
- true residual definition；
- fine p=2 target identity；
- Task027 canonical records。
```

---

# 6. 统一基线

Task030 主基线是 Task027/028：

```text
profile = physical-slab two-level fixed-coarse sm2
outer = right FGMRES restart=100
h5 iterations = 1201
h3 iterations = 993
h2 iterations = 1804
h5 RSS ≈ 1.96–1.99 GB
h3 RSS ≈ 5.07–5.08 GB
h2 RSS ≈ 12.96–13.08 GB
```

必须保留以下 baseline metrics：

```text
100-step explicit true residual
full solve iterations
setup RSS
solve peak RSS
simultaneous total RSS
cgroup memory
swap
operator nnz
local factor nnz
coarse dimension
operator complexity
grid complexity
PC apply time
Krylov vector memory
R/T/A and closure
```

若基线 records 在 Task28 已可信，可复用，不要求先重跑全部 h5/h3/h2。Task030 只需在新 runner/interface 发生不兼容时做 h5 baseline smoke。

---

# 7. 总体研究原则：多 lane 漏斗

本任务允许 Codex 同时探索多个机制不同的 lane，但必须使用统一漏斗。

## 7.1 正反馈继续规则

Codex 被明确授权：

```text
- 某 lane 出现弱正信号时，可在该机制内做 1–2 轮有针对性的参数/结构改进；
- 某 lane 出现强正信号时，必须继续追到 h5 full solve；
- h5 full solve 强正信号必须继续进入 h3；
- h3 同时通过数值、内存和 scaling Gate 后，必须完成 h2 预测；
- h2 预测通过后，允许运行一个最佳 h2 候选；
- 不需要每次向用户确认继续同一正反馈 lane。
```

但授权不包括：

```text
- 改变物理问题；
- 无限制网格/参数扫描；
- 同时运行多个 h2；
- 创建新 ordinary default；
- 跨任务实现 adaptivity 或全新物理功能。
```

## 7.2 停止规则

某 lane 满足任一条件，应停止并记录：

```text
- 代数/transfer correctness Gate 失败且两次修正后仍失败；
- 100-step true residual 比基线恶化超过 25%；
- setup/peak RSS 高于 Task027 超过 20%，且无明显迭代优势；
- PC apply 时间增加超过 3x，残差改善小于 2x；
- 依赖不可维护的私有 API；
- 需要大规模全局直接因子才能工作；
- 只在 reported residual 上正反馈，explicit true residual 不支持；
- 减少 modes 或破坏 official R/T/A；
- 只在 p1/default sandbox 有效，无法在 p2 target h5 重现。
```

负结果必须保留，不能包装成 positive。

---

# 8. Stage A：多层基础设施

这是所有主线的共同前置工作。

## 8.1 嵌套或可验证的层次网格

至少实现两种候选层次中的一种，并优先支持两者比较：

### A1：严格嵌套、材料面对齐的 hexa h-hierarchy

```text
fine p2 mesh
coarser p1/p2 mesh
coarsest p1 mesh
```

要求：

```text
- x/y/z coarse cells refine into fine cells；
- grating/air/substrate material planes remain aligned；
- left/right and front/back periodic faces use identical partitions；
- no accidental geometry change；
- no hanging constraints in first implementation；
- record level cells/DoF/nnz。
```

### A2：semi-coarsening hierarchy

因结构在 z 方向有长层状特征、入射接近掠射，应比较：

```text
isotropic xyz coarsening
xy coarsening with finer z
z-focused or layer-preserving semi-coarsening
```

semi-coarsening不是 COMSOL 复刻，而是针对本问题几何与波传播方向的独立假设。

## 8.2 p-hierarchy

优先实现：

```text
V_h^p2
 -> V_h^p1
 -> V_2h^p1
 -> V_4h^p1
```

必要时比较：

```text
p2 -> p1 only
p2 h-hierarchy
mixed p2/p1 h-hierarchy
```

## 8.3 H(curl) transfer

必须明确处理：

```text
- edge orientation；
- p2 edge/face DoF；
- coarse/fine ownership；
- MPI ghost data；
- double Floquet phase；
- corner constraints；
- complex scalar semantics；
- constrained/reduced space mapping。
```

优先使用公开 Basix/DOLFINx/PETSc API；不得用不可维护的 probe/pinv 全局 hack 替代真正 transfer。

## 8.4 transfer correctness Gate

至少测试：

```text
constant/low-order representable fields
plane-wave-like fields
random coarse vectors
periodic trace identity
Floquet phase identity
MPI1 vs MPI2/4 transfer action
```

记录：

```text
||P u_c - u_f,expected|| / ||u_f,expected||
||R P - I|| on coarse vectors
curl-commuting diagnostic
energy/norm preservation diagnostic
constraint violation
```

`curl-commuting diagnostic` 不要求第一版达到理论机器精度，但必须量化并与 candidate performance 关联。

## 8.5 coarse operator

比较：

```text
Galerkin: A_c = R A_f P
rediscretized coarse operator
hybrid: rediscretized F_c + Galerkin low-rank DtN
```

每条路线需记录：

```text
matrix action difference
coarse spectrum/conditioning diagnostics
operator complexity
memory
setup time
```

---

# 9. Lane 1：真正 3D H(curl) geometric multigrid

## 9.1 假设

真正的多层 coarse hierarchy 可以逐级处理 Task027 固定 75D coarse 无法覆盖的长波误差，同时避免保存 16 个大型 slab ILU1 因子。

## 9.2 初始结构

```text
outer FGMRES on exact condensed A
V-cycle / W-cycle on shifted or true FE operator F
2–5 levels depending on available hierarchy
small direct solve only on coarsest level
```

优先比较：

```text
2-level
3-level
5-level when hierarchy supports
V-cycle
W-cycle only after V-cycle positive
```

## 9.3 level memory policy

```text
fine level operator preferably matrix-free or single assembled F
middle levels assembled sparse
coarsest level direct
no large overlapping slab factors by default
reuse transfer and coarse matrices
```

---

# 10. Lane 2：p-multigrid 与 mixed p/h hierarchy

## 10.1 假设

p2 高阶 face/edge modes 可由便宜的 p-smoother 处理，主要低频误差转到 p1 H(curl) 后再由 h-multigrid处理。

## 10.2 候选

```text
p2 -> p1 additive correction
p2 -> p1 multiplicative correction
p2 high-order complement smoother
p1 h-multigrid coarse solve
```

比较：

```text
pure h-GMG
pure p-coarsening
mixed p/h
```

## 10.3 关键诊断

```text
p2 high-order complement residual
edge vs face DoF residual distribution
material-interface residual
port-trace residual
```

---

# 11. Lane 3：低内存 smoother 家族

至少系统测试三种机制不同的 smoother，不得只测试参数变体。

## 11.1 Polynomial smoother

```text
damped Jacobi
Chebyshev
fixed-step GMRES polynomial
```

作用对象优先是 shifted/coercive level operator，而不是真实非定 A。

记录：

```text
eigenvalue bound estimation
number of smoothing steps
memory
high-frequency residual reduction
```

## 11.2 Small patch Schwarz / Vanka-like smoother

patch 候选：

```text
vertex patch
edge-star patch
cell patch
material-interface patch
port-trace patch
small z-column patch
```

local solver 候选：

```text
small dense LU
small sparse LU
ILU0
fixed inner Krylov
```

必须控制：

```text
patch size distribution
factor nnz
overlap duplication
owner-computes / coloring
MPI communication
```

第一目标是替代 Task027 的大型 full-slab ILU1。

## 11.3 Hybrid smoother

允许探索：

```text
polynomial + patch
pre-polynomial / post-patch
pre-patch / post-polynomial
interface patch + bulk polynomial
```

若某个 hybrid 出现正反馈，可继续针对机制优化，而不是只扫 relaxation 数值。

---

# 12. Lane 4：AMS/HX 的重新定位

## 12.1 不重复旧失败

禁止再次尝试：

```text
complex full Stage4 A directly with unsafe AMS
FE-AMS + aux identity as complete PC
same-H1 AMS without DtN-aware outer structure
```

## 12.2 新假设

AMS/HX 只用于其更合适的 shifted/coercive p1 level：

```text
F_shift = curlcurl + positive/complex-safe mass shift
```

外层 FGMRES 仍作用于真实 exact condensed A。

候选：

```text
p1 coarse-level AMS
real-split AMS only on selected levels
AMS as coarse correction inside p/h MG
AMS + polynomial pre/post smoother
```

必须记录：

```text
real/complex representation cost
auxiliary H1 vector spaces
memory per level
AMS setup/apply time
true outer residual
```

如果 AMS 只在 isolated FE-only sandbox 正反馈、无法接入 target h5，则停止。

---

# 13. Lane 5：all-mode DtN low-rank Schur correction

## 13.1 前序依据

Task021–025 已证明：

```text
- FE/aux coupling structure是关键；
- exact FE inverse 上的小 Schur 上界极好；
- sampled few-mode route 不迁移 p2；
- cached Q 的主要失败来自 FE response quality。
```

Task026 已提供 exact condensation：

```math
A = F - C H^{-1}D.
```

## 13.2 新组合路线

使用 multigrid approximate inverse `M_F^-1` 构造全部 80 modes 的低秩 correction：

```math
M_A^{-1}
\approx
M_F^{-1}
+
M_F^{-1}C
\left(H-DM_F^{-1}C\right)^{-1}
DM_F^{-1}.
```

允许实现等价的 condensed Woodbury/Schur form，但必须：

```text
- 保留全部 80 modes；
- 不缓存 49M nnz 的低质量 Q 作为默认；
- 小 Schur 维度和条件数可审计；
- response columns 可按需/批量/复用；
- 真实 outer residual 决定成功。
```

## 13.3 比较组

```text
F-MG only
F-MG + fixed 75D z-hat coarse
F-MG + all-mode low-rank correction
F-MG + all-mode correction + small global coarse
Task027 baseline
```

该 lane 是 Task030 的重点组合方向。

---

# 14. Lane 6：anisotropic / layer-aware / wave-aware 方向

这不是主线第一实现，但应允许至少两个低成本原型。

候选：

```text
- z-line or z-column smoother；
- layer-preserving semi-coarsening；
- material-interface strengthened patches；
- port-trace correction on top/bottom faces；
- impedance/optimized Schwarz on small layer blocks；
- directional multiplicative sweep over z slabs；
- symmetric forward/backward sweep；
- moving-PML-like or approximate layered inverse only as research prototype。
```

注意：Task020 的 diagonal slab sweep 已失败。新的 sweep 必须在真正 physical block/impedance interface 或 MG hierarchy 上具有新的机制，不能重复旧 diagonal proxy。

---

# 15. Lane 7：外层 Krylov 与 recycling

仅在 PC 结构固定并证明 apply 线性/确定后进行。

候选：

```text
FGMRES restart 100 baseline
GMRES restart 50/100
GCR
TFQMR
BiCGStab(l)
GCRO-DR / recycling
```

优先目的：

```text
- 减少 Krylov basis memory；
- 不显著增加 PC applies；
- 为后续参数扫描保留 recycling 可能性。
```

禁止用不同 Krylov 掩盖 PC 不收敛。若真残差轨迹无改善，只降低 reported residual，不得算正反馈。

---

# 16. h5 统一筛选协议

## 16.1 Level 0：代数 smoke

```text
small mesh / h5 setup
transfer action
coarse action
one PC apply
linearity test
MPI identity
memory leak/repeated apply
```

## 16.2 Level 1：固定预算筛选

每个候选至少运行：

```text
20-step smoke
100-step explicit true residual screen
```

Task027 h5 100-step true residual 作为统一 baseline，需从 canonical funnel record 读取，不得凭记忆硬编码。

## 16.3 正信号分类

### weak_positive

满足：

```text
100-step true residual <= 0.80 x Task027 h5 baseline
peak RSS <= 1.10 x Task027 h5
no algebra/numeric Gate failure
```

允许 1–2 轮针对性深化。

### strong_positive

满足任一：

```text
100-step true residual <= 0.50 x baseline
```

或：

```text
100-step residual <= 0.70 x baseline
and peak RSS <= 0.80 x Task027 h5
```

强正信号必须继续到 h5 full solve。

### memory_positive

```text
peak RSS <= 0.70 x Task027 h5
100-step residual no worse than 1.10 x baseline
```

可继续一次改善收敛质量。

### negative

```text
100-step residual > 1.25 x baseline
or memory > 1.20 x baseline without >2x residual gain
or true/report residual inconsistency
```

停止。

## 16.4 h5 full solve Gate

```text
full true residual <= 1e-6
same modal set and n_aux
R/T/A delta vs direct <= 1e-6
energy closure within existing Stage4 Gate
peak RSS <= Task027 h5
iterations <= 1000 preferred; <=1200 maximum positive
no swap growth
```

满足主要 Gate后进入 h3。

---

# 17. h3 升级协议

最多选择 3 个机制不同的 h5 strong candidates 进入 h3，避免只有同一路线的参数变体。

h3 先运行：

```text
100-step screen
memory/setup audit
```

正信号后完整求解。

## 17.1 h3 full Gate

```text
full true residual <= 1e-6
same 80 modes
R/T/A numeric Gate pass
peak RSS <= 3.8 GB strong target
or at least 25% reduction vs Task027 h3
iterations <= 1000 preferred
h5/h3 iteration ratio <= 2
no swap
operator complexity documented
```

若 h3 只能从 5.07 GB 降至约 4.7 GB 且迭代无明显改善，标记微调，不解锁 h2。

---

# 18. h2 条件解锁

默认：

```text
RUN_H2 = false
```

只有一个最佳 candidate 可以解锁 h2，并必须满足：

```text
G1 h5 full numeric Gate pass
G2 h3 full numeric Gate pass
G3 h3 peak RSS reduction >=25% vs Task027
G4 h5/h3 iteration ratio <=2
G5 two independent h2 memory predictions central <=10 GB
G6 prediction upper engineering bound <=12 GB
G7 no swap on h3
G8 same 80 modes and exact condensation
G9 memory watchdog configured
G10 ordinary default unchanged
```

h2 watchdog 建议：

```text
soft warning >=10.5 GB
controlled termination >=12.5 GB
hard host/cgroup safety margin preserved
```

h2 若运行，必须完成：

```text
full solve
full true residual
official per-order/total R/T
A_volume
closure
memory timeline
iteration history
PC/operator complexity
```

不允许只运行 factor/setup 后宣称成功。

---

# 19. 内存与复杂度遥测

复用并扩展 Task029 telemetry，至少记录：

```text
simultaneous worker RSS
process-tree RSS
cgroup current/peak
swap
stage markers
CPU utilization
setup/apply/solve timing
```

多层专用：

```text
number of levels
cells/DoF per level
nnz per level
operator complexity = sum nnz(levels) / nnz(fine)
grid complexity = sum DoF(levels) / DoF(fine)
transfer nnz/storage
patch count and size distribution
local factor nnz/storage
coarse factor memory
Krylov basis memory
low-rank Schur storage
cache storage
```

目标不是只移动峰值；必须说明内存来自哪里。

---

# 20. 数值可信度 Gate

所有 candidate：

```text
reported residual != success criterion
explicit condensed true residual required
explicit full augmented residual required for qualified full solve
```

必须验证：

```text
PC linearity or explain why FGMRES required
Hermitian/conjugation semantics
coarse operator action
transfer orientation
MPI ownership
Floquet phase
mode identity
auxiliary back-substitution
R/T/A reconstruction
energy closure
```

失败或未收敛的场不得输出 official R/T/A；若输出仅用于诊断，必须标记 `diagnostic_only=true`。

---

# 21. 允许的代码架构

建议新增独立模块，不把研究代码塞入 ordinary runtime：

```text
src/solvers/multilevel_hcurl.py
src/solvers/hcurl_transfer.py
src/solvers/hcurl_patch_smoother.py
src/solvers/dtn_low_rank_pc.py
src/studies/run_task030_multilevel_hcurl.py
```

具体文件可调整，但必须保持：

```text
- core reusable components 与 research runner 分离；
- Task027 stable solver 不被改写；
- ordinary main preset 不变；
- candidate profile 显式 opt-in；
- failed lanes 可以留分支，但 production merge 必须 selective。
```

---

# 22. Benchmark 与输出

建立：

```text
benchmarks/cases/060_multilevel_hcurl_iterative_solver/
```

建议结构：

```text
README.md
config.json
expected/gates.json
records/
  h5_baseline.json
  candidate_screen_summary.json
  best_h5.json
  best_h3.json
  best_h2.json        # only if run
  transfer_contract.json
  hierarchy_contract.json
run.sh / runner command
```

Task outcomes：

```text
docs/task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/
```

必需文件：

```text
README.md
summary.md
run_log.txt
test_summary.md
changed_files.md
environment.json
baseline_contract.md
hierarchy_design.md
transfer_validation.md
level_inventory.csv
candidate_funnel.csv
candidate_comparison.csv
memory_breakdown.csv
negative_results.md
h2_memory_prediction.md
h2_launch_decision.md
merge_recommendation.md
next_decision.md
```

每条 lane 至少记录：

```text
hypothesis
implementation
parameters
actual run status
true residual
memory
cost
root-cause interpretation
disposition
```

---

# 23. Task 回顾与文档合同

严格遵循：

```text
docs/task_retrospective_standard.md
```

Task030 最终审查前必须：

```text
- 完整编写 outcomes/summary.md；
- 在 docs/development_progress.md 新增独立 Task030 章节；
- 更新 docs/README.md；
- 更新 capability_matrix.md；
- 更新 solver_guide.md；
- 更新 benchmark.md；
- 更新相关 theory/walkthrough；
- 增加 documentation contract。
```

`development_progress.md` 至少说明：

```text
为什么 Task027 内存仍偏高
COMSOL 参考边界
探索了哪些 lane
正反馈如何继续
哪些方向失败以及为什么
最佳 h5/h3/h2 结果
最终合并什么
ordinary default 是否变化
下一步为什么这样安排
```

---

# 24. 测试要求

## 24.1 单元/代数测试

```text
mesh hierarchy identity
p2/p1 transfer
orientation
Floquet phase
corner constraints
MPI ownership
Galerkin action
rediscretized action comparison
smoother linearity
patch assembly
low-rank Schur
complex dot/Hermitian semantics
repeated apply stable memory
```

## 24.2 MPI

至少：

```text
MPI1
MPI2
MPI4
```

验证 transfer、PC apply、coarse solve 和 result identity。

## 24.3 项目回归

```text
ruff changed Python
compileall
Task026 condensation tests
Task027 physical-slab regression
Task029 telemetry tests
Task030 focused tests
full unit discovery
documentation contracts
benchmark checker --no-write
JSON/CSV parse
git diff --check
tracked source clean
```

---

# 25. 成功分类

## infrastructure_success

```text
hierarchy/transfer/MPI/telemetry correct
but no solver lane has useful residual performance
```

## diagnostic_success

```text
reliably identifies why tested multilevel lanes fail
and narrows the next mechanism
```

## research_positive

```text
h5 strong positive
but h3 not qualified
```

## engineering_success

```text
h5/h3 full solve pass
h3 memory >=25% lower than Task027
mesh iteration ratio <=2
h2 predicted <=10 GB central
```

## workstation_success

```text
h2 full solve pass
RSS <=10 GB
true residual <=1e-6
same 80 modes
R/T/A pass
```

## strong_workstation_success

```text
h2 RSS <=8 GB
iterations <=800
all numeric and physical gates pass
```

---

# 26. 合并原则

可以考虑合并：

```text
- validated hierarchy generator；
- validated H(curl) transfer；
- reusable low-memory smoother components；
- validated all-mode DtN low-rank PC；
- telemetry and Benchmark060；
- documentation and negative results；
- explicit candidate profile after final review。
```

不得自动合并：

```text
- failed lane production code；
- research runner as ordinary default；
- unqualified AMS/TFQMR/GMG profiles；
- heavy artifacts；
- h2 failed/partial outputs；
- reduced-mode shortcuts；
- private API hacks；
- changed ordinary default。
```

最终需要 ChatGPT review 和用户明确许可。

---

# 27. 优先执行顺序

Codex 应按以下顺序工作，但允许在 Stage B 后并行推进多个 lane：

```text
Stage A0 读取前序证据和冻结 baseline
Stage A1 hierarchy mesh
Stage A2 p/h transfer and MPI/Floquet validation
Stage A3 level operator and telemetry

Stage B1 polynomial smoother
Stage B2 small patch/Vanka smoother
Stage B3 pure h-GMG
Stage B4 mixed p/h MG
Stage B5 shifted p1 AMS/HX
Stage B6 all-mode DtN low-rank correction
Stage B7 anisotropic/layer-aware prototypes

Stage C unified h5 funnel
Stage D positive lanes h5 full solve
Stage E top candidates h3
Stage F h2 prediction and conditional single h2
Stage G documentation, selective merge recommendation and review
```

建议最先实现的组合：

```text
mixed p2->p1 h-GMG
+ low-memory polynomial/patch smoother
+ coarsest small MUMPS
+ all-mode DtN low-rank correction
+ outer FGMRES
```

但任务不要求该组合必然成功，也不限制 Codex 在统一 Gate 下发现更好的独立路线。

---

# 28. 最终决策问题

Task030 最终必须回答：

```text
1. Task027 的 slab ILU 内存是否可被真正多层架构显著替代？
2. 哪种 hierarchy 对本问题最有效：h、p 还是 mixed p/h？
3. 哪种 smoother 能低内存处理 p2 H(curl) 高频误差？
4. AMS/HX 在 shifted p1 level 上是否重新获得价值？
5. all-mode DtN low-rank Schur 是否能解决完整 port coupling 慢方向？
6. fine matrix-free + assembled coarse 是否可行？
7. h3 是否达到至少 25% 内存下降？
8. h2 是否预测/实测进入 10 GB？
9. 哪些代码可以进入 master，哪些必须留研究分支？
10. 下一步应进入 adaptivity、parameter robustness，还是继续某条多层正反馈？
```

---

# 29. 启动约束总结

```text
Task029 must be merged first
Task030 branch must start from updated clean master
h5 first
multiple mechanism lanes allowed
positive feedback must continue within scope
negative lanes stop with evidence
h3 only after h5 strong signal
h2 default locked
one best h2 only after all Gates
all 80 propagating modes retained
true residual and official R/T/A mandatory
ordinary default unchanged
```
