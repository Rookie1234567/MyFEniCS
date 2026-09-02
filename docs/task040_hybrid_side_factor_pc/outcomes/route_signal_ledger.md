# Task040 current route ledger

## V9 current authority（Response v10）

| 路线 | measured / failed / not_run | 当前含义 |
|---|---|---|
| source canonical bridge / full-spectrum | transform 与 source bridge measured pass；screen `FULL_SPECTRUM_SWEEP_NO_SIGNAL` | 两源 one-apply/r8/r16/r32/r64齐全；不是 implementation failure |
| C0 explicit coarse | worker one-apply measured no-signal；watchdog terminal resource metadata gap | watchdog raw仍为 `ADAPTIVE_COARSE_EXPLICIT_RESOURCE_OR_TIME_UNAVAILABLE`，但不推翻 C0 numerical Gate |
| C1 matrix-free Galerkin | `not_run_by_numerical_gate` | C0 no-signal 后不实现同 basis matrix-free；旧 next 字段保留 |
| V9-E fallback | entry成立但无 qualified physical positive | C0与full-spectrum双真实 no-signal；fallback仍未给出 qualified physical positive |
| B0/B1/S3/LOR L2/bare-F external | exploratory component/formal evidence | 用于解释边界，不替代 V9-E 主 Gate |
| 0.7 nm / Full3D boundary handoff | boundary handoff 文档已建立 | qualified architecture candidate / capacity=`NOT_ESTABLISHED`；不写物理不可行 |

以下 V1–V8 ledger 和 raw failure roots 保持原样。

## V9-E failure/formal compact ledger

详细命令、身份和逐文件 SHA 见 [response v10](../response_v10.md) 的 formal appendix；本表只
保留可复核的 root、分类和停止原因，避免把失败现场或组件结果互相覆盖。

| root / route | classification | 精确数值或 failure reason | resource/lifecycle 边界 |
|---|---|---|---|
| `results/task040_v9_e_s3_j1_baseline_mpi8_7bfef8e9_native` | `S3B_J1_BASELINE_IMPLEMENTATION_FAILURE` | `C shape (8424,300)`，要求 `(8424,296)` | 无 one-apply/FGMRES；factor ready=`0`；MPI8/threads1；swap=`0`；response appendix |
| `results/task040_v9_e_s3_j1_baseline_mpi8_8b9fb0b8_native_fix1` | `S3B_J1_BASELINE_IMPLEMENTATION_FAILURE` | canonical token `9786 != 8424` | 无 numerical Gate；factor ready=`0`；MPI8/threads1；swap=`0`；response appendix |
| `results/task040_v9_e_s3_j1_baseline_mpi8_e2ec5e4a_native_fix2` | `S3B_J1_BASELINE_IMPLEMENTATION_FAILURE` | requires six real layers，got `2` | 无 numerical Gate；factor ready=`0`；MPI8/threads1；swap=`0`；response appendix |
| `results/task040_v9_e_lor_l2_h10_mpi8_8c19b841_native` | `V9_E_LOR_L2_ONLY_ACTION_PASS` | explicit=`9.49183402945266e-9`，`211` steps | max rows=`432`；factor local/rank-sum=`29/221`；resource gate pass；component action-screen |
| `results/task040_v9_e_lor_l2_h5_mpi8_8c19b841_native` | `V9_E_LOR_L2_ONLY_ACTION_FAIL` | explicit=`3.743078556589845e-7`，`256` steps，reason=`-3` | max rows=`432`；factor local/rank-sum=`93/667`；resource gate pass；h5 refinement/action-screen negative；不外推为 h-independent conclusion |
| `results/task040_v9_e_lor_l2_h10_mpi8_9cba44c0_native` | path/orchestration implementation failure | `run-directory already exists` | 无 watchdog/run summary；不是 formal numerical result |
| `results/task040_v9_e_lor_bare_f_external_h10_mpi8_18b00b58_native` | implementation/authority failure | external-mode authority 未供给 | watchdog rc=`1`；无 run summary；raw 保留 |
| `results/task040_v9_e_lor_bare_f_external_h10_mpi8_78896698_native` | worker numerical no-signal；watchdog unresolved | explicit=`0.7349227023138162` | old terminal bookkeeping gap；resource/result wrapper待裁决；无 positive |
| `results/task040_v9_e_tiny_identity_ec8eaaea_native_final` | measured component identity；B0/B1 improvement Gate `>=8` 已通过 | serial B0 best=`0.032778129179444594`、final=`7.473487968169046e-15`、improvement=`4385921181522.289`、`b0_positive=true`；MPI2 B0 best=`0.032776771424794904`、final=`7.844174153538335e-15`、improvement=`4178485941698.5303`、`b0_positive=true`；serial B1 best=`0.032778129179444594`、final=`1.7990718431044546e-14`、improvement=`1821946650161.7349`、direct=`1.6039075528205737e-14`、`b1_positive=true`、`direct_identity_pass=true`；MPI2 B1 best=`0.032776771424794904`、final=`1.5332004278102346e-14`、improvement=`2137800826967.3997`、direct=`2.1440084159556094e-14`、`b1_positive=true`、`direct_identity_pass=true` | 流程上具备进入 reduced 5 nm pilot 的依据；仅是 tiny component identity evidence，无 formal JSON/hash，绝不是 physical formal positive |

S3 的三次失败均在实现前置阶段，按固定顺序后转 fixed LOR；不能写成 numerical no-signal。
LOR、bare-F external 和 tiny 结果是 exploratory/component evidence；V9-E 当前停止仍由
full-spectrum 与 C0 的真实 numerical no-signal 以及 fallback 无 qualified physical positive
共同决定。

## V8 historical authority ledger

| 路线 | 证据 | 当前状态 | 边界 |
|---|---|---|---|
| V7 scale-normalized identity | 3 scales、D0/D1、raw/checker | Review V8 `review_adjudicated=true`；selected=`D0_lower_memory`；`V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0` | raw `formal_adjudication=false` preserved；V6 absolute negative 不改 |
| V8 当时 dedicated full-spectrum | `results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1` | `FULL_SPECTRUM_IMPLEMENTATION_FAILURE` | transform PASS；two source entries/orchestration 已形成但 owner-vector load failure；无 begin/end、one-apply 或 FGMRES checkpoint；apply=`0`；historical wall=`1533.1877332139993s`、peak RSS=`38975795200 B`、swap=`0` |
| adaptive Stage A | `.../task040_v8_adaptive_stage_a_mpi8_0b6c6a26_fix1` | `V8_ADAPTIVE_STAGE_A_LOCAL_GATE_PASS` | 630 patch local Gate；global true residual `2.390497409724407` 不等于 Stage-A failure |
| exact generalized B1 | `results/task040_v8_adaptive_stage_b1_mpi8_0e92079f_fix1` | `not_completed_at_10800s`；wall timeout=`10800s`；无 run summary/数值结果 | 不是 numerical no-signal；转 economical |
| adaptive Stage B/C | `.../task040_v8_adaptive_stage_bc_mpi8_0ed2ebef_native` | `ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE` | projected `130502065136 B`=`121.539519295 GiB`，hard `45 GiB`；未分配 coarse/outer；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0` |
| V8 当时 0.7 nm / Full3D | 当时无 qualified candidate | `NOT_ESTABLISHED / resource-blocked` | V8 当时不创建 Full3D handoff；不写物理不可行 |

所有旧 full-spectrum phase/token、adaptive cache/marker 与 moving-PML 失败现场都保留。当前停止是
V9-E fallback 未取得 qualified physical positive；`Task040=OPEN_AWAITING_REVIEW`，
`selective merge=NO`。C0 watchdog 的 resource metadata gap 与 worker numerical no-signal 并列保留。

## V8 failure-root ledger

这些 root 是 provenance、环境或实现层失败/停止现场，不是 numerical negative；全部保留，不能互相覆盖。

| root | 精确语义 |
|---|---|
| `task040_v8_full_spectrum_mpi8_5f66551c_native` | ahead/upstream provenance preflight failure |
| `task040_v8_full_spectrum_mpi8_5f66551c_native_rerun1` | phase-once implementation failure |
| `task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1` | transform PASS；source token/layout implementation failure |
| `task040_v8_adaptive_stage_b1_mpi8_0e92079f` | sandbox JIT cache read-only implementation failure |
| `task040_v8_adaptive_stage_b1_mpi8_0e92079f_fix1` | exact B1 wall/resource unavailable；无数值结果 |
| `task040_v8_adaptive_stage_bc_mpi8_540a0d3b_native` | sandbox JIT cache read-only implementation failure |
| `task040_v8_adaptive_stage_bc_mpi8_540a0d3b_native_rerun1` | duplicate status marker implementation failure |
| `task040_v8_adaptive_stage_bc_mpi8_0ed2ebef_native` | final Review V8 §12.2 resource Gate |

旧 root 的 cache/marker/token 细节仍以各自 raw evidence 为准。

## 历史 V7 ledger

本表下方原有 V1–V6/V7 记录完整保留；其中旧的“adaptive 未启动”只是当时快照，不覆盖上面的正式 Stage A/Stage B/C 结果。

以下 V7/V8 plan-time 表仅用于还原当时计划，不代表 current authority；上方实际 raw 结果优先。
没有 checkpoint 的路线不得写成
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
| V8-0 review adjudication | V8 review=`0ce67c0c` + V7 raw/checker | `V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0`；`review_adjudicated=true`；selected=`D0_lower_memory` | V6 absolute negative unchanged |
| V8-1 plan-time snapshot | `--v8-full-spectrum-only` | `not_run_at_that_snapshot` | 已由上方 V8 `089bf8a1` actual row supersede；不作 current authority |

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
