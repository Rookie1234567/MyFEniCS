# Task039 Review Report V7：Hybrid iterative 分级内存目标与可测极限

## 0. 审阅决定

```text
review                                  = Task039 Review Report V7
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = 9ce588133375ed3848c7ddee4951a98b1ac7d483
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
primary_method_line                     = Hybrid direct reference + Hybrid iterative limit finding
physical_case                           = 5 nm / 1° grazing / phi=0° / S
formal_spatial_discretization           = p6/h4
formal_Hybrid_M                         = 480 per direction
formal_MPI                              = 8
matched_Hybrid_direct_reference_GiB     = 93.377006531
minimum_objective                       = full workflow peak strictly below direct
robust_minimum_saving                   = 5 percent
strongest_primary_target                = at least 50 percent saving
half_memory_target_GiB                  = 46.6885032655
Full3D_new_heavy_run                    = forbidden
full_0p7nm_PDE                          = forbidden
third_BLR_profile                       = forbidden
generic_ILU_or_budget_scan              = forbidden
full_ephemeral_Petrov_rerun             = forbidden
heavy_jobs_concurrent                   = forbidden
default_heavy_timeout_seconds           = 21600
conditional_iterative_timeout_seconds   = 28800 total, one time only
response_required                       = response_v8.md
```

本 Review 根据用户最新明确指令纠正 V6 的资源目标定位：

> Hybrid iterative 的最低成功标准，是在同一物理、网格、M480、MPI8 和全过程资源口径下，
> 峰值内存低于 Hybrid direct；节省 50% 以上是最强主目标，而不是所有候选进入研究的唯一
> 前置门槛。

项目既要争取 50% 以上节省，也必须在达不到 50% 时测清：

```text
实际能节省多少
内存最低点在哪里
哪个对象或算法阻止继续下降
进一步节省会付出多少迭代和时间代价
```

因此 V7 从“单一半内存硬裁决”改为“分级资格 + 有限的 Pareto/极限测量”。历史 V6
结果和当时的 hard-stop 分类保持不变；V7 不回写或美化旧负结果，而是依据新的用户目标
授权新的、结构上不同的测量。

---

## 1. V6 结果的正确继承

### 1.1 已建立事实

| 路径 | 数值/物理 | process-tree RSS | 当前角色 |
|---|---|---:|---|
| h4 Hybrid direct | own Gate pass | `93.377006531 GiB` | matched reference |
| V4 exact-side iterative | residual/physics/direct comparison pass | `104.334560394 GiB` | numerical oracle，resource fail |
| V6 post-compaction exact-side | 在 `bottom_F_ready` 前受控停止，未完成 setup | `42.708419800 GiB` | incomplete setup evidence |
| V6 full-ephemeral Petrov bottom | 在 owner-ready/rank64 前受控停止 | `22.025470734 GiB` | current construction negative |

V6 的两个停止均符合当时 Review V6 的合同：

```text
42.7084 GiB > 42.0197 GiB setup line
22.0255 GiB > 22.0000 GiB construction line
```

但它们不能扩大解释为：

```text
exact-side 不可能低于 direct
Petrov 数学修正无效
50% 节省不可能
Hybrid iterative 的实际极限已经测清
```

V6 exact-side 未到完整 bottom/top side setup；V6 Petrov 未生成 Z/Y/E、rank64 或六组
numerical probes。被否定的是当轮执行合同和 full-ephemeral construction，不是所有后续
表示和算法。

### 1.2 仍然冻结的负方向

下列方向已有足够证据，不因目标更正而重开：

```text
第三个 MUMPS BLR profile
普通 ILU0/ILU1/drop-tolerance 扫描
只把 fixed-budget 32 改成 64/128
原样重跑 full right/left 1920-vector ephemeral Petrov
把 explicit-W 的几十 MiB 变化写成十余 GiB RSS 修复
```

---

## 2. V7 正式分级资源目标

唯一 matched baseline 为：

```text
B_direct = 93.377006531 GiB
```

完整工作流峰值定义为所有串行 producer、setup、solve、recovery 和 postprocess 进程峰值的
最大值，而不是相加：

```math
B_{\mathrm{workflow}}
=
\max_p B_p.
```

正式分类如下。

| 分类 | 完整工作流峰值 | 含义 |
|---|---:|---|
| no saving / fail | `>=93.377006531 GiB` | 不低于 direct |
| minimum lower-memory positive | `<93.377006531 GiB` | 满足用户最低目标，但可能接近测量噪声 |
| robust minimum pass | `<=88.708156204 GiB` | 至少节省 5%，具备工程余量 |
| useful pass | `<=74.701605225 GiB` | 至少节省 20% |
| strong pass | `<=65.363904572 GiB` | 至少节省 30% |
| major pass | `<=56.026203919 GiB` | 至少节省 40% |
| half-memory strategic pass | `<=46.688503266 GiB` | 至少节省 50%，最强主目标 |
| stretch pass | `<=37.350802612 GiB` | 至少节省 60% |

任何 `<93.377006531 GiB` 的完整、数值合格结果都必须保留为正结果，不能因为没有达到
50% 而改写成失败；但只有 `<=46.688503266 GiB` 才能称为 half-memory strategic pass。

如果只低于 direct 不足 5%，必须同时报告采样间隔、重复性边界和 allocator 高水位，并使用：

```text
LOWER_MEMORY_POSITIVE_WITH_SMALL_MARGIN
```

不得直接称 production-qualified。

即使达到 50%，仍只表示固定 5 nm h4 Hybrid 案例通过，不等于 0.7 nm、任意三维或 ordinary
production 通过。

---

## 3. V7 的核心目标：建立内存—精度—时间 Pareto 前沿

V7 不只寻找一个 pass/fail 点。每个候选必须形成表格：

```text
candidate / rank / representation
process-tree peak RSS
setup wall / apply wall / total wall
base/coarse factor inventory
worst mandatory side residual
preferred modal/external residual
outer iterations（若运行）
最终 physics delta（若运行）
```

需要回答：

1. 最低内存的数值可用点是什么；
2. 首个低于 direct 的点是什么；
3. 首个达到 20%、30%、40%、50% 节省的点是否存在；
4. 若不存在，当前实测极限和 blocker 是什么；
5. 节省内存时，迭代次数与时间如何增长。

不允许开放参数扫描。只使用本 Review 预先冻结的有限检查点和候选结构。

---

## 4. Lane A：重新完成 post-compaction exact-side 极限测量

### 4.1 定位

exact-side 仍不是长期 0.7 nm production candidate，因为它保留 full side sparse factors。
但 V6 在 setup 尚未完成时被 50% 预留线终止，因此当前不知道：

```text
V5 factor-only + single-Schur + GMRES10
在完整 h4 setup/full run 中能否低于 Hybrid direct
```

为了测清 5 nm 当前架构的实际极限，V7 允许一次新的完整 setup-only 测量。它是
`limit-finding/reference lane`，不是恢复 exact-side 的 0.7 nm production 身份。

### 4.2 冻结配置

```text
same h4 selected-mode packet
same 5 nm / 1° / phi0 / S / p6h4 / M480 / MPI8
factor-only exact side handles
single-build modal Schur + frozen sampled repeat
fixed linear GMRES10 setup
bottom build → cleanup → top build
no outer solve in setup-only
```

### 4.3 新 advancement Gate

V6 的 `42.019652939 GiB` 继续作为“50%目标的优秀 setup line”，但不再是 V7 的唯一停止线。

新的 setup-only 分类：

```text
<=42.019652939 GiB  = half-memory-compatible setup
<=84.039305878 GiB  = minimum-goal advancement pass
>84.039305878 GiB   = no full exact-side formal
```

`84.039305878 GiB` 为 direct 的 90%，给 outer Krylov、solution/recovery 和 telemetry 留出约
10% 余量。

如果完整 setup peak `<=84.039305878 GiB`，且：

```text
outer-ready state reached
bottom/top exact factor lifecycle audited
packet/QEP references released
swap=0
```

则只允许一次 exact-side full formal。完整结果按 §2 分级；即使低于 direct，也必须标记：

```text
5NM_EXACT_SIDE_LOWER_MEMORY_CASE_RESULT
NOT_0P7NM_SCALABLE_DUE_FULL_SIDE_FACTORS
```

如果 setup 超过 84.039 GiB，则 exact-side 极限测量结束，不运行 full formal，并报告最高阶段、
峰值和无法继续的对象重叠。

---

## 5. Lane B：streamed owner-row Petrov producer/consumer

### 5.1 V6 full-ephemeral 路径不得原样重跑

V6 在同时 hydrate：

```text
positive/negative × right/left × M480 = 1920 full ephemeral vectors
```

之后越过 22 GiB。该表示不面向 0.7 nm。

V7 必须改为进程拆分和流式 source/basis construction。

### 5.2 Producer

独立 producer 只做：

```text
读取一个 mode pair或固定小 batch
→ 生成 owner-row right/left physical sources
→ 增量 QR / biorthogonal update
→ 形成 nested Z/Y checkpoints
→ 销毁当前 full mode、Function、Vec和assembly temporaries
→ 继续下一 batch
```

禁止同时建立 whole-endcap ILU/Woodbury base action、outer operator 或读取 holdout exact-output。

冻结 nested checkpoints：

```text
rank = 64 / 128 / 256 / 512
```

每个 checkpoint 写 hash-bound、owner-row sharded basis packet；训练与 holdout严格分离。

### 5.3 Consumer

独立 bottom consumer：

```text
建立 matrix-free side F
建立 fixed cheap base action
读取 rank64 owner-row Z/Y
构造 E = Y^H F Z
运行 frozen six-probe holdout
```

只有 rank64 数值不通过，才依次读取同一 basis packet 的 rank128、256、512。不得重新 hydrate
模式或重新训练。

冻结数值 Gate：

```text
finite                              = true
repeat relative error               <= 1e-10
linearity relative error            <= 1e-10
all mandatory true residual         <= 1e-2
modal+/modal-/external residual      <= 1e-3
coarse E condition                  <= 1e12
exact/global direct factor          = 0/0
swap                                = 0
```

使用第一个通过的 rank 作为 bottom preferred point；同时保留之前所有 rank 的内存、时间和
残差，形成 Pareto 表。如果 rank512 仍不通过，Petrov 数值能力在该冻结 source family 下
分类为 `NUMERICAL_LIMIT_NOT_REACHED_BY_RANK512`。

### 5.4 Petrov 资源线

V6 的：

```text
producer/construction 22 GiB
retained consumer 16 GiB
```

保留为 half-memory-oriented aggressive lines，不再作为所有研究的唯一 family-closure line。

新的分级 Gate：

```text
producer peak < 93.377006531 GiB required for minimum workflow saving
producer peak <= 88.708156204 GiB robust minimum
consumer setup <=84.039305878 GiB required before full solve
full workflow peak classified by §2
```

因此，V6 的 `22.025 GiB` 仍是当时合同下的真实 resource stop，但不能据此永久关闭 streamed
Petrov。V7 不允许放宽后原样重跑；只有完成流式 producer/consumer 架构后才允许新的正式
测量。

### 5.5 从 bottom 到 full

执行顺序：

```text
bottom producer/consumer
→ bottom first passing rank
→ top producer/consumer
→ both-side setup-only
→ one full h4 iterative formal
```

bottom 未通过前，top、outer、recovery 和 R/T/A 全部禁止。both-side setup peak 必须
`<=84.039305878 GiB` 才能运行 full formal。

full formal 使用可变 side approximation 时必须为 FGMRES；固定线性且重复性通过时才允许
GMRES。最终必须通过全部 residual、R/T/A/A_volume、selected E/H、canonical、normal flux、
channels 和 external-key identity Gate。

---

## 6. Lane C：独立 side layer-graph audit

V6 将 layer audit 绑在 exact-side heavy setup 上，最终在 `bottom_F_ready` 前停止，所有 graph
字段均为 `not_available`。

V7 允许一个独立 graph-only audit：

```text
构造 h4 side mesh / FE space / constraints / static-condensation connectivity
不运行 QEP
不 hydrate M480
不建立数值 factor
不运行 PDE solve
```

必须分别统计：

```text
local FE/static-condensed same-layer NNZ
adjacent-layer NNZ
long-range NNZ
每层 active rows
block half-bandwidth
DtN low-rank/global coupling的独立身份
```

只有 local FE 图满足预先报告的近邻占比和带宽证据后，下一 Review 才能授权：

```text
z-layer sweeping
hierarchical Schur
cyclic reduction
```

V7 不直接实现或重型运行 sweeping solver。

---

## 7. 时间政策

内存仍为第一目标，但需要记录极限对应的时间代价。

默认 heavy timeout：

```text
21600 s = 6 h
```

仅已进入 outer iterative solve、swap=0、峰值低于 direct、残差有客观下降趋势时，允许一次
延长到：

```text
28800 s = 8 h total
```

Producer、QEP、direct、setup-only、graph audit、尚未进入 outer 的阶段不得自动延长。

即使一个候选低于 direct，如果 8 小时仍未完成，分类必须同时写：

```text
memory positive
wall-time not qualified
```

不得因时间失败删除其内存正结果。

---

## 8. 重型运行上限

```text
V7 exact-side complete setup-only      <= 1
V7 exact-side full formal              <= 1 conditional
streamed Petrov basis producer         <= 1
bottom Petrov consumer/rank ladder     <= 1
Top Petrov consumer                    <= 1 conditional
both-side Petrov setup-only            <= 1 conditional
Petrov full h4 formal                  <= 1 conditional
side graph-only audit                  <= 1 lightweight
Full3D new heavy                       = 0
0.7 nm PDE                             = 0
full-ephemeral Petrov rerun            = 0
```

rank64/128/256/512 必须是同一 producer packet和同一 consumer过程中的嵌套 checkpoint，不得
拆成四次独立训练 campaign。

---

## 9. 必须输出的极限证据

```text
outcomes/review_v7_inherited_audit.md
outcomes/v7_exact_side_limit.md
outcomes/v7_streamed_petrov_basis.md
outcomes/v7_petrov_bottom_pareto.md
outcomes/v7_petrov_full_result.md          # conditional
outcomes/v7_side_layer_graph.md
outcomes/v7_memory_limit_summary.md
outcomes/v7_0p7nm_implications.md
outcomes/test_summary.md
outcomes/summary.md
docs/development_progress.md
response_v8.md
```

`v7_memory_limit_summary.md` 必须明确给出：

```text
最低测得 RSS
首个低于 direct 的候选
最大已建立节省百分比
未达到的下一级目标
继续下降的主 blocker
内存下降对应的时间/迭代代价
```

所有数据必须区分 `measured / derived / predicted / not_run / controlled_stop`。

---

## 10. 测试与治理

开始前第一项提交仍为 docs-only inherited audit。数值核心修改必须进入 `src/`，runner 只做
参数化 orchestration。

至少需要：

```text
streamed mode batch ownership/release tests
incremental owner-row QR repeat and rank tests
basis packet hash/shape/coverage tests
training/holdout separation tests
Petrov E rank/condition and destroy tests
serial/MPI2/MPI4 tiny producer-consumer tests
graph-only connectivity audit tests
Ruff / format-check / compileall
focused pytest
check_benchmarks --no-write
compact JSON / Markdown / diff-check
```

full repository pytest 若不运行，必须写 `not_run`；不得声称 CI。

未经最终 review 和用户授权，不得 merge master。research-negative BLR、fixed-budget、
full-ephemeral Petrov 与未资格化 solver 不得提升为 ordinary production。

---

## 11. 当前核心判断

V6 的 50% 目标方向是对的，但把它作为所有候选继续研究的唯一门槛过于严格，会在尚未测清
实际极限之前提前关闭路线。

V7 的正确策略是：

```text
最低目标：完整 iterative 必须低于 matched Hybrid direct
工程目标：至少稳定节省 5%–30%
主要强目标：节省 50%以上
研究职责：达不到50%时，也要用有限checkpoint测出真实极限与blocker
```

exact-side 用于测当前实现的低内存下限并继续作为 oracle；streamed owner-row Petrov 是主要
factor-free candidate；独立 layer graph 决定下一步是否值得发展 sweeping/hierarchical
side solver。

50% 仍是面向 0.7 nm 的理想战略标准，但不再把 20%、30% 或40%的真实正结果误判为失败。