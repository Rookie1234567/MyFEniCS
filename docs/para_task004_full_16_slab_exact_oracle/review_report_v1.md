# REVIEW REPORT V1：PARA-Task004 全 16-Slab Exact-Local-Inverse Oracle 验收与 Learned-PC 放行结论

## 0. 最终状态

```text
review = PARA-Task004 review_report_v1
branch = ChatGPT/20260715-para-task-neural-local-pc
review_status = PASS_WITH_QUALIFICATIONS
implementation_commit = c8a70dc17e405fcf0bcd5742592530967d26bbc1
no_hidden_ilu_infrastructure = PASS
factor_census = PASS
g4_two_step = NUMERIC_PASS_DIAGNOSTIC
g8_two_step = NUMERIC_PASS_DIAGNOSTIC
g16_two_step = NUMERIC_PASS_POSITIVE_GLOBAL_SIGNAL
g16_two_step_iteration_reduction = 34.2625%
g16_two_step_operator_action_reduction = 34.23%
g16_strong_signal = false
g16_positive_signal = true
g16_one_step = NUMERIC_FAILURE_AND_ARCHITECTURE_SIGNAL_FAIL
learned_model_training_in_task004 = NOT_RUN_BY_CONTRACT
learned_pc_followup_task = APPROVED_AFTER_EXPLICIT_USER_DECISION
preferred_first_learned_configuration = 16 independent slab-specific models as upper-bound experiment
shared_or_expert_model = DEFERRED_UNTIL_INDEPENDENT_MODEL_UPPER_BOUND
h3_allowed = false
h2_allowed = false
ordinary_default_changed = false
production_claim_allowed = false
branch_management = prohibited
master_operations = prohibited
```

PARA-Task004 的实施、数值结果、资源证据和停机边界可以验收。任务首次建立了真正的 `no-hidden-ILU` local backend planning：exact-enabled slab 在 factorization 之前就被识别，不构造 ILU factor，不允许 ILU fallback，运行时 ILU apply count 为 0。该基础设施解决了 PARA-Task003 中“先构造 ILU、再用 exact backend 覆盖 action”的生命周期缺陷。

本任务最重要的科学结论为：

```text
same-run ILU baseline：861 iterations
G4 exact：804 iterations，下降 6.62%
G8 exact：792 iterations，下降 8.01%
G16 exact two-step：566 iterations，下降 34.26%
```

因此，少量 isolated slab replacement 的弱信号不能代表 full all-slab replacement。只有 16 个 local inverses 同时提升时，当前 16-slab Schwarz + 75D coarse + right FGMRES90 架构才出现明显的非线性谱收益。这为后续研究全 slab learned local inverse 提供了可信的理论上限和因果依据。

但本审阅必须同时强调：

```text
exact-LU oracle positive
!= NN 已训练
!= NN 已达到相同局部质量
!= NN 已实现 wall-time acceleration
!= NN 已节省内存
!= production-ready learned PC
```

Task004 本身没有训练任何模型，也不得把 exact-LU 的 174.429 s solve time、873.657 MiB factor storage 或 3.275 GiB worker peak解释为 neural runtime/memory。

---

# 1. 审阅范围

本轮审阅覆盖：

```text
docs/para_task004_full_16_slab_exact_oracle/task.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/*
benchmarks/cases/093_full_16_slab_exact_oracle/
benchmarks/cases/093_full_16_slab_exact_oracle/records/*
benchmarks/neural_pc/benchmark_all_slab_exact_oracle.py
benchmarks/run_workstation_iterative.py
benchmarks/run_task031_memory_forensics.py
src/solvers/local_slab_solver.py
src/solvers/physical_slab_two_level.py
src/solvers/lu_teacher_local_solver.py
src/test/test_36_exact_lu_oracle_petsc_adapter.py
src/test/test_38_local_backend_plan.py
src/test/test_39_all_slab_exact_oracle_contract.py
src/test/test_40_para_task004_contract.py
```

冻结物理与求解框架为：

```text
wavelength = 13.5 nm
material = validated complex Si
geometry = 50 x 25 x 140 nm periodic cell with 17 x 25 x 120 nm block
incidence = theta 80 deg, phi 0 deg, S polarization
finite element = p2 Nedelec hexahedral
mesh = h5, 44,698 FE DoF
periodicity = double Floquet
ports = 80 Fourier-DtN auxiliary unknowns
operator = exact condensed F-C H^-1D
outer = right FGMRES90, rtol 1e-6, max_it 1200
physical slabs = 16, overlap 0.25
coarse = fixed 75D true-action Galerkin
formal parallelism = MPI4, one thread per rank
```

本审阅不执行任何分支管理、master 操作、合并或 production 决策。所有结论只约束当前 research branch。

---

# 2. 接受的基础设施结果

## 2.1 LocalBackendPlan 与 factorization-before-backend 缺陷修复：接受

新增 `LocalBackendPlan`，在任何 local factor 构造之前固定：

```text
identity
requires_ilu_factor
requires_portable_operator
allows_fallback
```

其关键安全约束为：

```text
allows_fallback = true
=> requires_ilu_factor = true
```

exact oracle plan 使用：

```text
identity = sparse_lu_teacher
requires_ilu_factor = false
requires_portable_operator = true
allows_fallback = false
```

因此 exact-enabled slab 不进入 PETSc ILU setup；local factory 接收的 fallback action 为 `None`。这不是“ILU factor 已经构造但运行时不用”，而是真正的 setup-level replacement。

审阅确认：

```text
backend planning = PASS
ordinary ILU path remains available = PASS
fallback-without-ILU rejected = PASS
exact backend identity checked = PASS
```

## 2.2 No-hidden-ILU G16 硬合同：接受

正式 G16 two-step record 满足：

```text
exact_backend_count = 16
ilu_factor_constructed_count = 0
global stored ILU factor nnz = 0
ILU apply count = 0
hidden fallback count = 0
```

同时 root 汇集了 16 个 slabs 的 owner、factor、apply timing 和 destroy diagnostics。Task003 中 non-root timing 未汇集的问题已经关闭。

建议后续将 diagnostics 字段：

```text
global_stored_factor_nnz
```

逐步改名或增加别名：

```text
global_stored_ilu_factor_nnz
```

因为 exact factor nnz 已单独记录，当前旧字段在 no-ILU profile 中为 0，容易被读者误解为“没有任何 factor storage”。这是术语清晰度问题，不阻塞本任务验收。

## 2.3 Factor census 与资源预检：接受

16 个 local operators 均通过逐 slab sparse-LU factorize/test/destroy：

```text
census exact factor nnz = 45,724,195
census explicit factor storage = 915,625,532 B
formal G16 exact factor nnz = 45,747,719
formal G16 explicit factor storage = 916,096,012 B
maximum test RHS residual = 8.3014e-15
factor destroy/reject-after-destroy = 16/16
swap in/out = 0/0
```

census 与 formal run 的约 0.05% fill 差异来自 SuperLU numeric pivot fill；operator fingerprints 不变，局部 residual 与 full solve 均通过。该差异不影响安全或谱结论。

## 2.4 MPI ownership 和 rank balance：接受

正式 G16 每个 MPI rank 拥有 4 个 exact factors：

```text
rank 0: slabs 0,1,8,9
rank 1: slabs 2,3,10,11
rank 2: slabs 4,5,12,13
rank 3: slabs 6,7,14,15
```

per-rank exact factor storage约为：

```text
228.70–229.35 MB
```

factorization sum约为：

```text
6.563–6.601 s
```

critical rank exact solve accumulated time为：

```text
142.176 s
```

所有 rank 的 factor storage和 solve time接近，未发现足以解释迭代正信号的异常 owner imbalance。

---

# 3. 接受的正式数值结果

## 3.1 Same-run ILU baseline：接受

clean implementation SHA 上的正式基线：

```text
iterations = 861
condensed operator applies = 2,603
one-level applies = 5,166
solve = 89.190 s
full residual = 9.992481e-7
external simultaneous worker peak = 1.607 GiB
swap = 0
```

reported、condensed true 和 full augmented residual一致。official R/T/A 与 closure通过。

## 3.2 G4/G8 梯度：接受为趋势诊断

```text
G4  = {0,5,10,15}
iterations = 804
reduction = 6.62%
operator applies = 2,430

G8  = {0,2,5,7,8,10,13,15}
iterations = 792
reduction = 8.01%
operator applies = 2,394
```

两者 numeric Gate、R/T/A、memory 和 no-hidden-ILU Gate通过。它们不构成 learned-PC 解锁依据，只用于说明 replacement 数量与空间覆盖的趋势。

## 3.3 G16 two-step：接受为 positive global oracle signal

正式结果：

```text
iterations = 566
iteration reduction = 34.2625%
condensed operator applies = 1,712
operator action reduction = 34.23%
one-level applies = 3,396
one-level reduction = 34.26%
full residual = 9.974429e-7
max official R/T/A delta = 6.131e-9
closure = -5.484e-9
external simultaneous worker peak = 3.275 GiB
swap = 0
```

该结果满足任务书：

```text
Positive Signal: outer iteration reduction >= 20%
```

但未满足：

```text
Strong Signal: outer iteration reduction >= 40%
```

因此最终身份应为：

```text
all_slab_oracle_positive_signal
```

而不是 `strong_signal`。

## 3.4 G16 one-step：接受为完整负结果

one-step 配置虽然把 one-level applies降至 2,400，但：

```text
iterations = 1200, reached max_it
reported/full residual = 1.048139e-5
KSP reason = -3
condensed operator applies = 3,629
```

相对 baseline：

```text
outer iterations at least +39.37%
operator applies +39.42%
```

因此 one-step 同时失败：

```text
numeric Gate
operator-action Gate
outer-increase Gate
```

未收敛场没有进入 official R/T/A，处理正确。

审阅结论：

```text
G16 one-step = REJECTED
future learned PC default must retain current two-step smoother
```

不得因为 one-step 单次 PC apply 较少而忽略其全局 operator action反而增加的事实。

---

# 4. 核心科学解释

## 4.1 Task003 少量 slab 负结果与 Task004 全 slab 正结果并不矛盾

历史结果：

```text
1 exact slab: 860 -> 862
3 exact slabs: 860 -> 840, reduction 2.33%
```

Task004：

```text
4 exact slabs: reduction 6.62%
8 exact slabs: reduction 8.01%
16 exact slabs: reduction 34.26%
```

这说明 local inverse 对全局预条件算子的影响不是按 slab 数线性叠加。只增强少量 isolated local blocks时，大部分 Schwarz action仍由 ILU质量控制；全部 16 个 local blocks同时增强后，预条件后算子的谱/非正规结构发生了更明显的整体变化。

因此 Task003 的停机决定仍然正确：

```text
不应为 1–3 个低杠杆 slabs 训练模型。
```

Task004 则提供了新的、此前不存在的依据：

```text
全 16-slab learned replacement值得进入独立研究任务。
```

## 4.2 当前 two-step smoother 仍不可删除

G16 exact inverse 已经是非常强的 one-level action，但 one-step仍不能在 1200 步内达到 `1e-6`。这说明 current two-step inner GMRES不是单纯重复局部求解，而是在真实 shifted operator上重新组合 Schwarz directions，对收敛至关重要。

后续 learned local inverse应首先近似：

```text
G16 exact local inverse + current two-step smoother
```

而不是直接追求：

```text
one learned apply replaces the entire two-step smoother
```

除非新的独立任务重新设计整个 smoother/coarse interaction并重新通过 full Gate。

---

# 5. 性能与内存限定

## 5.1 Exact-LU wall time不是 learned-PC 性能

正式 wall time：

```text
baseline solve = 89.190 s
G16 exact two-step solve = 174.429 s
```

G16 exact 更慢，主要因为 SciPy sparse-LU triangular solves累计约 142.176 s。该结果只说明 exact local inverse的谱质量，不说明未来 learned action一定更快。

不得表述：

```text
Task004 已实现求解加速
Task004 neural PC faster
exact LU runtime代表 NN runtime
```

可接受表述为：

```text
Task004证明了未来 learned local inverse存在34.26%的iteration/action理论收益上限；
是否转化为wall-time收益取决于learned action的质量、成本、存储和通信。
```

## 5.2 Learned runtime budget：接受为规划上限，不是性能保证

为了达到至少20%的 projected solve speedup：

```text
target solve <= 71.352 s
critical learned-local total budget <= 39.100 s
```

对应：

```text
independent model <= 2.878 ms per slab call
owner batch of 4 slabs <= 11.514 ms per one-level apply
all-rank critical path <= 11.514 ms per global one-level apply
```

该预算基于从 formal telemetry中分离 critical exact-solve time和non-local observed time。它是合理的 first-screen budget，但仍包含以下近似：

- critical owner local time被视为主要串行关键路径；
- future model保持接近566-step exact-oracle谱质量；
- future model不会增加额外MPI同步、audit或device-transfer瓶颈；
- training/setup amortization未包含。

因此 Task005 必须重新实测：

```text
packing
inference
H2D/D2H if any
audit
gather/scatter
MPI wait
full solve
```

不得仅以 microbenchmark低于2.878 ms宣布成功。

## 5.3 Learned storage budget：接受为 memory-neutral reference

被移除的 baseline ILU factor estimate为：

```text
global = 141,220,416 B = 134.678 MiB
per owner rank = 35,305,104 B = 33.670 MiB
```

未来：

```text
model + bases + persistent buffers + required runtime operator/audit storage
```

若要声称 memory-neutral，应不超过上述预算。

Exact oracle factor storage：

```text
916,096,012 B = 873.657 MiB
```

只属于 oracle，不是 learned model预算或 neural memory结论。

---

# 6. Provenance 与验证

接受以下证据：

```text
implementation SHA = c8a70dc17e405fcf0bcd5742592530967d26bbc1
tracked_source_dirty = false
host clean attestation = present
baseline/G4/G8/G16/one-step = same clean implementation SHA
heavy records = Git ignored
lightweight records = bind heavy JSON SHA-256
```

验证结果：

```text
Task004 targeted contracts = 22 passed
complete src/test = 195 passed, 11 skipped
MPI2 exact owner/gather/lifecycle = 4 passed per rank
Ruff = pass
compileall = pass
git diff --check = pass
heavy artifact ignore audit = pass
```

外部 sampler summary顶层仍保留历史：

```text
task = Task031
```

但 Case093、worker command、source SHA和outcomes均正确标识 PARA-Task004。该字段是复用 sampler schema的遗留标签，不影响数据，但建议后续将其改为通用：

```text
sampler_schema_origin = Task031
current_task = PARA-Task005
```

避免未来审阅时产生身份混淆。

---

# 7. 阻塞性边界与不可宣称事项

## 7.1 本任务没有证明 learned model能保持 exact-oracle谱质量

Exact inverse residual接近机器精度。未来低秩线性模型、MLP、GNN或shared model均可能显著弱于 exact inverse，导致：

```text
566-step oracle
-> learned profile回升至700、900或不收敛
```

因此不能从34.26% oracle reduction直接承诺任何 learned iteration count。

## 7.2 本任务只覆盖一个h5物理/RHS

当前结论限定于：

```text
one geometry
one wavelength
one angle/polarization
one RHS
h5
MPI4
current 16-slab partition
current 75D coarse
```

它不证明：

- h3/h2同样有34%收益；
- 不同波长/角度/材料可复用模型；
- shared universal model可行；
- parameter scan或inverse problem已获得amortized speedup；
- ordinary solver应改变默认。

## 7.3 One-step不得作为Task005默认路线

Task005若建立，必须保持：

```text
smoother_iterations = 2
post_smooth = current frozen setting
coarse = 75D
outer = right FGMRES90
```

one-step只保留为Task004 negative evidence。

---

# 8. 后续 Learned-PC 研究建议

## 8.1 是否允许新的 Task005

审阅结论：

```text
Task005 learned all-slab local inverse research = APPROVED
```

但必须满足：

- 用户明确要求创建新任务；
- 仍在research branch执行；
- 不自动改变ordinary default；
- 不自动运行h3/h2；
- 不把Task004 exact oracle称为NN结果。

## 8.2 第一轮应采用16个独立slab-specific模型

建议第一阶段使用：

```text
N_s: raw local residual r_s -> z_s ≈ A_s^-1 r_s
s = 0,...,15
```

即16个独立模型作为**能力与工程上限实验**。理由：

1. G16 exact oracle证明全slab同时增强才有明显收益；
2. 一开始使用通用模型会混淆“模型容量不足”和“local-inverse路线本身不可行”；
3. 每个slab operator fingerprint不同，16个独立模型最容易建立严格teacher、checksum和factor-removal因果链；
4. 只有独立模型上限成功后，才值得压缩为3 experts或shared trunk + slab adapters。

该身份必须明确为：

```text
fixed-operator engineering upper-bound
not generalizable universal neural preconditioner
```

## 8.3 每个slab仍应强制比较linear inverse与nonlinear NN

固定 `A_s` 下：

```text
r_s -> A_s^-1 r_s
```

本质为线性映射。因此每个slab必须先测试：

```text
learned linear/low-rank inverse
```

只有nonlinear model在独立real-Krylov validation和runtime budget上明确胜出，才允许承担额外复杂度。

## 8.4 数据与teacher建议

使用Task003已经验证的合同扩展至16slabs：

```text
raw RHS only
one sparse-LU factor per slab
many RHS labels
factor one slab -> generate -> destroy -> next slab
independent train / validation / holdout captures
no ILU output/residual as teacher
```

禁止同时常驻16个teacher LU factors。

## 8.5 Task005最低Gate建议

### Local quality Gate

每个slab必须：

```text
teacher residual pass
all outputs finite
determinism pass
independent real-Krylov holdout
learned local residual显著优于该slab ILU baseline
inference/audit满足预算或给出可信batch方案
```

不应只报告平均值；必须列出16个slabs的median/p95/worst，并对最差slab fail closed。

### Shadow Gate

正式active前：

```text
all 16 learned outputs计算
exact local audit every call
ILU仍写回，仅作对照
记录learned-vs-ILU-vs-teacher residual
记录owner batch、MPI wait和总overhead
```

若shadow overhead已使projected 20% speedup不可能，应停止active。

### Factor-removal Gate

最终learned candidate必须：

```text
16 learned backends active
16 ILU factors not constructed
ILU apply count = 0
hidden fallback = 0
current two-step smoother retained
```

诊断性fallback profile可以先运行，但不能用于memory-saving或true-replacement声明。

### Global numeric Gate

```text
KSP reason > 0
reported/condensed/full residual <= 1e-6
max official R/T/A delta <= 1e-6
closure pass
all finite
```

### Global signal Gate

建议至少同时要求：

```text
outer iteration reduction >= 20%
solve wall time reduction >= 20%
```

即：

```text
iterations <= approximately 688 relative to 861 baseline
solve <= approximately 71.35 s relative to 89.19 s baseline
```

还应报告相对exact oracle的收益保留比例：

```text
oracle benefit retention =
(baseline_iterations - learned_iterations)
/
(baseline_iterations - exact_iterations)
```

这可以区分：

```text
模型很快但几乎没有谱改善
vs
模型保留大部分exact inverse价值
```

### Storage Gate

memory-neutral目标：

```text
global learned storage <= 134.678 MiB
per owner rank <= 33.670 MiB
```

同时external worker peak不得因额外CSR、audit和allocator显著超过baseline。若以速度优先允许小幅内存增加，必须预先冻结上限，不能运行后解释。

## 8.6 Shared/expert模型的顺序

只有16 independent model profile通过full Gate后，才进入后续压缩：

```text
16 independent models
-> 3 physical expert classes
-> shared trunk + slab-specific encoders/decoders
-> operator-conditioned cross-parameter model
```

不能跳过upper-bound实验直接声称一个shared model失败就代表learned local inverse路线失败。

---

# 9. 最终验收结论

```text
PARA-Task004 disposition = ACCEPTED_WITH_QUALIFICATIONS
no-hidden-ILU infrastructure = ACCEPTED
factor census and MPI diagnostics = ACCEPTED
G16 two-step exact oracle = POSITIVE GLOBAL SIGNAL
G16 one-step = REJECTED
learned model result = NOT YET AVAILABLE
neural acceleration claim = NOT ALLOWED
memory-saving claim = NOT ALLOWED
Task005 all-slab learned inverse research = APPROVED AFTER USER DECISION
preferred first Task005 lane = 16 independent slab-specific learned inverses
ordinary default = UNCHANGED
h3/h2 = LOCKED
production merge/default discussion = OUT OF SCOPE
```

Task004 已经回答了最关键的 go/no-go 问题：

```text
全部16个local inverses同时增强时，当前架构存在约34%的outer/action理论收益；
因此全slab learned local inverse值得进入独立研究任务。
```

下一步的难点不再是“local inverse是否有全局价值”，而是：

```text
能否在每slab约2.878 ms、每owner batch约11.514 ms、每rank约33.670 MiB的严格预算内，
让16个 learned models保留足够的exact-inverse谱质量，
并在no-hidden-ILU two-step full solve中真正实现至少20%的wall-time加速。
```
