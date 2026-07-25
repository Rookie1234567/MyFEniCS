# Task035b Review V3：Task035/035b 选择性合并、模型总账闭环与静态凝聚 Hybrid 续研

## 1. 审阅身份与总决定

```text
review_status = CONDITIONAL_SELECTIVE_MERGE_APPROVED_AND_NEXT_BRANCH_AUTHORIZED
reviewed_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
reviewed_head = 25a35e2b301d7f1ccae565ae8de16120df14ae37
master_base = 5002636852ffb67b4711443da70eb536c303e34e
branch_ahead_of_master = 265 commits
Task035_scientific_status = accepted_research_baseline
Task035b_final_accuracy_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
whole_branch_merge = forbidden
file_level_selective_merge = approved_after_M0_to_M4
user_merge_authorization = explicit_in_current_instruction
ordinary_default = original_full_matrix_direct
static_condensation_public_port = required_before_merge
static_condensation_status = qualified_opt_in_direct_backend
condensed_iterative_status = research_negative_not_public_profile
next_branch = codex/20260726-task35b-high-order-local-hp-resource-envelope
next_branch_base = merged_clean_master
static_condensation_hybrid = authorized
hybrid_adaptivity_from_h13_seed = authorized_with_two_level_accuracy_gate
irregular_geometry = still_out_of_scope
```

本 Review 同时完成 Task035 与 Task035b 的统一合并审查。Task035 Review V6 已明确要求二者最终不能分开合并；当前 Task035b 分支正是从 Task035 审查基线堆叠而来，因此本轮不再把两者拆成两个互不完整的合并动作。

准确结论分为四层：

1. **Task035 的科学问题已经得到肯定回答。** 双周期 Maxwell/Floquet/DtN 问题上，真实离散伴随、DWR、周期四面体局部细化和同源 h/p 比较已经形成研究证据；但它不是 production 自动 hp 求解器。
2. **Task035b 的静态凝聚直接法已经形成明确工程价值。** 它在受限但清楚的规则六面体范围内，精确消去 cell-interior 自由度、在全局插入前消去 Floquet slave，并保留完整场恢复、真残差和正式 R/T/A/衍射级；该能力值得进入 master，作为与原始完整矩阵法并列的显式可选后端。
3. **Task035b 尚未达到最终同误差目标。** 当前预算内最强 `fixed p5 trace + p6 cell interior, directional-z h13` 为 89,740 Full3D-equivalent DoF、20,120 active rows，但仍只有 10/12 significant powers 与 10/12 significant complex amplitudes；不能把该模型提升为最终自适应成功解。
4. **当前分支不能整体 merge。** 它相对 master 多 265 个提交，包含 production 候选、研究基础设施、未完成 selective trace、失败迭代 profile、任务专用 runner、大量重复/中间 records 与受控负结果。必须从干净 master 建立一次文件级选择性整合，严格按依赖组迁移。

本轮用户已明确授权：Codex 在完成本 Review 的合并前置 Gate 后，可以执行选择性 merge，不需要再次请求用户确认，也不需要再等待一轮中间 ChatGPT Review。若合并过程中发现源码身份、ABI、测试、数值 anchor 或依赖闭包异常，则必须停止并报告，不能为了完成 merge 放宽 Gate。

---

# PART I：合并前必须完成的收口工作

## 2. M0：先完整维护 `development_model_registry.md`

在任何 master 合并前，Codex 必须先完成：

```text
docs/development_model_registry.md
```

当前文档已经建立了正确的一级方法分类，但“所有 Task 的探索模型”仍不完整，章节编号和逐 Task 主模板也未完全符合用户要求。本轮必须读取 **Task000–Task035b 的全部任务总结、正式 response、最终 review、benchmark records 和历史进度表**，完成项目级回填。

### 2.1 固定一级结构

必须保持并完善：

```text
1.1 COMSOL 收敛与求解器参考
    1.1.1 直接法
    1.1.2 成功迭代法

1.2 FEniCS 原始完整 FE 矩阵法：直接求解
    1.2.1 Full 3D
    1.2.2 Hybrid

1.3 FEniCS 原始完整 FE 矩阵法：迭代求解
    1.3.1 Full 3D
    1.3.2 Hybrid

1.4 静态凝聚法：直接求解
    1.4.1 Full 3D
    1.4.2 Hybrid

1.5 静态凝聚法：迭代求解
    1.5.1 Full 3D
    1.5.2 Hybrid

1.6 自适应求解
    1.6.1 Full 3D
    1.6.2 Hybrid
```

### 2.2 “所有 Task”章节必须改为第 3 章

必须改成：

```text
3. 所有 Task 的探索模型
3.1 Task000
3.2 Task001
...
3.36 Task035
3.37 Task035b
```

不得只登记 Task027–Task035b，也不得把早期 Task 用一句总链接代替。没有重型 PDE 的 Task 也要说明它做的是组件、诊断、求解器或未运行 Gate；有多个模型的 Task 必须逐模型列出。

### 2.3 每个 Task 使用统一主模板

每个 Task 先写一段通俗说明：

```text
研究对象是什么？
为什么要算这个模型？
它改变了原有流程的哪一部分？
最终得到什么结论？
```

随后使用统一主表。最低字段为：

| 字段组 | 必须登记的字段 |
|---|---|
| 身份 | Model ID、Task、source SHA、evidence path、数据身份 |
| 物理 | 几何、尺寸、波长、入射角、偏振、材料、边界、衍射级范围 |
| 离散 | cell type、几何阶次、Nédélec 阶次、trace/interior 阶次、h、cell count、Full3D/Hybrid |
| 算法 | 原始完整矩阵/静态凝聚/matrix-free，direct/iterative，solver、preconditioner、MPI、M |
| 规模 | FE DoF、Full3D-equivalent DoF、active rows、matrix NNZ、factor NNZ、QEP/modal rows |
| 总量 | R00、Rtotal、Ttotal、Aclosure、Avolume、energy closure、full explicit residual |
| 逐级 | 12 个 significant R/T powers；有记录时写 12 个 complex amplitudes |
| 资源 | build、symbolic、numeric factorization、backsolve、postprocess、total、RSS/PSS/cgroup、swap |
| 结论 | 实际未通过值、参考/限值、直观原因、success/controlled_negative/failed/incomplete/not_run |

### 2.4 逐级衍射数据规则

对具备完整衍射谱的模型，至少登记：

```text
R(0,0), R(-1,0), R(-2,0), R(-4,0), R(-5,0), R(-7,0)
T(0,0), T(-1,0), T(-2,0), T(-4,0), T(-5,0), T(-7,0)
```

有复振幅时登记对应 `r(m,0)`、`t(m,0)`。历史模型只保存总量或零级时，必须写“历史未记录”或“该模型只启用零级”，不能填 0，也不能由功率反推复振幅。

### 2.5 负结果必须写实际值

禁止只写：

```text
10/12
failed
controlled negative
```

必须写出具体失败对象，例如：

```text
T(-4,0) power = ...，reference band = ...
r(-5,0) = ...，relative error = ...
terminal true residual = ...，limit = ...
peak memory = ...，hard cap = ...
```

并用通俗语言解释：是整体场错误、弱衍射级相位误差、线性求解不收敛、exact sequence 破坏、内存 Gate，还是能力尚未实现。

### 2.6 建议的维护实现

允许新增一个轻量、只读的 registry 生成/校验工具，从已跟踪的 CSV/JSON/summary 中抽取字段并检查：

- 章节与 Task 编号连续；
- 表头与列数一致；
- evidence path 存在；
- `not_run` 不含伪造数值；
- 逐级缺失值明确标记；
- 状态与原始 record 一致。

该工具不得重新实现求解器，也不得修改原始 records。

---

## 3. M1：建立一个稳定、单一的用户选择端口

原始完整矩阵直接法和 assembly-time 静态凝聚直接法都值得保留，但不能让普通用户通过多个互相冲突的布尔开关猜测组合。

合并前必须形成一个公开、稳定、可校验的端口，例如：

```python
stage4_full3d_assembly_backend = "standard_full"
# 可选：
# "standard_full"
# "assembly_time_static_condensed"
```

具体名称可由 Codex 根据现有配置风格确定，但必须满足：

1. `standard_full` 是 ordinary default，保持 master 现有行为；
2. `assembly_time_static_condensed` 是显式 opt-in；
3. 不允许同时开启旧的多个 condensation 布尔量形成歧义；
4. 旧研究布尔量若为历史 records 所需，可以保留为内部兼容层，但必须 fail closed，并由单一公开端口统一解析；
5. 用户在日志、record 和 summary 中能直接看到实际使用的 assembly backend；
6. original full 与 static-condensed 两条路径必须拥有同一物理配置入口、同一 official 后处理和可比较的 provenance。

### 3.1 静态凝聚的当前资格范围

合并到 master 时必须在文档和运行时错误中明确：当前已资格化的是：

```text
complex128
H(curl) Nédélec
first-order axis-aligned affine hexahedral geometry
explicit material tag for every owned cell
fixed rectangular target
assembly-time cell-interior condensation
Floquet slave elimination before global insertion
sparse auxiliary DtN
full-field recovery + full explicit residual
```

当前不允许静默外推到：

```text
curved/distorted hexahedra
runtime coefficients/constants not covered by the compiled-kernel contract
tetrahedra
mixed cell meshes
irregular geometry
production selective trace
```

不满足时必须明确拒绝并提示用户改用 `standard_full`，不能自动降级后仍把 record 标成 static-condensed。

---

# PART II：选择性合并清单

## 4. M2：允许进入 master 的 production/core 组

以下是**候选依赖组**，不是允许整体复制目录。Codex 必须根据导入关系、测试和现有 master 差异生成精确文件级 allowlist。

### 4.1 原始完整矩阵直接法

必须完整保留 master 已有 standard full assembly/direct 路径，并增加回归测试证明：

```text
不设置新端口时，矩阵 rows/NNZ、R/T/A、残差和默认 solver 不变。
```

不得为了接入静态凝聚而把原始路径改写成包装后的隐式凝聚。

### 4.2 高阶 p5/p6 与 Floquet 基础能力

值得进入 master 的是通用高阶能力，而不是某个 Task 的参数扫描：

- p5/p6 Nédélec 空间可构造、可组装、可求解；
- 高阶 edge/face orientation 与 Basix entity transform；
- 高阶双 Floquet trace 配对、相位和 MPI identity；
- p4/p5/p6 same-mesh 离散与后处理兼容；
- 对应 serial/MPI 测试。

候选文件依赖组包括：

```text
src/constraints/floquet_3d.py
src/constraints/floquet_3d_high_order.py
src/constraints/high_order_floquet_trace.py
src/common/config_3d.py
src/common/modes_3d.py
以及必要的 geometry/solver 调用链与 tests
```

其中 Task 专用 tolerance、目标几何参数和 benchmark 决策不得进入普通 API 默认。

### 4.3 静态凝聚直接法核心

以下能力值得作为 opt-in direct backend 进入 master：

```text
src/solvers/hcurl_cell_static_condensation.py
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/hcurl_affine_isotropic_tensor.py
必要的 common_3d_case_flow/common_3d_solve/common_3d_utils 接线
必要的 dtn_port_3d / surface-vector cache 接线
必要的 Stage4 solver/config 接线
```

必须同时迁移：

- local block partition 与 Schur 正确性测试；
- orientation、Floquet、DtN、full recovery、true residual 测试；
- original-vs-condensed 同物理对照；
- MPI identity；
- unsupported-geometry fail-closed；
- cache invalidation 与 ordinary-default 测试。

### 4.4 setup/cache 与资源遥测

以下工程能力可合并，但保持显式 opt-in：

- tensor/class dedup；
- exact PETSc preallocation；
- bounded bulk insertion；
- checksum/SHA-bound cold/warm cache；
- solver/factor 生命周期释放；
- RSS/PSS/USS、factor inventory 和 phase timing；
- cache identity/invalidation tests。

不得把 research cache 路径改成 ordinary default。不同 geometry/material/wavelength/degree/orientation/source identity 必须失效重建。

### 4.5 四面体与 DWR 的可复用研究基础设施

用户要求保留 Task035 中已经开发的四面体和 p5/p6 能力。本 Review 接受以下内容以 **research-grade opt-in infrastructure** 身份进入 master：

- periodic tetra mesh audit/refinement；
- periodic closure、deterministic marking 与 MPI identity；
-真实 discrete adjoint/DWR 基础；
- uniform tetra controls；
- same-origin h-vs-p 对照基础；
- p5/p6 tetra/高阶空间可运行能力；
- 对应 fixtures、tests 和少量权威 records。

候选依赖组包括：

```text
src/geometry/tetra_mesh_audit.py
src/adaptivity/periodic_tetra_refinement.py
src/adaptivity/dtn_goal_adjoint.py
src/adaptivity/goal_weighted_two_level.py
src/adaptivity/target_uniform_tetra_control.py
src/adaptivity/target_dwr_adaptive_cycles.py
必要的 target/common helpers 与 tests
```

合并身份必须保持：

```text
research-grade
explicit opt-in
not production automatic hp
not ordinary default
```

`src/adaptivity/__init__.py` 不应一次性导出全部研究模块；只导出已经稳定、文档化、测试闭合的最小 API。

---

## 5. M2：允许进入 master 的 docs/benchmark/evidence 组

### 5.1 文档治理和总账

应合并：

```text
AGENTS.md 完整恢复后的版本
docs/AGENTS.md
docs/development_model_registry.md
docs/COMSOL_direct_solver_report.md
docs/README.md / capability_matrix.md / development_progress.md 的必要更新
Task035 与 Task035b 的 task/review/response/outcomes 文档
```

### 5.2 精简 benchmark case

Case094/095 可作为可复现研究基准进入 master，但不得把全部中间 records 和重复失败历史原样搬入。

Case094 最低保留：

- README/config/expected/test command；
- periodic tetra 与 DWR 最终权威记录；
- uniform control；
- h-vs-p 或 hp budget 的最终代表记录；
- compact failure/negative summary；
- 对应 checker/tests。

Case095 最低保留：

- README/config/test command；
- p4/p5/p6 same-code reference；
- `significant_channel_reference_v1`；
- assembly-time condensation authority；
- fixed h15、directional-z h14/h13；
- cold/warm setup authority；
- MPI1/2/4/8 direct resource authority；
- 三条 condensed iterative negative 的聚合 authority；
- selective-trace capability boundary；
- `all_candidates.csv/json` 与 compact outcomes；
- 对应 checker/tests。

中间失败 attempt 应由 compact record 或 outcome 表保留结论；大型重复 JSON、raw logs、field、matrix、factor、timeline 和 ignored artifact 不进入 master。

---

## 6. 明确不得提升到 master production 的内容

### 6.1 selective p6 trace 当前不得作为正式求解能力合并

以下能力仍是 fixture/correctness 或架构未闭环：

- actual enriched residual-weighted channel DWR 不存在；
- actual selected orbit set 不存在；
- formal h14 runner/PDE/candidate 数为 0；
- standard full-p6 storage 与 generalized recovery 尚未形成正式生产闭环；
- matrix-free action 无 production DtN/preconditioner/KSP。

因此以下模块及其直接依赖默认留在研究分支，除非它们被证明是静态凝聚 core 的必要、独立可测小组件：

```text
selective_p6_trace_*
physical_channel_dwr_trace_selection.py
physical_missing_p6_action_only_complement.py
missing_p6_trace_sensitivity.py
formal_h14_live_capture_bridge.py
selective_p6_trace_matrix_free.py
```

可以合并文档、capability boundary 和 compact negative evidence，但不能暴露为普通用户可选 solver。

### 6.2 regionwise p 和 inverse trace/interior 失败空间不得合并为能力

已知不满足 local exact sequence 的 `p5-trace + p4-interior`、inverse p6-trace/p5-or-p4-interior 路线不得进入生产入口。结构审计工具可保留，但失败空间构造器不得作为合法 candidate API。

### 6.3 condensed iterative profiles 不得成为公共 solver profile

Task035b 的：

```text
GMRES + Jacobi
FGMRES + ASM/ILU
FGMRES + z-slab ILU + DtN coarse
```

均在 200 步内几乎不收敛。`condensed_iterative_profiles.py`、physical-slab/harmonic PC 若仅服务这些失败 profile，应留在研究分支；可以合并其负结果文档和通用 residual-history/failure-semantics helper，但不得让用户误以为它们是可用迭代求解器。

### 6.4 task-numbered research runners 与重复 records

仅为一次参数扫描服务的 runner、诊断脚本和重复 records 不进入 production/core。若某 runner 已成为通用、参数化、由多个 case 使用的工具，可在 manifest 中单独申请合并，并证明不包含 Task-specific physics hardcode。

### 6.5 不规则几何、混合网格和 tetra static condensation

这些能力没有在 Task035b 中完成，保持 `not_run/incomplete`。不得因为 periodic tetra 和 hexa static condensation 分别存在，就宣称 tetra/hexa mixed static condensation 已可用。

---

# PART III：选择性合并执行流程

## 7. M3：生成精确 manifest

Codex 必须新增：

```text
docs/task035b_high_order_local_hp_resource_envelope/outcomes/selective_merge_manifest_v1.csv
docs/task035b_high_order_local_hp_resource_envelope/outcomes/selective_merge_manifest_v1.md
```

每个文件必须属于以下之一：

```text
production_core
research_api_opt_in
reusable_benchmark
compact_evidence
project_docs
do_not_merge
```

每行至少写：

```text
path
dependency_group
public_behavior_change
ordinary_default_change
required_tests
fresh_PDE_evidence
merge_order
reason
```

manifest 必须从 `master@5002636852ffb67b4711443da70eb536c303e34e` 与当前分支实际 diff 生成，不能只复制本 Review 的候选路径。

## 8. M4：从干净 master 做选择性整合

禁止：

```text
git merge codex/20260723-task35b-high-order-local-hp-resource-envelope
```

建议流程：

1. 确认当前 research branch clean，并完成 registry 与 manifest；
2. 从最新干净 `origin/master` 创建临时 selective-integration branch；
3. 按 manifest 依赖组迁移文件；
4. 先迁移 core，再迁移 tests/benchmark/docs；
5. 不带入 do-not-merge、raw artifact 和重复历史；
6. 运行全部 Gate；
7. 形成一个可审阅的 selective integration commit/merge commit；
8. 合并到 master；
9. 报告精确 master SHA、合并方式、文件数、测试结果和 clean worktree。

### 8.1 必须通过的测试

最低包括：

- original full matrix direct serial/MPI regression；
- new public assembly-backend port 与 conflict/fail-closed tests；
- static-condensed direct serial/MPI2/MPI8；
- p5/p6 high-order Floquet/orientation/MPI；
- periodic tetra/refinement/DWR fixtures 与代表 PDE record tests；
- Task032/033 Hybrid regression，确认未被新 backend 接线破坏；
- Case094/095 checker；
- registry structure/evidence checker；
- Task034/035/035b targeted regression；
- full repository pytest；
- scoped/full Ruff、compileall、JSON parse、diff-check。

### 8.2 merge 授权

只要 M0–M4 全部通过，Codex 已获得本 Review 与用户本轮指令的明确授权，可以执行选择性 merge，无需再等待中间 Review。

若任何 production anchor 失败，则不得只合并 docs 后继续假称数值能力已进入 master；应停止，保留 manifest 和失败证据并报告。

---

# PART IV：合并后新分支与续研

## 9. 创建新分支

选择性 merge 完成并确认 master clean 后，Codex 创建：

```text
codex/20260726-task35b-high-order-local-hp-resource-envelope
```

基线必须是新合并后的精确 master SHA。旧 `codex/20260723-...` 分支保留为 Task035/035b 完整研究档案，不继续在其上叠加 Hybrid 新实现。

新分支继承本 Review，但不得把旧分支中的 do-not-merge 研究原型重新整体搬入。

---

# PART V：静态凝聚与 Hybrid 结合

## 10. H0：先明确算法边界

Hybrid 的中间模态区保持 Task032/033 的二维 QEP、双向传播和 matching-trace 架构。静态凝聚只作用于上下两个局部三维 FE 端区：

```text
local 3D cell matrix
→ eliminate cell-interior DoFs
→ retain exterior/interface trace DoFs
→ couple retained interface trace to modal amplitudes
→ assemble Hybrid augmented or modal-Schur system
```

不得：

- 把 modal amplitudes 当作 cell-interior 一起错误消去；
- 消去 Hybrid 接口必须保留的 tangential trace；
- 对已经形成的 Hybrid global matrix 再做一次无物理意义的重复凝聚；
- 改变 QEP、matching trace、M 定义或 external DtN 身份后仍称同一基线。

## 11. H1：典型案例矩阵

采用逐级 Gate，避免直接启动最重模型。

### 11.1 Case H1-A：p2/h5

目的：低成本验证静态凝聚 local-FE 与原始 Hybrid 的代数/物理闭合。

对照：

```text
Full3D standard full
Full3D static-condensed
Hybrid standard local-FE, M160
Hybrid static-condensed local-FE, M160
```

### 11.2 Case H1-B：p2/h3

只有 H1-A 全部通过后运行。用于验证规模增长时 rows、NNZ、factor、内存和时间的真实收益。

### 11.3 Case H1-C：高阶已成功点

优先选择 Task033 已有同阶闭合的高阶点，例如 `p3/h7.5` 或经现有记录确认的等价成功点。比较原始 Hybrid 与 static-condensed Hybrid，验证高阶 interior-mode 消元是否比 p2 更有收益。

### 11.4 Case H1-D：Task035b h13 seed

模型：

```text
fixed p5 trace + p6 cell interior
directional-z h13
Full3D-equivalent DoF = 89,740
```

该点是 Hybrid 自适应的种子，不是绝对精度真值。先完成同一离散上的 static-condensed Full3D ↔ Hybrid 闭合，再进入自适应。

## 12. H2：每个案例的正式输出

每个案例必须同时报告：

```text
full FE / Full3D-equivalent DoF
local FE DoF per side
trace rows after condensation
total Hybrid rows
matrix NNZ / factor NNZ / fill
QEP DoF / interface DoF / M / 2M
R00 / Rtotal / Ttotal / Aclosure / Avolume
12 significant powers
12 significant complex amplitudes（存在时）
full explicit residual
interface E/H errors
selected planes/volume field errors
cold/warm build
MUMPS symbolic/numeric/backsolve
postprocess / total
RSS/PSS/cgroup / swap
```

## 13. H3：正确性 Gate

### 13.1 静态凝聚等价 Gate

对相同 Full3D 离散：

```text
standard full vs static-condensed
```

必须通过：

- full explicit residual；
- R/T/A；
- 逐级功率和复振幅；
- selected fields；
- MPI identity；
- recovered interior equation residual。

### 13.2 Hybrid 同离散 Gate

对相同 p/h/M：

```text
static-condensed Full3D vs static-condensed Hybrid
```

必须通过：

- R/T/A；
- 12 significant powers/amplitudes；
- interface E/H；
- selected field planes；
- M120→M160 convergence，必要时 M240；
- augmented/minimal path identity（若两条路径都保留）。

任何资源下降都不能覆盖物理 Gate 失败。

---

# PART VI：以 h13 为种子的 Hybrid h/p 自适应

## 14. A0：h13 的正确身份

当前 h13：

```text
89,740 Full3D-equivalent DoF
20,120 active rows
10/12 significant powers
10/12 significant complex amplitudes
```

它是当前预算内最强点，但仍在：

```text
T(-4,0) power
R(-4,0) power
r(-4,0)
r(-5,0)
```

上失败。因此：

- 可以作为 Hybrid 工程闭合 seed；
- 不能作为绝对物理精度 reference；
- Hybrid 只匹配 h13 不能称“保证了最终精度”。

## 15. A1：两层精度 Gate

### Gate A：无新增 Hybrid/自适应误差

每个 Hybrid candidate 先与同一 seed/discrete Full3D 比较，证明 Hybrid、M 截断和静态凝聚没有增加不可接受误差。

### Gate B：绝对参考精度

最终成功 candidate 还必须与：

```text
significant_channel_reference_v1
+
FEniCS global p6/h10 same-code reference
+
COMSOL high-order trend center（仅适用总量）
```

比较，并通过完整 12/12 powers、12/12 complex amplitudes、R/T/A、fields 和 residual。

若 candidate 只通过 Gate A、未通过 Gate B，状态只能是：

```text
Hybrid engineering closure on an under-resolved seed
```

不能提升为 adaptive accuracy success。

## 16. A2：Hybrid 中允许探索的压缩方向

按以下顺序推进：

1. **local 3D 端区静态凝聚**：先消去 cell interiors；
2. **local 3D 高度与 z 分辨率**：只减少对接口和显著通道不敏感的端区层；
3. **exact-sequence-compatible trace/interior p 分配**：只能使用已通过结构审计的空间；
4. **目标量驱动的局部 h/p**：以接口 E/H、12 通道和 total R/T/A 的 adjoint/DWR 为目标；
5. **M 自适应**：M80/M120/M160，必要时 M240，并按通道/接口误差停止；
6. **生命周期和缓存**：local Schur、QEP、trace projection、symbolic structure 合法复用。

当前 selective p6 trace 尚未形成正式 PDE，因此不能作为第一批 Hybrid adaptive 的必需前置。只有 actual channel DWR、periodic orbit、active numbering 和正式 candidate 完成后，才能重新加入。

## 17. A3：资源目标

Hybrid 自适应不能只报告 Full3D-equivalent DoF。正式优化目标按优先级为：

```text
1. 通过完整精度 Gate
2. 降低 local 3D FE DoF
3. 降低 condensed trace rows
4. 降低 total Hybrid rows
5. 降低 matrix/factor NNZ 与 fill
6. 降低 simultaneous peak memory
7. 降低 cold/warm setup 与 total time
```

规划目标继续保留：

```text
Full3D-equivalent hard cap <= 90,000
preferred robust 65,000–75,000
stretch <= 60,000 only after all independent gates pass
```

但 Hybrid 的最终工程结论必须以实际 local FE、total rows、M、峰值内存和时间为主，不能机械地把 Full3D-equivalent DoF 乘一个固定比例。

## 18. A4：停止规则

以下情况保存负结果后切换方向，不进行盲扫：

- 两个相反方向的同成本候选均退化；
- 只改善总 R/T 但破坏弱通道；
- DoF 下降但 rows/NNZ/factor/peak 不降；
- M 增大仍不能消除接口误差；
- exact-sequence 或 periodic closure 失败；
- simple iterative profile 重复已知谱缺陷；
- 预测超出内存安全 Gate。

---

# PART VII：交付与连续执行

## 19. 当前分支 closeout

在旧分支完成 M0–M4 后新增：

```text
docs/task035b_high_order_local_hp_resource_envelope/response_v4.md
```

至少报告：

- registry 回填范围与自动检查；
- exact selective merge manifest；
- public assembly backend 端口；
- 合并文件和排除文件；
- targeted/full tests；
- master merge SHA；
- clean worktree。

response_v4 可在 merge 后以最终 master SHA 回填；不得在 merge 前预写一个未知 SHA。

## 20. 新分支交付

新分支完成静态凝聚 Hybrid 与 adaptive Hybrid 批次后新增：

```text
docs/task035b_high_order_local_hp_resource_envelope/response_v5.md
```

至少报告：

1. p2/h5、p2/h3、高阶典型点的 standard/static Full3D/Hybrid 对照；
2. h13 seed 的 Full3D–Hybrid 闭合；
3. M 漏斗与 interface/field/12-channel 结果；
4. adaptive candidates 的实际值，而非只写通过数；
5. local FE、trace rows、total rows、NNZ、factor、memory、setup、solve；
6. Gate A 与 Gate B 的独立结论；
7. 所有负结果和 not-run 原因；
8. registry 同步更新；
9. full repository regression 与工作树状态。

## 21. 连续执行权限

Codex 可按以下顺序连续执行，不逐小阶段等待 Review：

```text
registry + public port + manifest
→ selective integration tests
→ merge master
→ create 20260726 branch
→ static-condensed Hybrid H1/H2/H3
→ h13-seeded Hybrid adaptivity A1–A4
→ response_v5
```

只有以下情况停止请求用户或新 Review：

- 需要系统级安装、凭据或 ABI 变更；
- master 在整合期间出现冲突性更新；
- 原始 full 默认必须改变；
- 要把当前禁止合并的 selective-trace/iterative profile 提升为公共能力；
- 安全内存 Gate 或数据身份异常；
- 准备再次 merge master。

本 Review 不授权新分支完成后的第二次 master merge；该批次仍需新的最终 Review。
