# Task041 review v2 / S5a response

## 结论先行

截至 2026-09-15，本轮 S1f 的未优化 fixed-eight-RHS baseline 在第一条代表性 RHS
之前因严格的 `process_tree_rss_limit` 受控停止。实际覆盖为 `0/8`，没有新的 RHS
等价性、数值、物理或提速结论。本轮主状态是
`controlled_negative_resource_stop`，直接原因为 `process_tree_rss_limit`；这不是数值
方法失败，也不是内存节省成功。`RESOURCE_COMPARISON_INCONCLUSIVE` 只属于旧 H3
BAL_H 的完整资源比较缺口，不能覆盖本轮 S1f 的受控资源负结果。

外层同时进程树 RSS 在原始第 7349 行达到 `53331742720 B`，超过严格 cap
`53221163008 B` `110579712 B`；host MemAvailable、job swap 和新增 global swap
仍满足各自安全线。停止不是 CPU23 邻作业或 PDE 数值 Gate；本轮 shared S0/S1/S3 的
21600 秒（6 小时）预算也未触发，不能混写成旧 48 小时预算停止。公共
`run_summary.json`仍为 `status=launching`、`exit_status=null`，所以本次终态以外层
summary、service parent summary、finalizer 和真实 systemd journal 为准。

本文件只整理 S5a；H2/H3 已完成的数值比较、H3g 事故和旧负结果不被重写。完整的
S5a 紧凑索引是
`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/s5a_completion_evidence.json`
（SHA256=`5bae6062f6ad91abf3f4dfd91e21b9ed66c90b4e8c3e8a2a1e0df3d687330c3c`）；追踪的
S0/S1 compact 为 [task041_schur_speed_v2.json](outcomes/records/task041_schur_speed_v2.json)。

## 1. 方法和实验边界

BAL_H 的通俗含义是：两侧完整的 p6 直接因子不长期驻留，改为每侧保留一个准确的
p4 粗问题因子，再用迭代平衡响应构造侧区作用。目标是降低因子内存，代价是侧区
响应需要重复求解。Maxwell 方程、全局 action/RHS、P/PH 传递、真实残差、物理量和
recovery 定义没有因为 S1f 改变。BAL_H 仍是 `research-only opt-in`，不是普通默认路径。

S0 冻结了一个八项代表性清单，用少量正/负模式覆盖两侧传播规则，再决定是否值得
进行昂贵的完整 Schur。清单绑定 packet manifest、branch/source、side、固定 ordinal、
formal column 以及生成/传播合同，不只依赖 `mode_keys`：

| side | polarity | old audit index | formal column (`index-20`) |
|---|---|---:|---:|
| bottom | positive | 227, 35 | 207, 15 |
| bottom | negative | 691, 513 | 671, 493 |
| top | positive | 330, 32 | 310, 12 |
| top | negative | 686, 513 | 666, 493 |

清单文件为 [task041_representative_rhs_v1.json](outcomes/records/task041_representative_rhs_v1.json)，
SHA256=`fb68011ed3e55861c59455d082be549cdd9f6c2d5a569015cf88bdc739f5636a`。S1f 未
materialize 任何 RHS/response owned shard，故 vector hash 为 `not_materialized`，
不能拿旧解代替。

## 2. 四个已完成模型与 S1f 位置

| 模型/方法 | p/h/M/MPI | 已有数值状态 | 时间与资源口径 | 当前结论 |
|---|---|---|---|---|
| 13.5 nm exact | p6/10 nm/120/MPI8 | H2 冻结数值比较 PASS | consumer `390.9697992079891 s`；public resource contract PASS | exact reference |
| 13.5 nm BAL_H | p6/10 nm/120/MPI8 | H2 冻结数值比较 PASS | consumer `3002.409810984973 s`；consumer resource PASS；RSS 比 exact 少 `254894080 B`（`2.707606%`） | 同模型已测对照；约慢 `7.68x`，不外推到5 nm |
| 5 nm exact | p6/4 nm/480/MPI8 | H3 五残差、R/T/A、fields、canonical 和 comparison PASS | consumer `1868.4593736410607 s`；完整 consumer RSS/PSS/USS=`89123696640/87368944640/87121264640 B` | H3 exact reference |
| 5 nm BAL_H（H3） | p6/4 nm/480/MPI8 | frozen numerical/comparison contract PASS；公共资源证据不完整 | worker `191662.819902868 s`；Schur `183016.74211002886 s`；public/orphan resource authority 未资格化 | `RESOURCE_COMPARISON_INCONCLUSIVE` |
| 5 nm BAL_H S1f fixed-eight | p6/4 nm/480/MPI8 | 到达 `top_factor_setup_begin`，代表性 RHS `0/8` | outer phase `2221.4903851540294 s`；同时树 RSS 超 cap | controlled resource stop；无新数值结果 |

S1f 配置仍为 inner `128/0.01`、outer restart `32`/max `2048`/rtol `5e-9`、zero
start、MPI8×1、OS CPU0–7、M480、p6 factor 0、每侧 p4 factor 1。S1f 没有进入完整
Schur、outer、recovery 或 official RTA。

## 3. S0 旧归因与 S1 工程证据

旧 H3 candidate RHS raw 文件为
`/home/fenics/Projects/MyFEniCS/results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260912T075551.700563Z/consumer/numerical_output/balh_side_rhs_audits.jsonl`，
3,852,327 B，SHA256=`b84de36f3eacd82eab6ff8fad03c689bb49476efb153e7c4096fcdf61b3fc51b`。
它有 1980 行：cost `8`、modal `1952`（两侧各976，含32 sample，正式1920）、
outer `20`；1978 行 KSP converged（reason 2），2 行 exact zero RHS。inner iterations
合计 `30295`，单 RHS 最大 `112`，显式 inner residual 最大 `0.009989594141011119`。
计数和是调用次数，不是可相加 wall：`pc/H6/J/JH=30295`，
`A6/P/Q/PH_audit/p4_backsolve=60590`，`PH_total=121180`，`p4_refinement=0`，
`side_A=32333`，`checkpoint=183748`。日志中的 `per_rank_accumulated_seconds` 是
写日志 rank 的 local 字典，不能恢复 campaign rank-max 总和，也不能把逐行 max 相加
冒充父 wall。

S0 已完成的归因统计另存于
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/task041_schur_speed_v2_s1a_3890cdd2/s0_rhs_statistics_v2.json`
（18,352 B，SHA=`36781c22a3565d70ed37364c94a0c2ec104b12279bbad0a8f27c06f2ef8917cf`）。
它按 bottom/top 与 cost、modal（含 sample 与正式 960）、outer 分列 RHS wall 总和、
median/p90/max、Q/H6/A6 和 uncovered；这些是逐 RHS logging-rank max 的累计诊断，
不是父 wall 或 campaign rank-max，完整紧凑表见中心报告和 S0/S1 compact。

S1a–S1e 完成的是接口/计时/监督与固定入口资格：BAL_H P/PH、p4/A4/A6/H6/Q 细分
计时链，service parent/finalizer pure mocks，finite RHS binding，以及 105 个通过的
focused pytest；Ruff、compileall、diff-check 是另外的静态检查，不计入这个 105。该
提交集确实包含 BAL_H 数值 core 与计时适配，但没有 A–D 等价性能优化；它们没有证明
S1f 的 8 RHS 数值或性能收益。源码/测试绑定到提交
`1c1d36b168bfb3939314ee2faf5b943cca804382`。

## 4. S1f 资源、阶段和停止证据

外层 authority memory 文件为：
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/s1e_preparation_20260915_1c1d36b1/unoptimized_rhs_baseline_1c1d36b1/memory_stages.jsonl`，
7350 行、26,113,795 B，SHA=`5a46a99427c7d82e5c4eb9d8209b887e0a33c66f5ff865ae12df0c786e75c5b8`。

| 事件 | raw 证据 |
|---|---|
| 首次90% warning | line 7313，elapsed `2210.5727085701656 s`，RSS `47914586112 B`，threshold `47899046707 B` |
| 首次且唯一 cap 超限/峰 | line 7349，elapsed `2221.3724097050726 s`，RSS `53331742720 B`，cap `53221163008 B`，超出 `110579712 B` |
| 峰值组成 | 同行各 PID RSS 求和精确等于 `53331742720 B`；不是 cgroup `memory.current` 替代 |
| 稀疏 PSS/USS | observed peak `40538401792/40140140544 B`；74 条 smaps-complete、7276 条缺测；不是同一 RSS 时刻 |
| sampling | RSS/VmSwap 设定 `0.25 s`，PSS/USS 稀疏周期 `30 s`，最大相邻间隔 `0.8098343990277499 s` |
| swap/reserve | job swap `0`；global baseline `8192 B`、pswpin `0`、pswpout `2`，新增 delta 均为 `0`；reserve 未触发 |
| terminal row | line 7350 只剩监督 root RSS `39407616 B`；这是清理后低点，不能覆盖峰值 |

严格 RSS cap 是同时 process-tree RSS，不是 cgroup `memory.current`。hard memory
`274877906944 B` 与 host/cgroup reserve `412316860416 B` 是独立安全线；它们通过并
不豁免 simultaneous-RSS cap。public-only memory 段峰 `53134987264 B` 不含外层 service
parent，不能用来扣除监督器后声称不超 cap。

阶段停在 `top_factor_setup_begin`。外层返回 `-15`，`termination_reason=process_tree_rss_limit`，
`process_group_gone=true`；所以新 fixed-eight representative RHS 为 `0/8`，full
Schur、outer、recovery、official RTA 和任何优化对照均为 `not_run`。

## 5. 生命周期与时间结账

外层 POSIX 阶段在 RSS Gate 后对 public group 发出 SIGTERM，并报告被管理 PGID gone；
这不等于所有 MPI 成员已自然退出。parent pre-exit summary 仍列出 mpiexec/ranks，
`pre_exit_members_clean=false`。之后 systemd `KillMode=control-group` 清理 service
cgroup；finalizer 的 `post_cgroup_finalizer_only=true` 只表示 post 时 cgroup 中只剩
finalizer，不能反写前一阶段为自然成功。

finalizer 原始状态为 `status=failed`、`result_classification=service_boundary_failure`，
`SERVICE_RESULT=exit-code`、`EXIT_CODE=exited`、`EXIT_STATUS=3`；关闭文件 hash 阶段
本身 returncode `0`，但 `pre_exit_members_clean=false`、`public_result_completed=false`、
`service_terminal_normal=false` 均保留。已知 Task041 PID 最终从 host `/proc` 消失，
邻近 Full3D PID `1652293/1652340/1652343` 未触碰。

| 计时层 | 实际值 | 口径 |
|---|---:|---|
| outer phase | `2221.4903851540294 s` | `_run_phase` phase wall |
| service parent | `2221.674698243 s` | unit start 到 parent summary；不是完整 post wall |
| finalizer unit | `2223.491907262 s` | unit monotonic start 到 finalizer 收口；账本已写入一次 |
| terminal envelope | `2223.517343 s`；journal `Consumed`=`2026-09-15T05:39:48.195160Z` | 由 unit start `1558321618156000 ns` 到 raw journal `__MONOTONIC_TIMESTAMP=1560545135499 us`；早期 finalizer 记录 `05:39:48.194451Z` 保留，不与前两行相加 |
| journal CPU | `5h 8min 46.354s` | CPU time 说明，不是 wall，不计入账本 |

该 unit 的精确六条原始 journal 已保存为
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/task041-s1e-rhs-baseline-1c1d36b1.journal.jsonl`
（6 行，SHA=`33b847ddf7206e33e876d290cb9130fcff55c90c07c55eb28aa55889694b2d96`）。
其中 `SERVICE_RESULT=exit-code`、`EXIT_STATUS=3` 和 `Consumed` 行均绑定同一
Invocation；systemd 的 CPU sum 与 `33.9G` memory 字段只是 systemd 诊断，不替代
外层 process-tree RSS 或 monotonic wall。

唯一 V2 ledger 当前为
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/task041_schur_speed_v2_s1a_3890cdd2/task041_schur_speed_v2_compute_wall_ledger.json`，
SHA=`902e8bbd40c5df4cbfef0a1f9c501d33575516e084fed6a10c54c275add26f7a`，
`used_compute_wall_seconds=2881.0536036838917 s`，shared S0/S1/S3 remaining
`18718.946396316107 s`，batch remaining `198718.9463963161 s`，S2/S4 均为 `0`。
其中 S1f finalizer 的 `2223.491907262 s` 已收费一次；raw journal `Consumed` 外包络与其
差 `0.025435738 s` 已作为一次 terminal-tail 追加；两次独立文档检查外层 wall
`1.125902230 s` 与 `1.110528022 s` 也各收费一次，共 `2.236430252 s`。未保存的完整
S1f preflight 外层 wall 保持 `unknown`，不填零。

## 6. 完成、未运行和合入边界

| 维度 | S5a 事实 |
|---|---|
| numerical | 新 fixed-eight RHS `not_run`（`0/8`）；H2/H3 既有数值比较不变 |
| time | measured to resource stop；no speedup measurement |
| memory | strict outer RSS cap failed by `110579712 B`；PSS/USS sparse diagnostic only |
| coverage | outer authority memory 7350 行、post memory 2 行及 terminal evidence 已保留；到达 top factor setup，但没有 representative response shard 或自然完整 consumer 覆盖 |
| producer/QEP | S1f not run；继承的 H3 packet 只读保留 |
| optimized/A-D | not run；没有新算法、精度或矩阵改变 |
| Full3D secondary | `not_run`；邻作业只读保护 |

Selective merge 仍按依赖组处理：

1. `production numerical/core`：S5a 本身没有新增数值算法；本次已审提交集包含 BAL_H
   numerical core/计时适配，改变研究 opt-in 路径但保留 exact/default 行为，不能因 S1f
   负结果升为默认。
2. `reusable runner/watchdog`：profile/有限入口/有界 I/O/service 逻辑已有 focused
   evidence；S1f 的严格 cap 负结果不等于完整 heavy-service 资格。
3. `checker/benchmark`：固定 RHS manifest、计时字段和原始重算合同可复用；不把 `0/8`
   转成 numerical pass。
4. `compact evidence/docs`：本文件、[中心报告](outcomes/schur_speed_v2.md)、[S0/S1
   compact](outcomes/records/task041_schur_speed_v2.json) 及 summary/test summary 保存
   路径与 hash；大 memory、mesh、matrix、factor 和场仍在 ignored results。
5. `research-only`：BAL_H opt-in、`task041_schur_speed_v2`、固定八 RHS 研究入口；需要
   新的资源准入和真实数值证据才能继续。
6. `do-not-merge`：incident-specific orphan sampler、固定 PID 临时监控、大型 raw
   artifacts 和未资格化生产实现；S1f/H3g 的负结果文档与 compact 必须保留并可提交，
   但不能作为生产 watchdog 或内存节省证明。

本轮没有 master approval，没有 optimized8、13.5 nm 新运行、新 producer/QEP、Full3D
secondary 或 full repository CI 结果。旧 H3e `SETUP_COST_BLOCKED`、H3g 监控事故和所有
此前负结果继续保留。

## 7. 已运行入口（仅复现说明）

下面是已运行的 service parent 入口，不表示应再次启动：

已运行的完整 `systemd_run_argv`、`ExecStopPost`、日志参数和 `WorkingDirectory` 均保存在
冻结配置
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/s1e_preparation_20260915_1c1d36b1/unoptimized_rhs_baseline_config.json`
（SHA=`128efc75837a2e2b549cc9b945268b71cd6dad4d05c194c889286ac481d0a9c1`）的
`native_service_commands.systemd_run_argv` 中；这里不复制一个可能被误用的残缺命令。
该配置对应 `Type=exec`、`KillMode=control-group`、`Restart=no`，public 无 outer
`mpiexec`，实际 worker 才启动 MPI8。

public command、profile、legacy packet descriptor 和 fixed RHS manifest 均由 launch
manifest 绑定；没有 outer `mpiexec`，实际 worker 才启动 MPI8。若以后获批，必须用新的
clean source、unit 和 root 重新审查，不能把这次 `0/8` 当成优化候选。
