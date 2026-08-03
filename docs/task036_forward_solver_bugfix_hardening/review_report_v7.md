# Task036 Review Report V7：冻结 B1 负结论，并将 reachable-source POD 收窄为一次可判定实验

## 1. 审阅身份与最终决定

```text
review                         = Task036 Review V7
reviewed_head                  = 610945dcf4197620529155d795c859111be93e39
reviewed_response              = docs/task036_forward_solver_bugfix_hardening/response_v6.md
branch                         = codex/20260730-task36-forward-solver-bugfix-hardening
ordinary_default               = unchanged
master_merge                   = not_authorized
iterative_solver               = forbidden_in_current_batch
B1_discrete_Bloch_d_le_360     = accepted_controlled_negative / frozen
C1a_primal_scaffold            = accepted_as_research_checkpoint_only
C1b_96RHS_teacher              = authorized_once_with_revised_split_and_hard_stop
C1c_test_space                 = locked_pending_C1b_response
R2_R3_actual_candidate         = locked
p6_0p7nm_RCWA_iterative        = not_authorized
```

本 Review 接受 `response_v6.md` 的两个主要结论：

1. 完整 FE trace-chain 已经证明 direct Hybrid 域分解本身可以在小掠射角和 P 偏振下恢复
   Full3D；
2. 本批 discrete-Bloch `M120+r` 候选在 `d_port<=360` 内没有证明具备足够的 trial capacity，
   不应继续增加 v9 mode、改变 Petrov 阈值或扩大 rank。

同时，本 Review 对 C1 reachable-source/POD 路线作一项关键修订：

> C1a 当前构造的是 **paired two-end global response POD**，不是已经完成的 localized endpoint
> corrector。若使用全部 96 个 source response 建基，保留全部有效 rank 后训练 source-span 的
> endpoint projection 必然趋近机器精度；因此 `r=96` 的训练残差不能作为低秩成功证据。

下一阶段只允许一次带有预冻结 capacity/holdout 分离的 96-RHS exact teacher。该实验必须在
一个受控运行中给出正或负结论，不能再次演化为开放式算法开发。

---

## 2. 对 B1 discrete-Bloch 结果的审阅

### 2.1 负结论成立，而且 trial-space 证据比 Petrov 失败更强

`response_v6.md` 给出的 v4 数据为：

| r | d_port | trial/test rank | Petrov rank | best-trial endpoint residual |
|---:|---:|---:|---:|---:|
| 0 | 240 | `240/240` | `240` | `9.367535806e-5` |
| 40 | 280 | `280/280` | `240` | `9.356921361e-5` |
| 80 | 320 | `320/320` | `276` | `9.349354982e-5` |
| 120 | 360 | `360/360` | `356` | `8.885746566e-5` |

Petrov operator 在三档 enriched basis 上均秩亏，说明现有 right/adjoint pairing 不能形成稳定
方阵。但即使暂时忽略 test-space 问题，`d_port=360` 的 best-trial residual 相对 M120 只改善
约 5.14%，仍为 `O(1e-4)`，距离冻结的 `1e-9` 目标约五个数量级。

因此，本 Review 接受：

```text
DISCRETE_BLOCH_LOW_RANK_NOT_DEMONSTRATED_IN_THIS_BATCH
```

该分类不是由一个可调 Petrov 阈值产生，而是由 trial space 本身对真实 RHS 的最佳逼近下界
支持。继续增加同一 v9 pool、重新排序 block 或修 test space，都无法弥补这一 trial-capacity
负证据。

### 2.2 B1 后续处置

立即冻结：

```text
additional_v9_targets           = forbidden
additional_v9_mode_families     = forbidden
Petrov_threshold_relaxation     = forbidden
pinv_or_regularization          = forbidden
rank_above_360                  = forbidden_in_Task036
new_B1_forward_PDE              = forbidden
```

现有 B1 runner、tests 和 ignored artifacts 保留为研究负证据。不得删除 v1--v4 的失败过程，
也不得将 v2 的错误 Euclidean whitening 数值与 v4 正式结论混用。

### 2.3 必须补一个 compact tracked record

v4 heavy artifact 目前位于 ignored 目录。`response_v6.md` 已记录主要数值和 SHA256，但在下一
数值运行前，应新增一个小型、机器可读的 tracked JSON 或 CSV，至少绑定：

```text
source SHA
case/config identity
artifact relative paths and SHA256
r / d_port
trial rank / test rank / Petrov rank
best-trial residual
actual residual or null
wall / process-tree peak / swap
formal disposition
```

这只是保存现有结果，不得发展成新 schema 或 evidence framework，也不触发 B1 重跑。

---

## 3. 对 C1a primal reachable-source POD 的审阅

### 3.1 公式在“全局两端响应子空间”意义下成立

C1a 对相同 source coefficient 的 bottom/top joint-Cauchy response 使用联合 metric：

$$
G_{core}=\sum_{s\in\{b,t\}} C_s^H G_s C_s,
\qquad
B=\sum_{s\in\{b,t\}} C_s^H G_s T_s,
$$

$$
R_s=T_s-C_sG_{core}^{-1}B,
\qquad
G_{res}=\operatorname{Herm}\left(\sum_s R_s^H G_sR_s\right).
$$

对 `G_res` 的特征向量使用同一 source coefficient 组合 bottom/top response。这在以下对象上是
数学一致的：

```text
source coefficient
    -> paired bottom/top exact response
    -> one global reduced response coordinate
```

代码也正确检查了：

- bottom/top source identity 必须完全一致；
- M120 core 从两端联合 metric 中一次投影出去；
- corrector 在两端联合 metric 下正交归一；
- source rank 饱和时不 padding、不复制列。

因此 C1a pure scaffold 可以保留。

### 3.2 但它不是 localized endpoint corrector

同一个 coefficient 同时决定 bottom 和 top corrector，意味着一列 basis 实际表示：

$$
r_j=\begin{bmatrix}r_{b,j}\\r_{t,j}\end{bmatrix}.
$$

这是一种 **nonlocal paired two-end response mode**。它可以用于固定 operator 的全局 reduced
model，但不能自动解释为：

```text
bottom local corrector
+
M120 core
+
top local corrector
```

后者通常具有两端独立局部坐标，或需要明确证明局部消元后为何仍只保留一个共享系数。

因此后续文档和代码必须使用：

```text
paired_two_end_reachable_response_POD
```

而不得提前使用：

```text
localized_endpoint_corrector_pass
```

若 C1 最终采用共享系数，实际 reduced trial column 必须包含其完整 11-plane harmonic/global
extension，而不能只保存两个 endpoint arrays 后假设存在未定义的局部传播规则。

### 3.3 cell-only traction 修正是必要且正确的

本 Review 接受 `response_v6.md` 第7.3节的纠偏：exact solution 上的总 endpoint equilibrium
block 等于 RHS，不能冒充 core-facing cell traction。正确 joint-Cauchy column 应使用相邻
middle cell 的 raw-outward contribution：

```text
q_bottom = first block of cell_action([X0; J X1])
q_top    = J* last block of cell_action([X9; J X10])
```

其中 top/bottom orientation 由既有 transfer/dual map 统一处理，不再额外猜测符号。新增
`endpoint_cauchy_columns()` 将提取逻辑从 balance audit 中拆出，职责清晰，可以保留为
reusable numerical helper。

---

## 4. C1a 中必须避免的“96 维必然饱和”误判

exact teacher 对固定 operator 是线性的：

$$
X_{teacher}=K^{-1}B,\qquad B\in\mathbb C^{13200\times96}.
$$

因此这 96 个 source response 的线性 span 的秩不可能超过 96。若使用全部 96 列建基，再保留
全部有效 rank，则训练 source-span 的 endpoint response 被该 basis 表示到舍入误差是构造本身
决定的结果，而不是低秩物理发现。

所以以下逻辑不被批准：

```text
all 96 columns used to build basis
-> r=96 training endpoint residual is tiny
-> low-rank Hybrid pass
```

`r=96` 可以作为 source-rank saturation 和实现闭合检查，但不能单独获得 compression credit，
也不能解锁 actual Hybrid。

真正有信息量的证据必须至少包含一类未参与 basis/rank 选择的 source 或 operator holdout。

---

## 5. Stage C1b：唯一批准的一次 96-RHS teacher

### 5.1 运行范围

批准一次 exact trace-chain matrix-RHS 运行：

```text
operator                       = frozen A004-S p5/h10/Ny4 exact trace-chain
RHS columns                    = 96 physical incoming channels
trace solution shape           = 13200 x 96
independent Full3D solves       = 0
new discrete-Bloch solve       = 0
new adjoint solve              = 0
actual compressed PDE          = 0
```

所有 96 列可以在同一次 matrix-RHS solve 中获得，但 POD 建基和 rank 选择只能使用预冻结的
capacity 子集。

### 5.2 运行前冻结 80/16 source split

在查看 teacher spectrum 前，先提交一个小型 source-identity 表，将 96 列冻结为：

```text
capacity columns = 80
holdout columns  = 16
```

要求：

- source identity 使用 `(incident side, m, n, polarization)`；
- bottom/top 均有 holdout；
- S/P 均有 holdout；
- 零级和非零级均有 holdout；
- 分配规则或明确列表在数值运行前进入 Git；
- 运行后不得移动 difficult columns、改变 split 或重选 seed。

96 列仍一次求出；只有 80 个 capacity columns 可进入 `G_res`、POD eigenvectors 和首次通过
rank 的选择。16 个 holdout columns 只作 same-operator source-family capacity 检查，不能用于
更新 basis。

### 5.3 冻结 prefix

同一个最大 POD spectrum 只读取：

```text
r = 0 / 20 / 40 / 60 / 80

d_port = 240 + r = 240 / 260 / 280 / 300 / 320
```

不得为每个 r 重建 teacher、修改 source split 或重复运行 exact chain。`r>80` 在本阶段没有
意义，因为 capacity source rank 已被冻结为 80。

### 5.4 必须报告的数值

对每个 prefix 同时报告 capacity 和 holdout：

1. endpoint electric / traction / joint-Cauchy best-approximation residual；
2. 11-plane trace best-approximation residual；
3. exact trace operator-action residual：

   $$
   \frac{\|KX_r-B\|}{\|B\|};
   $$

4. next singular ratio、discarded energy 和 effective rank；
5. M120 core orthogonality、corrector metric identity；
6. bottom/top 分项误差，不能只报两端聚合值；
7. teacher 每列 full residual 的 max/aggregate；
8. cold setup、factor、96-RHS solve、extraction/POD 各阶段 wall 和 peak。

C1b 仍是 primal capacity，不构造 Petrov test，不计算 official R/T/A，也不把 teacher projection
写成 reduced solve。

### 5.5 C1b 通过条件

只有存在某个 `r<=80` 同时满足：

```text
capacity endpoint joint-Cauchy residual <= 1e-8
holdout endpoint joint-Cauchy residual  <= 1e-8
capacity full/operator residual         <= 1e-8
holdout full/operator residual          <= 1e-8
core orthogonality                      <= 1e-10
corrector metric identity               <= 1e-10
```

才可写：

```text
C1_primal_capacity = pass_on_frozen_same_operator_source_holdout
```

这仍不是跨角度、跨几何或 production pass。

若只有 capacity/training 在 `r=80` 降到舍入误差，而 holdout 不通过，分类为：

```text
SOURCE_SPAN_INTERPOLATION_ONLY
```

若所有 `r<=80` 均不通过，分类为：

```text
REACHABLE_SOURCE_PRIMAL_COMPRESSION_NOT_DEMONSTRATED
```

两种负结论都立即停止 C1；不得扩大 source、增加 snapshots、改变 split 或开始 adjoint/test。

### 5.6 硬资源和停止条件

本轮只允许一次数值运行：

```text
external wall hard cap          = 7200 s
process-tree peak hard cap      = 10 GiB
swap                            = 0
retry                           = 0
automatic code modification     = forbidden after launch
```

任何 cap、residual、identity 或 source-binding 失败均保存 artifact 并停止。不得再次出现持续
24 小时仍不断修改 target/配对逻辑的开放执行。

### 5.7 C1b 交付

运行后创建：

```text
docs/task036_forward_solver_bugfix_hardening/response_v7.md
```

必须给出全部 prefix 原值、source split、artifact SHA、资源、代码 diff、tests 和明确的
pass/negative 分类，然后停止等待下一轮审阅。

---

## 6. C1c 的 test-space 决策：先做 minimum-residual QR，不先开发 physical adjoint batch

`response_v6.md` 询问 primal capacity 通过后应优先选择 physical-adjoint batch 还是
minimum-residual test construction。本 Review 的决定是：

```text
first diagnostic test space = minimum-residual / QR Petrov
physical-adjoint batch       = deferred
```

理由：

- C1 当前首先要回答 trial basis 是否足以求出真实解；
- 新建 96-column physical-adjoint load builder 会再次扩大为独立研究课题；
- minimum-residual test 可完全由已资格化 exact operator 和 trial basis 决定；
- 它不会像 B1 v2 那样依赖无物理意义的 Euclidean `L^H R` overlap。

若 C1b 通过，下一轮可定义：

$$
Y=KR,
\qquad
Y=QT
$$

其中 `Q` 是 residual metric 下的正交列，`T` 为方形上三角或等价 rank-revealing factor。对
每个 RHS 求：

$$
Ta=Q^Hb,
\qquad
x_r=Ra.
$$

要求：

- `Y` 必须满列秩；
- 使用 QR/SVD 只做 rank 检查和稳定方解，不形成 full-space normal equations；
- 不允许 pseudoinverse、regularization、retry 或 fallback；
- full explicit residual 必须实测；
- 该 minimum-residual formulation 先获得 diagnostic credit，不能自动冒充最终 physical
  adjoint/Petrov production formulation。

C1c 当前仍锁定，必须等 `response_v7.md` 审阅后才能实现。

---

## 7. 跨角度/Floquet phase holdout 的 canonical identity

不同入射角具有不同 Bloch vector，不能直接比较各自的 1200 个 active coefficient。建议采用
**periodic-gauge pullback**：

$$
J(k_t):V_\Gamma(k_t)\rightarrow V_\Gamma(0),
\qquad
E_t\mapsto \Pi_h\left[e^{-ik_t\cdot r_t}E_t\right].
$$

实现必须基于完整有向 H(curl) trace，而不是对 active coefficient 逐项乘点相位：

1. 用当前 Floquet expansion `C(k_t)` 将 active trace 展开到 original edge/face rows；
2. 在同一物理端面上对 `e^{-ik_t·r_t}E_t` 做有限元投影/插值；
3. 映射到固定 `k_t=0` 的 canonical periodic trace coordinates；
4. traction dual 使用配对保持的 dual pullback，而不是与 electric 相同的 primal map；
5. 检查：

   $$
   q_k^HE_k=q_0^HE_0,
   $$

   以及 mass pullback、roundtrip、orientation 和 corner phase；
6. 所有 identity 误差必须 `<=1e-10`。

在该 map 资格化前，不允许把不同 Bloch phase 的 coefficient arrays 直接堆成 POD snapshots，
也不允许宣称跨角度 holdout 已建立。

---

## 8. 对当前代码 checkpoint 的处置

### 8.1 接受为 research checkpoint

当前 commit `610945dc...` 的四文件差异可以保留：

- `endpoint_cauchy_columns()` 已进入职责合理的 reusable solver helper；
- B1 v4 负结果和 C1a pure tests 有明确区分；
- 没有修改 ordinary default；
- 没有加入 iterative、fallback、scheduler 或自动 rank tuning。

因此 C1b 前不要求为了形式拆分 7600 行 runner，也不要求机械重排整个历史文件。

### 8.2 若 C1b 通过，C1c 前必须拆分

只有 C1b 获得正的 primal-capacity 结论后，才将以下内容从综合 runner 中抽成职责单一模块：

```text
reachable teacher endpoint/full-trace extraction
paired two-end POD construction
minimum-residual reduced solve
compact capacity record
```

研究调度、历史 Q1--Q5 审计和 production candidate 不能继续累积在同一个 runner 中。

### 8.3 格式和测试

`ruff format --check` 当前不通过不是 C1b 数值阻断项，但在任何 selective merge 或 production
promotion 前必须收口。C1b 前至少要求：

- touched-file Ruff lint；
- touched-file compileall；
- focused pure tests；
- `git diff --check`；
- source-split contract test；
- watchdog negative-path test。

不要求在 C1b 前机械格式化全部历史 runner，也不要求重跑与本轮无关的 48 分钟 full suite。

---

## 9. 对 `response_v6.md` 七个问题的逐项答复

### Q1：是否冻结 B1 `d<=360` 为 controlled negative？

**同意。** 不再追加 v9 模态、不改阈值、不扩大 rank。

### Q2：是否先做 primal reachable-source capacity？

**同意，但按本 Review 的 80/16 split 执行。** 不批准使用全部 96 列建基后用同一 source-span
自证成功。

### Q3：是否使用两端共享 source coefficient？

**有条件同意。** 对 fixed-operator 的 paired two-end global response POD，shared coefficient 是
正确的；它不能被命名为两个独立 localized endpoint corrector。实际 trial column必须包含其
完整 global/harmonic extension。

### Q4：physical-adjoint batch 还是 minimum-residual test？

**优先 minimum-residual QR diagnostic。** physical-adjoint batch 延期，避免在 primal capacity
尚未知时再发展一套复杂 adjoint-load framework。

### Q5：跨角度 canonical identity？

采用第7节的 periodic-gauge pullback，并对 traction 使用保持 primal/dual pairing 的 dual map。
在该 map 通过前不做跨角度 coefficient POD。

### Q6：是否批准一次 96-RHS teacher？

**批准一次。** 必须预冻结 80 capacity / 16 holdout、2 小时 wall、10 GiB peak、zero swap、
无 retry。任一失败立即停止。

### Q7：当前 diff 是否可作为 checkpoint？

**可以。** C1b 前不要求继续拆分；若 C1b 正结果解锁 C1c，则先拆出职责单一的 reachable-POD
与 reduced-solve 模块，再继续。

---

## 10. 当前状态与后续锁定

```text
exact FE trace-chain oracle                 = pass
small-grazing / P domain decomposition      = pass
original M120/M240 global port              = controlled negative
B1 discrete-Bloch d<=360                    = accepted controlled negative / closed
C1a paired two-end primal POD scaffold      = accepted research checkpoint
C1b 96-RHS teacher                          = authorized once under Review V7
C1c minimum-residual reduced solve          = locked pending response_v7
cross-operator holdout                      = locked pending gauge-map qualification
actual compressed Hybrid A004/A007          = locked
p6 / wavelength continuation / 0.7 nm       = locked
RCWA / POD beyond frozen C1 / H-matrix      = not authorized
iterative solver                            = forbidden / not run
master merge                                = not_authorized
```

若 C1b 为负，Task036 的 direct low-rank interface compression 研究应在 13.5 nm 处正式收口：

```text
exact trace-chain correctness = proven
low-rank direct Hybrid         = not demonstrated
```

随后由用户另立任务决定独立 RCWA、跨 operator snapshot ROM、或迭代/预条件路线，不能在
Task036 中自动切换。

若 C1b 为正，也只能进入一次 `response_v7` 审阅；不得自动启动 C1c、A004、A007、p6 或
0.7 nm。

---

## 11. 合并和发布边界

- 本 Review 只写入 `codex/20260730-task36-forward-solver-bugfix-hardening`；
- `master` 不修改、不合并；
- 不创建 PR；
- B1/C1 heavy artifacts 继续保持 ignored，compact identity 和 SHA 写入 tracked records；
- Task036 分支仍是 research branch，最终只允许选择性整合通用 bugfix 和小型 reusable helper；
- 本 Review 不批准整体 merge 当前综合 runner。

最终审阅结论：

> B1 已经得到足够强的负证据，应立即关闭。C1a 的 paired two-end POD 公式可以保留，但必须
> 承认其固定 operator、全局非局部和 source-rank 饱和边界。只批准一次有 80/16 分离的
> 96-RHS teacher；该实验必须直接回答真实可达响应是否在 `r<=80` 内可压缩。无论正负，完成
> 后提交 `response_v7.md` 并停止。

---

## 12. 对 `reply_review_report_v7.md` 的二次审阅与绑定修订

### 12.1 总体处置

```text
reviewed_reply                  = docs/task036_forward_solver_bugfix_hardening/reply_review_report_v7.md
reviewed_reply_blob             = c6d81ddcbc09026aacc67332b298aa0a7b084ac8
reply_disposition               = ACCEPTED_WITH_MATERIAL_CLARIFICATIONS
B1_closure                      = unchanged / accepted
C1b_80_16_split                 = accepted
C1b_source_name                 = revised_below
C1b_formal_coefficient          = full-action minimum-residual lower-bound oracle
teacher_projection_coefficient  = diagnostic_only
fixed_operator_source_claim     = strengthened_conditionally_by_induced_norm
C1c_actual_reduced_solver       = still_locked
```

回复总体上具有良好的辩证性，特别是以下几点值得接受并纳入执行：

- `A004-S` 是冻结 operator 的算例标签，而 96 列内部的 `s/p` 是端口通道极化，二者不能混称；
- 16 列 holdout 只能获得同一 operator 下的 source-space 信用，不能外推为跨角度或跨几何；
- `X_r` 必须是完整 11-plane trial response，不能用 endpoint-only projection 代替全算子残差；
- 各项正式误差不能分别选择最有利的 coefficient 后再拼接成“同时通过”；
- `10 GiB / 7200 s` 只是离线 teacher 的 safety cap，不是最终 Hybrid 工程 Gate；
- C1b-0 / C1b-1 / C1b-2 的分段能够防止再次发生边运行、边改算法的开放式执行；
- minimum-residual QR 与 periodic-gauge pullback 都应继续锁定在后续阶段。

但回复中仍有两处需要实质修订：

1. 96 列是否都能称为“远场物理 incoming channels”，必须由 mode policy 和 `propagating`
   identity 决定；
2. formal `best-trial action residual` 不应由 teacher-solution projection coefficient 冒充，而应
   使用 trial span 内冻结的 full-action minimum-residual lower bound。

此外，回复对 same-operator holdout 的信用表述略显过度保守：若 96 列构成冻结端口 source
空间的完整基，且在 rank 选择后对全部 96 列计算诱导算子范数，则可以获得“冻结 96 维 source
空间上一致”的信用；它仍然不是跨 operator 信用。

### 12.2 接受的 source identity 澄清，并补充传播属性

`build_hybrid_local_incoming_load_columns()` 确实按每侧现有 `PortMode3D` 顺序构造 incoming
companions，每列可绑定：

```text
(side, m, n, polarization)
```

但 `outgoing_port_modes_3d()` 的选取语义还包括：

- `auto_propagating`：选择零级或传播级；
- `zero_order`：只选择零级；
- `manual`：可包含非传播级；
- companion 继承 `propagating` 与 `rayleigh_warning`。

因此 source table 除回复要求的四元组外，还必须记录：

```text
stage4_dtn_order_policy
propagating
rayleigh_warning
power_per_unit_amplitude
beta / vertical_sign
```

正式中性名称使用：

```text
external_port_companion_load_columns
```

只有 `propagating=true` 且对应远场可入射解释明确的列，才可简称 far-field physical incoming
channels。若当前 96 列全部满足该条件，source table 应以实测字段证明，而不是由“48 列/侧”
数量推断。

80/16 split 的覆盖检查在已有 side、polarization、zero/nonzero order 之外，还应覆盖：

```text
propagating / nonpropagating（若两类均存在）
rayleigh_warning（若存在）
不同 |m| / |n| 层级
```

这不会增加数值运行，只是让预冻结 source identity 更诚实、更可迁移。

### 12.3 same-operator holdout 的信用：同意边界，但增加完整 96 维算子范数

回复正确指出，80/16 split 首先是防止 rank-selection leakage。16 个 holdout 不参与：

- residual Gram；
- POD eigenvectors；
- prefix/rank 选择；
- 任何运行后调参。

但是，在 prefix 和首次通过 rank 完全冻结后，96 个 canonical source columns 都会被评价。如果：

1. 这 96 列在冻结 source metric 下满秩；
2. 它们构成当前 external port source space 的完整坐标基；
3. reduced trial response 对全部 96 列使用同一线性 coefficient map；
4. 不再根据 16 个 holdout 修改 basis 或 rank；

那么最终证据不只是 16 个离散样本的“插值”。它可以证明该固定 operator 在完整冻结 96 维
source space 上的统一误差界。

设所有 source coefficient 为 `c`，完整 action residual map 为：

$$
E_r c = K X_r(c)-B c.
$$

除 per-column max/aggregate 外，应在小型 96 维空间中报告一个基变换不变的最坏情况量。若使用
source metric `G_S` 和 residual metric `G_R`，可计算：

$$
\epsilon_r
=\left\|G_R^{1/2}E_rG_S^{-1/2}\right\|_2.
$$

若正式归一化使用 RHS 范数，也可在 `B^H G_R B` 满秩时解广义本征问题：

$$
E_r^H G_R E_r v
=\epsilon_r^2 B^H G_R B v.
$$

实现要求：

- 只处理 `96×96` Gram/generalized eigenproblem；
- 使用 Cholesky 或明确的满秩 quotient，不显式形成 inverse；
- source/RHS Gram 若秩亏必须 fail closed，并报告有效商空间；
- 该指标只在 rank 冻结后计算，不能反向用于选择 rank；
- per-column maximum 仍必须保留，不能只报一个谱范数。

若该诱导范数和 V7 既有 Gate 均通过，允许写：

```text
uniform_on_frozen_96D_port_source_space = pass
```

但仍必须同时写：

```text
cross_operator_generalization = not_run
cross_angle_geometry_wavelength = not_demonstrated
```

因此，本 Review 不同意把任何正结果永久限制为“若干 source 插值样本”，也不同意把它升级为
跨 operator production 结论；正确结论位于二者之间。

### 12.4 formal action residual 的 coefficient：修正回复中的 teacher-projection 口径

回复提出可由 teacher response 在某个解空间度量下投影得到 coefficient，再计算 `KX_r-B`。
该量有价值，但它不是 formal `best-trial action residual`，因为解空间最佳逼近 coefficient 一般
不等于 action/residual 空间中的最小残差 coefficient。

对每个冻结 prefix，令完整 11-plane trial basis 为 `R_r`，定义：

$$
Y_r=K R_r.
$$

C1b 的 formal trial-capacity 下界应为：

$$
a_r^{MR}(b)
=\arg\min_a\left\|Y_ra-b\right\|_{G_R},
$$

$$
\rho_r^{MR}(b)
=\frac{\left\|Y_ra_r^{MR}-b\right\|_{G_R}}
       {\left\|b\right\|_{G_R}}.
$$

这与 B1 已使用的 best-trial lower-bound 语义一致：它回答“即使给这个 trial span 最有利的
系数，残差最低能到多少”。它仍不是最终 production Petrov formulation，也不解锁 C1c。

C1b 允许用一次小型 rank-revealing QR/SVD 计算该**容量下界**，但约束为：

- 不构造新的 adjoint-load framework；
- 不形成 normal equations；
- 不使用 pseudoinverse、regularization、retry 或 fallback；
- rank 不满时 fail closed；
- coefficient 只用于离线 best-trial capacity；
- 不计算 official R/T/A，不声称 actual reduced Hybrid solve。

同时可另行报告：

```text
teacher_projection_action_residual
```

其 coefficient 来自 teacher solution 在 joint-Cauchy 或 trace metric 下的投影。两种 coefficient
必须分别命名、分别报告，不能挑选较小值作为正式 Gate。

正式 pass 行中：

- action residual 使用 `a_r^{MR}`；
- endpoint、11-plane trace 和 joint-Cauchy 的 solver-relevant 误差也使用同一 `a_r^{MR}`；
- 各自数学最佳逼近误差可作为额外 lower-bound diagnostics，但不能跨 coefficient 拼成同时通过。

C1c 继续保持 locked。C1c 要回答的是：如何把这种最小残差思想整理成一个可重复、可恢复
observable、可实测整作业资源的 actual reduced solver；C1b 只做 trial-capacity oracle。

### 12.5 `r=80` 的 capacity 闭合是预期现象，决策重点必须放在 holdout 和低 rank 前缀

capacity set 只有 80 列。若其 core-complement 有效 rank 接近 80，则在 `r=80` 时 capacity
endpoint response 接近舍入级闭合是构造预期，不获得独立 compression credit。

因此 `response_v7.md` 必须突出：

- 首次通过 rank，而不是只报 `r=80`；
- `r=20/40/60` 的 singular decay、discarded energy 和 action residual；
- 16 个 holdout 的 per-column maximum、aggregate 和诱导最坏情况；
- `r=80` 是否仅仅到达 training-rank ceiling；
- `d_port/1200` 与 `d_port/13200` 两种维度口径，不能只选择更好看的比例。

若仅在 `r=80` 通过，可分类为：

```text
capacity_pass_at_training_rank_ceiling
```

它仍可获得 V7 限定的固定 operator 数学信用，但属于边界正结果，不能自动解释为快速谱衰减或
局部端口低秩。

### 12.6 正结果仍是固定长度、固定 operator 的全局 ROM，不是可复用 localized port

即使 C1b 完全通过，当前 basis 仍通过 bottom/top 共享 coefficient 和 11-plane harmonic
extension定义，绑定：

```text
wavelength / material
kx / ky / Floquet phase
p / h / Ny
cell_count = 10
trace_plane_z = 10,20,...,110 nm
bottom/top endcap and DtN identity
geometry and interface positions
stage4_dtn_order_policy
```

因此正结果的准确命名应为：

```text
fixed_operator_fixed_length_paired_response_ROM
```

它不能直接证明：

- bottom/top localized corrector 已找到；
- 改变中间长度或 cell count 后 basis 仍适用；
- 改角度、几何、材料、网格或波长后仍适用；
- 0.7 nm 下 rank 比例保持；
- direct Hybrid 的 cold setup 已有工程优势。

但这并不意味着它没有价值。若后续服务是在同一 operator 上处理多 RHS，或在严格冻结的配置中
重复求解，它可能成为有效的 global ROM。对几何反演而言 operator 会随参数变化，因此仍需
跨 operator 验证或更新策略，不能直接当成代理模型基础已完成。

### 12.7 minimum-residual QR 的 metric：接受“范数一致”，不强制新增物理 metric 框架

回复正确要求 QR 与正式显式 residual 使用同一内积。但 binding rule 是：

```text
QR norm == official residual norm
```

而不是无条件引入新的 physical `G`-QR。

- 若 exact trace-chain 的正式 true residual 使用 canonical complex Euclidean `2`-norm，则标准
  complex QR / rank-revealing QR 就是正确且优先的实现；
- 若 C1b 明确冻结加权 residual metric，则先将 `Y` 和 `b` 映射到同一 whitened residual
  coordinates，再做标准 QR；
- 不得一边使用 Euclidean coefficient，一边用另一个 metric 宣称“最小”；
- 也不得为了这一步新建通用 weighted-QR framework。

这项澄清用于防止 C1c 再次膨胀成新的长期数值基础设施研究。

### 12.8 对 C1b 分段和执行授权的最终确认

接受回复的高效率分段：

```text
C1b-0 = compact B1 record + frozen source split + contract test
C1b-1 = minimal teacher/POD/action implementation + focused tests
C1b-2 = one watchdog numerical run
```

本节即为对回复的监督复审。满足以下条件后，C1b-2 无需再新增算法性 review 即可按一次性授权
执行：

- C1b-0 已提交，source split 在看谱前冻结；
- source table 包含第12.2节新增的传播/Rayleigh字段；
- C1b-1 diff 只覆盖已批准最小职责；
- formal coefficient 和 induced-norm 口径符合第12.3--12.4节；
- focused tests、Ruff lint、compileall、`git diff --check`、watchdog negative path 通过；
- clean source、ABI、process-group termination、10 GiB/7200 s/zero-swap preflight 通过。

运行后无论正负，都只写 `response_v7.md` 并停止。不得自动进入 C1c、跨角度 gauge、actual
A004/A007、p6、0.7 nm、RCWA 或迭代法。

### 12.9 最终修订矩阵

```text
Reply V7 strategic direction                    = accepted
B1 d<=360                                        = controlled negative / closed
C1a paired two-end POD                           = accepted research checkpoint
80/16 pre-frozen split                           = accepted
all-96 far-field incoming wording                = conditional / source-table verified
C1b full 11-plane action                         = binding
C1b formal coefficient                           = minimum-residual trial-capacity oracle
teacher-solution projection coefficient          = separate diagnostic only
same-operator 16-column holdout                   = binding anti-leakage test
full frozen 96D source-space induced norm         = additionally required
positive C1b identity                             = fixed-operator fixed-length global ROM only
C1c actual minimum-residual solver                = locked pending response_v7
cross-angle gauge                                 = locked
engineering whole-job gate                        = not run in C1b
p6 / 0.7 nm / RCWA / iterative                    = locked
ordinary default / master / PR                    = unchanged / not authorized
```

最终二次审阅结论：

> `reply_review_report_v7.md` 的总体方向正确，并补充了多项此前 Review 未充分明确的边界；这些
> 补充应被接受。需要修正的是：不要把所有 companion loads 自动称为远场物理入射，也不要
> 用 teacher-solution projection coefficient 冒充 best-trial action residual。80/16 split 在防止
> rank-selection leakage 方面仍然必要；但若 rank 冻结后对完整 96 维 source basis 的诱导算子
> 范数也通过，则可以获得“固定 operator 的完整 96 维端口 source 空间上一致”的正信用。
> 这仍然只是固定长度的 global response ROM，不是 localized modal Hybrid，也不能外推到
> 0.7 nm。