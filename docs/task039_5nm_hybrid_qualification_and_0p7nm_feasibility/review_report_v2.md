# Task039 Review Report V2：移除 h10 物理资格、完成 h5 Full3D/Hybrid M480 对照并条件性验证 Hybrid iterative

## 0. 审阅决定

```text
review                              = Task039 Review Report V2
reviewed_branch                     = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                       = f44cc6112501f4b6eb36ee674e8fd832409d306f
extension_status                    = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge               = forbidden
new_branch_or_worktree              = forbidden
ordinary_default_change             = forbidden
h10_role                            = historical_underresolved_stress_anchor_only
h10_new_PDE                         = forbidden
h5_full3d_direct                    = authorized_once
h5_hybrid_direct_M480               = authorized_once_after_h5_full3d
h5_hybrid_iterative_M480_MPI8       = conditional_after_h5_hybrid_direct_pass
h5_hybrid_iterative_MPI1            = forbidden
M_above_480                         = forbidden
M960_new_run                        = forbidden
Full3D_M3a_retuning                 = forbidden
new_PC_family                       = forbidden
neural_or_learned_factor            = frozen
full_0p7nm_PDE                      = forbidden
concurrent_heavy_jobs               = forbidden
```

本 Review 接受以下科学判断，并据此改变 Task039 后续执行漏斗：

1. `p6/h10` 在 5 nm 下给出的反射/吸收物理与 h7.5/h6 完全不同，今后不得再作为 5 nm 物理参考、Hybrid 准确性参考或 0.7 nm 外推的精度锚点；
2. h10 历史记录不得删除或改写，只保留为 under-resolved solver/capacity stress evidence；
3. h7.5 与 h6 的 R/T/A 和整体 E/H 已非常接近，但旧 comparator 被功率约 `1e-8–1e-7` 的弱通道相对误差一票否决，因此必须在 h5 后采用“主体物理资格 + 弱通道诊断”双层判据；
4. M480 与 M960 在同一 h10 离散系统上的 R/T/A、衍射级和场已经高度一致，因此后续固定 `M=480`，禁止再增加 M；
5. 下一步不是继续堆叠模态，而是先建立 h5 Full3D discrete authority，再验证同一 h5 网格上的 Hybrid direct M480；
6. 只有 h5 Hybrid direct M480 与 h5 Full3D direct 的主体物理 Gate 通过，才允许运行 h5 Hybrid iterative M480 MPI8；本轮不运行 MPI1。

本 Review 不撤销此前的历史分类：

```text
TASK039_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM
FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_WITHIN_RESOURCE_BUDGET
M480_H_DISCREPANCY_UNRESOLVED
0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN
0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN
0P7NM_CONVERGENCE_RISK_UNRESOLVED
```

它只授权一个更直接的 h5 同网格验证链。

---

# 1. 为什么 Hybrid direct M480 h10 会比 Full3D direct h10 更占内存

不能把 Hybrid 的额外成本理解为“只多了 960 个 modal unknowns”。`M=480` 表示正向 480 与反向 480，共 960 个 modal unknowns；但每个 modal unknown 都不是一个孤立标量，而是通过接口投影和牵引块与成千上万个 FE trace DoFs 全局耦合。

Hybrid direct 的内存至少包含：

```text
bottom/top endcap FE-DtN systems
positive/negative QEP matrices and eigensolver workspaces
raw candidate eigenvectors
left/right and positive/negative biorthogonal modes
full/cross-section/trace representations
canonical negative traces and Gram/mapping arrays
bottom/top projection matrices P_b/P_t
bottom/top traction matrices T_b/T_t
Hybrid augmented sparse matrix
MUMPS symbolic/numeric factor and workspace
field reconstruction and canonical export temporaries
MPI-rank replication and allocator high-water
```

因此内存由矩阵图的稠密度和 LU fill-in 决定，而不是只由 rows 决定。已有 M960 记录说明这一点：Hybrid augmented system 只有约 19,372 rows，却有约 73,328,868 assembled NNZ；5 nm Full3D h10 约 51,796 rows、43,283,050 NNZ。较少 rows 完全可能因为 FE–modal coupling 更密而拥有更多 NNZ和更严重的 LU fill。

本轮必须用 h5 的真实 stage-aligned telemetry 回答：

```text
Hybrid direct额外内存中，多少来自QEP/basis/coupling，
多少来自augmented matrix，
多少来自MUMPS factor/workspace，
多少来自生命周期重叠或allocator high-water。
```

在没有这一证据前，禁止直接把问题归因于 modal Schur、QEP、factor 或 Python 对象中的任意一项。

---

# 2. V2 执行顺序

Codex 必须在同一 Task039 分支按以下顺序执行，并在每个阶段完成后及时 commit 与 push：

```text
V2-0  inherited audit and h10 demotion
V2-1  h5 Full3D direct readiness / integer / resource audit
V2-2  one formal h5 Full3D direct MPI8 run
V2-3  h6-vs-h5 two-tier convergence and h5 discrete authority
V2-4  h5 Hybrid direct M480 implementation/preflight with persistent stage telemetry
V2-5  one formal h5 Hybrid direct M480 MPI8 run
V2-6  h5 Hybrid-direct vs Full3D same-grid comparison and memory attribution
V2-7  conditional h5 Hybrid iterative M480 MPI8
V2-8  final comparison, resource conclusion and response_v3.md
```

任何两个重型 PDE job 不得并发。

---

# 3. V2-0：h10 降级与继承审计

创建：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/review_v2_inherited_audit.md
```

必须记录：

- current local/remote SHA、upstream、ahead/behind和clean状态；
- h10/h7.5/h6 Full3D records及SHA；
- M480/M960 Hybrid direct records及SHA；
- h5现有preflight record；
- machine physical/selected/effective memory；
- 本Review的范围和禁止项；
- h10新身份：`historical_underresolved_stress_anchor_only`。

从本阶段开始，所有新summary/table/comparator必须将h10放在单独的历史栏，禁止把h10列入：

```text
Full3D 5 nm reference candidates
Hybrid 5 nm physical validation authorities
5 nm accuracy-qualified results
0.7 nm mesh-accuracy scaling anchors
```

第一项V2提交必须是docs-only。

---

# 4. V2-1/V2-2：一次 h5 Full3D direct MPI8

## 4.1 冻结输入

使用现有输入：

```text
input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat
```

物理和算法必须冻结：

```text
wavelength             = 5.0 nm
n_grating/substrate    = 0.99396854453 + 0.00435380777i
geometry               = existing 50 x 25 x 140 nm target grating
grazing/theta/phi      = 10° / 80° / 0°
polarization           = S
Nedelec degree         = p6
mesh target            = h5 nm
assembly               = assembly-time static condensed
external inventory     = exact same 604 keys
solver                 = MUMPS direct
MPI                    = 8
initial/result contract= ordinary Full3D direct authority
```

禁止：

```text
BLR
out-of-core MUMPS
equation/mesh/material modification
reduced accuracy
alternative direct solver
silent fallback
```

## 4.2 取代旧 symbolic-only 阻断

Review V1要求独立 MUMPS symbolic/analysis-only authority，但当前仓库没有这一public path，导致h5虽预测RSS约90–150 GiB、低于195 GiB hard stop，仍未启动。

本Review取消“必须存在独立analysis-only入口”这一前置条件，改为：

1. 完成mesh-only与assembled-dimension审计；
2. 检查PETSc/MUMPS integer ABI，特别记录PETSc IntType、MUMPS integer build以及预测factor NNZ是否可能超过32-bit计数范围；
3. 若发现已知不可恢复的integer overflow风险，记录 `H5_BLOCKED_BY_MUMPS_INTEGER_WIDTH` 并停止；
4. 否则允许一次正式MUMPS setup/factor/solve，在全程watchdog保护下执行。

## 4.3 正式资源合同

启动前必须满足：

```text
no concurrent heavy job
swap used = 0
MemAvailable >= 200 GiB
selected finite limit is valid
disk free >= 20 GiB
input validate/dry-run pass
604 keys exact
worktree clean
```

正式watchdog：

```text
warning process-tree RSS = 170 GiB
hard-stop process-tree RSS = 195 GiB
any swap use = immediate termination
poll interval <= 0.25 s
timeout = existing h5 dat contract, at least 6 h
```

若触发hard stop、swap、MUMPS integer error或numeric factor failure，保留为正式负证据；不得切换OOC/BLR或调低精度重跑。

## 4.4 Full3D h5 own Gate

```text
direct solve / official result             = true
true relative residual                     <= 1e-9
R/T/A/A_volume                             finite
energy closure                             <= 1e-5
604 external keys                          exact/unique
selected E/H                               complete and finite
canonical active/full                      complete
swap                                       = 0
```

只要own Gate通过，h5就是合法的 `Full3D h5 discrete authority`，即使h6-vs-h5尚未收敛。

---

# 5. V2-3：h6-vs-h5 双层收敛判据

旧Gate把所有功率 `>=1e-8` 的通道用最大相对误差统一否决；对功率约 `1e-8–1e-7` 的通道，这会把很小的绝对差放大成O(1)相对差。本Review保留这些弱通道数据，但不再允许其单独否决主体物理参考。

## 5.1 Primary physics Gate

```text
max |delta R,T,A_balance,A_volume|      <= 1e-5
both energy closure                     <= 1e-5
selected E overall relative L2          <= 2e-3
selected H overall relative L2          <= 5e-3
604 keys                                exact
```

Primary diffraction set定义为两次运行中：

```text
max(power_left, power_right) >= 1e-6
```

对该集合要求：

```text
max individual power relative delta     <= 1e-3
max individual complex amplitude delta  <= 1e-3
all-channel power-weighted aggregate     <= 1e-4
all-channel amplitude-weighted L2        <= 1e-3
```

## 5.2 Weak-channel diagnostic

对：

```text
1e-8 <= max(power_left,power_right) < 1e-6
```

必须完整记录：

```text
absolute power delta
relative power delta
absolute complex-amplitude delta
relative complex-amplitude delta
phase delta
```

但它们只用于：

```text
FULL_CHANNEL_WEAK_ORDER_CONVERGENCE_PENDING
```

不得单独否决Primary physics reference。

## 5.3 h5 reference分类

```text
if Primary physics Gate passes:
    classification = FULL3D_DIRECT_5NM_PRIMARY_REFERENCE_ESTABLISHED_AT_P6H5
    h5 role = primary physical reference

if Primary physics Gate and old full weak-channel Gate both pass:
    classification += FULL3D_DIRECT_5NM_FULL_CHANNEL_REFERENCE_ESTABLISHED_AT_P6H5

if Primary physics Gate fails:
    classification = FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_AT_P6H5
    h5 remains best available discrete authority only
```

无论Primary是否通过，只要h5 own Gate通过，后续仍允许进行同网格 h5 Hybrid direct vs Full3D diagnostic；但只有Primary通过，才可称为5 nm refined physical reference。

---

# 6. V2-4/V2-5：h5 Hybrid direct M480 MPI8

## 6.1 冻结候选

新增一个且只有一个输入：

```text
input/official/task039/5nm_p6h5_hybrid_direct_m480_mpi8.dat
```

冻结：

```text
wavelength / mesh / p        = 5 nm / h5 / p6
M                             = 480 per direction
external modes                = exact 604 keys
interfaces                    = 10 / 110 nm
internal propagation          = existing full3d_uniform_cg
traction                      = existing exact one-cell authority
direct solver                 = existing Hybrid direct MUMPS path
MPI                           = 8
zero physics/solver retuning
```

禁止：

```text
M960 or any M>480
M sweep
interface movement
mode-key truncation
lower QEP tolerance
new propagation/traction model
out-of-core/BLR fallback
```

## 6.2 Hybrid h5 preflight

在正式factor前至少记录：

```text
cross-section DoFs and QEP reduced dimension
candidate/retained mode count
bottom/top full FE and active trace rows
projection/traction matrix dimensions and NNZ
augmented rows and assembled NNZ
estimated MUMPS factor range
available memory/swap/disk
```

如果预测peak超过195 GiB或已知integer ABI不安全，停止并记录；否则允许一次正式运行。正式watchdog与h5 Full3D相同：170/195 GiB、swap=0。

## 6.3 必须真正持久化stage-aligned memory telemetry

上轮虽然实现了18-stage telemetry合同，但M960正式运行没有写出stage JSONL。本次必须在启动h5 Hybrid direct前完成接线测试，并在正式结果目录持久化：

```text
memory_stages.jsonl
process_tree_samples.jsonl
memory_object_ledger.json
```

至少在以下节点同步采样RSS/PSS/USS：

```text
baseline_before_mesh
mesh_spaces_ready
qep_matrices_ready
positive_qep_peak
negative_qep_peak
raw_candidate_modes_ready
selected_biorthogonal_bases_ready
canonical_traces_ready
projection_matrices_ready
traction_matrices_ready
local_fe_dtn_ready
hybrid_augmented_matrix_ready
mumps_analysis_ready_when_available
mumps_numeric_factor_ready
solution_ready
field_reconstruction_peak
modal_qep_temporaries_released
final_cleanup
```

每个节点同时记录可计算的对象容量：

```text
QEP matrices/workspace
candidate and selected mode vectors
left/right/positive/negative/raw/canonical representations
Gram/inverse/mapping arrays
projection/traction matrices
local FE-DtN matrices
augmented matrix
factor NNZ and factor bytes/INFOG when available
field reconstruction buffers
```

如果stage telemetry再次没有持久化，结果的数值部分可以保留，但内存归因必须分类为失败，且不得声称找到了内存主因。

## 6.4 h5 Hybrid direct own Gate

```text
true residual                           <= 1e-9
interface projection                    <= 1e-8
exact traction bottom/top               <= 1e-8
external q identity                     <= 1e-10
R/T/A/A_volume                          finite
energy closure                          <= 1e-5
604 keys                                exact
selected E/H and canonical exports      complete
swap                                    = 0
```

---

# 7. V2-6：h5 Hybrid direct 与 h5 Full3D 同网格比较

该比较只回答：

```text
在同一个 p6/h5 离散系统上，M480 Hybrid是否复现Full3D。
```

它不依赖h10，也不需要M960。

## 7.1 Same-grid primary Gate

```text
max |delta R,T,A_balance,A_volume|       <= 1e-5
604 mode keys                            exact
energy closure                           <= 1e-5
selected E overall relative L2           <= 5e-3
selected H overall relative L2           <= 1e-2
max per-plane E relative L2              <= 1e-2
max per-plane H relative L2              <= 5e-2
normal flux aggregate relative delta     <= 1e-4
```

对Primary diffraction set（power >=1e-6）：

```text
max power relative delta                 <= 1e-3
max complex amplitude relative delta     <= 1e-3
power-weighted all-channel aggregate      <= 1e-4
```

弱通道继续只作diagnostic。

## 7.2 分类

```text
if own Gate and same-grid primary Gate pass:
    classification = H5_M480_HYBRID_DIRECT_SAME_GRID_PASS

if own Gate passes but same-grid primary Gate fails:
    classification = H5_M480_HYBRID_MODEL_FAIL
    V2-7 iterative = not_run

if own Gate fails:
    classification = H5_M480_HYBRID_DIRECT_OWN_FAIL
    V2-7 iterative = not_run
```

本轮不允许通过增加M或调整接口来补救失败。

## 7.3 内存归因报告

必须创建：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/h5_hybrid_direct_memory_attribution.md
```

并对比：

```text
Full3D direct h5
Hybrid direct M480 h5
historical Full3D direct h10
historical Hybrid direct M480 h10
```

但h10只作为资源历史，不作为物理参考。

最终把Hybrid相对Full3D的峰值差分到：

```text
QEP and mode basis
interface coupling P/T
external DtN
augmented matrix
MUMPS factor/workspace
field recovery
lifecycle overlap
unattributed allocator/runtime high-water
```

必须同时报告：

```text
row count
assembled NNZ
factor NNZ
peak RSS/PSS/USS
setup/factor/solve/recovery wall
```

禁止只用“多了960个未知量”解释内存差异。

---

# 8. V2-7：条件性 h5 Hybrid iterative M480 MPI8

只有 `H5_M480_HYBRID_DIRECT_SAME_GRID_PASS` 才允许启动。

## 8.1 冻结候选

```text
wavelength / p / h / M            = 5 nm / p6 / h5 / 480
external modes                    = exact 604 keys
outer operator                    = exact monolithic Hybrid action
outer KSP                         = right FGMRES
restart                           = 90
max_it                            = 6000
initial guess                     = zero
five residual thresholds          = 5e-9
exact traction                    = 1e-8
external q identity               = 1e-10
bottom/top PC                     = whole-endcap ILU(0) + dynamic DtN Woodbury
residual correction               = fixed two-pass
nested local KSP                  = false
bottom/top direct factors         = 0/0
MPI                               = 8 only
```

禁止修改：

```text
shift / overlap / ILU level / restart / passes / tolerance / M / mode set
```

## 8.2 数值 Gate

```text
KSP reason                              > 0
iterations                              <= 6000
reported/global/bottom/top/modal        <= 5e-9
exact traction bottom/top               <= 1e-8
external q identity                     <= 1e-10
full recovery and own physics           = pass
no direct fallback                      = true
nested local KSP                        = false
swap                                    = 0
```

与 h5 M480 Hybrid direct比较：

```text
R/T/A/A_volume absolute delta           <= 1e-6
Primary power/amplitude relative delta  <= 1e-4
canonical active/full relative L2       <= 1e-5
selected E/H relative L2                <= 5e-3
604 keys                                exact
```

## 8.3 资源分类

本轮不运行MPI1，也不得把“MPI1约为MPI8的1/3”写成测量结果。

MPI8相对h5 Hybrid direct分类：

```text
RSS_iterative < RSS_direct              = memory saving measured
RSS_iterative <= 0.80 * RSS_direct      = meaningful saving >=20%
RSS_iterative <= 0.60 * RSS_direct      = major saving >=40%
RSS_iterative >= RSS_direct             = no memory advantage at h5/M480
```

数值与资源必须分别分类。

若6000步未收敛，停止并记录：

```text
H5_M480_HYBRID_ITERATIVE_SOLVER_FAIL
```

不得增加max_it或调PC。

---

# 9. Bug处理授权

用户授权Codex在本Review范围内自主定位并修复真实实现bug。允许的bug包括：

```text
input/launcher/path wiring
missing or malformed telemetry artifacts
MPI ownership or gather/scatter defects
schema/record/comparator defects
array shape/order/key mismatch caused by implementation
incorrect lifecycle destroy ordering
clear numerical coding defect that violates the frozen mathematical contract
```

处理规则：

1. 先保留失败raw与分类；
2. 写最小复现或focused test；
3. 只做窄修复；
4. 静态/focused/MPI tiny tests通过；
5. 只重跑受影响的正式候选一次；
6. 及时commit并push。

以下不是bug，不得通过调参“修复”：

```text
h5内存过高
M480与Full3D物理不一致
iterative残差停滞
弱通道不收敛
MUMPS fill过大
PC不够强
```

这些必须作为科学/资源负结果保留。

---

# 10. 提交、测试与最终交付

每个阶段至少一个职责清晰的commit，并及时push到同一远程Task039分支。禁止创建其他分支或worktree。

正式PDE前后运行：

```text
Task39/V2 focused tests
Task38 dat validate/dry-run
MPI1/2/4 tiny ownership fixture
Ruff check and scoped format-check
compileall
git diff --check
check_benchmarks.py --no-write
compact JSON/document-link/math/table checks
```

完整repository pytest本轮不是硬前置；若未运行，必须继续写 `not_run`，不得声称pass。

最终新增/更新：

```text
outcomes/review_v2_inherited_audit.md
outcomes/full3d_h5_direct_and_convergence.md
outcomes/h5_hybrid_direct_m480.md
outcomes/h5_hybrid_direct_memory_attribution.md
outcomes/h5_hybrid_iterative_m480_mpi8.md
outcomes/resource_ledger.md
outcomes/summary.md
outcomes/test_summary.md
response_v3.md
```

完成后停止等待审阅。禁止自动：

```text
merge master
run MPI1 Hybrid iterative
run M960 or M>480
retune Full3D M3a
retune Hybrid PC
run h4/h3
run full 0.7 nm PDE
develop neural factor
```

---

# 11. 最终结果表要求

## 11.1 Full3D reference

| mesh | DoFs | rows/NNZ/factor NNZ | R/T/A | E/H delta to next | primary channels | weak channels | RSS | wall | status |
|---|---:|---|---|---|---|---|---:|---:|---|

## 11.2 h5 same-grid comparison

| method | M | residual | R/T/A | primary channel error | E error | H error | RSS | wall | classification |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|

## 11.3 Hybrid memory attribution

| stage/component | Full3D h5 | Hybrid direct h5 | Hybrid iterative h5 | measured/derived | notes |
|---|---:|---:|---:|---|---|

## 11.4 Final classifications

必须分别给出：

```text
Full3D h5 own authority
Full3D h6-vs-h5 primary convergence
weak-channel convergence
h5 M480 Hybrid direct own result
h5 M480 Hybrid-vs-Full3D same-grid result
h5 M480 Hybrid iterative numerical result
h5 M480 Hybrid iterative resource result
memory-attribution confidence
```

不得用一个总的 pass/fail 掩盖这些不同问题。
