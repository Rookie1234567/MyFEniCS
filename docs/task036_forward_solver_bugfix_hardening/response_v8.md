# Task036 Response V8：受控失败结项与 master 选择性整合

## 1. 回应结论

接受 Review V8 的最终判定：Task036 的低秩 direct Hybrid 生产目标没有证明，研究继续扩展
已经停止；同时保留 Full3D 通用修复、Hybrid 接口安全修复、strong-trace research core
和 exact FE trace-chain correctness oracle。没有整体 merge Task036 分支，也没有把
research-only 路径设为 ordinary default。

## 2. V8 指令逐项回应

| V8 要求 | 本轮处理 | 状态 |
|---|---|---|
| 冻结 Task036，不再运行 C1b/C1c | 最终研究身份固定为 `7a0334008dc9bbdeefe55dd0ffa535cc756e661c`；96-RHS teacher、POD 和 actual compressed candidate 不再运行 | complete |
| 从 master 按意图选择性整合 | 以 `007298261681014efbe6508ac91c6c3ae9a6a44a` 为研究基线，未整体 merge/cherry-pick 大型研究提交 | complete |
| Group 1 通用修复 | selective commit `7735a2617d18fe5f869331a90d47ec16632fd8d3` | complete |
| Group 2 Hybrid 安全/物理修复 | selective commit `a741ad1b5cfb579e2667600bcc6497ec5c4f23d9` | complete |
| Group 3 research oracle | strong trace、exact trace-chain 与 endpoint metric 只保留最小 core/tests | complete；commit `4c9e1b9cedd4b04d65824698202c9fff96f3a0dc` |
| 禁止 capacity/POD/campaign | robustness、capacity、mode-pool、POD、teacher 和自动 repair/fallback 均未迁入 master | complete |
| 文档结项包 | 原样加入 `task.md`、`review_report_v8.md`、`fix_report.md`、`test_summary.md`；新增 `final_summary.md` 和本文 | complete |
| 更新能力和模型总账 | `capability_matrix.md`、`development_model_registry.md`、`development_progress.md` 使用 controlled-negative/research-only/not-run 语义 | complete |
| 保持模型登记合同 | registry checker 的任务序列 authority 仍冻结到 Task035e；Task036 closeout 进入现有 Hybrid 方法级 registry，不新增 `3.41`，也不把 Task036 冒充旧任务 | complete |
| 创建 Task037 空分支 | `codex/20260803-task37-matrix-free-iterative-development` 已从已推送 master `b615a130d7c34060a3445c352c1f683bbf3aa23f` 创建并推送；创建时 upstream 正确、ahead/behind=`0/0`、worktree clean | complete；task not defined |

## 3. 最终能力判定

| 项目 | 回应 |
|---|---|
| compressed direct Hybrid | `controlled_negative / closed` |
| strong-trace Hybrid | `research_only`；E 连续性通过，但 energy 与 19 个固定通道未闭合 |
| exact FE trace-chain | `research_only correctness oracle`；不称 scalable solver |
| M120/M240 complete global port | `not production-qualified` |
| M120 long-range modal core | retained；selected-space exact FE 对照约 `2e-11` |
| C1b/C1c | `cancelled / not_run` |
| 0.7 nm / 2 TiB | `not solved` |
| ordinary default | unchanged |

## 4. 当前 master 集成测试

| 测试项 | 结果 | 判定 |
|---|---|---|
| ABI preflight | qualified activation；PETSc `complex128 / int32` | pass |
| Group 1 targeted | `39 passed in 2.18 s`；另组 `15 passed in 3.11 s` | pass；保留分组，不重复累计 |
| Group 2 contracts | `10 passed in 1.81 s`；default/record 组合 `20 passed in 1.88 s` | pass；两组有重叠 |
| Group 2 小型真实离散 | p2 reconstruction、exact conormal direct、static Hybrid equivalence 各 `1 passed` | pass |
| Group 3 research oracle | serial `7 passed in 3.26 s`；MPI2 recursion 每 rank `1 passed in 1.61 s` | pass |
| 最终 compact targeted | `24 passed in 1.91 s`；DtN/alias `14 passed in 2.20 s` | pass |
| Full3D PDE smoke | p2 ordinary direct `1 passed in 2.74 s`；p2 static direct `1 passed in 2.50 s` | pass；均为 802 FE DoF |
| Ruff / format / compileall / diff-check | pass | pass |
| 文档与数据合同 | docs targeted `7 passed`；tracked JSON `928` files parse pass | pass |
| combined pytest | `41 passed in 107.99 s` 后收到用户中断要求；exit `2` / `KeyboardInterrupt` | `interrupted_by_user`，不是代码 failure |
| 小时级 full repository pytest | 用户明确取消 | `cancelled / not_run` |
| actual Ny3/Ny4 PDE pair | 未运行；synthetic alias 正/负合同已通过 | `not_run_by_user_cost_override`；V8 原文为“若成本允许” |

历史 Task036 分支的 `803 passed, 41 skipped, 3 failed` 及后续定向闭合仍保留在
`outcomes/test_summary.md`，但它绑定旧研究 SHA，不能替代当前 selective master 的未完成
full-suite。没有删除失败测试，也没有放宽数值阈值。

## 5. 停止与交接

Task037 空分支已创建；本次必须的结项文档追加后，该分支保持与最终 master 快进同步，
并再次核验 upstream、ahead/behind=`0/0` 与 clean status。没有创建 Task037 `task.md`、
实现代码或运行新 PDE。本响应不授权新的 iterative、0.7 nm、capacity、POD 或
direct-port 数值开发。
