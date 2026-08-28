# Task040 Response V7

## 结论

V6-2 完整 15120-row interface Schur formal 已执行一次，独立 checker 也执行一次。结果是
有效的 identity negative：`checker_pass=true`、`evidence_valid=true`，但
`gate_pass=false`、`executed_exact=false`，classification 为
`V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL`。Review V6 §19.1 stop Gate 已触发，后续不再启动
新的 heavy route。

这不是“all-new-routes-negative”：本轮只证明 V6-2 identity fail；full-spectrum、moving-PML
和 adaptive Schwarz 等 fallback 均未运行。

## 身份快照与提交链

| 项目 | 值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| formal source / HEAD / upstream | `82bd11099a843dc960629970b9074fb241fba0f4` |
| formal-run snapshot | clean，ahead/behind `0/0`；本轮文档编辑后仅 6 个文档待审核、未提交 |
| commits after `86014171` | `253199e2..82bd1109` |

提交链（按时间顺序）：

```text
253199e2 docs(task040): record v6 factor-stage forensic
3d8f58bb feat(task040): add full-interface Schur action
7c3f068f feat(task040): add V6-2 interface identity runner
0b66b633 feat(task040): add V6-2 exact qualification loader
53e75340 feat(task040): add V6-2 exact family consumer
41d09404 feat(task040): complete V6-2 exact authority bridge
a8531b1a docs: define controller-executor workflow
875f3234 feat: complete Task40 V6-2 exact qualification evidence
72975fff fix: recognize native Task40 activation
8199929b fix: adapt V6 resource gate to native Linux
82bd1109 fix: bridge frozen RHS to native bare F
```

## Formal、checker 与 identity 证据

| 项目 | 结果 |
|---|---|
| formal run root | `/home/fenics/Projects/MyFEniCS/results/task040_v6_2_full_interface_schur_mpi8_82bd1109_native` |
| checker formal root / worker root | `/home/fenics/Projects/MyFEniCS/results/task040_v6_2_full_interface_schur_mpi8_82bd1109_native/worker` |
| checker output | `/home/fenics/Projects/MyFEniCS/results/task040_v6_2_full_interface_schur_mpi8_82bd1109_native/v6_2_checker_82bd1109.json` |
| formal worker | `rc=0`，`termination_reason=natural_exit` |
| manifest/run-summary SHA | `71963c98b543ae9b6de05dbce249f3b72931b202ecffc542aedb08f0eeaaa4fa` |
| checker artifact SHA | `9da96cc142e4a1e590d8f790398c98352466849a08f0bde5a55ff691b6b0c9c3` |
| watchdog SHA | `d34adcea148891ca33e0badc1af5b9dbf1a9c82a788fbf52559ea6c643847788` |
| operator audit SHA | `bd3a5fa88bceb45f35bf202cb1fa7b64a6736c4a77158b4faa50041baee8ca2c` |
| checker | `rc=0`；valid evidence，但 `gate_pass=false`；未读 NPY |
| rank evidence | rank `0..7` 完整；hash、layout、resource、factor lifecycle 和 raw gate 一致性通过 |

固定 identity 阈值与观测如下：

| 项目 | 阈值 | 观测 |
|---|---:|---:|
| Gamma action | `<=1e-10` | max `3.783538480529195e-10`，fail |
| interior residual | `<=1e-10` | max `1.2298155651030158e-9`，fail |
| linearity | `<=1e-11` | `6.766170711131541e-9`，fail |
| repeat | `<=1e-11` | max `1.4161645932820494e-9`，fail |
| zero / roundtrip | `<=1e-13` / `<=1e-11` | `0 / 0`，pass |

Gamma `L/U/joint=7560/7560/15120`；三个 deterministic vector solve count 均为 `3`。
canonical layout、owner distribution、coverage、no replica、rank consensus 和结构证据均通过。

## 资源、operator 与 lifecycle

watchdog：`339.7141449260016 s`，peak process-tree RSS `27,801,870,336 B`（约 `25.89 GiB`），
swap `0`，`616` authoritative samples，hard stop `45 GiB`，timeout `21600 s`，worker natural
exit `rc=0`。

当前机制为 `explicit_current_bare_F`，modal source 为
`full3d_one_cell_exact_schur`，selected columns `281/283`，`C/D/H=0`、QEP/PDE 均未运行。
factor lifecycle 为 `3 -> 0`，无 full/global factor。

allgather 纠正口径：top-level `numeric_allgather=false`、`fe_numeric_allgather=false`、
`full_interface_numeric_replica=false`；`identity_gate.numeric_allgather=true` 表示检查通过，
本次没有被禁止的 numeric allgather。

`run_summary.json` 与 checker 输出均未发出 `operator_identity_bridge` 字段（`has=false`）。
这是因为 identity stop 在 exact runner 前发生，`exact_output_vectors_loaded=0`；bridge 未执行、
未判定，不能写显式 null、pass 或 fail。冻结 RHS 未加载、未修改。当前 live bare-F hash 为
`c7a5551232f23f835ee0c21ea74b337f779addaef2d76464370000fb53c49ee4`；不把历史 raw-byte hash
差异写成数值变化结论。

## 测试与路线边界

此前 `72975fff`、`8199929b`、`82bd1109` 上的 native/resource/bridge focused 最小验证均按
阶段通过；本次 formal 只执行一次，checker 只执行一次。checker 不是 pytest；本轮文档仅做
`git diff --check`，不跑 pytest、Ruff、full repository pytest 或任何 heavy run，也不声称 CI。

V6-0 为 `FORENSIC_TRUE_FACTOR_STALL`；V6-1 factor-only rescue 禁止重试；V6-2 identity fail
后，old Route A/B、full-spectrum Floquet-DtN、moving-PML、adaptive spectral Schwarz、
factor-free local service、bottom/top/both/full Hybrid、h3 scaling、0.7 nm PDE 和 arbitrary
Full3D 均为 `not_run_by_v6_2_identity_gate`。0.7 nm/2 TB 只有边界记录，没有 measured、
qualified prediction；Full3D 未到达、未资格化，也没有把 Hybrid 结果当作 Full3D handoff。

| 账本类型 | V6-2 结论 |
|---|---|
| measured | 仅本次 identity component：`25.89 GiB`；不是 0.7 nm 或完整 workflow |
| derived | `not_run_by_v6_2_identity_gate` |
| predicted | `not_run_by_v6_2_identity_gate` |
| 2 TB / Full3D qualification | `not reached` |

## 合入边界与待审

当前 `selective merge approval=NO`，没有任何本轮路线获得 production 或 0.7 nm 合入资格。
剩余 blocker 是 full-interface Schur action identity 无法在固定阈值下建立；此外 Review V6 要求
的 0.7 nm capacity derivation 与 Full3D architecture handoff 尚未到达。不得通过调阈值、修改
输入或重跑路线伪造通过；不创建额外空文档。等待 ChatGPT 与用户审核本次 V6-2 valid identity
negative、六个文档改动及 stop-Gate 后续决定。
