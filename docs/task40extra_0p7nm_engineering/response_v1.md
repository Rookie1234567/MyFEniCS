# Response V1：Task40extra B 线 N0–N6 执行结果

> **2026-09-30 续算更新：** 用户已直接批准主控修复 Task40 续算入口。前述两次 G0 失败和 91.79305701722132 秒成本保留；本次仅增加一个绑定旧账本、输入和真实实现失败的 G0 attempt。字段修复已通过针对性检查，新增 4 项纯 mock/账本测试通过；正式续算尚未启动，未取得新数值结果。原数值/资源安全 Gate 不变，后续按原 N0–N6 条件执行。授权见 [增量记录](outcomes/records/g0_user_authorized_continuation_v1.json)。下文失败收口为此次授权前的历史状态。

## 结论先行

**没有得到真实 0.7 nm、非可分三维 p6 Maxwell 的完整 FE 解。** G0 的 336-cell 网格、p6/q4 空间与模式准备确实建立到部分 setup 阶段，但 worker 在 geometry audit 清理路径抛出实现异常；原 A6 求解、完整真残差、恢复、E/H 与 official R/T/A 都没有发生。该结论是 `WORKER_FAILED` 实现错误，不是 `NUMERICAL_FAIL`，也不是 `RESOURCE_BLOCKED`。

| 问题 | 回答 | 数据范围/证据 |
|---|---|---|
| 哪张网格、到哪一步？ | G0 计划 `6×4×14=336` cells，attempt 2 实际建成 336 cells。p6 rows `229,680`、q4 rows `69,856`；完成 native projection 检查后在 cleanup/audit 失败 | `records/run_index.json`、`records/g0_startup_bug_replay.json` |
| 求解准确到什么程度？ | G0 的 full explicit A6 residual `not_run`；没有 KSP steps、factorization、场恢复或 official power packet | `records/phase_I_results.json` |
| setup/KSP/R/T/A/内存峰值？ | G0 attempt 2 worker `87.89696 s`；KSP、factor、official R/T/A 未发生。watchdog process-tree RSS peak `1,538,707,456 B`；active cgroup `memory.peak=1,673,117,696 B`，两种口径分开报告 | `records/run_index.json`；资源定义见 `outcomes/accuracy_and_capacity.md` |
| h 细化支持工程网格吗？ | 不能判断；G1 880-cell 网格仅有 derived plan、没有运行，h agreement 为 `not_run` | `records/geometry_plan.json` |
| 谁限制目标扩展？ | 目前无法判定 p4 全局因子、端口或局部缓存谁主导；G0 失败时 p4 factor 尚未建立 | `outcomes/accuracy_and_capacity.md` |
| 下一项唯一算法候选？ | 本轮不选 Phase II 方法 | 缺少 official 解、精度差异和容量数据；重跑需 superseding review/authorization |

## N0–N6 状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| N0 | `complete` | B 线保留已有远端 Task40 分支；真实 branch ancestry/worktree 见 `branch_provenance.json` |
| N1 | `complete` | 0.7 nm 材料、解析缺口、G0/G1 网格计划和 80-mode inventory 已绑定 SHA |
| N2 | `diagnostic_pass_only` | 一个 60-cell p2 缩小求解通过其诊断检查；不冒充 p6 G0/G1 |
| N3 / G0 | `WORKER_FAILED` | 第一次 ledger identity error；一次修复重放后在缺少 `rectangular_air_void_audit` 的包装器字段处失败；重放次数已用完 |
| N4 / G1 | `not_run` | G0 没有合格结果；唯一错误重放额度用尽 |
| N5 / G0 direct | `not_run` | 没有可对照的 G0 iterative 解，直接法安全预检未运行 |
| N6 | `incomplete` | h、reference、官方物理量与容量闭环未完成 |

## 已做修复、未完成验证

`1ee85bc2133b783da419d31dbe429643eb2c1191` 让 Task40 case 的冻结 `run_id` 与 V14 ledger identity 一致，并让容量上下文读取 G0/G1 实际轴计划与 live q4 class metadata；相关 targeted fixtures 为 `3 passed`。这使唯一允许的 G0 实现错误重放越过了第一次启动问题，但发现新的几何审计 metadata 丢失错误。

`59bad0d977f0e23555098d923a95afbf2e9f5bf4` 将 Task40 缺口审计、轴统计和材料面对齐 metadata 保留在 same-mesh wrapper 中；新加的真实 G0 mesh/FE/MPC fixture `1 passed`。**这项修复没有 PDE 重放验证**，因为唯一重放已消耗；因此官方 G0 数值路径仍未被资格化。

## 资源语义更正

前面曾把 `1,538,707,456 B` 口头称为 cgroup peak，该称呼不准确：它是 watchdog 采到的 simultaneous process-tree RSS。另一个活动 cgroup 快照的 `memory.peak` 为 `1,673,117,696 B`。RSS 与 cgroup accounting 不同，不能拼接或相加；PSS 按 profile 禁用。没有观察到 swap、OOM kill 或 watchdog resource stop。

ledger 的 `workflow_seconds=43,200` 是 observe-only reference/accounting 值，并非 12 小时硬超时。最终 shared ledger 记录 elapsed `91.793057 s`、bug replay `1/1`、active attempt `null`。

## 决策

当前 N0–N6 结果按 `INCOMPLETE_WORKER_FAILED_REPLAY_BUDGET_EXHAUSTED` 收口。不得由失败启动推断 Maxwell 离散不收敛，也不得据此判断 2 TB 目标可行或不可行。G1、direct reference 和任意进一步数值重跑均不在当前一次 replay 合同内；若继续，需要后续 review 明确新的运行许可。Phase II 不选算法，生产默认不变，当前分支不合并到 `master`。

详细指标与依赖组边界见 [`outcomes/summary.md`](outcomes/summary.md)；材料/几何身份、精度/容量边界及测试分别见 [`material_and_geometry_identity.md`](outcomes/material_and_geometry_identity.md)、[`accuracy_and_capacity.md`](outcomes/accuracy_and_capacity.md) 和 [`test_summary.md`](outcomes/test_summary.md)。原始运行 artifact 留在 ignored `results/`，其可追溯 SHA 记录于 [`records/run_index.json`](outcomes/records/run_index.json)。

## G0 第三次启动失败与继续修复

第三次启动已通过原先缺失的几何审计字段，随后因 Task40 新 worktree 不含 Task39 的相对 JIT 缓存目录而发生 `FileNotFoundError`。尚未分解或进入 KSP，不是数值 Gate。全部后代已清场，累计正式成本为 **138.62440517507468 s**，原 91.79305701722132 s 保留。用户已授权修复实现 bug 后继续；本次仅修正 Task40 的合格缓存位置，缓存不命中的新表单仍在正式监督和计时内编译。新结果尚未取得。详见 `g0_jit_path_failure.json` 和增量授权记录。
