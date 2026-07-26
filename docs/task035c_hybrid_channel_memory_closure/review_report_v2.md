# Task035c Review V2：选择性合并授权与 Task035d exact-sequence h/p 任务移交

## 1. 审阅决定

```text
review_status = TASK035C_SELECTIVE_MERGE_AUTHORIZED_AND_TASK035D_STAGED
reviewed_branch = codex/20260726-task35c-hybrid-channel-memory-closure
reviewed_head_before_this_review = f4941ba1f6c36eac399f1e9215d0a96e67138dc8
master_base = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
Task035c_completion = accepted_with_qualified_scope
Task035c_physics_closure = pass
Task035c_memory_gate_15pct = pass
Task035c_memory_gate_25pct = pass
user_50pct_memory_target = open_engineering_gap
modal_coupling_time_hard_gate = cancelled_by_user / report_only
PSS_USS_backfill_without_raw_samples = forbidden
Task035c_selective_merge = authorized_after_M0_to_M4
Task035d_branch_creation_by_ChatGPT = forbidden_by_user
Task035d_branch_creation_by_Codex_after_merge = authorized
Task035d_branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
Task035d_base = exact post-Task035c master SHA
ordinary_default = standard_full
ordinary_default_changed = false
```

Task035c 已经回答并修复了两个关键问题：

1. Full3D 与 Hybrid 弱衍射级不一致的根因，是两者原先使用了不同的轴向离散传播相位与端点 traction；
2. static Hybrid 在 `p6/h10, M120, MPI8` 下已经把峰值从 `11.077 GiB` 降到 `7.544 GiB`，并保持 12/12 功率和 12/12 复振幅闭合。

因此 Task035c 可以结束研究并进入 master 整合。用户同时决定：**现在不由 ChatGPT 创建 Task035d 分支**。应先由 Codex 完成 Task035c 的收口、选择性合并和 master 验证，再从新的 master 创建 Task035d 分支并开始工作。

---

# 2. 合并前必须完成的收口

## 2.1 适用边界必须写到用户真正能看到的位置

Task035c 当前正式资格范围是：

```text
fixed rectangular block grating
structured tensor-product mesh
axis-aligned first-order affine hexahedra
uniform z segmentation in the modal middle region
one well-defined axial h for the scalar CG(p) chain
supported axial degree p1–p6
complex128
Floquet periodicity
sparse auxiliary DtN
direct standard/static Full3D and Hybrid
```

尚未资格化：

```text
nonuniform z spacing
locally refined or hanging-node hexa mesh
curved or distorted hexahedra
high-order curved geometry mapping
tetrahedral static condensation
hexa/tetra/prism/pyramid mixed meshes
sloped sidewalls, rounded corners, roughness or defects
arbitrary irregular geometry
production automatic hp adaptivity
```

Codex 在合并前必须把这些限制同步写入：

- `docs/task035c_hybrid_channel_memory_closure/README.md`；
- `task.md` 的最终能力边界；
- `outcomes/summary.md`；
- `response_v1.md`；
- Case096 README；
- `docs/development_model_registry.md`；
- 新传播/traction 配置字段的注释、运行日志和 fail-closed 错误。

不能只在 Review 中写一次。用户从配置入口选择 `full3d_uniform_cg` 或 `scalar_cg_discrete_derivative` 时，应立即知道它要求规则、均匀的轴向有限元链；不支持的模型必须明确拒绝，不能静默回落后仍伪报该后端。

## 2.2 PSS/USS 的处理

先检查本机未跟踪的 watchdog/timeline artifact：

- 若原始运行已经采集 `/proc/<pid>/smaps_rollup`、PSS 或 USS，可只重新生成 compact resource ledger，不需要重新求解 PDE；
- 若原始运行仅有 RSS/process-tree 记录，不得从 RSS 推算或伪造 PSS/USS。

若没有原始PSS/USS，文档统一写：

```text
PSS/USS = historical Task035c campaign did not record qualified values
formal Task035c relative-memory authority = simultaneous process-tree/live-worker RSS
```

不要求为了这个诊断字段重跑全部六条 `p6/h10` 路径。以后所有新的重型模型必须从启动时同时记录 RSS、PSS、USS、cgroup和swap。

## 2.3 模型总账

在合并前更新：

```text
docs/development_model_registry.md
```

至少加入完整 Task035c 条目，记录：

- p2/h5 原始错误、phase-only负结果和phase+traction修复；
- p6/h10六路径的rows、NNZ、factor、峰值、时间、R/T/A；
- 12个显著功率和12个物理边界面复振幅；
- M120为何被选择、M160为何停止；
- MPI1数值负结果和MPI2资源authority负结果；
- 当前均匀网格、规则仿射六面体的适用边界；
- 50%额外内存目标未达到；
- PSS/USS未采集时的证据边界。

---

# 3. Task035c 中值得合并到 master 的内容

以下是依赖组，不是允许无检查地整体复制目录。Codex 必须根据 `master...Task035c` 的真实diff生成精确manifest。

## 3.1 Production/core：Hybrid离散闭合

值得进入 master，保持显式opt-in：

```text
src/modes/stable_propagation.py
src/coupling/hybrid_internal_modes.py
src/postprocessing/hybrid_field_reconstruction.py
src/constraints/cross_section_floquet.py
```

核心能力包括：

- `full3d_uniform_cg` 的scalar-CG离散Bloch传播；
- `scalar_cg_discrete_derivative` 的离散端点traction；
- p1–p6横截面Floquet entity-DoF和orientation支持；
- Full3D与Hybrid统一的physical-boundary-plane复振幅；
- 非均匀轴向网格、非支持阶次和非资格化几何的fail-closed检查。

普通Hybrid默认不得被无提示改成该模型；应保留明确的配置/provenance，使用户知道是在追求“与同一Full3D有限元离散完全一致”，而不是连续解析传播。

## 3.2 Production/core：Static Hybrid

值得进入 master，保持显式opt-in：

```text
src/solvers/hybrid_local_static_condensation.py
src/solvers/hybrid_static_field_recovery.py
src/solvers/hybrid_fem_modal_augmented_direct.py
src/solvers/hybrid_fem_modal_schur_direct.py
src/solvers/hybrid_local_dtn.py
src/solvers/hcurl_assembly_time_condensation.py
```

必须保留：

- 只消去local 3D FEM的cell-interior未知量；
- Hybrid接口切向trace、external DtN和modal amplitudes不被错误消去；
- Floquet slave在全局插入前物理消元；
- eliminated interior与slave roundoff分开审计；
- 完整场流式恢复；
- full-operator与eliminated-equation residual；
- `standard_full`仍为ordinary default。

## 3.3 Reusable benchmark、watchdog与checker

下列内容可作为可复现benchmark基础进入master，但不得成为普通求解器默认：

```text
benchmarks/cases/096_hybrid_channel_memory_closure/**
benchmarks/task035c_channel_resource_checker.py
benchmarks/task035c_p6_h10_gates.py
benchmarks/run_task032_phase6_augmented.py
benchmarks/run_task033_full3d_watchdog.py
benchmarks/run_task033_memory_watchdog.py
benchmarks/task034_numerical_blob_checker.py
benchmarks/task034_workstation_resource_gates.py
```

Case096应保留：

- p2/h5根因compact authority；
- p6/h10六路径authority；
- rank study的受控负结果；
- dependency failures；
- SHA-bound generator和hermetic contract。

一次性raw stdout、timeline、field、matrix、factor和ignored artifacts不进入Git。

## 3.4 Tests

与上述能力直接对应的serial/MPI测试应合并，至少包括：

```text
src/test/test_34_task032_stable_propagation.py
src/test/test_38_task032_hybrid_internal_modes.py
src/test/test_40_task032_hybrid_field_reconstruction.py
src/test/test_48_task033_cross_section_exact_constraints.py
src/test/test_115_task035b_assembly_time_condensation.py
src/test/test_179_task035b_hybrid_static_condensation.py
src/test/test_180_task035b_hybrid_h1a_record.py
src/test/test_181_task035c_p6_h10_runner_gates.py
src/test/test_182_task035c_channel_resource_checker.py
src/test/test_case096_compact_evidence_contract.py
```

以及实际依赖到的watchdog、documentation和hardening测试。

## 3.5 文档与compact evidence

应合并：

```text
docs/task035b_high_order_local_hp_resource_envelope/
    H0/H1-A的最终response、review和compact outcomes

docs/task035c_hybrid_channel_memory_closure/
    README、task、response、reviews和全部compact outcomes

docs/development_model_registry.md
docs/development_progress.md
docs/README.md
benchmarks/cases/095/.../hybrid_static_condensation_h1a_mpi8_v1.json
```

本Review以及Task035d的README/task也应随整合进入master，使新分支从一开始就具有明确任务入口。

---

# 4. 明确不得合并或不得提升为production的内容

以下内容不得因Task035c成功而被扩大解释：

- 本机ignored重型artifacts、缓存、timeline、stdout、field、matrix和factor；
- 从RSS推算出的PSS/USS；
- MPI1的 `1.7517 GiB` Hybrid记录作为正式最低内存authority；
- MPI2的 `3.1418 GiB` 记录作为正式authority；
- 非均匀z网格的scalar-CG传播/traction；
- 曲面、扭曲六面体、四面体或混合网格static Hybrid；
- h13 adaptive Hybrid；
- production selective trace；
- 新的condensed iterative profile；
- 0.7 nm资源外推；
- 把约31.9%的额外Hybrid内存下降写成50%或理论下限。

失败记录和受控负结果应以compact evidence进入master，但不能暴露为成功求解profile。

---

# 5. 合并执行流程

## M0：完成文档、PSS/USS和局限性收口

完成第2章要求，且不无理由重跑重型PDE。

## M1：生成精确manifest

新增：

```text
docs/task035c_hybrid_channel_memory_closure/outcomes/selective_merge_manifest_v1.md
docs/task035c_hybrid_channel_memory_closure/outcomes/selective_merge_manifest_v1.csv
```

每个差异文件分类为：

```text
production_core
research_opt_in
reusable_benchmark
compact_evidence
project_docs
do_not_merge
```

每行至少记录：path、依赖组、默认行为变化、测试、数值证据、迁移顺序和理由。

## M2：从干净master建立临时integration branch

不得在旧Task035c分支上直接移动master。应从最新：

```text
origin/master
```

建立临时integration分支，按manifest依赖组迁移。若manifest证明Task035c全部tracked差异都属于允许组，可以使用清晰的merge/cherry-pick策略；若包含任何`do_not_merge`，必须文件级迁移，不能整体merge。

## M3：数值身份规则

Task035c正式PDE绑定：

```text
244b62e1fb4f299a468363cf90a2dd548dc34ff6
```

若整合过程保持所有numerical-kernel blob逐字一致，只发生文档、manifest或证据路径变化，则不得无理由重跑六条p6/h10重型PDE。

若冲突解决或重构改变以下任一numerical kernel，则必须按numerical-blob checker判定重新运行必要anchor：

- discrete propagation/traction；
- cross-section Floquet；
- Hybrid modal coupling；
- static condensation/recovery；
- DtN或逐通道后处理；
- solver assembly路径。

## M4：合并前测试

最低要求：

- Task035c focused suite；
- static Hybrid serial/MPI2/MPI8组件测试；
- p1–p6 cross-section Floquet；
- Case095/096 compact generator与hermetic checker；
- Task032/033 Hybrid回归；
- original `standard_full` ordinary-default回归；
- registry/documentation contract；
- full repository pytest；
- Ruff、compileall、tracked JSON parse、`git diff --check`；
- clean worktree。

M0–M4全部通过后，Codex获得用户与本Review授权，可把Task035c选择性整合到master，不需要再次等待中间审阅。必须报告新master SHA、整合方式、迁移文件数、测试结果和是否触发PDE重跑。

---

# 6. 合并后创建 Task035d 分支

Task035c合并并确认master干净后，由Codex创建：

```text
codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
```

基线必须是Task035c整合后的精确master SHA。

旧Task035c分支保留为完整研究档案并冻结；不得继续在旧分支叠加h/p实现。

新分支创建后，完整阅读：

```text
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/README.md
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/task.md
```

随后连续执行Task035d。Task035d中途的commit/push不是等待点；只有遇到源码身份、exact-sequence、MPI、数值或资源硬blocker时才停止报告。

---

## 7. 最终决定

```text
Task035c = ACCEPTED_WITH_QUALIFIED_SCOPE
Task035c selective merge = AUTHORIZED_AFTER_M0_TO_M4
Task035c whole-branch blind merge = NOT_AUTHORIZED
Task035d docs = STAGED_ON_TASK035C_BRANCH
Task035d branch = CREATE_BY_CODEX_AFTER_MASTER_MERGE
Task035d priority = TRUE_GOAL_ORIENTED_EXACT_SEQUENCE_LOCAL_HP
iterative solver = AFTER_HP_SPACE_FREEZES
matrix-free/streaming low-memory = AFTER_HP_AND_ITERATIVE
```