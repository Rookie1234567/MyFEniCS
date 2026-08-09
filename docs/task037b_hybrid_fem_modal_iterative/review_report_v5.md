# Task037b Review Report V5：多指标收敛一致化与完整物理闭环

## 0. 审阅身份与授权边界

```text
review                              = Task037b Review Report V5
reviewed_branch                     = codex/20260807-task37b-hybrid-iterative-development
reviewed_response                   = docs/task037b_hybrid_fem_modal_iterative/response_v5.md
reviewed_numerical_source           = eb1fc88483dd4d9cb5eabb071f8af0e87f91ba49
reviewed_parent                     = d3b15af96d4719f04dcf006c6caf98d1a2503366
ordinary_default                    = unchanged
merge_to_master                     = not_authorized
same_candidate_requalification      = authorized_once
custom_multimetric_convergence      = authorized
full_recovery_and_physics           = authorized_after_linear_gate
conditional_direct_authority_export = authorized_after_candidate_physics_pass
restart_sweep                       = not_authorized
MPI1_or_MPI4_full                   = not_authorized
PC_parameter_change                 = forbidden
new_PC_family                       = forbidden
LOR_HX_reopen                       = forbidden
production_qualification            = not_authorized
```

本报告接受 V4 的原始合同结论，不改写旧记录：

```text
FIXED_ILU0_WOODBURY_BLOCK_PC_FULL_NEGATIVE
```

该结论在 V4 冻结 Gate 下是正确的，因为第 534 步 bottom block true residual 为
`1.3641751886101987e-6`，高于 `1e-6`。但是，本次审阅同时确认：V4 不是预条件器发散、
平台或 breakdown，而是**外层停止条件和最终资格条件不一致**导致的受控局部 Gate miss。

第 534 步：

| 指标 | 实测值 | V4 Gate |
|---|---:|---:|
| PETSc reason | `2 = CONVERGED_RTOL` | `>0` |
| reported residual | `9.83224189598995e-7` | `<=1e-6` |
| global true residual | `9.832241902112744e-7` | `<=1e-6` |
| bottom block true residual | `1.3641751886101987e-6` | `<=1e-6`，未通过 |
| top block true residual | `7.290772097898545e-7` | `<=1e-6` |
| modal block true residual | `1.2365161175289584e-15` | `<=1e-6` |

V4 的 KSP 只根据 reported/global residual 达到 `1e-6` 而停止；post-solve qualification
却额外要求 bottom/top/modal 也同时达到 `1e-6`。因此 V5 只批准：

```text
same exact operator
+ same fixed double block-PC
+ same physical/discrete parameters
+ convergence-policy alignment
```

不得将 V5 当作新的算法候选、参数调优或容差放宽。

---

# 1. V4 的最终科学复核

## 1.1 已经证明的算法正结果

V4 已经真实证明：

- right FGMRES 正常返回正收敛 reason；
- global true residual 达到 `9.832e-7`；
- 200 步后的持续收缩预测基本正确，实际在 534 步达到 global `1e-6`；
- bottom/top 均使用 fixed whole-endcap ILU(0) + 40-mode DtN Woodbury；
- bottom/top direct factors 为 `0/0`；
- nested local FGMRES/KSP 为 false；
- global Hybrid AIJ matrix、global F、bottom/top A 均未物化；
- explicit external `C/D` 为 `0/0`；
- approximate modal Schur 为 `240x240`、rank `240`、condition finite；
- modal residual 全程约为 `1e-15`；
- callback identity、linearity、determinism、rank、condition 和生命周期全部通过。

因此，除非 V5 出现新的 exact-action regression，不得把 V4 的局部 Gate miss重新解释为：

```text
Hybrid block formula failure
DtN Woodbury sign failure
modal Schur failure
fixed block-PC family divergence
```

## 1.2 Bottom residual 没有平台证据

V4 完整 535 行 history 显示：

- reported/global/top residual 全 history 无正向回升；
- bottom residual 早期有 12 次正向回升；
- iteration `444 -> 534` 的最后 90 个间隔中，bottom residual 无回升；
- 最后 90 个间隔 bottom residual 有明确净改善；
- 运行在 `534 < 700` 时因 global RTOL 提前结束，而不是达到 max_it。

所以当前证据支持：

```text
bottom local equilibrium converges slightly later than global residual
```

不支持：

```text
bottom local equilibrium cannot reach 1e-6
```

## 1.3 Block residual 与 global residual 的尺度不同

全局残差为：

```math
\rho_{\mathrm{global}}
=
\frac{\lVert b-\mathcal Kx\rVert}{\lVert b\rVert}.
```

bottom block residual 使用局部平衡尺度：

```math
\rho_b
=
\frac{\lVert r_b\rVert}
{\max\left(
\lVert b_b\rVert,
\lVert A_bu_b\rVert,
\lVert T_ba\rVert,
10^{-30}
\right)}.
```

因此 global `9.83e-7` 与 bottom `1.36e-6` 并不矛盾。V5 不修改这一定义，也不放宽
bottom Gate；只让外层 KSP 真正运行到所有冻结指标同时通过。

## 1.4 资源负结果继续保留

V4 MPI8 process-tree RSS peak 为：

```text
6.289192199707031 GiB
```

按既有 `<=6.0 GiB` 线仍是 resource negative。V5 不是资源优化轮，不允许通过：

```text
restart change
object deletion before required audit
mode reduction
ILU compression
MPI count change
```

来获得较低峰值。数值、物理和资源继续分别分类。

---

# 2. V5 唯一允许的代码变化：多指标收敛策略

## 2.1 冻结求解器身份

以下内容全部保持 V4 原值：

```text
wavelength                     = 13.5 nm
polarization                   = S
incident grazing angle         = 10 deg
bottom/top interface           = 10 / 110 nm
endcap FE degree / mesh        = p6 / h10
modal FE degree / mesh         = p6 / h10
requested modes                = M120
modal unknowns                 = 240
external DtN modes/endcap      = 40
assembly backend               = assembly_time_static_condensed
internal propagation model     = full3d_uniform_cg
internal traction model        = scalar_cg_discrete_derivative
MPI                            = 8
outer KSP                      = right FGMRES
restart                        = 90
rtol metadata                  = 1e-6
atol                           = 0
max_it                         = 700
initial guess                  = zero
bottom/top subdomains          = 1 / 1
overlap                        = 0 / 0
ILU level                      = 0
bottom/top direct factor       = 0 / 0
nested local KSP               = false
fixed Woodbury action/callback = exactly one apply
```

不得更改任一项。

## 2.2 资格收敛条件

新增一个单一、纯函数式的多指标判定器。每个 iteration row 至少包含：

```text
reported_relative_residual
global_true_relative_residual
bottom_true_relative_residual
top_true_relative_residual
modal_true_relative_residual
```

定义：

```math
\rho_{\max}
=
\max\left(
\rho_{\mathrm{reported}},
\rho_{\mathrm{global}},
\rho_b,
\rho_t,
\rho_m
\right).
```

只有当：

```text
iteration > 0
all five residuals finite and non-negative
reported <= 1e-6
global   <= 1e-6
bottom   <= 1e-6
top      <= 1e-6
modal    <= 1e-6
```

时，custom convergence test 才可返回正收敛 reason。

若 PETSc build 支持 `CONVERGED_USER`，优先使用并记录：

```text
convergence_reason_identity = multimetric_true_residual_gate
```

若资格化 PETSc enum 不提供该值，可使用正的 `CONVERGED_RTOL`，但必须在 record 中明确：

```text
positive reason came from custom multimetric convergence test
```

不得将 default PETSc reported-residual convergence 冒充为 V5 多指标通过。

## 2.3 失败与继续规则

custom convergence test 必须遵守：

```text
任一 residual NaN/Inf/negative -> DIVERGED_NANORINF
iteration < 700 且未全部通过  -> ITERATING
iteration >= 700 且未全部通过 -> DIVERGED_MAX_IT
全部通过                        -> positive converged reason
```

禁止因为 global residual 已小于 `1e-6` 而提前结束。

## 2.4 每个 iteration 只能计算一次 exact row

V4 已在 monitor 中逐步计算 exact global/bottom/top/modal residual。V5 不得同时在 monitor 和
convergence test 中重复构造两份 exact row。

允许的结构是：

1. custom convergence test 调用一次 `snapshot(...)`；
2. 该 snapshot 同时：
   - 记录 history；
   - 触发 checkpoint；
   - 返回多指标 decision；
3. ordinary monitor 不再重复调用 exact `_residual_metrics(...)`，或仅消费已缓存 row；
4. 同一 iteration 在 history 中只允许一行权威记录。

要求审计：

```text
one authoritative history row per iteration
no duplicated exact residual action from monitor + convergence test
PC/action apply counts consistent with the chosen implementation
```

## 2.5 Post-solve 显式重算仍是最终权威

KSP 返回后必须使用 retained solution 再独立重算一次：

```text
reported residual
global true residual
bottom true residual
top true residual
modal true residual
```

最终线性 Gate只认这次 post-solve explicit recomputation。

若 custom convergence test 返回正 reason，但 post-solve 任何一项大于 `1e-6`，必须分类为：

```text
CUSTOM_CONVERGENCE_FALSE_POSITIVE
```

并停止，不得运行 field/R/T/A。

---

# 3. 实施前测试 Gate

## 3.1 纯判定器测试

至少新增以下测试：

| case | reported/global/bottom/top/modal | 预期 |
|---|---|---|
| V4 final replay | `9.83e-7 / 9.83e-7 / 1.364e-6 / 7.29e-7 / 1e-15` | `ITERATING` |
| all pass | 全部 `<=1e-6` | positive converged |
| global pass, top fail | top `>1e-6` | `ITERATING` |
| reported fail, true pass | reported `>1e-6` | `ITERATING` |
| NaN | 任一项 NaN | divergence |
| negative | 任一项小于 0 | divergence |
| max_it miss | iteration 700 且任一项未过 | max-it negative |

不得通过修改 `1e-6` threshold 让 V4 replay 直接通过。

## 3.2 KSP callback 集成测试

构造小型固定线性系统，验证：

- default reported residual先达到阈值时，custom test仍能继续；
- block residual随后达到阈值后，KSP才返回正 reason；
- history 每 iteration只有一条权威 row；
- final explicit row与 custom decision一致；
- max_it 与 NaN 路径 fail closed；
- restart仍为 90；
- ordinary solver path不受影响。

## 3.3 V4 candidate regression

必须继续通过：

- bottom/top fixed action identity；
- callback线性与确定性；
- K rank/condition；
- approximate modal Schur repeat；
- outer-ready direct factor `0/0`；
- no nested local KSP；
- lifecycle与borrowed action survival；
- residual failure时 official physics fail closed。

执行 focused serial tests，并对关键 callback/convergence/lifecycle tests运行 MPI2 和 MPI4。
随后执行：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

不得为了通过测试删除旧 V4 negative record、改变 threshold或修改 PC参数。

---

# 4. V5 正式候选运行

## 4.1 运行次数

只允许一次新的正式 MPI8 candidate run：

```text
same candidate
same zero initial guess
same restart90
same max_it700
same PC/action/modal Schur
custom multimetric convergence only
```

禁止：

```text
从 V4 solution warm start
从 iteration 534 continuation
读取旧 Krylov basis
失败后增加 max_it
失败后更改 rtol/restart/shift/ILU
```

这样才能确认 V5 与 V4 的唯一数值差异是停止策略，而不是初值或算法改变。

若 parent/worker 在进入 outer iteration 之前因纯 launch/schema/path wiring停止，可保留证据后做一次窄修复；一旦开始 numerical outer solve，不得为了改变结果自动重跑。

## 4.2 Checkpoints

除 V4 checkpoint外，至少增加：

```text
500, 520, 534, 540, 550, 560, 580, 600, 630, 700,
and the actual convergence iteration
```

每个 checkpoint记录：

```text
reported/global/bottom/top/modal residual
multimetric max residual
custom convergence decision
PC apply count
bottom/top fixed-action apply count
elapsed time
```

## 4.3 线性 Gate

正式 candidate只有在 post-solve explicit recomputation满足以下全部条件时通过：

```text
KSP converged reason              > 0
iterations                        <= 700
reported relative residual        <= 1e-6
Hybrid global true residual       <= 1e-6
bottom block true residual        <= 1e-6
top block true residual           <= 1e-6
modal block true residual         <= 1e-6
all residuals finite              = true
bottom/top direct factors         = 0/0
nested local KSP                  = false
no direct fallback                = true
```

若 700 步仍未全部通过，分类为：

```text
MULTIMETRIC_LINEAR_GATE_NOT_REACHED_BY_700
```

这不自动证明所有 Hybrid iterative PC 不可行，但 V5 不再批准继续增加 max_it。

---

# 5. 线性通过后的对象生命周期

## 5.1 必须先保存的最小结果

在销毁 solver/PC 前复制并保留：

```text
complete Hybrid solution snapshot
bottom active trace solution
top active trace solution
240 modal amplitudes
final five residual metrics
external auxiliary recovery inputs
canonical identity metadata
```

必须记录 retained snapshot 的：

```text
global/local size
dtype
ownership
finite status
content hash
```

## 5.2 释放顺序

线性 Gate通过后，先完成 final explicit residual audit，再按顺序释放：

1. outer KSP 与 FGMRES basis；
2. Python PC context；
3. bottom/top whole-endcap ILU factors；
4. bottom/top Woodbury `W/K/LU`；
5. approximate modal Schur 与 LU；
6. 仅为 PC setup持有的临时 vectors和components。

必须保留：

```text
retained final solution
exact borrowed bottom/top actions
static-condensation recovery authority
modal coupling and mode identities
postprocess所需最小 mesh/function-space objects
```

然后验证：

```text
factor count 1/1 -> 0/0
borrowed exact actions still usable
post-release final residual repeat <= 1e-10 relative
```

## 5.3 Snapshot 最终销毁证据

V4 只记录了 snapshot retained，没有完整 `snapshot_destroyed` 证据。V5 完成全部 recovery、export
和checker输入写出后，必须显式销毁 retained solution及其split副本，并记录：

```text
snapshot_destroyed = true
bottom_snapshot_destroyed = true
top_snapshot_destroyed = true
modal_snapshot_released = true
```

不得用进程退出代替生命周期证据。

---

# 6. Candidate 自身恢复与物理 Gate

线性 Gate未通过时，本节全部保持 `not_run_dependency_gate`。

## 6.1 External auxiliary recovery

按：

```math
q_s
=
H_s^{-1}(g_s-D_su_s),
\qquad s\in\{b,t\}
```

恢复外部 modal amplitudes。要求：

```text
mode-key closure                 exact
missing/extra/duplicate          0/0/0
beta/polarization/Rayleigh flags exact
recovery/action identity         <=1e-10
all amplitudes finite            true
```

## 6.2 Bottom/top full-FE recovery

从 active trace solution恢复：

- eliminated cell-interior DoFs；
- MPC slave DoFs；
- bottom/top完整 FE vectors。

至少验证：

```text
active-trace equation residual       <=1e-6
full local augmented residual        <=1e-6
eliminated-interior relative residual<=1e-6
MPC/Floquet identity                 <=1e-10
all recovered vectors finite         true
```

不得只用 condensed residual代替 full-FE recovery residual。

## 6.3 Candidate 自身物理输出

完成并保存：

```text
R_total
T_total
A_volume_total
A_volume_by_material
R+T+A_volume
energy closure
all external diffraction orders
12 significant powers
12 significant boundary amplitudes
interface E/H samples
middle-plane E/H samples
canonical active vectors
canonical full-FE vectors
240 modal amplitudes
```

所有输出必须绑定：

```text
source SHA
solver configuration
solution hash
mode-key digest
canonical-key digest
```

---

# 7. Authority payload 审计与独立比较

## 7.1 先做只读 payload inventory

在正式 candidate run之前，可执行一次不运行 PDE 的只读 inventory，检查：

```text
H1 direct authority existing payloads
pinned Full3D authority existing payloads
Case095 significant-channel authority
```

必须区分：

```text
scalar summary exists
numeric array exists
manifest exists
hash/pass label only
```

禁止用旧 `pass=true`、hash标签或零数组冒充缺失数值载荷。

## 7.2 必须直接复用的权威

以下不需要重跑：

- pinned Full3D authority及其已存在数值 payload；
- Case095 `significant_channel_reference_v1.json` 的冻结 12+12 threshold；
- H1 direct Hybrid 已有的 scalar R/T/A、residual和已记录 field-error summary。

所有 threshold沿用原 authority，不得放宽。

## 7.3 条件批准一次 direct-Hybrid authority export

V4 checker 已明确记录 H1 缺少：

```text
modal numeric vector
canonical numeric manifests/vectors
selected interface/middle E/H numeric arrays
```

如果只读 inventory确认这些 payload确实不存在，则在以下条件全部满足后，V5 才批准一次
**独立、隔离的 direct-Hybrid authority-export run**：

```text
candidate multimetric linear Gate pass
candidate own recovery pass
candidate own R/T/A and 12+12 pass
candidate process already exited and released all objects
```

该 direct run要求：

```text
same p6/h10 physical/discrete identity
same M120 and 40 external modes/endcap
same direct Hybrid authority solver
MPI8
no candidate objects in memory
no parameter changes
output-only additions for missing arrays/manifests
```

它只用于生成：

```text
240 modal amplitudes
canonical active/full vectors
selected interface E/H arrays
selected middle-plane E/H arrays
12+12 numeric rows
R/T/A and A_volume scalar authority
```

该 direct run的内存和时间不得计入 candidate online resource authority。

如果现有 H1 raw already包含可验证数组，则优先只读提取并生成 compact export，不得无意义重跑 direct PDE。

## 7.4 独立 checker

candidate process完全结束后，独立checker至少比较：

1. candidate vs direct Hybrid：
   - 240 modal amplitudes；
   - canonical active/full vectors；
   - selected interface E/H；
   - selected middle-plane E/H；
   - R/T/A 与 A_volume；
2. candidate vs Case095：
   - 12/12 powers；
   - 12/12 complex amplitudes；
3. candidate vs pinned Full3D：
   - available canonical/selected-field quantities；
   - R/T/A；
   - significant channels；
   - energy closure。

所有比较使用既有 H1/Task36/Case095/Full3D tolerance；V5 不新增更宽 threshold。

如果 candidate own physics通过，但 direct authority payload仍无法建立，分类必须是：

```text
NUMERICAL_AND_OWN_PHYSICS_PASS_AUTHORITY_PAYLOAD_INCOMPLETE
```

不得伪造 full qualification pass。

---

# 8. 资源与时间 Gate

## 8.1 Candidate online authority

candidate online process的权威范围包括：

```text
mode/QEP
action/coupling setup
block-PC/modal-Schur setup
full outer solve
solver/PC release
full-FE recovery
candidate field/RTA/canonical export
candidate cleanup
```

不包括后续独立 direct authority-export run和offline checker。

必须报告：

```text
process-tree RSS peak
worker simultaneous RSS/PSS/USS
swap observations and readability
stage of peak
wall time by phase
factor/W/K/Schur/Krylov inventory
```

## 8.2 分类线不变

```text
MPI8 resource-positive     <=6.0 GiB process-tree RSS
MPI8 engineering-positive  <=5.0 GiB process-tree RSS
stretch                    <=3.77 GiB process-tree RSS
```

数值与物理通过但 RSS高于 6 GiB时，分类为：

```text
numerical and physics pass / MPI8 resource negative
```

不得把资源负结果写成线性求解失败。

## 8.3 Swap authority

若 all-live per-rank/process-tree swap samples完整可读且均为 0，可记 zero-swap pass。

若 post-exit `/proc` 不可读但所有 all-live samples完整，应将“正常退出后的不可读”和“运行中
缺失 authority”分开记录；不得因为进程已退出而伪造 all-live gap。

若任一 all-live authority sample无法读取，则 zero-swap资格保持 `unqualified`，但这不改变数值
和物理结论。

本轮不批准专门的资源优化或 watchdog语义大改；只允许修复显然把“正常退出后不可读”误报成
“运行中 authority丢失”的窄逻辑，并必须有单元测试。

---

# 9. 最终分类矩阵

## 9.1 完整通过

若：

- 多指标线性 Gate全部通过；
- recovery/full-FE residual通过；
- candidate own physics通过；
- 12+12通过；
- direct/Full3D comparisons通过；

则记录：

```text
DOUBLE_APPROXIMATE_MPI8_FULL_NUMERICAL_AND_PHYSICS_PASS
```

资源另行写：

```text
MPI8_RESOURCE_POSITIVE
或
MPI8_RESOURCE_NEGATIVE
```

## 9.2 线性通过但 authority payload不完整

```text
NUMERICAL_AND_OWN_PHYSICS_PASS_AUTHORITY_PAYLOAD_INCOMPLETE
```

## 9.3 线性通过但 recovery/physics失败

```text
MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL
```

必须明确失败发生于：

```text
external recovery
full-FE recovery
field reconstruction
12+12
R/T/A
energy closure
direct comparison
Full3D comparison
```

## 9.4 700 步未达到多指标 Gate

```text
MULTIMETRIC_LINEAR_GATE_NOT_REACHED_BY_700
```

记录 final reported/global/bottom/top/modal、最后 90 步趋势和是否存在平台；不得自动增加 max_it。

## 9.5 Custom convergence false positive

```text
CUSTOM_CONVERGENCE_FALSE_POSITIVE
```

若 KSP正 reason但 post-solve explicit recomputation未全部通过，physics必须 not_run。

---

# 10. 明确禁止事项

V5 禁止：

- 修改 `1e-6` residual Gate；
- 把 bottom Gate改成 `1.5e-6`；
- 将 global pass直接当 full linear pass；
- warm start或从 V4 iteration 534 continuation；
- 修改 restart90、max_it700、shift、overlap、ILU level；
- 增加 local Krylov steps或nested KSP；
- 修改 M120、external mode count或接口位置；
- 重新开启 LOR/AMS/HX、p2/p4/p-multigrid、full-space ILU；
- 运行角度、偏振、p/h或波长扫描；
- 运行 0.7 nm PDE；
- 在 candidate进程中同时加载 direct/Full3D solver对象；
- 候选通过后自动进行 restart sweep、MPI1/MPI4或内存优化；
- merge master或修改 ordinary default。

---

# 11. 执行顺序

```text
V5-0  读取 V4/V5 evidence，完成 authority payload inventory

V5-1  实现纯多指标 convergence decision

V5-2  将 V4 full solver 接到 custom convergence test
       每 iteration只生成一条 exact history row

V5-3  完成 focused serial/MPI2/MPI4、Ruff、compileall、diff-check

V5-4  唯一 MPI8 same-candidate requalification run
       zero initial / restart90 / max_it700

V5-5  post-solve explicit five-residual audit

V5-6  若线性通过：
       保存 solution snapshot
       释放 KSP/PC/factors/W/K/modal Schur
       完成 external/full-FE recovery与candidate own physics

V5-7  若现有 H1 payload缺失且candidate own physics通过：
       运行一次隔离 direct-Hybrid authority-export

V5-8  独立 checker完成 direct/Case095/Full3D比较

V5-9  写 compact record、outcomes和 response_v6.md
       停止等待审阅
```

---

# 12. Codex 最终回报格式

最终只报告：

```text
V5 implementation source SHA
formal candidate source SHA
custom convergence reason identity
actual iteration count
final reported/global/bottom/top/modal residual
post-solve explicit recomputation pass/fail
candidate recovery/full-FE residuals
R/T/A/A_volume/closure
12/12 powers and amplitudes
canonical/modal/selected-field comparison summary
direct authority payload source or conditional rerun SHA
Full3D comparison summary
candidate online process-tree RSS/PSS/USS/swap status
candidate phase timings
snapshot/factor/W/K/Schur lifecycle status
focused serial/MPI test summary
full pytest status or explicit not_run
final numerical/physics/resource classification
```

随后停止。不得自动进入 restart、MPI1、MPI4、0.7 nm或新候选。

---

# 13. 最终主审结论

```text
V4 global convergence                 = pass
V4 local bottom qualification         = near-miss under mismatched stop policy
fixed double block-PC capacity         = demonstrated
algorithm change required              = no
convergence-policy alignment required  = yes
same-candidate MPI8 requalification    = authorized once
full recovery/physics after linear pass= authorized
conditional direct payload export      = authorized
resource optimization                  = deferred
new PC family                          = forbidden
master merge                           = not authorized
```
