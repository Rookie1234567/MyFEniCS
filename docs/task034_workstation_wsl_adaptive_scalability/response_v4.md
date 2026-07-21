# Task034 Response V4

## 结论

Review V3 与 `review_report_v3_task35_planning_addendum.md` 的 blocking findings 已逐项关闭。当前实现状态仍为 `PASS_WITH_QUALIFICATIONS`；本轮没有修改 Maxwell/Floquet/QEP/DtN/Hybrid 数值核心，没有重跑 p3/h3、p4/h5、M funnel 或 MPI 重型矩阵，也没有执行 Task035 代码或 PDE。分支等待最终 Review V4；未经最终批准和用户授权不得合并 `master`。

| 项目 | 结果 |
|---|---|
| branch | `codex/20260717-task34-workstation-wsl-adaptive-scalability` |
| Review V3/addendum base | `3a6a464156b88cc138a732110f1e22b0915c1f3b` |
| master synchronization | 只对当前分支 `pull --ff-only`；未 merge/rebase/cherry-pick `origin/master` |
| numerical core | unchanged |
| heavy PDE | not rerun；Task035 not started |
| final merge | Review V4 approval + user authorization pending |

## Blocking Finding 1：clean-checkout hermetic 聚合

- 新增 tracked 最小 fixture：`benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/all_model_compact_fixture.json`。
- fixture 固定 40 行 schema 所需字段，并含 generator version、field-source 口径、每行 source SHA、原 artifact SHA-256 和 repository-relative evidence path。
- `benchmarks/task034_review_v2_aggregation.py` 不再解析或打开 `benchmarks/artifacts`；artifact path 只作 provenance string。
- 聚合器对 40 行列集合、row decomposition、S-mainline、`factor_nnz` 适用范围、artifact digest 格式、source/evidence identity、Case092/093 tracked authority 和 MPI coverage 全部 fail closed。
- test86 在临时 no-artifact clean root 中重建 JSON/CSV，并与 tracked 输出逐字节比较；删除关键字段会失败。

## Blocking Finding 2：p4/h3 authority 与 40 行审计

正式权威选用 tracked `p4_h3_execution_outcome.json` / `p4_h3_resource_gate.json` 的 process-tree compact measurement：

| field | selected value |
|---|---:|
| `assembly_seconds` / `total_seconds` | `3035.1390509350167` s |
| `peak_memory_gib` | `80.53771209716797` GiB |

`all_model_results.json/csv`、summary、fixture 与回归断言已一致。`all_model_authority_audit.json` 覆盖全部 40 行；仅 p4/h3 Full3D 的 elapsed/memory 两字段存在旧 artifact-descriptor 漂移，均已解析到 tracked compact authority。p2/h1、p3/h2、p4/h3 Full3D 的 assembly elapsed 也明确写入 `assembly_seconds`，不再混同未知 factorization/solve。

`factor_nnz` 统一定义为 direct factor inventory 的 measured `matrix_stats.matrix_nnz_used`；无 inventory 或 Hybrid 时保持 `null`，不再与 assembled NNZ 混用。

## Blocking Finding 3：项目级当前能力文档

已同步 Task034 README、root/docs README、development progress、capability matrix、roadmap、benchmark/case index、Quick Start、solver guide、code walkthrough、theory index 与 current-version boundaries。统一边界为：

- 主线是 S 偏振；P 只保留 p2/h5 capability sample；
- p3/h3、p4/h5 same-degree closure 已接受；
- p3/h5 Full3D/Hybrid MPI1/8/16 identity 通过，MPI32 仅 exploratory；
- p4/h3 只有 Hybrid M160 shard，Full3D 在 assembly 后受控停止；
- graded-h 只有 conforming mechanism pass，same-error compression 是 controlled negative；
- field/goal-oriented adaptive、variable-p H(curl) 与 0.7 nm production feasibility 均未资格化；
- Task035 仅 planning package；scalable modal core、low-memory Hybrid iterative 与 wavelength continuation 改为后续未冻结编号的独立任务。

## Blocking Finding 4：同一任务分支治理

用户授权的规则已同步到：

- `AGENTS.md`；
- `docs/repository_work_principles.md`；
- root `README.md` / `docs/README.md` 保护区；
- `src/test/test_24_repository_work_principles.py`。

保护测试锁定：ChatGPT/Codex 全部任务材料在同一执行分支；review 直接提交该分支；Codex fast-forward 拉取；`master` 不作 review 中转；只有最终 review approval + 用户授权后由 Codex 合并并报告精确 SHA、测试和工作树。

## Blocking Finding 5：selective merge

最终 manifest 已扩充为文件级依赖组，包含治理、当前能力文档、Task034 compact facts/no-artifact test、Review V1–V3、Response V1–V4、Task035 planning package、summary/test/changed-files。以下保持 `research_only_do_not_merge_yet`：

- `src/geometry/task034_adaptive_mesh.py`；
- `benchmarks/run_task034_adaptive_mechanism.py`；
- `benchmarks/task034_adaptive_compression.py`；
- test82/test83/test84 research-only 配套测试。

它们不因 Task035 planning 而升级为 production。

## Task035 planning addendum

- Task035 README/task/theory package 已纳入 `task035_planning_docs_only` 组；本轮未执行 Task035 代码或 PDE。
- 连续 Maxwell 方程首项已从破损的 `abla\\times` 修为 `\\nabla\\times`。
- CommonMark+table 检查结果：42 个 `$$` delimiter、5 张表、15 个唯一 DOI target；表格列数一致，theory README 本地链接通过。
- DOI resolver 的额外在线探测因工具权限审批超时被终止；未将其伪装为网络可达性通过。Markdown DOI target 的解析、格式与唯一性检查已通过。

## 测试

| Gate | 结果 |
|---|---|
| governance + documentation + hermetic targeted | `28 passed` |
| Task034 test73–test86 | `107 passed` |
| test86 no-artifact/authority | `8 passed` |
| qualified ABI | `numpy.complex128`；PETSc 3.19.6；DOLFINx 0.10.0.post2；SLEPc 3.19.2 |
| full repository pytest | `503 passed, 18 skipped` |
| scoped Ruff | pass |
| compileall | pass |
| `git diff --check` | pass |
| Task035 CommonMark/table/DOI syntax | pass（42 delimiters / 5 tables / 15 unique DOI targets） |

完整命令与口径见 `outcomes/test_summary.md`。本轮只使用已有 accepted evidence 和 tracked compact facts；所有资源负结果原样保留，没有放宽阈值或改写为通过。

## 等待 Review V4

当前分支在提交、推送后停止。未经最终 Review V4 approval 和用户授权，不合并 `master`。
