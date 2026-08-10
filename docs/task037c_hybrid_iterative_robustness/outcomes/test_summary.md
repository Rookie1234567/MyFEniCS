# Task037c R7 测试与静态检查记录

## 测试身份

所有命令均在 `/tmp/task037b-selective-integration-20260810-local` 的 qualified WSL shell
执行，numerical code/config parent SHA 为 `65556637dd10f2de674a800d575983f24336c9d3`。Python/PETSc/MPI 使用同一
`.venv` ABI，`PETSc.ScalarType=complex128`、`PETSc.IntType=int32`；线程变量固定为1。
数值 solver/config/threshold 未改；唯一非文档改动是 `test_26` 中 Case102 空-record
closed-contract 登记，commit `12a12647f89f1b0b4f6deb080046510b8e53821a`，不影响 R2/R3/
diagnostic，故不重跑 PDE。

## focused tests

| 命令 | 结果 | 身份 |
|---|---|---|
| `python -m pytest -q src/test/test_250_task037c_robustness_contract.py src/test/test_251_task037c_full3d_watchdog_contract.py src/test/test_252_task037c_hybrid_direct_contract.py src/test/test_253_task037c_comparator_contract.py src/test/test_24_repository_work_principles.py src/test/test_26_documentation_contract.py src/test/test_183_development_model_registry_markdown.py src/test/test_development_model_registry_contract.py` | `65 passed in 3.67s`（含 Case102 最小登记后的 focused 集合） | measured |
| `python -m pytest -q src/test/test_24_repository_work_principles.py src/test/test_26_documentation_contract.py src/test/test_183_development_model_registry_markdown.py src/test/test_development_model_registry_contract.py` | `27 passed in 0.17s` | measured |
| Markdown fenced-math/table/link checks | 24/24 绝对 artifact 链接及绑定 SHA 通过；数学块、表格、相对链接通过；同 phi 标题计数为1 | measured |

测试范围覆盖角度/S/Floquet、dynamic mode、Full3D/direct authority、q identity、comparator
阈值、M 选择、ordinary default 和 fail-closed 记录。任何测试失败都不应通过删除断言或放宽数值阈值处理。

## 静态检查

| 检查 | 范围 | 结果 | 身份 |
|---|---|---|---|
| Ruff check | 实际 15 个 Task37c touched Python 文件 | passed | measured |
| Ruff format --check | 同上；15 files already formatted | passed | measured |
| `python -m compileall -q src benchmarks` | `src`、`benchmarks` | passed | measured |
| `git diff --check` | 六份 Markdown | passed | measured |

## 唯一完整 pytest

最终数值代码/config parent 未修改后，在 tested HEAD
`12a12647f89f1b0b4f6deb080046510b8e53821a` 的 qualified activation shell
按任务书只运行一次：

```bash
source scripts/activate_myfenics_wsl.sh
python -m pytest -q
```

| 项目 | 实测结果 |
|---|---|
| exit code | `0` |
| pytest 计数 | `940 passed, 48 skipped, 0 failed` |
| pytest duration | `1336.24s` |
| 日志 | `/tmp/task037c_r7_full_pytest_12a1264.log`，1165 bytes |
| 日志 SHA256 | `b0c7b108c9f56dadc50818a6bfad12892cd9c9787838bdfcf4eb133f75baa32a` |
| 运行语义 | 自然结束；无 rerun、无 PDE；未使用 `-k`、deselect、短 timeout、xfail 或阈值修改 |

## Gate 边界

R7 文档只是在既有证据上建立可审阅索引。`not_run`、`not_run_by_gate` 和
`not_run_due_linear_gate` 是有意保留的状态，不是缺失数据；完整 pytest 通过也不会改变
`M_robust=not_established`，因为它不能替代正式 iterative/MPI1 数值证据。
