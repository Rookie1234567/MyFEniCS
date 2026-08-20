# Task038-extra Review Report V2：接受 T1–T4，恢复 T5 physical-dual authority，并条件授权 sweep contraction 与 T6 screen

## 0. 审阅身份与决定

```text
review                                  = Task038-extra Review Report V2
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 4d4f65aaa5c3cfd79ec5a7f3defb33174b94e674
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 18 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v1.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v1.md
T1_status                               = ACCEPTED_AND_FROZEN_CONTRACT_PASS
T2_status                               = ACCEPTED_AND_FROZEN_ACTION_PASS
T3_status                               = ACCEPTED_AND_FROZEN_DYNAMIC_DTN_PASS
T4_status                               = ACCEPTED_AND_FROZEN_INTERFACE_ACTION_PASS
T5_status                               = ACCEPTED_CONTROLLED_STOP_BEFORE_CONTRACTION
T5_algorithm_result                     = NOT_TESTED
T6_status                               = NOT_RUN_BY_GATE
review_classification                   = PASS_WITH_BOUNDED_AUTHORITY_RECOVERY
continuous_authorized_batch             = R0 through R5 below
routine_stop_between_R0_and_R4          = not required when all prior Gates pass
mandatory_review_stop                   = after T6-S screen, any earlier hard stop, or authority recovery failure
T6_full_solve_and_physics_recovery       = not authorized
T7_T8_T9                                = not authorized
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
whole_Task37_extra_migration            = forbidden
whole_Task039_migration                 = forbidden
amend_rebase_force_push                 = forbidden
response_required                       = response_v2.md
```

本 Review 接受 `response_v1.md` 对上一批次的主要分类：T1–T4 已形成当前 `master` 基线上的 fresh evidence；T5 在真正运行 Candidate A/B/C 以前，由 long-tail residual authority Gate 阻止；T6 及后续阶段没有运行。该停止是正确的 fail-closed 行为。

当前不能把结果写成“sweep 失败”或“Candidate A 失败”。已知失败的是 old/current physical RHS coefficient bridge，不是 forward-backward sweep 的 contraction。反过来，也不能因为 T2–T4 通过就推断 sweep 会收敛或 0.7 nm 已具可行性。

为避免再次只完成一个很小诊断后停止，本 Review 将以下工作作为一个连续、有界批次授权：

```text
R0 重新确认 branch / ABI / artifact authority
→ R1 冻结 old/current physical identity 与 component inventory
→ R2 建立 top-boundary physical-dual component oracle
→ R3 建立可用于当前算子的 long-tail residual authority
→ R4 运行有界 A→B→C sweep contraction
→ R5 仅在 R4 通过后运行 T6-S 20/100/150/200 screen
→ response_v2.md and stop
```

本轮仍不授权 T6-F 完整求解、official E/H 恢复、T7 h-scaling、T8 0.7 nm/2 TiB 审计或 T9 结项。

---

# 1. 对 Response V1 的审阅结论

## 1.1 Git、范围和停止行为

| 审阅项 | 结果 | 说明 |
|---|---|---|
| base / merge-base | pass | 均为 `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| reviewed HEAD | pass | `4d4f65aaa5c3cfd79ec5a7f3defb33174b94e674` |
| branch relation | pass | 审阅时 `ahead 18 / behind 0` |
| ordinary default | unchanged | 新方法仍为显式 opt-in |
| master | unchanged | 未 merge、未写入 `master` |
| 0.7 nm PDE | correctly not_run | 未运行、未冒充通过 |
| T5 hard stop | accepted | authority bridge失败后未运行 MPI2、A/B/C或T6 |
| OOM / swap | none | authority run peak `981,893,120 B`，swap `0 B` |

Codex 拉取本 Review 后仍须在本地 canonical worktree 重新报告：

```text
branch
HEAD
upstream
ahead/behind
git status --short
canonical worktree identity
Python/MPI/PETSc/DOLFINx/Basix ABI
PETSc ScalarType/IntType
MemAvailable/swap/disk
```

远端 review 无法观察 nonignored untracked 文件；工作树或 ABI 不合格时不得开始 R1。

## 1.2 T1：`.dat` 合同

接受以下结果：

```text
method.kind          = full3d_iterative
linear solver        = iterative
preconditioner       = full3d_scalable_v1
ordinary default     = unchanged
validate-only        = supported
dry-run              = supported
unknown/mismatched   = fail closed
```

T1 是方法入口和 provenance PASS，不是 solver 数值 PASS。该合同在本轮保持冻结；除非 authority recovery 发现输入物理身份字段缺失，否则不得扩展公共 schema，也不得把临时 transmission 或 normalization 参数暴露给用户。

## 1.3 T2：full-space matrix-free volume action

接受并冻结以下 fresh evidence：

| 项目 | measured result | Gate |
|---|---:|---:|
| p2 assembled identity | `1.0623006934406839e-15` | `<=1e-12` |
| p3 assembled identity | `3.571370033045663e-15` | `<=1e-12` |
| p6/h10 MPI1 identity | `7.263059324300498e-17` | `<=1e-11` |
| p6/h10 MPI2 identity | `7.120392279402028e-17` | `<=1e-11` |
| cross-MPI action identity | `1.1449579596647522e-13` | `<=1e-12` |
| 12-repeat max difference | `0.0` | deterministic |
| h10→h5 retained exponent | `0.9779306095631883` | `<=1.10` |
| swap | `0 B` | `0 B` |

该结果证明当前 volume action 的数值与 retained-payload scaling 合格。它仍是 action-only evidence；T2 没有测量完整 workflow process-tree peak，也没有证明 PC 或 PDE 收敛。

若 R2 只修改 RHS assembly、canonical diagnostics 或 evidence，不得无故改动 T2。若修改涉及 MPC orientation、basis transform、volume form或共享 full-FE vector semantics，则 T2 五案 formal evidence必须在新 SHA 下全部重跑。

## 1.4 T3：dynamic streaming Fourier-DtN

接受并冻结：

```text
dynamic modes       = 80 for the frozen 13.5 nm anchor
propagating         = 78
near-cutoff         = 0
evanescent          = 2
batch size / count  = 8 / 10
action error        = 1.5267729283364925e-16
recovery error      = 8.148489733468128e-17
cross-MPI           = 0.0
repeat              = 0.0
swap                = 0 B
```

`80` 是 frozen case 的动态解析结果，不是 production 常数。当前 action 使用 owner-local surface functionals、显式 projection denominator `H` 和 bounded batches；没有 explicit C/D、global Schur 或 FE-sized numeric allgather。

若 R2 发现 defect 位于：

```text
traction vector
mode polarization/e_vector
projection denominator H
surface component assembly
coupling sign or conjugation
mode amplitude ordering
```

则 T3 MPI1、MPI2、independent modal-sum、recovery 和 manifest evidence必须全部在修复后的同一 SHA 重跑；旧 T3 PASS不能覆盖改变后的 operator/RHS semantics。

## 1.5 T4：slab/interface 与 Candidate A transmission action

接受并冻结当前 T4 的 algebra/action PASS：

| 项目 | measured result | Gate |
|---|---:|---:|
| max Robin action/oracle error | `1.1347e-15` | `<=1e-11` |
| max cross-MPI canonical error | `7.1149e-15` | `<=1e-12` |
| R/P adjoint error | `0.0` | closure |
| reconstruction error | `0.0` | closure |
| repeat difference | `0.0` | deterministic |
| swap | `0 B` | `0 B` |

T4 证明的是 owner-local interface topology、restriction/prolongation、phase-once 和 first-order Robin transmission action正确；它没有实现或测试完整 sweep contraction。

若 R2 修改通用 entity orientation、MPC canonical transform或 surface measure semantics，T4 p2/p3、MPI1/MPI2 四案必须重新运行。单纯新增只读 component telemetry不要求重跑 action，仍须运行相关 focused regression。

## 1.6 T5：正确分类

当前 T5 authority run 建立了以下事实：

| 项目 | measured result |
|---|---:|
| old/current packet count | `164,592 / 164,592` |
| duplicate/missing/extra | `0 / 0 / 0` |
| key set | equal |
| physical RHS relative coefficient L2 | `10.934736136386151` |
| maximum packet absolute difference | `1.2846616424283923` |
| best global complex scaling后的相对差 | `0.10029800143967213` |
| process-tree peak | `981,893,120 B` |
| swap | `0 B` |

差异集中在 top boundary 的非零 modal packets；bottom 为零，side/volume接近数值零。旧 W5 自身满足 `residual = rhs - outer_action`，relative closure约 `1.7427e-20`，因此旧文件没有自相矛盾，但这不能证明旧 dual coefficients与当前 physical load semantics相同。

正式分类保持：

```text
T5 = BLOCKED_BY_LONG_TAIL_RESIDUAL_AUTHORITY
Candidate A/B/C = NOT_RUN_BY_GATE
sweep algorithm = NOT_TESTED
T6 = NOT_RUN_BY_GATE
```

---

# 2. 当前 blocker 的准确解释

## 2.1 不是 row/key/mesh mismatch

现有证据已经排除：

```text
mesh connectivity mismatch
geometry mismatch
row count mismatch
constraint count mismatch
canonical key ordering mismatch
duplicate/missing/extra packet mismatch
old residual file internal corruption
```

因此下一轮不应继续重复 shape、key-set 或全局 norm 检查来代替 component physics audit。

## 2.2 仍未证明的量

当前尚未独立证明 old/current 在以下量上完全一致：

```text
frozen physical input identity
incident traction component coefficients
top modal coupling amplitudes
mode ordering and polarization identity
surface normal and traction convention
projection denominator / normalization H
complex conjugation convention
facet marker and ds measure
quadrature degree and component form
Basix entity orientation transform
MPC slave/master treatment and phase-once
canonical dual coefficient interpretation
```

当前 `FullspacePhysicalAction.compose_physical_rhs` 只是把调用转发给 dynamic DtN action；current DtN RHS合同是：

```math
b_{\mathrm{current}}
=
b_{\mathrm{incident}}+C a.
```

current carrier又通过 MPC-aware surface entries、`-traction` coupling 和显式 mode inventory 构造 `C`。所以恢复 authority 的关键不是给最终向量乘一个经验系数，而是逐层证明 `b_incident`、`a`、`C` 与 canonical dual basis 的物理含义。

## 2.3 禁止的错误修复

不得采用：

```text
把 current RHS 乘以 old/current norm ratio
使用 best-fit complex alpha 后继续
只改一个负号直到总向量接近
降低 1e-12 identity Gate
忽略 top modal packets
删除 evanescent modes
改 mode ordering或normalization以匹配旧文件
把 old residual 当普通数组直接塞入 current Vec
用 R/T/A 接近来替代 dual coefficient authority
```

经验拟合不能建立跨 source SHA 的物理等价性。

---

# 3. 本 Review 授权的连续恢复批次

## R0：身份、工作树与原始证据冻结

开始前必须：

1. fast-forward 拉取本 Review；
2. 确认同一执行分支、clean tracked worktree和无 nonignored untracked 文件；
3. 记录 Review V2 start HEAD、upstream、ahead/behind；
4. 确认 qualified WSL/Linux ABI、complex128、int32和单线程；
5. 核验旧 W5 raw目录、92 MB shard、mesh H5/XDMF、rhs/residual/action/solution SHA仍与 V1 evidence一致；
6. 将本轮新 raw写入新的 ignored authority-v2目录，不覆盖 v1；
7. 一次只运行一个 heavy job，swap必须为0。

旧 raw 任一 hash不匹配时停止，不允许重新生成一个“看起来相同”的 Task37 residual冒充历史 authority。

## R1：建立 old/current frozen physical identity manifest

先做 read-only/static + lightweight runtime inventory，不改数值代码。

必须为 old W5 和 current Task038-extra 分别生成结构化 manifest，至少包含：

```text
wavelength
geometry dimensions and mesh witness
material epsilon / loss identity
incidence theta / phi / polarization
Floquet kx / ky and phase_x / phase_y
finite-element family / degree / quadrature
boundary side and facet tags
outward normal convention
external mode count and ordered mode keys
per-mode m / n / polarization / alpha / gamma / kz
per-mode e_vector / traction vector / normalization H
incident-mode amplitudes
RHS composition sign convention
MPC relation digest and constraint count
source SHA and raw/config hashes
```

### R1 Gate

| 项目 | Gate |
|---|---|
| old manifest completeness | all mandatory fields available or explicitly unavailable |
| current manifest completeness | all mandatory fields available |
| mesh/space identity | exact current evidence already established, rechecked |
| same-physics claim | only if every mandatory physical field agrees |
| unavailable old field | cannot be guessed from current input |

若 old/current 物理身份确实不同，必须分类为：

```text
HISTORICAL_W5_NOT_SAME_PHYSICAL_RHS
```

此时不得强迫 whole-RHS equality；继续 R2 的目的改为证明 canonical dual basis和构造 current residual authority，而不是修 current physics去迎合 old RHS。

## R2：top-boundary physical-dual component oracle

R2 解决的问题是：同一个物理边界 component 经过 old/current assembly、orientation、MPC与canonical extraction后，是否代表同一 dual covector。

### R2.1 分解对象

必须把 RHS至少拆成：

```text
incident traction base
modal coupling total
per side
per mode key
per polarization
per tangential component 0 / 1
before MPC combination
after MPC owner-local assembly
after canonical dual packing
```

最终 whole-RHS norm只能作为汇总，不得替代 component表。

### R2.2 独立 oracle

至少建立两层独立证据：

1. **小 fixture direct surface oracle**：在 p2/p3 的真实 hexahedral top facets上，用独立 UFL/facet quadrature或等价 direct assembly，对单个切向 component、单个 mode和已知解析场检查 coefficient；
2. **p6/h10 component authority**：在 frozen production mesh上，对 incident base和所有非零 mode amplitudes，比较 current component carrier、direct assembled component vector和canonical packets。

checker只能读取 raw component records并重算结论，不得导入 runner或复用被测 assembly函数来生成“独立”参考。

### R2.3 必须显式审计

```text
surface normal sign
ds marker identity
traction definition
mode amplitude ordering
projection denominator H
complex conjugation placement
-traction coupling sign
e_vector component convention
edge/face orientation matrix
MPC slave exclusion
Floquet phase applied exactly once
owner/ghost accumulation
```

### R2.4 数值 Gate

| R2 项目 | Gate |
|---|---:|
| p2/p3 component vs independent surface oracle | `<=1e-12` |
| p6/h10 current component vs direct component assembly | `<=1e-11` |
| current whole RHS recomposed from recorded components | `<=1e-12` |
| MPI1/MPI2 component canonical identity | `<=1e-12` |
| repeat identity | `<=1e-12`，目标 exact deterministic |
| finite / duplicate / missing / extra | finite，`0 / 0 / 0` |
| swap | `0 B` |

如果 R1证明 old/current 是同一物理输入，则还要求：

| same-physics old/current 项目 | Gate |
|---|---:|
| incident component identity | `<=1e-12` |
| nonzero modal amplitude identity | `<=1e-12` |
| per-mode coupling component identity | `<=1e-12` |
| recomposed whole RHS identity | `<=1e-12` |

允许出现一个**预先由数学定义推导、与观测数据无关**的固定 basis transform；必须记录公式、orientation class和独立验证，closure `<=1e-12`。禁止从 old/current vectors拟合 dense transform或global alpha。

### R2.5 修复权限

先完成 read-only/component diagnosis。只有定位到单一、明确的 current implementation defect后，才允许一次窄修，例如：

```text
wrong conjugation
wrong normal/sign
wrong component ordering
missing H normalization
phase applied twice or omitted
incorrect MPC owner/slave treatment
wrong facet marker/measure
```

不得为了匹配 old source而改变正确的 current physics。

若证据表明 old Task37 assembly是 obsolete/incorrect，而 current path通过独立 oracle，则保留 old negative evidence但不修改 current。该分类应写成：

```text
OLD_W5_PHYSICAL_DUAL_NOT_CURRENT_AUTHORITY
CURRENT_DUAL_ORACLE_PASS
```

任何数值核心修复后必须按影响范围重跑 T1–T4 fresh regressions：

- 改 schema/identity：T1；
- 改 basis/MPC/full-FE semantics：T2、T4；
- 改 mode/traction/H/coupling：T3；
- 改 surface orientation/measure：T3、T4；
- 改 exact physical operator：T2、T3及同 SHA direct/operator authority。

R2经一次窄修仍不能达到 Gate时停止，不进入 R3。

## R3：建立 current long-tail residual authority

R3 允许两条路径，按优先级执行；不得同时开放无界 residual-generation研究。

### Path A：historical residual dual bridge

只有在以下条件全部满足时，才可直接转移旧 W5 residual：

```text
canonical dual basis semantics independently qualified
old/current physical space and orientation map exact
old residual packets finite and hash-bound
no empirical scaling or fitted transform
MPI1 reconstruction roundtrip pass
MPI1/MPI2 canonical identity pass
```

这条 source必须标记为：

```text
HISTORICAL_W5_LONG_TAIL_DUAL
```

若 R1证明 physical RHS不同，它只能作为经独立 basis authority证明后的历史困难 dual direction，不能称为 current physical residual。R4 表格必须同时保留这一身份边界。

### Path B：current recomputed historical-state residual

若 old RHS不是同一物理 authority，或 whole-RHS identity不应成立，但 old primal solution可可靠映射，则允许构造一个 fresh current residual：

```math
r_{\mathrm{current@oldstate}}
=
b_{\mathrm{current}}-A_{\mathrm{current}}x_{\mathrm{old,mapped}}.
```

该路径不迁移旧 PC，也不重新运行 W5。它只把冻结的 old primal state映射到当前 primal basis，再用当前 exact operator与当前 physical RHS重新计算 residual。

必须证明：

| Path B 项目 | Gate |
|---|---:|
| old solution primal canonical roundtrip | `<=1e-12` |
| MPI1/MPI2 mapped solution identity | `<=1e-12` |
| current action repeat | `<=1e-12` |
| residual recompute closure | `<=1e-11` |
| finite and nonzero | true |
| source/operator/input hashes | exact |
| empirical scaling of solution | forbidden for qualification |
| swap | `0 B` |

old residual与新 residual的角度、group energy和norm可以作为 diagnostic报告，但不得据此拟合或修改 source。Path B 的正式名称为：

```text
CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE
```

它是当前算子下的真实 residual，但不等于“当前旧 PC 在200步产生的 residual”。文档必须保留该边界。

### R3 hard stop

若 Path A无法证明 dual basis authority，且 Path B又无法证明 old primal solution mapping，则：

```text
T5_LONG_TAIL_AUTHORITY_UNRECOVERED
```

并停止。不得使用 PCNONE、任意随机困难向量、手工缩放 old residual或新建旧 PC replay来替代本 Review 的 bounded recovery。

## R4：有界 forward-backward sweep contraction

只有 R3 至少产生一个合格 long-tail source后才可开始。

### R4.1 固定 source family

```text
physical RHS
gradient-dominated residual
curl-dominated residual
checkerboard/high-frequency residual
qualified Path A or Path B long-tail source
```

每个 source必须绑定 canonical manifest、norm定义、source SHA、MPI identity和生成方式。

### R4.2 Candidate 顺序

```text
A first-order impedance/Robin
→ B propagating + near-cutoff Floquet modal transmission
→ C bounded rational/second-order or local spectral impedance
```

Candidate A 当前只有 transmission action authority，R4仍需实现并测试真正的：

```text
forward slab solve
interface outgoing data
next-slab update
backward sweep
assembled correction
r_new = r - A z
```

不得把 T4 单次 interface action误写成完整 sweep。

Candidate B只允许在 homogeneous interface或已资格化的解析 modal interface使用。Candidate C仍是唯一 fallback；禁止添加第四类 transmission。

### R4.3 Gate

| source | required contraction `rho` |
|---|---:|
| physical RHS | `<=0.60` |
| qualified long-tail source | `<=0.70` |
| checkerboard/high-frequency | `<=0.75` |
| gradient-dominated | `<=0.90` |
| curl-dominated | `<=0.90` |

同时要求：

```text
finite and deterministic
current exact action closure <= 1e-11
MPI1/MPI2 identity <= 1e-12
process-tree peak < 6,000,000,000 B
swap = 0
retained payload approximately interface/volume linear
no global AIJ / global Schur / dense interface matrix / growing slab factor
```

每个 candidate只允许一次明确 implementation defect修复后的 formal rerun。参数必须在实现前冻结；禁止连续扫描 Robin系数、Padé阶数、mode count、overlap、slab count、local inner steps或coarse rank。

某个 candidate通过全部 source Gate后，立即停止实现更复杂 candidate并进入 R5。若 A/B/C全部未使 long-tail `rho<=0.70`，分类为当前 sweep family数值负结果并停止，不进入 R5。

## R5：条件授权 T6-S screen，不授权 T6-F

只有以下全部通过后才允许 R5：

```text
R2 physical-dual authority pass
R3 current-compatible long-tail source pass
R4 at least one sweep candidate passes all contraction Gates
T1–T4 affected regressions pass on final source SHA
preflight swap=0 and watchdog active
```

外层冻结为：

```text
right FGMRES
restart = 20
standard in-memory Krylov
no disk-backed Krylov
no KSP/restart/inner parameter scan
```

### T6-S checkpoint Gate

| checkpoint | full explicit true residual Gate |
|---:|---:|
| 20 | `<=0.40` |
| 100 | `<=0.05` |
| 200 | `<=0.005` |
| 150→200 improvement | `>=20%` |

必须保存 20/100/150/200 的 solution/residual hash-bound compact packet；checkpoint residual由当前 exact action显式重算，不能只相信 KSP monitor。

### R5 资源边界

```text
strategic line              = process-tree peak < 2,000,000,000 B
warning                     = 10,000,000,000 B
controlled hard stop        = 12,000,000,000 B
swap                        = 0
OOM kill                    = unacceptable
```

超过2 GB但低于12 GB、swap=0的 screen只能分类为 diagnostic/resource fail，不得称0.7 nm scalable pass。

### R5 停止点

无论 T6-S通过或失败，本 Review 都要求在 screen后停止。禁止继续到：

```text
final <=1e-6 solve
official E/H recovery
R/T/A/A_volume
full diffraction-channel comparison
T7 h-scaling
T8 0.7 nm capacity audit
```

若 T6-S通过，应保留当前 solution、residual、Krylov/PC telemetry和lifecycle evidence，写 `response_v2.md` 等待下一次 review授权 T6-F。

---

# 4. 本批次明确禁止的工作

| 对象 | Review V2 决定 |
|---|---|
| whole Task37-extra branch | forbidden |
| old shifted-patch/range/nested PC migration | forbidden |
| W8–W18 reopening | forbidden |
| old PC replay to manufacture residual | forbidden |
| disk-backed FGMRES | forbidden |
| p4→p6 multilevel/factor campaign | deferred |
| 84×882D or complement factor store | forbidden |
| fixed 75/390/530D global range | forbidden |
| LOR-HX hierarchy | closed |
| Task039 Hybrid/QEP/Petrov/exact-side code | forbidden |
| global AIJ / global Schur | forbidden |
| dense interface Schur/mass | forbidden |
| growing slab LU/ILU store | forbidden |
| empirical old/current alpha scaling | forbidden |
| physical material/angle/mode reduction to force equality | forbidden |
| full T6-F solve/recovery | not authorized |
| T7/T8/T9 | not authorized |
| full 0.7 nm PDE | forbidden |
| ordinary default change | forbidden |
| merge/rebase master | forbidden |

---

# 5. 全批次硬停止条件

任一条件发生，保存证据、提交轻量结果、写 `response_v2.md` 并停止：

1. branch、base、upstream、canonical worktree或ABI不正确；
2. old W5 raw/artifact hash与V1 evidence不符；
3. old mandatory physical identity字段缺失且无法从old raw/source独立恢复；
4. R2 component oracle经一次窄修后仍不能闭合；
5. 需要经验global alpha、fitted dense transform或降低Gate才能建立authority；
6. current numerical core被修改后，受影响的T1–T4 fresh regressions失败；
7. Path A dual authority失败且Path B primal mapping/closure失败；
8. long-tail source没有current source/operator/hash/MPI identity；
9. A/B/C均不能达到long-tail `rho<=0.70`；
10. sweep需要无界增加mode、overlap、slab、inner steps或coarse rank；
11. 需要global matrix、global Schur、dense interface matrix或growing factor；
12. T6-S任一checkpoint失败，或150→200改善小于20%；
13. process-tree达到12 GB、出现swap、termination失效或OOM风险；
14. 工作转向Hybrid、RCWA、z-separable内部模态传播或0.7 nm full PDE；
15. 必须改变Maxwell弱式、材料、Floquet phase或official Gate才能继续。

硬停止只关闭当前 authority/sweep lane，不得扩大为“Full3D iterative 永远不可能”。

---

# 6. 提交计划与执行纪律

继续使用同一分支：

```text
codex/20260820-task38-extra-full3d-iterative-0p7nm
```

推荐提交顺序：

```text
diag(maxwell): add old-current physical dual component authority
fix(maxwell): correct qualified physical dual defect              # only if R2 proves one

evidence(task038-extra): qualify T5 long-tail residual authority
feat(dd): add bounded forward-backward sweep contraction

evidence(task038-extra): record T5 contraction results
bench(task038-extra): run conditional T6 residual screen

docs(task038-extra): respond to review v2
```

若没有 defect，不创建空的 `fix(maxwell)` 提交。每个提交只含一个可解释阶段；禁止 amend、force push、rebase、创建新分支或混入无关清理。正常通过时 R0–R5之间不必等待 ChatGPT；达到 R5 screen或任何硬停止后必须停。

活动期间即使 `master` 更新，也继续使用冻结 base `438caf...`，未经新 review不得同步。

---

# 7. 测试与证据要求

## 7.1 每个代码阶段

至少运行：

```text
focused unit tests
serial fixture
MPI2 fixture where applicable
compileall
git diff --check
input validate-only / dry-run when schema or adapter touched
compact JSON parse and independent checker
Markdown fence/table/link checks
```

所有测试必须在该阶段最终代码后重跑。没有 GitHub Actions时只能报告 local tests，不得写CI pass。

## 7.2 新 outcomes

本批次至少新增或更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/t5_physical_dual_authority.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/sweep_oracle.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/task038_extra_full3d_iterative_0p7nm/response_v2.md
```

若运行 T6-S，还需创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/full3d_iterative_screen.md
```

并同步更新：

```text
docs/development_model_registry.md
```

本轮仍未到 T9，`outcomes/summary.md` 与 `docs/development_progress.md` 的最终结项更新不要求提前伪造；`response_v2.md` 必须明确它们仍属于后续 closeout。

## 7.3 Compact record建议

```text
records/t5_physical_identity_v2.json
records/t5_component_oracle_p2_mpi1_v2.json
records/t5_component_oracle_p2_mpi2_v2.json
records/t5_component_oracle_p3_mpi1_v2.json
records/t5_component_oracle_p3_mpi2_v2.json
records/t5_component_oracle_p6h10_mpi1_v2.json
records/t5_component_oracle_p6h10_mpi2_v2.json
records/t5_long_tail_authority_v2.json
records/t5_sweep_candidate_<a|b|c>_v2.json
records/t6_screen_v2.json
```

实际命名可适度调整，但必须保持版本、case、MPI、source和classification可读，不能覆盖v1 negative evidence。

## 7.4 Watchdog/provenance

R3 p6/h10 authority、R4 contraction和R5 screen均须绑定：

```text
source SHA
input/resolved/physical hash
old artifact hashes where used
MPI/thread/ABI identity
MemAvailable/swap/disk preflight
process-tree watchdog
expected/start/end source SHA
raw tree/artifact hashes
true residual or contraction recompute
cleanup/termination status
```

重型 vector、mesh、JIT、timeline和raw component arrays留在ignored artifact目录，不提交Git。

---

# 8. `response_v2.md` 必须回答的问题

1. branch、base、Review V2 start HEAD、final HEAD、upstream、ahead/behind和worktree；
2. R0–R5 planned/run/pass/fail/not_run矩阵；
3. old/current physical identity manifest逐项结果；
4. RHS incident/modal/per-mode/per-component分解；
5. normal、sign、H、conjugation、measure、orientation和phase-once的根因裁决；
6. 是否修改 current numerical core，为什么，影响哪些旧evidence；
7. 修复后T1–T4哪些formal evidence被fresh rerun；
8. Path A或Path B如何建立long-tail authority；
9. old solution/residual mapping、MPI1/MPI2和closure数据；
10. A/B/C 对五类source的rho、wall、retained bytes、process-tree peak和停止原因；
11. 若运行T6-S，20/100/150/200 true residual、150→200改善、RSS、swap和wall；
12. T6-F、E/H、R/T/A、T7–T9和0.7 nm准确的not_run边界；
13. measured/derived/predicted/failed/controlled_stop/not_run分类；
14. changed files、tests、checker、rendered-view和evidence index；
15. 下一轮是否应授权T6-F，以及该判断如何推进0.7 nm arbitrary-3D blocker。

负结果必须给实际值、Gate与具体机制；不得只写“authority失败”或“测试通过”。

---

# 9. 下一次审阅范围

下一次 Review 将裁决：

```text
current physical RHS是否获得独立component authority
历史W5 residual是否可合法桥接
或current@historical-state residual是否成为合格替代source
sweep A/B/C是否真正处理困难long-tail direction
T6-S是否显示足够的波长/网格收敛信号
是否授权T6-F完整Maxwell solve与official physics
是否保留或拒绝当前sweep architecture
哪些T1–T4组件进入最终selective-merge候选
```

在下一次 review 前不得开始 T6-F、T7、T8、T9 或 master integration。

---

# 10. 最终决定

```text
T1 = ACCEPTED_AND_FROZEN_PASS
T2 = ACCEPTED_AND_FROZEN_ACTION_PASS
T3 = ACCEPTED_AND_FROZEN_DYNAMIC_DTN_PASS
T4 = ACCEPTED_AND_FROZEN_INTERFACE_ACTION_PASS
T5_V1_STOP = ACCEPTED_AS_CORRECT_FAIL_CLOSED_BEHAVIOR
R0_R1_R2_R3_R4 = AUTHORIZED_AS_ONE_BOUNDED_CONTINUOUS_BATCH
T6_S = CONDITIONALLY_AUTHORIZED_AFTER_R4_FULL_GATE
T6_F = NOT_AUTHORIZED
T7_T8_T9 = NOT_AUTHORIZED
MASTER_MERGE = FORBIDDEN
```

Codex可以连续推进到 T6-S screen，而不必在每个恢复子阶段等待审阅；但必须在 T6-S完成、authority无法恢复、sweep Gate失败或任何更早硬停止后，提交并推送同一分支，写 `response_v2.md`，然后停止等待下一轮审阅。
