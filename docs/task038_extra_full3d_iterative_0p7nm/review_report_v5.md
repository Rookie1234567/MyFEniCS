# Task038-extra Review Report V5：冻结 N2 v1 负结果，授权单失败 exact-class 线性代数归因与条件恢复

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V5
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 8cb3cfd62586f4e050afe41932b54a823ee2f5d8
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 49 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v4.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v4.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
T1_T2_T3_T4                             = ACCEPTED_AND_FROZEN_PASS
R2_current_physical_dual                = ACCEPTED_AND_FROZEN_PASS
R3_current_difficult_residual           = ACCEPTED_AND_FROZEN_PASS
N0_capacity_preflight                   = ACCEPTED_AS_CONDITIONAL_BUDGET_PASS
N1_local_spectral_oracle                = ACCEPTED_AND_FROZEN_SMALL_FIXTURE_PASS
N2_v1_MPI1                              = ACCEPTED_CONTROLLED_NEGATIVE
N2_v1_reclassification                  = forbidden
N2_original_solve_gate                  = fixed at <= 1.0e-11
local_spectral_family_current_status    = HOLD_FOR_ONE_BOUNDED_LINEAR_ALGEBRA_DIAGNOSTIC
continuous_authorized_batch             = LA0 through LA5 below, conditional on every prior Gate
mandatory_review_stop                   = after LA5/N4 screen or any earlier hard stop
T6_full_solve_and_physics_recovery       = not authorized
T7_T8_T9                                = not authorized
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_write_or_merge                   = forbidden
whole_Task37_extra_migration            = forbidden
whole_Task039_migration                 = forbidden
amend_rebase_force_push                 = forbidden
response_required                       = response_v5.md
```

本 Review 接受 `response_v4.md` 的事实与停止行为。N0 的容量账本在冻结假设下得到 conditional pass；N1 在 p2/p3、MPI1/MPI2 小 fixture 上通过；N2 唯一一次 p6/h10、MPI1 formal attempt 在 `local_factor_build` 阶段触发：

```text
fixed local factor solve residual = 1.0426245523812324e-11
frozen Gate                       = 1.0000000000000000e-11
absolute excess                   = 4.26245523812324e-13
relative excess vs Gate           = 4.26245523812324%
```

该结果必须继续分类为：

```text
CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE
```

不得四舍五入为 pass，不得事后把 Gate 放宽到 `1.1e-11`，也不得覆盖、删除或改写原始 negative record。

但这次负结果与 Candidate C 的 12 GiB resource stop、D2 trace-harmonic 的 500-step CG failure不同。当前局部 Cholesky factor已经成功生成，唯一实际数值硬失败只是一个固定 RHS 的局部 solve residual略高于极严 Gate；同时现有实现对三角 Cholesky factor使用通用 `numpy.linalg.solve`，而失败 record没有保存 p6 矩阵的 Hermitian defect、condition estimate、factorization residual及独立 solve对照。

因此，本 Review 不直接关闭整个 `bounded_local_spectral_multilevel_v1`，也不直接放宽 Gate。只授权一次单失败 exact class 的线性代数归因，并根据预先冻结的决策树最多选择一种确定性修复。只有在原 `1e-11` Gate 下取得 fresh pass，才允许继续完整 N2 MPI1、MPI2、N3和条件 N4。

---

# 1. 对 Response V4 的审阅结论

## 1.1 Git、范围与停止行为

| 审阅项 | 结果 | 说明 |
|---|---|---|
| base / merge-base | pass | 均为 `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| reviewed HEAD | pass | `8cb3cfd62586f4e050afe41932b54a823ee2f5d8` |
| branch relation | pass | 审阅时 `ahead 49 / behind 0` |
| same branch | required | 继续当前执行分支，不新建分支或 worktree |
| ordinary default | unchanged | `full3d_iterative` 仍为显式 opt-in research method |
| master | unchanged | 未 merge、未写入 `master` |
| N2 stop | accepted | MPI1 local factor Gate失败后未进入 MPI2、N3、N4 |
| watchdog | accepted | 未外部终止；worker rc=1；no orphan；swap=0 |
| full 0.7 nm PDE | correctly not_run | 没有运行或伪造结果 |

Codex 拉取本 Review 后，开始 LA0 前必须重新报告：

```text
branch
HEAD
upstream
ahead/behind
git status --short
canonical worktree identity
Python/MPI/PETSc/DOLFINx/Basix/SciPy ABI
PETSc ScalarType/IntType
OMP/OpenBLAS/MKL threads
MemAvailable
system/process-tree/cgroup swap state
disk free
```

远端审阅无法观察本地 ignored artifacts 和 nonignored untracked 文件。工作树、ABI 或资源身份不合格时不得开始 LA0。

## 1.2 接受并冻结的正成果

以下能力继续保留：

| 资产 | 当前身份 | 后续用途 |
|---|---|---|
| T1 `.dat` contract | frozen pass | one-dat/one-run、resolved config与provenance |
| T2 full-space volume action | frozen pass | exact physical fine action |
| T3 dynamic streaming Fourier-DtN | frozen pass | exact top/bottom open-boundary action |
| T4 owner-local topology | frozen pass | MPC/Floquet、owner-local support与接口身份 |
| R2 current physical-dual oracle | frozen pass | 当前 RHS/component authority |
| R3 current-compatible difficult residual | frozen pass | 正式 long-tail source |
| N0 local-spectral capacity ledger | conditional budget pass | 设计上限，不是 p6实测资格 |
| N1 p2/p3 local-spectral oracle | frozen small-fixture pass | 局部代数、PoU、R/P和MPI source/action identity |
| watchdog/provenance | reusable pass | cold setup、online和termination资源权威 |

这些正结果不能推导：

```text
N2 complete setup pass
252-patch inventory pass
regional/top coarse pass
N3 contraction pass
N4 iterative screen pass
complete workflow < 2 GB
0.7 nm feasibility pass
```

## 1.3 N2 v1 controlled negative 的正式裁决

N2 v1 的正式事实为：

| item | measured / actual |
|---|---:|
| formal source SHA | `907fe8fb204cffa34a921c6d0cab7ff4dd4831b8` |
| case | p6/h10 MPI1 |
| failure stage | `local_factor_build` |
| local factor | lower-packed complex128 Cholesky |
| fixed RHS solve residual | `1.0426245523812324e-11` |
| Gate | `<=1.0e-11` |
| process-tree peak before failure | `1,506,271,232 B` |
| process-tree swap | `0 B` |
| warning / hard line | `1,800,000,000 B` / `2,000,000,000 B` |
| termination | worker rc=1；watchdog already_exited；无 SIGTERM/SIGKILL |
| post-setup sample | not obtained |
| MPI2 / N3 / N4 | not run by Gate |

这里的 `4.26245523812324%` 表示 residual相对极小 Gate的超出比例，不表示场解、R/T/A或任何物理量有4.26%误差。该 residual本身仍为约 `1.04e-11`。

N2 v1 的12条 checker错误是成功 schema 的 fail-closed边界，不是12个独立数值错误。唯一已证实的数值硬失败是 fixed RHS solve residual。

原 worker record 顶层 `source_identity.source_git_sha=null` 是保留的 evidence metadata defect；nested `runtime.source_identity` 正确绑定 formal SHA。不得修改旧 ignored record来制造闭合。fresh v2记录必须修复未来 negative/success record的顶层身份写入。

---

# 2. 为什么只授权一次窄诊断

## 2.1 当前未知根因

当前 `_PackedCholesky` 路径执行：

```text
B
→ numpy.linalg.cholesky(B)
→ lower triangle packed as complex128
→ reconstruct L
→ numpy.linalg.solve(L, b)
→ numpy.linalg.solve(L^H, y)
→ evaluate ||B x - b|| / ||b||
```

现有 negative record没有保存：

```text
failed exact-class digest
local row count
matrix SHA
fixed RHS SHA
||B-B^H||/||B||
lambda_min(B)
lambda_max(B)
kappa_2(B)
||L L^H-B||/||B||
packed-vs-unpacked solve difference
direct B solve residual
componentwise backward error
```

因此还不能区分：

```text
high-condition-number roundoff
small Hermitian/assembly defect
packed/unpacked factor defect
general-solve-on-triangular-factor accuracy debt
```

## 2.2 为什么不能直接放宽 Gate

原 Gate是预先冻结的 certification boundary。事后改成 `1.1e-11` 会把一次真实 negative重新命名为 pass，并且无法说明未来其他 exact classes是否只超出4.26%。

本 Review 要求：

```text
old N2 v1 remains FAIL
new implementation, if any, must pass the same <=1e-11 Gate
```

## 2.3 为什么不能立即关闭整条 family

与此前结构性负结果相比，本次：

```text
Cholesky factorization did not throw
resource hard line was not crossed
swap remained zero
failure margin was 4.262e-13 absolute
N1 p2/p3 local algebra passed at approximately 1e-15 scale
```

因此一次窄诊断具有科学价值。但如果诊断不能识别唯一的、可界定的 local-solve实现缺陷，则必须关闭该 family，不得演变为参数扫描或精度技巧 campaign。

---

# 3. 冻结物理、矩阵与诊断对象

LA0–LA2 必须保持：

```text
input/template              = current frozen full3d_iterative p6/h10 input
wavelength                  = 13.5 nm
degree / mesh target        = p6 / h10
scalar / index              = complex128 / int32
material and geometry       = unchanged
Floquet/MPC                 = unchanged
local auxiliary B0          = curl-curl + k0^2 * M_|epsilon|
patch construction          = unchanged fixed 1-cell design
exact-class digest rule     = unchanged
fixed RHS                   = unchanged j + 0.125 + 0.25i
original solve Gate         = <=1.0e-11
factor byte cap             = unchanged
class count cap             = unchanged
```

诊断对象只能是：

> 在 N2 v1 中第一个触发 fixed RHS solve Gate 的 exact class。

禁止遍历全部252 patches追逐最优结果，禁止换 RHS，禁止改变 scaling、tau、材料、patch、overlap、mode cap、regional/top rank或physical action。

诊断 artifact必须记录：

```text
exact-class digest
representative cell canonical identity
local rows
matrix and RHS SHA-256
matrix/factor finite status
all scalar diagnostics below
```

大 dense matrix可以留在 ignored artifact中，不得提交到Git；tracked只保存compact facts和hash。

---

# 4. 连续授权批次

```text
LA0  single-class extraction and diagnostic contract
→ LA1 one failed-class linear-algebra diagnostic
→ LA2 one deterministic repair chosen by the frozen decision tree
→ LA3 fresh cold N2 MPI1 complete setup
→ LA4 conditional N2 MPI2 setup/identity
→ LA5 conditional N3 contraction and N4 T6-S screen
→ response_v5.md and stop
```

正常通过时不需要在每个子阶段等待ChatGPT。任一 hard Gate触发时，保存真实结果、提交轻量证据、写 `response_v5.md` 并停止。

---

# 5. LA0：单失败 class 提取与合同

## 5.1 允许修改

允许新增窄诊断 runner/checker和focused tests，或在现有N2 builder中增加仅用于诊断的fail-before-register hook，用来在原失败位置保存：

```text
class digest
matrix metadata/hash
fixed RHS hash
original negative residual
```

允许修复未来 negative record的顶层 `source_identity` 写入，但不得修改旧 v1 raw/compact artifact。

## 5.2 禁止修改

LA0 不得：

```text
修改 _PackedCholesky.solve 的production行为
修改 1e-11 Gate
运行完整N2
运行MPI2
运行N3/N4/PDE
修改local B0、patch、mode或coarse设计
```

## 5.3 LA0 tests

至少覆盖：

```text
exact failed-class selection is deterministic
matrix/RHS hashes are repeatable
old v1 residual is reproduced within 1e-14 relative agreement
diagnostic does not accept physical RHS or residual
no global AIJ/Schur/factor or FE-sized numeric allgather
future negative record writes complete top-level source identity
```

若无法精确重现 v1 失败 class和residual，停止；不得对另一个“差不多”的class做诊断。

---

# 6. LA1：一次性局部线性代数归因

## 6.1 必须计算的指标

对唯一失败 class、同一固定 RHS，记录：

```text
n_rows
||B||_2 or independently labelled norm used
Hermitian defect = ||B-B^H|| / ||B||
lambda_min of Hermitian B
lambda_max of Hermitian B
kappa_2 estimate = lambda_max/lambda_min
factorization residual = ||L L^H-B|| / ||B||
```

并比较四条固定 solve路径：

```text
S0 current packed L + generic solve
S1 unpacked L + dedicated lower/upper triangular solve
S2 direct solve B x=b, diagnostic only
S3 S1 followed by exactly one deterministic iterative-refinement step
```

每条记录：

```text
relative residual ||B x-b||/||b||
normalized backward error ||B x-b||/(||B|| ||x||+||b||)
finite status
solution pairwise relative differences
peak temporary bytes if measurable
```

专用 triangular solve应调用 qualified environment中已有的BLAS/LAPACK triangular solve接口；不得自行写不稳定的Python回代。若采用SciPy，必须记录SciPy路径、版本和BLAS/LAPACK identity。

S3 只允许恰好一次：

```text
r0 = b-B x0
dx = L^{-H} L^{-1} r0
x1 = x0+dx
```

禁止测试2、3、5、10次 refinement。

## 6.2 诊断资源 Gate

```text
process-tree hard peak < 2,000,000,000 B
process-tree swap      = 0 B
one formal attempt only
threads                = 1
```

该诊断允许同时持有一个 `<=882 x 882` dense class matrix、factor和有限的eigensolver workspace；它是diagnostic，不是production retained布局。所有dense临时对象必须在阶段结束时释放。

## 6.3 LA1 checker独立性

checker必须从ignored matrix/RHS artifact重新计算核心scalar，不得只读取worker写出的`passed=true`。至少独立重算：

```text
matrix/RHS hashes
Hermitian defect
factorization residual
S0/S1/S2/S3 residual
backward errors
```

---

# 7. LA2：冻结决策树与最多一种修复

## 7.1 Path T：专用 triangular solve 通过

若全部满足：

```text
Hermitian defect       <=1e-11
factorization residual <=1e-11
lambda_min             >0
S1 residual            <=1e-11
S1 improves S0 by a reproducible nonzero amount
```

则唯一允许的production修复为：

```text
replace generic solve on L/L^H
with dedicated lower/upper triangular solve
```

不得同时增加refinement或修改Gate。

## 7.2 Path R：恰好一次 refinement 才通过

仅当：

```text
Path T prerequisites on matrix/factor pass
S1 residual >1e-11
S3 residual <=1e-11
S3 finite and deterministic
S2/direct diagnostic does not reveal a contradictory assembly failure
```

才允许production算法冻结为：

```text
dedicated triangular solve
+ exactly one deterministic refinement
```

不得保留可配置 refinement count，不得根据residual动态追加第二步。

## 7.3 Path C：condition-limited but backward-stable

若：

```text
Hermitian/factorization diagnostics pass
S1/S2/S3 all remain >1e-11
backward error is small and kappa_2 is large
```

则分类为：

```text
CONDITION_LIMITED_LOCAL_FACTOR_CERTIFICATION
```

本轮立即停止。不得在V5中改为condition-aware Gate，也不得放宽`1e-11`。是否重新设计certification必须由下一份Review单独决定。

## 7.4 Path A：assembly/Hermitian defect

若出现：

```text
Hermitian defect       >1e-11
lambda_min             <=0
factorization residual >1e-11
matrix/RHS identity mismatch
```

则停止并分类为local auxiliary assembly/identity defect。V5不授权修改cell tensor、orientation、MPC expansion或B0定义后直接续跑。

## 7.5 Path P：packed/unpacked defect

若dedicated solve仍失败，但packed/unpacked重建或factor hash显示单一明确错误，则允许修复该单一packing defect；修复后必须重新完成LA1并满足原Gate，才能进入LA3。

## 7.6 无唯一窄修时关闭

若无法落入Path T、R或P，正式关闭：

```text
bounded_local_spectral_multilevel_v1
= CLOSED_BY_LOCAL_FACTOR_CERTIFICATION
```

禁止继续测试：

```text
other RHS
other scaling
different factor type
mixed precision
multiple refinement steps
relaxed tolerance
class-specific exception
```

---

# 8. LA3：条件 fresh N2 MPI1 complete setup

只有Path T、R或P在新clean SHA下通过全部LA1 Gate，才允许一次fresh N2 MPI1。

## 8.1 必须从cold lifecycle运行

```text
new ignored artifact root
no reuse of v1 record
no warm-cache-only resource claim
watchdog covers JIT through post-setup release
one heavy job at a time
threads=1
```

JIT cache可以按仓库正常可复现机制存在，但不得把compiler/JIT阶段移出process-tree测量后称complete-workflow pass。必须清楚区分：

```text
cold/setup peak
post-setup retained
online identity apply peak
```

## 8.2 N2 MPI1 numerical Gate

全部满足：

```text
all exact classes <=32
all local active rows <=882
all factor bytes/class <=6,230,448 B
all local factorization residuals <=1e-11
all fixed RHS solve residuals <=1e-11
gradient rank exactly 3 per qualified class
local mode cap exactly 8
regional rank exactly 16
top rank exactly 32
Z16/Z32/AZ32/E32 finite
identity apply closure <=1e-11
no missing/duplicate canonical owner rows
```

若使用Path R，每个factor solve必须固定执行恰好一次refinement；不能只对失败class特判。

## 8.3 N2 MPI1 resource Gate

```text
cold complete process-tree peak < 2,000,000,000 B
post-setup retained authority   < 1,800,000,000 B
process-tree swap               = 0 B
no orphan                       = true
```

当前v1的`1,506,271,232 B`只是失败点之前的partial peak，不能作为v2 complete setup pass。

## 8.4 禁止项

```text
no global physical AIJ
no global Schur
no global or growing factor
no FE-sized numeric allgather
no per-rank complete factor replication
no per-rank full Z/AZ replication
no global direct coarse solve
```

任一失败即停止，不运行MPI2。

---

# 9. LA4：条件 N2 MPI2 setup与identity

只有LA3全部通过，才允许一次fresh MPI2 setup。

必须验证：

```text
same exact class set and operator digests
same deterministic class ownership rule
one global factor per exact class
no factor duplication across ranks
same patch/mode/regional/top identities
canonical Z16/Z32/AZ32 relative L2 <=1e-12
E32 relative difference <=1e-12
identity apply relative difference <=1e-12
missing/extra/duplicate = 0
```

资源Gate仍按整个process-tree：

```text
cold complete peak <2,000,000,000 B
post-setup retained <1,800,000,000 B
swap=0
```

MPI2若超过MPI1资源上限或产生复制，不得用per-rank RSS替代process-tree authority。

---

# 10. LA5：条件 N3 contraction与N4 screen

## 10.1 N3 五类 source

只有N2 MPI1/MPI2均通过，才运行：

| source | one-apply Gate |
|---|---:|
| physical RHS | `rho <=0.60` |
| R3 qualified difficult residual | `rho <=0.70` |
| checkerboard/high-frequency | `rho <=0.75` |
| gradient-dominated | `rho <=0.90` |
| curl-dominated | `rho <=0.90` |

必须同时报告：

```text
coarse-only rho
full multilevel PC rho
true action closure
repeat
MPI1/MPI2 identity
wall
cold/online process-tree peak
post-apply retained
swap
```

如果coarse-only或full multilevel需要source-dependent basis、residual fitting或改变N0/N1冻结参数，立即停止。

N3 resource Gate：

```text
online process-tree peak <2,000,000,000 B
swap=0
```

任一source Gate失败即停止，不运行N4。

## 10.2 N4 T6-S screen

只有N3全部通过，才允许运行p6/h10：

```text
right FGMRES
restart=20
checkpoints=20,100,150,200
```

Gate：

```text
iteration 20  true residual <=0.40
iteration 100 true residual <=0.05
iteration 200 true residual <=0.005
iteration 150 -> 200 relative improvement >=20%
process-tree peak <2,000,000,000 B
swap=0
```

N4结束后必须停止。本轮仍不授权：

```text
final 1e-6 solve
official E/H recovery
R/T/A/A_volume
diffraction channels
T7 h-scaling
T8 0.7 nm/2 TiB audit
T9 closeout or master integration
```

---

# 11. 证据、文件与提交要求

## 11.1 必需 outcomes

至少创建或更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/local_factor_linear_algebra_diagnostic.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/n2_local_factor_la_v1.json
```

若进入后续阶段，再创建版本化compact records：

```text
n2_local_spectral_setup_mpi1_v2.json
n2_local_spectral_setup_mpi2_v2.json
n3_local_spectral_contraction_v1.json
n4_t6s_screen_v1.json
```

原v1 negative record和raw hashes必须保留，不覆盖。

## 11.2 Tests

至少包含：

```text
single failed-class reproducibility
matrix/RHS digest closure
triangular solve correctness
one-step refinement exact-count contract
no dynamic refinement loop
old 1e-11 Gate unchanged
negative/success source-identity completeness
LA decision-tree checker tests
focused N2 regression
compileall
git diff --check
```

## 11.3 Commit与停止

允许多个职责清晰的focused commits；不得amend、rebase或force push。正式heavy run必须绑定clean source SHA。

最终必须提交并推送：

```text
docs/task038_extra_full3d_iterative_0p7nm/response_v5.md
```

然后停止等待ChatGPT审阅。

---

# 12. `response_v5.md` 必答矩阵

1. branch、base、Review V5 start、final source、upstream、ahead/behind和worktree；
2. old N2 v1 negative是否保持不变；
3. failed class digest、rows、matrix/RHS hashes；
4. Hermitian defect、lambda min/max、condition estimate；
5. factorization residual；
6. S0/S1/S2/S3 residual和backward error；
7. 最终选择Path T/R/P/C/A或close；
8. 是否修改production solve，以及为何只有这一种修改；
9. 原`1e-11` Gate是否完全未变；
10. diagnostic process-tree peak、swap和lifecycle；
11. 若运行N2 MPI1：完整inventory、factor/mode/coarse、Z/AZ/E、资源；
12. 若运行MPI2：cross-MPI identity和factor ownership；
13. 若运行N3：五类source的coarse-only/full PC rho与资源；
14. 若运行N4：20/100/150/200 true residual与资源；
15. measured、exact、derived、budget、failed、controlled_negative、not_run分类；
16. T6-F、official physics、T7–T9和0.7 nm边界；
17. selective-merge / research-only / do-not-merge建议；
18. 全部tracked compact和ignored raw hash索引。

---

# 13. Hard-stop 总表

任一发生立即停止受影响lane：

```text
failed class不能精确重现
matrix/RHS identity不闭合
Hermitian defect >1e-11
lambda_min <=0
factorization residual >1e-11
S1和S3均不能通过原1e-11 Gate
需要放宽Gate或class-specific exception
需要多于一次refinement
需要改变B0、patch、overlap、mode或coarse参数
LA diagnostic process-tree达到2GB或出现swap
N2 MPI1完整setup达到2GB或retained达到1.8GB
N2 MPI2 identity/resource失败
N3任一source contraction失败
N4任一checkpoint失败或形成平台
出现global AIJ/Schur/factor、numeric allgather或basis/factor复制
```

发生hard stop后不得继续“顺便运行”后续案例。

---

# 14. 当前项目判断

当前最准确的状态是：

```text
matrix-free exact Full3D action and DtN infrastructure = positive
current transmission-only sweep family                 = closed
current large-slab trace-harmonic family                = closed
bounded local-spectral small-fixture oracle             = positive
bounded local-spectral p6 production setup              = not qualified
```

N2 v1只证明当前packed local factor certification miss，不证明外层PC收敛，也不证明整个family应立即关闭。V5只允许把这个局部数值问题归因清楚。若原Gate可通过，再继续一次完整setup和contraction；若不能，必须关闭该family，不再把求解困难转移到更深的数值技巧或参数扫描中。
