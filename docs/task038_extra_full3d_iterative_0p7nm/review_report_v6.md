# Task038-extra Review Report V6：冻结 N2 v1/v2 负结果，授权最后一次全 exact-class backward-stability 认证

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V6
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = e2ab499fb0d12e9c8f8ba5fbb931bb20294c25ea
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 58 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v5.md
reviewed_response_addendum              = docs/task038_extra_full3d_iterative_0p7nm/response_v5_addendum.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v5.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
T1_T2_T3_T4                             = ACCEPTED_AND_FROZEN_PASS
R2_current_physical_dual                = ACCEPTED_AND_FROZEN_PASS
R3_current_difficult_residual           = ACCEPTED_AND_FROZEN_PASS
N0_capacity_preflight                   = ACCEPTED_AS_CONDITIONAL_BUDGET_PASS
N1_small_fixture_oracle                 = ACCEPTED_AND_FROZEN_PASS
LA0_LA1_v3                              = ACCEPTED_DIAGNOSTIC_PATH_T_PASS
production_triangular_repair            = ACCEPTED_AS_RESEARCH_FIX_ONLY
N2_v1_under_certification_v1            = ACCEPTED_CONTROLLED_NEGATIVE
N2_v2_under_certification_v1            = ACCEPTED_CONTROLLED_NEGATIVE
N2_v1_v2_reclassification               = forbidden
certification_v1_relative_residual_gate = HISTORICAL_ONLY; old results remain FAIL
local_spectral_family_current_status    = HOLD_FOR_ONE_FINAL_ALL_CLASS_CERTIFICATION
new_certification_contract              = LOCAL_FACTOR_CERTIFICATION_V2_PROSPECTIVE_ONLY
continuous_authorized_batch             = FC0 through FC5 below, conditional on every prior Gate
mandatory_review_stop                   = after FC5/N4 screen or any earlier hard stop
T6_full_solve_and_physics_recovery      = not authorized
T7_T8_T9                                = not authorized
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_write_or_merge                   = forbidden
whole_Task37_extra_migration            = forbidden
whole_Task039_migration                 = forbidden
amend_rebase_force_push                 = forbidden
response_required                       = response_v6.md
```

本 Review 接受当前远端证据：

1. LA0/LA1 v3 在同一 p6/h10、同一首个失败 exact class、同一固定 RHS 下精确重现旧 N2 v1 的 `S0=1.0426245523812324e-11`；
2. 专用 `scipy.linalg.solve_triangular` 路径得到 `S1=9.316208748538303e-12`，满足旧 `1e-11` Gate，形成有效的 `Path T` 归因；
3. 该 class 的 Hermitian defect、factorization residual、packed roundtrip和 normalized backward error均显示局部矩阵与 Cholesky factor本身闭合；
4. production `_PackedCholesky.solve` 随后只改为两次专用 triangular solve，没有 refinement、fallback、B0、patch、mode、coarse或 Gate变化；
5. fresh N2 MPI1 v2 在完整 class registration 的后续未具名 class 上仍出现 `1.1089747142000698e-11 > 1e-11`，因此 N2 v2仍是正式 controlled negative，后续 MPI2、N3、N4均正确未运行。

当前不能继续采用以下循环：

```text
遇到一个 class 的 relative residual略超1e-11
→ 单独诊断该 class
→ 再添加一种 class-specific 精度修复
→ 重跑直到遇到下一个 class
```

这会把项目退化为逐 class 精度追逐，并允许根据已见结果不断调整规则。

另一方面，首个已诊断 class 的数据表明：

```text
Hermitian defect             = 9.757433025229162e-17
factorization residual       = 8.158904706122267e-16
kappa_2                      = 5.757670411589122e7
S1 normalized backward error = 8.058382790658791e-19
S1 relative residual         = 9.316208748538303e-12
```

因此，一个与矩阵条件数无关、只看 `||Bx-b||/||b|| <= 1e-11` 的单一 hard Gate，不能独立区分：

```text
backward-stable direct solve with condition-amplified ordinary residual
versus
assembly/factor/packing/solve defect
```

本 Review 不回溯修改旧 Gate和旧结果，而是建立一个**全新、只对未来运行生效**的 `LOCAL_FACTOR_CERTIFICATION_V2`。它要求一次覆盖全部 exact classes 的统一认证，用 Hermitian、SPD、condition、factorization和 normalized backward-error Gate共同裁决，并保留一个固定的 ordinary relative-residual safety cap。

这条 local-spectral family只再获得这一次全 class资格审查。若任一 class、资源或后续完整 setup Gate失败，则正式关闭；不得继续修改 threshold、逐 class修补、增加 refinement、切换 precision或重新扫描 local solver。

---

# 1. 对 Response V5 及补充结果的审阅

## 1.1 Git、范围与停止行为

| 审阅项 | 结果 | 说明 |
|---|---|---|
| base / merge-base | pass | 均为 `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| reviewed HEAD | pass | `e2ab499fb0d12e9c8f8ba5fbb931bb20294c25ea` |
| branch relation | pass | 审阅时 `ahead 58 / behind 0` |
| same branch | required | 继续当前执行分支，不新建分支或 worktree |
| ordinary default | unchanged | `full3d_iterative` 仍是显式 opt-in research method |
| master | unchanged | 未 merge、未写入 `master` |
| old evidence | preserved | N2 v1、LA v1/v2/v3、N2 v2均未删除或重分类 |
| N2 v2 stop | accepted | local factor Gate失败后未进入 MPI2、N3、N4 |
| resource stop | not triggered | N2 v2失败点前 peak约1.505 GB，swap=0；不是完整 setup pass |
| full 0.7 nm PDE | correctly not_run | 没有运行或伪造结果 |

Codex 拉取本 Review 后，开始 FC0 前必须重新报告：

```text
branch
HEAD
upstream
ahead/behind
git status --short
canonical worktree identity
Python/MPI/PETSc/DOLFINx/Basix/SciPy ABI
PETSc ScalarType/IntType
OMP/OpenBLAS/MKL/NUMEXPR threads
MemAvailable
system/process-tree/cgroup swap state
disk free
```

远端审阅无法观察本地 ignored artifacts 和 nonignored untracked 文件。工作树、ABI、threads或资源身份不合格时不得开始 FC0。

## 1.2 继续接受并冻结的正成果

| 资产 | 当前身份 | 后续用途 |
|---|---|---|
| T1 `.dat` contract | frozen pass | one-dat/one-run、resolved config与provenance |
| T2 full-space volume action | frozen pass | exact physical fine action |
| T3 dynamic streaming Fourier-DtN | frozen pass | exact top/bottom open-boundary action |
| T4 owner-local topology | frozen pass | MPC/Floquet、owner-local support与接口身份 |
| R2 current physical-dual oracle | frozen pass | 当前 RHS/component authority |
| R3 difficult residual | frozen pass | 正式 long-tail source |
| N0 capacity ledger | conditional budget pass | 设计预算，不是完整 setup实测 |
| N1 p2/p3 oracle | frozen small-fixture pass | 局部代数、PoU、R/P与MPI identity |
| LA v3 Path T | diagnostic pass | 证明 generic solve可被专用 triangular solve替代 |
| watchdog/provenance | reusable pass | cold setup、online与termination资源权威 |

这些正结果不能推导：

```text
all p6 exact classes certified
N2 complete setup pass
regional/top coarse pass
N3 contraction pass
N4 iterative screen pass
complete workflow <2GB
0.7nm feasibility pass
```

## 1.3 LA v3 的正式接受边界

LA v3 捕获的 class：

```text
digest = 0c6b9830423f8baf83b6714ac178c724b63af1359d01b3ca5badd1d40c070a67
rows   = 882
slot   = 1
```

正式数值：

| path | relative residual | normalized backward error | classification |
|---|---:|---:|---|
| S0 generic solve | `1.0426245523812324e-11` | `9.01854818500637e-19` | reproduces N2 v1 negative |
| S1 triangular solve | `9.316208748538303e-12` | `8.058382790658791e-19` | Path T candidate pass |
| S2 direct full-B solve | `2.544882468429781e-11` | `2.2012856990841358e-18` | diagnostic only |
| S3 S1 + one refinement | `6.672944399115928e-12` | `5.771998219478778e-19` | diagnostic only; not production |

`Path T` 证明专用 triangular solve是一个明确、单一、合理的实现修复。它没有证明所有 exact classes都通过，也没有授权 refinement。

## 1.4 production triangular repair 的边界

提交 `b20de4960db4210f510195cff6136c72cd990b3f` 将：

```text
np.linalg.solve(L,b)
np.linalg.solve(L^H,y)
```

替换为：

```text
scipy.linalg.solve_triangular(L,b,lower=True)
scipy.linalg.solve_triangular(L^H,y,lower=False)
```

本 Review保留该修复作为当前 research candidate。仍禁止：

```text
iterative refinement in production
fallback to generic/direct solve
class-specific solve path
long double / mixed precision
matrix scaling campaign
B0/patch/mode/coarse parameter changes
```

只有 FC1全 class认证和 FC3完整 N2通过后，该修复才可进入后续 selective-merge候选。

## 1.5 N2 v1/v2 负结果永久冻结

| run | solve implementation | residual | historical Gate | status |
|---|---|---:|---:|---|
| N2 v1 | generic triangular factors through `np.linalg.solve` | `1.0426245523812324e-11` | `<=1e-11` | controlled negative |
| N2 v2 | dedicated triangular solve | `1.1089747142000698e-11` | `<=1e-11` | controlled negative |

两个结果均不得改写为 pass。`LOCAL_FACTOR_CERTIFICATION_V2` 是新 prospective contract，不回溯作用于 v1/v2。

---

# 2. 为什么需要全 class、condition-aware、backward-stability 认证

## 2.1 两种误差的区别

旧 fixed RHS ordinary relative residual：

```math
\eta_{rel}=\frac{\|Bx-b\|_2}{\|b\|_2}.
```

新的 normalized normwise backward error：

```math
\eta_{back}=\frac{\|Bx-b\|_2}{\|B\|_2\|x\|_2+\|b\|_2}.
```

`eta_rel` 会受到 `||B|| ||x|| / ||b||` 和条件数影响。`eta_back` 衡量需要对矩阵和右端项施加多小的相对扰动，才能使计算解成为精确解，更适合判断直接分解和三角求解是否 backward stable。

本任务仍保留 ordinary relative residual，但不再允许它作为唯一 certification observable。

## 2.2 为什么必须增加 condition cap

只看很小的 backward error仍不够。若局部矩阵条件数极大，forward error和局部逆的有效性可能变差。因此 certification v2同时要求：

```text
Hermitian identity
strict positive definiteness
bounded kappa_2
small factorization defect
small normalized backward error
fixed ordinary-residual safety cap
```

这不是降低物理 Maxwell精度。`B0` 是预条件器的正定辅助局部算子；最终物理正确性仍由 exact full-space Maxwell action、true residual、E/H和R/T/A Gates裁决。

## 2.3 为什么不能再逐 class诊断

fresh N2 v2 已证明：修复首个 class后，还可能在后续 class触发旧 Gate。若继续逐 class增加解法，会形成开放式精度 campaign。

因此 FC1 必须一次覆盖**全部** deterministic exact classes，并使用完全统一的阈值。任何 class失败都使整个 family失败。

---

# 3. LOCAL_FACTOR_CERTIFICATION_V2 的冻结数学合同

## 3.1 固定对象

FC0–FC3 必须保持：

```text
input/template              = current frozen full3d_iterative p6/h10 input
wavelength                  = 13.5 nm
degree / mesh target        = p6 / h10
scalar / index              = complex128 / int32
material and geometry       = unchanged
Floquet/MPC                 = unchanged
local auxiliary B0          = curl-curl + k0^2 M_|epsilon|
patch construction          = fixed 1-cell shared-row-overlap design
exact-class digest/order    = unchanged
fixed RHS                   = arange(n)+(0.125+0.25j)
solve                       = exactly two dedicated triangular solves
factor storage              = lower-packed complex128
factor byte cap             = 6,230,448 B/class
class count cap             = 32
mode/regional/top design    = unchanged from Review V4
```

禁止改变：

```text
B0
patch size or overlap
class coalescing rule
fixed RHS
factor format
mode cap 8
regional rank16
top rank32
levels=2
physical action
```

## 3.2 机器精度与尺寸尺度

定义：

```text
eps64   = 2.220446049250313e-16
n       = local active rows, 1 <= n <= 882
gamma_n = n*eps64/(1-n*eps64)
```

在最大 `n=882` 时：

```text
gamma_882      = 1.9584334154391596e-13
8*gamma_882    = 1.5667467323513277e-12
16*gamma_882   = 3.1334934647026553e-12
```

这些公式和常数在查看 FC1 全 class结果之前冻结，不得根据结果调整。

## 3.3 每个 exact class 的 hard Gates

对每个 class 的原始 constrained `B0`，全部满足：

```text
finite matrix/RHS/factor/solution                         = true
1 <= rows <= 882                                          = true
Hermitian defect_F <= max(1e-13, 8*gamma_n)               = true
lambda_min((B+B^H)/2) > 0                                 = true
kappa_2((B+B^H)/2) <= 1.0e8                              = true
packed lower roundtrip exact and hash-equal               = true
factorization defect_F <= max(1e-13, 16*gamma_n)          = true
triangular solve repeat exact                             = true
normalized backward error_2 <= max(1e-14,16*gamma_n)      = true
ordinary relative residual_2 <= 1.0e-10                   = true
factor bytes <= 6,230,448                                 = true
```

这里：

```text
Hermitian defect_F = ||B-B^H||_F / ||B||_F
factorization defect_F = ||L L^H-B||_F / ||B||_F
normalized backward error_2 uses spectral ||B||_2 and Euclidean vector norms
ordinary relative residual_2 = ||Bx-b||_2/||b||_2
```

`1e-10` 是新 contract 中事前冻结的 safety cap，不是旧 v1/v2 Gate的重命名。旧 v1/v2仍然 FAIL。新 cap只在上述 Hermitian/SPD/condition/factorization/backward Gates全部通过时有效。

## 3.4 全局 class inventory Gates

```text
exact class count                   <= 32
one deterministic owner per class   = true
duplicate/missing class digest       = 0
total packed factor bytes            <= 199,374,336 B
all class matrices processed         = class_count
all class certificates passed        = class_count
class order repeat/hash               = exact
no class-specific threshold/exception = true
```

## 3.5 为什么不授权 refinement

LA v3 的 S3虽然更小，但本项目已经选择 Path T。FC1/FC2只认证 dedicated triangular solve。

禁止：

```text
one or more production refinement steps
fallback based on class residual
per-class solve selection
iterative residual correction campaign
```

若 dedicated triangular solve不能使全部 classes通过 certification v2，则关闭 family。

---

# 4. 连续授权批次

```text
FC0  all-class certification-v2 runner/checker and tests
→ FC1 one formal p6/h10 MPI1 all-class certification audit
→ FC2 conditional prospective certification-v2 production wiring
→ FC3 one fresh cold N2 MPI1 complete setup
→ FC4 conditional N2 MPI2 setup/identity
→ FC5 conditional N3 contraction and N4 T6-S screen
→ response_v6.md and stop
```

正常通过时不需要在各阶段等待 ChatGPT。任一 hard Gate触发时，保存真实证据、提交轻量文件、创建 `response_v6.md` 并停止。

本轮仍不授权：

```text
T6-F final 1e-6 solve
official E/H recovery
R/T/A/A_volume
full diffraction-channel recovery
T7 h-scaling
T8 0.7 nm/2 TiB audit
T9 merge/closeout
full 0.7 nm PDE
```

---

# 5. FC0：全 class认证实现与测试

## 5.1 允许实现

允许新增窄的：

```text
all-class certification runner
independent checker
compact-record schema
focused tests
prospective certification-v2 helper
```

FC0 runner只允许：

```text
build mesh/space/MPC and deterministic exact-class inventory
construct one representative B0 at a time
factor and diagnose the current class
write/hash its ignored matrix/RHS evidence
release dense B0 before next class
```

禁止 FC0 构造：

```text
local modes
regional/top coarse
Z/AZ/E
physical RHS/residual
outer KSP/PDE
```

## 5.2 顺序与 fail behavior

FC1 不得因为旧 `1e-11` relative-residual Gate提前停止。它必须在安全范围内遍历全部 classes，以获得完整分布。

若发生以下严重条件，允许立即 fail closed：

```text
non-finite matrix/factor
Cholesky failure
lambda_min <= 0
class count >32
process-tree >=2GB
swap >0
evidence path collision or source identity failure
```

若只是 certification-v2 scalar Gate失败，应记录该 class并继续处理剩余 classes；最终 overall status仍为 FAIL。

## 5.3 Artifact合同

每个 class至少记录：

```text
class digest and deterministic slot
representative canonical cell identity
rows
matrix SHA-256
RHS SHA-256
factor SHA-256
factor bytes
Hermitian defect
lambda_min/lambda_max/kappa_2
factorization defect
packed roundtrip identity
triangular relative residual
normalized backward error
repeat identity
all individual Gate booleans
```

建议 ignored artifacts逐 class保存：

```text
class_<slot>_<digest-prefix>_B.npy
class_<slot>_<digest-prefix>_rhs.npy
```

独立 checker必须从 ignored matrices重新计算数值，不得只相信 worker status。

tracked compact必须包括：

```text
all scalar per-class facts
worst-class identity for every metric
class-count/factor-byte closure
resource/provenance summary
raw paths and SHA-256
```

## 5.4 FC0 focused tests

至少覆盖：

```text
gamma_n threshold formula exactness
n=882 threshold constants
all Gates at boundary/pass/fail
all-class order and digest repeat
no early stop on historical 1e-11-only miss
immediate stop on non-SPD/non-finite/resource/path collision
one dense class matrix live at a time
matrix/RHS/factor hashes repeat
independent checker recomputation
old N2 v1/v2 evidence unchanged
no refinement/fallback/class-specific exception
no global AIJ/Schur/factor or FE-sized numeric allgather
```

---

# 6. FC1：唯一一次正式全 exact-class认证

## 6.1 Formal case

```text
case             = p6/h10
MPI              = 1
attempt          = exactly one under Review V6
source           = new clean SHA after FC0
artifact root    = new ignored v6 root
watchdog warning = 1,800,000,000 B
watchdog hard    = 2,000,000,000 B
swap             = 0
```

旧 v1/v2/v3 artifact roots不得删除、覆盖或复用。

## 6.2 FC1 numerical PASS

全部满足：

```text
all deterministic exact classes discovered
class count <=32
all per-class certification-v2 Gates pass
total factor-byte arithmetic closes
independent checker pass
worker/checker/watchdog rc0
source/provenance/hash closure pass
```

## 6.3 FC1 resource PASS

```text
simultaneous process-tree peak < 2,000,000,000 B
process-tree swap = 0 B
no SIGKILL/OOM/orphan
dense class matrices are sequentially released
no complete setup or online claim is made
```

FC1只是 factor-certification audit。即使 peak低于2GB，也不能称 N2完整 setup通过。

## 6.4 FC1 failure decision

任一 class未通过 certification v2，或资源/identity Gate失败：

```text
bounded_local_spectral_multilevel_v1
= CLOSED_BY_ALL_CLASS_FACTOR_CERTIFICATION
```

然后：

```text
FC2-FC5 not_run_by_gate
response_v6.md
commit/push/stop
```

禁止再：

```text
诊断单个失败 class
提高1e-10 safety cap
提高kappa cap
改变gamma multiplier
增加refinement
换precision
缩小/改变patch
修改B0
```

---

# 7. FC2：条件 prospective production certification-v2 wiring

只有 FC1全部通过才允许 FC2。

## 7.1 允许修改

在 local factor registration中引入单一：

```text
LOCAL_FACTOR_CERTIFICATION_V2
```

要求 fresh N2 setup对每个 class重新计算并保存同一组 metrics。不得只读取 FC1 compact后跳过运行时认证。

production solve保持：

```text
exactly two scipy.linalg.solve_triangular calls
no refinement
no fallback
```

## 7.2 历史 Gate处理

不得删除或修改旧常数、旧 records或旧 checker解释。

在新代码中必须清楚区分：

```text
certification_v1_relative_residual_1e-11 = historical result identity
certification_v2                         = prospective current research contract
```

旧 v1/v2 run仍为 FAIL。

## 7.3 禁止全局放宽其他 Gate

不得把通用：

```text
N1_ALGEBRA_LIMIT
Hermitian/eigen/PoU/RP/repeat Gates
```

统一改成 `1e-10`。只允许新增职责明确的 local-factor certification-v2 fields和constants。

---

# 8. FC3：条件 fresh cold N2 MPI1 complete setup

只有 FC1和FC2全部通过，才允许一次 fresh N2 MPI1。

## 8.1 Frozen setup

```text
p6/h10
MPI1
current exact full-space action
current dynamic streaming DtN
same 252-cell anchor inventory
same fixed patch design
same mode cap8
regional rank16
top rank32
certification v2 for every exact class
```

不得改变 local-spectral设计或删减 setup对象以满足内存。

## 8.2 Numerical/setup Gates

```text
all class certificates pass v2
exact class count <=32
total factor bytes <=199,374,336 B
all 252 patches accounted for
all local mode shards complete
regional Z16 complete
top Z32 and AZ32 complete
E32 complete and finite
zero/identity apply closure pass
repeat pass
forbidden-materialization audit pass
```

## 8.3 Resource Gates

```text
cold complete-setup process-tree peak < 2,000,000,000 B
post-setup retained <= 1,798,919,864 B
process-tree swap = 0 B
post-setup dwell/sample present
no orphan/SIGKILL/OOM
```

`1.505 GB` 的 N2 v2 early-failure peak不能替代 FC3完整 setup资源。

## 8.4 FC3 failure

任一 Gate失败：

```text
bounded_local_spectral_multilevel_v1
= CLOSED_BY_COMPLETE_N2_SETUP
```

FC4/FC5不运行，写 `response_v6.md` 后停止。不得再修改 certification或内存布局追逐通过。

---

# 9. FC4：条件 N2 MPI2 setup与identity

只有 FC3全部通过才允许一次 fresh MPI2。

必须验证：

```text
same exact class set/order/operator digests
same per-class certification metrics within fixed comparison tolerance
same total factor bytes globally
one deterministic factor owner per class
no per-rank full factor duplication
same Z16/Z32/AZ32/E32 canonical packets
missing/extra/duplicate canonical keys = 0
cross-MPI relative L2 <=1e-12
process-tree peak <2,000,000,000 B
post-setup retained <=1,798,919,864 B
swap=0
```

MPI2不得通过每 rank复制全部 factors或basis制造 identity。

任一失败，关闭该 family并停止。

---

# 10. FC5：条件 N3 contraction与 N4 T6-S screen

只有 FC3/FC4全部通过才允许 FC5。

## 10.1 N3 五类 residual contraction

必须使用 current exact physical operator计算 before/after true residual norm。

| source | Gate |
|---|---:|
| physical RHS | `rho <= 0.60` |
| R3 current-compatible long-tail residual | `rho <= 0.70` |
| checkerboard/high-frequency | `rho <= 0.75` |
| gradient-dominated | `rho <= 0.90` |
| curl-dominated | `rho <= 0.90` |

还要求：

```text
repeat <=1e-12
true action closure <=1e-11
process-tree peak <2,000,000,000 B
swap=0
```

任一 source失败即停止，不进入 N4，不增加 modes/ranks/levels/patch或solver参数。

## 10.2 N4 T6-S screen

只有 N3全部通过，才运行冻结的 p6/h10、right FGMRES、restart20 screen：

```text
iteration 20  true residual <=0.40
iteration 100 true residual <=0.05
iteration 200 true residual <=0.005
iteration 150→200 relative improvement >=20%
no terminal plateau classification
process-tree peak <2,000,000,000 B
swap=0
```

运行到200步后必须停止。不得继续 final `1e-6` solve或物理恢复。

---

# 11. Hard-stop 总表

任一条件触发，保存真实证据、写 `response_v6.md`、提交推送并停止：

1. branch/HEAD/worktree/ABI/source identity不合格；
2. old N2 v1/v2 evidence被修改、删除或重分类；
3. exact class count超过32；
4. 任一 class非有限、非Hermitian超Gate、非SPD或`kappa_2>1e8`；
5. 任一 class factorization/backward/relative-residual certification-v2 Gate失败；
6. packed roundtrip或repeat不闭合；
7. FC1或后续 process-tree达到2GB、swap>0、OOM/SIGKILL/orphan；
8. 需要 refinement、fallback、class-specific exception或提高阈值才能继续；
9. FC3完整 setup任何 inventory/coarse/retained Gate失败；
10. FC4 MPI identity或ownership失败；
11. N3任一 residual contraction失败；
12. N4 iteration checkpoint失败或形成平台；
13. 需要 global AIJ、global Schur、global factor、global direct coarse solve、FE-sized numeric allgather或per-rank full basis/factor复制；
14. 试图运行 T6-F、official physics、T7–T9或full 0.7nm PDE。

若 FC1、FC3、FC4、N3或N4任一失败，本 Review不授权新的 local-spectral变体。

---

# 12. 文件与提交计划

建议按职责提交：

```text
1. test/task038: add all-class factor certification-v2 contract
2. evidence/task038: record formal all-class factor certification
3. solver/task038: wire prospective factor certification v2       # only if FC1 passes
4. evidence/task038: record fresh N2 MPI1/MPI2                    # conditional
5. evidence/task038: record N3/N4 screen                          # conditional
6. docs/task038-extra: respond to review v6
```

禁止 amend、squash负结果、force push或删除旧 artifacts。

必须创建/更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/local_factor_all_class_certification.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/n2_local_factor_all_class_cert_v2.json
```

若运行 FC3/FC4/FC5，再创建版本化的 setup/contraction/screen records，不覆盖 v1/v2。

最终创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/response_v6.md
```

---

# 13. `response_v6.md` 必答矩阵

1. branch、HEAD、base、upstream、ahead/behind、worktree、ABI；
2. old N2 v1/v2 negative是否原样保留；
3. FC0实现和focused tests；
4. eps/gamma formulas及实际 per-row thresholds；
5. 完整 exact-class count/order/digests/rows；
6. 每个 class的 Hermitian/SPD/kappa/factorization/packing/relative residual/backward error；
7. worst class identity for every metric；
8. total factor bytes和owner/class closure；
9. FC1 process-tree peak/swap/lifecycle；
10. certification-v2 overall PASS/FAIL及独立 checker；
11. 是否执行 FC2，以及 production solve/certification具体变化；
12. 若执行 FC3：完整 N2 MPI1 inventory、Z/AZ/E、retained和cold peak；
13. 若执行 FC4：MPI2 ownership/canonical identity和资源；
14. 若执行 N3：五类 source的before/after/rho/repeat/closure和资源；
15. 若执行 N4：20/100/150/200 true residual、wall、RSS、swap和平台判断；
16. measured/exact/derived/budget/failed/controlled_stop/not_run分类；
17. selective-merge建议；
18. T6-F、official physics、T7–T9和0.7nm边界；
19. commits、commands、artifact paths和SHA-256；
20. 最终建议：继续、关闭或只保留基础设施。

---

# 14. 本 Review 的最终判断

当前已经证明：

```text
专用 triangular solve 是首个 class 的正确窄修
但单 class Path T 不能推出全 class N2 pass
旧 fixed relative-residual-only Gate 对条件差异敏感
```

本 Review允许的最后一步不是继续逐 class调试，而是：

> 用一次统一、全覆盖、事前冻结的 backward-stability认证，决定 fixed-size local-spectral factors是否作为一个整体值得继续。

若全部 classes认证并完成 N2/N3/N4 Gate，这条路线才获得新的正证据；若任一阶段失败，则正式关闭 `bounded_local_spectral_multilevel_v1`，保留 T1–T4、R2/R3和其他 matrix-free基础设施，停止继续围绕局部 factor精度开发。
