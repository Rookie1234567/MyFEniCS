# Task039 Review Report V1：5 nm Full3D direct 网格参考、M480 Hybrid iterative 与 M960/H/内存取证扩展

## 0. 审阅决定

```text
review                              = Task039 Review Report V1
reviewed_branch                     = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_closeout_head              = 758ce5e734f4404fac502117c695b7148ba8e4f0
historical_T3_to_T10_results        = retained_without_rewrite
extension_status                    = AUTHORIZED_WITH_STRICT_SCOPE
ordinary_default_change             = forbidden
master_write_or_merge               = forbidden
new_branch_or_worktree              = forbidden
full_0p7nm_PDE                      = forbidden
neural_or_learned_factor            = frozen
new_PC_family                       = forbidden
full3d_M3a_retuning                 = forbidden_in_this_extension
Hybrid_M_above_960                  = forbidden
heavy_jobs_concurrent               = forbidden
```

Task039 的首轮结论必须原样保留：

- 5 nm、p6/h10 Full3D direct 成功，但只是 fixed-grid stress authority；
- Full3D M3a iterative 在 4000 步后残差约 `0.1553`，形成真实的跨波长 PC 负结果；
- Hybrid direct 从 M120 到 M480 呈现明确收敛趋势，M480 的 R/T/A、显著衍射级与 E 场已经高度接近 Full3D h10；
- M480 的 H 场在 z=10 nm 和 z=60 nm 仍约有 6% 相对差异；
- M960 在形成解之前被 fixed `1e-12` raw canonical-trace consistency Gate 截停；
- Hybrid iterative 从未运行；
- h7.5/h5 从未运行；
- 0.7 nm 只有组件级容量外推，没有完整 PDE。

本 Review 不把这些历史结果改写成成功，也不撤销已有 negative classification。它只授权一个窄范围研究扩展，用来回答首轮尚未回答的五个问题：

1. 5 nm Full3D direct 在更细 p6 网格上是否收敛，能否建立可信参考解；
2. M480 Hybrid iterative 能否准确求解已经存在的 M480 Hybrid direct 方程；
3. M480 的 H 场差异来自模态截断、H 恢复/后处理，还是比较口径；
4. M960 的停止是物理/代数失败，还是固定前向误差阈值没有反映大规模浮点 backward error；
5. M 增大时 8.7→10.7→22.3 GiB 的峰值究竟由哪些对象和生命周期重叠造成。

本扩展不要求先建立 `M_robust_h10` 才允许 M480 solver-only diagnostic。该依赖在本 Review 中被明确拆分：

```text
Hybrid iterative vs Hybrid direct = solver qualification
Hybrid direct vs Full3D           = reduced-model qualification
Full3D grid convergence           = discretization/reference qualification
```

三者必须分别分类，禁止互相替代。

---

# 1. 对首轮结果的审阅判断

## 1.1 Full3D M3a iterative：真实 PC 负结果

同一 p6/h10 离散系统的 Full3D direct residual 约为 `3.51e-11`，而 M3a iterative 在 4000 步后 reported、condensed 与 full-augmented residual 均约为 `0.1553`。因此：

```text
Full3D equation / material / DtN / direct authority = valid
Full3D M3a wavelength robustness at 5 nm            = fail
```

本扩展禁止通过增加 `max_it`、修改 16 slabs、overlap、75D coarse、ILU level、shift 或 Krylov family 来补救 M3a。若未来继续发展 Full3D iterative，应另立专门 PC-redesign 任务。

## 1.2 Hybrid M480：强正信号，但不能冒充完整通过

M480 已有：

```text
true residual              ≈ 8.98e-12
R/T/A totals               ≈ Full3D h10
33 significant powers      max relative delta ≈ 3.05e-8
33 significant amplitudes  max relative delta ≈ 2.22e-8
selected E overall L2      ≈ 5.48e-6
```

但 selected H 在 z=10/z=60 nm 约为 `0.0617/0.0600`，超过现有 Gate。因此准确身份是：

```text
M480 = legal, high-quality Hybrid direct solver reference
M480 = not Full3D-validated Hybrid model
```

它足以用于 Hybrid iterative solver-only comparison，不足以用于 production/full-model claim。

## 1.3 M960：audit-blocked，不得直接解释为 modal-capacity failure

M960 的：

```text
raw_relative_error            = 1.678e-11
fixed forward-error limit      = 1e-12
representation_relative_error = 1.008e-14
```

它没有形成 linear solution、R/T/A、field 或 canonical result。当前只能分类为：

```text
M960 canonical raw-coordinate audit blocked
physical/model result unknown
```

不得写成“即使 M960 也不够”。但也不得直接把固定阈值放宽后重跑；必须先完成数值取证。

## 1.4 22 GiB 峰值尚未解释

tracked record 中 M480 的 `basis_bytes≈122.8 MB`、coupling 约几十 MB、direct augmented path未形成 modal Schur，远不足以解释 `22.264 GiB` process-tree peak。M960 在解前停止却仍约 `22.008 GiB`，也表明峰值不只是最终 \(2M\times2M\) 线性系统。

因此当前不批准立即开发 modal matrix-free、owner-only Schur 或 basis compression。必须先做生命周期与对象容量取证。

---

# 2. 扩展执行顺序

Codex 必须在同一 Task039 分支内按以下顺序执行，并在每个阶段完成后及时 commit 与 push：

```text
E0  extension inherited audit and exact plan
E1  non-invasive telemetry/comparator implementation and focused tests
E2  Full3D direct p6/h7.5
E3  Full3D direct p6/h6
E4  conditional Full3D direct p6/h5
E5  Full3D direct grid-convergence decision and reference selection
E6  M480 H-field discrepancy decomposition
E7  M960 canonical-trace numerical audit and conditional one-time rerun
E8  M480 Hybrid iterative MPI8 solver-only diagnostic
E9  conditional M480 Hybrid iterative MPI1 minimum-memory diagnostic
E10 memory-lifecycle attribution and extension closeout
```

允许 E6/E7 的轻量离线取证与 E2/E3 的文档整理交错进行，但任何重型 PDE 必须严格串行。禁止同时运行两个 Full3D/Hybrid job。

若任一阶段发现共享物理、material sign、mode-key、field convention 或 source-provenance defect，停止后续重型作业，先做窄修复和 focused tests。不得把失败后调参包装成同一候选重跑。

---

# 3. E0：扩展继承审计

创建：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/extension_inherited_audit.md
```

必须记录：

- current local/remote branch SHA、upstream、ahead/behind、clean status；
- T3 h10 Full3D direct authority record和raw hash；
- T5 M480 direct reference和selected payload hash；
- M960 negative-trace audit raw evidence；
- measured machine capacity：physical、WSL selected limit、effective hard limit；
- 本 Review 授权的扩展范围；
- ordinary defaults、master与其他分支不变；
- full pytest 首轮为 cancelled/not_run，不得写成 pass。

第一项扩展提交必须为 docs-only：

```text
docs(task039): audit approved post-closeout extension
```

---

# 4. E1：非侵入式实现与测试

只允许增加或扩展以下能力：

1. Full3D direct h7.5/h6/h5 `.dat` 和 mesh/resource preflight；
2. 跨网格 physical comparison checker；
3. M480 Hybrid iterative solver-only profile与 direct-reference checker；
4. H-field三路径诊断；
5. M960 canonical-trace backward-error audit；
6. QEP/modal/coupling/factor/lifecycle的阶段内存 telemetry。

禁止：

- 修改 Maxwell 方程、材料、几何、DtN mode selection；
- 修改 Full3D M3a PC；
- 修改 Hybrid whole-endcap ILU、Woodbury、two-pass、block-LDU参数；
- 新增 M>960；
- 使用 warm start；
- 恢复 learned/neural分支；
- 自动运行0.7 nm PDE。

所有新 `.dat` 必须继续遵守一个 `.dat` 对应一次运行，并通过 Task38 strict validate/dry-run。

---

# 5. E2–E5：5 nm Full3D direct 网格收敛

## 5.1 固定物理

所有 direct 网格必须共享：

```text
wavelength             = 5.0 nm
n_grating/substrate    = 0.99396854453 + 0.00435380777i
geometry               = current 50 x 25 x 140 nm target grating
grazing/theta/phi      = 10° / 80° / 0°
polarization           = S
Nedelec degree         = p6
assembly               = assembly-time static condensed
external DtN inventory = exact same 604 keys
solver                 = same MUMPS direct authority path
MPI                    = 8
```

只改变 `mesh_target_nm`。

## 5.2 网格序列

```text
h10   = existing T3 authority; do not rerun
h7.5  = mandatory
h6.0  = mandatory if h7.5 resource run completes safely
h5.0  = conditional only
```

选择 h6 是为了在 h5可能接近内存上限时仍获得三个网格点：h10、h7.5、h6。

不得自动运行 h4、h3 或提高 p。

## 5.3 每个新网格的 preflight

正式 direct solve前必须完成：

```text
mesh-only cells / full DoFs / active rows
assembled-row and NNZ estimate
dynamic external-key identity
MUMPS symbolic/analysis estimate when available
predicted factor NNZ and process-tree peak range
available memory and swap audit
output-disk free space
```

资源策略：

```text
warning threshold        = 170 GiB process-tree RSS
configured hard stop     = 195 GiB process-tree RSS
effective hard stop      = min(195 GiB, 0.90 * measured selected limit)
any swap                 = immediate resource failure
concurrent heavy jobs    = forbidden
```

h7.5/h6在预测超过 hard stop时不得启动。h5只有同时满足以下条件才可运行：

```text
at least h10/h7.5/h6 measured records exist
predicted process-tree peak <= 180 GiB
predicted numeric factor + workspace has >=15% memory margin
MUMPS symbolic/analysis succeeds
swap = 0
disk/output capacity sufficient
```

若 h5不满足，记录 `not_run_by_resource_policy`；不得启用 BLR、改变方程或静默切换近似 direct。Out-of-core MUMPS不在本轮自动授权范围内。

## 5.4 每个 direct 结果的 own Gate

```text
direct solve success                   = true
true relative residual                 <= 1e-9
R/T/A/A_volume finite                  = true
energy closure absolute value          <= 1e-5
604 external keys exact and unique     = true
33+ dynamic significant set exported   = true
selected E/H common physical grid      = true
process-tree RSS/PSS/USS measured      = true
swap                                   = 0
```

每个网格必须输出：

- cells、full DoF、active/condensed rows；
- matrix NNZ与MUMPS factor NNZ；
- analysis/factor/solve/postprocess wall；
- R/T/A/A_volume；
- 全604通道和动态显著通道；
- 共同采样平面 E/H；
- process-tree RSS/PSS/USS；
- source/input/resolved/physical SHA。

不同网格之间不能比较 canonical DoF vector identity；必须在共同物理采样点比较场。

## 5.5 跨网格比较

比较：

```text
h10 vs h7.5
h7.5 vs h6
h6 vs h5 if h5 exists
```

significant channel集合使用相邻两网格中 `power_ratio >= 1e-8` 的并集；mode key必须完全一致。

Mandatory Gate：

```text
max |delta R,T,A_balance,A_volume|     <= 1e-4
max significant power relative delta   <= 1e-3
max significant amplitude rel delta    <= 1e-3
selected E relative L2                  <= 5e-3
selected H relative L2                  <= 1e-2
both runs energy closure                <= 1e-5
```

Strong Gate：

```text
max |delta R,T,A_balance,A_volume|     <= 1e-5
max significant power relative delta   <= 1e-4
max significant amplitude rel delta    <= 1e-4
selected E relative L2                  <= 2e-3
selected H relative L2                  <= 5e-3
```

## 5.6 Full3D reference选择

```text
if h6 vs h5 exists and Strong Gate passes:
    reference = h5
    classification = FULL3D_DIRECT_5NM_REFERENCE_ESTABLISHED_AT_P6H5

elif h7.5 vs h6 Strong Gate passes
and every monitored delta is non-increasing relative to h10 vs h7.5:
    reference = h6
    classification = FULL3D_DIRECT_5NM_REFERENCE_ESTABLISHED_AT_P6H6

else:
    reference = best_available_only
    classification = FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_WITHIN_RESOURCE_BUDGET
```

不得仅因 R/T/A 收敛就忽略场与通道；也不得仅因某个近零场分量的相对误差异常就直接否定，checker必须同时记录分母范数和绝对误差，供审阅判断。

## 5.7 三层误差分解

建立 direct reference后，必须同时报告：

```text
Full3D h10 vs Full3D href       = discretization error
Hybrid M480 h10 vs Full3D h10  = same-grid Hybrid model error
Hybrid M480 h10 vs Full3D href = total error to refined reference
```

这三项不得混成一个数字。

---

# 6. E6：M480 H 场差异分解

## 6.1 目标

区分以下三种情况：

```text
A. current Hybrid H export/postprocess is inconsistent
B. E is accurate but curl/derivative field needs more modal content
C. comparison plane/component/normalization creates artificial relative error
```

## 6.2 三种 H authority

在同一 common physical sample points上生成：

```text
H_hybrid_native   = current Hybrid modal/FE reconstruction output
H_hybrid_curlE    = independently compute curl(E_hybrid)/(i*omega*mu)
H_full3d          = Full3D direct field evaluated by the accepted Full3D path
```

`H_hybrid_curlE` 必须使用完整重建场和解析/FE导数，不得对40×20 sampled E做有限差分。

至少检查：

```text
z = 30, 60, 90 nm               # middle-region non-interface planes
z = 10 and 110 nm existing roles
one-sided near-interface planes  # e.g. 10+epsilon / 110-epsilon or element-safe offsets
```

near-interface offsets必须由实际网格/单元安全位置生成，不能使用落在facet归属不确定区的任意极小 epsilon。

## 6.3 必须输出

对每个plane与每个component：

```text
reference L2 norm
absolute L2 error
relative L2 error
max absolute error
phase-sensitive complex error
```

另外输出：

```text
total H vector error
normal Poynting flux error
local energy-density diagnostic
H_native vs H_curlE
H_curlE vs Full3D
H_native vs Full3D
```

## 6.4 分类

```text
if H_curlE vs Full3D passes but H_native vs Full3D fails:
    classification = M480_H_RECOVERY_OR_POSTPROCESS_DEFECT

elif H_native and H_curlE both fail similarly:
    classification = M480_H_DERIVATIVE_MODAL_TRUNCATION_NOT_CONVERGED

elif failure is dominated by near-zero denominator/component only
and total/vector/flux errors pass:
    classification = M480_H_GATE_CONDITIONING_REVIEW_REQUIRED

else:
    classification = M480_H_DISCREPANCY_UNRESOLVED
```

若 existing artifacts足以离线完成，不得重跑 PDE。只有缺少完整重建场/导数authority时，才允许一次 M480 Hybrid direct diagnostic rerun；其物理、M、MPI和solver必须完全不变。

若确认后处理缺陷，允许窄修复、focused tests和一次M480 checker重算；不得借机修改Hybrid方程或模态选择。

---

# 7. E7：M960 canonical trace 数值审计与条件性重跑

## 7.1 禁止简单放宽 fixed Gate

不得把：

```text
1e-12 -> 1e-10
```

作为无依据修复。

必须保留 raw forward relative error作为诊断，并新增 scale-aware backward error：

```math
\eta_{\mathrm{raw}}
=
\frac{
\lVert R-GM\rVert_\infty
}{
\lVert R\rVert_\infty
+
\lVert G\rVert_\infty\lVert M\rVert_\infty
+
\mathrm{tiny}
}.
```

其中 \(R\) 为 raw negative overlap，\(G\) 为 surface Gram，\(M\) 为 canonical mapping。

必须记录：

```text
M=120/240/480/960 raw forward error
M=120/240/480/960 backward error eta
surface Gram condition and norms
mapping norm
per-column absolute/relative errors
worst column and corresponding near-degenerate group
deterministic repeated-assembly difference
canonical representation error
machine epsilon and matrix dimension
```

## 7.2 允许替换 Gate 的严格条件

只有以下全部成立，才允许把 fixed forward-error Gate替换为 backward-error qualification：

```text
canonical representation error <= 1e-12
all matrices finite
no column/sign/order mismatch
repeat assembly backward error <= same limit
eta_raw <= 100 * eps_machine * matrix_dimension
raw forward relative error <= 1e-9 hard guard
M120/M240/M480 historical valid cases remain pass
focused unit/MPI tests pass
```

这不是“放宽物理精度”，而是用可解释的 backward stability Gate替代未随矩阵规模变化的固定 forward-error Gate。raw forward error仍必须写入结果。

若上述任一项不成立：

```text
classification = M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_FAIL
M960 rerun = forbidden
```

## 7.3 条件性一次 M960 rerun

若数值审计通过，只允许一次完全冻结的 M960 Hybrid direct MPI8 rerun：

```text
same physics / p6h10 / 604 keys
same QEP selection and tolerance
same exact traction
same direct solver
zero changes to M or material
```

必须完成 own residual、traction、projection、closure、R/T/A、orders、selected E/H、canonical和resource telemetry。

若 M960成功，再比较：

```text
M480 vs M960
M960 vs Full3D h10
M960 vs refined Full3D reference if available
```

但本 Review 不自动授权 M960 Hybrid iterative。完成 M960 direct后停止在该分支等待下一次审阅。

---

# 8. E8–E9：M480 Hybrid iterative solver-only diagnostic

## 8.1 身份

```text
reference equation/result = existing legal M480 Hybrid direct
Full3D model qualification = not claimed
purpose                    = test block-LDU iterative solver at 5 nm
```

M480不能被重命名为 `M_robust_h10`。结果只能回答：当前 iterative PC能否求解M480 Hybrid方程。

## 8.2 冻结候选

```text
wavelength / mesh / M      = 5 nm / p6h10 / 480
external modes             = exact 604 keys
outer operator             = exact monolithic Hybrid action
outer KSP                  = right FGMRES
restart                    = 90
max_it                     = 6000
initial guess              = zero
five residual thresholds   = 5e-9
exact traction Gate        = 1e-8
bottom/top action          = whole-endcap ILU(0) + dynamic DtN Woodbury
residual correction        = fixed two-pass
nested local KSP           = false
bottom/top direct factors  = 0/0
```

禁止根据结果修改：

```text
shift / overlap / ILU level / restart / passes / tolerance / M / mode set
```

## 8.3 Progressive monitoring

记录：

```text
0, 20, 60, 100, 200, 500, 1000, 2000, 4000, 6000
```

的：

```text
reported/global/bottom/top/modal true residual
bottom/top action residual when available
modal-Schur condition
PC apply time
Woodbury K condition
```

到达6000仍不通过时停止，不自动增加上限。

## 8.4 MPI8 numerical Gate

```text
KSP reason                          > 0
iterations                          <= 6000
reported/global/bottom/top/modal    <= 5e-9
exact traction bottom/top           <= 1e-8
external q identity                 <= 1e-10
full recovery and own physics       = pass
no direct fallback                  = true
nested local KSP                    = false
swap                                = 0
```

与 M480 direct比较：

```text
R/T/A/A_volume absolute delta       <= 1e-6
significant power relative delta    <= 1e-4
significant amplitude rel delta     <= 1e-4
canonical active/full relative L2   <= 1e-5
selected E/H relative L2            <= 5e-3
all 604 mode keys                   exact match
```

raw modal coefficients在独立QEP gauge下只作诊断，不作为正式逐项Gate。

通过时分类：

```text
M480_HYBRID_ITERATIVE_SOLVER_PASS_MODEL_NOT_FULL3D_QUALIFIED
```

失败时分类：

```text
M480_HYBRID_ITERATIVE_SOLVER_FAIL_AT_5NM
```

不得把它写成Hybrid reduced model失败。

## 8.5 MPI1

只有MPI8 numerical Gate通过后，才运行完全相同的MPI1候选。

MPI1必须通过MPI8 identity Gate，并报告极限内存。资源只分类，不改变数值结论：

```text
preferred MPI1 peak      <= 8 GiB
engineering MPI1 peak    <= 16 GiB
hard stop                = 48 GiB or any swap
```

MPI8资源相对M480 direct的分类：

```text
RSS < 22.264 GiB              = measured memory reduction
RSS <= 17.811 GiB             = >=20% relative reduction
RSS >= 22.264 GiB             = no memory advantage at this M
```

这些线不是numerical Gate。

---

# 9. E10：内存生命周期取证

## 9.1 必须覆盖的节点

对可用的 M120/M240/M480，以及M960 audit/rerun，记录以下阶段的同时process-tree RSS/PSS/USS和已知payload：

```text
mesh/spaces ready
QEP matrices ready
positive QEP solve peak
negative QEP solve peak
raw candidate eigenvectors ready
selected biorthogonal bases ready
canonical negative traces ready
projection matrices ready
traction matrices ready
local FE-DtN systems ready
Hybrid augmented operator ready
direct factor or iterative side factors ready
modal Schur ready (iterative only)
field reconstruction start/peak
postprocess peak
all modal/QEP temporaries released
final cleanup
```

## 9.2 对象容量

至少报告：

```text
QEP matrices and eigensolver workspace when observable
candidate/selected positive and negative eigenvectors
right/left/full/trace mode objects
canonical mapping/Gram/inverse Gram arrays
projection and traction matrix NNZ/bytes
interior-correction arrays
local FE-DtN matrices/factors
Woodbury W/K/LU
modal constraint/Schur/LU
Krylov basis estimate
field reconstruction buffers
```

不能用“modal basis≈123 MB”解释整个22 GiB，也不能把allocator high-water自动当成live object。

## 9.3 取证后分类

```text
QEP_WORKSPACE_DOMINANT
MODE_OBJECT_REPLICATION_DOMINANT
COUPLING_ASSEMBLY_DOMINANT
LOCAL_FE_FACTOR_DOMINANT
MODAL_SCHUR_DOMINANT
LIFECYCLE_OVERLAP_DOMINANT
UNATTRIBUTED_RUNTIME_OR_ALLOCATOR_HIGH_WATER
```

可多选，但必须给出 measured/derived/not_available边界。

本 Review只授权取证，不授权随后自动实施 modal matrix-free、owner-only Schur、basis compression或QEP算法替换。

---

# 10. 更新后的科学结论边界

本扩展结束后必须能够分别回答：

| 问题 | 允许的答案 |
|---|---|
| 5 nm Full3D direct是否网格收敛 | h6/h5 reference established，或 within-budget not established |
| h10 direct离精细参考多远 | measured discretization deltas |
| M480 Hybrid模型误差 | same-grid 与 refined-reference 两套结果 |
| M480 H差异来源 | postprocess / truncation / gate conditioning / unresolved |
| M960为何停止 | backward-stable audit pass/fail；若pass则一次direct结果 |
| M480 iterative是否可求解 | MPI8 pass/fail；条件性MPI1 identity与内存 |
| 22 GiB由谁占用 | stage/object attribution |
| 0.7 nm当前架构 | 首轮T9分类保留；不得因本扩展自动改成plausible |

禁止使用以下结论，除非相应Gate真实完成：

```text
5NM_HYBRID_ITERATIVE_FULL_MODEL_PASS
5NM_FULL3D_CONTINUUM_REFERENCE_ESTABLISHED
M960_PHYSICS_PASS
0P7NM_CURRENT_ARCHITECTURE_PLAUSIBLE
```

---

# 11. 交付文件

新增或更新：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/extension_inherited_audit.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/full3d_direct_grid_convergence_v2.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/m480_h_field_diagnostic.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/m960_trace_numerical_audit.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/m480_hybrid_iterative_solver_diagnostic.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/memory_lifecycle_forensics.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/resource_ledger.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/summary.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/test_summary.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v2.md
```

compact records必须使用新版本/新文件名，不能覆盖T3/T4/T5/T9历史记录。

---

# 12. 测试、provenance 与提交边界

每个实现阶段后运行对应focused tests；所有重型结果完成后至少运行：

```text
Task39 extension focused suite
MPI1/2/4 tiny ownership/launcher fixtures
all Task39 dat validate-only and dry-run
Ruff check on changed Python
Ruff format --check on changed Python
python -m compileall
git diff --check
benchmarks/check_benchmarks.py --no-write
compact JSON/schema/link/math/table checks
```

完整 repository pytest本轮不自动运行。只有后续master integration review明确要求时才运行；不得把它写成pass。

所有正式运行必须绑定：

```text
clean source SHA
input SHA
resolved config SHA
physical model SHA
raw artifact SHA
process-tree telemetry
```

按阶段及时 commit和push到：

```text
origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
```

禁止：

```text
修改或push master
创建新分支/worktree
force push
删除或重写首轮negative records
提交raw meshes/fields/factors/timelines
```

完成 E10 和 `response_v2.md` 后停止等待审阅，不得自动开始Full3D PC redesign、modal matrix-free、0.7 nm PDE或master merge。
