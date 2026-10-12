# Task041 Review V12 执行回应：有界模态备选与 W0.7 准备包

> **历史时点说明：**下文“当前阶段”和“warm准备包”章节记录的是2026-10-10 dispatch前的准备状态，原文保留作为历史快照。唯一后续Invocation及其负终态见本目录的[Response V15](response_v15.md)与[outcomes summary](outcomes/summary.md)；此注记不改变原raw或负结果。

## 当前阶段（历史准备时点）

两侧 P4 因子已经能够完成；此前停止在固定 8 步的模态辅助求解没有达到 `1e-3`，所以还没有合格的全场。本阶段提交了一个有界的继续策略：先用原 fixed-H6；只有满足已封存的正常返回与可信向量条件，才最多切换一次 fixed physical BAL_H。它试图让原外层求解器有一次有限继续机会，不改变原 Maxwell 方程、P4 精度门或最终验收门。

该准备时点的状态是**代码已提交、合同测试按 attempt 分批通过、warm 包已准备、尚未 dispatch**。这不是 FE 数值结果，也不是 W0.7 资格通过。

## 代码与测试证据

代码提交为 `eca72c8b12e2b979f919cb5b69578ad99111fef0`，parent 为 `8af296d9cbe41e7132e9e623574d9b9a5fb5fdda`，位于原任务分支；upstream 同步 `0/0`。提交仅含 11 个已审路径：

| 类别 | 路径 |
|---|---|
| workflow | `benchmarks/task041_balh_workflow.py`、`benchmarks/task041_exact_side_workflow.py` |
| launcher/service/supervisor | `scripts/run_case.py`、`src/runners/task038_launcher.py`、`src/runners/task041_service.py`、`src/runners/task041_supervisor.py` |
| solver | `src/solvers/hybrid_fem_modal_block_ldu.py`、`src/solvers/physical_balanced_side_inverse.py` |
| tests | `src/test/test_349_task041_balh_side_inverse.py`、`src/test/test_350_task041_balh_block_ldu.py`、`src/test/test_351_task041_balh_public_workflow.py` |

共 15 个实际 pytest parent attempt，父 `CLOCK_MONOTONIC` wall 合计 `184.67645929614082 s`；V5 从 218 项变为 233 项，新增 wall 只计一次，V5 SHA 为 `18bca854947d3dbfecc2081153469e70d5b395dd70e507bd0a1c3ac9400378f1`。serial、MPI2 与公共 setup/route 回归分批执行；早期 fixture/接线失败均保留。MPI2 的 rank-local 快照断言失败及其后修正也保留。没有一个 attempt 覆盖最终提交的整组 11 个文件，因此不称“最终 SHA 单次全组通过”。

每个 attempt 的 argv、stdout、attempt SHA、清理状态和逐路径 source SHA 见 [attempt compact](../../results/task041_v12_a2_setup_public_bridge_scope_fix_fixturefix16_20261010T0814Z/v12_a2_test_attempts_compact.json)，SHA `6b7338fb08996301c37d2c637ab7637d0a729c8c3de44e777cfcd7663dd63406`。原始追加记录见 [V5 append receipt](../../results/task041_v12_a2_setup_public_bridge_scope_fix_fixturefix16_20261010T0814Z/v5_append_receipt.json)，SHA `7860a1cd263248d5ca3320396bd51bb1e8f1dcf5cb259f72774f52c7c22faff8`。34 条 runtime 与 5 条 test source 共 39 条绑定，逐条比对 commit HEAD 的 blob OID/hash 与工作树；`source_bindings.json` SHA 为 `ecfbf7c4650fa47951b8a5a727717b1edb68d428d75146dedc56bfbf1e8294bb`。

attempt 结果按阶段收敛如下；详细 pass/fail/skip 数及全部源码 SHA 以 compact 为准。

| 阶段 | 结果 | 说明 |
|---|---|---|
| serial attempts 1–9 | 多次局部失败，均留存 | 覆盖 fixture 参数/证据、restart helper、outer 顺序、backup stop 委托、identity 和诊断键等定位；不是数值门放宽 |
| serial attempt 10 | 2 passed | 实际 selector：`test_v12_backup_does_not_fallback_after_primary_matmult_exception` 与 `test_task041_v12_backup_service_and_supervisor_bind_one_switch`；不是 restart64 选择/捕获测试 |
| MPI2 attempt 11 | 单条 pytest 摘要为 `1 failed, 12 passed`，parent wall `133.939134262 s` | 失败在 `test_v12_finite_stop_waits_for_resolved_trial_and_two_fresh_windows` 的 owner-only snapshot 计数断言；non-owner 得到空列表。紧接该 rank-local 断言的 collective 造成另一 rank 等待。raw 只保留 1/2 预期 rank 摘要且无 rank 身份，不据此声称任一 rank 或双 rank 通过；保留原 stdout 并按本次进程组合同清理 |
| MPI2 attempt 12 | 每 rank 各 5 passed | 实际五项均为 test350：`test_v12_backup_switches_after_normal_primary_refusal_and_keeps_outer_residual`、`test_v12_backup_outer_stagnation_switches_at_next_pc_and_terminal_can_cancel`、`test_v12_finite_stop_waits_for_resolved_trial_and_two_fresh_windows`、`test_v12_restart32_restore_capacity_stop_retains_x_and_rhs`、`test_v12_backup_does_not_fallback_after_primary_matmult_exception`。不是 restart64 选择/捕获组，也不是 FE |
| serial attempts 13–14 | 两个接线/fixture 失败，保留 | staged bridge scope 与 default trial state 问题随后窄修 |
| serial attempt 15 | 2 passed，wall `5.392439984 s` | 实际 setup helper 与显式 public backup route 边界；对应本轮最后修正的入口 |

small-matrix 合同只验证固定算法边界、同因子借用、有限停止和身份传递，不证明 M400/MPI8 上的 modal 收敛或最终物理量。

## V12 W0.7 warm 准备包（历史封存状态）

| 项目 | 已封存值 | 证据边界 |
|---|---|---|
| 包 | 修正后的派生包 `results/task041_v12_w0p7_bounded_modal_backup_policy_only_preparation_20261010T085320Z/`；17 项 payload，SHA256SUMS 全过 | 原 `...bounded_modal_backup_warm_preparation_20261010T082109Z/` 保留为 method/policy 冲突的负准备证据；派生包不授权 dispatch |
| 源码 | HEAD `eca72c8b12e2b979f919cb5b69578ad99111fef0`；source binding SHA `ecfbf7c4650fa47951b8a5a727717b1edb68d428d75146dedc56bfbf1e8294bb` | 39 条逐文件 HEAD blob/worktree 匹配；准备后需保持源冻结 |
| config / argv | config SHA `d9dcbb98be62870d1db14e9da1a206d9c00b80a7534e81d6c85be71646bae460`；systemd argv SHA `849ee146a1a2548a5ef51e428d721470f79b7e3a6319e4f261364661edb91674`；checksum 清单 SHA `c637c41920f371f9b4ec6dc9cd11a2b078c04537cef075cb9054b6d2031439ee` | `modal_feedback_method=null`，public argv 无该 flag，只保留 fixed-H6 与 once-backup policy；service parent、ExecStopPost 和 argv 数组使用同一 config 路径；dispatch/started 均为 false |
| unit / runroot | `task041-v12-w0p7-bounded-modal-backup-policy-only-cpu10-11-14-15-16-17-18-19-20261010T085320Z.service`；`results/task041_v12_w0p7_bounded_modal_backup_policy_only_run_20261010T085320Z/` | 新路径在派生时不存在；旧包 08:24 host admission 只属父包，不能作为新 unit/runroot 的 fresh 门 |
| policy | 唯一请求 `task041_v12_bounded_inexact_modal_once_backup`；初始 `fixed_h6_modal_gmres_research`；最多一次条件 backup `fixed_physical_balh_once_modal_gmres_research` | service resolve 与 public CLI `--validate-only` 已通过；实际方法仍未运行。只有可信正常返回/触发条件可切换；异常、非有限值或身份/布局错误不走 backup |
| 方法与原门 | modal `max_it/restart=32/32`，target `1e-3`，approximate-PC 上限 `eta<=0.1`，solver/total S action `34/35`；P4 target `5e-13`、最多2次；原五项真残差、A4 与物理门不变 | 不把内层 approximate return 当原方程通过；最终全场仍须通过原门 |
| 资源 | hard `85,899,345,920 B`，warning `77,309,411,328 B`，W `8,589,934,592 B`，node0 floor `412,316,860,416 B`；不设 elapsed stop；V8 资源绑定中的 swap 仅观察 | case cap 是停止上限，不是峰值预测；正式调用前还须重新核 host/node0/cgroup/disk |
| producer / bridge | producer source `2708214386d38bd69f73e6b196c8ed843bb53d81`；manifest `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`；identity `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`；bridge SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b` | 复用 producer，QEP=0；准备阶段未读大 shards/未跑完整 validator。正式 consumer 仍沿既有 envelope validation 与 packet reader/hydration |
| resolve / validate-only | receipt SHA `9ba7bfc5699588d64a9a5d8210580cd6262ee881b88cee4d572c35985b27f720` | service `_service_contract` 解析为纯 fixed-H6 primary + once-backup policy；public argv 追加 `--validate-only` 返回 `valid`。只读五个小 envelope JSON，不读 shards、不调用 launcher/service、不做数值计算 |
| host admission | 父包 raw SHA `9afef4e5aac0bdff309040984653965c9e680730f3ab43e9bb037e6884ea1a0a`；assessment SHA `ae4fc65137778eab4841529c14158175d324c978f01e6fab5f117a1b3bffba82` | 2026-10-10 08:24 UTC 两点样本仅对应旧父包；派生 unit 当前尚未做 fresh host 门。候选 CPU tuple 保留作准备值，`performance_not_isolated=true` |

宿主样本时 node0 MemFree 为 `536,991,444,992 B`，扣 floor 后余 `124,674,584,576 B`，再扣 case cap 后余 `38,775,238,656 B`；host MemAvailable 为 `1,915,557,838,848 B`，host 减 floor、reserve 与 cap 后余 `1,417,341,632,512 B`。cgroup `memory.max/high=max`，磁盘可用 `2,993,063,002,112 B`。这些都是该次采样读数；dispatch 前必须重新采样。详细 raw/assessment 位于准备包 `fresh_host_admission/`。

复用了同 CPU map、同 native stack 与同桥的 MPI8 ABI 记录；其 ABI 原测时源码 HEAD 是 `f4718519d8a244eae9ea87148422ade14771e534`，所以不称它测试了当前 V12 Python 源。ABI stdout SHA `e723181be00270fadf619e8f3903a05260495bfd9735ca44e6544ac34ab07099`，attempt SHA `b4d1d53b988fdc3e73c300b04b7888846c3593f6398e31bdbdffcb7ad8dcbb92`。当前源身份另由 39 条 HEAD/worktree 绑定及本轮分批合同测试覆盖。

本包尚未启动。下一步须由主控审 sealed argv 并另行给出唯一 dispatch 裁定；当前只完成准备。W5弱显著衍射级按用户决定延期处理，保留原失败，不作为W0.7前置；W2不延误0.7主线。50×25 nm、约2 TB和48 h完整目标仍未完成或资格化。

## V12 唯一 warm 场终态补记（2026-10-11）

本节更新上文的准备态：Invocation `62c3763e266345e0b094a4f3ba3ae19c` 已运行并结束。两侧因子和一次 BAL_H 反馈线性样本已经完成；连接两侧的模态子求解最终没有把残差压到允许近似返回的范围，因此没有合格全场。

| 项目 | 本场记录 | 解释与证据 |
|---|---|---|
| 终态分类 | consumer `IMPLEMENTATION_FAILURE`；public `task041_public_command_nonzero` / rc 3；finalizer `service_boundary_failure` / `failed`；`controlled_stop.active=false` | 保留原分类；modal 首次失败阶段为 `modal_inner_solve`，清理阶段为 `final_cleanup`。错误记录的 `observed_stage=top_construction_cleanup` 不覆盖首次失败阶段 |
| 反馈与最终 modal solve | V12 policy 实际切换一次：`fixed_h6_modal_gmres_research` → `fixed_physical_balh_once_modal_gmres_research`；相同两侧因子句柄经核验。最终 solve 为 32 步、reason `-3`、solver/total MatMult `32/33`，`rhs_norm=0.2594808945363501`、独立 residual norm `0.12270908805805157`、relative eta `0.47290220837766356`、raw pass=false、`budget_exhausted=false` | iterate可信且输入未污染；eta 高于`0.1`的PC可用上限，策略拒绝该近似并抛错。不是资源门停止，也不是未得到可信 iterate |
| outer 与物理输出 | 有 outer progress 至 iteration 11；末条 global/bottom/top/modal true residual 分别为 `0.062043088541883354 / 0.07364811812944605 / 0.03898362761015896 / 0.22925865297129536`，决策仍为 `ITERATING` | outer未收敛；最终五项残差、recovery、E/H、R/T/A、`A_volume`、完整衍射输出均未完成；official RTA=`not_run` |
| side restart64 | bottom/top 都是 armed 状态，`capture_armed=false`、`pending=false`、`trial_count=0`、无trial record | side64对照没有执行，不是其容量拒绝或数值失败 |
| finalizer检查 | 7/12 true、5/12 false：`service_terminal_normal`、`pre_exit_members_clean`、`public_result_completed`、`modal_solver_policy_matches_request`、`post_cgroup_finalizer_only` | 前退出时成员列表为 `[3843144,3843152]`，不同于只含预期主PID；post-I/O检查也记录了两个成员。之后只读复核时unit为`MainPID=0`、`ControlGroup`为空，已记录PID均不存在。后来全清不改写当时两项历史成员检查失败 |
| policy匹配检查 | finalizer 的 `modal_solver_policy_matches_request=false` | public `summary.json`顶层有正确请求字符串，但没有检查器要求的`setup.candidate_inventory`和`setup.full_formal.solve.inventory`。consumer记录则显示同一policy、H6→physical方法历史和实际一次备选切换。因此这是finalizer输入缺少嵌套证据，不能据此断言实际方法错配 |
| modal向量快照 | `first_unmet_target`一次，solve ordinal 4、owner rank 7、32步、eta `0.0048661796696292964`；`first_success_control`一次，ordinal 1、6步、eta `0.0009056691677168769`。两份各含`[800]`的`g/m/raw_residual`复向量并由index绑定SHA | 首次未达目标配额已使用且向量确实落盘。最后一次（累计solve 13）虽然`trusted_iterate=true`，却没有保存其向量；兜底标签`not_saved_exception_no_trusted_snapshot`将策略拒绝后的异常写成“没有可信快照”，措辞与已记录可信iterate不一致，不能当成iterate不可信的证据 |
| wall、账目、资源 | 唯一service-unit wall `52356.221030979 s`；V5 ledger 234项，SHA `f307eab7c908eed21627c29360e5424a8d545c4b46b0b43c26f61b50ae466775`，本Invocation恰一条。process-tree RSS峰 `53504184320 B`；专属job-cgroup history峰 `51665588224 B` | 两种内存值来自不同authority/scope，分列，不相加。resource summary SHA `adef4e71a2b8b7939d0a604c0b6da3c0be4004aba7ca888e8701de3fb9047bf2`；两峰均未触发`85899345920 B` hard cap，资源不是本场停止原因 |

本次outer确有迭代进度，但没有完成原方程门或物理恢复资格。W5弱显著通道按用户决定延期处理；本轮不启动W2。旧raw和ledger均未改；本节证据索引见[终态compact](../../results/task041_v12_w0p7_bounded_modal_backup_policy_only_run_20261010T085320Z/terminal_compact_v12.json)，SHA `77a5ab816d9d48103f8a31c6e9e2c8a50fef2a70e1606beac3919185169b04f5`。
