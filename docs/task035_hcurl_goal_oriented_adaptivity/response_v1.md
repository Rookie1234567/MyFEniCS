# Task035 Response V1：Phase A Gate 失败与受控停止

## 结论

Task035 分支已经从 clean
`master@5002636852ffb67b4711443da70eb536c303e34e` 创建并推送。环境、源码、ABI、
MPI1/2/4/8、MUMPS/PEP、Task034 compact baseline 与六份必需 artifact hash 子 Gate
全部通过；但完整 pytest 的 Case094 文档合同 Gate 失败。因此：

```text
overall_status = controlled_stop
phase_a_full_regression_gate = fail
phase_b_unlocked = false
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

## 已完成的 Phase A 证据

- 环境原始记录位于 gitignored
  `benchmarks/artifacts/task035/phase_a/5002636/`，JSON SHA-256 为
  `f47801cdb48af7d5958aa4ecc9c25cf3ccbc0c0d1816bf35db115ff806aa87fe`。
- `base_manifest.json` 绑定 Task034 final master、Case093 三份 compact records、
  p4/h5 Full3D/Hybrid/M funnel、p3/h3 reference、材料/几何/config 与 Task035 theory。
- 六份必需 Task034 artifact 全部实体存在且实际 SHA-256 与 tracked descriptor 匹配。
- ordinary checker 默认不读取 ignored artifacts；显式模式才验证实体，缺失分类为
  `artifact_not_materialized`。
- Task034 research-only graded mesh/adaptive runner 没有恢复或提升。

## 编号冲突及用户授权处理

阅读全仓时发现
`docs/project_service_requirements_phase1_scope.md` 仍把早期三阶段路线标为旧
Task033–Task035，与当前 Task035 `task.md` 冲突。Codex 按 `AGENTS.md` 停止受影响
工作并报告。用户随后明确授权：

1. 当前以用户指令与 Task035 `task.md` 为权威；
2. 旧 Task033–Task035 映射只视为过期规划；
3. 只在 Task035 执行分支修正文档，不回写其创建基线的 `master`；
4. 在 response 中记录此问题。

本分支已把旧三段改称“历史规划阶段 A/B/C”，并增加当前正式编号说明。没有修改
Task033、Task034 或 Task035 的权威任务书。

## 测试与阻断证据

| 检查 | 结果 |
|---|---|
| focused regression | 24 passed |
| hermetic checker | pass |
| explicit artifact checker | pass，6/6 |
| Ruff / compileall | pass / pass |
| full `pytest -q` | **1 failed, 488 passed, 18 skipped，247.53 s** |

唯一失败：

```text
DocumentationContractTests::
test_numbered_benchmark_cases_use_case_contained_contracts
```

直接原因：新编号目录 `094_hcurl_goal_oriented_adaptivity` 尚无完整 case-contained
contract，因此不在测试的 authoritative case set 中。没有把它改成 skip、没有修改阈值，
也没有立即补齐合同；失败已另存为
`records/phase_a_regression_failure.json` 和 `outcomes/test_summary.md`。

## 停止边界

本轮在失败处停止。没有进入 Phase B，没有运行 estimator fixture、Task035 PDE、adaptive
cycle 或重型 p4，也没有重跑 Task034 已接受的重型矩阵。下一步必须由 review 或用户明确
指令决定如何补齐 Case094 case-contained contract 后重新执行完整 Gate。
