# Task39extra Review V12 selective merge manifest

本 manifest 只登记 V12 的依赖边界，不是 master merge approval。V12 取得了真实 42 块物理宏块 inventory 和 4 条有限 bare B4/I4 控制记录，但 O1 共享预算停止；没有完整 p6 outer 或 official output。因此以下内容整体只能按 research-only / evidence closeout 审阅，不能提升 ordinary default。

| 依赖组 | 文件/内容 | 数值行为是否改变 | 测试与 fresh evidence | 建议合入顺序/结论 |
|---|---|---|---|---|
| production numerical/core | src/io/input_schema.py、src/io/input_validation.py、src/io/physical_intermediate_profile.py、src/io/physical_recursive_profile.py、src/solvers/physical_macro_dd4.py、src/solvers/fullspace_memory_first_krylov.py、src/runners/physical_recursive_controls.py、src/runners/physical_macro_v12.py、9份 input/task39extra/v12_*.dat；src/solvers/fullspace_bounded_mumps.py 是复用依赖，本轮未改 | 仅显式 physical_macro_dd4_v12 改变；V10/V11/ordinary default不变 | V12 27 focused tests；42块 inventory；4条 p4 records；无p6 official fresh evidence | 与 runner/contract 一起审阅；不得单独合入 production default |
| reusable runner/watchdog | scripts/run_case.py、src/runners/physical_macro_controls.py、src/runners/physical_recursive_entry.py、src/runners/physical_recursive_controls.py、src/runners/physical_macro_v12.py、Krylov stop/snapshot safety | 改变生命周期/受控停止记录；不改变 ordinary numerical path | 3-stop smoke PASS；O0/O1/O4 terminal/resource audits；O1 controlled stop | core后作为同一 research-only group 审阅；保留 stop semantics |
| checker/benchmark | V12 compact、raw JSON evidence、inventory/p4/resource audits、run index V12 registration、相关 tests | checker只重算原始字段，不重新实现求解器 | 759 inventory checks；88 p4 arithmetic checks；JSON/hash/diff validation | 与core/runner证据绑定审阅；不得把 controlled stop 改成 pass |
| compact evidence/docs | response_v13.md、outcomes/physical_macro_v12.md、summary/test/progress/registry/handoff、raw logs | 无数值行为改变 | raw stdout/stderr、source/input/physical/artifact SHA、p2 stage SHA | 数值/runner审阅后最后合入；只合compact和轻量raw，不合大型artifact |
| research-only | physical_macro_dd4_v12 显式分支、2.5 GiB local inventory policy、42块 MUMPS factors、C_U class factors、bare B4/I4 controls | 研究路径；局部质量未证明 full p6 solver | O1 PERFORMANCE_CONTROLLED_STOP；p4 true residual与field errors未达目标；O2/O3未运行 | 整体保持 research-only；禁止升级为 production capability |
| do-not-merge | ignored matrix/factor/field/cache/timeline/checkpoint/raw tree；任何绕过 inventory/Q/cap 的修改 | 不适用 | 大型artifact只由 raw SHA 指向；不把RSS/used替换保守inventory | 不合入；若重开需新review、预算和identity |

## 固定边界

- V12 的 42 个宏块各自是独立 numeric factor records；18 个 C_U 内部响应类因子不替代这 42 块，也不属于 DtN block factor count。
- S/p2 rows=7326、NNZ=818100、allocated/used padded=270000000/65000000 B、derived matrix+reported-factor=341069688 B < 536870912 B；这是一条与 local inventory 分开的、同时存在的 derived policy budget，原始 stages SHA 已登记。
- 4 条 record stem 的 BAL_H 是历史 packet 标签；本轮只做 bare B4/I4，没有完整 BAL_H/ONE_C outer comparison。A2R160_01/LIGHT448_09 的 residual improvement伴随 field error worsening，不能把 residual improvement写成PC强。
- p6 原方程 1e-6、restart32/64、original/notch、E/H/R/T/A、A_volume、modes、diffraction和守恒均 not_run。V5 original/notch成功与448页global swap attribution UNRESOLVED 保持历史。
- build/JIT/其他检查没有独立终态时钟，记为 unknown/included；不从O1阶段费用扣p4小计伪造build成本。
- 当前状态 NOT_APPROVED_FOR_MASTER_MERGE；ordinary default unchanged。继续必须重新绑定 source/input/artifact 和新预算，不要求修改冻结 input 本身。

---
# 历史：Task39extra Review V11 selective merge manifest

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
