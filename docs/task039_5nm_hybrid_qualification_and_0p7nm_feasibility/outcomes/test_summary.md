# Task39 T10：测试与检查摘要

本文登记 Task39 已完成的 focused、MPI tiny fixture、静态和文档检查。最终 repository
pytest 按用户于 2026-08-12 的成本覆盖明确取消，状态为 `cancelled / not_run`；不将其写成
通过、zero failures 或 CI 结果。

## 已完成的 focused evidence

| 阶段 | 已有检查/证据 | 状态 |
| --- | --- | --- |
| T1 | Task39 profile、input/provenance、dispatch、adapter 和 ordinary-default focused contracts | `pass`，见已推送 T1 commits 与 `test_268` |
| T2 | A0 compact capacity record、8 个 dat 的 validate/dry-run 与 preflight capacity contract | `pass`，见 [T2 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t2_a0_preflight_v1.json) |
| T3/T4/T5 | 正式运行 raw 的独立 compact evidence 与对应负结果/diagnostic 边界 | 已记录；不是测试替代物 |
| T9 focused closeout | 0.7 nm air-side component generator/test：`test_272` 2 passed；`test_268` 52 passed；`test_26` 14 passed；JSON、链接、Markdown math、Ruff、format、compileall、diff-check pass | `pass`，source `60d2b3caa2bc5ea71be047718eace690e5638d2b` |
| T10 B1 | ABI qualified；Task39 focused `86 passed`；MPI1/2/4 tiny DtN fixture pass；Ruff check、31-file changed-Python format-check、compileall、`check_benchmarks` `302/302`、compact JSON、链接、fenced math、表格列数、diff-check pass | `pass`，code/static parent `b737c62149186356a1c07c267f473e360274cc8a` |

T9 的生成器只读取 tracked dat 和 compact records，没有创建 mesh、组装矩阵、启动
MPI/PDE 或读取 ignored raw。详细分类和容量边界见
[0.7 nm outcome](feasibility_0p7nm.md)。

## T10 结项边界

以下结果如实保留：

| Gate | 状态 | 边界 |
| --- | --- | --- |
| Task-focused final suite | `pass` | focused Task39 suite `86 passed`；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| MPI1/MPI2/MPI4 launcher/ownership contract | `pass` | tiny DtN fixture；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a`；不等同于 T6 numerical lane，T6 仍 `not_run` |
| changed-Python Ruff/format/compileall | `pass` | 31-file scoped format-check、Ruff check、compileall；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| `check_benchmarks.py --no-write` | `pass` | `302/302`；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| repository `python -m pytest -q` | `cancelled / not_run` | 用户于 2026-08-12 为节省时间明确取消；无 zero-failures 或 CI 声明 |
| Markdown/documentation final Gate | `pass` | compact JSON、相对链接、fenced math、表格列数、diff-check |

本任务没有运行完整 0.7 nm PDE，没有恢复 neural/learned factor 路线，没有修改
master，也没有创建其他分支或 worktree。首轮 focused pytest 包装曾丢失 final exit/summary，
随后同一命令以可恢复 session 正式重跑并通过；一次误下发的全目录 Ruff format probe 报告
247 个历史文件需格式化，未批量修改，最终以权威 31-file changed-Python scoped Gate 通过。
上述 T10 B1 代码和静态检查的历史 parent SHA 为
`b737c62149186356a1c07c267f473e360274cc8a`；Review V1 当前代码的最终轻量 Gate
已在 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` 上完成。后续最终
docs-only closeout 不再改变 Python、config 或 schema；本 Gate 对应上述已提交内容。

## E6 Review V1 H-field diagnostic closeout

| 检查/证据 | 状态 | 说明 |
| --- | --- | --- |
| E6 implementation regression | `pass` | `test_273_task039_review_v1_contracts.py` + `test_274_task039_h_field_diagnostic.py`：22 passed |
| changed Python Ruff check/format/compileall/diff-check | `pass` | 仅 E6 序列化修复涉及的两文件；commit `af75d8c73c72cd9340191f7fb332227496e62509` |
| offline Hybrid/Full3D comparison | `pass` | `diagnostic_complete=true`、`numeric_gate_pass=true`；classification=`M480_H_DISCREPANCY_UNRESOLVED` |
| comparison payload identity | `pass` | Hybrid/Full3D payload、metadata 和 output SHA 见 E6 outcome |
| M480 Hybrid direct MPI8 diagnostic rerun | `completed exactly once` | 按 Review 冻结合同执行；最终 compare 消费该次 payload |
| Full3D new solve | `not_run` | 仅进行了既有 canonical replay |
| E7（首轮 T10 snapshot） | `historical not_run` | 首轮 E6 closeout 后停下；Review V1 extension 随后独立完成 E7 |

`pass` 在上表表示实现/离线比较命令成功，不表示 Full3D 或 production validation 成功；
历史 T3–T5 negative/qualification 边界保持不变。

## Review V1 extension checks

| 阶段 | 检查/证据 | 状态 |
| --- | --- | --- |
| E7 family audit | 四档 hash-bound JSON/NPZ、两侧矩阵、finite、sign/order、repeat、backward error | `pass`；family classification=`M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_PASS` |
| E7 M960 direct | own residual、projection、exact traction、canonical online Gate、R/T/A、closure、604 keys、resource | `pass` own authority；`official_record=false` 是 M/model qualification pending |
| E7 offline comparisons | M480-vs-M960 pass；h10/h6 comparison 的 H/model negative 如实保留 | `pass` checker execution；不是 Full3D qualification |
| E8/E9 | Hybrid iterative MPI8/MPI1 | `not_run_by_review_v1_7p3_stop_after_m960_direct` |
| E10 | global RSS/PSS/USS、历史 RSS series、stage attribution boundary | `pass` evidence closeout；stage-aligned snapshots `not_available` |
| repository full pytest | 全仓 `python -m pytest -q` | `cancelled / not_run`；用户成本覆盖，不是 pass |

Review V1 extension 未运行新的 Full3D/Hybrid iterative/0.7 nm PDE；没有开发新 PC、
modal matrix-free 或 neural 路线。详细数值见 [M960 audit](m960_trace_numerical_audit.md)、
[iterative boundary](m480_hybrid_iterative_solver_diagnostic.md) 和
[memory forensics](memory_lifecycle_forensics.md)。

## Review V1 final light Gate

以下是当前 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` 上完成的最终轻量
Gate；它们不改写上面的历史 T10 B1 结果。全仓 `python -m pytest -q` 仍按用户成本覆盖为
`cancelled / not_run`。

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| ABI preflight | `pass` | qualified activation；仓库 `.venv`；PETSc complex128/int32；同一 Linux ABI |
| Task39 focused（8 个文件） | `132 passed, 1 skipped` | 当前 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` |
| targeted `test_40`/`test_275` | `17 passed, 1 skipped` | 当前 code parent |
| MPI tiny DtN | `MPI1/MPI2/MPI4 pass` | ranks 1/2/4；tiny fixture，不是 PDE |
| official dat validate/dry-run | `26/26 pass` | 13 个 dat × 2；未启动 worker/PDE |
| Ruff check/format-check | `24/24 pass` | 24 个 changed Python |
| compileall | `pass` | `src`、`benchmarks`、`scripts` |
| `check_benchmarks --no-write` | `302/302 pass` | 无写入 |
| compact JSON | `17 parsed` | Task39 records |
| 文档合同 | `7/7 pass` | 相对链接、fenced math、表格列数 |
| `git diff --check` | `pass` | 当前工作树 |
| 全仓 repository pytest | `cancelled / not_run` | 用户成本覆盖；不代表 pass 或 zero failures |
