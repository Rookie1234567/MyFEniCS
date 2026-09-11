# V12 supplement repair evidence index

本目录是 V12 supplement bounded continuation 的轻量、可远程审阅证据索引。源码身份按 workflow 分段：O1 fresh 与首次失败 R32 绑定 `7d9df5e19d324776588aaa9efc4996cc3fe36d8e`；修复后的 R32、R64 和 continuation ledger 绑定 `d39261bb17e8d9042c03d4d4990258da5043b621`。所有 workflow 共享物理模型 SHA256 `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` 和 qualified Linux complex128/int32 ABI。

## 结论边界

| 项目 | 结果 | 解释 |
|---|---|---|
| O1 fresh physical controls | `COMPLETED`, selected `BAL_H` | 42 个物理 block；3 个 shared-q 比较均匹配；完整摘要见 `core/o1_m1_summary.json`。 |
| 原始 R32 | `WORKER_FAILED` / `partial_checkpoint_evidence` | 旧 TypeError：field diagnostic 使用了尚未存在的 recovery quadrature metadata；8/16/24 residual=`0.8283760020203784/0.8172376273064963/0.811621467511064` 已保存；最终 candidate unavailable、restart comparison incomplete；这是 inherited engineering failure，不是数值 PC 结果。 |
| 修复后 R32 | `COMPLETED` | 64 outer steps；final true residual `0.7666389832389989`；R32 outer conservative elapsed `1542.916955076985 s`，父 workflow charge `1846.2808846201353 s`；128 次 I4 原始标量和 outer ledger 在 `core/repaired_r32_outer_summary.json`。 |
| R64 | `USER_REQUESTED_CONTROLLED_STOP` / `partial_checkpoint_evidence` | 按用户要求停止，保存 8/16/24 residual=`0.8283760020203784/0.8172376273064963/0.811621467511064`，最终持久化到 24 步；candidate unavailable、restart comparison incomplete；原始 watchdog classification 保留为 `USER_CONTROLLED_STOP`。这不是 R64 数值失败。 |
| supplement formal charge | `4361.38889024941 s` | O1 `601.0369560300772 s` + repaired R32 `1846.2808846201353 s` + stopped R64 `885.4244810280746 s` + inherited original R32 `1028.6465685711235 s` 已分别保留；余量 `6438.61110975059 s`。 |

实现活动时间不计入 formal cap；可观测实现子区间保留在 continuation ledger，完整工程耗时保持 `unknown`，没有把子区间相加冒充完整成本。

## 核心记录

`core/` 保留完整但轻量的阶段身份、terminal、ledger 和 summary：

- `o1_m1_summary.json`、`o1_terminal.json`：O1 完整控制摘要和资源终点。
- `p4_controls/`：六条 O1 p4 calibration raw JSON 的 byte-identical tracked 副本；原始 artifact 路径和 SHA 仍在 compact 中绑定。
- `original_supplement_ledger.json`：旧 ledger 原样副本，SHA256 `af72d67ab51af205841c4757de5b7413ed2f6ddccbbf8c5a92bc4ccbe633d5fe`。
- `original_r32_outer_summary.json`、`original_r32_terminal.json`、`original_r32_worker.log`：旧 TypeError 负证据；outer summary SHA256 `34e5bc938e20e3b042f59e412da40a3c0b0748f660831fb1e986c98926a92fac`，terminal SHA256 `dad9ac6d76f273e6e6c0682196b2d3237105582ce055184d1dc8af5a3bab25d8`。
- `repaired_r32_outer_summary.json`、`repaired_r32_terminal.json`：修复后 R32；summary SHA256 `b8bd542ff9a192dbcc530ca3a8c337ea409ab1bf9043bc096891b72177dcbf7e`，terminal SHA256 `776dc9d3bd36ffbec1da8378d3068386bf67a2061faafca7feee5fee323f6d4d`。
- `repair_continuation_ledger.json`：同一 supplement schema 的续算 ledger，SHA256 `74a863666e4b299002306f505d070ff248847c9e7c91d1bc97494beec2b6c329`。
- `stopped_r64_terminal.json`、`stopped_r64_user_stop_reason.json`：R64 原始 watchdog 终点和用户停止原因；terminal SHA256 `ca1419f33d0b21c00bf3422cef0e8f77ad8b2f2c50ef11077fd5f926ece28a64`。

R32 summary 中的 128 个 I4、B4/MD 计数和 balance ledger 是嵌套细分；`outer_pc_total_operation_seconds`、I4 facts 和 B4/MD seconds 不混作可相加的同口径父时间。时钟口径和 field-diagnostic 频度差异应结合 `physical_macro_v12.md` 及比较图阅读。

## 审计、脚本与日志

- `audits/`：O1、原始失败 R32、修复 R32、停止 R64 的 inventory/resource/outer/prefix/budget/shared/P4 审计 JSON，以及 `history.json` 对照原始标量。代表性审计：R32 outer `1187 checks / 0 errors`；R32 repaired inventory `759 / 0`；R64 stopped prefix 对 8/16/24 checkpoint 做同解绑定；final budget audit 无错误。
- `scripts/`：`task39extra_v12_supplement_*.py` 审计、history、candidate/field smoke 和 plot 脚本的冻结副本。
- `logs/`：ABI、focused tests、field metric smoke、audit 和 candidate smoke 的 stdout/stderr；测试日志只报告本地测试，不代表 CI。
- `runner_help.txt`：本轮公开入口和参数快照，确认使用的是现有 `--macro-v12 --macro-v12-supplement --profile-budget-ledger`，没有 repair flag 或第三套 schema。

## 对照图与未复制的大文件

比较图位于 [`../../charts/v12_supplement_comparison.svg`](../../charts/v12_supplement_comparison.svg) 和 [`../../charts/v12_supplement_comparison.png`](../../charts/v12_supplement_comparison.png)，分别 SHA256 `0f97dbc73d1dfbbda1e80629d6c01d31d6df464525723c25559f7529d139755e`、`c85a4cf6bec87305b2a1ca41e05fadba4ae000cbc9c0450facb70e237a2ec845`。图只绘制有完整节点时间的 repaired R32 与历史对照；R64 受控停止只在表和 prefix evidence 中出现。

大 `NPZ`、field、完整 watchdog resource timeline 和其他重型 raw artifacts 仍在 ignored `benchmarks/artifacts/` 下，不复制到 Git；本目录的 terminal、summary、audit 和 manifest/hash 字段提供其身份入口。R64 停止保留 periodic checkpoints 8/16/24，但不推断 32/64 终态，也不宣称任何 R64 numeric pass/fail。
