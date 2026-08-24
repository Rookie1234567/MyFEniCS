# Task038-extra Review Report V11：LOR foundation PASS 后的确定性谱闭合、p6 基础内存锚点与低阶 edge multigrid 有界试验

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V11
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = a9396df8857eb8598873e3f876b5e44630c7675a
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 108 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v10_addendum.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v10.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
old_Q0_500_step_result                  = PERMANENT_NEGATIVE_UNDER_OLD_GATE
exact_LOR_edge_foundation_10000         = ACCEPTED_PASS_AT_ITERATION_3020
old_global_spectral_audit               = ACCEPTED_CONTROLLED_NEGATIVE; SPECTRUM_NOT_ESTABLISHED
current_multiplicative_HX_PCGAMG        = CLOSED_AS_PRODUCTION_INVERSE
additive_HX_v2                          = CLOSED; do not reactivate
LOR_high_to_low_foundation              = PROVISIONALLY_ACCEPTED
next_scalable_candidate                 = lor_edge_geometric_mg_v1, conditional
fallback_if_LOR_structure_fails         = same_mesh_hcurl_p_multigrid_design_only
primary_objective                       = final correctness under bounded memory
iteration_count_and_wall_time           = secondary
p6_h10_strategy_line                    = complete workflow below 2,000,000,000 B
continuous_authorized_batch             = S0 through S6 below, conditional on every prior Gate
mandatory_review_stop                   = after S6 or any earlier hard stop
p6_h10_physical_Maxwell                 = not authorized in V11
p6_h10_long_positive_solve              = not authorized in V11
p6_h5                                   = not authorized in V11
full_0p7nm_PDE                          = forbidden
0p7nm_2TiB_new_capacity_audit           = not authorized until measured p6 hierarchy evidence exists
ordinary_default_change                 = forbidden
master_merge                            = forbidden
response_required                       = response_v11.md
```

本 Review 继续服从项目最终目标：

> 在单节点约 2 TiB 物理内存内，以自主 FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解 0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

本轮不再围绕同一个 HX/PCGAMG 预条件器继续增加迭代上限、调整参数或构造第三个组合变体。最新结果已经把问题分成两个相互独立的 blocker：

1. **数学 blocker**：需要用不依赖迭代 eigensolver 运气的方式，确定高阶正定算子与 LOR edge 算子在全局独立自由度空间中的秩、正定性和谱关系；
2. **资源 blocker**：需要首次实测 p6/h10 的 matrix-free high-order + streaming DtN + LOR edge foundation 在保留 `restart=20` 工作空间后，是否仍有足够余量容纳一个可扩展低阶 inverse。

只有上述两项同时闭合，才允许实现一个固定、直接作用于 LOR edge 空间的 geometric multigrid 小型 oracle。V11 不授权物理 Maxwell 长求解，也不允许用小模型 direct factor 冒充 production coarse solve。

---

# 1. 对最新结果的审阅

## 1.1 旧 Q0 负结果永久保留

Review V10 Q0 Reference E 在固定：

```text
p3/h50
MPI1
random source
exact LOR edge inverse
right GMRES
restart = 20
max_it = 500
residual replacement every 20
```

下得到：

```text
final explicit true residual = 4.2034233790900783e-4 > 1e-8
```

这仍然是旧 500-step 合同下的真实 negative，不能删除、覆盖或重新分类。

## 1.2 foundation-E 正式通过

用户随后明确授权同一 foundation 路径最多运行 10,000 步。唯一正式 numerical foundation run 使用 fresh source、fresh artifact root 和 zero initial guess，实际在第 3020 步达到：

```text
final explicit true residual = 9.260562270838936e-9 <= 1e-8
```

完整 checkpoint 画像为：

| iteration | explicit true residual |
|---:|---:|
| 500 | `4.2034233790900783e-4` |
| 1000 | `4.401332743770308e-5` |
| 1500 | `3.282602742213605e-6` |
| 2000 | `5.321845410207366e-7` |
| 2500 | `7.438106631138348e-8` |
| 3000 | `1.005098887039319e-8` |
| 3020 | `9.260562270838936e-9` |

资源与生命周期事实为：

```text
matvec                    = 3170
PC apply                  = 3171
KSP destroy               = 151
outer wall                = 613.287 s
process-tree peak RSS     = 253,284,352 B
process-tree swap         = 0 B
single exact edge solve residual = 9.13154427545479e-16
finite / repeat / input unchanged / primal constraint = pass
```

因此 V11 正式接受：

> 高阶空间到 LOR edge 空间、exact `B_L^{-1}`、再回到高阶空间的基础路线，至少在 p3/h50 正定辅助问题上能够在固定 `restart=20` 和固定 Krylov 常驻内存下最终收敛。

这是一项数学 authority，不是 production PC。其 exact edge inverse 使用小模型 MUMPS factor，不能进入 p6 或 0.7 nm 生产路线。

## 1.3 当前 HX/PCGAMG 的 blocker 已被定位

同一 p3/h50 random 案例中，现有可扩展候选 `multiplicative HX + scalar PCGAMG` 在 2000 步后仍为：

```text
1.0278389622635529e-2
```

而 exact LOR edge inverse 在 2000 步时已经达到：

```text
5.321845410207366e-7
```

两者相差约 `1.93e4` 倍。因此当前主要数值 blocker不是 matrix-free high-order action、memory-first Krylov 生命周期或 LOR edge 矩阵可解性，而是：

```text
当前 HX + scalar PCGAMG 对 B_L^{-1} 的近似质量不足
```

V11 继续关闭当前 multiplicative HX/PCGAMG production inverse，禁止参数扫描；其代码和负证据保留为 research archive。

## 1.4 旧 global spectral audit 只表示“未建立”

随后唯一一次 global transfer/rank/spectral audit 使用 matrix-free pulled-high shell 和固定 SLEPc GHEP endpoint 配置。smallest endpoint 在 `max_it=500` 内得到：

```text
SLEPc reason = -1
converged    = 0
lambda_min   = not available
lambda_max   = not run / not available
condition    = not available
```

其 process-tree peak 为 `176,119,808 B`，swap 为 0。该结果接受为：

```text
CONTROLLED_NEGATIVE_GHEP_NONCONVERGENCE
SPECTRUM_NOT_ESTABLISHED
```

它不能被解释为：

```text
transfer rank deficient
lambda_min = 0
LOR foundation failed
geometric multigrid impossible
```

但也不能被写成谱等价性通过。V11 用一次小模型显式、确定性的 generalized Hermitian direct audit 替代继续提高同一 SLEPc 迭代上限。

---

# 2. 本轮工作与最终目标 blocker 的对应关系

| 阶段 | 直接消除的 blocker | 与 0.7 nm / 2 TiB 的关系 |
|---|---|---|
| S0 | 冻结 authority、删除 Gate 歧义 | 防止继续反复重解释同一负结果 |
| S1 | 确定全局 transfer 的秩、正定性和真实谱端点 | 判断 LOR 是否能作为高阶辅助空间长期保留 |
| S2 | 实测 p6/h10 LOR foundation 的完整基础 live set | 确认 2 GB 战略线内是否还有低阶 solver 和 recovery 余量 |
| S3 | 根据 S1/S2 作唯一分支决定 | 防止再产生无界 solver family 搜索 |
| S4 | 验证一个固定 LOR-edge geometric V-cycle | 用真正不同的低阶 inverse 替代已失败 HX/PCGAMG |
| S5 | 测量 p6/h10 geometric hierarchy 容量和最粗层规模 | 为后续 distributed p1 coarse solver 提供实测设计输入 |
| S6 | outcomes、response 和停止 | 保留完整可审计决策链 |

V11 不授权不能直接消除上述 blocker 的旁支研究。

---

# 3. 全局冻结条件与禁止项

## 3.1 继续使用的基础组件

```text
Task038 single-dat opt-in contract
full-space matrix-free Maxwell volume action
dynamic streaming Fourier-DtN
Floquet/MPC owner-local action and canonical authority
memory-first right GMRES restart=20 lifecycle
solution-only checkpoint and explicit true residual authority
existing high<->LOR edge transfer foundation
```

## 3.2 本轮禁止修改或扫描

```text
restart 10/30/40/80
FGMRES / GCROT / LGMRES / BiCGStab
edge Jacobi omega
auxiliary shift or coefficient
PCGAMG type / smoother / threshold / levels
HX correction order
additive-v2 or third HX variant
new Robin / sweep / trace-harmonic / local-spectral family
high-order global AIJ outside S1 p2/p3 audit
p6 exact LOR edge LU/MUMPS factor
global direct coarse solve in p6 or production
FE-sized numeric allgather
real/imag 2N production split
physical Maxwell long solve
full 0.7 nm PDE
```

## 3.3 数值权威

```text
small audit algebra     = independent action/work/rank/SPD/eigen-residual checks
iterative correctness   = explicit unpreconditioned true residual
resource correctness    = simultaneous process-tree peak + process-tree swap
physical correctness    = not exercised in V11
```

任何未运行项必须写为 `not_run` 或 `not_run_by_gate`，不能由 foundation-E PASS 外推。

---

# 4. S0：authority 冻结与实现边界

## 4.1 必须保留的历史事实

以下结果永久保留，不得覆盖：

```text
V10 Q0 Reference E 500-step negative
foundation-E 3020-step PASS
old global SLEPc audit controlled negative
old multiplicative HX/PCGAMG p3 failure
additive-v2 closed
V8/V9 scalar-owner and MPI internal diagnostics
```

## 4.2 S0 允许的代码工作

只允许为 S1–S5 增加通用、可测试的 audit/resource/oracle 组件。数值核心必须放入合适的 `src/solvers/` 模块；benchmark runner 只负责参数、watchdog、provenance 和轻量 evidence。

必须先增加 focused tests，覆盖：

```text
independent owner layout and row bijection
explicit transfer construction
matrix-free vs audit-AIJ action identity
generalized Hermitian endpoint residual recomputation
resource ledger and no-overwrite artifact lifecycle
geometric edge transfer orientation and phase-once contract
```

S0 不运行 heavy case。

---

# 5. S1：p2/p3 确定性全局 transfer / rank / spectral audit

## 5.1 目的

旧 audit 失败于 iterative GHEP endpoint 求解，未得到 `lambda_min`、`lambda_max` 或 rank。S1 在小规模 p2/h50、p3/h50、MPI1 上使用显式 audit matrices 和 generalized Hermitian direct endpoint solver，一次性建立不可再由迭代次数解释的结果。

## 5.2 允许的 audit-only 对象

仅在 p2/p3 小模型中允许：

```text
assembled high-order positive B_H AIJ
explicit sparse independent transfer L
reduced independent low-order edge matrix B_L
explicit pulled matrix A_pull = L^H B_H L
dense audit copies needed by a LAPACK generalized Hermitian endpoint solve
```

这些对象：

```text
只属于 audit
不得进入 p6
不得进入 production PC
不得改变 ordinary default
```

## 5.3 固定构造

在去除 Floquet/MPC slave identity rows后的独立 owner 坐标中：

```math
A_{\mathrm{pull}} = L^H B_H L.
```

必须验证：

1. high-order audit AIJ 与现有 matrix-free `B_H` 对至少 8 个确定性向量的 action relative `<=1e-11`；
2. primal/dual work identity relative `<=1e-12`；
3. `L` 的输入、输出独立维数闭合；
4. `L` 的 numerical rank 使用标准阈值：

```math
\tau_{\mathrm{rank}} = \max(m,n)\,\epsilon_{\mathrm{mach}}\,\sigma_{\max};
```

要求 rank 等于独立 owner 维数；
5. `B_L` 与 `A_pull` 的 Hermitian defect均 `<=1e-12`；
6. 两者 Cholesky/SPD 检查通过；
7. phase 只应用一次，orientation 和 owner mapping闭合。

## 5.4 确定性 endpoint solver

首选并冻结为：

```text
complex128 LAPACK generalized Hermitian direct endpoint solve
例如 scipy.linalg.eigh 的 subset endpoint driver
```

分别求最小和最大 generalized eigenvalue：

```math
A_{\mathrm{pull}} q = \lambda B_L q.
```

不得再次使用旧的 matrix-free `SMALLEST_REAL + STSHIFT + max_it` 方式，也不得扫描 SLEPc 参数。

必须独立重算每个 endpoint 的 residual：

```math
\eta_{\lambda}
=
\frac{\|A_{\mathrm{pull}}q-\lambda B_Lq\|}
{\max(\|A_{\mathrm{pull}}q\|,|\lambda|\|B_Lq\|)}.
```

Gate：

```text
endpoint residual <= 1e-10
lambda_min > max(n*eps*lambda_max, 0)
lambda_max finite
condition = lambda_max/lambda_min finite
```

`condition` 与 p2→p3 增长必须报告，但在 V11 中不设置事后人为 condition cap。当前用户优先级是最终正确性与内存；只要 transfer 满秩、两算子 SPD、endpoint可靠，condition大小属于后续迭代成本预测，不单独关闭 LOR。

## 5.5 S1 资源 Gate

```text
process-tree peak RSS < 2,000,000,000 B
process-tree swap     = 0
one heavy audit at a time
```

这是小模型 audit 上限，不是 p6 production 资格。

## 5.6 S1 决策

| 结果 | 决策 |
|---|---|
| rank、work、SPD、endpoint全部通过 | `LOR_GLOBAL_STRUCTURE_PASS`，进入 S2 |
| rank不足、非正定或 map/work identity失败 | `LOR_GLOBAL_STRUCTURE_FAIL`，关闭当前 LOR family，执行 S3 fallback docs-only 后停止 |
| direct endpoint solver出现明确实现缺陷 | 只允许修复一个可定位 defect并以 fresh SHA重跑；不得换回 iterative参数扫描 |
| 达到2 GB或swap | `AUDIT_RESOURCE_FAIL`，停止并保存证据 |

## 5.7 S1 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_global_spectral_audit_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_global_spectral_audit_v2.json
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_global_spectral_audit_v2_checker.json
```

---

# 6. S2：p6/h10 production-compatible LOR foundation 资源资格

## 6.1 启动条件

只有 S1 的 structural algebra通过，才运行 S2。

S2 与 geometric multigrid 数值资格解耦；它首先回答：在不保留已关闭 HX/PCGAMG 对象的前提下，p6/h10 是否存在足够的基础内存余量。

## 6.2 固定案例

```text
wavelength          = 13.5 nm
p / h               = p6 / h10
MPI                 = 1
scalar              = complex128
exact fine operator = matrix-free volume + streaming Fourier-DtN
periodicity         = dual Floquet MPC
```

## 6.3 必须构造并保留的对象

```text
mesh / p6 Nedelec space / Floquet MPC
matrix-free positive high action
matrix-free physical volume action
streaming Fourier-DtN action
fine LOR lowest-order edge topology
fine LOR positive edge sparse matrix B_L
high<->LOR primal/dual transfer metadata
memory-first GMRES restart20 vector reserve
minimal action/work vectors
```

## 6.4 明确不得保留的对象

```text
old scalar node matrix and HX correction hierarchy
PCGAMG hierarchy
p6 exact edge factor
high-order global AIJ
global dense transfer
global direct coarse factor
recovery field arrays
```

S2 必须执行至少 10 次：

```text
high positive action
physical volume + DtN action
high-to-low restriction
low edge matvec
low-to-high lift
```

并证明 repeated apply 不产生持续 live-set 增长。

## 6.5 对象级内存闭合

必须分别报告：

```text
mesh/space/MPC bytes
high-action retained bytes
DtN retained/work bytes
fine B_L rows/NNZ/index/numeric bytes
transfer/map bytes
high and low vector bytes
restart20 Krylov reserve bytes
PETSc hierarchy/object overhead
allocator/unattributed process-tree remainder
```

不得用 derived object bytes替代实测 process-tree RSS。

## 6.6 S2 资源 Gate

为了给未来 edge hierarchy、coarse solver、recovery和运行时波动保留余量，冻结：

```text
cold setup process-tree peak                         < 1,800,000,000 B
post-setup foundation + restart20 retained live set <= 1,550,000,000 B
process-tree/rank swap                               = 0
repeated-apply live-set growth                       <= 32,000,000 B
```

`1.55 GB` retained Gate为设计资格线，给2 GB完整流程保留约450 MB：

```text
>=250 MB  future edge hierarchy/coarse work
>=100 MB  recovery/postprocess reserve
>=100 MB  allocator/MPI/watchdog uncertainty margin
```

若基础 retained介于1.55–2.0 GB，不能写成“已经接近通过”，必须分类：

```text
BASE_FITS_BUT_NO_PRODUCTION_HEADROOM
```

并停止 geometric MG 实现。

## 6.7 S2 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_p6h10_foundation_resource_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_p6h10_foundation_resource_v1.json
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_p6h10_foundation_resource_v1_checker.json
```

---

# 7. S3：唯一分支决定

| S1 structural | S2 resource | 后续 |
|---|---|---|
| PASS | PASS | 进入 S4 `lor_edge_geometric_mg_v1` |
| FAIL | 任意 | 关闭 LOR；只写 same-mesh `p6→p3→p1` H(curl) p-multigrid 设计/容量文档，然后停止 |
| PASS | FAIL | 数学 foundation保留，但当前 p6 LOR storage architecture关闭；记录最大对象并停止 |
| PASS | `BASE_FITS_BUT_NO_PRODUCTION_HEADROOM` | 不实现新solver；先完成storage/lifecycle blocker清单并停止 |

fallback只允许生成：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/same_mesh_p_multigrid_fallback_design.md
```

不得在 V11 中实现第二个 solver family。

---

# 8. S4：固定 LOR-edge geometric multigrid 小型 oracle

## 8.1 启动条件

只有 S1 与 S2 同时 PASS 才运行。

## 8.2 它解决什么问题

foundation-E 已证明 exact `B_L^{-1}` 能最终求解高阶正定问题。S4 用一个直接作用于 LOR lowest-order edge 空间的 geometric V-cycle近似 `B_L^{-1}`，不再通过：

```text
gradient + Pi_x/Pi_y/Pi_z + scalar PCGAMG
```

间接近似 edge inverse。

## 8.3 唯一候选

```text
method = lor_edge_geometric_mg_v1
```

低阶 subcell 分辨率层级固定为：

```text
p2 oracle: 2 -> 1
p3 oracle: 3 -> 1
future p6 capacity: 6 -> 3 -> 1
```

层间 transfer使用最低阶 Nédélec edge line-integral interpolation/histopolation，不允许把非嵌套 edge空间当作简单 injection。

每层 operator为相同正定辅助物理系数下重新离散的 lowest-order edge operator；不得形成高阶 global AIJ。

## 8.4 固定 V-cycle

```text
one V-cycle per PC apply
one degree-3 Chebyshev smoother before coarse correction
one degree-3 Chebyshev smoother after coarse correction
Jacobi diagonal scaling
one deterministic 10-step power estimate per level
restriction = conjugate transpose of verified primal prolongation
```

禁止扫描：

```text
smoother degree
pre/post次数
spectral window
level count
transfer variant
V-cycle count
```

p2/p3 小 oracle 的最粗 p1 level允许 `PREONLY+LU/MUMPS`，仅用于隔离上层 geometric hierarchy。该 direct coarse不得进入 p6，也不得称为 production pass。

## 8.5 de Rham 与 transfer Gate

每个 level pair必须验证：

```text
orientation and phase once
owner/slave closure
primal prolongation legality
restriction adjoint work identity <= 1e-12
gradient/curl commuting identity  <= 1e-11
rediscretized coarse energy consistency <= 1e-9
linearity <= 1e-12
repeat    <= 1e-13
finite    = true
```

## 8.6 数值案例

```text
p2/h50 MPI1 and MPI2
p3/h50 MPI1 and MPI2
sources = random, gradient, curl, checkerboard
```

外层固定：

```text
right-preconditioned GMRES
restart = 20
max_it = 10,000
residual replacement every 20
explicit true residual authority
```

成功要求每个 individual case：

```text
final explicit true residual <= 1e-8
```

迭代次数和 wall time只作性能画像。10,000步仍未通过时关闭 `lor_edge_geometric_mg_v1`，不得调整 smoother、level或restart后重跑。

MPI1/MPI2最终 action comparison继续使用 residual-based动态上界；内部 level向量不要求逐项跨MPI相同，但每个 MPI PC自身必须linear、finite、repeatable并输出合法primal。

## 8.7 S4 小模型资源 Gate

```text
process-tree peak RSS < 500,000,000 B
process-tree swap     = 0
no retained Krylov basis across restart cycles
```

## 8.8 S4 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_edge_geometric_mg_oracle_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_oracle_v1.json
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_oracle_v1_checker.json
```

---

# 9. S5：p6/h10 edge hierarchy 容量与最粗层审计

## 9.1 启动条件

只有 S4 全部 small cases PASS 才运行。

## 9.2 固定范围

建立但不运行 p6 长求解：

```text
LOR edge levels = 6 -> 3 -> 1
all sparse edge matrices
all verified interlevel transfers
Chebyshev/Jacobi smoother metadata and bounded work vectors
restart20 high-space reserve
```

明确禁止：

```text
p1 global direct factor
p6 exact edge factor
p6 long positive solve
physical Maxwell solve
recovery/postprocess
```

S5 只执行：

```text
level action identity
transfer work/commuting identity
smoother one-apply legality
setup/destroy/rebuild lifecycle
object and process-tree memory closure
```

## 9.3 必须报告的 coarse facts

```text
level 6/3/1 rows and NNZ
matrix/index/numeric bytes per level
transfer rows/NNZ/bytes per level pair
smoother vectors/work bytes
p1 coarsest rows/NNZ
estimated distributed coarse-solver budget
retained and cold process-tree peak
```

这些数据将决定下一轮是：

```text
在p1 level上发展distributed h-multigrid/domain decomposition
```

还是因coarsest问题过大而调整层级设计。V11 不提前选择或实现 p1 production coarse solver。

## 9.4 S5 资源 Gate

```text
complete hierarchy cold setup peak < 2,000,000,000 B
post-setup retained              < 1,800,000,000 B
process-tree/rank swap            = 0
no global direct factor           = true
```

S5 PASS只能称为：

```text
P6_LOR_EDGE_HIERARCHY_RESOURCE_PASS_WITH_COARSE_SOLVER_OPEN
```

不能称为 p6 iterative solver pass。

## 9.5 S5 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_edge_geometric_mg_p6_capacity_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1.json
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1_checker.json
```

---

# 10. S6：结果闭环与停止

必须更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/development_progress.md
docs/task038_extra_full3d_iterative_0p7nm/response_v11.md
```

`response_v11.md` 必须逐项回答：

1. branch、HEAD、base、upstream、ahead/behind、worktree和ABI；
2. foundation-E PASS与旧500-step negative如何同时保留；
3. S1 p2/p3 transfer rank、singular endpoints、lambda endpoints、condition和residual；
4. S1 audit peak、swap和audit-only high AIJ边界；
5. S2 p6 foundation所有对象bytes、cold peak、retained、headroom和swap；
6. 是否进入 S4；若未进入，触发哪个唯一决策分支；
7. S4全部 individual case的true residual、iterations、MPI pair和资源；
8. S5 levels/rows/NNZ/bytes、coarsest规模和完整setup资源；
9. failed、controlled_negative、not_run与pass的明确分类；
10. changed files、tests、commands、raw/compact hashes和provenance；
11. 下一 blocker是否已经收敛为“p1 distributed coarse solver”；
12. ordinary default、master和完整0.7 nm PDE均未改变。

完成 S6 或任何更早 hard stop后：

```text
commit
push current branch
stop and wait for ChatGPT review
```

---

# 11. 测试要求

至少运行：

```text
new focused unit tests
existing LOR transfer/HX/root-cause/memory-first regressions
MPI1/MPI2 focused transfer tests
compileall for changed Python
git diff --check
JSON strict parse with allow_nan=false
Markdown rendering checks
```

若 Ruff在资格化环境不可用，必须如实记录，不得临时安装或声称通过。

正式 numerical run之后若修改任何数值核心、transfer、matrix construction或checker，相关 formal evidence失效，必须用 fresh SHA和fresh artifact root重跑受影响阶段。

---

# 12. 最终判断

最新 evidence不支持“LOR失败”，也不支持“当前HX已经可生产”。它支持更精确的判断：

```text
exact LOR edge foundation = mathematically viable at p3
current HX/PCGAMG inverse = insufficient and closed
full global spectrum      = not yet deterministically established
p6 foundation memory      = not yet measured
```

V11 的路线严格沿着最终目标推进：

```text
确定性闭合 LOR 全局结构
→ 实测 p6 基础 live set
→ 只测试一个直接 LOR-edge geometric hierarchy
→ 测量 p6 hierarchy 与最粗层规模
→ 下一轮只解决 distributed p1 coarse solver
```

这条路线不依赖内部材料可分离，不恢复 Hybrid 假设，不形成高阶 global factor，也不通过增大 restart换取收敛；它仍属于 arbitrary-3D Full3D matrix-free iterative 主线。