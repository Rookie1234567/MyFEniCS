# Task40extra 测试与文档检查摘要

## 测试结果

| 范围 | 命令/输入 | 结果 | 证据边界 |
|---|---|---|---|
| N2 tiny p2 diagnostic | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_n2_tiny_task40_stage4_static_condensed_diagnostic` | `1 passed`；solver `8.608 s` | source `036dec55beb0fdb1f3cae7693fddfc0225921eb9`；60-cell p2 diagnostic，不是 G0/G1 official |
| Task40 profile smoke/identity suite（历史阶段） | Task40-focused suite，修复前 source 范围 | `41 passed, 1 deselected in 9.20 s` | 历史测试；未覆盖其后的两项修复 |
| ledger identity 与 G0/G1 capacity fixtures | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger src/test/test_task40_nonseparable_geometry.py::test_task40_capacity_context_binds_frozen_axes_and_live_class_metadata` | `3 passed, 10 deselected in 0.76 s` | source `1ee85bc2133b783da419d31dbe429643eb2c1191`；一个 ledger fixture、G0/G1 两个 capacity fixture；不包含 PDE |
| final mesh metadata fixture | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_same_mesh_levels_preserve_air_void_audit_metadata` | `1 passed in 3.89 s` | source `59bad0d977f0e23555098d923a95afbf2e9f5bf4`；真实 G0 mesh/FE/MPC fixture，不装全局矩阵或因子 |
| compileall / diff whitespace | compileall for modified solver modules；`git diff --check` | `PASS` | 在最终 source 修复后完成；不等于 full test suite |
| full repository / MPI2/4 / Ruff / CI | 未运行 | `not_run` | 不声称 full pytest、Ruff 或 CI 通过 |

两个 systemd service-log SHA 保留在原始 Task40 run records；日志未作为独立文件出现在本工作树，因此本轮只校验可见 artifact，不声称重新计算了这两项。 Task39 V31 首个 instrumentation failure 的原始注释仍保存在父任务记录 [`projection_layout_v31_resource_reaudit.json`](../../task039_extra_physical_multilevel/outcomes/records/projection_layout_v31_resource_reaudit.json)；该事件属于父任务。Task40 仅记录自身两次 G0 worker implementation failures，不覆盖或重分类父任务记录。

## 当前文档检查

| 检查 | 结果 | 范围 |
|---|---|---|
| 证据 JSON parse 与 identity/hash 对照 | `PASS`；10 个 JSON 可解析，G1 hash 与 geometry plan 一致；input、ledger 及当前可见的 9 个 raw run files 逐项复核 | `outcomes/records/*.json` 与 ignored raw runs |
| whitespace/diff check | `PASS`；`git diff --check` 与新增文本行尾空白检查通过 | 本轮文档与 metadata |
| Markdown fenced math / 表格 / 相对链接 | `PASS`；8 个相关 Markdown 的表格列数、围栏、相对链接检查通过；修复一条原模型登记表中指向 ignored artifact 的旧链接 | 新建/修改 Task40 Markdown 与项目索引 |
| GitHub rendered view | 尚未核验 | 推送后查看；若 GitHub 无法取回页面，将明确报告 `NOT_VERIFIED` |
