# Task039 Review V7：继承审计（V7-0）

本文件是 V7-0 的 docs-only inherited audit。它只核对 V7 的新分级目标、V6 的真实负结果、
V5 的可复用证据和当前环境身份；本轮没有修改 Python/config/test，没有启动 PDE、MPI job、
QEP 或 heavy。V7-0 完成后仍需主审批准，才可进入 V7-1 的实现或唯一 heavy 候选。

## 1. Git 身份与继承关系

| 字段 | 实测值 | 口径 |
| --- | --- | --- |
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | 当前本地分支 |
| reviewed ancestor | `9ce588133375ed3848c7ddee4951a98b1ac7d483` | V7 Review 的 reviewed_head；V6 docs closeout |
| current HEAD | `e9a251411a90e18efc158d1d1cc9e282d74e9bd0` | V7 review docs 的 fast-forward 后 HEAD |
| upstream | `origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` at `e9a251411a90e18efc158d1d1cc9e282d74e9bd0` | 非交互 fetch 后核对 |
| relation | `e9a2514` 是 `9ce58813` 的纯 docs-only 后继 | 无分叉；未有代码漂移 |
| ahead / behind | `0 / 0` | `git rev-list --left-right --count HEAD...@{upstream}` |
| initial worktree | `clean` | fast-forward 与本文件创建前 |
| V7 review SHA256 | `116fccf2300d95b7b36092439db233afd2426127f47627c03a004d78d2d192ff` | `review_report_v7.md` |

Task39 目录没有独立 `README.md` 或补充任务书；本审计继承根/ docs 规则、Task39 `task.md`、
Review V7、V6 `response_v7.md`、V6 outcomes 和 compact records。

## 2. 现有 response 与 compact evidence 身份

| 文件 | SHA256 | 继承用途 |
| --- | --- | --- |
| `response_v7.md` | `649bb40722027ce03f1a4b803ea28f0f99829248c19c6efd0aca5baab9654f8c` | V6 最终回应；不是 V7 response |
| `outcomes/summary.md` | `39af639d8cf9a67d651d4f1592d638f4e61066bb3ae7df93bb0ece3ba3d9bb0b` | V5/V6 统一边界 |
| `review_v6_inherited_audit.md` | `54813af8bb592978ab51fc02cfc4ccb1e816b43da03f5cc8c354e8915ca9a4de` | V6 环境、spool、身份和隔离事实 |
| `task039_v5_h4_exact_side_memory_attribution_v1.json` | `6caf6804f5c71ce9fe30b303d553d0dc5004a7f618bf328b633adebf6343c5f7` | V5-2 h4 setup |
| `task039_v5_h5_current_hybrid_direct_sidecar_v1.json` | `ecb3825eee7ffa858e6c7c837cd4d4c06e4cfaa6aeac258230b83647013ccdc9` | V5-S h5 nonblocking sidecar |
| `task039_v5_factor_light_side_inverse_v1.json` | `fd8e6603acefcc6bedddd0cdbbf08980c85549f0012f91b8b19ab2d41410b510` | 两个 BLR profile 的关闭证据 |
| `task039_v5_fixed_budget_side_krylov_component_v1.json` | `37f2ddd39b5b23493910a2e2cc513ed95699738d62a6a40b6c748f937b940280` | budget=32 数值负结果 |
| `task039_v5_streaming_woodbury_component_v1.json` | `9c16a981dcd8abdcf994a3ed7c5bcd5248e915f05d91309b9fa80f6e706c5e09` | retained/streaming-W MPI1 synthetic component |
| `task039_v6_post_compaction_exact_side_setup_v1.json` | `aef228304febbde794f7122ea5911ad79cc0ddc5bcc52725b35f241f894c5990` | V6-1 exact-side setup stop |
| `task039_v6_port_modal_bottom_component_v1.json` | `00c8b889d75b7fa0b77a6563d4ffe708a07d00f23133dec06b5929e4cabe3368` | V6 Petrov bottom resource stop |

V5-2 source 为 `2ba0c44d...`，V5-3 factor-only 为 `61d3b06f...`，V5-4
single-Schur/GMRES10 为 `2eab55d...`，V5-5 streaming action/runner 分别为
`9ca332bf...` / `76d374f8...`。这些均为显式 research evidence；ordinary default
行为没有被改成 factor-only、streaming-W、sampled Schur 或 GMRES10。

## 3. h4 继承基线与 V6 负结果

| 路径 | measured evidence | 当前解释 |
| --- | ---: | --- |
| h4 Hybrid direct | `93.377006531 GiB` | matched direct reference；own numerical/physics pass |
| V4 exact-side iterative | `104.334560394 GiB` | numerical/physics pass，但 resource regression |
| V6-1 post-compaction exact-side setup | `42.70841979980469 GiB` | 超过旧 `42.019652939 GiB` setup line；controlled resource stop，exact-side 仅 oracle |
| V6 full-ephemeral port/modal bottom | `22.025470733642578 GiB` | 超过旧 22 GiB construction line；authoritative resource-controlled negative |

V6-1 唯一 attempt 的 raw root 为
`results/task039_v6_h4_post_compaction_exact_side_setup_only_mpi8_35b1532e`，source
`35b1532e...`；V6 port/modal 的首次 `aac7e33e...` 是 left/right packet 接线错误，不能
当作方法负结果，修复后的 authoritative root 为
`results/task039_v6_h4_port_modal_bottom_component_mpi8_52f34262`，source `52f34262...`。
V6 两个负结果、硬停 overshoot、未到 owner/rank64、top/outer/recovery/RTA/field
`not_run` 均原样继承；本轮不重跑、不改写、不把资源停止改称 numerical failure。

## 4. V7 分级内存目标

V7 的唯一 matched baseline 是：

```text
B_direct = 93.377006531 GiB
```

完整 workflow 的峰值是所有串行阶段 process-tree RSS 的最大值，不是对象字节或各阶段之和：

```math
B_{\mathrm{workflow}} = \max_p B_p.
```

| 分类 | 峰值上限 | 由 direct 派生的含义 |
| --- | ---: | --- |
| minimum lower-memory positive | `<93.377006531 GiB` | 首个低于 direct 的完整、数值合格结果 |
| robust minimum pass | `<=88.708156204 GiB` | 至少节省 5% |
| useful pass | `<=74.701605225 GiB` | 至少节省 20% |
| strong pass | `<=65.363904572 GiB` | 至少节省 30% |
| major pass | `<=56.026203919 GiB` | 至少节省 40% |
| half-memory strategic pass | `<=46.688503266 GiB` | 至少节省 50% |
| stretch pass | `<=37.350802612 GiB` | 至少节省 60% |

`<93.377006531 GiB` 但没有至少 5% 余量的结果必须保留采样/allocator 边界并标为
`LOWER_MEMORY_POSITIVE_WITH_SMALL_MARGIN`，不能直接称 production-qualified。达到 50%
仍只证明固定 5 nm h4 案例，不等于 0.7 nm 或 ordinary production 资格。

## 5. V7 执行 lanes 与一次性资源政策

### Lane A：exact-side limit-finding

允许最多一次新的完整 h4/M480/MPI8 post-compaction setup-only。配置继续使用 factor-only、
single-build modal Schur、固定线性 GMRES10、bottom→cleanup→top lifecycle，setup-only 不做
outer solve。`84.039305878 GiB` 是新的 advancement line：setup 低于等于该值，并达到
outer-ready、bottom/top factor lifecycle、packet/QEP release 和 swap=0，才有资格最多运行
一次 exact-side full formal；否则 exact-side full formal forbidden、只保留 oracle。旧
`42.019652939 GiB` 仍是 half-memory-compatible setup 线，不再是 V7 所有研究的唯一硬停。

### Lane B：streamed owner-row Petrov

正式 candidate 改为 producer/consumer 进程拆分：producer 按小 batch 生成 owner-row Z/Y、
增量 QR、写同一嵌套 basis packet 后释放当前 mode/function/Vec；consumer 建 matrix-free
side F、fixed cheap base action、读取同一 packet 的 rank64/128/256/512 并构造
`E=Y^H F Z`。训练与 holdout 严格分离；V5 exact-response spool 只作 holdout/oracle，
不得用于训练或冒充 candidate 在线内存优势。只允许同一 producer packet 的嵌套 rank ladder，
不允许四次独立 campaign；base/exact/global direct factor identity 必须继续为 `0/0`（不把
cheap base action误称 exact/global factor）。

顺序固定为 bottom producer/consumer → bottom first passing rank → top producer/consumer
→ both-side setup-only → 唯一 conditional full h4 formal。bottom 未通过前，top、outer、
recovery、R/T/A 全部禁止。

### Lane C：独立 side layer-graph audit

允许最多一次轻量 graph-only audit：只构造 h4 side mesh、FE space、constraints 和
static-condensation connectivity，统计 same/adjacent/long-range NNZ、每层 rows/NNZ、
block half-bandwidth 与 DtN low-rank identity；不运行 QEP、不 hydrate M480、不建数值 factor、
不做 PDE solve。只有真实图证据通过后，下一 Review 才可考虑 sweeping/hierarchical Schur；
本轮不实现 sweeping solver。

### 次数与时间

| 项目 | V7 上限/政策 |
| --- | --- |
| exact-side complete setup-only | `<=1` |
| exact-side full formal | `<=1 conditional` |
| streamed Petrov producer | `<=1` |
| bottom Petrov consumer/rank ladder | `<=1` |
| top consumer / both-side setup / Petrov full formal | 各 `<=1 conditional` |
| side graph-only audit | `<=1 lightweight` |
| Full3D new heavy、0.7 nm PDE、full-ephemeral Petrov rerun | `0` |
| 默认 heavy timeout | `21600 s`（6 h） |
| 条件 8 h | 仅 outer iterative、swap=0、低于 direct 且有客观残差下降趋势时，最多一次，总计 `28800 s` |

Producer、QEP、direct、setup-only、graph audit 和尚未进入 outer 的阶段不得自动延长；若 8 h
仍未完成，必须同时记录 memory positive 与 wall-time not qualified。

## 6. V7 数值与生命周期 Gate 继承

Streamed consumer 的冻结 Gate 为：finite、repeat `<=1e-10`、linearity `<=1e-10`、每个
mandatory true residual `<=1e-2`、modal+/modal−/external `<=1e-3`、coarse E condition
`<=1e12`、exact/global direct factor `0/0`、swap=0。rank 64/128/256/512 必须是同一
packet 的嵌套 checkpoint；第一个通过的 rank 才是 preferred point，同时保留此前 rank 的
内存、时间和 residual Pareto 证据。rank512仍不通过时，使用
`NUMERICAL_LIMIT_NOT_REACHED_BY_RANK512`。

V7 不得重开：第三 BLR profile、普通 ILU 或 generic budget scan、原样 full-ephemeral
Petrov rerun、h5 rerun、Full3D 新 heavy、0.7 nm PDE、new branch/worktree/master 写入，
以及 ordinary default 改动。

## 7. 现有 exact-response spool 与隔离

V5 authoritative spool 位于：
`results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output/v5_blr_reference_spool`。
它有 8 个 producer rank、6 个冻结 labels、192 个 response 文件（每个 label/rank 各一份
RHS 与 exact output）和对应 metadata/hash。packet manifest SHA 为
`2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067`。spool 是 oracle/holdout
输入，不是 V7 candidate 的 production memory saving；不能在训练阶段打开或把 exact-output
生成成本从 candidate RSS 中删除。V7 producer 的训练数据必须来自新的 factor-free、hash-bound
physical source schedule；同一 spool 只能在 basis sealed 后由 consumer 验证。

## 8. V7 待创建证据与本轮边界

Review V7 预先列出的后续证据入口为：

| 文件 | 条件/用途 |
| --- | --- |
| `outcomes/review_v7_inherited_audit.md` | 本轮 V7-0，docs-only |
| `outcomes/v7_exact_side_limit.md` | Lane A setup-only；未运行前不得创建通过结论 |
| `outcomes/v7_streamed_petrov_basis.md` | Lane B producer/basis packet |
| `outcomes/v7_petrov_bottom_pareto.md` | bottom rank ladder Pareto |
| `outcomes/v7_petrov_full_result.md` | conditional full formal；未授权前不创建为通过 |
| `outcomes/v7_side_layer_graph.md` | Lane C graph-only |
| `outcomes/v7_memory_limit_summary.md` | 最低 RSS、首个低于 direct、最大节省、blocker 与时间代价 |
| `outcomes/v7_0p7nm_implications.md` | 仅在已有证据足够时做 conditional capacity implications |
| `outcomes/test_summary.md` / `outcomes/summary.md` | 阶段汇总，保留 measured/not_run/controlled_stop |
| `docs/development_progress.md` / `response_v8.md` | 后续阶段收口，不在 V7-0 提前改写 |

V7-0 不创建 Lane A/B/C 的结果文档，不运行任何 heavy，不修改 V6 负结果，不更新普通
solver/default，不写 raw artifact，也不执行 commit/push。V7 下一步只能在主审批准后按上述
顺序继续。
