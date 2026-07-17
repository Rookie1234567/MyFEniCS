# PARA-Task004：Full 16-Slab Exact-Local-Inverse Oracle and Learned-PC Go/No-Go Decision

## 0. 任务身份

```text
task = PARA-Task004
name = Full 16-Slab Exact-Local-Inverse Oracle and Learned-PC Go/No-Go Decision
status = planned / research-only continuation
execution_branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task003
predecessor_review = docs/para_task003_lu_teacher_nn_only_local_inverse/review_report_v1.md
remote_repository = Rookie1234567/MyFEniCS
reference_wavelength = 13.5 nm
reference_geometry = current validated full-3D periodic Si block grating
reference_discretization = p2 Nedelec hexahedral FEM
reference_parallelism = MPI4 for formal h5 A/B
ordinary_default_changed = false
production_claim_allowed = false
model_training_allowed = false in this task
branch_management = prohibited by explicit user instruction
master_operations = prohibited by explicit user instruction
```

### 0.1 分支操作禁令

本任务只允许在现有：

```text
ChatGPT/20260715-para-task-neural-local-pc
```

分支中新增或修改 Task004 相关代码、测试、benchmark 和文档。不得：

- 创建、切换、移动、重命名或删除分支；
- merge、rebase、cherry-pick、reset 或同步其他分支；
- pull、push、提交或合并到 `master`；
- 开 PR；
- 因当前分支与其他分支存在差异而主动改变分支历史；
- 把本任务解释为 production merge preparation。

若当前分支缺少其他路线的新基础设施，应在 outcomes 中记录限制，不得擅自同步。

---

# 1. 为什么启动本任务

PARA-Task003 已建立高精度 sparse-LU teacher 和 exact-local-inverse oracle，并得到：

```text
P0 ILU baseline:
iterations = 860

slab 9 exact LU:
iterations = 862
reduction = -0.23%

slab 0/9/10 exact LU:
iterations = 840
reduction = 2.33%
```

因此 Task003 正确停止了少量 selected-slab NN-only 训练路线。

但 Task003 的结论范围只覆盖：

```text
1 个 exact slab
3 个 exact slabs
```

它没有回答：

```text
当全部 16 个 physical slabs 都使用 exact local inverse 时，
当前 two-level FGMRES 架构的 outer spectrum、operator actions 和 smoother 成本
最多能改善多少？
```

如果全部 16 个 local inverse 达到 exact 精度仍没有明显全局收益，那么：

```text
训练 16 个独立 NN-only models；
训练三类 expert models；
训练 shared trunk + slab adapters；
```

都缺乏可信的局部逆上限依据，研究应转向 coarse/deflation/global modes，而不是继续局部 inverse learning。

如果 full 16-slab exact oracle 显著改善 outer iterations 或允许 one-step smoother 大幅减少 operator actions，则说明：

```text
少量 slab 杠杆不足；
all-slab replacement 具有全局理论上限；
后续训练 16 个模型或共享模型才有因果依据。
```

因此 Task004 是一个 **训练前的全局上限与架构决策任务**。本 Task 不训练任何模型。

---

# 2. Task003 对本任务的强制结论

执行者必须接受以下冻结事实，不得重复争论或选择性忽略：

1. h5 slab-9 sparse-LU teacher 资源可行，teacher residual 约 `1e-14`；
2. raw RHS capture 可以不保存 ILU output/residual；
3. selected exact-LU owner backend 数值路径正确；
4. one-slab exact oracle 没有全局正信号；
5. three-slab exact oracle 只有 2.33% iteration reduction；
6. Task003 oracle profile 保留了原 ILU factors，因此其内存不是 replacement 内存；
7. Task003 正确没有进入 learned model training；
8. 当前唯一未回答的 local-inverse 上限问题是 full 16-slab replacement。

本任务不得重新训练 slab 9，也不得继续调 Task001/002 的 POD rank、MLP hidden width 或 ILU-residual correction。

---

# 3. 开始前必须读取

执行者必须完整读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/solver_guide.md
docs/iterative_solver_ports.md
docs/architecture_overview.md

docs/para_task001_neural_local_pc_acceleration/outcomes/summary.md
docs/para_task001_neural_local_pc_acceleration/review_report_v1.md

docs/para_task002_batched_neural_smoother_acceleration/outcomes/summary.md
docs/para_task002_batched_neural_smoother_acceleration/review_report_v1.md

docs/para_task003_lu_teacher_nn_only_local_inverse/task.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/summary.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/teacher_resource_report.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/runtime_breakdown.csv
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/memory_report.md
docs/para_task003_lu_teacher_nn_only_local_inverse/review_report_v1.md

benchmarks/cases/092_lu_teacher_nn_only_local_inverse/README.md
src/solvers/local_slab_solver.py
src/solvers/lu_teacher_local_solver.py
src/solvers/physical_slab_two_level.py
src/solvers/sparse_galerkin_two_level.py
benchmarks/run_workstation_iterative.py
```

完成任务时必须维护：

```text
docs/para_task004_full_16_slab_exact_oracle/outcomes/summary.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/changed_files.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/experiment_matrix.csv
docs/para_task004_full_16_slab_exact_oracle/outcomes/oracle_ladder.csv
docs/para_task004_full_16_slab_exact_oracle/outcomes/factor_lifecycle_report.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/runtime_breakdown.csv
docs/para_task004_full_16_slab_exact_oracle/outcomes/memory_report.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/operator_action_report.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/learned_runtime_budget.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/decision.md
docs/development_progress.md
benchmarks/cases/093_full_16_slab_exact_oracle/
```

重型 artifacts 必须放在：

```text
benchmarks/artifacts/cases/093/
```

并保持 Git ignored。不得提交：

- sparse-LU factors；
- local CSR matrices；
- full solver records with large histories；
- raw fields；
- HDF5/XDMF/VTU；
- profiler dumps；
- raw MPI logs。

Git 中只提交轻量 JSON/CSV 摘要、checksum、配置、测试 fixture 和必要文档。

---

# 4. 冻结物理与数值基线

## 4.1 物理问题

第一阶段固定：

```text
wavelength = 13.5 nm
material = current validated complex Si optical constant
periodic cell = 50 x 25 x 140 nm
Si block = 17 x 25 x 120 nm
incidence = theta=80 deg, phi=0 deg, S polarization
periodicity = double Floquet in x/y
ports = current 80 auxiliary Fourier-DtN unknowns
finite element = p2 Nedelec hexahedral
mesh = h5
formal MPI = 4 ranks
```

不得改变：

- 波长、材料、几何、偏振；
- DtN mode 定义；
- 16-slab partition、overlap、weights 和 owner assignment；
- 75D coarse basis；
- right FGMRES90；
- official R/T/A 和 volume absorption；
- baseline fine/condensed operator action；
- thread 数和 memory sampler。

## 4.2 正式 baseline

Task004 必须从 clean Task004 implementation HEAD 重新成对运行 baseline/candidate：

```text
outer = right FGMRES90
physical slabs = 16
local baseline = shifted-F ILU0
smoother = current two-step path
coarse = fixed 75D true-action Galerkin
MPI = 4
OMP/BLAS threads = 1
```

历史数字只用于 sanity：

```text
Task003 baseline iterations = 860
Task003 baseline solve = 104.725 s
Task003 baseline peak incl. RTA = 1.595139 GiB
```

不得直接把 Task003 dirty-worktree wall time 当作 Task004 正式 baseline。

---

# 5. 核心研究问题

本任务必须回答：

1. exact-enabled slabs 能否在 setup 阶段真正跳过 ILU factorization？
2. full 16-slab exact profile 是否满足 `ILU factor count = 0` 和 `ILU apply count = 0`？
3. 从 4 到 8 到 16 exact slabs，outer iterations 是否出现可解释的单调或趋势性改善？
4. full 16-slab exact inverse 对 outer iterations 的最大改善是多少？
5. current two-step smoother 中，exact local inverse 是否被重复调用而浪费？
6. one-step exact Schwarz 是否可以减少 inner/operator actions，同时保持数值正确？
7. no-hidden-ILU exact profile 的 host memory、factor storage 和 rank imbalance 如何？
8. 若未来用 learned model 替代 exact LU，每次 local inference 必须快到什么程度，才能获得至少 20% global solve-time reduction？
9. full 16-slab oracle 是否足以解锁后续 16-model/expert/shared-model 任务？
10. 若 full 16-slab oracle 仍无信号，研究是否应转向 learned coarse/deflation/global error modes？

---

# 6. 关键基础设施修正：No-Hidden-ILU Backend Planning

## 6.1 Task003 当前限制

Task003 的 selected exact backend 虽然替换了 runtime local action，但原 smoother setup 仍构造并保存 ILU factors。因此正式 oracle 内存为：

```text
existing ILU factors
+ selected sparse-LU factors
```

这不是真正 replacement profile。

## 6.2 Task004 必须先决定 backend，再决定 factorization

应新增稳定 abstraction，名称可调整，但职责必须类似：

```python
@dataclass(frozen=True)
class LocalBackendPlan:
    identity: str
    requires_ilu_factor: bool
    requires_portable_operator: bool
    allows_fallback: bool
```

setup 顺序必须变为：

```text
resolve slab backend plan
-> if backend requires ILU: build ILU factor
-> if backend is exact oracle: skip ILU factor entirely
-> construct selected backend
```

不得继续：

```text
先构造 ILU factor
-> 再用 exact backend 覆盖 action
```

## 6.3 普通默认路径必须保持不变

未传显式 Task004 oracle flags 时：

```text
all current ILU setup/action/lifecycle = unchanged
```

Task004 infrastructure 不得改变 ordinary solver default、Task030/031 profile 或现有 neural/reduced research flags 的默认行为。

## 6.4 强制 diagnostics

每个 slab 必须记录：

```text
slab_id
owner_rank
backend_identity
requires_ilu_factor
ilu_factor_constructed
ilu_factor_nnz
ilu_factor_storage_estimate
ilu_apply_count
exact_factor_constructed
exact_factor_nnz
exact_factor_storage_bytes
exact_apply_count
factorization_s
apply_elapsed_s
apply_mean_s
apply_p95_s
destroyed
```

root record 必须汇集所有 MPI ranks 的 16 个 slab diagnostics，不得再缺失 non-root local timing。

Full 16-slab exact profile 的硬合同：

```text
exact_backend_count = 16
ilu_factor_constructed_count = 0
global_stored_ilu_factor_nnz = 0
ilu_apply_count = 0
hidden_fallback_count = 0
```

任一不满足，正式 oracle profile fail closed。

---

# 7. Exact Oracle 梯度

## 7.1 为什么使用 4/8/16 梯度

Task003 已有 1/3-slab 结果，但 selected set 不足以显示 all-slab scaling。Task004 使用预先冻结、嵌套、空间分布较均衡的集合，避免运行后挑选有利 slabs。

冻结集合：

```text
G4  = {0, 5, 10, 15}
G8  = {0, 2, 5, 7, 8, 10, 13, 15}
G16 = {0, 1, 2, ..., 15}
```

这些集合必须在运行前写入 Case093 config，不得根据结果修改。Task003 的 `{9}` 与 `{0,9,10}` 结果作为独立历史点保留，不与 G4/G8 严格合并为同轮 A/B。

若当前实际 slab 编号或 partition 与冻结 h5 合同不一致，任务应 fail closed 并记录，不得自动重选集合。

## 7.2 每个梯度点的共同配置

除 exact slab allow-list 外，必须保持：

```text
same h5 mesh
same MPI4
same thread settings
same operator action
same coarse basis
same overlap/weights
same outer FGMRES/restart/rtol
same two-step smoother
same monitor stride
same memory sampler
```

## 7.3 G4/G8 的目的

G4/G8 不是最终 qualification，而是诊断：

- iteration reduction 是否随 exact slab 数增加；
- exact factor memory 是否与预测一致；
- owner imbalance 是否出现；
- exact apply cost是否集中在某 rank；
- full G16 运行前是否存在资源或数值风险。

只要 numeric/resource Gate 通过，即使 G4/G8 无性能信号，也应继续 G16；本任务的核心问题是 full 16-slab oracle。

---

# 8. 两条正式 Oracle Lane

## 8.1 Lane A：Full 16-Slab Exact + Current Two-Step Smoother

配置：

```text
all 16 slabs = exact sparse-LU local inverse
all 16 slab ILU factors = not constructed
smoother_iterations = 2
post_smooth = current frozen setting
coarse = fixed 75D
outer = right FGMRES90
```

目的：测量在现有架构完全不改变时，local inverse 精度的最大 outer-iteration 上限。

必须记录：

```text
outer iterations
outer operator apply count
inner/action operator apply count
PC apply count
one-level apply count
per-slab exact apply count
solve / total wall time
factorization setup time
full true residual
R/T/A and closure
peak RSS / swap
```

Exact-LU wall time不是未来 NN wall time，但必须如实记录，用于分离：

```text
iteration benefit
vs
oracle implementation cost
```

## 8.2 Lane B：Full 16-Slab Exact + One-Step Smoother

只有 Lane A numeric pass 且资源安全后运行。

配置：

```text
all 16 slabs = exact sparse-LU local inverse
all ILU factors = absent
smoother_iterations = 1
coarse / outer / operator = unchanged
```

目的：测试一次强 local Schwarz action 是否可以替代 current two-step smoother，减少真实 Maxwell/inner action 数量。

必须比较：

```text
outer iterations
outer + inner operator actions
one-level applies
per-iteration cost
solve wall time
full residual/RTA
```

Lane B 不要求 outer iterations 一定低于 Lane A；关键是总 operator actions 和 projected learned-runtime potential。

## 8.3 不测试的 Lane

本任务不得测试：

- nonlinear NN；
- learned linear inverse；
- 16 个 checkpoint；
- shared model；
- online training；
- learned coarse；
- no-coarse profile；
- h3/h2；
- 不同 overlap、slab 数或 coarse dimension。

这些会破坏 oracle 因果隔离。

---

# 9. 资源预检与安全 Gate

## 9.1 全 16-slab factor census

正式 global solve 前，必须对 16 个 local operators 记录：

```text
shape
matrix nnz
operator fingerprint
owner rank
factorization time
L/U nnz
fill ratio
factor storage bytes
RSS delta during factor
factor destroy test
```

预检可以逐 slab factorize/destroy，以获得资源预测；正式 G4/G8/G16 solve 则按对应 allow-list 保持 exact factors 常驻。

## 9.2 Per-rank 预测

根据 owner assignment 计算：

```text
predicted exact factor bytes per rank
predicted maximum worker rank
predicted global sum
predicted setup time
```

正式 G16 前必须给出：

```text
predicted_peak_worker_rss
warning_threshold
stop_threshold
available_memory
swap status
```

安全要求：

- predicted peak 不得超过可用物理内存的 50%；
- warning/stop threshold 必须显式写入 record；
- 运行期间 swap in/out 必须为 0；
- OOM、swap 或 worker RSS 越过 stop threshold 时立即停止；
- 不得通过扩大 WSL swap 掩盖不可行性。

## 9.3 Factor 生命周期

正式 solve 后必须：

```text
destroy all exact factors
collect per-rank destroy diagnostics
confirm no repeated destroy error
record RSS after destroy
```

RSS 不完全回落可以由 allocator cache 解释，但 solver object 必须不可再调用并通过 lifecycle test。

---

# 10. 数值 Gate

每个 G4/G8/G16 和 Lane B 正式运行必须满足：

```text
KSP converged reason > 0
reported relative residual <= 1e-6
condensed true residual <= 1e-6
full augmented true residual <= 1e-6
max official R/T/A delta from same-run baseline <= 1e-6
energy closure within current benchmark Gate
all outputs finite
no hidden fallback
```

任一 numeric Gate 失败：

```text
stop current lane
preserve negative evidence
do not continue to learned-PC decision
```

---

# 11. Global Oracle Signal Gate

## 11.1 主要指标

Oracle 的主要指标不是 exact-LU wall time，而是：

```text
outer iteration reduction
outer/inner operator action reduction
one-level apply reduction
```

因为未来 learned action 可能远快于 sparse LU，但不能突破 exact local inverse 的谱质量上限。

## 11.2 Lane A：Two-Step All-Exact Signal

相对同轮 ILU baseline：

### Strong Signal

```text
outer iteration reduction >= 40%
```

### Positive Signal

```text
outer iteration reduction >= 20%
```

### Weak / Review-Required Signal

```text
10% <= outer iteration reduction < 20%
```

### No Signal

```text
outer iteration reduction < 10%
```

Lane A 的 G4/G8 趋势只作机制解释，最终 classification 以 G16 为主。

## 11.3 Lane B：One-Step Architecture Signal

Lane B 相对同轮 ILU two-step baseline满足以下任一，可视为 positive architecture signal：

```text
A. total outer+inner operator actions reduction >= 25%
   and outer iterations increase <= 10%
```

或：

```text
B. solve wall time reduction >= 20%
   and numeric Gate pass
```

由于 exact LU 本身可能较慢，A 是更主要的 future-learned-PC 上限指标。

## 11.4 后续 learned-PC 解锁条件

只有满足以下至少一项，最终 review 才可建议后续 Task005 训练：

```text
Lane A G16 outer iteration reduction >= 20%
```

或：

```text
Lane B operator action reduction >= 25%
with outer iterations increase <= 10%
```

若只有 10%–20% 的弱信号：

```text
automatic training remains locked
requires explicit ChatGPT review and user decision
```

若 G16 two-step <10%，且 one-step action reduction <25%：

```text
stop local-inverse learning route
recommend learned coarse / deflation / global correction research
```

---

# 12. Learned Runtime Budget

本任务虽不训练模型，但必须根据 baseline/oracle telemetry 计算未来 learned action 的预算。

至少给出：

```text
baseline solve time
baseline non-local time estimate
baseline ILU local apply accumulated time
G16 two-step apply count
G16 one-step apply count
operator action savings
```

推导未来 learned local action 最大允许平均时间：

```math
T_{learned,max}
```

使 projected solve time 至少比 baseline 下降 20%。

分别给出：

```text
per-slab independent model budget
per-owner batched model budget
all-rank synchronized critical-path budget
```

必须说明该预算是预测，不是实测 NN 性能。

训练成本、checkpoint 大小和泛化不在本 Task 中估算为已知事实。

---

# 13. 内存评估合同

必须区分：

```text
baseline ILU factor storage
exact factor storage
portable CSR storage
PETSc/local matrix storage
Krylov vectors
coarse objects
staging buffers
Python/SciPy allocator cache
```

正式 no-hidden-ILU G16 profile必须报告：

```text
removed ILU factor nnz/estimated bytes
exact factor nnz/bytes
net factor storage change
external simultaneous worker RSS
maximum rank RSS
swap in/out
```

注意：

- exact factor 比 ILU 大不代表未来 NN 一定更占内存；
- exact oracle 内存主要用于测量 replacement lifecycle 和未来 model-storage budget；
- 不得把 exact factor memory 直接称为 neural model memory；
- 不得在没有 checkpoint 的情况下声称 NN memory saving。

`learned_runtime_budget.md` 中应同时给出未来 learned model 的 host-storage 上限：

```text
model + basis + buffers
<= removed ILU storage
```

作为 memory-neutral 参考预算。

---

# 14. 性能与 MPI 诊断

每个正式 run 必须汇集所有 ranks 并拆分：

```text
system assembly
coarse setup
ILU factorization or exact factorization
local gather/scatter
local exact solve
inner/operator action
coarse apply
FGMRES orthogonalization if available
MPI wait / rank imbalance
RTA postprocessing
```

至少记录：

```text
mean / median / p95 / max
call counts
owner rank
per-slab factor/apply timing
critical rank time
outer iterations
operator apply counts
solve / total wall time
peak RSS / swap
```

不得只记录 root-owned slabs；non-root slab diagnostics 必须 gather。

---

# 15. 实施阶段

## P0：环境与同轮 baseline

1. 记录 branch、HEAD、remote、dirty status；
2. 明确记录不执行分支操作；
3. 记录 WSL、Python、PETSc、DOLFINx、MPC、SciPy、CPU、memory、MPI/thread；
4. 从 clean Task004 implementation HEAD 运行 h5 ILU baseline；
5. full residual/RTA/memory pass；
6. 运行现有 full unit suite 和 diff check。

P0 失败不得继续。

## P1：No-hidden-ILU backend planning

1. 实现 backend plan；
2. exact slab setup 跳过 ILU；
3. ordinary default path equivalence；
4. selected exact slab `ilu_factor_constructed=false`；
5. MPI2 owner test；
6. 16-slab diagnostics gather test；
7. repeated destroy/no leak test。

P1 Gate：

```text
numeric action equivalence <= 1e-12
ordinary ILU path unchanged
selected exact path no hidden ILU
all diagnostics complete
```

## P2：16-slab factor census

逐 slab测量资源，建立 per-rank predictor和 watchdog。不得直接盲跑 G16。

P2 Gate：

```text
all factors finite and solvable
all local exact residuals <= 1e-11 on test RHS
predicted G16 peak within safety threshold
swap = 0
```

## P3：G4 two-step oracle

运行冻结 G4。主要用于基础设施和趋势诊断。

## P4：G8 two-step oracle

运行冻结 G8。主要用于 scaling 和 rank imbalance 诊断。

## P5：G16 two-step oracle

这是 Task004 的主要 oracle。必须完成 numeric、iteration、action 和 memory evidence。

## P6：G16 one-step oracle

Lane A numeric pass 且资源安全后运行。比较 operator action reduction 与 outer iteration变化。

## P7：决策与文档

根据第 11 节 Gate 分类：

```text
all_slab_oracle_strong_signal
all_slab_oracle_positive_signal
all_slab_oracle_weak_signal
all_slab_oracle_no_signal
numeric_failure
resource_infeasible
infrastructure_incomplete
```

本 Task 不自动开始训练。即使 oracle positive，也只写出后续 Task005 推荐，不创建模型或 checkpoint。

---

# 16. 测试要求

至少新增或更新：

1. backend plan 在 exact slab 上跳过 ILU factor；
2. ordinary ILU path setup/action equivalence；
3. exact local solve residual test；
4. no-hidden-fallback test；
5. full-exact profile global ILU factor nnz = 0 contract；
6. per-rank diagnostics gather test；
7. G4/G8/G16 allow-list contract；
8. one-step/two-step apply-count contract；
9. MPI2 owner-computes exact backend；
10. repeated apply/destroy lifecycle；
11. factor census JSON/CSV schema；
12. memory predictor/warning/stop threshold test；
13. h5 G4/G8/G16 full residual/RTA integration records；
14. current full unit suite；
15. benchmark contract checker；
16. Ruff / compileall / `git diff --check`。

性能测试不得硬编码绝对秒数到 unit test；正式 Gate 使用 benchmark records。

---

# 17. 禁止事项

本任务不得：

- 执行任何分支管理或 `master` 操作；
- 训练 neural/linear/shared/expert model；
- 生成或提交 checkpoint；
- 使用 Task003 dirty wall time 替代同轮 baseline；
- 对 exact slab 先构造 ILU 再覆盖 action；
- 为正式 G16 profile保留隐藏 ILU fallback；
- 每次 local apply 重新 factorize LU；
- 根据中间结果修改 G4/G8 集合；
- 改变 slab partition、overlap、coarse dimension、物理参数或 outer solver；
- 用 local residual 替代 full global residual；
- 用 exact-LU wall time直接推断 NN wall time；
- 将 exact factor memory称为 NN memory；
- 在 h5 oracle Gate 前运行 h3/h2；
- 把 positive oracle 称为已实现 neural acceleration；
- 把 negative oracle 外推为所有 learned preconditioner 都无效；
- 提交大型 factor、matrix、field 或 raw profiler artifacts。

---

# 18. 交付物

建议代码路径：

```text
src/solvers/physical_slab_two_level.py
src/solvers/local_backend_plan.py or equivalent
src/solvers/lu_teacher_local_solver.py
benchmarks/neural_pc/benchmark_all_slab_exact_oracle.py
benchmarks/run_workstation_iterative.py
benchmarks/cases/093_full_16_slab_exact_oracle/
src/test/test_38_local_backend_plan.py
src/test/test_39_all_slab_exact_oracle_contract.py
src/test/test_40_exact_oracle_diagnostics_mpi.py
```

文件名可以调整，但职责必须清楚。

任务文档至少包括：

```text
outcomes/summary.md
outcomes/changed_files.md
outcomes/experiment_matrix.csv
outcomes/oracle_ladder.csv
outcomes/factor_lifecycle_report.md
outcomes/runtime_breakdown.csv
outcomes/memory_report.md
outcomes/operator_action_report.md
outcomes/learned_runtime_budget.md
outcomes/decision.md
review_report_vN.md / response_vN.md
```

Case093 至少包含：

```text
README.md
config.json
expected.json
run.sh
records/ lightweight summaries
```

---

# 19. 最终分类与下一步边界

## 19.1 Strong/Positive

若：

```text
G16 two-step iteration reduction >= 20%
```

或：

```text
G16 one-step operator action reduction >= 25%
且 outer iterations increase <= 10%
```

则 Task004 可分类为 positive/strong oracle signal。最终 review 可以建议新的 Task005，但 Task004 本身不得训练。

Task005 再决定：

```text
16 个独立 learned inverse 上限实验
vs
3 类 expert models
vs
shared trunk + slab-specific adapters
```

## 19.2 Weak

若 G16 iteration reduction 为 10%–20%，或 one-step 接近但未达到 action Gate：

```text
classification = all_slab_oracle_weak_signal
```

不得自动解锁训练，必须由 ChatGPT review 和用户显式决定。

## 19.3 No Signal

若：

```text
G16 two-step iteration reduction < 10%
且
G16 one-step operator action reduction < 25%
```

则：

```text
classification = all_slab_oracle_no_signal
```

停止 local-inverse learning 主路线。推荐后续研究：

```text
learned coarse basis
learned deflation vectors
global low-rank correction
cross-slab error modes
operator-action acceleration
```

不得继续训练 16 个 local inverse models 来绕过 oracle 结论。

---

# 20. 任务完成标准

Task004 不能以“代码可运行”完成。必须完整回答：

1. exact-enabled slab 是否真正没有 ILU factor？
2. 4/8/16 exact slab 的 iteration 趋势是什么？
3. full 16-slab exact inverse 的 outer iteration上限是多少？
4. one-step exact smoother 能否减少 operator actions？
5. no-hidden-ILU replacement 的内存和 rank imbalance 是什么？
6. exact factors 的 setup/apply 成本如何分布？
7. 未来 learned action 为实现 20% global speedup必须多快？
8. 未来 learned model 为 memory-neutral 最多可以占多少存储？
9. full residual、R/T/A 和 closure 是否保持？
10. 下一步应训练 16 个模型、研究共享模型，还是停止 local inverse 路线？

只有上述证据完整，PARA-Task004 才允许进入最终审阅。