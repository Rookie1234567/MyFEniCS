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

## Final f2d7719 / 2dbf898 closeout

上面的表述仅保留原 `6555663`、scalar traction、max_it=1600 冻结阶段的历史边界。后续
用户授权 research extension 的 numerical PDE 证据绑定 `f2d7719b6253251a06e8cd8388fd443bbf47d443`；
其后只发生已审的 Python Ruff 机械格式和 test-only 夹具/Case102 evidence contract 变更，
没有改变算法、ordinary default、阈值或已完成 PDE 的物理输入。

### Full repository pytest

| HEAD | command | result | duration | log / SHA256 |
|---|---|---|---:|---|
| `9a51a76e44d43e9f35e545f6dc9a442f25bfb08d` | `python -m pytest -q` | 974 passed, 48 skipped, 1 failed; exit 1 | 1330.53 s | `/tmp/task037c_r7_full_pytest_9a51a76.log` / `d14b92f0612f49964d86cabcb52addbb5b9facc599790bb649dc2988d98cceb2` |
| `2dbf898c431595982b84dedc14bd196cc7bf74cc` | `python -m pytest -q` | 975 passed, 48 skipped, 0 failed; exit 0 | 1328.33 s | `/tmp/task037c_r7_full_pytest_2dbf898.log` / `2cbc7c673887077af120b6678e540090a55e8ba8569957baf40f39caa3c25f6e` |

第一次失败是 legacy Task036 `SimpleNamespace` 缺少正式 dataclass 字段
`modal_traction_model`；获批的 test-only commit `2dbf898` 只补该夹具字段，未修改 production
solver、runner、阈值或数值配置。修复后的该次 run 内无自动重试/单测 rerun；无 PDE、无
`-k`/deselect/xfail 或短 timeout。

### Focused 与静态 Gate

| Gate | 结果 |
|---|---|
| serial focused（Task037b/Task037c、exact coupling、Case102 contract 等） | 107 passed |
| MPI2 lightweight fixture | 每 rank 2 passed |
| MPI4 lightweight fixture | 每 rank 2 passed |
| Ruff check / Ruff format --check | passed |
| `python -m compileall -q src benchmarks` | passed |
| `git diff --check` | passed |
| final f2d 三角度 MPI8/MPI1 PDE 与 comparisons | numerical/identity 全 pass；资源边界另列 |

授权扩展的 M 选择为 `M_robust=120`，不改变上段历史 `not_established` 结论的适用范围；
最终分类为
`TASK037C_S_POL_1DEG_AZIMUTH_ROBUSTNESS_PASS_UNDER_USER_AUTHORIZED_RESEARCH_EXTENSION`，
不是 `production-qualified`。文档-only 修改后只需重跑文档合同、Markdown rendering、
compileall 和 diff-check，不重复完整 pytest 或 PDE。
