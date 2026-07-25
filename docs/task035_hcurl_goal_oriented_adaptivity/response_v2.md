# Task035 Response V2：Case094 staging contract 恢复

## 结论

Review V1 的唯一阻断已按授权完成局部修正：

```text
initial_full_regression = fail_one_document_contract
contract_fix = pass
final_phase_a_gate = pass
phase_b_unlocked = true
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

实现基于远程 Review V1 提交
`787ba951aa81768ff57c4f09f3f9476a9b1467f3`，没有 merge、rebase、cherry-pick
`origin/master`，也没有重复环境、MPI、artifact 或 Task034 重型资格化。

## 修正内容

### formal 与 staging 生命周期

`test_26_documentation_contract.py` 现在显式区分：

- `QUALIFIED_OR_FROZEN_CASES`：原 Case001–Case093 集合，原有 60 行 README、
  22 项参数、规定章节和 expected status 严格合同完全保留；
- `STAGING_OR_IN_PROGRESS_CASES`：仅
  `094_hcurl_goal_oriented_adaptivity`。

实际编号目录必须严格等于两者并集。staging case 必须包含 README、config、expected、
test_command 和 base manifest，并固定：

```text
status = phase_a_in_progress
canonical = false
production_qualified = false
pde_run = false
phase_b_or_later_results = not_available
```

### Case094 scaffold 与 hermetic checker

新增最小 staging scaffold：

- `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/README.md`；
- `config.json`；
- `expected.json`；
- `test_command.txt`。

普通命令严格为：

```bash
python -m benchmarks.task035_case094
```

它只检查 tracked Phase A descriptors，不读取 ignored artifacts、不启动 MPI 或 PDE。
显式 `--verify-artifacts` 仍仅作为人工 formal artifact 复核入口，不在普通 test command 中。

`test_87_task035_phase_a.py` 新增 staging 非 canonical、base manifest final pass、
ignored-artifact hermetic、formal∪staging 目录集合及首次失败历史保留断言。
Phase A checker 也 fail-closed 检查 manifest 最终 status 和 `full_regression`。

## 首次失败历史

`records/phase_a_regression_failure.json` 保持原内容，仍记录：

```text
1 failed, 488 passed, 18 skipped in 247.53s
```

没有删除、覆盖或把首次结果改写成通过。最终 pass 作为后续证据写入 manifest、outcomes
与本 response。

## 测试

严格按 Review V1 顺序执行：

| 顺序 | 范围 | 结果 |
|---:|---|---:|
| 1 | 原失败 test26 method | 1 passed |
| 2 | test26 + test87 | 23 passed |
| 3 | repository governance + test26 + Case093 + Task034 aggregation + test87 | 49 passed |
| 4 | full `pytest -q`，仅一次 | 494 passed, 18 skipped in 247.77s |
| quality | scoped Ruff | pass |
| quality | scoped compileall | pass |
| quality | JSON / hermetic test command / git diff --check | pass |

没有 GitHub Actions；以上均为本地 WSL 测试。

## 数值与范围边界

本修正没有修改 Maxwell、Floquet、DtN、QEP、Hybrid、材料、几何、mesh backend 或
求解器数值核心。没有重跑 Task034 PDE、MPI 资格化或六份 artifact 全量验证。

Phase B 已按用户与 Review V1 授权解锁。下一阶段只执行 estimator 数学定义和
analytic/manufactured fixtures；不得跳过 fixture 启动真实 p4 adaptive 或其他重型 PDE。

## Review V1 后续：Phase B estimator fixtures

Phase A Gate 通过并按用户授权进入 Phase B 后，只实现 estimator 数学定义与
analytic/manufactured fixtures，没有启动真实 PDE、adaptive mesh 或 p4 heavy case。

新增内容：

- 纯验证层 `src/validation/task035_hcurl_estimator_fixtures.py`；
- hermetic serial/MPI component runner；
- 四类 fixture：homogeneous periodic analytic field、flat lossy layer、material
  interface manufactured corner、Hybrid analytic interface；
- R1–R5、G1/G2、B1/M1 状态矩阵与 compact evidence；
- `outcomes/estimator_definitions.md`、`fixture_matrix.csv/json` 和 Case094
  `records/fixture_summary.json`。

R1、R2、R3、R5、G1、G2、B1、M1 得到 `fixture_pass`。R4 只有局部 SPD
precursor，维持 `formula_defined`，没有宣称 constrained equilibration、
guaranteed bound 或 production qualification。

Phase B 定向结果：

| 检查 | 结果 |
|---|---:|
| estimator fixture targeted | 12 passed |
| Task035 focused suite | 35 passed |
| serial / MPI2 / MPI4 component identity | pass / pass / pass |
| scoped Ruff / compileall / diff-check | pass / pass / pass |

### Full regression 首次错误启动与受控停止

首次 full pytest 错误地直接调用 `.venv/bin/python`，遗漏了任务规定的：

```bash
source .venv/bin/activate-myfenics
```

完成的错误环境 run 为：

```text
36 failed, 453 passed, 18 skipped, 17 errors in 10.71s
```

代表性症状是 real-valued DOLFINx array 拒绝 complex 材料值。另有一次相同命令被外层
5 秒 timeout 终止，没有形成测试结论。错误启动被分类为
`operator_launch_environment_mismatch`，并保存为
`records/phase_b_regression_failure.json`；该历史记录不得删除或改写为通过。

### 用户授权后的正确 activation 恢复

用户随后明确授权“使用正确 activation 重跑一次 full pytest”。执行：

```bash
source .venv/bin/activate-myfenics
pytest -q
```

正确 complex 环境结果：

```text
506 passed, 18 skipped in 248.08s
```

恢复证据保存在 `records/phase_b_regression_recovery.json`，绑定测试源码
`8c85469a5720573f51b784049de7d25bcbe012f4`。首次失败 JSON 保持原样。

```text
phase_b_full_regression_gate = pass
phase_c_unlocked = true
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

Phase C 已解锁但尚未启动。后续只能先执行低成本 estimator bake-off，不得跳过
low-cost point 与 refinement Gate 直接运行真实 p4 adaptive 或其他重型 PDE。
