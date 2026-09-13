# Review V15 最终 selective merge 决策

当前仍为 **`NOT_APPROVED_FOR_MASTER_MERGE`**。最终新增的是 R0/R1 审计、一次 Q0 `PERFORMANCE_CONTROLLED_STOP`、Q6 `EVIDENCE_INCOMPLETE` packet 和紧凑文档；Q1–Q5 未运行，不能以剩余预算越过第三次 Q0 禁令。

| 依赖组 | 本次最终材料 | 数值行为/依赖 | 测试与 fresh PDE | 建议合入顺序 |
|---|---|---|---|---|
| production numerical/core | 无新的 production core 资格；Q0 只到 assembly | 不改 production default；无 completed core qualification/linear solve | 无 official residual、field、R/T/A 或完整 p6；Q0 是受控停止 | 不合入 production；等待新 review 与完整资格 |
| reusable runner/watchdog | 已审阅的 recovery/accounting、runtime-clock 和 watchdog 逻辑，源码 `ea5ed4cd...` | 影响运行边界/账本语义，需与现有 launcher 一起审阅；不等于 solver 通过 | targeted 24 passed；fresh Q0 为 performance controlled stop，无 Q1–Q5 | 若后续批准，先合入 runner/watchdog 与 tests；当前不合 master |
| checker/benchmark | Q6 evidence checker、compact/index 增量 | 只重算/登记原始记录，不实现求解器；Q0/Q6 结果不得升级 | Q6 packet `Q6_EVIDENCE_INCOMPLETE`；无 Q1/Q2 comparison | 可单独审阅文档化 checker，但不宣称科学资格 |
| compact evidence/docs | `response_v16.md`、`v14_io_recovery_v15.json`、V14 compact/comparison、run_index、summary、test_summary、registry、本 manifest | 不改变数值方程；保留旧 EIO、未知费用、新 Q0 负结果和 Q6 incomplete 边界 | JSON/hash/compileall/targeted tests；无 fresh PDE pass | 这是当前最小可审阅组；先于任何 production merge |
| research-only | 新 Q0 assembly 观测、未完成接口候选和所有未资格化 Schur 路径 | 只说明固定模型的资源/证据边界，不能推广到 5 nm 或作为默认 PC | Q1/Q2/Q3/Q4/Q5 `not_run_after_q0_gate` | 保留证据，不提升为 production default |
| do-not-merge | ignored `results/` 与 `benchmarks/artifacts/` 大型产物、最终/旧 ledger snapshot、临时环境与凭据 | 机器相关、不可替代的原始状态；不得重写或搬移 | compact 只保存路径/hash；无 | 不提交、不改 master、不迁移至 D: |

R0 cleanup 后 source `665a09b6a7d66eff15b4a744036d21f1dad3649d` 的全部准入通过；C: 剩余 `37233180672 B`，4 轮实际 payload `16178076 B`，累计 `32955292 B`。最终 ledger SHA `59aa33110927596a27af04382ac7830b0631fb3a1892e3460a77d812ab6b75ba`；policy debit `600 s`，按 conservative-realtime 规则结算 elapsed 字段 `613.2807354921454 s`，remaining `41983.619264507855 s`。这些是证据和账本边界，不是 master 合并批准。

---

# 历史快照：Review V14/V15 阶段合入边界

以下旧表保留各历史时点的 merge 分组；其中 R0 “没有 R1/Q0/PDE”的状态不覆盖本页上方最终收口。

## Review V15 增量边界

当前状态仍为 **`NOT_APPROVED_FOR_MASTER_MERGE`**，本轮最终运行分类为 **`INFRASTRUCTURE_BLOCKED`**。V15 只登记 R0 I/O 探针、宿主范围存储 Gate 和相应的 compact/docs；没有 R1 账本迁移、源码数值改动、新 Q0 或正式 PDE。C: 是 Ubuntu-24.04 WSL VHD 的承载卷，剩余 `827174912 B`；D: 虽有更多空间，但本轮没有使用或搬移任务。

| 依赖组 | V15 增量 | 数值行为 | 测试 / fresh PDE | 建议 |
|---|---|---|---|---|
| production numerical/core | 无新增；现有 V14 core 不因 R0 改判 | 不变 | 无新 PDE；Q0–Q6 均 `not_run_by_infrastructure_gate` | 不迁移、不提升默认；继续等待后续准入 |
| reusable runner/watchdog | 无可合入的 R1 实现；未执行草稿仅留 ignored artifact | 不变 | V14 104/30 不重跑；无新 worker | 不合入未执行草稿或临时恢复代码 |
| checker/benchmark | 无新增求解器 checker；仅更新 compact/index 引用 | 不变 | 仅 JSON/文档/hash 合同范围；不声称 solver pass | 可与 docs 一起审阅 |
| compact evidence/docs | `response_v16.md`、`v14_io_recovery_v15.json`，以及既有 V14 compact/comparison、run_index、summary/test_summary 的增量 | 无数值变化 | raw R0/host-scope hash-bound；无 fresh PDE | 这是本轮唯一可审阅的增量组，仍需统一 review |
| research-only | R1 未执行草稿、宿主探针临时文件和 ignored raw | 不提升任何算法结论 | 没有 Q1/Q2、接口 admission 或 original/notch | 保留作证据，不合入 |
| do-not-merge | 原 ledger、`old_ledger_snapshot.json`、大型 field/matrix/factor/timeline、临时环境和凭据 | 不得改变 | 无 | 不提交、不重写、不移动到 D: |

V15 的唯一 compact 记录原 ledger SHA `b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0` 前后不变；旧 `600 s` 只作为政策责任、未正式写入 ledger，旧实际耗时仍 unknown。宿主存储由用户/系统管理员处理；按后续指令沿用原 V14 合同和未用恢复额度复核准入，当前停止等待统一审核。

当前为 `NOT_APPROVED_FOR_MASTER_MERGE`。Review base 为 `25c90229410ca4f75406307ff55ea1ebad343b7b`；工程代码为 `5d239140d3931364bc16d35c45458189cd957808`，正式 Q0 仍绑定旧 source `efea244159d63a7c9db67ca091e29a9c19f9ce88`。本表划分依赖组，不能解释为批准合并。

| 依赖组 | 文件与作用 | 数值行为/依赖 | 测试和 fresh PDE | 合入建议 |
|---|---|---|---|---|
| production numerical/core | `physical_interface_schur.py`、`physical_interface_balanced.py`、`fullspace_p4_reference.py`、`fullspace_v17_p3_oracle.py` | 内部消元、物理接口 SVD/P/Q、固定周期和 BAL_H 适配；依赖现有 PETSc/MUMPS、transfer、metric；改变新显式 profile 的数值路径 | 小型代数与生命周期测试通过；新完整候选无 fresh PDE 资格 | 目前保留 research-only；正式资格后才考虑生产组，不能单独迁移适配器而漏掉核心 |
| reusable runner/watchdog | `physical_p4_schur_v14.py`、`physical_balanced_fgmres.py`、`task038_launcher.py`、`subreaper_watchdog.py` | Q1–Q6 调度、同 KSP 进展、全 PC 时间边界、账本和资源；新策略显式启用，旧默认保持 | 有限 KSP、旧策略与 watchdog 测试；没有新正式账本运行 | 依赖核心和输入配置整体审阅，不把记录读取路径作为数值成功 |
| checker/benchmark | `input_schema.py`、`input_validation.py`、`physical_intermediate_profile.py`、`task038_full3d_iterative.py`、`physical_recursive_controls.py`、七份 `input/task39extra/v14_*.dat`、相关 tests | 固定物理/资源 profile，准入和 Q6 共用原始证据检查；不重做数值求解来检查状态 | 联合测试 104 passed；准确 p4 三 RHS 配对仍缺失 | 核心→profile/dispatch→benchmark/检查，保留 explicit opt-in |
| compact evidence/docs | `response_v15.md`、`response_v16.md`、V14 compact/comparison、V15 I/O compact、run index、summary/test summary、开发登记和本表 | 无数值变化；保留 Q0 EIO、未结算费用及所有历史负结果 | raw hash、JSON、链接与文档检查；无 fresh PDE 声明 | 可以独立审阅；V15 当前仍为 `INFRASTRUCTURE_BLOCKED`，未批准 master merge |
| research-only | 本批所有新准确/近似 Schur profiles 与未资格化候选 | 仅本固定模型的机制研究，不能推广到 5 nm 或大尺度 | Q1/Q2/Q3/Q4/Q5 正式完整结果不可用 | 不提升为 production default，不以小型 PASS 代替完整物理 Gate |
| do-not-merge | ignored `results/`、`benchmarks/artifacts/` 内的 field/matrix/factor/timeline、临时环境、未结算账本及任何凭据 | 大型或机器相关运行状态 | 紧凑记录只引用路径/hash，不搬运大产物 | 不提交；不重写原账本、Review、master 或 5 nm 工作线 |

文档和工程测试的精确身份见 [response_v15](../response_v15.md) 与 [engineering evidence](records/p4_schur_v14_engineering.json)。正式结果恢复后应增量更新本表，不能追溯改判旧停止。
