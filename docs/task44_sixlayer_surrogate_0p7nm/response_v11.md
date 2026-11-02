# Task44 Response v11：train_011 标签与进程身份覆盖收口

## 本轮结论

主控批准 train_011 登记为 `qualified_v2_training_label`。该标签只绑定本次冻结的 P6 离散模型，表示完整数值结果、残差、能量闭合、服务退出、零 swap 和产物身份检查通过；它不表示连续解误差已收敛，也不代表 GP 开发集或盲测已通过。`sample_design_v2.json` 的计划字段保持原样，旧版 A–D 的 y/空气稳定性结论也未改写。

train_010 继续 held。它的数值 worker 确实写完官方结果并通过 residual/closure 数值门，但外层 service/watchdog 在成员身份 gate 失败后以 `MONITORING_FAILED` 结束；外层 manifest 和 run summary 保留 `launching` / null，不能提升成训练标签。当前稳定 R 状态与 direct-membership 缺口的宿主根因仍未确定；本轮不热改监控器、不重跑 PDE。

## train_011 数值、资源与标签依据

| 项目 | 实测结果 |
|---|---|
| 模型 | 六层 v2 厚度 `[0.7947163799252728, 0.8796863908804735, 0.6812293123471473, 0.7677461393481539, 0.8091205228839121, 0.6510064760601553] nm`；P6 `[3,12,8]`、288 个六面体、160 个 DtN 模态、MPI1、MUMPS exact。自由度 `197,994`，求解系统 `59,776` 行（`59,616` trace + `160` auxiliary），used NNZ `48,629,752`。静态凝聚先消去单元内部自由度来缩小全局矩阵，求解后仍恢复完整场并重算完整算子残差。 |
| 功率与吸收 | `R_total/T_total=0.09539431746138823/0.8818471128925663`；`R00_s/p/total=0.09539398436285274/1.9023763956054786e-21/0.09539398436285274`；`A_balance=0.02275856964604539`；`A_volume=0.022758569590891644`。 |
| 数值门 | full true relative residual `9.99492471986335e-10≤1e-6`；`R+T+A_volume−1=-5.515377043963099e-11`，绝对值低于 `1e-5`；160 行端口模态独立重聚合与结果记录在 `1e-12` 内一致。 |
| service 与资源 | worker `5795.535607716069 s`；service wall `5865.956483785063 s`；service/watchdog `COMPLETED`、leader exit `0`、stop event null、后代清空、unit/cgroup 清理；dedicated cgroup zero-swap gate 1,071 次采样通过、peak swap `0 B`。采样进程树 RSS peak `13,142,904,832 B`；内核 cgroup memory peak `13,865,336,832 B`，二者口径不同。 |
| 身份 | source `586e270a5c79843f6ac2c8f610859f31d430ef42`；input SHA `01935abed93b3c9378411db79059db0b8f9759fa6f44e7910babc40a3dd3a710`；physical SHA `22e725793b0e5e08691dd8f087618faecf2c8d45af01247d592e7ff044864c75`；discretization SHA `19a726fc988bf9a476f6d710494098a28919642319e864ff70bbdb5e129802e2`。 |
| 标签边界 | `qualified_v2_training_label`；原数值记录仍保留 `validation_role=numerical_sanity_only`、`physical_benchmark_candidate=false`，这些通用字段不替代 Task44 固定 v2 标签判断。标签不外推到连续解、整个厚度范围或 GP 泛化。 |

## 历史进程身份覆盖差集

我逐行读取并重算 watchdog `resources.jsonl`，将 summary 中的 `(PID,start_ticks)` observed-child 集合与每条资源行 `members` 中相同二元身份比较。1,071 行的进程树快照都报告 `identity_complete=true` 且 `all_status_readable=true`；完整观测到 37 个 child identities，其中 36 个在成员采样表出现，差集只有 `(PID 480380,start_ticks 351446618)`。它只在 row 1056、elapsed `5789.447126599029 s` 的 `live_or_unreaped_children` PID 列表出现；对应 `members` 列表没有该 PID。PID `456544`、`456567`、`456570` 在各自首次至末次出现区间的 1,068、1,067、1,066 行中连续带有相同 start ticks。

现有 raw 证据没有为 `480380` 留下 `members` 身份条目、Tgid、进程状态或该 PID 的 RSS，故角色保持 `unknown`，不推测它是编译器或其他类型子进程，也不声称它的 RSS 已测。于是 watchdog 原始字段 `process_tree_identity_coverage=incomplete_or_not_sampled`、`observed_child_identity_coverage=incomplete` 均原样保留。cgroup 的内核 memory peak 覆盖整个专属 cgroup；process-tree RSS 数值仍只称采样峰值，不将它解释为缺失 PID 的完整 RSS 记录。

派生 hash-bound 收据为 [train011 identity coverage difference](../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/train011_identity_coverage_difference_20261102.json)，SHA-256 `ec0b4c5068f36e2e0476f2d9d864ebf8c640dcf396b5297f4b54f184dab88cf1`。它引用的原始 `resources.jsonl`、watchdog/service summary、run manifest、数值 summary、场与模态文件均保留原样。

## train_010 保持 held

train_010 数值 worker 的 `R_total/T_total=0.10014744277467244/0.881888710462282`，`A_volume=0.01796384676247524`，full true relative residual `1.0163064670925226e-9` 和能量闭合误差 `-5.703215677499429e-13` 均通过。但 watchdog 因 `owned_service_member_identity_unverified` 停止；候选 PID `456276` 当时连续为 `R`，其 direct-member 检查未通过，而 service-context 列表包含它。外层 service/watchdog 分类为 `MONITORING_FAILED`，worker leader exit `-9`，外层 run manifest/summary 未转成 completed。service wall `5873.108734170906 s`，cgroup memory peak `13,877,776,384 B`，swap `0 B`，后代清空。不能用数值文件写出或前一个 monitor-fix 的历史 pass 覆盖这项当前身份缺口，因此样本仍无标签。

## 本轮文件与验证

- 更新 `outcomes/training_results_v2.md`、`outcomes/summary.md`，加入 train_011 标签及 train_010 held 状态和成本。
- 更新仓库模型总账 `docs/development_model_registry.md`，保留两个运行各自的正/负状态。
- 新增本响应和 ignored 的差集收据；未改代码、冻结设计或任何 raw PDE 输出。
- 本轮没有运行 pytest、MPI 或 PDE；完成后仅做文档 diff、hash 与工作树检查。

起始 branch `task44_sixlayer_surrogate_0p7nm`，起始 HEAD/upstream `586e270a5c79843f6ac2c8f610859f31d430ef42`。本轮改动待主控审查，不自行 commit/push。
