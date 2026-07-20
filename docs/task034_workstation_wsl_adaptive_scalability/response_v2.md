# Task034 Codex response v2

## 交付结论

Review V1 与 Review V1 Addendum 的 blocking findings 已同时关闭。Task034 保留总状态：

```text
PASS_WITH_QUALIFICATIONS
```

该状态只表示 workflow/decision complete，不表示所有能力通过。uniform benchmark 与代表性 MPI identity 通过；equal-accuracy graded compression 是受控负结果；field-driven adaptivity 未资格化；0.7 nm production target-accuracy feasibility 仍为 unknown。所有失败、超时和资源停止条件均原样保留，没有降低阈值或改写为 pass。

## Git 与 Review 权威身份

| 字段 | full SHA / 状态 |
|---|---|
| branch | `codex/20260717-task34-workstation-wsl-adaptive-scalability` |
| pre-Review-V2 Task034 HEAD | `2de3814ebd28331d114ec78adabd37cfa3ca288e` |
| merged `origin/master` | `6b80b209c07d3c1d8354365a4359bf532ad7aec2` |
| normal merge commit | `a23d59981a64015e35c82b8afa2a945b8d8e1e3e` |
| Review V2 reviewed-content commit | `a161ce0fb61454f3fb5588f645cf6d8b95b0f5f7` |
| history policy | normal merge；no rebase；no force push；no history rewrite |

`response_v2.md` 的交付提交必然是 reviewed-content commit 的直接子提交；Git 提交对象不能在自身内容中预写自身 SHA。最终推送后的精确 branch HEAD 由交付回执中的 `git rev-parse HEAD` 与 `git rev-parse origin/codex/20260717-task34-workstation-wsl-adaptive-scalability` 共同确认。审阅的代码、测试、机器可读 outcomes 和 `summary.md` 均冻结在上述 reviewed-content commit。

本次 normal merge 从 master 引入：

```text
M  AGENTS.md
A  docs/task034_workstation_wsl_adaptive_scalability/review_report_v1.md
A  docs/task034_workstation_wsl_adaptive_scalability/review_report_v1_addendum.md
```

两份 Review 权威文件和根 `AGENTS.md` 在后续修复中均未被 Task034 修改。

## Review V1 blocking findings 关闭情况

| Finding | 修复 | 证据 |
|---|---|---|
| 1：组件库存之和误称 predicted peak | resource model v2.1 分离 largest component、local subtotal、modal subtotal、cumulative component envelope、measured simultaneous peak 与 unknown predicted simultaneous peak；所有 ratio 按对象命名 | `outcomes/resource_model_v2.json/csv/md`、`test_85` |
| 2：0.7 nm 未按 p 情景且未绑定精度边界 | 增加 p2/h3、p3/h3、p4/h5 三个 current-layout mechanical stress-test；明确它们不是 common target-accuracy p 比较；区分 current-layout single-component infeasible 与 production target-accuracy unknown | `outcomes/0p7nm_workstation_and_tib_assessment.md` |
| 3：缺少稳定 provenance | 记录 master、merge、reviewed-content 的完整 SHA；机器可读表逐行保留 `source_sha` 与 `evidence_path`；最终 push 回执确认远端 HEAD | 本 response、`all_model_results.json/csv` |
| 4：`PASS_WITH_QUALIFICATIONS` 语义过宽 | 增加 capability layering，分别标记 workflow、uniform benchmark、MPI、graded mechanism、equal-accuracy compression、field-driven adaptivity 和 0.7 nm | `outcomes/summary.md` |
| 5：selective manifest 不可直接执行 | 逐文件给出 merge action、dependency group、targeted tests、numerical behavior、fresh PDE evidence、merge order 和 rationale；历史 JSON portability 单独分组并声明 semantic payload 未变 | `outcomes/selective_merge_manifest.csv` |

## Review V1 Addendum 关闭情况

### A1：Benchmark Python 架构

`outcomes/benchmark_python_inventory.csv/md` 覆盖 31 个变更的 benchmark Python 文件，按 generic PDE runner、watchdog/telemetry、checker/aggregator、one-off research、historical entrypoint 分类。未发现 Task034 在 `benchmarks/` 复制新的 Maxwell/Floquet/QEP/Hybrid solver；生产数值功能仍归 `src/`。adaptive、reranking、resource model 与 Review 聚合器明确为 research/evidence-only，不作为 production API。

### A2 与 A5：补充 p/h 点和 S 偏振语义

- p2/h1、p3/h2、p4/h3 Full3D 的精确状态均为 `not_run_by_conservative_resource_gate_after_assembly`；`factorization_launched=false`、`full_solve_launched=false`；factorization upper 是 prediction，不是 measured peak。
- p2/h1 Hybrid 的精确状态为 `timeout_during_field_recovery_no_official_solution`：7200 s、95.878723 GiB、zero swap；没有 solver terminal record、true residual 或 official R/T/A，不能归类为 memory negative 或 numerical nonconvergence。
- p3/h2、p4/h3 Hybrid 只登记 M160 shard pass，不声称 M funnel 或 Full3D/Hybrid closure。
- 正式主线为 S polarization。`R00_p/T00_p` 是 S 入射下的 cross-polarized p 输出，不是 P incidence；没有为了补表重跑整套 P 矩阵。既有 p2/h5 P sample 仅保留 capability 结论。

### A3：统一全案例结果表

新增 `outcomes/all_model_results.json/csv`：40 行、严格 36 列，统一覆盖 Case093、p3/h3 与 p4/h5 M funnel、p3/h5 MPI identity、p2/h1/p3/h2/p4/h3 资源或 shard 结果。缺失量使用 `null`，不插值、不从预测值伪造实测量。`outcomes/summary.md` 已增加：

1. all models；
2. p3/h3 与 p4/h5 M80/M120/M160；
3. p3/h5 Full3D/Hybrid MPI1/8/16 和 MPI32 exploratory；
4. resource stop/timeout。

### A4：仓库级规则

Review V2 开始前已 normal merge 最新 master，并完整重读根 `AGENTS.md`、仓库工作原则、Task034 任务书、补充任务书和两份 Review 权威。仓库级 `src/`/`benchmarks/` 边界已应用到 inventory 与 selective manifest。

## 资源模型与 0.7 nm 结论

13.5 nm 三个 current-layout 情景的 measured simultaneous peaks 分别为 p2/h3 4.695 GiB、p3/h3 14.272 GiB、p4/h5 9.206 GiB。0.7 nm 的 cumulative component envelopes 分别约为 2,014,975、6,804,671、3,008,763 GiB，但这些累计值不是同时峰值；extrapolated simultaneous peak 一律为 unknown。三个情景均有单组件超过 2 TiB，因此 current layout stress test 为负；材料色散、cutoff、角度、evanescent buffer、目标精度 DoF/M 和 production peak 未知，不能把该结论升级为 production target-accuracy feasibility prediction。

## 验证

| 验证 | 结果 |
|---|---:|
| Review V2 targeted test85+test86 | 5 passed |
| Task034 test73–test86 | 102 passed |
| documentation contract test26 | 13 passed |
| scoped Ruff | clean |
| bytecode compile | exit 0 |
| full repository pytest | 496 passed，18 skipped，243.68 s |
| `git diff --check` | clean |

本轮没有修改 Maxwell/Floquet/QEP/Hybrid 数值核心，因此按 Review 指示没有重跑已接受的 p3/h3、p4/h5 和 MPI 重型矩阵。

## 交付索引与停止点

- 总结：`outcomes/summary.md`
- 统一结果：`outcomes/all_model_results.json/csv`
- resource model：`outcomes/resource_model_v2.json/csv/md`
- 0.7 nm：`outcomes/0p7nm_workstation_and_tib_assessment.md`
- benchmark inventory：outcomes/benchmark_python_inventory.csv、outcomes/benchmark_python_inventory.md
- tests：`outcomes/test_summary.md`
- changed files：`outcomes/changed_files.md`
- selective merge：`outcomes/selective_merge_manifest.csv`

请基于本 response 和 reviewed-content commit 执行 Review V2。Codex 在提交并推送本文件后停止，不自行合并 master。
