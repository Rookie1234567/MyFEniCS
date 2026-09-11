# Task39extra V11 selective merge manifest

本 manifest 只登记 Review V11 的依赖边界，不是 `master` merge approval。V11 N1 证明了显式新 policy 在两个代表块上的局部等价性；N2 在完整 retained inventory 的第 42 块前置 Gate 受控停止，因此没有 production solver 或 workstation heavy-case 资格。

| 依赖组 | 文件/内容 | 数值行为是否改变 | 测试与 fresh evidence | 建议合入顺序/结论 |
|---|---|---|---|---|
| production numerical/core | `src/io/input_schema.py`、`src/io/input_validation.py`、`src/io/physical_intermediate_profile.py`、`src/io/physical_recursive_profile.py`、`src/solvers/fullspace_bounded_mumps.py`、`src/solvers/fullspace_v17_p3_oracle.py`、`src/solvers/physical_macro_dd4.py`；以及 V11 input contracts | 改变仅发生在显式 `physical_macro_dd4_v11`；old default/V10 policy 不变 | V11 N1 equivalence pass；N2 `LOCAL_INVENTORY_RESOURCE_BLOCKED`；无完整 PDE fresh evidence | 研究审阅后才可与依赖 runner 原子评估；不得作为 ordinary default 合入 |
| reusable runner/watchdog | `scripts/run_case.py`、`src/runners/physical_macro_controls.py`、`src/runners/physical_recursive_entry.py`；调用上列 core/profile/solver | 增加可复现的 opt-in 控制、fresh-process lifecycle、inventory gate 和受控停止分类 | 37 focused tests；actual MUMPS 2 + real MUMPS 1；N1/N2 raw manifests and watchdog summaries | 不能脱离依赖 core 独立合入；若审阅允许，必须与 core 同一 research-only change group 原子处理 |
| checker/benchmark | V11 compact schema、per-block compact、`src/test/test_260_task038_input_schema.py`、`src/test/test_355_bounded_p1_factor.py`、`src/test/test_373_condensed_fine_reference.py`、`src/test/test_410_physical_macro_dd4.py`、run-index V11 registration | 不改变求解方程；checker 只重算记录字段 | compact JSON/hash、82 backsolve audit、N2 no-double-count audit | 与依赖 core/runner 一起作为 research-only group 评估；不得把 controlled negative 变成 pass |
| compact evidence/docs | `macro_memory_lifecycle_v11.md`、`macro_memory_lifecycle_v11.json`、`response_v12.md`、summary/test/handoff/progress/registry 更新 | 无数值行为改变 | JSON parse、hash/link/diff checks；完整 pytest/CI 未运行 | 可在审阅后作为 evidence/docs 合入 |
| research-only | 全部 V11 code/profile/runner wiring、N1 symbolic-sized policy comparison、N2 41-block partial inventory、`COMPACTION_UNSUPPORTED` observation | 仅研究测量；不能推出完整 outer 或 RAM 定理 | source/input/physical/ledger/raw hash-bound | 整体保持 research-only；不升格为 production capability |
| do-not-merge | ignored matrix/factor/field/cache/timeline/raw tree；任何绕过 retained inventory 的 cap/Q 修改 | 不适用 | 大型 artifact 不入 Git；N3/N4 未运行 | 不合入；若重新打开需新 review、预算和 identity |

## 固定边界

- V11 N2 的 `2,178,209,948 B > 2,147,483,648 B` 是 retained inventory + 当前 block matrix + 一次 symbolic-sized Q 的保守 Gate；不能用 measured RSS、MUMPS used 或最小值替代。
- block 41 没有 numeric factorization；`MemoryError` 是 runner 的 local/workflow gate 分类，不是 MUMPS `-9/-19` 或数学失败。
- N3 restart、N4 original/notch、p4 true error、BAL_H/ONE_C、E/H/R/T/A 和 workstation 0.7 nm 均 `not_run`。
- 当前状态为 `NOT_APPROVED_FOR_MASTER_MERGE`；source run SHA `7c936958451bc196f784ecc30db9278c4e5b402f`。V11 代码与依赖 runner 只能作为一个 research-only change group 提交审阅，不能先行拆合。
