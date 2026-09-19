# Task39extra V22 capacity-trial incremental summary

这是对既有 `outcomes/summary.md` 的增量，不改写旧 109 份文件、旧 profile 或旧 ledger。正式 B 使用 source `57d1f601119900a52b7aa574fd4df557cfe0aa6c`；checker 字段修复已独立提交为 `cf9f2346c400612e41926e0b21b7946e9a5e6715`，不能冒充正式运行 source。

| 轴 | V22 original B 结果 | 证据边界 |
|---|---|---|
| numeric | `INFOG(1)=0`，numeric factor call completed；`INFOG(9)=INFOG(29)=221594144` 实际因子条目 | numeric 成功不等于完整求解通过 |
| continuation | `RESOURCE_CONTROLLED_STOP` | allocated upper `4688000000 B` > frozen continuation ceiling `3857054344 B` |
| used / RSS | used upper `4327000000 B`；watchdog RSS peak `6913208320 B`，numeric observer RSS `6913241088 B` | used 不可替代 allocated；实际 RSS 未越 8 GiB tree cap |
| 预算预测 | ICNTL23 request/readback/frozen=`4687 MB`；旧 V11 `INFOG16/17=5060 MB`、request=`10131 MB`；future inventory=`763172216 B`；future workspace peak=`1070871176 B` | 预测账与 native upper/RSS 分列 |
| 失败类型 | 不是 RSS 超限、不是 MUMPS `-9/-19` | `INFOG(1)=0`；停止发生在冻结续算额度门槛 |
| 三层分类 | worker=`CONTROLLED_STOP/RESOURCE_CONTROLLED_STOP`；parent=`WORKER_FAILED`；checker=`CAPACITY_EVIDENCE_VALID_AUTHORITY_LIMITED` | 原始层级不互相覆盖 |
| 物理范围 | A6、outer residual、完整 B、物理场及 C=`not_run/unknown` | 无 post-factor hash，after identity 保持 pending/unknown |
| JIT | 11 miss、0 hit，策略选择 `v21_reuse_all_qualified`；事件 elapsed=`101.78435976599758 s` | 复用未实际实现，本场编译成本保留；elapsed 嵌套于全流程 |
| 时间 | factor numeric=`217.1021214370012 s`；全场 monotonic=`493.84353463599837 s`；V22 ledger=`538.0163161130178 s` | 旧 V21 ledger `1884.4679552510706 s` 单列；已知 V21+V22 ledger=`2422.4842713640884 s`，不是 monotonic/全历史；工程时间 unknown |
| 清场 | descendants cleared，remaining pids为空，zero swap/global delta | watchdog authority raw evidence |

checker 初次运行的两个失败为 `continuation_gate_recomputed` 和 `controlled_stop_classification`；初始 JSON 已被修正版覆盖，没有伪造原始快照。真实 producer 字段为 `v22_continuation_allocated_gate_failed.facts.native_used_upper_bytes`，checker 已按此最小修复，并保留 allocated/limit/INFOG 独立重算。修正后真实结果 checker `evidence_valid=true`、capacity checks 全通过，但 `full_numerical_pass=false`、`official_result=false`。定向 checker 测试为 `6 passed`；无扩展测试。入口首次缺少显式 `observe_only` 时拒绝且未创建 attempt；Ruff 不可用且未运行，无 CI 声明，不重跑 PDE。numeric observer inventory=`1136131046 B` 是 factor 登记前 callback 账本值，不代表 numeric 后完整常驻库存；native allocated/used 另列。正式 setup 已包含在 full workflow/ledger，只有运行外工程修复和 checker 时间独立且未实测。watchdog 顶层 stage 均为 workflow；依据既有 `worker_phase.phase_started_clock.monotonic` 的阶段 RSS/时差为 `preflight 4.546213274001275 s / 428781568 B`、`setup 238.1087810299996 s / 3325509632 B`、`assembly 28.39934371599884 s / 2377670656 B`、`factor 217.8001403520011 s / 6913208320 B`、`cleanup 4.046380408999539 s / 6880735232 B`，最后一段使用 watchdog/resources.jsonl 最后一行 `parent_clock.monotonic=12527.367271841` 并含退出清场；compiler-descendant 筛选的 300 个 setup 样本峰值为 `3325509632/3288349696 B` RSS/PSS。前期实现验证记录在 ignored `benchmarks/artifacts/task39extra/b_capacity_v22/root_engineering/luna_source_ready.md` 及同目录 `supervisor_state.md` 的 Stage3 交接段：26 passed、共享回归3 passed、旧 A 只读 checker 65/65；这些集合不相加、不重复运行，全仓/CI 未跑。

机器记录见 [V22 compact](records/dual_condensed_capacity_v22_compact.json)、[V22 decision](records/dual_condensed_capacity_v22_decision.json)、[tracked checker evidence](records/dual_condensed_capacity_v22_checker.json) 和 [raw evidence index](records/dual_condensed_capacity_v22_compact.json#raw_evidence_index)。ignored [result-ready JSON](../../../benchmarks/artifacts/task39extra/b_capacity_v22/root_engineering/luna_b_result_ready.json) 仅作本地补充，不是远程审阅唯一入口。最终状态：`AWAITING_CHATGPT_REVIEW`；`no merge`、`no new PDE`。不生成重型 timeline，不改变旧证据。
