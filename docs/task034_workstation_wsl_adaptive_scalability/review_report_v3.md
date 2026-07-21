# Task034 Review V3

## 1. 审查结论

```text
review_status = CHANGES_REQUIRED_BEFORE_FINAL_SELECTIVE_MERGE
master_merge = not_approved_yet
heavy_pde_rerun_required = false unless numerical core changes
expected_next_review = final merge review
```

本轮审查基于：

- 执行分支：`codex/20260717-task34-workstation-wsl-adaptive-scalability`；
- 审查时远端 HEAD：`db88e166781df196dd940b90f1147442df5f158b`；
- Review V3 reviewed-content commit：`2ce6befca16441fe6b1f3f338c67b1a018559695`；
- `response_v3.md` 交付提交：`db88e166781df196dd940b90f1147442df5f158b`。

Review V2 的字段误绑定、summary 展示和 adaptive selective-merge 边界已经基本关闭。当前 p3/h3、p4/h5、Case093、M funnel 与代表性 MPI 数值结论继续接受；S 偏振仍是正式主线，完整 P 入射矩阵无需补跑。

目前不再发现需要回滚 Maxwell、Floquet、QEP、DtN 或 Hybrid 数值内核的重大 bug。剩余阻塞主要属于：

1. 统一事实表仍依赖 gitignored 重型 artifact，无法在 clean checkout/CI 中独立重建；
2. 一处 p4/h3 资源数值在 tracked compact record 与聚合表之间不一致；
3. 项目级文档没有同步到 Task034；
4. 新的“ChatGPT/Codex 同一任务分支协作”规则尚未同步到全部治理文档和保护测试；
5. 最终 selective merge 清单还没有完整纳入上述治理与项目文档。

这些问题关闭后，如果没有引入新的数值核心修改，Task034 可进入最终 selective-merge approval，不需要再次运行已接受的重型 PDE。

---

## 2. 已接受内容

以下内容继续接受，不要求因本轮文档和聚合修正而重跑：

1. WSL native complex PETSc/MPI/MUMPS/SLEPc 环境资格化；
2. Floquet cache 生命周期、active-column reduction、swap authority、source-clean 与 numerical-blob hardening；
3. Task033 p3/h7.5、p3/h5 WSL 锚点复现；
4. p3/h3 Full3D 与 Hybrid M160 same-degree closure；
5. p4/h5 Full3D 与 Hybrid M160 same-degree closure；
6. p2、p3、p4 固定结构的 measured uniform sequences；
7. p3/h5 Full3D/Hybrid MPI1、MPI8、MPI16 identity，MPI32 exploratory；
8. p3/h3 MPI8 与 p4/h5 MPI4 的 M80/M120/M160 模态漏斗；
9. p2/h1、p3/h2、p4/h3 Full3D 的准确状态为 `not_run_by_conservative_resource_gate_after_assembly`；
10. p2/h1 Hybrid 的准确状态为 `timeout_during_field_recovery_no_official_solution`；
11. graded-h mechanism structural pass，但三档同误差压缩均为 controlled negative；
12. resource model v2.1 对 largest component、cumulative envelope、measured peak 与 unknown predicted peak 的区分。

`outcomes/summary.md` 的四类主表现在已经直接展示物理量、规模、资源、M 和 MPI 影响，满足用户要求的主要展示结构。

---

## 3. Blocking Finding 1：统一事实表必须脱离 gitignored artifact 才能重建和测试

### 3.1 当前问题

`benchmarks/task034_review_v2_aggregation.py` 仍会直接读取：

```text
benchmarks/artifacts/...
```

中的 gitignored 重型/原始记录，以补充：

- Hybrid/Full3D timing；
- factor inventory；
- zero-order diffraction；
- DoF/rows/NNZ；
- M-funnel 记录。

这使当前结果存在两个问题：

1. `all_model_results.json/csv` 不能仅从 Git 中的 tracked compact records 在 clean clone 中确定性重建；
2. `test_86_task034_review_v2_aggregation.py` 的通过依赖当前工作站恰好保留完整 `benchmarks/artifacts`，换机器或 CI clean checkout 后可能直接失败。

测试依赖不进 Git 的本地 artifact，不属于可合并的 hermetic regression test。Task034 的机器可读事实表可以引用重型 artifact 的 hash，但其可重建/可检查字段必须来自 tracked compact evidence 或 tracked minimal fixture。

### 3.2 必须修正

Codex 必须选择一种可维护方案：

#### 方案 A：tracked compact descriptors 为唯一重建权威（推荐）

- 扩充 Case092/Case093 tracked JSON，使其包含总表需要的全部精确字段；
- 聚合器只读取 tracked records；
- `evidence_path` 和 SHA 仍指向重型 artifact，但不打开该 artifact；
- 若需要验证 artifact 内容，只比较 tracked SHA descriptor，不把 artifact 是否存在作为普通测试前提。

#### 方案 B：提交最小、去场数据的 tracked fixture

- 从重型记录提取只包含 schema 所需字段的小型 fixture；
- fixture 必须带原 artifact SHA、source SHA、字段来源和生成器版本；
- 聚合器与测试只读取 fixture，不读取重型目录。

不接受：

- 继续依赖 `/home/Projects/...` 或 `benchmarks/artifacts/...` 实体文件；
- 在 artifact 缺失时静默保留旧 CSV 而不验证；
- 将完整原始 solver record 提交 Git；
- 用手写 Markdown/CSV 替代机器可重建来源。

### 3.3 必须新增的 clean-checkout Gate

新增测试或 checker，至少证明：

1. 临时重命名、隐藏或在临时 checkout 中不存在 `benchmarks/artifacts` 时，`build()` 仍可成功；
2. 重建的 `all_model_results.json/csv` 与 tracked 文件逐字节一致；
3. 全部 repo 内 evidence path 为相对路径；
4. tracked compact record 缺少关键字段时 fail closed，而不是从其他方法/阶段猜测；
5. test suite 不依赖用户本地 `/home/Projects` 路径。

最终 merge 后的 full pytest 必须能在 clean clone、只有 tracked files 的条件下通过。

---

## 4. Blocking Finding 2：p4/h3 assembly memory/time 存在 tracked authority 冲突

### 4.1 当前不一致

tracked compact evidence：

```text
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/
  p4_h3_execution_outcome.json
  p4_h3_resource_gate.json
```

均记录：

```text
assembly_elapsed_seconds = 3035.1390509350167
assembly_peak_memory_gib = 80.53771209716797
```

但当前 `all_model_results.csv` 和 `summary.md` 使用：

```text
assembly/total seconds = 3035.1394660410006
peak memory            = 80.58727264404297 GiB
```

两者绑定同一个 assembly evidence path，却不是同一数值。聚合器先读取 tracked compact 值，随后又从本机 artifact descriptor 覆盖该字段，导致 tracked authority 和总表漂移。

### 4.2 修正要求

1. 明确哪一种是正式 memory authority：process-tree simultaneous、cgroup peak 或其他采样字段；
2. 同一字段在 compact record、resource gate、总表和 summary 中必须一致；
3. 若两个数值代表不同口径，必须拆成两个不同字段，不得覆盖；
4. tracked compact record 是最终可移植事实权威时，聚合器不得由 gitignored artifact 静默改写；
5. 为 p4/h3 加入明确回归断言，锁定最终选择的 elapsed 和 memory authority；
6. 同样扫描全部 40 行，检查是否还有 compact-vs-artifact 漂移。

本问题不要求重跑 p4/h3 assembly；只需从现有记录澄清口径并统一 tracked evidence。

---

## 5. Blocking Finding 3：Task034 项目级文档没有同步

Task034 任务书明确要求在结束前更新项目级和 notes 文档，但当前分支仍存在明显过期内容。

### 5.1 `docs/task034.../README.md`

当前仍写：

```text
task_book_and_convergence_addendum_created_on_master
execution_branch_not_created_by_chatgpt
implementation_not_started
```

必须更新为 Task034 Review V3/V4 的真实状态、当前分支、主要 accepted/negative、最终 merge pending 状态和证据入口。

### 5.2 `docs/development_progress.md`

当前标题、时间线和 current branch 仍停在 Task033。必须新增完整 Task034 回顾，至少包括：

- WSL 迁移与 hardening；
- p2/p3/p4 uniform benchmark；
- p3/h3 与 p4/h5 closure；
- M 与 MPI 结论；
- resource-stop 精确语义；
- graded-h controlled negatives；
- 0.7 nm current-layout stress-test 边界；
- Task034 最终 selective-merge 决策；
- Task035 adaptive 专项的下一步。

### 5.3 `docs/capability_matrix.md`

当前仍包含与 Task034 已接受证据冲突的旧描述，例如：

- p3/p4 目标光栅 Hybrid/full3D 尚无资格；
- p4 target Hybrid 未资格化；
- qualification 仅 p2、MPI4、h5/h3/h2；
- graded-h 仅“由下一任务重新建立”，没有记录 Task034 mechanism pass 和 same-error negative。

必须按 Task034 结果更新，但保持准确边界：

- p3/h3、p4/h5 same-degree closure supported/experimental 的实际状态；
- p2/p3/p4 S uniform sequences；
- p3/h5 MPI1/8/16 identity；
- conforming graded-mesh mechanism 为 `research_only`/`experimental mechanism only`；
- field-driven adaptivity 仍 `not_verified`/`not_implemented`；
- p4/h3 仅 Hybrid M160 shard，无 closure；
- 0.7 nm production feasibility unknown。

### 5.4 `docs/README.md`

当前任务索引只到 Task033。必须新增 Task034 目录、状态、review/response 入口，并将“当前任务”表同步。

### 5.5 `docs/project_service_requirements_and_forward_model_roadmap.md`

当前路线仍把：

```text
Task034 = scalable generic 2D modal core
Task035 = final Hybrid iterative solver
```

作为未来安排，这与实际 Task034 和用户决定的 Task035 自适应专项冲突。必须更新为：

```text
Task034 = WSL qualification + high-order fixed-geometry benchmark + controlled graded-h decision
Task035 = H(curl) field/goal-oriented adaptive mesh and hp strategy
subsequent task(s) = scalable modal core
subsequent task(s) = low-memory Hybrid iterative solver
subsequent task(s) = wavelength continuation to 0.7 nm
```

后续任务编号若尚未冻结，可写“Task036+ / 后续独立任务”，不要保留已失效编号承诺。

### 5.6 notes 文档

任务书要求更新：

- `notes/reference/code_walkthrough.md`；
- `notes/theory/README.md`。

至少应增加：

- Task034 hardening、Case093、统一结果表的入口；
- graded-h mechanism 与真正 field-driven adaptivity 的区别；
- Task035 理论文档链接；
- 当前不具备 variable-p H(curl) 或 production adaptive 的明确边界。

### 5.7 其他索引

同步检查并按需更新：

- `docs/benchmark.md`；
- `benchmarks/cases/README.md`；
- root `README.md` 的任务/治理入口；
- `notes/reference/current_version_boundaries.md`；
- 与 Task034 能力声明直接相关的 quick-start/solver 文档。

不要求为了“全面更新”改写无关历史，但所有写着“当前能力/当前任务/下一任务”的文档必须与 Task034 最终状态一致。

---

## 6. Blocking Finding 4：同一任务分支协作规则尚未同步到治理保护区

用户已经明确修改协作规则：

```text
ChatGPT 与 Codex 在同一个任务执行分支提交任务书、review、代码、outcomes 和 response；
最终 review 通过并经用户授权后，才由 Codex 合并 master。
```

Task034 分支的根 `AGENTS.md` 已加入这条规则，但以下治理副本仍未完整同步：

- `docs/repository_work_principles.md`；
- root `README.md` 的治理保护区；
- `docs/README.md` 的治理保护区；
- `src/test/test_24_repository_work_principles.py`；
- 必要时 `src/test/test_26_documentation_contract.py`。

必须按保护区规则同步更新，并获得测试保护：

1. ChatGPT 不在活动任务期间向 `master` 写 task/review/规则修订；
2. ChatGPT review 直接提交同一执行分支；
3. Codex 从同一分支 fast-forward 拉取 review；
4. 未经最终 review approval 和用户授权，不得 merge master；
5. 最终 merge 由 Codex 执行并报告精确 master SHA、测试和工作树；
6. `master` 只接受最终批准的合并，不作为 review 中转分支。

该规则属于用户明确授权的治理变更，应进入 Task034 最终 selective merge，不能只留在 Task034 research branch。

---

## 7. Blocking Finding 5：最终 selective merge manifest 与交付闭环

### 7.1 manifest 必须补齐

最终 manifest 必须纳入并正确分组：

- 根 `AGENTS.md`；
- `docs/repository_work_principles.md`；
- root/docs README 治理保护区；
- governance tests；
- Task034 README、development progress、capability matrix、roadmap；
- notes theory/reference 更新；
- Review V1/V2/V3 与 response V1–V4；
- 最终 summary、事实表和 compact evidence；
- clean-checkout aggregation tests。

`src/geometry/task034_adaptive_mesh.py` 及相关未资格化 adaptive runner 继续保持：

```text
research_only_do_not_merge_yet
```

不得因准备 Task035 而把 Task034 的 controlled-negative adaptive code 提升为 production。

### 7.2 合并方式

Task034 最终仍不建议 whole-branch merge。Codex 应：

1. 在当前 Task034 分支完成 `response_v4.md`；
2. 由 ChatGPT 做最终 Review V4；
3. 最终 review 明确批准、用户授权后；
4. Codex 从 clean `master` 按最终 manifest 做 file-level selective merge；
5. 在合并后的 master 上运行治理、Task034、回归和 clean-checkout aggregation tests；
6. 推送 master 并报告精确 SHA；
7. 不把 research-only adaptive/resource analysis code 无差别整体合入。

---

## 8. Response V4 要求

Codex 应在当前 Task034 分支：

1. 完整阅读本 `review_report_v3.md`；
2. 不 merge/rebase/cherry-pick `origin/master`；
3. 将事实表聚合改为 clean-checkout hermetic；
4. 统一 p4/h3 resource authority；
5. 同步全部项目级与 notes 文档；
6. 同步治理规则、保护区和测试；
7. 更新最终 selective merge manifest；
8. 新增 `response_v4.md`，不得覆盖已有 task/review/response；
9. 若未修改 Maxwell/Floquet/QEP/DtN/Hybrid 数值核心，不重跑已接受重型 PDE；
10. 至少运行：
   - clean-checkout/no-artifact aggregation test；
   - governance tests；
   - documentation contract；
   - Task034 targeted/full tests；
   - full repository pytest in qualified complex environment；
   - scoped Ruff、compileall、`git diff --check`；
11. 提交、推送当前分支，然后停止等待最终 Review V4。

本轮修改完成且无新 blocker 时，下一轮预计可以给出 Task034 最终 selective-merge approval。
