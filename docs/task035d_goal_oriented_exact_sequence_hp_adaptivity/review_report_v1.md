# Task035d 最终审阅报告 V1：部分验收、选择性合并与 Task035e 移交

## 0. 审阅身份

```text
task = Task035d
review = review_report_v1
execution_branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
reviewed_branch_head = 706aeef4501cee586e2c83b76fd578eb202d7cdc
branch_base = 9c2160d41382026352908d692ad479dc4508424d
review_decision = ACCEPT_PARTIAL_WITH_CONTROLLED_NEGATIVES
merge_policy = selective_merge_only
ordinary_default = unchanged
next_task = Task035e
```

本审阅接受 Task035d 的结构能力、数值基础设施、资源证据和受控负结果，但**不接受“完整 h/p 自适应已经成功”或“已经形成生产级自动 h/p 求解器”的表述**。

Task035d 的正式分类保持：

```text
PARTIAL_WITH_CONTROLLED_NEGATIVES
```

原因很明确：

- true local-p 已实现；
- true local-h 已实现；
- H(curl) exact sequence、hanging trace、双 Floquet、静态凝聚、完整场恢复和 MPI1/2/8 identity 已实现；
- rows、matrix NNZ、factor NNZ 和峰值内存都获得了真实压缩；
- 但没有任何正式候选达到冻结的 `12/12 powers + 12/12 complex amplitudes`；
- 自动 cycle 1–4 没有完成；
- Full3D hp Gate 未通过，因此 Hybrid Phase F 没有运行；
- 当前不存在 production hp candidate。

---

# 1. Task035d 已经完成且值得保留的成果

## 1.1 true local-p

Task035d 已经证明：局部 p 不是“先组装完整 p6 矩阵，再把部分系数设成零”，而是从编号阶段开始只建立 active edge/face/cell-interior 模式。

因此：

- inactive p6 mode 不获得 global row；
- inactive mode 不进入 matrix NNZ；
- inactive mode 不进入 MUMPS factor；
- shared entity、orientation、periodic orbit 和 exact-sequence 约束有正式测试；
- variable-p field 可以恢复到完整物理场容器；
- ordinary default 未改变。

这是可复用的通用数值能力。

## 1.2 true local-h

Task035d 已经把六面体 local-h 从小型拓扑 fixture 推进到正式 MPI8 Maxwell PDE：

- dyadic 8-way local split；
- 2:1 balance；
- material-interface protection；
- x/y 周期镜像细化；
- coarse face 与四个 fine faces 的 H(curl) tangential restriction；
- p4/p5/p6 face restriction；
- D4 orientation；
- hanging + Floquet flattened graph；
- static condensation 后的 constrained Schur；
- PETSc owner-routed rows；
- MPI1/2/8 identity；
- full residual 与 field recovery。

这项能力解决了过去“规则六面体只能整体加层、不能真正局部细分”的主要结构 blocker。

## 1.3 DWR 与目标量审计基础

本任务完成了两类 actual residual-weighted adjoint：

1. same-trace nested-p DWR；
2. selective-p6-face DWR。

并且能够对：

```text
12 powers
12 amplitude real parts
12 amplitude imaginary parts
```

共 36 个实目标做 signed closure。

这些能力可以作为后续“无参考解自适应”的核心研究 API，但目前不应宣称已经完成自动选择器。

## 1.4 真实资源压缩

相对 p6/h10 Full3D static MPI8：

```text
rows = 51,272
matrix NNZ = 41,989,040
factor NNZ = 212,343,992
peak = 14.721756 GiB
```

Task035d 最小正式候选达到：

```text
active FE DoF = 76,205
rows = 18,470
matrix NNZ = 10,186,108
factor NNZ = 30,865,200
peak = 7.29866 GiB
```

资源压缩是真实的，不是通过后处理删除对象、改变采样口径或把 slave row 隐藏在统计之外得到的。

但该候选只有 `4/12 + 4/12`，因此只能称为资源正结果、精度负结果。

---

# 2. 必须在选择性合并前修正或补充的问题

## 2.1 明确当前最优工程候选仍是 Task035b h13

最终文档必须增加一段醒目的横向结论：

```text
Task035b fixed p5-trace/p6-interior h13
DoF = 89,740
rows = 20,120
peak = 6.411 GiB
powers/amplitudes = 10/12 + 10/12
```

而 Task035d 最强通道候选为：

```text
h15 top-air local-h
DoF = 82,925
rows = 18,470
peak = 7.50068 GiB
powers/amplitudes = 6/12 + 6/12
```

因此：

> Task035d 建立了更通用的 local-h/local-p 架构，但当前并没有在“精度 + 内存”上超过 h13。

不能只按 DoF 或 rows 更小，就写成 Task035d 已经产生更优工程模型。

## 2.2 修正内存基线口径

后续文档必须统一：

```text
p6/h10 Full3D static MPI8 peak = 14.721756 GiB
p6/h10 Hybrid static M120 MPI8 peak = 7.544262 GiB
p6/h10 Hybrid standard M120 MPI8 peak ≈ 11.0769 GiB
```

不得把约 11 GiB 写成 Full3D static 基线。

Task35e 的资源目标必须以同 MPI、同遥测、同生命周期政策下的 14.721756 GiB 和 7.544262 GiB 为正式基线。

## 2.3 自动 h/p 循环尚未完成

`response_v1.md`、`outcomes/summary.md`、Case097 README 和模型总账必须一致写明：

```text
automatic cycles 1–4 = not completed
```

实际完成的是一组受控、人工冻结的 discriminator：

- p-only T30；
- sidewall-z0 guard；
- top-air local-h；
- factorial bridge；
- ten-face selective trace；
- bounded single-root left-grating。

这些研究证明了组件能力与失败边界，但不能冒充完整自动循环。

## 2.4 当前 local-h 仍局限于 h15 single-root candidate space

最终文档必须解释：

- true local-h 技术本身已经支持非均匀叶单元；
- 但正式物理搜索只在 `h15 + global p5 trace + bounded single-root` 这一候选空间中进行；
- 没有完成多层、多区域、多个 refinement level 的真正自动网格；
- 当前停止只关闭该 lane，不等价于“所有 local-h 均无效”。

## 2.5 selective trace 的边界必须继续保持

十个 grating-top face 的 actual DWR `36/36` 闭合只证明：

> 对这十个已知 coarse/enriched endpoint，face contribution 的后验归因是正确的。

它没有证明：

- 十面选择由 DWR 因果产生；
- 其他 top-port face 无效；
- edge modes 无效；
- material-interface face 无效；
- whole top-port selective trace 已失败。

因此必须保持：

```text
frozen ten-face subset = closed_controlled_negative
whole top-port selective trace = incomplete_not_run_no_authorized_candidate
```

## 2.6 nested-p DWR 的结果应解释为“禁止盲目 p-down”

16 个 periodic p-down pair 在保守甚至放宽预算下均无 safe pair。该结果说明：

- 远端均匀空气单元也可能携带弱通道相位信息；
- “离光栅远”不是 p-down 的充分条件；
- cell-interior p-down 的全局 rows 收益可能为零，因为 trace 不变；
- 后续不能继续几何启发式 p-down 扫描。

但这不等价于“任何 local-p 都不可能成功”。它只否定当前 same-trace remote-interior lane。

## 2.7 时间字段需要重新审计命名

最终 left-grating 记录出现：

```text
base matrix assembly = 256.515 s
reported total build = 68.972 s
total elapsed = 297.114 s
```

这些计时显然不是同一互斥 wall-clock 分解。Codex 必须：

1. 在文档中说明每个计时是 wall time、累计 rank time、嵌套 timer 还是局部阶段时间；
2. 不把嵌套字段相加；
3. 对含义不清的旧字段重命名为 diagnostic；
4. Task35e 建立互斥 phase timeline：mesh/plan、local tensor、constraint/reduction、PETSc insertion、MUMPS symbolic、numeric、backsolve、recovery、postprocess。

## 2.8 模型总账必须与独立回填分支合并而不是覆盖

当前 Task035d 分支的 `docs/development_model_registry.md` 必须与：

```text
chatgpt/20260726-development-model-registry-backfill
```

中的 COMSOL、Task034 p2/p3/p4、Hybrid、M funnel、MPI identity 和 Markdown 修复做三方合并。

禁止用 Task035d 版本覆盖已经回填的历史总账。

最终总账必须同时保留：

- COMSOL p2–p6；
- FEniCS Task034 Full3D/Hybrid 收敛矩阵；
- Task035/035b/035c；
- Task035d 的全部正式正/负结果；
- Task35e 新任务入口。

## 2.9 文档中必须区分三种“成功”

请统一用下列口径：

```text
capability pass
    数学/软件结构可运行并通过组件测试

resource pass
    rows/NNZ/factor/peak 实测下降

accuracy pass
    冻结物理输出达到正式误差 Gate
```

Task035d 是：

```text
capability pass
resource pass
accuracy fail
```

不能只写“local-h success”而不说明它是 capability success、不是 production accuracy success。

---

# 3. Task035d 的科学结论

## 3.1 p6/h10 不是可以“轻微删改”的冗余空间

已有结果说明，p6/h10 虽然只有约 17 万 FE DoF，但弱衍射级对：

- 全局 trace；
- 分布式 cell-interior phase；
- 轴向分辨率；
- periodic orbit；

都可能敏感。

因此，从 p6/h10 直接做大范围 p-down，容易使所有弱通道同时退化。

## 3.2 单一局部细化无法替代全局传播相位分辨率

Task035b 的 h15→h14→h13 对弱通道有连续正信号，而 Task035d 的 h15 single-root local-h 最多达到 6/12+6/12。

这提示：

> 当前剩余误差并不只是一个局部奇异区，而包含沿传播路径积累的分布式相位误差。

下一任务应允许多层、多区域 local-h，而不是继续只在 h15 上移动一个 root。

## 3.3 未来自适应必须在“无参考解”条件下独立停止

Task035d 的 selector 仍然大量依赖历史 reference、已知 endpoint 或 posthoc attribution。

对于未来 0.7 nm，完整高阶 reference 不可获得，因此必须建立：

- 当前解残差；
- 目标伴随；
- local p-shadow；
- local h-shadow；
- algebraic/DtN/Hybrid error budgets；
- 不同初始网格的独立收敛；
- 最终隐藏 reference audit（仅用于本次13.5 nm验证算法，不参与选择）。

这正是 Task035e 的任务。

---

# 4. Task035d 选择性合并建议

禁止整体执行：

```bash
git merge codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
```

当前分支相对 master 有大量研究 runner、候选计划、失败记录和临时 selector。必须生成文件级 manifest，并按依赖组迁移。

## 4.1 建议合并：production/reusable numerical core

以下能力值得作为显式 opt-in 通用基础进入 master：

### variable-p / exact-sequence

```text
src/adaptivity/exact_sequence_variable_p.py
src/adaptivity/variable_p_degree_plan.py
src/adaptivity/variable_p_entity_map.py
src/adaptivity/variable_p_periodic_orbits.py
src/adaptivity/variable_p_transfer.py
src/solvers/hcurl_variable_p_local.py
src/solvers/hcurl_variable_p_assembly.py
src/solvers/hcurl_variable_p_reduction.py
```

### true local-h / hanging / periodic graph

```text
src/adaptivity/dyadic_hexa_refinement.py
src/adaptivity/dyadic_hexa_broken_mesh.py
src/adaptivity/hcurl_hanging_trace.py
src/adaptivity/hcurl_trace_constraint_graph.py
src/adaptivity/hcurl_broken_trace_graph.py
src/adaptivity/hcurl_broken_cell_trace.py
src/adaptivity/stage4_local_h.py
```

### 通用集成

```text
src/common/config_3d.py
src/geometry/mesh_builder_3d.py
src/runners/run_3d_cases.py
src/solvers/common_3d_case_flow.py
src/solvers/solve_maxwell_3d_stage_4b_block_grating.py
src/solvers/dtn_port_3d.py
```

这些改动必须满足：

- ordinary default 不变；
- unsupported geometry fail closed；
- 只支持已资格化 axis-aligned affine hexa；
- local-h、variable-p 都必须显式 opt-in；
- 不得暴露“production automatic hp”选项。

## 4.2 建议合并：research API，保持 explicit opt-in

```text
src/adaptivity/dtn_goal_adjoint.py
src/adaptivity/nested_p_dwr.py
src/adaptivity/variable_p_nested_dwr.py
src/adaptivity/selective_face_complement.py
src/adaptivity/selective_face_root_transfer.py
src/adaptivity/variable_p_selective_face_dwr.py
```

这些模块可以作为 Task35e 的研究基础，但必须标记：

```text
research_api = true
production_selector = false
```

## 4.3 建议合并：通用 bug fix

`src/solvers/hybrid_local_dtn.py` 中向 collective `_combine_owned_entries` 补传 `comm=comm` 的修复值得单独合并，并运行 Task032/033/035b Hybrid targeted regression。

该修复不能被写成 Task035c 历史重型 PDE 的重新资格化。

## 4.4 建议合并：测试

建议保留能够验证通用能力的测试：

- reference active-space；
- entity numbering；
- variable-p PETSc assembly；
- compiled kernel；
- reduction/recovery；
- dyadic local-h；
- hanging trace；
- periodic/hanging graph；
- MPI ownership；
- unit-channel adjoint；
- nested-p DWR；
- selective face complement/action；
- public backend default unchanged。

候选特定 selector 测试可以进入 benchmark/test 组，但不能成为 production capability 声明。

## 4.5 建议合并：benchmark、compact evidence 与文档

建议合并：

```text
benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/
docs/task035e_reference_blind_multilevel_hp_adaptivity/
```

但只提交：

- README/config/expected/test command；
- hash-bound compact records；
- controlled negatives；
- response/outcomes/review；
- Task35e任务书；
- 修订后的模型总账。

不得提交 ignored raw VTU、matrix、factor、timeline、stdout 或大文件。

## 4.6 仅作为 research-only / benchmark 保留

下列内容不应出现在普通求解器菜单中：

```text
legacy_seeded_variable_p.py
physics_guard_variable_p.py
candidate-specific analyze_* / generate_* scripts
T30 / sidewall / top-air / left-grating 固定候选计划
bounded single-root selector
frozen ten-face selector
```

它们可作为 Case097 历史研究与复现入口保留。

## 4.7 明确禁止提升为 production

不得声称或暴露：

- automatic hp production driver；
- reference-blind convergence certification；
- complete combined hp success；
- Hybrid hp success；
- whole top-port selective trace success；
- irregular/curved hexa；
- tetra static condensation；
- mixed-cell hp；
- 0.7 nm qualification；
- iterative hp solver。

---

# 5. 合并前必须完成的 M0–M5

## M0：文档与总账修正

- 完成本 review 第2章全部修正；
- 三方合并 registry backfill；
- README/response/summary 状态一致；
- 明确 h13 仍是当前预算内最佳 accuracy/resource 候选；
- 补充 Task35e入口。

## M1：selective merge manifest

生成：

```text
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/
  selective_merge_manifest_v1.csv
  selective_merge_manifest_v1.md
```

每个文件归类为：

```text
production_core
research_api_opt_in
reusable_runner_watchdog
checker_benchmark
compact_evidence_docs
research_only
do_not_merge
```

并写明依赖、数值行为、测试和是否需要 fresh PDE。

## M2：临时 integration 分支

从最新干净 `origin/master` 创建临时 integration 分支。

先合入/迁移：

```text
chatgpt/20260726-development-model-registry-backfill
```

中的总账和Markdown测试，再迁移 Task035d manifest 中批准的文件。

不得整体 merge 任一大型研究分支。

## M3：测试

至少运行：

- variable-p/local-h serial focused；
- MPI2 hanging/Floquet/ownership；
- MPI8 representative component tests；
- Task032/033/035b Hybrid targeted；
- Case094/095/096/097 checker；
- registry checker；
- full repository pytest；
- Ruff；
- compileall；
- JSON parse；
- diff-check。

如果文件迁移不改变正式 numerical blob，可不重跑 Task035d 全部重型 PDE。

若冲突处理改变：

- local tensor；
- variable-p expansion；
- hanging/Floquet graph；
- DtN；
- static condensation；
- recovery；
- official postprocess；

则必须重跑最小必要的正式 anchor。

## M4：选择性合并 master

M0–M3 全部通过后，按用户授权完成选择性合并并报告：

- 新 master SHA；
- 合并方式；
- 迁移文件数；
- 测试结果；
- 是否重跑 PDE；
- clean worktree。

## M5：创建 Task35e 分支

从新的干净 master 创建：

```text
codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity
```

然后严格执行：

```text
docs/task035e_reference_blind_multilevel_hp_adaptivity/task.md
```

Task035d旧分支保留为完整研究历史，不继续开发。

---

# 6. Task035e 的核心方向

Task035e 不再以“把已知 p6/h10 reference 拿给 selector 比较”为工作方式。

它要模拟未来 0.7 nm 的真实情况：

> 完整收敛参考解不可获得，自适应控制器只能根据当前解、残差、伴随、局部 h/p shadow enrichment 和误差预算自行决定何时停止。

本次13.5 nm中的 p6/h10、p6/h7.5、p6/h5 只由独立 reference certifier 与最终 hidden auditor 使用；adaptive controller 不得读取其数值、网格差、通道误差或 cellwise场差。

Task35e 还必须：

- 先完成 p6/h10、p6/h7.5、p6/h5 高阶收敛审计；
- 不再按功率阈值筛“显著通道”；
- 当前固定采用按衍射级编号排序的前 N=8 个 n=0 传播级：`m=0,-1,...,-7`；
- 对 top/bottom 的每级功率和复振幅设置统一的 mixed absolute/relative 容差；
- 允许真正多层 local-h，使最终网格同时存在粗、中、细多个尺寸；
- 不再以 `<=90k DoF` 为硬限制，改为实测 rows/NNZ/factor/peak 优先；
- Full3D hp 峰值必须低于 p6/h10 static 的 14.721756 GiB，目标低于 11 GiB，优选低于 9 GiB；
- Full3D hidden audit通过后，才接入 static Hybrid M120，并要求低于 7.544262 GiB，优选不高于约 6.4 GiB；
- 内存信用必须来自 active-space、rows、matrix/factor inventory 的结构压缩，不得只来自对象提前释放或不同MPI生命周期。

完整方案见 Task035e任务书。

---

# 7. 最终审阅决定

```text
Task035d task closure = approved
Task035d classification = PARTIAL_WITH_CONTROLLED_NEGATIVES
Task035d overall merge = prohibited
Task035d selective merge after M0–M3 = approved
Task035e branch creation after merge = approved
Task035e heavy execution = approved under task contract
```

Task035d 的成功之处是建立了真正可复用的 variable-p/local-h 数值架构；失败之处是没有得到同精度 production hp candidate。两者都必须完整保留，不能把结构能力失败写成算法无效，也不能把资源下降写成精度成功。
