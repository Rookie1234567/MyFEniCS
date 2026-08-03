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
master merge                                = not authorized
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