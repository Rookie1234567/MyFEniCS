# Task39 T10：测试与检查摘要（Stage A 草稿）

本文只登记已完成的阶段性检查和仍待执行的 T10 final gates。它不把未运行的 full
pytest、MPI launcher contract 或 PDE 写成通过。

## 已完成的 focused evidence

| 阶段 | 已有检查/证据 | 状态 |
| --- | --- | --- |
| T1 | Task39 profile、input/provenance、dispatch、adapter 和 ordinary-default focused contracts | `pass`，见已推送 T1 commits 与 `test_268` |
| T2 | A0 compact capacity record、8 个 dat 的 validate/dry-run 与 preflight capacity contract | `pass`，见 [T2 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t2_a0_preflight_v1.json) |
| T3/T4/T5 | 正式运行 raw 的独立 compact evidence 与对应负结果/diagnostic 边界 | 已记录；不是测试替代物 |
| T9 focused closeout | 0.7 nm air-side component generator/test：`test_272` 2 passed；`test_268` 52 passed；`test_26` 14 passed；JSON、链接、Markdown math、Ruff、format、compileall、diff-check pass | `pass`，source `60d2b3caa2bc5ea71be047718eace690e5638d2b` |

T9 的生成器只读取 tracked dat 和 compact records，没有创建 mesh、组装矩阵、启动
MPI/PDE 或读取 ignored raw。详细分类和容量边界见
[0.7 nm outcome](feasibility_0p7nm.md)。

## T10 final gates：当前仍 pending

以下项目在本 Stage A 没有运行，统一保持 `pending`：

| Gate | 状态 | 边界 |
| --- | --- | --- |
| Task-focused final suite | `pending` | 不以阶段 focused 结果替代最终无 deselect suite |
| MPI1/MPI2/MPI4 launcher/ownership contract | `pending` | T10 未重新启动 MPI；T6 MPI1 numerical lane 仍 `not_run` |
| changed-Python Ruff/format/compileall | `pending` | T10 文档草稿阶段未运行新静态 Gate |
| `check_benchmarks.py --no-write` | `pending` | 未运行 |
| repository `python -m pytest -q` | `pending` | 未运行；不能声称 zero failures |
| Markdown/documentation final Gate | `pending` | 本轮只做草稿和允许的轻量 JSON/diff 检查 |

本阶段没有运行完整 0.7 nm PDE，没有恢复 neural/learned factor 路线，没有修改
master，也没有创建其他分支或 worktree。Stage A 的文档仍需主对话审查后，才可决定
是否进入最终检查和 Git 收口。
