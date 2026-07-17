# PARA-Task003：LU-Teacher NN-Only Local Inverse Feasibility for the Full-3D Maxwell Solver

## 0. 任务身份

```text
task = PARA-Task003
name = LU-Teacher NN-Only Local Inverse Feasibility for the Full-3D Maxwell Solver
status = planned / research-only continuation
execution_branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task002
predecessor_review = docs/para_task002_batched_neural_smoother_acceleration/review_report_v1.md
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

分支中新增或修改 Task003 相关代码、测试、benchmark 和文档。不得：

- 创建、切换、移动、重命名或删除分支；
- merge、rebase、cherry-pick、reset 或同步其他分支；
- pull、push、提交或合并到 `master`；
- 开 PR；
- 因当前分支落后或领先主线而主动改变分支历史；
- 将本任务解释为 production merge preparation。

若当前分支缺少其他路线的新基础设施，应在 outcomes 中记录限制，不得擅自同步。

---

# 1. 为什么启动本任务

PARA-Task001 与 PARA-Task002 已完成两条 **ILU-conditioned** 路线：

```text
PARA-Task001:
ILU(r_s) + nonlinear POD-MLP correction on ILU residual

PARA-Task002:
ILU(r_s) + fixed linear reduced correction on ILU residual
```

它们证明：

1. 学习模型能够改善选定 slab 的局部 residual；
2. Python CSR 和逐向量 nonlinear inference 可以显著优化；
3. 但由于原 ILU factor、ILU solve、两步 inner smoother 和大部分 slabs 全部保留，全局迭代变化很小；
4. 当前研究仍没有回答：

```text
NN 是否能够在完全不知道 ILU 输出的条件下，
独立学习 A_s^{-1} 的局部动作，
并真正替代 selected slab 的 ILU factor/solve？
```

PARA-Task002 Review V1 已明确要求下一轮改为：

```text
raw local residual r_s
-> frozen learned local inverse
-> z_s^NN ≈ A_s^{-1} r_s
```

teacher label 必须由高精度局部解产生，而不是来自：

```text
ILU output
ILU residual
ILU correction
current approximate PC output
```

因此 Task003 的核心研究问题是：

```text
在固定 h5 full-3D Maxwell local shifted-F slab operator 上，
高精度 sparse LU teacher 能否生成可控、可审计的训练数据，
使 NN-only / learned-only local inverse 在 independent real-Krylov RHS 上
达到或超过当前 ILU 的局部质量，
并在正式 runtime 中不构造 selected slab 的 ILU factor？
```

本 Task 是“独立替代可行性”任务，不是 16-slab rollout、通用模型或参数泛化任务。

---

# 2. 本任务的核心概念修正

## 2.1 “假装不知道 PC”是什么意思

训练和 selected local runtime 中，模型不得使用：

```text
z_ilu
r_s - A_s z_ilu
ILU factor statistics
ILU fill pattern
ILU output as teacher
current PC correction as teacher
```

模型只允许接收：

```text
raw local residual r_s
+ explicitly allowed operator/slab metadata
```

并输出：

```text
z_s^NN ≈ A_s^{-1} r_s
```

## 2.2 “假装不知道 PC”不是什么意思

不得删除或弱化：

- outer right FGMRES；
- 75D true-action coarse correction；
- exact condensed operator `F-C H^-1D`；
- physical slab partition、overlap、weights、owner assignment 和 MPI scatter；
- final condensed/full augmented true residual；
- official R/T/A、volume absorption 和 energy closure；
- benchmark provenance、memory sampler、watchdog 和 lifecycle；
- 其他未被选中的 slab 的当前 ILU baseline。

本任务只让 selected slab 的 local backend 暂时“看不到 ILU”。

---

# 3. 开始前必须读取

执行者必须完整读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/solver_guide.md
docs/iterative_solver_ports.md
docs/architecture_overview.md

docs/para_task001_neural_local_pc_acceleration/task.md
docs/para_task001_neural_local_pc_acceleration/outcomes/summary.md
docs/para_task001_neural_local_pc_acceleration/review_report_v1.md

docs/para_task002_batched_neural_smoother_acceleration/task.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/summary.md
docs/para_task002_batched_neural_smoother_acceleration/review_report_v1.md

benchmarks/cases/090_neural_local_pc_acceleration/README.md
benchmarks/cases/091_batched_neural_smoother_acceleration/README.md

src/solvers/local_slab_solver.py
src/solvers/neural_local_pc.py
src/solvers/batched_reduced_smoother.py
src/solvers/physical_slab_two_level.py
benchmarks/neural_pc/data_contract.py
benchmarks/neural_pc/petsc_capture.py
benchmarks/run_workstation_iterative.py
```

完成任务时必须维护：

```text
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/summary.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/changed_files.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/experiment_matrix.csv
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/teacher_resource_report.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/local_quality.csv
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/runtime_breakdown.csv
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/memory_report.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/model_and_dataset_provenance.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/decision.md
docs/development_progress.md
benchmarks/cases/092_lu_teacher_nn_only_local_inverse/
```

重型 artifacts 必须放在：

```text
benchmarks/artifacts/cases/092/
```

并保持 Git ignored。不得提交：

- LU factors；
- 大型 local CSR；
- 原始训练集；
- checkpoint；
- raw residual streams；
- full profiler；
- field/HDF5/XDMF/VTU；
- 完整求解日志。

---

# 4. 冻结物理与求解器基线

## 4.1 冻结物理问题

第一阶段继续使用：

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

不得同时改变波长、材料、几何、偏振、端口模式、粗空间、slab partition、overlap、outer KSP 或 operator action 路线。

## 4.2 冻结 global baseline

正式 A/B 必须在同一机器、同一 MPI4、同一 thread、同一 action 和同一 sampler 下成对运行：

```text
outer = right FGMRES90
physical slabs = 16
coarse = fixed 75D true-action Galerkin
local baseline = current shifted-F ILU0
smoother = current two-step path
```

历史 Task002 同轮参考仅用于 sanity：

```text
h5 FE DoF = 44,698
baseline iterations = 849
baseline solve = 151.343 s
baseline peak incl. RTA = 1.595348 GiB
```

正式结果必须重新运行，不能用历史数字代替本轮 A/B。

## 4.3 三个代表 slab

本 Task 最多研究三个独立、slab-specific 模型：

```text
slab 9  = first target; grating/interior representative
slab 0  = boundary representative; conditional
slab 10 = second interior representative; conditional
```

第一阶段只允许 slab 9。只有 slab 9 通过明确 Gate，才允许 slab 0/10。

本 Task 不训练：

- 16 个完整模型；
- 三专家模型；
- shared universal model；
- operator-conditioned cross-geometry model。

这些属于后续任务。

---

# 5. 高精度 LU teacher 合同

## 5.1 teacher 的数学身份

对 selected slab 的局部 shifted-F operator：

```math
A_s z_s^* = r_s
```

teacher label 为：

```math
z_s^* = A_s^{-1} r_s.
```

允许 teacher：

```text
sparse direct LU with pivoting/reordering
or tightly converged high-accuracy local KSP if LU becomes infeasible
```

Task003 第一选择必须是 sparse LU。

## 5.2 LU 资源生命周期

不得对每个样本重新 factorize。正确流程为：

```text
build one A_s
-> factorize once
-> solve many RHS using the same LU factor
-> verify teacher residuals
-> save bounded dataset/checksum/metadata
-> destroy LU factor
-> train model
```

三个 slab 必须逐个处理：

```text
factor slab 9 -> generate -> destroy
factor slab 0 -> generate -> destroy
factor slab 10 -> generate -> destroy
```

不得同时常驻三个 teacher LU factors。

## 5.3 teacher 资源必须记录

每个 slab 至少记录：

```text
matrix shape / nnz
ordering / pivot configuration
factorization time
factor nnz or solver-reported fill
fill ratio
factor storage estimate
external RSS before/after factor
cgroup current/peak
swap in/out
per-RHS triangular solve mean/p95
factor destroy confirmation
```

若出现 swap、OOM 风险或 factor 内存达到机器安全阈值，必须停止该 slab，不得继续堆叠数据。

## 5.4 teacher 数值 Gate

每个 teacher pair 必须满足：

```math
rho_{teacher}=
\frac{\|A_s z_s^*-r_s\|}{\|r_s\|}.
```

Gate：

```text
all finite
median rho_teacher <= 1e-11
p95 rho_teacher <= 1e-10
max rho_teacher <= 1e-9
```

不满足时不得用该 teacher dataset 训练正式模型。

---

# 6. Exact-LU oracle 上限实验

## 6.1 为什么必须先做 oracle

在训练 NN 之前，必须回答：

```text
如果 selected slab 使用真正的高精度 local inverse，
外层 FGMRES 到底能改善多少？
```

若 exact local LU 都几乎不改变全局迭代，那么任何近似该 LU 的 NN 也不太可能通过单-slab 路线带来显著全局加速。

## 6.2 slab-9 exact-LU oracle

正式 oracle profile：

```text
slab 9 = exact sparse LU local solve
other 15 slabs = current ILU
coarse / outer / smoother / operator = unchanged
```

必须记录：

```text
outer iterations
operator apply count
one-level apply count
PC apply count
solve / total wall time
local exact-LU apply time
full true residual
R/T/A and closure
peak memory
```

Oracle 的 wall time 不作为最终 NN 加速结果；它主要用于测量 **迭代/谱改善上限**。

## 6.3 oracle Gate

slab-9 单独进入模型训练的 global-signal Gate：

```text
numeric Gate pass
and outer iteration reduction >= 2%
```

若 slab-9 exact LU 的迭代下降 `<2%`：

1. 不立即训练 slab-9 大模型；
2. 允许做一次三代表 slab exact-LU oracle：slab 0/9/10 使用 exact LU；
3. 若三-slab exact-LU oracle 仍不能达到：

```text
outer iteration reduction >= 5%
```

则停止“少量 selected slabs NN-only”全局路线，保留 teacher/local feasibility 结果，不进入 active learned PC。

---

# 7. 数据生成合同

## 7.1 初始数据规模

slab-9 第一轮建议：

```text
train = 512 RHS
validation = 128 RHS
holdout active-like test = 64 RHS
```

可按 Gate 扩展至：

```text
train <= 2048
validation <= 512
```

不得在没有 learning-curve 证据时无上限增加样本。

## 7.2 RHS 类型

初始数据以高精度 LU teacher 为主，混合：

```text
real Krylov raw local RHS from independent baseline captures
restart-window RHS
stagnation / hard residual RHS
structured smooth random RHS
interface-localized RHS
boundary/overlap-localized RHS
wave-like local modes
multiple residual magnitude scales
```

所有正式标签都由 LU teacher 解：

```text
r_s -> z_s^* = LU_s(r_s)
```

允许将 `e -> A_s e` 作为额外 exact-pair diagnostic，但第一轮正式结论不能只依赖 synthetic `e -> Ae` 数据。

## 7.3 数据独立性

必须至少区分：

```text
capture A = training
capture B = validation
capture C = shadow/active distribution check
```

禁止在同一次 Krylov 流中随机切行后声称完全独立泛化。

## 7.4 数据标准化

必须记录：

```text
complex packing convention
residual norm scaling
zero/tiny RHS handling
basis normalization
output rescaling
slab local DoF ordering
operator fingerprint
```

归一化不得破坏输出的尺度一致性。

---

# 8. 模型 lanes

## 8.1 Lane A：learned linear inverse baseline（强制）

对于固定 `A_s`，映射：

```text
r_s -> A_s^{-1} r_s
```

本质是线性的。因此必须先实现一个 learned linear inverse baseline，例如：

```text
POD/SVD encoder U_s
reduced linear map W_s
POD/SVD decoder V_s
```

```math
z_s^{lin}=V_s W_s U_s^H r_s.
```

要求：

```text
no ILU conditioning
no nonlinear activation
no bias that breaks zero mapping
fixed frozen action
linearity error <= 1e-11
determinism error <= 1e-13
predict_many() support
```

## 8.2 Lane B：nonlinear NN-only local inverse

只有 Lane A 无法达到 local quality Gate，或 nonlinear 模型显示明确额外能力时，才训练：

```text
raw residual
-> reduced encoder
-> small MLP/residual network
-> reduced decoder
-> local correction
```

模型必须满足：

```text
zero RHS -> zero output within tolerance
frozen offline-trained checkpoint
no online update
no ILU input/label
single-vector and batch API
CPU runtime required
optional same-process GPU runtime benchmark
```

第一版允许 slab-specific model，作为固定 operator 能力上限实验，不得宣传为通用模型。

## 8.3 Lane C：operator-aware/GNN

本 Task 默认不进入。只有 slab-specific linear/MLP 明确失败且证据指向表示能力不足时，记录为后续研究建议，不在本 Task 扩展架构。

---

# 9. Loss 与模型选择

## 9.1 correction loss

```math
L_{corr}=
\frac{\|z_s^{model}-z_s^*\|^2}
{\|z_s^*\|^2+\delta}.
```

## 9.2 equation residual loss

```math
L_{res}=
\frac{\|A_s z_s^{model}-r_s\|^2}
{\|r_s\|^2+\delta}.
```

## 9.3 optional hard-mode weighting

可对以下样本增加权重：

```text
high ILU residual difficulty
restart/stagnation windows
interface-localized residuals
teacher solution with large amplification
```

但 ILU difficulty 只能用于评价/采样权重，不能作为 teacher 输出或模型输入。

## 9.4 模型选择标准

不得只根据 training/validation loss。正式模型必须按以下顺序选择：

1. teacher-independent local action Gate；
2. 与 current ILU 的 local residual 和时间比较；
3. shadow online distribution；
4. active factor-removal global A/B；
5. full true residual/RTA。

---

# 10. Local validation Gate

在 independent real-Krylov validation 上同时比较：

```text
exact LU teacher
current ILU
learned linear inverse
nonlinear NN-only (if run)
```

至少记录：

```text
rho median / p95 / max
relative correction error to teacher
inference mean / p95
model storage
temporary storage
linearity/determinism
out-of-distribution norm ranges
```

## 10.1 可行性 Gate

模型至少满足：

```text
all finite
determinism pass
rho_model_median <= rho_ILU_median
rho_model_p95 <= min(0.95, 1.05 * rho_ILU_p95)
```

## 10.2 强局部 Gate

建议目标：

```text
rho_model_median <= 0.80 * rho_ILU_median
rho_model_p95 <= 0.90 * rho_ILU_p95
```

## 10.3 时间 Gate

至少满足下列之一：

```text
A: model inference mean <= ILU solve mean
```

或：

```text
B: model median rho improves >=25%
and model inference mean <= 1.5 * ILU solve mean
```

若只提高精度但推理远慢于 ILU，应保留局部正结果，但不得进入 active global acceleration。

---

# 11. Runtime 阶段

## 11.1 P0：环境、基线与 capture

必须记录：

```text
git status / HEAD / branch
explicit no-branch-operation acknowledgement
Python/PETSc/DOLFINx/MPC/SciPy/PyTorch
CPU/GPU/MPI/thread
artifact root
```

运行：

- current h5 ILU baseline；
- bounded independent raw-local-RHS captures；
- unit/import smoke；
- `git diff --check`。

不得运行 h3/h2。

## 11.2 P1：slab-9 LU teacher resource feasibility

完成：

```text
extract exact local operator
factor once
verify teacher residual
measure fill/time/RSS
solve bounded RHS dataset
save provenance/checksum
release factor
```

P1 失败时，Task003 可分类为：

```text
teacher_resource_infeasible
```

并停止模型训练。

## 11.3 P2：exact-LU oracle

按第 6 节执行 single-slab，必要时执行 three-slab conditional oracle。

Oracle 不通过 global-signal Gate 时，禁止无目的训练大量模型。

## 11.4 P3：slab-9 offline model construction

强制顺序：

```text
learned linear inverse
-> local evaluation
-> nonlinear NN only if justified
```

不得使用 ILU-conditioned dataset。

## 11.5 P4：slab-9 shadow NN-only

shadow mode 同时计算：

```text
baseline ILU correction (comparison only)
NN-only correction from raw residual
exact local rho for both
```

但写回原 ILU。

P4 用于：

- 检查真实在线 residual distribution；
- 验证 NN-only 没有有害输出；
- 测量 inference/audit 开销；
- 比较 NN-only 与 ILU，而不是 ILU+NN。

shadow 中允许保留 ILU factor，因为它只用于比较，不作内存节约声明。

Gate：

```text
full true residual/RTA unchanged
no harmful NN output on accepted set
shadow overhead <=10% of baseline solve
online rho distribution consistent with offline validation
```

## 11.6 P5：slab-9 active NN-only with ILU fallback diagnostic

第一轮 active 可保留 ILU fallback，仅用于验证全局数值稳定性，但必须明确：

```text
this is not factor replacement
this cannot support memory-saving claim
```

Gate：

```text
full true residual <=1e-6
R/T/A delta <=1e-6
energy closure pass
fallback fraction <=1%
outer iterations not worse by >2%
```

只有 P5 通过，才允许真实 factor removal。

## 11.7 P6：slab-9 true factor removal

正式 replacement candidate 必须：

```text
selected slab ILU factor is not constructed
or is destroyed before outer solve
selected slab runtime uses only NN/learned inverse
no ILU fallback retained
exact local audit remains enabled
failure -> fail closed / abort candidate
```

必须在 object ledger 和 runtime diagnostics 中证明：

```text
selected slab factor absent
selected slab ILU apply count = 0
NN-only apply count > 0
```

P6 Global Gate：

```text
full augmented true residual <=1e-6
max official R/T/A delta <=1e-6
energy closure pass
outer iterations reduction >=2%
or solve time reduction >=5%
peak memory not worse by >5%
selected factor memory demonstrably removed
```

注意：单 slab 的全局 RSS 下降可能很小；至少必须证明 local factor 对象和估算存储已消失，且 external RSS 没被模型/CSR 副本完全抵消。

## 11.8 P7：slab 0/10 conditional

只有 slab-9 P6 通过，才允许依次对 slab 0、slab 10 重复：

```text
teacher resource
exact-LU oracle
independent model
shadow
active
factor removal
```

不得直接复制 slab-9 checkpoint。

三个模型都属于 slab-specific upper-bound 实验。

Three-slab Global Signal Gate：

```text
all three selected ILU factors absent
full residual/RTA/closure pass
outer iterations reduction >=5%
or solve time reduction >=10%
peak memory <= baseline +5%
```

P7 未通过时，不得创建 16-model rollout。

---

# 12. 为什么本 Task 不直接训练 16 个或通用模型

本 Task 的目的首先是建立能力上限和因果链：

```text
exact local inverse has global value?
-> teacher feasible?
-> learned inverse matches/exceeds ILU locally?
-> NN-only active solve stable?
-> factor removal real?
```

若直接训练 16 个模型失败，将无法区分：

- teacher/data 问题；
- 单 slab 模型能力不足；
- global spectral benefit不足；
- 多模型 runtime overhead；
- MPI imbalance；
- factor-removal integration错误。

若 Task003 的三个 slab-specific 模型成功，后续任务再比较：

```text
16 independent models = fixed-operator upper bound
3 expert models = class sharing
shared trunk + slab adapters = compressed shared model
```

本 Task 不提前决定最终模型数量。

---

# 13. 内存与资源合同

## 13.1 离线 teacher 内存

必须与在线 solver 内存分开报告：

```text
teacher factor memory
teacher dataset memory
training host memory
training GPU memory
checkpoint storage
```

teacher LU 在正式 NN-only runtime 前必须销毁，因此不得把 teacher factor 计入在线 candidate peak。

## 13.2 在线 candidate 内存

必须区分：

```text
model weights
input/output bases
local CSR/action copy
staging buffers
selected slab factor removed bytes
remaining 15/13 slab factors
Krylov/coarse/global objects
```

## 13.3 训练成本摊销

即使本 Task 主要验证可行性，也必须报告：

```text
teacher_factor_time
teacher_rhs_solve_time
training_time
setup_time
single_solve_time
```

并给出：

```math
T_{effective}(N)=T_{teacher}+T_{train}+T_{setup}+N T_{NN-solve}.
```

分别讨论：

- 单 RHS；
- 多 RHS；
- 参数扫描/反演。

不得无条件忽略 teacher 和训练成本。

---

# 14. Safety 与 fallback

## 14.1 shadow/diagnostic 阶段

允许 ILU comparator/fallback，但不得声称 factor replacement。

## 14.2 true factor-removal 阶段

selected slab 不得保留 ILU fallback。以下情况必须 fail closed：

```text
missing/corrupt checkpoint
operator fingerprint mismatch
NaN/Inf
abnormal output norm
exact local audit failure
MPI rank exception
runtime backend failure
global true residual abnormal growth
```

可以终止 candidate 并记录失败，不得静默恢复 ILU 后仍声称替代成功。

## 14.3 exact audit

Task003 初始阶段必须 every-call exact local audit：

```math
rho_s^{NN}=\frac{\|r_s-A_s z_s^{NN}\|}{\|r_s\|}.
```

periodic/proxy audit 不属于本 Task 的正式 acceleration candidate，除非另有独立证据和后续任务。

---

# 15. 测试要求

至少新增或更新：

1. sparse LU teacher residual Gate fixture；
2. one-factor/many-RHS teacher reuse test；
3. factor destroy lifecycle test；
4. raw residual/teacher label contract test；
5. explicit rejection of ILU-conditioned dataset metadata；
6. learned linear inverse linearity/determinism；
7. nonlinear NN zero-map/scaling sanity；
8. independent validation split contract；
9. NN-only local residual vs ILU comparison fixture；
10. exact-LU oracle local backend adapter；
11. shadow NN-only writes baseline ILU only；
12. active diagnostic fallback telemetry；
13. true factor-removal selected slab has no factor object；
14. fail-closed missing/corrupt/fingerprint mismatch；
15. MPI2 selected-slab owner backend smoke；
16. full h5 true residual/RTA integration Gate；
17. repeated apply/destroy no leak；
18. benchmark contract checker；
19. complete pytest suite；
20. Ruff/compileall/`git diff --check`。

测试不能使用一次随机收敛作为稳定性证据；所有 dataset/model seed、checksum、operator fingerprint 和 capture source 必须记录。

---

# 16. 禁止事项

本任务不得：

- 进行任何分支管理或 `master` 操作；
- 使用 ILU output 或 ILU residual 作为正式 teacher label；
- 把当前 PC 输出当作 ground truth；
- 在每个训练样本上重新 factorize LU；
- 同时常驻多个大型 teacher LU factors；
- 在线训练或更新权重；
- 用训练 loss 代替 local residual Gate；
- 用 local rho 代替 full global true residual；
- 在 factor-removal candidate 中保留隐藏 ILU fallback；
- ILU factor 未移除时声称 memory saving；
- oracle 没有 global signal 时仍盲目训练 16 个模型；
- 直接训练一个无 operator/slab 信息的“通用网络”覆盖不同 `A_s`；
- 未通过 h5 Gate 运行 h3/h2；
- 提交大型 LU/data/checkpoint/artifacts；
- 宣称 mesh-independent、parameter-general 或 production-ready。

---

# 17. 建议代码与 benchmark 路径

建议职责分离为：

```text
src/solvers/lu_teacher_local_solver.py
src/solvers/nn_only_local_inverse.py

benchmarks/neural_pc/build_lu_teacher_dataset.py
benchmarks/neural_pc/evaluate_exact_lu_oracle.py
benchmarks/neural_pc/train_nn_only_local_inverse.py
benchmarks/neural_pc/evaluate_nn_only_local_inverse.py
benchmarks/run_nn_only_local_inverse.py

benchmarks/cases/092_lu_teacher_nn_only_local_inverse/

src/test/test_35_lu_teacher_contract.py
src/test/test_36_nn_only_local_inverse.py
src/test/test_37_para_task003_contract.py
```

文件名可调整，但必须保持：

```text
teacher generation
model training
runtime backend
benchmark orchestration
```

彼此分离。

---

# 18. 交付物

代码/轻量配置至少包括：

```text
LU teacher dataset schema
teacher provenance/checksum
exact-LU oracle runner/profile
raw-residual learned inverse model
NN-only runtime backend
selected factor-skip/removal port
local/global telemetry
Case092 config/expected/README/run entry
unit + MPI smoke tests
```

outcomes 至少包括：

```text
summary.md
changed_files.md
experiment_matrix.csv
teacher_resource_report.md
local_quality.csv
runtime_breakdown.csv
memory_report.md
model_and_dataset_provenance.md
decision.md
```

---

# 19. 最终分类

最终 classification 必须从以下选择：

```text
three_slab_nn_only_speed_and_memory_positive
single_slab_nn_only_factor_replacement_positive
nn_only_local_feasibility_only
exact_lu_oracle_global_signal_insufficient
teacher_feasible_model_quality_failure
teacher_resource_infeasible
numeric_failure
performance_failure
not_feasible_with_current_runtime_architecture
```

含义：

- `single_slab_nn_only_factor_replacement_positive`：至少一个 selected slab 真正移除 ILU，数值通过并有明确全局/内存正信号；
- `three_slab_nn_only_speed_and_memory_positive`：三个代表 slab 都完成独立替代且达到 three-slab Gate；
- `nn_only_local_feasibility_only`：局部 NN-only 达到/超过 ILU，但全局信号不足；
- `exact_lu_oracle_global_signal_insufficient`：连 exact local inverse 都不能为 selected slabs 带来足够全局收益；
- 其他分类按字面记录真实失败边界。

所有结果仅属于当前 research branch，不讨论合并，不改变 ordinary default。

---

# 20. 最短执行顺序

```text
P0  reproduce h5 baseline + independent captures
-> P1 slab-9 sparse LU teacher resource/accuracy
-> P2 slab-9 exact-LU global oracle
-> conditional three-slab exact-LU oracle if needed
-> Gate
-> P3 slab-9 learned linear inverse
-> conditional nonlinear NN-only
-> P4 slab-9 shadow NN-only
-> P5 slab-9 active diagnostic with fallback
-> P6 slab-9 true factor removal
-> Gate
-> P7 slab 0/10 conditional repetition
-> final review
```

不得跳步。

---

# 21. 任务完成标准

Task003 不能以“LU 能生成数据”“模型 loss 下降”或“代码可运行”完成。至少必须回答：

1. slab-9 sparse LU factorization 的时间、fill 和峰值资源是多少；
2. 一次 factor、多 RHS teacher reuse 是否稳定；
3. teacher residual 是否达到高精度 Gate；
4. exact-LU oracle 对 single slab / three slabs 的 outer iteration 上限改善是多少；
5. learned linear inverse 和 nonlinear NN-only 谁更准确、更快；
6. NN-only 是否在 independent real-Krylov RHS 上达到或超过 ILU；
7. shadow/active residual distribution 是否发生 OOD 漂移；
8. selected slab 的 ILU factor 是否真正没有构造/已销毁；
9. NN-only active candidate 是否保持 full true residual、R/T/A 和 closure；
10. factor removal 后内存是否真实下降或至少未被模型/CSR 抵消；
11. single-slab 与 three-slab global signal 是否足以支持后续 16-model/expert/shared-model研究；
12. teacher/training 成本在单 RHS、多 RHS和反演中的摊销是否合理。

只有以上证据完整，PARA-Task003 才允许进入最终审阅。
