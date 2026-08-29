# V7 当前 route ledger

本表先记录当前 authority；下方原有 V1–V6 历史表完整保留。没有 checkpoint 的路线不得写成
`no-signal`。

| 路线 | 入口/证据 | 当前状态 | 下一步/边界 |
|---|---|---|---|
| V6-0 factor forensic | factor-stage raw | `FORENSIC_TRUE_FACTOR_STALL` | V6-1 不重试 |
| V6-1 factor-only rescue | Review V6 | 禁止重试 | 进入 full-interface family |
| V6-2 full interface identity | formal+checker | `V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL`；valid negative | old absolute 表保留 |
| V7 scale-normalized identity | 3 scales、D0/D1、A/B/C raw+checker | candidate pass；`formal_adjudication=false` | full-spectrum integration |
| full-spectrum transform | e7/ab formal roots | 未闭合的 implementation failure | 不写 numerical no-signal；不第三跑 |
| moving-PML first | 5e6 root | provider wiring implementation failure | 已由 7b 修复 |
| moving-PML corrected | 7b root | `INCONCLUSIVE_RESOURCE_GATE / SIGNAL_UNAVAILABLE` | 不得分类 PML no-signal |
| adaptive Schwarz | corrected moving 无五源证据 | `NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE` | 等 stop-Gate 审核 |

V7 后续的 exact qualification、full-spectrum numerical screen、PML five-source residual、
factor-free local service、h3、0.7 nm 与 Full3D 均为 `not_run_by_true_resource_gate` 或
`not_reached`，不拆成空的正/负结果文档。

# V5 Route A/B/C signal ledger

## 结论

本轮只实际运行了 Route C 的低内存 fallback screen。Route C 的独立 checker 从 raw manifest
重算出 `ROUTE_C_NO_SIGNAL`；同时 process-tree authority 有两个中段 live-unreadable rows，
所以最终分类为：

```text
VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_RESOURCE_AUTHORITY_GAP
```

`checker_pass=true`、`evidence_valid=true` 表示 raw evidence 合同完整；`gate_pass=false`
表示没有正信号且 resource authority 不完整。它不是允许继续的 candidate pass。

## V6-2 full-interface Schur identity ledger

| 阶段 | 状态 | 记录与后续边界 |
|---|---|---|
| V6-0 factor forensic | `FORENSIC_TRUE_FACTOR_STALL` | 确认 V5 factor stall；不再重试 factor-only rescue |
| V6-1 factor-only rescue | `forbidden_no_retry_after_v6_0` | Review V6 已禁止再次启动该路线 |
| V6-2 full-interface Schur | `valid_identity_negative` | formal 与独立 checker 均为 `V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL`；完整接口 Schur action identity 未建立，触发 Review V6 §19.1 stop Gate |
| V6-3 及其余后续路线 | `not_run_by_v6_2_identity_gate` | full-spectrum、moving-PML、adaptive Schwarz、factor-free local service、bottom/top/both/full Hybrid、h3 与 0.7 nm 均不运行 |

V6-2 的 `checker_pass=true`、`evidence_valid=true` 只表示 raw evidence 合同和独立重算
有效；`gate_pass=false` 且 `executed_exact=false`，因此这是 valid identity negative，不是
exact numerical negative。后续路线统一保留为 `not_run_by_v6_2_identity_gate`，不为未运行路线
创建空结果文档。

## Route A

| 项目 | 记录 |
|---|---|
| entry condition | fresh exact trace/lift 或 dual composition 具备资格 |
| exact configuration | 未进入；没有 exact current-layout packet/lift authority |
| actual checkpoints | `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| training/holdout | `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| memory/wall | 无 Route A 测量 |
| classification | `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| continue/switch reason | 不运行；V5-2 未取得 full-side factor-ready，Route C fallback 已触发 stop Gate |
| 0.7 nm implication | 无 candidate；不能由未运行的 Route A 推断 0.7 nm 或 production |

## Route B

| 项目 | 记录 |
|---|---|
| entry condition | fresh decomposition 显示需要 response-enriched coarse |
| exact configuration | 未进入；没有建立 exact-trace missing-response candidates |
| actual checkpoints | rank/basis/Level B 均为 `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| training/holdout | `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| memory/wall | 无 Route B 测量 |
| classification | `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| continue/switch reason | 不运行；不得用更多 rank 追逐 Route C 的无信号 |
| 0.7 nm implication | 无 candidate；没有 rank/basis 或 scaling 数据可外推 |

## Route C

Route C 的 entry 是 V5-2 factor-construction wall window耗尽后的低内存 fallback。正式配置为
root `results/task040_v5_route_c_online_long_fgmres_mpi8_b5b765ef_retry1`、source
`b5b765ef02d52a877184b14fb8d72ad16a0432f8`、MPI8、每 rank 1 thread、bottom-only、连续
right-FGMRES restart 32，只有 `external_dtn_coupling` 和 `fixed_random_repeat_0` 两个
RHS。保存了 16/32/64/128 的 true residual 与 lower/upper canonical interface residual
traces；没有授权 256。

| Route C ledger item | 记录 |
|---|---|
| entry | V5-2 在授权 factor-construction wall window耗尽后切换的低内存 fallback |
| exact configuration | 上述 formal root/source；MPI8、threads1、bottom-only、restart32、两个 RHS、checkpoint 16/32/64/128 |
| actual checkpoints | 两源均 final iteration `128`；`r64/r128/log10(r64/r128)` 如下表；256 两源均 unauthorized/completed=false；shared stable count `0` |
| training/holdout | 不适用且未进入；两个规定 screen RHS 不是正式 train/holdout split |
| memory/wall | process-tree peak `30254075904 B`、raw observed swap `0`、timeline last wall 约 `13029.23296845 s`；authority gap 见下文 |
| classification | `VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_RESOURCE_AUTHORITY_GAP`；独立 checker `checker_pass=true`、`evidence_valid=true`、`gate_pass=false` |
| continue/switch reason | no-signal 是 V5 stop Gate，且 resource authority 有 live-unreadable gap；停止当前 family，不进入 bounded rank/Level B |
| 0.7 nm implication | `CURRENT_SIDE_INTERFACE_FAMILY_NO_POSITIVE_SIGNAL_NOT_A_CANDIDATE`；不得外推 0.7 nm |

| source | `r64` | `r128` | `log10(r64/r128)` | no-signal 条件 |
|---|---:|---:|---:|---|
| `external_dtn_coupling` | `0.8906247440000827` | `0.9116861468870889` | `-0.010150598869495011` | `r128>0.9` 且下降 `<0.05` |
| `fixed_random_repeat_0` | `1.036891675911675` | `1.0585987178847864` | `-0.008997975654488713` | `r128>0.9` 且下降 `<0.05` |

两源均在 iteration 128 结束；`shared_slow_directions.count=0`、`stable_components=[]`。
仅有三个孤立的相关性匹配，不满足“至少两个 restart 的稳定共享方向”规则。故：

| Gate | 结果 |
|---|---|
| `route_c_no_signal_stop_gate_triggered` | `true` |
| `route_c_positive_signal_gate_pass` | `false` |
| conditional 256 authorized/completed | 两源均 `false` |
| direction/interface projection/basis persistence | observed and pass；`replicated=false` |
| Route C next action | `stop_current_coupled_response_family` |

## Route C resource authority

raw watchdog peak RSS 是 `30254075904 B`，低于 `45 GiB` hard line
`48318382080 B`；raw observed swap bytes 最大值为 `0`。但 raw timeline 中第 `5825/5826`
行在 `v5_route_c_interface_projection_ready` 期间 live 且 process tree unreadable，不能被
terminal teardown 规则排除。只有末尾第 `21296/21297` 行是连续 cleanup-complete suffix，
按派生规则排除；两行 RSS 均 `15327232 B`、swap `0`。

因此 `resource_authority_gate_pass=false`，不是内存越线：

- `raw_observed_rss_below_hard_stop=true`；
- `raw_observed_swap_zero=true`；
- `process_tree_authority_complete_after_terminal_exclusion=false`；
- `rss_authority_complete=false`、`swap_authority_complete=false`；
- `dedicated_cgroup_present=false`，raw dedicated-swap 的 `0` 仅为诊断值。

## 统一停止边界

Route C no-signal 是 V5 stop Gate，资源 authority gap 又使 candidate gate 保持 false。
因此以下项目全部明确为：

```text
not_run_by_route_c_no_signal_and_resource_authority_gate
```

bounded total-rank `64/128/256/512`、packet-independent online rebuild、Level B、bottom
bare-F production candidate、bottom A-side、same-config top、both-side、唯一 full Hybrid、
h3 probe、0.7 nm PDE 和 2 TB full-scale capacity test 均未运行。不得用 Route C 的两个
screen RHS 或旧 exact/side root 推断这些项目的数值或 scalability。
