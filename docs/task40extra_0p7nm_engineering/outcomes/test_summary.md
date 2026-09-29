# Task40extra 测试与文档检查摘要

## 测试结果

| 范围 | 命令/输入 | 结果 | 证据边界 |
|---|---|---|---|
| N2 tiny p2 diagnostic | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_n2_tiny_task40_stage4_static_condensed_diagnostic` | `1 passed`；solver `8.608 s` | source commit/base `036dec55beb0fdb1f3cae7693fddfc0225921eb9` 加未提交实现 diff `7cd587b76d90670bc396dc3e82f4641fbd1cce3b1f65d2f4c71058bb6dd977e1`；60-cell p2 diagnostic，不是 G0/G1 official |
| Task40 focused regression suite（历史阶段；并非 profile smoke） | 5 个目标文件，精确命令见下方 | `41 passed, 1 deselected in 9.20 s` | 含 Task40 几何/launcher 与 Task038 staging/watchdog 回归，也含 V19 真实 FFCx/MPC 小 FE action、V18 小 FE 的真实 LU factor/solve；`-k` 排除 N2 测试。额外执行的 V19/V18 真实 FE/factor 测试超出 N2 单一 tiny fixture 范围；总耗时为 9.20 s，各 fixture 次数与单独耗时均 `unknown`。这不是 G0/G1 正式 PDE。该运行早于 `1ee85bc`，精确 HEAD 与未提交 diff 身份未保留，记为 `unknown` |
| ledger identity 与 G0/G1 capacity fixtures | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger src/test/test_task40_nonseparable_geometry.py::test_task40_capacity_context_binds_frozen_axes_and_live_class_metadata` | `3 passed, 10 deselected in 0.76 s` | source `1ee85bc2133b783da419d31dbe429643eb2c1191`；一个 ledger fixture、G0/G1 两个 capacity fixture；不包含 PDE |
| final mesh metadata fixture | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_same_mesh_levels_preserve_air_void_audit_metadata` | `1 passed in 3.89 s` | source `59bad0d977f0e23555098d923a95afbf2e9f5bf4`；真实 G0 mesh/FE/MPC fixture，不装全局矩阵或因子 |
| compileall / diff whitespace | compileall for modified solver modules；`git diff --check` | `PASS` | 在最终 source 修复后完成；不等于 full test suite |
| full repository / MPI2/4 / Ruff / CI | 未运行 | `not_run` | 不声称 full pytest、Ruff 或 CI 通过 |

历史 focused regression suite 的原始命令（该运行早于 `1ee85bc2133b783da419d31dbe429643eb2c1191`）：

```bash
source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py src/test/test_337_task038_full3d_jit_staging.py src/test/test_task39extra_v30_monitor_policy.py src/test/test_task39extra_v19_p6_cell_condensed_action.py src/test/test_task39extra_v18_cell_condensed_core.py -k 'not n2_tiny_task40_stage4_static_condensed_diagnostic'
```

该 41 项 suite 的精确 HEAD 与未提交实现 diff SHA 未保留，因此 source identity 为 `unknown`；不能把它归到 `1ee85bc`。N2 diagnostic 则有独立运行记录：`source_head=036dec55beb0fdb1f3cae7693fddfc0225921eb9`，另绑定未提交实现 diff SHA256 `7cd587b76d90670bc396dc3e82f4641fbd1cce3b1f65d2f4c71058bb6dd977e1`。

两个 systemd service-log SHA 保留在原始 Task40 run records；日志未作为独立文件出现在本工作树，因此本轮只校验可见 artifact，不声称重新计算了这两项。 Task39 V31 首个 instrumentation failure 的原始注释仍保存在父任务记录 [`projection_layout_v31_resource_reaudit.json`](../../task039_extra_physical_multilevel/outcomes/records/projection_layout_v31_resource_reaudit.json)；该事件属于父任务。Task40 仅记录自身两次 G0 worker implementation failures，不覆盖或重分类父任务记录。

## 当前文档检查

| 检查 | 结果 | 范围 |
|---|---|---|
| 证据 JSON parse 与 identity/hash 对照 | `PASS`；10 个 JSON 可解析，G1 hash 与 geometry plan 一致；input、ledger 及当前可见的 9 个 raw run files 逐项复核 | `outcomes/records/*.json` 与 ignored raw runs |
| whitespace/diff check | `PASS`；`git diff --check` 与新增文本行尾空白检查通过 | 本轮文档与 metadata |
| Markdown fenced math / 表格 / 相对链接 | `PASS`；8 个相关 Markdown 的表格列数、围栏、相对链接检查通过；修复一条原模型登记表中指向 ignored artifact 的旧链接 | 新建/修改 Task40 Markdown 与项目索引 |
| GitHub rendered view | `NOT_VERIFIED` | 推送后尝试打开 summary、response 与 material identity 页面；页面读取返回 `Cache miss`，因此未确认 GitHub 渲染结果 |

## 2026-09-30 主控续算入口验证

资格化 complex128 / PETSc 3.19.6 环境下，`python -m pytest -q src/test/test_task40_bug_continuation.py src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger`：**4 passed in 1.10 s**。仅 mock/账本测试，无 FE/FFCx/因子：验证第三次预约保留两次历史和累计成本、授权只能消费一次、G1不获额外额度，以及授权不匹配/数值失败保持拒绝。未重跑已合格的字段修复网格 fixture。

## G0 JIT 缓存路径修复

最终组合执行 `python -m pytest -q src/test/test_task40_qualified_jit_cache.py src/test/test_task40_bug_continuation.py src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger`：**5 passed in 1.15 s**；compileall、diff 检查通过。此前隔壁单独路径 fixture 为 **1 passed in 0.19 s**，成本保留。测试只核对显式父 artifact 绑定、旧 V31 配置与账本，不建立 FE 矩阵/因子。父缓存路径是本笔记本显式配置，不声称跨机器自动可用；新 FFCx 表单仍按签名编译。


## 2026-09-30 attempt4 N6 evidence closeout

本轮只整理已落盘 attempt4 数值 Gate 和主控离线数组复核；没有改数值源码、重跑 FE/KSP/PDE，也没有新增测试。raw KSP status/reason 未持久化，callback因果为source-derived。

Task40 仓库根执行以下轻量检查，输出为：PASS: 3 JSON parse; 9 raw SHA match; identity normalization consistent.

命令1：
python3 -c 'import json,hashlib; from pathlib import Path; d=Path("docs/task40extra_0p7nm_engineering/outcomes/records"); [json.loads((d/n).read_text()) for n in ("g0_attempt4_identity_gate_stop.json","run_index.json","phase_I_results.json")]; r=Path("results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g0_iterative_v1__full3d_iterative__mpi1__Mna/20260929T230709.246850Z"); c=json.loads((d/"g0_attempt4_identity_gate_stop.json").read_text()); a={"worker_summary_sha256":"task40extra_nonseparable_0p7nm_p6q4_summary.json","run_manifest_sha256":"run_manifest.json","run_summary_sha256":"run_summary.json","watchdog_summary_sha256":"watchdog/summary.json","release_gate_packet_sha256":"release_gate_failure/v20_release_gate.json","monitor_residuals_sha256":"monitor_residuals.jsonl","iterations_sha256":"iterations.jsonl","x2_retained_final_npz_sha256":"x2_retained_final.npz","x2_terminal_residual_npz_sha256":"x2_residual_0008_0002.npz"}; assert all(hashlib.sha256((r/v).read_bytes()).hexdigest()==c["artifacts"][k] for k,v in a.items()); assert abs(c["gate_metrics"]["native_identity_difference_norm"]/c["gate_metrics"]["native_identity_operation_scale"]-c["gate_metrics"]["native_identity_relative_recomputed"])<1e-25; print("PASS: 3 JSON parse; 9 raw SHA match; identity normalization consistent.")'

命令2：
git diff --cached --check

结果：两条命令均通过。该检查不是pytest、MPI、Ruff或CI。此前targeted tests的source SHA和范围仍按历史记录保存，不归到attempt4。
