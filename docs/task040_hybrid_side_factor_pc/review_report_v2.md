# Task040 Review Report V2：45 GiB Gate 释义与 interface-Schur producer/consumer 分进程续研

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V2
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = 6c5e39598aada3c1ffec6affc3cb0977f2575b0e
reviewed_numerical_source_sha               = 16ecba568be901325e53c3652aa10bb432de5a6b
reviewed_response                           = response_v2.md
reviewed_resource_record                    = task040_v1_2_v1_3_run_b_resource_stop_v1.json
review_status                               = PASS_WITH_QUALIFICATIONS
scalar_transmission                         = CLOSED_NUMERICAL_DIRECTIONAL_NEGATIVE
V1_2_exact_interface_oracle                 = NOT_QUALIFIED_DUE_RESOURCE_LIFECYCLE_STOP
V1_3_projected_transmission                 = NOT_EVALUATED
45_GiB_implies_full_workflow_over_80_GiB    = false
next_primary_action                         = PROCESS_SPLIT_AND_HASH_BOUND_PACKET
same_branch_continuation                    = required
new_branch                                  = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
physical_case                               = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
QEP_M_physical_DtN_global_Hybrid_change     = forbidden
full_0p7nm_PDE                              = forbidden
response_required                           = response_v3.md
```

正式裁决：

1. `45 GiB` 不是由“组件一旦超过45 GiB，完整 workflow 就必然超过80 GiB”推导出的硬数学
   阈值；
2. 它原本是一个保守的 Level-A 资源线：既低于单侧 exact-factor 阶段的 `49.313 GiB`，又接近
   相对 direct 节省50%所对应的 `46.6885 GiB`，同时用于阻止同一进程中的对象和 allocator
   高水位继续叠加；
3. 最新 Run B 在 exact oracle factor 已记录 `3 -> 0` 后、V1-3 projected setup 尚未 ready 时，
   以 `45.057529 GiB` 触发 hard stop。该结果只证明原来“V1-2 + V1-3 同一 MPI 进程连续执行”
   的生命周期不合格，不证明 projected transmission 数学失败，也不证明完整 workflow 必然超过
   `80.025856 GiB`；
4. 因 Review V1 的正式资源 Gate 已触发，继续执行必须由本 Review V2 重新授权，不能只用口头
   指令越过原 Gate；
5. 下一轮不改变 transmission 数学、mode span、分区、QEP、physical DtN 或 Hybrid 方程；只把
   V1-2 exact-interface oracle 与 V1-3 projected-transmission candidate 拆成两个独立进程，
   通过 hash-bound packet 传递必要的小矩阵和 owner-row数据；
6. 诊断 oracle producer 与生产候选 consumer 采用不同资源语义：oracle可有有限的诊断余量，
   但不能被提升为0.7 nm production pass；consumer和后续 bounded Level B继续执行严格低内存
   Gate。

---

## 1. 已审阅事实

### 1.1 完整 workflow 基线

| 路线 | 范围 | process-tree RSS peak | 数值/物理状态 |
|---|---|---:|---|
| Hybrid direct h4 | full workflow | `93.377006531 GiB` | matched authority pass |
| exact-side Hybrid iterative h4 | full workflow | `80.025856018 GiB` | residual、recovery、R/T/A、E/H、canonical、channels pass |
| T40-3 scalar Level A | bottom bare-F component | `28.333576202 GiB` | one-apply transmission fail |
| V1-1 scalar FGMRES | bottom bare-F component | `27.790115356 GiB` | directional fail by16 steps |
| V1-2/V1-3 Run B | combined component attempt | `45.057529449 GiB` | resource stop before numerical qualification |

组件峰值不能直接冒充完整 workflow saving tier。

### 1.2 Scalar route 已经完成数值裁决

V1-1 对五个非零 source 得到：

```text
r16                         = 0.98486 ... 0.99368
optimal-scaled rho*         = 0.99895 ... 0.99937
absolute direction corr     = 0.03563 ... 0.04587
conditional 32-step         = not_run_by_gate
```

因此当前 fixed scalar transmission 不是单纯幅值或相位错误，而是没有提供有效的预条件方向：

```text
SCALAR_TRANSMISSION_DIRECTIONAL_FAIL
```

不得继续扫描 `beta`、sign、damping、restart或更多 scalar FGMRES steps。

### 1.3 V1-2/V1-3 没有形成数值负结果

Run B 到达：

```text
system_ready
lower/upper interface mass ready
v1_2_exact_oracle_ready      factors=3, lower modes=296, upper modes=480
v1_2_exact_oracle_released   factors=0
```

但没有到达：

```text
V1-2 probe/gate serialization
V1-3 projected_ready
V1-3 one-apply
V1-3 FGMRES checkpoint
run_summary serialization
```

正式资源记录：

```text
peak RSS       = 45.057529449 GiB
hard stop      = 45.000000000 GiB
overshoot      = 0.057529449 GiB
swap           = 0
termination    = watchdog absolute_memory_limit
SIGKILL        = not required
```

所以：

```text
V1-2 numerical qualification = NOT_ESTABLISHED
V1-3 numerical capacity       = NOT_EVALUATED
```

---

## 2. 45 GiB Gate 的正确含义

### 2.1 它不是完整80 GiB的直接预测公式

完整 workflow 峰值不是所有阶段峰值的简单求和。若两个阶段在不同进程中串行执行并彻底退出，
其冷启动工作流峰值应按：

```math
B_{workflow}
=
\max(B_{producer}, B_{consumer}, B_{full\ Hybrid}).
```

因此，一个 `45.1 GiB` 的离线/诊断 producer 并不会自动推出后续完整 workflow超过
`80.026 GiB`。

只有在同一进程中继续保留对象、allocator高水位或后续 candidate数据时，早期45 GiB才会显著
增加后续越过80 GiB的风险。最新 Run B 正是这种同进程高水位叠加，而不是一个完整工作流
容量外推。

### 2.2 原45 GiB包含三层工程意图

#### A. 低于单侧 exact-factor阶段

Task039 V7 的 bottom exact-factor阶段为：

```text
bottom F ready       = 23.195 GiB
bottom factor ready  = 49.313 GiB
```

Level-A candidate若已经高于约49.313 GiB，就没有证明替代单侧 exact factor的资源价值。

#### B. 保留面向50%节省的战略余量

相对 Hybrid direct 节省50%对应：

```text
93.377006531 / 2 = 46.688503266 GiB
```

45 GiB接近但略低于这一战略线，适合作为生产候选的强约束，但不是诊断 oracle的数学必要条件。

#### C. 防止同进程生命周期叠加

V1-2 exact factors、PETSc sparse blocks、mode bases、U/V/W和V1-3 base factors在同一进程连续
构造时，逻辑 `destroy()` 不保证操作系统立刻回收RSS。45 GiB hard stop用于在这种叠加失控前
安全终止，而不是判定 transmission数学失败。

### 2.3 新的资源语义

从本 Review起，必须区分：

```text
ORACLE_PRODUCER_RESOURCE
MECHANISM_CONSUMER_RESOURCE
SCALABLE_LEVEL_B_RESOURCE
FULL_WORKFLOW_RESOURCE
```

它们不得再共享一个没有语义区分的45 GiB结论。

---

## 3. 新的资源 Gate

### 3.1 V2-A exact-interface packet producer：诊断/oracle Gate

该进程不是0.7 nm production candidate，允许使用三个 cross-section exact oracle factors。

```text
preferred peak target       <=45 GiB
absolute hard stop          <=55 GiB
swap                        =0
factor lifecycle            =3 -> 0
full-side/global factor     =0/0
packet complete before exit =true
```

分类：

| Producer peak | 分类 | 是否可继续 |
|---:|---|---|
| `<=45 GiB` | `ORACLE_RESOURCE_TARGET_PASS` | 是 |
| `(45,55] GiB` | `ORACLE_RESOURCE_OVER_TARGET_BUT_BOUNDED` | 是，仅可作为诊断 packet producer |
| `>55 GiB` | `ORACLE_RESOURCE_HARD_STOP` | 否；只能转为逐group streaming生命周期 |

`45–55 GiB`的 producer不得称为 scalable side inverse，也不得直接计为完整Hybrid production
memory pass。它只允许我们获得数学资格所需的离散接口 authority。

若第一次独立 producer在55 GiB内仍无法完整写包，唯一授权的生命周期 fallback为：

```text
group0 factor -> projected data -> write -> destroy/trim
group1 factor -> lower/upper/cross data -> write -> destroy/trim
group2 factor -> projected data -> write -> destroy/trim
```

使 simultaneous exact-factor count从3降到1。不得改变Schur公式、probe、mode span或数值Gate。

### 3.2 V2-B projected-transmission consumer：机制候选 Gate

Fresh consumer不得建立 exact interface Schur oracle，也不得读取其factor对象，只读取packet。

```text
peak hard line                    <45 GiB
swap                              =0
exact-interface oracle factors    =0
full-side/global factors          =0/0
scalar cross-section base factors =3（仍为Level-A oracle-only）
projected owner-row basis replica =false
FE-sized numeric allgather        =false
```

如果 fresh consumer仍超过45 GiB，分类为数据表示/consumer资源失败，不是 transmission数学失败。
此时唯一允许的修正是减少 U/V/W 临时复制、Gamma-sparse表示和batched W construction；不得修改
mode span、分区或数学算子。

### 3.3 Level B真正可扩展候选

只有 V2-B 数值通过后才进入原 Task040 bounded patch Level B：

```text
full-cross-section exact factors =0
max_local_rows                   <=1024
bottom construction peak         <=35 GiB
strong target                    <=30 GiB
post-setup retained              <=30 GiB
PC resident growth               =O(N) target
```

### 3.4 完整 Hybrid Gate

完整工作流仍使用：

| 分类 | full workflow peak |
|---|---:|
| 未刷新当前 iterative | `>=80.025856018 GiB` |
| 新最低点 | `<80.025856018 GiB` |
| 至少节省20% vs direct | `<=74.701605225 GiB` |
| 至少节省30% vs direct | `<=65.363904572 GiB` |
| 至少节省40% vs direct | `<=56.026203919 GiB` |
| 至少节省50% vs direct | `<=46.688503266 GiB` |

Producer、consumer和full formal若为不同进程，完整冷工作流峰值取各阶段实测峰值的最大值；同时
必须另列 production-only peak，不得混淆两种口径。

---

## 4. V2-A：hash-bound interface-Schur packet producer

### 4.1 冻结项

完全继承 Review V1：

```text
5 nm / 1 deg / phi0 / S / p6h4 / M480 / MPI8
same input / physical SHA / selected-mode packet
same bare F and three groups
same lower 296 Fourier/Floquet span
same upper M480 QEP span
same scalar complement
same exact discrete interface Schur formula
same probes and fixed seeds
same left/right non-Hermitian dual convention
QEP calls =0
PDE solve =not_run
```

### 4.2 Producer只做以下工作

```text
assemble same bare F and interface supports/masses
build exact interface Schur oracle
construct lower/upper Z/Y owner-row bases
compute all physical/interface/complement/cross-interface probes
compute projected Gram/scalar/exact matrices
export exact-minus-scalar owner-row correction factors
serialize full V1-2 Gate before destroying oracle
write hash-bound packet
release all three factors
collective heap trim if already reviewed/available
exit MPI process
```

禁止在producer内构造V1-3 projected base factors或运行FGMRES。

### 4.3 Packet最低内容

```text
schema/version/source SHA
input/physical/selected-packet/exact-spool hashes
lower/upper mode keys, beta, branch, polarization hashes
interface z/material/support hashes
group order and Gamma canonical row identities
owner ranges and row-key-to-owner mapping hash
Z/Y or finalized U/V owner-row shards
Gram G and projected scalar/exact matrices
rank, singular values, condition
physical/interface/complement/cross-interface probe reports
V1-2 identity/finite/projection/gram/complement/middle-cross Gate
factor and resource lifecycle
all shard and manifest SHA256
```

只保存PETSc整数global row不够。必须保存稳定的 canonical active-trace/Gamma row identity，并在
fresh consumer中证明 key-remap round trip；防止重复 Task039 response packet的跨运行行号问题。

### 4.4 Producer数值 Gate

必须在oracle销毁前写出并由独立checker重算：

```text
identity                  =pass
all finite                =pass
left/right Gram full rank =pass
condition                 <=1e12
complement orthogonality  <=1e-8
all frozen probe identities exact
middle cross-interface probes finite/nonzero
no FE-sized dense Schur
no FE-sized numeric allgather
```

Producer只负责建立 authority，不要求它本身成为side inverse。

---

## 5. V2-B：fresh projected-transmission consumer

### 5.1 Fresh进程合同

```text
new MPI8 process
reassemble same bare F
rebuild same three scalar base factors
read V2-A packet
canonical Gamma key remap
construct projected group inverse from packet U/V/G
never build exact interface oracle
run one-apply audit
run fixed right-FGMRES screen
exit and release all factors
```

### 5.2 不允许的隐藏重算

```text
QEP rerun
exact interface Schur factorization
response-packet producer
physical DtN redesign
new mode selection
mode-count enrichment
basis re-normalization from current outcome
sign/beta/damping scan
```

### 5.3 Consumer实现 Gate

```text
packet hashes and identities       =exact
canonical Gamma remap round trip   <=1e-12
finite/zero/repeat/linearity       =pass
base factor count ready/cleanup    =3 -> 0
exact-interface factor count       =0
full-side/global factor count      =0/0
owner-row basis replicated         =false
FE-sized allgather                  =false
peak                               <45 GiB
swap                               =0
```

### 5.4 Consumer数值 Gate

使用同一五个非零 source和physical zero-map：

```text
right-FGMRES checkpoints =0/4/8/16/conditional32
```

只有16步 finite且最近8步下降至少 `0.25 decade` 时允许32。

首个同时满足：

```text
all mandatory true residual <=1e-2
modal+ / modal- / external  <=1e-3
```

的checkpoint为 preferred。

决策：

| 结果 | 分类 | 后续 |
|---|---|---|
| 数值与资源均通过 | `PROJECTED_EXACT_TRANSMISSION_PASS` | 进入analytic mode-aware V2-C |
| 资源通过但32步数值失败 | `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` | 停止，等待coarse/long-range review |
| 数值趋势存在但consumer资源失败 | `PROJECTED_CONSUMER_RESOURCE_FAIL` | 仅优化U/V/W表示后重跑同一数学候选 |
| packet/remap身份失败 | `PACKET_COORDINATE_IDENTITY_FAIL` | 停止并修复实现，不作算法结论 |

---

## 6. 条件后续路线

### 6.1 V2-C analytic mode-aware transmission

只有 V2-B通过后才运行：

```text
lower uniform substrate:
    order-dependent Floquet beta_mn and S/P admittance
upper mixed cross-section:
    inherited M480 right/left trace-traction modal action
scalar complement retained
```

必须先与 V2-A exact oracle比较，再运行同一one-apply/FGMRES Gate。禁止mode-count、shift、
rational order或damping扫描。

### 6.2 V2-D bounded patch Level B

只有 analytic 或明确授权保留 projected transmission通过后，才删除三个 cross-section exact base
factors，改为：

```text
fixed local FGMRES
+
bounded overlapping patch PC
+
max_local_rows <=1024
```

未到 transmission pass前不得启动Level B。

### 6.3 V2-E bottom/top/both/full

Level B bottom通过后：

```text
same configuration top
both-side setup-only
unique full Hybrid formal with outer FGMRES
conditional h3 scaling probe
```

所有 Task039 residual/physics/canonical/channel Gate继续冻结。

---

## 7. Codex 自主修复 implementation bug

Codex可自行修复并继续：

```text
packet path/schema/hash透传
canonical row-key generation/remap
PETSc ownership/VecScatter/owner/ghost
workspace alias/copy/lifecycle/destroy顺序
marker/checker/watchdog/artifact wiring
已证明的内存泄漏或不必要临时副本
```

必须：

```text
保留失败root
分类implementation_failure
unit/tiny/MPI复现
最小修复
增加回归测试
新SHA重跑同一阶段
```

以下不得冒充bug fix：

```text
改变mode span或M
改变分区、sweep、beta、sign、damping
增加coarse/new PC family
放宽consumer/Level B/full workflow Gate
改变physical DtN、QEP或Hybrid方程
```

---

## 8. 连续执行顺序

```text
V2-0  docs-only inherited audit
V2-A1 independent V1-2 packet producer
V2-A2 conditional one-factor-at-a-time producer fallback
V2-B1 fresh packet identity/remap consumer setup
V2-B2 projected one-apply and fixed FGMRES screen
V2-C  conditional analytic mode-aware transmission
V2-D  conditional bounded patch Level B
V2-E  conditional bottom/top/both/full Hybrid
V2-F  conditional h3 scalability probe
V2-G  outcomes、Pareto、response_v3.md
```

Codex在正常通过或可修复implementation bug后自动继续。只有真正的数值、资源、identity、
scalability Gate或全部授权阶段完成时才停止等待review。

---

## 9. 时间与运行规则

```text
one heavy job at a time
swap =0
default heavy timeout =6 h
```

只有已进入FGMRES、RSS低于对应阶段hard line、finite且最近90分钟有持续true-residual下降时，
才允许一次延长到总计8小时。

Producer不是Krylov solve，不得因接近完成自动延长时间；但它使用本Review独立的55 GiB oracle
hard line。

每次heavy记录：

```text
process-tree RSS/PSS/USS（可用时）
swap
stage markers
factor inventory
packet/shard hashes
true residual history
termination reason
```

---

## 10. 必需交付物

```text
docs/task040_hybrid_side_factor_pc/outcomes/review_v2_inherited_audit.md
docs/task040_hybrid_side_factor_pc/outcomes/interface_schur_packet_producer.md
docs/task040_hybrid_side_factor_pc/outcomes/projected_transmission_consumer.md
docs/task040_hybrid_side_factor_pc/outcomes/analytic_mode_aware_transmission_v2.md
docs/task040_hybrid_side_factor_pc/outcomes/bounded_patch_pc.md
docs/task040_hybrid_side_factor_pc/outcomes/bottom_full_side.md
docs/task040_hybrid_side_factor_pc/outcomes/top_full_side.md
docs/task040_hybrid_side_factor_pc/outcomes/both_side_setup.md
docs/task040_hybrid_side_factor_pc/outcomes/full_hybrid_result.md
docs/task040_hybrid_side_factor_pc/outcomes/h_refinement_scaling.md
docs/task040_hybrid_side_factor_pc/outcomes/memory_residual_time_pareto.md
docs/task040_hybrid_side_factor_pc/outcomes/summary.md
docs/task040_hybrid_side_factor_pc/outcomes/test_summary.md
docs/task040_hybrid_side_factor_pc/response_v3.md
benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/<V2 compact records>
```

未运行阶段必须标记 `not_run_by_gate`，不得预写通过。

---

## 11. 停止条件

立即保存证据并停止：

```text
branch/input/physical/packet identity不一致
producer >55 GiB或swap>0
producer packet未完整写出且已用完逐group fallback
consumer >=45 GiB且完成一次表示优化后仍越线
canonical Gamma row remap失败
任何NaN/Inf
projected 32步数值失败
证据明确需要coarse/global information
max_local_rows >1024
bottom未通过却启动top/both/full
完整Hybrid residual或physics Gate失败
ordinary defaults、Task039或master被修改
```

资源停止不等于数值失败；数值失败也不得写成OOM。

---

## 12. 本轮对用户问题的最终回答

```text
45 GiB不是“超过后完整workflow大概率必然超过80 GiB”的直接公式。
```

它是原 Level-A 的保守目标和同进程安全线。最新 `45.0575 GiB` 发生在 exact oracle已释放、
V1-3尚未ready的生命周期重叠中，不能用于预测完整80 GiB峰值。

正确做法不是简单把所有Gate统一调高，而是：

```text
诊断exact oracle producer：独立进程，preferred 45 GiB，absolute 55 GiB
projected mechanism consumer：独立进程，继续严格 <45 GiB
真正scalable Level B：<=35 GiB，强目标<=30 GiB
完整Hybrid：必须刷新80.026 GiB并按20/30/40/50%分级
```

这样既不会因0.058 GiB的oracle高水位丢失数学证据，也不会把诊断性exact factor偷偷放宽为
0.7 nm生产架构。
