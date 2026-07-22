# Task035 测试摘要：Phase A staging contract 恢复

## 结论

```text
initial_full_regression = fail_one_document_contract
contract_fix = pass
final_phase_a_gate = pass
phase_b_unlocked = true
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

## 已通过检查

| 检查 | 结果 |
|---|---|
| JSON syntax | pass |
| hermetic Phase A checker | pass |
| explicit artifact hash checker | pass；6/6 materialized hash match |
| focused Case093/Task034/Task035 tests | 24 passed |
| targeted Ruff | pass |
| targeted compileall | pass |
| git diff --check（失败发生前） | pass |

## 初始阻断 Gate（历史保留）

命令：

```bash
pytest -q
```

结果：

```text
1 failed, 488 passed, 18 skipped in 247.53s
```

失败测试：

```text
src/test/test_26_documentation_contract.py::
DocumentationContractTests::
test_numbered_benchmark_cases_use_case_contained_contracts
```

直接原因是新增编号目录 `094_hcurl_goal_oriented_adaptivity` 只有 Phase A
`records/base_manifest.json`，尚未进入项目的完整 numbered-case contract 集合。当时按

## Review V1 合同修正与最终验证

Review V1 授权把 numbered case 生命周期拆分为 formal/frozen 与 staging/in-progress。
Case001–Case093 的完整严格合同保持不变；Case094 显式注册为 staging，新增最小
README/config/expected/test_command scaffold，普通入口只运行 hermetic checker。

| 顺序 | 命令范围 | 结果 |
|---:|---|---:|
| 1 | 原失败 test26 method | 1 passed |
| 2 | test26 + test87 | 23 passed |
| 3 | governance + Case093/Task034 + Task035 focused | 49 passed |
| 4 | full `pytest -q`（仅一次） | 494 passed, 18 skipped in 247.77s |
| quality | scoped Ruff / compileall / diff-check | pass / pass / pass |

最终状态：

```text
initial_full_regression = fail_one_document_contract
contract_fix = pass
final_phase_a_gate = pass
phase_b_unlocked = true
```

`records/phase_a_regression_failure.json` 继续保存首次失败历史，未删除、覆盖或改写为通过。
Gate 规则保存证据并停止；Review V1 随后授权局部 staging lifecycle 修正。

## Phase B fixture 与 full regression 恢复

| 检查 | 结果 |
|---|---:|
| estimator fixture targeted | 12 passed |
| Task035 focused suite | 35 passed |
| serial / MPI2 / MPI4 component identity | pass / pass / pass |
| scoped Ruff / compileall / diff-check | pass / pass / pass |
| 首次错误 launcher full pytest | controlled stop；36 failed, 453 passed, 18 skipped, 17 errors |
| 正确 sourced complex activation full pytest | 506 passed, 18 skipped in 248.08s |

首次 Phase B full failure 由遗漏 `source .venv/bin/activate-myfenics` 引起，已原样保存到
`records/phase_b_regression_failure.json`。用户明确授权后，仅用正确 activation 重跑一次；
恢复记录为 `records/phase_b_regression_recovery.json`。

```text
phase_b_full_regression_gate = pass
phase_c_unlocked = true
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```
