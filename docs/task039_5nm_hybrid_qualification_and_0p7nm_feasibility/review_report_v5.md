# Task039 Review Report V5：Hybrid iterative 内存回归消除与 0.7 nm 定向优化

## 0. 审阅决定

```text
review                                  = Task039 Review Report V5
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = 508d81ab1cffe26aff29038ab15f0b14a7516cde
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
primary_method_line                     = Hybrid direct authority + Hybrid iterative memory research
Full3D_new_heavy_run                    = deferred / forbidden in this Review
Full3D_existing_evidence                = retained, not deleted or reclassified
physical_case                           = 5 nm / 1° grazing / phi=0° / S
formal_spatial_discretization           = p6/h4
formal_Hybrid_M                         = 480 per direction
formal_MPI                              = 8
h4_Hybrid_direct_reference              = frozen V4 shared-packet result
h5_current_direct_sidecar               = authorized once, nonblocking curiosity measurement
full_0p7nm_PDE                          = forbidden
0p7nm_component_capacity_update         = required
neural_or_learned_factor                = frozen
ordinary_ILU_parameter_sweep            = forbidden
heavy_jobs_concurrent                   = forbidden
default_heavy_timeout_seconds           = 21600
conditional_iterative_extension_seconds = 28800 total, one time only
response_required                       = response_v6.md
```

本 Review 接受用户的阶段性路线选择：Task39 继续留在当前执行分支，后续以 Hybrid 为主，
用 Hybrid direct 作为同一 Hybrid 方程的数值、物理和资源参考，集中研究 Hybrid iterative
如何低于 direct 的峰值内存，并优先处理会在 0.7 nm 放大的 local side factor、显式
Woodbury `W`、modal Schur、coupling 和对象生命周期问题。

Full3D 路线在本 Review 中只是暂停新的重型运行，不是从项目最终目标中删除。传统 Hybrid
依赖内部区域可模态传播，仍不能证明任意非可分三维结构已经解决；项目级 arbitrary-3D
blocker 必须继续标记为 `deferred/unresolved`。

---

## 1. 用户本轮授权与边界

用户明确授权：

1. Task39 继续在原分支开发，不另建 Task 或分支；
2. 暂停新的 Full3D heavy work；
3. 以 h4 Hybrid direct 为当前 Hybrid 方程 reference；
4. 研究 Hybrid iterative 尽可能降低内存，时间暂列第二优先级；
5. 所有设计都要审视未来 0.7 nm 的扩展风险；
6. 在主任务开始前，额外测量一次“当前 shared-packet/lifecycle 实现下 p6/h5 Hybrid direct
   的内存需求”，仅出于好奇，不作为 V5 主 Gate；
7. 正式 heavy run 默认设置 6 小时 Gate；若 iterative 已进入真实迭代阶段、接近 6 小时且
   有客观收敛希望，可按 §6.3 的规则受控延长一次。

上述授权不允许：

```text
改变波长、角度、材料、几何、偏振或 M480
把 Hybrid direct 称为 continuum 或 arbitrary-3D authority
把 numerical pass 偷换成 resource/production pass
恢复普通 ILU0/ILU1 广泛扫描
运行完整 0.7 nm PDE
删除 V4 resource fail 或其他历史负结果
```

---

## 2. V4 已建立事实与本轮问题

### 2.1 h4 同架构比较

V4 的正式 h4 结果共享 5 nm、1°、phi=0、S、p6/h4、M480、MPI8 和同一 selected-mode
packet：

| 方法 | 数值/物理 | reuse wall | cold wall | process-tree RSS | 最终分类 |
|---|---|---:|---:|---:|---|
| Hybrid direct | own pass | 6771.478625 s | 8430.560853 s | 93.377006531 GiB | `HYBRID_DIRECT_H4_OWN_PASS` |
| Hybrid iterative exact-side | pass | 12357.484926 s | 14016.567154 s | 104.334560394 GiB | `HYBRID_ITERATIVE_H4_EXACT_SIDE_NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL` |

Iterative 与 direct 的 R/T/A/A_volume、selected E/H、canonical、normal flux、600-channel
checker 和五项 residual 均通过；resource fail 的唯一含义是：当前 iterative 峰值比 direct
高 `11.734745%`，时间也明显更长。该资源回归在本 Review 中不可接受，必须先消除，不能
因为 outer iteration=1 或物理量一致而提升为正结果。

### 2.2 h5 与 h4 direct 不能直接拟合网格增长

历史 1° p6/h5 Hybrid direct 峰值约 `85.02356 GiB`，但其 QEP、selected modes、coupling、
factor 和 recovery 生命周期与 V4 h4 shared-packet consumer 不同。旧 h5 峰值发生在
selected basis/field-reconstruction 高水位附近；V4 h4 已把 QEP producer 与 solve
consumer 分进程，并在 factor 前释放 mode basis，在 recovery 前释放 factor/global system。

因此：

```text
85.02 GiB (旧 h5) → 93.38 GiB (新 h4)
```

不是同实现、同生命周期的 h 缩放点，不能据此拟合 factor 或总 RSS 的网格指数。V5 的
h5 sidecar 用当前实现重跑后，才允许做“同架构 h5 与 h4”的工程比较；即便如此，它仍是
容量比较，不是空间收敛证明。

### 2.3 当前最可能的 h4 iterative 主导项

当前 exact-side iterative 没有 global Hybrid direct factor，但同时持有：

```text
bottom/top explicit side F
bottom/top exact sparse factors
bottom/top DtN C/D/H components
bottom/top Woodbury W_local、K、K-LU
P/T coupling blocks
2M x 2M modal Schur 和 LU
outer matrix-free operator
Krylov vectors与recovery state
```

h5 的 49.82 GiB 峰值发生在 exact-side factor 开始建立之前；网格细化到 h4 后，两个
local side factor、原始 F 和 action state 很可能成为新主导项。但 V4 compact record 没有
独立保存 bottom/top factor-ready 的 process-tree RSS、factor NNZ 和峰值 stage，因此这仍是
高概率假设，不是已完成的对象级归因。V5 必须先测清，再修改。

---

## 3. 冻结的 reference 与身份

### 3.1 h4 Hybrid direct reference

V5 的唯一正式 Hybrid 方程 reference 为既有 V4 h4/M480 shared-packet direct：

```text
classification          = HYBRID_DIRECT_H4_OWN_PASS
process-tree peak RSS   = 93.377006531 GiB
reuse wall              = 6771.478625 s
cold wall               = 8430.560853 s
R                       = 0.7331842736908196
T                       = 0.0002200986949369512
A_balance               = 0.26659562761424344
A_volume                = 0.26659627261424806
closure                 = 6.450000047397708e-7
external keys           = 600 exact, bottom/top 296/304
packet manifest SHA256  = 2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067
physical_model_sha256   = 8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c
```

若本地 ignored shared packet 仍存在且 manifest、identity、source 和 artifact hash 全部通过，
V5 h4 consumer 必须复用它，不得重新 QEP。只有 packet 缺失或 hash 失败时，才允许按完全
相同输入重新生成一次，并将新旧身份差异写入 evidence。

### 3.2 V4 iterative negative baseline

```text
process-tree peak RSS = 104.334560394 GiB
reuse wall            = 12357.484926 s
cold wall             = 14016.567154 s
outer iterations      = 1
five residual max     = 5.1673119e-10
resource saving       = -11.734745%
```

所有 V5 候选必须与该 baseline 及 h4 direct 同时比较。旧结果不得覆盖或改写。

---

## 4. V5-S：p6/h5 当前 Hybrid direct sidecar

### 4.1 目的和定位

本 sidecar 只回答：

> 使用 V4 当前的 QEP producer/selected-mode packet/consumer/lifecycle 路径，固定
> 5 nm、1°、p6/h5、M480、MPI8 时，Hybrid direct 实际需要多少全过程内存？

它是用户明确要求的好奇性资源测量，与 V5 主候选 Gate 无关。成功或失败均不得改变 h4
formal baseline、V5 候选顺序或最终分类。

### 4.2 冻结合同

```text
wavelength                       = 5 nm
grazing / phi / polarization     = 1° / 0° / S
Nedelec / mesh                   = p6/h5
M                               = 480 per direction
MPI                             = 8
method                          = Hybrid direct
QEP/solve                       = process split
selected modes                  = hash-bound owner-row packet
consumer QEP calls              = 0
factor lifecycle                = release before recovery/postprocess
external modes                  = dynamic exact inventory
ordinary defaults               = unchanged
```

执行一次 h5 packet producer 和一次 h5 Hybrid direct consumer。不得顺带运行 h5 iterative、
Full3D 或 M sweep。若已有 packet 能被严格验证并复用，可省略 producer；不得为省时间使用
不匹配的 h4 packet。

### 4.3 sidecar Gate 和输出

Direct own Gate仍要求 residual、projection、exact traction、R/T/A/A_volume、closure、E/H、
canonical、external keys、lifecycle 和 swap 全部通过。资源结果无“必须低于多少”的主任务
门槛，只需真实测量并分类：

```text
TASK039_V5_H5_CURRENT_DIRECT_RESOURCE_SIDECAR_MEASURED
```

若 own Gate 未通过，则按真实原因分类，不得为获得内存数字忽略数值失败。

输出：

```text
outcomes/v5_h5_current_hybrid_direct_sidecar.md
compact record under case 103 records/
packet producer peak/time
consumer RSS/PSS/USS、stage、factor NNZ、wall time
与旧 h5 direct 的 lifecycle-difference comparison
与当前 h4 direct 的 same-architecture capacity comparison
```

旧 h5 与新 sidecar 的差值只能称为 lifecycle/implementation comparison；新 h5 与新 h4
才可称为 same-architecture capacity comparison，仍不得称网格收敛。

---

## 5. V5 主目标

### 5.1 必须完成

1. 找到 h4 iterative 104.33 GiB 峰值的可审计 stage 和 resident stack；
2. 在不改变 Hybrid 方程和 M480 的前提下，先压缩 exact-side 路径的生命周期和重复状态；
3. 使正式 h4 iterative 至少低于 h4 Hybrid direct；
4. 以 `>=20%` 内存节省为 V5 meaningful target；
5. 建立不显式永久保存 `W` 的 action/streaming 原型，因为该问题会在 0.7 nm 放大；
6. 若 exact-side 即使瘦身仍不能达到 meaningful target，启动一个受控的 factor-light side
   inverse 候选，而不是继续普通 ILU 扫描；
7. 用 h5/h4 实测对象和阶段数据更新面向 2 TB 的 0.7 nm Hybrid 容量模型。

### 5.2 不属于本 Review

```text
新的 Full3D direct/iterative heavy run
0.7 nm full PDE
M > 480
改变 Hybrid interface 位置
改变材料/角度/偏振/几何
任意三维资格声明
普通 ILU0/ILU1/drop-tolerance 广泛扫描
神经网络或 learned factor
将 research route 改为 ordinary default
```

---

## 6. 资源与时间 Gate

### 6.1 内存分类

h4 Hybrid direct 的 `93.377006531 GiB` 是 V5 唯一 matched resource baseline。

| 分类 | iterative peak RSS 条件 | 含义 |
|---|---:|---|
| regression fail | `>= 93.377006531 GiB` | 仍不如 direct，不可接受 |
| positive but target not met | `<93.377006531 GiB` 且 `>74.701605225 GiB` | 已消除回归，但未达到 20% 目标 |
| meaningful pass | `<=74.701605225 GiB` | 相对 direct 至少节省 20% |
| strong pass | `<=65.363904572 GiB` | 相对 direct 至少节省 30% |
| major pass | `<=56.026203919 GiB` | 相对 direct 至少节省 40% |

V5 的正式目标为 `meaningful pass`。若只达到 positive，必须如实写
`RESOURCE_REGRESSION_REMOVED_TARGET_NOT_MET`，不能提升为 production qualification。

### 6.2 setup-only advancement Gate

任何完整 h4 PDE 候选前，先做 offline 或 setup-only 审计。只有满足以下之一才允许正式
full solve：

1. setup-only 的全过程 peak `<=84.039305878 GiB`（direct 的 90%），且关键 resident
   object 已全部进入正式 apply 状态；或
2. 使用 V4 stage-aligned 实测校准的保守上界证明，加入 outer solve/recovery 后仍低于
   `93.377006531 GiB`，并至少保留 5% 余量。

若 setup-only 在 mandatory cleanup 后已超过 direct baseline，立即受控停止，不运行完整
PDE。估计不得替代 process-tree 测量。

### 6.3 六小时时间 Gate 与受控延长

每个 heavy process 默认：

```text
timeout_seconds = 21600
```

时间不是 V5 的首要优化指标；在内存通过的前提下，允许 iterative 比 direct 更慢。但不得
无限运行。

只有 **outer iterative solve 已经开始** 时，才允许在 5.5 小时附近评估一次延长。QEP、
packet producer、direct factor/setup、sidecar direct、setup-only 或尚未进入 outer iteration
的阶段一律不得自动延长。

定义：

```text
r_max = max(reported, global, bottom, top, modal true residual)
formal threshold = 5e-9
extension checkpoint = 19800 s
one-time extended timeout = 28800 s total
```

自动延长必须同时满足：

1. swap=0，未触发 absolute memory stop，当前 process-tree RSS 低于 h4 direct baseline；
2. 当前 KSP reason 仍为 iterating，iteration number 持续增加，无 NaN/Inf；
3. 最近 90 分钟至少有 4 个独立 true-residual checkpoint；
4. `r_max` 在最近 90 分钟至少降低 0.5 decade，或当前已低于 `100 x 5e-9` 且最近 3 个
   best-so-far 值严格下降；
5. 对最近 checkpoint 的 `log10(r_max)` 做保守线性外推，达到 `5e-9` 的预测剩余时间
   不超过 7200 s；
6. 候选尚未违反 numerical、physics 或 memory objective；
7. 没有并行运行其他 heavy job。

满足时可自动把总 timeout 从 6 小时延长到 8 小时一次，并记录完整决策输入。8 小时仍未
收敛必须停止；继续延长需要新的用户授权或 review。若残差平台化、反弹、预测不稳定，
不得以“看起来可能”作为延长理由。

### 6.4 硬件安全

在当前约 256 GiB 执行环境中继续沿用：

```text
absolute process-tree terminate = 224000000000 bytes
swap                            = 0 required
poll interval                   <= 0.25 s
one heavy job at a time         = required
```

若实际机器或可用内存变化，必须在 preflight 中重新计算 warning/critical，但未经新 review
不得把 absolute line提高后重跑失败候选。未来 2 TB 是容量模型目标，不是本轮自动可用资源。

---

## 7. V5 执行顺序

```text
V5-0  inherited audit 与用户授权冻结
V5-S  current-lifecycle p6/h5 Hybrid direct sidecar
V5-1  existing h4 raw offline memory attribution
V5-2  instrumented h4 exact-side setup-only attribution（条件执行）
V5-3  exact-side factor/state/lifecycle compaction
V5-4  single-build modal Schur 与固定-PC Krylov storage reduction
V5-5  action-only / batched-streaming Woodbury W
V5-6  compact exact-side h4 formal run（通过 advancement Gate 后一次）
V5-7  factor-light side inverse component funnel（条件执行）
V5-8  factor-light h4 formal run（仅一个入选候选、一次）
V5-9  0.7 nm / 2 TB Hybrid capacity update
V5-10 response_v6.md 与停止审阅
```

---

## 8. V5-0：继承审计

Codex 拉取本 review 后，第一项提交必须为 docs-only：

```text
docs(task039): audit v5 hybrid memory redesign baseline
```

创建：

```text
outcomes/review_v5_inherited_audit.md
```

至少记录：

```text
branch/HEAD/upstream/ahead-behind/worktree
V4 direct/iterative compact hashes
shared packet availability and hashes
h5 historical direct/iterative evidence
current MemAvailable/swap/disk/thread/MPI/ABI
Full3D heavy deferred
h5 sidecar nonblocking status
6h/8h time policy
V5 memory classifications
```

不得夹带 Python 修改或启动 heavy run。

---

## 9. V5-1/V5-2：先完成真实内存归因

### 9.1 offline-first

首先只读分析既有 h4 direct 和 iterative raw。若 raw 已足以恢复下列证据，则不得为补表
重跑 PDE：

```text
bottom/top explicit F rows/NNZ/bytes
bottom/top factor setup begin/end
bottom/top factor NNZ与MUMPS telemetry
W_local、K、LU、pivots shape/bytes
C/D/H、P/T、modal Schur shape/bytes
outer operator/KSP/Krylov vector inventory
packet/coupling/system references
peak UTC、stage、process-tree RSS/PSS/USS
cleanup 前后 process-tree 与 max-rank RSS
```

### 9.2 instrumented setup-only

若现有 raw 缺少峰值 stage 或 factor-ready authority，允许增加显式 opt-in telemetry，并运行
一次 h4 setup-only：

```text
build bottom side
→ bottom exact factor
→ bottom Woodbury ready
→ bottom construction cleanup
→ build top side
→ top exact factor
→ top Woodbury ready
→ top construction cleanup
→ modal Schur ready
→ outer KSP setup ready
→ checkpoint/cleanup/exit
```

不运行 outer solve、recovery、R/T/A 或 field export。

必须增加并对齐这些 marker：

```text
bottom_F_ready
bottom_factor_setup_begin
bottom_factor_ready
bottom_woodbury_ready
bottom_construction_cleanup

top_F_ready
top_factor_setup_begin
top_factor_ready
top_woodbury_ready
top_construction_cleanup

both_side_actions_ready
modal_schur_build_begin
modal_schur_ready
outer_ksp_setup_ready
all_setup_objects_cleanup
```

每个 marker 必须绑定 process-tree sample；对象 ledger 不能与 RSS 相加。归因结果允许为
`unattributed`，但不得把最大对象自动写成峰值原因。

输出：

```text
outcomes/v5_h4_exact_side_memory_attribution.md
compact attribution record
```

---

## 10. V5-3：保持同一数学的 exact-side compaction

这是第一优先级，因为它不削弱当前 1-iteration exact-side 强度。

### 10.1 factor-only state

审计 `ResearchExactFactorInverse` 是否在 factor-ready 后仍不必要地同时保留：

```text
original explicit F
KSP/PC setup objects
MUMPS factor
assembly/preallocation temporaries
```

优先实现安全的 factor-only solve handle：factor-ready 后只保留 factor action 与必要通信
状态，销毁原始 F、KSP setup 临时量和不再使用的 matrix references。若当前 PETSc/MUMPS ABI
无法安全 detach factor，必须通过 focused reproducer 证明并记录 `blocked_by_ABI`，不得伪造
释放。

### 10.2 minimal Woodbury state

Woodbury build 完成后，正式 apply state 只保留确实需要的对象。至少审计并尝试：

```text
K factor 后销毁原始 K，只留 LU+pivots
H 合入 K 后释放 H
C 完成 W/K 构造后释放，或转为 action-only callback
components container 解除无用 F/C/H 引用
构造临时 Vec/Mat 立即销毁
```

`D`、factor action、必要工作向量和当前候选所需的 W/K-LU 可以保留。每个释放都必须有
重复 apply 和 true residual 测试。

### 10.3 bottom/top 严格串行

必须保证：

```text
bottom factor/Woodbury 完成
→ bottom construction temporaries collective cleanup
→ allocator trim
→ 才开始 top factor/Woodbury
```

不得让两侧 assembly、candidate columns、factor setup workspace 或 packet hydrate 高水位
无必要重叠。

### 10.4 coupling 与 recovery references

P/T 和 coupling 完成 ownership transfer 后，及时 detach：

```text
mode bases
packet mmap/references
raw/full trace representations
one-cell construction helpers
重复 canonical/recovery-only state
```

恢复所需内容必须进入 hash-bound minimal recovery packet；不得为了后处理把 setup 对象留到
solve 后。

---

## 11. V5-4：modal Schur 与 outer Krylov 瘦身

### 11.1 formal heavy run 不再完整构造 modal Schur 两遍

当前 `build_hybrid_action_modal_schur` 为 repeat authority 完整构造两次 2M x 2M action
matrix，使每侧产生约 `2 x 2M` 次 action apply。V5 应分离：

```text
focused/tiny fixture：保留完整 double-build repeat Gate
formal h4：构造一次完整 modal Schur
          + 固定 hash-bound 抽样列 repeat
          + LU repeat solve
```

抽样必须覆盖 positive/negative、bottom/top 强耦合、首尾和高能模式，列集合写入输入或
manifest，不能运行后挑选。single-build 必须与 V4 double-build matrix/LU 在可复现 fixture
上等价。

### 11.2 固定 exact-side PC 使用小 restart GMRES

exact-side action是固定线性映射。若 linearity/repeat test 通过，正式 compact exact-side
候选允许使用：

```text
right GMRES
restart = 10
```

替代 FGMRES/restart 90，以降低 Krylov vector reservation。outer 仍必须由五项 true
residual 决定。若任何 preconditioner action 随迭代变化，则必须恢复 FGMRES，不得错误使用
GMRES。

这一步预期主要降低时间和 Krylov storage，不得宣称能单独解决 factor 主峰。

---

## 12. V5-5：不显式永久保存 W 的 0.7 nm 定向实现

当前 exact Woodbury 以：

```math
W=F^{-1}C,
\qquad
K=H-DF^{-1}C
```

并在 apply 中使用显式 `W_local`。V5 必须实现或完成 component 原型：

```math
z=F^{-1}r,
\qquad
q=K^{-1}Dz,
\qquad
y=z+F^{-1}(Cq).
```

这样 apply 多一次 side inverse，但不需要 resident `W_local`。

K 构造采用 batch/streaming：

```text
读取一批 C columns
→ side inverse
→ 累积 D F^{-1} C 到 K
→ 立即释放该批 response
→ 下一批
```

只允许少量固定 batch size，例如 `8/16/32` 的 component benchmark，不做开放扫描。选择标准：

```text
与 retained-W action relative error <= 1e-10
K/LU repeat pass
process-tree peak 可测
无 W resident after setup
wall 与 factor solve count 完整报告
```

component 通过后，只有 setup-only 预测满足 §6.2 才允许进入 h4 formal candidate。

该方向是 0.7 nm 必做项：旧组件审计中单 air-side 显式 W 已达到约 201 GiB 的 derived
量级。2 TB 会放宽预算，但不能把两个端面的巨大 trace-by-channel matrix 作为长期默认。

输出：

```text
outcomes/v5_streaming_woodbury.md
component compact records
```

---

## 13. V5-6：compact exact-side h4 formal run

当 V5-3/V5-4，以及条件允许时 V5-5，通过 setup advancement Gate 后，只允许一次完整
h4/M480/MPI8 formal run。

冻结：

```text
exact monolithic Hybrid operator
same h4 direct physical identity
same selected-mode packet
same M480 and 600 dynamic keys
global direct factor = 0
bottom/top exact-side numerical action preserved
zero initial guess
```

它必须同时通过 §6 内存/时间、§15 数值/物理和全部 lifecycle Gate。若峰值仍不低于 direct，
exact-side formal 路线在 V5 中停止，不得继续通过小参数微调反复重跑。

---

## 14. V5-7/V5-8：factor-light side inverse（条件执行）

若 exact-side compaction 不能达到 meaningful target，说明两个 full side sparse factors 本身已
成为不可扩展核心。此时 exact-side 只保留 oracle，不再视为 0.7 nm production candidate。

### 14.1 最多两个受控 family

允许以下顺序：

1. **local compressed factor capability audit**：仅当当前 PETSc/MUMPS build 明确支持且能
   保存 complex128 true-residual authority时，测试最多两个冻结 compression profile；
2. **physics-aware fixed-budget side Krylov**：以 matrix-free side operator、端口/模态相关
   coarse correction和固定 budget构造 approximate inverse。不得退化成普通 ILU 参数扫描。

若 compressed factor capability 不存在，直接记录 `not_supported`，不要修改环境或另装未经
资格化 solver。

### 14.2 component Gate

factor-light 候选先在冻结 RHS ensemble 上与 exact-side oracle 比较。RHS 至少包括：

```text
actual side RHS
modal traction probes
external DtN coupling probes
fixed random repeat probes
```

推进到 outer formal 的最低条件：

```text
all values finite
repeat error <= 1e-10
side true residual <= 1e-2 for every mandatory RHS
side setup peak <= 70% of exact-side setup peak
no full exact side factor resident
no global direct factor
```

inner side inverse若随 RHS/iteration 变化，outer 必须使用 FGMRES。允许时间增加，但仍受
6h/8h 总 Gate约束。

### 14.3 formal 次数

最多选择一个 factor-light 候选运行一次 h4 full formal。不得并行运行多个候选，也不得在
formal failure后临时调参数重跑；真正 implementation bug按 §17 窄修后可重跑一次。

输出：

```text
outcomes/v5_factor_light_side_inverse.md
factor-light compact record
```

---

## 15. 正式数值与物理 Gate

所有完整 iterative 候选相对 h4 Hybrid direct 必须通过：

```text
KSP reason                         > 0
reported/global/bottom/top/modal   <= 5e-9
projection                         <= 1e-8
exact traction bottom/top          <= 1e-8
R/T/A/A_volume absolute delta      <= 1e-6
selected E relative L2             <= 5e-3
selected H relative L2             <= 5e-3
canonical active/full relative L2  <= 1e-5
normal flux relative delta         <= 1e-4
power-weighted channels            <= 1e-4
external key set/hash              exact
energy closure                     <= 1e-5
swap                               = 0
```

逐通道结果完整输出。历史 independent `12+12` count 没有单独持久化时，继续写
`not_separately_persisted`，不得补写不存在的数字。

Hybrid direct 是本轮同方程 reference；没有 Full3D h4 authority，因此不得宣称 Full3D
integrated physics、continuum convergence 或 arbitrary-3D qualification。

---

## 16. V5-9：0.7 nm / 2 TB Hybrid capacity update

不得启动 0.7 nm full PDE。使用 V5 新增的 measured h5/h4 evidence更新：

```text
bottom/top side rows和NNZ
exact/compressed factor NNZ、setup time和RSS
retained-W 与 streaming-W bytes/action cost
external channel inventory
K/K-LU bytes与factor/action复杂度
P/T、modal Schur、Krylov和recovery内存
MPI ownership与复制
生命周期顺序进程峰值
```

必须分别报告：

```text
measured 5 nm
h5→h4 same-architecture derived fit
0.7 nm predicted envelope
2 TB physical-memory fractions（例如70/80/90%），而不是假设程序可占满2 TB
pending 0.7 nm substrate/material authority
```

重点回答：

1. explicit W 是否已从正式候选中消除；
2. full side exact factor 在 0.7 nm 是否仍会超过工程预算；
3. factor-light candidate 的 local/coarse problem 是否有上界；
4. M 和 external channels 增长时，modal Schur/K-LU 时间是否成为新 blocker；
5. 哪些结论是 measured，哪些只是 conditional prediction。

输出：

```text
outcomes/v5_0p7nm_hybrid_capacity.md
```

不得把 256 GiB 旧 no-go直接复制成2 TB结论，也不得因为2 TB更大就声明现有架构可行。

---

## 17. Bug修复权限

Codex可自主窄修：

```text
telemetry marker/clock alignment
factor/component悬挂引用
collective destroy次序
packet mmap/reference leak
factor-only detach安全问题
single-build sampled-repeat checker
streaming W sign/order/batch bug
GMRES/FGMRES固定/可变PC身份错误
```

要求：

1. 保留失败 raw；
2. 添加 focused reproducer；
3. 不改变冻结物理、M、阈值和 reference；
4. 不扩大候选 sweep；
5. 只重跑受影响的最小 component；
6. full formal最多因真正实现 bug重跑一次。

以下不是 bug，不得静默调参：

```text
exact side factor本身太大
streaming W时间增加
factor-light outer iteration增加
6h时残差无客观收敛趋势
未达到20% memory target
0.7 nm capacity仍不成立
```

---

## 18. 测试与证据 Gate

heavy run 前至少完成：

```text
factor-only round-trip solve equivalence
original F release/no-use-after-free test
minimal Woodbury retained-state test
retained-W vs streaming-W action equivalence
batch-size deterministic K identity
single-build vs double-build modal Schur fixture
sampled-repeat fixed-column contract
fixed-PC GMRES linearity/repeat test
variable-PC FGMRES identity test
MPI2/MPI4 ownership and collective cleanup smoke
packet producer/consumer hash and no-QEP test
input validate/dry-run
```

静态检查：

```text
Ruff check
Ruff format --check on changed Python
compileall
focused pytest
check_benchmarks --no-write
compact JSON parse
Markdown links/fenced math/table columns
git diff --check
```

full repository pytest不是本 Review的强制 Gate；若不运行，必须写 `not_run`，不得声称 CI
或 zero failures。

---

## 19. 重型运行数量与停止条件

V5 heavy上限：

```text
h5 packet producer                  <= 1（sidecar需要时）
h5 current Hybrid direct consumer  <= 1
h4 instrumented setup-only         <= 1
h4 compact exact-side formal       <= 1
h4 factor-light formal             <= 1（条件执行）
0.7 nm full PDE                     = 0
Full3D new heavy                    = 0
```

Component/tiny fixture可多次运行，但不得伪装成 full-case memory authority。

立即停止条件：

```text
swap > 0
absolute memory line reached
source/input/packet/physical hash mismatch
NaN/Inf or invalid KSP reason
setup-only超过direct且无可释放对象
6h extension条件不成立
8h仍未收敛
候选改变Hybrid方程或M480
需要新的大规模算法family才能继续
```

---

## 20. 必须创建或更新的证据

```text
outcomes/review_v5_inherited_audit.md
outcomes/v5_h5_current_hybrid_direct_sidecar.md
outcomes/v5_h4_exact_side_memory_attribution.md
outcomes/v5_exact_side_compaction.md
outcomes/v5_streaming_woodbury.md
outcomes/v5_factor_light_side_inverse.md              # conditional
outcomes/v5_h4_hybrid_iterative_final.md
outcomes/v5_0p7nm_hybrid_capacity.md
outcomes/test_summary.md
outcomes/summary.md
docs/development_progress.md
response_v6.md
```

对应 compact records进入：

```text
benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/
```

raw mesh、field、matrix、factor、packet arrays和timeline继续保存在 ignored artifact root。

---

## 21. Commit计划

建议按阶段提交并及时 push：

```text
docs(task039): audit v5 hybrid memory redesign baseline
bench(task039): add exact-side memory attribution telemetry
bench(task039): measure current h5 hybrid direct lifecycle
refactor(task039): compact exact-side factor and woodbury state
perf(task039): reduce modal schur and krylov storage
feat(task039): add streaming woodbury action
bench(task039): qualify compact h4 hybrid iterative candidate
research(task039): evaluate factor-light side inverse              # conditional
docs(task039): close v5 hybrid memory and 0p7nm capacity results
```

不得把多个 heavy结果、算法实现和最终文档混在一个不可审阅提交中。

---

## 22. response_v6.md 要求

最终 response 必须表格优先，并至少包含：

1. branch、base、最终 HEAD、worktree、测试状态；
2. h5 sidecar current-lifecycle measured结果及其 nonblocking定位；
3. h4 direct、V4 iterative、V5各候选统一表；
4. 104.33 GiB峰值的实测归因边界；
5. 每项释放前后对象和RSS；
6. retained-W/streaming-W的数学、内存、solve-count和时间比较；
7. exact-side和factor-light candidate的数值/物理/resource分类；
8. 6h Gate是否触发、是否延长、延长依据；
9. 0.7 nm / 2 TB更新后的 measured/derived/predicted容量表；
10. 未运行、失败、controlled stop和deferred项；
11. ordinary defaults、Full3D和arbitrary-3D边界；
12. selective-merge建议，但不得请求或执行merge。

Codex完成后提交并推送同一分支，然后停止等待下一轮ChatGPT review。

---

## 23. 当前核心判断

Task39可以继续以Hybrid为主，因为h4 Hybrid direct已经提供了可用的同方程reference，
exact-side iterative也证明了数值接线正确。但V4同时证明：仅仅把global factor换成两个
local exact factors，并不能保证网格细化后仍比direct省内存。

V5的首要任务不是继续压outer iteration，而是：

```text
测清local factor与action stack
→ 删除重复resident state
→ 严格串行生命周期
→ 消除显式W
→ 必要时从full side factor转向factor-light side inverse
```

只有这样，Hybrid iterative的内存优势才可能随h细化保持，并对0.7 nm具有真实意义。
