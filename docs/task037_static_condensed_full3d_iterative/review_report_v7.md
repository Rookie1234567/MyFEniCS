# Task037 Review Report V7：最终结项、选择性合入与 Task37b 本地分支交接

## 0. 审阅身份与授权边界

```text
review                         = Task037 Review Report V7
reviewed_branch                = codex/20260803-task37-matrix-free-iterative-development
reviewed_final_response        = docs/task037_static_condensed_full3d_iterative/response_v6.md
reviewed_final_capacity_record = task37_v6_e2_modal_capacity_closeout_v1.json
ordinary_default               = unchanged
whole_branch_merge             = forbidden
selective_merge_to_master      = authorized subject to all Gates below
push_origin_master             = authorized subject to all Gates below
Task37b task.md                = forbidden in this handoff
Task37b implementation         = forbidden in this handoff
Task37b remote branch push     = forbidden in this handoff
```

本报告是 Task037 的最终主审结论。Task037 不再开发 Candidate G/H，不再重新打开已经关闭的预条件器家族，也不在本分支继续 Task37b。

最终分类为：

```text
TASK037_CLOSED_NUMERICAL_CORE_PASS_SCALABLE_PC_NOT_DEMONSTRATED
```

其含义是：

- 高阶 `p6/h10`、静态凝聚 Full3D 的迭代求解代数已经建立；
- M3a 在完整场、残差、R/T/A 与显著衍射通道上通过；
- exact matrix-free p6 fine action 已经通过代数资格化；
- formal 80-mode Matrix-free DtN 已经通过 action/recovery Gate；
- 当前真正能收敛的方法仍依赖 16 个较大的 p6 slab ILU factors；
- p2、p4、部分凝聚、factor-free 裸局部 Krylov、当前 RAS、M120 modal coarse 等候选均未得到可扩展的收敛替代；
- 因而 Task037 没有证明 `0.7 nm` 可扩展 Full3D PC，但留下了可供 Task37b 复用的迭代与 matrix-free 基础设施。

---

# 1. 最终科学结论

## 1.1 当前唯一完整通过的迭代方法：M3a

M3a 使用：

```text
exact p6 static-condensed Full3D operator
+ right FGMRES
+ 16 overlapping physical z-slabs
+ local shifted ILU(0)
+ partition-of-unity additive Schwarz
+ 75D Floquet-wave coarse correction
```

其局部预条件器可写为：

```math
M_{\mathrm{M3a}}^{-1}r
=
\sum_{j=1}^{16}
R_j^T W_j U_j^{-1}L_j^{-1}R_jr
+
Q_{75}r.
```

M3a 已完成 MPI1/2/4/8 full solve，均通过：

- reported residual；
- condensed true residual；
- full augmented residual；
- full-FE residual；
- canonical active/full-FE vectors；
- fresh-mesh `L2`、curl 与 `H(curl)` norms；
- 12/12 significant powers；
- 12/12 boundary complex amplitudes；
- R/T/A 与能量闭合；
- zero swap。

资源事实：

| MPI | process-tree peak | wall | 结论 |
|---:|---:|---:|---|
| 1 | 4.600 GiB | 1999 s | 最低总内存 |
| 2 | 5.683 GiB | 1153 s | 通过 |
| 4 | 8.266 GiB | 712 s | 内存/速度折中 |
| 8 | 12.593 GiB | 471 s | 最快，但总内存较高 |

M3a 需要累计约 `91.4M` 个 p6 local factor NNZ，因此是可用研究基线，不是 `0.7 nm` 的可扩展终点。

## 1.2 Factor-free fine action：正结果

Task037 已证明，可以不形成：

```text
global augmented A
global fine F
global p6 direct factor
p6 slab matrix
p6 slab factor
```

而直接施加：

```math
F x
=
\sum_K C_K^H S_K C_Kx.
```

该 action 与 assembled static-condensed operator 达到机器精度一致。这个能力必须保留。

## 1.3 Matrix-free DtN：正结果

正式 80-mode Gate 已通过。当前 condensed operator 的端口部分为：

```math
A_{\mathrm{cond}}x
=
Fx-CH^{-1}Dx.
```

Matrix-free profile 按：

```math
y=Dx,
\qquad
z=H^{-1}y,
\qquad
t=Cz
```

执行，而不物化完整显式 `C/D` coupling。正式 E0 修复后：

- forward action 最大相对误差约 `1.24e-15`；
- auxiliary recovery 最大相对误差约 `1.11e-15`；
- physical RHS identity 为 0；
- primary profile 显式 `C/D = 0/0`；
- MatPython telemetry 正确写 `not_applicable`，不伪造 NNZ 为零。

该能力是 Task037 最重要的通用正成果之一，必须选择性合入。

## 1.4 已关闭的低内存 PC 家族

| 名称 | 含义 | 最终状态 |
|---|---|---|
| Candidate A | global p2 auxiliary + diagonal | closed negative |
| B2 | factor-free local GMRES(2) | long-tail plateau，closed |
| B4 extension | factor-free local GMRES(4) 及继续增加裸步数 | closed |
| Candidate C | 当前 one-hot RAS/interface-shift 实现 | closed |
| Candidate D | local p2-preconditioned p6 slab Krylov | contraction negative |
| R7 | p4-core partial condensation | component positive，public complement 未闭合 |
| Candidate F | p6→p4→p2 hierarchy | frozen ideal-capacity negative，closed |
| Candidate E | M120 modal-assisted Full3D coarse | frozen late-residual capacity negative，closed |

Candidate E 最终不是 implementation failure。E1 已成功建立 240 列、满秩 M120 Full3D basis；E2 使用 QR/SVD 理想 minimum-residual capacity oracle，M120 对第 100/200 步 B4 late residual 只改善约 `0.3–0.4%`，在已有 75D coarse 上的增益不到 `1%`，全部 late Gate 6/6 失败。因此不实现 actual modal coarse PC。

## 1.5 Task037 没有否定 Task37b

Task037 中的 Candidate E 是：

```text
Full3D unknowns
+ M120 仅作为 coarse/deflation directions
```

Task37b 将研究：

```text
original Hybrid block system
+ modal amplitudes 是真实系统未知量
+ top/bottom FEM blocks 使用迭代 inverse
```

两者不是同一个算法。Candidate E 的负结果不能用于关闭 Task37b。

---

# 2. 选择性合入总原则

## 2.1 禁止 whole-branch merge

禁止：

```bash
git merge codex/20260803-task37-matrix-free-iterative-development
```

也禁止：

```text
先 cherry-pick 大型综合提交
再删除大部分研究文件
```

Task037 分支包含大量受控负结果、临时候选、重型 runner flags、capacity oracles 和 evidence-only modules。必须从最新 `origin/master` 出发，按文件和 hunk 选择性移植。

## 2.2 Ordinary default 必须保持不变

所有新能力必须满足：

```text
ordinary Full3D direct default = unchanged
ordinary Hybrid direct default = unchanged
Task37 iterative profiles      = explicit opt-in
research-only negative lanes   = absent from master
```

不得将 M3a 写成 production default，也不得将 Task037 写成 `0.7 nm qualified`。

## 2.3 Master 中只保留三类内容

1. 已通过的通用 correctness / telemetry；
2. 已通过的 matrix-free / iterative 基础设施与 M3a opt-in baseline；
3. 紧凑结项文档和少量权威记录。

所有负候选的完整历史继续保存在 Task037 远程分支，不需要复制到 master。

---

# 3. M0：必须选择性合入的通用 correctness 与 telemetry

## 3.1 MatPython/SHELL-safe matrix telemetry

从 `src/solvers/common_3d_solve.py` 选择性合入：

- `_petsc_matrix_stats(...)` 对 `PETSc.Mat.Type.PYTHON/SHELL` 的安全处理；
- 记录 type、global/local size、ownership、block sizes、`matrix_free=true`；
- 不支持的 NNZ、memory、norm、PETSc-info 字段写 `not_applicable`；
- 不得把不适用字段伪造为 `0`；
- 显式 AIJ 路径原有统计不得退化。

从 `src/solvers/common_3d_case_flow.py` 选择性合入：

- action-only / no-global-A/F summary plumbing；
- `global_A_materialized=false` 时不误走显式矩阵统计；
- external solver lifecycle 与 official-result gating；
- 不合入 Candidate E 专属容量运行逻辑。

保留对应测试：

```text
src/test/test_28_direct_memory_telemetry.py
src/test/test_219_task037_external_solver_runtime.py
src/test/test_249_task037_e0_wiring.py
```

但 `test249` 只保留通用 MatPython/action-only wiring assertions，不保留 V6 campaign-only CLI 绑定。

## 3.2 进程树和资源语义

从 benchmark/watchdog 变更中只保留：

- simultaneous process-tree RSS/PSS/USS；
- historical rank peak 与 simultaneous authority 分离；
- zero-swap；
- TERM→KILL 完整进程组终止；
- no-orphan verification；
- matrix-free/action-only lifecycle stage 标记；
- clean-source SHA provenance。

禁止整体复制当前 `benchmarks/run_task033_full3d_watchdog.py`。该文件混入大量 A–F/E campaign flags，Codex 必须逐 hunk 提取通用能力和 M3a 最小入口。

---

# 4. M1：必须选择性合入的 Matrix-free DtN

## 4.1 `src/solvers/condensed_dtn.py`

选择性保留：

- `PetscCondensedBlocks` 的安全生命周期；
- exact condensed RHS / auxiliary recovery / full augmented residual；
- `_MatrixFreeDtnBlockState`；
- `_MatrixFreeDtnMatContext`；
- action-only `C/D` forward 与 Hermitian action；
- streaming `DtnBlockAssembler` 的 matrix-free profile；
- matrix-free condensed operator；
- explicit-oracle 与 matrix-free-primary identity probe；
- no-global-A/F materialization metadata。

不得保留：

- p2/p4/modal candidate-specific projection or capacity hooks；
- E1/E2 campaign-only snapshot logic；
- 仅为 research closeout 服务的 serialization branches。

## 4.2 `src/solvers/dtn_port_3d.py`

逐 hunk 合入：

- action-only external solver request/snapshot；
- 80-mode matrix-free block construction；
- auxiliary amplitude recovery；
- mode-key、beta、polarization、power normalization、Rayleigh identity；
- primary matrix-free / explicit oracle 分离；
- ordinary default 继续使用原有显式路径，除非显式 opt-in。

## 4.3 Wrapper

从：

```text
src/solvers/solve_maxwell_3d_stage_4b_block_grating.py
src/solvers/common_3d_case_flow.py
```

只合入最小公共参数透传，不合入 Task037 campaign flags。

## 4.4 Tests

至少保留并整理：

```text
src/test/test_22_condensed_dtn.py
src/test/test_230_task037_dtn_direct_blocks.py
src/test/test_231_task037_dtn_action_only_port.py
```

必要时从 `test249` 提取 MatPython wiring 测试到职责更清晰的小文件。

---

# 5. M2：选择性合入的 static-condensed Full3D iterative core

## 5.1 完整新模块可合入

以下模块属于通过的通用基础设施，可按当前职责审阅后整文件合入：

```text
src/solvers/static_local_schur_action.py
src/solvers/hcurl_canonical_vector.py
src/solvers/hcurl_canonical_vector_dolfinx.py
benchmarks/canonical_vector_artifacts.py
```

前提是它们不再 import Candidate A–F/E research modules，且 targeted tests通过。

## 5.2 `static_condensed_iterative.py` 必须瘦身后合入

不得整文件照搬当前版本。Master 版本只保留：

```text
solve_assembled_static_condensed_fgmres
solve released/static-local-Schur matrix-free authority path
solve_never_materialized_overlap0125_partition_fgmres  # M3a opt-in
true residual vector observer
condensed/full-augmented recovery and residual checks
external solver snapshot/lifecycle contract
```

必须删除或不移植：

```text
solve_never_materialized_p2_auxiliary_fgmres
solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres
solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres
Candidate D/F/E observers and capacity hooks
imports of static_p2_auxiliary_pc / modal capacity modules
```

M3a 必须保持 explicit opt-in，并在 docstring 中写明：

```text
numerically qualified on Case100 p6/h10
resource-scalability not qualified for 0.7 nm
```

## 5.3 `physical_slab_two_level.py` 必须逐 hunk 合入

保留：

- trace-aware physical slab partition；
- owner-local slab plan；
- owner-local diagonal；
- `DistributedPhysicalSlabSmoother`；
- factor-only local ILU lifecycle；
- partition-of-unity weights；
- `SparseCoarseVector`；
- `SparseGalerkinTwoLevelPc`；
- 75D Floquet wave coarse；
- factor inventory 与 setup observers。

不合入：

- Candidate C/D/F/E 专属 mask、capacity、snapshot、modal hooks；
- 已失败的 p2/p4 auxiliary and factor-free local-Krylov families；
- broad parameter-scan helpers。

## 5.4 Tests

选择性保留并整理：

```text
src/test/test_217_task037_f0_direct_authority.py
src/test/test_218_task037_static_iterative_port.py
src/test/test_219_task037_external_solver_runtime.py
src/test/test_220_task037_trace_aware_physical_slabs.py
src/test/test_221_task037_active_trace_basis.py
src/test/test_222_task037_assembled_fgmres_core.py
src/test/test_223_task037_f3_watchdog_screen.py
src/test/test_224_task037_static_local_schur_action.py
src/test/test_229_task037_action_only_condensation.py
src/test/test_232_task037_owner_local_slab_assembler.py
src/test/test_233_task037_owner_local_slab_smoother.py
```

若某测试只覆盖被排除的 Candidate，则不得无选择地复制；应拆分保留通用断言。

---

# 6. M3：Canonical comparator 与跨 MPI identity

必须保留：

- original trace → active trace → canonical entity packet 映射；
- edge/face entity identity；
- Basix orientation；
- Floquet master/phase；
- recovered full-FE canonical export；
- ownership-order数组与 canonical physical coordinates 明确区分；
- canonical active/full relative L2；
- fresh-mesh `L2`、curl、tangential trace mass 与 `H(curl)` norms。

对应模块：

```text
src/solvers/hcurl_canonical_vector.py
src/solvers/hcurl_canonical_vector_dolfinx.py
benchmarks/canonical_vector_artifacts.py
```

对应测试：

```text
src/test/test_225_task037_canonical_vector_comparator.py
src/test/test_226_task037_canonical_vector_dolfinx.py
src/test/test_227_task037_canonical_vector_artifacts.py
src/test/test_228_task037_canonical_vector_reconstruction.py
```

这套 comparator 对后续 Task37b 判断“iterative solver error”与“Hybrid model error”非常重要，必须合入。

---

# 7. M4：为 Task37b 保留的模态/跨网格通用修复

Candidate E 的 coarse 容量为负，不代表其过程中发现的通用正确性修复无效。以下内容可逐 hunk 合入，但必须通过 Hybrid 既有测试：

## 7.1 `src/modes/mode_classification.py`

允许保留：

- near-degenerate modes 的联合子空间识别与一致旋转；
- rotation 后 biorthogonality audit；
- fail-closed block partition split；
- 不改变冻结阈值、mode ordering、方向分类和 ordinary selection contract。

不得合入：

- Candidate E capacity-specific report structures；
- 为通过单个 case 而改变 tolerance 的代码；
- 自动重选 M、删模式或动态放宽 pairing。

## 7.2 `src/coupling/hybrid_internal_modes.py`

允许保留：

- owned+ghost cell 的稳定跨网格插值；
- canonical trace key closure；
- missing/extra/duplicate fail-closed；
- propagation/traction beta identity；
- 不改变原 Hybrid ordinary formulas。

## 7.3 测试

保留或提取：

```text
src/test/test_179_task035b_hybrid_static_condensation.py
src/test/test_hybrid_interface_audits.py
```

只保留通用 near-degenerate、orientation、cross-mesh trace 和 beta identity 测试；不合入 E1/E2 capacity campaign tests。

---

# 8. 明确禁止合入 master 的文件与能力

下列内容继续保留在 Task037 分支历史，不进入 master：

```text
src/solvers/static_factor_free_slab_pc.py
src/solvers/static_p2_auxiliary_pc.py
src/solvers/static_p2_slab_pc.py
src/solvers/static_trace_auxiliary.py
src/solvers/hcurl_p4_core_partial_condensation.py
src/solvers/hcurl_p4_core_global_partial_condensation.py
src/solvers/static_p4_capacity_oracle.py
src/solvers/static_modal_capacity_oracle.py
src/solvers/static_modal_coarse_basis.py
src/solvers/static_modal_coarse_gate.py
```

以及对应的 Candidate D/F/E 测试：

```text
src/test/test_234_task037_p2_trace_transfer.py
src/test/test_235_task037_p2_galerkin_auxiliary.py
src/test/test_236_task037_p2_auxiliary_pc.py
src/test/test_237_task037_factor_free_slab_pc.py
src/test/test_238_task037_p2_factor_free_composition.py
src/test/test_239_task037_p2_factor_free_core_profile.py
src/test/test_240_task037_p2_local_slab_pc.py
src/test/test_241_task037_candidate_d_local_p2.py
src/test/test_242_task037_p4_core_partial_condensation.py
src/test/test_243_task037_p4_core_partial_condensation_integration.py
src/test/test_244_task037_p4_core_assembly_time_integration.py
src/test/test_245_task037_retained_dtn_adapter.py
src/test/test_246_task037_p4_capacity_oracle.py
src/test/test_248_task037_candidate_f_f0b_capacity.py
src/test/test_250_task037_static_modal_coarse_basis.py
src/test/test_251_task037_e1_modal_basis_gate.py
src/test/test_252_task037_e2_b4_snapshot_carrier.py
```

禁止合入：

- A/B2/B4/C/D/F/E campaign CLI flags；
- 20/100/200 candidate funnel runner；
- capacity oracle runner；
- M120 Full3D coarse basis和E2 capacity code；
- p4 partial condensation public path；
- 96-RHS/POD/discrete-Bloch 等 Task036 已关闭路线；
- raw artifacts、memory timeline 和大型逐轮日志；
- 将 Candidate negative 标成 production capability 的文档。

---

# 9. Master 中保留的文档与记录

## 9.1 建议保留

```text
docs/task037_static_condensed_full3d_iterative/task.md
docs/task037_static_condensed_full3d_iterative/review_report_v7.md
docs/task037_static_condensed_full3d_iterative/response_v6.md
docs/task037_static_condensed_full3d_iterative/outcomes/summary.md
docs/task037_static_condensed_full3d_iterative/outcomes/test_summary.md
```

如果 `response_v6.md` 过长，可在 master 中用一份精简 final closeout 替代，但必须保留：

- E0 Matrix-free DtN pass；
- E1 M120 basis pass；
- E2 capacity negative；
- M3a MPI scaling；
- Candidate A–F closure表；
- selective merge manifest；
- Task37b handoff边界。

## 9.2 建议保留的 compact records

最多保留以下权威记录：

```text
task37_direct_authority_v2.json
task37_m3a_mpi_scaling_v1.json
task37_v2_preconditioner_funnel_v1.json
task37_candidate_f_f0b_decisive_capacity_v1.json
task37_v6_e2_modal_capacity_closeout_v1.json
```

不把每次 screen、implementation blocker和中间修复记录全部复制到 master。

## 9.3 项目总账

选择性合入完成后，更新：

```text
docs/development_progress.md
docs/development_model_registry.md
```

登记：

```text
Task37 M3a numerical pass
MPI1/2/4/8 resource results
matrix-free fine action pass
formal 80-mode Matrix-free DtN pass
factor-free scalable PC not demonstrated
A–F/E controlled negatives
Task37 closed
Task37b planned / task not yet written
```

---

# 10. 合入提交计划

Codex 应在本地最新、干净的 `master` 上直接进行选择性移植，不创建中间 integration 分支。建议形成以下提交：

```text
feat(task037): integrate static-condensed Full3D iterative core

feat(task037): integrate matrix-free DtN and action-only telemetry

fix(task037): integrate canonical trace and modal-basis safety

test(task037): add focused iterative and matrix-free coverage

docs(task037): record controlled closeout and Task37b handoff
```

允许根据依赖顺序将前两项调整或合并，但每个提交必须职责清晰。禁止把全部内容压成一个大型 commit。

---

# 11. 合入前测试 Gate

## 11.1 静态检查

对所有 touched Python files：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

不得使用自动格式化掩盖数值改动；若需要格式化，单独检查 diff。

## 11.2 Targeted serial tests

至少运行合入后的实际文件对应的：

```text
test_28_direct_memory_telemetry.py
test_217_task037_f0_direct_authority.py
test_218_task037_static_iterative_port.py
test_219_task037_external_solver_runtime.py
test_220_task037_trace_aware_physical_slabs.py
test_221_task037_active_trace_basis.py
test_222_task037_assembled_fgmres_core.py
test_224_task037_static_local_schur_action.py
test_225_task037_canonical_vector_comparator.py
test_226_task037_canonical_vector_dolfinx.py
test_227_task037_canonical_vector_artifacts.py
test_228_task037_canonical_vector_reconstruction.py
test_229_task037_action_only_condensation.py
test_230_task037_dtn_direct_blocks.py
test_231_task037_dtn_action_only_port.py
test_232_task037_owner_local_slab_assembler.py
test_233_task037_owner_local_slab_smoother.py
```

以及被选择性合入的 mode/Hybrid safety tests。

若测试文件因拆分而重命名，以实际功能覆盖为准；不得为了通过而删除断言或放宽阈值。

## 11.3 MPI tests

至少运行：

- MatPython telemetry MPI2；
- Matrix-free DtN action/recovery MPI2 和 MPI4；
- canonical vector MPI2；
- slab partition / owner-local smoother MPI2；
- near-degenerate/cross-mesh modal trace MPI2。

## 11.4 PDE smoke

至少完成：

1. 一个小型 static-condensed assembled FGMRES smoke；
2. 一个小型 no-global-A/F local-Schur action smoke；
3. formal 80-mode Matrix-free DtN component Gate；
4. p6/h10 M3a 一次完整 MPI4 full solve，或在资源环境明确不足时使用 MPI1 full solve。

M3a full 必须通过：

```text
reported / condensed / full-FE residual <= 1e-6
canonical active/full <= 1e-5
12/12 powers
12/12 amplitudes
R/T/A and closure
swap = 0
```

不得运行 Candidate A–F/E。

## 11.5 Full repository pytest

在 targeted Gate 全部通过后，运行一次无 deselect 的 full repository pytest。

- 若完整通过，记录 PASS；
- 若因明确的小时级 timeout 未完成，必须记录 completed count、首个未执行位置与 timeout，不得写 PASS；
- 若出现与本次 touched code相关的失败，停止，不得推送 master；
- 不得通过删除测试、xfail 新失败或放宽 Gate完成合入。

---

# 12. Master 推送 Gate

只有满足以下全部条件，才允许：

```bash
git push origin master
```

条件：

- 本地 master 以最新 `origin/master` 为起点；
- 没有 whole-branch merge；
- diff 只包含 V7 白名单；
- ordinary defaults不变；
- research-only负候选不在 master；
- targeted serial/MPI/PDE Gates通过；
- full pytest结果如实记录，且无 touched-code failure；
- 工作树 clean；
- master ahead/behind 与预期一致；
- push 后 `master == origin/master`。

若任一 Gate 失败，停止并报告，不创建 Task37b 分支。

---

# 13. Task37b 本地分支交接

## 13.1 分支名称

Master 成功推送后，Codex 只在本地创建：

```text
codex/20260807-task37b-hybrid-iterative-development
```

## 13.2 创建方式

先更新远程引用并确认：

```text
local master SHA == origin/master SHA
master worktree  == clean
```

然后从该 SHA 创建本地分支。

要求：

```text
new branch initial SHA == updated master SHA == origin/master SHA
worktree clean
no file changes
no commits
no task.md
no code implementation
no PDE
no remote push of Task37b branch
```

若同名本地分支已经存在，禁止覆盖或强制移动；停止并报告其 SHA 与相对 `origin/master` 状态。

Task37b 任务书将在新分支身份确认后，由下一轮主审单独制定。

---

# 14. Codex 最终回报格式

完成后只报告：

```text
Task37 reviewed source SHA
review_report_v7 commit SHA
selective master commits and one-line purpose
excluded research-only file count / key families
serial targeted test summary
MPI targeted test summary
PDE smoke/full summary
full pytest summary or explicit incomplete boundary
pushed master SHA
origin/master SHA
Task37b local branch name
Task37b local branch SHA
Task37b relative status vs origin/master
Task37b worktree status
```

不得在 Task37b 分支创建任务书或开始开发。

---

# 15. 最终主审结论

```text
Task037 scientific work        = closed
M3a numerical capability       = retained as explicit opt-in baseline
matrix-free p6 fine action      = retain
formal matrix-free DtN          = retain
canonical comparator            = retain
MatPython/resource telemetry    = retain
near-degenerate/trace safety    = selective retain
factor-free scalable PC         = not demonstrated
Candidates A–F/E               = preserve as branch history only
whole branch merge              = forbidden
selective master merge          = authorized after Gates
Task37b local branch creation   = authorized only after master push
Task37b task/implementation     = not authorized in this handoff
```
