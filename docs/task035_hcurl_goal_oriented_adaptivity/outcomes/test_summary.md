# Task035 测试摘要：Phase A controlled stop

## 结论

```text
phase_a_full_regression_gate_fail
controlled_stop
phase_b_unlocked = false
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

## 阻断 Gate

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
`records/base_manifest.json`，尚未进入项目的完整 numbered-case contract 集合。按用户
Gate 规则，本轮不补合同、不改期望集合、不放宽阈值，保存证据并停止。
