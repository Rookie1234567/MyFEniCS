# REVIEW REPORT V1：PARA-Task002 局部微核验收与研究方向修正

## 0. 最终状态

```text
review = PARA-Task002 review_report_v1
branch = ChatGPT/20260715-para-task-neural-local-pc
review_status = PASS_WITH_QUALIFICATIONS
numerical_result = PASS
local_action_microkernel = PASS
linear_reduced_local_gate = PASS
global_acceleration_result = NOT_PROVEN
current_ILU_plus_reduced_candidate = REJECT_AS_FINAL_ACCELERATOR
memory_saving_result = NOT_PROVEN
final_classification = microkernel_success_global_neutral
all_slab_allowed = false
h3_allowed = false
h2_allowed = false
ordinary_default_changed = false
production_claim_allowed = false
branch_management = prohibited
master_operations = prohibited
```

PARA-Task002 的实施过程和负结果记录可以验收。任务成功消除了 PARA-Task001 中最明显的 Python CSR 和逐向量 nonlinear POD-MLP 开销，并证明固定线性 reduced correction 可以在真实 h5 slab-9 上保持数值正确、确定性和局部残差改善。

但是，当前正式 P4 候选仍然是：

```text
ILU local solve
+ linear reduced residual correction
+ every-call exact non-degradation audit
```

它不是独立的 NN/reduced local inverse，也没有替代 ILU factor、inner smoother step 或真实 Maxwell action。因此本任务不能回答“神经网络能否独立替代局部预条件器并显著降低迭代数、时间或内存”这一核心问题。

本审阅接受基础设施和局部结果，拒绝将当前候选提升为全局 Maxwell 加速器，并建议后续研究转向：

```text
raw local residual r_s
-> NN-only / learned local inverse
-> z_s ≈ A_s^{-1} r_s
```

训练标签必须来自局部高精度或精确 teacher solve，而不是来自 ILU 输出或 ILU residual correction。

---

# 1. 审阅范围

本轮审阅覆盖：

```text
docs/para_task002_batched_neural_smoother_acceleration/task.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/summary.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/*.csv
docs/para_task002_batched_neural_smoother_acceleration/outcomes/*.md
benchmarks/cases/091_batched_neural_smoother_acceleration/
src/solvers/local_slab_solver.py
src/solvers/batched_reduced_smoother.py
benchmarks/neural_pc/benchmark_local_action.py
benchmarks/neural_pc/fit_linear_reduced_map.py
benchmarks/neural_pc/evaluate_batched_reduced_smoother.py
benchmarks/run_workstation_iterative.py
src/test/test_34_para_task002_linear_reduced.py
```

正式物理与求解框架继续冻结为：

```text
13.5 nm
complex Si
p2 Nedelec hexahedral FEM
h5 = 44,698 FE DoF
16 physical z-slabs
75D true-action coarse correction
right FGMRES90
exact condensed DtN operator
full explicit true residual
official R/T/A + volume absorption
MPI4
```

本审阅不执行任何分支管理、master 操作或合并决策。所有结论只约束当前 research branch。

---

# 2. 接受的结果

## 2.1 Python CSR 局部 action 优化：接受

真实 slab 0、9、10 的 complex128 microbenchmark 表明：

| slab | Python mean | SciPy mean | SciPy/Python |
|---:|---:|---:|---:|
| 0 | 9.266 ms | 0.661 ms | 7.13% |
| 9 | 13.191 ms | 0.957 ms | 7.26% |
| 10 | 13.769 ms | 1.032 ms | 7.49% |

SciPy action 与 portable action 的相对误差为 0；PETSc SeqAIJ 对照误差约为 `2.568e-16`。P1 的 mean、p95 和 repeated-call stability Gate 均通过。

结论：

```text
Task001 的 Python DoF-row-loop 确实是可消除的实现瓶颈。
persistent SciPy CSR 是当前 owner-local single-vector/small-batch 路径的有效 research backend。
```

该结论只针对当前调用尺寸和机器，不代表 SciPy 普遍快于所有 PETSc MatMult。

## 2.2 固定线性 reduced map：局部验收

rank-32 候选满足：

```text
linearity error = 3.894e-15
determinism error = 0
batch vs independent error = 0
ILU-residual rho median = 0.593884
ILU-residual rho p95 = 0.745695
inference + fused audit mean = 2.281 ms
inference + fused audit p95 = 2.490 ms
model storage = 5,390,336 bytes
```

相对 PARA-Task001 同类 inference+audit，rank-32 mean 约为 10.39%。因此：

```text
固定线性 reduced map 比当前 nonlinear POD-MLP 更便宜、更确定，
并在选定 ILU-residual validation 上通过局部质量 Gate。
```

这证明了局部微核路线有价值，但不等于证明它是更强的全局预条件器。

## 2.3 P3 shadow 数值和安全语义：接受但有限定

P3 shadow 每次仍执行原 ILU、candidate 和 exact audit，但无条件写回原 ILU。所有 5,166 次 candidate 均通过 non-degradation 检查，full true residual、official R/T/A 和 closure 通过。

接受的结论：

```text
shadow adapter 的代码语义正确；
candidate 在该运行的真实在线 residual 上未出现有害修正；
安全和 telemetry 链可用。
```

不接受的结论：

```text
P0 baseline 与 P3 shadow 位级等价；
shadow 已证明零开销；
一次 noisy wall time 可以资格化为加速。
```

## 2.4 P4 active 数值正确性：接受

正式 P4 active slab-9 结果：

| 指标 | P0 original ILU | P4 active | 变化 |
|---|---:|---:|---:|
| iterations | 849 | 847 | -0.24% |
| solve time | 151.343 s | 137.261 s | -9.30% |
| total time | 227.120 s | 191.938 s | -15.49% |
| peak incl. RTA | 1.595348 GiB | 1.618153 GiB | +1.43% |
| full residual | `9.988413e-7` | `9.985467e-7` | pass |

P4 的 reported、condensed true 和 full augmented true residual 一致；official R/T/A 与能量闭合保持。5,082 次 candidate 全部被接受，fallback 为 0。

因此：

```text
P4 numeric Gate = PASS
```

---

# 3. 阻塞性发现

## 3.1 Major：当前训练目标不是独立 NN local inverse

当前 Task002 的正式数学路径为：

```text
z_ilu = ILU_s(r_s)
q_s = r_s - A_s z_ilu
delta z_s = reduced_model(q_s)
z_s = z_ilu + delta z_s
```

也就是说，模型训练和运行依赖：

```text
ILU 已经先给出 baseline correction；
模型只学习 ILU 没消掉的残差子空间；
ILU factor 和 ILU apply 全部保留。
```

这不是“让 NN 学习 ILU 输出”的严格复制，但它仍属于 **ILU-conditioned residual correction**。模型的能力上限和训练分布都围绕 ILU 剩余误差建立，而不是从 raw residual 独立学习：

```text
r_s -> A_s^{-1} r_s
```

因此当前实验不能用于判断：

```text
NN-only 是否能比 ILU 更接近 exact local inverse；
NN-only 是否能显著减少 outer iterations；
NN-only 是否能销毁 ILU factor 并节省内存；
NN-only 是否能替代一个 inner smoother step。
```

这正是当前研究问题与用户真正问题之间的主要偏差。

### 审阅判断

用户提出的方向是合理的：下一轮应在训练阶段“假装不存在 ILU”，即不把 ILU 输出、ILU residual 或 ILU metadata 作为网络输入和 teacher。

但必须保留外层数值可信框架。准确路线应是：

```text
raw local residual r_s
-> frozen NN / learned operator
-> z_s^NN ≈ A_s^{-1} r_s
-> local and global true-residual verification
```

“忽略 PC”只适用于网络的训练目标和 runtime local backend，不意味着删除 outer FGMRES、coarse correction、真实 operator 或最终 residual/RTA Gate。

## 3.2 Major：P4 未通过性能信号 Gate

任务书允许两条 P4 成功路径：

```text
A: solve <= 1.05 * baseline AND iterations reduction >= 5%
B: solve reduction >= 10%
```

实测：

```text
iterations reduction = 0.24%
solve reduction = 9.30%
```

两条均未通过。不得用 total time 的 15.49% 替代 solve Gate，也不得把 9.30% 四舍五入为 10%。

此外，P3/P4 重型记录为：

```text
git_commit = null
git_dirty = true
```

因此该 9.30% 只能作为弱 research signal，不能作为 clean-final-HEAD canonical performance claim。

结论：

```text
current active profile = REJECT_AS_FINAL_ACCELERATOR
P5/all-slab = not allowed
h3/h2 = locked
```

## 3.3 Major：局部改善没有转化为预条件器谱的显著改善

P4 中 slab-9 candidate rho 明显优于 baseline：

```text
baseline rho median = 0.533488
candidate rho median = 0.379118
candidate rho p95 = 0.531194
```

但 outer iterations 只从 849 降到 847。

这说明当前最深层瓶颈已不再是 Python 微核，而是：

```text
只修一个 slab 对 16-slab two-level PC 的全局谱影响太弱；
原 ILU 仍保留；
两步 inner smoother 仍保留；
没有减少一个完整的 Maxwell/operator action；
owner-rank 额外工作仍会形成 MPI wait。
```

继续只调 rank 16/24/32/64，不能从根本上解决这一问题。

## 3.4 Moderate：“batched”尚未进入正式全局算法

代码已实现：

```text
predict_many()
action_many()
batch vs independent certification
```

但正式 P4 中仍然是：

```text
one selected slab
-> one vector
-> solve()
```

并未实现同一 owner rank 上多个 slabs 的在线 batch，也没有 all-slab batch integration。

因此当前可接受身份为：

```text
batched API / local microkernel infrastructure
```

不得称为已验证的 batched global smoother。

## 3.5 Moderate：没有内存节省证据

P4 保留 ILU factor，并额外保存：

```text
rank-32 map ≈ 5.14 MiB
slab-9 SciPy CSR duplicate ≈ 10.07 MiB
runtime buffers
```

峰值内存增加 1.43%。由于未销毁任何 ILU factor，不能声称 NN/reduced route 节省预条件器内存。

## 3.6 Moderate：最终 classification 应统一

任务书允许的分类中，与当前结果最接近的是：

```text
microkernel_success_global_neutral
```

outcomes 使用：

```text
local_microkernel_success_global_signal_insufficient
```

含义接近，但不符合冻结枚举。审阅统一采用：

```text
final_classification = microkernel_success_global_neutral
```

## 3.7 Moderate：测试和 provenance 仍不足以支持扩大

当前测试验证了 compiled CSR、batch equality、checkpoint 和 shadow 基础合同。但任务书要求的以下项目尚未形成完整正式证据：

```text
true owner-rank multi-slab batch MPI test
periodic/proxy audit injected failure
active candidate repeated/destroy leak qualification
clean-final-HEAD paired baseline/candidate
selected factor removal and external memory proof
```

因此不得解锁 all-slab、h3 或 h2。

---

# 4. 关于“直接让 NN 学习”的技术判断

## 4.1 为什么当前方法大概率接近 ILU 的迭代表现

当前输出为：

```text
z_NN-enhanced = z_ILU + small low-rank correction
```

当 correction 只覆盖少量 residual modes、只作用一个 slab，并且两级 PC 的其他组成完全不变时，预条件后的全局算子只发生小扰动。因此 outer iterations 与 ILU baseline 接近是预期现象。

这不是数学上“必然完全相同”，因为 correction 可能命中 ILU 最困难的模态并显著改善收敛；但当前实测已经说明：

```text
该 rank-32 单-slab correction 没有命中足以改变全局收敛的关键模态。
```

## 4.2 下一步应直接学习什么

对固定局部 operator `A_s`，理想训练合同应为：

```text
input  = raw local residual r_s
label  = exact/high-accuracy local solution z_s* = A_s^{-1} r_s
output = z_s^NN
```

数据来源应混合：

```text
real Krylov local RHS from independent baseline runs
structured synthetic local errors e_s with r_s = A_s e_s
local wave/interface modes
random combinations across residual magnitude scales
hard residuals collected from failed/stagnating iterations
```

teacher 必须为：

```text
local sparse direct LU
or tightly converged high-accuracy local KSP
```

不得把以下量作为 teacher：

```text
ILU output
ILU residual correction
current approximate PC output
```

训练 loss 至少包括：

```math
L_{corr}=\frac{\|z_s^{NN}-z_s^*\|^2}{\|z_s^*\|^2+\delta}
```

```math
L_{res}=\frac{\|A_sz_s^{NN}-r_s\|^2}{\|r_s\|^2+\delta}
```

## 4.3 为什么 NN-only 有可能优于 ILU

ILU 是对 `A_s` 的不完全分解，忽略部分 fill。若 NN 能逼近更完整的：

```text
A_s^{-1}
```

则它可能给出比 ILU 更强的局部 correction，从而减少 outer FGMRES iterations。

极限情况下，如果每个 slab 都使用 exact local inverse，并配合 overlap/coarse correction，Schwarz PC 通常应比 ILU local solves 更强。但 NN 只是近似，因此实际效果由以下因素决定：

```text
模型是否覆盖真实 Krylov residual distribution；
是否保留关键高频/界面/近核模态；
推理是否比 ILU 足够便宜；
是否作用于足够多的关键 slabs；
local improvement 是否真正改变全局谱；
```

所以 NN-only 不保证一定比 ILU 少迭代，但它至少是一个真正回答“NN 能否替代 ILU”的实验。

## 4.4 固定 operator 下不应默认需要非线性

对固定 `A_s`：

```text
r_s -> A_s^{-1}r_s
```

本质是线性映射。因此下一轮仍应保留一个强制基线：

```text
learned linear inverse / low-rank linear operator
```

然后再比较：

```text
nonlinear MLP
GNN / message passing
operator-conditioned network
```

只有非线性模型在独立验证和全局 A/B 上明确胜出，才有理由承担额外运行成本。

如果目标扩展到不同波长、材料、几何或不同 `A_s`，映射：

```text
(A_s features, r_s) -> z_s
```

才可能需要真正的非线性和图结构。

---

# 5. 推荐的下一轮实验合同

本报告不创建新任务，也不执行任何分支操作。若用户后续建立新 PARA Task，建议冻结以下路线。

## 5.1 Lane A：NN-only single-slab upper bound

选择 h5 的三个代表 slab：

```text
boundary slab
interface/grating slab 9
second interior slab
```

每个 slab 允许先训练独立模型，作为“模型能力上限”实验。第一阶段不追求跨 slab 泛化。

必须比较：

```text
ILU local solve
exact local teacher
NN-only local solve
learned linear inverse baseline
```

Local Gate 建议为：

```text
independent real-Krylov validation
no NaN/Inf
determinism pass
NN-only rho median <= ILU rho median
NN-only rho p95 < 0.95
preferably median improvement >= 20%
inference time <= ILU local solve time, or show a justified global tradeoff
```

## 5.2 Lane B：真正移除 selected slab ILU

只有 NN-only local Gate 通过后，正式 runtime 必须：

```text
do not construct or destroy selected slab ILU after setup
or explicitly destroy factor before solve
selected slab correction = NN-only
```

否则不能称为 ILU replacement，也不能评估 factor-memory saving。

必须记录：

```text
outer iterations
operator applies
PC/one-level applies
NN apply time
MPI wait
full true residual
R/T/A/closure
external RSS/cgroup peak
actual factor nnz/bytes removed
```

## 5.3 Lane C：多 slab 上限实验

若 single-slab NN-only 只产生很小全局变化，不应立即判定 NN 无效。可以在 h5 上训练多个 slab-specific upper-bound models，回答：

```text
如果所有关键 slabs 都有接近 exact local inverse 的 learned solver，
全局 iterations 和 wall time 最多能改善多少？
```

只有该上限实验出现显著 global positive signal，才值得研究 shared model、batching 和跨参数泛化。

## 5.4 停机规则

建议：

```text
single-slab local Gate fail -> stop model lane
three-slab upper-bound global iteration reduction < 10% -> stop NN local-inverse route
all-key-slab upper bound cannot beat total wall time -> stop runtime route
factor removal does not reduce external peak -> no memory claim
h5 global Gate fail -> no h3/h2
```

---

# 6. 接受、拒绝与保留边界

| 对象 | 审阅决定 | 原因 |
|---|---|---|
| persistent SciPy CSR action | ACCEPT as research infrastructure | 正确且约快 13–14 倍 |
| fixed linear reduced map/checkpoint | ACCEPT as local research infrastructure | 线性、确定、低开销、局部 Gate 通过 |
| batch API | ACCEPT as infrastructure only | 未完成 owner multi-slab global integration |
| fused exact audit | ACCEPT | 数值语义正确且比 Task001 便宜 |
| P3 shadow result | ACCEPT as diagnostic | 数值安全通过，performance 有跨 run 限定 |
| P4 active result | ACCEPT as negative/weak-signal evidence | 数值通过，正式 signal Gate 失败 |
| current ILU+reduced active profile | REJECT as final accelerator | 仍保留 ILU/two-step smoother，迭代改善 0.24% |
| factor-memory saving claim | REJECT | 未移除 factor，peak 反而增加 |
| all-slab rollout | NOT ALLOWED | P4 Gate 失败 |
| h3/h2 | NOT ALLOWED | h5 global qualification 不足 |
| ordinary default change | PROHIBITED | research-only |
| master/branch operations | PROHIBITED | 用户明确要求 |

---

# 7. 最终结论

PARA-Task002 的最重要贡献不是证明了 NN PC 能加速，而是把问题定位得更准确：

```text
Task001 的失败首先有实现层原因；
Task002 已基本消除这些实现层原因；
消除后，全局迭代仍几乎不变；
因此当前 ILU-conditioned 单-slab residual correction 的算法影响太弱。
```

最终状态：

```text
PARA-Task002 disposition = ACCEPTED_WITH_QUALIFICATIONS
final classification = microkernel_success_global_neutral
current solver candidate = rejected as final accelerator
research infrastructure = retained on current branch
all-slab/h3/h2 = locked
ordinary default = unchanged
production claim = prohibited
```

后续真正值得回答的问题应改为：

```text
不使用 ILU 作为输入、teacher 或 runtime baseline，
直接用 exact local solves 训练 NN-only local inverse，
并在 selected slab 实际移除 ILU factor 后，
验证它能否减少 outer iterations、wall time 和内存。
```

这条路线才是对“NN 能否替代 ILU/局部 PC”的直接检验。