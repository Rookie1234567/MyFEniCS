# Task034 Review Report V1

## 1. Review 结论

```text
review_status = CHANGES_REQUIRED_BEFORE_SELECTIVE_MERGE
branch_result = substantial_partial_success_with_controlled_negatives
master_merge = not_approved
```

Task034 已形成大量可信的 WSL 原生数值证据，尤其是 p3/h3、p4/h5、Full3D–Hybrid 同阶闭合、MPI 数值一致性和 Case093 compact benchmark。受控资源负结果与 graded-h 物理负结果也被原样保留，没有通过放宽阈值制造正结论。

但当前 `response_v1.md`、resource model v2 和 selective merge manifest 仍有需要修正的正式问题。在这些问题关闭前，不建议把 Task034 整体或按当前 manifest 直接选择性合入 `master`。

## 2. 已接受的主要结果

### 2.1 WSL 环境与 post-merge hardening

以下结论可接受：

- WSL native complex PETSc/SLEPc/DOLFINx/MPI/MUMPS 环境已形成结构化资格化证据；
- MPI1/2/4/8/16 formal，MPI32 exploratory 的边界明确；
- cache lifecycle、Python active-column allgather、process-tree/cgroup swap、完整 source-clean、numerical-blob checker 均有实现和测试；
- ordinary defaults 保持不变，研究路径显式 opt-in。

### 2.2 p3/h3 与 p4/h5 数值主线

以下数值结论可接受：

- p3/h3 Full3D staged reference 成功，true residual、official R/T/A、A_volume、场、接口和衍射级证据完整；
- p3/h3 Hybrid M80/M120/M160 funnel 成功，M160 与同阶 Full3D 的 16 项 closure Gate 通过；
- p4/h5 Full3D staged reference 成功；
- p4/h5 Hybrid M80/M120/M160 funnel 成功，M160 与同阶 Full3D closure 通过；
- p4/h5 相对 p3/h5 显示清晰的工程精度收益，但没有升级为 continuum reference；
- p2/p3/p4 的 uniform 序列只声明 measured discrete trend，不声明连续解或严格网格收敛，措辞正确。

### 2.3 MPI identity 与 Case093

以下结论可接受：

- p3/h5 Full3D 与 Hybrid 的 MPI1/8/16 数值身份闭合；
- MPI32 被正确限制为 exploratory；
- Case093 明确标记为 `canonical_partial_with_user_approved_reduced_scope`；
- canonical anchors p2/h2、p3/h3、p4/h5 以及 `grid_convergence_proven=false`、`continuum_reference=false` 的边界合理。

### 2.4 自适应负结果

当前 graded-h 结果应作为正式负结果接受：

- conforming tensor-product hexahedral graded mechanism 通过；
- conservative/balanced/aggressive 三档虽然减少 raw DoF，但均未通过 same-error physical Gate；
- `qualified_compression_ratio=null`、`genuine_fixed_p_h_adaptivity=not_yet_qualified` 的分类正确；
- 没有把几何 graded mesh 冒充 field-driven adaptivity；
- 根据任务书 stop condition 停止 common-mesh、p3 adaptive 和更重计算是允许的 fail-closed 行为。

## 3. Blocking findings

### Finding 1 — resource model v2 把组件库存之和称为 predicted peak

**Severity: High**

`resource_model_v2` 将 local assembly、local factorization、QEP matrices、QEP factor、mode vectors、projection、replicated dense arrays、dense multi-RHS、field reconstruction 和 MPI/runtime overhead 逐项相加，得到 `predicted_total_gib`，并在 summary/response 中表述为 0.7 nm `predicted peak ≈ 2,014,975 GiB`。

当前记录没有给出这些对象在真实执行生命周期中的同时驻留关系、释放顺序或峰值阶段组合。13.5 nm 校准通过把 residual overhead 调整到使组件和精确等于 measured peak，只能闭合基准总量，不能证明所有缩放后的组件会在同一时刻共存。

因此：

- `2,014,975 GiB` 不能作为严格的 simultaneous peak；
- `7,871x / 1,968x / 984x joint compression` 也不能作为精确的峰值压缩需求；
- 最大单组件 `dense multi-RHS ≈ 1,747,721 GiB` 和 local direct factor `≈198,690 GiB` 已足以证明当前布局不可行，这一“不可能性”结论仍成立。

**Required changes:**

1. 二选一：
   - 将当前 `predicted_total_gib` 全部改名为 `cumulative_component_envelope_gib` 或等价名称，明确不是 simultaneous peak；或
   - 建立生命周期/overlap 模型，定义每个执行阶段同时存在的对象，并以各阶段和的最大值作为 predicted peak。
2. 把 largest single component、local-side subtotal、modal-side subtotal、cumulative envelope、simultaneous peak estimate 分开报告。
3. 对压缩倍数分别给出：
   - largest-component lower bound；
   - cumulative-envelope ratio；
   - 若有生命周期模型，再给 peak ratio。
4. 修正 `response_v1.md`、`summary.md`、`resource_model_v2.md/json/csv` 和 `0p7nm_workstation_and_tib_assessment.md` 中的相应措辞。

### Finding 2 — 0.7 nm 外推没有绑定目标精度或按 p 阶次分情景

**Severity: High**

当前 0.7 nm 模型以 `p2/h3 Hybrid M160` 为唯一空间与对象基准，并使用固定 points-per-wavelength 的 `s^3/s^4/s^5` 机械缩放。这个基准在 13.5 nm 下不是当前最佳离散参考，也没有证明与 p4/h5 或 p4/h3 处于相同目标精度。

因此当前的 490,611,687 local FE DoF、763,591 QEP DoF 和整体资源数字只能解释为：

```text
p2/h3-based current-layout mechanical stress test
```

不能解释为“0.7 nm 下达到目标物理精度所需的统一预测”。此外，材料色散、cutoff、角度和 evanescent buffer 已列为 unknown，这些边界必须在总标题和表头层面更明显。

**Required changes:**

1. 至少生成 p2、p3、p4 三个空间离散情景，或明确说明为何只保留 p2/h3 stress-test scenario。
2. 若生成多阶情景，网格尺度应来自 13.5 nm 的同误差/最佳可用离散证据，而不是仅按一个低阶基准外推。
3. 把“current architecture infeasible”与“达到某一目标精度所需资源 unknown”分开。
4. 0.7 nm 的最终正式结论应是：当前对象布局在任何合理情景下存在独立的 local-factor 和 modal-dense bottleneck；具体 production DoF/peak 尚未被证明。

### Finding 3 — 最终 response 缺少精确 branch HEAD 和稳定 provenance

**Severity: Medium**

`response_v1.md` 的 branch HEAD 写为：

```text
以本 response 的最终提交/推送 SHA 为准
```

这不是可审计身份。正式 response 必须写出精确 full SHA，并确认：

- `HEAD == origin/codex/20260717-task34-workstation-wsl-adaptive-scalability`；
- response 写入前后的 source 状态；
- worktree clean including nonignored untracked；
- 最终测试和 compact records 对应的 SHA 边界。

**Required changes:**

在 `response_v2.md` 中写出精确 final HEAD；不得覆盖 `response_v1.md`。

### Finding 4 — `PASS_WITH_QUALIFICATIONS` 的语义需要收紧

**Severity: Medium**

任务书允许在关键 observable 失败时停止当前 adaptive lane，因此“任务获得完整 decision”可以成立。但当前 response 同时写：

- Task034 已完成；
- 所有阶段均闭合；
- genuine fixed-p h-adaptivity 尚未资格化；
- robust common mesh 与 p3 adaptive 未运行。

这容易让读者把“执行流程按 stop condition 结束”误解为“自适应能力完成”。

**Required changes:**

在 `response_v2.md` 和 summary 顶部增加能力矩阵，至少区分：

```text
workflow_decision_complete = true
uniform_full3d_hybrid_benchmark = pass
mpi_identity = pass
conforming_graded_mesh_mechanism = pass
equal_accuracy_graded_compression = controlled_negative
genuine_field_driven_adaptivity = not_qualified
robust_common_mesh = not_run_by_stop_condition
p3_adaptive = not_run_by_stop_condition
resource_model = engineering_stress_test_requires_revision
```

最终总状态可保留 `PASS_WITH_QUALIFICATIONS`，但必须明确它是 workflow/decision 层状态，不是 adaptive capability pass。若不采用该分层，建议改为 `PARTIAL_RESULT_COMPLETE_WITH_CONTROLLED_NEGATIVES`。

### Finding 5 — selective merge manifest 仍不足以直接执行 file-level merge

**Severity: Medium**

当前 manifest 有大量文件使用同一个泛化理由：

```text
merge_candidate_requires_review
既有代码、测试或文档的 Task034 硬化，需选择性回归审查
```

这还不是可直接执行的 selective merge 计划。尤其是：

- 修改了多个 Task030/031/032/033 runner；
- 修改了历史 benchmark record 的 checkout bytes/hash；
- 新增 Case092/093 checker/tooling；
- adaptive/resource research 文件与 production hardening 文件混在同一清单；
- 没有逐文件给出依赖组、对应测试、数值 PDE rerun binding 和推荐 merge commit/group。

**Required changes:**

1. 将 manifest 分成明确组：
   - production hardening；
   - environment/watchdog utilities；
   - Case093 benchmark/checker；
   - compact evidence/docs；
   - research-only adaptive；
   - review-only resource model；
   - do-not-merge negatives/artifact indexes。
2. 每个待合入源文件至少给出：
   - exact path；
   - merge action；
   - dependency group；
   - targeted tests；
   - whether numerical behavior changes；
   - corresponding fresh PDE rerun evidence；
   - recommended merge order。
3. 历史 JSON portability 修改必须单列，并说明内容字段是否改变、只改变 checkout hash 还是改变 canonical semantic payload。
4. 在 Review V2 通过前，不执行 source-code selective merge。

## 4. Non-blocking observations

### 4.1 Full Ruff

15 个 Ruff 问题来自未修改历史文件，已被正确标为 baseline boundary，不构成 Task034 blocker。

### 4.2 Adaptive implementation

`src/geometry/task034_adaptive_mesh.py` 当前是 conforming graded tensor-product mechanism，不是 arbitrary local octree/hanging-node adaptivity。现有文档已经正确限制该能力；保持 research-only、不合入 production 是合理决定。

### 4.3 p2/h1、p3/h2、p4/h3

受控资源停止和单点 Hybrid 结果均应保留。没有同点 Full3D closure 或 M funnel 的结果不得进入 canonical physical convergence positive；当前多数文档已遵守该边界。

## 5. Codex Response V2 最低要求

Codex 应在原 Task034 分支新增：

```text
docs/task034_workstation_wsl_adaptive_scalability/response_v2.md
```

不得覆盖任务书、补充任务书、`response_v1.md` 或本 review。

V2 至少需要：

1. 修正 resource model 的 peak/envelope 语义，或实现生命周期 peak 模型；
2. 将 0.7 nm 结果改为按 p 情景或明确的 p2/h3 current-layout stress test；
3. 写出 exact final branch HEAD 和 clean/stable provenance；
4. 分层说明 workflow completion 与 adaptive capability status；
5. 重写可执行的 selective merge manifest；
6. 更新受影响 tests/checkers，并重新运行 Task034 serial/native、selected MPI、Task032/033 regression、scoped Ruff、compileall 和 numerical blob audit；
7. 提交并推送后停止，等待 Review V2。

## 6. 当前 merge 建议

```text
merge_now = false
continue_on_same_task034_branch = true
response_required = response_v2.md
```

在 V2 关闭 Blocking Findings 1–5 前，不建议把 Task034 源码或 benchmark authority 选择性合入 master。
