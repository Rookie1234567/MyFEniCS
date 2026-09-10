# Task39extra V10 selective merge manifest

这是 V10 M4 的依赖组边界，不是 `master` merge approval。V10 的 macro candidate 在 M1 资源预审处未资格化；只有小型 compact/docs 证据可在最终 review 后考虑选择性合入。

| 依赖组 | 本轮范围 | 数值行为是否改变 | 依赖与验证 | fresh evidence | 建议顺序 |
|---|---|---|---|---|---|
| production numerical/core | `src/solvers/physical_macro_dd4.py`、macro profile 接线 | 是；新增 explicit-opt-in macro candidate，但未形成 production-qualified solver | 依赖 p6/p4/p2 physical actions、MUMPS、MPC/map；macro suite 9 passed，M1 full controls 未通过 | V10 M1 两次 raw；第二次 `RESOURCE_BLOCKED` | 不合入 ordinary default；如继续研究，另开 review 后再审 |
| reusable runner/watchdog | `src/runners/physical_macro_controls.py`、`src/runners/physical_recursive_entry.py`、`scripts/run_case.py` 相关 macro dispatch | 接线行为改变；只对 macro `.dat` profile 生效，旧 profile 不应改变 | 依赖 shared worker/ledger/cleanup；task-focused tests 55 passed，formal M1 没有 I4/B4 | 两次 source/input/physical/inventory hash-bound run summaries、watchdog cleanup | core 合同与 runner 边界先审，不能因静态测试提升为 production |
| checker/benchmark | V10 compact checker字段、run index、static/hash/link checks | 只增加证据读取/重算能力，不实现 solver | 依赖 ignored M1 records；compact 保存 14 个 ratio 原始分子/分母、6 个 witness 原始分子/尺度和 block7 INFOG | [V10 compact](records/physical_macro_inverse_v10.json) | 可与 compact/docs 一起审；不得重算或补造 block7 未持久化回代 |
| compact evidence/docs | `response_v11.md`、`outcomes/physical_macro_inverse_v10.md`、summary、test summary、run index、development docs、handoff、manifest | 不改变数值行为；明确 `not_run` 与负结果边界 | 依赖 compact/ledger/raw artifact hashes；`git diff --check`、JSON/link/hash checks | source `b0df745...`、input/physical/ledger/compact SHA | 最后选择性合入，保留历史 V5–V9 记录 |
| research-only | macro local inverse、42-block factor inventory、V10 dat/profile、相关 tests | 改变研究分支可选行为；不代表全局 Maxwell solver 通过 | 依赖 M1 local factorization；p4 true error、cached/native bridge、BAL/ONE、restart 均未运行 | `LOCAL_INVERSE_UNQUALIFIED` / `RESOURCE_BLOCKED` | 仅保留研究分支，等待新 review；不合 production |
| do-not-merge | `benchmarks/artifacts/task39extra/v10_m1/**`、JIT cache、matrix/factor/raw timeline、`/tmp` supervisor audit | 不合入 | 大型或环境特定运行产物；compact 只保存必要 hash-bound 标量 | raw artifact roots 和 hashes 已登记 | 保持 ignored；不得为“补完整”删除或改写负证据 |

建议选择性顺序：先审 compact/docs 与 checker，再审 runner/watchdog，最后单独审 research-only macro candidate。未取得明确 review approval 与用户授权前，不执行 merge master。
