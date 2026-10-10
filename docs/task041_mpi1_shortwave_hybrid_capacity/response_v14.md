# Task041 Review V12 执行回应：有界模态备选与 W0.7 准备包

## 当前阶段

两侧 P4 因子已经能够完成；此前停止在固定 8 步的模态辅助求解没有达到 `1e-3`，所以还没有合格的全场。本阶段提交了一个有界的继续策略：先用原 fixed-H6；只有满足已封存的正常返回与可信向量条件，才最多切换一次 fixed physical BAL_H。它试图让原外层求解器有一次有限继续机会，不改变原 Maxwell 方程、P4 精度门或最终验收门。

当前状态是**代码已提交、合同测试按 attempt 分批通过、warm 包已准备、尚未 dispatch**。这不是 FE 数值结果，也不是 W0.7 资格通过。

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

## V12 W0.7 warm 准备包

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
