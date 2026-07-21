# Task034 Review V4

## 1. 审查结论

```text
review_status = FINAL_PRE_MERGE_CHANGES_AUTHORIZED
master_merge = conditionally_approved_after_all_final_gates_pass
heavy_pde_rerun_required = false unless numerical core changes
additional_chatgpt_review_required = false
user_merge_authorization = granted_conditionally_by_user
```

本轮审查基于：

- 执行分支：`codex/20260717-task34-workstation-wsl-adaptive-scalability`；
- 审查时远端 HEAD：`319c94390aa6275d0f82c33ffbbd388b464244eb`；
- `response_v4.md` 与该 HEAD 的 tracked 内容；
- 当前 `master`：`82a5107b5c2bfe4c466a0d00ead31d7b172e2af4`。

Review V3 的主要工程阻塞已经关闭：

1. 40 行事实表现在可在无 `benchmarks/artifacts` 的 clean root 中确定性重建；
2. p4/h3 assembly 的 elapsed/memory 已统一为 tracked compact process-tree authority；
3. Task034 README、development progress、治理保护区、Case093/Task035 索引和大部分能力文档已同步；
4. Task034 adaptive 实现继续保持 research-only；
5. Task035 仍只是 planning package，未运行代码或 PDE。

当前没有发现需要回滚 Maxwell、Floquet、QEP、DtN 或 Hybrid 数值核心的重大错误。以下剩余问题是 Task034 合并前的最后修改清单。用户已明确授权：Codex 完成这些修正、通过全部规定 Gate、保持工作树干净后，可直接按最终 manifest 执行 file-level selective merge，无需再等待额外 ChatGPT review。

---

## 2. 已接受内容

以下内容继续接受，不要求重跑重型 PDE：

- WSL native complex ABI 和 Task034 hardening；
- Case093 p2/p3/p4 S 偏振固定几何序列；
- p3/h3 与 p4/h5 Full3D–Hybrid same-degree closure；
- p3/h5 Full3D/Hybrid MPI1/8/16 identity，MPI32 exploratory；
- p3/h3 MPI8 与 p4/h5 MPI4 的 M80/M120/M160 漏斗；
- p2/h1、p3/h2、p4/h3 Full3D 的 assembly 后资源受控停止；
- p2/h1 Hybrid 的 field-recovery timeout；
- graded-h mechanism pass、same-error controlled negative、field-driven adaptivity not qualified；
- resource model v2.1 的 envelope/peak 语义；
- tracked compact fixture + no-artifact hermetic aggregation 的总体设计；
- Task035 H(curl) field/goal-oriented adaptivity planning package。

---

## 3. Final Finding 1：Hybrid `elements=0` 是错误的数据语义

### 3.1 当前问题

`all_model_compact_fixture.json` 和生成的 `all_model_results.json/csv` 中，多条 Hybrid 行写成：

```text
elements = 0
fe_dofs > 0
```

例如 p2/h5 Hybrid 有 `fe_dofs=13652`、`total_rows=14052`，但 `elements=0`。p3/h3、p4/h5 和补充 Hybrid 行也存在同类情况。

Hybrid 局部三维 FEM 显然拥有非零网格单元。`0` 表示“确切测得为零”，不是“记录未提供”。因此这会误导后续统计、压缩比和 Task035 baseline binding。

### 3.2 修正要求

1. 若 accepted compact evidence 中能取得 bottom/top local mesh cell counts，写入两者之和；
2. 若无法从已接受证据可靠取得，必须写 `null`，不得写 `0`；
3. 扫描全部 40 行：任何 `fe_dofs > 0` 的 FEM/Hybrid 行不得出现 `elements == 0`；
4. 更新 compact fixture、事实表、authority audit 和必要文档；
5. test86 增加回归断言；
6. 不允许仅为填表从未绑定的本地 artifact 猜测 cell count。

---

## 4. Final Finding 2：最终 manifest 与真实 `master` 状态不一致

### 4.1 Review V1 文件并不在当前 master

当前 `master` 是 `82a5107...`。远程 compare 将以下文件列为相对 master 的新增文件：

```text
docs/task034_workstation_wsl_adaptive_scalability/review_report_v1.md
docs/task034_workstation_wsl_adaptive_scalability/review_report_v1_addendum.md
```

但 selective manifest 将它们标为：

```text
status = already_on_master
merge_action = already_on_master_dependency
```

`changed_files.md` 也遗漏了这两个实际新增文件。若按当前 manifest 执行，最终 master 会缺失 Review V1 权威链。

### 4.2 修正要求

1. 以当前真实 `origin/master` 重新机械生成 changed-file 集；
2. 将 Review V1 与 V1 addendum 改为需要选择性合入的 review/evidence 文件；
3. 将本 `review_report_v4.md` 和最终 `response_v5.md` 纳入最终 manifest；
4. 增加 manifest/changed-files 集合一致性 checker：
   - 每个真实 changed path 有且只有一个 manifest row；
   - `already_on_master` 只允许用于当前 master 实际存在且内容一致的路径；
   - research-only path 仍列出，但明确不合入；
5. 最终报告 manifest 总行数、changed path 数、实际 include/exclude 数量。

---

## 5. Final Finding 3：仍有少量当前能力/路线文档保留旧表述

### 5.1 `docs/capability_matrix.md` 的全局 Qualification 表仍停在旧 p2/MPI4 范围

当前表仍写：

```text
element = p2 Nedelec
mesh target = h5/h3/h2
MPI = 4 ranks
Task32 Hybrid direct = h5/h3 only
```

这张表位于通用标题 `Qualification 范围` 下，与前面已经加入的 Task034 p3/p4、MPI8/16 和 Case093 能力容易冲突。

允许两种修正：

1. 将该表明确重命名为 `Task027–Task031 canonical iterative profile qualification`，说明它只约束旧迭代 profile；并新增 Task034 fixed-geometry qualification 表；或
2. 重构成按能力分组的 qualification 表，分别列 iterative、Full3D/Hybrid Case093 和 representative MPI。

同时将 `future complex-ends Hybrid route | Task033–Task036 roadmap` 等旧编号范围改为当前未冻结的后续路线描述。

### 5.2 roadmap 仍保留冲突的 `Task036` 编号承诺

`docs/project_service_requirements_and_forward_model_roadmap.md` 一方面写“后续任务编号尚未冻结”，另一方面仍保留：

```text
## Task036：逐波长缩短至 0.7 nm
```

并在文档身份/范围中继续使用 `Task031–Task036`。这与 Review V3 的明确要求及 Task035 改号后的路线不完全一致。

修正为：

```text
Task034 = WSL + fixed-geometry benchmark + controlled graded-h decision
Task035 = H(curl) field/goal-oriented adaptivity
后续独立任务 = scalable modal core
后续独立任务 = low-memory Hybrid iterative
后续独立任务 = wavelength continuation to 0.7 nm
```

尚未冻结编号的任务不得继续使用精确 `Task036` 标题。同步修正 `docs/README.md` 中 `Task031–Task036` 的概述文字以及其他直接引用该旧范围的当前路线文档。

---

## 6. Final P1：compact fixture 的生成身份应表述准确

fixture 当前写：

```text
generator.name = benchmarks/task034_review_v2_aggregation.py
```

但当前该脚本的职责是读取 fixture 并生成 `all_model_results`，并不从重型 artifact 生成 fixture。最终收口时改为更准确的字段，例如：

```text
extraction_process
fixture_schema_version
output_aggregator
```

或明确该 fixture 是一次性的 reviewed SHA-bound extraction，而不是声称 clean checkout 可由该脚本从 artifact 重新生成。该问题不改变物理结果，但应避免 provenance 描述过度。

---

## 7. 最终修改、选择性合并与 Task035 启动授权

Codex 应继续在当前 Task034 分支：

1. 读取本 `review_report_v4.md`；
2. 不 merge/rebase/cherry-pick `origin/master`；
3. 修正 Hybrid `elements` 的零值语义并重建事实表；
4. 以当前真实 master 修正 changed-files 和 selective manifest；
5. 完成 capability qualification 表和 roadmap 编号同步；
6. 准确化 fixture provenance/generator 表述；
7. 新增 `response_v5.md`，不得覆盖既有 review/response；
8. 若不修改数值核心，不重跑重型 PDE；
9. 至少重跑：
   - no-artifact aggregation/test86；
   - manifest/changed-files exact coverage checker；
   - governance tests；
   - documentation contract；
   - Task034 suite；
   - qualified complex ABI 下 full pytest；
   - scoped Ruff、compileall、`git diff --check`；
10. 所有 Gate 通过且工作树干净后，本 Review 与用户本轮指令共同构成最终合并授权；无需等待 Review V5；
11. 不得 whole-branch merge，必须严格按最终 manifest 做 file-level selective merge，并排除全部 `research_only_do_not_merge_yet`、`review_only_do_not_merge_to_production`、`historical_compatibility_optional` 中未明确选择的文件；
12. 在合并后的 `master` 上重新运行 governance、documentation、Task034、hermetic aggregation 和 full repository tests；
13. 测试通过后推送 `master`，并报告：
    - 精确 master SHA；
    - 合并方式；
    - 实际合入和排除文件数量；
    - 测试结果；
    - 工作树状态；
14. 随后从最新、干净且已推送的 `origin/master` 创建并推送：

```text
codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

15. 在 Task035 分支完整读取 `AGENTS.md`、Task035 README、任务书、理论文档和 Task034 最终 evidence，重新完成环境与 baseline binding，然后严格按 Phase A → Phase B → 后续 Gate 顺序执行；
16. 不得把 Task034 research-only adaptive code 直接提升为 Task035 production，也不得跳过 estimator fixture 直接运行重型 p4 adaptive；
17. 任一修改、测试、选择性合并或 Task035 启动 Gate 失败时立即停止并报告，不得强行继续。
