# Task40extra Response V22：原尺寸局部 action 已测，扫描在固定窗口门限受控停止

| 审查问题 | V22 结果 | 边界 |
|---|---|---|
| 生产链是否接通 | 原尺寸 Ny=8 运行已进入 p6 generated action 与真实 B/D 路径；top/bottom 两个锚点的 production support 路径一致性均过 1e-10 | 这是 shared-kernel path consistency，不是独立全边界积分。V22 记录的独立证据仅为每侧一个 hash-bound、882-row、degree-60 B/D packet |
| 原尺寸 FE/MPC 与 Bα/Dx | descriptor 已记录全局 topological_trace_p6 MPC finalized：owned_slave_count=284,004，storage/independent rows 20,181,348/19,897,344 | 系数 SHA-256 `9312e5f0ad152e517ffc5b7050951fe33ea75f2066bd2e6e7a40639e70366411`；两侧 882-row 局部 identity-MPC witness 的 zero expansion rows 仅属局部范围。未建立 8 个 q CSR，未 factor/KSP/解完整场 |
| 内存与耗时 | watchdog process-tree RSS 峰 3,242,729,472 B；专用 cgroup 峰 3,533,070,336 B/16 GiB，task swap 峰值 0，OOM/OOM-kill 0；单次 run monotonic 3,991.941 s，保守计时 4,383.978 s | PSS 按 profile 禁用且为 null；全局 WSL swap 不能归因于本任务。固定窗口在数值截止前 cooperatively stop；campaign ledger 的累计值与 run 内读数保留各自口径，不相减推造额外成本 |
| support 覆盖与数值资格 | 每侧 882-row 独立 packet 各 1 个，B/D 相对误差约 2.229e-12；mode prefix hash `617cb54178e46928647b245f5f5de1225dc4ac614a009e0735746b86cfcfbe54` | 每 cell 活跃 mode 数直方图、Σm_c、Σm_c² 仍 UNKNOWN；全模式×882-row 独立覆盖 PARTIAL；未完成全 60 类资格 |
| 已关闭与未关闭断点 | 已证明确切 cell/class 的 generated action 调用及两侧局部 B/D 支持路径；任务外部进程树清场由 watchdog 证实 | cached reference 未完全接通；V21 top forward 负结果保留；worker 的 native owners / temporary objects release 原字段仍 UNKNOWN。LU≤3 修正、MUMPS admission/cleanup 三类 fixture 本轮 NOT_RUN |
| 下一 q 与最终目标 | q coverage 0/8，q CSR/factor/KSP/full field/PDE/R/T/A 均 NOT_RUN | 当前没有可审计的下一 q build、symbolic 或 numeric 成本上界；2 TB/48 h 与原尺寸完整数值资格仍 NOT_QUALIFIED |

运行身份：`task40extra_0p7nm_target_original_ny8_operator_probe_v22`，source `ae3f1a4bc557170dc9af51669139683a8ab032a5`，input SHA-256 `33cb569eb900f60100569a6659138589a9d26784a22e05d50c7fe63190bac4ff`，physical-model SHA-256 `ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241`。分类为 `RESOURCE_CONTROLLED_STOP`，不是数值失败或 all-mode pass。固定 window SHA-256 `a4da3d83c2a06672a2337a518dcc8a8bb5d12a446e995783e0f9dd406427d777`；T0 `2026-10-10T02:34:32Z`，numerical cutoff `08:24:32Z`，deadline `08:34:32Z`。原始证据目录与 worker/watchdog 分层状态见 [V22 operator compact](outcomes/records/target_operator_probe_v22.json)。

## 可读解释

p6 表示每个网格单元用六阶有限元基函数描述场；q 表示 y 周期边界的不同相位子问题。模式扫描检查边界模态对单元 action 的实际支持。V22 证明了两侧代表局部数据可走生成式 p6 action，并在有限前缀内完成了实际 action；它没有构建所有周期子问题的全局矩阵，也没有求得完整电磁场。因此目前只能报告部分算子/资源证据，不能把它称为原尺寸求解通过。

## 资源与清场分类

run monotonic 3,991.941 s；UTC/monotonic 正跳后的保守 attempt 计时 4,383.978 s。campaign accounting ledger 最后一条 `watchdog_end` 样本累计 20,889.287384595274 s；probe 记录的固定窗口累计读数为 20,887.459420917243 s，两读数相差约 1.828 s，保持分列，不推断差额归属。watchdog 确认 `descendants_cleared=true` 且 remaining children 为空；worker 原始 cleanup `native_owners_released`、`temporary_stage_objects_released` 与 `process_descendants_cleared` 仍为 null/UNKNOWN，不回写成 PASS。真实全局 descriptor MPC 已 finalized，284,004 owned slave rows；局部 identity-MPC witness 的零 expansion rows 只适用于两个局部 packet。

V21 top forward `1.488391772882517e-11 > 1e-11` 的既有负结果未被本轮覆盖。只读 checker 脚本 `task40_v21_readonly_recheck.py` 的 CLI main 仍指向旧 E2 结构；对 V22 raw root 缺少 `task40_v10_p6_candidate_summary.json`，会以 FileNotFoundError 退出。此为 CLI 接线缺口，不是 V22 PDE 结果；主控改用已实现的 `validate_stage_receipt_semantics` 公共 API 核验 V22 receipt，API 核验结果以主控回执为准。此前 V22 入口失败、校准失败和 raw evidence 均保留在各自 attempt 目录。新的 LU 修正、MUMPS lifecycle fixture、cached reference 接线及全模式独立 packet 覆盖没有在截止前完成，保持 NOT_RUN/PARTIAL/UNKNOWN。

## 主控独立收口核算

本轮实际前缀为 18,968/32,060 modes：top 16,030、bottom 2,938。主控回读科学 payload 的 7,976,570 B，SHA-256 与 checkpoint 一致。公共 `validate_stage_receipt_semantics` 对真实 partial receipt 的18项检查均通过；它仅核验本次受控停止回执，不是全模式或 Maxwell 解通过。旧 E2 专用 CLI 的缺文件失败保留。源码、命令/API、输入 hash、各检查结果及主控提交前预算快照见 [主控回读](outcomes/records/controller_readback_v22.json)。

提交前 append-only 预算快照累计 21574.978431403273 s；其包含 worker结束后的文档和审查费用。旧 watchdog/worker 读数是历史快照，不是现时余额，不清零或重记旧区间。后续提交/推送费用继续进入原 artifact 账本；数值运行已停止，窗口不刷新。
