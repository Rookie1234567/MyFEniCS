# PARA-Task002：Batched Low-Overhead Neural Smoother Acceleration

## 0. 任务身份

```text
task = PARA-Task002
name = Batched Low-Overhead Neural Smoother Acceleration
status = planned / research-only continuation
execution_branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task001
predecessor_implementation_sha = ee5d248e09aaff3700f22805024ce0abc2e25822
predecessor_review = docs/para_task001_neural_local_pc_acceleration/review_report_v1.md
remote_repository = Rookie1234567/MyFEniCS
reference_wavelength = 13.5 nm
reference_geometry = current validated full-3D periodic Si block grating
reference_discretization = p2 Nedelec hexahedral FEM
reference_parallelism = MPI4 for formal h5 A/B
ordinary_default_changed = false
production_claim_allowed = false before final review
branch_management = prohibited by explicit user instruction
master_operations = prohibited by explicit user instruction
```

### 0.1 分支操作禁令

本任务只允许在现有：

```text
ChatGPT/20260715-para-task-neural-local-pc
```

分支中新增或修改任务相关文件。不得：

- 创建新分支；
- 切换到其他开发分支；
- merge、rebase、cherry-pick 或 reset 分支历史；
- 移动、重命名或删除远程分支；
- push、merge 或提交到 `master`；
- 因当前分支与主线存在差异而主动同步主线；
- 开 PR 或执行任何分支管理动作。

若当前分支缺少主线新基础设施，应在 outcomes 中记录限制，不得擅自同步或改写分支历史。

---

# 1. 为什么启动本任务

PARA-Task001 已证明两件不同的事实：

1. **数值正信号存在。** 冻结 POD-MLP 能改善真实 h5 slab-9 的 ILU residual，one-slab full true residual、official R/T/A 和能量闭合全部通过；
2. **当前工程实现失败。** 外层迭代仅从 861 降到 854，下降 0.813%，但 solve time 从 93.312 s 增至 412.318 s，total time 从 156.746 s 增至 452.641 s，峰值内存增加 3.241%。

PARA-Task001 的主要性能成本为：

```text
per-slab Python/NumPy small-call inference
+ large POD projections executed one vector at a time
+ Python-row-loop portable CSR action
+ multiple exact local residual/non-degradation checks
+ owner-rank MPI waiting
+ original ILU and two-step smoother still retained
```

其中 outcomes 已记录：

```text
5124 NN calls
NN inference accumulated = 35.036 s
NN residual checks accumulated = 69.543 s
one-level mean apply = 0.00937 s -> 0.07125 s
```

因此本任务不再研究“把相同单-slab POD-MLP 复制到更多 slabs”。新的核心问题是：

```text
能否把 NN/reduced correction 变成一个真正低开销、批量、可替代昂贵步骤的 smoother，
而不是在原 ILU 与 inner GMRES 之后继续叠加额外计算？
```

本任务仍是 full-3D FEM 路线的 research-only 并行试验，不改变 Hybrid FEM–Modal、自适应或其他主路线，也不改变 ordinary solver default。

---

# 2. 开始前必须读取

执行者开始前必须完整读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/solver_guide.md
docs/iterative_solver_ports.md
docs/architecture_overview.md

docs/para_task001_neural_local_pc_acceleration/task.md
docs/para_task001_neural_local_pc_acceleration/outcomes/summary.md
docs/para_task001_neural_local_pc_acceleration/outcomes/runtime_breakdown.csv
docs/para_task001_neural_local_pc_acceleration/outcomes/memory_report.md
docs/para_task001_neural_local_pc_acceleration/outcomes/model_and_dataset_provenance.md
docs/para_task001_neural_local_pc_acceleration/review_report_v1.md

benchmarks/cases/090_neural_local_pc_acceleration/README.md
src/solvers/local_slab_solver.py
src/solvers/neural_local_pc.py
src/solvers/physical_slab_two_level.py
benchmarks/neural_pc/data_contract.py
benchmarks/neural_pc/petsc_capture.py
benchmarks/neural_pc/train_local_pc.py
benchmarks/neural_pc/evaluate_local_pc.py
benchmarks/run_workstation_iterative.py
```

完成任务时必须维护：

```text
docs/para_task002_batched_neural_smoother_acceleration/outcomes/summary.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/changed_files.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/experiment_matrix.csv
docs/para_task002_batched_neural_smoother_acceleration/outcomes/microkernel_breakdown.csv
docs/para_task002_batched_neural_smoother_acceleration/outcomes/runtime_breakdown.csv
docs/para_task002_batched_neural_smoother_acceleration/outcomes/memory_report.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/model_and_dataset_provenance.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/decision.md
docs/development_progress.md
benchmarks/cases/091_batched_neural_smoother_acceleration/
```

重型 artifacts 必须放在：

```text
benchmarks/artifacts/cases/091/
```

并保持 Git ignored。不得提交大型 CSR、训练集、checkpoint、完整 profiler、raw field、HDF5 或全量日志。

---

# 3. 冻结物理与数值基线

## 3.1 冻结物理模型

第一阶段继续使用 PARA-Task001 的真实 h5 目标：

```text
wavelength = 13.5 nm
material = current validated complex Si optical constant
periodic cell = 50 x 25 x 140 nm
Si block = 17 x 25 x 120 nm
incidence = theta=80 deg, phi=0 deg, S polarization
periodicity = double Floquet in x/y
ports = current 80 auxiliary Fourier-DtN unknowns
finite element = p2 Nedelec hexahedral
formal MPI = 4 ranks
```

第一阶段不得同时改变：

- 波长、材料、几何或偏振；
- DtN 模态定义；
- 16-slab 划分、overlap 或 owner assignment；
- 75D coarse basis；
- outer FGMRES 设置；
- official R/T/A 口径；
- baseline operator action 路线。

## 3.2 正式 h5 比较基线

冻结 PARA-Task001 真实 h5 original ILU baseline：

```text
iterations = 861
solve_s = 93.311718469
total_s = 156.745570644
peak_including_RTA = 1.602940 GiB
full true residual <= 1e-6
official R/T/A and closure = pass
```

正式性能声明必须在同一机器、同一 MPI4、同一 action、同一 thread 设置和同一 memory sampler 下重新运行 baseline 与 candidate。历史数字只用于 sanity，不得替代正式同轮 A/B。

## 3.3 PARA-Task001 负候选

当前 one-slab ILU+NN 负候选：

```text
iterations = 854
solve_s = 412.318154497
total_s = 452.640684922
peak = 1.654888 GiB
NN inference accumulated = 35.036240659 s
NN residual check accumulated = 69.543171739 s
```

本任务所有 micro-optimization 都必须与该负候选拆分比较，证明究竟消除了哪一项成本。

---

# 4. 核心研究假设

本任务验证以下四个假设。

## H1：portable CSR Python row loop 是主要可消除成本

当前 `LocalCsrOperator.action()` 逐行执行 Python 循环。该实现适合小 fixture 和可移植性验证，不适合作为生产-sized slab 的高频 residual check。

必须比较：

```text
current Python-row CSR action
SciPy CSR matvec
PETSc owner-local MatMult
optional CuPy/torch sparse action
```

并验证相对 action error：

```text
<= 1e-12 in complex128
```

若优化后的 local action 不能显著加速，不得把后续收益归因于 NN。

## H2：线性 reduced operator 可能比非线性 MLP 更合适

对于固定 local operator，目标 inverse action 本质上是线性的。PARA-Task001 的 nonlinear MLP 可能没有提供足够迭代收益，却增加了运行时成本。

必须首先测试：

```text
reduced residual coordinates c = U_r^H r
reduced correction d = W_r c
z = V_r d
```

其中 `W_r` 可由 teacher pairs 通过 least squares / ridge / reduced Galerkin 直接构造。

该 lane 的目的不是追求最低训练 loss，而是形成可由 BLAS 高效执行的固定线性 preconditioner action。

## H3：owner-local batching 可以摊薄调用开销

MPI4、16 slabs 下，每个 owner rank 通常负责多个 slabs。应将同一 owner 上多个 residual 的 reduced coordinates 组成 batch：

```text
[r_s1, r_s2, ...]
-> slab-specific encoder / shared reduced trunk / slab-specific decoder
-> [delta z_s1, delta z_s2, ...]
```

允许 slab 尺寸不同，但必须采用：

- reduced-coordinate bucketing；
- fixed-rank padding + mask；
- shared trunk + slab-specific small adapters；
- 或其他不要求全局 dense padding 的方案。

不得把完整 global PETSc vector 送入 GPU。

## H4：NN 必须替代昂贵步骤，而不是额外叠加

优先验证：

```text
current two-step inner GMRES smoother
-> one ILU apply + one batched reduced correction
```

或：

```text
current second local/inner correction
-> batched neural/reduced correction
```

只有 NN-only local action 通过严格 Gate 后，才允许试验移除一个 selected slab 的 ILU factor。

本任务不接受：

```text
ILU + two-step inner GMRES + full per-call residual checks + extra NN
```

作为最终候选，因为这不会解决 PARA-Task001 的根因。

---

# 5. 必须保留的可信框架

不得替换或弱化：

- exact condensed operator `F-C H^-1D`；
- outer right FGMRES；
- 75D true-action Galerkin coarse correction；
- physical slab index sets、overlap、weights、owner assignment 和 MPI scatter；
- final condensed/full augmented explicit true residual；
- official modal R/T/A 和 volume absorption；
- energy closure；
- current memory sampler、watchdog、lifecycle 和 provenance；
- frozen checkpoint/checksum；
- no-online-training rule。

NN/reduced model 只允许进入：

```text
local slab correction
inner smoother replacement
selected factor replacement after local Gate
```

不得输出最终全局场，不得替代真实 operator verification。

---

# 6. 候选 lanes

## Lane A：Optimized local action microkernel

目标：消除与 NN 无关的 Python CSR 瓶颈。

实现和比较：

```text
A0 = current LocalCsrOperator.action Python loop
A1 = scipy.sparse.csr_matrix.dot
A2 = owner-local PETSc Mat.mult
A3 = optional persistent GPU sparse action
```

必须记录：

- build/setup time；
- mean、median、p95 action time；
- action relative error；
- temporary allocation；
- repeated-call stability；
- thread count；
- CSR storage duplication。

A1/A2 中最优者成为后续 residual check 和 reduced correction 的正式 local action backend。

## Lane B：Linear reduced correction（第一优先）

使用现有 real Krylov / ILU residual dataset 构造：

```text
q_s = r_s - A_s z_s^ILU
c_s = U_s^H q_s
d_s = W_s c_s
delta z_s = V_s d_s
```

允许：

- POD/SVD bases；
- ridge regression；
- reduced Galerkin inverse；
- low-rank Woodbury-like correction；
- complex or real-imag packed BLAS。

要求：

- frozen fixed linear action；
- determinism error `<=1e-13`；
- linearity error `<=1e-11`；
- no nonlinear activation；
- no Python loop over DoFs；
- batched `predict_many()` API；
- model storage、temporary storage 和 setup time 可审计。

## Lane C：Batched shared-trunk neural correction

只有 Lane B 无法达到局部质量 Gate或显示非线性明确必要性时才进入。

推荐结构：

```text
slab-specific encoder U_s
-> fixed reduced rank r
-> shared small MLP / residual network
-> slab-specific decoder V_s
```

运行时必须：

- persistent model；
- persistent staging buffers；
- owner-local batch；
- no per-call checkpoint load；
- no file/subprocess exchange；
- CPU and optional same-process GPU backend 分别 benchmark；
- GPU lane 必须分解 H2D、inference、D2H、synchronization。

若 complex PETSc FE 环境无法安全加载 CUDA runtime，必须记录环境限制，不得通过每次迭代启动外部 Python 进程规避。

## Lane D：One-step smoother replacement

仅当 Lane B/C 在 local microbenchmark 和 shadow integration 中出现明确正信号时测试。

候选：

```text
current: inner GMRES step 1 + inner GMRES step 2
candidate: one ILU/local Schwarz step + one batched reduced correction
```

必须记录：

- outer operator apply count；
- inner operator apply count；
- one-level apply count；
- coarse apply count；
- outer iterations；
- per-iteration wall time。

目标是减少真实 Maxwell action 次数，而不是只替换一个便宜的 dense coarse solve。

## Lane E：Selected ILU factor removal（严格条件）

只有某个 slab 的 NN-only/reduced-only action 在 independent real-Krylov validation 上达到：

```text
rho median <= current ILU rho median * 1.10
rho p95 < 0.95
no NaN/Inf
fixed action certified
runtime <= current ILU solve time
```

才允许对该 slab 做 factor removal A/B。

任何内存节约声明必须实测：

```text
factor destroyed before solve
external simultaneous worker RSS下降
cgroup peak下降
no hidden duplicate CSR/device copy抵消收益
```

---

# 7. Safety 与 residual audit 新策略

PARA-Task001 每次调用做多次 exact local residual action，安全但过贵。本任务允许研究分层 audit，但必须先经过 shadow 证据。

## 7.1 Shadow mode

第一阶段每次同时计算：

```text
candidate output
exact local rho
baseline ILU rho
non-degradation decision
```

但不一定把 candidate 写入全局。用于建立误判率和 proxy 可靠性。

## 7.2 Fused exact audit

优先复用已经计算的：

```text
q_s = r_s - A_s z_s^ILU
```

避免重复计算相同 `A_s z`。若 candidate 为 `z_ilu + delta`：

```text
candidate residual = q_s - A_s delta
```

只需要新增一次 `A_s delta`，不得再次完整计算 `A_s(z_ilu+delta)`。

## 7.3 Periodic audit

只有 shadow mode 证明：

```text
no accepted harmful candidate
proxy false-accept rate = 0 on recorded validation
periodic exact audit catches injected failure
```

后，才允许：

- 每 `K` 次 exact local audit；
- 其余调用使用 norm bound / reduced residual proxy；
- 新 checkpoint 前若 fingerprint、norm distribution 或 global residual 异常则立即恢复 every-call audit；
- final global true residual 始终不能抽样。

## 7.4 Fail closed

以下情况必须回退当前 ILU 或终止 candidate：

- missing/corrupt checkpoint；
- fingerprint/action-equivalence certificate mismatch；
- NaN/Inf；
- abnormal output norm；
- exact audit failure；
- proxy/exact disagreement超过阈值；
- global true residual异常增长；
- MPI rank exception；
- GPU synchronization/device failure。

---

# 8. Operator fingerprint 与 canonical representation

PARA-Task001 两次独立 run 中有 6/16 slab 发生位级 fingerprint 变化。本任务不得简单关闭 fingerprint。

必须先诊断变化来自：

```text
DoF local ordering
MPI partition / owner ordering
CSR column ordering
duplicate summation order
floating-point assembly variation
actual operator value change
```

允许新增：

- sorted CSR canonicalization；
- duplicate-column consolidation；
- canonical local DoF permutation；
- rounded diagnostic fingerprint（只能辅助，不能代替 exact）；
- random-vector action certificate；
- permutation-equivalence certificate。

模型复用只有在：

```text
exact fingerprint match
or rigorously certified permutation/action equivalence
```

时允许。不得用宽松数值 hash 直接跳过安全检查。

---

# 9. 实施阶段与 Gate

## P0：环境和基线冻结

必须记录：

```text
git status / HEAD / remote
current branch identity
explicit no-branch-operation acknowledgement
WSL/Python/PETSc/DOLFINx/MPC/PyTorch/SciPy versions
CPU/GPU/thread/MPI settings
artifact root
```

运行：

- pure unit/import smoke；
- current h5 baseline；
- current one-slab negative candidate（若环境允许）；
- `git diff --check`。

不得运行 h3/h2。

## P1：Local action microbenchmark

至少用：

- one boundary slab；
- slab 9 grating/interior representative；
- one second interior slab。

Gate：

```text
action relative error <= 1e-12
optimized mean action time <= 0.20 * Python-loop mean
optimized p95 action time <= 0.30 * Python-loop p95
no repeated-call memory growth
```

若达不到，必须保留准确结果并解释，不得继续把 Python loop 作为正式 high-frequency backend。

## P2：Linear reduced map

训练/构造数据必须使用独立 runs 或独立时间段：

```text
train = capture A
validation = capture B
runtime A/B = capture-independent solve
```

Local Gate：

```text
linearity error <= 1e-11
determinism error <= 1e-13
ilu-residual correction rho median <= 0.60
rho p95 <= 0.85
batched output finite
batch result equals independent result <= 1e-12
```

Performance micro-Gate：

```text
optimized inference + fused audit mean <= 0.25 * PARA-Task001 inference+audit mean
p95 <= 0.35 * PARA-Task001 p95
```

同时必须与 current ILU local solve 直接比较。

## P3：One-slab shadow integration

先运行：

```text
candidate computed
exact audits recorded
but global output remains original ILU
```

证明：

- diagnostics 没有改变 baseline 数值；
- timing 拆分准确；
- audit false accept/false reject 可解释；
- MPI owner waiting 可测量。

若 shadow overhead 本身已超过 baseline solve time 10%，必须先优化，不得进入 active candidate。

## P4：One-slab active h5 A/B

必须满足数值 Gate：

```text
full augmented true residual <= 1e-6
max official R/T/A delta <= 1e-6
energy closure within current Gate
no hidden online training
```

One-slab Engineering Signal Gate：

```text
solve time <= 1.05 * same-run baseline
and outer iterations reduction >= 5%
```

或：

```text
solve time reduction >= 10%
with no numeric degradation
```

未达到至少一个条件时，不得进入 all-slab batch。

## P5：Owner-batch / all-slab h5 conditional

只有 P4 通过才允许。

正式 Engineering Positive Gate：

```text
full augmented true residual <= 1e-6
max official R/T/A delta <= 1e-6
energy closure pass
solve wall time reduction >= 20%
peak memory increase <= 10%
no online training
no uncontrolled fallback concentration
```

Strong Gate：

```text
solve wall time reduction >= 2x and peak <= baseline
or peak memory reduction >= 20% with no solve-time regression
```

必须同时报告：

- iteration reduction；
- operator action reduction；
- per-step cost；
- batch utilization；
- MPI wait time；
- audit cost；
- model/device memory；
- training amortization。

## P6：h3/h2 锁定

本任务默认不运行 h3/h2。

只有 h5 all-slab 达到 Engineering Positive Gate，并经新的 ChatGPT review 明确放行后，才可在后续任务考虑 h3/h2。执行者不得自行解锁。

---

# 10. 性能诊断要求

必须拆分：

```text
condensed/fine operator action
inner operator action
local gather/scatter
ILU factor solve
Python CSR action
optimized CSR/PETSc action
POD/reduced encode
reduced map / MLP
reduced decode
batch packing
H2D / D2H
GPU synchronization
exact residual audit
proxy audit
coarse projection/solve
FGMRES orthogonalization if available
MPI wait / imbalance
setup/checkpoint load
training time
```

至少记录：

```text
mean / median / p95 / max
call counts
bytes moved
batch size and utilization
operator apply counts
outer iterations
solve / total wall time
external worker RSS / cgroup peak
GPU peak allocated/reserved
checkpoint and dataset size
```

不得只报告训练 loss或 GPU kernel 时间。

---

# 11. 内存评估合同

内存必须区分：

```text
host model weights
host POD bases
host local CSR
PETSc local matrix/factor
staging buffers
device weights
device persistent buffers
device temporary activations
Krylov vectors
coarse objects
```

若 ILU 保留：

```text
不得声称 NN 节省了预条件器内存
```

若 factor removal：

```text
必须在 factor destroy 后用 external sampler 证明峰值下降
```

必须给出单次 solve 和多 RHS amortization：

```text
total effective time = training + setup + sum(solve_i)
```

训练成本不能无条件忽略。

---

# 12. 测试要求

至少新增或更新：

1. optimized CSR/PETSc local action equivalence；
2. Python-loop vs optimized action timing smoke（非硬编码绝对时间 Gate可放 benchmark）；
3. batched complex pack/unpack round trip；
4. batched prediction等价于逐样本 prediction；
5. linearity/determinism certification；
6. fused residual identity：`q-A delta` 等价于 full candidate residual；
7. periodic audit injected-failure test；
8. proxy false-accept fail-closed test；
9. checkpoint/fingerprint/permutation certificate tests；
10. single-rank/MPI2 owner-batch adapter；
11. repeated apply/destroy no leak；
12. h5 shadow mode no-numeric-change integration；
13. h5 active candidate full true residual/RTA Gate；
14. current full unit suite；
15. benchmark contract checker；
16. `git diff --check`。

随机训练必须记录 seed；性能试验必须记录 warm-up、thread、CPU affinity 和 GPU synchronization方法。

---

# 13. 禁止事项

本任务不得：

- 进行任何分支管理或 `master` 操作；
- 直接复制 PARA-Task001 单-slab NumPy MLP 到 16 slabs 后运行；
- 未优化 Python CSR action 就做正式性能结论；
- 用训练 loss代替 local action Gate；
- 用 local rho代替 full true residual；
- 在正式 solve 中在线训练；
- 每次迭代通过文件或 subprocess 调用外部 GPU trainer；
- 在 h5 Gate 前运行 h3/h2；
- 为追求速度删除 final global true residual/RTA；
- 未建立 action/permutation equivalence 就放宽 fingerprint；
- ILU 保留时声称实现了 factor-memory saving；
- 把不同 action、不同硬件、不同 MPI/thread 或不同 sampler 结果当严格 A/B；
- 提交大型模型、训练数据、CSR 或 profiler artifacts；
- 宣称参数通用、mesh independent 或 production-ready。

---

# 14. 交付物

建议代码路径：

```text
src/solvers/local_slab_solver.py
src/solvers/neural_local_pc.py
src/solvers/batched_reduced_smoother.py
benchmarks/neural_pc/benchmark_local_action.py
benchmarks/neural_pc/fit_linear_reduced_map.py
benchmarks/neural_pc/evaluate_batched_smoother.py
benchmarks/run_batched_neural_smoother.py
benchmarks/cases/091_batched_neural_smoother_acceleration/
src/test/test_34_optimized_local_csr_action.py
src/test/test_35_batched_reduced_smoother.py
src/test/test_36_para_task002_contract.py
```

文件名可以调整，但职责必须保持清楚，不能把训练、runtime 和 benchmark 混在单一脚本。

任务文档至少包括：

```text
outcomes/summary.md
outcomes/changed_files.md
outcomes/experiment_matrix.csv
outcomes/microkernel_breakdown.csv
outcomes/runtime_breakdown.csv
outcomes/memory_report.md
outcomes/model_and_dataset_provenance.md
outcomes/decision.md
review_report_vN.md / response_vN.md
```

---

# 15. 最终分类

最终 classification 必须从以下选择：

```text
strong_speed_and_memory_success
speed_success_memory_neutral
memory_success_speed_neutral
engineering_positive_unqualified
microkernel_success_global_neutral
local_feasibility_only
numeric_failure
performance_failure
not_feasible_with_current_runtime_architecture
```

默认边界：

- 当前分支中的代码和文档仅用于 research；
- 不讨论或执行 master merge；
- 不改变 ordinary default；
- checkpoint 和 heavy artifacts 留在 ignored目录；
- 当前任务是否继续，由最终 review 决定；
- h3/h2 始终保持锁定，除非后续 review 明确解除。

---

# 16. 最短执行顺序

```text
P0 reproduce h5 baseline
-> P1 eliminate Python CSR action bottleneck
-> P2 fit/evaluate fixed linear reduced map
-> P3 shadow integration
-> P4 active one-slab h5 A/B
-> Gate
-> P5 owner-batch/all-slab h5 conditional
-> final review
```

不得跳步。

---

# 17. 任务完成标准

本任务不能以“代码可运行”或“loss 下降”完成。至少必须回答：

1. Python CSR action 优化后到底快了多少；
2. linear reduced map 是否比 nonlinear POD-MLP 更便宜、更稳定；
3. batched owner-local inference 是否真正减少 wall time；
4. exact/fused/periodic audit 各自成本和风险；
5. outer/inner operator action 次数是否下降；
6. h5 全局 wall time 是否至少改善 20%；
7. 若声称内存下降，哪个 ILU factor 被移除、实测下降多少；
8. full true residual、R/T/A、closure 是否保持；
9. 训练成本在单 RHS、多 RHS 和参数扫描下如何摊销；
10. 该路线应继续、停止，还是只保留 microkernel 基础设施。

只有以上证据完整，PARA-Task002 才允许进入最终审阅。
